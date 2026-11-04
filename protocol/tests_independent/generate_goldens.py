"""Independent stdlib V4 byte vectors. No actor codec or production import."""
import binascii
import hashlib
import json
import struct
from pathlib import Path

HERE=Path(__file__).resolve().parent
CONTRACT=HERE.parent/'contract.json'
C=json.loads(CONTRACT.read_text(encoding='utf-8'))
CFG=C['config_signature']
T=0xA1234567; K=0x11223344
assert binascii.crc_hqx(b'123456789',0xffff)==0x29b1

def h(typ,seq=1,action=0,token=T,key=K,epoch=1,flags=0):
    return bytearray(struct.pack('<2sBBHBBIII',b'\xa5\x5a',4,typ,seq,action,flags,token,key,epoch)+bytes(12))
def seal(b):
    b[30:32]=struct.pack('<H',binascii.crc_hqx(bytes(b[2:30]),0xffff))
    return bytes(b)
def make(typ,pay,**kwargs):
    assert len(pay)==10
    b=h(typ,**kwargs);b[20:30]=pay;return seal(b)
rows=[]
def add(name,b,accepted=True,layer='contract_fields',note=''):
    assert len(b)==32
    rows.append({'name':name,'hex':b.hex(),'frame_bytes':32,'codec_accept':b[:2]==b'\xa5\x5a' and b[2]==4 and 1<=b[3]<=10 and int.from_bytes(b[30:32],'little')==binascii.crc_hqx(b[2:30],0xffff),'contract_fields_accept':accepted,'scope':layer,'note':note})
hello=lambda build:struct.pack('<IHBBH',build,0x7f,32,4,0)
add('HELLO_FPGA_ZERO',make(1,hello(0xBB1F4401),token=0,key=0,epoch=CFG),note='Boot announcement only; no normal ownership or arm.')
add('HELLO_ESP_REQUEST',make(1,hello(0x53334401),token=0,key=T,epoch=CFG))
add('HELLO_FPGA_CHALLENGE',make(1,hello(0xBB1F4401),key=T,epoch=CFG))
add('HELLO_ESP_ECHO',make(1,hello(0x53334401),key=T,epoch=CFG))
state=lambda imu,park,sr,flags:struct.pack('<HHBBI',imu,park,sr,flags,0)
add('STATE_IDLE_CONTROL_ONLY',make(2,state(0,6000,3,223),key=0),note='Valid byte fields; idle key never grants task STEP/READ.')
add('STATE_ACTIVE_READY',make(2,state(180,6000,3,223),action=1,epoch=3))
add('STATE_ACCEPTED0',make(2,state(0,6000,0,31),action=1,epoch=1))
add('STATE_RUNNING1',make(2,state(5,0,1,27),action=1,epoch=2))
add('STATE_SETTLING1',make(2,state(5,100,2,27),action=1,epoch=2))
add('STATE_EARLY_NO_OUTPUT0',make(2,state(5,6000,4,223),action=1,epoch=1))
start=lambda delta,mode:struct.pack('<hBB6x',delta,mode,0)
add('START_LEFT_DIAGNOSTIC',make(3,start(10000,1)))
add('START_RIGHT_FORMAL',make(3,start(-10000,0),key=0xffffffff))
step=lambda src,age,delta,fl:struct.pack('<IHhH',src,age,delta,fl)
add('STEP_LEFT_420MS_NEGATIVE',make(9,step(0xfffffffe,455,10000,35),action=1))
add('STEP_RIGHT_SOURCE_WRAP',make(9,step(0,1100,-10000,35),action=36,epoch=0xffffffff))
stop=lambda src,age,fl,r:struct.pack('<IHHBB',src,age,fl,r,0)
add('STOP_PARTIAL_SOURCE_WRAP',make(10,stop(0,50,31,24),action=1,epoch=2))
add('STOP_FULL',make(10,stop(13,200,23,24),action=36,epoch=0xffffffff))
add('STOP_UNQUALIFIED_SAFE_BRAKE',make(10,stop(13,0xffff,0,1),action=1,epoch=2),note='May brake matching action, never grants image/read evidence.')
obs=lambda src,age,fl,s,r:struct.pack('<IHHBB',src,age,fl,s,r)
add('OBS_CAMERA_PROGRESS',make(6,obs(0,5,1025,3,0)),note='Typed camera source; source0 valid wrap.')
add('OBS_BOX',make(6,obs(8,200,23,3,0)))
add('OBS_COMPLETED_NEGATIVE',make(6,obs(9,1100,35,3,9)))
add('OBS_READ_FENCE_FLOOR',make(6,obs(0xffffffff,0xffff,131,6,0),action=1,epoch=3))
add('OBS_CONTROL_NONE',make(6,obs(0,0xffff,1,5,0),action=1,epoch=3))
result=lambda src,q,age,fl,r:struct.pack('<IHHBB',src,q,age,fl,r)
add('RESULT_NEW_READ_SOURCE_WRAP',make(7,result(0,0x8000,200,3,0),action=1,epoch=3),note='Contextual acceptance still needs prior actual floor0xFFFFFFFF, parked owner and diagnostic local mode.')
add('RESULT_Q_ZERO',make(7,result(1,0,0,3,0),action=1,epoch=3))
add('RESULT_Q_MAX',make(7,result(2,0xffff,199,3,0),action=1,epoch=3))
add('ACK_START',make(5,struct.pack('<HBBBxI',0xffff,3,0,0,0)))
add('FAIL_NO_IMAGE31',make(8,struct.pack('<IBBI',0,31,0,0),action=1,epoch=3))
add('CANCEL',make(4,bytes([1])+bytes(9),action=1,epoch=3))
add('SEQ_WRAP_FFFF',make(6,obs(0xffffffff,5,1025,0,0),seq=0xffff,key=0))
add('SEQ_WRAP_ZERO',make(6,obs(0,5,1025,0,0),seq=0,key=0),note='Forwardness is stateful; 0 followsFFFF under half range.')

