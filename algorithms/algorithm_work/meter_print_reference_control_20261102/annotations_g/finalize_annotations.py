"""Materialize the G-only fixed-print visual audit; no pressure/prediction input."""
from pathlib import Path
import json, hashlib, math
import cv2
import numpy as np

BASE=Path(__file__).resolve().parent
ANCHORS=('outer_psi_10_text_centroid','lower_striped_ball_print_centroid')

# Coordinates manually read from the ID-only 384x384 raw face views.
# Values are image evidence, not neural/silver-pose labels and not pressure-derived.
POINTS={
 1:((181,62),(187,251)), 2:((174,62),(188,252)), 3:((185,62),(183,250)),
 4:((193,63),(181,251)), 5:((197,63),(186,251)), 6:((182,63),(177,251)),
 7:((181,64),(183,250)), 8:((178,64),(187,251)), 9:((185,62),(179,251)),
 10:((190,62),(179,249)), 11:((196,64),(184,249)), 12:((179,62),(182,251)),
 13:(None,None), 14:(None,None), 15:(None,None),
 16:(None,None), 17:(None,None), 18:(None,None),
 19:((177,63),(187,251)), 20:((174,76),(190,264)), 21:((177,63),(184,251)),
 22:((189,64),(180,251)), 23:((195,63),(191,251)), 24:((186,63),(181,251)),
 25:((191,63),(181,251)), 26:((193,63),(180,251)), 27:((192,63),(178,251)),
 28:((192,63),(181,251)), 29:((192,63),(190,251)), 30:((185,63),(178,249)),
 31:((186,63),(186,251)), 32:((180,72),(181,258)), 33:((185,63),(180,251)),
 34:((187,63),(179,251)), 35:((197,63),(188,251)), 36:((181,63),(178,251)),
 37:((181,63),(188,251)), 38:((175,64),(184,251)), 39:((183,63),(187,251)),
 40:((190,64),(184,251)), 41:((198,63),(190,251)), 42:((179,63),(181,251)),
 43:((195,63),(181,251)), 44:((190,62),(177,251)), 45:((187,62),(181,251)),
 46:((177,62),(186,251)), 47:((183,62),(190,251)), 48:((176,62),(188,251)),
 49:(None,None), 50:(None,None), 51:(None,None),
 52:(None,(177,243)), 53:(None,None), 54:(None,None), 55:(None,None),
 56:((196,81),(191,265)), 57:((198,80),(182,263)),
 58:((196,78),(180,262)), 59:((208,75),(188,259)),
}

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def wrap(a): return (a+180)%360-180
def native(point,record):
    if point is None:return None
    t=record['view_transform'];x0,y0,_,_=record['native_crop_xyxy']
    return [x0+(point[0]-t['offset_x'])/t['scale_x'],y0+(point[1]-t['offset_y'])/t['scale_y']]
def roi(point,record):
    if point is None:return None
    req=record['roi_request'];s=req['stride']
    return [(point[0]-req['x0']-(s-1)/2)/s,(point[1]-req['y0']-(s-1)/2)/s]

