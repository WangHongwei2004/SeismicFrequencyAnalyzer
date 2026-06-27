# -*- coding: utf-8 -*-
"""用直接法和间接法计算宽频带地震动卓越频率。

本程序复用原始 TXT 数据格式，不使用主程序中的 Welch 分段谱估计。
两种方法：
1. 间接法：时域信号 -> 自相关函数 -> FFT -> 功率谱 -> 除以频率分辨率 -> 功率谱密度。
2. 直接法：时域信号 -> FFT -> 幅值谱 -> 平方 -> 功率谱。
"""

from __future__ import annotations

import argparse
import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


INSTRUMENT_RESPONSE = 420.0
UM_PER_METER = 1_000_000.0

# 卓越频率只在这个频段内选取。0 表示不设对应边界。
# 例如只在 10-20 Hz 内找峰值：PEAK_SEARCH_MIN_FREQUENCY_HZ = 10.0,
# PEAK_SEARCH_MAX_FREQUENCY_HZ = 20.0。
PEAK_SEARCH_MIN_FREQUENCY_HZ = 0.0
PEAK_SEARCH_MAX_FREQUENCY_HZ = 0.0
PEAK_MARKER_COUNT = 4
PEAK_MARKER_MIN_SEPARATION_HZ = 0.5

COMPONENT_NAMES = {0: "UD", 1: "NS", 2: "EW"}

matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
matplotlib.rcParams["figure.facecolor"] = "#f6f8fb"
matplotlib.rcParams["axes.facecolor"] = "#ffffff"
matplotlib.rcParams["axes.edgecolor"] = "#c7ced8"
matplotlib.rcParams["axes.linewidth"] = 0.8
matplotlib.rcParams["axes.titleweight"] = "semibold"
matplotlib.rcParams["grid.color"] = "#d7dde6"
matplotlib.rcParams["xtick.color"] = "#2f3742"
matplotlib.rcParams["ytick.color"] = "#2f3742"

SPECTRUM_LINE_COLOR = "#2563a6"
DOMINANT_PEAK_COLOR = "#d92d20"
SECONDARY_PEAK_COLOR = "#7c3aed"
AVERAGE_LINE_COLOR = "#0f766e"


@dataclass(frozen=True)
class Trace:
    source_file: Path
    sample_rate_hz: float
    component_index: int
    component_name: str
    declared_duration_s: float | None
    raw_counts: np.ndarray

    @property
    def sample_count(self) -> int:
        return int(self.raw_counts.size)

    @property
    def duration_s(self) -> float:
        return self.sample_count / self.sample_rate_hz

    @property
    def time_s(self) -> np.ndarray:
        return np.arange(self.sample_count, dtype=float) / self.sample_rate_hz


@dataclass(frozen=True)
class SpectrumMethodResult:
    method_name: str
    dominant_frequency_hz: float
    dominant_period_s: float
    peak_value: float
    frequency_resolution_hz: float


@dataclass(frozen=True)
class PeakMarker:
    rank: int
    frequency_hz: float
    value: float
    index: int


@dataclass(frozen=True)
class ComponentResult:
    file_name: str
    component_name: str
    sample_rate_hz: float
    sample_count: int
    duration_s: float
    direct: SpectrumMethodResult
    indirect: SpectrumMethodResult
    direct_peaks: tuple[PeakMarker, ...]
    indirect_peaks: tuple[PeakMarker, ...]


def parse_args() -> argparse.Namespace:
    project_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="直接法/间接法计算地震动卓越频率并绘图。")
    parser.add_argument("--data-dir", type=Path, default=project_dir / "data", help="输入 TXT 数据目录。")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_dir / "two_method_spectrum_output",
        help="输出目录。",
    )
    parser.add_argument(
        "--min-peak-frequency",
        type=float,
        default=PEAK_SEARCH_MIN_FREQUENCY_HZ,
        help="卓越频率搜索下限；默认使用文件顶部 PEAK_SEARCH_MIN_FREQUENCY_HZ。",
    )
    parser.add_argument(
        "--max-peak-frequency",
        type=float,
        default=PEAK_SEARCH_MAX_FREQUENCY_HZ,
        help="卓越频率搜索上限；默认使用文件顶部 PEAK_SEARCH_MAX_FREQUENCY_HZ，0 表示不设上限。",
    )
    parser.add_argument(
        "--plot-max-frequency",
        type=float,
        default=0.0,
        help="频谱图显示上限，默认 0（显示到 Nyquist 频率）。",
    )
    parser.add_argument(
        "--processing-points",
        type=int,
        default=0,
        help="实际参与处理的前 N 个点；默认 0 表示使用全部样本。",
    )
    return parser.parse_args()


