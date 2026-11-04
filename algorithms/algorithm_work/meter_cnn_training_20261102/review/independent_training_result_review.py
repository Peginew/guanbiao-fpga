"""Verify completed float training; no optimizer or H inputs."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import math
import numpy as np
import torch

HERE = Path(__file__).resolve().parent
TASK = HERE.parent
RUN = TASK / 'run_001'


def read(path):
    return json.loads(Path(path).read_text('utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    global RUN
    parser=argparse.ArgumentParser()
    parser.add_argument('--run', default='run_001')
    parser.add_argument('--trainer', default='train_grouped.py')
    args=parser.parse_args()
    RUN=TASK/args.run
    trainer = module('independent_trainer', TASK/args.trainer)
    adapter = module('independent_roi', TASK/'roi_adapter.py')
    receipt = read(RUN/'training_receipt.json')
    config = read(RUN/'training_config.json')
    history = read(RUN/'history.json')
    result = read(RUN/'validation_evaluation.json')
    checks = []
    def check(ok, name):
        checks.append(dict(name=name, passed=bool(ok)))
        if not ok:
            raise AssertionError(name)
    check(sha(RUN/'training_config.json') == receipt['config_sha256'], 'config_receipt_sha')
    check(sha(RUN/'best_weights.pt') == receipt['best_checkpoint_sha256'], 'best_checkpoint_sha')
    check(sha(RUN/'last_weights.pt') == receipt['last_checkpoint_sha256'], 'last_checkpoint_sha')
    check(config['train_groups'] == ['D','E','F'] and config['validation_groups'] == ['G'], 'actual_groups')
    check(len(config['train_ids']) == 164 and len(config['validation_ids']) == 59, 'actual_sample_counts')
    check(all(x[0] in 'DEF' for x in config['train_ids']) and all(x[0] == 'G' for x in config['validation_ids']), 'identity_groups')
    check(config['initialization'].startswith('scratch') and config['test_H_pixels_or_labels_opened'] is False, 'scratch_and_test_exclusion')
    for name, key in [(args.trainer,'trainer_sha256'), ('roi_adapter.py','roi_adapter_sha256'), ('prepared_train.jsonl','prepared_train_sha256'), ('prepared_validation.jsonl','prepared_validation_sha256')]:
        check(sha(TASK/name) == config[key], 'frozen_input_'+name)
    expected_step = min(history, key=lambda r:r['validation']['validation_or_training_loss'])['step']
    check(expected_step == receipt['best_step'], 'best_step_is_minimum_G_validation_loss')
    check(history[-1]['step'] == receipt['completed_steps'] == 2400, 'actual_2400_steps')
    selected = torch.load(RUN/'best_weights.pt', weights_only=True, map_location='cpu')
    last = torch.load(RUN/'last_weights.pt', weights_only=True, map_location='cpu')
    check(selected['training_steps'] == expected_step and last['training_steps'] == 2400, 'checkpoint_step_identity')
    check(selected['prepared_train_sha256'] == config['prepared_train_sha256'], 'checkpoint_data_identity')
    torch.set_num_threads(2)
    model = trainer.Direct(4)
    model.load_state_dict(selected['state_dict'])
    model.eval()
    records = adapter.load_prepared(TASK/'prepared_validation.jsonl')
    byid = {r['id']: r for r in result['rows']}
    predicted_maxdiff = 0.
    errors = [[], []]
    angles = []
    accepted_angles = []
    false_accepts = 0
    first_trace = {}
    trace_handles = []
    for name, layer in model.named_modules():
        if isinstance(layer, torch.nn.Conv2d):
            def capture(layer, args, out, name=name):
                a = out.detach().numpy()
                first_trace[name] = dict(min=float(a.min()), max=float(a.max()), fraction_nonzero=float(np.mean(a != 0)), spatial_std=float(np.std(a, axis=(-1,-2)).max()))
            trace_handles.append(layer.register_forward_hook(capture))
    with torch.inference_mode():
        for i, r in enumerate(records):
            g = adapter.read_roi(r)
            q = model(torch.from_numpy((g.astype(np.float32)-128)[None,None]/128))[0].numpy()
            if i == 0:
                for handle in trace_handles:
                    handle.remove()
            # Independent unquantized sigmoid/3x3 centroid arithmetic.
            points, peaks, margins = [], [], []
            for head in q:
                prob = 1/(1+np.exp(-np.clip(head,-40,40)))
                iy, ix = np.unravel_index(prob.argmax(), prob.shape)
                wx = wy = total = 0.
                for yy in range(max(0,iy-1), min(64,iy+2)):
                    for xx in range(max(0,ix-1), min(64,ix+2)):
                        weight = float(prob[yy,xx]); total += weight
                        wx += xx*weight; wy += yy*weight
                points.append([2*wx/total,2*wy/total])
                peaks.append(float(prob[iy,ix]))
                ys,xs=np.mgrid[:64,:64]
                far=prob.copy();far[(xs-ix)**2+(ys-iy)**2<=25]=0
                margins.append(float(prob[iy,ix]-far.max()))
            p=np.asarray(points)
            stored=byid[r['id']]
            diff=float(np.abs(p-stored['predicted_points_roi']).max())
            predicted_maxdiff=max(predicted_maxdiff,diff)
            check(diff<2e-4,r['id']+'_checkpoint_prediction_reproduced')
            length=float(np.linalg.norm(p[1]-p[0]));center=float(np.linalg.norm(p[0]-63.5))
            accept=min(peaks)>=.3 and min(margins)>=.02 and 18<=length<=65 and center<=20
            check(accept==stored['evidence_accepted'],r['id']+'_acceptance_reproduced')
            target=[]
            for h,key in enumerate(('hub','thin_terminal')):
                xy=r['roi_keypoints'][key]['xy'] if r['loss_mask'][h] and r['target_present'] else None
                target.append(xy)
                if xy is not None:
                    error=float(np.linalg.norm(p[h]-xy));errors[h].append(error)
                    check(abs(error-stored[key+'_error_roi'])<2e-4,r['id']+'_'+key+'_error_recomputed')
            if all(x is not None for x in target):
                predangle=math.degrees(math.atan2(*(p[1]-p[0])[::-1]))%360
                a=np.asarray(target);gt=math.degrees(math.atan2(*(a[1]-a[0])[::-1]))%360
                err=abs((predangle-gt+180)%360-180);angles.append(err)
                check(abs(err-stored['angle_error_deg'])<2e-3,r['id']+'_angle_error_recomputed')
                if accept:accepted_angles.append(err)
            if not r['target_present'] and accept:false_accepts+=1
    summary=result['summary']
    check(len(errors[0])==len(errors[1])==52 and len(angles)==50,'correct_visible_keypoint_denominators')
    check(summary['negative_count']==3 and sum(not r['target_present'] for r in records)==3,'three_negative_crops_only')
    check(summary['negative_evidence_false_accepts']==false_accepts,'negative_false_accept_count')
    check(abs(np.mean(angles)-summary['angle_error_deg']['mean'])<2e-3,'mean_angle_error_recomputed')
    check(summary['within_5deg']==sum(e<=5 for e in angles),'within5_count_recomputed')
    check(summary['evidence_accepted_full_points']==len(accepted_angles),'coverage_denominator_recomputed')
    report=dict(status='PASS_EXECUTION_AND_REPORTING_EFFECTS_REPORTED_NO_DEPLOYMENT_ACCEPTANCE',checks=len(checks),failures=[],
        run=str(RUN), best_step=expected_step, completed_steps=2400, checkpoint_G_prediction_max_difference_roi=predicted_maxdiff,
        best_checkpoint_sha256=sha(RUN/'best_weights.pt'),last_checkpoint_sha256=sha(RUN/'last_weights.pt'),
        config_sha256=sha(RUN/'training_config.json'),validation_report_sha256=sha(RUN/'validation_evaluation.json'),
        history_sha256=sha(RUN/'history.json'),training_receipt_sha256=sha(RUN/'training_receipt.json'),
        validation_metrics_recomputed=dict(hub_n=len(errors[0]),hub_mean_roi=float(np.mean(errors[0])),thin_n=len(errors[1]),thin_mean_roi=float(np.mean(errors[1])),
          full_n=len(angles),angle_mean_deg=float(np.mean(angles)),within5=sum(e<=5 for e in angles),evidence_accepted_full=len(accepted_angles),negatives=3,negative_false_accepts=false_accepts),
        G001_convolution_activation_trace=first_trace,
        deployment_decision='No integer or board deployment acceptance; assess actual float metrics separately. Training completion is not deployment success.',
        diagnosis_scope='Activation trace is from G001 only; it is not an exhaustive per-frame activation audit.',
        test_H_pixels_or_labels_opened=False,optimizer_executed_by_reviewer=False,integer_or_board_READ_accepted=False)
    report_name='training_result_review.json' if args.run=='run_001' else 'training_result_review_'+args.run+'.json'
    (HERE/report_name).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(report,ensure_ascii=False))


if __name__=='__main__':main()
