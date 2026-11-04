"""Actual offline RV32 ELF/bin build:48KiBTCM and one64KiB app sector.

Every referenced model must already exist. No fake weights, virtual RAM, board
operations or re-use of a historical ELF as the new deliverable.
"""
from pathlib import Path
import hashlib,json,shutil,struct,subprocess,zlib
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];SRC=HERE/'source';OUT=HERE/'build'
BASE=Path('C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_flash_final_20261031/mcu_boot/flash_tcm20e_candidate_20261101_040529_172170')
TOOL=Path('C:/Anlogic/FD_2026.2/toolchain/gcc/riscv/ph1p35/bin');FLASH=0x20e00000;TCM=0x08000000
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf-8')
def prepare():
    assert sha(BASE/'mroi_flash_tcm20e.elf')=='fea81904b304dce91ba6b868a86be1d1ad38f1b19cda78edf866ebc29ba52661'
    for name in ['soc_plat.c','soc_plat.h','platform_binding.c','platform_binding.h','mroi_guard.S','al_rv32_start_flash_tcm.S']:
        target=SRC/name
        if not target.exists():shutil.copy2(BASE/'source'/name,target)
    target=SRC/'minimal_app.c'
    if not target.exists():
        s=(BASE/'source/minimal_app.c').read_text()
        s=s.replace('#include "mroi_direct_cnn.h"\n#include "mroi_sparse_hybrid.h"','#include "reader_runtime.h"')
        s=s.replace('mroi_hybrid_bind(&io)','mroi_reader_bind(&io)').replace('&mroi_hybrid_stage','&mroi_reader_stage')
        target.write_text(s,'ascii')
    ld=(BASE/'source/gcc_ph1p35_flash_unified_tcm.ld').read_text().replace('LENGTH = 1M','LENGTH = 64K')
    # Explicitly mapped physical QSPI memory already used for coldboot .init.
    # These sections are NOT copied into TCM. No new QSPI controller/IO used.
    objects=['mroi_c4','mroi_decode','reader_numeric','reader_runtime','meter_pose_frontend','meter_pose_matcher','landmark_geometry']
    body='  .flash_runtime : ALIGN(8)\n  {\n'
    for n in objects:
        if n in ['mroi_c4','meter_pose_matcher']:continue
        body+=f'    *{n}.o(.text .text.*)\n'
        if n not in ['reader_runtime','reader_numeric','mroi_decode']:body+=f'    *{n}.o(.rodata .rodata.* .srodata .srodata.*)\n'
    body+='    *reader_numeric.o(.rodata.reader_cos_* .rodata.reader_sin_* .rodata.reader_ring_* .rodata.reader_polar_* .rodata.reader_templates .rodata.ring_*)\n'
    body+='    *libgcc.a:*(.text .text.* .rodata .rodata.* .srodata .srodata.*)\n    . = ALIGN(4);\n  } >flash AT>flash :flash_init\n\n'
    ld=ld.replace('  .config_settings          : ALIGN(4)',body+'  .config_settings          : ALIGN(4)',1)
    (SRC/'reader_flash_tcm.ld').write_text(ld,'ascii')
    return objects
