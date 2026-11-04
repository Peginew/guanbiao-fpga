create_clock -name {sys_clk_50m} -period 20.000 -waveform {0.000 10.000} [get_ports {I_sys_clk}]
create_clock -name {mipi_rx_ck_pad} -period 2.415 -waveform {0.000 1.208} [get_nets {IO_rx_clk_pad_p}]

derive_clocks

rename_clock -name {pll_clk_100m} [get_clocks {u_PLL/ph1p_phy_pll_wrapper_25a56e5ce2f9_Inst/u_PH1P_PHY_PLL.clkc[0]}]
rename_clock -name {pll_clk_24m} [get_clocks {u_PLL/ph1p_phy_pll_wrapper_25a56e5ce2f9_Inst/u_PH1P_PHY_PLL.clkc[1]}]
rename_clock -name {HDMI_PIXEL_CLK} [get_clocks {u_PLL/ph1p_phy_pll_wrapper_25a56e5ce2f9_Inst/u_PH1P_PHY_PLL.clkc[4]}]
rename_clock -name {HDMI_SERIAL_CLK} [get_clocks {u_PLL/ph1p_phy_pll_wrapper_25a56e5ce2f9_Inst/u_PH1P_PHY_PLL.clkc[5]}]

rename_clock -name {MIPI_RX_BYTE_CLK} [get_clocks {u_mipi_dphy_rx_ph1p_mipiio_wrapper/u_ph1p_mipiio_rx_wrapper/u_PH1P_LOGIC_DPHY_MIPI_RX.o_fabric_div4_8_clk}]

# I2C state now uses clock enables in pll_clk_24m; no fabric generated clock.
# SWUG200 5.3.2: bound asynchronous data paths, then allow FIFO IP to tighten
# Gray-pointer paths below the smaller source/destination period.
# Reviewed against SWUG200 PDF42-43 and actual generated clocks.
# Replaces legacy 100ns with 7.2ns (<7.5ns user DDR period).
# These bounds do not replace CDC/reset/held-data protocol review.
# Keep collections inline: TD SDC timing parser does not expand Tcl collection variables.
set_max_delay -from [get_clocks {sys_clk_50m pll_clk_100m pll_clk_24m HDMI_PIXEL_CLK HDMI_SERIAL_CLK}] -to [get_clocks {mipi_rx_ck_pad MIPI_RX_BYTE_CLK}] -datapath_only 7.200
set_max_delay -from [get_clocks {mipi_rx_ck_pad MIPI_RX_BYTE_CLK}] -to [get_clocks {u_ph1p35_324_ddr_wrapper/u_ddr2/usr_clk u_ph1p35_324_ddr_wrapper/u_ddr2/ddr_clk}] -datapath_only 7.200
set_max_delay -from [get_clocks {u_ph1p35_324_ddr_wrapper/u_ddr2/usr_clk u_ph1p35_324_ddr_wrapper/u_ddr2/ddr_clk}] -to [get_clocks {mipi_rx_ck_pad MIPI_RX_BYTE_CLK}] -datapath_only 7.200
set_max_delay -from [get_clocks {sys_clk_50m pll_clk_100m pll_clk_24m HDMI_PIXEL_CLK HDMI_SERIAL_CLK}] -to [get_clocks {u_ph1p35_324_ddr_wrapper/u_ddr2/usr_clk u_ph1p35_324_ddr_wrapper/u_ddr2/ddr_clk}] -datapath_only 7.200
set_max_delay -from [get_clocks {u_ph1p35_324_ddr_wrapper/u_ddr2/usr_clk u_ph1p35_324_ddr_wrapper/u_ddr2/ddr_clk}] -to [get_clocks {sys_clk_50m pll_clk_100m pll_clk_24m HDMI_PIXEL_CLK HDMI_SERIAL_CLK}] -datapath_only 7.200

# BOARD_REVIEW selective first-stage CDC bounds
# Board _2/_7 + DS1300 v1.2 PDF160: B17 is HR BANK32 GPIO input.
# Shared HPD/EN level is asynchronous, not a source-synchronous data bus.
# Only pad-to-first-stage is exempt; meta-to-sync remains timed.
# User DDR 7.5ns minimum period: 7.2ns leaves 0.3ns routing allowance.
# Existing FIFO Gray constraints remain authoritative and are audited separately.
set_max_delay -to [get_regs {u_video_in/fs_sync[0] u_video_in/good_sync[0] u_video_out/vs_sync[0] u_video_out/live_sync[0]}] -datapath_only 7.200
# Pixel-domain diagnostic levels: period 13.333ns, bound 12.8ns.

