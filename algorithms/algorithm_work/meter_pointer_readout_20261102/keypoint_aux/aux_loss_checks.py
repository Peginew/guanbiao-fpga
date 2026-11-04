"""Loss-mask and weak-supervision checks; no optimizer, H or deployment."""
import json
from pathlib import Path
import numpy as np
import torch
import train_aux as candidate


def main():
    candidate.base.setup(1102, 4)
    train, _ = candidate.items_and_sources()
    checked, noneligible, unknown_tip, negative = 0, 0, 0, 0
    for item in train:
        for seed in [1102, 1103, 1104]:
            x, heat, head_mask, line, line_mask, hard_mask, points = candidate.augment(np.random.default_rng(seed), item)
            if not candidate.eligible(item)[0]:
                assert not line_mask.any()
                noneligible += 1
            if not item['mask'][1]:
                assert not hard_mask.any()
                unknown_tip += 1
            elif not item['target_present']:
                assert hard_mask.all()
                negative += 1
            else:
                px, py = np.asarray(points[1]) / 2
                uncertainty = item['record']['keypoints']['thin_terminal']['uncertainty_px'] / (2 * item['stride'])
                radius = max(3., 3 * item['sigmas'][1], uncertainty + 1)
                protected = (candidate.base.X - px) ** 2 + (candidate.base.Y - py) ** 2 <= radius ** 2
                assert not (hard_mask & protected).any()
                assert (heat[1][hard_mask] < .05).all()
            checked += 1
    logits = torch.zeros(2, 2, 64, 64, requires_grad=True)
    auxiliary = torch.zeros(2, 1, 64, 64, requires_grad=True)
    targets = torch.zeros_like(logits)
    head_mask = torch.tensor([[0., 0.], [1., 1.]])
    lines = torch.zeros(2, 64, 64)
    line_mask = torch.zeros(2, 64, 64)
    hard = torch.zeros(2, 64, 64, dtype=torch.bool)
    hard[1] = True
    loss, main_loss, weak_loss, hard_loss = candidate.losses(logits, auxiliary, targets, head_mask, lines, line_mask, hard)
    loss.backward()
    assert not logits.grad[0].count_nonzero()
    assert logits.grad[1].count_nonzero()
    assert not auxiliary.grad.count_nonzero()
    result = dict(status='PASS_LOSS_MASK_AND_HARD_NEGATIVE_EXCLUSION', trainer_sha256=candidate.base.sha(candidate.__file__),
                  actual_train_augmented_records_checked=checked, noneligible_aux_masks_zero=noneligible,
                  unknown_tip_hard_negative_masks_zero=unknown_tip, true_negative_hard_masks_full=negative,
                  protected_tip_region_hard_negative_overlap=0, ignored_head_gradient_nonzero_count=0,
                  absent_aux_gradient_nonzero_count=0, true_negative_gradient_nonzero_count=int(logits.grad[1].count_nonzero()),
                  real_optimizer_steps=0, H_opened=False, PLAN=candidate.PLAN)
    candidate.base.write(Path(__file__).parent / 'aux_loss_checks.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()
