"""Only synthetic pixel/Q5/rational-profile checks of the new C frontend."""
from pathlib import Path
import ctypes as C
import hashlib,importlib.util,json,sys
sys.dont_write_bytecode=True
import cv2
import numpy as np

HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pointer(x,typ):return x.ctypes.data_as(C.POINTER(typ))

def main():
    spec=importlib.util.spec_from_file_location('synthetic_frontend_reference',HERE/'pose_frontend.py')
    ref=importlib.util.module_from_spec(spec);sys.modules[spec.name]=ref;spec.loader.exec_module(ref)
    dll=HERE/'meter_pose_frontend.dll';lib=C.CDLL(str(dll))
    for name in ['mpf_normalize_workspace_size','mpf_profile_workspace_size']:getattr(lib,name).restype=C.c_size_t
    U8=C.POINTER(C.c_uint8);S8=C.POINTER(C.c_int8);S16=C.POINTER(C.c_int16)
    lib.mpf_normalize9x9_u8.argtypes=[U8,U8,C.c_void_p]
    lib.mpf_bilinear_q5_u8.argtypes=[U8,S16,S16,C.c_uint16,U8]
    lib.mpf_normalize_profile_s8.argtypes=[U8,S8]
    lib.mpf_profile_q5_s8.argtypes=[U8,S16,S16,S8,C.c_void_p]
    assert lib.mpf_normalize_workspace_size()==1408 and lib.mpf_profile_workspace_size()==360
    ws=C.create_string_buffer(1408);pws=C.create_string_buffer(360)
    rng=np.random.default_rng(1108)
    images=[np.zeros((128,128),np.uint8),np.full((128,128),255,np.uint8),
        np.arange(16384,dtype=np.uint16).reshape(128,128).astype(np.uint8)]
    images.extend(rng.integers(0,256,(128,128),dtype=np.uint8)for _ in range(13))
    counts=dict(normalize_pixels=0,inplace_normalize_pixels=0,bilinear_Q5_pixels=0,
        profile_elements=0,inplace_profile_elements=0,fused_profile_elements=0)
    norms=[]
    for image in images:
        output=np.empty_like(image);expected=ref.normalize_local_u8(image)
        assert lib.mpf_normalize9x9_u8(pointer(image,C.c_uint8),pointer(output,C.c_uint8),ws)==0
        assert np.array_equal(output,expected)
        copy=image.copy()
        assert lib.mpf_normalize9x9_u8(pointer(copy,C.c_uint8),pointer(copy,C.c_uint8),ws)==0
        assert np.array_equal(copy,expected)
        counts['normalize_pixels']+=16384;counts['inplace_normalize_pixels']+=16384;norms.append(output)
    maps=[]
    for _ in range(16):
        maps.append((rng.integers(-32768,32768,(12,360),dtype=np.int16),rng.integers(-32768,32768,(12,360),dtype=np.int16)))
    for xb,yb in [(-1,-1),(-1,0),(0,-1),(0,0),(126,127),(127,127),(127,128),(128,0)]:
        fx,fy=np.meshgrid(np.arange(32,dtype=np.int16),np.arange(32,dtype=np.int16))
        maps.append((np.ascontiguousarray(xb*32+fx),np.ascontiguousarray(yb*32+fy)))
    for i,(xq,yq)in enumerate(maps):
        image=norms[i%len(norms)];got=np.empty(xq.shape,np.uint8)
        assert lib.mpf_bilinear_q5_u8(pointer(image,C.c_uint8),pointer(xq,C.c_int16),pointer(yq,C.c_int16),xq.size,pointer(got,C.c_uint8))==0
        expected=ref.bilinear_q5_u8(image,xq,yq)
        cv=cv2.remap(image,xq.astype(np.float32)/32,yq.astype(np.float32)/32,cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT,borderValue=128)
        assert np.array_equal(got,expected)and np.array_equal(got,cv)
        counts['bilinear_Q5_pixels']+=got.size
        if xq.shape==(12,360):
            fused=np.empty((12,360),np.int8)
            assert lib.mpf_profile_q5_s8(pointer(image,C.c_uint8),pointer(xq,C.c_int16),pointer(yq,C.c_int16),pointer(fused,C.c_int8),pws)==0
            assert np.array_equal(fused,ref.normalize_profile_s8(expected))
            counts['fused_profile_elements']+=4320
    special=np.empty((12,360),np.uint8)
    special[0]=0;special[1]=255;special[2]=np.arange(360,dtype=np.uint16)%256
    special[3]=rng.integers(0,256,360,dtype=np.uint8)
    special[4,:180]=0;special[4,180:]=255
    special[5,:256]=255;special[5,256:]=0
    special[6,:104]=255;special[6,104:]=0
    special[7]=0;special[7,0]=255
    special[8]=255;special[8,0]=0
    special[9]=np.tile(np.array([0,128,255],np.uint8),120)
    special[10]=np.tile(np.array([1,2],np.uint8),180)
    special[11]=rng.integers(0,2,360,dtype=np.uint8)
    profiles=[special,*[rng.integers(0,256,(12,360),dtype=np.uint8)for _ in range(31)]]
    for sampled in profiles:
        expected=ref.normalize_profile_s8(sampled);got=np.empty((12,360),np.int8)
        assert lib.mpf_normalize_profile_s8(pointer(sampled,C.c_uint8),pointer(got,C.c_int8))==0
        assert np.array_equal(got,expected)
        copy=sampled.copy()
        assert lib.mpf_normalize_profile_s8(pointer(copy,C.c_uint8),pointer(copy,C.c_int8))==0
        assert np.array_equal(copy.view(np.int8),expected)
        counts['profile_elements']+=4320;counts['inplace_profile_elements']+=4320
    rounded=ref.normalize_profile_s8(special)
    assert np.all(rounded[5,:256]==22) and np.all(rounded[6,104:]==-22)
    assert rounded[7,0]==127 and rounded[8,0]==-127
    receipt=dict(status='PASS_SYNTHETIC_C_FRONTEND_Q5_INTEGER_KERNELS',counts=counts,
        signed_positive_negative_RNE_half_ties=True,both_saturation_ends=True,
        exact_alias_normalize_and_profile=True,full_signed_S16_Q5_domain_sampled=True,
        normalized_workspace_bytes=1408,profile_workspace_bytes=360,
        coordinate_generation_or_outside_count_implemented=False,model_training=False,
        real_dataset_inputs_read=False,hardware_actions=False,
        source_sha256={p.name:sha(p)for p in[HERE/'meter_pose_frontend.c',HERE/'meter_pose_frontend.h',dll,HERE/'pose_frontend.py',Path(__file__)]})
    (HERE/'host_frontend_test_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