# Board _10: J3/U53 open-drain SDA, sampled through two parent-clock stages.
set_false_path -from [get_ports {IO_cam_sda}] -to [get_regs {u_uicfgcs520/u_i2c/sda_meta}]


# DDR recalibration monitor: asynchronous level, only first synchronization stage.
set_max_delay -from [get_clocks {u_ph1p35_324_ddr_wrapper/u_ddr2/usr_clk}] -to [get_regs {u_ddr_recovery/calib_sync[0]}] -datapath_only 7.200

# LF14 passive metadata additions; original video constraints above retained.
# Proposed ONLY. Not run through TD and no physical endpoint/Active claim.
# Root instance name assumed u_latency_frame. Append after unchanged baseline.
# Do not cut the related PLL clk0/time100 -> clk4/HDMI75 clock relationship.
# Source0 Gray time to CSI: < both 10ns time clock and 9.660ns byte clock.
set_max_delay -from [get_regs {u_latency_frame/u_time/time_gray*}] -to [get_clocks {MIPI_RX_BYTE_CLK}] -datapath_only 7.200
# Count changes by exactly one for each first-valid RAW frame, no binary bus CDC.
# Held mailbox toggle first stages ONLY; all second-stage Q->D stays timed.
set_max_delay -from [get_regs {u_latency_frame/src_req}] -to [get_regs {u_latency_frame/src_req_sync[0]}] -datapath_only 7.200
set_max_delay -from [get_regs {u_latency_frame/src_ack}] -to [get_regs {u_latency_frame/src_ack_sync[0]}] -datapath_only 7.200
set_max_delay -from [get_regs {u_latency_frame/display_req}] -to [get_regs {u_latency_frame/display_req_sync[0]}] -datapath_only 7.200
set_max_delay -from [get_regs {u_latency_frame/display_ack}] -to [get_regs {u_latency_frame/display_ack_sync[0]}] -datapath_only 7.200
set_max_delay -from [get_regs {u_latency_frame/source_fault}] -to [get_regs {u_latency_frame/source_fault_sync[0]}] -datapath_only 7.200
set_max_delay -from [get_regs {u_latency_frame/display_fault}] -to [get_regs {u_latency_frame/display_fault_sync[0]}] -datapath_only 7.200
# Held binary buses: synchronized request + one settle cycle, immutable until
# returned ACK. Destination CLOCK limits exclude ordinary same-domain aliases.
# Expected raw receivers: 97 DDR descriptor bits, 65 display fields,96 stats.
set_max_delay -from [get_regs {u_latency_frame/src_payload*}] -to [get_clocks {u_ph1p35_324_ddr_wrapper/u_ddr2/usr_clk}] -datapath_only 7.200
set_max_delay -from [get_regs {u_latency_frame/display_payload*}] -to [get_clocks {HDMI_PIXEL_CLK}] -datapath_only 7.200
# Metadata common asynchronous assertion only. On PH1P a physical two-register
# slice may share ASR, so this may also cover release-chain stage2 ASR. This
# exception does NOT cover stage1-Q -> stage2-D or stage2-Q -> ordinary users.
# Need actual TD physical-cell/arc audit before implementation acceptance.
set_false_path -through [get_nets {u_latency_frame/metadata_reset_n}] -to [get_regs {u_latency_frame/c_reset[0] u_latency_frame/c_reset[1] u_latency_frame/d_reset[0] u_latency_frame/d_reset[1] u_latency_frame/h_reset[0] u_latency_frame/h_reset[1]}]

# Held watchdog request: DDR user clock to live 100 MHz reference.
# First-stage only; stage1 Q -> stage2 D and controller fanout remain timed.
set_max_delay -from [get_clocks {u_ph1p35_324_ddr_wrapper/u_ddr2/usr_clk}] -to [get_regs {u_ddr_recovery/request_sync[0]}] -datapath_only 7.2
# calibration_still_valid asynchronously captures calibration loss. No new
# blanket false path is added. Physical ASR/recovery/removal scope must be
# checked during the future implementation before any bitstream release.


