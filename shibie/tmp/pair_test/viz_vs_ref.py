"""对照图：自相关周期 28px 网格 vs 检出的中心线 98.9px 间距。"""
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
trans = imread_u(os.path.join(ROOT, "transmission.png"))
res = json.load(open(os.path.join(ROOT, "result_pair01.json"), encoding="utf-8"))
ce = res["centerline_evidence"]

X0, Y0, S = 600, 600, 520
crop_f = front[Y0:Y0 + S, X0:X0 + S].copy()
crop_t = trans[Y0:Y0 + S, X0:X0 + S].copy()

# A: 原始 + 参考周期网格（28px）
a = crop_f.copy()
for k in range(0, S, 28):
    cv2.line(a, (k, 0), (k, S - 1), (0, 255, 0), 1)
for k in range(0, S, 28):
    cv2.line(a, (0, k), (S - 1, k), (0, 200, 0), 1)

# B: 检出中心线（映射到裁剪坐标）
b = crop_f.copy()
for pts in ce.get("warp", []):
    p = np.array(pts, dtype=np.float32) - np.array([X0, Y0], np.float32)
    if p[:, 0].max() > -20 and p[:, 0].min() < S + 20 and p[:, 1].max() > -20 and p[:, 1].min() < S + 20:
        cv2.polylines(b, [p.astype(np.int32)], False, (0, 0, 255), 2, cv2.LINE_AA)

# C: 透射图 + 参考网格
c = crop_t.copy()
for k in range(0, S, 28):
    cv2.line(c, (k, 0), (k, S - 1), (0, 255, 0), 1)

row = np.hstack([a, b, c])
imwrite_u(os.path.join(ROOT, "viz_vs_ref.png"), row)

# 中文说明拼版
try:
    f = ImageFont.truetype(FONT, 20)
    ft = ImageFont.truetype(FONT, 24)
except Exception:
    f = ft = ImageFont.load_default()
canvas = Image.new("RGB", (row.shape[1], row.shape[0] + 78), "white")
canvas.paste(Image.fromarray(cv2.cvtColor(row, cv2.COLOR_BGR2RGB)), (0, 40))
d = ImageDraw.Draw(canvas)
d.text((8, 8), "同一块布同一尺度：绿=28px 自相关真实周期　红=算法检出的 warp 中心线", font=ft, fill="black")
d.text((8, row.shape[0] + 44), "左：真实周期网格（约 18 根纱）　中：检出仅 10 条、间距 98.9px（≈3.5 根合并）　右：透射图同样只应切出 18 条",
       font=f, fill=(180, 0, 0))
canvas.save(os.path.join(ROOT, "viz_vs_ref_labeled.png"))
print("saved viz_vs_ref.png / viz_vs_ref_labeled.png")
