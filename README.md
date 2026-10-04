# DNG 文件结构与 RAW 数据复核

本仓库提供两份 DNG 样本、只读检查程序、检查日志和原字节提取的 JPEG，用于复现文件目录解析、数据区段边界计算和未压缩 RAW 字节统计。结论限定于仓库内 SHA-256 对应的样本。

## 实测结果

| 项目 | IMG_20261003_205510.dng | IMG_20261003_205503.dng |
|---|---:|---:|
| 文件字节数 | 51,380,224 | 110,393,705 |
| RAW 分辨率 | 5760 × 4320 | 8192 × 6144 |
| RAW 存储位深 | 16 bit | 16 bit |
| RAW 压缩标记 | 1，未压缩 | 1，未压缩 |
| RAW 起点 | 4,036,050 | 9,730,409 |
| RAW 声明长度 | 49,766,400 | 100,663,296 |
| RAW 声明结束边界，不含终点 | 53,802,450 | 110,393,705 |
| 声明范围中缺少的字节 | **2,422,226** | 0 |
| 实际扫描的 RAW 字节 | 47,344,174 | 100,663,296 |
| 非零 RAW 字节 | **0** | 100,466,091 |

205510 的主 JPEG 可以从原文件偏移 301,332 处提取，长度为 3,379,426 字节，图像为 5760 × 4320、8 bit/通道。提取只是复制原字节，不是 RAW 恢复或重新编码。

“RAW 声明范围越界”与“现存 RAW 区段全零”是字节层面的事实；它们不能单独确定错误发生在拍摄、保存、导出还是传输阶段，也不能证明 Photoshop 首先因哪个字段拒绝该文件。205503 存在非零 RAW 数据，并不自动证明所有像素正确或全部软件都能解码。

## 下载完整样本

两份 `.dng` 使用 Git LFS 保存，其中 205503 超过 GitHub 普通文件的 100 MiB 限制。安装 [Git LFS](https://git-lfs.com/) 后运行：

```bash
git lfs install
git clone https://github.com/aoyukkk/dng-raw-evidence.git
cd dng-raw-evidence
git lfs pull
```

不要把只有几行文字的 LFS 指针文件当作 DNG。先核对文件字节数及 SHA-256。网页下载 ZIP 的 LFS 内容取决于仓库归档设置，建议使用上述克隆方式。

## 运行

环境：Python 3.9 或以上，仅使用标准库，无需 `pip install`。

Windows 用户可双击 **`双击运行_DNG检查.cmd`**。启动器依次支持 `DNG_PYTHON` 指定的解释器、本机 Codex 缓存的 Python、`py -3` 和 PATH 中的 `python`。两份 DNG 放在脚本同目录即可。

命令行运行：

```bash
python run_dng_check.py
```

指定输出根目录：

```bash
python run_dng_check.py --outdir results
```

程序连续完成 10 项检查，不包含截图提示或逐步暂停。每次创建独立的时间命名结果目录，保存分步日志、完整日志、JSON 摘要及提取的 JPEG。源 DNG 只读，运行前后比较 SHA-256。

更详细的 ExifTool 交叉核对、HxD 字段地址、手动 JPEG 提取方法和可选受控实验，见 [使用说明](使用说明.md)。

## 文件组织

```text
.
├── README.md
├── 使用说明.md
├── 一键检查使用说明.txt
├── dng_evidence.py
├── run_dng_check.py
├── 双击运行_DNG检查.cmd
├── IMG_20261003_205510.dng
├── IMG_20261003_205503.dng
├── 检查结果/
│   └── 20261004_185309/        原有检查记录及提取文件
│   └── 独立ExifTool复核/      ExifTool 13.59 字段交叉核对
├── 工具/                     原文件夹中的 HxD、ExifTool 发行文件
├── evidence-manifest.json    文件清单、字节数及 SHA-256
├── THIRD_PARTY_NOTICES.md
├── .gitattributes            DNG 使用 LFS，其余文件不转换换行
└── .gitignore                排除视频素材与 Python 缓存
```

桌面文件夹中的 `视频素材/` 和 Python 缓存不纳入仓库。原有检查记录保留当时的输出，包括本机路径；新生成记录使用当前脚本，可能在说明文本和路径上不同，但对应样本的字节统计应一致。

## 样本 SHA-256

```text
IMG_20261003_205510.dng
95f24b254a39a88cf33d38154343cfebca8d6b203db0f7bcab42c347789118a2

IMG_20261003_205503.dng
dcd24880e8212e9022a2176736a40f7520d06ca335d8f6b3f62e05352f290981
```

## 结论与限制

- `BitsPerSample=16` 表示存储位深，不能据此认定传感器 ADC 原生有效精度为 16 bit。
- 未覆盖在文件内的声明字节是缺失，不应计为已读取的零字节。
- 本程序支持这些样本所用的经典 TIFF、strip 结构；不是完整 DNG SDK 验证器。
- RAW 全零判断建立在本样本 `Compression=1` 的未压缩表示上，不可直接套用于压缩 RAW 的字节流。
- JPEG 标记解析不等于完整像素解码，提取文件还应在图像软件中实际打开验证。
- 本仓库不据此对某品牌、型号或全部拍摄文件作推广性判断。

## 参考与第三方工具

- [Adobe DNG 与 TIFF 规范入口](https://www.adobe.com/support/downloads/dng/dng_sdk.html)
- [ExifTool 官方文档](https://exiftool.org/exiftool_pod2.html)
- [HxD 官方网站](https://mh-nexus.de/en/hxd/)
- [GitHub 大文件说明](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github)

第三方发行文件沿用各自的许可和版权声明，详见 [第三方工具说明](THIRD_PARTY_NOTICES.md)。本仓库没有为第三方软件或样本附加统一的开源授权。
