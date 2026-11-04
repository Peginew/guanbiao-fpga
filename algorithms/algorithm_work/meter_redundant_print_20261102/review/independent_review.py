"""Independent bounded redundant-print review; no training or board access."""
from pathlib import Path
from collections import Counter
import csv,hashlib,importlib.util,json,math,sys
import numpy as np
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;TASK=HERE.parent;ROOT=TASK.parents[1]
DATA=ROOT/'algorithm_work/meter_cnn_training_20261102';OLD=ROOT/'algorithm_work/meter_pointer_readout_20261102';BASE=ROOT/'algorithm_work/meter_robust_readout_20261102/pose'
checks=[]
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def rows(p):return[json.loads(s)for s in Path(p).read_text('utf-8-sig').splitlines()if s.strip()]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def need(ok,name):
    checks.append(name)
    if not ok:raise AssertionError(name)
def near(a,b):return a is None and b is None or a is not None and b is not None and abs(a-b)<1e-8
def wrap(a,c=0.):return(a-c+180)%360-180+c
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
def fit(x,y):
    x=np.asarray(x);y=np.asarray(y);A=np.empty((len(x)*2,4));A[::2]=np.column_stack([x[:,0],-x[:,1],np.ones(len(x)),np.zeros(len(x))]);A[1::2]=np.column_stack([x[:,1],x[:,0],np.zeros(len(x)),np.ones(len(x))])
    a,b,tx,ty=np.linalg.lstsq(A,y.ravel(),rcond=None)[0]
    return np.array([[a,-b,tx],[b,a,ty]])
def metric(rr,truth):
    positive=[r for r in rr if truth[r['id']]['target_present']];acc=[r for r in positive if r['valid']];ee=[abs(r['psi_estimate']-truth[r['id']]['pressure']['value'])for r in acc]
    return dict(outputs=len(acc),denominator=len(positive),MAE_psi=float(np.mean(ee))if ee else None,max_psi=max(ee,default=None),bins={str(t):sum(e<=t for e in ee)for t in[.25,.5,1.]},negative_outputs=sum(r['valid']and not truth[r['id']]['target_present']for r in rr))

