"""Independent final software freeze audit; no images, C/H, training or devices."""
from pathlib import Path
import ctypes as C,hashlib,json,math,struct,zlib
import numpy as np
HERE=Path(__file__).resolve().parent;TASK=HERE.parent;ROOT=TASK.parents[1]
FW=TASK/'firmware_prior_domain';PRIOR=ROOT/'algorithm_work/meter_landmark_mcu_training_20261103'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
def rows(p):return [json.loads(x)for x in Path(p).read_text('utf-8-sig').splitlines()if x.strip()]
checks=0

def ck(x,reason):
 global checks
 assert x,reason
 checks+=1

build=load(FW/'build/build_receipt.json');comp=load(FW/'completion.json')
for name,want in build['source_sha256'].items():ck(sha(FW/'source'/name)==want,'source:'+name)
for key in ['ELF','raw','coldboot_sector']:
 art=build[key];p=Path(art['path']);ck(sha(p)==art['sha256'],'artifact:'+key)
 if 'bytes'in art:ck(p.stat().st_size==art['bytes'],'size:'+key)
ck(sha(FW/'host/meter_landmark_reader.dll')=='21f3f341116be6a5e214cbd5bc61d1529edb5c9c0cb6b9da4941c9bc6f391505','finalDLL')
ck(build['ELF']['sha256']=='7b582ce32365dc6e326c03da562ca1c94ba7cc66d99742aa21256d61cdb2b9bc','selectedELF')
ck(f'{zlib.crc32(Path(build["raw"]["path"]).read_bytes())&0xffffffff:08x}'==build['raw']['crc32'],'rawCRC')
for rel,want in comp['artifacts'].items():ck(sha(FW/rel)==want,'evidence:'+rel)
elf=Path(build['ELF']['path']).read_bytes();eh=struct.unpack_from('<16sHHIIIIIHHHHHH',elf)
ck(eh[0][:5]==b'\x7fELF\x01'and eh[2]==243 and eh[4]==0x20e00000,'ELF32RVentry')
ck(eh[7]==3,'ILP32FELFflags')
loads=[]
for i in range(eh[10]):
 typ,off,va,pa,fs,ms,fl,align=struct.unpack_from('<IIIIIIII',elf,eh[5]+i*eh[9])
 if typ==1:loads.append(dict(vaddr=va,paddr=pa,filesz=fs,memsz=ms,offset=off,flags=fl))
ck(loads==build['loads'],'actualPTLOAD')
for l in loads:
 if l['memsz']:
  ck((0x08000000<=l['vaddr']and l['vaddr']+l['memsz']<=0x0800c000)or(0x20e00000<=l['vaddr']and l['vaddr']+l['memsz']<=0x20e10000),'memoryBounds')
tcm=build['TCM'];ck(tcm['bytes']==49152 and tcm['stack_bytes']==2048 and tcm['gap']==tcm['stack_limit']-tcm['end']==1072,'48Kgap')
syms={line.split()[2]:int(line.split()[0],16)for line in(FW/'build/symbols.stdout').read_text().splitlines()if len(line.split())==3}
ck(syms['_end']==tcm['end']and syms['__StackLimit']==tcm['stack_limit']and syms['_sp']==0x0800c000,'actualNMstack')
stack=load(FW/'link_stack_audit.json');ck(stack['stack']['static_conservative_bound']==1584<2048,'staticStackBound')
for source in stack['su_sources']:ck(sha(source['path'])==source['sha256'],'actualSU')
boot=load(FW/'boot_numeric_contract.json');enable=boot['FPU']['enable_address']
def eb(addr,n):
 for l in loads:
  if l['vaddr']<=addr and addr+n<=l['vaddr']+l['filesz']:return elf[l['offset']+addr-l['vaddr']:l['offset']+addr-l['vaddr']+n]
 raise AssertionError(addr)
ck(eb(enable,2)==bytes.fromhex('9962'),'mstatusFSsetLUI')
ck(eb(enable+2,4)==struct.pack('<I',0x3002a073),'mstatusFSsetCSR')
ck(struct.pack('<I',0x00301073)in eb(enable,24),'FCSRnearestEven')
ck(boot['polar_F32']['fused_FMA_count']==0 and boot['polar_F32']['fmul_count']==8 and boot['polar_F32']['fadd_count']==3,'F32nonFMAreceipt')
# Cal source only DEF; independently derive corrected domain and inward Q16.
cal=load(TASK/'calibration_domain.json');fitp=Path(cal['fit_record_source']);fit=load(fitp)
ck(sha(fitp)==cal['fit_record_source_sha256'],'fitSourceSHA')
prepared={r['id']:r for r in rows(ROOT/'algorithm_work/meter_cnn_training_20261102/prepared_train.jsonl')}
fits=fit['fit_measurements'];ck(len(fits)==65,'fit65')
for r in fits:
 ck(r['id'].split('_')[0]in{'D','E','F'},'fitGroup')
 q=prepared[r['id']];ck(r['source_sha256']==q['sha256']and r['reference_psi']==q['pressure']['value']and q['pressure']['unit']=='psi','fitSourcePressure')
