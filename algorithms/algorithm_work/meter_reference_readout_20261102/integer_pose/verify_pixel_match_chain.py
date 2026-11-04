"""Integer pixel/profile math plus actual C matching; geometry still float."""
import json,time
import numpy as np
import verify_matcher as m


def main():
    lib=m.dll();tt,keep=m.templates(lib)
    oldmanifest=m.load(m.HERE/'fixtures/manifest.json')
    old={r['id']:r for r in oldmanifest['records']}
    meta=m.load(m.HERE/'frontend_fixture_manifest.json')
    poses=[];differences=[];decisions=[];angles=[];timings=[]
    for r in meta['records']:
        if not r['actual_model_hub_available']:continue
        z=np.load(m.HERE/'frontend_fixtures'/(r['id']+'.npz'))
        raw,ctx,elapsed=m.run_one(lib,tt,z['profiles'],z['outside_counts'],r['center_allowed'])
        p=m.make_pose(r,raw,z);p['pixel_profile_math_integer']=True;p['coordinate_generation_integer']=False
        poses.append(p);timings.append(elapsed)
        b=old[r['id']]['baseline']
        if p['accepted']!=b['accepted']:decisions.append(dict(id=r['id'],old=b,integer=p))
        if p.get('relative_roll_deg')!=b.get('relative_roll_deg'):angles.append(dict(id=r['id'],old=b,integer=p))
        changes=[key for key in ['reference_id','dx','dy','radius_scale'] if p.get(key)!=b.get(key)]
        if changes:differences.append(dict(id=r['id'],fields=changes,old=b,integer=p))
    byid={p['id']:p for p in poses};report=m.numeric_result(byid)
    report['status']='INTEGER_PIXEL_PROFILE_AND_C_MATCHER_PC_NOT_FULL_INTEGER_GEOMETRY_OR_MCU'
    report['source_geometry_uses_float']=True
    (m.HERE/'integer_pixel_match_pose.jsonl').write_text(''.join(json.dumps(p)+'\n' for p in poses),'utf-8')
    m.write(m.HERE/'integer_pixel_match_readout_psi.json',report)
    baseline=m.load(m.OLD/'candidate_B_with_old_B_readout_psi.json')
    b={p['id']:p for p in baseline['rows']};pressure=[]
    for p in report['rows']:
        q=b[p['id']]
        if p['valid']!=q['valid'] or p['psi_estimate']!=q['psi_estimate']:
            pressure.append(dict(id=p['id'],old=q,integer=p))
    status='PASS_FROZEN_PSI_OUTPUTS_PRESERVED' if not pressure else 'INTEGER_FRONTEND_CHANGED_PSI_OUTPUTS'
    receipt=dict(status=status,model_hub_records=len(poses),arithmetic_only13_records_excluded_from_readout=True,
        pose_decision_changes=decisions,pose_angle_changes=angles,pose_winner_metadata_changes=differences,
        pressure_output_changes=pressure,summary=report['summary'],
        float32_tie_profile_differences=m.load(m.HERE/'frontend_verification.json')['counts']['rational_vs_float32_profile_mismatches'],
        frontend_profile_max_abs_difference=1,thresholds_changed=False,calibration_changed=False,
        geometry_uses_float=True,MCU_deployed=False,H_opened=False,hardware_actions=False,
        source=dict(frontend_manifest_sha256=m.numeric.sha(m.HERE/'frontend_fixture_manifest.json'),
                    matcher_verification_sha256=m.numeric.sha(m.HERE/'c_matcher_verification.json')))
    m.write(m.HERE/'integer_pixel_match_chain_receipt.json',receipt)
    print(status,'poses',len(poses),'decision changes',len(decisions),'angle changes',len(angles),'metadata changes',len(differences),
          'PSI changes',len(pressure),'readings',report['summary']['valid_readings'],'MAE',report['summary']['reading_mae_psi'])


if __name__=='__main__':main()
