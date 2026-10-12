"""10-parameter Demo powered by exact frozen V4 for A/B yarn candidates.

Color and quality from the existing prototype. No FFT/twill grid direction lines.
"""
from __future__ import annotations
import hashlib
import math
import numpy as np
import cv2
from common_analysis import (decode_image,calibrate,quality_metrics,color_and_texture,
                      shrink,image_uri,_parameter,CM)
from v4_adapter import run_v4
from reference_direction import reference_from_two_points


def family_angle(tracks):
    angles=[]; weights=[]
    for points in tracks:
        if len(points)<2:continue
        a=np.asarray(points,dtype=float)
        vec=a[-1]-a[0]
        length=float(np.linalg.norm(vec))
        if length<15:continue
        angles.append(math.atan2(vec[1],vec[0]))
        weights.append(min(length,1200))
    if not angles:return None
    ang=np.array(angles)
    x=np.sum(np.array(weights)*np.cos(2*ang));y=np.sum(np.array(weights)*np.sin(2*ang))
    return round((math.degrees(math.atan2(y,x))/2)%180,2)


def transect_segment(center,direction,h,w,inset=.06):
    xmin,xmax=w*inset,w*(1-inset)-1
    ymin,ymax=h*inset,h*(1-inset)-1
    lo,hi=-np.inf,np.inf
    for c,d,lower,upper in ((center[0],direction[0],xmin,xmax),(center[1],direction[1],ymin,ymax)):
        if abs(d)<1e-9:
            if c<lower or c>upper:return None
        else:
            t1=(lower-c)/d;t2=(upper-c)/d
            lo=max(lo,min(t1,t2));hi=min(hi,max(t1,t2))
    if hi-lo<40:return None
    return center+lo*direction,center+hi*direction


def line_intersection(p,q,a,b):
    """Intersection of finite segments pq and ab, or None."""
    v=q-p;w=b-a
    cross=lambda z,t: float(z[0]*t[1]-z[1]*t[0])
    den=cross(v,w)
    if abs(den)<1e-8:return None
    x=a-p
    t=cross(x,w)/den;s=cross(x,v)/den
    if 0<=t<=1 and 0<=s<=1:return p+t*v
    return None


def v4_transects(tracks,angle,shape):
    if angle is None:
        return {'transects':[], 'candidate_count_median':None,'count_range':None,
                'spacing_cv_median':None,'candidate_width_proxy_px_median':None}
    h,w=shape[:2];theta=math.radians(angle)
    d=np.array([math.cos(theta),math.sin(theta)])
    n=np.array([-d[1],d[0]])
    result=[]
    for t in (-0.36,0,0.36):
        center=np.array([w/2,h/2])+d*t*min(w,h)
        seg=transect_segment(center,n,h,w)
        if seg is None:continue
        p,q=seg
        pts=[]
        for track in tracks:
            arr=np.asarray(track,dtype=np.float64)
            if len(arr)<2:continue
            # match each candidate line ID at most once to a transect
            hit=None
            for i in range(1,len(arr)):
                hit=line_intersection(p,q,arr[i-1],arr[i])
                if hit is not None:break
            if hit is not None:pts.append(hit)
        projections=sorted(float(np.dot(x-p,n)) for x in pts)
        spacings=np.diff(projections)
        cv=float(np.std(spacings)/(np.mean(spacings)+1e-9)) if len(spacings)>=2 else None
        result.append({'line_points_px':[np.round(p,1).tolist(),np.round(q,1).tolist()],
                       'length_px':round(float(np.linalg.norm(q-p)),2),
                       'candidate_crossing_count':len(pts),
                       'crossing_points_px':[np.round(v,1).tolist() for v in pts],
                       'spacing_cv':round(cv,3) if cv is not None else None,
                       'source':'V4_TRACK_INTERSECTION_NOT_GROUND_TRUTH'})
    counts=[x['candidate_crossing_count'] for x in result]
    cvs=[x['spacing_cv'] for x in result if x['spacing_cv'] is not None]
    return {'yarn_axis_deg':angle,'transects':result,
            'candidate_count_median':float(np.median(counts)) if counts else None,
            'count_range':[min(counts),max(counts)] if counts else None,
            'spacing_cv_median':round(float(np.median(cvs)),3) if cvs else None,
            'candidate_width_proxy_px_median':None,
            'warning':'V4 检出的轨迹交点仅是候选，未验证每条轨迹对应一根物理纱线'}


