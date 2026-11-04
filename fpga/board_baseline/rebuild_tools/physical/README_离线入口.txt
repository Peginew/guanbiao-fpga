本目录只服务 native_reader_landmark_s3_20261103/project，工程名 reader_landmark_s3。
原 d882 任务、bb1f 工程、MCU7b58与权重不由本目录修改。没有设备、下载或Flash入口。

默认总计划（不启动TD，也不生成运行目录）：
D:/python312/python.exe -X utf8 algorithm_work/meter_landmark_stable3s_20261103/physical/run_pipeline.py

1. 新工程源码完成且工具定稿后，仅生成待审核快照：
D:/python312/python.exe -X utf8 algorithm_work/meter_landmark_stable3s_20261103/physical/run_pipeline.py --snapshot
默认输出 physical/source_freeze.json，不覆盖已存在快照。快照不是准入。
root审源码、Stable3s保留与PSI接口，参照 synth_admission.template.json 签 synth_admission.json。
实际gate须 passed=true、stage=synth、manifest_sha256=新快照实际SHA；模板本身不可运行。

2. SYN先验证计划，再由root加 --run：
D:/python312/python.exe -X utf8 algorithm_work/meter_landmark_stable3s_20261103/physical/run_pipeline.py --stage synth --gate algorithm_work/meter_landmark_stable3s_20261103/physical/synth_admission.json
只有 --run 才启动原生TD。新SYN成功后从实际网表重新推导DDR当前实际语义成员及soft8×8 origin3,41；数量与完整列表须独审，不复制旧SYN名或要求历史数量。

3. 新SYN实核后由root/审核员提供 guided_ui_macros/anchor_plan.json、ui_macro_anchors.adc、macro_anchor_admission.json。
位置可沿成功d882的10个UI/Logo宏；name/type/全部参数INIT/ports必须在本版新SYN验证。
anchor_plan使用 reference_routed_DB（参考成功DB）、SYN、anchors_ADC、netlists、source_comparison、source_positions_log；anchors为{name,col,row,offset,type,is_placed}。
全部宏仅通过 read_adc 载入；保DDR软分组，其他逻辑重排。
入口（默认PLAN，root加 --run 才place）：
D:/python312/python.exe -X utf8 algorithm_work/meter_landmark_stable3s_20261103/physical/run_pipeline.py --stage place

4. 新place后审核员用 mapping_helpers.derive_asr 推导当前12个逻辑串行FF、实际物理ASR pins、clock roots及无额外FF。
输出必须放在本目录 guided_ui_macros：placed_asr_mapping.json/asr_literal.sdc/psi_literal.sdc。
derive_asr只生成单行声明式SDC，不生成旧交互overlay。以本版actual网表/DB/ADC/SYN做输入，不可复制旧pin名单。
独立审81IO、18clock对象、10宏实际Grid/Offset、clockBound及PSI17实际oqa/oqb源后签 guided_route_admission.json。
gate schema沿新runner：passed/stage=guided_route；place_receipt/source_DB/manifest/ASR_mapping/asr_literal/psi_literal refs；ASR_count；clock_macro_reviews refs；runner_sha256。
入口（默认PLAN，--run才route，timeout默认7200秒）：
D:/python312/python.exe -X utf8 algorithm_work/meter_landmark_stable3s_20261103/physical/run_pipeline.py --stage route
纯ASR/PSI read_sdc先于首timer；实际PSI17/17/0/0和ASR Max、Min各n/n/0/0强门通过后才route。effort normal/timing on/fix_hold on/post off。
不得为Stable3s新增普通DATA或普通DDR增加例外。

5. FINAL逐源PSI17的7.2ns与非负Slack、fresh ASR、81IO/18clock、捕获36、宏INIT、普通DDR和Stable3s普通DATA独审后，root签 bitgen_admission.json。
bitgen gate必须绑定新freeze SHA和latest_guided_route的实际DB SHA及独审refs；全部FINAL/容量/PSI/ASR/IOclockcapture/Stable3s_DATA字段true。
如侵占1200Slice车偏好须明确rover_reserve_release_authorized，不得冒满额预留。
仅同已签routed DB生成bit（默认PLAN，--run才bitgen）：
D:/python312/python.exe -X utf8 algorithm_work/meter_landmark_stable3s_20261103/physical/run_pipeline.py --stage bitgen --gate algorithm_work/meter_landmark_stable3s_20261103/physical/bitgen_admission.json

本目录只更新本任务latest_synth/latest_guided_place/latest_guided_route/latest_bitgen；不更新原任务、MCU、其它聊天工程或运行进程。
任何组件/布局/路由/文件通过均不等于新pair上板验收。
