# 第三方来源与许可说明

本仓库公开团队编写及修改的应用源码、接口、配置与验证工具，不将厂商IP或参考例程重新声明为团队原创。

## 明确开放许可的源文件

- Nuclei启动与异常处理汇编明确使用`SPDX-License-Identifier: Apache-2.0`。保留原Nuclei/Anlogic版权头，并附`LICENSES/Apache-2.0.txt`。本项目修改了启动/Flash到TCM路径；异常恢复修复单独保留在`firmware/mcu_repair`。
- Anlogic的芯片初始化汇编及链接脚本明确使用`SPDX-License-Identifier: BSD-3-Clause`。保留原版权头，并附`LICENSES/BSD-3-Clause.txt`。其中标准许可模板中的占位字段以各源文件保留的原版权声明为准。

## 仅保留获取说明的依赖

受保护的Anlogic HDMI/MIPI/DDR实现、没有公开再分发授权的厂商IP源码/生成实现、MiLianKe仅学习参考例程，以及未核清许可的预编译二进制和嵌套原包没有放入公开Git。逐文件相对路径、SHA256及文件内证据见根目录`DEPENDENCIES_REQUIRED.json`。这是本次公开范围选择，不宣告其他未核文件在任何情况下都禁止分发。

IP参数、引脚/时序配置与团队上层连接仍用于说明工程设计；需通过官方TD/IP工具和HX1P35A赛题资料重新取得缺失实现。公开仓库没有解密、替代或伪造厂商核心。

## 标识与来源

Anlogic标识用于赛题要求的显示与来源说明，商标权仍属于权利人。原文件中保留的厂商名称、第三方声明和许可头不得由项目总许可证覆盖或删除。
