"""Rebuild the frozen trained reader with only the guarded-MMIO repair.

Replays actual frozen compiler/link flags into isolated source/output paths.
No model generation/training or device access. Old artifacts are never written.
"""
from pathlib import Path
import hashlib, json, shutil, struct, subprocess, sys

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
BASE=ROOT/'meter_landmark_expanded_20261103/firmware_prior_domain'
SRC=HERE/'source'
OUT=HERE/'build'
FLASH=0x20e00000
TCM=0x08000000

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf-8')

def main():
    assert sha(BASE/'build/meter_landmark_reader.elf')=='7b582ce32365dc6e326c03da562ca1c94ba7cc66d99742aa21256d61cdb2b9bc'
    changed=[p.name for p in SRC.iterdir() if p.is_file() and p.read_bytes()!=(BASE/'source'/p.name).read_bytes()]
    assert sorted(changed)==['minimal_app.c','mroi_client.c','mroi_client.h','mroi_guard.S']
    OUT.mkdir(exist_ok=True)
    for name in ['nuclei_startup.o','nuclei_intexc.o','al_chip.o']:
        shutil.copy2(BASE/'build'/name,OUT/name)
    commands=[]
    def mapped(v):
        v=v.replace('\\\\','\\')
        return v.replace(str(BASE/'source'),str(SRC)).replace(str(BASE/'build'),str(OUT))
    for old in json.loads((BASE/'build/commands.json').read_text('utf-8-sig')):
        if old['name']=='boot_numeric_contract':continue
        argv=[mapped(v) for v in old['argv']]
        p=subprocess.run(argv,capture_output=True)
        (OUT/(old['name']+'.stdout')).write_bytes(p.stdout)
        (OUT/(old['name']+'.stderr')).write_bytes(p.stderr)
        commands.append({'name':old['name'],'argv':argv,'exit_code':p.returncode})
        write(OUT/'commands.json',commands)
        if p.returncode:raise RuntimeError((old['name'],p.stderr.decode(errors='replace')))
    elf=OUT/'meter_landmark_reader.elf';raw=elf.with_suffix('.bin')
    data=elf.read_bytes();h=struct.unpack_from('<16sHHIIIIIHHHHHH',data)
    syms={v[2]:int(v[0],16) for line in (OUT/'symbols.stdout').read_text().splitlines() if len(v:=line.split())==3}
    assert h[4]==FLASH and syms['_sp']==TCM+49152 and syms['__StackLimit']==TCM+49152-2048
    assert syms['_end']<=syms['__StackLimit']
    image=raw.read_bytes();assert len(image)<=65536
    loads=[]
    for i in range(h[10]):
        t,off,va,pa,fs,ms,fl,al=struct.unpack_from('<IIIIIIII',data,h[5]+i*h[9])
        if t==1:
            loads.append(dict(vaddr=va,paddr=pa,filesz=fs,memsz=ms,offset=off,flags=fl))
            if fs:
                assert FLASH<=pa<pa+fs<=FLASH+len(image)
                assert image[pa-FLASH:pa-FLASH+fs]==data[off:off+fs]
    payload=OUT/'U33_E00000_E0FFFF_reader_payload.bin'
    payload.write_bytes(image+b'\xff'*(65536-len(image)))
    observed_symbols=['mroi_guard_load_pc','mroi_guard_load_wait_pc','mroi_guard_store_pc','mroi_guard_store_wait_pc','mroi_guard_load_recover','mroi_guard_store_recover','mroi_exception_mepc','mroi_fault','mroi_diag','mroi_reader_diag','mroi_cold_boot_diag','mroi_live']
    proof={'status':'GUARDED_MMIO_REPAIR_REAL_BUILD_OFFLINE_NOT_BOARD_VALIDATED','entry':h[4],
           'base_ELF_sha256':sha(BASE/'build/meter_landmark_reader.elf'),
           'ELF':{'path':str(elf),'sha256':sha(elf),'bytes':elf.stat().st_size},
           'raw':{'path':str(raw),'sha256':sha(raw),'bytes':len(image)},
           'payload':{'path':str(payload),'sha256':sha(payload),'bytes':65536,'Flash_offset':0xe00000},
           'TCM':{'bytes':49152,'end':syms['_end'],'stack_limit':syms['__StackLimit'],'stack_bytes':2048,'gap':syms['__StackLimit']-syms['_end']},
           'symbols':{s:syms[s] for s in observed_symbols},'loads':loads,'changed_sources':changed,
           'source_sha256':{p.name:sha(p) for p in SRC.iterdir() if p.is_file()},
           'trained_weights_exact_old':{p.name:sha(p) for p in SRC.glob('*weights*')},
           'training':False,'device':False,'Flash_write':False,'TCM_write':False,
           'ABI':'Original ROI/PSI feature ABI and all reader mathematics preserved'}
    write(OUT/'build_receipt.json',proof)
    subprocess.run([sys.executable,str(BASE/'verify_boot_numeric_contract.py'),'--build',str(OUT),'--out',str(HERE/'boot_numeric_contract.json')],check=True,capture_output=True)
    print(json.dumps({'ELF':proof['ELF'],'payload':proof['payload'],'TCM':proof['TCM'],'symbols':proof['symbols']},indent=2))

if __name__=='__main__':main()
