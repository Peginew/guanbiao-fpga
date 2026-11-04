"""Read-only rescoring of already produced C predictions; no forward/device."""
from pathlib import Path
from datetime import datetime
import hashlib,json,math
HERE=Path(__file__).resolve().parent;TASK=HERE.parent;TEST=TASK/'firmware_final_test'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(Path(p).read_text('utf-8-sig'))
checks=0
def ck(x,m):
 global checks
 assert x,m
 checks+=1
manifest_path=TEST/'FINAL_FROZEN_SELECTED.json';m=load(manifest_path);marker=load(TEST/'C_TEST_ONCE.json');report_path=TEST/'FINAL_C_ONCE/final_C_evaluation.json';report=load(report_path)
ck(sha(manifest_path)==marker['manifest_sha256']==report['manifest_sha256']=='9df9e85087bb36269ab42ce26673d7e6c58b3b3b93f8b7a8c4b20bbe5514cfc1','FrozenManifest')
ck(marker['status']=='COMPLETED'and sha(report_path)==marker['report_sha256'],'CompletedMarkerReportIdentity')
ck(datetime.fromisoformat(m['root_release_UTC'])<datetime.fromisoformat(marker['started_UTC'])<datetime.fromisoformat(marker['completed_UTC']),'ReleaseBeforeEvaluation')
ck(sha(TEST/'run_locked_C.py')==m['harness_sha256']==report['harness_sha256'],'HarnessFreeze')
for k in ['canonical','roi_adapter','ELF','DLL','build_receipt','selection_policy_before_G','selection_decision_before_C','independent_software_review']:
 ck(sha(m[k]['path'])==m[k]['sha256'],'Artifact:'+k)
for a in m['frozen_model_and_calibration_artifacts']:ck(sha(a['path'])==a['sha256'],'ModelCalibration:'+a['role'])
ck(report['ELF_sha256']==m['ELF']['sha256']and report['DLL_sha256']==m['DLL']['sha256'],'SelectedMachineIdentity')
ck(m['selected_point_model']==marker['selected_point_model']==report['selected_point_model']=='PRIOR_B857','SinglePriorCandidate')
predp=TEST/'FINAL_C_ONCE/predictions_before_scoring.jsonl';pred=[json.loads(x)for x in predp.read_text('utf8').splitlines()if x.strip()]
canonical=load(m['canonical']['path']);truth={r['id']:r for r in canonical['records']if r['group']=='C'}
ck(len(pred)==len(truth)==59 and {p['id']for p in pred}==set(truth)and len({p['id']for p in pred})==59,'CompleteC59Unique')
ck(pred==report['rows'],'PredictionsPersistedUnchanged')
ck(all('pressure'not in p and 'reference_psi'not in p for p in pred),'NoPressureInInferenceRows')
roi_log={x['id']:x for x in report['ROI_log']};ck(set(roi_log)==set(truth),'SameROI59Log')
for p in pred:
 t=truth[p['id']]
 ck(p['source_sha256']==t['sha256'],'SourceNativeSHA')
 ck(p['ROI_request']==roi_log[p['id']]['request'],'SharedROIRequest')
 ck(len(roi_log[p['id']]['ROI_sha256'])==64,'InputROIHashRecorded')
 if p['ring']['accepted']:ck(p['selected_reference_kind']==1,'OldReferenceFirst')
 if p['integer_ring_only']['valid']:
  ck(p['trained_sixpoint_fusion']==p['integer_ring_only'],'OldValueAndValidityPreserved')
 if t['target_present']:ck(t['pressure']['unit']=='psi'and t['pressure']['value']is not None,'CanonicalDirectPSI')
summary={}
for key in ['integer_ring_only','trained_sixpoint_fusion']:
 gauges=[p for p in pred if truth[p['id']]['target_present']];neg=[p for p in pred if not truth[p['id']]['target_present']];valid=[p for p in gauges if p[key]['valid']]
 errors=[(p['id'],abs(p[key]['psi']-float(truth[p['id']]['pressure']['value'])))for p in valid]
 v=dict(total_rows=59,gauges=len(gauges),negative=len(neg),gauge_outputs=len(valid),gauge_rejected=len(gauges)-len(valid),negative_outputs=sum(bool(p[key]['valid'])for p in neg),pressure_evaluable_outputs=len(errors),output_without_known_pressure=0,MAE_psi=sum(e for _,e in errors)/len(errors),error_bands=[dict(absolute_error_max_psi=b,count=sum(e<=b for _,e in errors),over_ids=[i for i,e in errors if e>b])for b in [.25,.5,1.]],output_ids=[p['id']for p in valid],all_gauges_are_denominator=True)
 ck(v==report['summary'][key],'IndependentStatistics:'+key);summary[key]=v
