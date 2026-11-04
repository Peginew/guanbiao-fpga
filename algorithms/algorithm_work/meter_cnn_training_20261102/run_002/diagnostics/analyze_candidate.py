"""Frozen float candidate diagnostics only; no optimizer or H/test access."""
from pathlib import Path
import json
import sys
import math
import numpy as np
import torch

RUN = Path(__file__).resolve().parents[1]
TASK = RUN.parent
sys.path.insert(0, str(TASK))
import train_grouped_v2 as trainer


def topk_tip(logits):
    logits = logits.astype(np.float64)
    prob = 1 / (1 + np.exp(-np.clip(logits, -40, 40)))
    available = np.ones((64, 64), bool)
    yy, xx = np.mgrid[:64, :64]
    result = []
    for rank in range(4):
        y, x = np.unravel_index(np.where(available, logits, -np.inf).argmax(), (64, 64))
        ya, xa = np.mgrid[max(0, y - 1):min(64, y + 2), max(0, x - 1):min(64, x + 2)]
        weight = prob[ya, xa]
        point = [float((weight * xa).sum() / weight.sum()) * 2, float((weight * ya).sum() / weight.sum()) * 2]
        result.append(dict(rank=rank + 1, xy_roi=point, sigmoid_peak=float(prob[y, x])))
        available[(xx - x) ** 2 + (yy - y) ** 2 <= 25] = False
    return result


def cohort(rows):
    full = [r for r in rows if 'angle_error_deg' in r]
    accepted = [r for r in full if r['evidence_accepted']]
    return dict(images=len(rows), hub_error_roi=trainer.stats([r['hub_error_roi'] for r in rows if 'hub_error_roi' in r]),
                tip_error_roi=trainer.stats([r['thin_terminal_error_roi'] for r in rows if 'thin_terminal_error_roi' in r]),
                angle_error_deg=trainer.stats([r['angle_error_deg'] for r in full]), full_point_labels=len(full),
                within5deg=sum(r['angle_error_deg'] <= 5 for r in full), within10deg=sum(r['angle_error_deg'] <= 10 for r in full),
                accepted=len(accepted), accepted_over10deg=sum(r['angle_error_deg'] > 10 for r in accepted))


def topk_summary(rows):
    full = [r for r in rows if 'candidate_angle_errors_using_predicted_hub' in r]
    return dict(full_point_labels=len(full),
                predicted_hub_top1_within5=sum(r['candidate_angle_errors_using_predicted_hub'][0] <= 5 for r in full),
                predicted_hub_top1_within10=sum(r['candidate_angle_errors_using_predicted_hub'][0] <= 10 for r in full),
                predicted_hub_top4_within5=sum(min(r['candidate_angle_errors_using_predicted_hub']) <= 5 for r in full),
                predicted_hub_top4_within10=sum(min(r['candidate_angle_errors_using_predicted_hub']) <= 10 for r in full),
                reference_hub_top1_within5=sum(r['candidate_angle_errors_using_reference_hub'][0] <= 5 for r in full),
                reference_hub_top1_within10=sum(r['candidate_angle_errors_using_reference_hub'][0] <= 10 for r in full),
                reference_hub_top4_within5=sum(min(r['candidate_angle_errors_using_reference_hub']) <= 5 for r in full),
                reference_hub_top4_within10=sum(min(r['candidate_angle_errors_using_reference_hub']) <= 10 for r in full),
                thin_terminal_top4_within4roi=sum(min(r['candidate_tip_errors_roi']) <= 4 for r in full),
                thin_terminal_top1_within4roi=sum(r['candidate_tip_errors_roi'][0] <= 4 for r in full))


