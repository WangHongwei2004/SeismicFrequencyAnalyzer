# -*- coding: utf-8 -*-
"""最优数据段自动筛选算法。

使用滑动窗口遍历数据，对每个窗口进行多维度评分，
自动选出最平稳（线漂最小）、干扰最小的数据段。

评分策略（针对地震原始counts数据优化）：
1. 平稳性 — 窗口内子段统计量（均值/标准差）的一致性
2. 弯曲度惩罚 — 二次拟合显著优于线性拟合 → 有弯曲漂移，重罚
3. 尖峰检测 — 去趋势后超过阈值倍数的异常点
4. 死数据惩罚 — 全零段或常数值段
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from numpy.typing import NDArray


# ── 数据类型 ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class WindowScore:
    """单个窗口的评分详情。"""

    start_index: int
    end_index: int
    component: str
    stationarity_score: float
    """平稳性得分 (0-1，1=最平稳)"""
    curvature_penalty: float
    """弯曲度惩罚 (0-1，0=无弯曲)"""
    spike_penalty: float
    """尖峰异常惩罚 (0-1，0=无尖峰)"""
    dead_zone_penalty: float
    """死数据惩罚 (0-1，0=活跃数据)"""
    total_score: float
    """综合得分 (0-1)"""
    detrended_std: float
    """去趋势后残差标准差"""
    slope: float
    """线性拟合斜率"""
    spike_count: int
    """尖峰数量"""
    mean_value: float
    """均值"""

    @property
    def summary(self) -> str:
        return (
            f"窗口 [{self.start_index}, {self.end_index}) "
            f"平稳性={self.stationarity_score:.4f} "
            f"弯曲={self.curvature_penalty:.4f} "
            f"尖峰={self.spike_penalty:.4f} "
            f"死区={self.dead_zone_penalty:.4f} "
            f"总={self.total_score:.4f}"
        )


@dataclass(frozen=True)
class BestSegmentResult:
    """最优数据段筛选结果。"""

    component: str
    best_window: WindowScore
    all_top_windows: list[WindowScore]
    data: np.ndarray
    sample_rate_hz: float
    original_sample_rate_hz: float


# ── 评分函数 ──────────────────────────────────────────────────────


def _analyze_window(data: np.ndarray, n_subwindows: int = 4) -> dict:
    """对窗口数据进行全面分析，返回各维度指标。

    核心思路：
    - 地震数据本身是振荡的，不是"线性的"
    - 关键是：数据没有弯曲漂移、没有尖峰干扰、统计特性平稳
    """
    n = len(data)
    x = np.arange(n, dtype=float)

    # 1. 线性拟合 + 弯曲检测
    coeffs_linear = np.polyfit(x, data, 1)
    slope = coeffs_linear[0]
    trend_linear = np.polyval(coeffs_linear, x)
    residual_linear = data - trend_linear
    detrended_std = float(np.std(residual_linear))

    # 二次拟合（检测弯曲）
    coeffs_quad = np.polyfit(x, data, 2)
    residual_quad = data - np.polyval(coeffs_quad, x)
    rms_linear = np.sqrt(np.mean(residual_linear ** 2))
    rms_quad = np.sqrt(np.mean(residual_quad ** 2))

    if rms_linear > 1e-10:
        curvature_improvement = (rms_linear - rms_quad) / rms_linear
    else:
        curvature_improvement = 0.0

    # 2. 平稳性：划分子窗口，检查均值和标准差的稳定性
    sub_size = n // n_subwindows
    sub_means = []
    sub_stds = []
    for i in range(n_subwindows):
        sub = data[i * sub_size:(i + 1) * sub_size]
        sub_means.append(float(np.mean(sub)))
        sub_stds.append(float(np.std(sub)))

    sub_means = np.array(sub_means)
    sub_stds = np.array(sub_stds)

    # 均值稳定性：子窗口均值的变化系数
    global_mean = float(np.mean(data))
    if abs(global_mean) > 1e-10:
        mean_cv = float(np.std(sub_means) / abs(global_mean))
    else:
        mean_cv = 1.0  # 均值≈0时，检查绝对变化
        if np.std(sub_means) < 1.0:
            mean_cv = 0.0

    # 标准差稳定性
    global_std = float(np.std(data))
    if global_std > 1e-10:
        std_cv = float(np.std(sub_stds) / global_std)
    else:
        std_cv = 1.0

    # 3. 尖峰检测（基于去趋势残差，用中位数绝对偏差更鲁棒）
    med = np.median(residual_linear)
    mad = np.median(np.abs(residual_linear - med))
    if mad > 1e-10:
        robust_std = mad * 1.4826  # 转换到正态分布等效std
        spike_mask = np.abs(residual_linear - med) > 5.0 * robust_std
        spike_count = int(np.sum(spike_mask))
    elif detrended_std > 1e-10:
        spike_mask = np.abs(residual_linear) > 5.0 * detrended_std
        spike_count = int(np.sum(spike_mask))
    else:
        spike_count = 0

    # 4. 死数据检测：全零或近乎常数
    data_arr = data.astype(np.float64)
    data_range = float(np.max(data_arr) - np.min(data_arr))
    zero_count = int(np.sum(data_arr == 0))
    near_zero_ratio = float(np.sum(np.abs(data_arr) < 1.0)) / n

    return {
        "slope": slope,
        "detrended_std": detrended_std,
        "rms_linear": rms_linear,
        "rms_quad": rms_quad,
        "curvature_improvement": curvature_improvement,
        "mean_cv": mean_cv,
        "std_cv": std_cv,
        "spike_count": spike_count,
        "zero_count": zero_count,
        "data_range": data_range,
        "near_zero_ratio": near_zero_ratio,
        "global_mean": global_mean,
        "global_std": global_std,
        "n": n,
    }


def score_window(
    data: np.ndarray,
    weights: tuple[float, float, float, float] = (0.50, 0.25, 0.10, 0.15),
) -> dict[str, float]:
    """对单个数据窗口进行多维度评分。

    Parameters
    ----------
    data : np.ndarray
        窗口内的数据（1D）。
    weights : tuple
        (平稳性权重, 弯曲惩罚权重, 尖峰惩罚权重, 死区惩罚权重)。

    Returns
    -------
    dict
    """
    info = _analyze_window(data)
    w_stat, w_curv, w_spike, w_dead = weights

    # ── 平稳性得分 ──
    # 均值和标准差的变异系数越小越平稳
    mean_cv = info["mean_cv"]
    std_cv = info["std_cv"]

    # 综合平稳性：均值平稳 × 标准差平稳
    stat_mean_score = np.exp(-mean_cv * 8.0)  # cv=0→1.0, cv=0.25→0.14
    stat_std_score = np.exp(-std_cv * 5.0)    # cv=0→1.0, cv=0.4→0.14
    stationarity_score = float(stat_mean_score * stat_std_score)

    # ── 弯曲度惩罚 ──
    curv = info["curvature_improvement"]
    if curv <= 0.003:
        curvature_penalty = 0.0
    elif curv >= 0.03:
        curvature_penalty = 1.0
    else:
        curvature_penalty = (curv - 0.003) / 0.027

    # ── 尖峰惩罚（放宽阈值，关注异常尖峰而非正常波动）──
    spike_ratio = info["spike_count"] / info["n"]
    if spike_ratio <= 0.01:
        spike_penalty = 0.0
    elif spike_ratio >= 0.08:
        spike_penalty = 1.0
    else:
        spike_penalty = (spike_ratio - 0.01) / 0.07  # 1%→0, 8%→1

    # ── 死数据惩罚 ──
    # 全零段 或 数据范围极窄 或 大量接近零值 → 死数据
    dead_score = 0.0
    if info["data_range"] < 1.0:
        dead_score = 1.0  # 完全平坦 = 死数据
    else:
        dead_score = info["near_zero_ratio"]  # 接近零的比例
        dead_score = max(dead_score, info["zero_count"] / info["n"])
    dead_zone_penalty = min(1.0, dead_score / 0.50)

    # ── 综合得分 ──
    total = (
        w_stat * stationarity_score
        - w_curv * curvature_penalty
        - w_spike * spike_penalty
        - w_dead * dead_zone_penalty
    )
    total = max(0.0, min(1.0, total))

    return {
        "stationarity_score": stationarity_score,
        "curvature_penalty": curvature_penalty,
        "spike_penalty": spike_penalty,
        "dead_zone_penalty": dead_zone_penalty,
        "total_score": total,
        "detrended_std": info["detrended_std"],
        "slope": info["slope"],
        "spike_count": info["spike_count"],
        "mean_value": info["global_mean"],
    }


# ── 滑动窗口搜索 ──────────────────────────────────────────────────


def find_best_segment(
    data: np.ndarray,
    window_size: int,
    sample_rate_hz: float,
    component: str = "",
    step: int | None = None,
    top_k: int = 10,
    progress_callback: Callable[[str], None] | None = None,
) -> BestSegmentResult:
    """滑动窗口搜索最优数据段。

    Parameters
    ----------
    data : np.ndarray
        完整的分量数据（1D 数组）。
    window_size : int
        窗口大小（数据点数）。
    sample_rate_hz : float
        采样率。
    component : str
        分量名（用于日志）。
    step : int or None
        滑动步长，默认为 window_size // 4。
    top_k : int
        保留排名前 top_k 的结果。
    progress_callback : callable or None
        进度回调。

    Returns
    -------
    BestSegmentResult
    """
    n = len(data)
    if n < window_size:
        raise ValueError(f"数据长度 ({n}) 小于窗口大小 ({window_size})")

    if step is None:
        step = max(1, window_size // 4)

    total_windows = (n - window_size) // step + 1
    all_scores: list[WindowScore] = []

    for idx in range(0, n - window_size + 1, step):
        window_data = data[idx:idx + window_size]
        scores = score_window(window_data)
        ws = WindowScore(
            start_index=idx,
            end_index=idx + window_size,
            component=component,
            stationarity_score=scores["stationarity_score"],
            curvature_penalty=scores["curvature_penalty"],
            spike_penalty=scores["spike_penalty"],
            dead_zone_penalty=scores["dead_zone_penalty"],
            total_score=scores["total_score"],
            detrended_std=scores["detrended_std"],
            slope=scores["slope"],
            spike_count=scores["spike_count"],
            mean_value=scores["mean_value"],
        )
        all_scores.append(ws)

        if progress_callback and len(all_scores) % 200 == 0:
            progress_callback(
                f"  筛选进度: {len(all_scores)}/{total_windows} 窗口"
            )

    all_scores.sort(key=lambda s: s.total_score, reverse=True)
    top_windows = all_scores[:top_k]

    best = top_windows[0]
    segment_data = data[best.start_index:best.end_index].astype(np.float64)

    if progress_callback:
        progress_callback(
            f"  最优: [{best.start_index}, {best.end_index}) "
            f"平稳={best.stationarity_score:.4f} "
            f"弯曲={best.curvature_penalty:.4f} "
            f"尖峰={best.spike_penalty:.4f} "
            f"死区={best.dead_zone_penalty:.4f} "
            f"总={best.total_score:.4f}"
        )

    return BestSegmentResult(
        component=component,
        best_window=best,
        all_top_windows=top_windows,
        data=segment_data,
        sample_rate_hz=sample_rate_hz,
        original_sample_rate_hz=sample_rate_hz,
    )


# ── 重采样 ─────────────────────────────────────────────────────────


def resample_data(
    data: np.ndarray,
    original_sr: float,
    target_sr: float,
) -> np.ndarray:
    """将数据重采样到目标采样率（FFT 重采样）。"""
    if abs(original_sr - target_sr) < 0.01:
        return data.copy()

    ratio = target_sr / original_sr
    n_original = len(data)
    n_target = int(np.round(n_original * ratio))

    fft_data = np.fft.rfft(data)

    if n_target < n_original:
        n_keep = n_target // 2 + 1
        fft_data = fft_data[:n_keep]
    else:
        n_fft_new = n_target // 2 + 1
        pad = n_fft_new - len(fft_data)
        if pad > 0:
            fft_data = np.pad(fft_data, (0, pad), mode="constant")

    resampled = np.fft.irfft(fft_data, n=n_target)
    resampled = resampled * ratio
    return resampled


# ── 便捷接口 ──────────────────────────────────────────────────────


def find_best_segment_all_components(
    ew: np.ndarray,
    ns: np.ndarray,
    ud: np.ndarray,
    window_size: int,
    sample_rate_hz: float,
    target_sample_rate_hz: float | None = None,
    step: int | None = None,
    top_k: int = 10,
    progress_callback: Callable[[str], None] | None = None,
) -> dict[str, BestSegmentResult]:
    """对三分量分别搜索最优数据段。"""
    results: dict[str, BestSegmentResult] = {}

    for comp_name, comp_data in [("EW", ew), ("NS", ns), ("UD", ud)]:
        if progress_callback:
            progress_callback(f"正在搜索 {comp_name} 分量最优窗口...")

        result = find_best_segment(
            data=comp_data,
            window_size=window_size,
            sample_rate_hz=sample_rate_hz,
            component=comp_name,
            step=step,
            top_k=top_k,
            progress_callback=progress_callback,
        )

        if target_sample_rate_hz is not None and abs(
            target_sample_rate_hz - sample_rate_hz
        ) > 0.01:
            result = BestSegmentResult(
                component=result.component,
                best_window=result.best_window,
                all_top_windows=result.all_top_windows,
                data=resample_data(result.data, sample_rate_hz, target_sample_rate_hz),
                sample_rate_hz=target_sample_rate_hz,
                original_sample_rate_hz=sample_rate_hz,
            )
            if progress_callback:
                progress_callback(
                    f"  {comp_name} 已重采样: {sample_rate_hz:.1f} -> "
                    f"{target_sample_rate_hz:.1f} Hz, "
                    f"点数: {len(result.data)}"
                )

        results[comp_name] = result

    return results