def parse_header(header: str, source_file: Path) -> tuple[float, int, str, float | None]:
    sample_rate_match = re.search(r"samp:\s*([0-9.]+)", header, flags=re.IGNORECASE)
    component_match = re.search(r"comp:\s*(\d+)", header, flags=re.IGNORECASE)
    duration_match = re.search(r"Data\s*length:\s*([0-9.]+)", header, flags=re.IGNORECASE)
    if not sample_rate_match or not component_match:
        raise ValueError(f"无法解析数据头: {source_file} -> {header!r}")

    sample_rate_hz = float(sample_rate_match.group(1))
    component_index = int(component_match.group(1))
    component_name = COMPONENT_NAMES.get(component_index, f"COMP{component_index}")
    declared_duration_s = float(duration_match.group(1)) if duration_match else None
    return sample_rate_hz, component_index, component_name, declared_duration_s


def load_traces(file_path: Path) -> list[Trace]:
    lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    traces: list[Trace] = []
    current_header: str | None = None
    current_values: list[float] = []

    def flush_current() -> None:
        nonlocal current_header, current_values
        if current_header is None:
            return
        sample_rate_hz, component_index, component_name, declared_duration_s = parse_header(current_header, file_path)
        if not current_values:
            raise ValueError(f"{file_path} {component_name} 没有样本数据。")
        traces.append(
            Trace(
                source_file=file_path,
                sample_rate_hz=sample_rate_hz,
                component_index=component_index,
                component_name=component_name,
                declared_duration_s=declared_duration_s,
                raw_counts=np.asarray(current_values, dtype=float),
            )
        )
        current_values = []

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(";"):
            flush_current()
            current_header = line
            continue
        if current_header is None:
            raise ValueError(f"数据出现在文件头之前: {file_path}，第 {line_number} 行。")
        try:
            current_values.append(float(line))
        except ValueError as exc:
            raise ValueError(f"发现非数值样本: {file_path}，第 {line_number} 行: {line!r}") from exc

    flush_current()
    if not traces:
        raise ValueError(f"未找到分量数据: {file_path}。")
    seen_component_indices: set[int] = set()
    duplicate_component_indices: list[int] = []
    for trace in traces:
        if trace.component_index in seen_component_indices:
            duplicate_component_indices.append(trace.component_index)
        seen_component_indices.add(trace.component_index)
    if duplicate_component_indices:
        duplicated_components = ", ".join(
            f"{COMPONENT_NAMES.get(index, f'COMP{index}')}(comp={index})"
            for index in sorted(set(duplicate_component_indices))
        )
        actual_components = ", ".join(
            f"{trace.component_name}(comp={trace.component_index})"
            for trace in traces
        )
        raise ValueError(
            f"{file_path} 存在重复分量头: {duplicated_components}。"
            f"实际读取顺序: {actual_components}。"
            "请检查每段数据头中的 comp 值，通常应为 0/1/2。"
        )
    return sorted(traces, key=lambda trace: trace.component_index)


def truncate_traces(traces: list[Trace], processing_point_count: int) -> list[Trace]:
    if processing_point_count <= 0:
        return traces
    truncated_traces: list[Trace] = []
    for trace in traces:
        if trace.sample_count < processing_point_count:
            raise ValueError(
                f"{trace.source_file} {trace.component_name} 样本数 {trace.sample_count} "
                f"少于实际处理点数 {processing_point_count}。"
            )
        truncated_traces.append(
            Trace(
                source_file=trace.source_file,
                sample_rate_hz=trace.sample_rate_hz,
                component_index=trace.component_index,
                component_name=trace.component_name,
                declared_duration_s=trace.declared_duration_s,
                raw_counts=trace.raw_counts[:processing_point_count],
            )
        )
    return truncated_traces


def remove_linear_drift(values: np.ndarray) -> np.ndarray:
    if values.size < 2:
        return values.copy()
    sample_index = np.arange(values.size, dtype=float)
    centered_index = sample_index - np.mean(sample_index)
    denominator = float(np.dot(centered_index, centered_index))
    if denominator == 0.0:
        return values.copy()
    slope = float(np.dot(centered_index, values) / denominator)
    return values - slope * centered_index


def remove_instrument_response(raw_counts: np.ndarray) -> np.ndarray:
    return raw_counts.astype(float) / INSTRUMENT_RESPONSE


