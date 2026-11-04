"""Finalize actual newELF/oneG matrix evidence; never runs a network or C/H."""
from pathlib import Path
import hashlib,json,re
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];B=HERE/'build'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')
def main():
    receipt=load(B/'build_receipt.json');matrix=load(HERE/'host_matrix/validation_matrix.json')
    assert matrix['ELF_sha256']==receipt['ELF']['sha256']==sha(B/'meter_landmark_reader.elf')
    boot=load(HERE/'boot_numeric_contract.json');assert boot['ELF_sha256']==receipt['ELF']['sha256']
    assert matrix['old_domain_all59_exactly_reconstructed'] and not matrix['H_rerun'] and not matrix['C_group_opened']
    for n,v in receipt['source_sha256'].items():assert sha(HERE/'source'/n)==v,n
    sym={x[2]:int(x[0],16)for l in (B/'symbols.stdout').read_text(errors='replace').splitlines()if len(x:=l.split())==3}
    frames={};su=[]
    for p in B.glob('*.su'):
        su.append(dict(path=str(p),sha256=sha(p)))
        for line in p.read_text(errors='replace').splitlines():
            name,size,kind=line.rsplit('\t',2);assert kind=='static';frames[name.rsplit(':',1)[-1]]=int(size)
    chain=['main','mroi_process_one_with_consumer','finish','mlg_consensus_q8','solve','project','mlg_atan2_deg_q16']
    bound=sum(frames[n]for n in chain)+80+frames['core_exception_handler']+64
    assert bound<=2048
    heap=(sym['_end']+15)&~15;assert heap<=sym['__StackLimit'] and sym['_sp']==0x0800c000
    audit=dict(status='ACTUAL_EXPANDED_FULL_ELF_LINK_AND_STATIC_STACK_PASS',ELF_sha256=sha(B/'meter_landmark_reader.elf'),raw_bytes=receipt['raw']['bytes'],TCM=receipt['TCM'],gap_after_heap_alignment=sym['__StackLimit']-heap,stack=dict(reserved=2048,conservative_bound=bound,remaining=2048-bound,frames={n:frames[n]for n in chain},exception_entry=80,exception_C_handler=frames['core_exception_handler'],helper_slack=64,actual_MCU_watermark_measured=False),stack_usage_sources=su,Flash_sector_bytes=65536,Flash_read_or_compute_cycles_measured=False,calibration_domain=receipt['calibration_domain'],H_rerun=False,C_group_opened=False,device=False)
    write(HERE/'link_stack_audit.json',audit)
    prior=load(HERE/'fork_receipt.json');origin=Path(prior['origin'])
    if not origin.is_absolute():origin=ROOT/origin
    changes=[]
    for name,want in prior['old_all_files_sha256'].items():
        if sha(origin/name)!=want:changes.append(name)
    assert not changes,changes
    write(HERE/'preservation_check.json',dict(status='ORIGINAL_DD8A_ALL138_FILES_UNCHANGED',files=len(prior['old_all_files_sha256']),old_ELF_sha256=sha(origin/'build/meter_landmark_reader.elf'),original_H_test_unchanged_by_this_task=True))
    truth={r['id']:r for r in [json.loads(s)for s in (ROOT/'algorithm_work/meter_cnn_training_20261102/prepared_validation.jsonl').read_text().splitlines()if s.strip()]}
    production='new_network_corrected_domain';rr=matrix['rows'];front=[r for r in rr if truth[r['id']]['scene']['primary']in ['front_medium_soft_light','front_large_soft_light']]
    front_ok=sum(r[production]['valid']and r[production]['absolute_error_psi']<=.5 for r in front)
    goal=dict(reference_only_not_user_acceptance=True,target_correct_descriptive_05psi=32,actual_correct=matrix['summary'][production]['within_05psi'],front_target=12,front_correct=front_ok,front_denominator=len(front),met_on_reused_G=matrix['summary'][production]['within_05psi']>=32 and front_ok>=12)
    report=dict(status='EXPANDED_EXPERIMENTAL_FULL_FIRMWARE_AND_G_MATRIX_COMPLETE_AWAIT_FINAL_C_AND_BOARD',unit='psi',candidate='new1222sixpointU7+frozen1202hub/1009polar+oldfirstring+TRAINcorrecteddomain',ELF=dict(path=str(B/'meter_landmark_reader.elf'),sha256=sha(B/'meter_landmark_reader.elf')),raw=dict(path=str(B/'meter_landmark_reader.bin'),sha256=sha(B/'meter_landmark_reader.bin'),bytes=receipt['raw']['bytes'],crc32=receipt['raw']['crc32']),coldboot_payload=receipt['coldboot_sector'],calibration_domain=receipt['calibration_domain'],actual_memory=audit,boot_numeric_contract=boot,development_G_matrix=matrix['summary'],changes=matrix['changes'],engineering_goal=goal,artifacts={p.relative_to(HERE).as_posix():sha(p)for p in [B/'build_receipt.json',HERE/'link_stack_audit.json',HERE/'preservation_check.json',HERE/'numeric_verification.json',HERE/'calibration_domain_preflight.json',HERE/'boot_numeric_contract.json',HERE/'host_matrix/validation_matrix.json',HERE/'host_matrix/predictions_before_scoring.jsonl']},limits=['Ghasbeenreusedfordevelopmentandisnotindependenttest','FinalCgroupmustremainlockeduntilsupervisorFINALmanifest','Hhistoricalevaluationneverrerunorrewritten','TCMlinked/hostCcorrectnessdoesnotproveactualMCUFlashXIPcycleorcoldboot','stage_cycles0..3hub/landmarks/polar/ring;slot4reserved;totalmroi_diag.elapsed_cyclesincludesall','Same-sourceproxyROI/manualboxesnotactualauto-FPGA/CSIbytevalidation','RequirespairedPSIfeatures064/PSI124bit;old80f9isnotcompatible'],hardware_actions=False,H_rerun=False,C_group_opened=False)
    write(HERE/'completion.json',report);print(json.dumps(dict(raw_bytes=report['raw']['bytes'],TCM_gap=audit['gap_after_heap_alignment'],stack_bound=bound,engineering_goal=goal),indent=2))
if __name__=='__main__':main()
