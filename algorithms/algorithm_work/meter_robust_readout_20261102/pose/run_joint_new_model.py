"""Frozen two pose methods/templates with NEW predicted query hubs, train/G.

Old model predictions used solely toinitialize immutable train templates;
there is no oldhub inference/cached query pose in the combined path.
"""
from pathlib import Path
import json,sys,numpy as np
HERE=Path(__file__).resolve().parent;OUT=HERE/'joint_new_model';OUT.mkdir(exist_ok=True)
sys.path.insert(0,str(HERE));import roi_pose_candidates as pose;import calibrate_and_score as calmod
NEW=HERE.parent/'training/run_001/polar'

def main():
    rr,gray,oldsetup=pose.assets();c=pose.Candidates(rr,gray,oldsetup)
    pred={r['id']:r for r in pose.rows(NEW/'train_predictions.jsonl')+pose.rows(NEW/'validation_predictions.jsonl')}
    metadata=dict(frozen_pose_config=pose.CONFIG,frozen_template_offsets=c.offsets,
        oldmodel_role='Fixed train template setup only; no oldhub runtime execution',
        newquery_role='Every query uses actual same-new-model hub_roi and same-source ROI',
        source_sha256={str(p):pose.sha(p)for p in[NEW/'train_predictions.jsonl',NEW/'validation_predictions.jsonl',HERE/'candidate_config.json',HERE/'template_setup.json',HERE/'roi_pose_candidates.py',Path(__file__)]},
        thresholds_tuned_on_G=False,template_reselected_using_G=False)
    pose.write(OUT/'input_contract.json',metadata)
    results={k:[]for k in['A','B']}
    for r in rr:
        if r['id']not in pred:continue
        p=pred[r['id']]
        for name in['A','B']:
            out=getattr(c,name)(gray[r['id']],p['hub_roi'],r['roi_request']['radius'])
            out.update(id=r['id'],split=r['split'],source_sha256=r['sha256'],query_predicted_hub_roi=p['hub_roi'],
                query_model='NEW_ROBUST_HUB_POLAR_CHAIN',query_uses_GT_points=False,query_uses_pressure=False,native_frame_used=False,method=name)
            results[name].append(out)
    train=[r for r in rr if r['split']=='train'];val=[r for r in rr if r['split']=='validation'];lookup={r['id']:r for r in val}
    predictions=pose.rows(NEW/'validation_predictions.jsonl');summary={}
    for name,r in results.items():
        posefile=OUT/f'candidate_{name}_pose.jsonl';posefile.write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n'for x in r),'utf-8')
        poses={x['id']:x for x in r};cal=calmod.calibrate(train,poses,name)
        cal['source_sha256'].update(pose=pose.sha(posefile),query_model_predictions_train=pose.sha(NEW/'train_predictions.jsonl'),joint_driver=pose.sha(__file__))
        cal['query_inputs']=['U8ROI128','NEWrobustmodel predictedhub','locatorradius']
        pose.write(OUT/f'candidate_{name}_calibration_psi.json',cal)
        outputs=[]
        for p in predictions:
            row=calmod.numeric.apply_prediction(p,poses[p['id']],cal);row['pose_source']=f'ROI128_CANDIDATE_{name}_SAME_NEW_QUERY_HUB_MODEL_NO_NATIVE_FRAME';outputs.append(row)
        metrics=calmod.numeric.score_outputs(outputs,lookup);metrics['static_pose_supported']=sum(x['accepted']for x in r if x['split']=='validation')
        result=dict(status='NEW_MODEL_PLUS_SAME_NEW_HUB_ROI128_POSE_PC_ONLY',unit='psi',summary=metrics,rows=outputs,
            model='NEWrobusthub+polar, same-source queryhub used bypose',pose_candidate=name,
            source_sha256=dict(query_model_val=pose.sha(NEW/'validation_predictions.jsonl'),query_model_train=pose.sha(NEW/'train_predictions.jsonl'),
                pose=pose.sha(posefile),calibration=pose.sha(OUT/f'candidate_{name}_calibration_psi.json'),input_contract=pose.sha(OUT/'input_contract.json')),
            query_native_frame_or_GT_or_pressure_used=False,G_fitted=False,H_opened=False,hardware_actions=False)
        pose.write(OUT/f'candidate_{name}_readout_psi.json',result)
        summary[name]=dict(metrics,train_fit_images=len(cal['fit_measurements']),train_fit_MAE_psi=cal['train_fit_MAE_psi'])
    pose.write(OUT/'summary.json',dict(status='JOINT_SAME_NEW_HUB_MODEL_TWO_FROZEN_POSE_METHODS_COMPLETE',summary=summary,
        old_query_hub_cache_reused=False,H_opened=False,hardware_actions=False))
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