def raw_counts_signal(trace: Trace) -> np.ndarray:
    return trace.raw_counts.astype(float)


def corrected_acceleration_um_s2(trace: Trace) -> np.ndarray:
    acceleration = remove_instrument_response(trace.raw_counts)
    acceleration = acceleration - np.mean(acceleration)
    acceleration = remove_linear_drift(acceleration)
    return acceleration * UM_PER_METER


def direct_power_spectrum(values: np.ndarray, sample_rate_hz: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    sample_count = values.size
    frequencies = np.fft.rfftfreq(sample_count, d=1.0 / sample_rate_hz)
    spectrum = np.fft.rfft(values)
    amplitude_spectrum = np.abs(spectrum) * 2.0 / sample_count
    if amplitude_spectrum.size:
        amplitude_spectrum[0] /= 2.0
        if sample_count % 2 == 0:
            amplitude_spectrum[-1] /= 2.0
    power_spectrum = amplitude_spectrum**2
    frequency_resolution_hz = sample_rate_hz / sample_count
    return frequencies, amplitude_spectrum, power_spectrum, frequency_resolution_hz


def autocorrelation(values: np.ndarray) -> np.ndarray:
    sample_count = values.size
    full_correlation = np.correlate(values, values, mode="full")
    nonnegative_lags = full_correlation[sample_count - 1 :]
    lag_counts = np.arange(sample_count, 0, -1, dtype=float)
    return nonnegative_lags / lag_counts


def indirect_power_spectral_density(values: np.ndarray, sample_rate_hz: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    correlation = autocorrelation(values)
    symmetric_correlation = np.concatenate([correlation, [0.0], correlation[:0:-1]])
    transform = np.fft.rfft(symmetric_correlation)
    power_spectrum = np.maximum(np.real(transform), 0.0)
    frequency_resolution_hz = sample_rate_hz / symmetric_correlation.size
    power_spectral_density = power_spectrum / frequency_resolution_hz
    frequencies = np.fft.rfftfreq(symmetric_correlation.size, d=1.0 / sample_rate_hz)
    return frequencies, power_spectrum, power_spectral_density, frequency_resolution_hz


def peak_index_in_band(
    frequencies: np.ndarray,
    values: np.ndarray,
    min_frequency_hz: float,
    max_frequency_hz: float | None,
) -> int:
    mask = frequencies >= min_frequency_hz
    if max_frequency_hz is not None:
        mask &= frequencies <= max_frequency_hz
    if not np.any(mask):
        return int(np.argmax(values))
    masked_indices = np.flatnonzero(mask)
    return int(masked_indices[np.argmax(values[mask])])


def ranked_peak_markers(
    frequencies: np.ndarray,
    values: np.ndarray,
    min_frequency_hz: float,
    max_frequency_hz: float | None,
    count: int = PEAK_MARKER_COUNT,
    min_separation_hz: float = PEAK_MARKER_MIN_SEPARATION_HZ,
) -> list[PeakMarker]:
    mask = (frequencies >= min_frequency_hz) & np.isfinite(values)
    if max_frequency_hz is not None:
        mask &= frequencies <= max_frequency_hz
    masked_indices = np.flatnonzero(mask)
    if masked_indices.size == 0:
        masked_indices = np.flatnonzero(np.isfinite(values))
    if masked_indices.size == 0:
        return []

    dominant_index = peak_index_in_band(frequencies, values, min_frequency_hz, max_frequency_hz)
    local_peak_indices: list[int] = [dominant_index]
    for index in masked_indices:
        left_value = values[index - 1] if index > 0 else -np.inf
        right_value = values[index + 1] if index + 1 < values.size else -np.inf
        if values[index] >= left_value and values[index] >= right_value and int(index) != dominant_index:
            local_peak_indices.append(int(index))

    candidate_indices = local_peak_indices or [int(index) for index in masked_indices]
    sorted_indices = sorted(candidate_indices, key=lambda index: float(values[index]), reverse=True)
    selected_indices: list[int] = []
    for index in sorted_indices:
        frequency = float(frequencies[index])
        if all(abs(frequency - float(frequencies[selected_index])) >= min_separation_hz for selected_index in selected_indices):
            selected_indices.append(index)
        if len(selected_indices) >= count:
            break

    if len(selected_indices) < count:
        for index in sorted(masked_indices, key=lambda item: float(values[item]), reverse=True):
            if int(index) not in selected_indices:
                selected_indices.append(int(index))
            if len(selected_indices) >= count:
                break

    return [
        PeakMarker(
            rank=rank,
            frequency_hz=float(frequencies[index]),
            value=float(values[index]),
            index=index,
        )
        for rank, index in enumerate(selected_indices, start=1)
    ]


def style_axis(axis: plt.Axes) -> None:
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.tick_params(axis="both", which="major", labelsize=9, length=4, width=0.8)
    axis.tick_params(axis="both", which="minor", length=2, width=0.6)


def annotate_peak_markers(axis: plt.Axes, peaks: list[PeakMarker]) -> None:
    if not peaks:
        return
    peak_colors = [DOMINANT_PEAK_COLOR, SECONDARY_PEAK_COLOR, "#ea580c", "#0891b2"]
    for peak in peaks:
        color = peak_colors[(peak.rank - 1) % len(peak_colors)]
        linestyle = "--" if peak.rank == 1 else ":"
        linewidth = 1.1 if peak.rank == 1 else 0.95
        alpha = 0.95 if peak.rank == 1 else 0.75
        axis.axvline(peak.frequency_hz, color=color, linestyle=linestyle, linewidth=linewidth, alpha=alpha, zorder=2)
        axis.scatter(
            [peak.frequency_hz],
            [peak.value],
            s=34 if peak.rank == 1 else 26,
            color=color,
            edgecolor="white",
            linewidth=0.7,
            zorder=4,
        )

    peak_summary = "\n".join(f"P{peak.rank}: {peak.frequency_hz:.3f} Hz" for peak in peaks)
    axis.text(
        0.985,
        0.965,
        peak_summary,
        transform=axis.transAxes,
        ha="right",
        va="top",
        fontsize=8.5,
        color="#1f2937",
        bbox={
            "boxstyle": "round,pad=0.32",
            "facecolor": "#ffffff",
            "edgecolor": "#cbd5e1",
            "alpha": 0.92,
        },
        zorder=5,
    )


def make_method_result(
    method_name: str,
    frequencies: np.ndarray,
    spectrum_values: np.ndarray,
    frequency_resolution_hz: float,
    min_peak_frequency_hz: float,
    max_peak_frequency_hz: float | None,
) -> SpectrumMethodResult:
    peak_index = peak_index_in_band(frequencies, spectrum_values, min_peak_frequency_hz, max_peak_frequency_hz)
    dominant_frequency_hz = float(frequencies[peak_index])
    dominant_period_s = 1.0 / dominant_frequency_hz if dominant_frequency_hz > 0.0 else math.inf
    return SpectrumMethodResult(
        method_name=method_name,
        dominant_frequency_hz=dominant_frequency_hz,
        dominant_period_s=float(dominant_period_s),
        peak_value=float(spectrum_values[peak_index]),
        frequency_resolution_hz=float(frequency_resolution_hz),
    )


def format_peak_search_band(min_peak_frequency_hz: float, max_peak_frequency_hz: float | None) -> str:
    lower = f"{min_peak_frequency_hz:g} Hz"
    upper = "Nyquist" if max_peak_frequency_hz is None else f"{max_peak_frequency_hz:g} Hz"
    return f"{lower} - {upper}"


def safe_stem(file_name: str) -> str:
    return re.sub(r"[^0-9A-Za-z_.-]+", "_", Path(file_name).stem)


def save_three_component_time_plot(
    traces: list[Trace],
    signals: dict[str, np.ndarray],
    output_dir: Path,
    title_suffix: str,
    y_label: str,
    output_suffix: str,
) -> Path:
    figure, axes = plt.subplots(len(traces), 1, figsize=(12.5, 2.75 * len(traces)), sharex=True)
    axes = np.atleast_1d(axes)
    for axis, trace in zip(axes, traces):
        axis.plot(trace.time_s, signals[trace.component_name], color=SPECTRUM_LINE_COLOR, linewidth=0.85)
        axis.set_title(f"{trace.component_name} {title_suffix}")
        axis.set_ylabel(y_label)
        axis.grid(True, alpha=0.28)
        style_axis(axis)
    axes[-1].set_xlabel("时间 (s)")
    figure.suptitle(f"{traces[0].source_file.name} {title_suffix}", fontsize=14, fontweight="semibold")
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.98))
    output_path = output_dir / f"{safe_stem(traces[0].source_file.name)}_{output_suffix}.png"
    figure.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(figure)
    return output_path


