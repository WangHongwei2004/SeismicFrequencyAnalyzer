# -*- coding: utf-8 -*-
"""EVT 预处理后台工作线程。

read_evt() 已完成：int32 顺序三块解析 + 前导切除。
此Worker：读取 → 联合搜索 → 导出 TXT（兼容现有频谱分析）。
"""

from __future__ import annotations

import traceback
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal

from evt_reader import read_evt
from segment_selector import find_best_segment_three_component
from dat_exporter import export_three_component_dat


class EvtPreprocessWorker(QObject):
    """后台处理 EVT 文件：三分量联合筛选 → 导出 TXT。"""

    log = pyqtSignal(str)
    finished = pyqtSignal(str, str, dict)  # output_dir, txt_path, results
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
            h = evt.header

            self.log.emit(
                f"  台站: {h.station_name or '(未知)'} | "
                f"仪器: {h.instrument or '(未知)'} | "
                f"坐标: ({h.latitude:.4f}, {h.longitude:.4f})"
            )
            self.log.emit(
                f"  前导 int32: {h.preamble_int32} | "
                f"有效数据: {evt.sample_count} 点/分量 | "
                f"采样率: {self.instrument_sample_rate_hz:.0f} Hz | "
                f"窗口: {self.window_size} 点"
            )
            self.log.emit(
                f"  时长: {evt.sample_count / self.instrument_sample_rate_hz:.1f} s "
                f"@ {self.instrument_sample_rate_hz:.0f} Hz"
            )

            ew = evt.ew
            ns = evt.ns
            ud = evt.ud

            # 三分量联合搜索最优窗口
            self.log.emit("三分量联合搜索最优数据段...")
            result = find_best_segment_three_component(
                ew=ew, ns=ns, ud=ud,
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

            # 导出为 txt —— 兼容现有频谱分析
            base_name = self.evt_path.stem
            txt_path = self.output_dir / f"{base_name}.txt"

            export_three_component_dat(
                ew_data=result.ew_data,
                ns_data=result.ns_data,
                ud_data=result.ud_data,
                output_path=txt_path,
                sample_rate_hz=self.instrument_sample_rate_hz,
                start_sample_index=bw.start_index,
                end_sample_index=bw.end_index,
                original_file=self.evt_path.name,
                record_time=str(h.record_time) if h.record_time else "",
                extra_metadata={
                    "window_score": f"{bw.total_score:.4f}",
                    "ew_score": f"{bw.ew_score:.4f}",
                    "ns_score": f"{bw.ns_score:.4f}",
                    "ud_score": f"{bw.ud_score:.4f}",
                },
            )

            self.log.emit(f"  已导出: {txt_path.name}")

            results = {
                "txt_path": str(txt_path),
                "start_index": bw.start_index,
                "end_index": bw.end_index,
                "score": bw.total_score,
                "ew_score": bw.ew_score,
                "ns_score": bw.ns_score,
                "ud_score": bw.ud_score,
                "sample_count": len(result.ew_data),
                "sample_rate": self.instrument_sample_rate_hz,
            }

            self.finished.emit(str(self.output_dir), str(txt_path), results)

        except Exception as exc:
            details = traceback.format_exc()
            self.failed.emit(f"{exc}\n\n{details}")