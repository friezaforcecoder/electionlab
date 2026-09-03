APP_QSS = r"""
* {
    font-family: "Segoe UI";
    font-size: 10pt;
    color: #e8edf5;
}
QMainWindow, QWidget#AppRoot, QWidget#Page, QWidget#ScrollContent,
QStackedWidget, QScrollArea, QDialog, QMessageBox {
    background: #0b1017;
}
QLabel { background: transparent; border: none; }
QWidget#InfoLabelHost { background: transparent; }
QFrame#Sidebar {
    background: #0f1722;
    border-right: 1px solid #223044;
}
QLabel#Brand { font-size: 19pt; font-weight: 750; color: #f5f8fc; }
QLabel#Muted { color: #9aa9bd; }
QLabel#Footnote { color: #8e9db1; font-size: 9pt; }
QLabel#PageTitle { font-size: 23pt; font-weight: 750; color: #f7f9fc; }
QLabel#SectionTitle { font-size: 13pt; font-weight: 700; color: #f0f4fa; }
QLabel#FieldLabel { color: #cbd5e1; }
QLabel#MetricLabel { color: #aebbcf; font-size: 9pt; }
QLabel#MetricValue { font-size: 22pt; font-weight: 760; color: #f8fafc; }
QLabel#SmallCaps { color: #8fa3bf; font-size: 8pt; font-weight: 700; letter-spacing: 1px; }

QFrame#Card {
    background: #121b27;
    border: 1px solid #263448;
    border-radius: 12px;
}
QFrame#Card[accent="a"] { border-top: 3px solid #3b82f6; }
QFrame#Card[accent="b"] { border-top: 3px solid #ef4764; }
QFrame#Card[accent="neutral"] { border-top: 3px solid #64748b; }
QFrame#HeroCard {
    background: #111c2a;
    border: 1px solid #2b3b52;
    border-radius: 16px;
}
QFrame#MapFrame {
    background: #0e1723;
    border: 1px solid #293a50;
    border-radius: 12px;
}
QFrame#ActionBar {
    background: #101a27;
    border: 1px solid #2a3b51;
    border-radius: 11px;
}

QPushButton {
    min-height: 18px;
    background: #182536;
    border: 1px solid #31445c;
    border-radius: 8px;
    padding: 8px 13px;
    color: #eaf0f8;
}
QPushButton:hover { background: #213149; border-color: #48617f; }
QPushButton:pressed { background: #111b28; }
QPushButton:focus { border-color: #5f93ff; }
QPushButton:disabled { color: #68778c; background: #111925; border-color: #202d3d; }
QPushButton#Primary {
    background: #397cff;
    border-color: #397cff;
    color: white;
    font-weight: 700;
}
QPushButton#Primary:hover { background: #4b88ff; border-color: #4b88ff; }
QPushButton#Danger { background: #3a1d24; border-color: #6b2a3a; color: #ffb7c3; }
QPushButton#Nav {
    text-align: left;
    border: none;
    border-left: 3px solid transparent;
    background: transparent;
    padding: 10px 12px;
    color: #aeb9c9;
    border-radius: 8px;
}
QPushButton#Nav:hover { background: #172334; color: #f2f6fb; }
QPushButton#Nav[active="true"] {
    background: #1b2c45;
    color: white;
    border-left: 3px solid #4d86ff;
    font-weight: 650;
}
QToolButton#Info {
    background: #1c2d43;
    color: #c7daf8;
    border: 1px solid #45617f;
    border-radius: 9px;
    padding: 0;
    font-size: 8pt;
    font-weight: 800;
}
QToolButton#Info:hover { background: #2b4668; color: white; border-color: #7898c0; }
QToolButton#ToggleChip {
    text-align: left;
    min-height: 22px;
    background: #0e1722;
    color: #bdc9d8;
    border: 1px solid #2b3d53;
    border-radius: 8px;
    padding: 7px 10px;
}
QToolButton#ToggleChip:hover { background: #162437; border-color: #405a78; color: #f4f7fb; }
QToolButton#ToggleChip:checked { background: #17345a; border-color: #3e73b6; color: #ffffff; }

QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    min-height: 18px;
    background: #0d1622;
    border: 1px solid #304158;
    border-radius: 7px;
    padding: 7px 9px;
    color: #edf2f8;
    selection-background-color: #397cff;
}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover { border-color: #405774; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #5b8eff; }
QLineEdit::placeholder { color: #718198; }
QComboBox::drop-down { border: 0; width: 28px; }
QComboBox QAbstractItemView {
    background: #121c29;
    border: 1px solid #34475f;
    selection-background-color: #244774;
    selection-color: #ffffff;
    padding: 4px;
    outline: 0;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button { width: 0; height: 0; border: 0; }

QCheckBox { spacing: 8px; background: transparent; color: #dde5f0; }
QCheckBox:hover { color: #ffffff; }
QCheckBox::indicator { width: 17px; height: 17px; }

QGroupBox {
    background: #0f1824;
    border: 1px solid #2a3a4f;
    border-radius: 10px;
    margin-top: 15px;
    padding-top: 12px;
    font-weight: 650;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    background: #121b27;
    color: #d7e0ed;
}

QTableWidget {
    background: #0d1621;
    alternate-background-color: #111c29;
    border: 1px solid #28384c;
    border-radius: 9px;
    gridline-color: #223145;
    selection-background-color: #24466f;
    selection-color: white;
    outline: 0;
}
QTableWidget::item { padding: 7px; border: none; }
QTableWidget::item:selected { background: #24466f; color: white; }
QHeaderView::section {
    background: #172435;
    color: #c9d3e1;
    border: none;
    border-right: 1px solid #26364b;
    border-bottom: 1px solid #2a3a4f;
    padding: 8px;
    font-weight: 650;
}
QTableCornerButton::section { background: #172435; border: none; }

QListWidget, QListView {
    background: #0d1621;
    border: 1px solid #28384c;
    border-radius: 9px;
    outline: 0;
    padding: 5px;
}
QListWidget::item, QListView::item {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 9px 10px;
    margin: 2px 0;
    color: #dce5f1;
}
QListWidget::item:hover, QListView::item:hover { background: #162438; border-color: #263d5a; }
QListWidget::item:selected, QListView::item:selected {
    background: #1e3b61;
    border-color: #35649a;
    color: #ffffff;
}

QScrollArea { border: none; }
QScrollBar:vertical { background: #0c131d; width: 11px; margin: 0; }
QScrollBar::handle:vertical { background: #33455d; min-height: 32px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #425a78; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #0c131d; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #33455d; min-width: 32px; border-radius: 5px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

QSplitter::handle { background: transparent; }
QSplitter::handle:horizontal { width: 7px; }
QSplitter::handle:horizontal:hover { background: #1c2b3e; }

QProgressBar { border: 1px solid #304158; border-radius: 7px; text-align: center; background: #0d1622; }
QProgressBar::chunk { background: #397cff; border-radius: 6px; }
QTabWidget::pane { border: 1px solid #28384c; border-radius: 8px; }
QTabBar::tab { background: #111b28; padding: 8px 12px; margin-right: 3px; border-radius: 6px; }
QTabBar::tab:selected { background: #263b58; }
QToolTip { background: #172435; color: white; border: 1px solid #3b526e; padding: 7px; }
"""

