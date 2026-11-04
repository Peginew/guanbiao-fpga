"""Isolate the current80f9 video/UI project and extend only MCU scalar result ABI."""
from pathlib import Path
import hashlib
import json
import shutil

HERE = Path(__file__).resolve().parent
BASE = Path("C:/Users/Edward/Desktop/FPGA/MCU_Live_ROI_20261029")
OLD = BASE / "native_hdmi_ui_ref_fix_20261103/project"
NEW = BASE / "native_reader_landmark_20261103/project"


def replace(text, before, after, count=1):
    assert text.count(before) == count, (before[:100], text.count(before), count)
    return text.replace(before, after)


def main():
    assert not NEW.exists(), "Do not overwrite a candidate"
    shutil.copytree(OLD / "user_source", NEW / "user_source")
    (NEW / "td_project").mkdir()
    shutil.copyfile(OLD / "td_project/base_auto_quality.sdc", NEW / "td_project/base_auto_quality.sdc")
    al = (OLD / "td_project/hdmi_ui_ref_fix.al").read_text(encoding="utf-8-sig")
    al = replace(al, "<Name>hdmi_ui_ref_fix</Name>", "<Name>reader_landmark</Name>")
    (NEW / "td_project/reader_landmark.al").write_text(al, encoding="utf-8")
    for p in NEW.rglob("*"):
        if p.is_file() and p.suffix.lower() in {".v", ".sv", ".vh", ".vhd", ".tcl", ".sdc", ".adc", ".xml", ".txt", ".al"}:
            before = p.read_bytes()
            after = before.replace(OLD.as_posix().encode(), NEW.as_posix().encode()).replace(str(OLD).encode(), str(NEW).encode())
            if after != before:
                p.write_bytes(after)
    hdl = NEW / "user_source/hdl_source/meter_pair"
    p = hdl / "meter_mcu_roi_ahb_live.v"
    s = p.read_text(encoding="utf-8")
    s = replace(s, "output reg [31:0] checksum_bytes,checksum_code", "output reg [31:0] checksum_bytes,checksum_code,\n output reg [15:0] checksum_psi_q8,output reg checksum_psi_valid")
    s = replace(s, "reg [7:0] ret_mask;", "reg [7:0] ret_mask;reg [15:0] ret_psi_q8;reg ret_psi_valid;")
    s = replace(s, "a<=32'h60", "a<=32'h64")
    s = replace(s, "'h60:read_register={31'd0,platform_armed};", "'h60:read_register={31'd0,platform_armed};\n   'h64:read_register=32'h00000001; // FEATURES bit0: PSI_Q8_RETURN_V1")
    s = replace(s, "   'h120:if(!owner_visible)", "   'h124:if(!owner_visible)write_error=E_OWNER;else if(!claimed)write_error=E_CLAIM;\n    else if(write_data[30:16]!=0||(write_data[31]&&(write_data[15:0]<640||write_data[15:0]>3072)))write_error=E_FORMAT;\n   'h120:if(!owner_visible)")
    s = replace(s, "ret_code<=0;ret_mask<=0;", "ret_code<=0;ret_mask<=0;ret_psi_q8<=0;ret_psi_valid<=0;")
    s = replace(s, "checksum_bytes<=0;checksum_code<=0;", "checksum_bytes<=0;checksum_code<=0;checksum_psi_q8<=0;checksum_psi_valid<=0;")
    s = replace(s, "claim_mask<=0;ret_mask<=0;quiet_mask<=0;\n    end", "claim_mask<=0;ret_mask<=0;quiet_mask<=0;ret_psi_q8<=0;ret_psi_valid<=0;\n    end")
    s = replace(s, "if(bus_offset=='h120)ret_mask<=0;", "if(bus_offset=='h120)begin ret_mask<=0;ret_psi_valid<=0;end")
    s = replace(s, "'h8c:claimed<=1;", "'h8c:begin claimed<=1;ret_psi_q8<=0;ret_psi_valid<=0;end")
    s = replace(s, "       'h120:begin\n        checksum_crc32", "       'h124:begin ret_psi_q8<=write_data[15:0];ret_psi_valid<=write_data[31];end\n       'h120:begin\n        checksum_psi_q8<=ret_psi_q8;checksum_psi_valid<=ret_psi_valid;\n        checksum_crc32")
    p.write_text(s, encoding="utf-8")
    p = hdl / "meter_mcu_live_roi.v"
    s = p.read_text(encoding="utf-8")
    s = replace(s, "output reg result_checksum_ok,result_quality_ok,", "output reg result_checksum_ok,result_quality_ok,\n output reg [15:0] result_psi_q8,output reg result_psi_valid,")
    s = replace(s, "reg [31:0] return_source_crc,return_cpu_crc,return_bytes,return_code;", "reg [31:0] return_source_crc,return_cpu_crc,return_bytes,return_code;\n reg [15:0] return_psi_q8;reg return_psi_valid;\n wire [15:0] br_psi_q8;wire br_psi_valid;")
    s = replace(s, ".checksum_result_config(br_config),.checksum_crc32(br_crc),", ".checksum_result_config(br_config),.checksum_crc32(br_crc),\n  .checksum_psi_q8(br_psi_q8),.checksum_psi_valid(br_psi_valid),")
    s = replace(s, "return_code<=0;", "return_code<=0;return_psi_q8<=0;return_psi_valid<=0;", 2)
    s = replace(s, "return_code<=br_code;", "return_code<=br_code;return_psi_q8<=br_psi_q8;return_psi_valid<=br_psi_valid;")
    s = replace(s, "result_code<=0;", "result_code<=0;result_psi_q8<=0;result_psi_valid<=0;", 2)
    s = replace(s, "result_code<=return_code;", "result_code<=return_code;result_psi_q8<=return_psi_q8;result_psi_valid<=return_psi_valid;")
    p.write_text(s, encoding="utf-8")
    p = hdl / "t06_meter_roi_reader.v"
    s = p.read_text(encoding="utf-8")
    s = replace(s, "wire live_crc_ok,live_qgood;", "wire live_crc_ok,live_qgood;wire [15:0] live_psi_q8;wire live_psi_valid;\n reg [15:0] held_psi_q8;reg held_psi_valid;")
    s = replace(s, ".result_checksum_ok(live_crc_ok),", ".result_psi_q8(live_psi_q8),.result_psi_valid(live_psi_valid),\n  .result_checksum_ok(live_crc_ok),")
    start = s.index(" t06_meter_scale_runtime scale(")
    end = s.index(" always @(posedge clk or negedge rst_n)begin", start)
    s = s[:start] + " t06_meter_psi_return_runtime scale(.clk(clk),.rst_n(rst_n),.start(mstart),.cancel(kill),\n  .calibration_valid(calibration_valid),.input_valid(held_psi_valid),.psi_q8(held_psi_q8),\n  .busy(mbusy),.done(mdone),.value_valid(mgood),.value_q16(mq16),.value_bcd(mbcd),.reason(mreason));\n" + s[end:]
    s = replace(s, "held_hub_only<=0;\n  end else begin", "held_hub_only<=0;held_psi_q8<=0;held_psi_valid<=0;\n  end else begin")
    s = replace(s, "held_hub_only<=0;result_cnn_valid<=0;result_cnn_pass<=0;stable_observations<=0;", "held_hub_only<=0;held_psi_q8<=0;held_psi_valid<=0;result_cnn_valid<=0;result_cnn_pass<=0;stable_observations<=0;")
    s = replace(s, "held_hub_only<=0;result_cnn_valid<=0;result_cnn_pass<=0;result_cnn_margin<=0;", "held_hub_only<=0;held_psi_q8<=0;held_psi_valid<=0;result_cnn_valid<=0;result_cnn_pass<=0;result_cnn_margin<=0;")
    s = replace(s, "held_mean<=live_mean;held_gradient<=live_gradient;held_crc<=live_crc;", "held_mean<=live_mean;held_gradient<=live_gradient;held_crc<=live_crc;\n      held_psi_q8<=live_psi_q8;held_psi_valid<=live_psi_valid;")
    p.write_text(s, encoding="utf-8")
    p = hdl / "t06_meter_pair_link.v"
    s = p.read_text(encoding="utf-8")
    s = replace(s, "t06_meter_visual_pipeline #(.PAIR_FILE(PAIR_FILE),.TRIG_FILE(TRIG_FILE)) pipeline(",
                "t06_meter_visual_pipeline #(.PAIR_FILE(PAIR_FILE),.TRIG_FILE(TRIG_FILE),\n  .MAX_PHASE_CYCLES(1800000000),.MAX_READ_JOB_CYCLES(1500000000)) pipeline(")
    p.write_text(s, encoding="utf-8")
    shutil.copyfile(HERE / "rtl/t06_meter_psi_return_runtime.v", hdl / "t06_meter_psi_return_runtime.v")
    p = NEW / "td_project/reader_landmark.al"
    s = p.read_text(encoding="utf-8")
    anchor = '            <File Path="../user_source/hdl_source/meter_pair/t06_meter_scale_runtime.v">'
    addition = '''            <File Path="../user_source/hdl_source/meter_pair/t06_meter_psi_return_runtime.v">
                <FileInfo>
                    <Attr Name="UsedInSyn" Val="true"/>
                    <Attr Name="UsedInP&R" Val="true"/>
                    <Attr Name="BelongTo" Val="design_1"/>
                    <Attr Name="CompileOrder" Val="107"/>
                </FileInfo>
            </File>
'''
    s = replace(s, anchor, addition + anchor)
    p.write_text(s, encoding="utf-8")
    changed = []
    for p in (OLD / "user_source").rglob("*"):
        if not p.is_file():
            continue
        q = NEW / p.relative_to(OLD)
        expected = p.read_bytes().replace(OLD.as_posix().encode(), NEW.as_posix().encode()).replace(str(OLD).encode(), str(NEW).encode())
        if q.read_bytes() != expected:
            changed.append(str(p.relative_to(OLD)))
    assert len(changed) == 4, changed
    result = dict(status="ISOLATED_PSI_RESULT_ABI_CANDIDATE_NOT_YET_SIMULATED", old=str(OLD), new=str(NEW),
                  project=str(NEW / "td_project/reader_landmark.al"), changed_files=changed,
                  added="t06_meter_psi_return_runtime.v", pins_constraints_clocks_unchanged=True,
                  arm060_unchanged=True, features064=1, returnPSIQ8=0x124,
                  units="New scalar PSI_Q8 is explicitly converted to existing barU0.16 transport; old angleTEST mapper removed. Display remainspsi.",
                  hardware_actions=False)
    (HERE / "fpga_interface_candidate.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
