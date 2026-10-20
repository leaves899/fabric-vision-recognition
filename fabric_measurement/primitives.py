"""Auditable image primitives reused from the local centerline PoC. See PROVENANCE.json."""
from __future__ import annotations
from dataclasses import dataclass
import cv2
import numpy as np
from scipy.ndimage import gaussian_filter, gaussian_filter1d
from scipy.optimize import linear_sum_assignment
from scipy.signal import find_peaks

@dataclass(frozen=True)
class Config:
    tensor_scales: tuple[float, ...] = (.8, 1.5, 2.5)
    ridge_scales: tuple[float, ...] = (1.4, 2.4, 4.)
    reference_size: int = 512
    tensor_max_side: int = 512
    min_direction_separation_deg: float = 40.
    orientation_search_half_width_deg: float = 20.
    direction_min_peak_to_median: float = 1.8
    direction_min_mass: float = .07
    normalization_sigma_fraction: float = .045
    sample_step_fraction: float = .008
    ridge_min_response: float = .18
    ridge_min_prominence: float = .10
    max_missing_slices: int = 2
    min_track_points: int = 8
    min_track_span_fraction: float = .22
    min_track_coverage: float = .5
    max_density_disagreement: float = .15
    max_spacing_cv: float = .30
    max_section_count_cv: float = .20
    min_section_centers: int = 5


def angular_distance(a, b):
    return abs((float(a)-float(b)+90) % 180-90)


def load_rgb(path):
    from PIL import Image, ImageOps
    with Image.open(path) as image:
        return np.asarray(ImageOps.exif_transpose(image).convert('RGB')).copy()


def save_rgb(path, image):
    from PIL import Image
    Image.fromarray(np.uint8(np.clip(image, 0, 255))).save(path)


def grayscale(rgb):
    a = np.asarray(rgb)
    integer_input = np.issubdtype(a.dtype, np.integer)
    if a.ndim == 3 and a.shape[2] == 3:
        a = cv2.cvtColor(a.astype(np.float32), cv2.COLOR_RGB2GRAY)
    if a.ndim != 2 or min(a.shape) < 64 or not np.isfinite(a).all():
        raise ValueError('Expected a finite grayscale/RGB image, minimum side 64 pixels')
    a = a.astype(np.float32)
    if integer_input or a.max() > 1:
        a /= 255.
    if a.min() < 0 or a.max() > 1:
        raise ValueError('Image intensity must be in [0,1] or [0,255]')
    return a


def normalize(gray, cfg):
    sigma = max(5., min(gray.shape)*cfg.normalization_sigma_fraction)
    mean = gaussian_filter(gray, sigma)
    variance = np.maximum(gaussian_filter(gray*gray, sigma)-mean*mean, 0)
    floor = max(.025, float(np.std(gray))*.15)
    return np.clip((gray-mean)/np.sqrt(variance+floor*floor), -3, 3).astype(np.float32)


def _circular_peaks(hist, distance=12):
    indices = find_peaks(np.tile(hist, 3), distance=distance)[0]
    return indices[(indices >= 180) & (indices < 360)]-180