def main():
    report=load(TASK/'results/comparison_summary.json');completion=load(TASK/'automatic/completion.json')
    for rel,h in report['source_sha256'].items():need(sha(ROOT/rel)==h,'source_'+rel)
    for key,name in [('code','static_point_locator.py'),('config','config_frozen_before_G.json'),('setup','setup.json'),('predictions','predictions.jsonl'),('templates','train_templates.npz')]:need(sha(TASK/'automatic'/name)==completion['source_sha256'][key],'automatic_bound_'+name)
    need(sha(DATA/'run_002/best_weights.pt')=='c221678efa4762bed298828b2e8e8ba3c2a6b343c2c16efe35aec77a85c896df','old_hub_immutable')
    need(sha(OLD/'polar_angle/run_001/best_weights.pt')=='d139ecdc1059829be18e23eaf5d503d5c9d59a798d2986774441f88cc1804882','old_needle_immutable')
    dev=rows(DATA/'prepared_validation.jsonl');truth={r['id']:r for r in dev};tr={r['id']:r for r in rows(DATA/'prepared_train.jsonl')}
    need(len(dev)==59 and sum(r['target_present']for r in dev)==56 and all(i.startswith('G_')for i in truth),'G59_only_56gauges')
    geometry=module('review_redundant_geometry',TASK/'landmark_geometry.py');names=geometry.NAMES
    nn={r['id']:r for r in rows(OLD/'polar_angle/run_001/validation_predictions.jsonl')};tp={r['id']:r for r in rows(OLD/'polar_angle/run_001/train_predictions.jsonl')}
    annotations=rows(TASK/'annotations/print_annotations.jsonl');need(len(annotations)==59,'59_annotation_rows');visible={};hist={n:Counter()for n in names};nativecount=roicount=0
    for r in annotations:
        ident=r['id'];rec=truth[ident];need(r['source_sha256']==rec['sha256']and r['point_selection_used_pressure_or_predictions']is False,ident+'_sidecar_source')
        need(set(r['anchors'])==set(names),ident+'_six_identity_slots');visible[ident]={};q=rec['roi_request']
        for name,p in r['anchors'].items():
            hist[name][p['visibility']]+=1;xy=p['native_xy'];supported=p['visibility']in['visible','partial','partially_visible']
            need(supported==(xy is not None),ident+'_'+name+'_unknown_not_filled')
            if xy is None:continue
            nativecount+=1;roi=(np.array(xy)-[q['x0'],q['y0']]-(q['stride']-1)/2)/q['stride']
            need(np.max(abs(roi-p['roi_xy']))<1e-9,ident+'_'+name+'_ROI_mapping')
            inside=bool(np.all((roi>=0)&(roi<=127)));roicount+=inside
            need(inside==p['within_roi_pixel_center_bounds'],ident+'_'+name+'_ROI_availability')
            if inside:visible[ident][name]=((roi-nn[ident]['hub_roi'])*48/q['radius']+64).tolist()
    annc=load(TASK/'annotations/completion.json');need(nativecount==299 and roicount==298,'299native298ROI_points')
    need(sum(len(p)>=3 for p in visible.values())==53,'53_information_available_not_pose_success')
    for name,h in hist.items():need(all(h.get(k,0)==v for k,v in annc['per_identity_visibility'][name].items())and not(set(h)-set(annc['per_identity_visibility'][name])),name+'_visibility_histogram')
    setup=load(TASK/'results/canonical_setup.json');reference=setup['reference_points_normalized'];offset=setup['canonical_roll_relative_D002'];common=setup['alignment_identities'];refpoints={}
    for ident in['D_002','D_025']:
        r=load(TASK/'annotations'/f'reference_{ident[0]+ident[2:]}.json');rec=tr[ident];q=rec['roi_request'];pp={}
        need(r['source_sha256']==rec['sha256'],ident+'_train_reference_source')
        for n,p in r['anchors'].items():
            if p['native_xy']is not None:pp[n]=((np.array(p['native_xy'])-[q['x0'],q['y0']]-(q['stride']-1)/2)/q['stride']-tp[ident]['hub_roi'])*48/q['radius']+64
        refpoints[ident]=pp
    M=fit([refpoints['D_002'][n]for n in common],[refpoints['D_025'][n]for n in common]);need(abs(math.degrees(math.atan2(M[1,0],M[0,0]))-offset)<1e-8,'independent_train_only_offset')
    automatic={r['id']:r for r in rows(TASK/'automatic/predictions.jsonl')};need(len(automatic)==223 and sum(i.startswith('G_')for i in automatic)==59,'223_prediction_rows')
    poses={kind:{r['id']:r for r in rows(TASK/'results'/f'{kind}_reference_poses.jsonl')}for kind in['visual','automatic']}
    for kind in poses:
        for ident,p in poses[kind].items():
            query=visible[ident]if kind=='visual'else{n:v['normalized_xy']for n,v in automatic[ident]['points'].items()if v['accepted']}
            replay=geometry.consensus(reference,query,offset)
            need(p['accepted']==replay['accepted']and p['reason']==replay['reason'],ident+'_'+kind+'_consensus_replay')
            if not p['accepted']:continue
            ids=p['inlier_identities'];need(len(ids)>=3 and len(set(ids))==len(ids),ident+'_'+kind+'_independent_identities')
            mat=fit([reference[n]for n in ids],[query[n]for n in ids]);need(np.max(abs(mat-np.asarray(p['matrix'])))<1e-7,ident+'_'+kind+'_independent_LS_matrix')
            predicted=np.asarray([reference[n]for n in ids])@mat[:,:2].T+mat[:,2];res=np.linalg.norm(predicted-np.asarray([query[n]for n in ids]),axis=1)
            need(res.max()<=2.5+1e-8 and np.sqrt(np.mean(res**2))<=2+1e-8,ident+'_'+kind+'_residuals')
            scale=math.hypot(mat[0,0],mat[1,0]);shift=np.linalg.norm(mat[:,:2]@np.array([64.,64.])+mat[:,2]-64)
            roll=wrap(math.degrees(math.atan2(mat[1,0],mat[0,0]))+offset)
            need(.85<=scale<=1.15 and shift<=20 and abs(roll)<24 and near(roll,p['relative_roll_deg']),ident+'_'+kind+'_frozen_geometry_limits')
    oldposes={r['id']:r for r in rows(BASE/'candidate_B_pose.jsonl')};cal=load(BASE/'candidate_B_calibration_psi.json');oldoutputs={r['id']:r for r in load(BASE/'candidate_B_with_old_B_readout_psi.json')['rows']};numbers={}
    for name,kind in[('old_ring',None),('visual_old_first','visual'),('automatic_old_first','automatic')]:
        result=load(TASK/'results'/f'{name}.json');need(len(result['rows'])==59,name+'_all59')
        for out in result['rows']:
            ident=out['id'];old=oldposes[ident];new=poses[kind][ident]if kind else old;po=old if old['accepted']or not new['accepted']else new;pred=nn[ident]
            if not pred['valid']:valid=False;reason='PREDICTION_NOT_PERMITTED';psi=None
            elif not po['accepted']:valid=False;reason=po['reason'];psi=None
            else:
                angle=wrap(pred['angle_deg_image']-po['relative_roll_deg'],cal['branch_center_deg']);psi=cal['slope_psi_per_degree']*angle+cal['intercept_psi'];lo,hi=cal['supported_angle_interval_deg'];pl,ph=cal['supported_pressure_interval_psi'];valid=bool(lo<=angle<=hi and pl<=psi<=ph)
                reason='PC_EMPIRICALLY_CALIBRATED_READING_PSI'if valid else'PREDICTED_DIRECTION_OUTSIDE_TRAIN_CALIBRATION'if not lo<=angle<=hi else'PREDICTED_VALUE_OUTSIDE_TRAIN_PRESSURE_SUPPORT'
            need(out['old_model_permitted']==pred['valid']and out['valid']==valid and out['reason']==reason and(not valid or near(psi,out['psi_estimate'])),ident+'_'+name+'_same_neural_calibration')
            if old['accepted']:need(out['reference_route']=='OLD_REFERENCE_PRESERVED',ident+'_'+name+'_old_route_immutable')
            if oldoutputs[ident]['valid']:need((out['valid'],out['psi_estimate'],out['reason'],out['source_sha256'])==(oldoutputs[ident]['valid'],oldoutputs[ident]['psi_estimate'],oldoutputs[ident]['reason'],oldoutputs[ident]['source_sha256']),ident+'_'+name+'_old21_exact')
        mm=metric(result['rows'],truth);s=result['summary'];need(mm['outputs']==s['valid_readings']and near(mm['MAE_psi'],s['reading_mae_psi'])and mm['denominator']==56,name+'_independent_metrics')
        raw_negative=[]if kind is None else[i for i,p in poses[kind].items()if p['accepted']and not truth[i]['target_present']]
        need(set(result['new_reference_supported_negative_ids'])==set(raw_negative),name+'_raw_reference_negative_scope')
        need(all(mm['bins'][str(t)]==s['descriptive_correct_output_coverage'][str(t)]['correct_outputs']for t in[.25,.5,1.]),name+'_all_error_bands')
        newids={r['id']for r in result['rows']if r['valid']and not oldoutputs[r['id']]['valid']};need(newids==set(result['changes']['new_output_ids'])and not result['changes']['withdrawn_output_ids'],name+'_incremental_no_withdrawal')
        for t in[.25,.5,1.]:
            wrong={r['id']for r in result['rows']if r['valid']and(r['absolute_error_psi']is None or r['absolute_error_psi']>t)and not(oldoutputs[r['id']]['valid']and(oldoutputs[r['id']]['absolute_error_psi']is None or oldoutputs[r['id']]['absolute_error_psi']>t))}
            need(wrong==set(result['changes']['bands'][str(t)]['new_wrong_ids']),name+'_new_over_band_'+str(t))
        mm['new_output_IDs']=sorted(newids);mm['frontal16']=metric([r for r in result['rows']if truth[r['id']]['scene']['primary']in['front_medium_soft_light','front_large_soft_light']],truth);numbers[name]=mm
    locator_module=module('review_static_locator',TASK/'automatic/static_point_locator.py');loc=locator_module.Locator();items={r['id']:r for r in locator_module.material('validation')}
    rng=np.random.default_rng(1110)
    for width,logo in[(17,False),(13,True)]:
        template=rng.integers(0,256,(width,width)).astype(np.float32);mask=locator_module.body_mask(width,logo);tv=template[mask>0].astype(float);tv-=tv.mean()
        for tag,query in[('same',template.copy()),('opposite',255-template),('random',rng.integers(0,256,(width,width)).astype(np.float32))]:
            qv=query[mask>0].astype(float);qv-=qv.mean();oracle=float(qv@tv/np.sqrt((qv@qv)*(tv@tv)))
            need(abs(float(locator_module.masked_ncc(query,template,mask)[0,0])-oracle)<2e-5,f'masked_NCC_{width}_{tag}')
        for value in[0,128,255]:need(not np.any(locator_module.masked_ncc(np.full((width,width),value,np.float32),template,mask)>=.68),f'masked_NCC_{width}_constant{value}')
        if logo:
            query=rng.integers(0,256,(width,width)).astype(np.float32);before=locator_module.masked_ncc(query,template,mask).copy();query[mask==0]=255-query[mask==0];template[mask==0]=255-template[mask==0]
            need(np.array_equal(before,locator_module.masked_ncc(query,template,mask)),'masked_corner_context_invariance')
            template[mask>0]=128;need(not np.any(locator_module.masked_ncc(query,template,mask)>=.68),'constant_body_template_is_unknown')
    for ident in['G_014','G_041','G_053']:
        it=items[ident];actual=loc.infer(it['image'],it['hub'],it['radius']);saved=automatic[ident]
        for n,p in actual['points'].items():
            q=saved['points'][n];need(p['accepted']==q['accepted']and near(p['score'],q['score'])and near(p['margin'],q['margin']),ident+'_'+n+'_actual_locator_replay')
            if p['accepted']:need(np.max(abs(np.array(p['normalized_xy'])-q['normalized_xy']))<1e-8,ident+'_'+n+'_coordinate_replay')
    z=np.load(TASK/'automatic/train_templates.npz');bankbytes=sum(z[f'bank_{i}'].nbytes for i in range(6));maskbytes=sum(z[f'mask_{i}'].nbytes for i in range(6))
    c=completion['cost'];need(bankbytes==76944==c['FP32template_bytes']and maskbytes==5496==c['FP32mask_bytes'],'actual_template_mask_bytes')
    need(c['nominal_three_correlation_direct_products']==3*c['maximum_nominal_patch_pixel_products']==97007148,'3_correlations_count_not_hidden')
    need(c['minimum_explicit_PC_image_score_winner_far_mgrid_bytes']==491520 and c['actual_PC_peak_RAM_unmeasured'],'explicit_scratch_lower_bound_not_MCU_fit')
    pointreport=load(TASK/'results/point_evaluation.json')
    for n in names:
        errs=[];vis=0;acc=0;unknown=[];neg=[]
        for ident in truth:
            p=automatic[ident]['points'][n];present=p['accepted'];acc+=present
            if n in visible[ident]:
                vis+=1
                if present:errs.append(float(np.linalg.norm(np.array(p['normalized_xy'])-visible[ident][n])))
            elif present:unknown.append(ident)
            if present and not truth[ident]['target_present']:neg.append(ident)
        s=pointreport[n];need(s['automatic_accepted']==acc and s['visually_localizable_labels']==vis and s['automatic_accepted_on_visible']==len(errs)and s['localization_error_normalized']['within3px']==sum(e<=3 for e in errs)and set(s['accepted_on_visual_unknown_ids'])==set(unknown)and set(s['accepted_on_negative_ids'])==set(neg),n+'_independent_point_metrics')
        need(near(float(np.mean(errs))if errs else None,s['localization_error_normalized']['mean'])and near(max(errs,default=None),s['localization_error_normalized']['max']),n+'_point_mean_max')
    csvrows=list(csv.DictReader((TASK/'results/逐图参考保留与补充.csv').open(encoding='utf-8-sig',newline='')));need(len(csvrows)==4*59,'all236_CSV_rows')
    result=dict(status='PASS_RESEARCH_REPLAY_KEEP_OLD_READER_AUTOMATIC_PATCH_NOT_FINAL_SOLUTION',checks=len(checks),unit='psi',source_sha256={str(p.relative_to(TASK)):sha(p)for p in[TASK/'task_contract.json',TASK/'landmark_geometry.py',TASK/'fusion.py',TASK/'evaluate_redundant.py',TASK/'annotations/print_annotations.jsonl',TASK/'automatic/static_point_locator.py',TASK/'automatic/config_frozen_before_G.json',TASK/'automatic/predictions.jsonl',TASK/'results/comparison_summary.json']},numbers=numbers,
        old21_unchanged=True,query_G_visibility_not_used_in_automatic=True,query_psi_or_true_needle_not_used=True,
        judgement=['Old-first routing preserves all21 original outputs exactly. This does not guarantee new accepted readings are correct.',
            'AI visual redundant points recover10 outputs but2 exceed0.5psi; native diagnostic labels are not automatic ROI128 extraction or pose gold.',
            'Automatic patch candidate adds onlyG041, error0.0304369psi; frontal16 remains9 outputs. No broad robustness/reading completion claim.',
            'Outer5/10 andsoccer point localisation is weak. Keep the identified-reference/routing design, not this expensive weak locator as final implementation.',
            '76944B FP32bank and491520B named PC scratch alone do not fit48KiB TCM. Quantization/streaming/link/cycles are not implemented or proven.'],
        cost=c,manual_visual_scope='Independent G010..018 andG055..059 overlay pages plus clean D025 patch contact checked; not full354point human-gold recertification',
        labels_are_diagnostic_not_blind_gold=True,similarity_not_full_perspective_or_frontal_quality=True,
        error_bands_are_descriptive_not_user_final_tolerance=True,H_or_ABC_opened=False,training=False,hardware_actions=False)
    (HERE/'supervision_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({k:v for k,v in result.items()if k not in['source_sha256','cost']},ensure_ascii=False))
if __name__=='__main__':main()
