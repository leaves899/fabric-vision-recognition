from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[2]
CLASS_NAMES = ['visible_A_candidate', 'background', 'visible_B_candidate']
PALETTE = np.array([[239, 105, 65], [55, 62, 73], [42, 190, 202], [170, 170, 170]], np.uint8)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def save_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    def encode(x):
        if isinstance(x, np.ndarray): return x.tolist()
        if isinstance(x, np.generic): return x.item()
        if isinstance(x, Path): return str(x)
        raise TypeError(type(x).__name__)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=encode, allow_nan=False), encoding='utf-8')


def read_rgb(path):
    with Image.open(path) as image:
        return np.asarray(ImageOps.exif_transpose(image).convert('RGB')).copy()


def center_crop(image, size=640):
    h, w = image.shape[:2]
    s = min(size, h, w) // 8 * 8
    x, y = (w-s)//2, (h-s)//2
    return image[y:y+s, x:x+s].copy(), [x, y, x+s, y+s]


def decision(probabilities, confidence=.65, margin=.20):
    """UNKNOWN is distinct from physical background and never a forced yarn."""
    order = np.sort(probabilities, axis=-1)
    result = probabilities.argmax(-1).astype(np.uint8)
    result[(order[..., -1] < confidence) | (order[..., -1]-order[..., -2] < margin)] = 3
    return result


def panel(path, images, titles, max_side=600):
    tiles=[]
    for arr, title in zip(images, titles):
        im=Image.fromarray(np.uint8(arr)).convert('RGB')
        im.thumbnail((max_side,max_side))
        tile=Image.new('RGB',(max_side,max_side+42),'#f5f6f8')
        tile.paste(im,((max_side-im.width)//2,42))
        ImageDraw.Draw(tile).text((10,12),title,fill='#17202c')
        tiles.append(tile)
    out=Image.new('RGB',(max_side*len(tiles),max_side+42),'white')
    for i,tile in enumerate(tiles):out.paste(tile,(i*max_side,0))
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    out.save(path)


def pixel_agreement(pred, ref):
    """Reference may be another model; caller must name its source."""
    valid=ref!=3
    ious=[]
    for k in range(3):
        union=((pred==k)|(ref==k))&valid
        ious.append(float((((pred==k)&(ref==k))&valid).sum()/union.sum()) if union.any() else None)
    return {'reference_valid_pixels':int(valid.sum()),'prediction_resolved_fraction':float((pred!=3).mean()),
            'agreement_on_reference_valid':float((pred[valid]==ref[valid]).mean()) if valid.any() else None,
            'iou_by_class':ious,'mean_iou':float(np.mean([x for x in ious if x is not None])) if any(x is not None for x in ious) else None}
