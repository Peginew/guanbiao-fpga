"""Minimal coordinate/roll handling check; no optimizer or H inputs."""
from pathlib import Path
import ast
import hashlib
import importlib.util
import json
import math
import cv2
import numpy as np

HERE=Path(__file__).resolve().parent;TASK=HERE.parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def module(name,p):
    s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def main():
    v2=module('rollreview_v2',TASK/'train_grouped_v2.py');v3=module('rollreview_v3',TASK/'train_grouped_v3.py')
    adapter=module('rollreview_roi',TASK/'roi_adapter.py');checks=[]
    def check(ok,name):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    a=ast.parse((TASK/'train_grouped_v2.py').read_text('utf-8'));b=ast.parse((TASK/'train_grouped_v3.py').read_text('utf-8'))
    for name in ('angle','angular','evaluate','build_items','heat_from_points'):
        aa=next(n for n in a.body if isinstance(n,ast.FunctionDef) and n.name==name);bb=next(n for n in b.body if isinstance(n,ast.FunctionDef) and n.name==name)
        check(ast.dump(aa,include_attributes=False)==ast.dump(bb,include_attributes=False),'unchanged_'+name)
    records=adapter.load_prepared(TASK/'prepared_train.jsonl')+adapter.load_prepared(TASK/'prepared_validation.jsonl')
    angle_residual=[]
    for ident in ('D_001','D_005','G_006'):
        r=next(r for r in records if r['id']==ident)
        native=np.array([r['keypoints'][k]['xy'] for k in ('hub','thin_terminal')]);roi=np.array([r['roi_keypoints'][k]['xy'] for k in ('hub','thin_terminal')])
        error=v3.angular(v3.angle(native),v3.angle(roi));angle_residual.append(error)
        check(error<1e-10,ident+'_ROI_preserves_actual_captured_direction')
    points=[[63.5,63.5],[95.5,85.5]];im=np.full((128,128),32,np.uint8);im[85:88,95:98]=240
    item=dict(image=im,points=points,sigmas=[1.25,1.25],mask=np.ones(2,np.float32))
    r1=np.random.default_rng(81102);r2=np.random.default_rng(81102)
    for i in range(20):
        old=v2.augment(r1,item);new=v3.augment(r2,item)
        check(all(np.array_equal(x,y) for x,y in zip(old,new)),f'default_augmentation_bit_exact_{i}')
    class TracedRNG:
        def __init__(self,seed):self.rng=np.random.default_rng(seed);self.draws=[]
        def uniform(self,*args,**kwargs):
            x=self.rng.uniform(*args,**kwargs);self.draws.append(x);return x
        def random(self):return 1.
    max_angle=0.;max_image_alignment=0.
    for theta in (-90.,-30.,-8.,0.,8.,30.,90.):
        rng=TracedRNG(20261102);image,heat,mask=v3.augment(rng,item,(theta,theta))
        m=cv2.getRotationMatrix2D((63.5,63.5),rng.draws[0],rng.draws[1]);m[:,2]+=rng.draws[2]
        p=np.c_[points,np.ones(2)]@m.T
        error=v3.angular(v3.angle(p),v3.angle(points)-theta);max_angle=max(max_angle,error)
        check(error<1e-10,f'opencv_CCW_to_image_clockwise_{theta}')
        for k in range(2):
            yy,xx=np.unravel_index(heat[k].argmax(),heat[k].shape)
            check(np.linalg.norm(np.array([xx,yy])*2-p[k])<=math.sqrt(2)+1e-5,f'same_affine_heatmap_point_{theta}_{k}')
        yy,xx=np.unravel_index(image[0].argmax(),(128,128));err=float(np.linalg.norm([xx-p[1][0],yy-p[1][1]]));max_image_alignment=max(max_image_alignment,err)
        check(err<2.5,f'same_affine_image_dot_{theta}')
    pose=read(TASK/'pose/roll_audit_summary.json')
    check(pose['reference']['absolute_upright_verified'] is False and pose['H_opened'] is False,'relative_print_registration_not_absolute_roll_or_H')
    report=dict(status='PASS_ROLL_HANDLING_TOOL_REVIEW_NO_NEW_TRAINING',checks=len(checks),failures=[],
        trainer_v3_sha256=sha(TASK/'train_grouped_v3.py'),prepared_train_sha256=sha(TASK/'prepared_train.jsonl'),prepared_validation_sha256=sha(TASK/'prepared_validation.jsonl'),
        pose_audit_sha256=sha(TASK/'pose/roll_audit_summary.json'),native_ROI_direction_examples=['D_001','D_005','G_006'],
        maximum_actual_native_to_ROI_angle_change_deg=max(angle_residual),synthetic_maximum_rotation_convention_error_deg=max_angle,
        synthetic_maximum_dot_to_mapped_point_distance_roi=max_image_alignment,default_v3_vs_v2_bitexact_augmentations=20,
        default_roll_augmentation_opencv_deg=[-8,8],roll_range_for_next_training_selected=False,
        reference_convention='Image right=0, clockwise positive. OpenCV positive rotation is displayed CCW: transformed image needle angle=original−theta.',
        original_capture_roll='Preserved in original pixel coordinates and native keypoints. No implicit upright normalization or pressure-based label rotation.',
        validation='Original G image geometry, each prediction compared to that image visual native/ROI endpoint direction; no upright zero-roll assumption.',
        pose_evidence='Static printed-feature homography/polar rotation relative to D002; direct needle points only exclude dynamic features. Does not use pressure or needle angle as roll value.',
        boundaries=['Image roll differs from yaw/sideview; affine roll augmentation is not perspective supervision',
                    'Needle direction in image does not establish bar value; pressure calibration requires printed scale reference and roll handling',
                    'run002 mean43deg angular residual already compares each image own direction, so cannot be wholly attributed to photographed dial roll'],
        optimizer_steps=0,run003_started=False,test_H_opened=False,hardware_actions=False)
    (HERE/'roll_handling_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