def common_frequency_grid(spectra: dict[str, dict[str, np.ndarray]], frequency_key: str) -> np.ndarray:
    first_component = next(iter(spectra.values()))
    return first_component[frequency_key]


def average_spectrum(
    spectra: dict[str, dict[str, np.ndarray]],
    frequency_key: str,
    value_key: str,
) -> tuple[np.ndarray, np.ndarray]:
    frequencies = common_frequency_grid(spectra, frequency_key)
    value_stack = np.vstack([component_spectra[value_key] for component_spectra in spectra.values()])
    return frequencies, np.mean(value_stack, axis=0)


def apply_spectrum_axis_style(
    axis: plt.Axes,
    frequencies: np.ndarray,
    values: np.ndarray,
    max_frequency_hz: float | None,
) -> None:
    if max_frequency_hz is not None:
        mask = (frequencies >= 0.0) & (frequencies <= max_frequency_hz)
    else:
        mask = frequencies >= 0.0
    visible_values = np.asarray(values[mask], dtype=float)
    finite_values = visible_values[np.isfinite(visible_values)]
    positive_values = finite_values[finite_values > 0.0]
    style_axis(axis)
    if positive_values.size == 0:
        axis.grid(True, alpha=0.28)
        return

    peak_value = float(np.max(positive_values))
    baseline_value = float(np.percentile(positive_values, 20))
    dynamic_ratio = peak_value / max(baseline_value, np.finfo(float).tiny)

    if dynamic_ratio >= 30.0 and positive_values.size >= 8:
        lower_bound = max(float(np.percentile(positive_values, 2)), peak_value / 10_000.0, np.finfo(float).tiny)
        upper_bound = peak_value * 1.15
        axis.set_yscale("log")
        axis.set_ylim(lower_bound, upper_bound)
        axis.grid(True, which="major", alpha=0.32)
        axis.grid(True, which="minor", alpha=0.12)
    else:
        upper_bound = peak_value * 1.08
        axis.set_ylim(0.0, upper_bound if upper_bound > 0.0 else 1.0)
        axis.grid(True, which="major", alpha=0.32)


