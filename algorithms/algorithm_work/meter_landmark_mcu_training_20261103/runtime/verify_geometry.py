"""Host checks of the actual deployable integer C geometry, no model fitting."""
from pathlib import Path
import ctypes as C
import hashlib
import json
import math
import subprocess
import sys
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRIOR = ROOT / "algorithm_work/meter_redundant_print_20261102"
sys.path.insert(0, str(PRIOR))
from landmark_geometry import NAMES, consensus, wrap


class Point(C.Structure):
    _fields_ = [("x", C.c_int32), ("y", C.c_int32)]


class Result(C.Structure):
    _fields_ = [("roll", C.c_int32), ("sse", C.c_uint32), ("accepted", C.c_uint8),
                ("reason", C.c_uint8), ("mask", C.c_uint8), ("count", C.c_uint8)]


def load():
    cmd = ["C:/Users/Edward/Desktop/mingw64/bin/gcc.exe", "-std=c99", "-O2", "-Wall", "-Wextra", "-Werror",
           "-shared", "-static-libgcc", str(HERE / "landmark_geometry.c"), "-o", str(HERE / "landmark_geometry.dll")]
    cp = subprocess.run(cmd, capture_output=True, text=True, creationflags=0x08000000)
    (HERE / "host_compile.log").write_text(cp.stdout + cp.stderr, encoding="utf-8")
    assert cp.returncode == 0
    lib = C.CDLL(str(HERE / "landmark_geometry.dll"))
    lib.mlg_consensus_q8.argtypes = [C.POINTER(Point), C.POINTER(Point), C.c_uint8, C.c_int32, C.POINTER(Result)]
    lib.mlg_consensus_q8.restype = C.c_int
    lib.mlg_atan2_deg_q16.argtypes = [C.c_int32, C.c_int32]
    lib.mlg_atan2_deg_q16.restype = C.c_int32
    lib.mlg_normalize_q8.argtypes = [C.POINTER(Point), Point, C.c_uint32, C.c_uint8, C.POINTER(Point)]
    return lib


def array(values):
    return (Point * 6)(*(Point(round(p[0] * 256), round(p[1] * 256)) for p in values))


def infer(lib, reference, query, offset):
    mask = sum(1 << i for i, n in enumerate(NAMES) if n in query)
    xx = array([reference[n] for n in NAMES])
    yy = array([query.get(n, [0, 0]) for n in NAMES])
    result = Result()
    lib.mlg_consensus_q8(xx, yy, mask, round(offset * 65536), C.byref(result))
    return result


def run():
    lib = load()
    setup = json.loads((PRIOR / "results/canonical_setup.json").read_text(encoding="utf-8"))
    reference, offset = setup["reference_points_normalized"], setup["canonical_roll_relative_D002"]
    lines = ["#ifndef METER_LANDMARK_REFERENCE_H", "#define METER_LANDMARK_REFERENCE_H", '#include "landmark_geometry.h"',
             "static const mlg_point_q8 mlg_reference_q8[6] = {"]
    lines += [f"    {{{round(reference[n][0]*256)}, {round(reference[n][1]*256)}}}, /* {n} */" for n in NAMES]
    lines += ["};", f"#define MLG_REFERENCE_ROLL_Q16 ({round(offset*65536)})", "#endif", ""]
    (HERE / "landmark_reference.h").write_text("\n".join(lines), encoding="utf-8")
    checks, angles, mismatch = 0, [], []
    for degree in np.arange(-180, 180, .2):
        rad = math.radians(degree)
        actual = lib.mlg_atan2_deg_q16(round(math.sin(rad)*65536), round(math.cos(rad)*65536))/65536
        assert abs(wrap(actual-degree)) < .003
        checks += 1
    rng = np.random.default_rng(20261103)
    for k in range(500):
        angle = rng.uniform(-19, 19) - offset
        a = math.radians(angle)
        mat = rng.uniform(.9, 1.1)*np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        xy = (np.array([reference[n] for n in NAMES])-64)@mat.T+64+rng.uniform(-10, 10, 2)+rng.normal(0, .15, (6, 2))
        ids = rng.choice(6, rng.integers(2, 7), replace=False)
        q = {NAMES[i]: xy[i].tolist() for i in ids}
        if k % 7 == 0 and len(ids) > 3:
            q[NAMES[ids[0]]] = (xy[ids[0]]+[13, -17]).tolist()
        expected = consensus(reference, q, offset)
        actual = infer(lib, reference, q, offset)
        if bool(actual.accepted) != expected["accepted"]:
            mismatch.append(dict(case=k, C_accepted=bool(actual.accepted), python_accepted=expected["accepted"], C_reason=actual.reason))
        if actual.accepted and expected["accepted"]:
            angles.append(abs(wrap(actual.roll/65536-expected["relative_roll_deg"])))
        checks += 1
    # Algorithm preservation on the previously frozen59 manual point records,
    # not an additional trained-model experiment.
    old = json.loads((PRIOR / "results/visual_old_first.json").read_text(encoding="utf-8"))
    label_results = []
    for row in old["routing"]:
        p = row["new_pose"]
        record = next(x for x in [json.loads(t) for t in (ROOT/'algorithm_work/meter_cnn_training_20261102/prepared_validation.jsonl').read_text(encoding='utf-8-sig').splitlines()] if x['id'] == row['id'])
        prediction = next(x for x in [json.loads(t) for t in (ROOT/'algorithm_work/meter_pointer_readout_20261102/polar_angle/run_001/validation_predictions.jsonl').read_text(encoding='utf-8-sig').splitlines()] if x['id'] == row['id'])
        annotation = next(x for x in [json.loads(t) for t in (PRIOR/'annotations/print_annotations.jsonl').read_text(encoding='utf-8-sig').splitlines()] if x['id'] == row['id'])
        import evaluate_redundant as ev
        q, _ = ev.manual_points(annotation, record, prediction)
        actual = infer(lib, reference, q, offset)
        assert bool(actual.accepted) == p['accepted'], row['id']
        err = abs(wrap(actual.roll/65536-p['relative_roll_deg'])) if actual.accepted else None
        if err is not None:
            assert err < .05, (row['id'],err)
        label_results.append(dict(id=row['id'],accepted=bool(actual.accepted),angle_error_degrees=err))
        checks += 1
    assert not mismatch, mismatch
    assert max(angles, default=0) < .05
    report = dict(status='PASS_INTEGER_C_GEOMETRY_NOT_FIRMWARE_OR_BOARD', checks=checks,
                  synthetic_cases=500, atan_cases=1800, synthetic_acceptance_mismatch=mismatch,
                  max_synthetic_roll_error_deg=max(angles, default=None), original_visual59=label_results,
                  quantization='pointsQ8,coefficientsQ16,angleQ16; not arbitrary-input bit equivalence to float',
                  training=False, hardware_actions=False,
                  sources={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [HERE/'landmark_geometry.c',HERE/'landmark_geometry.h',Path(__file__),HERE/'landmark_reference.h']})
    (HERE / 'geometry_validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k != 'original_visual59'},ensure_ascii=False))


if __name__ == '__main__':
    run()