# MOT15 proposed narrow CDC constraints. Root must audit actual post-map/route
# endpoints and ASR arcs. No blanket domain false_path or clock-group cuts.
set_max_delay -from [get_regs {u_motion/req}] -to [get_regs {u_motion/req_sync[0]}] -datapath_only 7.200
set_max_delay -from [get_regs {u_motion/ack}] -to [get_regs {u_motion/ack_sync[0]}] -datapath_only 7.200
set_max_delay -from [get_regs {u_motion/source_quarantine}] -to [get_regs {u_motion/unsafe_sync[0]}] -datapath_only 7.200
# 96-bit binary payload and its one-bit re-arm sideband remain immutable from
# request until returned ACK. Clock limit excludes ordinary same-domain aliases.
set_max_delay -from [get_regs {u_motion/held_bus*}] -to [get_clocks {HDMI_PIXEL_CLK}] -datapath_only 7.200
set_max_delay -from [get_regs {u_motion/held_rearm}] -to [get_clocks {HDMI_PIXEL_CLK}] -datapath_only 7.200
# Async assertion only to the two local release chains. Physical slice ASR can
# be shared by both stages. Their DATA chain must retain ordinary timing.
set_false_path -through [get_nets {u_motion/metadata_reset_n}] -to [get_regs {u_motion/c_release[0] u_motion/c_release[1] u_motion/h_release[0] u_motion/h_release[1]}]

# AQ18 single-message mailboxes. First synchronization stages only; subsequent
# synchronizer DATA paths remain timed. Held payload is captured only after
# two request flops plus a settle cycle, and remains immutable through ACK.
set_max_delay -from [get_regs {u_auto_exposure/u_stats_mailbox/s_req_toggle}] -to [get_regs {u_auto_exposure/u_stats_mailbox/d_req_sync1}] -datapath_only 7.200
set_max_delay -from [get_regs {u_auto_exposure/u_stats_mailbox/d_ack_toggle}] -to [get_regs {u_auto_exposure/u_stats_mailbox/s_ack_sync1}] -datapath_only 7.200
set_max_delay -from [get_regs {u_auto_exposure/u_stats_mailbox/s_payload_hold*}] -to [get_clocks {pll_clk_24m}] -datapath_only 7.200
set_max_delay -from [get_regs {u_quality_display_mailbox/s_req_toggle}] -to [get_regs {u_quality_display_mailbox/d_req_sync1}] -datapath_only 7.200
set_max_delay -from [get_regs {u_quality_display_mailbox/d_ack_toggle}] -to [get_regs {u_quality_display_mailbox/s_ack_sync1}] -datapath_only 7.200
set_max_delay -from [get_regs {u_quality_display_mailbox/s_payload_hold*}] -to [get_clocks {HDMI_PIXEL_CLK}] -datapath_only 7.200


