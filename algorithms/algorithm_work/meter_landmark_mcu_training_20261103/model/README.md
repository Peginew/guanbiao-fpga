# Six identified static-print heatmaps

This is one bounded 1,222-parameter C4 candidate. It takes the original whole
128×128 grayscale ROI and emits six 64×64 heatmaps in the identity order in
`landmark_model.py`. It does not take a needle angle, pressure, visibility label,
or query pose as input. The old trained 1,202-parameter hub and 1,009-parameter
polar models remain separate and frozen.

`train_landmarks.py preflight` verifies parameter/MAC counts and gradient masks.
The one authorized training run is 4,800 steps, seed 1109, Adam and the fixed
augmentation/selection plan in `plan_before_training.json`. Data must be the
reviewed DEF177 labels and fixed G59 development labels from `../data/`.
Unknown points are ignored; explicitly invisible/absent points have no-peak
targets; visible points have spatial targets. The coordinate and visibility
supervision masks have different meanings. No PSI value is a learning target.
G is development data used for checkpoint selection, not an independent test.

The step-zero control randomizes only the new landmark branch. It does not
randomize the already trained hub/polar system. A training loss reduction or
point score alone does not establish improved pressure readout; the parent
pipeline evaluates geometry, old-first preservation and PSI on all 59 images.

`export_integer.py` calibrates activation scales using DEF177 originals and four
fixed train-only views per image. It exports power-of-two W8/S32-bias layers,
signed RNE-even shifts, U7 hidden activations and S8 final logits at scale 1/16.
The two input branch scales of `fuse` are folded into its quantized weights.
The arithmetic reference uses CHW arrays; the MCU activation interface is HWC,
and saved layer traces contain both layouts. The MCU can decode each 4096-byte
head in turn rather than retaining all six maps. C headers include exact peak
and margin thresholds 9831/656 in Q15 and the separate sigmoid LUT header.

Per-point peak/margin are evidence, not calibrated visibility probabilities.
Failure to accept a point means evidence is insufficient; it does not identify
the physical reason for occlusion or blur. The integer decoder returns ROI_Q8
coordinates using signed-independent RNE-even integer division. Quantization
displacement and acceptance changes are reported rather than hidden.

The arithmetic exports and memory plan do not establish fit in the actual
48-KiB MCU application, cycles, board ROI equivalence or physical readout.
The firmware owner must reuse the existing workspaces, link the complete
application and resample polar features around the actual integer hub output.
No old files, H/ABC images, device configuration, Flash or vehicle are changed.
