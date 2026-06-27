# -*- coding: utf-8 -*-
"""PyQt5 UI for the dominant-frequency analysis workflow."""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtCore import Qt, QThread, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QApplication,
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
from ui_style import MAIN_WINDOW_STYLE


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.project_dir = application_dir()
        self.worker_thread: QThread | None = None
        self.worker: AnalysisWorker | None = None

        self.setWindowTitle(f"宽频带地震动卓越频率分析 {APP_VERSION}")
        self.resize(1180, 840)
        self.setMinimumSize(1060, 760)
        self._build_menu()
        self._build_ui()
        self._apply_style()

    def _build_menu(self) -> None:
        help_menu = self.menuBar().addMenu("帮助")
        about_action = help_menu.addAction("关于")
        about_action.triggered.connect(self._show_about_dialog)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(24, 22, 24, 22)
        root_layout.setSpacing(16)

        header = QFrame()
        header.setObjectName("header")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(22, 18, 22, 18)
        header_layout.setSpacing(16)

        title_layout = QVBoxLayout()
        title_layout.setSpacing(5)
        title_label = QLabel("宽频带地震动卓越频率分析")
        title_label.setObjectName("appTitle")
        subtitle_label = QLabel("直接法与间接法频谱计算，自动标注 P1-P4 候选峰")
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

        path_group = QGroupBox("路径")
        path_layout = QGridLayout(path_group)
        path_layout.setContentsMargins(18, 24, 18, 18)
        path_layout.setHorizontalSpacing(12)
        path_layout.setVerticalSpacing(12)
        self.data_dir_edit = QLineEdit(str(self.project_dir / "data"))
        self.output_dir_edit = QLineEdit(str(self.project_dir / "two_method_spectrum_output"))
        data_button = QPushButton("浏览...")
        data_button.setObjectName("secondaryButton")
        output_button = QPushButton("浏览...")
        output_button.setObjectName("secondaryButton")
        data_button.clicked.connect(self._choose_data_dir)
        output_button.clicked.connect(self._choose_output_dir)
        path_layout.addWidget(QLabel("数据目录"), 0, 0)
        path_layout.addWidget(self.data_dir_edit, 0, 1)
        path_layout.addWidget(data_button, 0, 2)
        path_layout.addWidget(QLabel("输出目录"), 1, 0)
        path_layout.addWidget(self.output_dir_edit, 1, 1)
        path_layout.addWidget(output_button, 1, 2)

        settings_group = QGroupBox("参数")
        settings_group.setMinimumHeight(178)
        settings_layout = QGridLayout(settings_group)
        settings_layout.setContentsMargins(18, 24, 18, 18)
        settings_layout.setHorizontalSpacing(16)
        settings_layout.setVerticalSpacing(14)
        settings_layout.setColumnStretch(1, 1)
        settings_layout.setColumnStretch(3, 1)
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
            settings_layout.addWidget(label, row, label_column)
            settings_layout.addWidget(editor, row, label_column + 1)

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

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.status_label = QLabel("待运行")
        self.status_label.setObjectName("statusLabel")
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)
        self.log_edit.setPlaceholderText("运行日志会显示在这里。")

        status_panel = QFrame()
        status_panel.setObjectName("statusPanel")
        status_layout = QHBoxLayout(status_panel)
        status_layout.setContentsMargins(16, 12, 16, 12)
        status_layout.setSpacing(14)
        status_title = QLabel("运行状态")
        status_title.setObjectName("sectionLabel")
        status_layout.addWidget(status_title)
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.progress_bar, stretch=1)

        log_group = QGroupBox("运行日志")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(14, 24, 14, 14)
        log_layout.addWidget(self.log_edit)

        root_layout.addWidget(header)
        root_layout.addWidget(path_group)
        root_layout.addWidget(settings_group)
        root_layout.addLayout(action_layout)
        root_layout.addWidget(status_panel)
        root_layout.addWidget(log_group, stretch=1)
        self.setCentralWidget(root)

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

    def _show_about_dialog(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("关于")
        dialog.setModal(True)
        dialog.resize(460, 280)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        title = QLabel("宽频带地震动卓越频率分析")
        title.setObjectName("aboutTitle")
        title.setStyleSheet("font-size: 20px; font-weight: 700; color: #0f172a;")

        info = QLabel(
            f"软件版本号: {APP_VERSION}<br>"
            f"作者: {APP_AUTHOR}<br>"
            f"完成时间: {APP_COMPLETION_DATE}<br>"
            f'作者 GitHub 主页: <a href="{APP_GITHUB_URL}">{APP_GITHUB_URL}</a>'
        )
        info.setOpenExternalLinks(True)
        info.setTextFormat(Qt.RichText)
        info.setWordWrap(True)
        info.setStyleSheet(
            "color: #334155; font-size: 13px; line-height: 1.4; "
            "background: #f8fafc; border: 1px solid #d8dee8; border-radius: 8px; padding: 14px;"
        )

        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(dialog.accept)

        layout.addWidget(title)
        layout.addWidget(info)
        layout.addStretch(1)
        layout.addWidget(buttons)
        dialog.exec_()

    def _choose_data_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择数据目录", self.data_dir_edit.text())
        if directory:
            self.data_dir_edit.setText(directory)

    def _choose_output_dir(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择输出目录", self.output_dir_edit.text())
        if directory:
            self.output_dir_edit.setText(directory)

    def _run_analysis(self) -> None:
        data_dir = Path(self.data_dir_edit.text()).expanduser()
        output_dir = Path(self.output_dir_edit.text()).expanduser()
        min_peak = self.min_peak_spin.value()
        max_peak = self.max_peak_spin.value()
        plot_max = self.plot_max_spin.value()
        processing_points = self.processing_points_spin.value()
        if max_peak > 0 and max_peak < min_peak:
            QMessageBox.warning(self, "参数错误", "选峰上限必须大于或等于选峰下限；上限为 0 表示不设上限。")
            return
        if processing_points == 1:
            QMessageBox.warning(self, "参数错误", "实际处理点数必须为 0（全部）或大于等于 2。")
            return

        self.log_edit.clear()
        self._append_log("开始分析")
        self.progress_bar.setRange(0, 0)
        self.status_label.setText("运行中...")
        self.run_button.setEnabled(False)
        self.open_output_button.setEnabled(False)

        self.worker_thread = QThread(self)
        self.worker = AnalysisWorker(data_dir, output_dir, min_peak, max_peak, plot_max, processing_points)
        self.worker.moveToThread(self.worker_thread)
        self.worker_thread.started.connect(self.worker.run)
        self.worker.log.connect(self._append_log)
        self.worker.finished.connect(self._analysis_finished)
        self.worker.failed.connect(self._analysis_failed)
        self.worker.finished.connect(self.worker_thread.quit)
        self.worker.failed.connect(self.worker_thread.quit)
        self.worker_thread.finished.connect(self._thread_finished)
        self.worker_thread.start()

    def _analysis_finished(self, csv_path: str, file_count: int, figure_count: int) -> None:
        self._append_log(f"处理完成：数据文件 {file_count} 个，图文件 {figure_count} 张")
        self._append_log(f"结果表: {csv_path}")
        self.status_label.setText("处理完成")
        self.open_output_button.setEnabled(True)

    def _analysis_failed(self, message: str) -> None:
        self._append_log(message)
        self.status_label.setText("处理失败")
        QMessageBox.critical(self, "处理失败", message.splitlines()[0])

    def _thread_finished(self) -> None:
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