def save_spectrum_plot(
    traces: list[Trace],
    spectra: dict[str, dict[str, np.ndarray]],
    component_results: list[ComponentResult],
    average_result: SpectrumMethodResult,
    output_dir: Path,
    method: str,
    peak_search_band_label: str,
    min_peak_frequency_hz: float,
    max_peak_frequency_hz: float | None,
    plot_max_frequency_hz: float | None,
) -> Path:
    frequency_key = f"{method}_frequencies"
    value_key = "direct_power" if method == "direct" else "indirect_psd"
    method_label = "直接法" if method == "direct" else "间接法"
    y_label = "功率谱 ((um/s^2)^2)" if method == "direct" else "功率谱密度 ((um/s^2)^2/Hz)"
    output_suffix = "03_direct_spectrum" if method == "direct" else "04_indirect_spectrum"
    line_width = 0.75 if method == "direct" else 0.48
    line_alpha = 0.9 if method == "direct" else 0.62

    average_frequencies, average_values = average_spectrum(spectra, frequency_key, value_key)
    rows = len(traces) + 1
    figure, axes = plt.subplots(rows, 1, figsize=(13.2, 2.95 * rows), sharex=True)
    axes = np.atleast_1d(axes)

    for axis, trace, component_result in zip(axes[:-1], traces, component_results):
        component_spectra = spectra[trace.component_name]
        result = component_result.direct if method == "direct" else component_result.indirect
        frequencies = component_spectra[frequency_key]
        values = component_spectra[value_key]
        peak_markers = ranked_peak_markers(
            frequencies,
            values,
            min_peak_frequency_hz,
            max_peak_frequency_hz,
        )
        axis.plot(frequencies, values, color=SPECTRUM_LINE_COLOR, linewidth=line_width, alpha=line_alpha)
        axis.set_title(
            f"{trace.component_name} {method_label} 卓越频率 {result.dominant_frequency_hz:.4f} Hz"
        )
        axis.set_ylabel(y_label)
        if plot_max_frequency_hz is not None:
            axis.set_xlim(0.0, plot_max_frequency_hz)
        apply_spectrum_axis_style(
            axis,
            frequencies,
            values,
            plot_max_frequency_hz,
        )
        annotate_peak_markers(axis, peak_markers)

    average_axis = axes[-1]
    average_peak_markers = ranked_peak_markers(
        average_frequencies,
        average_values,
        min_peak_frequency_hz,
        max_peak_frequency_hz,
    )
    average_axis.plot(
        average_frequencies,
        average_values,
        color=AVERAGE_LINE_COLOR,
        linewidth=line_width + 0.12,
        alpha=min(line_alpha + 0.2, 0.95),
    )
    average_axis.set_title(f"AVG {method_label} 平均谱卓越频率 {average_result.dominant_frequency_hz:.4f} Hz")
    average_axis.set_ylabel(y_label)
    average_axis.set_xlabel("频率 (Hz)")
    if plot_max_frequency_hz is not None:
        average_axis.set_xlim(0.0, plot_max_frequency_hz)
    apply_spectrum_axis_style(
        average_axis,
        average_frequencies,
        average_values,
        plot_max_frequency_hz,
    )
    annotate_peak_markers(average_axis, average_peak_markers)

    figure.suptitle(
        f"{traces[0].source_file.name} {method_label} 三分量与平均谱（选峰范围 {peak_search_band_label}）",
        fontsize=15,
        fontweight="semibold",
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.975), h_pad=1.05)
    output_path = output_dir / f"{safe_stem(traces[0].source_file.name)}_{output_suffix}.png"
    figure.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(figure)
    return output_path


