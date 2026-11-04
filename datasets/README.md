# 仪表实拍数据集

本目录提供项目自行采集的仪表图像索引、canonical标注、历史训练分区及最新使用情况。图像来自FPGA HDMI输出经USB采集后的1280×720画面，保留原始文件名与像素，不是传感器RAW，也不作为采集链逐字无损证明。

## 图像与标注范围

- 共497张PNG，恢复后放在`images/A/`至`images/H/`。Git仅保留部分原图作为预览；完整497张原图由同一仓库的Release提供。
- canonical标注为472张，A～H各59张；包含448张有表图及24张无表／非表反例。
- 另外25张PNG未纳入canonical标注，全部在`image_index.json`中标为`canonical=false`、`initial_split=unassigned`。不能自动视为已标注、训练或独立测试样本。
- `annotations.json`、`annotations.jsonl`、`annotations.csv`是同一canonical数据的不同导出。公开副本只重定位路径，保留原有几何坐标、压力、可见性、不确定度及分区语义；未知点不补造。
- `image_index.json/csv`列出全部497张图片的相对路径、SHA256、大小及canonical归属。全部472张canonical原图均重新计算SHA并与原注释一致。

## 分区与实际使用历史

初始按整场划分为D/E/F训练177张、G开发59张、H预留测试59张、A/B/C储备177张；`splits/`与`dataset_manifest.json`保留这套历史分区，不随机打散同场图片。

后续已有新的实际使用，不能再把旧“reserve/test”标签解释为从未使用：最终保留的六印刷点网络由D/E/F训练；A/B加入过295张扩充训练，但扩充权重未采用。G反复用于开发。H已用于早期候选的终检；C也已在最终候选冻结后进行一次终检。H与C此前参与过标注QA，均不能称真人盲测金标；已使用的场次不能继续用于新方案调参后宣称独立验收。准确状态见`current_usage.json`。

## 标签含义与边界

坐标采用原生1280×720图像坐标；框为半开区间`[x0,y0,x1,y1)`。轴心为真实机械轴心，细端为读数指针端；不可见或未知时保留null和可见性标志。压力主单位为psi，来自用户读表参考，未声明校准标准器精度。AI辅助标注仍含粗点及不确定度，不冒充全量人工精修金标。

图像中的FPGA OSD、框、针线、状态及数值属于当时系统输出，不是标注真值。部分画面有室内背景、圆物反例或采集人员的手。

## 数据许可

本项目自行采集的图像及原创标注采用 **CC BY 4.0（署名4.0国际）**，标准许可全文见仓库数据许可文件。使用时请署名“观表项目团队（Peginew/guanbiao-fpga）”、注明数据来源及所作修改。该许可仅覆盖团队有权许可的数据内容，图中第三方商标与标识的权利归原权利人。

## 文件使用

所有图片路径相对于本`datasets/`目录，例如`images/A/原文件名.png`。`annotations.json`保留标注任务当时的历史scope；后来的训练和评价以`current_usage.json`为准。训练与验证JSONL中的同名图片路径也已转换为相对路径。少量`source_file`字段保留了标注修订的历史来源相对引用，对应中间草稿不作为本数据包的必需输入。

## 下载完整原图

完整图像见[原图Release](https://github.com/Peginew/guanbiao-fpga/releases/tag/instrument-images-20261104)。图像以不压缩、不转码的ZIP保存，再切分为16MiB分卷；所有分卷、整ZIP及497个图像条目均有SHA256校验。`image_archive.json`列出下载地址、长度及校验值，`image_index.json`记录每张原图的SHA256。

安装Python 3.9或更新版本后，在仓库根目录运行以下命令；无需第三方Python包：

```bash
python datasets/download_images.py
```

脚本下载并逐片校验、合并ZIP、校验全部原图，再恢复到`datasets/images/`。已有同SHA图片直接跳过；已有不同内容会报错并拒绝覆盖。分卷缓存默认放在系统临时目录`GuanBiao-images-20261104`，便于断点后重用；建议预留约2.5GB磁盘空间。完整ZIP大小为847,403,594字节，共51片。

也可手动按文件名顺序合并Release分卷为`images.zip`，再离线校验恢复：

```bash
python datasets/download_images.py --archive /path/to/images.zip
```

只校验而不恢复时增加`--verify-only`。恢复后的路径与所有标注一致，无需更改标注坐标、标签或分区。

本公开整理不包含浏览器profile、Cookies、采集日志、用户电脑的绝对路径或视频录制过程文件；未编辑图像、重新标注、训练或访问设备。
