"""Visual theme: graphite, éclair text and a caramel accent."""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

# Palette ---------------------------------------------------------------
BG = "#141619"
CANVAS = "#111316"
RIBBON = "#1b1d21"
RIBBON_ALT = "#202329"
PANEL = "#1d2024"
PAGE = "#1e2125"
FIELD = "#17191d"
BORDER = "#2a2e34"
BORDER_STRONG = "#3a3f47"
TEXT = "#f2ebdd"          # éclair
MUTED = "#a39d91"
FAINT = "#736f66"
ACCENT = "#d3a35f"        # caramel
ACCENT_HOVER = "#e2b676"
ACCENT_PRESSED = "#b98a4b"
ACCENT_DIM = "#3a2f21"
GOLD = "#d8b26e"
BLUE = "#7da7d9"
RED = "#d97a6c"
GREEN = "#7fbf9a"
SELECTION = "#594a33"
HIGHLIGHT = "#6b5427"

UI_FONT = "Segoe UI"
DOC_FONT = "Georgia"
MONO_FONT = "Consolas"


STYLESHEET = f"""
* {{
    outline: none;
}}
QWidget {{
    background: transparent;
    color: {TEXT};
    font-family: "{UI_FONT}", "Inter", sans-serif;
    font-size: 13px;
}}
QMainWindow, QDialog {{
    background: {BG};
}}
QMenuBar {{
    background: {BG};
    color: {TEXT};
    border-bottom: 1px solid {BORDER};
    padding: 2px 8px;
    spacing: 2px;
}}
QMenuBar::item {{
    background: transparent;
    border-radius: 4px;
    padding: 5px 10px;
}}
QMenuBar::item:selected {{
    background: {PANEL};
}}
QMenu {{
    background: {RIBBON_ALT};
    border: 1px solid {BORDER_STRONG};
    border-radius: 7px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 30px 7px 24px;
    border-radius: 5px;
}}
QMenu::item:selected {{
    background: {ACCENT_DIM};
}}
QMenu::item:disabled {{
    color: {FAINT};
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 5px 8px;
}}
QToolBar {{
    background: {RIBBON};
    border: none;
    border-bottom: 1px solid {BORDER};
    spacing: 4px;
    padding: 5px 10px;
}}
QToolBar#TopBar {{
    border-bottom: 1px solid {BORDER};
    padding-bottom: 6px;
}}
QToolBar#FormatBar {{
    background: {RIBBON_ALT};
    padding-top: 6px;
    padding-bottom: 7px;
}}
QToolBar::separator {{
    background: {BORDER};
    width: 1px;
    margin: 4px 7px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px;
    padding: 4px;
    color: {TEXT};
}}
QToolButton:hover {{
    background: {PANEL};
    border-color: {BORDER};
}}
QToolButton:pressed {{
    background: {FIELD};
}}
QToolButton:checked {{
    background: {ACCENT_DIM};
    border-color: #6b5634;
}}
QToolButton:disabled {{
    color: {FAINT};
}}
QToolButton::menu-indicator {{
    image: none;
}}
QToolButton#ColorButton {{
    padding: 3px;
}}
QComboBox {{
    background: {FIELD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 26px 4px 8px;
    min-height: 20px;
    selection-background-color: {ACCENT_DIM};
}}
QComboBox:hover {{
    border-color: {BORDER_STRONG};
}}
QComboBox:focus {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px;
    border: none;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {MUTED};
    width: 0;
    height: 0;
    margin-right: 7px;
}}
QComboBox QAbstractItemView {{
    background: {RIBBON_ALT};
    border: 1px solid {BORDER_STRONG};
    border-radius: 6px;
    padding: 4px;
    selection-background-color: {ACCENT_DIM};
    outline: none;
}}
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background: {FIELD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: {SELECTION};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {ACCENT};
}}
QPlainTextEdit, QTextBrowser {{
    background: {FIELD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px;
    selection-background-color: {SELECTION};
}}
QPlainTextEdit#FrontMatter {{
    background: #14161a;
    color: #cfc7b8;
    font-family: "{MONO_FONT}", monospace;
    font-size: 12px;
    border: 1px solid {BORDER};
}}
QPlainTextEdit#Preview {{
    background: #121418;
    color: #c8c2b5;
    font-family: "{MONO_FONT}", monospace;
    font-size: 12px;
    border: none;
}}
QPlainTextEdit#LogView {{
    background: #121418;
    color: #cfc7b8;
    font-family: "{MONO_FONT}", monospace;
    font-size: 12px;
    border: none;
    padding: 8px;
}}
QPlainTextEdit#LogInput {{
    background: {FIELD};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 8px;
    font-size: 12px;
}}
QPlainTextEdit#LogInput:focus {{
    border-color: {ACCENT};
}}
QTreeView#FileTree {{
    background: #121418;
    border: none;
    color: #d8d1c4;
    selection-background-color: {ACCENT_DIM};
    selection-color: {TEXT};
    outline: none;
}}
QTreeView#FileTree::item {{
    padding: 3px 4px;
    border-radius: 4px;
}}
QTreeView#FileTree::item:hover {{
    background: {PANEL};
}}
QTreeView#FileTree::item:selected {{
    background: {ACCENT_DIM};
    color: {TEXT};
}}
QTreeView#FileTree::branch {{
    background: transparent;
}}
QTextBrowser#ChatView {{
    background: #121418;
    color: {TEXT};
    border: none;
    padding: 6px;
}}
QPlainTextEdit#ChatInput {{
    background: {FIELD};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 8px;
    font-size: 12px;
}}
QPlainTextEdit#ChatInput:focus {{
    border-color: {ACCENT};
}}
QTabWidget#PreviewTabs::pane, QTabWidget#WorkspaceTabs::pane {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    top: -1px;
}}
QTabBar::tab {{
    background: {PANEL};
    color: {MUTED};
    border: 1px solid {BORDER};
    border-bottom: none;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    padding: 5px 12px;
    margin-right: 3px;
}}
QTabBar::tab:selected {{
    background: {FIELD};
    color: {TEXT};
    border-color: {BORDER_STRONG};
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT};
}}
QTextEdit#Editor {{
    background: {PAGE};
    color: {TEXT};
    border: 1px solid #2c3036;
    border-radius: 12px;
    selection-background-color: {SELECTION};
    selection-color: #fff8ea;
}}
QTextEdit#Editor:focus {{
    border-color: #373c43;
}}
QFrame#PageFrame {{
    background: {CANVAS};
    border: none;
}}
QFrame#PreviewPanel {{
    background: {PANEL};
    border-left: 1px solid {BORDER};
}}
QFrame#FrontMatterPanel {{
    background: {PANEL};
    border-bottom: 1px solid {BORDER};
}}
QFrame#Ribbon {{
    background: {RIBBON};
    border-bottom: 1px solid {BORDER};
}}
QLabel#AppTitle {{
    color: {TEXT};
    font-size: 13px;
    font-weight: 600;
}}
QLabel#DocTitle {{
    color: {MUTED};
    font-size: 12px;
}}
QLabel#SectionLabel {{
    color: {FAINT};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
}}
QLabel#Hint {{
    color: {MUTED};
    font-size: 11px;
}}
QLabel#Warning {{
    color: {GOLD};
    font-size: 11px;
}}
QLabel#Chip {{
    background: {ACCENT_DIM};
    color: {ACCENT_HOVER};
    border: 1px solid #5b4a2f;
    border-radius: 5px;
    padding: 2px 6px;
    font-family: "{MONO_FONT}", monospace;
    font-size: 11px;
}}
QPushButton {{
    background: {PANEL};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
    border-radius: 7px;
    padding: 7px 14px;
    min-height: 18px;
}}
QPushButton:hover {{
    background: #272b31;
    border-color: #4a5059;
}}
QPushButton:pressed {{
    background: {FIELD};
}}
QPushButton#Primary {{
    background: {ACCENT};
    color: #1a1711;
    border: 1px solid {ACCENT};
    font-weight: 600;
}}
QPushButton#Primary:hover {{
    background: {ACCENT_HOVER};
}}
QPushButton:disabled {{
    color: {FAINT};
    border-color: {BORDER};
}}
QCheckBox {{
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1px solid {BORDER_STRONG};
    background: {FIELD};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 14px;
    padding: 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 5px;
    color: {MUTED};
}}
QStatusBar {{
    background: {BG};
    color: {MUTED};
    border-top: 1px solid {BORDER};
}}
QStatusBar QLabel {{
    color: {MUTED};
    padding: 0 8px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 11px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #3a3e45;
    min-height: 24px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical:hover {{
    background: #4b5059;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 11px;
    margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: #3a3e45;
    min-width: 24px;
    border-radius: 4px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QSplitter::handle {{
    background: {BORDER};
    width: 1px;
}}
QListWidget, QTableWidget {{
    background: {FIELD};
    alternate-background-color: #191c20;
    border: 1px solid {BORDER};
    border-radius: 7px;
}}
QHeaderView::section {{
    background: {PANEL};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {BORDER};
    padding: 5px;
}}
QProgressBar {{
    background: {FIELD};
    border: 1px solid {BORDER};
    border-radius: 5px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 4px;
}}
QToolTip {{
    background: {RIBBON_ALT};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
    border-radius: 5px;
    padding: 5px;
}}
QMessageBox {{
    background: {BG};
}}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(FIELD))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(PANEL))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(PANEL))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(SELECTION))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#fff8ea"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(RIBBON_ALT))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(FAINT))
    palette.setColor(QPalette.ColorRole.Link, QColor(BLUE))
    palette.setColor(QPalette.ColorRole.Mid, QColor(BORDER))
    palette.setColor(QPalette.ColorRole.Dark, QColor(CANVAS))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
    app.setFont(QFont(UI_FONT, 9))
