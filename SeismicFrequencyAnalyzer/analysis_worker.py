# -*- coding: utf-8 -*-
"""Background worker for running the frequency analysis from the UI."""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

from PyQt5.QtCore import QObject, pyqtSignal


class AnalysisWorker(QObject):
    log = pyqtSignal(str)
    finished = pyqtSignal(str, int, int)
    failed = pyqtSignal(str)

    def __init__(
        self,
        data_dir: Path,
        output_dir: Path,
        min_peak_frequency: float,
        max_peak_frequency: float,
        plot_max_frequency: float,
        processing_point_count: int,
    ) -> None:
        super().__init__()
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.min_peak_frequency = min_peak_frequency
        self.max_peak_frequency = max_peak_frequency
        self.plot_max_frequency = plot_max_frequency
        self.processing_point_count = processing_point_count

    def run(self) -> None:
        try:
            try:
                from dominant_frequency_two_methods import run_analysis
            except ModuleNotFoundError as exc:
                missing_package = exc.name or "未知依赖"
                self.failed.emit(
                    f"当前 Python 环境缺少依赖: {missing_package}\n\n"
                    f"当前解释器: {sys.executable}\n\n"
                    "请在 PowerShell 中执行:\n"
                    f'"{sys.executable}" -m pip install matplotlib numpy PyQt5'
                )
                return
            results, figures, csv_path, peak_band = run_analysis(
                self.data_dir,
                self.output_dir,
                self.min_peak_frequency,
                self.max_peak_frequency,
                self.plot_max_frequency,
                self.processing_point_count,
                progress_callback=self.log.emit,
            )
            file_count = len({result.file_name for result in results})
            self.finished.emit(str(csv_path), file_count, len(figures))
            self.log.emit(f"卓越频率选峰范围: {peak_band}")
        except Exception as exc:
            details = traceback.format_exc()
            self.failed.emit(f"{exc}\n\n{details}")
