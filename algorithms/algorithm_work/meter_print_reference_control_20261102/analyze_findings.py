"""Interpret the frozen controls without selecting thresholds or new policies."""
from pathlib import Path
import json
from run_controls import load,write,HERE,BANDS


def main():
    s=load(HERE/'results/comparison_summary.json');v=s['variants']
    old=v['oldref_oldcal'];printed=v['visualref_oldcal'];joint=v['visualref_newcal']
    front=('front_medium_soft_light','front_large_soft_light')
    def frontal(q):
        b=q['summary']['by_scene']
        return dict(images=sum(b[x]['gauges'] for x in front),outputs=sum(b[x]['valid'] for x in front),
            descriptive_correct_outputs={str(t):sum(b[x]['within_bands_psi'][str(t)] for x in front) for t in BANDS})
    references=[json.loads(x) for x in (HERE/'annotations_g/print_annotations.jsonl').read_text('utf-8').splitlines()]
    missing=[dict(id=r['id'],reason=r['reason']) for r in references if not r['accepted']]
    oldv=old['same_visual_available_subset_summary'];newv=printed['same_visual_available_subset_summary']
    report=dict(
        status='CONDITIONAL_VISUAL_REFERENCE_BENEFIT_NO_AUTOMATIC_REPLACEMENT_ADMISSION',unit='psi',
        primary_decision='Keep frozen original neural models and calibration; do not adopt this two-anchor reference as an automatic reader',
        observed_reference_value=dict(full56=dict(baseline_outputs=old['summary']['valid_readings'],
            visual_reference_outputs=printed['summary']['valid_readings'],
            baseline_correct_in_descriptive_half_psi_band=old['summary']['descriptive_correct_output_coverage']['0.5']['correct_outputs'],
            visual_correct_in_descriptive_half_psi_band=printed['summary']['descriptive_correct_output_coverage']['0.5']['correct_outputs']),
            same_visual_available_subset=dict(gauge_denominator=oldv['gauge_images'],old_outputs=oldv['valid_readings'],
                visual_outputs=newv['valid_readings'],old_MAE_psi=oldv['reading_mae_psi'],visual_MAE_psi=newv['reading_mae_psi']),
            newly_output_ids=printed['changes']['new_output_ids'],withdrawn_old_output_ids=printed['changes']['withdrawn_output_ids'],
            band_changes=printed['changes']['bands']),
        frontal_baseline=frontal(old),frontal_visual_with_old_calibration=frontal(printed),
        new_calibration_not_recommended=True,
        new_calibration_evidence=dict(
            old_reference_frozen_calibration=old['summary']['reading_mae_psi'],
            old_reference_new_calibration=v['oldref_newcal']['summary']['reading_mae_psi'],
            visual_reference_frozen_calibration=printed['summary']['reading_mae_psi'],
            visual_reference_new_calibration=joint['summary']['reading_mae_psi'],
            matched_train_observations=s['common_calibration_observations'],
            matched_visual_with_oldcal_correct_half_psi=v['matched_visualref_oldcal']['summary']['descriptive_correct_output_coverage']['0.5']['correct_outputs'],
            matched_visual_with_newcal_correct_half_psi=v['matched_visualref_newcal']['summary']['descriptive_correct_output_coverage']['0.5']['correct_outputs']),
        fixed_anchor_missingness=missing,
        conclusions=[
            'Reliable static reference evidence can recover some correct readings; this is an annotation-assisted diagnostic, not an automatic model gain.',
            'Using only these two fixed structures loses observations when the pointer/counterweight covers one; that does not imply no other static structure is visible.',
            'New calibration has no demonstrated robust net advantage in MAE and larger-error outputs, including common-training-observation controls; some finer-band counts improve, so not every metric uniformly worsens.',
            'Frontal correct output count in the descriptive0.5psi band remains9/16, so the basic frontal goal is not solved.',
            'Reference replacement changes both pose value and pose availability; old ring-specific gates are not silently claimed preserved.',
            'Remaining PSI errors may involve hub/needle geometry, projection, labels and reference uncertainty; this experiment does not identify a unique cause.'
        ],
        next_scope='Before model/deployment selection: design a redundant identified-print landmark observation and uncertainty contract, preserving old reference when new evidence is absent; verify its effect separately. Do not train the failed scalar-roll classifier again.',
        not_authorized_by_this_receipt=['New training','New hardware/MCU/Flash changes','H test evaluation'],
        no_threshold_or_label_optimization=True,new_neural_architecture_frozen=False,
        model_deployment_cost_claim=False,hardware_actions=False,
        descriptive_half_psi_band_is_user_final_target=False)
    write(HERE/'results/findings.json',report)
    print(report['status'],report['frontal_baseline'],report['frontal_visual_with_old_calibration'])


if __name__=='__main__':main()
