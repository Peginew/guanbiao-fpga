"""Selected prior+TRAIN-domain package. No G/C/H forward invocation."""
from pathlib import Path
import hashlib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];B=HERE/'build'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')
def main():
    receipt=load(B/'build_receipt.json');boot=load(HERE/'boot_numeric_contract.json');host=load(HERE/'host/calibration_replay_receipt.json')
    elfsha=sha(B/'meter_landmark_reader.elf');assert receipt['ELF']['sha256']==boot['ELF_sha256']==host['ELF_sha256']==elfsha
    for n,want in receipt['source_sha256'].items():assert sha(HERE/'source'/n)==want,n
    prior=ROOT/'algorithm_work/meter_landmark_mcu_training_20261103'
    assert sha(HERE/'source/landmark_weights_q8.h')==sha(prior/'model/landmark_integer/landmark_weights.h')
    assert sha(HERE/'source/hub_weights_q8.h')==sha(prior/'model/hub_integer/hub_weights.h')
    frames={};su=[]
    for p in B.glob('*.su'):
        su.append(dict(path=str(p),sha256=sha(p)))
        for l in p.read_text(errors='replace').splitlines():
            f,n,mode=l.rsplit('\t',2);assert mode=='static';frames[f.rsplit(':',1)[-1]]=int(n)
    chain=['main','mroi_process_one_with_consumer','finish','mlg_consensus_q8','solve','project','mlg_atan2_deg_q16']
    bound=sum(frames[x]for x in chain)+80+frames['core_exception_handler']+64;assert bound<=2048
    sym={x[2]:int(x[0],16)for l in (B/'symbols.stdout').read_text(errors='replace').splitlines()if len(x:=l.split())==3}
    heap=(sym['_end']+15)&~15;gap=sym['__StackLimit']-heap;assert gap>=0 and sym['_sp']==0x0800c000
    memory=dict(status='SELECTED_FULL_ELF_REAL48K_LINK_AND_STATIC_STACK_PASS',ELF_sha256=elfsha,TCM=receipt['TCM'],actual_gap_after_heap_alignment=gap,stack=dict(reserved=2048,static_conservative_bound=bound,remaining=2048-bound,actual_MCU_watermark=False,frames={x:frames[x]for x in chain},exception_entry=80,exception_handler=frames['core_exception_handler'],helper_allowance=64),su_sources=su,Flash_payload_bytes=receipt['raw']['bytes'],Flash_limit_bytes=65536,no_virtual_memory_expansion=True,device=False)
    write(HERE/'link_stack_audit.json',memory)
    matrix_path=HERE.parent/'firmware/host_matrix/validation_matrix.json';matrix=load(matrix_path)
    scores=dict(final_prior_corrected=matrix['summary']['old_network_corrected_domain'],same_C_ring_corrected=matrix['summary']['ring_only_corrected_domain'],historical_prior_old_domain=matrix['summary']['old_network_old_domain'])
    known=load(HERE.parent/'firmware/fork_receipt.json');origin=ROOT/known['origin']if not Path(known['origin']).is_absolute()else Path(known['origin'])
    for name,want in known['old_all_files_sha256'].items():assert sha(origin/name)==want,name
    write(HERE/'preservation_check.json',dict(status='DD8A138FILES_PRESERVED_AND_EXPANDED_SOURCE_SEPARATE',files=len(known['old_all_files_sha256']),prior_ELF_sha256=sha(origin/'build/meter_landmark_reader.elf'),expanded_source_difference_only=host['source_difference_from_expanded'],H_test_rewritten=False))
    art=[B/'build_receipt.json',HERE/'boot_numeric_contract.json',HERE/'numeric_verification.json',HERE/'link_stack_audit.json',HERE/'host/calibration_replay_receipt.json',HERE/'preservation_check.json',HERE/'calibration_domain_preflight.json']
    result=dict(status='SELECTED_PRIOR_B857_TRAIN_CORRECTED_FULL_FIRMWARE_READY_FOR_LOCKED_C_TEST_NOT_BOARD_VALIDATED',selected_point_model='PRIOR_B857',selected_numeric='U7',selection='ExpandedmodelrejectedusingpredeclaredGpolicy;priorcheckpointunchanged;onlyTRAINdomaincorrectionadopted',ELF=dict(path=str(B/'meter_landmark_reader.elf'),sha256=elfsha),raw=receipt['raw'],coldboot_payload=receipt['coldboot_sector'],DLL=host['DLL'],memory=memory,boot_numeric_contract=boot,calibration_domain=receipt['calibration_domain'],G_development=scores,G_provenance=dict(source=str(matrix_path),sha256=sha(matrix_path),method='FrozenoldCrawviaCURRENTselectedDLLcalibrationonly;allfourGarmsverifiedexactly;noGnetworkrerun',scalar_checks=host['G_calibration_scalar_checks']),artifacts={p.relative_to(HERE).as_posix():sha(p)for p in art},limits=['FinalCgroupstilllockedawaitsupervisorFINAL','NoHrerun;historicalHfactbelongspriordomainonly','Gisreuseddevelopmentanddoesnotproveindustrialreliability','NoactualMCUcycle/FlashXIPthroughput/coldbootorCSIautoROIvalidation','stage_cycles0..3populated,slot4reserved;totalmroi_diag.elapsed_cyclesincludesall','RequirepairedPSI064/124platform,old80f9notcompatible'],hardware_actions=False,C_group_opened=False,H_rerun=False)
    selection=HERE.parent/'final_selection.json'
    if selection.exists():result['final_selection_sha256']=sha(selection)
    write(HERE/'completion.json',result);print(json.dumps(dict(ELF_sha256=elfsha,DLL=host['DLL'],raw_bytes=receipt['raw']['bytes'],TCM_gap=gap,stack_bound=bound,G=scores),indent=2))
if __name__=='__main__':main()
