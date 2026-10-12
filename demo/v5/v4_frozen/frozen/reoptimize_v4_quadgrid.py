import cv2, numpy as np, json
from pathlib import Path
from scipy.ndimage import gaussian_filter, gaussian_filter1d
from scipy.signal import find_peaks
import lightgbm as lgb

OUT=Path('/mnt/data/reoptimize_v4'); OUT.mkdir(exist_ok=True)
TRAIN_IMG='/mnt/data/ghostwriter_images/context/cbd213a0-f246-5e17-a674-15bc3f8bbbef.jpg'
TRAIN_CROP=(368,1168,624,1424)
GT='/mnt/data/fabric_direction_fix/registered_user_annotation_masks.npz'
TRAIN_ROT=-10.28
ITEMS=[
    ('img1','/mnt/data/ghostwriter_images/context/c1667069-4f96-59ad-9345-b7704712fdde.jpg',(215,1335,355,1715),-13),
    ('img2','/mnt/data/ghostwriter_images/context/76e460f0-a54a-5114-adac-89682aeea51c.jpg',(125,1375,255,1765),-18),
    ('img3','/mnt/data/ghostwriter_images/context/5ffdc98f-1c47-5fea-a833-ebdd1117552a.jpg',(125,1395,235,1780),-16),
]


def build_features(lab):
    L=lab[:,:,0].astype('float32'); F=[]
    def add(a): F.append(a.astype('float32'))
    for sig in [0.9,1.7,2.7,4.2,6.5,10.]:
        sm=gaussian_filter(L,sig)
        add(sm)
        for dx in [-8,-4,-2,2,4,8]: add(sm-np.roll(sm,dx,axis=1))
        if sig in [1.7,2.7,4.2]:
            for dy in [-8,-4,4,8]: add(sm-np.roll(sm,dy,axis=0))
        add(gaussian_filter(L,sig,order=(0,2))*sig**2)
        add(gaussian_filter(L,sig,order=(2,0))*sig**2)
    for ch in [1,2]:
        C=lab[:,:,ch].astype('float32')
        for sig in [2.,5.]:
            sm=gaussian_filter(C,sig)
            add(sm)
            add(sm-.5*(np.roll(sm,-6,axis=1)+np.roll(sm,6,axis=1)))
    return np.stack(F,axis=-1)


def train_model(mask_name, orientation):
    img=cv2.imread(TRAIN_IMG)
    y0,y1,x0,x1=TRAIN_CROP
    crop=img[y0:y1,x0:x1]
    gt=np.load(GT)[mask_name]
    M=cv2.getRotationMatrix2D((400,400),TRAIN_ROT,1.0)
    rot=cv2.warpAffine(crop,M,(800,800),borderMode=cv2.BORDER_REFLECT)
    rg=cv2.warpAffine(gt.astype('uint8'),M,(800,800),flags=cv2.INTER_NEAREST)>0
    F=build_features(cv2.cvtColor(rot,cv2.COLOR_BGR2LAB))
    rows=[]
    if orientation=='horizontal':
        for x in range(20,340,3):
            yy=np.where(rg[115:370,x])[0]+115
            groups=[]
            for y in yy:
                if not groups or y-groups[-1][-1]>2: groups.append([y])
                else: groups[-1].append(y)
            if len(groups)!=6: continue
            centers=[int(np.median(g)) for g in groups]
            for ident,y in enumerate(centers):
                for off in [-12,-10,-8,-1,0,1,8,10,12]:
                    p=y+off
                    if 0<=p<800: rows.append((p,x,ident,int(abs(off)<=1)))
    else:
        for y in range(52,428,3):
            if 160<=y<=235: continue
            xx=np.where(rg[y,115:370])[0]+115
            groups=[]
            for x in xx:
                if not groups or x-groups[-1][-1]>2: groups.append([x])
                else: groups[-1].append(x)
            if len(groups)!=6: continue
            centers=[int(np.median(g)) for g in groups]
            for ident,x in enumerate(centers):
                for off in [-12,-10,-8,-1,0,1,8,10,12]:
                    p=x+off
                    if 0<=p<800: rows.append((y,p,ident,int(abs(off)<=1)))
    rows=np.asarray(rows,dtype=int)
    X=F[rows[:,0],rows[:,1]]; y=rows[:,3]
    tr=(rows[:,2]%2==0)
    model=lgb.LGBMClassifier(n_estimators=150,num_leaves=13,max_depth=5,learning_rate=.045,
                             reg_lambda=8,min_child_samples=25,verbosity=-1,random_state=42,n_jobs=4)
    model.fit(X[tr],y[tr])
    return model


