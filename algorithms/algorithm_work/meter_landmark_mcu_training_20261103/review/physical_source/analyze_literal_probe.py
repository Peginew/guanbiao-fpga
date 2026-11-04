"""Analyze existing native files only; FP belongs to ignored, SMD to exception."""
import re
from pathlib import Path
from audit_synth import HERE,read,ref,sha,write

def summary_rows(text,needle):
    out=[]
    for s in text.splitlines():
        m=re.match(r'^\s*(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(set_.*)$',s)
        if m and needle in m[5]:out.append(dict(Total=int(m[1]),Dominated=int(m[2]),Shadowed=int(m[3]),Ignored=int(m[4]),command=m[5]))
    return out

def main():
    old=read(HERE/'readonly_literal_contract_probe.json');run=Path(old['run'])
    exc=(run/'actual_exception.timing').read_text();ign=(run/'ignored.timing').read_text();log=(run/'console.log').read_text()
    psi=summary_rows(exc,'return_psi_q8');asr=summary_rows(ign,'.asr')
    assert old['code']==0 and old['both_registered_before_first_timer']
    assert len(psi)==1 and psi[0]['Total']==psi[0]['Dominated']==17 and psi[0]['Shadowed']==psi[0]['Ignored']==0
    assert len(asr)==2 and all(x['Total']==x['Dominated']==6 and x['Shadowed']==x['Ignored']==0 for x in asr)
    assert all('u_hdmi_reset/release_ff[2]'in x['command']for x in asr)
    literal=(run/'asr_literal.sdc').read_text();psi_literal=(run/'psi_literal.sdc').read_text()
    assert len(re.findall(r'\.asr\b',literal))==6 and len(literal.splitlines())==len(psi_literal.splitlines())==1
    assert not any(k in psi_literal for k in ['set_false_path','set_multicycle','set_clock_groups'])
    result=dict(passed=True,status='PASS_REAL_READ_SDC_ASR6_PSI17_REGISTRATION_ONLY',run=str(run),
        original_probe_receipt=ref(HERE/'readonly_literal_contract_probe.json'),parser=ref(__file__),
        original_probe_reported_false_reason='It searched for false-path rows in MCP exception report; actual FP table is report_timing_ignored',
        native_log=ref(run/'console.log'),MCP_SMD_report=ref(run/'actual_exception.timing'),FP_report=ref(run/'ignored.timing'),
        PSI_unique_SMD=psi[0],ASR_Max_and_Min_FP=asr,source_place=old['source_place'],
        ASR_literal=ref(run/'asr_literal.sdc'),PSI_literal=ref(run/'psi_literal.sdc'),
        exact_same_asr12FF6pin_mapping_review=ref(HERE/'place_route_admission_review.json'),
        both_read_sdc_registered_before_first_native_timer=True,actual_object_counts='q8=16 valid=1 hdmi=1',
        no_device_route_place_or_DBexport=True,physical_FINAL_or_bitgen_passed=False,
        scope='Actual registration and scope proof on same placed DB, not timing convergence or causal proof for current routed9endpoints')
    write(HERE/'literal_contract_effective_review.json',result)
    print(result['status'],sha(HERE/'literal_contract_effective_review.json'))

if __name__=='__main__':main()