# Validated against imported joint01 gate DB ccadf60bef135c61c29b724023aa39ef8c5ac4719ac9d1c6bfc2e822ad20977d.
# Recheck after final reader/source revision and again at routed FINAL DB.
# CORE=HDMI_PIXEL_CLK13.333ns, CSI=MIPI_RX_BYTE_CLK9.660ns. No domain cuts.
set_max_delay -from [get_regs {u_meter_pair/pipeline/frame_cache/ack}] -to [get_regs {u_meter_pair/pipeline/frame_cache/ack1}] -datapath_only 7.200
set_max_delay -from [get_regs {u_meter_pair/pipeline/frame_cache/req}] -to [get_regs {u_meter_pair/pipeline/frame_cache/req1}] -datapath_only 7.200
set_max_delay -from [get_clocks {HDMI_PIXEL_CLK}] -to [get_regs {u_meter_pair/pipeline/frame_cache/cancel1}] -datapath_only 7.200
set_max_delay -from [get_regs {u_meter_pair/pipeline/frame_cache/cancel_generation}] -to [get_regs {u_meter_pair/pipeline/frame_cache/generation1}] -datapath_only 7.200
set_max_delay -from [get_regs {u_meter_pair/pipeline/frame_cache/generation_ack}] -to [get_regs {u_meter_pair/pipeline/frame_cache/generation_ack1}] -datapath_only 7.200
# Exact vector patterns[*], not broadname*: broadname* also matches FFcell D
# aliases in this TD version. Epoch/cfg benchmark aliases share one actualbit.
set_max_delay -from [get_regs {u_meter_pair/pipeline/frame_cache/payload_id[*] u_meter_pair/pipeline/frame_cache/payload_cfg[*] u_meter_pair/pipeline/frame_cache/payload_capture_cycles[*] u_meter_pair/pipeline/frame_cache/payload_generation}] -to [get_clocks {HDMI_PIXEL_CLK}] -datapath_only 7.200
set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/capture/request_toggle}] -to [get_regs {u_meter_pair/pipeline/reader/live/capture/request_sync[0]}] -datapath_only 7.200
set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/capture/release_toggle}] -to [get_regs {u_meter_pair/pipeline/reader/live/capture/release_sync[0]}] -datapath_only 7.200
set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/capture/request_ack}] -to [get_regs {u_meter_pair/pipeline/reader/live/capture/ack_sync[0]}] -datapath_only 7.200
set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/capture/commit_toggle}] -to [get_regs {u_meter_pair/pipeline/reader/live/capture/commit_sync[0]}] -datapath_only 7.200
set_max_delay -from [get_clocks {MIPI_RX_BYTE_CLK}] -to [get_regs {u_meter_pair/pipeline/reader/live/capture/armed_sync[0]}] -datapath_only 7.200
set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/capture/request_payload[*]}] -to [get_clocks {MIPI_RX_BYTE_CLK}] -datapath_only 7.200
# Metadatareason is unconsumed/optimized0bits in joint01, not waived if used later.
set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/capture/x0[*] u_meter_pair/pipeline/reader/live/capture/y0[*] u_meter_pair/pipeline/reader/live/capture/stride[*] u_meter_pair/pipeline/reader/live/capture/radius[*] u_meter_pair/pipeline/reader/live/capture/hint[*] u_meter_pair/pipeline/reader/live/capture/config_id[*] u_meter_pair/pipeline/reader/live/capture/target[*] u_meter_pair/pipeline/reader/live/capture/published_id[*] u_meter_pair/pipeline/reader/live/capture/metadata_good}] -to [get_clocks {HDMI_PIXEL_CLK}] -datapath_only 7.200
# Only global asynchronous assertion to actual22 reset/enable-release FF ASR.
# DATA stage1->stage2 and local-release-Q->ordinary users remain normally timed.
set_false_path -through [get_nets {u_meter_pair/arst_n}] -to [get_regs {u_meter_pair/release_hdmi/release_ff[*] u_meter_pair/release_csi/release_ff[*] u_meter_pair/pipeline/core_release[*] u_meter_pair/pipeline/csi_release[*] u_meter_pair/pipeline/enabled_csi[*] u_meter_pair/pipeline/frame_cache/c_release[*] u_meter_pair/pipeline/frame_cache/p_release[*] u_meter_pair/pipeline/reader/reset_release[*]}]

# CAP3 diagnostics are held in CSI LEASED until existing commit/lease release.
# Use the original7.2ns held-data budget; preserve all ordinary synchronous paths.
set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/capture/diag_first_causes[*] u_meter_pair/pipeline/reader/live/capture/diag_close_flags[*] u_meter_pair/pipeline/reader/live/capture/bad u_meter_pair/pipeline/reader/live/capture/full_seen u_meter_pair/pipeline/reader/live/capture/groups_seen[*] u_meter_pair/pipeline/reader/live/capture/canonical_count[*] u_meter_pair/pipeline/reader/live/capture/metadata_reason[*]}] -to [get_clocks {HDMI_PIXEL_CLK}] -datapath_only 7.200

