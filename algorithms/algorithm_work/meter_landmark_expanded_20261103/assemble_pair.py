"""Package an independently accepted FPGA DB/bit with the frozen MCU app.

Default is a plan only. No JTAG, board, debugger or flash commands exist here.
The independent physical release is supplied explicitly after FINAL review.
"""
from pathlib import Path
import argparse,hashlib,json,shutil,zipfile

HERE=Path(__file__).resolve().parent
PHYSICAL=HERE.parent/'meter_landmark_mcu_training_20261103/physical'
def read(p):return json.loads(Path(p).read_text('utf-8-sig'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ref(p):return dict(path=str(Path(p).resolve()),sha256=sha(p))
def check(v):
    p=Path(v['path']);assert sha(p)==v['sha256'],p
    return p
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--physical-release',type=Path)
    ap.add_argument('--run',action='store_true')
    args=ap.parse_args()
    if not args.run:
        print('PLAN ONLY: wait for independently accepted PSI17 FINAL DB and matching bit; no device actions.');return
    assert args.physical_release is not None
    release=read(args.physical_release)
    assert release['bitgen_admitted'] is True
    route=read(PHYSICAL/'latest_route.json');bitgen=read(PHYSICAL/'latest_bitgen.json')
    assert route['passed'] and (route.get('constraint_only_PSI_amendment') or route.get('PSI_contract_present_before_route') or route.get('constraint_only_literal_amendment'))
    assert route['PSI_paths_and_effective_constraint_passed']
    assert route['global_final_timing_passed'] and route['physical_capacity_passed']
    assert release['source_DB_sha256']==route['output']['sha256']
    signed_route=check(release['route_receipt'])
    assert read(signed_route)==route, 'Latest alias differs from independently signed route receipt'
    # The pre-bitgen admission signs the actual route/SDC/endpoint evidence.
    # Native bitgen then binds that SAME admission and DB to its actual bit.
    assert bitgen['gate']['sha256']==sha(args.physical_release)
    assert Path(bitgen['gate']['path']).resolve()==args.physical_release.resolve()
    for item in release['PSI_contract_and_endpoint_evidence']:check(item)
    assert len(release['PSI_contract_and_endpoint_evidence'])>=2
    assert bitgen['passed'] and bitgen['source_DB']['sha256']==route['output']['sha256']
    db=check(route['output']);bit=check(bitgen['output']);freeze=check(route['manifest'])
    inputs=read(freeze)
    for item in inputs['inputs']+inputs['tools']:check(item)
    soft=read(HERE/'final_software_release.json')
    check(soft['firmware']['ELF']);check(soft['firmware']['coldboot_payload'])
    assert read(check(soft['evidence']['once_marker']))['status']=='COMPLETED'
    src=HERE/'delivery/mcu';mcu=read(src/'package_manifest.json')
    for name,v in mcu['files'].items():
        f=src/name;assert sha(f)==v['sha256'] and f.stat().st_size==v['bytes'],name
    for relative,key in [('meter_landmark_reader.elf','ELF'),('meter_landmark_reader.bin','raw'),
                         ('U33_E00000_E0FFFF_reader_payload.bin','coldboot_payload')]:
        assert sha(src/relative)==soft['firmware'][key]['sha256'],relative
    for relative,key in [('final_C_evaluation.json','C_report'),('C_TEST_ONCE.json','once_marker'),
                         ('FINAL_FROZEN_SELECTED.json','frozen_manifest'),('independent_final_C_review.json','C_review')]:
        assert sha(src/'evidence/final_C'/relative)==soft['evidence'][key]['sha256'],relative
    report=read(check(soft['evidence']['C_report']))
    assert report['ELF_sha256']==soft['firmware']['ELF']['sha256']
    assert report['DLL_sha256']==soft['firmware']['DLL']['sha256']
    check(soft['firmware']['DLL'])
    out=HERE/'delivery/Trained_MCU_FPGA_Pair_20261103'
    out.mkdir(exist_ok=False);shutil.copytree(src,out/'mcu');(out/'fpga').mkdir()
    shutil.copyfile(HERE/'release_limitations.json',out/'已知限制与评价边界.json')
    shutil.copyfile(bit,out/'fpga/Meter_Trained_Readout_20261103.bit')
    shutil.copyfile(db,out/'fpga/accepted_routed.db')
    native_bitgen_receipt=Path(bitgen['run'])/'receipt.json'
    assert read(native_bitgen_receipt)==bitgen
    for name,path in [('source_freeze.json',freeze),('route_receipt.json',signed_route),('bitgen_receipt.json',native_bitgen_receipt),
                      ('physical_release.json',args.physical_release),('software_release.json',HERE/'final_software_release.json')]:
        shutil.copyfile(path,out/'fpga'/name)
    (out/'fpga/PSI_contract_evidence').mkdir()
    evidence_map=[]
    for i,item in enumerate(release['PSI_contract_and_endpoint_evidence']):
        p=check(item);name=f'{i:02d}_'+p.name
        shutil.copyfile(p,out/'fpga/PSI_contract_evidence'/name)
        evidence_map.append(dict(original=item,packaged='fpga/PSI_contract_evidence/'+name))
    write(out/'fpga/PSI_contract_evidence/index.json',evidence_map)
    project=Path(inputs['project']);mapping=[]
    with zipfile.ZipFile(out/'fpga/source_snapshot.zip','w',zipfile.ZIP_DEFLATED)as z:
        for item in inputs['inputs']:
            p=check(item)
            entry='project/'+p.relative_to(project).as_posix() if p.is_relative_to(project) else 'external/'+item['sha256'][:12]+'_'+p.name
            z.write(p,entry);mapping.append(dict(original=str(p),entry=entry,sha256=item['sha256']))
        z.writestr('restore_map.json',json.dumps(mapping,ensure_ascii=False,indent=2))
    prj=Path(route['run'])/'reader_landmark.prj'
    (out/'fpga/open_accepted_db.tcl').write_text(
        'import_device ph1_35p.db -package PH1P35MDG324 -speed 3\n'
        f'open_project {{{prj.as_posix()}}} -noanalyze\n'
        f'import_db {{{(out/"fpga/accepted_routed.db").as_posix()}}}\n','utf-8')
    write(out/'fpga/project_identity.json',dict(project=ref(project/'td_project/reader_landmark.al'),
          source_snapshot_preserves_original_paths=True,portable_rebuild_without_path_restoration=False,
          accepted_DB=ref(db),bit=ref(bit),unit='psi'))
    text='''本包为训练后 MCU 固件＋配套 FPGA 实验位流，尚未进行本版本实板验收。

MCU：mcu/U33_E00000_E0FFFF_reader_payload.bin，完整64KiB，写入U33物理偏移0xE00000（sector224）。
程序入口0x20E00000，代码47480字节；三个已训练网络及权重已编入，不需要电脑推理或现场训练。
FPGA：fpga/Meter_Trained_Readout_20261103.bit。必须与该固件配套；板上现有bb1f/80f9不具备新PSI返回接口。
本目录仅生成文件，不会自行下载、擦写或启动车辆。实际固化需同时使用本包配置位流与MCU内容，不能只更新其中一个。

条件：指定同一表型，优先正立、正对、清晰、稳定取景；当前标定2.5～12psi，不支持0psi或全量程声明。
SW4/SW3请设00（AUTO）查看真实READ。其他位置为REF预设压力，不能用于判断CNN读数是否成功。
原定位框/轴心/针向线及稳定读数显示保留，未满足输出条件时拒读。画出的针线是方向参考长度，并非实测针尖长度。

最终预留C组一次离线对照：56张有表图，原整数参考19读→训练融合31读，新增12、撤销0；31读均在0.5psi描述分档内，MAE0.16847psi，另25张拒读。3张无表图0输出。
这是人工框生成的128灰度代理ROI、同一C实现的结果，不是自动定位/CSI实板验收；C曾用于标注QA，不冒盲测。G开发集仍有1张误差>0.5psi，故不能保证任意环境正确。
较早固件的H组终检曾有2.09psi错读；本次未重测H，历史错误没有被新C结果抹去，具体版本见已知限制与评价边界.json。
实际MCU周期、Flash XIP速度、冷启动和板载出数率尚待验证。0.5psi是评价分档，不是用户已确认的精度指标。
板端沿用三个不同新源观察的稳定确认；单张ROI通过不等于屏幕已获准出数，确认等待时间须实测。

配套FPGA基于80f9恢复版，保留20模式/紧凑UI/AE/AWB/原定位；未合入另聊bb1f的REF等待3秒显示规则，AUTO真实识别不由该规则决定。
资源及最终时序见fpga/route_receipt.json；实际余量应据此，不使用综合估算冒实际面积。
TD工程位置见fpga/project_identity.json；在本机可用open_accepted_db.tcl查看已签物理库。source_snapshot.zip保原源码和资产，保留原绝对路径依赖，移机须恢复路径后重新核验。
MCU离线复建使用mcu/rebuild_offline.py，默认只显示计划；--build只在本包新目录输出，不操作板卡。
'''
    (out/'请先读_配套与固化位置.txt').write_text(text,'utf-8')
    files={p.relative_to(out).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)for p in sorted(out.rglob('*'))if p.is_file()}
    write(out/'pair_manifest.json',dict(status='OFFLINE_PAIR_COMPLETE_BOARD_PENDING',ELF=soft['firmware']['ELF'],
          MCU_payload=soft['firmware']['coldboot_payload'],bit=ref(bit),accepted_DB=ref(db),
          software_release=ref(HERE/'final_software_release.json'),physical_release=ref(args.physical_release),
          files=files,hardware_actions=False,board_validation=False,unit='psi'))
    archive=out.with_suffix('.zip');assert not archive.exists()
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9)as z:
        for p in sorted(out.rglob('*')):
            if p.is_file():z.write(p,out.name+'/'+p.relative_to(out).as_posix())
    with zipfile.ZipFile(archive)as z:assert z.testzip()is None
    write(HERE/'delivery/pair_completion.json',dict(status='PAIRED_EXPERIMENTAL_DELIVERY_COMPLETE_NOT_BOARD_ACCEPTED',
          directory=str(out),archive=ref(archive),manifest=ref(out/'pair_manifest.json'),hardware_actions=False))
    print(json.dumps(dict(directory=str(out),archive=ref(archive)),ensure_ascii=False))

if __name__=='__main__':main()
