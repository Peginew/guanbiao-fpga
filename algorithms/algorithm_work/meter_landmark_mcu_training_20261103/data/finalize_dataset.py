"""Freeze reviewed six-print supervision in original128ROI coordinates.

coordinate_mask and visibility_mask are separate. Unknown positive heads are
ignored, explicitly occluded/absent heads supervise no visible heat peak, and
reliable partial landmarks keep an uncertain visible coordinate. No pressure or
needle-angle labels participate. G is converted only from frozen validation
sidecars; it never supplies training/template samples.
"""
from pathlib import Path
import json,hashlib,math
import cv2
import numpy as np
from prepare_silver_candidates import BASE,ROOT,PKG,NAMES,rows,sha,roi

OLD=ROOT/'algorithm_work/meter_print_reference_control_20261102'
GSOURCE=ROOT/'algorithm_work/meter_redundant_print_20261102/annotations/print_annotations.jsonl'
def save(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf-8')
def native_from_view(p,d):
    x0,y0,_,_=d['native_crop_xyxy'];t=d['view_transform']
    return [x0+(p[0]-t['offset_x'])/t['scale_x'],y0+(p[1]-t['offset_y'])/t['scale_y']]

def visibility_ledger():
    # All21 contact pages (D/E/F 7each) were inspected before model training.
    # These compact codes record observations, not pressure-order assumptions:
    # v visible, p reliable partial, o explicitly occluded, u unresolved, a absent.
    m={}
    for g in 'DEF':
        for n in range(1,60):m[f'{g}_{n:03d}']='vvvvvv'
    for g in 'DE':
        for n in range(1,7):m[f'{g}_{n:03d}']='vvvppv'
        for n in range(7,13):m[f'{g}_{n:03d}']='vvvpop'
        for n in range(13,19):m[f'{g}_{n:03d}']='vvvppv'
        for n in range(19,31):m[f'{g}_{n:03d}']='vvvvpv'
    for n in range(1,7):m[f'F_{n:03d}']='vvvppv'
    for n in range(7,19):m[f'F_{n:03d}']='vvvpop'
    for n in range(19,25):m[f'F_{n:03d}']='vvvppv'
    for n in range(25,31):m[f'F_{n:03d}']='vvvvpv'
    for g in 'DF':
        for n in (49,50,51):m[f'{g}_{n:03d}']='aaaaaa'
    for n in (47,48,49):m[f'E_{n:03d}']='aaaaaa'
    # Extreme/unresolved exposure/defocus remains unknown, not negative evidence.
    for id in ('D_052','D_053','D_054','D_055','E_050','E_051','E_052','E_053',
               'F_003','F_009','F_010','F_015','F_021','F_027','F_033','F_039','F_045','F_053','F_054','F_055'):
        m[id]='uuuuuu'
    for id in ('D_004','D_010','D_022','D_028','D_034'):
        v=list(m[id]);v[2]='u';v[1]='p';m[id]=''.join(v)
    # The tool covers these identities, independently of the other print points.
    m.update(D_056='vvvpoo',D_057='vvvooo',D_058='ovvvvv',D_059='ovvvvv',
             E_028='vvovvv',E_054='vpvooo',E_055='vvvvpv',E_056='ovvvvv',E_057='ovvvvv',
             E_058='vvvppv',E_059='pppppp',F_016='vuvuuu',F_052='uuuppv',
             F_056='vvvpoo',F_057='vvvooo',F_058='ovvvvv',F_059='ovvvvv')
    return m

# Independent raw384 visual coordinates for clear unregistered observations.
# No static layout or pressure inversion supplies missing coordinates.
MANUAL={
 'F_016':{0:(82,151),2:(301,138)},
 'F_023':{0:(91,129),1:(208,77),2:(298,130),3:(202,150),4:(200,226),5:(201,260)},
 'F_026':{0:(71,232),1:(180,137),2:(304,201),3:(194,221),4:(198,291),5:(200,329)},
 'F_057':{0:(88,147),1:(209,72),2:(308,150)},
}

def pack_head(native,vis,unc_native,req,method,reason):
    p=None if native is None else roi(native,req)
    native_ok=native is not None and 0<=native[0]<1280 and 0<=native[1]<720
    inside=p is not None and all(0<=x<=127 for x in p)
    if vis in ('visible','partial') and (not native_ok or not inside):
        vis='unknown';reason+=' Point is outside native capture or current ROI; not clamped.'
    if vis in ('visible','partial') and p is None:
        vis='unknown';reason+=' No reviewed coordinate source available; mask ignored.'
    coord=vis in ('visible','partial') and p is not None and native_ok and inside
    vm=vis!='unknown';target=1 if vis in ('visible','partial') else 0 if vm else None
    return dict(xy_roi=p if coord else None,xy_native=list(map(float,native)) if coord else None,
        visibility=vis,coordinate_mask=int(coord),visibility_mask=int(vm),vis_target=target,
        uncertainty_px=float(unc_native/req['stride']) if coord and unc_native is not None else None,
        uncertainty_units='ROI128 pixel',uncertainty_is_certified_bound=False,
        provenance=method,review_reason=reason)

def finalize():
    cand={r['id']:r for r in rows(BASE/'registration_candidates.jsonl')}
    disp={r['id']:r for r in rows(BASE/'display_index.jsonl')}
    old={r['id']:r for r in rows(OLD/'annotations_train/print_annotations.jsonl')}
    ledger=visibility_ledger();assert len(ledger)==177
    legacy_differences=[];train=[]
    for id,d in sorted(disp.items()):
        n=int(id.split('_')[1]);req=d['roi_request'];cp=cand[id]['candidate_points'];pp={}
        for j,name in enumerate(NAMES):
            code=ledger[id][j];vis={'v':'visible','p':'partial','o':'occluded','u':'unknown','a':'absent'}[code]
            point=cp.get(name,{}).get('native_xy');u=cp.get(name,{}).get('uncertainty_native_px',6.)
            method='D025_NATIVE_STATIC_SIFT_RANSAC_H_SILVER_PLUS_AI_VISUAL_REVIEW'
            why='Raw ID-only contact visually reviewed; static identity aligns with its image evidence.'
            if vis=='partial':u=max(u,6.);why='Enough visible static contour/pattern supports an uncertain point; partial occlusion/exposure recorded.'
            if vis=='occluded':point=None;u=None;why='Needle/counterweight/tool/OSD covers the identity; no hidden center supervised.'
            if vis=='unknown':point=None;u=None;why='Visual localization unresolved under darkness, glare, blur or clipping; this positive head is ignored, not negative.'
            if vis=='absent':point=None;u=None;method='VISUALLY_CONFIRMED_TRUE_NEGATIVE_FRONT_GAUGE_ABSENT';why='No target front-gauge print in the source image; all six visible-peak targets are zero.'
            if vis in ('visible','partial') and id in MANUAL and j in MANUAL[id]:
                point=native_from_view(MANUAL[id][j],d);u=6./min(d['view_transform']['scale_x'],d['view_transform']['scale_y'])
                method='AI_VISUAL_NATIVE_RAW_POINT_UNREGISTERED_NO_PSI_OR_QUERY_NEEDLE'
                why='Independent raw-image point read for a clear identity after static registration failed; uncertainty retained.'
            if vis in ('visible','partial') and name in (NAMES[1],NAMES[5]) and id in old:
                aa=old[id]['anchors'][name]
                if aa.get('native_xy') is not None and aa.get('visibility') in ('visible','partial','partially_visible'):
                    op=aa['native_xy']
                    if point is not None:
                        distance=float(np.linalg.norm(np.asarray(point)-op));legacy_differences.append(dict(id=id,point=name,distance_native_px=distance))
                        if distance>10:
                            # No silent choice between disagreeing teachers.
                            point=None;u=None;vis='unknown';why='Frozen visual and new silver coordinates disagree by >10native pixels; ignored pending separate review.'
                        else:point=op;u=max(aa.get('uncertainty_native_px',4),6 if vis=='partial' else 4);method='FROZEN_TRAIN_VISUAL_PRINT_SIDECAR_PLUS_NEW_PER_POINT_VISIBILITY_REVIEW'
                    else:point=op;u=max(aa.get('uncertainty_native_px',4),6 if vis=='partial' else 4);method='FROZEN_TRAIN_VISUAL_PRINT_SIDECAR_PLUS_NEW_PER_POINT_VISIBILITY_REVIEW'
            if d['source_group']=='F' and n in (4,7,12,13,16,18,19,22,24,25,28,31,34,37,40,42,43,46,48) and u is not None:u=max(u,8.)
            pp[name]=pack_head(point,vis,u,req,method,why)
        train.append(dict(id=id,split='train',source_sha256=d['sha256'],source_group=d['source_group'],target_present=d['target_present'],
            roi_request=req,point_order=NAMES,points=pp,source_image_path=d['path'],
            input_source='frozen roi_cache_train.npz indexed by id; original128 U8, not annotated views',
            annotation_scope='AI-reviewed silver/visual supervision, not human gold',
            query_pressure_needle_or_NN_used_for_labels=False,canonical_modified=False))
    validation=[]
    valid_records={r['id']:{k:r[k] for k in ('id','sha256','target_present','roi_request','path')} for r in rows(PKG/'prepared_validation.jsonl')}
    for raw in rows(GSOURCE):
        id=raw['id'];r=valid_records[id];assert raw['source_sha256']==r['sha256'];pp={}
        for name in NAMES:
            a=raw['anchors'][name];vis=a['visibility'];p=a['native_xy'];u=a.get('uncertainty_native_px')
            if not r['target_present']:vis='absent';p=None;u=None
            pp[name]=pack_head(p,vis,u,r['roi_request'],'FROZEN_G_SIX_IDENTITY_VISUAL_SIDECAR_VALIDATION_ONLY',a['reason'])
        validation.append(dict(id=id,split='validation',source_sha256=r['sha256'],source_group='G',target_present=r['target_present'],
            roi_request=r['roi_request'],point_order=NAMES,points=pp,source_image_path=r['path'],
            input_source='frozen roi_cache_validation.npz indexed by id; no G updates/templates',
            annotation_scope='Frozen AI visual development labels, not independent gold',
            query_pressure_needle_or_NN_used_for_labels=False,canonical_modified=False))
    assert len(train)==177 and len(validation)==59
    for filename,rr in [('train_landmarks.jsonl',train),('validation_landmarks.jsonl',validation)]:
        (BASE/filename).write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rr),'utf-8')
    save(BASE/'visual_visibility_review_ledger.json',dict(code_order=NAMES,codes=ledger,
         reviewed_contact_pages=[f'{g}_candidates_{n:02d}.png' for g in 'DEF' for n in range(1,8)],
         reviewed_before_any_new_model_training=True,manual_unregistered_view_points=MANUAL,
         pressure_NN_or_known_needle_used=False,AI_nonblind_silver_not_human_gold=True))
    save(BASE/'legacy_point_alignment_check.json',dict(comparisons=legacy_differences,
        max_distance_native_px=max((r['distance_native_px'] for r in legacy_differences),default=None),
        over10=[r for r in legacy_differences if r['distance_native_px']>10],
        points_over10_are_masked_unknown_not_auto_corrected=True))
    # A bounded12-image ROI alignment audit, preserving original input bytes.
    audit_ids=['D_002','D_010','D_025','D_056','E_002','E_015','E_028','E_054','F_002','F_016','F_026','F_057']
    z=np.load(PKG/'roi_cache_train.npz');images={str(i):im for i,im in zip(z['ids'],z['images'])};lookup={r['id']:r for r in train}
    (BASE/'roi_alignment').mkdir(exist_ok=True);tiles=[]
    for id in audit_ids:
        original=images[id];assert original.dtype==np.uint8 and original.shape==(128,128)
        view=cv2.resize(cv2.cvtColor(original,cv2.COLOR_GRAY2BGR),(384,384),interpolation=cv2.INTER_NEAREST)
        for j,name in enumerate(NAMES):
            p=lookup[id]['points'][name]
            if p['coordinate_mask']:
                xy=tuple(round(3*v) for v in p['xy_roi']);color=(40,155,35) if p['visibility']=='visible' else (15,140,225)
                cv2.drawMarker(view,xy,color,cv2.MARKER_CROSS,11,1,cv2.LINE_AA);cv2.putText(view,str(j+1),(xy[0]+4,xy[1]-4),cv2.FONT_HERSHEY_SIMPLEX,.4,color,1,cv2.LINE_AA)
        cv2.imencode('.png',view)[1].tofile(str(BASE/'roi_alignment'/f'{id}_ROI128_overlay.png'))
        # Preview only: this is not the128network input or a second supervision system.
        cv2.imencode('.png',cv2.resize(original,(64,64),interpolation=cv2.INTER_AREA))[1].tofile(str(BASE/'roi_alignment'/f'{id}_ROI64_preview.png'))
        tile=np.full((414,384,3),255,np.uint8);tile[30:]=view
        cv2.putText(tile,id+' original128 labels',(8,22),cv2.FONT_HERSHEY_SIMPLEX,.55,(20,30,40),1,cv2.LINE_AA);tiles.append(tile)
    for start in (0,6):
        page=np.full((828,1152,3),255,np.uint8)
        for j,t in enumerate(tiles[start:start+6]):
            yy,xx=divmod(j,3);page[yy*414:(yy+1)*414,xx*384:(xx+1)*384]=t
        cv2.imencode('.png',page)[1].tofile(str(BASE/f'ROI_alignment_audit_{start//6+1:02d}.png'))
    def stats(rr):return {name:dict(coordinate_heads=sum(r['points'][name]['coordinate_mask'] for r in rr),
        visibility_heads=sum(r['points'][name]['visibility_mask'] for r in rr),
        occluded_or_absent=sum(r['points'][name]['vis_target']==0 for r in rr),
        unknown=sum(r['points'][name]['visibility']=='unknown' for r in rr)) for name in NAMES}
    summary=dict(status='EXPORTED_PENDING_FINAL_ROI_ALIGNMENT_QA',train_images=177,validation_images=59,
        train_supervised_images=sum(any(p['visibility_mask'] for p in r['points'].values()) for r in train),
        train_true_negatives=sum(not r['target_present'] for r in train),train_head_statistics=stats(train),validation_head_statistics=stats(validation),
        label_coordinates='native and originalROI128; heatmap64 target=xy_roi/2',
        coordinate_transform='(native-[x0,y0]-(stride-1)/2)/stride; no clipping or hidden-center reconstruction',
        G_frozen_sidecar_sha256=sha(GSOURCE),G_used_for_training_or_templates=False,H_or_ABC_read=False,
        no_model_or_firmware_or_board_actions=True,old_canonical_images_weights_modified=False,
        outputs_sha256={f:sha(BASE/f) for f in ('train_landmarks.jsonl','validation_landmarks.jsonl','visual_visibility_review_ledger.json','legacy_point_alignment_check.json')},
        sources_sha256={str(p.relative_to(ROOT)):sha(p) for p in (BASE/'registration_candidates.jsonl',OLD/'annotations_train/print_annotations.jsonl',GSOURCE,Path(__file__))})
    save(BASE/'dataset_receipt.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':finalize()