def visuals(roi,tracks,one,two):
    base=shrink(roi,850)
    height,width=base.shape[:2]
    sx=width/roi.shape[1];sy=height/roi.shape[0]
    direction=base.copy(); counts=base.copy()
    def draw_track(image,path,color):
        points=np.asarray(path,dtype=np.float32)
        if len(points)<2:return
        points[:,0]*=sx;points[:,1]*=sy
        pts=np.round(points).astype(np.int32)
        cv2.polylines(image,[pts],False,color,1,cv2.LINE_AA)
    for name,color in [('first',(57,110,243)),('second',(49,207,109))]:
        for path in tracks[name]:
            draw_track(direction,path,color)
            draw_track(counts,path,color)
    for local,color in [(one,(57,110,243)),(two,(49,207,109))]:
        for row in local['transects']:
            p,q=row['line_points_px']
            a=(round(p[0]*sx),round(p[1]*sy));b=(round(q[0]*sx),round(q[1]*sy))
            cv2.line(counts,a,b,(225,225,225),1,cv2.LINE_AA)
            for x,y in row['crossing_points_px']:
                cv2.circle(counts,(round(x*sx),round(y*sy)),2,color,-1,cv2.LINE_AA)
    for im,title in [(direction,'V4: FROZEN TRACK CANDIDATES'),(counts,'V4: TRANSECT INTERSECTIONS')]:
        cv2.rectangle(im,(0,0),(min(width,380),29),(20,29,47),-1)
        cv2.putText(im,title,(8,20),cv2.FONT_HERSHEY_SIMPLEX,.48,(255,255,255),1,cv2.LINE_AA)
    return {'roi':image_uri(base),'direction':image_uri(direction),'transects':image_uri(counts),
            'three_panel':image_uri(cv2.hconcat([base,direction,counts]),quality=82)}


