# ESP32 三轮车与训练版 Stable3s 源码配套

打开 `ESP32S3_4WD_Web_FPGA/ESP32S3_4WD_Web_FPGA.ino`。完整 41 个源码文件来自原 R24 ZIP `bb6d88ff…49ee12`，只修改生成协议头和 `LiteScanLink.h` 的两处 READ 等待常量引用。三轮车仍为 M2 左、M1 右；完整地图/路径预览/手动控制页与巡检页保留。默认未 ARM，标定和诊断连续模式仍须显式本地确认。

本次协议保持 V4、32 字节、小端、原 CRC/字段/消息编号，CFG 更新为 **8A2EBD57**。两端须使用上级 `protocol` 中的同一份生成头，旧 CFG 5948E36B 不能握手。

训练底座为指定的 `Stable3s_Trained_MCU_FPGA_Pair_20261103.zip`（e477c9fd…6a8c7d），FEATURE 0x064、PSI_Q8 0x124。MCU/权重由该 ZIP 原样配套，不含 2026-11-04 的 347b 异常恢复修复。UART RESULT 继续传原有归一化 bar U0.16；不把 PSI_Q8 直接当成 RAW_Q16。

训练版实例 READ job 上限 20 秒、单 phase 看门狗 24 秒，因此 ESP 从完整接收独立 READ_FENCE 起最多等待 **26000ms**。这是有界传输等待，不能保证忙等待、捕获或计算必定完成。重复 floor/心跳不重启期限；26000ms 到期失败，较晚 RESULT 不复活任务。原有 6 秒真实停稳、200ms 结果发布新鲜度、1000ms missing-floor、动作 5 秒、task 300 秒、point 600 秒均未放宽。取消、断链或原底层失败仍撤许可并停车。

`firmware/ESP32S3_4WD_Web_FPGA.ino.bin` 是本次真实 Arduino 离线编译产物：1060368 字节，SHA256 `a13acfb1ded9240c594fc1482f5c3dcce20993d0aacedf86858f98f3752caa4a`。官方核心为 esp32 3.3.10-cn，编译 exit0、177.08 秒；地址表仅为文件配套信息，未执行烧录。旧 R24 BIN 与原证据全部保存在 `history/r24_original`，不得当成新 BIN。

新源码实际 C++/RobotApp MockHAL 的 9 组、26222 项检查通过，另有新 CFG 的 54 个独立字节向量通过实际 C++ codec。检查包含旧 15 秒界限、24 秒、25999/26000ms、重复 floor、200/201ms 发布年龄、取消/断链、START/ACK 丢首包、6 秒停稳及双页控制。传感器、FG/GPIO/PWM 与毫秒为 host 注入，不是实车计时或新 C++↔RTL 整链证明。详细记录见 `source_freeze.json`、`component_completion.json` 与 `evidence`。

REF/LAST 不授权 READ 或自动下一点。实际 VU 仍显示 TEST 候选，`formalReadingValid=false`；只有显式诊断连续模式可按原规则记录真新候选并推进。这次仅交付合并源工程和 ESP 离线 BIN，未生成新的匹配 FPGA 位流、未验收新物理实现、未连接设备或车辆。