def main():
    trainer.setup(1102, 4)
    adapter = trainer.get_adapter()
    model = trainer.Direct(4)
    model.load_state_dict(torch.load(RUN / 'best_weights.pt', weights_only=True)['state_dict'])
    model.eval()
    reports = {}
    for split, groups in [('train', {'D', 'E', 'F'}), ('validation', {'G'})]:
        records = adapter.load_prepared(TASK / ('prepared_' + split + '.jsonl'))
        if split == 'train':
            records = [r for r in records if r['active_for_initial_weight_updates']]
        items = trainer.build_items(records, adapter, groups, split)
        prepared = {r['id']: r for r in records}
        evaluation = json.loads((RUN / ('train_evaluation.json' if split == 'train' else 'validation_evaluation.json')).read_text('utf-8'))
        rows = {r['id']: r for r in evaluation['rows']}
        output_rows = []
        with torch.inference_mode():
            for start in range(0, len(items), 16):
                batch = items[start:start + 16]
                values = model(torch.from_numpy(np.stack([trainer.normalized(it['image']) for it in batch]))).numpy()
                for item, value in zip(batch, values):
                    r = dict(rows[item['id']])
                    r['condition'] = prepared[item['id']]['scene']['primary']
                    r['source_group'] = prepared[item['id']]['source_group']
                    r['observed_tags'] = prepared[item['id']]['scene'].get('observed_tags', [])
                    candidates = topk_tip(value[1])
                    r['tip_candidates'] = candidates
                    if all(item['mask']) and all(p is not None for p in item['points']):
                        reference_angle = trainer.angle(item['points'])
                        predicted_hub = r['predicted_points_roi'][0]
                        reference_hub = item['points'][0]
                        r['candidate_angle_errors_using_predicted_hub'] = [trainer.angular(trainer.angle([predicted_hub, c['xy_roi']]), reference_angle) for c in candidates]
                        r['candidate_angle_errors_using_reference_hub'] = [trainer.angular(trainer.angle([reference_hub, c['xy_roi']]), reference_angle) for c in candidates]
                        r['candidate_tip_errors_roi'] = [float(np.linalg.norm(np.asarray(c['xy_roi']) - item['points'][1])) for c in candidates]
                    output_rows.append(r)
        by_condition = {condition: cohort([r for r in output_rows if r['condition'] == condition]) for condition in sorted({r['condition'] for r in output_rows})}
        by_group = {group: cohort([r for r in output_rows if r['source_group'] == group]) for group in sorted(groups)}
        by_condition_topk = {condition: topk_summary([r for r in output_rows if r['condition'] == condition]) for condition in sorted({r['condition'] for r in output_rows})}
        reports[split] = dict(overall=cohort(output_rows), by_condition=by_condition, by_source_group=by_group,
                              topk4_diagnostic=topk_summary(output_rows), topk4_by_condition=by_condition_topk, rows=output_rows)
    output = dict(status='FLOAT_DIAGNOSTICS_ONLY_NOT_ACCEPTED_FOR_DEPLOYMENT', model_sha256=trainer.sha(RUN / 'best_weights.pt'),
                  scope='Frozen float C4 candidate; native-label bbox proxy, G validation. No bar, integer, MCU or H assessment',
                  topk_semantics='Four maxima in thin-tip heatmap, radius5 heat-pixel NMS, 3x3 sigmoid centroid; reference-point minima are recall diagnostics only, never final output selection',
                  optimizer_steps=0, thresholds_changed=False, test_H_opened=False, reports=reports,
                  findings=['Hub localization learned; thin-tip accuracy remains insufficient even on training images',
                            'G cross-session thin-tip and accepted-angle errors are materially worse than training',
                            'Legacy evidence scores do not reliably reject wrong needle direction on G; no deployment'],
                  limitation='Source labels are AI-assisted uncertain annotations; condition tags are planned/visual categories, not measured pose/lux. TopK is float evidence not actual MCU integer postprocessing.')
    trainer.write(RUN / 'diagnostics' / 'candidate_diagnostics.json', output)
    print(json.dumps({split: {k: v for k, v in value.items() if k not in ['rows']} for split, value in reports.items()}, ensure_ascii=False))


if __name__ == '__main__':
    main()