def analyze(data:bytes,corners=None,confirm_corners=False,reference_points=None,
            confirm_reference=False,warp_family=None,weave_override=None,confirm_weave=False):
    img=decode_image(data)
    roi,calib=calibrate(img,corners,confirm_corners)
    if corners is None:
        # Preserve native-scale inputs; V4 features are scale-sensitive.
        roi=img.copy()
    reference=reference_from_two_points(
        reference_points, img.shape, corners=corners,
        homography=calib.get('homography'), confirmed=confirm_reference)
    angle=reference['v4_adapter_rotation_deg']
    v4=run_v4(roi,angle)
    tracks={'first':v4['first'],'second':v4['second']}
    a=family_angle(tracks['first']);b=family_angle(tracks['second'])
    one=v4_transects(tracks['first'],a,roi.shape)
    two=v4_transects(tracks['second'],b,roi.shape)
    quality=quality_metrics(roi)
    colors=color_and_texture(roi)
    # Until the user confirms warp/weft, A/B have no physical identity.
    assignment_valid=warp_family in ('A','B')
    warp=one if warp_family!='B' else two
    weft=two if warp_family!='B' else one
    identity_note=('操作员已指定经向组；V4 轨迹位置本身仍未经过真实纱线验证'
                   if assignment_valid else '当前只是候选组 A/B，未经确认不能把经纬身份作为定论')
    params=[]
    for idx,local in [(1,warp),(2,weft)]:
        params.append(_parameter(idx,local.get('yarn_axis_deg'),'NEEDS_CONFIRMATION' if local.get('yarn_axis_deg') is not None else 'UNAVAILABLE',
                      '°',['冻结 V4 实际输出轨迹端点方向统计'],identity_note))
    def pattern(x):
        cv=x['spacing_cv_median']
        if cv is None:return '候选交点不足'
        return '局部候选交点较均匀' if cv<.3 else '局部候选交点存在波动'
    for idx,local in [(3,warp),(4,weft)]:
        params.append(_parameter(idx,{'pattern_candidate':pattern(local),'spacing_cv':local['spacing_cv_median'],
                                      'transect_count_range':local['count_range']},'NEEDS_CONFIRMATION',None,
                        ['V4 轨迹与局部截线交点统计'],'轨迹交点不等于已确认的单根纱线排列'))
    for idx,local in [(5,warp),(6,weft)]:
        params.append(_parameter(idx,None,'UNAVAILABLE',None,['V4 仅提供中心线候选'],
                        'V4 不输出纱线边缘分割，不能用中心线间距冒充纱线粗细/等级'))
    choices=['平纹','2/1右斜纹','2/1左斜纹','3/1右斜纹','3/1左斜纹','破斜纹','缎纹','变化组织','其他/待确认']
    if weave_override and weave_override not in choices:raise ValueError('组织分类值不在允许范围内')
    params.append(_parameter(7,weave_override or '其他/待确认',
                  'CONFIRMED' if weave_override and confirm_weave else 'NEEDS_CONFIRMATION','类别',
                  ['人工指定组织类型' if weave_override else '冻结 V4 不含组织类型分类器'],
                  '组织结构不由 V4 的几何候选网格直接判定',options=choices))
    for idx,local in [(8,warp),(9,weft)]:
        density=[]
        if calib['confirmed']:
            for tr in local['transects']:
                L=tr['length_px']*calib['cm_per_px']
                if L>0:density.append(tr['candidate_crossing_count']/L)
        if density:
            value={'candidate_per_cm':round(float(np.median(density)),2),
                   'range_per_cm':[round(float(min(density)),2),round(float(max(density)),2)],
                   'sampled_transects':len(density)}
            status='NEEDS_CONFIRMATION'; unit='候选根/cm'
            note='已确认 5 cm 标定，但分子是 V4 候选轨迹交点计数，未经逐根核对，非正式经纬密度'
        else:
            value={'candidate_count_px_only':local['candidate_count_median'],'physical_density_per_cm':None}
            status='UNAVAILABLE';unit='未标定'
            note='未完成物理标定或缺少可靠交点；禁止计算正式根/cm'
        params.append(_parameter(idx,value,status,unit,['冻结 V4 轨迹','三条截线',
                          '已确认的实体标定框' if calib['confirmed'] else '未确认的标定信息'],note))
    params.append(_parameter(10,colors,'ESTIMATED','视觉特征',
                  ['RGB 颜色聚类','表面纹理梯度分析'],
                  '独立颜色/纹理分析，纹理方向未参与 V4 经/纬判定'))
    result={'schema_version':'1.0','demo_version':'0.3.0-v5','image_sha256':hashlib.sha256(data).hexdigest(),
            'input':{'width_px':img.shape[1],'height_px':img.shape[0],
                     'calibrated_roi_size_px':[roi.shape[1],roi.shape[0]]},
            'calibration':calib,'quality':quality, 'manual_yarn_reference':reference,
            'direction_evidence':{'family_a_deg':a,'family_b_deg':b,
               'v4_adapter_rotation_deg':angle,'automatic_rotation_estimation':False,
               'reference_axis_image_deg':reference['reference_axis_image_deg'],
               'reference_axis_roi_deg':reference['reference_axis_roi_deg'],
               'reference_source':'USER_TWO_POINT_SAME_REAL_YARN',
               'warning':'V4 输出候选轴仍须与人工参考轴及实际纱线逐项验收；不是自动方向检测'},
            'v4':{'frozen_sha256':v4['frozen_sha256'],'summary':v4['summary'],
                  'family_a_candidate_lines':len(tracks['first']),
                  'family_b_candidate_lines':len(tracks['second']),
                  'provenance':'UNMODIFIED_FROZEN_V4_WITH_IO_ONLY_ADAPTER',
                  'validated_yarn_accuracy':None},
            'family_assignment':{'warp_family':warp_family,'confirmed_by_human':assignment_valid,
                'name_a':'经向' if warp_family=='A' else ('纬向' if warp_family=='B' else '候选组 A'),
                'name_b':'经向' if warp_family=='B' else ('纬向' if warp_family=='A' else '候选组 B')},
            'local_evidence':{'family_a':one,'family_b':two},
            'parameters':params,
            'limits':['使用冻结 V4 的实际候选轨迹，不再绘制 FFT/Gabor 方向参考线',
                      'V4 可能将斜纹视觉纹理误当真实纱线；待人工验收',
                      'V5 不再使用 -13° 默认角度：必须人工点击并确认两点；该参考轴不代表自动经纬识别',
                      '粗细需独立纱线边缘分割，V4 不提供',
                      '组织类型当前依靠人工确认，V4 不是组织分类器',
                      '没有确认 5cm 框不能计算根/cm；有标定时 V4 计数仍为候选'],
            'status_counts':{s:sum(p['status']==s for p in params)
               for s in ['CONFIRMED','ESTIMATED','NEEDS_CONFIRMATION','UNAVAILABLE']}}
    return result,visuals(roi,tracks,one,two)
