"""Sparse template hypotheses. Missing cells are never filled for fitting."""
import numpy as np


def templates(shape):
    r,c=np.indices(shape)
    specs=[('plain','plain',2,1,1),('twill_2_1_slope_plus','twill',3,2,1),
           ('twill_2_1_slope_minus','twill',3,2,-1),('twill_3_1_slope_plus','twill',4,3,1),
           ('twill_3_1_slope_minus','twill',4,3,-1),('twill_2_2_slope_plus','twill',4,2,1),
           ('twill_2_2_slope_minus','twill',4,2,-1),('satin_5_step2','satin',5,1,2),
           ('satin_5_step3','satin',5,1,3)]
    for name,coarse,period,count,step in specs:
        for phase in range(period):
            for reverse in (False,True):
                grid=((c-step*r+phase)%period<count).astype(np.int8)
                if reverse:grid=1-grid
                yield name,coarse,{'period':period,'phase':phase,'complement':reverse},grid


def match(matrix):
    m=np.asarray(matrix,dtype=np.int8);valid=m>=0;n=int(valid.sum())
    result={'observed_cells':n,'shape':list(m.shape),'unknown_cells':int(m.size-n),
            'coarse_candidate':None,'status':'INSUFFICIENT_SUPPORT','physical_weave_verified':False,
            'index_continuity_verified':False,'handedness':'NOT_ASSIGNED_WITHOUT_CONFIRMED_WARP_AND_FACE'}
    if m.ndim!=2 or min(m.shape,default=0)<6 or n<36:return result
    if int(np.count_nonzero(valid.any(0)))<6 or int(np.count_nonzero(valid.any(1)))<6:return result
    if np.unique(m[valid]).size<2:
        result['status']='ONE_SIDED_EVIDENCE';return result
    best={}
    for name,coarse,params,grid in templates(m.shape):
        error=float((grid[valid]!=m[valid]).mean())
        if name not in best or error<best[name]['mismatch']:
            best[name]={'template':name,'coarse':coarse,'mismatch':error,**params}
    ranking=sorted(best.values(),key=lambda x:(x['mismatch'],x['template']));top=ranking[0]
    # Compare different physical repeat hypotheses, not phase/complement copies.
    margin=ranking[1]['mismatch']-top['mismatch'];result.update(ranking=ranking,runnerup_margin=margin)
    if top['mismatch']>.20:result['status']='NO_TEMPLATE_FIT'
    elif margin<.08:result['status']='AMBIGUOUS_TEMPLATES'
    else:
        result.update(status='CONDITIONAL_CANDIDATE_UNVERIFIED_INDICES',coarse_candidate=top['coarse'],template=top['template'])
    return result