def mutate(name,base,offset,value,accepted=False,reseal=True,note=''):
    b=bytearray(base);b[offset]=value
    add(name,seal(b) if reseal else bytes(b),accepted,note=note)
base=bytes.fromhex(rows[10]['hex'])
for v in (1,2,3): mutate(f'OLD_VERSION_{v}_REJECT',base,2,v)
mutate('CRC_BODY_CORRUPT',base,28,1,reseal=False)
mutate('BAD_SYNC',base,0,0,reseal=False)
mutate('UNKNOWN_TYPE',base,3,11)
mutate('HEADER_RESERVED',base,7,1)
mutate('START_RESERVED',base,24,1)
add('START_DELTA_9999_REJECT',make(3,start(9999,1)),False)
add('START_MODE2_REJECT',make(3,start(10000,2)),False)
add('STEP_NEGATIVE_EVIDENCE_MISSING',make(9,step(7,455,10000,3),action=1),False)
add('STEP_EXPIRED_1101',make(9,step(7,1101,10000,35),action=1),False)
add('STEP_BAD_DELTA',make(9,step(7,455,-9999,35),action=1),False)
add('STEP_ACTION37_REJECT',make(9,step(7,455,10000,35),action=37),False)
add('RESULT_PUB_AGE201_REJECT',make(7,result(7,123,201,3,0),action=1,epoch=3),False)
add('RESULT_REF_REJECT',make(7,result(7,123,100,8,0),action=1,epoch=3),False)
add('RESULT_LAST_REJECT',make(7,result(7,123,100,16,0),action=1,epoch=3),False)
add('RESULT_FORMAL_NOT_IMPLEMENTED',make(7,result(7,123,100,7,0),action=1,epoch=3),False)
add('HELLO_CFG_MISMATCH',make(1,hello(0x53334401),key=T,epoch=CFG^1),False)
add('HELLO_BUILD_MISMATCH',make(1,hello(0x53333301),key=T,epoch=CFG),False)
mutate('STATE_RESERVED',bytes.fromhex(rows[5]['hex']),29,1)
mutate('ACK_RESERVED',bytes.fromhex(rows[25]['hex']),29,1)
mutate('STOP_RESERVED',bytes.fromhex(rows[15]['hex']),29,1)
mutate('CANCEL_RESERVED',bytes.fromhex(rows[27]['hex']),29,1)

sizes={'u8':1,'u16':2,'i16':2,'u32':4}
def size(t):return sizes[t] if t in sizes else int(t[5:])
for name,fields in C['payload'].items():
    occupied=[]
    for n,o,t in fields: occupied += list(range(o,o+size(t)))
    assert sorted(occupied)==list(range(10)),(name,occupied)
occupied=[]
for n,o,t in C['header']:occupied+=list(range(o,o+size(t)))
assert sorted(occupied)==list(range(20))
assert sorted(C['enums']['Reason'].values())==list(range(32))
assert C['enums']['StateFlag']['READY_STEP']==64 and C['enums']['StateFlag']['READY_READ']==128
assert 'ACTION_OWNED' not in C['enums']['StateFlag']
assert C['ownership']['fpga_independent_six_second_timer'] is False
assert C['config']['MAX_STEPS']*C['config']['STEP_MAX_MDEG']==360000
HERE.mkdir(parents=True,exist_ok=True)
(HERE/'golden_frames.jsonl').write_text(''.join(json.dumps(x,separators=(',',':'))+'\n' for x in rows),encoding='utf-8')
(HERE/'golden32.hex').write_text(''.join(x['hex']+'\n' for x in rows),encoding='ascii')
audit={'status':'PASS_INDEPENDENT_WIRE_SCHEMA_AND_VECTOR_GENERATION_ONLY','config_signature':f'{CFG:08X}',
       'contract_sha256':hashlib.sha256(CONTRACT.read_bytes()).hexdigest(),'golden_count':len(rows),
       'field_accepted_count':sum(x['contract_fields_accept'] for x in rows),'crc_check_123456789':'29B1',
       'crc_range_inclusive':[2,29],'frame_bytes':32,'header_and_all_payloads_exact_nonoverlap':True,
       'actual_actor_implementation_executed':False,'native':False,'devices':False,
       'scope':'Independent struct/binascii bytes. Stateful replay, token/key/epoch, fences, terminal park, deadlines and local mode require actual both-end execution; this file is not that PASS.'}
(HERE/'schema_wire_audit.json').write_text(json.dumps(audit,indent=2)+'\n',encoding='utf-8')
print(json.dumps(audit))