def base_texture_mask(img):
    gray=cv2.cvtColor(img,cv2.COLOR_BGR2GRAY).astype(np.float32)
    mu=gaussian_filter(gray,5)
    mu2=gaussian_filter(gray*gray,5)
    std=np.sqrt(np.maximum(mu2-mu*mu,0))
    thr=np.percentile(std,55)
    tex=(std>thr).astype(np.uint8)
    nonwhite=(gray<232).astype(np.uint8)
    mask=(tex & nonwhite).astype(np.uint8)
    mask=cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((5,5),np.uint8))
    mask=cv2.morphologyEx(mask,cv2.MORPH_CLOSE,np.ones((51,51),np.uint8))
    num,labels,stats,_=cv2.connectedComponentsWithStats(mask)
    if num>1:
        idx=1+np.argmax(stats[1:,cv2.CC_STAT_AREA])
        mask=(labels==idx).astype(np.uint8)
    return mask


def detect_quad_mask(img):
    mask=base_texture_mask(img)
    cnts,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return mask, None
    cnt=max(cnts,key=cv2.contourArea)
    rect=cv2.minAreaRect(cnt)
    box=cv2.boxPoints(rect).astype(np.int32)
    # order points clockwise starting from top-left
    s=box.sum(axis=1); diff=np.diff(box,axis=1).ravel()
    tl=box[np.argmin(s)]; br=box[np.argmax(s)]; tr=box[np.argmin(diff)]; bl=box[np.argmax(diff)]
    poly=np.array([tl,tr,br,bl],dtype=np.int32)
    quad=np.zeros(mask.shape,np.uint8)
    cv2.fillPoly(quad,[poly],1)
    # intersect with lightly dilated texture region to avoid extending into blank white border
    tex=cv2.dilate(mask,np.ones((15,15),np.uint8),iterations=1)
    quad=(quad & tex).astype(np.uint8)
    quad=cv2.morphologyEx(quad,cv2.MORPH_CLOSE,np.ones((15,15),np.uint8))
    quad=cv2.erode(quad,np.ones((3,3),np.uint8),iterations=1)
    return quad, poly


def transform_poly(poly, M):
    arr=np.array(poly,np.float32).reshape(-1,1,2)
    out=cv2.transform(arr,M).reshape(-1,2)
    return np.round(out).astype(np.int32)


def robust_profile_rows(score, mask):
    H,W=score.shape; prof=np.zeros(H,np.float32)
    for y in range(H):
        vals=score[y][mask[y]>0]
        if vals.size>25: prof[y]=np.quantile(vals,0.88)
    return prof


def robust_profile_cols(score, mask):
    H,W=score.shape; prof=np.zeros(W,np.float32)
    for x in range(W):
        vals=score[:,x][mask[:,x]>0]
        if vals.size>25: prof[x]=np.quantile(vals,0.88)
    return prof


def choose_peaks(profile, min_dist, floor):
    smooth=gaussian_filter1d(profile,1.4)
    rng=float(np.max(smooth)-np.median(smooth))
    prom=max(0.008,0.16*rng)
    peaks,_=find_peaks(smooth,distance=min_dist,prominence=prom)
    thr=max(floor,float(np.median(smooth)+0.18*rng))
    peaks=[int(p) for p in peaks if smooth[p]>=thr]
    return peaks,smooth,thr


def build_grid_positions(peaks, smooth, valid_idx, thr, min_keep=0.82):
    if len(peaks) < 2 or len(valid_idx)==0:
        return peaks, 0.0, None
    peaks=np.array(sorted(peaks),dtype=float)
    diffs=np.diff(peaks)
    d=float(np.median(diffs))
    if d < 3:
        return peaks.astype(int).tolist(), d, None
    # estimate anchor using rounded indices around first peak
    p0=peaks[0]
    idx=np.round((peaks-p0)/d).astype(int)
    anchor=float(np.median(peaks - idx*d))
    lo=int(valid_idx[0]); hi=int(valid_idx[-1])
    # produce expected grid range across valid span
    k0=int(np.floor((lo-anchor)/d))-1
    k1=int(np.ceil((hi-anchor)/d))+1
    positions=[]; accepted=[]
    search=int(max(2, round(0.32*d)))
    for k in range(k0,k1+1):
        exp=anchor+k*d
        if exp < lo or exp > hi: continue
        c=int(round(exp))
        a=max(lo, c-search); b=min(hi, c+search)
        if a>b: continue
        seg=smooth[a:b+1]
        loc=a+int(np.argmax(seg))
        if smooth[loc] >= min_keep*thr:
            accepted.append(loc)
        positions.append(c)
    # dedup and trim too-close repeats by keeping stronger
    accepted=sorted(accepted)
    out=[]
    close=int(max(3, round(0.55*d)))
    for p in accepted:
        if not out or p-out[-1] > close:
            out.append(p)
        else:
            if smooth[p] > smooth[out[-1]]:
                out[-1]=p
    return out, d, anchor


