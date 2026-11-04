"""Necessary read-only identity check after exact accepted-DB bitgen."""
from pathlib import Path
import json,re,sys
from audit_synth import TASK,HERE,read,ref,sha,write
sys.path.insert(0,str(TASK/'physical'))
from source_helpers import validate_manifest,P


def main():
    rp=TASK/'physical/latest_bitgen.json';result=read(rp)
    assert result['stage']=='bitgen'and result['passed']and result['exit_code']==0 and not result['device']and result['errors']==[]
    for x in [result['manifest'],result['gate'],result['source_DB'],result['output'],result['log'],*result['artifacts'].values(),*result['controls']]:assert sha(x['path'])==x['sha256']
    gate=read(result['gate']['path']);assert gate['passed']and gate['stage']=='bitgen'and gate['bitgen_admitted']
    assert sha(gate['route_receipt']['path'])==gate['route_receipt']['sha256']
    accepted=read(gate['route_receipt']['path']);independent=read(HERE/'guided_final_physical_review.json')
    assert independent['passed']and independent['bitgen_from_this_accepted_DB_recommended']
    assert result['source_DB']==accepted['output']==independent['source_DB']
    assert result['source_DB']['sha256']=='def86a7b478657109e6a55cd17f1d6fb079dc2814d7d9b52949b2ac1a8b1a4a5'
    assert result['manifest']==accepted['manifest']and gate['manifest_sha256']==result['manifest']['sha256']
    for x in gate['PSI_contract_and_endpoint_evidence']:assert sha(x['path'])==x['sha256']
    frozen=validate_manifest(Path(result['manifest']['path']))
    log=Path(result['log']['path']).read_text(errors='replace');commands=re.findall(r'start command "([^"\r\n]+)"',log)
    assert commands==result['actual_commands']
    forbidden={'route','place','fix_hold','optimize_rtl','optimize_gate','elaborate','read_sdc','program','program_spi','write_memory','load'}
    assert not any(x.split()[0]in forbidden for x in commands)
    assert len([x for x in commands if x.startswith('bitgen ')])==1 and'UI_BITGEN_COMPLETE'in log
    assert 'Generate bitstream completely'in log and not re.search(r'\bERROR:|\bFATAL:|UI_BITGEN_FAILED:',log)
    bit=Path(result['output']['path']);payload=bit.read_bytes();assert len(payload)==result['bit_bytes']==1789539
    assert result['output']['sha256']=='d88297760b8b41be1466bf4a5ddeb18e4391c3601f2f529b788712b1de5469bd'
    header=payload[:180].decode('ascii',errors='strict')
    assert '# Anlogic ASCII Bitstream\n'in header and'# Architecture: ph1_35p\n'in header and'# Package: PH1P35MDG324\n'in header
    copied_DB=Path(result['run'])/'reader_landmark_pr.db';assert sha(copied_DB)==result['source_DB']['sha256']
    # The bit contains the reviewed coldboot hardware/ROM, not the separate
    # MCU application/weights. Check the selected offline firmware's declared
    # feature ABI against the actually frozen RTL without executing firmware.
    mcu=TASK.parent/'meter_landmark_expanded_20261103/delivery/mcu'
    selected=read(mcu/'evidence/selected_firmware_completion.json');abi=read(mcu/'evidence/abi_contract.json')
    for k in ['ELF','raw','coldboot_payload']:
        x=selected[k];assert sha(x['path'])==x['sha256']
    assert abi['FEATURES']['offset']=='0x064'and abi['FEATURES']['PSI_Q8_V1_bit']==0 and abi['RETURN_PSI']['offset']=='0x124'
    rtl=P/'user_source/hdl_source/meter_pair/meter_mcu_roi_ahb_live.v';text=rtl.read_text(encoding='utf-8-sig')
    assert "'h64:read_register=32'h00000001"in text and "'h124:begin ret_psi_q8<=write_data[15:0];ret_psi_valid<=write_data[31];end"in text
    assert any(x['path']==str(rtl.resolve())and x['sha256']==sha(rtl)for x in frozen['inputs'])
    assert sha(mcu/'meter_landmark_reader.bin')==selected['raw']['sha256']
    assert sha(mcu/'U33_E00000_E0FFFF_reader_payload.bin')==selected['coldboot_payload']['sha256']
    out=dict(passed=True,status='PASS_EXACT_ACCEPTED_DB_BITGEN_IDENTITY',bitgen_receipt=ref(rp),auditor=ref(__file__),
        accepted_route_receipt=gate['route_receipt'],physical_independent_review=ref(HERE/'guided_final_physical_review.json'),source_freeze=result['manifest'],
        accepted_DB=result['source_DB'],actual_copied_input_DB=ref(copied_DB),bit=result['output'],bit_bytes=len(payload),
        architecture='ph1_35p',package='PH1P35MDG324',actual_native_bitgen_count=1,actual_commands=commands,
        no_resynthesis_replacement_or_reroute=True,all_frozen_sources_and_tools_unchanged=True,
        matched_MCU_ABI=dict(contract=ref(mcu/'evidence/abi_contract.json'),RTL=ref(rtl),feature_offset='0x064',feature_bit0=True,psi_return_offset='0x124',
            selected_firmware_completion=ref(mcu/'evidence/selected_firmware_completion.json'),ELF=selected['ELF'],raw=selected['raw'],coldboot_payload=selected['coldboot_payload']),
        final_delivery_package_not_yet_present_or_reviewed=True,bit_alone_does_not_load_new_MCU_app=True,
        hardware_actions=False,board_Flash_download_admission=False)
    write(HERE/'bitgen_identity_review.json',out)
    print(json.dumps(dict(passed=True,review=ref(HERE/'bitgen_identity_review.json'),bit=result['output'],bit_bytes=len(payload)),ensure_ascii=False))


if __name__=='__main__':main()
