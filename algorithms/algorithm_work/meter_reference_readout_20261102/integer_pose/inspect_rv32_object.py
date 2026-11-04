"""Read an already compiled new matcher object; no application link/device use."""
from pathlib import Path
import hashlib,json,re,subprocess

HERE=Path(__file__).resolve().parent;BUILD=HERE/'rv32_build'
TOOLS=Path('C:/Anlogic/FD_2026.2/toolchain/gcc/riscv/ph1p35/bin')

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def run(exe,*args):
    command=[str(TOOLS/exe),*map(str,args)]
    cp=subprocess.run(command,capture_output=True,creationflags=0x08000000)
    def decode(raw):
        try:return raw.decode('utf-8')
        except UnicodeDecodeError:return raw.decode('gb18030')
    if cp.returncode:raise RuntimeError(decode(cp.stderr))
    return command,decode(cp.stdout),decode(cp.stderr)

def main():
    obj=BUILD/'meter_pose_matcher.o';data=obj.read_bytes()
    assert data[:4]==b'\x7fELF'and data[4]==1 and int.from_bytes(data[18:20],'little')==243
    scmd,size,serr=run('riscv64-unknown-elf-size.exe','-A','-d',obj)
    ncmd,undefined,nerr=run('riscv64-unknown-elf-nm.exe','-u',obj)
    sections={}
    for line in size.splitlines():
        m=re.match(r'^(\.[^\s]+)\s+(\d+)\s+\d+\s*$',line)
        if m:sections[m[1]]=int(m[2])
    stack={}
    for line in(BUILD/'meter_pose_matcher.su').read_text('utf-8-sig').splitlines():
        fields=line.split('\t');stack[fields[0].rsplit(':',1)[-1]]=dict(bytes=int(fields[1]),kind=fields[2])
    text=sum(v for k,v in sections.items()if k.startswith('.text'))
    rodata=sum(v for k,v in sections.items()if k.startswith(('.rodata','.srodata')))
    bss=sum(v for k,v in sections.items()if k.startswith(('.bss','.sbss')))
    data_bytes=sum(v for k,v in sections.items()if k.startswith(('.data','.sdata')))
    unresolved=[line.split()[-1]for line in undefined.splitlines()if line.strip()]
    assert text==1548 and rodata==0 and bss==0 and unresolved==['memset']
    receipt=dict(status='RV32IMAC_C99_OBJECT_COMPILED_NOT_APPLICATION_LINKED',
        compiler=str(TOOLS/'riscv64-unknown-elf-gcc.exe'),
        compile_flags=['-march=rv32imac','-mabi=ilp32','-std=c99','-O2','-ffreestanding','-ffunction-sections','-fdata-sections','-fstack-usage','-Wall','-Wextra','-Werror','-c'],
        compile_exit=0,compile_stderr='',ELFclass=32,ELFmachine='RISC-V243',
        text_bytes=text,rodata_bytes=rodata,data_bytes=data_bytes,bss_bytes=bss,
        object_file_bytes=obj.stat().st_size,nonalloc_metadata_bytes=sum(sections.values())-text-rodata-data_bytes-bss,
        stack_usage=stack,max_individual_function_static_frame_bytes=max(v['bytes']for v in stack.values()),
        undefined_symbols=unresolved,unresolved_libgcc_or_float_helpers=[],
        caller_owned_working_storage=dict(context_bytes=1104,query_profile_bytes=4320,
            frozen_template_values_bytes=3234,frozen_template_U16_indices_bytes=6468,
            local_shift_tables_S16_bytes=2*49*2,
            context_excludes_templates_profiles_and_frontend=True),
        limits=['0objectBSS means context/profile storage is supplied by caller, not zero workspace.',
            'Static stack frame96bytes excludes caller, interrupt and unresolvedmemset implementations; not measured stack watermark.',
            'Actual whole48KiBMCU application with rawROI frontend,newhub/polar,PSI andownership is NOT linked.',
            'No MCU cycles, board fit, software recognition deployment, Flash or device action is claimed.',
            'Exact-rational thresholds are matched to frozenkeep1307/1280; generickeep125 IEEE cancellation edge is documented separately.'],
        sources_sha256={p.name:sha(p)for p in[HERE/'meter_pose_matcher.c',HERE/'meter_pose_matcher.h',obj,BUILD/'meter_pose_matcher.su',Path(__file__)]},
        inspection_commands=[scmd,ncmd],model_training=False,application_link=False,hardware_actions=False)
    (BUILD/'size.stdout.log').write_text(size,'utf-8');(BUILD/'nm_undefined.stdout.log').write_text(undefined,'utf-8')
    (BUILD/'rv32_object_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({k:receipt[k]for k in['status','text_bytes','rodata_bytes','bss_bytes','max_individual_function_static_frame_bytes','undefined_symbols']},indent=2))

if __name__=='__main__':main()
