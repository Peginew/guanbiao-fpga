# 原始采集视频与恢复方法

本目录记录原始 H 组采集视频的校验信息和恢复脚本。视频按原字节切分，未重新编码、裁剪或改变内容；完整分片存放于[本仓库的原始视频 Release](https://github.com/Peginew/guanbiao-fpga/releases/tag/raw-capture-20261104)，上传是否完成以该页面实际列出的资产为准。原始 PNG 与标注可从上一级数据集目录独立获取。

| 项目 | 内容 |
|---|---|
| 原文件名 | `video_070326_229311_77dbcd.avi` |
| 容器／编码 | AVI／FFV1 无损编码 |
| 分辨率／像素格式 | 1280 × 720／BGRA |
| 帧率／帧数 | 30 帧/秒／1397 帧（容器记录） |
| 时长 | 46.566667 秒 |
| 完整文件大小 | 1,367,634,672 字节 |
| 分片数量 | 150 片；前 59 片各 16 MiB，其后 90 片各 4 MiB，末片 291,568 字节 |
| 完整文件 SHA-256 | `f98285a9b6915c34db108fce03d00d2b027157da8c7f24488347dc702ffbeb4a` |

## 下载与恢复

1. 按本目录最新 `raw_video_manifest.json` 的 `parts` 清单，从 Release 下载全部分片，并放进同一个文件夹。当前采用前段 16 MiB、后段 4 MiB 的混合分片；文件名连续编号，它们是原始字节分片，不是 ZIP，不能单片播放。若曾下载旧版分片，请按新清单重新下载第 60 片及其后文件，避免同名旧分片混入。
2. 保留本目录的 `restore_video.py` 和 `raw_video_manifest.json`。使用 Python 3.9 或更新版本，在仓库根目录运行：

```powershell
python .\datasets\raw_video\restore_video.py --parts-dir .\raw_video_parts --output .\raw_capture.avi
```

脚本仅使用 Python 标准库，逐片核对文件名、顺序、大小和 SHA-256，再核对完整文件大小及 SHA-256。全部通过才生成最终 AVI，并输出 `"status": "PASS"`；已有输出文件不会被覆盖。恢复时需额外约 1.37 GB 磁盘空间。视频可用支持 FFV1 的播放器打开。

也可在仓库根目录用以下 PowerShell 命令下载所有分片，随后运行恢复命令；公开 Release 可用后无需登录或令牌：

```powershell
New-Item -ItemType Directory -Path .\raw_video_parts -Force | Out-Null
$videoManifest = Get-Content .\datasets\raw_video\raw_video_manifest.json -Raw | ConvertFrom-Json
foreach ($videoPart in $videoManifest.parts) {
    $videoUrl = $videoManifest.release_download_base + "/" + $videoPart.name
    Invoke-WebRequest -Uri $videoUrl -OutFile (Join-Path ".\raw_video_parts" $videoPart.name)
}
python .\datasets\raw_video\restore_video.py --parts-dir .\raw_video_parts --output .\raw_capture.avi
```

## 清单与本地验证

- `raw_video_manifest.json`：完整视频信息及每片大小、SHA-256和下载地址前缀。
- `SHA256SUMS.parts.txt`：方便外部校验工具使用的逐片 SHA-256。
- `LOCAL_VERIFICATION.json`：发布准备阶段的实际本地往返恢复记录。当前清单的全部 150 片与完整视频均校验通过，临时恢复副本随后删除，原文件未修改；此记录不代表远端上传已完成。

该视频用于保留采集来源与复现实验，不单独构成模型精度或整机功能的验收结论。
