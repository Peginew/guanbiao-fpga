"""Preserve already accepted old observations; new evidence only supplements."""
import copy


def select_reference(old_pose,new_pose):
    if old_pose['accepted']:
        return copy.deepcopy(old_pose),'OLD_REFERENCE_PRESERVED'
    if new_pose.get('accepted',False):
        for field in ('id','source_sha256'):
            if new_pose[field]!=old_pose[field]:raise ValueError('mixed observation '+field)
        return copy.deepcopy(new_pose),'NEW_REDUNDANT_REFERENCE'
    return copy.deepcopy(old_pose),'NO_ACCEPTED_REFERENCE'


def preflight():
    old=dict(id='synthetic',source_sha256='same',accepted=True,relative_roll_deg=3.,reason='old')
    for new in [dict(accepted=False),dict(id='synthetic',source_sha256='same',accepted=True,relative_roll_deg=-19.,reason='conflicting new')]:
        p,route=select_reference(old,new)
        assert p==old and p is not old and route=='OLD_REFERENCE_PRESERVED'
    missing=dict(id='synthetic',source_sha256='same',accepted=False,reason='ring ambiguous')
    p,route=select_reference(missing,dict(id='synthetic',source_sha256='same',accepted=True,relative_roll_deg=4.))
    assert p['relative_roll_deg']==4 and route=='NEW_REDUNDANT_REFERENCE'
    p,route=select_reference(missing,dict(accepted=False));assert p==missing and route=='NO_ACCEPTED_REFERENCE'
    try:select_reference(missing,dict(id='late',source_sha256='same',accepted=True))
    except ValueError:pass
    else:raise AssertionError('mixed source was accepted')
    return dict(status='PASS_OLD_REFERENCE_ROUTING_INVARIANT',cases=5,hardware_actions=False)
