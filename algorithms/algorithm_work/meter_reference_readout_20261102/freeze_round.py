"""Bind completed offline work and append its pointer; never contacts hardware."""
from pathlib import Path
from datetime import datetime
import hashlib,json

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]


def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')


def main():
    decision=load(HERE/'selection_decision.json')
    assert decision['status']=='REJECT_NEW_REFERENCE_CNN_KEEP_ORIGINAL_2211_PLUS_MULTI_RING'
    chain=load(HERE/'integer_pose/c_pixel_chain_verification.json')
    assert chain['status']=='PASS_C_PIXEL_PROFILE_MATCHER_FROZEN_PSI_OUTPUTS'
    assert chain['counts']['ROIs']==223 and not chain['pressure_output_changes']
    assert chain['PSI']['valid_readings']==21 and abs(chain['PSI']['reading_mae_psi']-.15740682142050108)<1e-12
    review=load(HERE/'review/supervision_review.json')
    assert review['status']=='EXECUTION_REPLAY_PASS_CANDIDATE_FAIL_KEEP_BASELINE'
    checks={
        'algorithm_work/meter_cnn_training_20261102/run_002/best_weights.pt':'c221678efa4762bed298828b2e8e8ba3c2a6b343c2c16efe35aec77a85c896df',
        'algorithm_work/meter_pointer_readout_20261102/polar_angle/run_001/best_weights.pt':'d139ecdc1059829be18e23eaf5d503d5c9d59a798d2986774441f88cc1804882',
        'algorithm_work/meter_dataset_annotation_20261102/annotations.json':'cb977f2b8f1b1324993982f9947314ae9a130c055cdcf90f65b5081d4ad22b7e'}
    for name,expected in checks.items():assert sha(ROOT/name)==expected,name
    files=['task_contract.json','candidate_config_before_training.json','candidate_preflight.json','reference_candidate.py',
        'reference_cnn/run_001/config.json','reference_cnn/run_001/training_receipt.json','reference_cnn/run_001/best_weights.pt',
        'reference_cnn/run_001/candidate_pose.jsonl','reference_cnn/run_001/readout_psi.json',
        'reference_cnn/run_001/new_reference_old_calibration.json','reference_cnn/run_001/old_reference_new_calibration.json',
        'selection_decision.json','finalize_comparison.py','comparison/index.html','comparison/逐图对照.csv',
        'input_audit/completion.json','input_audit/input_domain_contract.json','input_audit/visual_review_24.json',
        'input_audit/static_print_direction_sidecar.jsonl','diagnostics/completion.json','diagnostics/run_003/findings.json',
        'cost/static_roll_cost.json','integer_pose/meter_pose_matcher.c','integer_pose/meter_pose_matcher.h',
        'integer_pose/meter_pose_frontend.c','integer_pose/meter_pose_frontend.h','integer_pose/pose_frontend.py',
        'integer_pose/core_completion.json','integer_pose/frontend_core_completion.json',
        'integer_pose/fixtures/manifest.json','integer_pose/frontend_fixture_manifest.json',
        'integer_pose/c_matcher_verification.json','integer_pose/frontend_verification.json',
        'integer_pose/integer_pixel_match_chain_receipt.json','integer_pose/c_pixel_chain_verification.json',
        'integer_pose/host_test_receipt.json','integer_pose/host_frontend_test_receipt.json',
        'integer_pose/rv32_build/rv32_object_receipt.json','integer_pose/rv32_build/rv32_frontend_object_receipt.json',
        'review/supervision_review.json','review/integer_matcher_review.json','review/integer_frontend_review.json',
        '本轮结果与后续入口.txt']
    bindings={name:sha(HERE/name) for name in files}
    frontreview=load(HERE/'review/integer_frontend_review.json')
    # The independent review states its actual partial scope, not MCU acceptance.
    completion=dict(status='OFFLINE_ROUND_COMPLETE_NEW_CNN_REJECTED_RETAINED_POSE_C_OPERATORS_VERIFIED',
        date_local='2026-11-02',primary_unit='psi',scope='Bounded diagnostics and model comparison; selected old pose C-operator implementation',
        implemented=['24-image bounded visual/input-domain audit','Joint overlapping rejection decomposition',
            'One6226-parameter reference-CNN run rejected on actual final PSI results',
            'C99 integer normalization, Q5 bilinear, rational profile and trimmed annular matcher',
            'ActualRV32IMAC relocatable objects and frozen223-input operator/readout replay'],
        selected='Original1202hub+1009polar+multi-reference ringB; weights unchanged',
        selected_development_summary=chain['PSI'],rejected_candidate_summary=decision['candidate'],
        rejected_candidate_deployed=False,baseline_sha256_unchanged=checks,
        evidence_levels=dict(PC='PASS_BOUNDED_EXECUTION_AND_SELECTED_C_OUTPUT_PRESERVATION',
            new_reference_CNN='FAIL_NOT_ADOPTED',C_integer_pixel_profile_matcher='PASS_FROZEN_SOURCES_AND_COORDINATE_INPUTS',
            full_integer_geometry='PENDING',full_neural_and_PSI_C_chain='PENDING',whole_MCU_link='PENDING',
            real_MCU_cycles='PENDING',paired_real_camera_ROI_domain='PENDING',new_board_deployment='NOT_PERFORMED'),
        current_TCM_static_gap_bytes=1404,TCM_capacity_bytes=49152,
        H_test_used=False,ABC_reserve_used=False,canonical_changed=False,old_weights_changed=False,
        board_actions=False,Flash_actions=False,MCU_firmware_modified=False,FPGA_or_OSD_or_REF_modified=False,
        need_user_new_capture_now=False,final_user_PSI_tolerance_set=False,
        next='Integer coordinate generation, lifetime-based shared workspace and actual48KiB whole-firmware linking before any new deployment',
        files_sha256=bindings)
    write(HERE/'completion.json',completion)
    pointer=dict(status=completion['status'],date_local='2026-11-02',primary_unit='psi',task=str(HERE),
        completion=str(HERE/'completion.json'),completion_sha256=sha(HERE/'completion.json'),
        selected='Frozen original2211-parameter neural pair plus multi-reference ringB',
        new_reference_CNN_adopted=False,development_readings=21,development_gauge_images=56,
        development_MAE_psi=.15740682142050108,independent_test=False,
        C_operator_chain_verified=True,full_MCU_firmware_ready=False,new_bit_ready=False,board_deployed=False,
        comparison=str(HERE/'comparison/index.html'),note=str(HERE/'本轮结果与后续入口.txt'),
        next=completion['next'])
    write(ROOT/'hardware/current_meter_reference_readout.json',pointer)
    # Append only; the prior selected baseline and its receipt remain intact.
    previous=ROOT/'hardware/current_meter_robust_readout.json';p=load(previous)
    p['latest_supervised_reference_development']=dict(pointer='hardware/current_meter_reference_readout.json',
        completion=str(HERE/'completion.json'),completion_sha256=sha(HERE/'completion.json'),
        new_reference_CNN_adopted=False,selected_old_networks_and_pose_unchanged=True,
        new_integer_C_operators=True,new_MCU_deployment=False)
    write(previous,p)
    print(completion['status'],sha(HERE/'completion.json'),'bindings',len(bindings))


if __name__=='__main__':main()
