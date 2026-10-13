#!/usr/bin/env python3
"""One-shot, archive-first GitHub branch cleanup.

Run only from the repository's explicitly approved, main-branch workflow.
Uses REST contents:write token. Does not rewrite any commit, merge, or touch V5.
All 10 heads are SHA-pinned and archived as immutable tags before deletion.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

REPOSITORY = "leaves899/fabric-vision-recognition"
ARCHIVE_PREFIX = "archive/2026-10-13"
KEEP = {"main", "experiment/v15-fft-acf-v4"}
RETIRE = {
    "experiment/v5-new-reviewed-annotations-round2": "71eafbe562181a43f297b5d379ff872f87c512b0",
    "experiment/v5-reviewed-sample-baseline": "c2f8c1a63e54a532b54698f0651684a823ed7699",
    "experiment/v15-fft-acf-v3": "6db3363351c4155b6311b7bee623f8357298fed5",
    "experiment/v15-reflectance-engine": "5ae42d6b2bd95161a3f2509d107df8f00b1737a7",
    "feature/public-photo-intake-v01": "75774e1431e4535a2c4b66b1c298d8d54c0ed29d",
    "feature/public-photo-intake-v02": "823c10b099e353cfb2b2df9cc351b132b0e68c44",
    "feature/step0-benchmark-framework": "c523340df7c4deaab0f71d96be22bf1778590261",
    "feature/v5-manual-yarn-reference-batch": "efa465e5b8f1067f641ed6c76ec867ba22131f64",
    "fix/anchored-yarn-center-phase-v06": "9fb5d9bd83fbc919d488802212167e68f734fd5d",
    "fix/v61-physical-yarn-duplicate-guard": "ecfa3880f857abf87b145dedd425e45fa676adea",
}
API = "https://api.github.com/repos/" + REPOSITORY
TOKEN = os.environ.get("GITHUB_TOKEN", "")
RESULT_PATH = Path("branch_cleanup_result.json")


def call(method: str, path: str, data=None, missing_ok=False):
    if not TOKEN:
        raise RuntimeError("GITHUB_TOKEN is required")
    body = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        API + path, data=body, method=method,
        headers={"Authorization": "Bearer " + TOKEN,
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "User-Agent": "fabric-vision-safe-branch-archive",
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as res:
            raw = res.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        if missing_ok and exc.code == 404:
            return None
        details = exc.read().decode("utf-8", errors="replace")[:350]
        raise RuntimeError(f"{method} {path}: HTTP {exc.code}: {details}") from None


def ref_uri(kind: str, name: str) -> str:
    return "/git/ref/" + kind + "/" + urllib.parse.quote(name, safe="/")


def full_refs_uri(kind: str, name: str) -> str:
    return "/git/refs/" + kind + "/" + urllib.parse.quote(name, safe="/")


def get_ref(kind: str, name: str):
    return call("GET", ref_uri(kind, name), missing_ok=True)


def ref_sha(data) -> str | None:
    return (data or {}).get("object", {}).get("sha")


def dump(report):
    RESULT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k != "history"},
                     ensure_ascii=False, indent=2), flush=True)


def main():
    report = {
        "repo": REPOSITORY, "archive_prefix": ARCHIVE_PREFIX,
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "kept": sorted(KEEP), "archived": [], "deleted": [],
        "skipped": [], "status": "PREFLIGHT", "history": []
    }
    try:
        if os.environ.get("GITHUB_REPOSITORY") != REPOSITORY:
            raise RuntimeError("Wrong GitHub repository; cleanup refused")
        if os.environ.get("GITHUB_REF") != "refs/heads/main":
            raise RuntimeError("Not running from main; cleanup refused")
        repo = call("GET", "")
        if repo["default_branch"] != "main":
            raise RuntimeError("Default branch changed; cleanup refused")
        if set(RETIRE) & KEEP:
            raise RuntimeError("KEEP / RETIRE overlap")
        # All open PRs checked, not only merged ones. Fails closed if pagination
        # would be needed instead of making a partial open-PR decision.
        prs = call("GET", "/pulls?state=open&per_page=100")
        if len(prs) == 100:
            raise RuntimeError("Open PRs may be paginated; cleanup refused")
        active_sources = {p.get("head",{}).get("ref") for p in prs}
        if active_sources & RETIRE.keys():
            raise RuntimeError("Retired branch has open PR; cleanup refused")
        branches = call("GET", "/branches?per_page=100")
        if len(branches) == 100:
            raise RuntimeError("Branches may be paginated; cleanup refused")
        current = {b["name"]:b for b in branches}
        if not KEEP.issubset(current):
            raise RuntimeError("Preserved main/V4 branch absent; cleanup refused")
        for name, expected in RETIRE.items():
            b = current.get(name)
            if b is None:
                raise RuntimeError("Inventoried branch is missing: " + name)
            if b["protected"]:
                raise RuntimeError("Protected branch refused: " + name)
            if b["commit"]["sha"] != expected:
                raise RuntimeError("Head changed, refusing all deletion: " + name)
            actual = ref_sha(get_ref("heads", name))
            if actual != expected:
                raise RuntimeError("Ref changed during preflight: " + name)
            tag_name = ARCHIVE_PREFIX + "/" + name
            tag = get_ref("tags", tag_name)
            if tag is not None and ref_sha(tag) != expected:
                raise RuntimeError("Conflicting existing archive tag: " + tag_name)
        report["status"] = "CREATING_ARCHIVES"
        dump(report)
        # Archive every head first. Never delete even one branch unless all
        # ten immutable refs have been created and verified at expected SHA.
        for name, sha in RETIRE.items():
            tag_name = ARCHIVE_PREFIX + "/" + name
            if get_ref("tags", tag_name) is None:
                call("POST", "/git/refs",
                     {"ref":"refs/tags/" + tag_name, "sha":sha})
            if ref_sha(get_ref("tags", tag_name)) != sha:
                raise RuntimeError("Archive tag verification failure: " + tag_name)
            report["archived"].append({"branch":name,"tag":tag_name,"sha":sha})
        report["status"] = "ARCHIVES_VERIFIED"
        dump(report)
        # Each deletion must recheck both branch and tag SHA to avoid racing
        # any active push. A changed branch is kept, not force-deleted.
        for name, sha in RETIRE.items():
            tag_name = ARCHIVE_PREFIX + "/" + name
            if ref_sha(get_ref("tags", tag_name)) != sha:
                report["skipped"].append({"branch":name,"reason":"TAG_CHANGED"})
                continue
            if ref_sha(get_ref("heads", name)) != sha:
                report["skipped"].append({"branch":name,"reason":"HEAD_CHANGED"})
                continue
            try:
                call("DELETE", full_refs_uri("heads", name))
                report["deleted"].append(name)
            except RuntimeError as exc:
                report["skipped"].append({"branch":name,"reason":str(exc)[:250]})
        report["status"] = "COMPLETE_WITH_SKIPS" if report["skipped"] else "COMPLETE"
        for name in KEEP:
            if get_ref("heads", name) is None:
                raise RuntimeError("Preserved branch unexpectedly missing: " + name)
        dump(report)
        return 0 if not report["skipped"] else 1
    except Exception as exc:
        report["status"] = "FAILED_SAFE"
        report["error"] = str(exc)
        dump(report)
        return 2


if __name__ == "__main__":
    sys.exit(main())
