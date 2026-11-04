"""Offline readonly tables from the frozen polar/ring assets; no training."""
from pathlib import Path
import hashlib,json,math
import numpy as np
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SRC=HERE/'source'
POSE=ROOT/'algorithm_work/meter_reference_readout_20261102/integer_pose'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def arr(typ,name,a):
    vals=[]
    for x in np.asarray(a).ravel():
        vals.append(float(x).hex()+('f' if typ=='float' else '') if typ in ('float','double') else str(int(x)))
    return f'static const {typ} {name}[]={{'+','.join(vals)+'};\n'
def main():
    z=np.load(POSE/'fixtures/templates.npz')
    print('template keys',z.files)
    text='#ifndef READER_TABLES_H\n#define READER_TABLES_H\n#include <stdint.h>\n'
    theta=np.arange(360,dtype=np.float32)*(np.pi/180)
    text+=arr('float','reader_cos_f32',np.cos(theta))+arr('float','reader_sin_f32',np.sin(theta))
    theta64=np.arange(360)*np.pi/180
    text+=arr('double','reader_cos_f64',np.cos(theta64))+arr('double','reader_sin_f64',np.sin(theta64))
    text+=arr('int32_t','reader_cos_q30',np.rint(np.cos(theta64)*(1<<30)))+arr('int32_t','reader_sin_q30',np.rint(np.sin(theta64)*(1<<30)))
    text+=arr('double','reader_ring_fractions',np.linspace(.4,.88,12))
    text+=arr('float','reader_polar_fractions',np.linspace(.20,.84,8,dtype=np.float32))
    sig=arr('uint16_t','reader_sigmoid_q15',np.rint(32767/(1+np.exp(-np.arange(-128,128)/16)))).replace('static const','const',1)
    (SRC/'reader_sigmoid.c').write_text('#include <stdint.h>\n'+sig,'ascii')
    text+='extern const uint16_t reader_sigmoid_q15[256];\n'
    text+='\n#endif\n';(SRC/'reader_tables.h').write_text(text,'ascii')
    # Keep the exact previously signed indices/shifts; no template regeneration.
    body='#ifndef READER_RING_TEMPLATES_H\n#define READER_RING_TEMPLATES_H\n#include "meter_pose_matcher.h"\n'
    for ti in range(2):
        for suffix,typ in [('indices','uint16_t'),('values','int8_t'),('local_shift','int16_t')]:
            candidates=[f'{suffix}_{ti}',f'{suffix}{ti}',f't{ti}_{suffix}',f'{ti}_{suffix}',f'shifts_{ti}' if suffix=='local_shift' else '']
            key=next((x for x in candidates if x in z.files),None)
            if key is None:raise ValueError((suffix,ti,z.files))
            body+=arr(typ,f'ring_{suffix}_{ti}',z[key])
    body+='static const mp_template reader_templates[2]={\n'
    for i in range(2):body+=f'{{ring_indices_{i},ring_values_{i},ring_local_shift_{i},sizeof(ring_values_{i})}},\n'
    body+='};\n#endif\n';(SRC/'reader_ring_templates.h').write_text(body,'ascii')
    (HERE/'assets_receipt.json').write_text(json.dumps({'source_templates':str(POSE/'fixtures/templates.npz'),'source_sha256':sha(POSE/'fixtures/templates.npz'),'generated':{p.name:sha(p)for p in [SRC/'reader_tables.h',SRC/'reader_ring_templates.h']},'scope':'Readonly tables only, no firmware execution or MCU cycle claim'},indent=2))
if __name__=='__main__':main()