def main():
    prepare();OUT.mkdir(exist_ok=True);commands=[]
    # Copy only actual trained exports, never synthesize or train here.
    model=HERE.parent/'model'
    for origin,name in [(model/'hub_integer/hub_weights.h','hub_weights_q8.h'),(model/'landmark_integer/landmark_weights.h','landmark_weights_q8.h')]:
        if not origin.exists():raise FileNotFoundError(f'Complete firmware awaits trained export: {origin}')
        shutil.copy2(origin,SRC/name)
    for name in ['landmark_geometry.c','landmark_geometry.h','landmark_reference.h']:shutil.copy2(HERE.parent/'runtime'/name,SRC/name)
    old=json.loads((BASE/'commands.json').read_text());startup=next(x['argv']for x in old if x['name']=='startup_compile')
    cc=str(TOOL/'riscv64-unknown-elf-gcc.exe')
    flags=startup[2:startup.index('-c')];flags=[str(SRC)if x==str(BASE/'source')else x for x in flags]
    flags+=['-ffp-contract=off','-fno-strict-aliasing']
    def run(name,args):
        p=subprocess.run(list(map(str,args)),capture_output=True);(OUT/(name+'.stdout')).write_bytes(p.stdout);(OUT/(name+'.stderr')).write_bytes(p.stderr)
        commands.append(dict(name=name,argv=list(map(str,args)),exit_code=p.returncode));write(OUT/'commands.json',commands)
        if p.returncode:raise RuntimeError((name,p.stderr.decode(errors='replace')))
        return p.stdout.decode(errors='replace')
    sources=['mroi_client.c','minimal_app.c','minimal_libc.c','mroi_guard.S','platform_binding.c','soc_plat.c','al_rv32_start_flash_tcm.S','mroi_c4.c','mroi_decode.c','reader_numeric.c','reader_runtime.c','reader_sigmoid.c','meter_pose_frontend.c','meter_pose_matcher.c','landmark_geometry.c']
    objects=[]
    for name in sources:
        obj=OUT/(Path(name).stem+'.o');extra=['-DVECTOR_TABLE_REMAPPED']if name=='al_rv32_start_flash_tcm.S'else[]
        run('compile_'+Path(name).stem,[cc,*flags,*extra,'-c',SRC/name,'-o',obj]);objects.append(obj)
    # Exact vendor startup/exception/configuration objects retained from realfea819.
    for name in ['nuclei_startup.o','nuclei_intexc.o','al_chip.o']:
        shutil.copy2(BASE/name,OUT/name);objects.append(OUT/name)
    elf=OUT/'meter_landmark_reader.elf';raw=elf.with_suffix('.bin');mapping=elf.with_suffix('.map')
    run('link',[cc,*flags,'-nostdlib','-nostartfiles',*objects,'-T',SRC/'reader_flash_tcm.ld','-Wl,--gc-sections','-Wl,-e,_start',f'-Wl,-Map={mapping}','-Wl,--defsym=__STACK_SIZE=2048','-Wl,--defsym=__HEAP_SIZE=0','-lgcc','-o',elf])
    run('objcopy',[TOOL/'riscv64-unknown-elf-objcopy.exe','-O','binary',elf,raw])
    nm=run('symbols',[TOOL/'riscv64-unknown-elf-nm.exe','-n',elf]);sym={v[2]:int(v[0],16)for s in nm.splitlines()if len(v:=s.split())==3}
    sections=run('sections',[TOOL/'riscv64-unknown-elf-size.exe','-A',elf]);run('segments',[TOOL/'riscv64-unknown-elf-readelf.exe','-lW',elf]);run('disassembly',[TOOL/'riscv64-unknown-elf-objdump.exe','-d',elf])
    data=elf.read_bytes();h=struct.unpack_from('<16sHHIIIIIHHHHHH',data);loads=[]
    for i in range(h[10]):
        t,off,va,pa,fs,ms,fl,al=struct.unpack_from('<IIIIIIII',data,h[5]+i*h[9])
        if t==1:loads.append(dict(vaddr=va,paddr=pa,filesz=fs,memsz=ms,offset=off,flags=fl))
    image=raw.read_bytes();assert h[4]==FLASH and sym['_sp']==TCM+49152 and sym['__StackLimit']==TCM+49152-2048
    assert len(image)<=65536 and sym['_end']<=sym['__StackLimit']
    memory=bytearray(49152);ranges=[]
    for l,v,e in [('_config_settings_load_start','_config_settings_vma_start','_config_settings_vma_end'),('_ilm_lma','_ilm','_eilm'),('_data_lma','_data','_edata')]:
        a,b,c=sym[l],sym[v],sym[e];assert FLASH<=a<=a+c-b<=FLASH+len(image) and TCM<=b<=c<=TCM+49152
        memory[b-TCM:c-TCM]=image[a-FLASH:a-FLASH+c-b];ranges.append(dict(lma=a,vma=b,bytes=c-b))
    for r in loads:
        if r['filesz']:
            a=r['paddr'];b=r['filesz'];assert FLASH<=a<a+b<=FLASH+len(image)
            assert image[a-FLASH:a-FLASH+b]==data[r['offset']:r['offset']+b]
            if TCM<=r['vaddr']<TCM+49152:assert memory[r['vaddr']-TCM:r['vaddr']-TCM+b]==data[r['offset']:r['offset']+b]
    package=bytearray(b'\xff'*65536);package[:len(image)]=image
    (OUT/'U33_E00000_E0FFFF_reader_payload.bin').write_bytes(package)
    record=dict(status='FULL_READER_ELF_LINKED_OFFLINE_NOT_BOARD_VALIDATED',entry=h[4],ELF=dict(path=str(elf),sha256=sha(elf)),raw=dict(path=str(raw),bytes=len(image),sha256=sha(raw),crc32=f'{zlib.crc32(image):08x}'),coldboot_sector=dict(path=str(OUT/'U33_E00000_E0FFFF_reader_payload.bin'),flash_offset=0xe00000,bytes=65536,sha256=hashlib.sha256(package).hexdigest(),policy='Dedicated sector224 replacement, requires matchedPSIfeaturebit. No device write by builder.'),loads=loads,startup_copy_ranges=ranges,TCM=dict(bytes=49152,bss_start=sym['__bss_start'],end=sym['_end'],stack_limit=sym['__StackLimit'],stack_bytes=2048,gap=sym['__StackLimit']-sym['_end'],arena_bytes=32768),source_sha256={p.name:sha(p)for p in SRC.iterdir()if p.is_file()},builder_sha256=sha(__file__),oldfea819_unchanged=sha(BASE/'mroi_flash_tcm20e.elf'),floating_point_evidence='OfficialDS1300Section2.14.1 RV32I/M/A/F/C/P/B; linker uses existingRV32ILP32F platform. Double uses libgcc explicitly counted.',new_Flash_XIP_access_cycle_validation=False,MCU_cycles=False,device=False,ABI='FEATURES0x064 bit0,PSI0x124 valid31/UQ8low16; originaltokenandRES1commit0x120',limitations=['No currentbitcompatibilityuntilnewPSIfeatureRTL','No device or same-sourceCSIgray validation','Hostsame-codePSImetricsandstackauditseparate'])
    write(OUT/'build_receipt.json',record);print(json.dumps({'raw_bytes':len(image),'TCM':record['TCM'],'elf_sha256':sha(elf)},indent=2))
if __name__=='__main__':main()
