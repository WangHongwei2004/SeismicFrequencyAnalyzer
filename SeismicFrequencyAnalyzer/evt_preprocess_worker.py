# -*- coding: utf-8 -*-
"""EVT 预处理后台工作线程。

读取 EVT 文件，自动筛选最优数据段，导出 DAT 文件。
"""

from __future__ import annotations

import traceback
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal

from evt_reader import read_evt, find_first_valid_frame, get_component_array
from segment_selector import find_best_segment, resample_data
from dat_exporter import export_dat


class EvtPreprocessWorker(QObject):
    """后台处理 EVT 文件：筛选最优数据段并导出 DAT。"""

    log = pyqtSignal(str)
    finished = pyqtSignal(str, int, dict)  # output_dir, file_count, results
    failed = pyqtSignal(str)

    def __init__(
        self,
        evt_path: Path,
        output_dir: Path,
        window_size: int,
        target_sample_rate_hz: float | None,
        components: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.evt_path = evt_path
        self.output_dir = output_dir
        self.window_size = window_size
        self.target_sample_rate_hz = target_sample_rate_hz
        self.components = components or ["EW", "NS", "UD"]

    def run(self) -> None:
        try:
            self.log.emit(f"读取 EVT 文件: {self.evt_path.name}")
            evt = read_evt(self.evt_path)
            header = evt.header

            self.log.emit(
                f"  台站: {header.station_name or '(未知)'} | "
                f"仪器: {header.instrument or '(未知)'} | "
                f"坐标: ({header.latitude:.4f}, {header.longitude:.4f})"
            )
            self.log.emit(
                f"  原始采样率: {header.sample_rate_hz:.2f} Hz | "
                f"数据帧数: {header.total_frames} | "
                f"时长: {evt.duration_s:.1f} s"
            )

            effective_sr = (
                self.target_sample_rate_hz
                if self.target_sample_rate_hz
                else header.sample_rate_hz
            )
            self.log.emit(f"  目标采样率: {effective_sr:.2f} Hz | 窗口大小: {self.window_size} 点")

            # 跳过前导零
            first_valid = find_first_valid_frame(evt)
            if first_valid > 0:
                self.log.emit(
                    f"  跳过前导零/预触发数据: {first_valid} 帧 "
                    f"({first_valid / header.sample_rate_hz:.1f} s)"
                )

            # 对每个分量进行处理
            results: dict = {}
            exported_count = 0

            for comp_name in self.components:
                self.log.emit(f"处理 {comp_name} 分量...")

                comp_data = get_component_array(evt, comp_name)[first_valid:]
                self.log.emit(
                    f"  有效数据: {len(comp_data)} 点 "
                    f"[{comp_data.min()}, {comp_data.max()}] "
                    f"mean={comp_data.mean():.1f}"
                )

                # 搜索最优窗口
                result = find_best_segment(
                    data=comp_data,
                    window_size=self.window_size,
                    sample_rate_hz=header.sample_rate_hz,
                    component=comp_name,
                )
                bw = result.best_window

                self.log.emit(
                    f"  最优窗口: [{bw.start_index}, {bw.end_index}) "
                    f"得分={bw.total_score:.4f} "
                    f"平稳性={bw.stationarity_score:.4f} "
                    f"弯曲={bw.curvature_penalty:.4f}"
                )

                # 重采样（如需要）
                export_sr = effective_sr
                export_data = result.data.copy()
                if (
                    self.target_sample_rate_hz
                    and abs(self.target_sample_rate_hz - header.sample_rate_hz) > 0.01
                ):
                    export_data = resample_data(
                        result.data,
                        header.sample_rate_hz,
                        self.target_sample_rate_hz,
                    )
                    self.log.emit(
                        f"  重采样: {header.sample_rate_hz:.1f} -> "
                        f"{self.target_sample_rate_hz:.1f} Hz "
                        f"({len(export_data)} 点)"
                    )

                # 计算在原始文件中的实际点号
                actual_start = first_valid + bw.start_index
                actual_end = first_valid + bw.end_index

                # 导出 DAT
                base_name = self.evt_path.stem
                dat_path = self.output_dir / f"{base_name}_{comp_name}.dat"

                export_dat(
                    data=export_data,
                    output_path=dat_path,
                    component=comp_name,
                    sample_rate_hz=export_sr,
                    start_sample_index=actual_start,
                    end_sample_index=actual_end,
                    original_file=self.evt_path.name,
                    original_sample_rate_hz=header.sample_rate_hz,
                    target_sample_rate_hz=self.target_sample_rate_hz,
                    record_time=str(header.record_time) if header.record_time else "",
                    extra_metadata={
                        "window_score": f"{bw.total_score:.4f}",
                        "stationarity": f"{bw.stationarity_score:.4f}",
                        "first_valid_frame": str(first_valid),
                    },
                )

                results[comp_name] = {
                    "dat_path": str(dat_path),
                    "start_index": actual_start,
                    "end_index": actual_end,
                    "score": bw.total_score,
                    "stationarity": bw.stationarity_score,
                    "sample_count": len(export_data),
                    "sample_rate": export_sr,
                }

                exported_count += 1
                self.log.emit(f"  已导出: {dat_path.name}")

            self.finished.emit(str(self.output_dir), exported_count, results)

        except Exception as exc:
            details = traceback.format_exc()
            self.failed.emit(f"{exc}\n\n{details}")