"""双图结果可视化：中心线覆盖 + 局部放大 + 周期对照。"""
import sys, os, json
import numpy as np
import cv2

ROOT = os.path.dirname(os.path.abspath(__file__))
SHIBIE = os.path.abspath(os.path.join(ROOT, "..", ".."))
sys.path.insert(0, SHIBIE)

from PIL import Image, ImageDraw, ImageFont

FONT = r"C:\Windows\Fonts\msyh.ttc"


def imread_u(path, flags=cv2.IMREAD_COLOR):
    return cv2.imdecode(np.fromfile(path, dtype=np.uint8), flags)


def imwrite_u(path, img):
    ok, buf = cv2.imencode(os.path.splitext(path)[1], img)
    if ok:
        buf.tofile(path)
    return ok


def pil_font(size):
    try:
        return ImageFont.truetype(FONT, size)
    except Exception:
        return ImageFont.load_default()


front = imread_u(os.path.join(ROOT, "front.png"))
trans = imread_u(os.path.join(ROOT, "transmission.png"))
res = json.load(open(os.path.join(ROOT, "result_pair01.json"), encoding="utf-8"))
ce = res["centerline_evidence"]

WARP_C = (255, 60, 60)
WEFT_C = (60, 255, 255)


def draw(base, scale=1.0, thick=2):
    img = base.copy()
    for pts in ce.get("warp", []):
        p = np.array(pts, dtype=np.float32) * scale
        cv2.polylines(img, [p.astype(np.int32)], False, WARP_C, thick, cv2.LINE_AA)
    for pts in ce.get("weft", []):
        p = np.array(pts, dtype=np.float32) * scale
        cv2.polylines(img, [p.astype(np.int32)], False, WEFT_C, thick, cv2.LINE_AA)
    return img


# 1) 全图覆盖（两图并排，各缩到 640）
s = 640 / front.shape[1]
a = draw(front, s, 1)
b = draw(trans, s, 1)
cv2.putText(a, "FRONT  warp(red)=10  weft(cyan)=7", (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
cv2.putText(b, "TRANSMISSION", (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
pair = np.hstack([a, b])
imwrite_u(os.path.join(ROOT, "viz_full.png"), pair)

# 2) 局部放大：1:1 裁剪 360x360，看真实纱根数 vs 检出线
crop_box = (180, 180, 540, 540)
x0, y0, x1, y1 = crop_box
cf = front[y0:y1, x0:x1]
ct = trans[y0:y1, x0:x1]
cf = draw(np.zeros_like(front), 1.0, 0)  # placeholder
cfa = front.copy()
cta = trans.copy()
for pts in ce.get("warp", []):
    p = np.array(pts, dtype=np.float32)
    cv2.polylines(cfa, [p.astype(np.int32)], False, WARP_C, 2, cv2.LINE_AA)
    cv2.polylines(cta, [p.astype(np.int32)], False, WARP_C, 2, cv2.LINE_AA)
for pts in ce.get("weft", []):
    p = np.array(pts, dtype=np.float32)
    cv2.polylines(cfa, [p.astype(np.int32)], False, WEFT_C, 2, cv2.LINE_AA)
    cv2.polylines(cta, [p.astype(np.int32)], False, WEFT_C, 2, cv2.LINE_AA)
cfa = cfa[y0:y1, x0:x1]
cta = cta[y0:y1, x0:x1]
imwrite_u(os.path.join(ROOT, "viz_crop_front.png"), cfa)
imwrite_u(os.path.join(ROOT, "viz_crop_trans.png"), cta)

# 3) 亮度剖面 + 自相关峰标注
gray_t = cv2.cvtColor(trans, cv2.COLOR_BGR2GRAY)
gray_f = cv2.cvtColor(front, cv2.COLOR_BGR2GRAY)
row = int(gray_t.shape[0] * 0.5)
prof = gray_t[row - 6:row + 6, 200:1000].mean(axis=0)
prof = prof - prof.mean()
ac = np.correlate(prof, prof, mode="full")[len(prof) - 1:]
ac = ac / (ac[0] + 1e-9)

H, W = 320, 1600
panel = np.full((H, W, 3), 245, np.uint8)
# 左：剖面
seg = 800
for i in range(seg - 1):
    x1p = int(i * (seg - 1) / (seg - 1))
    y1p = int(H * 0.5 - prof[i] * 0.6)
    y2p = int(H * 0.5 - prof[i + 1] * 0.6)
    if 0 <= y1p < H and 0 <= y2p < H:
        cv2.line(panel, (x1p, y1p), (x1p + 1, y2p), (40, 40, 40), 1)
cv2.line(panel, (0, H // 2), (seg, H // 2), (200, 200, 200), 1)
# 标 28px 周期
for k in range(1, 20):
    x = int(k * 28.0)
    if x < seg:
        cv2.line(panel, (x, 0), (x, H), (0, 0, 255), 1)
cv2.putText(panel, "transmission row profile, red = 28px autocorr period", (8, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 200), 1)
# 右：自相关
base = seg
for i in range(1, min(120, len(ac))):
    y = int(H - 20 - ac[i] * (H - 60))
    cv2.line(panel, (base + i * 4, y), (base + (i + 1) * 4, y), (0, 120, 0), 2)
cv2.putText(panel, "autocorrelation (x4)", (base + 6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 100, 0), 1)
peak_x = base + 28 * 4
cv2.line(panel, (peak_x, 20), (peak_x, H - 20), (0, 0, 255), 1)
cv2.putText(panel, "28px", (peak_x + 4, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 200), 1)
imwrite_u(os.path.join(ROOT, "viz_period.png"), panel)

# 4) 中文标注总结图
f1, f2 = pil_font(22), pil_font(18)
canvas = Image.new("RGB", (1300, 700), "white")
d = ImageDraw.Draw(canvas)
cv2_img = cv2.cvtColor(pair, cv2.COLOR_BGR2RGB)
canvas.paste(Image.fromarray(cv2_img), (0, 40))
d.text((10, 8), "双图链路：检出 warp 10 条 / weft 7 条（红=经 warp，青=纬 weft）", font=f1, fill="black")

info = [
    f"自相关周期: 28.0 px  →  折算密度 10/(28*0.0125) = {10/(28*0.0125):.2f} 根/cm",
    f"中心线中位间距: 98.91 px  →  折算密度 {10/(98.91*0.0125):.2f} 根/cm",
    f"两者差 111.7%（触发 PERIODICITY_CENTERLINE_DISAGREEMENT）",
    f"实际输出 warp 密度: {res['warp_density_per_cm']:.2f} 根/cm",
    f"同批候选 dark@2.3 给出: 26.59 根/cm（quality 0.98146），被淘汰",
    f"胜出候选 bright@3.6: 8.09 根/cm（quality 0.98214），差 0.00007",
]
y = 690 - 26 * len(info) - 10
for line in info:
    d.text((16, y), line, font=f2, fill=(20, 20, 20))
    y += 26
canvas.save(os.path.join(ROOT, "viz_summary.png"))
print("saved viz_full.png / viz_crop_front.png / viz_crop_trans.png / viz_period.png / viz_summary.png")