# MCU_ROI_LIVE: separate names from the DDR IP's historical mcu_clk.
# Official50MHz wrapper is a real direct wire ahb_clk=core_clk. Both hard-MCU
# and fabric AHB paths must be checked in FINAL; no hard-DPLL output is guessed.
rename_clock -name {MCU_ROI_50} [get_clocks {u_mcu_clocks/ph1p_phy_pll_wrapper_08353213927c_Inst/u_PH1P_PHY_PLL.clkc[0]}]
rename_clock -name {MCU_TIMER_25} [get_clocks {u_mcu_clocks/ph1p_phy_pll_wrapper_08353213927c_Inst/u_PH1P_PHY_PLL.clkc[1]}]
set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/offer_toggle}] -to [get_regs {u_meter_pair/pipeline/reader/live/offer_sync[0]}] -datapath_only 7.200
set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/job_live}] -to [get_regs {u_meter_pair/pipeline/reader/live/live_sync[0]}] -datapath_only 7.200
set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/ret_ack}] -to [get_regs {u_meter_pair/pipeline/reader/live/retack_sync[0]}] -datapath_only 7.200
set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/ret_toggle}] -to [get_regs {u_meter_pair/pipeline/reader/live/ret_sync[0]}] -datapath_only 7.200
set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/bridge/platform_armed}] -to [get_regs {u_meter_pair/pipeline/reader/live/armed_sync[0]}] -datapath_only 7.200
# Descriptor held through complete return/ACK;2sync+settle precedes capture.
set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/offer_payload[*]}] -to [get_clocks {MCU_ROI_50}] -datapath_only 7.200
set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/return_token[*] u_meter_pair/pipeline/reader/live/return_target[*] u_meter_pair/pipeline/reader/live/return_config[*] u_meter_pair/pipeline/reader/live/return_source_crc[*] u_meter_pair/pipeline/reader/live/return_cpu_crc[*] u_meter_pair/pipeline/reader/live/return_bytes[*] u_meter_pair/pipeline/reader/live/return_code[*] u_meter_pair/pipeline/reader/live/return_mean[*] u_meter_pair/pipeline/reader/live/return_gradient[*] u_meter_pair/pipeline/reader/live/return_qreason[*] u_meter_pair/pipeline/reader/live/return_kind[*] u_meter_pair/pipeline/reader/live/return_qgood}] -to [get_clocks {HDMI_PIXEL_CLK}] -datapath_only 7.200
# Common global assertion only. Video reset is a revoke, not a slot reset.
# The normal Q->D release chains and local FF/RAM DATA paths remain timed.
set_false_path -through [get_nets {S_mcu_arst_n}] -to [get_regs {S_mcu_release[*] u_meter_pair/pipeline/reader/live/core_reset[*] u_meter_pair/pipeline/reader/live/mc_reset[*] u_meter_pair/pipeline/reader/live/capture/cr[*] u_meter_pair/pipeline/reader/live/capture/pr[*]}]

# Readonly one-shot diagnostic only. Append to a NEW private project.
# Requests/result/ACK use two synchronizers + explicit settle. No clock cuts.
set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/observer/d_request}] -to [get_regs {u_meter_pair/pipeline/reader/live/observer/request_sync[0]}] -datapath_only 7.200
set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/observer/s_result}] -to [get_regs {u_meter_pair/pipeline/reader/live/observer/result_sync[0]}] -datapath_only 7.200
set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/observer/d_ack}] -to [get_regs {u_meter_pair/pipeline/reader/live/observer/ack_sync[0]}] -datapath_only 7.200
# s_hold remains immutable from publication through returned ACK and DONE.
# Exact register-vector patterns avoid TD's D aliases matched by broadname*.
set_max_delay -from [get_regs {u_meter_pair/pipeline/reader/live/observer/s_hold[*]}] -to [get_regs {u_meter_pair/pipeline/reader/live/observer/d_snapshot[*]}] -datapath_only 7.200
# Only common-global async assertion to the four local release flops.
# Do not suppress their normal Q->D or local-release-Q -> ordinary DATA paths.
set_false_path -through [get_nets {S_mcu_arst_n}] -to [get_regs {u_meter_pair/pipeline/reader/live/observer/s_reset[*] u_meter_pair/pipeline/reader/live/observer/d_reset[*]}]

# Only physical asynchronous switch inputs to their first synchronizer stages.
# sync0->sync1 and every consumer remain ordinarily timed in the CSI domain.
set_false_path -from [get_ports {I_saturation_sw[*]}] -to [get_regs {u_saturation_sw/sync0[*]}]

# Manual REF switches: only async input pads to first synchronizer FFs.
# sync0->sync1 and all HDMI consumers remain normally timed.
set_false_path -from [get_ports {I_preset_sw[*]}] -to [get_regs {u_meter_pair/reference_control/switch_sync0[*]}]