# 0.4 additions are appended so upgrades remain easy to diff.
APP_QSS += r"""
QLabel#Portrait {
    background: #0d1621;
    border: 1px solid #31445c;
    border-radius: 12px;
    color: #89a3c4;
    font-size: 22pt;
    font-weight: 750;
}
QLabel#DebateQuestion {
    background: #0e1825;
    border: 1px solid #2f4662;
    border-radius: 10px;
    padding: 12px 14px;
    color: #eef4fb;
    font-size: 11pt;
}
QPlainTextEdit {
    background: #0d1622;
    border: 1px solid #304158;
    border-radius: 8px;
    padding: 9px;
    color: #edf2f8;
    selection-background-color: #397cff;
}
QPlainTextEdit:focus { border-color: #5b8eff; }
"""

# 0.5 campaign timeline / major-event takeover additions.
APP_QSS += r"""
QLabel#EventTitle {
    font-size: 28pt;
    font-weight: 800;
    color: #f8fafc;
    padding: 8px;
}
"""

# 0.7 interaction polish: make sortable headers and hover help feel deliberate.
APP_QSS += r"""
QHeaderView::section:hover {
    background: #203149;
    color: #ffffff;
}
QHeaderView::up-arrow, QHeaderView::down-arrow {
    width: 8px;
    height: 8px;
}
QToolTip {
    background: #152235;
    color: #f2f6fb;
    border: 1px solid #46617f;
    padding: 6px 8px;
    font-size: 9pt;
}
"""

