"""Build a standalone PSI reference-substitution control viewer.

Design: cool laboratory paper (#f5f7fa), navy text (#1a2430), green print
landmarks (#117a72), blue model evidence (#366ca8), red errors (#b83a35),
amber rejection (#9b6b16). Actual 2x2 experiment tables encode reference x
calibration; all59 image observations remain accessible without external JS.
This is a diagnostic viewer, never a deployment/automatic-model selection tool.
"""
from pathlib import Path
import base64,csv,hashlib,html,io,json,math
import cv2
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OUT=HERE/'comparison'
MAIN=('oldref_oldcal','visualref_oldcal','oldref_newcal','visualref_newcal')
MATCHED=tuple('matched_'+x for x in MAIN)
NAMES={'oldref_oldcal':'旧自动参考＋旧标定','visualref_oldcal':'视觉参考＋旧标定',
       'oldref_newcal':'旧自动参考＋新标定','visualref_newcal':'视觉参考＋新标定'}
TOP='outer_psi_10_text_centroid';BOTTOM='lower_striped_ball_print_centroid'
SCENE={'front_large_soft_light':'正面大目标柔光','front_medium_soft_light':'正面中目标柔光',
       'front_dim':'正面暗光','backlight_or_local_reflection':'背光或局部反光',
       'mild_left_view':'轻度左侧视','mild_right_view':'轻度右侧视',
       'challenge_with_gauge':'有表挑战样本','empty_background':'空背景',
       'non_gauge_circular_or_reflective_object':'圆物或反光物反例'}

