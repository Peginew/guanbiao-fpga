"""Review v2 initialization repair; actual training pixels, zero optimizer steps."""
from pathlib import Path
import ast
import hashlib
import importlib.util
import json
import numpy as np
import torch

HERE=Path(__file__).resolve().parent
TASK=HERE.parent

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
    checks=[]
    def check(ok,name):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    original=TASK/'train_grouped.py';candidate=TASK/'train_grouped_v2.py'
    a=ast.parse(original.read_text('utf-8'));b=ast.parse(candidate.read_text('utf-8'))
    ac=next(n for n in a.body if isinstance(n,ast.ClassDef) and n.name=='Direct')
    bc=next(n for n in b.body if isinstance(n,ast.ClassDef) and n.name=='Direct')
    ai=next(n for n in ac.body if isinstance(n,ast.FunctionDef) and n.name=='__init__')
    bi=next(n for n in bc.body if isinstance(n,ast.FunctionDef) and n.name=='__init__')
    check(len(bi.body)==len(ai.body)+3,'only_three_initialization_statements_added')
    # Normalizing only Direct.__init__ and initialization provenance must recover
    # the original complete AST: no forward, loss, data or policy changes.
    for i,n in enumerate(bc.body):
        if n is bi:bc.body[i]=ai
    class Normalize(ast.NodeTransformer):
        def visit_Constant(self,node):
            if node.value=='scratch_kaiming_relu_fuse_positive_head_prior_v2':return ast.copy_location(ast.Constant(value='scratch'),node)
            return node
    b=Normalize().visit(b)
    check(ast.dump(a,include_attributes=False)==ast.dump(b,include_attributes=False),'all_other_AST_operators_data_masks_and_thresholds_unchanged')
    v1=module('v1_initreview',original);v2=module('v2_initreview',candidate);adapter=module('adapter_initreview',TASK/'roi_adapter.py')
    pre=json.loads((TASK/'initialization_fix_preflight.json').read_text('utf-8'))
    source=adapter.load_prepared(TASK/'prepared_train.jsonl');byid={r['id']:r for r in source}
    records=[byid[i] for i in pre['source_ids']]
    check(len(records)==21 and all(r['source_group'] in 'DEF' and r['split']=='train' for r in records),'actual_21_train_only_ROIs')
    v2.setup(1102,2);model=v2.Direct(4)
    x=torch.from_numpy(np.stack([(adapter.read_roi(r).astype(np.float32)-128)[None]/128 for r in records]))
    targets=[adapter.build_targets(r) for r in records]
    target=torch.from_numpy(np.stack([t[0] for t in targets]));mask=torch.from_numpy(np.stack([t[1] for t in targets]))
    observed={}
    def hook(layer,args,out):observed['fuse']=out.detach().clone()
    handle=model.fuse.register_forward_hook(hook)
    logits=model(x);handle.remove()
    fractions=(observed['fuse']>0).float().mean((0,2,3)).numpy()
    check((fractions>0).all(),'all_four_fuse_channels_have_positive_support')
    check(float(logits.detach().std((2,3)).min())>0,'actual_heads_not_spatially_constant')
    loss=v2.masked_loss(logits,target,mask);loss.backward()
    grad={n:int(p.grad.count_nonzero()) for n,p in model.named_parameters()}
    check(all(v>0 for v in grad.values()),'point_loss_backpropagates_to_all_parameter_tensors')
    old=v1.Direct(4);old.load_state_dict(model.state_dict())
    with torch.inference_mode():check(torch.equal(old(x),model(x)),'same_loaded_weights_forward_bit_equal_original_architecture')
    report=dict(status='PASS_INITIALIZATION_REPAIR_ADMISSION_NO_OPTIMIZER',checks=len(checks),failures=[],
        candidate_sha256=sha(candidate),original_sha256=sha(original),
        prepared_train_sha256=sha(TASK/'prepared_train.jsonl'),prepared_validation_sha256=sha(TASK/'prepared_validation.jsonl'),
        roi_adapter_sha256=sha(TASK/'roi_adapter.py'),source_ids=pre['source_ids'],
        fuse_positive_fraction_by_channel=fractions.tolist(),minimum_output_spatial_std=float(logits.detach().std((2,3)).min()),
        gradient_nonzero_counts=grad,parameter_count=sum(p.numel() for p in model.parameters()),
        root_authorized_next_action='Execute isolated run_002, same 2400 steps and data/mask/metrics; no H or board access',
        real_optimizer_steps=0,test_H_pixels_or_labels_opened=False,original_run001_preserved=True,
        limitation='Nonzero initialization gradients do not guarantee final training quality; run002 remains subject to effect review')
    (HERE/'initialization_fix_admission.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n','utf-8')
    print(json.dumps(report,ensure_ascii=False))

if __name__=='__main__':main()
