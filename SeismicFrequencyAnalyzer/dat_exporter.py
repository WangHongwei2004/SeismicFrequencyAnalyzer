# -*- coding: utf-8 -*-
"""DAT 格式导出模块。

将裁剪后的三分量地震数据导出为单个 DAT 文本文件，
格式兼容现有 TXT 解析逻辑（load_traces()）。

关键约束：load_traces() 把每一行 `;` 开头的行都当作分量头解析，
因此所有元信息必须编码到分量头行中，不能有纯注释的 `;` 行。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


def export_three_component_dat(
    ew_data: np.ndarray,
    ns_data: np.ndarray,
    ud_data: np.ndarray,
    output_path: str | Path,
    sample_rate_hz: float,
    start_sample_index: int,
    end_sample_index: int,
    original_file: str = "",
    original_sample_rate_hz: float | None = None,
    record_time: str = "",
    extra_metadata: dict[str, Any] | None = None,
) -> Path:
    """导出三分量数据为单个 DAT 文件（兼容现有 TXT 解析格式）。

    Parameters
    ----------
    ew_data, ns_data, ud_data : np.ndarray
        三分量数据（长度应相同）。
    output_path : str or Path
        输出文件路径。
    sample_rate_hz : float
        采样率（地震仪实际采样率）。
    start_sample_index : int
        截取起始点号（相对于原始文件）。
    end_sample_index : int
        截取结束点号（不含）。
    original_file : str
        原始 EVT 文件名。
    original_sample_rate_hz : float or None
        原始文件采样率（若重采样过则不同）。
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

    n_samples = min(len(ew_data), len(ns_data), len(ud_data))
    duration_s = n_samples / sample_rate_hz

    if original_sample_rate_hz is not None:
        start_time_s = start_sample_index / original_sample_rate_hz
        end_time_s = end_sample_index / original_sample_rate_hz
    else:
        start_time_s = 0.0
        end_time_s = duration_s

    if original_sample_rate_hz is None:
        original_sample_rate_hz = sample_rate_hz

    # 构建元信息字符串（嵌入第一个分量头）
    extra_parts = []
    if original_file:
        extra_parts.append(f"Original: {original_file}")
    if record_time:
        extra_parts.append(f"RecordTime: {record_time}")
    extra_parts.append(f"OriginalSR: {original_sample_rate_hz:.4f}")
    extra_parts.append(f"StartIdx: {start_sample_index}")
    extra_parts.append(f"EndIdx: {end_sample_index}")
    extra_parts.append(f"StartTime: {start_time_s:.6f}s")
    extra_parts.append(f"EndTime: {end_time_s:.6f}s")
    if extra_metadata:
        for key, value in extra_metadata.items():
            extra_parts.append(f"{key}: {value}")

    extra_info = "; ".join(extra_parts)

    lines: list[str] = []

    # ── 三分量数据 ──
    # 分量顺序：comp:0=UD, comp:1=NS, comp:2=EW（与 COMPONENT_NAMES 一致）
    components: list[tuple[int, str, np.ndarray]] = [
        (0, "UD", ud_data),
        (1, "NS", ns_data),
        (2, "EW", ew_data),
    ]

    for idx, (comp_idx, comp_name, comp_data) in enumerate(components):
        if idx == 0:
            # 第一个分量头包含所有元信息
            lines.append(
                f"; samp: {sample_rate_hz:.4f}; comp: {comp_idx}; "
                f"Data length:{duration_s:.6f}; {extra_info}"
            )
        else:
            lines.append(
                f"; samp: {sample_rate_hz:.4f}; comp: {comp_idx}; "
                f"Data length:{duration_s:.6f}"
            )

        for value in comp_data[:n_samples]:
            lines.append(f"{value:.6f}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")

    return output_path