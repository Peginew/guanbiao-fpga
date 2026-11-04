"""G59 per-identity print-visibility diagnostic, independently of readout.

Four additional identities are visually read from raw ID-only views. Previously
frozen top/lower points are copied individually, with explicit visual review of
the six formerly jointly rejected top points. No PSI/NN/pose results are inputs.
"""
from pathlib import Path
import json,hashlib,sys
import cv2
import numpy as np
from build_annotations import BASE,ROOT,OLD,NAMES,sha,readrows,save,roi,pnative,anchor

# Raw384-view centers, ordered outer5,outer15,upper basketball,middle soccer.
# None is never replaced with layout/angle/pressure-based coordinates.
NEW_POINTS={
 1:((71,148),(296,136),(185,144),(185,219)),
 2:((67,153),(293,131),(183,145),(187,218)),
 3:((78,143),(301,135),(191,144),(186,219)),
 4:((76,137),(304,148),(190,145),(186,218)),
 5:((81,140),(298,141),(196,144),(191,218)),
 6:((83,132),(299,155),(186,145),(179,218)),
 7:((75,141),(299,145),(188,144),(185,218)),
 8:((69,145),(296,141),(184,143),(188,219)),
 9:((78,141),(299,149),(191,143),(182,219)),
 10:((79,133),(302,149),(192,143),(185,217)),
 11:((79,138),(301,143),(196,143),(187,218)),
 12:((78,133),(302,146),(183,144),(182,218)),
 13:((76,138),(302,145),(192,143),None),
 14:((75,141),(300,142),(190,143),None),
 15:((78,140),(301,147),(190,144),None),
 16:((74,141),(302,145),(191,144),None),
 17:((80,139),(303,149),(201,142),None),
 18:((78,137),(299,146),(188,142),None),
 19:((72,149),(297,137),(185,145),(186,219)),
 20:((70,167),(296,145),(185,158),(187,232)),
 21:((76,143),(298,137),(191,144),(186,219)),
 22:((78,137),(306,146),(192,144),(184,218)),
 23:((84,141),(301,141),(195,143),(190,219)),
 24:((78,139),(301,146),(190,143),(181,218)),
 25:((76,142),(304,144),(192,144),(186,219)),
 26:((81,141),(301,143),(192,143),(184,219)),
 27:((80,142),(300,144),(192,142),(182,218)),
 28:((79,136),(306,147),(192,144),(186,218)),
 29:((82,144),(299,134),(193,143),(191,218)),
 30:((81,132),(299,148),(186,144),(181,218)),
 31:((77,142),(304,145),(188,144),(186,218)),
 32:((70,159),(300,145),(185,154),(181,232)),
 33:((78,143),(299,143),(189,143),(184,218)),
 34:((75,137),(299,147),(189,143),(183,218)),
 35:((81,140),(302,143),(197,143),(188,218)),
 36:((77,134),(299,149),(187,142),(181,217)),
 37:((72,152),(298,134),(187,145),(187,219)),
 38:((69,151),(294,134),(183,144),(186,219)),
 39:((78,144),(300,136),(189,144),(187,217)),
 40:((79,143),(303,147),(191,144),(186,219)),
 41:((84,139),(301,142),(194,143),(190,218)),
 42:((78,134),(300,149),(185,142),(181,217)),
 43:((78,140),(304,146),(192,143),(185,217)),
 44:((76,140),(298,145),(189,143),(180,220)),
 45:((77,140),(303,144),(191,143),(187,218)),
 46:((70,148),(298,136),(186,144),(186,218)),
 47:((78,146),(299,136),(192,143),(191,218)),
 48:((78,136),(301,146),(183,144),(182,218)),
 49:(None,None,None,None),50:(None,None,None,None),51:(None,None,None,None),
 52:((76,132),None,(188,141),(180,214)),
 53:(None,None,None,None),
 54:(None,None,(183,152),None),55:(None,None,(185,150),None),
 56:((82,148),(295,139),(193,151),None),
 57:((79,143),None,None,None),
 58:(None,None,(192,160),(183,230)),
 59:((87,143),None,(202,160),(188,228)),
}

