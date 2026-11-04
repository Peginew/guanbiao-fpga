"""Reviewed AB silver supervision plus byte-preserved DEF training labels.

No C/H inputs. G labels are byte-copied frozen validation only. This preparation
does not claim blind human gold and never reconstructs an obscured center.
"""
from pathlib import Path
import json,hashlib,sys,shutil
import numpy as np
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[2]
PREV=ROOT/'algorithm_work/meter_landmark_mcu_training_20261103/data'
sys.path.insert(0,str(PREV))
from finalize_dataset import pack_head
from prepare_silver_candidates import NAMES
def rows(p):return [json.loads(s) for s in Path(p).read_text('utf-8-sig').splitlines() if s.strip()]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf-8')
def main():
    ledger={f'{g}_{n:03d}':'vvvvvv' for g in 'AB' for n in range(1,60)}
    for n in range(1,6):ledger[f'A_{n:03d}']='vvvppv'
    for n in range(6,18):ledger[f'A_{n:03d}']='vvvpop'
    for n in range(18,24):ledger[f'A_{n:03d}']='vvvppv'
    for n in range(24,30):ledger[f'A_{n:03d}']='vvvvpv'
    for n in range(1,13):ledger[f'B_{n:03d}']='vvvpop'
    for n in range(13,19):ledger[f'B_{n:03d}']='vvvppv'
    for n in range(19,31):ledger[f'B_{n:03d}']='vvvvpv'
    for n in (48,49,50):ledger[f'A_{n:03d}']='aaaaaa'
    for n in (49,50,51):ledger[f'B_{n:03d}']='aaaaaa'
    for id in ('A_052','A_053','A_054','B_043','B_052','B_053','B_054','B_055'):ledger[id]='uuuuuu'
    ledger.update(A_008='ppppop',A_014='ppppop',A_020='pppppv',A_026='vuvvpv',A_027='vovvpv',
        A_028='vovvpv',A_029='vovvpv',A_031='vpvvvv',A_037='vovvvv',A_038='vpvvvv',A_039='pppppp',
        A_040='vovvvv',A_041='vovvvv',A_045='vovvvv',A_051='uooppp',
        A_055='vvvooo',A_056='uuuooo',A_057='ovvvvv',A_058='uvvvvv',A_059='pppppp',
        B_004='ppppop',B_010='ppppop',B_016='pppppv',B_022='pppvpv',B_028='vvvvuu',
        B_031='vovvvv',B_056='vvvpoo',B_057='vovooo',B_058='oovvvv',B_059='uovvvv')
    prepared=rows(BASE/'prepared_ab.jsonl');candidates={r['id']:r for r in rows(BASE/'registration_candidates.jsonl')}
    ab=[];checks=0;roundtrip=0
    for r in prepared:
        id=r['id'];c=candidates[id];q=r['roi_request'];points={}
        assert c['source_sha256']==r['sha256'] and r['source_group'] in ('A','B');assert sha(r['path'])==r['sha256'];checks+=2
        for j,name in enumerate(NAMES):
            vis={'v':'visible','p':'partial','o':'occluded','u':'unknown','a':'absent'}[ledger[id][j]]
            cp=c['candidate_points'].get(name,{});p=cp.get('native_xy');u=cp.get('uncertainty_native_px',6)
            why='Raw native ID-only view reviewed; static identity has supporting image evidence.'
            method='D025_NATIVE_STATIC_SIFT_RANSAC_H_SILVER_PLUS_AI_VISUAL_REVIEW'
            if vis=='partial':u=max(u,8);why='Partial print/lighting evidence reviewed, with increased uncertainty; no wholly hidden center.'
            if vis=='unknown':p=None;u=None;why='Unresolved print, glare/blur or unavailable static registration: ignore this positive head, not a negative.'
            elif vis=='occluded':p=None;u=None;why='Needle/counterweight/finger/tool or burned-in OSD explicitly covers identity; no center reconstructed.'
            elif vis=='absent':p=None;u=None;why='Source visually confirms no specified front gauge; all six print heads have absent targets.';method='VISUALLY_CONFIRMED_TRUE_NEGATIVE_FRONT_GAUGE_ABSENT'
            points[name]=pack_head(p,vis,u,q,method,why)
            head=points[name]
            if head['coordinate_mask']:
                pred=[(head['xy_native'][a]-q['x0' if a==0 else 'y0']-(q['stride']-1)/2)/q['stride'] for a in (0,1)]
                roundtrip=max(roundtrip,max(abs(a-b) for a,b in zip(pred,head['xy_roi'])))
            assert (head['visibility']=='unknown')==(head['visibility_mask']==0)
            assert head['vis_target'] in (0,1,None);checks+=2
        ab.append(dict(id=id,split='train',source_sha256=r['sha256'],source_group=r['source_group'],target_present=r['target_present'],roi_request=q,
            point_order=NAMES,points=points,source_image_path=r['path'],input_source='new roi_cache_train.npz; same frozen hardware-shaped128 U8 arithmetic',
            annotation_scope='AI-reviewed silver, not blind human gold',reserve_promoted_by_expanded_task=True,
            query_pressure_needle_or_NN_used_for_labels=False,canonical_modified=False))
    assert len(ab)==118
    abtext=''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in ab)
    (BASE/'ab_landmarks.jsonl').write_text(abtext,'utf-8')
    defbytes=(PREV/'train_landmarks.jsonl').read_bytes()
    combined=abtext.encode('utf-8')+defbytes
    (BASE/'train_landmarks.jsonl').write_bytes(combined)
    assert (BASE/'train_landmarks.jsonl').read_bytes()[len(abtext.encode('utf-8')):]==defbytes
    train=rows(BASE/'train_landmarks.jsonl');assert len(train)==295 and {r['source_group'] for r in train}==set('ABDEF')
    shutil.copyfile(PREV/'validation_landmarks.jsonl',BASE/'validation_landmarks.jsonl')
    assert sha(BASE/'validation_landmarks.jsonl')==sha(PREV/'validation_landmarks.jsonl')
    oldcache=np.load(ROOT/'algorithm_work/meter_cnn_training_20261102/roi_cache_train.npz');cache=np.load(BASE/'roi_cache_train.npz')
    assert np.array_equal(cache['ids'][118:],oldcache['ids']) and np.array_equal(cache['images'][118:],oldcache['images'])
    save(BASE/'visual_visibility_review_ledger.json',dict(point_order=NAMES,codes=ledger,
        A_pages_01_to_07_reviewed_by='roi_adapter; root independently reviewedA03',
        B_pages_01_to_07_reviewed_by='training_adapter independent raw-image visual review, consolidated byroi_adapter',
        B_pages_01_to_03_also_seen_by='training_review; duplicateQA stopped before remainingpages',
        no_C_H_images_or_points=True,no_G_training_or_templates=True,no_pressure_or_query_needle_or_NN_result_for_labels=True,
        ambiguous_and_unregistered_points_masked_unknown_instead_of_forced_coordinates=True))
    def stat(rr):return {n:dict(coordinates=sum(r['points'][n]['coordinate_mask'] for r in rr),visibility_heads=sum(r['points'][n]['visibility_mask'] for r in rr),unknown=sum(r['points'][n]['visibility']=='unknown' for r in rr)) for n in NAMES}
    receipt=dict(status='READY_AB_EXPANDED295_FROZEN_DEF_AND_G_PRESERVED',AB_images=118,train_images=295,validation_images=59,
        train_active_images=sum(any(p['visibility_mask'] for p in r['points'].values()) for r in train),train_true_negatives=sum(not r['target_present'] for r in train),
        AB_head_statistics=stat(ab),combined_head_statistics=stat(train),AB_original_PNG_SHA_checked=118,
        mask_coordinate_checks=checks,roundtrip_max_error_ROI_px=roundtrip,old_DEF_label_lines_byte_identical=True,old_DEF_pixels_byte_identical=True,
        G_validation_file_byte_identical=True,C_H_images_or_points_read=False,G_used_as_training_or_templates=False,
        no_training_or_firmware_or_device_operations=True,labels_are_human_gold=False,
        labels_frozen_no_further_changes=True,
        outputs_sha256={f:sha(BASE/f) for f in ('train_landmarks.jsonl','validation_landmarks.jsonl','ab_landmarks.jsonl','roi_cache_train.npz','visual_visibility_review_ledger.json')},
        preserved_DEF_labels_sha256=sha(PREV/'train_landmarks.jsonl'),preserved_DEF_cache_sha256=sha(ROOT/'algorithm_work/meter_cnn_training_20261102/roi_cache_train.npz'),
        same_ROI_adapter_sha256=sha(ROOT/'algorithm_work/meter_cnn_training_20261102/roi_adapter.py'))
    save(BASE/'dataset_receipt.json',receipt);print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
