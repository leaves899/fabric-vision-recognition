from __future__ import annotations
"""Correct one-to-one yarn-centre evaluation at a physical distance gate.

CRITICAL: minimizing unbounded L1 distance with linear_sum_assignment and
THEN thresholding is NOT the same as maximizing matched physical yarns.
On periodic unequal-cardinality sequences an optimal L1 assignment may
have a whole-pitch shift despite near-perfect within-gate matches.

This scorer uses *maximum cardinality* among gated physical correspondences,
with a tiny distance tie-break. Evaluation ONLY; never an inference prior.
"""
import numpy as np
from scipy.optimize import linear_sum_assignment


def cardinality_gated_yarn_match(predicted, physical_truth, pitch_px,
                                 tolerance_fraction=.32):
    a=np.asarray(predicted,dtype=np.float64)
    b=np.asarray(physical_truth,dtype=np.float64)
    if a.ndim!=1 or b.ndim!=1:
        raise ValueError("ONE_DIMENSIONAL_CENTRE_COORDINATES_REQUIRED")
    if not np.isfinite(a).all() or not np.isfinite(b).all():
        raise ValueError("NONFINITE_CENTRE_COORDINATES")
    if pitch_px<=0 or tolerance_fraction<=0 or tolerance_fraction>=.5:
        raise ValueError("BAD_PHYSICAL_MATCH_GATE")
    n=len(a);m=len(b)
    if n==0 or m==0:
        return {"matches":0,"predicted":n,"truth":m,"precision":0.,
                "recall":0.,"f1":0.,"matched_distances_fraction_pitch":[]}
    tolerance=pitch_px*tolerance_fraction
    D=np.abs(a[:,None]-b[None,:])
    valid=D<tolerance
    # Dummy nodes allow both false positives and false negatives.
    # A permitted edge costs <=0.01; an unmatched pair costs 1+1.
    # Forbidden physical edges cost 3, so never beat two dummies.
    cost=np.zeros((n+m,n+m),dtype=np.float64)
    cost[:n,:m]=np.where(valid,.01*D/tolerance,3.)
    cost[:n,m:]=1.
    cost[n:,:m]=1.
    ii,jj=linear_sum_assignment(cost)
    accepted=[(int(i),int(j)) for i,j in zip(ii,jj)
              if i<n and j<m and valid[i,j]]
    matches=len(accepted)
    precision=matches/n
    recall=matches/m
    f1=2*matches/(n+m)
    return {"matches":matches,"predicted":n,"truth":m,
            "precision":round(float(precision),6),"recall":round(float(recall),6),
            "f1":round(float(f1),6),
            "matched_distances_fraction_pitch":[
               round(float(D[i,j]/pitch_px),6) for i,j in accepted],
            "scoring":"MAX_CARDINALITY_WITHIN_PHYSICAL_GATE"}


def legacy_unbounded_assignment(predicted, physical_truth, pitch_px,
                                 tolerance_fraction=.32):
    a=np.asarray(predicted,float);b=np.asarray(physical_truth,float)
    if not len(a) or not len(b):return 0.
    D=np.abs(a[:,None]-b[None,:])
    ii,jj=linear_sum_assignment(D)
    valid=int(np.sum(D[ii,jj] < tolerance_fraction*pitch_px))
    return float(2*valid/(len(a)+len(b)))
