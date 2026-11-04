"""Bind actual ELF, bounded failure analysis and compiled stack evidence."""
from pathlib import Path
import hashlib,json,math,re,subprocess
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];B=HERE/'build'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def rows(p):return[json.loads(x)for x in Path(p).read_text('utf-8-sig').splitlines()if x.strip()]
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')
def main():
    replay=load(HERE/'host/validation_replay.json');new={r['id']:r for r in replay['rows']}
    oldhub={r['id']:r for r in load(ROOT/'algorithm_work/meter_cnn_training_20261102/run_002/validation_evaluation.json')['rows']}
    oldp={r['id']:r for r in rows(ROOT/'algorithm_work/meter_pointer_readout_20261102/polar_angle/run_001/validation_predictions.jsonl')}
    oldpose={r['id']:r for r in rows(ROOT/'algorithm_work/meter_robust_readout_20261102/pose/candidate_B_pose.jsonl')}
    failures=[]
    for ident in ['G_011','G_028','G_045','G_042']:
        n=new[ident];h=oldhub[ident];p=oldp[ident];pose=oldpose[ident]
        corrected=n['angle_deg_image']-n['selected_roll']
        failures.append(dict(id=ident,old_float_hub=h['predicted_points_roi'][0],new_W8_hub=n['hub'],hub_movement_ROI=math.dist(h['predicted_points_roi'][0],n['hub']['roi_xy']),old_hub_peak=h['peaks'][0],old_hub_margin=h['margins'][0],old_angle=p['angle_deg_image'],new_angle=n['angle_deg_image'],old_neural_valid=p['valid'],new_neural_valid=n['neural_valid'],new_needle_peak=n['needle_peak_q15']/32767,new_needle_margin=n['needle_margin_q15']/32767,old_ring=pose,new_ring=n['ring'],new_points=n['landmarks'],new_print_pose=n['landmark_pose'],selected_reference=n['selected_reference_kind'],corrected_angle=corrected,frozen_angle_domain=[164.9189063841552,288.1874999590581],final=n['final'],interpretation={'G_011':'Hub peak0.29423 below fixed0.3 afterW8; geometry movement only0.042ROI and ring stillaccepted. No threshold relaxation.', 'G_028':'Hub peak0.23371 below fixed0.3 afterW8; geometry movement0.081ROI and ring stillaccepted. No threshold relaxation.', 'G_045':'Hub moves0.875ROI, needle−2.456deg, ring12→13deg. Corrected163.320deg falls below frozen164.919deg; old-first does not switch to new print solely to rescue calibration.', 'G_042':'Oldring rejects; newprint acceptedroll6.273deg. Needle199.786deg produces4.93359psi against4psi, addedwrong>0.5. Geometric consistency does not prove calibration/pointcorrectness.'}[ident]))
    write(HERE/'bounded_failure_diagnosis.json',dict(status='ANALYSIS_ONLY_NO_CODE_OR_THRESHOLD_CHANGE',rows=failures,replay_sha256=sha(HERE/'host/validation_replay.json'),reference='Fixedmodelandcalibration; noGparameterretuning'))
    frames={};su=[]
    for p in B.glob('*.su'):
        su.append(dict(path=str(p),sha256=sha(p)))
        for line in p.read_text(errors='replace').splitlines():
            name,size,kind=line.rsplit('\t',2);frames[name.rsplit(':',1)[-1]]=int(size);assert kind=='static'
    # Explicit indirect consumer lifecycle edges, plus conservative simultaneous
    # solve/project/atan allocations (the latter two are actually alternatives).
    chain=['main','mroi_process_one_with_consumer','finish','mlg_consensus_q8','solve','project','mlg_atan2_deg_q16']
    compiled=sum(frames[x]for x in chain)
    dis=(B/'disassembly.stdout').read_text(errors='replace')
    assert re.search(r'<exc_entry>:\n[^\n]*\bsp,sp,-80',dis)
    exception=80+frames['core_exception_handler'];assert exception==112
    bound=compiled+exception+64 # additional conservative fixedhelper allowance
    assert bound<=2048
    receipt=load(B/'build_receipt.json');sym={x[2]:int(x[0],16)for line in (B/'symbols.stdout').read_text(errors='replace').splitlines()if len(x:=line.split())==3}
    for name in ['mroi_c4_compute','mp_push','hub_w0','landmark_w0','polar_w0','reader_sigmoid_q15']:
        assert 0x08000000<=sym[name]<0x0800b800,(name,sym.get(name))
    for name in ['reader_ring','ring_indices_0','ring_values_0','reader_cos_q30']:
        assert 0x20e00000<=sym[name]<0x20e10000,(name,sym.get(name))
    audit=dict(status='OFFLINE_FULL_ELF_MEMORY_LOAD_AND_BOUNDED_STACK_PASS',ELF_sha256=sha(B/'meter_landmark_reader.elf'),raw_sha256=sha(B/'meter_landmark_reader.bin'),raw_bytes=receipt['raw']['bytes'],flash_sector_bytes=65536,TCM_bytes=49152,stack_bytes=2048,static_end=sym['_end'],heap_alignment_end=(sym['_end']+15)&~15,stack_limit=sym['__StackLimit'],gap_after_alignment=sym['__StackLimit']-((sym['_end']+15)&~15),stack=dict(compiled_frames={n:frames[n]for n in chain},sum_conservatively_nested=compiled,exception_entry_plus_handler=exception,extra_helper_allowance=64,bound=bound,remaining=2048-bound,static_only_not_MCUwatermark=True),section_and_runtime_symbols={n:sym[n]for n in ['mroi_c4_compute','mp_push','hub_w0','landmark_w0','polar_w0','reader_sigmoid_q15','reader_ring','ring_indices_0','ring_values_0','reader_cos_q30']},stack_usage_sources=su,source_domain='GproxyROI/manualbbox HDMIgray; not actualCSIautoROI or board inference',hardware_actions=False,Flash_read_timing_measured=False)
    write(HERE/'link_stack_audit.json',audit)
    lifecycle=subprocess.run([str(HERE/'lifecycle_host.exe')],capture_output=True);assert lifecycle.returncode==0
    write(HERE/'lifecycle_receipt.json',dict(status='HOST_LIFECYCLE_AND_PSI_ABI_PASS',stdout=lifecycle.stdout.decode().strip(),fixture_sha256=sha(HERE/'verify_lifecycle.c'),client_sha256=sha(HERE/'source/mroi_client.c'),coldstart_sha256=sha(HERE/'source/mroi_cold_start.c'),scope='Transportfixtureonly,notmodelorboard',hardware_actions=False))
    write(HERE/'completion.json',dict(status='FULL_FIRMWARE_OFFLINE_LINK_PASS_PERFORMANCE_TARGET_NOT_MET_NO_DEPLOYMENT',entry='0x20e00000',ELF=str(B/'meter_landmark_reader.elf'),ELF_sha256=sha(B/'meter_landmark_reader.elf'),BIN=str(B/'meter_landmark_reader.bin'),BIN_sha256=sha(B/'meter_landmark_reader.bin'),coldboot_payload=str(B/'U33_E00000_E0FFFF_reader_payload.bin'),TCM_gap_after_alignment=audit['gap_after_alignment'],stack_bound=bound,G_development=replay['summary'],goal_not_met='26outputs/25within0.5psi versusdeclared32 and oldfloat21notallpreserved. Existingfrozenreferenceprioritypreserved under newintegerobservations; nofalseclaimbitexactoldfloatreadings.',artifacts={str(p.relative_to(HERE)):sha(p)for p in [B/'build_receipt.json',HERE/'abi_contract.json',HERE/'numeric_verification.json',HERE/'link_stack_audit.json',HERE/'host/validation_replay.json',HERE/'host/validation_predictions.jsonl',HERE/'bounded_failure_diagnosis.json',HERE/'lifecycle_receipt.json']},limitations=['RequiresnewPSIfeaturebit; old80f9isnotcompatible','PhysicalFlashXIPtiming/coldboot/actualcameraROI/MCUcyclesunverified','Originalstartupcopyhasno runtimeCRC; CRCandsectorcontentboundoffline only','Gisreuseddevelopmentset;3negativesnotindustrialFAR'],H_ABC_opened=False,hardware_actions=False))
    print(json.dumps(dict(stack_bound=bound,TCM_gap_after_alignment=audit['gap_after_alignment'],ELF_sha256=sha(B/'meter_landmark_reader.elf'))))
if __name__=='__main__':main()
