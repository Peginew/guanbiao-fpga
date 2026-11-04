"""Freeze this offline diagnostic and update its own current entry only."""
from pathlib import Path
import json,hashlib

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')


def main():
    s=load(HERE/'results/comparison_summary.json');r=load(HERE/'review/supervision_review.json')
    assert r['status']=='PASS_OFFLINE_CONTROL_REPLAY_NO_AUTOMATIC_READER_ADOPTION'
    assert s['total_G_images']==59 and s['visual_reference_available_G_count']==46
    expected={'oldref_oldcal':(21,21),'visualref_oldcal':(27,24),'oldref_newcal':(23,19),'visualref_newcal':(29,23)}
    for name,(count,within) in expected.items():
        q=s['variants'][name]['summary']
        assert q['valid_readings']==count and q['output_error_distribution_psi']['within_0_5_psi']==within
    frozen={
        'algorithm_work/meter_cnn_training_20261102/run_002/best_weights.pt':'c221678efa4762bed298828b2e8e8ba3c2a6b343c2c16efe35aec77a85c896df',
        'algorithm_work/meter_pointer_readout_20261102/polar_angle/run_001/best_weights.pt':'d139ecdc1059829be18e23eaf5d503d5c9d59a798d2986774441f88cc1804882',
        'algorithm_work/meter_dataset_annotation_20261102/annotations.json':'cb977f2b8f1b1324993982f9947314ae9a130c055cdcf90f65b5081d4ad22b7e'}
    for path,value in frozen.items():assert sha(ROOT/path)==value,path
    # Bind all direct controls and both annotation/export contracts.
    files=['task_contract.json','run_controls.py','analyze_findings.py','freeze_results.py','结果说明.txt',
        'annotations_train/print_annotations.jsonl','annotations_train/completion.json','annotations_train/reference_D002.json',
        'annotations_train/export_annotations.py','annotations_train/view_manifest.json',
        'annotations_g/print_annotations.jsonl','annotations_g/completion.json','annotations_g/reference_D002.json',
        'results/comparison_summary.json','results/findings.json','results/reference_D002.json',
        'results/visual_print_poses.jsonl','results/new_calibration_psi.json',
        'results/matched_old_calibration_psi.json','results/matched_visual_calibration_psi.json',
        'results/逐图四格与共同标定对照.csv','review/supervision_review.json','review/independent_controls.py',
        'build_comparison.py','comparison/index.html','comparison/build_receipt.json',
        'comparison/per_image_psi_controls.csv','comparison/summary_psi_controls.csv']
    files.extend('results/'+name+'.json' for name in s['variants'])
    bindings={name:sha(HERE/name) for name in files}
    view=load(HERE/'comparison/build_receipt.json')
    assert view['status']=='PASS_STANDALONE_VIEW_AND_ACTUAL_RENDER_QA'
    assert view['outputs_sha256']['comparison\\index.html']==sha(HERE/'comparison/index.html')
    primary={name:s['variants'][name]['summary'] for name in expected}
    result=dict(status='COMPLETED_CONDITIONAL_PRINT_REFERENCE_DIAGNOSTIC_NO_AUTOMATIC_READER_ADOPTION',
        date_local='2026-11-02',primary_unit='psi',request='Reliable printed reference + existing hub/needle + independent calibration controls',
        roles=dict(root='Frozen controls and calibration',training_adapter='Train48 visual annotations',roi_adapter='G59 visual annotations and comparison view',training_review='Independent supervision'),
        annotations=dict(train_images=48,train_reference_available=44,G_images=59,G_reference_available=46,certified_gold=False),
        calibration=dict(new_train_measurements=43,matched_train_measurements=31,source_groups=['D','E','F'],G_fitted=False),
        primary_four_cells=primary,old_neural_and_calibration_unchanged=True,
        conclusions=['Visible static-print reference recovers some correct outputs, but fixed two-point visibility loses prior correct outputs.',
            'New calibration does not show robust net advantage; maintain old calibration.',
            'In descriptive0.5psi band frontal correct count remains9/16; basic frontal robustness is unresolved.',
            'These are native-image AI visual reference diagnostics, not automated128ROI inference or board results.'],
        main_error_bands_psi=[.25,.5,1.],user_final_error_tolerance_set=False,
        network_architecture_frozen=False,new_weights=False,new_deployment_cost_claim=False,
        evidence=dict(offline_execution='PASS',independent_replay_checks=r['checks'],automatic_reader_replacement='NOT_ADMITTED',
            new_model_training='NOT_PERFORMED',integer_or_RTL_port='OUT_OF_SCOPE',board_or_MCU_or_Flash='NOT_PERFORMED'),
        H_or_ABC_used=False,originals_or_canonical_modified=False,concurrent_UI_or_REF_modified=False,
        next='Effect first: redundant identified printed landmarks with visibility, retain already reliable old reference, and establish frontal correct-reading gain before freezing a network or deployment budget.',
        frozen_baseline_sha256=frozen,files_sha256=bindings)
    write(HERE/'completion.json',result)
    pointer=dict(status=result['status'],date_local='2026-11-02',primary_unit='psi',task=str(HERE),
        completion=str(HERE/'completion.json'),completion_sha256=sha(HERE/'completion.json'),
        comparison=str(HERE/'comparison/index.html'),note=str(HERE/'结果说明.txt'),
        baseline_readings=21,visual_reference_old_cal_readings=27,visual_reference_new_cal_readings=29,
        correct_in_descriptive_half_psi_band=dict(baseline=21,visual_oldcal=24,visual_newcal=23),
        frontal_correct_in_descriptive_half_psi_band=dict(baseline=9,visual_oldcal=9,denominator=16),
        new_reference_or_calibration_adopted=False,automatic_inference_demonstrated=False,new_network_or_bit=False,
        H_used=False,hardware_actions=False,next=result['next'])
    write(ROOT/'hardware/current_meter_print_reference_control.json',pointer)
    previous=ROOT/'hardware/current_meter_reference_readout.json';p=load(previous)
    p.setdefault('prior_next_before_print_reference_control',p.get('next'))
    p['latest_print_reference_control']=dict(pointer='hardware/current_meter_print_reference_control.json',
        completion=str(HERE/'completion.json'),completion_sha256=sha(HERE/'completion.json'),
        replaces_original_neural_or_calibration=False,automatic_reader_admitted=False)
    p['latest_user_priority']='PC reading effect and correct coverage before full MCU deployment'
    p['next']=result['next'];write(previous,p)
    print(result['status'],sha(HERE/'completion.json'),'bindings',len(bindings))


if __name__=='__main__':main()