def main():
    records=[json.loads(s) for s in (BASE/'display_index.jsonl').read_text(encoding='utf-8').splitlines()]
    assert len(records)==59 and len(POINTS)==59
    # Public zero reference selected by the train annotator before any new scoring.
    # This is fixed native geometry, not an automatically registered pose estimate.
    ref_top=[444.53125,35+(82-7)*505/497]
    ref_bottom=[215+269*520/512,35+(359-7)*505/497]
    ref_angle=math.degrees(math.atan2(ref_top[1]-ref_bottom[1],ref_top[0]-ref_bottom[0]))%360
    train_prepared=BASE.parents[2]/'algorithm_work/meter_cnn_training_20261102/prepared_train.jsonl'
    ref_identity=None
    for line in train_prepared.read_text(encoding='utf-8').splitlines():
        item=json.loads(line)
        if item['id']=='D_002':
            ref_identity={k:item[k] for k in ('id','sha256','roi_request')}
            break
    assert ref_identity is not None
    ref_anchors={}
    for k,p in zip(ANCHORS,(ref_top,ref_bottom)):
        rp=roi(p,ref_identity)
        ref_anchors[k]={'native_xy':p,'roi_xy':rp,'visibility':'visible','uncertainty_native_px':4,
                        'within_roi_pixel_center_bounds':all(0<=v<=127 for v in rp)}
    ref={'id':'D_002','source_sha256':ref_identity['sha256'],'roi_request':ref_identity['roi_request'],
         'anchors':ref_anchors,'accepted':all(a['within_roi_pixel_center_bounds'] for a in ref_anchors.values()),
         'public_zero_reference':'annotations_train final D_002 row; no pressure-based selection',
         'anchor_semantics':list(ANCHORS),'top_native_xy':ref_top,'bottom_native_xy':ref_bottom,
         'absolute_image_print_axis_angle_deg':ref_angle,
         'independent_check_view_xy':{'top':[228,84],'bottom':[270,359]},
         'public_reference_view_xy':{'top':[226,82],'bottom':[269,359]},
         'independent_check_max_native_difference_px':math.hypot(2*520/512,2*505/497),
         'uncertainty_native_px_each':4,
         'reference_is_absolute_upright_or_camera_yaw':False,
         'non_blind_ai_diagnostic_not_human_gold':True}
    (BASE/'reference_D002.json').write_text(json.dumps(ref,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    rows=[]; overlay_tiles=[]
    partial_top={4,10,22,56,57,58,59}
    partial_bottom={7,8,9,10,11,12,56}
    dark={3,6,9,12,15,18,21,24,27,30,33,36,39,42,45,48}
    for r in records:
        n=int(r['id'].split('_')[1]);points=POINTS[n]
        anchors={}
        for k,v in zip(ANCHORS,points):
            is_top=k==ANCHORS[0]
            partial=n in (partial_top if is_top else partial_bottom)
            u=2.0
            if n in dark:u=3.0
            if partial:u=max(u,3.0 if is_top else 4.0)
            if n in {56,57,58,59}:u=4.0
            p=native(v,r);pr=roi(p,r)
            if v is None:
                if n in {49,50,51}:vis='absent_non_gauge_front'
                elif 13<=n<=18:vis='occluded_or_not_confidently_localizable'
                elif n==52 and is_top:vis='cropped_out_of_native_image'
                elif n==53:vis='unresolved_blur'
                elif n in {54,55}:vis='unresolved_overexposure'
                else:vis='unknown'
                uncertainty=None
            else:
                vis='partially_visible' if partial else 'visible'
                uncertainty=u/max(r['view_transform']['scale_x'],r['view_transform']['scale_y'])
            anchors[k]={'native_xy':p,'roi_xy':pr,'visibility':vis,
                        'uncertainty_native_px':uncertainty,'uncertainty_is_certified_bound':False,
                        'manually_read_view_xy':list(v) if v is not None else None,
                        'within_roi_pixel_center_bounds':bool(pr is not None and all(0<=q<=127 for q in pr)),
                        'within_roi_uncertainty_bounds':bool(pr is not None and all(uncertainty/r['roi_request']['stride']<=q<=127-uncertainty/r['roi_request']['stride'] for q in pr))}
        native_ok=all(a['native_xy'] is not None for a in anchors.values())
        roi_ok=native_ok and all(a['within_roi_pixel_center_bounds'] for a in anchors.values())
        if n in {49,50,51}:reason='No specified printed gauge face: empty background / football / reverse metal face respectively.'
        elif 13<=n<=18:reason='Counterweight covers nearly all lower striped-ball print; thin needle and/or glare also confounds the tiny top 10. No static fallback substituted.'
        elif n==52:reason='Top 10 lies beyond cropped native image; lower print alone cannot define fixed two-anchor direction.'
        elif n==53:reason='Severe defocus: neither fixed print centroid can be reliably distinguished.'
        elif n in {54,55}:reason='Severe overexposure washes out the fixed printed anchors.'
        elif n==56:reason='Both centers localizable from visible static contours; lower ball partially covered by tool, larger uncertainty.'
        elif n in {57,58,59}:reason='Tool crosses central/left face, but both specified static print locations remain visible; blur/partial top text increases uncertainty.'
        elif n in partial_bottom:reason='Top 10 and remaining lower-ball circumference/stripes permit center estimation; counterweight covers a portion, larger uncertainty.'
        else:reason='Both fixed static printed landmarks are visually localizable in the source image.'
        if native_ok and not roi_ok:reason+=' At least one landmark is outside the current 128ROI; not MCU-input-available.'
        angle=roll=None
        if native_ok:
            t,b=[anchors[k]['native_xy'] for k in ANCHORS]
            angle=math.degrees(math.atan2(t[1]-b[1],t[0]-b[0]))%360
            roll=wrap(angle-ref_angle)
            sep=math.dist(t,b)
            total_u=sum(anchors[k]['uncertainty_native_px'] for k in ANCHORS)
            angular_u=math.degrees(math.atan2(total_u,sep))
        else:angular_u=None
        row={'id':r['id'],'source_sha256':r['sha256'],
             'source_kind':'current original native PNG; identity-only face view',
             'annotation_kind':'AI visual diagnostic reference, not blind human gold and not automatic runtime output',
             'historical_exposure_disclosure':'Annotator previously saw 8 audit sidecars and old project results; these points were independently re-read from raw ID-only views, not copied or pose-guided.',
             'anchors':anchors,'accepted_native':native_ok,'accepted':roi_ok,
             'reason':reason,'absolute_image_print_axis_angle_deg':angle,
             'relative_print_roll_deg':roll,'relative_reference_id':'D_002',
             'estimated_axis_uncertainty_deg':angular_u,
             'angle_convention':'atan2(top_y-bottom_y, top_x-bottom_x) modulo360; image x right/y down, clockwise positive; relative=wrap(query-reference)',
             'side_view_or_absolute_upright_estimate':False,
             'roi_request':r['roi_request'],'view_transform':r['view_transform'],'native_crop_xyxy':r['native_crop_xyxy'],
             'source_view_sha256':r['clean_view_sha256'],
             'pressure_or_query_neural_pose_used_for_points':False,'ready_as_training_label':False}
        rows.append(row)
        im=cv2.imdecode(np.fromfile(r['clean_view'],np.uint8),1)
        for k,color in zip(ANCHORS,[(0,180,0),(220,60,0)]):
            p=anchors[k]['manually_read_view_xy']
            if p:
                q=tuple(round(x) for x in p)
                cv2.drawMarker(im,q,color,cv2.MARKER_CROSS,12,1,cv2.LINE_AA)
        if all(points):cv2.line(im,tuple(points[0]),tuple(points[1]),(0,160,220),1,cv2.LINE_AA)
        cv2.imencode('.png',im)[1].tofile(str(BASE/'review_views'/f'{r["id"]}.png'))
        tile=np.full((414,384,3),255,np.uint8);tile[30:]=im
        cv2.putText(tile,r['id']+(' REF' if roi_ok else ' UNKNOWN'),(8,22),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,0,0),1,cv2.LINE_AA)
        overlay_tiles.append(tile)
    target=BASE/'print_annotations.jsonl'
    target.write_text('\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n',encoding='utf-8')
    for page in range(0,len(overlay_tiles),9):
        canvas=np.full((1242,1152,3),255,np.uint8)
        for j,t in enumerate(overlay_tiles[page:page+9]):
            yy,xx=divmod(j,3);canvas[yy*414:(yy+1)*414,xx*384:(xx+1)*384]=t
        cv2.imencode('.png',canvas)[1].tofile(str(BASE/f'review_contact_{page//9+1:02d}.png'))
    receipt={'status':'COMPLETE_AI_VISUAL_DIAGNOSTIC_SIDECAR_NOT_GOLD','denominator':59,
             'accepted_native':sum(r['accepted_native'] for r in rows),'accepted_roi':sum(r['accepted'] for r in rows),
             'unknown_native_ids':[r['id'] for r in rows if not r['accepted_native']],
             'native_visible_but_roi_unavailable_ids':[r['id'] for r in rows if r['accepted_native'] and not r['accepted']],
             'source_pressure_or_model_predictions_used':False,
             'forbidden_H_ABC_access':False,'canonical_or_original_modified':False,
             'annotation_sha256':sha(target),'public_reference_sha256':sha(BASE/'reference_D002.json'),
             'quality_limits':['manual AI non-blind diagnostic, no certified pixel uncertainty',
                               'two print centroids provide image-relative direction, not full perspective/camera pose',
                               'baked original HDMI peripheral OSD is retained and not used as label truth',
                               'native-to128ROI availability is separately checked; no outside point clamping',
                               'no pressure fitting, model training, new evaluation, or device operations']}
    (BASE/'completion.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))

if __name__=='__main__':
    (BASE/'review_views').mkdir(exist_ok=True)
    main()