def process_file(
    file_path: Path,
    output_dir: Path,
    min_peak_frequency_hz: float,
    max_peak_frequency_hz: float | None,
    plot_max_frequency_hz: float | None,
    processing_point_count: int = 0,
) -> tuple[list[ComponentResult], list[Path]]:
    traces = truncate_traces(load_traces(file_path), processing_point_count)
    file_output_dir = output_dir / safe_stem(file_path.name)
    file_output_dir.mkdir(parents=True, exist_ok=True)
    for old_figure_path in file_output_dir.glob("*.png"):
        old_figure_path.unlink()

    raw_signals: dict[str, np.ndarray] = {}
    corrected_signals: dict[str, np.ndarray] = {}
    spectra: dict[str, dict[str, np.ndarray]] = {}
    component_results: list[ComponentResult] = []

    for trace in traces:
        raw_values = raw_counts_signal(trace)
        values = corrected_acceleration_um_s2(trace)
        raw_signals[trace.component_name] = raw_values
        corrected_signals[trace.component_name] = values

        direct_frequencies, direct_amplitudes, direct_power, direct_df = direct_power_spectrum(
            values,
            trace.sample_rate_hz,
        )
        indirect_frequencies, indirect_power, indirect_psd, indirect_df = indirect_power_spectral_density(
            values,
            trace.sample_rate_hz,
        )

        direct_result = make_method_result(
            "直接法",
            direct_frequencies,
            direct_power,
            direct_df,
            min_peak_frequency_hz,
            max_peak_frequency_hz,
        )
        indirect_result = make_method_result(
            "间接法",
            indirect_frequencies,
            indirect_psd,
            indirect_df,
            min_peak_frequency_hz,
            max_peak_frequency_hz,
        )
        direct_peaks = tuple(
            ranked_peak_markers(
                direct_frequencies,
                direct_power,
                min_peak_frequency_hz,
                max_peak_frequency_hz,
            )
        )
        indirect_peaks = tuple(
            ranked_peak_markers(
                indirect_frequencies,
                indirect_psd,
                min_peak_frequency_hz,
                max_peak_frequency_hz,
            )
        )

        spectra[trace.component_name] = {
            "direct_frequencies": direct_frequencies,
            "direct_amplitudes": direct_amplitudes,
            "direct_power": direct_power,
            "indirect_frequencies": indirect_frequencies,
            "indirect_power": indirect_power,
            "indirect_psd": indirect_psd,
        }
        component_results.append(
            ComponentResult(
                file_name=file_path.name,
                component_name=trace.component_name,
                sample_rate_hz=trace.sample_rate_hz,
                sample_count=trace.sample_count,
                duration_s=trace.duration_s,
                direct=direct_result,
                indirect=indirect_result,
                direct_peaks=direct_peaks,
                indirect_peaks=indirect_peaks,
            )
        )

    direct_average_frequencies, direct_average_power = average_spectrum(spectra, "direct_frequencies", "direct_power")
    indirect_average_frequencies, indirect_average_psd = average_spectrum(spectra, "indirect_frequencies", "indirect_psd")
    peak_search_band_label = format_peak_search_band(min_peak_frequency_hz, max_peak_frequency_hz)
    average_direct_result = make_method_result(
        "直接法平均谱",
        direct_average_frequencies,
        direct_average_power,
        traces[0].sample_rate_hz / traces[0].sample_count,
        min_peak_frequency_hz,
        max_peak_frequency_hz,
    )
    average_indirect_result = make_method_result(
        "间接法平均谱",
        indirect_average_frequencies,
        indirect_average_psd,
        traces[0].sample_rate_hz / (2 * traces[0].sample_count),
        min_peak_frequency_hz,
        max_peak_frequency_hz,
    )
    average_direct_peaks = tuple(
        ranked_peak_markers(
            direct_average_frequencies,
            direct_average_power,
            min_peak_frequency_hz,
            max_peak_frequency_hz,
        )
    )
    average_indirect_peaks = tuple(
        ranked_peak_markers(
            indirect_average_frequencies,
            indirect_average_psd,
            min_peak_frequency_hz,
            max_peak_frequency_hz,
        )
    )
    component_results.append(
        ComponentResult(
            file_name=file_path.name,
            component_name="AVG",
            sample_rate_hz=traces[0].sample_rate_hz,
            sample_count=min(trace.sample_count for trace in traces),
            duration_s=min(trace.duration_s for trace in traces),
            direct=average_direct_result,
            indirect=average_indirect_result,
            direct_peaks=average_direct_peaks,
            indirect_peaks=average_indirect_peaks,
        )
    )

    figure_paths = [
        save_three_component_time_plot(
            traces,
            raw_signals,
            file_output_dir,
            "原始计数时程（未去仪器响应、零漂、线漂）",
            "原始计数",
            "01_raw_counts_time_history",
        ),
        save_three_component_time_plot(
            traces,
            corrected_signals,
            file_output_dir,
            "校正加速度时程（去仪器响应、零漂、线漂）",
            "um/s^2",
            "02_corrected_acceleration_time_history_um_s2",
        ),
        save_spectrum_plot(
            traces,
            spectra,
            component_results[:-1],
            average_direct_result,
            file_output_dir,
            "direct",
            peak_search_band_label,
            min_peak_frequency_hz,
            max_peak_frequency_hz,
            plot_max_frequency_hz,
        ),
        save_spectrum_plot(
            traces,
            spectra,
            component_results[:-1],
            average_indirect_result,
            file_output_dir,
            "indirect",
            peak_search_band_label,
            min_peak_frequency_hz,
            max_peak_frequency_hz,
            plot_max_frequency_hz,
        ),
    ]
    return component_results, figure_paths