m,b=fit['slope_psi_per_degree'],fit['intercept_psi'];a=[r['reference_angle_unwrapped_deg']for r in fits]
lo=max(min(a),(2.5-b)/m);hi=min(max(a),(12.-b)/m);q16=[math.ceil(lo*65536),math.floor(hi*65536)]
ck([lo,hi]==cal['corrected_domain']and q16==cal['corrected_Q16_inward_inclusive']==[10564968,18954848],'trainIntersectionQ16')
ck(m==cal['slope_unchanged']and b==cal['intercept_unchanged'],'sameFit')
# Verify actual selected DLL against frozen G raw: no image or forward inference.
lib=C.CDLL(str((FW/'host/meter_landmark_reader.dll').resolve()));lib.reader_calibrate_psi_q8_domain.argtypes=[C.c_int32,C.c_int32,C.c_int,C.POINTER(C.c_uint16)];lib.reader_calibrate_psi_q8.argtypes=[C.c_int32,C.c_int32,C.POINTER(C.c_uint16)]
lib.mroi_reader_diagnostic_size.restype=C.c_uint32;ck(lib.mroi_reader_diagnostic_size()==252,'actualABI')
matrix=load(TASK/'firmware/host_matrix/validation_matrix.json');oldp=Path(matrix['old_raw_source']);ck(sha(oldp)==matrix['old_raw_sha256'],'oldRawSHA');old={r['id']:r for r in load(oldp)['rows']}
scalar=0;preserved=0
for n in matrix['rows']:
 ck(n['id'].startswith('G_'),'Gonlyreplay')
 o=old[n['id']]
 def run(raw,domain,ring=False,default=False):
  allow=raw['neural_valid']and(raw['ring']['accepted']if ring else raw['selected_reference_kind']);v=C.c_uint16();angle=round(raw['angle_deg_image']*65536);roll=round((raw['ring']['roll']if ring else raw['selected_roll'])*65536)
  ok=bool(allow and(lib.reader_calibrate_psi_q8(angle,roll,C.byref(v))if default else lib.reader_calibrate_psi_q8_domain(angle,roll,domain,C.byref(v))))
  return dict(valid=ok,psi=v.value/256 if ok else None)
 for raw,name in[(o,'old'),(n,'new')]:
  for dom,dname in[(0,'old_domain'),(1,'corrected_domain')]:ck(run(raw,dom)=={k:n[f'{name}_network_{dname}'][k]for k in ['valid','psi']},('CcalibrationReplay',n['id'],name,dom,run(raw,dom),n[f'{name}_network_{dname}']));scalar+=1
 for dom,dname in[(0,'old_domain'),(1,'corrected_domain')]:ck(run(o,dom,True)=={k:n[f'ring_only_{dname}'][k]for k in ['valid','psi']},'ringCalReplay');scalar+=1
 ck(run(o,1,default=True)=={k:n['old_network_corrected_domain'][k]for k in ['valid','psi']},'defaultCorrected');scalar+=1
 if n['old_network_old_domain']['valid']:
  ck(n['old_network_corrected_domain']==n['old_network_old_domain'],'preservedOldValue');preserved+=1
