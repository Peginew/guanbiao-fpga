# 训练版 READ 期限解释

本说明不额外修改 wire、CFG 或所有权规则。实际生成 CFG 为 `8A2EBD57`；ESP 与 FPGA 使用本目录的对应 C++/VH 头。

FPGA `t06_meter_pair_link.v` 实例覆盖 `MAX_READ_JOB_CYCLES=1500000000`、`MAX_PHASE_CYCLES=1800000000`，75MHz 下分别为 20/24 秒。`t06_meter_visual_pipeline.v` 在 `REQUEST_ROI` 的 `roi_request && roi_ready` 接受时建立 `read_job_active` 并清零 `read_job_age`；phase 看门狗则随实际状态转换清零。因此这些计时原点不同于 UART READ_FENCE，24 秒也不是整个 floor→RESULT 的完成保证。

ESP `LiteScanLink.h` 首次完整解析并接受 typed `READ_FENCE` 后设置 `readAt_`；同一阶段的重复 floor 不重启它。RESULT 必须 elapsed `<26000`，expiry 在 elapsed `>=26000` 生效。26 秒是 24 秒阶段量级加 2 秒有限 UART/调度裕量的独立等待上限；底层忙、捕获/ARM/owner/job/phase 超时仍可提前失败。task 300 秒、point 600 秒及其他既有期限均未延长。

FPGA 没有新增 READ 总计时器。其 floor 事件必须真实发完最后 stop bit 后才能授予 `floor_published`，RESULT 仍要求真实 VU 发布→交付保守年龄不超过 200ms、源严格前进、独立 floor 与精确 owner/epoch。较长的静止计算时间不能替换成虚减发布年龄，LOC 源/捕获年龄也不能代替 READ 源/发布年龄。

实际新 C++ 边界测试与观察到的生产源引用见 `../esp32/evidence/read_timeout_analysis.json` 和 `host_checks_receipt.json`。它们不是 FPGA 新布局路由、实物读数或运动验收。
