"""Read actual ELF instructions/flags and compiler contract; no device use."""
from pathlib import Path
import argparse,hashlib,json,re,struct
HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--build',type=Path,default=HERE/'build');ap.add_argument('--out',type=Path,default=HERE/'boot_numeric_contract.json');args=ap.parse_args()
    b=args.build;elf=b/'meter_landmark_reader.elf';data=elf.read_bytes();h=struct.unpack_from('<16sHHIIIIIHHHHHH',data)
    assert h[0][:7]==b'\x7fELF\x01\x01\x01'and h[2]==243 and h[4]==0x20e00000
    assert (h[7]&6)==2,'ActualELFmustdeclareRISC-VsinglefloatABI'
    found=None
    for i in range(h[10]):
        kind,off,va,pa,fs,ms,flags,al=struct.unpack_from('<IIIIIIII',data,h[5]+i*h[9])
        if kind==1 and va<=h[4]<va+fs:
            init=data[off+h[4]-va:off+h[4]-va+540]
            signature=bytes.fromhex('99 62 73 a0 02 30 73 10 30 00')
            p=init.find(signature);assert p>=0
            # c.lui t0,6:rd5/imm6, then CSRRS mstatus,x5 and CSRRWfcsr,x0.
            ins=struct.unpack_from('<H',init,p)[0];rd=(ins>>7)&31;imm=((ins>>2)&31)|(((ins>>12)&1)<<5)
            assert rd==5 and imm==6
            assert struct.unpack_from('<I',init,p+2)[0]==0x3002a073
            assert struct.unpack_from('<I',init,p+6)[0]==0x00301073
            found=h[4]+p
    assert found is not None
    symbols={v[2]:int(v[0],16)for s in (b/'symbols.stdout').read_text(errors='replace').splitlines()if len(v:=s.split())==3}
    assert symbols['_sp']==0x0800c000 and symbols['_sp']%16==0
    dis=(b/'disassembly.stdout').read_text(errors='replace')
    m=re.search(r'^[0-9a-f]+ <reader_polar>:\n(.*?)(?=\n[0-9a-f]+ <|\Z)',dis,re.M|re.S);assert m
    body=m[1];assert 'fmul.s' in body and 'fadd.s' in body
    fma=re.findall(r'\b(?:fmadd|fmsub|fnmadd|fnmsub)\.[sd]\b',body);assert not fma
    commands=json.loads((b/'commands.json').read_text('utf-8-sig'))
    comp=next(x['argv']for x in commands if x['name']=='compile_reader_numeric')
    assert '-ffp-contract=off'in comp and not any(x in ['-ffast-math','-Ofast']for x in comp)
    assert '-mabi=ilp32f'in comp and any(x.startswith('-march=rv32imafc')for x in comp)
    proof=dict(status='ACTUAL_ELF_FPU_START_AND_POLAR_ROUNDING_CONTRACT_PASS',ELF_path=str(elf),ELF_sha256=sha(elf),ELF_flags=h[7],ABI='ILP32F',stack_top=symbols['_sp'],stack_alignment=16,FPU=dict(enable_address=found,compressed_lui='0x6299 x5=0x6000',set_FS_instruction='0x3002a073 CSRRS mstatus,x5',result_FS_bits='11 Dirty beforemain',FCSR_instruction='0x00301073 CSRRW fcsr,x0',rounding='frm0 nearest-even;fflags0'),polar_F32=dict(fp_contract='off',fast_math=False,fmul_count=body.count('fmul.s'),fadd_count=body.count('fadd.s'),fused_FMA_count=len(fma),machinecode_sha256=sha(b/'disassembly.stdout')),source_scope='OfficialSDKstartup reused, no newFPUprotectionlayers',new_board_execution=False,hardware_actions=False)
    args.out.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps(proof,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
