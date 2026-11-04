"""Independent source-only shared mapper candidate; never invokes TD/device."""
from pathlib import Path
import hashlib,json,re,shutil,difflib
TASK=Path(__file__).resolve().parents[1]
BASE=Path('C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_reader_staged_display_20261104/project')
P=Path('C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029/native_reader_shared_mapper_20261104/project')
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def replace(text,old,new):
    assert text.count(old)==1,(old[:100],text.count(old));return text.replace(old,new,1)
def main():
    assert not P.exists(),'No overwrite of any existing candidate'
    baseline=[ref(p) for p in BASE.rglob('*') if p.is_file() and ('user_source' in p.relative_to(BASE).parts or p.relative_to(BASE).as_posix() in ['td_project/reader_staged.al','td_project/base_auto_quality.sdc'])]
    shutil.copytree(BASE/'user_source',P/'user_source')
    (P/'td_project').mkdir()
    shutil.copyfile(BASE/'td_project/base_auto_quality.sdc',P/'td_project/base_auto_quality.sdc')
    shutil.copyfile(BASE/'td_project/reader_staged.al',P/'td_project/reader_shared.al')
    for p in P.rglob('*'):
        if not p.is_file() or p.suffix.lower() not in ['.v','.sv','.vh','.xml','.tcl','.al','.sdc','.adc','.txt']:continue
        try:text=p.read_text('utf-8-sig')
        except UnicodeDecodeError:continue
        new=text.replace(BASE.as_posix(),P.as_posix()).replace(str(BASE),str(P))
        if p.name=='reader_shared.al':new=replace(new,'<Name>reader_staged</Name>','<Name>reader_shared</Name>')
        if new!=text:p.write_text(new,'utf-8')
    reader=P/'user_source/hdl_source/meter_pair/t06_meter_roi_reader.v'
    text=reader.read_text('utf-8-sig')
    text=replace(text,'output wire [2:0] progress_stride,output wire [6:0] progress_radius\n',
        'output wire [2:0] progress_stride,output wire [6:0] progress_radius,\n output wire [12:0] native_hub_x,native_hub_y,\n output reg [12:0] progress_native_x,progress_native_y\n')
    old=''' wire [16:0] nxq4=({6'd0,result_x0}<<4)+hub_x_q4*result_stride+((result_stride-1'b1)<<3);
 wire [16:0] nyq4=({7'd0,result_y0}<<4)+hub_y_q4*result_stride+((result_stride-1'b1)<<3);
 wire [12:0] nx=(nxq4+17'd8)>>4,ny=(nyq4+17'd8)>>4;'''
    new=''' // Exactly one native mapper. At a passed early event it maps the incoming
 // frozen live code; all other cycles map the original final registers.
 // Cache the early native coordinates with its package: TRACK confirmation
 // can arrive after WAIT_CPU, so visual must not remap that package later.
 wire map_progress=state==WAIT_CPU&&live_progress&&!kill&&!take&&
  live_target==owner_target&&live_config==owner_config&&
  (progress_pointer||progress_hub)&&(!progress_valid||!progress_needle_valid||progress_pointer);
 wire [10:0] map_x0=map_progress?live_x:result_x0;
 wire [9:0] map_y0=map_progress?live_y:result_y0;
 wire [2:0] map_stride=map_progress?live_stride:result_stride;
 wire [10:0] map_hx=map_progress?live_progress_code[21:11]:hub_x_q4;
 wire [10:0] map_hy=map_progress?live_progress_code[10:0]:hub_y_q4;
 wire [16:0] nxq4=({6'd0,map_x0}<<4)+map_hx*map_stride+((map_stride-1'b1)<<3);
 wire [16:0] nyq4=({7'd0,map_y0}<<4)+map_hy*map_stride+((map_stride-1'b1)<<3);
 wire [12:0] nx=(nxq4+17'd8)>>4,ny=(nyq4+17'd8)>>4;
 assign native_hub_x=nx;assign native_hub_y=ny;'''
    text=replace(text,old,new)
    text=replace(text,'progress_valid<=0;progress_pulse<=0;progress_needle_valid<=0;progress_hub_x_q4<=0;progress_hub_y_q4<=0;progress_angle<=0;',
        'progress_valid<=0;progress_pulse<=0;progress_needle_valid<=0;progress_hub_x_q4<=0;progress_hub_y_q4<=0;progress_angle<=0;progress_native_x<=0;progress_native_y<=0;')
    text=replace(text,'''else if(state==WAIT_CPU&&live_progress&&live_target==owner_target&&live_config==owner_config&&
           (progress_pointer||progress_hub)&&(!progress_valid||!progress_needle_valid||progress_pointer))begin''',
        '''else if(map_progress)begin''')
    text=replace(text,'progress_valid<=1;progress_pulse<=1;progress_needle_valid<=progress_pointer;',
        'progress_valid<=1;progress_pulse<=1;progress_needle_valid<=progress_pointer;\n    progress_native_x<=nx;progress_native_y<=ny;')
    reader.write_text(text,'utf-8')
    visual=P/'user_source/hdl_source/meter_pair/t06_meter_visual_pipeline.v'
    text=visual.read_text('utf-8-sig')
    text=replace(text,'wire [10:0] hub_x_q4,hub_y_q4;wire [31:0] mcu_result_crc;',
        'wire [12:0] reader_native_x,reader_native_y,progress_native_x,progress_native_y;wire [31:0] mcu_result_crc;')
    text=replace(text,'wire progress_have,progress_pulse,progress_needle;wire [10:0] progress_hx,progress_hy,progress_x;',
        'wire progress_have,progress_pulse,progress_needle;wire [10:0] progress_x;')
    text=replace(text,'.hub_x_q4(hub_x_q4),.hub_y_q4(hub_y_q4),.mcu_result_crc(mcu_result_crc),',
        '.hub_x_q4(),.hub_y_q4(),.native_hub_x(reader_native_x),.native_hub_y(reader_native_y),.mcu_result_crc(mcu_result_crc),')
    text=replace(text,'.progress_hub_x_q4(progress_hx),.progress_hub_y_q4(progress_hy),.progress_angle(progress_angle),',
        '.progress_hub_x_q4(),.progress_hub_y_q4(),.progress_native_x(progress_native_x),.progress_native_y(progress_native_y),.progress_angle(progress_angle),')
    old=''' wire [10:0] display_x=early_request?progress_x:result_x;
 wire [9:0] display_y=early_request?progress_y:result_y;
 wire [2:0] display_stride=early_request?progress_stride:result_stride;
 wire [10:0] display_hx=early_request?progress_hx:hub_x_q4,display_hy=early_request?progress_hy:hub_y_q4;
 // One shared native-coordinate mapper, rather than two added multiplier paths.
 wire [16:0] display_nxq4=({6'd0,display_x}<<4)+display_hx*display_stride+((display_stride-1'b1)<<3);
 wire [16:0] display_nyq4=({7'd0,display_y}<<4)+display_hy*display_stride+((display_stride-1'b1)<<3);
 wire [12:0] display_nx=(display_nxq4+17'd8)>>4,display_ny=(display_nyq4+17'd8)>>4;'''
    new=''' // Reader owns the only mapper. Early native coordinates were cached
 // on the same accepted-code edge and remain tied to that entire package.
 wire [12:0] display_nx=early_request?progress_native_x:reader_native_x;
 wire [12:0] display_ny=early_request?progress_native_y:reader_native_y;'''
    text=replace(text,old,new);visual.write_text(text,'utf-8')
    assert all(sha(r['path'])==r['sha256'] for r in baseline),'Main frozen project changed'
    changes=[]
    for p in P.rglob('*'):
        if not p.is_file():continue
        rel=p.relative_to(P);old=BASE/rel
        if p.name=='reader_shared.al':old=BASE/'td_project/reader_staged.al'
        assert old.is_file(),str(old)
        if p.read_bytes()!=old.read_bytes():
            ot=old.read_text('utf-8-sig');nt=p.read_text('utf-8-sig')
            normalized=nt.replace(P.as_posix(),'<P>').replace(str(P),'<P>').replace('<Name>reader_shared</Name>','<Name>NAME</Name>')
            normalized_old=ot.replace(BASE.as_posix(),'<P>').replace(str(BASE),'<P>').replace('<Name>reader_staged</Name>','<Name>NAME</Name>')
            kind='PATH_OR_PROJECT_ONLY' if normalized==normalized_old else 'SHARED_COORDINATE_MAPPER_ONLY'
            diff=TASK/'integration'/(p.name+'.diff');diff.write_text(''.join(difflib.unified_diff(ot.splitlines(True),nt.splitlines(True),fromfile=str(old),tofile=str(p))),'utf-8')
            changes.append({'path':str(rel),'kind':kind,'old':ref(old),'new':ref(p),'diff':ref(diff)})
    assert {Path(c['path']).name for c in changes if c['kind']!='PATH_OR_PROJECT_ONLY'}=={'t06_meter_roi_reader.v','t06_meter_visual_pipeline.v'}
    out={'status':'SOURCE_ONLY_CANDIDATE_REQUIRES_INDEPENDENT_DIFF_REVIEW_AND_COMPONENT_TESTS','project':str(P),'name':'reader_shared','main_project_unchanged':True,'main_input_snapshot':baseline,'candidate_file_count':len([p for p in P.rglob('*') if p.is_file()]),'changes':changes,'MCU6035_unchanged':True,'no_TD_or_device':True}
    (TASK/'integration/clone_receipt.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n','utf-8')
    print(json.dumps({'project':str(P),'changes':[(c['path'],c['kind']) for c in changes],'receipt':ref(TASK/'integration/clone_receipt.json')},ensure_ascii=False))

if __name__=='__main__':main()
