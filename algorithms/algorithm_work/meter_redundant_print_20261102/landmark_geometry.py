"""Frozen redundant-identity similarity consensus, no pressure or image I/O.

Image x-right/y-down => positive fitted rotation is clockwise. Coordinates are
normalized using original predicted hub/locator radius to center64/radius48.
An identified match requires >=3 point identities, not a single pair.
"""
from itertools import combinations
import math
import numpy as np

NAMES=('outer_psi_5_text_centroid','outer_psi_10_text_centroid','outer_psi_15_text_centroid',
       'upper_basketball_logo_centroid','middle_soccer_logo_centroid','lower_striped_ball_print_centroid')
CONFIG=dict(minimum_consensus=3,baseline_min=30.,point_separation_min=8.,
    inlier_residual_max=2.5,RMS_max=2.,scale_min=.85,scale_max=1.15,
    center_displacement_max=20.,absolute_roll_D002_max_exclusive=24.,
    competing_angle_difference=5.,competing_RMS_gap=.5,center=[64.,64.])


def wrap(a):return (a+180)%360-180


def fit_similarity(reference,query):
    x=np.asarray(reference,np.float64);y=np.asarray(query,np.float64)
    if x.shape!=y.shape or x.ndim!=2 or x.shape[1]!=2 or len(x)<2:raise ValueError('at least2 corresponding2D points')
    xc=x-x.mean(0);yc=y-y.mean(0);den=float((xc*xc).sum())
    if den<1e-12:return None
    a=float((xc*yc).sum()/den)
    b=float((xc[:,0]*yc[:,1]-xc[:,1]*yc[:,0]).sum()/den)
    linear=np.array([[a,-b],[b,a]],np.float64)
    intercept=y.mean(0)-linear@x.mean(0)
    predicted=x@linear.T+intercept
    center=np.array(CONFIG['center']);displacement=linear@center+intercept-center
    return dict(matrix=np.c_[linear,intercept],scale=math.hypot(a,b),rotation_deg=math.degrees(math.atan2(b,a)),
        center_displacement=float(np.linalg.norm(displacement)),residuals=np.linalg.norm(predicted-y,axis=1),
        RMS=float(np.sqrt(np.mean((predicted-y)**2)*2)))


def predict(fit,points):
    m=np.asarray(fit['matrix']);return np.asarray(points)@m[:,:2].T+m[:,2]


def _spread(points):
    p=np.asarray(points)
    ds=[float(np.linalg.norm(p[i]-p[j])) for i,j in combinations(range(len(p)),2)]
    return (min(ds),max(ds)) if ds else (0.,0.)


def consensus(reference,query,canonical_roll_relative_D002=0.):
    names=[name for name in NAMES if name in reference and name in query]
    output=dict(accepted=False,reason='INSUFFICIENT_VISIBLE_IDENTIFIED_LANDMARKS',
        available_identities=names,required_identities=CONFIG['minimum_consensus'],
        full_perspective_rectification=False)
    if len(names)<CONFIG['minimum_consensus']:return output
    x=np.array([reference[n] for n in names],np.float64);y=np.array([query[n] for n in names],np.float64)
    assert np.isfinite(x).all() and np.isfinite(y).all()
    candidates=[];seen=set()
    for i,j in combinations(range(len(names)),2):
        if min(np.linalg.norm(x[i]-x[j]),np.linalg.norm(y[i]-y[j]))<CONFIG['baseline_min']:continue
        fit=fit_similarity(x[[i,j]],y[[i,j]])
        if fit is None:continue
        inliers=np.linalg.norm(predict(fit,x)-y,axis=1)<=CONFIG['inlier_residual_max']
        # Fixed two refits, no query-specific threshold adaptation.
        for _ in range(2):
            if inliers.sum()<CONFIG['minimum_consensus']:break
            fit=fit_similarity(x[inliers],y[inliers])
            inliers=np.linalg.norm(predict(fit,x)-y,axis=1)<=CONFIG['inlier_residual_max']
        if inliers.sum()<CONFIG['minimum_consensus']:continue
        fit=fit_similarity(x[inliers],y[inliers]);key=tuple(np.flatnonzero(inliers))
        if key in seen:continue
        seen.add(key)
        near,span=_spread(y[inliers]);_,refspan=_spread(x[inliers])
        roll=wrap(fit['rotation_deg']+canonical_roll_relative_D002)
        if not CONFIG['scale_min']<=fit['scale']<=CONFIG['scale_max']:continue
        if fit['center_displacement']>CONFIG['center_displacement_max'] or abs(roll)>=CONFIG['absolute_roll_D002_max_exclusive']:continue
        if near<CONFIG['point_separation_min'] or min(span,refspan)<CONFIG['baseline_min']:continue
        if fit['RMS']>CONFIG['RMS_max'] or fit['residuals'].max()>CONFIG['inlier_residual_max']:continue
        candidates.append(dict(inlier_indices=key,inlier_identities=[names[k] for k in key],
            outlier_identities=[names[k] for k in range(len(names)) if k not in key],
            inlier_count=len(key),RMS=fit['RMS'],rotation_deg=fit['rotation_deg'],relative_roll_deg=roll,
            scale=fit['scale'],center_displacement=fit['center_displacement'],baseline=span,
            matrix=np.asarray(fit['matrix']).tolist(),residuals=np.linalg.norm(predict(fit,x)-y,axis=1).tolist()))
    if not candidates:
        output.update(reason='NO_CONSISTENT_REDUNDANT_LANDMARK_GEOMETRY');return output
    candidates.sort(key=lambda f:(-f['inlier_count'],f['RMS'],f['inlier_indices']))
    best=candidates[0]
    ambiguous=[f for f in candidates[1:] if abs(wrap(f['relative_roll_deg']-best['relative_roll_deg']))>CONFIG['competing_angle_difference']
        and f['inlier_count']>=best['inlier_count'] and f['RMS']<=best['RMS']+CONFIG['competing_RMS_gap']]
    if ambiguous:
        output.update(reason='REDUNDANT_LANDMARK_GEOMETRY_AMBIGUOUS',best=best,competing=ambiguous);return output
    output.update(accepted=True,reason='REDUNDANT_IDENTIFIED_LANDMARK_CONSENSUS',**best,
        canonical_roll_relative_D002=canonical_roll_relative_D002,alternative_hypotheses=len(candidates)-1)
    return output