def main():
    display={r['id']:r for r in readrows(OLD/'annotations_g/display_index.jsonl')}
    # Only previously frozen per-anchor coordinates/visibility are selected.
    old={r['id']:{'source_sha256':r['source_sha256'],'anchors':{k:r['anchors'][k] for k in (NAMES[1],NAMES[5])}} for r in readrows(OLD/'annotations_g/print_annotations.jsonl')}
    assert len(display)==59 and len(NEW_POINTS)==59
    out=[];tiles=[]
    for id,d in sorted(display.items()):
        n=int(id.split('_')[1]);q=d['roi_request'];a={}
        for k in (NAMES[1],NAMES[5]):
            o=old[id]['anchors'][k];p=o['native_xy'];vis=o['visibility']
            vis='partial' if vis=='partially_visible' else 'visible' if vis=='visible' else 'unknown'
            why='Per-point reuse of prior frozen static-print visual sidecar; old whole-reference accepted flag is not used.'
            if 13<=n<=18 and k==NAMES[5]:vis='occluded';why='Broad counterweight covers nearly all lower striped-ball print; center is not reconstructed.'
            if 13<=n<=18 and k==NAMES[1]:
                vp={13:(191,63),14:(181,63),15:(185,63),16:(190,63),17:(198,63),18:(183,63)}[n]
                p=pnative(vp,d);vis='visible' if n==17 else 'partial'
                uv=3 if n==17 else 6 if n==16 else 5
                u=uv/min(d['view_transform']['scale_x'],d['view_transform']['scale_y'])
                why='Independently re-read tiny top10 from visible glyph fragments; no longer coupled to hidden lower ball. Increased uncertainty for thin-needle/glare overlap.'
                a[k]=anchor(p,vis,u,q,why,False,vp);continue
            if n==52 and k==NAMES[1]:why='Fixed outer10 extends beyond the captured native image; no point inferred.'
            a[k]=anchor(p,vis,o['uncertainty_native_px'],q,why,False,o.get('manually_read_view_xy'))
        for k,vp in zip((NAMES[0],NAMES[2],NAMES[3],NAMES[4]),NEW_POINTS[n]):
            p=pnative(vp,d);vis='visible';uv=3.;why='Fixed printed identity center read visually in the raw ID-only face crop.'
            if k==NAMES[3] and 1<=n<=24:
                vis='partial';uv=4.;why='Part of static basketball logo is crossed by the thin needle; remaining circular contour/pattern supports a deliberately uncertain center.'
            if k==NAMES[4] and (1<=n<=12 or 19<=n<=30):
                vis='partial';uv=4.;why='Counterweight covers part of the static soccer logo; visible circle/pattern remains. No needle direction used to choose the center.'
            if n in {3,6,9,12,15,18,21,24,27,30,33,36,39,42,45,48}:uv=max(uv,4.)
            if n in {52,56,57,58,59}:uv=5.;vis='partial';why='Identity is visible but blur, nearby tool, or partial clipping increases visual localization uncertainty.'
            if n in {54,55} and k==NAMES[3]:
                uv=7.;vis='partial';why='Only the orange basketball internal mark and part of its outline remain through overexposure; weak visual center retained with large uncertainty, not a complete reference.'
            if vp is None:
                vis='unknown';why='Printed identity cannot be reliably localized; no center reconstructed from gauge layout.'
                if n in {49,50,51}:why='No specified front printed gauge: background, external football, or reverse metal face. External ball is not the printed soccer identity.'
                elif (13<=n<=18 and k==NAMES[4]) or (n in {56,57} and k in (NAMES[3],NAMES[4])) or (n==58 and k==NAMES[0]):
                    vis='occluded';why='Needle/counterweight/tool masks this printed identity; no hidden center supplied.'
                elif n in {52,57,58,59} and k==NAMES[2]:
                    vis='occluded';why='Original burned-in HDMI OSD covers or confounds the outer15 word group; no hidden center supplied.'
                elif n==53:why='Severe defocus does not resolve this printed identity.'
                elif n in {54,55}:why='Severe overexposure does not resolve this printed identity.'
                u=None
            else:u=uv/min(d['view_transform']['scale_x'],d['view_transform']['scale_y'])
            a[k]=anchor(p,vis,u,q,why,False,vp)
        a={k:a[k] for k in NAMES}
        r={'id':id,'source_sha256':d['sha256'],'semantic_names_frozen':NAMES,'anchors':a,'roi_request':q,
           'annotation_kind':'AI visual per-identity information diagnostic; non-blind, not human gold or automatic runtime output',
           'point_selection_used_pressure_or_predictions':False,'old_overall_accepted_is_not_point_visibility':True,
           'no_hidden_center_or_zero_pose_filled':True,'no_G_templates_or_training':True,
           'prior_results_seen':True,'ready_as_training_label':False,
           'points_native_available':sum(x['native_xy'] is not None for x in a.values()),
           'points_ROI_available':sum(x['within_roi_pixel_center_bounds'] for x in a.values()),
           'display_provenance':{k:d[k] for k in ('native_crop_xyxy','view_transform','clean_view_sha256')}}
        out.append(r)
        im=cv2.imdecode(np.fromfile(d['clean_view'],np.uint8),1)
        for j,(key,ap) in enumerate(a.items()):
            vp=ap['manually_read_view_xy']
            if vp is not None:
                vv=tuple(round(v) for v in vp);color=(40,145,35) if ap['visibility']=='visible' else (15,145,220)
                cv2.drawMarker(im,vv,color,cv2.MARKER_CROSS,10,1,cv2.LINE_AA)
                cv2.putText(im,str(j+1),(vv[0]+5,vv[1]-4),cv2.FONT_HERSHEY_SIMPLEX,.38,color,1,cv2.LINE_AA)
        cv2.imencode('.png',im)[1].tofile(str(BASE/'review_views'/f'{id}.png'))
        tile=np.full((414,384,3),255,np.uint8);tile[30:]=im
        cv2.putText(tile,f'{id}: {r["points_native_available"]}/6 visible evidence',(8,22),cv2.FONT_HERSHEY_SIMPLEX,.52,(20,30,40),1,cv2.LINE_AA)
        tiles.append(tile)
    target=BASE/'print_annotations.jsonl'
    target.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in out),'utf-8')
    for start in range(0,59,9):
        page=np.full((1242,1152,3),255,np.uint8)
        for j,t in enumerate(tiles[start:start+9]):
            yy,xx=divmod(j,3);page[yy*414:(yy+1)*414,xx*384:(xx+1)*384]=t
        cv2.imencode('.png',page)[1].tofile(str(BASE/f'review_contact_{start//9+1:02d}.png'))
    count={}
    for k in NAMES:
        count[k]={v:sum(r['anchors'][k]['visibility']==v for r in out) for v in ('visible','partial','unknown','occluded')}
    complete={'status':'COMPLETE_SIX_IDENTITY_AI_VISUAL_DIAGNOSTIC_NOT_GOLD','G_images':59,
        'point_identity_count':6,'G_point_denominator':354,'per_identity_visibility':count,
        'points_native_available':sum(r['points_native_available'] for r in out),
        'points_ROI_available':sum(r['points_ROI_available'] for r in out),
        'G_with_at_least_3_points':sum(r['points_ROI_available']>=3 for r in out),
        'label_pressure_NN_pose_results_used':False,'G_used_as_template_or_training':False,
        'canonical_originals_old_annotations_modified':False,'H_or_ABC_accessed':False,
        'prior_result_exposure_disclosed':True,'annotation_sha256':sha(target),
        'reference_sha256':{p.name:sha(p) for p in [BASE/'reference_D002.json',BASE/'reference_D025.json']},
        'limitations':['AI visual diagnostic sidecars, not blind human gold or calibrated uncertainty.',
                       'Partial points only estimate visible printed contours, never wholly hidden centers.',
                       'Outer5/10/15 mean complete distinct text identities; external football is never printed soccer.',
                       'Original peripheral/burned-in OSD is retained and can obscure an identity.',
                       'No full pose, automatic detection, pressure prediction, or board validation implied.']}
    save(BASE/'completion.json',complete);print(json.dumps(complete,ensure_ascii=False,indent=2))

if __name__=='__main__':
    (BASE/'review_views').mkdir(exist_ok=True)
    main()
