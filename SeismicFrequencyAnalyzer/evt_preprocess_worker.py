# -*- coding: utf-8 -*-
"""EVT 预处理后台工作线程。

读取 EVT 文件，先重采样到地震仪实际采样率，再三分量联合搜索最优数据段，
导出为单个 DAT 文件（兼容现有 TXT 解析格式）。
"""

from __future__ import annotations

import traceback
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal

from evt_reader import read_evt, find_first_valid_frame, get_component_array
from segment_selector import find_best_segment_three_component, resample_data
from dat_exporter import export_three_component_dat


class EvtPreprocessWorker(QObject):
    """后台处理 EVT 文件：重采样 → 三分量联合筛选 → 导出 DAT。"""

    log = pyqtSignal(str)
    finished = pyqtSignal(str, str, dict)  # output_dir, dat_path, results
    failed = pyqtSignal(str)

    def __init__(
        self,
        evt_path: Path,
        output_dir: Path,
        window_size: int,
        instrument_sample_rate_hz: float,
    ) -> None:
        super().__init__()
        self.evt_path = evt_path
        self.output_dir = output_dir
        self.window_size = window_size
        self.instrument_sample_rate_hz = instrument_sample_rate_hz

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
                f"  EVT 内部采样率: {header.sample_rate_hz:.2f} Hz | "
                f"数据帧数: {header.total_frames} | "
                f"时长: {evt.duration_s:.1f} s"
            )
            self.log.emit(
                f"  地震仪采样率: {self.instrument_sample_rate_hz:.0f} Hz | "
                f"窗口大小: {self.window_size} 点"
            )

            # 跳过前导零
            first_valid = find_first_valid_frame(evt)
            if first_valid > 0:
                self.log.emit(
                    f"  跳过前导零/预触发数据: {first_valid} 帧 "
                    f"({first_valid / header.sample_rate_hz:.1f} s)"
                )

            ew_raw = get_component_array(evt, "EW")[first_valid:]
            ns_raw = get_component_array(evt, "NS")[first_valid:]
            ud_raw = get_component_array(evt, "UD")[first_valid:]

            # ── 步骤 1：先重采样整个三分量数据到地震仪采样率 ──
            need_resample = abs(header.sample_rate_hz - self.instrument_sample_rate_hz) > 0.01

            if need_resample:
                self.log.emit(
                    f"重采样: {header.sample_rate_hz:.2f} -> "
                    f"{self.instrument_sample_rate_hz:.0f} Hz ..."
                )
                ew = resample_data(
                    ew_raw.astype(float), header.sample_rate_hz,
                    self.instrument_sample_rate_hz,
                )
                ns = resample_data(
                    ns_raw.astype(float), header.sample_rate_hz,
                    self.instrument_sample_rate_hz,
                )
                ud = resample_data(
                    ud_raw.astype(float), header.sample_rate_hz,
                    self.instrument_sample_rate_hz,
                )
                self.log.emit(
                    f"  重采样完成: {len(ew)} 点/分量 "
                    f"({len(ew) / self.instrument_sample_rate_hz:.1f} s)"
                )
            else:
                ew = ew_raw.astype(float)
                ns = ns_raw.astype(float)
                ud = ud_raw.astype(float)

            # ── 步骤 2：三分量联合搜索最优窗口 ──
            self.log.emit("三分量联合搜索最优数据段...")
            result = find_best_segment_three_component(
                ew=ew,
                ns=ns,
                ud=ud,
                window_size=self.window_size,
                sample_rate_hz=self.instrument_sample_rate_hz,
                progress_callback=self.log.emit,
            )
            bw = result.best_window

            self.log.emit(
                f"  最优窗口: [{bw.start_index}, {bw.end_index}) "
                f"综合={bw.total_score:.4f} "
                f"EW={bw.ew_score:.4f} NS={bw.ns_score:.4f} "
                f"UD={bw.ud_score:.4f}"
            )

            # ── 步骤 3：计算在原始文件中的实际点号 ──
            if need_resample:
                # 重采样比例
                ratio = header.sample_rate_hz / self.instrument_sample_rate_hz
                actual_start = first_valid + int(round(bw.start_index * ratio))
                actual_end = first_valid + int(round(bw.end_index * ratio))
            else:
                actual_start = first_valid + bw.start_index
                actual_end = first_valid + bw.end_index

            # ── 步骤 4：导出单个三分量 DAT 文件 ──
            base_name = self.evt_path.stem
            dat_path = self.output_dir / f"{base_name}.dat"

            export_three_component_dat(
                ew_data=result.ew_data,
                ns_data=result.ns_data,
                ud_data=result.ud_data,
                output_path=dat_path,
                sample_rate_hz=self.instrument_sample_rate_hz,
                start_sample_index=actual_start,
                end_sample_index=actual_end,
                original_file=self.evt_path.name,
                original_sample_rate_hz=header.sample_rate_hz,
                record_time=str(header.record_time) if header.record_time else "",
                extra_metadata={
                    "window_score": f"{bw.total_score:.4f}",
                    "ew_score": f"{bw.ew_score:.4f}",
                    "ns_score": f"{bw.ns_score:.4f}",
                    "ud_score": f"{bw.ud_score:.4f}",
                    "first_valid_frame": str(first_valid),
                    "resampled": str(need_resample),
                },
            )

            self.log.emit(f"  已导出: {dat_path.name}")

            results = {
                "dat_path": str(dat_path),
                "start_index": actual_start,
                "end_index": actual_end,
                "score": bw.total_score,
                "ew_score": bw.ew_score,
                "ns_score": bw.ns_score,
                "ud_score": bw.ud_score,
                "sample_count": len(result.ew_data),
                "sample_rate": self.instrument_sample_rate_hz,
            }

            self.finished.emit(str(self.output_dir), str(dat_path), results)

        except Exception as exc:
            details = traceback.format_exc()
            self.failed.emit(f"{exc}\n\n{details}")