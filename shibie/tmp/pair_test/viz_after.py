"""补丁后可视化：33 条 warp 中心线 vs 28px 真实周期。"""
import os, json
import numpy as np
import cv2
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
FONT = r"C:\Windows\Fonts\msyh.ttc"


def imread_u(p, fl=cv2.IMREAD_COLOR):
    return cv2.imdecode(np.fromfile(p, dtype=np.uint8), fl)


def imwrite_u(p, img):
    ok, buf = cv2.imencode(os.path.splitext(p)[1], img)
    if ok:
        buf.tofile(p)


front = imread_u(os.path.join(ROOT, "front.png"))
res = json.load(open(os.path.join(ROOT, "result_pair01.json"), encoding="utf-8"))
ce = res["centerline_evidence"]

X0, Y0, S = 600, 600, 520
crop = front[Y0:Y0 + S, X0:X0 + S].copy()

# 左：参考 28px 网格
left = crop.copy()
for k in range(0, S, 28):
    cv2.line(left, (k, 0), (k, S - 1), (0, 255, 0), 1)

# 中：补丁后检出的 warp 中心线
mid = crop.copy()
n_in = 0
for pts in ce.get("warp", []):
    p = np.array(pts, dtype=np.float32) - np.array([X0, Y0], np.float32)
    if p[:, 0].max() > -10 and p[:, 0].min() < S + 10:
        cv2.polylines(mid, [p.astype(np.int32)], False, (0, 0, 255), 2, cv2.LINE_AA)
        n_in += 1

# 右：补丁前（10 条，取自旧 JSON 备份如存在，否则只画提示）
right = crop.copy()
old_path = os.path.join(ROOT, "result_pair01_old.json")
if os.path.exists(old_path):
    old = json.load(open(old_path, encoding="utf-8"))
    for pts in old["centerline_evidence"].get("warp", []):
        p = np.array(pts, dtype=np.float32) - np.array([X0, Y0], np.float32)
        if p[:, 0].max() > -10 and p[:, 0].min() < S + 10:
            cv2.polylines(right, [p.astype(np.int32)], False, (0, 0, 255), 2, cv2.LINE_AA)

row = np.hstack([left, mid, right])
imwrite_u(os.path.join(ROOT, "viz_after.png"), row)

try:
    f = ImageFont.truetype(FONT, 19)
    ft = ImageFont.truetype(FONT, 23)
except Exception:
    f = ft = ImageFont.load_default()
canvas = Image.new("RGB", (row.shape[1], row.shape[0] + 76), "white")
canvas.paste(Image.fromarray(cv2.cvtColor(row, cv2.COLOR_BGR2RGB)), (0, 40))
d = ImageDraw.Draw(canvas)
d.text((8, 8), "局部同一区域：绿=28px 真实周期　红=检出 warp 中心线", font=ft, fill="black")
d.text((8, row.shape[0] + 46),
       f"左：真实周期网格　中：补丁后（裁剪区内 {n_in} 条，全图 33 条，间距 27.9px）　右：补丁前（10 条，间距 98.9px）",
       font=f, fill=(180, 0, 0))
canvas.save(os.path.join(ROOT, "viz_after_labeled.png"))
print("saved viz_after.png / viz_after_labeled.png  in-crop:", n_in)
