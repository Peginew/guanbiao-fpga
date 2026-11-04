"""Build a local, read-only annotation viewer. No camera, models, or training."""
from pathlib import Path
import json

HERE = Path(__file__).resolve().parent


def main():
    doc = json.loads((HERE / 'annotations.json').read_text(encoding='utf-8'))
    items = []
    pending = []
    for r in doc['records']:
        item = {k: r.get(k) for k in ('id', 'group', 'filename', 'path', 'image_uri', 'image_kind', 'negative_kind',
                                      'pressure_raw_value', 'pressure_bar_derived', 'pressure_label_source',
                                      'bbox_native_xyxy', 'keypoints', 'review_status', 'condition',
                                      'capture_condition_planned', 'joint_keypoints_visible', 'target_present')}
        item['coordinate_precision_tier'] = r.get('coordinate_precision_tier')
        item['independent_reposition'] = r.get('independent_reposition')
        item['manual_focus_setting_unchanged'] = r.get('manual_focus_setting_unchanged')
        item['pressure_stable_within_capture_group'] = r.get('pressure_stable_within_capture_group')
        items.append(item)
        if r['target_present'] and (r.get('bbox_native_xyxy') is None or any(
                r['keypoints'][k]['visibility'] == 'unknown' or (r['keypoints'][k].get('uncertainty_px') or 0) > 8
                for k in ('hub', 'thin_terminal'))):
            pending.append(item)
    (HERE / 'uncertain_annotations.json').write_text(json.dumps({'scope': 'Uncertain visible structure; occluded is separately labelled, not fabricated.',
                                                               'count': len(pending), 'records': pending}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    payload = json.dumps(items, ensure_ascii=False).replace('<', '\\u003c')
    html = r'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>观表 · 新数据标注复核</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f1ec;color:#252525;font:15px/1.6 "Microsoft YaHei",sans-serif}
header{background:#212b2c;color:#fff;padding:18px 25px;display:flex;align-items:center;justify-content:space-between;gap:20px}
header strong{font-size:22px;font-weight:600}header span{color:#d4dcd8;font-size:13px}.tools{padding:13px 24px;display:flex;gap:12px;align-items:center;flex-wrap:wrap;border-bottom:1px solid #d8d6ce}
button,select{font:inherit;padding:6px 12px;border:1px solid #b9c2bc;border-radius:5px;background:white;color:#253531;cursor:pointer}
button:hover{border-color:#386a57}main{display:grid;grid-template-columns:240px minmax(0,1fr);gap:20px;padding:20px 24px}nav{max-height:78vh;overflow:auto;border:1px solid #d8d6ce;background:#fff}
nav button{display:block;width:100%;text-align:left;border:0;border-radius:0;border-bottom:1px solid #eee;padding:9px 12px}nav button.active{background:#dce9e1;border-left:4px solid #356650}
article{min-width:0}.canvas{position:relative;width:100%;aspect-ratio:16/9;background:#151918;border:1px solid #aaa}img,svg{position:absolute;inset:0;width:100%;height:100%;object-fit:contain}
.legend{display:flex;gap:20px;flex-wrap:wrap;font-size:13px;margin:10px 0}.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px}.facts{background:#fff;padding:15px 20px;border:1px solid #d8d6ce;overflow-wrap:anywhere}.facts p{margin:4px 0}.file{font-size:12px;color:#5b6863}small{color:#5b6863}.empty{padding:30px}
@media(max-width:850px){main{grid-template-columns:1fr}nav{max-height:150px}.tools{padding:10px}main{padding:12px}}
</style>
<header><strong>观表 / 新数据标注复核</strong><span>472张 · A—H · 仅标注，未训练</span></header>
<div class="tools"><label>分组 <select id="group"><option value="">全部</option></select></label><label>查看 <select id="filter"><option value="all">全部图片</option><option value="joint">轴心与细端均可见</option><option value="incomplete">有表，但关键点不完整</option><option value="negative">无表盘反例</option></select></label><button id="prev">← 上一张</button><button id="next">下一张 →</button><label><input type="checkbox" id="show" checked> 显示标注</label><span id="count"></span></div>
<main><nav id="list"></nav><article><div class="canvas"><img id="image" alt="原始采集图"><svg id="overlay" viewBox="0 0 1280 720"></svg></div><div class="legend"><span><i class="dot" style="background:#62ed68"></i>真实盘面框</span><span><i class="dot" style="background:#ef68e4"></i>机械轴心</span><span><i class="dot" style="background:#54e4f1"></i>细读数端</span><span>虚线圆表示坐标不确定度；看不清的点不画</span></div><div class="facts" id="facts"></div></article></main>
<script>const data=__DATA__;const $=id=>document.getElementById(id);let rows=data,index=0;const ns='http://www.w3.org/2000/svg';
for(const g of [...new Set(data.map(r=>r.group))]){let o=document.createElement('option');o.value=g;o.textContent=g;$('group').appendChild(o)}
function apply(){let group=$('group').value,f=$('filter').value;rows=data.filter(r=>(!group||r.group===group)&&(f==='all'||f==='joint'&&r.joint_keypoints_visible||f==='incomplete'&&r.target_present&&!r.joint_keypoints_visible||f==='negative'&&!r.target_present));index=0;render()}
function shape(tag,attrs){const e=document.createElementNS(ns,tag);for(const [k,v]of Object.entries(attrs))e.setAttribute(k,v);$('overlay').appendChild(e);return e}
const vis={visible:'可见',occluded:'被遮挡',unknown:'无法确认',absent:'无此目标'};
function row(text,cls){let e=document.createElement('p');e.textContent=text;if(cls)e.className=cls;$('facts').appendChild(e)}
function render(){const list=$('list');list.replaceChildren();$('count').textContent=rows.length?(index+1)+' / '+rows.length:'0张';for(let i=0;i<rows.length;i++){const r=rows[i],b=document.createElement('button');b.textContent=r.id+' · '+(r.target_present?(r.pressure_raw_value??'?')+' psi':'反例');b.className=i===index?'active':'';b.onclick=()=>{index=i;render()};list.appendChild(b)}
$('facts').replaceChildren();$('overlay').replaceChildren();if(!rows.length){$('image').removeAttribute('src');row('没有符合筛选条件的图片。');return}const r=rows[index];$('image').src=r.image_uri;
const b=r.bbox_native_xyxy;if(b)shape('rect',{x:b[0],y:b[1],width:b[2]-b[0],height:b[3]-b[1],fill:'none',stroke:'#62ed68','stroke-width':2});
const h=r.keypoints.hub,t=r.keypoints.thin_terminal;
if(h.xy&&t.xy)shape('line',{x1:h.xy[0],y1:h.xy[1],x2:t.xy[0],y2:t.xy[1],stroke:'#ffe676','stroke-width':1.5});
for(const [key,c]of [['hub','#ef68e4'],['thin_terminal','#54e4f1']]){const p=r.keypoints[key];if(p.visibility==='visible'&&p.xy){shape('circle',{cx:p.xy[0],cy:p.xy[1],r:4,fill:'none',stroke:c,'stroke-width':2});shape('circle',{cx:p.xy[0],cy:p.xy[1],r:p.uncertainty_px||6,fill:'none',stroke:c,'stroke-width':1,'stroke-dasharray':'3 3'})}}
$('overlay').style.display=$('show').checked?'block':'none';row(r.id+' · '+(r.target_present?'有表盘':'反例 / '+(r.negative_kind||'无表盘')));row('压力：'+(r.pressure_raw_value===null?'不适用':r.pressure_raw_value+' psi；换算约 '+r.pressure_bar_derived+' bar（同一标签的单位换算）'));
row('轴心：'+vis[h.visibility]+(h.xy?' ('+h.xy.join(', ')+') ±'+h.uncertainty_px+'px':''));row('细读数端：'+vis[t.visibility]+(t.xy?' ('+t.xy.join(', ')+') ±'+t.uncertainty_px+'px':''));
if(r.independent_reposition===true&&r.manual_focus_setting_unchanged===true)row('采集说明：组间重新摆放，手动调焦设置不变；每档压力基本稳定（用户确认）。','file');
row('原文件：'+r.filename,'file');row(r.path,'file');row('本轮为AI辅助目视标注，保留不确定度；尚未作为独立人工精密真值认证。原图未改，分组未分配训练或测试用途。','file');
let active=list.querySelector('.active');if(active)active.scrollIntoView({block:'nearest'})}
$('group').onchange=apply;$('filter').onchange=apply;$('show').onchange=render;$('prev').onclick=()=>{index=Math.max(0,index-1);render()};$('next').onclick=()=>{index=Math.min(rows.length-1,index+1);render()};
document.addEventListener('keydown',e=>{if(['SELECT','INPUT'].includes(e.target.tagName))return;if(e.key==='ArrowRight')$('next').click();if(e.key==='ArrowLeft')$('prev').click()});render();</script></html>'''
    (HERE / '图片标注复核.html').write_text(html.replace('__DATA__', payload), encoding='utf-8')
    print(json.dumps({'viewer': str(HERE / '图片标注复核.html'), 'uncertain_records': len(pending), 'training': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