def direction_field(gray, cfg):
    scale = min(1., cfg.tensor_max_side/max(gray.shape))
    small = cv2.resize(gray, None, fx=scale, fy=scale) if scale < 1 else gray
    hist = np.zeros(180, dtype=float)
    per_scale = []
    field_angle = coherence = None
    for sigma in cfg.tensor_scales:
        z = gaussian_filter(small, sigma)
        gy, gx = np.gradient(z)
        xx = gaussian_filter(gx*gx, sigma)
        yy = gaussian_filter(gy*gy, sigma)
        xy = gaussian_filter(gx*gy, sigma)
        energy = xx+yy
        co = np.sqrt((xx-yy)**2+4*xy*xy)/(energy+1e-10)
        tangent = (.5*np.degrees(np.arctan2(2*xy, xx-yy))+90) % 180
        weight = np.sqrt(energy)*co**2
        weight[co < .3] = 0
        hs = np.bincount(tangent.astype(int).ravel(), weights=weight.ravel(), minlength=180)
        hs = hs/max(float(hs.sum()), 1e-10)
        smooth = gaussian_filter1d(hs, 3., mode='wrap')
        peaks = sorted(_circular_peaks(smooth), key=lambda p: -smooth[p])
        per_scale.append(dict(sigma_px_at_tensor_resolution=sigma,
                              peaks=[dict(angle_deg=int(p), strength=float(smooth[p])) for p in peaks[:5]]))
        hist += hs/len(cfg.tensor_scales)
        if field_angle is None:
            field_angle, coherence = tangent, co
    hist = gaussian_filter1d(hist, 3., mode='wrap')
    candidates = sorted(_circular_peaks(hist), key=lambda p: -hist[p])
    selected = []
    for p in candidates:
        if all(angular_distance(p, q['angle_deg']) >= cfg.min_direction_separation_deg for q in selected):
            nearby = np.array([angular_distance(p, a) <= 12 for a in range(180)])
            local = np.array([(p+offset) % 180 for offset in range(-4, 5)])
            # Refine only within this independent peak, never force a perpendicular pair.
            weights = hist[local]
            a = np.deg2rad(2*local)
            angle = float(np.degrees(np.arctan2(np.sum(weights*np.sin(a)),
                                                np.sum(weights*np.cos(a))))/2 % 180)
            score = float(hist[p]/max(float(np.median(hist)), 1e-10))
            mass = float(hist[nearby].sum())
            selected.append(dict(angle_deg=angle, peak_to_median=score, mass_within_12deg=mass,
                                 sufficient=bool(score >= cfg.direction_min_peak_to_median and mass >= cfg.direction_min_mass)))
            if len(selected) == 2:
                break
    selected.sort(key=lambda p: p['angle_deg'])
    result = dict(method='multiscale local structure tensor, two independent circular histogram peaks',
                  directions=selected, histogram=hist.tolist(), scales=per_scale,
                  two_direction_evidence=bool(len(selected) == 2 and all(x['sufficient'] for x in selected)),
                  angle_convention='image coordinates x-right=0,y-down=90,modulo180',
                  forced_orthogonality=False)
    return result, (field_angle, coherence, small.shape)


