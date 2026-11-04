"""Record actual visualreview + manual staticprint sidecar. No training.

Manual anchor estimates were read fromthe saved clean nativeface context
panels; neither printed-label pressure nor needle angle generated them.
They are approximate review aids, not independently certified posegroundtruth.
"""
from pathlib import Path
import json,hashlib,sys,math
import cv2,numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'algorithm_work/meter_cnn_training_20261102'));import roi_adapter as adapter
HW=Path('C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_reader_flash20e_20261101/project/user_source/hdl_source')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf-8')
def save(p,im):ok,b=cv2.imencode('.png',im);assert ok;Path(p).write_bytes(b.tobytes())

# Pixel estimates in the512px native-context panel, read visually. Eight long-
# baseline pairs; partially covered or washed-out logos intentionally notfilled.
MANUAL={
 'D_002':([227,95],[268,351],2.5),
 'E_002':([227,91],[271,349],2.5),
 'E_028':([235,90],[275,348],3.5),
 'E_040':([244,83],[272,344],3.5),
 'F_025':([241,91],[266,348],3.0),
 'G_001':([235,75],[249,338],3.0),
 'G_004':([258,70],[239,336],3.5),
 'G_040':([251,75],[245,335],3.5),
}

def main():
    selected=[json.loads(x)for x in(HERE/'selected_records.jsonl').read_text('utf-8').splitlines()];records={r['id']:r for r in selected}
    angles={k:math.degrees(math.atan2(top[1]-bottom[1],top[0]-bottom[0]))%360 for k,(top,bottom,_)in MANUAL.items()}
    side=[];tiles=[]
    for ident,(top,bottom,uncert)in MANUAL.items():
        r=records[ident];A=np.asarray(r['native_view_affine']);scale=A[0,0];points={}
        for key,p in [('outer_psi_10_text_centroid',top),('lower_striped_ball_print_centroid',bottom)]:
            native=(np.asarray(p)-A[:,2])/scale;rp=adapter.native_to_roi(native,r['roi_request'])
            points[key]=dict(view_xy=p,native_xy=native.tolist(),roi_xy=rp.tolist(),visibility='visible',manual_view_pick_uncertainty_px=3)
        relative=(angles[ident]-angles['D_002']+180)%360-180
        s=r['native_SIFT_silver'];difference=abs((relative-s['relative_roll_deg']+180)%360-180)if s['accepted']else None
        item=dict(id=ident,split=r['split'],source_sha256=r['source_sha256'],anchor_semantics='Top10printedtext andbottomstripedballprintedlogo; no mechanicalhub/needle/psi value used',
            anchors=points,reference_id='D_002',absolute_image_print_axis_angle_deg=angles[ident],
            relative_print_axis_angle_deg=relative,relative_direction_interval_deg=[relative-uncert,relative+uncert],
            estimated_uncertainty_deg=uncert,uncertainty_is_certified_error_bound=False,
            method='Manual visual reading ofclean originalnativeface panel, mapped toROI byknown crop math; noSIFTpointprojection/no pressure inversion',
            review_tier='lower_visual_uncertainty'if uncert<=2.5 else'moderate_visual_uncertainty',
            independently_human_certified_gold=False,review_was_not_blind_to_prior_silver_results=True,
            ready_as_training_ground_truth=False,use='Audit sidecar only; Gdevelopment only, nottraininglabels',
            native_registration_silver_agreement_diagnostic=dict(accepted=s['accepted'],silver_relative_deg=s.get('relative_roll_deg'),
                absolute_difference_deg=difference,comparison_is_not_accuracy_measurement=True))
        side.append(item)
        im=cv2.imdecode(np.frombuffer((HERE/'views'/f'{ident}_native_roi.png').read_bytes(),np.uint8),1)
        cv2.line(im,tuple(bottom),tuple(top),(255,255,0),2)
        for p in [top,bottom]:cv2.circle(im,tuple(p),5,(0,255,0),1)
        roi_points=[points[n]['roi_xy']for n in['outer_psi_10_text_centroid','lower_striped_ball_print_centroid']]
        a,b=[tuple(np.rint(np.asarray(v)*4+[512,0]).astype(int))for v in roi_points]
        cv2.line(im,b,a,(255,255,0),2)
        for pt in[a,b]:cv2.circle(im,pt,5,(0,255,0),1)
        cv2.putText(im,f'VISUAL refaxis {relative:+.1f}deg +/-{uncert:g} audit only',(10,510),cv2.FONT_HERSHEY_SIMPLEX,.55,(0,255,255),1)
        save(HERE/'views'/f'{ident}_manual_static_axis.png',im);tiles.append(cv2.resize(im,(640,350)))
    (HERE/'static_print_direction_sidecar.jsonl').write_text(''.join(json.dumps(s,ensure_ascii=False)+'\n'for s in side),'utf-8')
    canvas=np.full((350*4,640*2,3),15,np.uint8)
    for i,t in enumerate(tiles):y,x=divmod(i,2);canvas[y*350:(y+1)*350,x*640:(x+1)*640]=t
    save(HERE/'manual_static_axis_contact.png',canvas)
    weak={'D_015','F_003','F_010','F_033','F_045'}
    occluded={'D_056','F_056','G_056'}
    audit=[]
    for r in selected:
        ident=r['id'];status='VISIBLE_STATIC_PRINT_REFERENCE'
        note='Native andROI staticnumerals/ticklayout recognizable; no observed staticdirection sign reversal.'
        if ident in weak:status='WEAK_OR_PARTIAL_STATIC_PRINT';note='Darkness/local glare reducesprecise anchorvisibility; broaderstaticprint mayremain useful, no precise newpointforced.'
        if ident in occluded:status='PARTIAL_PRINT_WITH_EXTERNAL_OCCLUDER';note='Screwdriver maskscentralshaft/printaxis. Otherouterdigits remain; no forcedpair axislabel.'
        if ident=='E_053':status='INSUFFICIENT_STATIC_PRINT_OVEREXPOSED';note='Largearea saturation removesprintedstructure; no staticaxis fabricated.'
        if ident in{'E_009','E_018'}:note+=' Lowerstripedlogo partlycovered bycounterweight; twoanchorvisibility isnotCNNstartup condition.'
        audit.append(dict(id=ident,source_sha256=r['source_sha256'],scene=r['scene']['primary'],native_and_ROI_images_actually_viewed=True,
            static_reference_visibility=status,comment=note,original_keypoint_loss_mask=r['loss_mask'],
            mapping_visual_check='No mapping displacement foundinthis24sample; thisdoesnotcertify canonicalpointprecision',
            hub_visual_state='occluded'if ident in occluded else'unknown_overexposure'if ident=='E_053'else'visible_or_lowcontrast',
            thin_terminal_visual_state=r['keypoints']['thin_terminal']['visibility'],
            manual_static_direction_sidecar_available=ident in MANUAL))
    write(HERE/'visual_review_24.json',dict(status='24_NATIVE_AND_ROI_VISUAL_REVIEW_COMPLETE_NOT_GOLD_CERTIFICATION',records=audit,
        manual_axis_labels=len(side),train_manual_axis_labels=sum(s['split']=='train'for s in side),G_development_axis_labels=sum(s['split']=='validation'for s in side),
        no_fundamental_static_direction_sign_problem_seen=True,anchors_are_not_required_network_inputs=True,
        main_caveats=['Staticprint reference isapparent imageorientation, notabsolutegravity/yaw/pitch.','Highpressure counterweight canhide lowerprint anchor; do notforceuniformtwoanchorlabels.',
            'Silver homography/orientation isnotposegroundtruth; thisvisualcheck wasnotblinded.','Manual uncertainty isestimated, notindependentinstrumentmeasurement.','Model quality remainsdetermined byheldout direction/psioutputs; thisaudit doesnotupgrade failedCNN.'],
        canonical_changed=False,H_or_ABC_opened=False,training_executed=False,hardware_actions=False))
    sourcefiles=['isp/isp_top.v','t06/t06_native_bridge.v','t06/t06_video_filter.v','t06/t06_gray4_exact_dsp.v','design_top_wrapper.v','meter_pair/t06_meter_roi_capture_mcu.v','meter_pair/meter_roi_window_policy.v']
    write(HERE/'input_domain_contract.json',dict(status='SOURCE_STAGE_AND_SAMPLING_IDENTIFIED_ACTUAL_PAIRED_CAMERA_DOMAIN_PENDING',
        actual_pipeline='Demosaic -> AWB -> nativebridge/filter originalRGB andexactgray -> ownedblockmeanROI -> AHBMCU; displaymode/OSD downstream separate',
        gray_is_raw_sensor=False,gray_is_AWB_after_RGB_luma=True,gray_formula='(77R+150G+29B+128)>>8',
        gray4_unaffected_by_20_mode_and_SAT=True,gray4_before_MODE_motion_meter_OSD=True,
        screenshot_mode0_background='SameAWBafterRGB beforedisplayoverlay; not theoreticallya whollydifferentrawsensor domain',
        known_proxy_differences=['Annotatedfacebbox vsactualautolocatorwindow','OriginalHDMI PNGcontainsOSD boxes/text/logos, actualROIanalysisgraydoesnot',
            'HDMI/readoutphase/sourceframe correspondence absent','CapturecardRGB/YUVrange/gamma/compression effects notmeasured'],
        sampling='Capture acceptsstride1..4,parentchooses2/3/4;128squareblockmeans, xorigin4aligned,s3(*7282)>>16',
        coordinate_mapping='ROI=(native-origin-(stride-1)/2)/stride',
        current_dataset_paired_actual_boardROI_available=False,
        known_board_dumps='Seven16KiB allzero failedsnapshots; notvalidcameraROIs, notproofcameraimageblack',
        simulator_exports='ExistingAHBexports supportlogicalsamplearithmetic only, notphysicalcapturecardpixeldomain',
        old_images_or_zero_dumps_used_for_training=False,
        next_minimum='Ifboardvalidationlaterauthorized, exportoneownedROI+sameTsource/descriptor+correspondingmode0screenshot first; no immediatenewsample request inthisaudit',
        source_sha256={str(HW/n):sha(HW/n)for n in sourcefiles},H_or_ABC_opened=False,hardware_actions=False))
    names=['selected_records.jsonl','view_build_receipt.json','existing_board_dump_inventory.json','visual_review_24.json','static_print_direction_sidecar.jsonl','input_domain_contract.json','manual_static_axis_contact.png','build_audit_views.py','finish_audit.py']
    write(HERE/'completion.json',dict(status='INPUT_DOMAIN_AND24_SAMPLE_STATIC_REFERENCE_AUDIT_COMPLETE_NO_TRAINING',images_reviewed=24,
        manual_axis_sidecar_records=8,manual_train_records=5,manual_G_dev_records=3,
        actual_board_pixel_domain_equivalence_proven=False,current_static_direction_network_pass_claim=False,
        files_sha256={n:sha(HERE/n)for n in names},canonical_changed=False,H_or_ABC_opened=False,hardware_actions=False))
    print(json.dumps([(r['id'],round(r['relative_print_axis_angle_deg'],2),r['native_registration_silver_agreement_diagnostic']['absolute_difference_deg'])for r in side],indent=2))

if __name__=='__main__':main()