ck(scalar==413 and preserved==26,'413and26')
policy=load(TASK/'final_model_selection_before_G.json');sel=load(TASK/'final_selection.json');sm=matrix['summary'];oldsm=sm['old_network_corrected_domain'];newsm=sm['new_network_corrected_domain']
ck(sha(TASK/'final_model_selection_before_G.json')==sel['policy']['sha256'],'selectionPolicySHA')
ck(sha(TASK/'firmware/host_matrix/validation_matrix.json')==sel['actual_matrix']['sha256'],'matrixSHA')
ck(newsm['within_05psi']==oldsm['within_05psi']==28 and len(newsm['over_05psi_ids'])==2>len(oldsm['over_05psi_ids'])==1,'predeclaredSelectionFailsNew')
ck(sel['selected']=='PRIOR_B857_U7_TRAIN_CORRECTED'and not sel['expanded_selected'],'selectedPrior')
# Freeze metadata/data provenance, not own annotation gold correctness.
cfg=load(TASK/'model/run_001/config.json');receipt=load(TASK/'model/run_001/training_receipt.json');hist=load(TASK/'model/run_001/history.json')
sourcepaths={'train_labels':TASK/'data/train_landmarks.jsonl','validation_labels':PRIOR/'data/validation_landmarks.jsonl','train_cache':TASK/'data/roi_cache_train.npz','validation_cache':ROOT/'algorithm_work/meter_cnn_training_20261102/roi_cache_validation.npz','model_code':TASK/'model/landmark_model.py','trainer':TASK/'model/train_landmarks.py'}
for k,p in sourcepaths.items():ck(sha(p)==cfg['source_sha256'][k],'trainingSource:'+k)
train=rows(sourcepaths['train_labels']);val=rows(sourcepaths['validation_labels']);ck(len(train)==295 and {r['id'].split('_')[0]for r in train}=={'A','B','D','E','F'},'only295TrainABDEF');ck(len(val)==59 and all(r['id'].startswith('G_')for r in val),'onlyG59dev')
priorlines=(PRIOR/'data/train_landmarks.jsonl').read_bytes().splitlines();newlines=sourcepaths['train_labels'].read_bytes().splitlines();ck({json.loads(x)['id']:x for x in priorlines}=={json.loads(x)['id']:x for x in newlines if json.loads(x)['id'][0]in'DEF'},'DEFlabelBytePreservation')
cache=np.load(sourcepaths['train_cache']);ck(cache['images'].shape==(295,128,128)and cache['images'].dtype==np.uint8 and set(cache['ids'])=={r['id']for r in train},'295cacheIDs')
ck([r['step']for r in hist]==list(range(400,8001,400))and receipt['steps']==8000 and receipt['best_step']==min(hist,key=lambda x:x['validation']['selection_score'])['step']==8000,'one8000History')
ck(sha(TASK/'model/run_001/best_weights.pt')==receipt['best_checkpoint_sha256']==sel['rejected_expanded_point_weights']['sha256'],'rejectedCheckpoint')
ck(sha(Path(sel['selected_point_weights']['path']))==sel['selected_point_weights']['sha256'],'selectedPriorCheckpoint')
ck((FW/'source/landmark_weights_q8.h').read_bytes()==(PRIOR/'firmware/source/landmark_weights_q8.h').read_bytes(),'priorWeightHeaderUnchanged')
for name in['hub_weights_q8.h','polar_weights_q8.h']:ck((FW/'source'/name).read_bytes()==(PRIOR/'firmware/source'/name).read_bytes(),'oldhubpolarUnchanged')
diff=[p.name for p in(FW/'source').iterdir()if p.is_file()and(TASK/'firmware/source'/p.name).exists()and p.read_bytes()!=(TASK/'firmware/source'/p.name).read_bytes()];ck(diff==['landmark_weights_q8.h'],'sourceOnlySelectedWeightsDifference')
report=dict(status='INDEPENDENT_SOFTWARE_FREEZE_PASS_ADMIT_ONE_LOCKED_C_TEST',checks=checks,reviewer='roi_adapter_independent_software_not_own_label_gold',selected='PRIOR_B857_U7_TRAIN_CORRECTED',ELF=build['ELF'],DLL_sha256=sha(FW/'host/meter_landmark_reader.dll'),raw=build['raw'],sources_bound=build['source_sha256'],calibration=dict(source_sha256=sha(fitp),measurements=65,groups=['D','E','F'],Q16=q16,permission_extension_acknowledged=True,clamping=False),G_replay=dict(scalar_checks=scalar,old_domain26_values_preserved_exactly=preserved,new_model_rejected=True,selected_outputs=29,selected_within_descriptive_halfpsi=28,selected_over_halfpsi_ids=['G_042']),training=dict(one8000_step=True,source_train295_groups=['A','B','D','E','F'],G_only_step_selection=True,expanded_not_selected=True),memory=dict(TCM_bytes=49152,gap_bytes=1072,stack_reserved=2048,static_conservative_stack=1584,watermark_measured=False),scope=dict(C_H_opened=False,new_images_read=False,neural_forward_invocations=0,device_actions=False,own_label_gold_certified=False),remaining=['Freeze exactselectedELF/DLL/cal/thresholds beforeoneCtest; no postCselect/retrain','17bitPSIheldbundleSDCamendment/physicalFINAL/bitpair independentlypending','No boardMCUcycles/FlashXIPthroughput/coldboot/CSIautoROIequivalence evidence','G reuseddevelopment; three negativecases cannot establishlowFAR; .5psi descriptive not useraccuracytarget'],bindings={str(p.relative_to(ROOT)):sha(p)for p in [TASK/'final_model_selection_before_G.json',TASK/'final_selection.json',TASK/'calibration_domain.json',TASK/'firmware/host_matrix/validation_matrix.json',FW/'completion.json',FW/'host/calibration_replay_receipt.json',TASK/'model/run_001/training_receipt.json']})
(HERE/'independent_software_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8');print(json.dumps({k:v for k,v in report.items()if k not in['sources_bound','bindings']},ensure_ascii=False,indent=2))
