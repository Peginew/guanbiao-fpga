# 观表 · GuanBiao FPGA

基于安路 **HX1P35A / PH1P35MDG324-3** 的实时图像处理与仪表视觉巡检项目，对应2026年全国大学生嵌入式芯片与系统设计竞赛安路赛题二。

本仓库是统一的公开提交入口，访客无需登录即可阅读和下载。内容包括FPGA逻辑、片内MCU算法、ESP32小车程序、训练权重、实拍图像与标注、工程依赖和验证记录。

## 系统组成

SC500CS摄像头输入经MIPI接入、像素恢复和DDR帧缓存，送入实时图像处理与HDMI显示通路。仪表识读采用机械轴心、径向指针和六印刷点三个轻量网络，结合整数几何匹配与标定计算；独立保留ESP32三轮车巡检控制及双向UART协议。

| 入口 | 内容 |
|---|---|
| [FPGA部署基线](fpga/board_baseline) | 已部署87da版本的团队RTL、约束、参数及工程配置 |
| [MCU固件](firmware/mcu_repair) | 793d异常恢复修复源码、整数推理与3433参数模型 |
| [算法与训练](algorithms) | 训练、量化、几何匹配、三份选定权重及既有评价记录 |
| [数据集](datasets) | 497张原始PNG索引、472张canonical标注、历史分区及使用说明 |
| [小车程序](rover/integrated) / [通信协议](protocol) | ESP32巡检控制与FPGA双向UART接口 |
| [独立候选](fpga/candidates) | 分阶段显示、共享映射与小车合并候选源工程 |
| [实现状态](docs/IMPLEMENTATION_STATUS.md) | 已部署版本、离线候选及尚待验证的边界 |
| [资源图](docs/resource_utilization.png) / [参考文献](docs/references.txt) | 资源占用与25条参考资料 |

## 如何使用

```bash
git clone https://github.com/Peginew/guanbiao-fpga.git
cd guanbiao-fpga
```

请先阅读对应目录README。FPGA工程需要Anlogic TD 6.2.1、官方IP、HX1P35A例程及MCU SDK；须按[依赖清单](DEPENDENCIES_REQUIRED.json)补齐受限第三方实现并配置本机路径。Python算法依赖见[requirements.txt](algorithms/requirements.txt)。本次按原字节整理源文件，部分历史脚本仍有源工作站路径和SHA断言，尚未整理为跨电脑一键构建。

原始图像保留像素、文件名和SHA。标注公开副本使用`datasets/`下的相对路径；训练与评价之前请阅读[数据使用历史](datasets/current_usage.json)，避免将已使用场次再次当作独立测试。原始采集视频的分卷入口见[datasets/raw_video](datasets/raw_video)。

## 验证范围

- **视频与物理实现：** 已部署87da基线具备独立的布局布线及存储核对记录。资源为Slice 20096/21216（94.72%）、LUT6 18821/21216（88.71%）、FF 22978/42432（54.15%）、ERAM 102/108（94.44%）、DSP 38/40（95.00%）、PLL 4/6（66.67%）。这些数据对应该基线，不套用到后续候选。
- **软件算法：** 冻结C组59张中56张有表、3张负例；融合方法输出31条，MAE约0.16847psi，仍有25张有表图拒读，负例0/3输出。输入为人工框HDMI代理ROI，不能当作自动CSI输入的实板结果。详细记录及历史失败保留在`algorithms/`。
- **尚待验证：** 当前自然任务的轴心、针向与压力读数仍未完成稳定实板验收；793d受控异常恢复通过不等于读表完成。分阶段显示、共享映射和小车合并版分别保存，不能拼接各自通过项宣称整机闭环已通过。REF预设值不是真实测量结果。

## 开源许可

团队原创软件采用[MIT License](LICENSE)，团队自采图像与原创标注采用[CC BY 4.0](datasets/LICENSE)。第三方代码保留原Apache-2.0、BSD-3-Clause等声明。厂商工具、许可证、加密IP和未取得公开再分发授权的参考实现仅列出获取方式，详见[第三方说明](THIRD_PARTY_NOTICES.md)。商标与第三方标识不随本项目授权。

公开归档不包含账号凭据、浏览器会话、工具安装包和构建缓存。整理与上传过程未修改生产工程、模型、板卡或小车状态。
