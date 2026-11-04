"""Necessary synthetic occlusion and frame-routing checks before G scoring."""
import json,math
from pathlib import Path
import numpy as np
from landmark_geometry import NAMES,CONFIG,consensus
from fusion import preflight


def main():
    xy=np.array([[18,57],[58,18],[108,48],[61,48],[65,74],[68,92]],float)
    c=np.array([64.,64.]);a=math.radians(12)
    R=np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])
    q=(xy-c)@R.T*.98+c+[4,-3]
    ref=dict(zip(NAMES,xy.tolist()));query=dict(zip(NAMES,q.tolist()))
    cases=[]
    for hidden in [(),(NAMES[1],),(NAMES[-1],),(NAMES[1],NAMES[-1])]:
        visible={k:v for k,v in query.items() if k not in hidden};out=consensus(ref,visible,2.)
        assert out['accepted'] and abs(out['relative_roll_deg']-14)<1e-10
        cases.append(dict(hidden=list(hidden),accepted=out['accepted'],support=out['inlier_count'],relative_roll_deg=out['relative_roll_deg']))
    bad=dict(query);bad[NAMES[-1]]=[115,115]
    out=consensus(ref,bad,2.)
    assert out['accepted'] and out['inlier_count']==5 and NAMES[-1] in out['outlier_identities']
    cases.append(dict(test='one_wrong_match',support=out['inlier_count'],ignored=out['outlier_identities']))
    too_few={NAMES[0]:query[NAMES[0]],NAMES[2]:query[NAMES[2]]}
    out=consensus(ref,too_few,2.);assert not out['accepted']
    cases.append(dict(test='two_points_not_redundant',accepted=False))
    report=dict(status='PASS_OCCLUSION_GEOMETRY_AND_OLD_REFERENCE_ROUTING',config=CONFIG,cases=cases,routing=preflight(),
        real_G_images_opened=False,training=False,hardware_actions=False)
    p=Path(__file__).resolve().parent/'preflight_receipt.json';p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(report['status'],'geometry cases',len(cases),'routing',report['routing']['cases'])


if __name__=='__main__':main()
