"""Evidence overlays of global orientation proposals, NEVER physical yarn traces."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from PIL import Image, ImageDraw


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,default=Path("."))
    p.add_argument("--result",type=Path,default=Path("experiments/v15_reflection/output/g2_project_images.json"))
    p.add_argument("--out",type=Path,default=Path("experiments/v15_reflection/output/overlays"))
    args=p.parse_args(argv)
    rows=json.loads(args.result.read_text(encoding="utf-8"))["results"]
    labels={}
    for name in (args.root/"datasets/annotations/drafts").glob("*.json"):
        rec=json.loads(name.read_text(encoding="utf-8"))
        if rec.get("review_state")=="OPERATOR_REVIEWED" and rec.get("reference_confirmed"):
            labels[rec["sample_id"]]=rec
    args.out.mkdir(parents=True,exist_ok=True)
    index=[]
    for row in rows:
        if row.get("status")!="DIAGNOSTIC_ONLY": continue
        key=row["sample_id"]
        with Image.open(args.root/row["image_path"]) as img:
            w0,h0=img.size
            img.thumbnail((720,720),Image.Resampling.LANCZOS)
            img=img.convert("RGB")
            canvas=img.copy()
            d=ImageDraw.Draw(canvas)
            pred=row["orientation"][0]["v2"]
            if pred["status"]=="PROPOSED_NOT_VALIDATED":
                cx,cy=img.width/2,img.height/2
                half=min(img.width,img.height)*.35
                for theta,color in zip(pred["unlabelled_axes_deg"],("lime","orange")):
                    rad=math.radians(theta)
                    x=half*math.cos(rad)
                    y=half*math.sin(rad)
                    d.line((cx-x,cy-y,cx+x,cy+y),fill="black",width=6)
                    d.line((cx-x,cy-y,cx+x,cy+y),fill=color,width=3)
            if key in labels:
                label=labels[key]
                for field,color in (("reference","yellow"),("check_same","magenta")):
                    seg=label.get("segments",{}).get(field)
                    if seg:
                        coords=[(q[0]*img.width/w0,q[1]*img.height/h0) for q in seg]
                        d.line((*coords[0],*coords[1]),fill=color,width=4)
            d.rectangle((0,0,img.width,33),fill="black")
            d.text((7,9),f"{key}  {pred['status']}  {pred.get('reason') or 'unverified'}"[:90],fill="white")
            name=f"{key}.jpg"
            canvas.save(args.out/name,quality=78,optimize=True)
            index.append({"sample_id":key,"image_file":name,
                          "semantic":"global axis proposal / operator reference, NOT real-yarn centers",
                          "has_candidate":pred["status"]=="PROPOSED_NOT_VALIDATED"})
    (args.out/"index.json").write_text(json.dumps(index,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"G2_VISUAL_OVERLAYS_SAVED={len(index)}")
    return 0 if len(index)==66 else 2


if __name__=="__main__":
    raise SystemExit(main())