# 0.8 responsive-work overlay and real rounded portrait clipping.
APP_QSS += r"""
QFrame#BusyOverlay {
    background: rgba(3, 8, 15, 205);
}
QFrame#BusyPanel {
    background: #121d2a;
    border: 1px solid #38506d;
    border-radius: 16px;
}
QFrame#BusyPanel QProgressBar {
    min-height: 16px;
    border: 1px solid #38506d;
    border-radius: 8px;
    background: #0b1420;
    color: #dce7f5;
}
QFrame#BusyPanel QProgressBar::chunk {
    background: #397cff;
    border-radius: 7px;
}
QLabel#Portrait {
    background: #0b141f;
    border: 1px solid #34485f;
    border-radius: 14px;
}
"""

# 0.11 game-shell transition.
APP_QSS += r"""
QWidget#MainMenu {
    background: #080d14;
}
QFrame#MainMenuPanel {
    background: #101925;
    border: 1px solid #2b3d54;
    border-radius: 22px;
}
QLabel#MenuBrand {
    font-size: 38pt;
    font-weight: 850;
    color: #f8fbff;
}
QLabel#MenuSubtitle {
    color: #83a8db;
    font-size: 9pt;
    font-weight: 700;
    letter-spacing: 1.3px;
}
QLabel#MenuVersion {
    color: #65768d;
    font-size: 8pt;
}
QPushButton#MenuPrimary, QPushButton#MenuButton {
    min-height: 32px;
    padding: 11px 18px;
    border-radius: 10px;
    text-align: center;
    font-size: 11pt;
    font-weight: 650;
}
QPushButton#MenuPrimary {
    background: #397cff;
    border-color: #397cff;
    color: white;
    font-size: 12pt;
    font-weight: 750;
}
QPushButton#MenuPrimary:hover { background: #4d89ff; border-color: #4d89ff; }
QPushButton#MenuUtility {
    min-height: 20px;
    padding: 8px 10px;
    background: #111c29;
    border-color: #283b53;
    color: #b8c7da;
}
QFrame#GameTopBar {
    background: #0e1722;
    border-bottom: 1px solid #26364a;
}
QPushButton#TopBarButton {
    min-height: 16px;
    padding: 6px 10px;
    background: transparent;
    border: 1px solid #2c4059;
    color: #c9d6e6;
}
QPushButton#TopBarButton:hover { background: #17263a; color: white; }
QLabel#ShellTitle {
    font-size: 12pt;
    font-weight: 750;
    color: #f5f8fc;
}
QLabel#RulesBadge {
    background: #14263c;
    color: #bcd4f5;
    border: 1px solid #31567f;
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 9pt;
    font-weight: 700;
}
QLabel#RulesBadge[modified="true"] {
    background: #2b2110;
    color: #ffd38a;
    border-color: #66502b;
}
QCheckBox[ruleFuture="true"] { color: #69798e; }
"""
