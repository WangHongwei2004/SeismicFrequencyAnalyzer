# -*- coding: utf-8 -*-
"""DAT 格式导出模块。

将裁剪后的地震数据导出为 DAT 文本文件，包含元信息头和数据值。
兼容现有 TXT 数据格式，同时保留裁剪来源信息，便于溯源。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


def export_dat(
    data: np.ndarray,
    output_path: str | Path,
    component: str,
    sample_rate_hz: float,
    start_sample_index: int,
    end_sample_index: int,
    original_file: str = "",
    original_sample_rate_hz: float | None = None,
    target_sample_rate_hz: float | None = None,
    record_time: str = "",
    extra_metadata: dict[str, Any] | None = None,
) -> Path:
    """导出单分量数据为 DAT 文件。

    格式：
    - 以 `;` 开头的注释行记录元信息
    - 每行一个数值（float）

    Parameters
    ----------
    data : np.ndarray
        裁剪后的数据（1D）。
    output_path : str or Path
        输出文件路径。
    component : str
        分量名（EW, NS, UD）。
    sample_rate_hz : float
        实际采样率。
    start_sample_index : int
        截取起始点号（相对于原始文件）。
    end_sample_index : int
        截取结束点号（不含）。
    original_file : str
        原始 EVT 文件名。
    original_sample_rate_hz : float or None
        原始采样率。
    target_sample_rate_hz : float or None
        目标采样率（若重采样过）。
    record_time : str
        原始数据记录时间。
    extra_metadata : dict or None
        额外元数据。

    Returns
    -------
    Path
        输出文件路径。
    """
    output_path = Path(output_path)

    # 计算时间信息
    duration_s = len(data) / sample_rate_hz
    if start_sample_index >= 0 and original_sample_rate_hz is not None:
        start_time_s = start_sample_index / original_sample_rate_hz
        end_time_s = end_sample_index / original_sample_rate_hz
    else:
        start_time_s = 0.0
        end_time_s = duration_s

    if original_sample_rate_hz is None:
        original_sample_rate_hz = sample_rate_hz

    # 构建头信息
    lines: list[str] = []

    # ── 基本文件信息 ──
    lines.append(f"; DAT Export - SeismicFrequencyAnalyzer")
    lines.append(f"; Export time: {_now_str()}")
    lines.append(";")

    # ── 原始文件信息 ──
    if original_file:
        lines.append(f"; Original file: {original_file}")
    if record_time:
        lines.append(f"; Record time: {record_time}")
    lines.append(f"; Original sample rate: {original_sample_rate_hz:.4f} Hz")

    # ── 裁剪信息 ──
    lines.append(f"; Component: {component}")
    lines.append(f"; Data type: raw counts (int16)")
    lines.append(f";")
    lines.append(f"; --- Extraction info ---")
    lines.append(f"; Start sample index: {start_sample_index}")
    lines.append(f"; End sample index:   {end_sample_index}")
    lines.append(f"; Extracted samples:  {len(data)}")
    lines.append(f"; Start time: {start_time_s:.6f} s")
    lines.append(f"; End time:   {end_time_s:.6f} s")
    lines.append(f"; Duration:   {duration_s:.6f} s")

    # ── 采样率信息 ──
    if target_sample_rate_hz is not None:
        lines.append(f"; Target sample rate: {target_sample_rate_hz:.4f} Hz")
    lines.append(f"; Sample rate: {sample_rate_hz:.4f} Hz")
    lines.append(f"; samp: {sample_rate_hz:.4f}")

    # ── 数据特征 ──
    lines.append(f"; Data min: {np.min(data):.2f}")
    lines.append(f"; Data max: {np.max(data):.2f}")
    lines.append(f"; Data mean: {np.mean(data):.2f}")
    lines.append(f"; Data std: {np.std(data):.2f}")
    lines.append(f";")

    # ── 额外元数据 ──
    if extra_metadata:
        lines.append("; --- Additional metadata ---")
        for key, value in extra_metadata.items():
            lines.append(f"; {key}: {value}")
        lines.append(";")

    lines.append(f"; Data length: {len(data)}")
    lines.append("; --- Begin data ---")

    # ── 数据体 ──
    for value in data:
        lines.append(f"{value:.6f}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")

    return output_path


def export_all_components_dat(
    components_data: dict[str, tuple[np.ndarray, int, int]],
    output_dir: str | Path,
    base_name: str,
    sample_rate_hz: float,
    original_file: str = "",
    original_sample_rate_hz: float | None = None,
    target_sample_rate_hz: float | None = None,
    record_time: str = "",
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """导出多个分量数据为 DAT 文件。

    Parameters
    ----------
    components_data : dict
        key=分量名, value=(数据数组, 起始点号, 结束点号).
    output_dir : str or Path
        输出目录。
    base_name : str
        基础文件名（不含扩展名）。
    sample_rate_hz : float
        实际采样率。
    ...（其他参数同 export_dat）

    Returns
    -------
    dict[str, Path]
        分量名 -> 输出路径。
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}

    for component, (data, start_idx, end_idx) in components_data.items():
        out_path = output_dir / f"{base_name}_{component}.dat"
        exported = export_dat(
            data=data,
            output_path=out_path,
            component=component,
            sample_rate_hz=sample_rate_hz,
            start_sample_index=start_idx,
            end_sample_index=end_idx,
            original_file=original_file,
            original_sample_rate_hz=original_sample_rate_hz,
            target_sample_rate_hz=target_sample_rate_hz,
            record_time=record_time,
            extra_metadata=extra_metadata,
        )
        paths[component] = exported

    return paths


def _now_str() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")