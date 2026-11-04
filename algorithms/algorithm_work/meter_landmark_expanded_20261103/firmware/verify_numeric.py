"""Same-C numeric replay; uses existing train/G proxyROI, no devices or H."""
from pathlib import Path
import ctypes as C,hashlib,importlib.util,json,sys
import cv2,numpy as np
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE.parent/'model'))
import export_integer as q
sys.path.insert(0,str(ROOT/'algorithm_work/meter_pointer_readout_20261102/polar_angle'))
import quantize_polar as pq
import train_polar as pf
sys.path.insert(0,str(ROOT/'algorithm_work/meter_reference_readout_20261102/integer_pose'))
import pose_frontend as front
import verify_matcher as matcher
class Point(C.Structure):_fields_=[('x',C.c_int32),('y',C.c_int32),('peak',C.c_uint16),('margin',C.c_uint16),('valid',C.c_uint8)]
class Needle(C.Structure):_fields_=[('angle',C.c_int32),('peak',C.c_uint16),('margin',C.c_uint16),('outside',C.c_uint16),('valid',C.c_uint8)]
def ptr(a,typ):return a.ctypes.data_as(C.POINTER(typ))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    lib=C.CDLL(str(HERE/'numeric_host.dll'))
    lib.c4_probe_hub.argtypes=[C.POINTER(C.c_uint8),C.POINTER(C.c_int8),C.POINTER(Point)]
    lib.c4_probe_landmark.argtypes=lib.c4_probe_hub.argtypes
    lib.reader_polar.argtypes=[C.POINTER(C.c_uint8),C.c_int32,C.c_int32,C.c_uint,C.POINTER(Needle),C.c_void_p,C.c_void_p]
    lib.reader_ring.argtypes=[C.POINTER(C.c_uint8),C.c_int32,C.c_int32,C.c_uint,C.POINTER(matcher.Result),C.c_void_p,C.c_void_p]
    matchlib=matcher.dll();templates,keep=matcher.templates(matchlib)
    layers=q.load_layers(ROOT/'algorithm_work/meter_landmark_mcu_training_20261103/model/hub_integer/integer_model.npz')
    landmark_layers=q.load_layers(HERE.parent/'model/landmark_integer/integer_model.npz')
    original=ROOT/'algorithm_work/meter_pointer_readout_20261102/polar_angle/integer_reference'
    pmeta=json.loads((original/'quantization.json').read_text());pa=dict(np.load(original/'integer_weights.npz'))
    images={}
    for split in ['train','validation']:
        z=np.load(ROOT/f'algorithm_work/meter_cnn_training_20261102/roi_cache_{split}.npz');images.update(zip(z['ids'].tolist(),z['images']))
    counts=dict(maps=0,map_elements=0,map_mismatches=0,decode_fields=0,decode_mismatches=0,polar_logit_elements=0,polar_logit_mismatches=0,polar_Q6_difference_from_previous_float_frontend=0,ring_result_fields=0,ring_result_mismatches=0,ring_Q5_differences_from_floatgeometry=0,ring_outside_count_differences=0,ring_Q5_components=0)
    rows=[]
    for ident in ['D_002','D_013','D_025','E_002','F_002','F_025']:
        im=np.ascontiguousarray(images[ident],np.uint8);out=np.empty((2,64,64),np.int8);pp=(Point*2)()
        assert lib.c4_probe_hub(ptr(im,C.c_uint8),ptr(out,C.c_int8),pp)==1
        expected=q.forward(im,layers);decoded=q.decode_integer(expected)
        counts['maps']+=2;counts['map_elements']+=out.size;counts['map_mismatches']+=int((expected!=out).sum())
        for i in range(2):
            actual=[pp[i].x,pp[i].y,pp[i].peak,pp[i].margin,int(pp[i].valid)]
            want=decoded[i]['roi_xy_q8']+[decoded[i]['peak_q15'],decoded[i]['margin_q15'],int(decoded[i]['accepted'])]
            counts['decode_fields']+=5;counts['decode_mismatches']+=sum(x!=y for x,y in zip(actual,want))
        lm=np.empty((6,64,64),np.int8);lp=(Point*6)()
        assert lib.c4_probe_landmark(ptr(im,C.c_uint8),ptr(lm,C.c_int8),lp)==1
        expected_lm=q.forward(im,landmark_layers);decoded_lm=q.decode_integer(expected_lm)
        counts['maps']+=6;counts['map_elements']+=lm.size;counts['map_mismatches']+=int((expected_lm!=lm).sum())
        for i in range(6):
            actual=[lp[i].x,lp[i].y,lp[i].peak,lp[i].margin,int(lp[i].valid)]
            want=decoded_lm[i]['roi_xy_q8']+[decoded_lm[i]['peak_q15'],decoded_lm[i]['margin_q15'],int(decoded_lm[i]['accepted'])]
            counts['decode_fields']+=5;counts['decode_mismatches']+=sum(x!=y for x,y in zip(actual,want))
        h=pp[0];center=[h.x/256,h.y/256];radius=48
        n=Needle();assert lib.reader_polar(ptr(im,C.c_uint8),h.x,h.y,radius,C.byref(n),None,None)==1
        # Independently construct exact rational Q6 from ordinary remap bytes.
        a=np.arange(360,dtype=np.float32)*(np.pi/180);r=(np.linspace(.2,.84,8,dtype=np.float32)[:,None]+np.array([-.02,0,.02],np.float32))*radius
        x=np.float32(center[0])+r[...,None]*np.cos(a);y=np.float32(center[1])+r[...,None]*np.sin(a)
        samples=cv2.remap(im,x.reshape(24,360),y.reshape(24,360),cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=128).reshape(8,3,360)
        sums=samples.astype(np.int32).sum(1)
        ints=np.concatenate([np.rint((sums-384)/6),np.rint((np.roll(sums,4,1)+np.roll(sums,-4,1)-2*sums)/6)],0)
        ints=np.clip(ints,-128,127).astype(np.int8)
        feature,outside=pf.polar_features(im,center,radius)
        counts['polar_Q6_difference_from_previous_float_frontend']+=int((ints!=np.clip(np.rint(feature*64),-128,127).astype(np.int8)).sum())
        expected_logits,_=pq.forward(ints.astype(np.float32)/64,pmeta['layers'],pa)
        arena=np.ctypeslib.as_array((C.c_int8*32768).in_dll(lib,'mroi_arena'))
        actual_logits=arena[10000:10360].copy();counts['polar_logit_elements']+=360
        counts['polar_logit_mismatches']+=int((actual_logits!=expected_logits).sum())
        # Independent fixed-point coordinate oracle with NumPy64 and Python
        # integer rational radial RNE. Feed its profiles to the signed old C
        # matcher, separate from the newly integrated streaming/Flash-copy path.
        center_ok=np.linalg.norm(np.asarray(center)-63.5)<=14
        profiles=[];outside_counts=[];normalized=front.normalize_local_u8(im)
        cs=np.rint(np.cos(np.arange(360)*np.pi/180)*(1<<30)).astype(np.int64)
        sn=np.rint(np.sin(np.arange(360)*np.pi/180)*(1<<30)).astype(np.int64)
        for dx in [-384,0,384]:
            for dy in [-384,0,384]:
                for scale in [97,100,103]:
                    coords=[];oc=0
                    for k in range(12):
                        radial=q.rne_div(radius*scale*(110+12*k)*(1<<20),27500)
                        xx=np.int64(h.x+dx)*(1<<42)+radial*cs;yy=np.int64(h.y+dy)*(1<<42)+radial*sn
                        oc+=int(((xx<0)|(xx>127*(1<<50))|(yy<0)|(yy>127*(1<<50))).sum())
                        coords.append((np.array([q.rne_div(v,1<<45)for v in xx],np.int16),np.array([q.rne_div(v,1<<45)for v in yy],np.int16)))
                    xq=np.stack([v[0]for v in coords]);yq=np.stack([v[1]for v in coords])
                    raw=front.bilinear_q5_u8(normalized,xq,yq);profiles.append(front.normalize_profile_s8(raw));outside_counts.append(oc)
                    xf,yf,of,*_=front.geometry_q5_from_float(np.asarray(center)+[dx/256,dy/256],radius*scale/100)
                    counts['ring_Q5_components']+=xq.size*2;counts['ring_Q5_differences_from_floatgeometry']+=int((xq!=xf).sum()+(yq!=yf).sum());counts['ring_outside_count_differences']+=int(oc!=of)
        want,_,_=matcher.run_one(matchlib,templates,profiles,outside_counts,center_ok)
        got=matcher.Result();imring=im.copy();assert lib.reader_ring(ptr(imring,C.c_uint8),h.x,h.y,radius,C.byref(got),None,None)==1
        for name,_ in matcher.Result._fields_:
            counts['ring_result_fields']+=1;counts['ring_result_mismatches']+=int(getattr(got,name)!=getattr(want,name))
        rows.append(dict(id=ident,hub_roi_q8=[h.x,h.y],needle_angle_deg=n.angle/65536,needle_valid=bool(n.valid),outside=n.outside))
    assert counts['map_mismatches']==counts['decode_mismatches']==counts['polar_logit_mismatches']==counts['ring_result_mismatches']==0,counts
    report=dict(status='SAME_C_HUB_POLAR_AND_STREAMING_RING_NUMERIC_PASS',counts=counts,rows=rows,source_sha256={p.name:sha(p)for p in (HERE/'source').glob('*')if p.suffix in ['.h','.c']},DLL_sha256=sha(HERE/'numeric_host.dll'),scope='6 proxyROIs; exact C4 maps/decode, rationalQ6 polar logits and independently reconstructed Q20radial/Q30trig ring pose. Not complete model/PSI or MCU execution.',H_opened=False,hardware_actions=False)
    (HERE/'numeric_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8');print(json.dumps(counts))
if __name__=='__main__':main()
