# -*- coding: utf-8 -*-
"""Qt stylesheet for the desktop UI."""

MAIN_WINDOW_STYLE = """
QMainWindow {
    background: #eef2f7;
}
QMenuBar {
    background: #ffffff;
    color: #1f2937;
    padding: 4px 10px;
    border-bottom: 1px solid #d8dee8;
}
QMenuBar::item {
    padding: 6px 10px;
    border-radius: 4px;
}
QMenuBar::item:selected {
    background: #e8eef7;
}
QMenu {
    background: #ffffff;
    border: 1px solid #cfd7e3;
    padding: 5px;
}
QMenu::item {
    padding: 7px 28px 7px 18px;
    border-radius: 4px;
}
QMenu::item:selected {
    background: #e8eef7;
}
QWidget#root {
    background: #eef2f7;
    color: #182230;
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 14px;
}
QFrame#header {
    background: #ffffff;
    border: 1px solid #d8dee8;
    border-radius: 8px;
}
QLabel#appTitle {
    color: #0f172a;
    font-size: 24px;
    font-weight: 700;
}
QLabel#appSubtitle {
    color: #526070;
    font-size: 14px;
}
QLabel#versionBadge {
    min-width: 68px;
    padding: 6px 10px;
    color: #0f4c81;
    background: #e8f1fb;
    border: 1px solid #bdd4ee;
    border-radius: 6px;
    font-weight: 600;
}
QGroupBox {
    background: #ffffff;
    border: 1px solid #d8dee8;
    border-radius: 8px;
    margin-top: 12px;
    font-weight: 600;
    color: #182230;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 14px;
    padding: 0 6px;
    color: #0f4c81;
    background: #ffffff;
}
QLabel {
    color: #2d3748;
}
QLabel#sectionLabel {
    color: #0f4c81;
    font-weight: 600;
}
QLabel#statusLabel {
    min-width: 82px;
    padding: 5px 10px;
    color: #334155;
    background: #f8fafc;
    border: 1px solid #dbe3ef;
    border-radius: 6px;
}
QLineEdit, QDoubleSpinBox, QSpinBox {
    min-height: 30px;
    padding: 4px 8px;
    color: #182230;
    background: #fbfdff;
    border: 1px solid #cfd7e3;
    border-radius: 6px;
    selection-background-color: #0f4c81;
}
QLineEdit:focus, QDoubleSpinBox:focus, QSpinBox:focus {
    border: 1px solid #0f4c81;
    background: #ffffff;
}
QPushButton {
    min-height: 32px;
    padding: 6px 16px;
    border-radius: 6px;
    font-weight: 600;
}
QPushButton#primaryButton {
    color: #ffffff;
    background: #0f4c81;
    border: 1px solid #0f4c81;
}
QPushButton#primaryButton:hover {
    background: #0d416f;
}
QPushButton#primaryButton:pressed {
    background: #0a355c;
}
QPushButton#secondaryButton {
    color: #18364f;
    background: #ffffff;
    border: 1px solid #b9c7d8;
}
QPushButton#secondaryButton:hover {
    background: #f3f7fb;
    border-color: #8da4bf;
}
QPushButton:disabled {
    color: #94a3b8;
    background: #e5eaf1;
    border: 1px solid #d6dde8;
}
QFrame#statusPanel {
    background: #ffffff;
    border: 1px solid #d8dee8;
    border-radius: 8px;
}
QProgressBar {
    min-height: 12px;
    text-align: center;
    color: transparent;
    background: #e5eaf1;
    border: 1px solid #d8dee8;
    border-radius: 6px;
}
QProgressBar::chunk {
    background: #0f4c81;
    border-radius: 5px;
}
QPlainTextEdit {
    color: #1f2937;
    background: #fbfdff;
    border: 1px solid #cfd7e3;
    border-radius: 6px;
    padding: 8px;
    font-family: "Consolas", "Microsoft YaHei", monospace;
    font-size: 12px;
}
"""
