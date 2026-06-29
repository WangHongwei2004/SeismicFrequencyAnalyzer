# -*- coding: utf-8 -*-
"""PyQt5 UI for the dominant-frequency analysis workflow.

v1.1.0 — 新增 EVT 原始数据预处理（自动筛选最优线性段，导出 DAT）。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from analysis_worker import AnalysisWorker
from app_info import (
    APP_AUTHOR,
    APP_COMPLETION_DATE,
    APP_GITHUB_URL,
    APP_VERSION,
    application_dir,
    load_default_peak_settings,
)
from evt_preprocess_worker import EvtPreprocessWorker
from ui_style import MAIN_WINDOW_STYLE


# ── 常量 ──────────────────────────────────────────────────────────

_APP_TITLE = "宽频带地震动卓越频率分析"
_APP_SUBTITLE = "直接法与间接法频谱计算，自动标注 P1-P4 候选峰 — EVT 智能裁剪"

_WINDOW_SIZE_OPTIONS = {
    "1024 点": 1024,
    "2048 点": 2048,
    "4096 点": 4096,
    "8192 点": 8192,
}

_SAMPLE_RATE_OPTIONS = [
    ("50 Hz", 50.0),
    ("100 Hz", 100.0),
    ("200 Hz", 200.0),
]


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.project_dir = application_dir()

        # 原有的分析线程
        self.worker_thread: QThread | None = None
        self.worker: AnalysisWorker | None = None

        # EVT 预处理线程
        self.evt_thread: QThread | None = None
        self.evt_worker: EvtPreprocessWorker | None = None
        self.evt_output_dir: Path | None = None  # 记录预处理输出目录

        self.setWindowTitle(f"{_APP_TITLE} {APP_VERSION}")
        self.resize(1200, 980)
        self.setMinimumSize(1080, 880)
        self._build_menu()
        self._build_ui()
        self._apply_style()

    # ── 菜单 ───────────────────────────────────────────────────────

    def _build_menu(self) -> None:
        help_menu = self.menuBar().addMenu("帮助")
        about_action = help_menu.addAction("关于")
        about_action.triggered.connect(self._show_about_dialog)

    # ── UI 构建 ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(24, 22, 24, 22)
        root_layout.setSpacing(14)

        # ── 标题头 ──
        header = self._build_header()
        root_layout.addWidget(header)

        # ── EVT 预处理（新增）──
        evt_group = self._build_evt_preprocess_group()
        root_layout.addWidget(evt_group)

        # ── 路径 ──
        path_group = self._build_path_group()
        root_layout.addWidget(path_group)

        # ── 参数 ──
        settings_group = self._build_settings_group()
        root_layout.addWidget(settings_group)

        # ── 操作按钮 ──
        action_layout = self._build_action_layout()
        root_layout.addLayout(action_layout)

        # ── 状态 ──
        status_panel = self._build_status_panel()
        root_layout.addWidget(status_panel)

        # ── 日志 ──
        log_group = self._build_log_group()
        root_layout.addWidget(log_group, stretch=1)

        self.setCentralWidget(root)

    # ── 标题头 ──

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 18, 22, 18)
        header_layout.setSpacing(16)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(5)
        title_label = QLabel(_APP_TITLE)
        title_label.setObjectName("appTitle")
        subtitle_label = QLabel(_APP_SUBTITLE)
        subtitle_label.setObjectName("appSubtitle")
        title_layout.addWidget(title_label)
        title_layout.addWidget(subtitle_label)

        version_label = QLabel(APP_VERSION)
        version_label.setObjectName("versionBadge")
        version_label.setAlignment(Qt.AlignCenter)
        self.about_button = QPushButton("关于")
        self.about_button.setObjectName("secondaryButton")
        self.about_button.clicked.connect(self._show_about_dialog)

        header_layout.addLayout(title_layout, stretch=1)
        header_layout.addWidget(version_label)
        header_layout.addWidget(self.about_button)
        return header

    # ── EVT 预处理 ──

    def _build_evt_preprocess_group(self) -> QGroupBox:
        group = QGroupBox("EVT 数据预处理 — 自动筛选最优线性段")
        layout = QGridLayout(group)
        layout.setContentsMargins(18, 24, 18, 18)
        layout.setHorizontalSpacing(14)
        layout.setVerticalSpacing(12)

        # EVT 文件选择
        self.evt_path_edit = QLineEdit()
        self.evt_path_edit.setPlaceholderText("选择 .evt 原始数据文件...")
        evt_browse = QPushButton("浏览...")
        evt_browse.setObjectName("secondaryButton")
        evt_browse.clicked.connect(self._choose_evt_file)

        layout.addWidget(QLabel("EVT 文件"), 0, 0)
        layout.addWidget(self.evt_path_edit, 0, 1)
        layout.addWidget(evt_browse, 0, 2)

        # 窗口大小
        layout.addWidget(QLabel("截取长度"), 1, 0)
        self.window_size_combo = QComboBox()
        for label, _ in _WINDOW_SIZE_OPTIONS.items():
            self.window_size_combo.addItem(label)
        self.window_size_combo.setCurrentIndex(1)  # 默认 2048
        layout.addWidget(self.window_size_combo, 1, 1)

        # 自定义窗口大小
        self.custom_window_spin = QSpinBox()
        self.custom_window_spin.setRange(128, 100000)
        self.custom_window_spin.setSingleStep(128)
        self.custom_window_spin.setValue(2048)
        self.custom_window_spin.setEnabled(False)
        self.custom_window_spin.setToolTip("自定义截取点数（勾选后方可编辑）")
        self.custom_window_check = QCheckBox("自定义")
        self.custom_window_check.toggled.connect(
            lambda checked: self.custom_window_spin.setEnabled(checked)
        )
        custom_layout = QHBoxLayout()
        custom_layout.addWidget(self.custom_window_check)
        custom_layout.addWidget(self.custom_window_spin)
        layout.addLayout(custom_layout, 1, 2)

        # 目标采样率
        layout.addWidget(QLabel("地震仪采样率"), 2, 0)
        self.sample_rate_combo = QComboBox()
        for label, _ in _SAMPLE_RATE_OPTIONS:
            self.sample_rate_combo.addItem(label)
        self.sample_rate_combo.setCurrentIndex(1)  # 默认 100 Hz
        layout.addWidget(self.sample_rate_combo, 2, 1)

        # 分量选择（始终处理全部三分量）
        layout.addWidget(QLabel("处理分量"), 2, 2)
        comp_layout = QHBoxLayout()
        comp_label = QLabel("EW + NS + UD（三分量联合筛选）")
        comp_label.setStyleSheet("color: #526070; font-size: 12px;")
        comp_layout.addWidget(comp_label)
        comp_layout.addStretch()
        layout.addLayout(comp_layout, 3, 0, 1, 3)

        # 操作按钮
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        self.evt_run_button = QPushButton("裁剪并导出 DAT")
        self.evt_run_button.setObjectName("primaryButton")
        self.evt_run_button.clicked.connect(self._run_evt_preprocess)
        self.evt_open_button = QPushButton("打开 DAT 输出目录")
        self.evt_open_button.setObjectName("secondaryButton")
        self.evt_open_button.setEnabled(False)
        self.evt_open_button.clicked.connect(self._open_evt_output_dir)
        btn_layout.addWidget(self.evt_run_button)
        btn_layout.addWidget(self.evt_open_button)
        btn_layout.addStretch()
        layout.addLayout(btn_layout, 4, 0, 1, 3)

        return group

    # ── 路径 ──

    def _build_path_group(self) -> QGroupBox:
        group = QGroupBox("频谱分析 — 路径")
        layout = QGridLayout(group)
        layout.setContentsMargins(18, 24, 18, 18)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(12)
        self.data_dir_edit = QLineEdit(str(self.project_dir / "data"))
        self.output_dir_edit = QLineEdit(
            str(self.project_dir / "two_method_spectrum_output")
        )
        data_button = QPushButton("浏览...")
        data_button.setObjectName("secondaryButton")
        data_button.clicked.connect(self._choose_data_dir)
        output_button = QPushButton("浏览...")
        output_button.setObjectName("secondaryButton")
        output_button.clicked.connect(self._choose_output_dir)
        layout.addWidget(QLabel("数据目录"), 0, 0)
        layout.addWidget(self.data_dir_edit, 0, 1)
        layout.addWidget(data_button, 0, 2)
        layout.addWidget(QLabel("输出目录"), 1, 0)
        layout.addWidget(self.output_dir_edit, 1, 1)
        layout.addWidget(output_button, 1, 2)
        return group

    # ── 参数 ──

    def _build_settings_group(self) -> QGroupBox:
        group = QGroupBox("频谱分析 — 参数")
        group.setMinimumHeight(160)
        layout = QGridLayout(group)
        layout.setContentsMargins(18, 24, 18, 18)
        layout.setHorizontalSpacing(16)
        layout.setVerticalSpacing(14)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(3, 1)
        min_peak_default, max_peak_default = load_default_peak_settings()
        self.min_peak_spin = self._make_frequency_spin(min_peak_default)
        self.max_peak_spin = self._make_frequency_spin(max_peak_default)
        self.plot_max_spin = self._make_frequency_spin(0.0)
        self.processing_points_spin = self._make_point_count_spin()
        settings_items = [
            ("选峰下限 Hz", self.min_peak_spin),
            ("选峰上限 Hz（0 表示不设上限）", self.max_peak_spin),
            ("频谱图显示上限 Hz（0 表示到 Nyquist）", self.plot_max_spin),
            ("实际处理点数（0 表示全部）", self.processing_points_spin),
        ]
        for index, (label_text, editor) in enumerate(settings_items):
            row = index // 2
            label_column = (index % 2) * 2
            label = QLabel(label_text)
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            label.setWordWrap(True)
            editor.setMinimumWidth(220)
            layout.addWidget(label, row, label_column)
            layout.addWidget(editor, row, label_column + 1)
        return group

    # ── 操作按钮 ──

    def _build_action_layout(self) -> QHBoxLayout:
        action_layout = QHBoxLayout()
        action_layout.setSpacing(10)
        self.run_button = QPushButton("开始分析")
        self.run_button.setObjectName("primaryButton")
        self.open_output_button = QPushButton("打开输出目录")
        self.open_output_button.setObjectName("secondaryButton")
        self.open_output_button.setEnabled(False)
        self.run_button.clicked.connect(self._run_analysis)
        self.open_output_button.clicked.connect(self._open_output_dir)
        action_layout.addWidget(self.run_button)
        action_layout.addWidget(self.open_output_button)
        action_layout.addStretch(1)
        return action_layout

    # ── 状态栏 ──

    def _build_status_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("statusPanel")
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(14)
        status_title = QLabel("运行状态")
        status_title.setObjectName("sectionLabel")
        layout.addWidget(status_title)
        self.status_label = QLabel("待运行")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar, stretch=1)
        return panel

    # ── 日志 ──

    def _build_log_group(self) -> QGroupBox:
        group = QGroupBox("运行日志")
        layout = QVBoxLayout(group)
        layout.setContentsMargins(14, 24, 14, 14)
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setPlaceholderText("运行日志会显示在这里。")
        layout.addWidget(self.log_edit)
        return group

    # ── 微件工厂 ───────────────────────────────────────────────────

    def _make_frequency_spin(self, value: float) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(4)
        spin.setRange(0.0, 100000.0)
        spin.setSingleStep(0.1)
        spin.setValue(float(value))
        return spin

    def _make_point_count_spin(self) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(0, 10_000_000)
        spin.setSingleStep(1024)
        spin.setSpecialValueText("全部")
        spin.setValue(0)
        return spin

    def _apply_style(self) -> None:
        self.setStyleSheet(MAIN_WINDOW_STYLE)

    # ── 对话框 ─────────────────────────────────────────────────────

    def _show_about_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("关于")
        dialog.setModal(True)
        dialog.resize(480, 320)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        title = QLabel(_APP_TITLE)
        title.setObjectName("aboutTitle")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #0f172a;")

        info = QLabel(
            f"软件版本号: {APP_VERSION}<br>"
            f"作者: {APP_AUTHOR}<br>"
            f"完成时间: {APP_COMPLETION_DATE}<br>"
            f"新功能: EVT 原始数据智能裁剪<br>"
            f'作者 GitHub 主页: <a href="{APP_GITHUB_URL}">{APP_GITHUB_URL}</a>'
        )
        info.setOpenExternalLinks(True)
        info.setTextFormat(Qt.RichText)
        info.setWordWrap(True)
        info.setStyleSheet(
            "color: #334155; font-size: 13px; line-height: 1.4; "
            "background: #f8fafc; border: 1px solid #d8dee8; "
            "border-radius: 8px; padding: 14px;"
        )

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(dialog.accept)

        layout.addWidget(title)
        layout.addWidget(info)
        layout.addStretch(1)
        layout.addWidget(buttons)
        dialog.exec_()

    # ── 文件选择 ───────────────────────────────────────────────────

    def _choose_evt_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择 EVT 原始数据文件",
            str(self.project_dir),
            "EVT 文件 (*.evt);;所有文件 (*)",
        )
        if file_path:
            self.evt_path_edit.setText(file_path)

    def _choose_data_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "选择数据目录", self.data_dir_edit.text()
        )
        if directory:
            self.data_dir_edit.setText(directory)

    def _choose_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(
            self, "选择输出目录", self.output_dir_edit.text()
        )
        if directory:
            self.output_dir_edit.setText(directory)

    # ── EVT 预处理 ─────────────────────────────────────────────────

    def _run_evt_preprocess(self) -> None:
        evt_path = Path(self.evt_path_edit.text()).expanduser()
        if not evt_path.exists():
            QMessageBox.warning(self, "文件不存在", f"找不到文件:\n{evt_path}")
            return

        # 窗口大小
        if self.custom_window_check.isChecked():
            window_size = self.custom_window_spin.value()
        else:
            idx = self.window_size_combo.currentIndex()
            window_size = list(_WINDOW_SIZE_OPTIONS.values())[idx]

        # 目标采样率
        sr_idx = self.sample_rate_combo.currentIndex()
        instrument_sr = _SAMPLE_RATE_OPTIONS[sr_idx][1]

        # 输出目录
        output_dir = self.project_dir / "evt_dat_output"
        output_dir.mkdir(exist_ok=True)

        self.log_edit.clear()
        self._append_log("=== EVT 预处理 ===")
        self._append_log(f"输入文件: {evt_path}")
        self._append_log(f"窗口大小: {window_size} 点")
        self._append_log(f"地震仪采样率: {instrument_sr:.0f} Hz | 窗口大小: {window_size} 点")
        self._append_log("分量: EW + NS + UD（三分量联合筛选）")
        self._append_log(f"输出目录: {output_dir}")
        self._append_log("")

        self.progress_bar.setRange(0, 0)
        self.status_label.setText("EVT 处理中...")
        self.evt_run_button.setEnabled(False)
        self.evt_open_button.setEnabled(False)

        self.evt_output_dir = output_dir

        self.evt_thread = QThread(self)
        self.evt_worker = EvtPreprocessWorker(
            evt_path=evt_path,
            output_dir=output_dir,
            window_size=window_size,
            instrument_sample_rate_hz=instrument_sr,
        )
        self.evt_worker.moveToThread(self.evt_thread)
        self.evt_thread.started.connect(self.evt_worker.run)
        self.evt_worker.log.connect(self._append_log)
        self.evt_worker.finished.connect(self._evt_finished)
        self.evt_worker.failed.connect(self._evt_failed)
        self.evt_worker.finished.connect(self.evt_thread.quit)
        self.evt_worker.failed.connect(self.evt_thread.quit)
        self.evt_thread.finished.connect(self._evt_thread_done)
        self.evt_thread.start()

    def _evt_finished(self, output_dir: str, dat_path: str,
                      results: dict) -> None:
        self._append_log("")
        self._append_log("=== 预处理完成，已导出三分量 DAT 文件 ===")
        self._append_log(f"  DAT 文件: {Path(dat_path).name}")
        self._append_log(f"  {results['sample_count']} 点/分量 @ {results['sample_rate']:.1f} Hz")
        self._append_log(f"  综合得分: {results['score']:.4f}")
        self._append_log(f"  EW={results['ew_score']:.4f} NS={results['ns_score']:.4f} UD={results['ud_score']:.4f}")

    def _evt_failed(self, message: str) -> None:
        self._append_log(message)
        self.status_label.setText("EVT 处理失败")
        QMessageBox.critical(self, "处理失败", message.splitlines()[0])

    def _evt_thread_done(self) -> None:
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self.status_label.setText("EVT 处理完成")
        self.evt_run_button.setEnabled(True)
        self.evt_open_button.setEnabled(True)
        self.evt_worker = None
        self.evt_thread = None

    def _open_evt_output_dir(self) -> None:
        if self.evt_output_dir is not None:
            QDesktopServices.openUrl(
                QUrl.fromLocalFile(str(self.evt_output_dir.resolve()))
            )

    # ── 频谱分析 ───────────────────────────────────────────────────

    def _run_analysis(self) -> None:
        data_dir = Path(self.data_dir_edit.text()).expanduser()
        output_dir = Path(self.output_dir_edit.text()).expanduser()
        min_peak = self.min_peak_spin.value()
        max_peak = self.max_peak_spin.value()
        plot_max = self.plot_max_spin.value()
        processing_points = self.processing_points_spin.value()
        if max_peak > 0 and max_peak < min_peak:
            QMessageBox.warning(
                self, "参数错误",
                "选峰上限必须大于或等于选峰下限；上限为 0 表示不设上限。",
            )
            return
        if processing_points == 1:
            QMessageBox.warning(
                self, "参数错误",
                "实际处理点数必须为 0（全部）或大于等于 2。",
            )
            return

        self.log_edit.clear()
        self._append_log("=== 频谱分析 ===")
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("分析中...")
        self.run_button.setEnabled(False)
        self.open_output_button.setEnabled(False)

        self.worker_thread = QThread(self)
        self.worker = AnalysisWorker(
            data_dir, output_dir, min_peak, max_peak, plot_max, processing_points
        )
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.log.connect(self._append_log)
        self.worker.finished.connect(self._analysis_finished)
        self.worker.failed.connect(self._analysis_failed)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._analysis_thread_done)
        self.worker_thread.start()

    def _analysis_finished(
        self, csv_path: str, file_count: int, figure_count: int
    ) -> None:
        self._append_log(
            f"分析完成：数据文件 {file_count} 个，图文件 {figure_count} 张"
        )
        self._append_log(f"结果表: {csv_path}")
        self.status_label.setText("分析完成")
        self.run_button.setEnabled(True)
        self.open_output_button.setEnabled(True)

    def _analysis_failed(self, message: str) -> None:
        self._append_log(message)
        self.status_label.setText("分析失败")
        QMessageBox.critical(self, "处理失败", message.splitlines()[0])

    def _analysis_thread_done(self) -> None:
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self.run_button.setEnabled(True)
        self.worker = None
        self.worker_thread = None

    def _open_output_dir(self) -> None:
        output_dir = Path(self.output_dir_edit.text()).expanduser()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_dir.resolve())))

    def _append_log(self, message: str) -> None:
        self.log_edit.appendPlainText(message)


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()