oldids=set(summary['integer_ring_only']['output_ids']);newids=set(summary['trained_sixpoint_fusion']['output_ids']);added=[]
for p in pred:
 if p['id']in newids-oldids:
  t=truth[p['id']];added.append(dict(id=p['id'],target_present=t['target_present'],psi=p['trained_sixpoint_fusion']['psi'],absolute_error_psi=abs(float(t['pressure']['value'])-p['trained_sixpoint_fusion']['psi'])))
ck(added==report['new_fusion_outputs'],'TwelveAddedExact')
ck(not(oldids-newids)and report['withdrawn_old_integer_outputs']==[],'NoOldWithdrawals')
ck(len(oldids)==19 and len(newids)==31 and len(added)==12,'19to31')
ck(all(p['absolute_error_psi']<=.5 for p in added),'NoAddedOverDescriptiveHalf')
ck(len([p for p in pred if not truth[p['id']]['target_present']])==3,'OnlyThreeNegatives')
source=(TEST/'run_locked_C.py').read_text('utf8')
ck("ONCE.open('x'"in source and source.index("ONCE.open('x'")<source.index('canonical_path=check_artifact'),'ExclusiveMarkerBeforeCRead')
ck(all(bool(p['psi_word']>>31)==p['trained_sixpoint_fusion']['valid'] and (not p['trained_sixpoint_fusion']['valid'] or (p['psi_word']&65535)/256==p['trained_sixpoint_fusion']['psi'])for p in pred),'PSIWordSameSourceConsistency')
ck(source.index("(out/'predictions_before_scoring.jsonl')")<source.index('summaries={key:summarize'),'PredictionsBeforePressureScoring')
ck('infer_one(lib,roi,request[\'radius\'])'in source and 'check_artifact(m[\'canonical\'])'in source,'OnlyROIAndRadiusInferenceArguments')
# This audit does not run the C consumer, import the model, or open any PNG.
out=dict(status='INDEPENDENT_FINAL_C_EXISTING_PREDICTIONS_RESCORE_PASS',checks=checks,manifest_sha256=sha(manifest_path),ELF_sha256=m['ELF']['sha256'],DLL_sha256=m['DLL']['sha256'],canonical_sha256=sha(m['canonical']['path']),prediction_sha256=sha(predp),report_sha256=sha(report_path),marker_sha256=sha(TEST/'C_TEST_ONCE.json'),summary=summary,improvement=dict(old_outputs=19,new_outputs=31,added=12,withdrawn=0,all_old19_values_preserved_exactly=True,new_over_descriptive_halfpsi=0),scope=dict(existing_C_evaluation_only=True,new_forward_invocations=0,PNG_images_opened=0,H_rows_selected=False,training_or_threshold_modified=False,device_actions=False),interpretation=['Onefrozencandidate/sameCconsumer/sharedROIandradius; comparator isinteger-ringonly underSAMEcorrectedTRAINdomain,notoldfloat/nativeSIFT','Full59denominator=56gauge+3negative;31/56read,25gaugereject;MAEonly31accepted','0/3negativeoutputsdoesnotproveindustrialFAR; .25/.5/1psi descriptivebandsnotuseraccuracycontract','CpreviouslyexposedannotationQA acknowledged; nohumanblindgoldclaim;truthinstrumentprecisionunknown','Manualbbox/HDMIproxyinput and hostCexecution; notphysicalMCU/MMIO/CSI/boardacceptance','NoCfeedbacktraining/tuning/reselectionafterthisresult'],source_bindings={str(p):sha(p)for p in [manifest_path,TEST/'C_TEST_ONCE.json',TEST/'run_locked_C.py',predp,report_path]})
(HERE/'final_C_review.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n','utf8');print(json.dumps({k:v for k,v in out.items()if k not in ['source_bindings','summary']},ensure_ascii=False,indent=2))
