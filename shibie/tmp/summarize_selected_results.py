from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RESULT_PATH = ROOT / "tmp" / "quality_selected_latest_050.json"
SUMMARY_JSON = ROOT / "tmp" / "quality_selected_report_summary_050.json"
SUMMARY_CSV = ROOT / "tmp" / "quality_selected_report_samples_050.csv"


def get(mapping: dict, *keys: str, default=None):
    value = mapping
    for key in keys:
        if not isinstance(value, dict):
            return default
        value = value.get(key)
    return default if value is None else value


def counts(samples: list[dict], *keys: str) -> dict[str, int]:
    return dict(Counter(str(get(item["measurement"], *keys, default="NOT_AVAILABLE")) for item in samples))


def main() -> None:
    payload = json.loads(RESULT_PATH.read_text(encoding="utf-8"))
    samples = payload["samples"]
    summary = {
        "sample_count": len(samples),
        "source_results": str(RESULT_PATH),
        "main_status": counts(samples, "status"),
        "gate3_status": counts(samples, "gate3", "status"),
        "width_status": counts(samples, "apparent_width", "status"),
        "warp_width_status": counts(samples, "apparent_width", "warp", "status"),
        "weft_width_status": counts(samples, "apparent_width", "weft", "status"),
        "twill_direction_status": counts(samples, "twill", "direction_status"),
        "twill_angle_status": counts(samples, "twill", "angle_status"),
        "weave_status": counts(samples, "twill", "weave_status"),
        "evidence_status": counts(samples, "evidence", "status"),
        "yarn_status": counts(samples, "yarn_advisory", "status"),
        "yarn_confidence": counts(samples, "yarn_advisory", "warp", "confidence"),
        "gate3_warning_frequency": dict(Counter(
            warning
            for item in samples
            for warning in get(item["measurement"], "gate3", "warnings", default=[])
        )),
        "technology": {
            "main_route": "双图输入 -> 预处理/归一化 -> Structure Tensor 方向候选 -> Steerable filter -> Ridge/中心线 -> 清洗 -> 双路径密度",
            "apparent_width": "透射图中心线 -> 反射/透射梯度相位相关配准 -> 中心线映射 -> 法向灰度剖面 -> 多边缘候选配对 -> Pitch/剖面一致性筛选 -> MAD 异常值剔除 -> P10/P50/P90",
            "twill": "反射图局部归一化 -> 多尺度 Gabor 对角纹理带 -> Structure Tensor 局部方向场 -> 连通候选带 -> Canny/Hough 线段 -> 支持度、方向簇和角度离散度 -> 左/右斜与角度分别输出",
            "weave": "已有经纬中心线 -> 反射/透射配准 -> 交叉网格 -> 交点方向性对比度 -> 浮沉符号矩阵 -> 浮长/重复一致性 -> plain、2/1、3/1 模板候选匹配",
            "yarn_advisory": "经纬密度 + 经/纬表观宽度 P50 -> 粗粒度经验分档 -> Ne 区间与 tex 区间；reference_only、LOW confidence",
            "gate3": "Gate2、密度、宽度作为核心质量项；斜纹方向、角度、组织、Ne/tex、Evidence 作为辅助项；汇总 PASS/LOW_CONFIDENCE/FAIL 和 warnings",
            "evidence": "复用已计算结果生成宽度边缘图、斜纹 Hough 图、浮沉矩阵图和 evidence JSON 索引",
        },
    }
    SUMMARY_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    fields = [
        "image", "main_status", "gate3_status", "width_status", "warp_width_status", "weft_width_status",
        "warp_p10_mm", "warp_p50_mm", "warp_p90_mm", "weft_p10_mm", "weft_p50_mm", "weft_p90_mm",
        "direction_status", "direction", "angle_status", "angle_deg", "weave_status", "weave_candidate",
        "yarn_status", "yarn_reference_only", "evidence_status",
    ]
    with SUMMARY_CSV.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in samples:
            measurement = item["measurement"]
            row = {
                "image": item["image"],
                "main_status": get(measurement, "status"),
                "gate3_status": get(measurement, "gate3", "status"),
                "width_status": get(measurement, "apparent_width", "status"),
                "warp_width_status": get(measurement, "apparent_width", "warp", "status"),
                "weft_width_status": get(measurement, "apparent_width", "weft", "status"),
                "warp_p10_mm": get(measurement, "apparent_width", "warp", "p10_mm"),
                "warp_p50_mm": get(measurement, "apparent_width", "warp", "p50_mm"),
                "warp_p90_mm": get(measurement, "apparent_width", "warp", "p90_mm"),
                "weft_p10_mm": get(measurement, "apparent_width", "weft", "p10_mm"),
                "weft_p50_mm": get(measurement, "apparent_width", "weft", "p50_mm"),
                "weft_p90_mm": get(measurement, "apparent_width", "weft", "p90_mm"),
                "direction_status": get(measurement, "twill", "direction_status"),
                "direction": get(measurement, "twill", "direction"),
                "angle_status": get(measurement, "twill", "angle_status"),
                "angle_deg": get(measurement, "twill", "angle_deg"),
                "weave_status": get(measurement, "twill", "weave_status"),
                "weave_candidate": get(measurement, "twill", "weave_type"),
                "yarn_status": get(measurement, "yarn_advisory", "status"),
                "yarn_reference_only": get(measurement, "yarn_advisory", "reference_only"),
                "evidence_status": get(measurement, "evidence", "status"),
            }
            writer.writerow(row)
    print(SUMMARY_JSON)
    print(SUMMARY_CSV)


if __name__ == "__main__":
    main()
