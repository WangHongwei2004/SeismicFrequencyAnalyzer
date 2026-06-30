# 宽频带地震动卓越频率分析

> **📥 [下载 Windows 可执行程序（.exe）](https://github.com/WangHongwei2004/SeismicFrequencyAnalyzer/releases/latest)** — 无需安装 Python，下载后双击运行。

一个用于宽频带地震动 TXT/DAT 数据批量处理、频谱绘图和卓越频率判读的 PyQt5 桌面工具。
v1.1.0 新增 EVT 原始数据智能裁剪功能，可自动筛选最优线性数据段并导出为 DAT 格式。

软件版本：`v1.1.0`
作者：`WHW`
完成时间：`2026.6.27`（v1.0.0），`2026.6.29`（v1.1.0 EVT 裁剪）
GitHub：<https://github.com/WangHongwei2004/SeismicFrequencyAnalyzer>

## 功能特性

### 频谱分析（v1.0.0）
- 支持批量读取 `SeismicFrequencyAnalyzer/data` 中的三分量地震动 TXT 数据。
- 原始数据文件不随仓库发布，请在本地自行放入 TXT 数据。
- 同时计算直接法频谱和间接法功率谱密度。
- 自动生成原始计数时程图、校正加速度时程图、直接法频谱图、间接法频谱图。
- 在频谱图中标注 P1-P4 候选峰，辅助选择合理的卓越频率。
- 将各分量和平均谱的卓越频率、周期、峰值和 P1-P4 候选峰写入 CSV。
- 提供 PyQt5 图形界面，可设置选峰范围、显示频率上限和实际处理点数。

### EVT 原始数据智能裁剪（v1.1.0 新增）

- 支持直接读取 EDAS-24 系列数字地震仪生成的 `.evt` 原始二进制文件。
- **三分量联合自动筛选最优数据段**：滑动窗口 + 四维评分算法，对同一窗口位置的三分量分别评分后取平均，确保三分量时间对齐。
- 用户手动设置地震仪实际采样率（50 Hz / 100 Hz / 200 Hz），自动从 EVT 内部采样率重采样。
- 用户可自定义截取长度（1024/2048/4096/8192 点，或自定义任意点数）。
- 裁剪结果导出为单个 DAT 文件（放入 `evt_dat_output/` 目录），可直接被频谱分析流程读取。

#### EVT 二进制解析（`evt_reader.py`）

EVT 文件为 EDAS-24 地震仪的专有二进制格式，解析流程如下：

1. **文件头**（偏移 `0x000`–`0x322C`）：包含魔数 `digital event`、台站信息、仪器型号、经纬度、高程、记录时间等。文件头末尾可能存在校准参数（可变长度），通过搜索 `E-W` / `N-S` 标记确定数据区起始位置。
2. **前导搜索**（`_find_preamble`）：数据区起始处有一段前导数据，通过搜索连续 5 个绝对值 > 100 且相邻差值 < 1000 的 int32 值，定位第一个有效的 UD 数据块。
3. **50 块循环解码**：数据区由重复的 151-int32 循环组成（`_CYCLE_SIZE = 50×3 + 1 = 151`）。每个循环包含：
   - `[0, 50)` → UD 分量的 50 个 int32 采样
   - `[50, 100)` → NS 分量的 50 个 int32 采样
   - `[100, 150)` → EW 分量的 50 个 int32 采样
   - `[150]` → 1 个间隙值（跳过）
4. **记录时间提取**：优先从文件名解析（格式 `YYYYMMDDHHmm`），回退到文件头中的年/年积日/时分秒字段。

#### 最优数据段筛选算法（`segment_selector.py`）

核心算法为**四维滑动窗口评分**，对每个窗口位置计算总分，选取得分最高的数据段。

**滑动窗口参数**：
- 窗口大小：用户指定（1024/2048/4096/8192/自定义）
- 滑动步长：默认 `window_size // 4`（即窗口长度的 25%）
- 子窗口数量：4（用于平稳性评估）

**四维评分策略**（权重：平稳性 0.50，弯曲惩罚 0.25，尖峰惩罚 0.10，死数据惩罚 0.15）：

| 维度 | 评分方式 | 阈值 / 公式 |
|------|----------|-------------|
| **平稳性** | 窗口均分为 4 个子窗口，统计均值变异系数 `mean_cv` 和标准差变异系数 `std_cv`，评分 = `exp(-mean_cv×8) × exp(-std_cv×5)` | 变异系数越小越平稳 |
| **弯曲度惩罚** | 比较线性拟合与二次拟合的残差 RMS 改善量 `curvature_improvement = (RMS_linear - RMS_quad) / RMS_linear` | `≤ 0.003` 无惩罚；`≥ 0.03` 满惩罚 1.0；中间线性插值 |
| **尖峰检测** | 去趋势后基于 MAD（中位数绝对偏差）鲁棒统计：`robust_std = 1.4826 × MAD`，标记超过 `5 × robust_std` 的点为尖峰 | 尖峰占比 `≤ 1%` 无惩罚；`≥ 8%` 满惩罚 1.0 |
| **死数据惩罚** | 检测数据范围 < 1.0 或近零值占比过高 | 近零/零值占比 `≥ 50%` 满惩罚 1.0 |

**总分计算**：
```
total = max(0, min(1,  0.50 × 平稳性 − 0.25 × 弯曲惩罚 − 0.10 × 尖峰惩罚 − 0.15 × 死数据惩罚))
```

**三分量联合搜索**（`find_best_segment_three_component`）：
- 对同一窗口位置，分别计算 EW、NS、UD 三分量评分
- 综合得分 = `(EW_score + NS_score + UD_score) / 3`
- 保证三分量截取的是**同一时间窗口**，时间严格对齐
- 保留排名前 `top_k=10` 的候选窗口

#### FFT 重采样（`segment_selector.py`）

当用户设置的地震仪采样率与 EVT 内部采样率不同时，使用 FFT 重采样：

1. 对数据做 `rfft`，得到单边频谱
2. 若降采样：截断高频分量；若升采样：零填充高频
3. 做 `irfft` 还原时域，乘以采样率比 `target_sr / original_sr`

#### DAT 导出格式（`dat_exporter.py`）

裁剪结果导出为单个 DAT 文本文件，格式兼容现有 `load_traces()` 解析逻辑：

```
; samp: 100.0000; comp: 0; Data length:10.240000; Original: 202606071041.evt; ...
<UD 数据值，每行一个>
; samp: 100.0000; comp: 1; Data length:10.240000
<NS 数据值，每行一个>
; samp: 100.0000; comp: 2; Data length:10.240000
<EW 数据值，每行一个>
```

关键约束：`load_traces()` 将所有 `;` 开头的行解析为分量头，因此所有元信息必须编码到分量头行中，不能出现纯注释的 `;` 行。第一个分量头行包含完整元信息（原始文件名、记录时间、截取起止点号与时间、窗口评分），后续分量头仅含采样率、分量号和时长。

导出文件命名：`{原始文件名}_{截取起始时间}s.txt`

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
│   ├── analysis_worker.py                     # 后台频谱分析线程
│   ├── evt_preprocess_worker.py               # 后台 EVT 预处理线程（v1.1.0）
│   ├── evt_reader.py                          # EDAS EVT 二进制格式解析器（v1.1.0）
│   ├── segment_selector.py                    # 最优数据段自动筛选算法（v1.1.0）
│   ├── dat_exporter.py                        # DAT 格式导出模块（v1.1.0）
│   ├── app_info.py                            # 软件版本、作者和默认配置
│   ├── dominant_frequency_two_methods.py      # 直接法/间接法主分析流程
│   ├── ui_style.py                            # 界面样式表
│   ├── data/                                  # 本地 TXT 数据目录，原始数据不提交
│   ├── evt_dat_output/                        # EVT 裁剪 DAT 输出目录（v1.1.0）
│   └── two_method_spectrum_output/            # 直接法/间接法频谱分析结果
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

### 依赖

| 包 | 用途 |
|----|------|
| `numpy` | 数值计算、FFT、多项式拟合 |
| `matplotlib` | 频谱图、时程图绘制 |
| `PyQt5` | 图形界面 |

## 图形界面运行

```powershell
python SeismicFrequencyAnalyzer\analysis_ui.py
```

### EVT 预处理面板

界面顶部为 **"EVT 数据预处理 — 自动筛选最优线性段"** 面板：

1. **选择 EVT 文件**：点击"浏览..."选择 `.evt` 原始数据文件。
2. **设置截取长度**：从下拉框选择预设值（1024/2048/4096/8192 点），或勾选"自定义"手动输入任意点数。
3. **地震仪采样率**：选择地震仪实际工作采样率（50 Hz / 100 Hz / 200 Hz），默认 100 Hz。软件自动从 EVT 内部采样率重采样到目标采样率。
4. **点击"裁剪并导出 DAT"**：后台自动解析 EVT → 重采样 → 三分量联合搜索最优窗口 → 导出单个 DAT 文件。
5. 处理完成后点击"打开 DAT 输出目录"查看结果。

### 频谱分析面板

界面默认设置：

- 数据目录：`SeismicFrequencyAnalyzer/data`
- 输出目录：`SeismicFrequencyAnalyzer/two_method_spectrum_output`
- 选峰上限为 `0` 时表示不设上限，搜索到 Nyquist 频率。
- 频谱图显示上限为 `0` 时表示显示到 Nyquist 频率。
- 实际处理点数为 `0` 时表示使用全部样本。

## 命令行运行

### 频谱分析

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

说明：如果低频漂移影响卓越频率判断，建议将 `--min-peak-frequency` 或界面中的"选峰下限 Hz"设置为 `1` 或 `2`，再重新运行。

### EVT 裁剪（Python 脚本调用）

```python
from evt_reader import read_evt, find_first_valid_frame, get_component_array
from segment_selector import find_best_segment_three_component, resample_data
from dat_exporter import export_three_component_dat

# 读取 EVT
evt = read_evt("path/to/file.evt")
first = find_first_valid_frame(evt)
ew = get_component_array(evt, "EW")[first:]
ns = get_component_array(evt, "NS")[first:]
ud = get_component_array(evt, "UD")[first:]
h = evt.header

# 重采样到地震仪实际采样率（如 100 Hz）
INSTRUMENT_SR = 100.0
ew = resample_data(ew.astype(float), h.sample_rate_hz, INSTRUMENT_SR)
ns = resample_data(ns.astype(float), h.sample_rate_hz, INSTRUMENT_SR)
ud = resample_data(ud.astype(float), h.sample_rate_hz, INSTRUMENT_SR)

# 三分量联合搜索最优窗口（同一时间窗口，保证时间对齐）
result = find_best_segment_three_component(ew, ns, ud, window_size=1024,
                                           sample_rate_hz=INSTRUMENT_SR)
bw = result.best_window

# 导出单个 DAT 文件（兼容 load_traces()）
export_three_component_dat(
    ew_data=result.ew_data,
    ns_data=result.ns_data,
    ud_data=result.ud_data,
    output_path="output.dat",
    sample_rate_hz=INSTRUMENT_SR,
    start_sample_index=first + bw.start_index,
    end_sample_index=first + bw.end_index,
    original_file="file.evt",
    original_sample_rate_hz=h.sample_rate_hz,
)
```

## 输出文件

### 频谱分析输出

每个输入文件会生成一个同名子目录，包含：

- `*_01_raw_counts_time_history.png`
- `*_02_corrected_acceleration_time_history_um_s2.png`
- `*_03_direct_spectrum.png`
- `*_04_indirect_spectrum.png`

汇总表：

- `component_direct_indirect_results.csv`

CSV 中包含直接法和间接法的卓越频率、卓越周期、峰值，以及 P1-P4 候选峰频率、周期和峰值。

### EVT 裁剪 DAT 输出

输出目录：`SeismicFrequencyAnalyzer/evt_dat_output/`

生成单个 `.dat` 文件，命名格式：`{原始文件名}_{截取起始时间}s.txt`

DAT 文件格式兼容现有 TXT 解析逻辑（`load_traces()`），可直接用于频谱分析。详见上方"DAT 导出格式"小节。

头信息说明（编码在第一个分量头行中）：

| 字段 | 含义 |
|------|------|
| `samp` | 采样率（Hz） |
| `comp` | 分量号（0=UD, 1=NS, 2=EW） |
| `Data length` | 数据时长（秒） |
| `Original` | 原始 EVT 文件名 |
| `RecordTime` | 原始数据记录时间 |
| `StartIdx / EndIdx` | 截取起始/结束点号（相对于原始文件全帧） |
| `StartTime / EndTime` | 截取起止时间（秒） |
| `window_score` | 三分量综合评分 |
| `ew_score / ns_score / ud_score` | 各分量评分 |

## 打包

确认功能稳定后，可以使用 PyInstaller 打包：

```powershell
python -m PyInstaller SeismicFrequencyAnalyzer.spec --noconfirm
```

生成文件位于 `dist/SeismicFrequencyAnalyzer.exe`。

## 许可协议

本项目使用自定义非商业科研教学许可协议，允许个人自用、教学、科研、课程实验、非商业评估和非商业二次开发。

未经作者书面授权，不允许将本软件或其衍生版本用于商业产品、商业服务、付费咨询、付费培训、商业数据处理、商业工作流集成、转售、租赁、再许可或其他以商业利益为主要目的的场景。

如需商业授权，请通过作者 GitHub 主页联系：<https://github.com/WangHongwei2004>。