def sample_line(p0,p1,n=320):
    x=np.linspace(p0[0],p1[0],n)
    y=np.linspace(p0[1],p1[1],n)
    return list(zip(x,y))


def project_points(points, Minv):
    arr=np.array(points,np.float32).reshape(-1,1,2)
    out=cv2.transform(arr,Minv).reshape(-1,2)
    return [tuple(map(float,p)) for p in out]


def longest_valid_run(points, mask):
    H,W=mask.shape
    valid=[]
    for x,y in points:
        xi=int(round(x)); yi=int(round(y))
        valid.append(0<=xi<W and 0<=yi<H and mask[yi,xi]>0)
    best=(None,None,-1); s=None
    for i,ok in enumerate(valid+[False]):
        if ok and s is None: s=i
        elif not ok and s is not None:
            if i-s > best[2]: best=(s,i-1,i-s)
            s=None
    if best[0] is None or best[2] < 18: return []
    return points[best[0]:best[1]+1]


def draw(base, first_ev, second_ev, first_lines, second_lines, poly, name, angle):
    H,W=base.shape[:2]
    p1=base.copy(); p2=base.copy(); p3=base.copy()
    if poly is not None:
        cv2.polylines(p1,[poly],True,(255,255,255),1,cv2.LINE_AA)
        cv2.polylines(p2,[poly],True,(255,255,255),1,cv2.LINE_AA)
        cv2.polylines(p3,[poly],True,(255,255,255),1,cv2.LINE_AA)
    for pt in first_ev: cv2.circle(p1, tuple(pt), 1, (255,255,0), -1, cv2.LINE_AA)
    for ln in first_lines:
        cv2.polylines(p1,[np.array(ln,np.int32)],False,(0,0,255),1,cv2.LINE_AA)
        cv2.polylines(p3,[np.array(ln,np.int32)],False,(0,0,255),1,cv2.LINE_AA)
    for pt in second_ev: cv2.circle(p2, tuple(pt), 1, (255,0,255), -1, cv2.LINE_AA)
    for ln in second_lines:
        cv2.polylines(p2,[np.array(ln,np.int32)],False,(0,255,0),1,cv2.LINE_AA)
        cv2.polylines(p3,[np.array(ln,np.int32)],False,(0,255,0),1,cv2.LINE_AA)
    titles=[
        f'{name} | STEP1 first family (v4 quad+grid), angle={angle:.1f}°',
        f'{name} | STEP2 second family (v4 quad+grid)',
        f'{name} | STEP3 combined v4 result'
    ]
    subs=[
        'cyan=evidence points; red=first-family lines clipped by detected frame quad',
        'magenta=evidence points; green=second-family lines clipped by detected frame quad',
        'red=first family; green=second family; white=detected frame quad'
    ]
    cols=[(0,255,255),(255,0,255),(255,255,255)]
    panels=[]
    for im,title,sub,col in zip([p1,p2,p3],titles,subs,cols):
        hdr=np.zeros((44,W,3),np.uint8)
        cv2.putText(hdr,title,(8,18),cv2.FONT_HERSHEY_SIMPLEX,0.55,(255,255,255),1,cv2.LINE_AA)
        cv2.putText(hdr,sub,(8,37),cv2.FONT_HERSHEY_SIMPLEX,0.45,col,1,cv2.LINE_AA)
        panels.append(np.vstack([hdr,im]))
    return np.hstack(panels)

