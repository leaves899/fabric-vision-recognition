from __future__ import annotations
"""Photo-guided native 8k R/T appearance experiment for FLAT (0-degree) capture.

The reference image contributes ONLY color statistics and fine-grain amplitude.
We deliberately DO NOT paste a real denim patch into a synthetic image:
that would introduce visible "fibres" unconnected to synthetic physical-yarn
IDs, creating false labels and misleading test results.

Scene geometry and each yarn's continuous ID/over-under truth remain owned by
synthetic_capture_8k.py. Reference photo is a real user-contributed repository
image, not the unavailable uploaded RAR. All outputs identify the provenance.
"""
import argparse
import hashlib
import json
import math
from dataclasses import asdict
from pathlib import Path
import cv2
import numpy as np
from synthetic_capture_8k import CaptureScene, generate, hash_file


DEFAULT_REFERENCE=Path(
    "datasets/user_contributed/2026-10-13-six-fabric-images/images/U20261013_05.jpg"
)


def _sample_reference(path):
    original=cv2.imread(str(path),cv2.IMREAD_COLOR)
    if original is None or min(original.shape[:2])<256:
        raise ValueError("REAL_REFERENCE_MISSING_OR_TOO_SMALL")
    h,w=original.shape[:2]
    # Central 80 percent avoids wide field vignetting and capture edges.
    photo=original[h//10:h*9//10,w//10:w*9//10].copy()
    small=cv2.resize(photo,(min(800,photo.shape[1]),
                            min(800,photo.shape[0])),
                     interpolation=cv2.INTER_AREA)
    gray=cv2.cvtColor(small,cv2.COLOR_BGR2GRAY)
    quantiles=np.percentile(gray,[8,28,50,72,92]).astype(float)
    colors=[]
    for q in (quantiles[0],quantiles[2],quantiles[4]):
        mask=np.abs(gray.astype(float)-q) <= max(9, .075*(quantiles[4]-quantiles[0]))
        val=small[mask]
        colors.append(np.median(val,axis=0).astype(float).tolist()
                      if len(val)>100 else np.median(small.reshape(-1,3),axis=0).tolist())
    # A large sigma removes the reference image weave and yarn pitch.
    # ONLY amplitude of short-scale sensor/fibre residual is transferred,
    # not any patterned image tile or real-yarn coordinate.
    raw=cv2.cvtColor(photo,cv2.COLOR_BGR2GRAY).astype(np.float32)
    filtered=cv2.GaussianBlur(raw,(0,0),1.2)
    residual=raw-filtered
    grain_sigma=float(np.clip(np.std(residual),1.3,8.5))
    return original,{"shape":[int(h),int(w)],
       "palette_bgr_dark_mid_bright":np.round(np.asarray(colors),2).tolist(),
       "gray_quantiles":np.round(quantiles,2).tolist(),
       "fine_grain_sigma_px":round(grain_sigma,3),
       "photo_sha256":hash_file(path),
       "reference_path_in_repository":str(path).replace("\\","/"),
       "use":"COLOR_PALETTE_AND_SHORT_SCALE_GRAIN_ONLY_NOT_YARN_GROUND_TRUTH"}


def _frame_mask(y0,y1,width,height,mm_per_px):
    """5x5cm in the zero-angle camera plane; exact axis-aligned ROI wall."""
    bw=50./mm_per_px
    xl=width*.5-bw*.5
    xr=width*.5+bw*.5
    yt=height*.5-bw*.5
    yb=height*.5+bw*.5
    wall=17.
    xs=np.arange(width,dtype=float)[None,:]
    ys=np.arange(y0,y1,dtype=float)[:,None]
    outer=(xs>=xl-wall)&(xs<=xr+wall)&(ys>=yt-wall)&(ys<=yb+wall)
    inner=(xs>=xl)&(xs<=xr)&(ys>=yt)&(ys<=yb)
    return outer&(~inner)


def _colorize_reflection(gray, palettes, grain_sigma, rng):
    """Monotone photo-derived palette retains simulated R yarn geometry."""
    # Source simulator yarn bodies have graded optical contrast.
    y=gray.astype(np.float32)
    anchors=np.array([25.,92.,154.,229.],dtype=np.float32)
    dark,mid,bright=np.asarray(palettes,dtype=np.float32)
    # Preserve enough high-darkness structure to see yarn-vs-pore contrast.
    palette=np.stack([np.clip(dark*.63,0,255),dark,mid,bright],axis=0)
    out=np.empty((gray.shape[0],gray.shape[1],3),dtype=np.uint8)
    # Use just ONE shared luminance perturbation, not random independent R/G/B
    # noise that would make multicolored speckles unrelated to physical fibres.
    noise=rng.normal(0,grain_sigma,size=gray.shape).astype(np.float32)
    fine=cv2.GaussianBlur(noise,(3,3),.42)
    y=np.clip(y+fine*.62,0,255)
    for channel in range(3):
        ch=np.interp(y,anchors,palette[:,channel]).astype(np.float32)
        out[:,:,channel]=np.clip(ch,0,255).astype(np.uint8)
    return out


def apply_photo_appearance(scene, image_dir, reference=DEFAULT_REFERENCE, seed=98331,
                           keep_original_center=True):
    """Convert an existing *physical* R/T pair without changing geometry.

    Only R gets color conditioned on true photographic palette; T stays
    physically independent from the original transmittance renderer because a
    reflected-light photograph cannot certify transmission appearance.
    """
    for name in ("rotation_deg","fabric_rotation_deg","perspective"):
        if abs(getattr(scene,name)) > 1.e-12:
            raise ValueError("FLAT_NO_ROTATION_EXPERIMENT_REQUIRES_ZERO_"+name.upper())
    ref_image,style=_sample_reference(Path(reference))
    image_dir=Path(image_dir)
    original_reflect=image_dir/"reflection_8000x6000.jpg"
    transpath=image_dir/"transmission_8000x6000.jpg"
    truthpath=image_dir/"truth.json"
    if not (original_reflect.is_file() and transpath.is_file() and truthpath.is_file()):
        raise RuntimeError("COMPLETE_ORIGINAL_RT_PAIR_AND_TRUTH_REQUIRED")
    truth=json.loads(truthpath.read_text(encoding="utf-8"))
    if truth["sha256"]["reflection"]!=hash_file(original_reflect):
        raise RuntimeError("ORIGINAL_PHYSICAL_IMAGE_HASH_MISMATCH")
    original=cv2.imread(str(original_reflect),cv2.IMREAD_COLOR)
    if original is None or original.shape!=(6000,8000,3):
        raise RuntimeError("INPUT_MUST_BE_ACTUAL_NATIVE_8000_6000")
    # Each original image is already generated from the physical yarn-ID model;
    # no paint operation may move, rotate, stretch or invent yarn positions.
    old_center=original[2700:3300,3700:4300].copy()
    if keep_original_center:
        assert cv2.imwrite(str(image_dir/"old_physical_center_crop.jpg"),old_center)
    out=np.empty_like(original)
    rng=np.random.default_rng(seed)
    for y in range(0,scene.height,120):
        end=min(scene.height,y+120)
        slab=cv2.cvtColor(original[y:end],cv2.COLOR_BGR2GRAY)
        styled=_colorize_reflection(slab,style["palette_bgr_dark_mid_bright"],
                                    style["fine_grain_sigma_px"],rng)
        mask=_frame_mask(y,end,scene.width,scene.height,scene.mm_per_px)
        styled[mask]=(235,235,235)
        out[y:end]=styled
    assert cv2.imwrite(str(original_reflect),out,[cv2.IMWRITE_JPEG_QUALITY,91])
    # The unmodified T remains a separate physical modality from original
    # fibre cross sections; do not pretend a reflection photograph is a T GT.
    truth["sha256"]["reflection"]=hash_file(original_reflect)
    truth["photo_guided_appearance"]={
        **style,"source_is_actual_photo":True,"reference_is_true_transmission":False,
        "no_rotation_or_perspective":True,"weave_type_selected_independently":True,
        "style_seed":int(seed),"has_pasted_reference_texture":False,
        "reflection_palette_only_transmission_physics_unchanged":True,
        "not_real_camera_equivalence":True}
    truthpath.write_text(json.dumps(truth,ensure_ascii=False,indent=2),encoding="utf-8")
    assert cv2.imwrite(str(image_dir/"styled_reflection_preview.jpg"),
             cv2.resize(out,(1200,900),interpolation=cv2.INTER_AREA))
    new_center=out[2700:3300,3700:4300]
    assert cv2.imwrite(str(image_dir/"styled_reflection_center_crop.jpg"),new_center)
    T=cv2.imread(str(transpath))
    assert T is not None and T.shape==out.shape
    transmission_center=T[2700:3300,3700:4300]
    reference_center=ref_image[max(0,ref_image.shape[0]//2-300):
                               ref_image.shape[0]//2+300,
                               max(0,ref_image.shape[1]//2-300):
                               ref_image.shape[1]//2+300]
    reference_center=cv2.resize(reference_center,(600,600),interpolation=cv2.INTER_AREA)
    panels=[reference_center,old_center,new_center,transmission_center]
    canvas=np.full((620,2400,3),243,np.uint8)
    captions=["Actual source photo","Original physical sim",
              "Photo-colored R sim","Synthetic physical T"]
    for i,(picture,label) in enumerate(zip(panels,captions)):
        canvas[20:620,i*600:(i+1)*600]=picture
        cv2.rectangle(canvas,(i*600,0),(i*600+600,34),(255,255,255),-1)
        cv2.putText(canvas,label,(i*600+8,24),cv2.FONT_HERSHEY_SIMPLEX,
                    .71,(0,0,0),2,cv2.LINE_AA)
    assert cv2.imwrite(str(image_dir/"photo_vs_synth_AB.jpg"),canvas,
                       [cv2.IMWRITE_JPEG_QUALITY,88])
    # do not leave a cropped preview of the original under its previous
    # misleading name; renamed results tell which modality they represent.
    (image_dir/"reference_appearance_stats.json").write_text(
        json.dumps(truth["photo_guided_appearance"],ensure_ascii=False,indent=2),
        encoding="utf-8")
    return {"original_geometry":asdict(scene),"real_photo":style,
            "R_sha256":truth["sha256"]["reflection"],
            "T_sha256":truth["sha256"]["transmission"],
            "native_shape":[scene.height,scene.width]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--case",default="twill31_flat_photo_guided")
    p.add_argument("--weave",choices=("plain","twill_2_1","twill_3_1"),default="twill_3_1")
    p.add_argument("--reference",type=Path,default=DEFAULT_REFERENCE)
    p.add_argument("--out",type=Path,default=None)
    p.add_argument("--seed",type=int,default=99272)
    args=p.parse_args()
    scene=CaptureScene(name=args.case,weave=args.weave,seed=args.seed,
                       width=8000,height=6000,rotation_deg=0.,
                       fabric_rotation_deg=0.,perspective=0.,
                       warp_density_cm=30.,weft_density_cm=25.)
    out=args.out or Path("experiments/shibie-8k-capture-multiwindow/stress")/args.case
    generate(scene,out)
    result=apply_photo_appearance(scene,out,args.reference,seed=args.seed+19)
    print("PHOTO_GUIDED_NATIVE_8K_FLAT "+json.dumps(result,ensure_ascii=False),
          flush=True)


if __name__=="__main__":
    main()