def write_component_csv(results: list[ComponentResult], output_path: Path, peak_search_band_label: str) -> None:
    fieldnames = [
        "文件名",
        "分量",
        "选峰范围_Hz",
        "采样率_Hz",
        "样本数",
        "时长_s",
        "直接法频率分辨率_Hz",
        "直接法卓越频率_Hz",
        "直接法卓越周期_s",
        "直接法峰值功率谱",
        "间接法频率分辨率_Hz",
        "间接法卓越频率_Hz",
        "间接法卓越周期_s",
        "间接法峰值功率谱密度",
    ]
    for method_label in ("直接法", "间接法"):
        value_label = "功率谱" if method_label == "直接法" else "功率谱密度"
        for rank in range(1, PEAK_MARKER_COUNT + 1):
            fieldnames.extend(
                [
                    f"{method_label}P{rank}候选峰频率_Hz",
                    f"{method_label}P{rank}候选峰周期_s",
                    f"{method_label}P{rank}候选峰{value_label}",
                ]
            )

    def peak_fields(method_label: str, peaks: tuple[PeakMarker, ...]) -> dict[str, str]:
        value_label = "功率谱" if method_label == "直接法" else "功率谱密度"
        row: dict[str, str] = {}
        peaks_by_rank = {peak.rank: peak for peak in peaks}
        for rank in range(1, PEAK_MARKER_COUNT + 1):
            peak = peaks_by_rank.get(rank)
            if peak is None:
                row[f"{method_label}P{rank}候选峰频率_Hz"] = ""
                row[f"{method_label}P{rank}候选峰周期_s"] = ""
                row[f"{method_label}P{rank}候选峰{value_label}"] = ""
                continue
            period_s = 1.0 / peak.frequency_hz if peak.frequency_hz > 0.0 else math.inf
            row[f"{method_label}P{rank}候选峰频率_Hz"] = f"{peak.frequency_hz:.12g}"
            row[f"{method_label}P{rank}候选峰周期_s"] = f"{period_s:.12g}"
            row[f"{method_label}P{rank}候选峰{value_label}"] = f"{peak.value:.12g}"
        return row

    with output_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            row = {
                "文件名": result.file_name,
                "分量": result.component_name,
                "选峰范围_Hz": peak_search_band_label,
                "采样率_Hz": f"{result.sample_rate_hz:.12g}",
                "样本数": result.sample_count,
                "时长_s": f"{result.duration_s:.12g}",
                "直接法频率分辨率_Hz": f"{result.direct.frequency_resolution_hz:.12g}",
                "直接法卓越频率_Hz": f"{result.direct.dominant_frequency_hz:.12g}",
                "直接法卓越周期_s": f"{result.direct.dominant_period_s:.12g}",
                "直接法峰值功率谱": f"{result.direct.peak_value:.12g}",
                "间接法频率分辨率_Hz": f"{result.indirect.frequency_resolution_hz:.12g}",
                "间接法卓越频率_Hz": f"{result.indirect.dominant_frequency_hz:.12g}",
                "间接法卓越周期_s": f"{result.indirect.dominant_period_s:.12g}",
                "间接法峰值功率谱密度": f"{result.indirect.peak_value:.12g}",
            }
            row.update(peak_fields("直接法", result.direct_peaks))
            row.update(peak_fields("间接法", result.indirect_peaks))
            writer.writerow(row)


