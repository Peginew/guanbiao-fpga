"""Inspect only the new Q5-input C frontend object; no full application link."""
from pathlib import Path
import json,re,sys
sys.dont_write_bytecode=True
from inspect_rv32_object import run,sha

HERE=Path(__file__).resolve().parent;BUILD=HERE/'rv32_build'

def main():
    obj=BUILD/'meter_pose_frontend.o';raw=obj.read_bytes()
    assert raw[:4]==b'\x7fELF'and raw[4]==1 and int.from_bytes(raw[18:20],'little')==243
    scmd,size,_=run('riscv64-unknown-elf-size.exe','-A','-d',obj)
    ncmd,undefined,_=run('riscv64-unknown-elf-nm.exe','-u',obj)
    sections={}
    for line in size.splitlines():
        m=re.match(r'^(\.[^\s]+)\s+(\d+)\s+\d+\s*$',line)
        if m:sections[m[1]]=int(m[2])
    stack={}
    for line in(BUILD/'meter_pose_frontend.su').read_text('utf-8-sig').splitlines():
        fields=line.split('\t');stack[fields[0].rsplit(':',1)[-1]]=dict(bytes=int(fields[1]),kind=fields[2])
    text=sum(v for k,v in sections.items()if k.startswith('.text'))
    assert text==1320 and not undefined.strip()
    receipt=dict(status='RV32IMAC_Q5_INPUT_PIXEL_PROFILE_FRONTEND_OBJECT_COMPILED_NOT_LINKED',
        scope=['replicate9x9localcontrast','Q5bilinearconstantborder128','signedrationalRNEprofile'],
        compile_exit=0,compile_stderr='',
        compiler='C:/Anlogic/FD_2026.2/toolchain/gcc/riscv/ph1p35/bin/riscv64-unknown-elf-gcc.exe',
        compile_flags=['-march=rv32imac','-mabi=ilp32','-std=c99','-O2','-ffreestanding','-ffunction-sections','-fdata-sections','-fstack-usage','-Wall','-Wextra','-Werror','-c'],
        text_bytes=text,rodata_bytes=0,data_bytes=0,bss_bytes=0,object_file_bytes=obj.stat().st_size,
        undefined_symbols=[],unresolved_libgcc_or_float_helpers=[],stack_usage=stack,
        max_individual_function_static_frame_bytes=max(v['bytes']for v in stack.values()),
        fused_profile_known_internal_call_chain_bytes=48,
        caller_owned_storage=dict(normalizer_workspace_bytes=1408,fused_profile_workspace_bytes=360,
            normalized_U8_image_bytes=16384,output_S8_profile_bytes=4320,
            full_Q5_xy_coordinate_tables_S16_bytes=2*4320*2,
            all_caller_storage_is_not_newly_allocated_here=True),
        coordinate_generation_implemented=False,outside_predicate_implemented=False,
        pending=['Float-derivedQ5tables/hubradius/outside predicate are supplied, not all-integergeometry.',
            'RawROI ownership and normalized-image/scratch reuse must be planned in real application.',
            'Caller tables and profile/template storage do not disappear because objectBSSis0.',
            'No fullhub+polar+pose+psi C application link, measuredstack, MCUcycles orboardvalidation.'],
        source_sha256={p.name:sha(p)for p in[HERE/'meter_pose_frontend.c',HERE/'meter_pose_frontend.h',
            HERE/'pose_frontend.py',HERE/'inspect_rv32_object.py',obj,BUILD/'meter_pose_frontend.su',Path(__file__)]},
        inspection_commands=[scmd,ncmd],training=False,full_application_link=False,hardware_actions=False)
    (BUILD/'frontend_size.stdout.log').write_text(size,'utf-8')
    (BUILD/'frontend_nm_undefined.stdout.log').write_text(undefined,'utf-8')
    (BUILD/'rv32_frontend_object_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({k:receipt[k]for k in['status','text_bytes','undefined_symbols','max_individual_function_static_frame_bytes']},indent=2))

if __name__=='__main__':main()