def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def rows(p):return [json.loads(s) for s in Path(p).read_text('utf-8-sig').splitlines() if s.strip()]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_json(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf-8')
def data_uri(im,ext='.png'):
    params=[cv2.IMWRITE_JPEG_QUALITY,88] if ext=='.jpg' else []
    ok,b=cv2.imencode(ext,im,params);assert ok
    return 'data:image/'+('jpeg' if ext=='.jpg' else 'png')+';base64,'+base64.b64encode(b).decode()
def point_view(p,record):
    t=record['view_transform'];x0,y0,_,_=record['native_crop_xyxy']
    return (round((p[0]-x0)*t['scale_x']+t['offset_x']),round((p[1]-y0)*t['scale_y']+t['offset_y']))

def main():
    OUT.mkdir(exist_ok=True)
    summary=load(HERE/'results/comparison_summary.json')
    variants={k:load(HERE/'results'/f'{k}.json') for k in MAIN+MATCHED}
    annotations={r['id']:r for r in rows(HERE/'annotations_g/print_annotations.jsonl')}
    display={r['id']:r for r in rows(HERE/'annotations_g/display_index.jsonl')}
    prepared={r['id']:r for r in rows(ROOT/'algorithm_work/meter_cnn_training_20261102/prepared_validation.jsonl')}
    preds={r['id']:r for r in rows(ROOT/'algorithm_work/meter_pointer_readout_20261102/polar_angle/run_001/validation_predictions.jsonl')}
    z=np.load(ROOT/'algorithm_work/meter_cnn_training_20261102/roi_cache_validation.npz')
    gray={str(i):im for i,im in zip(z['ids'],z['images'])}
    ids=sorted(prepared)
    assert len(ids)==59 and all(sorted(r['id'] for r in v['rows'])==ids for v in variants.values())
    vm={k:{r['id']:r for r in v['rows']} for k,v in variants.items()}
    assets=OUT/'assets';assets.mkdir(exist_ok=True)
    samples=[];contact=[]
    for id in ids:
        a=annotations[id];d=display[id];p=preds[id]
        face=cv2.imdecode(np.fromfile(d['clean_view'],np.uint8),1)
        assert face is not None
        visible=[]
        for key in (TOP,BOTTOM):
            ap=a['anchors'][key]
            if ap['native_xy'] is not None:
                q=point_view(ap['native_xy'],d);visible.append(q)
                cv2.circle(face,q,7,(35,150,45),1,cv2.LINE_AA)
                cv2.drawMarker(face,q,(35,180,45),cv2.MARKER_CROSS,13,1,cv2.LINE_AA)
        if len(visible)==2:cv2.arrowedLine(face,visible[1],visible[0],(35,150,45),1,cv2.LINE_AA,tipLength=.045)
        g=gray[id];assert g.shape==(128,128) and g.dtype==np.uint8
        candidate=cv2.cvtColor(g,cv2.COLOR_GRAY2BGR)
        hub=p.get('hub_roi');endpoint=p.get('direction_reference_endpoint_roi')
        if hub is not None:
            q=tuple(round(v) for v in hub)
            cv2.drawMarker(candidate,q,(230,180,20),cv2.MARKER_CROSS,9,1,cv2.LINE_AA)
            if endpoint is not None:
                e=tuple(round(v) for v in endpoint)
                cv2.line(candidate,q,e,(220,80,200),1,cv2.LINE_AA)
        for suffix,im in [('native_print',face),('gray_roi',g),('same_nn',candidate)]:
            cv2.imencode('.png',im)[1].tofile(str(assets/f'{id}_{suffix}.png'))
        rr={k:vm[k][id] for k in variants}
        samples.append(dict(id=id,scene=SCENE.get(prepared[id]['scene']['primary'],prepared[id]['scene']['primary']),
            visual_available=a['accepted'],annotation_reason=a['reason'],
            anchor_visibility={k:a['anchors'][k]['visibility'] for k in (TOP,BOTTOM)},
            anchor_uncertainty_native_px={k:a['anchors'][k]['uncertainty_native_px'] for k in (TOP,BOTTOM)},
            reference_psi=rr[MAIN[0]]['psi_reference_for_scoring'],gauge=rr[MAIN[0]]['target_present_for_scoring'],
            source_sha256=a['source_sha256'],model_permitted=p['valid'],model_score=p.get('score'),
            roi_request=prepared[id]['roi_request'],variants=rr,
            images={'native':data_uri(face,'.jpg'),'gray':data_uri(g),'nn':data_uri(candidate)}))
        tile=np.full((244,352,3),255,np.uint8)
        cv2.putText(tile,id+(' print' if a['accepted'] else ' unknown'),(6,19),cv2.FONT_HERSHEY_SIMPLEX,.55,(30,40,50),1,cv2.LINE_AA)
        tile[28:188,4:164]=cv2.resize(face,(160,160))
        tile[28:188,180:340]=cv2.resize(candidate,(160,160),interpolation=cv2.INTER_NEAREST)
        for j,k in enumerate(MAIN):
            r=rr[k];s='--' if not r['valid'] else f'{r["psi_estimate"]:.2f}'
            color=(30,120,30) if r['valid'] and r['absolute_error_psi']<=.5 else (40,60,180) if r['valid'] else (110,110,110)
            cv2.putText(tile,f'{j+1}: {s}',(5+(j%2)*176,211+(j//2)*23),cv2.FONT_HERSHEY_SIMPLEX,.46,color,1,cv2.LINE_AA)
        contact.append(tile)
    for start in range(0,len(contact),12):
        canvas=np.full((244*3,352*4,3),240,np.uint8)
        for j,t in enumerate(contact[start:start+12]):
            yy,xx=divmod(j,4);canvas[yy*244:(yy+1)*244,xx*352:(xx+1)*352]=t
        cv2.imencode('.png',canvas)[1].tofile(str(OUT/f'overview_contact_{start//12+1:02d}.png'))
    # A complete machine-readable table accompanies, but does not alter, the frozen results.
    fields=['id','scene','target_present','reference_psi','visual_reference_available','model_permitted',
            'variant','valid','psi_estimate','absolute_error_psi','reason','source_sha256']
    stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    for s in samples:
        for k,r in s['variants'].items():
            writer.writerow(dict(id=s['id'],scene=s['scene'],target_present=s['gauge'],reference_psi=s['reference_psi'],
                visual_reference_available=s['visual_available'],model_permitted=s['model_permitted'],variant=k,
                valid=r['valid'],psi_estimate=r['psi_estimate'],absolute_error_psi=r['absolute_error_psi'],
                reason=r['reason'],source_sha256=s['source_sha256']))
    csv_text=stream.getvalue();(OUT/'per_image_psi_controls.csv').write_text('\ufeff'+csv_text,'utf-8')
    summary_fields=['variant','scope','images','gauge_images','valid_readings','reading_mae_psi','reading_max_abs_error_psi','within_0_25_psi','within_0_5_psi','within_1_0_psi','negative_false_accepts']
    with (OUT/'summary_psi_controls.csv').open('w',newline='',encoding='utf-8-sig') as fp:
        w=csv.DictWriter(fp,fieldnames=summary_fields);w.writeheader()
        for k,v in variants.items():
            for scope,field in [('all_G','summary'),('same_visual_available_subset','same_visual_available_subset_summary')]:
                s=v[field];w.writerow({**{q:s.get(q) for q in summary_fields if q in s},'variant':k,'scope':scope,**{q:s['output_error_distribution_psi'][q] for q in ('within_0_25_psi','within_0_5_psi','within_1_0_psi')}})
    payload={'summary':summary,'variants':variants,'samples':samples,'names':{**NAMES,**{'matched_'+k:'共同训练样本：'+v for k,v in NAMES.items()}},'main':MAIN,'matched':MATCHED,'csv':csv_text}
    text=TEMPLATE.replace('__DATA__',json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('</','<\\/'))
    # With only59 collapsible rows, avoid content-visibility anchor-scroll quirks
    # in the offline Chromium viewer. The raw images remain lazy-loaded.
    text=text.replace('content-visibility:auto;contain-intrinsic-size:auto 80px','')
    (OUT/'index.html').write_text(text,'utf-8')
    source_files=[HERE/'results/comparison_summary.json',HERE/'annotations_g/print_annotations.jsonl',HERE/'annotations_train/print_annotations.jsonl',Path(__file__)]
    source_files += [HERE/'results'/f'{k}.json' for k in variants]
    receipt={'status':'COMPLETE_STANDALONE_DIAGNOSTIC_VIEW_PENDING_RENDER_QA','images':59,'gauges':56,'visual_available':summary['visual_reference_available_G_count'],
        'variants':8,'per_image_csv_rows':59*8,'main_unit':'psi','full59_included':True,'no_network_or_annotation_or_output_change':True,
        'visual_reference_is_automatic_or_gold':False,'no_new_training_or_device_operation':True,
        'inputs_sha256':{str(p.relative_to(ROOT)):sha(p) for p in source_files},
        'outputs_sha256':{str(p.relative_to(HERE)):sha(p) for p in [OUT/'index.html',OUT/'per_image_psi_controls.csv',OUT/'summary_psi_controls.csv']}}
    write_json(OUT/'build_receipt.json',receipt)
    print(json.dumps({k:v for k,v in receipt.items() if not k.endswith('sha256')},ensure_ascii=False))

TEMPLATE=r'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>观表｜静态印刷参考替换对照</title><style>
:root{--paper:#f5f7fa;--ink:#1a2430;--muted:#5d6d80;--line:#cbd5df;--blue:#366ca8;--green:#117a72;--red:#b83a35;--amber:#9b6b16}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.65 "Segoe UI","Microsoft YaHei",sans-serif}main{max-width:1220px;margin:auto;padding:28px 32px 70px}h1{font-size:30px;line-height:1.25;font-weight:650;margin:0 0 13px}h2{font-size:22px;line-height:1.3;margin:34px 0 12px}h3{font-size:17px;margin:8px 0}p{max-width:84ch;margin:7px 0 13px}.intro{border-left:6px solid var(--blue);padding:8px 0 8px 19px}.intro strong{font-size:18px}.notice{background:#edf2f7;padding:13px 17px;border:1px solid #c7d3df;margin:17px 0;color:#263c55}.notice.warn{background:#fff5e7;border-color:#dbc49b;color:#674915}.tools{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:15px 0}.tools label{color:var(--muted)}button,select,input{font:inherit;color:inherit;border:1px solid #aab9c8;border-radius:4px;padding:6px 10px;background:white}button{cursor:pointer}button:hover{background:#e9f0f7}button:focus-visible,select:focus-visible,input:focus-visible,a:focus-visible{outline:3px solid #5e93c5;outline-offset:2px}a{color:#245f97;text-underline-offset:3px}.small{font-size:13px;color:var(--muted)}.tablewrap{overflow-x:auto}table{border-collapse:collapse;width:100%;background:white;font-variant-numeric:tabular-nums}th,td{text-align:left;padding:10px 13px;border:1px solid var(--line);vertical-align:top}th{background:#e8eef4;font-weight:600}.matrix{table-layout:fixed}.matrix th:first-child{width:130px}.matrix td{padding:16px 18px}.matrix .headline{font-size:20px;font-weight:650;display:block;margin:5px 0}.matrix .tag{color:var(--muted);font-size:13px}.matrix .bad{color:var(--red)}.meter{display:flex;height:9px;margin:10px 0 7px;background:#e1e7ed}.meter .ok{background:#377c70}.meter .near{background:#60918a}.meter .far{background:#cf8b46}.meter .wrong{background:#b84e4a}.metricline{margin-top:9px}.mono{font-variant-numeric:tabular-nums}.ids a{display:inline-block;padding:1px 4px;margin:1px;background:#eef3f7;font-size:13px}.change{margin-bottom:10px}.change strong{display:inline-block;min-width:160px}.changes-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.changeblock{border:1px solid var(--line);padding:13px 15px;background:white}.changes-grid p{margin:6px 0;font-size:13px}.sample{margin:12px 0;background:white;border:1px solid var(--line);border-radius:4px;overflow:hidden;content-visibility:auto;contain-intrinsic-size:auto 80px}.sample summary{cursor:pointer;padding:12px 15px;display:flex;gap:16px;align-items:center;flex-wrap:wrap;font-weight:500}.sample summary::marker{color:var(--blue)}.sample .id{font-weight:700;font-size:17px;min-width:65px}.badge{font-size:12px;border:1px solid #bbcad8;padding:1px 7px;border-radius:12px;background:#f1f5f8}.sample-body{padding:0 15px 18px}.visuals{display:grid;grid-template-columns:1fr 1fr 1fr;gap:13px;align-items:start}.visuals figure{margin:0}.visuals img{width:100%;aspect-ratio:1;object-fit:contain;background:#e5e9ed;display:block}.visuals .roi{image-rendering:pixelated}figcaption{font-size:12px;color:var(--muted);padding:5px 0;line-height:1.5}.state-ok{color:var(--green);font-weight:600}.state-wrong{color:var(--red);font-weight:600}.state-reject{color:var(--amber)}.detail-table{font-size:13px;margin-top:8px}.detail-table th,.detail-table td{padding:6px 9px}.reason{font-size:12px;overflow-wrap:anywhere;line-height:1.4;color:var(--muted)}.scope{font-size:13px;max-width:none}.source{overflow-wrap:anywhere;font:12px/1.65 Consolas,monospace}.foot{border-top:1px solid var(--line);margin-top:30px;padding-top:15px}.legend{display:flex;flex-wrap:wrap;gap:15px;font-size:13px}.legend span:before{content:"";display:inline-block;width:11px;height:11px;margin-right:5px;background:var(--legend)}.green{--legend:#23962d}.blue{--legend:#14b4e6}.pink{--legend:#c850dc}.red{--legend:#b83a35}@media(max-width:720px){main{padding:20px 14px 45px}h1{font-size:26px}.matrix th:first-child{width:92px}.matrix td{padding:10px}.matrix .headline{font-size:17px}.changes-grid{grid-template-columns:1fr}.visuals{grid-template-columns:1fr}.visuals img{max-height:360px}.sample summary{gap:8px}.tools input{max-width:200px}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
</style></head><body><main>
<header><h1>印刷参考方向，究竟卡住了多少读数？</h1><div class="intro"><strong>视觉参考替换诊断，不是新自动网络或板测结果。</strong><p>同一套轴心与指针预测保持不变，只替换静态印刷方向、标定，分别观察数值输出和错误。所有结果来自G开发集；AI视觉标注参考由原生图像审阅提供，不能直接当作MCU的自动能力。</p></div></header>
<div class="notice warn" id="conclusion"></div>
<p class="scope" id="scope"></p><p class="small">误差≤0.25 / 0.5 / 1.0 psi仅为展示分布，不改变输出许可，也不是用户确认的精度目标。MAE只统计已输出的读数，需与覆盖和错读一起看。</p>
<div class="tools"><button id="csv">下载全部八组逐图CSV</button><a href="#samples">核查全部59张</a><a href="#changes">查看新增与撤销ID</a><a href="#provenance">查看证据来源</a></div>
<h2>主对照：参考方向 × 标定</h2><p class="small">主表分母固定为全部59张：56张有表、3张反例。新标定只使用D/E/F中已视觉标注且有合格针位监督的训练图拟合，不用G压力拟合。</p>
<div class="tablewrap" id="matrix"></div>
<h2>同一视觉可用子集V</h2><p class="small" id="subset-note"></p><div class="tablewrap" id="subset"></div>
<details><summary><strong>共同训练样本控制：区分标定数据覆盖变化</strong></summary><p class="small" id="matched-note"></p><div class="tablewrap" id="matched"></div></details>
<h2 id="changes">新增输出、错读与撤销</h2><div class="tools"><label for="band">描述性误差观察带</label><select id="band"><option value="0.25">0.25 psi</option><option value="0.5" selected>0.5 psi</option><option value="1.0">1.0 psi</option></select></div><p class="small">下列变化均对比固定旧参考＋旧标定；“新增带内”也可能来自原错读被修正，不等同于新增输出。点击ID可定位原图证据。</p><div id="changes-body" class="changes-grid"></div>
<h2 id="samples">逐图证据：59张全部保留</h2><div class="legend"><span class="green">绿色：视觉印刷锚点</span><span class="blue">青色：原网络轴心候选</span><span class="pink">紫色：原网络方向参考线，非真针尖</span></div>
<p class="small">左图为原生盘面裁剪与视觉印刷点，中图为原128×128灰度ROI，右图叠加同一套原网络轴心及方向候选。拒读仍显示候选证据；原图烧入的OSD保持原样，未伪造无OSD图像。绿色侧标不是模型输出或人工金标。</p>
<div class="tools"><label for="variant">筛选依据</label><select id="variant"></select><select id="filter"><option value="all">全部59张</option><option value="valid">本格有读数</option><option value="reject">本格拒读</option><option value="wrong">本格误差超观察带</option><option value="changed">与基线数值许可不同</option><option value="no-ref">视觉参考不可用</option></select><input id="search" placeholder="搜索ID或场景" aria-label="搜索ID或场景"><button id="expand">展开当前全部图片</button><button id="collapse">折叠图片</button><span id="show-count" class="small"></span></div><div id="sample-list"></div>
<h2 id="provenance">证据与边界</h2><p>没有新训练、权重更新、MCU/RTL修改、板卡下载或车辆动作。视觉参考来自固定两个静态印刷锚点：顶部外圈“10”中心与底部条纹球标识中心；缺失不补零旋转，也不回退旧姿态来增加覆盖。它只提供图像内相对方向，不能完成侧视透视校正。</p><p class="small">G是已多次使用的开发集；3张反例零输出不等于工业低误识率。压力参考与视觉点均有未认证的不确定度。页面不会自动选择输出数最多的格子或把它标为可部署方案。</p><details><summary>查看冻结来源SHA及实验回执</summary><pre id="sources" class="source"></pre></details>
<footer class="foot small">本地独立页面；图片、逐图结果和CSV内容均已嵌入。主单位psi。实验范围仅静态印刷参考替换与训练专用标定控制。</footer>
</main><script id="data" type="application/json">__DATA__</script><script>
'use strict';const D=JSON.parse(document.getElementById('data').textContent),V=D.variants,S=D.summary;const f=(x,n=3)=>x==null?'—':Number(x).toFixed(n);const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const byid=id=>document.getElementById(id);const dist=s=>s.output_error_distribution_psi;
function bar(s){const d=dist(s),n=s.gauge_images||1;const counts=[d.bins.up_to_0_25,d.bins.over_0_25_to_0_5,d.bins.over_0_5_to_1_0,d.bins.over_1_0];return '<div class="meter" title="四段依次≤.25、.25到.5、.5到1、>1psi；余下灰色为拒读">'+counts.map((v,i)=>`<span class="${['ok','near','far','wrong'][i]}" style="width:${100*v/n}%"></span>`).join('')+'</div>'}
function cell(k){const s=V[k].summary,d=dist(s);return `<span class="tag">${esc(D.names[k])}</span><span class="headline">输出 ${s.valid_readings} / ${s.gauge_images}　MAE ${f(s.reading_mae_psi)} psi</span>${bar(s)}<div>误差≤0.25 / 0.5 / 1.0 psi：<strong>${d.within_0_25_psi} / ${d.within_0_5_psi} / ${d.within_1_0_psi}</strong></div><div class="metricline">有表拒读 ${s.gauge_images-s.valid_readings}　<span class="bad">误差&gt;0.5：${s.valid_readings-d.within_0_5_psi}</span>　最大误差 ${f(s.reading_max_abs_error_psi)} psi</div><div class="small">反例输出 ${s.negative_false_accepts} / ${s.negative_images}</div>`}
byid('matrix').innerHTML=`<table class="matrix"><thead><tr><th>训练专用标定</th><th>旧自动印刷参考</th><th>视觉辅助印刷参考</th></tr></thead><tbody><tr><th>旧标定</th><td>${cell('oldref_oldcal')}</td><td>${cell('visualref_oldcal')}</td></tr><tr><th>新标定</th><td>${cell('oldref_newcal')}</td><td>${cell('visualref_newcal')}</td></tr></tbody></table>`;
function summaryTable(keys,field){return '<table><thead><tr><th>对照格</th><th>输出 / 有表</th><th>MAE psi</th><th>≤.25 / .5 / 1 psi</th><th>&gt;.5 psi</th><th>拒读</th></tr></thead><tbody>'+keys.map(k=>{const s=V[k][field],d=dist(s);return `<tr><td>${esc(D.names[k])}</td><td>${s.valid_readings} / ${s.gauge_images}</td><td>${f(s.reading_mae_psi)}</td><td>${d.within_0_25_psi} / ${d.within_0_5_psi} / ${d.within_1_0_psi}</td><td>${s.valid_readings-d.within_0_5_psi}</td><td>${s.gauge_images-s.valid_readings}</td></tr>`}).join('')+'</tbody></table>'}
byid('subset').innerHTML=summaryTable(D.main,'same_visual_available_subset_summary');byid('matched').innerHTML=summaryTable(D.matched,'summary');
byid('scope').textContent=`全部G开发图59张 / 有表56张 / 反例3张；视觉双锚点可用V=${S.visual_reference_available_G_count}张。新标定实际训练观测${S.new_calibration_observations}张；共同训练标定观测${S.common_calibration_observations}张。`;
byid('subset-note').textContent=`V为在原生图与当前ROI中都能支持固定两锚点方向的${S.visual_reference_available_G_count}张有表图。四格均在完全相同V上统计；这里不再混入全部56张有表分母。`;
byid('matched-note').textContent=`共同训练样本${S.common_calibration_observations}张，使用同一批训练ID分别拟合旧参考与视觉参考标定。下面仍在全部59张G图（56有表）评估，避免把新标定的样本覆盖变化当作参考方向改善。`;
byid('conclusion').innerHTML='<strong>输出增多，仍伴随新错误。</strong> 旧基线21张输出、21张误差≤0.5psi；只替视觉参考后27张输出，其中24张在该观察带内。参考与标定同时替换虽输出29张，只有23张在该带内。<strong>不能把29次出数当作通过，或当成新自动方案。</strong>';
function links(ids){return ids.length?ids.map(i=>`<a href="#${i}" data-jump="${i}">${esc(i)}</a>`).join(' '):'<span class="small">无</span>'}
function renderChanges(){const band=byid('band').value;byid('changes-body').innerHTML=D.main.map(k=>{const c=V[k].changes_against_frozen_baseline,b=c.bands[band];return `<section class="changeblock"><h3>${esc(D.names[k])}</h3><p>新增输出 ${c.new_output_ids.length}；撤销输出 ${c.withdrawn_output_ids.length}</p><div class="change"><strong>新增带内 ${b.gained_correct_ids.length}</strong><span class="ids">${links(b.gained_correct_ids)}</span></div><div class="change"><strong>新增带外错读 ${b.new_wrong_ids.length}</strong><span class="ids">${links(b.new_wrong_ids)}</span></div><div class="change"><strong>撤销旧带内 ${b.lost_correct_ids.length}</strong><span class="ids">${links(b.lost_correct_ids)}</span></div><p class="small">“撤销旧带内”包含变成拒读或误差移到带外。</p></section>`}).join('')}
function status(r,band){if(!r.valid)return ['state-reject','拒读'];return r.absolute_error_psi<=band?['state-ok','带内输出']:['state-wrong','带外输出']}
function renderSamples(){const variant=byid('variant').value,filter=byid('filter').value,term=byid('search').value.toLowerCase(),band=Number(byid('band').value);let count=0;byid('sample-list').innerHTML=D.samples.map((s,i)=>{const r=s.variants[variant],b=s.variants.oldref_oldcal;let show=true;if(filter==='valid')show=r.valid;if(filter==='reject')show=!r.valid;if(filter==='wrong')show=r.valid&&r.absolute_error_psi>band;if(filter==='changed')show=r.valid!==b.valid;if(filter==='no-ref')show=!s.visual_available;if(term)show=show&&(s.id+' '+s.scene).toLowerCase().includes(term);if(!show)return '';count++;let [cls,label]=status(r,band);const rows=D.main.map(k=>{const q=s.variants[k],st=status(q,band);return `<tr><th>${esc(D.names[k])}</th><td class="${st[0]}">${st[1]}</td><td>${q.valid?f(q.psi_estimate)+' psi':'—'}</td><td>${q.valid?f(q.absolute_error_psi)+' psi':'—'}</td><td class="reason">${esc(q.reason)}</td></tr>`}).join('');return `<details class="sample" id="${s.id}" ${i===0?'open':''}><summary><span class="id">${s.id}</span><span>${esc(s.scene)}</span><span class="badge">${s.gauge?'参考 '+f(s.reference_psi,2)+' psi':'反例'}</span><span class="badge">${s.visual_available?'视觉参考可用':'视觉参考未知'}</span><span class="${cls}">${label} ${r.valid?f(r.psi_estimate,2)+' psi':''}</span></summary><div class="sample-body"><div class="visuals"><figure><img alt="${s.id}原生盘面与静态印刷点" src="${s.images.native}" loading="lazy"><figcaption>原生盘面；绿色为视觉诊断印刷点。原烧入OSD保持。</figcaption></figure><figure><img class="roi" alt="${s.id}原128灰度ROI" src="${s.images.gray}" loading="lazy"><figcaption>原128×128 U8灰度ROI，网络输入不改。</figcaption></figure><figure><img class="roi" alt="${s.id}同原网络轴心及针向候选" src="${s.images.nn}" loading="lazy"><figcaption>同原网络候选，许可${s.model_permitted?'成立':'未成立'}。紫线末端为方向参考，不是测得针尖。</figcaption></figure></div><div class="tablewrap"><table class="detail-table"><thead><tr><th>四格对照</th><th>状态</th><th>输出</th><th>绝对误差</th><th>输出或拒读原因</th></tr></thead><tbody>${rows}</tbody></table></div><p class="reason">视觉参考：${esc(s.annotation_reason)}<br>顶部“10”：${esc(s.anchor_visibility.outer_psi_10_text_centroid)}；底部条纹球：${esc(s.anchor_visibility.lower_striped_ball_print_centroid)}。原图SHA ${s.source_sha256}</p></div></details>`}).join('');byid('show-count').textContent=`显示${count} / 59张`}
byid('variant').innerHTML=D.main.map(k=>`<option value="${k}">${esc(D.names[k])}</option>`).join('');
byid('band').onchange=()=>{renderChanges();renderSamples()};['variant','filter','search'].forEach(k=>byid(k).addEventListener(k==='search'?'input':'change',renderSamples));
byid('expand').onclick=()=>document.querySelectorAll('.sample').forEach(e=>e.open=true);byid('collapse').onclick=()=>document.querySelectorAll('.sample').forEach(e=>e.open=false);
document.addEventListener('click',e=>{const a=e.target.closest('[data-jump]');if(!a)return;const id=a.dataset.jump;byid('filter').value='all';byid('search').value='';renderSamples();const t=byid(id);if(t){t.open=true;t.scrollIntoView({block:'start'})}});
byid('csv').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\ufeff',D.csv],{type:'text/csv;charset=utf-8'}));a.download='观表_印刷参考八组PSI逐图对照.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};
byid('sources').textContent=JSON.stringify({status:S.status,source_sha256:S.source_sha256,visual_reference_is_gold_or_automatic:S.visual_reference_is_gold_or_automatic,H_or_ABC_used:S.H_or_ABC_used,training:S.training,hardware_actions:S.hardware_actions},null,2);renderChanges();renderSamples();
</script></body></html>'''

if __name__=='__main__':main()
