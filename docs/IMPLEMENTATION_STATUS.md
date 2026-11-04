# 观表：PH1P35仪表视觉巡检公开源工程

本目录是比赛提交用公开源工程快照，不要求GitHub登录即可浏览；完整私有备份独立保存。

| 目录 | 内容与验收边界 |
|---|---|
| `fpga/board_baseline` | 已部署87da仪表识读工程的团队RTL、参数、约束及重建脚本。厂商核心需从官方资料取得。 |
| `firmware/mcu_repair` | 当前793d/347b异常恢复修复的应用源码，权重仍为3433参数；受控异常恢复已有实物证据，真实READ未验成功。 |
| `fpga/candidates/staged_display`、`firmware/staged_display` | 轴心/针向/PSI分别提交显示候选；原正式路线超时，未生成新bit或下载。 |
| `fpga/candidates/shared_mapper` | 后继共享映射候选；快照时正在布线，最终时序及位流待完成。 |
| `fpga/candidates/rover_integrated`、`rover/integrated`、`protocol` | 全系统合并源中的双向UART与三轮巡检源代码。组件/ESP编译和顶层展开通过，不代表新合并版物理实现/实车闭环通过。 |
| `docs/status_snapshots` | 归档时入口快照；路径使用来源别名，后续进度不自动更新。 |

## 如何复现

安装Anlogic TD6.2.1、厂商指定IP包、HX1P35A官方例程和对应MCU SDK，按照`DEPENDENCIES_REQUIRED.json`的路径/SHA补齐第三方依赖，再修改所选工程副本内的源电脑路径。代码、工程入口与ROM参数按字节归档；本次没有重新构建，也不宣称当前公开下载包能一键完整编译。厂商工具、许可证、加密IP、旧整包ZIP和预编译位流没有公开。

这些工程是分别保存的部署基线与候选，不应将各分支通过项拼成一份已经验收的最终整机。REF是预设显示，不是真实测量结果；自然读数、运动精度及视觉闭环需要相应实物证据。

第三方许可、保留声明和未公开依赖见`THIRD_PARTY_NOTICES.md`。数据集与大文件由仓库的独立数据归档入口提供，不在本代码目录重复打包。
