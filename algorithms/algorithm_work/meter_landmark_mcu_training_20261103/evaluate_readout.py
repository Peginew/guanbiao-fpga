"""Frozen old-first PSI evaluation of learned per-identity ROI landmarks.

No query labels/pressure enter pose or reference selection. All scoring follows
inference. Existing hub, polar network, calibration, and old accepted pose stay
unchanged. G is development data, not an independent test.
"""
from pathlib import Path
import argparse
import hashlib
import json
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PREVIOUS = ROOT / "algorithm_work/meter_redundant_print_20261102"
sys.path.insert(0, str(PREVIOUS))
import evaluate_redundant as base
from landmark_geometry import NAMES, consensus


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def rows(path):
    return [json.loads(s) for s in Path(path).read_text(encoding="utf-8-sig").splitlines() if s.strip()]


def run(predictions_path, output_path, name):
    records = rows(base.DATA / "prepared_validation.jsonl")
    inputs = rows(predictions_path)
    lookup = {r["id"]: r for r in records}
    assert len(inputs) == len(records) == 59
    assert len({r["id"] for r in inputs}) == 59
    assert {r["id"] for r in inputs} == set(lookup)
    predictions = {r["id"]: r for r in rows(base.MODEL / "polar_angle/run_001/validation_predictions.jsonl")}
    oldposes = {r["id"]: r for r in rows(base.OLD / "candidate_B_pose.jsonl")}
    cal = load(base.OLD / "candidate_B_calibration_psi.json")
    previous = load(base.OLD / "candidate_B_with_old_B_readout_psi.json")
    setup = load(PREVIOUS / "results/canonical_setup.json")
    reference = setup["reference_points_normalized"]
    poses = {}
    for row in inputs:
        i = row["id"]
        r, h = lookup[i], predictions[i]
        assert row["source_sha256"] == r["sha256"]
        assert set(row["points"]) == set(NAMES)
        points = {}
        for identity in NAMES:
            p = row["points"][identity]
            if not p["accepted"]:
                continue
            xy = p.get("roi_xy")
            assert xy is not None and len(xy) == 2
            xy = np.asarray(xy, np.float64)
            assert np.isfinite(xy).all() and np.all((xy >= 0) & (xy <= 127))
            points[identity] = ((xy - np.asarray(h["hub_roi"])) * 48 / r["roi_request"]["radius"] + [64, 64]).tolist()
        fit = consensus(reference, points, setup["canonical_roll_relative_D002"])
        poses[i] = dict(id=i, source_sha256=r["sha256"], split=r["split"], **fit,
                        reference_method="LEARNED_SIX_IDENTITY_ROI128", query_pressure_used=False,
                        query_visual_labels_used=False, automatic_reference_inference=True)
    result = base.evaluate(name, records, predictions, oldposes, poses, cal, previous["rows"])
    result["new_neural_weights"] = "random" not in name.lower()
    result["status"] = "LEARNED_REFERENCE_PC_DEVELOPMENT_PSI_NOT_BOARD_ACCEPTANCE"
    scenes = {r["id"]: r["scene"]["primary"] for r in records}
    front = [o for o in result["rows"] if scenes[o["id"]] in ("front_medium_soft_light", "front_large_soft_light")]
    validfront = [o for o in front if o["valid"]]
    result["frontal"] = dict(images=len(front), outputs=len(validfront),
                            correct_bands={str(t): sum(o["absolute_error_psi"] <= t for o in validfront) for t in (.25, .5, 1.)})
    assert not result["original_valid_ids_changed"]
    result["new_reference_pose_count"] = sum(p["accepted"] for p in poses.values())
    result["pose_rejection_counts"] = {reason: sum(p["reason"] == reason for p in poses.values())
                                        for reason in sorted({p["reason"] for p in poses.values() if not p["accepted"]})}
    result["predeclared_engineering_goal"] = dict(correct_within_descriptive_half_psi=32, denominator=56,
                                                  frontal_correct=12, frontal_denominator=16,
                                                  user_final_accuracy_tolerance=False)
    ss = result["summary"]["output_error_distribution_psi"]
    result["predeclared_engineering_goal_met"] = bool(ss["within_0_5_psi"] >= 32 and result["frontal"]["correct_bands"]["0.5"] >= 12)
    result["sources"] = {str(p.relative_to(ROOT)): sha(p) for p in [
        Path(predictions_path).resolve(), Path(__file__),
        PREVIOUS / "landmark_geometry.py", PREVIOUS / "fusion.py", PREVIOUS / "results/canonical_setup.json",
        base.OLD / "candidate_B_pose.jsonl", base.OLD / "candidate_B_calibration_psi.json",
        base.MODEL / "polar_angle/run_001/validation_predictions.jsonl"]}
    result["limits"] = ["Same-source offline proxy ROI, not real MCU dump", "G is repeatedly used development data",
                         "Three negatives cannot prove general FAR", "New point scores are not calibrated probabilities",
                         "Error bands are descriptive, not user final accuracy tolerance", "H and ABC not used"]
    base.write(output_path, result)
    base.save_rows(Path(output_path).with_suffix(".poses.jsonl"), list(poses.values()))
    print(json.dumps(dict(name=name, summary=result["summary"], frontal=result["frontal"],
                          changes=result["changes"], goal_met=result["predeclared_engineering_goal_met"]), ensure_ascii=False))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    run(args.predictions, args.out, args.name)
