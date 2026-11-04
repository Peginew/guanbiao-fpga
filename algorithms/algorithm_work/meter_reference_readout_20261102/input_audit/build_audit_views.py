"""Create reproducible24 native/ROI review panels, no training/data mutation.

Only D/E/F/G opened. Historical raw dumps are inspected as transfer evidence,
never made into current training examples. No device calls.
"""
from pathlib import Path
import sys,json,hashlib
import cv2
import numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
DATA=ROOT/'algorithm_work/meter_cnn_training_20261102'
sys.path.insert(0,str(DATA));import roi_adapter as roi
IDS=['D_002','D_004','D_015','D_022','D_041','D_056','E_002','E_009','E_018','E_028','E_040','E_053','F_003','F_010','F_025','F_033','F_045','F_056','G_001','G_004','G_015','G_018','G_040','G_056']

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf-8')
def save(p,im):Path(p).parent.mkdir(parents=True,exist_ok=True);ok,b=cv2.imencode('.png',im);assert ok;Path(p).write_bytes(b.tobytes())

def main():
    rr=roi.load_prepared(DATA/'prepared_train.jsonl')+roi.load_prepared(DATA/'prepared_validation.jsonl');records={r['id']:r for r in rr}
    poses={r['id']:r for n in ['train_print_pose.jsonl','validation_print_pose.jsonl']for r in roi.read_jsonl(ROOT/'algorithm_work/meter_pointer_readout_20261102/readout'/n)}
    out=[];tiles={g:[]for g in'DEFG'}
    for ident in IDS:
        r=records[ident];assert sha(r['path'])==r['sha256'];im=roi.read_native(r);gray=roi.read_roi(r)
        box=r['bbox_native_xyxy'];d=max(box[2]-box[0],box[3]-box[1])*1.12;cx=(box[0]+box[2])/2;cy=(box[1]+box[3])/2
        scale=512/d;A=np.array([[scale,0,256-cx*scale],[0,scale,256-cy*scale]],np.float64)
        native=cv2.warpAffine(im,A,(512,512),flags=cv2.INTER_LINEAR,borderValue=(40,40,40))
        patch=cv2.cvtColor(cv2.resize(gray,(512,512),interpolation=cv2.INTER_NEAREST),cv2.COLOR_GRAY2BGR)
        raw=np.full((560,1024,3),18,np.uint8);raw[:512,:512]=native;raw[:512,512:]=patch
        cv2.putText(raw,f'{ident} native face context | ROI128 hardware-shaped proxy', (7,534),cv2.FONT_HERSHEY_SIMPLEX,.65,(240,240,240),1)
        cv2.putText(raw,r['scene']['primary'],(7,554),cv2.FONT_HERSHEY_SIMPLEX,.45,(210,210,210),1)
        save(HERE/'views'/f'{ident}_native_roi.png',raw)
        marked=raw.copy()
        for i,key in enumerate(roi.HEADS):
            a=r['keypoints'][key];p=a.get('xy')
            if p is None:continue
            xy=np.asarray(p)*scale+A[:,2];color=(0,255,0)if i==0 else(0,0,255)
            cv2.drawMarker(marked,tuple(np.rint(xy).astype(int)),color,cv2.MARKER_CROSS,15,1)
            rp=r['roi_keypoints'][key]['xy']
            if rp is not None and r['roi_keypoints'][key]['inside_roi']:
                cv2.drawMarker(marked,tuple(np.rint(np.asarray(rp)*4+[512,0]).astype(int)),color,cv2.MARKER_CROSS,15,1)
        save(HERE/'views'/f'{ident}_mapped_labels.png',marked)
        grid=np.full((570,570,3),20,np.uint8);grid[40:552,40:552]=patch
        for v in range(0,129,8):
            x=40+4*v;y=40+4*v
            cv2.line(grid,(x,40),(x,552),(70,70,70),1);cv2.line(grid,(40,y),(552,y),(70,70,70),1)
            cv2.putText(grid,str(v),(max(0,x-9),29),cv2.FONT_HERSHEY_SIMPLEX,.38,(255,255,255),1)
            cv2.putText(grid,str(v),(5,min(566,y+4)),cv2.FONT_HERSHEY_SIMPLEX,.38,(255,255,255),1)
        save(HERE/'views'/f'{ident}_ROI_grid.png',grid)
        tiles[ident[0]].append(cv2.resize(marked,(640,350),interpolation=cv2.INTER_AREA))
        out.append(dict(id=ident,split=r['split'],source_path=r['path'],source_sha256=r['sha256'],scene=r['scene'],
            bbox_native_xyxy=r['bbox_native_xyxy'],roi_request=r['roi_request'],keypoints=r['keypoints'],roi_keypoints=r['roi_keypoints'],loss_mask=r['loss_mask'],
            native_SIFT_silver=poses[ident],native_view_affine=A.tolist(),ROI_pixels_sha256=hashlib.sha256(gray.tobytes()).hexdigest(),
            source_OSD_overlap=r['roi_preprocessing']['OSD_overlap_regions']))
    for group,panels in tiles.items():
        canvas=np.full((350*3,640*2,3),15,np.uint8)
        for i,p in enumerate(panels):y,x=divmod(i,2);canvas[y*350:(y+1)*350,x*640:(x+1)*640]=p
        save(HERE/f'{group}_native_ROI_contact.png',canvas)
    (HERE/'selected_records.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n'for r in out),'utf-8')
    board=Path('C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/board');dumps=[]
    for p in sorted(board.glob('live_snapshot_*/snapshot.raw')):
        a=np.frombuffer(p.read_bytes(),np.uint8);result=json.loads((p.parent/'result.json').read_text('utf-8'))
        dumps.append(dict(path=str(p),sha256=sha(p),bytes=len(a),unique_byte_values=len(np.unique(a)),minimum=int(a.min()),maximum=int(a.max()),
            snapshot_transport_passed=result.get('snapshot_transport_passed'),words=result.get('diagnostics',{}).get('words'),
            generation=result.get('bridge_readonly',{}).get('GENERATION'),usable_as_actual_camera_ROI=False,
            training_use=False,reason='Allzero buffer withfailedcapture/zero completedwords; not a valid camera sample',receipt=str(p.parent/'result.json'),receipt_sha256=sha(p.parent/'result.json')))
    write(HERE/'existing_board_dump_inventory.json',dict(status='NO_VALID_ACTUAL_BOARD_CAMERA_ROI_FOUND_IN_KNOWN_DUMPS',known_board_dumps=dumps,
        current_dataset_has_same_source_boardROI_pair=False,scope='Known board/raw and currentdataset paths; finite search not an assertion about every disk file',
        simulator_ROIs_exist_but_are_not_board_dumps=True,old_assets_used_for_current_training=False,H_or_ABC_opened=False,hardware_actions=False))
    write(HERE/'view_build_receipt.json',dict(status='24_AUDIT_PANELS_BUILT_PENDING_VISUAL_REVIEW',ids=IDS,images_opened=24,
        source_records_sha256=sha(HERE/'selected_records.jsonl'),script_sha256=sha(__file__),canonical_changed=False,training_executed=False,H_or_ABC_opened=False,hardware_actions=False))
    print('Built24native/ROI/label/grid views anddumpinventory')

if __name__=='__main__':main()
