# GitHub branch cleanup — 2026-10-13 (COMPLETED)

Repository: `leaves899/fabric-vision-recognition`. This is **branch-reference housekeeping only**: it must not merge experimental V1.5 code into `main`, change `demo/v5`, or force-push.

## Branches retained for development

| Branch | Role |
|---|---|
| `main` | Default product/data/benchmark line; do not rewrite |
| `experiment/v15-fft-acf-v4` | Latest isolated V1.5 FFT+ACF experiment |

## Planned one-time archival

Each retired branch is first saved under an immutable **lightweight Git tag**:

`archive/2026-10-13/<original-branch-name>`

Every tag points to the original **exact commit SHA**, not the equivalent files at `main` (important for squash/rebase merges and still-divergent histories).

| Retired branch | Exact branch head at inventory | Classification |
|---|---|---|
| `experiment/v5-new-reviewed-annotations-round2` | `71eafbe562181a43f297b5d379ff872f87c512b0` | merged PR #8 |
| `experiment/v5-reviewed-sample-baseline` | `c2f8c1a63e54a532b54698f0651684a823ed7699` | merged PR #6 |
| `experiment/v15-fft-acf-v3` | `6db3363351c4155b6311b7bee623f8357298fed5` | V4 ancestor; standalone rollback |
| `experiment/v15-reflectance-engine` | `5ae42d6b2bd95161a3f2509d107df8f00b1737a7` | V1.5 base (V2) |
| `feature/public-photo-intake-v01` | `75774e1431e4535a2c4b66b1c298d8d54c0ed29d` | fully ancestor of main |
| `feature/public-photo-intake-v02` | `823c10b099e353cfb2b2df9cc351b132b0e68c44` | merged PRs #2/#4, divergent history |
| `feature/step0-benchmark-framework` | `c523340df7c4deaab0f71d96be22bf1778590261` | merged PR #1, ancestor of main |
| `feature/v5-manual-yarn-reference-batch` | `efa465e5b8f1067f641ed6c76ec867ba22131f64` | merged PR #5 |
| `fix/anchored-yarn-center-phase-v06` | `9fb5d9bd83fbc919d488802212167e68f734fd5d` | merged PR #9 |
| `fix/v61-physical-yarn-duplicate-guard` | `ecfa3880f857abf87b145dedd425e45fa676adea` | merged PR #11 |

No open PRs were present at the initial inventory. Some historical heads are still `ahead` of main due to merge strategy, therefore **do not** run ordinary "merged-only branch deletion" without preserving their exact SHAs.

The one-shot cleanup runner:
1. Verifies repository, default branch, preserved refs, all retired branches' exact immutable expected SHAs, protection status, and absence of open PRs.
2. Creates and verifies **all ten archive tags before deleting any branch**. Any tag/verification failure aborts all deletions. No existing tag is overwritten.
3. Re-checks each branch SHA and archive tag, then deletes only the explicitly inventoried retired branch refs. A raced/changed branch will be preserved rather than force-deleted.
4. Records a machine-readable Actions artifact of tags, deletions and skips.

## Verified outcome (2026-10-13)

**SUCCESS** — GitHub Actions [run #38329289516](https://github.com/leaves899/fabric-vision-recognition/actions/runs/38329289516).

- Created and verified **10/10** archive tags against the recorded original commit SHAs.
- Deleted **10/10** inventoried retired branch refs only after all tags were verified.
- GitHub branch listing re-queried after cleanup: **exactly 2** refs remain (`main`, `experiment/v15-fft-acf-v4`).
- Both preserved refs were checked: V1.5 V4 at `6a6b3499946bdddbc4bc0ce8441e1d4df2af78d7`; `main` remained available (its SHA advances only via documentation/maintenance commits).
- No application algorithm was merged or changed; no tag was force-updated. No old commit became unreachable because every old branch head is anchored by a tag.
- The one-time destructive workflow is intentionally removed after this result is recorded; the archival script and audit documentation remain for transparency.

## Recovery

From the repository root with Git authorization, recover any archived branch as:

```bash
git fetch origin --tags
git push origin refs/tags/archive/2026-10-13/experiment/v15-reflectance-engine:refs/heads/experiment/v15-reflectance-engine
```

Replace the example name with any row above. Alternatively, GitHub REST `POST /repos/leaves899/fabric-vision-recognition/git/refs` with `ref=refs/heads/<branch>` and `sha=<archived SHA>`.

## Future branch convention

- Keep `main` stable and use short-lived `feature/<topic>` or `fix/<topic>` branches via PRs.
- One active algorithm research branch per effort: `experiment/v15-fft-acf-v4`; preserve valuable old snapshots as **tags**, not permanent active branches.
- After a merged PR, preserve unusual standalone work as an archive tag and remove stale remote branch.
- Never squash/merge the independent V1.5 experiment into `main` automatically.
