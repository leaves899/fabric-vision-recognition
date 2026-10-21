from __future__ import annotations
"""Publish only real GitHub Actions rendered, verified flat photo-guided 8k cases."""
import argparse
import json
import shutil
from pathlib import Path


EXPECTED={"plain_photo_flat":"plain","twill31_photo_flat":"twill_3_1"}


def publish(source:Path,out:Path):
    truth_files=sorted(source.rglob("truth.json"))
    cases={}
    out.mkdir(parents=True,exist_ok=True)
    for t in truth_files:
        data=json.loads(t.read_text(encoding="utf-8"))
        name=data["source_scene"]["name"]
        if name not in EXPECTED:
            raise RuntimeError("UNEXPECTED_SCENE_"+name)
        if name in cases:
            raise RuntimeError("DUPLICATE_SCENE")
        scene=data["source_scene"]
        style=data.get("photo_guided_appearance",{})
        if (scene["weave"]!=EXPECTED[name] or scene["width"]!=8000
            or scene["height"]!=6000 or
            scene["rotation_deg"]!=0 or scene["fabric_rotation_deg"]!=0
            or scene["perspective"]!=0 or
            style.get("no_rotation_or_perspective") is not True):
            raise RuntimeError("NOT_FLAT_NATIVE_PHYSICAL_IMAGE")
        if not style.get("photo_sha256") or style.get("has_pasted_reference_texture") is not False:
            raise RuntimeError("NONTRACEABLE_REFERENCE_OR_STRUCTURE_LEAK")
        for f in ("photo_vs_synth_AB.jpg","styled_reflection_preview.jpg",
                  "styled_reflection_center_crop.jpg",
                  "transmission_preview.jpg","reference_appearance_stats.json"):
            src=t.parent/f
            if not src.is_file():
                raise RuntimeError("EXPECTED_ACTUAL_OUTPUT_MISSING: "+str(src))
            shutil.copy2(src,out/(name+"_"+f))
        report=t.parent/"report.json"
        metrics=json.loads(report.read_text(encoding="utf-8")) if report.exists() else None
        cases[name]={"capture":[8000,6000],"rotation":0,"perspective":0,
            "true_weave_evaluation_only":scene["weave"],
            "sample_physical_yarns":{k:len(v)
                 for k,v in data["physical_yarn_centerlines"].items()},
            "reflect_hash":data["sha256"]["reflection"],
            "transmit_hash":data["sha256"]["transmission"],
            "photo_style_reference_hash":style["photo_sha256"],
            "reference":style["reference_path_in_repository"],
            "appearance":style,
            "algorithm_metrics":metrics["summary"] if metrics else None}
    if set(cases)!=set(EXPECTED):
        raise RuntimeError("TWO_REAL_RENDER_CASES_NOT_ARCHIVED")
    (out/"verified_cases.json").write_text(json.dumps(
        cases,ensure_ascii=False,indent=2),encoding="utf-8")
    lines=["# 真实照片统计引导的原生8000×6000织物合成（0°平铺工位）","",
      "本次使用GitHub仓库内的真实用户照片 `U20261013_05.jpg` 提取颜色分位值及细粒度纹理噪声幅度。",
      "单独上传的 `高质量照片.rar` 在当前工作环境没有成功解包；没有谎称已经学习该压缩包的所有高清原图。",
      "真实照片不被复制粘贴进合成织物，避免合成照片出现与物理纱线ID不对应的条纹。",
      "经纬实体、纱线宽度、交织浮沉、5×5厘米同平面框、R/T真值完全来自独立物理合成器。",
      "相机角0°、布料相对框0°、透视0；画面的斜纹仍属于组织形态，不属于相机或布料旋转。",
      "反射图只做真实照片的色彩/细粒度强度迁移；透射图仍为物理模拟，未冒充来自真实透射照片的纹理。",
      "",
      "| 场景 | 几何旋转 | 反射图外观 | 透射图 | 物理真值 |",
      "|---|---|---|---|---|"]
    for case in EXPECTED:
        lines.append(f"| {case} | 0° | {case}_styled_reflection_preview.jpg | "
                     f"{case}_transmission_preview.jpg | 真实模拟纱线ID+浮沉 |")
    lines+=["","## 实际图像验收",
      "仓库已提交4栏AB图（真实照片局部、原物理合成、照片色彩迁移、模拟透射）。这些图来自程序真实输出，未调用生成式AI作图。",
      "因为图像容器不可用，本报告可确认来源、路径、文件完整性；对纤维级真实性仍需人工视觉复核。",
      "",
      "## 边界",
      "该版本是受真实照片**统计特征**约束的物理合成，并非照片级写实渲染；尚未包含显微毛羽/纱线捻度的逐纤维物理建模。",
      "该版本没有进行图像旋转或背景增强。若后续现场工位显示相机未对齐再另行测角，不反向修改此次冻结场景。",
      "真实高清RAR文件成功解包之后应换用内部清晰无标注单根纱线区域作独立纹理建模，避免照片大尺度斜纹纹理泄漏到合成纱线。"]
    (out/"REPORT.md").write_text("\n".join(lines),encoding="utf-8")
    print("PHOTO_GUIDED_FLAT_8K_VERIFIED "+json.dumps({
        "cases":list(cases),"reference":cases["plain_photo_flat"]["reference"],
        "source_hash":cases["plain_photo_flat"]["photo_style_reference_hash"]},
        ensure_ascii=False),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--artifacts",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    args=p.parse_args()
    publish(args.artifacts,args.out)
