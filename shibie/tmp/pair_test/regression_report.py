import json, os
import openpyxl
import numpy as np

ROOT = r"E:\Internship_2026\织物识别工作区\shibie\tmp\pair_test"
XLSX = r"E:\Internship_2026\织物识别工作区\shibie\tmp\fabricnet\FabricNet_parameters.xlsx"

wb = openpyxl.load_workbook(XLSX, data_only=True)
rows = list(wb.active.iter_rows(values_only=True))[1:]
truth = {int(r[0]): (r[2], r[3], r[4]) for r in rows if r[0] is not None}

recs = json.load(open(os.path.join(ROOT, "regression_tiebreak.json"), encoding="utf-8"))
hdr = f"{'img':8}{'tex':7}{'tW':>5}{'tE':>5} | {'offW':>7}{'err%':>7} | {'onW':>7}{'err%':>7} | verdict"
print(hdr)
eo, en = [], []
for r in recs:
    i = int(r["img"][1:4])
    tw, te, tex = truth.get(i, (None, None, ""))
    ow, onw = r["off_warp"], r["on_warp"]
    e1 = abs(ow - tw) / tw * 100 if ow and tw else None
    e2 = abs(onw - tw) / tw * 100 if onw and tw else None
    if e1 is not None:
        eo.append(e1)
    if e2 is not None:
        en.append(e2)
    v = ""
    if e1 is not None and e2 is not None:
        v = "better" if e2 < e1 - 0.5 else ("WORSE" if e2 > e1 + 0.5 else "same")
    print(f"{r['img']:8}{tex:7}{tw or 0:5}{te or 0:5} | {ow or 0:7.2f}{(e1 if e1 is not None else -1):7.1f} | {onw or 0:7.2f}{(e2 if e2 is not None else -1):7.1f} | {v}")

print()
print(f"OFF (tiebreak 关)  warp MAPE = {np.mean(eo):.2f}%  median = {np.median(eo):.2f}%  n={len(eo)}")
print(f"ON  (tiebreak 开)  warp MAPE = {np.mean(en):.2f}%  median = {np.median(en):.2f}%  n={len(en)}")
