"""Static-only admission of root's PSI held-bundle amendment; no execution."""
import ast,re
from audit_synth import TASK,HERE,read,ref,sha,write

def main():
    path=TASK/'physical/amend_psi_timing.py';text=path.read_text();tree=ast.parse(text)
    node=next(n for n in tree.body if isinstance(n,ast.Assign)and any(isinstance(q,ast.Name)and q.id=='SDC'for q in n.targets))
    sdc=ast.literal_eval(node.value)
    assert re.findall(r'^set_max_delay.*$',sdc,re.M)==['set_max_delay -from $psi_return_sources -to $psi_return_hdmi_clock -datapath_only 7.200']
    assert not re.search(r'^set_(false_path|multicycle_path|clock_groups)',sdc,re.M)
    assert '[llength $psi_return_q8_sources] != 16'in sdc
    required=['and ordered_final','and drc_ok and psi_paths_ok',"timing['STNS']==0 and timing['HTNS']==0",'range(17)',
        "counts.get('Shadowed')==0 and counts.get('Ignored')==0",'PSI_GLOBAL_FINAL_BEGIN','PSI_GLOBAL_FINAL_END',
        "counts.get('Dominated',0)==counts.get('Total Paths')", "'Begin Point' in t and 'End Point' in t"]
    assert all(s in text for s in required)
    endpoints=read(HERE/'psi17_endpoint_precheck.json');assert len(endpoints['registers'])==17
    result=dict(status='PASS_STATIC_CONTRACT_ONLY_NOT_EXECUTION',admitted_to_execute_after_completed_route=True,
        script=ref(path),existing_final_report_runner=ref(TASK/'physical/run_td.py'),strict16q8plus1valid=True,
        only_new_constraint='7.200ns datapath_only PSI17 to HDMI_PIXEL_CLK',
        no_falsepath_multicycle_or_clockcut_in_new_SDC=True,GLOBAL_FINAL_order_TNSzero_DRC_17paths_effectiveSMD_forced=True,
        actual_endpoint_precheck=ref(HERE/'psi17_endpoint_precheck.json'),
        limitations=['TD actual report grammar and SMD coverage must match actual output; empty/missing/different format is FAIL, not proof',
            'Actual17 origins, effective7.2ns and zero ignored/shadowed require independent postrun inspection',
            'No RTL/source SDC/TD/device action by reviewer'],actual_psi_budget_verified=False,bitgen_admitted=False)
    write(HERE/'amend_static_contract_review.json',result)
    print(result['status'],sha(HERE/'amend_static_contract_review.json'))

if __name__=='__main__':main()
