from __future__ import annotations
"""Publish ONLY observed metrics and actual program-rendered 8k overlays.

Run after the GitHub Actions A/B run finishes and its artifacts are downloaded.
This is post-inference auditing; no scoring values feed back into an algorithm.
"""
import argparse
import json
import shutil
from pathlib import Path


def collect(artifacts: Path, dest: Path):
    dest.mkdir(parents=True, exist_ok=True)
    files = sorted(artifacts.rglob("comparison.json"))
    if not files:
        raise RuntimeError("NO_VERIFIED_AB_ARTIFACTS")
    lines = [
        "# Native 8K 亚像素周期/相位实验：实测 A/B 核验",
        "",
        "以下全部是同一原生8000×6000 R/T双图、同一标定框、同一局部窗口的旧/新对照。",
        "真值仅在两种算法推理结束后用于评分；F1为单截面代理，不是完整实体ID追踪。",
        "本次实验并未证明正式算法已改善，且不修改V0.6.3或默认pipeline。",
        "",
        "| 场景 | 纱线族 | 旧F1 | 亚像素F1 | ΔF1 | 旧通过窗 | 新通过窗 | 亚像素纱距MAPE |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    declines = []
    output = {}
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        name = data["case"]
        output[name] = {"pose": data["pose_from_pixels_only"].get("image_rotation_deg"),
                        "runtime_seconds": data["runtime_seconds"],
                        "peak_rss_mib": data["peak_rss_mib"],
                        "metrics": data["results"], "declining_windows": []}
        for family in ("warp", "weft"):
            r = data["results"][family]
            change = round(r["new_f1_proxy"] - r["old_f1_proxy"], 4)
            lines.append(f"| {name} | {family} | {r['old_f1_proxy']:.4f} | "
                         f"{r['new_f1_proxy']:.4f} | {change:+.4f} | "
                         f"{r['old_pass_windows']} | {r['new_pass_windows']} | "
                         f"{100*r['new_period_mape']:.2f}% |")
            for row in data["windows"]:
                if row["family"] != family:
                    continue
                vals = row["truth_assessment_only"]
                d = round(vals["new"]["f1_proxy"] - vals["old"]["f1_proxy"], 4)
                if d < -0.001:
                    entry = {
                       "family":family,"grid":row["grid"],"delta":d,
                       "old_f1":vals["old"]["f1_proxy"],
                       "new_f1":vals["new"]["f1_proxy"],
                       "integer_pitch":row["pitch_initial"],
                       "fractional_pitch":row["new"].get("pitch_px"),
                       "old_phase":row["old"].get("phase_px"),
                       "new_phase":row["new"].get("phase_px"),
                       "old_status":row["old"]["status"],
                       "new_status":row["new"]["status"],
                       "phase_margin":row["new"].get("relative_phase_margin"),
                       "longitudinal_drift":row["new"].get("continuity_phase_drift_fraction")
                    }
                    output[name]["declining_windows"].append(entry)
                    declines.append((name,entry))
        image = path.parent / "real_algorithm_visual_comparison.jpg"
        if image.exists():
            shutil.copy2(image, dest / f"{name}_old_new_truth.jpg")
        else:
            raise RuntimeError("ACTUAL_ALGORITHM_OVERLAY_MISSING: " + name)
    lines.extend(["", "## 逐窗口退化明细", "",
        "下表只列新版本F1低于旧版的窗口，均使用相同真值与阈值。",
        "",
        "| 场景 | 纱线族 | 窗格 | 旧F1 | 新F1 | ΔF1 | 初始/浮点纱距(px) | 旧/新相位(px) |",
        "|---|---|---|---:|---:|---:|---|---|"])
    for name,x in declines:
        lines.append(f"| {name} | {x['family']} | {x['grid']} | "
          f"{x['old_f1']:.4f} | {x['new_f1']:.4f} | {x['delta']:+.4f} | "
          f"{x['integer_pitch']} / {x['fractional_pitch']} | "
          f"{x['old_phase']} / {x['new_phase']} |")
    if not declines:
        lines.append("| — | — | — | — | — | — | — | — |")
    lines.extend(["", "## 判定", "",
        "**旋转15°场景已有明显退化，不能切换正式算法。** "
        "继续研究应先检查窗口局部坡度、相位随纵向漂移，以及初始方向误差对截面映射的影响。",
        "纯合成实验不构成真实R/T验收，旧的真实照片回归无法替代新版对照。",
        "图片均从该次8K推理程序的实际输出复制，不是图像生成模型作图。",
        ""])
    (dest / "AB_REVIEW.md").write_text("\n".join(lines), encoding="utf-8")
    (dest / "diagnostic_windows.json").write_text(
      json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print("VERIFIED_AB_ARTIFACTS " + json.dumps(
         {"cases":sorted(output),"declining_windows":len(declines),
          "largest_declines":sorted(declines,key=lambda x:x[1]["delta"])[:9]},
          ensure_ascii=False), flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--artifacts",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    collect(args.artifacts,args.out)
