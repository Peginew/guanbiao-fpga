"""Standalone evidence viewer for frozen old-first redundant-print controls.

All59 G observations are retained. AI-visual substitution and automaticROI128
patch evidence are distinct arms; this file never chooses an arm for deployment.
"""
from pathlib import Path
import base64,csv,hashlib,io,json,math
import cv2
import numpy as np

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
OLD=ROOT/'algorithm_work/meter_print_reference_control_20261102'
OUT=HERE/'comparison'
KEYS=('old_ring','previous_forced_two_point','visual_old_first','automatic_old_first')
LABELS={'old_ring':'旧环参考基线','previous_forced_two_point':'历史强制双点视觉参考',
        'visual_old_first':'旧优先＋冗余视觉参考','automatic_old_first':'旧优先＋自动patch参考'}
NAMES=['outer_psi_5_text_centroid','outer_psi_10_text_centroid','outer_psi_15_text_centroid',
       'upper_basketball_logo_centroid','middle_soccer_logo_centroid','lower_striped_ball_print_centroid']
SHORT=['外圈5','外圈10','外圈15','篮球印刷','足球印刷','条纹球印刷']
SCENE={'front_medium_soft_light':'正面中目标柔光','front_large_soft_light':'正面大目标柔光',
       'front_dim':'正面暗光','backlight_or_local_reflection':'背光或局部反光',
       'mild_left_view':'轻度左侧视','mild_right_view':'轻度右侧视','challenge_with_gauge':'有表挑战',
       'empty_background':'空背景','non_gauge_circular_or_reflective_object':'圆物/反光物反例'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def rows(p):return [json.loads(x) for x in Path(p).read_text('utf-8-sig').splitlines() if x.strip()]
def uri(im,jpg=False):
    ok,b=cv2.imencode('.jpg' if jpg else '.png',im,[cv2.IMWRITE_JPEG_QUALITY,88] if jpg else []);assert ok
    return 'data:image/'+('jpeg' if jpg else 'png')+';base64,'+base64.b64encode(b).decode()
def viewpoint(p,d):
    x,y,_,_=d['native_crop_xyxy'];t=d['view_transform']
    return (round((p[0]-x)*t['scale_x']+t['offset_x']),round((p[1]-y)*t['scale_y']+t['offset_y']))
def json_display_safe(value,counter):
    # Candidate diagnostics can contain NaN for unavailable evidence. JSON.parse
    # requires strict JSON; use null only for DISPLAY, never rewrite source data.
    if isinstance(value,float) and not math.isfinite(value):counter[0]+=1;return None
    if isinstance(value,dict):return {k:json_display_safe(v,counter) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [json_display_safe(v,counter) for v in value]
    return value
def main():
    OUT.mkdir(exist_ok=True);assets=OUT/'assets';assets.mkdir(exist_ok=True)
    summary=load(HERE/'results/comparison_summary.json')
    reports={k:load(HERE/'results'/f'{k}.json') for k in KEYS}
    labels={r['id']:r for r in rows(HERE/'annotations/print_annotations.jsonl')}
    display={r['id']:r for r in rows(OLD/'annotations_g/display_index.jsonl')}
    records={r['id']:r for r in rows(ROOT/'algorithm_work/meter_cnn_training_20261102/prepared_validation.jsonl')}
    preds={r['id']:r for r in rows(ROOT/'algorithm_work/meter_pointer_readout_20261102/polar_angle/run_001/validation_predictions.jsonl')}
    auto={r['id']:r for r in rows(HERE/'automatic/predictions.jsonl')}
    z=np.load(ROOT/'algorithm_work/meter_cnn_training_20261102/roi_cache_validation.npz')
    gray={str(i):im for i,im in zip(z['ids'],z['images'])}
    ids=sorted(records);assert len(ids)==59 and all(sorted(r['id'] for r in a['rows'])==ids for a in reports.values())
    rm={k:{r['id']:r for r in v['rows']} for k,v in reports.items()}
    old21=[i for i in ids if rm['old_ring'][i]['valid']];assert len(old21)==21
    for k in ('visual_old_first','automatic_old_first'):
        assert all((rm[k][i]['valid'],rm[k][i]['psi_estimate'],rm[k][i]['reason'],rm[k][i]['source_sha256'])==
                   (rm['old_ring'][i]['valid'],rm['old_ring'][i]['psi_estimate'],rm['old_ring'][i]['reason'],rm['old_ring'][i]['source_sha256']) for i in old21)
    samples=[];tiles=[]
    for id in ids:
        a=labels[id];d=display[id];p=preds[id];g=gray[id];ap=auto[id]['points']
        assert a['source_sha256']==records[id]['sha256']==p['source_sha256']==auto[id]['source_sha256']
        face=cv2.imdecode(np.fromfile(d['clean_view'],np.uint8),1)
        for j,name in enumerate(NAMES):
            q=a['anchors'][name]
            if q['native_xy'] is not None:
                v=viewpoint(q['native_xy'],d);color=(40,145,35) if q['visibility']=='visible' else (15,145,220)
                cv2.drawMarker(face,v,color,cv2.MARKER_CROSS,10,1,cv2.LINE_AA)
                cv2.putText(face,str(j+1),(v[0]+4,v[1]-4),cv2.FONT_HERSHEY_SIMPLEX,.34,color,1,cv2.LINE_AA)
        evidence=cv2.cvtColor(g,cv2.COLOR_GRAY2BGR)
        if p.get('hub_roi') is not None:
            hub=tuple(round(x) for x in p['hub_roi']);cv2.drawMarker(evidence,hub,(230,180,20),cv2.MARKER_CROSS,8,1,cv2.LINE_AA)
            if p.get('direction_reference_endpoint_roi') is not None:
                cv2.line(evidence,hub,tuple(round(x) for x in p['direction_reference_endpoint_roi']),(220,80,200),1,cv2.LINE_AA)
        for j,name in enumerate(NAMES):
            q=ap[name]
            if q.get('accepted') and q.get('roi_xy') is not None:
                v=tuple(round(x) for x in q['roi_xy']);cv2.circle(evidence,v,2,(220,130,20),1,cv2.LINE_AA)
                cv2.putText(evidence,str(j+1),(v[0]+2,v[1]-2),cv2.FONT_HERSHEY_SIMPLEX,.24,(220,130,20),1,cv2.LINE_AA)
        for suffix,im in [('visual_points_native',face),('gray_roi',g),('same_nn_and_auto_points',evidence)]:
            cv2.imencode('.png',im)[1].tofile(str(assets/f'{id}_{suffix}.png'))
        rr={k:rm[k][id] for k in KEYS};base=rr['old_ring']
        samples.append(dict(id=id,scene=SCENE.get(records[id]['scene']['primary'],records[id]['scene']['primary']),
            target_present=base['target_present_for_scoring'],reference_psi=base['psi_reference_for_scoring'],
            old_valid=id in old21,source_sha256=a['source_sha256'],model_permitted=p['valid'],
            visual_points=a['anchors'],automatic_points=ap,variants=rr,
            images=dict(native=uri(face,True),gray=uri(g),evidence=uri(evidence))))
        tile=np.full((244,352,3),255,np.uint8)
        cv2.putText(tile,id+(' old21' if id in old21 else ''),(7,19),cv2.FONT_HERSHEY_SIMPLEX,.55,(30,40,50),1,cv2.LINE_AA)
        tile[28:188,4:164]=cv2.resize(face,(160,160));tile[28:188,180:340]=cv2.resize(evidence,(160,160),interpolation=cv2.INTER_NEAREST)
        for j,k in enumerate(KEYS):
            r=rr[k];text='--' if not r['valid'] else f'{r["psi_estimate"]:.2f}'
            color=(30,120,30) if r['valid'] and r['absolute_error_psi']<=.5 else (30,60,185) if r['valid'] else (110,110,110)
            cv2.putText(tile,f'{j+1}: {text}',(5+(j%2)*176,211+(j//2)*23),cv2.FONT_HERSHEY_SIMPLEX,.46,color,1,cv2.LINE_AA)
        tiles.append(tile)
    for start in range(0,59,12):
        canvas=np.full((732,1408,3),240,np.uint8)
        for j,t in enumerate(tiles[start:start+12]):
            yy,xx=divmod(j,4);canvas[yy*244:(yy+1)*244,xx*352:(xx+1)*352]=t
        cv2.imencode('.png',canvas)[1].tofile(str(OUT/f'overview_contact_{start//12+1:02d}.png'))
    fields=['id','scene','target_present','reference_psi','old21','variant','valid','psi_estimate','absolute_error_psi','reason','reference_route','source_sha256']
    stream=io.StringIO(newline='');w=csv.DictWriter(stream,fieldnames=fields);w.writeheader()
    for s in samples:
        for k,r in s['variants'].items():
            w.writerow(dict(id=s['id'],scene=s['scene'],target_present=s['target_present'],reference_psi=s['reference_psi'],
                old21=s['old_valid'],variant=k,valid=r['valid'],psi_estimate=r['psi_estimate'],absolute_error_psi=r['absolute_error_psi'],
                reason=r['reason'],reference_route=r.get('reference_route','PREVIOUS_FORCED_TWO_POINT'),source_sha256=s['source_sha256']))
    csvtext=stream.getvalue();(OUT/'all59_readout_psi.csv').write_text('\ufeff'+csvtext,'utf-8')
    old_rejected=[i for i in ids if not rm['old_ring'][i]['old_reference_accepted']]
    cost=load(HERE/'automatic/completion.json')['cost']
    data=dict(summary=summary,reports=reports,samples=samples,keys=KEYS,names=LABELS,pointNames=NAMES,pointLabels=SHORT,old21=old21,oldReferenceRejected=old_rejected,csv=csvtext,cost=cost)
    nonfinite=[0];safe_data=json_display_safe(data,nonfinite)
    page=TEMPLATE.replace('__DATA__',json.dumps(safe_data,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('</','<\\/'))
    (OUT/'index.html').write_text(page,'utf-8')
    sources=[HERE/'results/comparison_summary.json',HERE/'annotations/print_annotations.jsonl',HERE/'annotations/reference_D002.json',HERE/'annotations/reference_D025.json',HERE/'automatic/predictions.jsonl',HERE/'automatic/completion.json',Path(__file__)]+[HERE/'results'/f'{k}.json' for k in KEYS]
    receipt=dict(status='BUILT_STANDALONE_PENDING_RENDER_QA',images=59,gauges=56,variants=4,CSV_rows=236,
        old21_exactly_preserved_in_visual_and_automatic_old_first=True,annotation_or_outputs_modified=False,
        visual_and_automatic_scopes_separated=True,no_training_or_device_operation=True,
        unavailable_nonfinite_diagnostic_values_displayed_as_null=nonfinite[0],source_diagnostics_unchanged=True,
        inputs_sha256={str(p.relative_to(ROOT)):sha(p) for p in sources},
        outputs_sha256={str(p.relative_to(HERE)):sha(p) for p in (OUT/'index.html',OUT/'all59_readout_psi.csv')},
        contact_legend={str(j+1):k for j,k in enumerate(KEYS)})
    (OUT/'build_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({k:v for k,v in receipt.items() if not k.endswith('sha256')},ensure_ascii=False))

TEMPLATE=r'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>观表｜冗余印刷参考保留与补充</title><style>
:root{--paper:#f5f7fa;--ink:#1a2430;--muted:#5d6d80;--line:#cbd5df;--blue:#366ca8;--good:#117a72;--bad:#b83a35;--warn:#9b6b16}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.65 "Segoe UI","Microsoft YaHei",sans-serif}main{max-width:1240px;padding:28px 30px 70px;margin:auto}h1{font-size:30px;line-height:1.3;margin:0 0 16px}h2{font-size:22px;line-height:1.35;margin:32px 0 12px}h3{font-size:17px;margin:4px 0 10px}p{max-width:88ch;margin:8px 0 13px}.intro{border-left:6px solid var(--blue);padding:8px 18px;background:#edf2f7}.notice{background:#fff5e7;border:1px solid #dbc49b;padding:14px 17px;margin:17px 0}.small{font-size:13px;color:var(--muted)}.tools{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:15px 0}button,select,input{font:inherit;border:1px solid #aab9c8;border-radius:4px;padding:6px 10px;background:white;color:inherit}button{cursor:pointer}button:hover{background:#e8eff6}button:focus-visible,select:focus-visible,input:focus-visible,a:focus-visible{outline:3px solid #5e93c5;outline-offset:2px}a{color:#245f97;text-underline-offset:3px}.tablewrap{overflow-x:auto}table{border-collapse:collapse;width:100%;background:white;font-variant-numeric:tabular-nums}th,td{padding:10px 12px;text-align:left;border:1px solid var(--line);vertical-align:top}th{background:#e8eef4;font-weight:600}.kind{display:block;font-size:12px;font-weight:400;color:var(--muted);max-width:240px}.ok{color:var(--good);font-weight:600}.bad{color:var(--bad);font-weight:600}.reject{color:var(--warn)}.number{font-weight:650;white-space:nowrap}.changes{display:grid;grid-template-columns:1fr 1fr;gap:15px}.changebox{border:1px solid var(--line);padding:14px 16px;background:white}.ids a{display:inline-block;background:#edf3f7;padding:1px 4px;margin:1px;font-size:12px}.changebox p{font-size:13px;margin:5px 0}.sample{background:white;border:1px solid var(--line);border-radius:4px;margin:11px 0;overflow:hidden}.sample summary{padding:12px 14px;display:flex;gap:12px;flex-wrap:wrap;align-items:center;cursor:pointer}.sample summary .id{font-size:17px;font-weight:700;min-width:65px}.badge{font-size:12px;background:#f1f5f8;border:1px solid #bbcad8;border-radius:12px;padding:1px 7px}.samplebody{padding:0 14px 17px}.visuals{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px}.visuals figure{margin:0}.visuals img{display:block;width:100%;aspect-ratio:1;object-fit:contain;background:#e4e9ed}.pixel{image-rendering:pixelated}figcaption{font-size:12px;line-height:1.5;color:var(--muted);padding:5px 0}.detail{font-size:12px;margin-top:9px}.detail th,.detail td{padding:5px 8px}.reason{font-size:12px;color:var(--muted);line-height:1.4;overflow-wrap:anywhere}.source{font:12px/1.6 Consolas,monospace;overflow-wrap:anywhere;white-space:pre-wrap}.legend{font-size:13px;margin:10px 0;color:var(--muted)}.foot{border-top:1px solid var(--line);padding-top:15px;margin-top:30px}@media(max-width:720px){main{padding:20px 14px 45px}h1{font-size:26px}.changes{grid-template-columns:1fr}.visuals{grid-template-columns:1fr}.visuals img{max-height:360px}.tools input{max-width:200px}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
</style></head><body><main><h1>冗余印刷点：保留与补充的逐图对照</h1><div class="intro"><strong>先保留旧参考，再研究能否补回拒读。</strong><p>四条路径使用同一套原轴心/针向网络和旧PSI标定。视觉冗余点来自AI视觉标注，只用于信息诊断；自动patch只使用128灰度ROI及现有预测轴心/定位尺度，仍是PC候选，未部署MCU或板测。</p></div><div class="notice" id="conclusion"></div><p class="small">全分母：G59张，其中56有表、3反例。0.25 / 0.5 / 1.0 psi仅为误差观察带，不是用户精度目标或输出许可。MAE只对已输出读数统计，不能脱离拒读及新增错误评价。</p><div class="tools"><button id="csv">下载59张四路径CSV</button><a href="#changes">新增与撤销ID</a><a href="#samples">全部59张证据</a><a href="#point-eval">自动点证据</a></div>
<h2>同输入、同网络、同标定</h2><div class="tablewrap" id="main-table"></div><p class="small">旧优先路径固定保留每个已接受旧参考；新增参考仅补旧参考未接受的观察。保住旧21次输出不代表新增输出一定正确。历史强制双点路径保留作对照，不作为新方案。</p>
<h2>只看新增部分</h2><div class="tablewrap" id="incremental"></div><p class="small">新增部分与旧21次输出分开统计，避免原基线掩盖补充支路的错误。</p>
<h2>旧参考未接受子集</h2><p class="small" id="subset-note"></p><div class="tablewrap" id="old-rejected"></div>
<h2>正面柔光子集</h2><p class="small">固定两种正面柔光场景共16张；暗光、逆光、左右侧视和强挑战不混入这一分母。</p><div class="tablewrap" id="frontal"></div>
<h2 id="point-eval">自动点定位与反例支持</h2><p class="small">逐点“接受”只是一条patch证据，不等于完整参考或读数有效；score/margin不是正确概率，也不自动诊断物理遮挡。定位误差以固定128规范盘面坐标计，不是原图像素；未知视觉标签不证明这个身份实际不存在。反例上若仍出现点证据，会在此单独显示。</p><div class="tablewrap" id="points"></div><p class="small" id="negative-reference"></p>
<h2 id="changes">逐ID增益与代价</h2><div class="tools"><label for="band">描述性误差观察带</label><select id="band"><option value="0.25">0.25 psi</option><option value="0.5" selected>0.5 psi</option><option value="1.0">1.0 psi</option></select></div><p class="small">各变化均相对旧环固定基线。新增带内包含既有错误被修正；“撤销旧带内”包含改成拒读或移到带外。点击ID打开原图证据。</p><div id="changes-body" class="changes"></div>
<h2 id="samples">59张全部保留</h2><p class="legend">左：AI视觉印刷点（绿=可见、橙=部分可见）；中：原128灰度ROI；右：同原网络轴心（青）/针向参考线（紫）与自动接受印刷点（蓝，编号1到6）。方向线末端不是实测针尖。</p><p class="small">六身份固定为外圈完整5、10、15字组，以及篮球、足球、条纹球印刷标识；不会把外部足球当作盘面足球标识。原图烧入OSD保持，隐藏点不补造，拒读仍展示候选。</p><div class="tools"><label for="variant">筛选路径</label><select id="variant"></select><select id="filter"><option value="all">全部59张</option><option value="old21">原21次有效输出</option><option value="new">本路径新增输出</option><option value="valid">本路径有输出</option><option value="reject">本路径拒读</option><option value="wrong">本路径超过观察带</option><option value="negative">仅3张反例</option></select><input id="search" placeholder="搜索ID或场景" aria-label="搜索ID或场景"><button id="expand">展开当前图片</button><button id="collapse">折叠图片</button><span id="count" class="small"></span></div><div id="sample-list"></div>
<h2>证据边界</h2><p>没有新训练、权重更新、标定重拟合、原图或canonical修改，也没有MCU/RTL修改、下载或车辆操作。D025是唯一训练模板图，D002只提供训练内的零方向对齐。自动参考没有使用本图视觉点、压力或真实针向作输入。</p><p id="cost" class="notice"></p><p class="small">G是反复使用的开发集，3张反例不能证明工业低误识率。AI视觉侧标不是盲人类金标，点位不确定度也不是认证误差界。128输入可取得不等于已证明MCU缓存、整数成本、整固件链接和耗时满足要求。不可用候选诊断中的NaN在本页显示为“—”，源文件未修改。</p><details><summary>冻结来源SHA与回执</summary><pre id="sources" class="source"></pre></details><footer class="foot small">本地独立页面；全部图片、逐图结果及CSV内容内嵌。主单位psi。不会自动选择输出最多的路径作为部署结论。</footer></main><script id="data" type="application/json">__DATA__</script><script>
'use strict';const D=JSON.parse(document.getElementById('data').textContent),S=D.summary,R=D.reports;const E=id=>document.getElementById(id);const f=(x,n=3)=>x==null?'—':Number(x).toFixed(n);const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const bands=s=>s.output_error_distribution_psi;const kind=k=>k==='old_ring'?'固定自动ROI128环基线':k==='previous_forced_two_point'?'历史AI视觉双点诊断':k==='visual_old_first'?'AI视觉冗余点信息诊断':'自动ROI128 patch候选，未上板';
E('main-table').innerHTML='<table><thead><tr><th>路径与范围</th><th>输出 / 有表</th><th>MAE psi</th><th>≤.25 / .5 / 1 psi</th><th>&gt;.5 psi</th><th>原21逐字保留</th></tr></thead><tbody>'+D.keys.map(k=>{const r=R[k],s=r.summary,d=bands(s);const changed=D.old21.filter(i=>{const a=r.rows.find(x=>x.id===i),b=R.old_ring.rows.find(x=>x.id===i);return JSON.stringify([a.valid,a.psi_estimate,a.reason,a.source_sha256])!==JSON.stringify([b.valid,b.psi_estimate,b.reason,b.source_sha256])});return `<tr><th>${esc(D.names[k])}<span class="kind">${kind(k)}</span></th><td class="number">${s.valid_readings} / 56</td><td>${f(s.reading_mae_psi)}</td><td>${d.within_0_25_psi} / ${d.within_0_5_psi} / ${d.within_1_0_psi}</td><td class="${s.valid_readings-d.within_0_5_psi?'bad':''}">${s.valid_readings-d.within_0_5_psi}</td><td>${21-changed.length} / 21${changed.length?'；变化 '+changed.join(', '):''}</td></tr>`}).join('')+'</tbody></table>';
const primary=['visual_old_first','automatic_old_first'];E('incremental').innerHTML='<table><thead><tr><th>补充路径</th><th>新增输出</th><th>新增MAE psi</th><th>新增≤.25 / .5 / 1</th><th>新增&gt;.5 psi</th><th>旧有效输出撤销</th></tr></thead><tbody>'+primary.map(k=>{const r=R[k],s=r.incremental_output_summary;return `<tr><th>${esc(D.names[k])}</th><td>${s.images}</td><td>${f(s.MAE_psi)}</td><td>${s.correct_bands['0.25']} / ${s.correct_bands['0.5']} / ${s.correct_bands['1.0']}</td><td class="${s.images-s.correct_bands['0.5']?'bad':''}">${s.images-s.correct_bands['0.5']}</td><td>${r.original_valid_ids_changed.length}</td></tr>`}).join('')+'</tbody></table>';
const sub=D.samples.filter(x=>D.oldReferenceRejected.includes(x.id)),subG=sub.filter(x=>x.target_present).length;E('subset-note').textContent=`旧参考未接受共${sub.length}张，其中${subG}张有表、${sub.length-subG}张反例；这是允许补充参考的固定子集。旧未出数则共38张，二者不能混为同一失败原因。下面四路径使用相同子集分母。`;E('old-rejected').innerHTML='<table><thead><tr><th>路径</th><th>子集输出 / 有表</th><th>子集MAE psi</th><th>≤.25 / .5 / 1 psi</th><th>反例数值输出</th></tr></thead><tbody>'+D.keys.map(k=>{const a=sub.filter(s=>s.target_present&&s.variants[k].valid).map(s=>s.variants[k]),err=a.map(x=>x.absolute_error_psi);return `<tr><th>${esc(D.names[k])}</th><td>${a.length} / ${subG}</td><td>${f(err.length?err.reduce((a,b)=>a+b,0)/err.length:null)}</td><td>${[.25,.5,1].map(t=>err.filter(e=>e<=t).length).join(' / ')}</td><td>${sub.filter(s=>!s.target_present&&s.variants[k].valid).length} / ${sub.length-subG}</td></tr>`}).join('')+'</tbody></table>';
E('frontal').innerHTML='<table><thead><tr><th>路径</th><th>正面柔光输出 / 16</th><th>≤.25 / .5 / 1 psi</th></tr></thead><tbody>'+D.keys.map(k=>{const a=S.reports[k].frontal;return `<tr><th>${esc(D.names[k])}</th><td>${a.outputs} / ${a.images}</td><td>${a.correct_bands['0.25']} / ${a.correct_bands['0.5']} / ${a.correct_bands['1.0']}</td></tr>`}).join('')+'</tbody></table>';
E('points').innerHTML='<table><thead><tr><th>静态印刷身份</th><th>自动点接受</th><th>视觉可定位</th><th>≤3规范像素 / 可定位</th><th>接受后定位均误差</th><th>反例接受ID</th></tr></thead><tbody>'+D.pointNames.map((n,j)=>{const p=S.point_evaluation[n];return `<tr><th>${j+1} ${D.pointLabels[j]}</th><td>${p.automatic_accepted} / 59</td><td>${p.visually_localizable_labels}</td><td>${p.localization_error_normalized.within3px} / ${p.visually_localizable_labels}</td><td>${f(p.localization_error_normalized.mean)}</td><td class="${p.accepted_on_negative_ids.length?'bad':''}">${p.accepted_on_negative_ids.join(', ')||'无'}</td></tr>`}).join('')+'</tbody></table>';
E('negative-reference').textContent='完整新增参考支持的反例ID：'+primary.map(k=>D.names[k]+' '+(R[k].new_reference_supported_negative_ids.join(', ')||'无')).join('；')+'。这些证据与最终数值输出分开，不因最终拒读就隐藏点级误支持。';
const v=R.visual_old_first.summary,a=R.automatic_old_first.summary;E('conclusion').innerHTML=`<strong>AI视觉诊断${v.valid_readings}次，与自动候选${a.valid_readings}次严格分开。</strong> 两条新路径均保留旧21次输出；视觉侧标不是自动识别能力。新增误差在下面单列，<strong>保留旧结果不是新增部分通过验收。</strong>`;E('cost').textContent=`自动候选PC平均${f(D.cost.PC_mean_ms,2)}ms不是MCU耗时；FP32模板${D.cost.FP32template_bytes}B，显式PC工作数据下界${D.cost.minimum_explicit_PC_image_score_winner_far_mgrid_bytes}B，尚不含OpenCV内部缓冲。当前实现不能直接装入48KiB TCM，整数压缩与复用缓存尚未实现或整应用验证。`;
function links(ids){return ids.length?ids.map(i=>`<a href="#${i}" data-jump="${i}">${i}</a>`).join(' '):'<span class="small">无</span>'}
function changes(){const t=E('band').value;E('changes-body').innerHTML=D.keys.map(k=>{const c=R[k].changes,b=c.bands[t];return `<section class="changebox"><h3>${esc(D.names[k])}</h3><p>新增输出 ${c.new_output_ids.length}；撤销输出 ${c.withdrawn_output_ids.length}</p><p><strong>新增带内 ${b.gained_correct_ids.length}</strong><br><span class="ids">${links(b.gained_correct_ids)}</span></p><p><strong>新增带外错读 ${b.new_wrong_ids.length}</strong><br><span class="ids">${links(b.new_wrong_ids)}</span></p><p><strong>撤销旧带内 ${b.lost_correct_ids.length}</strong><br><span class="ids">${links(b.lost_correct_ids)}</span></p></section>`}).join('')}
function state(r,t){return !r.valid?['reject','拒读']:r.absolute_error_psi<=t?['ok','带内输出']:['bad','带外输出']}
function render(){const k=E('variant').value,filter=E('filter').value,term=E('search').value.toLowerCase(),t=Number(E('band').value);let count=0;E('sample-list').innerHTML=D.samples.map((s,i)=>{const r=s.variants[k],b=s.variants.old_ring;let show=true;if(filter==='old21')show=s.old_valid;if(filter==='new')show=r.valid&&!b.valid;if(filter==='valid')show=r.valid;if(filter==='reject')show=!r.valid;if(filter==='wrong')show=r.valid&&r.absolute_error_psi>t;if(filter==='negative')show=!s.target_present;if(term)show=show&&(s.id+' '+s.scene).toLowerCase().includes(term);if(!show)return '';count++;const st=state(r,t);const rr=D.keys.map(n=>{const x=s.variants[n],v=state(x,t);return `<tr><th>${esc(D.names[n])}</th><td class="${v[0]}">${v[1]}</td><td>${x.valid?f(x.psi_estimate)+' psi':'—'}</td><td>${x.valid?f(x.absolute_error_psi)+' psi':'—'}</td><td class="reason">${esc(x.reference_route||'历史强制双点')}</td><td class="reason">${esc(x.reason)}</td></tr>`}).join('');const pp=D.pointNames.map((n,j)=>{const v=s.visual_points[n],a=s.automatic_points[n];return `<tr><th>${j+1} ${D.pointLabels[j]}</th><td>${esc(v.visibility)}${v.native_xy?'；u≈'+f(v.uncertainty_native_px,1)+'原图像素':''}${v.native_xy&&!v.within_roi_pixel_center_bounds?'；ROI外':''}</td><td>${a.accepted?'接受':'未知/拒绝'}</td><td>${f(a.score,3)}</td><td>${f(a.margin,3)}</td><td class="reason">${esc(a.reason||'')}</td></tr>`}).join('');return `<details class="sample" id="${s.id}" ${i===0?'open':''}><summary><span class="id">${s.id}</span><span>${esc(s.scene)}</span><span class="badge">${s.target_present?'参考 '+f(s.reference_psi,2)+' psi':'反例'}</span>${s.old_valid?'<span class="badge">原21次有效输出</span>':''}<span class="${st[0]}">${st[1]} ${r.valid?f(r.psi_estimate,2)+' psi':''}</span></summary><div class="samplebody"><div class="visuals"><figure><img alt="${s.id}AI视觉印刷点侧标" src="${s.images.native}" loading="lazy"><figcaption>AI视觉印刷侧标，不是自动输出或人工金标。编号固定六身份。</figcaption></figure><figure><img class="pixel" alt="${s.id}原128灰ROI" src="${s.images.gray}" loading="lazy"><figcaption>原128×128 U8灰度ROI，输入未修改。</figcaption></figure><figure><img class="pixel" alt="${s.id}同原轴针网络与自动点" src="${s.images.evidence}" loading="lazy"><figcaption>同原轴心/针向候选；自动点仅画其自身接受证据，不是最终共识/READ许可。</figcaption></figure></div><div class="tablewrap"><table class="detail"><thead><tr><th>路径</th><th>状态</th><th>输出</th><th>绝对误差</th><th>参考路由</th><th>原因</th></tr></thead><tbody>${rr}</tbody></table></div><details><summary>逐点可见性与自动证据</summary><div class="tablewrap"><table class="detail"><thead><tr><th>身份</th><th>视觉侧标</th><th>自动点</th><th>score</th><th>margin</th><th>原因</th></tr></thead><tbody>${pp}</tbody></table></div></details><p class="reason">原图SHA ${s.source_sha256}；旧网络许可 ${s.model_permitted?'成立':'未成立'}。视觉点的不确定度仅估计，非认证误差界。</p></div></details>`}).join('');E('count').textContent=`显示${count} / 59张`}
E('variant').innerHTML=D.keys.map(k=>`<option value="${k}">${esc(D.names[k])}</option>`).join('');E('band').onchange=()=>{changes();render()};['variant','filter','search'].forEach(k=>E(k).addEventListener(k==='search'?'input':'change',render));E('expand').onclick=()=>document.querySelectorAll('.sample').forEach(e=>e.open=true);E('collapse').onclick=()=>document.querySelectorAll('.sample').forEach(e=>e.open=false);document.addEventListener('click',e=>{const a=e.target.closest('[data-jump]');if(a){E('filter').value='all';E('search').value='';render();const t=E(a.dataset.jump);if(t){t.open=true;t.scrollIntoView({block:'start'})}}});E('csv').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob(['\ufeff',D.csv],{type:'text/csv;charset=utf-8'}));a.download='观表_冗余印刷参考59图PSI.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000)};E('sources').textContent=JSON.stringify({status:S.status,source_sha256:S.source_sha256,automatic_did_not_use_query_point_labels:S.automatic_did_not_use_query_point_labels,H_ABC_opened:S.H_ABC_opened,new_training:S.new_training,hardware_actions:S.hardware_actions},null,2);changes();render();
</script></body></html>'''
if __name__=='__main__':main()