def rotate_frame(gray, angle):
    h, w = gray.shape
    m = cv2.getRotationMatrix2D(((w-1)/2, (h-1)/2), angle, 1.)
    rw = int(np.ceil(w*abs(m[0,0])+h*abs(m[0,1])))
    rh = int(np.ceil(h*abs(m[0,0])+w*abs(m[0,1])))
    m[:,2] += [(rw-w)/2, (rh-h)/2]
    frame = cv2.warpAffine(gray, m, (rw,rh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)
    valid = cv2.warpAffine(np.ones((h,w),np.uint8),m,(rw,rh),flags=cv2.INTER_NEAREST)
    return frame, valid, m


def refine_by_directional_coherence(normalized, tensor_angle, cfg):
    """Local float tangent need not equal the direction linking successive floats.

    Search the tensor neighborhood for coherent along-tangent averaging.
    No warp hint, orthogonality constraint, or expected density enters this score.
    A boundary winner is flagged because a motif may be pulling the search away.
    """
    small=cv2.resize(normalized,(0,0),fx=min(1.,384/max(normalized.shape)),
                     fy=min(1.,384/max(normalized.shape)))
    def score(angle):
        image,mask,_=rotate_frame(small,angle)
        counts=mask.sum(axis=1)
        valid=counts>.6*min(small.shape)
        if np.count_nonzero(valid)<32:return 0.
        profile=(image*mask).sum(axis=1)/np.maximum(counts,1)
        profile-=gaussian_filter1d(profile,max(6.,min(small.shape)/32))
        return float(np.mean(profile[valid]**2))
    width=cfg.orientation_search_half_width_deg
    angles=np.arange(tensor_angle-width,tensor_angle+width+.01,1.)
    scores=np.array([score(a) for a in angles])
    best=int(np.argmax(scores))
    local_angles=np.arange(angles[best]-.75,angles[best]+.76,.25)
    local_angles=local_angles[(local_angles>=angles[0])&(local_angles<=angles[-1])]
    local_scores=[score(a) for a in local_angles]
    winner=float(local_angles[int(np.argmax(local_scores))] % 180)
    return winner,dict(tensor_angle_deg=tensor_angle,refined_angle_deg=winner,
                       method='directional projection coherence in tensor neighborhood',
                       coarse_angles_deg=(angles%180).tolist(),coarse_scores=scores.tolist(),
                       boundary_peak=bool(best in (0,len(angles)-1)),
                       peak_to_median=float(max(local_scores)/max(float(np.median(scores)),1e-9)),
                       tensor_refinement_difference_deg=angular_distance(tensor_angle,winner))


def _crossing(a, b):
    """Proper crossing for two monotonic candidate edges in tangent-normal frame."""
    p,q = np.array(a[0]),np.array(a[1])
    r,s = np.array(b[0]),np.array(b[1])
    def cross(u,v):
        return u[0]*v[1]-u[1]*v[0]
    return cross(q-p,r-p)*cross(q-p,s-p) < 0 and cross(s-r,p-r)*cross(s-r,q-r) < 0


def link_ridges(response, safe, cfg, sigmas):
    h,w = response.shape
    step = max(3,round(min(response.shape)*cfg.sample_step_fraction))
    min_dist = max(3,int(round(2*min(sigmas))))
    max_jump = max(3., min_dist*.65)
    tracks, active = [], []
    crossing_rejections = 0
    observed_total = 0
    for x in range(step,w-step,step):
        profile = gaussian_filter1d(response[:,x], .65)
        ys, properties = find_peaks(profile,height=cfg.ridge_min_response,
                                    prominence=cfg.ridge_min_prominence,distance=min_dist)
        ys = ys[safe[ys,x]]
        observed_total += len(ys)
        active = [t for t in active if x-t['points'][-1][0] <= step*(cfg.max_missing_slices+1)]
        used = set()
        if active and len(ys):
            cost = np.full((len(active),len(ys)),1e6)
            for i,t in enumerate(active):
                last = t['points'][-1]
                gap = (x-last[0])/step
                slope = 0.
                if len(t['points']) > 1:
                    prev=t['points'][-2]
                    slope = np.clip((last[1]-prev[1])/(last[0]-prev[0]),-.35,.35)
                prediction = last[1]+slope*(x-last[0])
                distance = abs(ys-prediction)
                gate = (distance <= max_jump*np.sqrt(gap)) & (abs(ys-last[1]) <= .65*(x-last[0])+2)
                cost[i,gate] = distance[gate]/(max_jump*np.sqrt(gap))+.1*(gap-1)
            ri,ci = linear_sum_assignment(cost)
            edges = []
            for i,j in sorted(zip(ri,ci),key=lambda ij:cost[ij]):
                if cost[i,j] >= 1e5:
                    continue
                edge = (active[i]['points'][-1][:2], [x,float(ys[j])])
                if any(_crossing(edge,old) for old in edges):
                    crossing_rejections += 1
                    continue
                active[i]['points'].append([x,float(ys[j]),float(response[ys[j],x])])
                used.add(int(j));edges.append(edge)
        for j,y in enumerate(ys):
            if j not in used:
                t=dict(id=len(tracks)+1,points=[[x,float(y),float(response[y,x])]])
                tracks.append(t);active.append(t)
    for t in tracks:
        points=np.asarray(t['points'])
        span=float(points[-1,0]-points[0,0])
        # Available chord at median y, so rotation does not penalize all corner lines.
        middle=int(np.clip(np.median(points[:,1]),0,h-1))
        valid_x=np.flatnonzero(safe[middle])
        chord=float(valid_x[-1]-valid_x[0]) if len(valid_x)>1 else float(w)
        coverage=len(points)/(span/step+1)
        reasons=[]
        if len(points)<cfg.min_track_points: reasons.append('too_few_observations')
        if span<cfg.min_track_span_fraction*chord: reasons.append('short_span')
        if coverage<cfg.min_track_coverage: reasons.append('low_observed_coverage')
        t.update(span_px=span,span_fraction=span/max(chord,1),observed_coverage=float(coverage),
                 accepted_candidate=not reasons,reasons=reasons,
                 gaps=int(sum(points[i,0]-points[i-1,0]>step*1.5 for i in range(1,len(points)))))
    return tracks,dict(sample_step_px=step,min_peak_distance_px=min_dist,
                       ridge_observations=observed_total,crossing_links_rejected=crossing_rejections)


def density_from_tracks(tracks, safe, step, cfg, px_per_cm=None):
    h,w=safe.shape
    sections=[]
    all_spacings=[]
    retained=[t for t in tracks if t['accepted_candidate']]
    for fraction in np.linspace(.2,.8,7):
        x=int(round(fraction*(w-1)))
        valid_y=np.flatnonzero(safe[:,x])
        if len(valid_y)<32:
            continue
        centers=[]
        for t in retained:
            p=np.asarray(t['points'])
            right=int(np.searchsorted(p[:,0],x))
            if right==len(p):
                continue
            if p[right,0]==x:
                y=float(p[right,1]);supported=True
            elif right==0:
                continue
            else:
                a,b=p[right-1],p[right]
                # Interpolation over a single observed sampling interval only.
                supported=b[0]-a[0]<=step*1.5
                y=float(np.interp(x,[a[0],b[0]],[a[1],b[1]]))
            if supported and valid_y[0]<=y<=valid_y[-1]:
                centers.append(dict(track_id=t['id'],y=y))
        centers.sort(key=lambda c:c['y'])
        values=np.array([c['y'] for c in centers])
        spacings=np.diff(values)
        enough=len(centers)>=cfg.min_section_centers
        if enough:
            all_spacings.extend(spacings.tolist())
        section=dict(x=x,centers=centers,number=len(centers),valid_span_px=int(valid_y[-1]-valid_y[0]),
                     count_density_per_px=float((len(values)-1)/(values[-1]-values[0])) if enough else None,
                     count_formula='(N-1)/(last_center-first_center); excludes boundary partial pitches',
                     median_spacing_px=float(np.median(spacings)) if enough else None)
        sections.append(section)
    counts=[s['count_density_per_px'] for s in sections if s['count_density_per_px'] is not None]
    spacing=np.asarray(all_spacings)
    if not len(counts) or not len(spacing):
        return dict(status='REJECTED',reasons=['insufficient_supported_centerline_intersections'],sections=sections,
                    count_density_per_px=None,spacing_density_per_px=None,
                    count_density_per_cm=None,spacing_density_per_cm=None,physical_accuracy='NOT_EVALUATED')
    d1=float(np.median(counts))
    pitch=float(np.median(spacing));d2=1/pitch
    disagreement=abs(d1-d2)/max(d1,d2)
    cv=float(np.std(spacing)/max(np.mean(spacing),1e-9))
    section_cv=float(np.std(counts)/max(np.mean(counts),1e-9))
    warnings=[]
    if disagreement>cfg.max_density_disagreement: warnings.append('count_spacing_disagree')
    if cv>cfg.max_spacing_cv: warnings.append('irregular_or_missed_duplicated_centers')
    if section_cv>cfg.max_section_count_cv: warnings.append('cross_section_density_unstable')
    if len(counts)<4: warnings.append('too_few_valid_cross_sections')
    if len(retained)<4: warnings.append('too_few_candidate_tracks')
    return dict(status='LOW_CONFIDENCE' if warnings else 'INTERNAL_CONSISTENT_CANDIDATE',reasons=warnings,
                count_density_per_px=d1,spacing_density_per_px=d2,
                count_density_per_cm=d1*px_per_cm if px_per_cm else None,
                spacing_density_per_cm=d2*px_per_cm if px_per_cm else None,
                median_spacing_px=pitch,spacing_cv=cv,section_density_cv=section_cv,
                path_relative_disagreement=disagreement,valid_sections=len(counts),sections=sections,
                physical_accuracy='NOT_EVALUATED',
                dependency='Both paths share the detected centerlines; agreement is not independent accuracy proof')


def _overlay(rgb, tracks, color, step):
    image=rgb.copy()
    for t in tracks:
        if not t['accepted_candidate']:
            continue
        points=np.rint(t['points_xy']).astype(int)
        for i in range(1,len(points)):
            # Dashed gaps show inferred connection, not observed centerline pixels.
            gap=t['points'][i][0]-t['points'][i-1][0]>step*1.5
            if gap:
                for frac in np.arange(0,1,.25):
                    a=points[i-1]+frac*(points[i]-points[i-1])
                    b=points[i-1]+min(frac+.12,1)*(points[i]-points[i-1])
                    cv2.line(image,tuple(np.rint(a).astype(int)),tuple(np.rint(b).astype(int)),(255,170,30),1,cv2.LINE_AA)
            else:
                cv2.line(image,tuple(points[i-1]),tuple(points[i]),color,1,cv2.LINE_AA)
        for pt in points[::3]:
            cv2.circle(image,tuple(pt),1,color,-1,cv2.LINE_AA)
        if len(points):
            pt=points[len(points)//2]
            cv2.putText(image,str(t['id']),tuple(pt),cv2.FONT_HERSHEY_SIMPLEX,.33,(0,0,0),2,cv2.LINE_AA)
            cv2.putText(image,str(t['id']),tuple(pt),cv2.FONT_HERSHEY_SIMPLEX,.33,color,1,cv2.LINE_AA)
    return image

