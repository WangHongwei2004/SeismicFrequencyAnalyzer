# 宽频带地震动卓越频率分析

一个用于宽频带地震动 TXT 数据批量处理、频谱绘图和卓越频率判读的 PyQt5 桌面工具。

软件版本：`v1.0.0`  
作者：`WHW`  
完成时间：`2026.6.27`  
GitHub：<https://github.com/WangHongwei2004>

## 功能特性

- 支持批量读取 `SeismicFrequencyAnalyzer/data` 中的三分量地震动 TXT 数据。
- 原始数据文件不随仓库发布，请在本地自行放入 TXT 数据。
- 同时计算直接法频谱和间接法功率谱密度。
- 自动生成原始计数时程图、校正加速度时程图、直接法频谱图、间接法频谱图。
- 在频谱图中标注 P1-P4 候选峰，辅助选择合理的卓越频率。
- 将各分量和平均谱的卓越频率、周期、峰值和 P1-P4 候选峰写入 CSV。
- 提供 PyQt5 图形界面，可设置选峰范围、显示频率上限和实际处理点数。

## 项目结构

```text
.
├── README.md
├── requirements.txt
├── LICENSE
├── .gitignore
├── SeismicFrequencyAnalyzer.spec
├── SeismicFrequencyAnalyzer/
│   ├── analysis_ui.py                         # PyQt5 图形界面入口
│   ├── analysis_worker.py                     # 后台分析线程
│   ├── app_info.py                            # 软件版本、作者和默认配置
│   ├── dominant_frequency_two_methods.py      # 直接法/间接法主分析流程
│   ├── ui_style.py                            # 界面样式表
│   ├── data/                                  # 本地 TXT 数据目录，原始数据不提交
│   └── two_method_spectrum_output/            # 直接法/间接法输出结果
├── build/                                     # PyInstaller 构建缓存，建议不提交
└── dist/                                      # 打包后的 exe，建议发布时单独上传
```

## 环境安装

建议使用 Python 3.10 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

如果使用 Anaconda，也可以在当前环境中直接执行：

```powershell
python -m pip install -r requirements.txt
```

## 图形界面运行

```powershell
python SeismicFrequencyAnalyzer\analysis_ui.py
```

界面默认：

- 数据目录：`SeismicFrequencyAnalyzer/data`
- 输出目录：`SeismicFrequencyAnalyzer/two_method_spectrum_output`
- 选峰上限为 `0` 时表示不设上限，搜索到 Nyquist 频率。
- 频谱图显示上限为 `0` 时表示显示到 Nyquist 频率。
- 实际处理点数为 `0` 时表示使用全部样本。

## 命令行运行

```powershell
python SeismicFrequencyAnalyzer\dominant_frequency_two_methods.py
```

常用参数示例：

```powershell
python SeismicFrequencyAnalyzer\dominant_frequency_two_methods.py `
  --data-dir SeismicFrequencyAnalyzer\data `
  --output-dir SeismicFrequencyAnalyzer\two_method_spectrum_output `
  --min-peak-frequency 1 `
  --max-peak-frequency 25 `
  --plot-max-frequency 25
```

说明：如果低频漂移影响卓越频率判断，建议将 `--min-peak-frequency` 或界面中的“选峰下限 Hz”设置为 `1` 或 `2`，再重新运行。

## 输出文件

每个输入文件会生成一个同名子目录，包含：

- `*_01_raw_counts_time_history.png`
- `*_02_corrected_acceleration_time_history_um_s2.png`
- `*_03_direct_spectrum.png`
- `*_04_indirect_spectrum.png`

汇总表：

- `component_direct_indirect_results.csv`

CSV 中包含直接法和间接法的卓越频率、卓越周期、峰值，以及 P1-P4 候选峰频率、周期和峰值。

## 打包

确认功能稳定后，可以使用 PyInstaller 打包：

```powershell
python -m PyInstaller SeismicFrequencyAnalyzer.spec --noconfirm
```

生成文件位于 `dist/SeismicFrequencyAnalyzer.exe`。

## 开源说明

本项目使用 MIT License。提交到 GitHub 时，建议提交源码、README、requirements、LICENSE 和必要示例数据；`build/`、`dist/`、`__pycache__/`、分析输出图和 CSV 属于生成物，默认通过 `.gitignore` 排除。