first_model=train_model('weft','horizontal')
second_model=train_model('warp','vertical')
summary=[]
out_paths=[]
for name,path,roi,angle in ITEMS:
    img=cv2.imread(path)
    y0,y1,x0,x1=roi
    full=img[y0:y1,x0:x1].copy()
    H,W=full.shape[:2]
    orig_mask, orig_poly = detect_quad_mask(full)
    M=cv2.getRotationMatrix2D((W/2,H/2),angle,1.0)
    Minv=cv2.invertAffineTransform(M)
    rot=cv2.warpAffine(full,M,(W,H),borderMode=cv2.BORDER_REFLECT)
    rot_poly=transform_poly(orig_poly, M) if orig_poly is not None else None
    rot_mask=np.zeros((H,W),np.uint8)
    if rot_poly is not None:
        cv2.fillPoly(rot_mask,[rot_poly],1)
    else:
        rot_mask=detect_quad_mask(rot)[0]

    F=build_features(cv2.cvtColor(rot,cv2.COLOR_BGR2LAB))
    s1=gaussian_filter(first_model.predict_proba(F.reshape(-1,F.shape[-1]))[:,1].reshape((H,W)),(1.0,2.0))
    s2=gaussian_filter(second_model.predict_proba(F.reshape(-1,F.shape[-1]))[:,1].reshape((H,W)),(2.0,1.0))

    row_profile=robust_profile_rows(s1,rot_mask)
    col_profile=robust_profile_cols(s2,rot_mask)
    row_peaks,row_smooth,row_thr=choose_peaks(row_profile, min_dist=10, floor=0.40)
    col_peaks,col_smooth,col_thr=choose_peaks(col_profile, min_dist=10, floor=0.40)
    row_valid=np.where(rot_mask.mean(axis=1)>0.12)[0]
    col_valid=np.where(rot_mask.mean(axis=0)>0.12)[0]
    row_grid,row_step,row_anchor=build_grid_positions(row_peaks,row_smooth,row_valid,row_thr,min_keep=0.83)
    col_grid,col_step,col_anchor=build_grid_positions(col_peaks,col_smooth,col_valid,col_thr,min_keep=0.85)

    first_lines=[]; first_ev=[]
    for y in row_grid:
        xs=np.where(rot_mask[y]>0)[0]
        if xs.size < 0.22*W: continue
        x0r=int(xs.min()); x1r=int(xs.max())
        rot_points=sample_line((x0r,y),(x1r,y),n=320)
        orig_points=project_points(rot_points,Minv)
        clipped=longest_valid_run(orig_points, orig_mask)
        if len(clipped) < 22: continue
        line=np.round(np.array(clipped)).astype(int)
        first_lines.append(line.tolist())
        first_ev.extend([tuple(map(int,np.round(p))) for p in clipped[::20]])

    second_lines=[]; second_ev=[]
    for x in col_grid:
        ys=np.where(rot_mask[:,x]>0)[0]
        if ys.size < 0.22*H: continue
        y0r=int(ys.min()); y1r=int(ys.max())
        rot_points=sample_line((x,y0r),(x,y1r),n=320)
        orig_points=project_points(rot_points,Minv)
        clipped=longest_valid_run(orig_points, orig_mask)
        if len(clipped) < 22: continue
        line=np.round(np.array(clipped)).astype(int)
        second_lines.append(line.tolist())
        second_ev.extend([tuple(map(int,np.round(p))) for p in clipped[::20]])

    panel=draw(full,first_ev,second_ev,first_lines,second_lines,orig_poly,name,angle)
    outp=OUT/f'{name}_three_panel_reopt_v4.png'
    cv2.imwrite(str(outp),panel)
    out_paths.append(str(outp))
    # save mask overlay
    ov=full.copy(); ov[orig_mask==0]=(ov[orig_mask==0]*0.4).astype(np.uint8)
    if orig_poly is not None: cv2.polylines(ov,[orig_poly],True,(0,255,255),2,cv2.LINE_AA)
    cv2.imwrite(str(OUT/f'{name}_mask_overlay.png'),ov)
    summary.append({
        'name':name,'angle':angle,
        'first_family_count':len(first_lines),'second_family_count':len(second_lines),
        'row_grid_step':row_step,'col_grid_step':col_step,
        'row_anchor':row_anchor,'col_anchor':col_anchor,
        'first_threshold':float(row_thr),'second_threshold':float(col_thr)
    })

ims=[cv2.imread(p) for p in out_paths]
h=min(im.shape[0] for im in ims)
res=[]
for im in ims:
    scale=h/im.shape[0]; res.append(cv2.resize(im,(int(im.shape[1]*scale),h),interpolation=cv2.INTER_AREA))
comp=np.hstack(res)
cv2.imwrite(str(OUT/'three_images_reopt_v4_comparison.png'),comp)
(OUT/'summary.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf-8')
print(json.dumps(summary,indent=2,ensure_ascii=False))
