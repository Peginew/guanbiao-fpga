"""Frozen prediction/calibration decomposition and all-image PSI comparison."""
from pathlib import Path
import base64,csv,html,json,math,sys
import cv2
import numpy as np
import reference_candidate as c
sys.path.insert(0,str(c.OLD/'readout_psi'))
import readout_adapter as numeric


def load(path):return json.loads(Path(path).read_text('utf-8-sig'))


def main():
    run=c.HERE/'reference_cnn/run_001'
    baseline=load(c.PREVIOUS/'candidate_B_with_old_B_readout_psi.json')
    candidate=load(run/'readout_psi.json')
    pp=c.rows(c.OLD/'polar_angle/run_001/validation_predictions.jsonl')
    oldpose={r['id']:r for r in c.rows(c.PREVIOUS/'candidate_B_pose.jsonl')}
    newpose={r['id']:r for r in c.rows(run/'candidate_pose.jsonl')}
    oldcal=load(c.PREVIOUS/'candidate_B_calibration_psi.json');newcal=load(run/'calibration_psi.json')
    rr=c.rows(c.DATA/'prepared_validation.jsonl');lookup={r['id']:r for r in rr}
    ablations={}
    for name,poses,cal in [('new_reference_old_calibration',newpose,oldcal),('old_reference_new_calibration',oldpose,newcal)]:
        outputs=[numeric.apply_prediction(p,poses[p['id']],cal) for p in pp]
        report=dict(status='FROZEN_OUTPUT_DECOMPOSITION_NO_TRAINING_OR_G_FIT',summary=numeric.score_outputs(outputs,lookup),rows=outputs)
        c.write(run/(name+'.json'),report);ablations[name]=report['summary']
    b={r['id']:r for r in baseline['rows']};n={r['id']:r for r in candidate['rows']}
    gains=[i for i in n if n[i]['valid'] and not b[i]['valid']]
    losses=[i for i in b if b[i]['valid'] and not n[i]['valid']]
    errors=[dict(id=i,prediction_psi=n[i]['psi_estimate'],reference_psi=n[i]['psi_reference_for_scoring'],absolute_error_psi=n[i]['absolute_error_psi'])
            for i in n if n[i]['valid'] and n[i]['absolute_error_psi'] is not None and n[i]['absolute_error_psi']>.5]
    decision=dict(status='REJECT_NEW_REFERENCE_CNN_KEEP_ORIGINAL_2211_PLUS_MULTI_RING',
        primary_unit='psi',baseline=baseline['summary'],candidate=candidate['summary'],ablations=ablations,
        gained_ids=gains,lost_ids=losses,outputs_over_descriptive_half_psi=errors,
        half_psi_is_user_final_tolerance=False,new_model_deployed=False,no_second_training_run=True,
        next_action='Quantize and verify the existing multi-ring pose core; not another G-tuned learning experiment',
        source=dict(checkpoint_sha256=c.sha(run/'best_weights.pt'),candidate_pose_sha256=c.sha(run/'candidate_pose.jsonl'),
                    candidate_readout_sha256=c.sha(run/'readout_psi.json'),baseline_readout_sha256=c.sha(c.PREVIOUS/'candidate_B_with_old_B_readout_psi.json')))
    c.write(c.HERE/'selection_decision.json',decision)
    out=c.HERE/'comparison';out.mkdir(exist_ok=True)
    fields=['id','scene','psi_reference','baseline_valid','baseline_psi','baseline_error_psi','baseline_reason',
            'candidate_valid','candidate_psi','candidate_error_psi','candidate_reason','candidate_roll_deg','candidate_roll_stddev_deg']
    table=[];panels=[]
    for it in c.material('validation'):
        i=it['id'];row=dict(id=i,scene=it['record']['scene']['primary'],psi_reference=n[i]['psi_reference_for_scoring'],
            baseline_valid=b[i]['valid'],baseline_psi=b[i]['psi_estimate'],baseline_error_psi=b[i]['absolute_error_psi'],baseline_reason=b[i]['reason'],
            candidate_valid=n[i]['valid'],candidate_psi=n[i]['psi_estimate'],candidate_error_psi=n[i]['absolute_error_psi'],candidate_reason=n[i]['reason'],
            candidate_roll_deg=newpose[i]['relative_roll_deg'],candidate_roll_stddev_deg=newpose[i]['conditional_stddev_deg'])
        table.append(row)
        canvas=cv2.cvtColor(it['image'],cv2.COLOR_GRAY2BGR)
        h=it['hub'];angle=it['pred']['angle_deg_image'];end=h+.7*it['radius']*np.array([math.cos(math.radians(angle)),math.sin(math.radians(angle))])
        cv2.drawMarker(canvas,tuple(np.rint(h).astype(int)),(0,220,255),cv2.MARKER_CROSS,7,1)
        cv2.line(canvas,tuple(np.rint(h).astype(int)),tuple(np.rint(end).astype(int)),(255,200,0),1)
        # Direction length is only a display reference, never a detected tip.
        canvas=cv2.resize(canvas,(256,256),interpolation=cv2.INTER_NEAREST)
        data=base64.b64encode(cv2.imencode('.png',canvas)[1]).decode()
        def val(p):return f"{p['psi_estimate']:.3f} psi; |e|={p['absolute_error_psi']:.3f}" if p['valid'] else p['reason']
        panels.append(f'<article><img src="data:image/png;base64,{data}"><div><b>{i}</b> · {html.escape(row["scene"])}<p>目视参考：{row["psi_reference"]} psi</p><p>保留基线：{html.escape(val(b[i]))}</p><p>淘汰候选：{html.escape(val(n[i]))}</p><p>候选参考角 {row["candidate_roll_deg"]:.2f}°；分布标准差 {row["candidate_roll_stddev_deg"]:.2f}°</p></div></article>')
    with (out/'逐图对照.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(table)
    body='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>观表 · 静态参考支路取舍</title><style>body{max-width:1100px;margin:30px auto;padding:0 20px;background:#101619;color:#dce6e7;font:16px/1.6 system-ui}h1{font-size:27px}p{margin:8px 0}.note{padding:16px;border-left:4px solid #e4ad67;background:#20292c}article{display:flex;gap:20px;padding:22px 0;border-bottom:1px solid #354044}img{width:256px;height:256px;object-fit:contain}article div{overflow-wrap:anywhere}b{color:#8ed4c2}</style><h1>静态参考CNN未通过，保留原读数链</h1><div class="note">同一G开发集59张：基线21/56有表出数，MAE0.157psi；新参考CNN6/56出数，MAE0.575psi。本次不部署新权重。H未打开。0.5psi仅为描述分档，尚非用户验收容差。</div><p>下方保留全部59张，包括拒读和3张无表。轴心与针向仍来自相同的原网络；线长为显示参考，不是检测到的针尖。本页只比较参考方向与标定支路，不代表MCU或板测。</p>'''
    (out/'index.html').write_text(body+''.join(panels)+'</html>','utf-8')
    print(json.dumps(dict(decision=decision['status'],gained=gains,lost=losses,ablations={k:(v['valid_readings'],v['reading_mae_psi']) for k,v in ablations.items()},errors=errors),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