def run_analysis(
    data_dir: Path,
    output_dir: Path,
    min_peak_frequency: float,
    max_peak_frequency: float,
    plot_max_frequency: float,
    processing_point_count: int = 0,
    progress_callback: callable | None = None,
) -> tuple[list[ComponentResult], list[Path], Path, str]:
    if not data_dir.exists():
        raise FileNotFoundError(f"数据目录不存在: {data_dir}")

    txt_files = sorted(data_dir.glob("*.txt"))
    if not txt_files:
        raise FileNotFoundError(f"数据目录中未找到 TXT 文件: {data_dir}")

    if min_peak_frequency < 0:
        raise ValueError("--min-peak-frequency 不能小于 0。")
    if processing_point_count < 0:
        raise ValueError("--processing-points 不能小于 0。")
    if processing_point_count == 1:
        raise ValueError("--processing-points 必须为 0（全部）或大于等于 2。")
    max_peak_frequency_hz = None if max_peak_frequency <= 0 else max_peak_frequency
    if max_peak_frequency_hz is not None and max_peak_frequency_hz < min_peak_frequency:
        raise ValueError("--max-peak-frequency 必须大于或等于 --min-peak-frequency。")
    peak_search_band_label = format_peak_search_band(min_peak_frequency, max_peak_frequency_hz)
    plot_max_frequency_hz = None if plot_max_frequency <= 0 else plot_max_frequency
    output_dir.mkdir(parents=True, exist_ok=True)
    if progress_callback is not None:
        point_label = "全部样本" if processing_point_count <= 0 else f"前 {processing_point_count} 个点"
        progress_callback(f"实际处理点数: {point_label}")

    all_component_results: list[ComponentResult] = []
    figure_paths: list[Path] = []
    for index, file_path in enumerate(txt_files, start=1):
        if progress_callback is not None:
            progress_callback(f"[{index}/{len(txt_files)}] 处理 {file_path.name}")
        component_results, file_figure_paths = process_file(
            file_path,
            output_dir,
            min_peak_frequency,
            max_peak_frequency_hz,
            plot_max_frequency_hz,
            processing_point_count,
        )
        all_component_results.extend(component_results)
        figure_paths.extend(file_figure_paths)

    component_csv = output_dir / "component_direct_indirect_results.csv"
    write_component_csv(all_component_results, component_csv, peak_search_band_label)
    return all_component_results, figure_paths, component_csv, peak_search_band_label


def main() -> None:
    args = parse_args()
    all_component_results, figure_paths, component_csv, peak_search_band_label = run_analysis(
        args.data_dir,
        args.output_dir,
        args.min_peak_frequency,
        args.max_peak_frequency,
        args.plot_max_frequency,
        args.processing_points,
    )

    print("处理完成")
    print(f"数据文件数: {len({result.file_name for result in all_component_results})}")
    print(f"图文件数量: {len(figure_paths)}")
    print(f"卓越频率选峰范围: {peak_search_band_label}")
    print(f"结果表: {component_csv}")
    for result in all_component_results:
        print(
            f"{result.file_name} {result.component_name}: "
            f"直接法 {result.direct.dominant_frequency_hz:.6f} Hz, "
            f"间接法 {result.indirect.dominant_frequency_hz:.6f} Hz"
        )


if __name__ == "__main__":
    main()
