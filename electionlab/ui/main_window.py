from __future__ import annotations

import copy
import html
import json
import math
import os
import random
import string
import traceback
import time
from datetime import datetime, date
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal, QSize, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMainWindow, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QDoubleSpinBox, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
    QHeaderView, QAbstractItemView, QGroupBox, QSplitter, QSizePolicy, QPlainTextEdit, QProgressBar
)

from electionlab.core.campaigns import CampaignManager
from electionlab.core.campaign_engine import CampaignEngine, REGIONS, MESSAGES, TONES, CAMPAIGN_OPERATION_SPECS
from electionlab.core.database import KnowledgeVault
from electionlab.core.diagnostics import SessionDiagnostics
from electionlab.core.extensions import ExtensionManager
from electionlab.core.settings import SettingsManager
from electionlab.core.simulation import ElectionEngine, SimulationConfig
from electionlab.core.simulation_archive import SimulationArchive
from electionlab.core.rules import RULE_PRESETS, RULE_CONTROLS, preset_rules, modified_from_preset, campaign_rules, enabled as rule_enabled
from electionlab.providers.openai_provider import OpenAIResearchProvider, clear_api_key, load_api_key, save_api_key
from electionlab.providers.profile_service import ProfileService
from electionlab.providers.photo_service import PhotoService
from electionlab.providers.debate_service import DebateService
from electionlab.providers.ollama_provider import OllamaProvider
from electionlab.version import BUILD_LABEL
from .widgets import BusyOverlay, Card, ElectoralGrid, ElectoralScoreBar, InfoButton, InfoLabel, MetricCard, RoundedPortraitLabel, ToggleChip, nav_icon


MODES = ["Arcade", "Analytical 1", "Analytical 2", "Forecast Lab"]
PARTIES = ["Democratic", "Republican", "Independent", "Libertarian", "Green", "Custom"]
DETAIL_LEVELS = ["Instant Election", "Highlights", "Debate-to-Debate", "Monthly", "Weekly", "Daily", "Custom"]
AGENCY_LEVELS = ["Play Ticket A", "Play Ticket B", "Control Both", "Spectate"]


def make_seed() -> str:
    return "CAMPAIGN-" + "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(7))


def page_shell(title: str, subtitle: str = ""):
    outer = QWidget()
    outer.setObjectName("Page")
    v = QVBoxLayout(outer)
    v.setContentsMargins(26, 22, 26, 24)
    v.setSpacing(14)
    t = QLabel(title)
    t.setObjectName("PageTitle")
    v.addWidget(t)
    if subtitle:
        st = QLabel(subtitle)
        st.setObjectName("Muted")
        st.setWordWrap(True)
        v.addWidget(st)
    return outer, v


class ResearchThread(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.done.emit(self.fn())
        except Exception as exc:
            self.failed.emit(str(exc))


class ProgressThread(QThread):
    done = Signal(object)
    failed = Signal(str)
    progress = Signal(int, str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            def report(percent: int, message: str = ""):
                self.progress.emit(int(percent), str(message))
            self.done.emit(self.fn(report))
        except Exception as exc:
            self.failed.emit(str(exc))


class BatchPortraitThread(QThread):
    progress = Signal(int, int, str)
    done = Signal(object)

    def __init__(self, names, service, parent=None):
        super().__init__(parent)
        self.names = list(names)
        self.service = service

    def run(self):
        ok=[]; failed=[]; total=len(self.names)
        for i,name in enumerate(self.names,1):
            self.progress.emit(i,total,name)
            try:
                self.service.fetch_and_cache(name)
                ok.append(name)
            except Exception as exc:
                failed.append((name,str(exc)))
        self.done.emit({"ok":ok,"failed":failed,"total":total})


class SortableTableItem(QTableWidgetItem):
    """Table item with an explicit sort key while preserving formatted display text."""

    def __init__(self, text: str, sort_value=None):
        super().__init__(str(text))
        self.sort_value = sort_value if sort_value is not None else str(text).lower()

    def __lt__(self, other):
        if isinstance(other, SortableTableItem):
            try:
                return self.sort_value < other.sort_value
            except TypeError:
                return str(self.sort_value) < str(other.sort_value)
        return super().__lt__(other)


class CustomProfileDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create Custom Candidate")
        self.setMinimumWidth(430)
        form = QFormLayout(self)
        self.name = QLineEdit()
        self.party = QComboBox(); self.party.addItems(PARTIES)
        self.state = QLineEdit(); self.state.setMaxLength(2); self.state.setPlaceholderText("MO")
        self.career = QLineEdit()
        self.appeal = QDoubleSpinBox(); self.appeal.setRange(-8, 8); self.appeal.setSingleStep(.5)
        self.charisma = QSpinBox(); self.charisma.setRange(0,100); self.charisma.setValue(50)
        self.debate = QSpinBox(); self.debate.setRange(0,100); self.debate.setValue(50)
        self.experience = QSpinBox(); self.experience.setRange(0,100); self.experience.setValue(50)
        self.recognition = QSpinBox(); self.recognition.setRange(0,100); self.recognition.setValue(25)
        form.addRow("Name", self.name); form.addRow("Party", self.party); form.addRow("Home state", self.state)
        form.addRow("Career / background", self.career); form.addRow("National appeal (-8…8)", self.appeal)
        form.addRow("Charisma (game input)", self.charisma); form.addRow("Debate ability", self.debate)
        form.addRow("Experience", self.experience); form.addRow("Name recognition", self.recognition)
        note = QLabel("These scores are simulation inputs, not objective judgments. You can create fictional people here.")
        note.setWordWrap(True); note.setObjectName("Muted"); form.addRow(note)
        box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        box.accepted.connect(self.accept); box.rejected.connect(self.reject); form.addRow(box)

    def profile(self):
        return {
            "canonical_name": self.name.text().strip(), "profile_type": "custom", "source_type": "user_created",
            "party": self.party.currentText(), "home_state": self.state.text().upper().strip() or None,
            "career": self.career.text().strip() or None, "national_appeal": self.appeal.value(),
            "charisma": self.charisma.value(), "debate_skill": self.debate.value(), "experience": self.experience.value(),
            "name_recognition": self.recognition.value(), "known_positions": {}, "inferred_positions": {},
            "confidence": 1.0, "profile_status": "custom", "snapshot_date": datetime.now().date().isoformat(),
        }


class MainWindow(QMainWindow):
    def __init__(self, settings: SettingsManager, vault: KnowledgeVault, diagnostics: SessionDiagnostics):
        super().__init__()
        self.settings = settings
        self.vault = vault
        self.diagnostics = diagnostics
        self.profile_service = ProfileService(settings, vault, diagnostics)
        self.photo_service = PhotoService(settings, vault)
        self.debate_service = DebateService(settings, vault)
        self.engine = ElectionEngine()
        self.simulation_archive = SimulationArchive(settings)
        self.campaigns = CampaignManager(settings)
        self.campaign_engine = CampaignEngine()
        self.extensions = ExtensionManager(settings)
        self.last_result = None
        self._research_thread = None
        self._simulation_thread = None
        self._campaign_election_thread = None
        self._campaign_create_thread = None
        self._interaction_thread = None
        self.active_campaign_id = None
        self._active_campaign_obj = None
        self._active_debate_question = None
        self._debate_campaign_id = None
        self._interaction_campaign_id = None
        self._pending_advisor_message = None
        self._pending_conversation_role = None
        self._interaction_kind = None
        self._photo_threads = []
        self._portrait_fetching = set()
        self._portrait_failed_names = set()
        self._batch_photo_thread = None
        self._history_thread = None
        self._provider_test_thread = None
        self._history_threads = []
        self._history_campaign_id = None
        self._history_turn_number = None
        self._manual_history_request = None
        self._hq_selected_state_code = None
        self._hq_refresh_pending = False
        self._hq_dirty = True

        self.setWindowTitle("ElectionLab — Political Simulation Sandbox")
        self.resize(1440, 900)
        self.setMinimumSize(1120, 720)
        with self.diagnostics.span("MAINWINDOW_BUILD_UI"):
            self._build_ui()
        self._ui_watchdog = QTimer(self)
        self._ui_watchdog.setInterval(250)
        self._ui_watchdog.timeout.connect(self.diagnostics.ui_heartbeat)
        self._ui_watchdog.start()
        with self.diagnostics.span("INITIAL_REFRESHES"):
            self.refresh_profiles()
            self.refresh_campaigns()
            self.refresh_dashboard()
            self.refresh_data_page()
        self.diagnostics.set_ui_action("idle")

    def _build_ui(self):
        # 0.11 introduces a traditional game shell. The existing feature pages are
        # retained as internal screens so no simulation/campaign work is thrown
        # away, but the user now enters them from a main menu rather than a global
        # desktop-utility sidebar.
        root = QWidget(); root.setObjectName("AppRoot"); self.setCentralWidget(root)
        outer = QVBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        self.root_stack = QStackedWidget(); outer.addWidget(self.root_stack, 1)

        self.main_menu = self._main_menu_page()
        self.root_stack.addWidget(self.main_menu)

        shell = QWidget(); shell.setObjectName("GameShell")
        shell_v = QVBoxLayout(shell); shell_v.setContentsMargins(0,0,0,0); shell_v.setSpacing(0)
        topbar = QFrame(); topbar.setObjectName("GameTopBar")
        tr = QHBoxLayout(topbar); tr.setContentsMargins(16,10,18,10); tr.setSpacing(10)
        menu_btn = QPushButton("←  Main Menu"); menu_btn.setObjectName("TopBarButton"); menu_btn.clicked.connect(self._open_main_menu); tr.addWidget(menu_btn)
        self.shell_title = QLabel("ElectionLab"); self.shell_title.setObjectName("ShellTitle"); tr.addWidget(self.shell_title)
        tr.addStretch(1)
        self.shell_context = QLabel(""); self.shell_context.setObjectName("Muted"); tr.addWidget(self.shell_context)
        shell_v.addWidget(topbar)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._dashboard_page())      # legacy/internal index 0; go(0) returns to menu
        self.stack.addWidget(self._simulation_page())     # Quick Election
        self.stack.addWidget(self._campaign_page())       # New Game / Save Library
        self.stack.addWidget(self._campaign_hq_page())    # Campaign gameplay
        self.stack.addWidget(self._vault_page())          # utility
        self.stack.addWidget(self._data_page())           # utility
        self.stack.addWidget(self._settings_page())       # utility
        shell_v.addWidget(self.stack, 1)
        self.root_stack.addWidget(shell)
        self.app_shell = shell
        self.nav_buttons = []  # compatibility with older refresh helpers

        self.busy_overlay = BusyOverlay(root)
        self.busy_overlay.setGeometry(root.rect())
        self.busy_overlay.raise_()
        self.root_stack.setCurrentIndex(0)
        self._update_offline_badge()
        self.refresh_main_menu()

    def _main_menu_page(self):
        page = QWidget(); page.setObjectName("MainMenu")
        base = QVBoxLayout(page); base.setContentsMargins(54,42,54,38); base.setSpacing(14)
        base.addStretch(1)
        center = QHBoxLayout(); center.addStretch(1)
        panel = QFrame(); panel.setObjectName("MainMenuPanel"); panel.setMaximumWidth(760); panel.setMinimumWidth(580)
        pv = QVBoxLayout(panel); pv.setContentsMargins(44,38,44,36); pv.setSpacing(12)
        brand = QLabel("ElectionLab"); brand.setObjectName("MenuBrand"); brand.setAlignment(Qt.AlignCenter); pv.addWidget(brand)
        subtitle = QLabel("THE AMERICAN EXPERIMENT · LOCAL-FIRST ELECTION SANDBOX"); subtitle.setObjectName("MenuSubtitle"); subtitle.setAlignment(Qt.AlignCenter); pv.addWidget(subtitle)
        desc = QLabel("Build a campaign, test an election matchup, or inspect the data behind the model.")
        desc.setObjectName("Muted"); desc.setAlignment(Qt.AlignCenter); desc.setWordWrap(True); pv.addWidget(desc)
        pv.addSpacing(12)

        self.menu_continue_btn = QPushButton("Continue Campaign"); self.menu_continue_btn.setObjectName("MenuPrimary"); self.menu_continue_btn.clicked.connect(self._continue_latest_campaign); pv.addWidget(self.menu_continue_btn)
        new_btn = QPushButton("New Game"); new_btn.setObjectName("MenuButton"); new_btn.clicked.connect(lambda:self.go(2)); pv.addWidget(new_btn)
        load_btn = QPushButton("Load / Manage Campaigns"); load_btn.setObjectName("MenuButton"); load_btn.clicked.connect(lambda:self.go(2)); pv.addWidget(load_btn)
        quick_btn = QPushButton("Quick Election"); quick_btn.setObjectName("MenuButton"); quick_btn.clicked.connect(lambda:self.go(1)); pv.addWidget(quick_btn)

        utilities = QHBoxLayout(); utilities.setSpacing(8)
        for text, idx in [("Knowledge Vault",4),("Data && Sources",5),("Settings",6)]:
            b=QPushButton(text); b.setObjectName("MenuUtility"); b.clicked.connect(lambda _=False,i=idx:self.go(i)); utilities.addWidget(b)
        exit_btn=QPushButton("Exit"); exit_btn.setObjectName("MenuUtility"); exit_btn.clicked.connect(QApplication.quit); utilities.addWidget(exit_btn)
        pv.addLayout(utilities)
        pv.addSpacing(8)
        self.menu_status = QLabel(""); self.menu_status.setObjectName("Muted"); self.menu_status.setAlignment(Qt.AlignCenter); self.menu_status.setWordWrap(True); pv.addWidget(self.menu_status)
        self.menu_version = QLabel(BUILD_LABEL); self.menu_version.setObjectName("MenuVersion"); self.menu_version.setAlignment(Qt.AlignCenter); pv.addWidget(self.menu_version)
        center.addWidget(panel); center.addStretch(1); base.addLayout(center)
        base.addStretch(1)
        return page

    def refresh_main_menu(self):
        if not hasattr(self, "menu_continue_btn"):
            return
        camps = self.campaigns.list()
        active = self._campaign_by_id(self.active_campaign_id) if self.active_campaign_id else None
        target = active or (camps[0] if camps else None)
        self.menu_continue_btn.setEnabled(bool(target))
        if target:
            self.menu_continue_btn.setText(f"Continue · {target.get('title','Campaign')}")
            self.menu_status.setText(f"Last campaign: {target.get('current_date','—')} · {target.get('branch_label','Main Timeline')} · seed {target.get('seed','—')}")
        else:
            self.menu_continue_btn.setText("Continue Campaign")
            self.menu_status.setText("No campaign saves yet. Start a New Game or run a Quick Election.")

    def _open_main_menu(self):
        self.diagnostics.set_ui_action("MAIN_MENU")
        if hasattr(self, "busy_overlay"):
            self.busy_overlay.finish()
        self.refresh_main_menu()
        self.root_stack.setCurrentIndex(0)
        self.diagnostics.log("INFO", "MAIN_MENU_OPENED")
        QTimer.singleShot(500, self.diagnostics.clear_ui_action)

    def _continue_latest_campaign(self):
        c = self._campaign_by_id(self.active_campaign_id) if self.active_campaign_id else None
        if not c:
            saves = self.campaigns.list(); c = saves[0] if saves else None
        if not c:
            return
        self.active_campaign_id = c.get("id"); self._active_campaign_obj = c
        self.go(3)

    def resizeEvent(self,event):
        if hasattr(self,"busy_overlay") and self.centralWidget():
            self.busy_overlay.setGeometry(self.centralWidget().rect())
            if self.busy_overlay.isVisible():self.busy_overlay.raise_()
        super().resizeEvent(event)

    def go(self, idx: int):
        if idx == 0:
            self._open_main_menu(); return
        labels={1:"quick_election",2:"new_game",3:"campaign",4:"vault",5:"data",6:"settings"}
        titles={1:"Quick Election",2:"New Game & Saves",3:"Campaign",4:"Knowledge Vault",5:"Data & Sources",6:"Settings"}
        label=labels.get(idx,str(idx)); action=f"NAVIGATE:{label}"
        self.diagnostics.set_ui_action(action); started=time.perf_counter()
        self.root_stack.setCurrentIndex(1); self.stack.setCurrentIndex(idx)
        if hasattr(self,"shell_title"): self.shell_title.setText(titles.get(idx,"ElectionLab"))
        if hasattr(self,"shell_context"):
            if idx == 3:
                c=self._campaign_by_id(self.active_campaign_id)
                self.shell_context.setText(f"{c.get('title','Campaign')} · {c.get('rules_preset','Campaign')}" if c else "No campaign loaded")
            else:
                self.shell_context.setText("OFFLINE LOCK" if self.settings.settings.offline_lock else "")
        if idx == 3 and hasattr(self,"busy_overlay"):
            self.busy_overlay.begin("Opening Campaign","Loading campaign state, map, polling and timeline…",None)
        def finish_nav():
            try:
                if idx == 2: self.refresh_campaigns()
                if idx == 3: self.refresh_campaign_hq()
                if idx == 4: self.refresh_vault_table()
                if idx == 5: self.refresh_data_page()
                if idx == 6: self._update_provider_status()
            finally:
                if idx == 3 and hasattr(self,"busy_overlay"): self.busy_overlay.finish()
                self.diagnostics.log("INFO","NAVIGATION_COMPLETE",page=label,duration_ms=round((time.perf_counter()-started)*1000,1))
                QTimer.singleShot(850,lambda:self.diagnostics.clear_ui_action(action))
        QTimer.singleShot(0, finish_nav)

    def _dashboard_page(self):
        page, v = page_shell(
            "Dashboard",
            "Your launchpad: continue a campaign, check data/provider readiness, or jump straight into a simulation.",
        )

        hero = Card(hero=True)
        hv = QHBoxLayout(); hv.setSpacing(18); hero.layout.addLayout(hv)
        intro = QVBoxLayout(); intro.setSpacing(9)
        headline = QLabel("ElectionLab Command Center"); headline.setStyleSheet("font-size:24pt;font-weight:750;")
        body = QLabel("Campaign strategy, live state movement, election modeling, candidate data and AI-assisted interactions all meet here.")
        body.setWordWrap(True); body.setObjectName("Muted")
        quick = QHBoxLayout(); quick.setSpacing(8)
        sim = QPushButton("Simulate Election"); sim.setObjectName("Primary"); sim.clicked.connect(lambda:self.go(1)); quick.addWidget(sim)
        campaigns = QPushButton("Campaign Library"); campaigns.clicked.connect(lambda:self.go(2)); quick.addWidget(campaigns)
        self.dash_continue_btn = QPushButton("Continue Active Campaign"); self.dash_continue_btn.clicked.connect(lambda:self.go(3)); quick.addWidget(self.dash_continue_btn)
        quick.addStretch(1)
        intro.addWidget(headline); intro.addWidget(body); intro.addLayout(quick)
        hv.addLayout(intro, 4)
        self.dash_status = QLabel(); self.dash_status.setAlignment(Qt.AlignCenter); self.dash_status.setWordWrap(True); self.dash_status.setStyleSheet("font-size:11pt;font-weight:650;")
        hv.addWidget(self.dash_status, 1)
        v.addWidget(hero)

        metrics = QHBoxLayout(); metrics.setSpacing(10)
        self.metric_profiles = MetricCard("Knowledge Vault")
        self.metric_portraits = MetricCard("Portrait coverage")
        self.metric_campaigns = MetricCard("Saved campaigns")
        self.metric_state_data = MetricCard("State data")
        for m in [self.metric_profiles,self.metric_portraits,self.metric_campaigns,self.metric_state_data]: metrics.addWidget(m)
        v.addLayout(metrics)

        row = QHBoxLayout(); row.setSpacing(12)
        active = Card("Active campaign", info_text="Shows the currently opened campaign, its next milestone and the strongest modeled state movement.")
        self.dash_active_campaign = QLabel("No campaign is active."); self.dash_active_campaign.setWordWrap(True); self.dash_active_campaign.setAlignment(Qt.AlignTop|Qt.AlignLeft); active.layout.addWidget(self.dash_active_campaign)
        row.addWidget(active, 3)

        readiness = Card("System readiness", info_text="A quick check of the optional AI providers and the local data ElectionLab can use right now.")
        self.dash_readiness = QLabel(); self.dash_readiness.setWordWrap(True); self.dash_readiness.setAlignment(Qt.AlignTop|Qt.AlignLeft); readiness.layout.addWidget(self.dash_readiness)
        data_btn = QPushButton("Open Data Workspace"); data_btn.clicked.connect(lambda:self.go(5)); readiness.layout.addWidget(data_btn,0,Qt.AlignLeft)
        row.addWidget(readiness, 2)
        v.addLayout(row)

        recent_row=QHBoxLayout(); recent_row.setSpacing(12)
        recent = Card("Recent campaign saves")
        self.dash_recent_campaigns = QListWidget(); self.dash_recent_campaigns.setMaximumHeight(190); self.dash_recent_campaigns.itemDoubleClicked.connect(self._dashboard_open_campaign)
        recent.layout.addWidget(self.dash_recent_campaigns)
        hint=QLabel("Double-click a save to continue it in Campaign HQ."); hint.setObjectName("Muted"); recent.layout.addWidget(hint)
        recent_row.addWidget(recent,1)
        saved=Card("Saved election results", info_text="Results you explicitly save from the simulation screen live in the portable Simulation Archive under your selected ElectionLab data folder.")
        self.dash_recent_sims=QListWidget(); self.dash_recent_sims.setMaximumHeight(190); self.dash_recent_sims.itemDoubleClicked.connect(self._dashboard_open_simulation); saved.layout.addWidget(self.dash_recent_sims)
        sim_actions=QHBoxLayout(); shint=QLabel("Double-click a result to reopen its full map and analysis."); shint.setObjectName("Muted"); sim_actions.addWidget(shint,1); self.dash_delete_sim_btn=QPushButton("Delete Selected"); self.dash_delete_sim_btn.setObjectName("Danger"); self.dash_delete_sim_btn.clicked.connect(self._dashboard_delete_simulation); sim_actions.addWidget(self.dash_delete_sim_btn); saved.layout.addLayout(sim_actions)
        recent_row.addWidget(saved,1)
        v.addLayout(recent_row)
        v.addStretch(1)
        return page

    def _dashboard_open_campaign(self, item):
        c=item.data(Qt.UserRole) if item else None
        if not c:return
        self.active_campaign_id=c.get("id")
        self._active_campaign_obj=c
        self.go(3)

    def _dashboard_open_simulation(self,item):
        payload=item.data(Qt.UserRole) if item else None
        result=(payload or {}).get("result") if isinstance(payload,dict) else None
        if not result:return
        self.last_result=result
        self.show_results(result)
        self.go(1)

    def _dashboard_delete_simulation(self):
        item=self.dash_recent_sims.currentItem() if hasattr(self,"dash_recent_sims") else None
        payload=item.data(Qt.UserRole) if item else None
        if not payload:return
        if QMessageBox.question(self,"Delete Saved Result",f"Delete saved simulation '{payload.get('title','simulation')}'?",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:return
        self.simulation_archive.delete(payload); self.refresh_dashboard()

    @staticmethod
    def _initials(name: str) -> str:
        parts = [p for p in name.replace("-", " ").split() if p]
        if not parts:
            return "?"
        return "".join(p[0].upper() for p in parts[:2])

    def _portrait_label(self, size: int = 104) -> QLabel:
        label = RoundedPortraitLabel("?")
        label.setObjectName("Portrait")
        label.setAlignment(Qt.AlignCenter)
        label.setFixedSize(size, size)
        label.setScaledContents(False)
        return label

    @staticmethod
    def _portrait_cover(pix: QPixmap, size: QSize) -> QPixmap:
        """Fill a portrait box while biasing vertical crop upward toward the face.

        KeepAspectRatio left visible letterboxing; a normal center crop cut too much off some
        headshots. The upper-center crop is a simple no-ML compromise that fills the frame while
        retaining more head/shoulder area for typical public portraits.
        """
        if pix.isNull() or size.width() <= 0 or size.height() <= 0:
            return pix
        scaled = pix.scaled(size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        x = max(0, (scaled.width() - size.width()) // 2)
        excess_y = max(0, scaled.height() - size.height())
        y = int(excess_y * 0.28)  # upper bias: preserve faces instead of dead center/body crop
        return scaled.copy(x, y, size.width(), size.height())

    def _set_portrait(self, label: QLabel, name: str) -> None:
        clean = (name or "").strip()
        label.setPixmap(QPixmap())
        if not clean:
            label.setText("?")
            label.setToolTip("No candidate selected.")
            return
        p = self.vault.get_profile(clean)
        photo_path = (p or {}).get("photo_path")
        if photo_path and Path(photo_path).exists():
            pix = QPixmap(photo_path)
            if not pix.isNull():
                label.setText("")
                label.setPixmap(self._portrait_cover(pix, label.size()))
                label.setToolTip(f"Cached portrait for {clean}. ElectionLab uses a face-biased fill crop; the original file remains unchanged.")
                return
        label.setText(self._initials(clean))
        label.setToolTip("Portrait is not cached yet. Use Knowledge Vault → Fetch Portrait while online.")

    def _queue_portrait_if_missing(self, name: str, label: QLabel | None = None) -> None:
        clean=(name or "").strip()
        if not clean or clean in self._portrait_fetching or clean in self._portrait_failed_names:
            return
        p=self.vault.get_profile(clean)
        if not p or (p.get("photo_path") and Path(p.get("photo_path")).exists()):
            if label:self._set_portrait(label,clean)
            return
        st=self.settings.settings
        if st.offline_lock or not st.internet_research:
            return
        self._portrait_fetching.add(clean)
        thread=ResearchThread(lambda:self.photo_service.fetch_and_cache(clean),self)
        self._photo_threads.append(thread)
        thread.done.connect(lambda _path,n=clean,l=label,t=thread:self._auto_portrait_done(n,l,t))
        thread.failed.connect(lambda _msg,n=clean,t=thread:self._auto_portrait_failed(n,t))
        thread.start()

    def _auto_portrait_done(self,name,label,thread):
        self._portrait_fetching.discard(name)
        if thread in self._photo_threads:self._photo_threads.remove(thread)
        if label:self._set_portrait(label,name)
        if hasattr(self,"profile_photo"):
            p=self._selected_vault_profile() if hasattr(self,"vault_table") else None
            if p and p.get("canonical_name")==name:self._set_portrait(self.profile_photo,name)
        if hasattr(self,"hq_summary") and self.active_campaign_id:self.refresh_campaign_hq()

    def _auto_portrait_failed(self,name,thread):
        self.diagnostics.log("WARNING","AUTO_PORTRAIT_FAILED",name=name)
        self._portrait_fetching.discard(name); self._portrait_failed_names.add(name)
        if thread in self._photo_threads:self._photo_threads.remove(thread)

    def _candidate_combo(self, placeholder: str, optional: bool = False):
        combo = QComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(QComboBox.NoInsert)
        combo.setMinimumWidth(190)
        if combo.lineEdit():
            combo.lineEdit().setPlaceholderText(placeholder)
            combo.lineEdit().setClearButtonEnabled(True)
        combo.setToolTip("Choose a saved Knowledge Vault profile or type a new name. Missing names can be researched/cached when online research is enabled.")
        combo.setProperty("candidateOptional", optional)
        return combo

    def _ticket_selector(self, title: str, accent: str):
        card = Card(title, accent=accent)
        body = QHBoxLayout(); body.setSpacing(14); card.layout.addLayout(body)
        portraits = QHBoxLayout(); portraits.setSpacing(7)
        pslot=QVBoxLayout(); pslot.setSpacing(3)
        portrait = self._portrait_label(96); setattr(self, f"_ticket_portrait_{accent}", portrait); pslot.addWidget(portrait, 0, Qt.AlignHCenter)
        plab=QLabel("PRES"); plab.setObjectName("SmallCaps"); plab.setAlignment(Qt.AlignCenter); pslot.addWidget(plab)
        vslot=QVBoxLayout(); vslot.setSpacing(3)
        vp_portrait = self._portrait_label(78); setattr(self, f"_ticket_vp_portrait_{accent}", vp_portrait); vp_portrait.setToolTip("Vice-presidential candidate portrait"); vslot.addWidget(vp_portrait, 0, Qt.AlignHCenter)
        vlab=QLabel("VP"); vlab.setObjectName("SmallCaps"); vlab.setAlignment(Qt.AlignCenter); vslot.addWidget(vlab)
        portraits.addLayout(pslot); portraits.addLayout(vslot)
        body.addLayout(portraits)
        form = QFormLayout()
        form.setContentsMargins(0, 2, 0, 0)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(10)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        body.addLayout(form, 1)
        pres = self._candidate_combo("Select or type a presidential candidate…")
        vp = self._candidate_combo("Optional vice-presidential candidate…", optional=True)
        party = QComboBox(); party.addItems(PARTIES)
        pres.currentTextChanged.connect(lambda text, lab=portrait: self._set_portrait(lab, text))
        pres.activated.connect(lambda _idx, combo=pres, lab=portrait: self._queue_portrait_if_missing(combo.currentText(), lab))
        vp.currentTextChanged.connect(lambda text, lab=vp_portrait: self._set_portrait(lab, text))
        vp.activated.connect(lambda _idx, combo=vp, lab=vp_portrait: self._queue_portrait_if_missing(combo.currentText(), lab))
        form.addRow("President", pres)
        form.addRow("Vice president", vp)
        form.addRow("Ticket party", party)
        return card, pres, vp, party

    def _simulation_page(self):
        page, v = page_shell("Simulate Election", "Build two tickets, choose how analytical the model should be, and run a reproducible Electoral College simulation. Hover or click the circled i icons whenever a term is unfamiliar.")
        scroll = QScrollArea(); scroll.setWidgetResizable(True); inner = QWidget(); inner.setObjectName("ScrollContent"); iv=QVBoxLayout(inner); iv.setContentsMargins(0,0,4,8); iv.setSpacing(14)
        tickets=QHBoxLayout(); ca,self.sim_a,self.sim_avp,self.sim_aparty=self._ticket_selector("Ticket A", "a"); cb,self.sim_b,self.sim_bvp,self.sim_bparty=self._ticket_selector("Ticket B", "b")
        self.sim_aparty.setCurrentText("Democratic"); self.sim_bparty.setCurrentText("Republican")
        tickets.addWidget(ca); tickets.addWidget(cb); iv.addLayout(tickets)

        setup = Card("Simulation setup", info_text="These controls change how the election model behaves. They do not change the saved candidate profiles themselves."); grid=QGridLayout(); grid.setHorizontalSpacing(14); grid.setVerticalSpacing(10); setup.layout.addLayout(grid)
        self.sim_mode=QComboBox(); self.sim_mode.addItems(MODES); self.sim_mode.setCurrentText(self.settings.settings.default_mode)
        self.sim_mode.setToolTip("Arcade is intentionally game-like. Analytical 1 and 2 progressively tighten assumptions. Forecast Lab emphasizes uncertainty and model transparency.")
        self.sim_runs=QSpinBox(); self.sim_runs.setRange(100,50000); self.sim_runs.setSingleStep(500); self.sim_runs.setValue(self.settings.settings.monte_carlo_runs)
        self.sim_runs.setToolTip("The number of alternate election universes sampled. More runs make probability estimates steadier, but take longer.")
        self.sim_seed=QLineEdit(make_seed()); seed_btn=QPushButton("New seed"); seed_btn.clicked.connect(lambda:self.sim_seed.setText(make_seed()))
        seedrow=QHBoxLayout(); seedrow.addWidget(self.sim_seed); seedrow.addWidget(seed_btn)
        self.sim_environment=QDoubleSpinBox(); self.sim_environment.setRange(-15,15); self.sim_environment.setDecimals(1); self.sim_environment.setSingleStep(.5); self.sim_environment.setSuffix(" pts toward A")
        self.sim_environment.setToolTip("A broad national shift applied to the race. Positive values favor Ticket A; negative values favor Ticket B.")
        grid.addWidget(InfoLabel("Mode", "Arcade emphasizes fun and larger candidate/event effects. Analytical 1 and 2 progressively rely more on election fundamentals. Forecast Lab is the strictest and most transparent mode."),0,0);grid.addWidget(self.sim_mode,0,1)
        grid.addWidget(InfoLabel("Monte Carlo runs", "Instead of predicting one exact result, ElectionLab runs the election many times with uncertainty. The share of runs a ticket wins becomes its modeled win probability."),0,2);grid.addWidget(self.sim_runs,0,3)
        grid.addWidget(InfoLabel("Seed", "The seed controls pseudo-randomness. Using the same seed with the same candidates and settings reproduces the same simulated universe."),1,0);grid.addLayout(seedrow,1,1)
        grid.addWidget(InfoLabel("National environment", "A manual national-level advantage measured in percentage points. +2 toward A means the overall environment is shifted about two points toward Ticket A before state-specific effects."),1,2);grid.addWidget(self.sim_environment,1,3)
        iv.addWidget(setup)

        factors=Card("What should the model consider?", info_text="Turn model ingredients on or off for experiments. Disabled factors contribute nothing to this run.")
        fg=QGridLayout(); factors.layout.addLayout(fg); self.factor_checks={}
        implemented=[
            ("historical_baseline","Historical state baseline"),("candidate_personality","Candidate personality/appeal"),("debates","Debate ability"),
            ("experience","Experience"),("name_recognition","Name recognition"),("home_state","Home/VP state effect"),("random_uncertainty","Uncertainty/randomness")
        ]
        factor_help={
            "historical_baseline":"Starts each state from its recent partisan/election baseline before candidate-specific effects are applied.",
            "candidate_personality":"Uses the structured appeal/personality inputs in each candidate profile. These are simulation inputs, not objective judgments.",
            "debates":"Lets the profile's debate-skill input affect the modeled race.",
            "experience":"Lets political/governing experience influence the modeled ticket effect.",
            "name_recognition":"Accounts for how familiar the electorate is modeled to be with the candidates.",
            "home_state":"Adds a limited home-state/regional effect for presidential and vice-presidential candidates.",
            "random_uncertainty":"Allows plausible variation around the model instead of treating its point estimate as certain.",
        }
        for i,(key,label) in enumerate(implemented):
            host=QWidget(); host.setObjectName("InfoLabelHost"); hr=QHBoxLayout(host); hr.setContentsMargins(0,0,0,0); hr.setSpacing(4)
            ch=ToggleChip(label, True); ch.setToolTip(factor_help[key]); self.factor_checks[key]=ch
            hr.addWidget(ch); hr.addWidget(InfoButton(label,factor_help[key])); hr.addStretch(1); fg.addWidget(host,i//3,i%3)
        reserved=QLabel("Coming before 1.0: live polling, demographics, economic conditions, current events, endorsements, fundraising and issue-salience modules. Until a module is actually implemented, ElectionLab does not silently fabricate it.")
        reserved.setWordWrap(True); reserved.setObjectName("Footnote"); factors.layout.addWidget(reserved); iv.addWidget(factors)

        action=QFrame(); action.setObjectName("ActionBar"); action.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed); action.setMaximumHeight(62); runrow=QHBoxLayout(action); runrow.setContentsMargins(14,10,12,10); self.run_status=QLabel("Ready to simulate."); self.run_status.setObjectName("Muted"); runrow.addWidget(self.run_status); runrow.addStretch(1)
        self.run_btn=QPushButton("Run Election"); self.run_btn.setObjectName("Primary"); self.run_btn.setMinimumWidth(150); self.run_btn.clicked.connect(self.run_simulation); runrow.addWidget(self.run_btn); iv.addWidget(action)

        self.results_card=Card("Results", info_text="Results summarize many simulated elections. They are model output, not a real poll or a statement about how anyone should vote."); self.results_card.setVisible(False)
        metrics=QHBoxLayout(); metrics.setSpacing(10)
        self.res_a=MetricCard("Ticket A electoral votes", info_text="EV means electoral votes. There are 538 total; a candidate normally needs at least 270 to win the presidency.")
        self.res_b=MetricCard("Ticket B electoral votes", info_text="EV means electoral votes. There are 538 total; a candidate normally needs at least 270 to win the presidency.")
        self.res_prob=MetricCard("Presidency win probability", info_text="The percentage of Monte Carlo runs in which each ticket wins the presidency. It is a probability generated by this model, not a poll percentage.")
        self.res_pop=MetricCard("Modeled popular-vote margin", info_text="The model's estimated nationwide popular-vote margin in percentage points. This is not an observed vote total or a real poll.")
        for m in [self.res_a,self.res_b,self.res_prob,self.res_pop]: metrics.addWidget(m,1)
        self.results_card.layout.addLayout(metrics)
        self.ev_score=ElectoralScoreBar(); self.results_card.layout.addWidget(self.ev_score)

        insight_row=QHBoxLayout(); insight_row.setSpacing(10)
        self.insight_tipping=MetricCard("Tipping-point state", info_text="On the model's average state map, this is the state that carries the projected winner across 270 electoral votes when states are ordered from safest to closest.")
        self.insight_closest=MetricCard("Closest state", info_text="The state with the smallest average modeled margin in this simulation.")
        self.insight_battlegrounds=MetricCard("Battlegrounds", info_text="States where the average modeled margin is within five percentage points.")
        self.insight_departure=MetricCard("Largest baseline departure", info_text="The state whose modeled result moved furthest from its baseline component after candidate, national, home-state and campaign factors were applied.")
        for card in [self.insight_tipping,self.insight_closest,self.insight_battlegrounds,self.insight_departure]: insight_row.addWidget(card)
        self.results_card.layout.addLayout(insight_row)
        overview=Card("Election overview", info_text="ElectionLab always creates a deterministic local recap from the numerical result. Generate AI Overview optionally asks your selected provider to explain that already-computed result; AI does not choose the winner.")
        ovrow=QHBoxLayout(); overview.layout.addLayout(ovrow)
        self.overview_provider=QComboBox(); self.overview_provider.addItems(["Auto — best available","Local AI","OpenAI"])
        self.ai_overview_btn=QPushButton("Generate AI Overview"); self.ai_overview_btn.clicked.connect(self.generate_ai_overview)
        ovrow.addWidget(QLabel("Optional AI explanation")); ovrow.addWidget(self.overview_provider); ovrow.addWidget(self.ai_overview_btn); ovrow.addStretch(1)
        self.election_overview=QLabel("Run an election to create a recap."); self.election_overview.setWordWrap(True); self.election_overview.setAlignment(Qt.AlignTop|Qt.AlignLeft); self.election_overview.setTextInteractionFlags(Qt.TextSelectableByMouse); overview.layout.addWidget(self.election_overview)
        self.results_card.layout.addWidget(overview)
        rr=QHBoxLayout(); rr.setSpacing(12); self.electoral_grid=ElectoralGrid(); self.electoral_grid.state_clicked.connect(self.show_state_detail); rr.addWidget(self.electoral_grid,3)
        state_card=Card("State inspector", info_text="Click a state on the geographic map or in the battleground table to see its modeled margin, win probability and starter baseline."); self.state_detail=QLabel("Click a state to inspect it."); self.state_detail.setWordWrap(True); self.state_detail.setAlignment(Qt.AlignTop | Qt.AlignLeft); self.state_detail.setTextInteractionFlags(Qt.TextSelectableByMouse); state_card.layout.addWidget(self.state_detail); state_card.layout.addStretch(1); rr.addWidget(state_card,2)
        self.results_card.layout.addLayout(rr)
        table_help=QHBoxLayout(); tl=QLabel("Battlegrounds"); tl.setObjectName("SectionTitle"); table_help.addWidget(tl); table_help.addWidget(InfoButton("Battleground table", "States are initially ordered by how close Ticket A's win probability is to 50%. Margin is measured in percentage points; rating is a plain-language confidence bucket.")); table_help.addStretch(1); self.results_card.layout.addLayout(table_help)
        self.state_table=QTableWidget(0,5); self.state_table.setHorizontalHeaderLabels(["State","Electoral votes","Ticket A win %","Avg margin (pts)","Rating"]); self.state_table.setAlternatingRowColors(True); self.state_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.state_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.state_table.setSelectionMode(QAbstractItemView.SingleSelection); self.state_table.setSortingEnabled(True); self.state_table.horizontalHeader().setSectionsClickable(True); self.state_table.horizontalHeader().setSortIndicatorShown(True); self.state_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.Stretch); self.state_table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeToContents); self.state_table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeToContents); self.state_table.horizontalHeader().setSectionResizeMode(3,QHeaderView.ResizeToContents); self.state_table.horizontalHeader().setSectionResizeMode(4,QHeaderView.ResizeToContents); self.state_table.setMinimumHeight(250); self.state_table.verticalHeader().setVisible(False); self.state_table.setShowGrid(False); self.state_table.cellClicked.connect(self._state_table_clicked)
        self.state_table.horizontalHeaderItem(1).setToolTip("Electoral votes assigned to the state. 270 of 538 are normally needed to win the presidency.")
        self.state_table.horizontalHeaderItem(2).setToolTip("Share of this model's runs where Ticket A wins the state.")
        self.state_table.horizontalHeaderItem(3).setToolTip("Average modeled two-ticket margin, in percentage points.")
        self.state_table.horizontalHeaderItem(4).setToolTip("Tossup / Lean / Likely / Safe is a plain-language bucket based on modeled win probability.")
        self.results_card.layout.addWidget(self.state_table)
        result_actions=QHBoxLayout(); result_actions.setSpacing(8)
        self.save_result_btn=QPushButton("Save Result"); self.save_result_btn.setToolTip("Save this simulation to ElectionLab's portable simulation archive."); self.save_result_btn.clicked.connect(self.save_simulation_result)
        self.export_result_btn=QPushButton("Export JSON…"); self.export_result_btn.setToolTip("Export the complete numerical result, state explanations and model metadata as JSON."); self.export_result_btn.clicked.connect(self.export_simulation_result)
        self.new_seed_rematch_btn=QPushButton("Rematch · New Seed"); self.new_seed_rematch_btn.setToolTip("Keep the matchup and settings, generate a new seed, then simulate another plausible universe."); self.new_seed_rematch_btn.clicked.connect(self.rematch_new_seed)
        result_actions.addWidget(self.save_result_btn); result_actions.addWidget(self.export_result_btn); result_actions.addWidget(self.new_seed_rematch_btn); result_actions.addStretch(1)
        self.results_card.layout.addLayout(result_actions)
        iv.addWidget(self.results_card)
        scroll.setWidget(inner); v.addWidget(scroll,1); return page

    def _campaign_page(self):
        page, v = page_shell(
            "New Game & Saves",
            "Start a campaign from an official ElectionLab rules preset, customize it if you want, or load an existing save.",
        )
        splitter = QSplitter(Qt.Horizontal); splitter.setChildrenCollapsible(False)
        left = QWidget(); left_col = QVBoxLayout(left); left_col.setContentsMargins(0,0,0,0); left_col.setSpacing(12)
        create = Card("New Game", info_text="Rules are saved inside this campaign. Changing global Settings later will not silently change what systems this save uses.")
        general = QGridLayout(); general.setHorizontalSpacing(12); general.setVerticalSpacing(9); create.layout.addLayout(general)
        self.camp_title = QLineEdit("2028 Campaign")
        self.camp_detail = QComboBox(); self.camp_detail.addItems(DETAIL_LEVELS); self.camp_detail.setCurrentText("Weekly")
        self.camp_agency = QComboBox(); self.camp_agency.addItems(AGENCY_LEVELS)
        self.camp_seed = QLineEdit(make_seed()); self.camp_seed.setClearButtonEnabled(True)
        self.camp_rules_preset = QComboBox(); self.camp_rules_preset.addItems(list(RULE_PRESETS)); self.camp_rules_preset.setCurrentText("Campaign")
        general.addWidget(QLabel("Campaign name"),0,0); general.addWidget(self.camp_title,0,1,1,3)
        general.addWidget(InfoLabel("Rules preset", "Official presets are read-only templates. Change any toggle and the campaign becomes a modified version of that preset."),1,0); general.addWidget(self.camp_rules_preset,1,1)
        general.addWidget(InfoLabel("Starting pace", "How much campaign time is simulated between decisions. You can change pace later."),1,2); general.addWidget(self.camp_detail,1,3)
        general.addWidget(InfoLabel("Agency", "Play Ticket A, Ticket B, control both, or spectate."),2,0); general.addWidget(self.camp_agency,2,1)
        general.addWidget(InfoLabel("Seed", "Reproduces the campaign's pseudo-random event sequence when rules, tickets and decisions match."),2,2); general.addWidget(self.camp_seed,2,3)
        general.setColumnStretch(1,1); general.setColumnStretch(3,1)
        self.camp_rule_desc = QLabel(); self.camp_rule_desc.setObjectName("Muted"); self.camp_rule_desc.setWordWrap(True); create.layout.addWidget(self.camp_rule_desc)

        tickets = QHBoxLayout(); tickets.setSpacing(10)
        a_box = QGroupBox("Ticket A"); af = QFormLayout(a_box); af.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.camp_a = self._candidate_combo("Select or type Ticket A president…")
        self.camp_avp = self._candidate_combo("Optional Ticket A VP…", optional=True)
        self.camp_aparty = QComboBox(); self.camp_aparty.addItems(PARTIES); self.camp_aparty.setCurrentText("Democratic")
        af.addRow("President", self.camp_a); af.addRow("Vice president", self.camp_avp); af.addRow("Party", self.camp_aparty)
        b_box = QGroupBox("Ticket B"); bf = QFormLayout(b_box); bf.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.camp_b = self._candidate_combo("Select or type Ticket B president…")
        self.camp_bvp = self._candidate_combo("Optional Ticket B VP…", optional=True)
        self.camp_bparty = QComboBox(); self.camp_bparty.addItems(PARTIES); self.camp_bparty.setCurrentText("Republican")
        bf.addRow("President", self.camp_b); bf.addRow("Vice president", self.camp_bvp); bf.addRow("Party", self.camp_bparty)
        tickets.addWidget(a_box,1); tickets.addWidget(b_box,1); create.layout.addLayout(tickets)

        rules_box = QGroupBox("Campaign rules · customize this save")
        rg = QGridLayout(rules_box); rg.setHorizontalSpacing(8); rg.setVerticalSpacing(7)
        self.camp_rule_controls = {}
        visible_controls=[x for x in RULE_CONTROLS]
        for i,(section,key,label,future) in enumerate(visible_controls):
            cb=QCheckBox(label + ("  · planned" if future else "")); cb.setProperty("ruleFuture", future)
            if future:
                cb.setEnabled(False); cb.setToolTip("This rule is reserved in the save format but the sourced live-data module is not implemented yet.")
            cb.stateChanged.connect(self._campaign_rules_changed)
            self.camp_rule_controls[(section,key)] = cb
            rg.addWidget(cb, i//3, i%3)
        create.layout.addWidget(rules_box)
        rule_footer=QHBoxLayout(); self.camp_rule_badge=QLabel("Official preset"); self.camp_rule_badge.setObjectName("RulesBadge"); rule_footer.addWidget(self.camp_rule_badge); rule_footer.addStretch(1)
        reset_rules=QPushButton("Reset to Preset"); reset_rules.clicked.connect(lambda:self._apply_campaign_preset(self.camp_rules_preset.currentText())); rule_footer.addWidget(reset_rules); create.layout.addLayout(rule_footer)

        self.create_campaign_btn = QPushButton("Start Campaign"); self.create_campaign_btn.setObjectName("Primary"); self.create_campaign_btn.clicked.connect(self.create_campaign); create.layout.addWidget(self.create_campaign_btn)
        left_col.addWidget(create); left_col.addStretch(1)

        saves = Card("Saved Games", info_text="Continue an existing campaign, create an alternate timeline branch, or delete a local save.")
        self.campaign_list = QListWidget(); self.campaign_list.setMinimumHeight(320); self.campaign_list.currentItemChanged.connect(self._campaign_selected); saves.layout.addWidget(self.campaign_list,1)
        actions = QHBoxLayout()
        self.open_hq_btn = QPushButton("Continue Selected"); self.open_hq_btn.setObjectName("Primary"); self.open_hq_btn.clicked.connect(self.open_campaign_hq); self.open_hq_btn.setEnabled(False)
        self.branch_btn = QPushButton("Branch Timeline"); self.branch_btn.clicked.connect(self.branch_campaign); self.branch_btn.setEnabled(False)
        self.delete_campaign_btn = QPushButton("Delete Save"); self.delete_campaign_btn.setObjectName("Danger"); self.delete_campaign_btn.clicked.connect(self.delete_campaign); self.delete_campaign_btn.setEnabled(False)
        actions.addWidget(self.open_hq_btn); actions.addWidget(self.branch_btn); actions.addStretch(1); actions.addWidget(self.delete_campaign_btn); saves.layout.addLayout(actions)
        self.campaign_info = QLabel("Select a save to inspect its tickets, rules and seed."); self.campaign_info.setWordWrap(True); self.campaign_info.setAlignment(Qt.AlignTop | Qt.AlignLeft); self.campaign_info.setObjectName("Muted"); saves.layout.addWidget(self.campaign_info)

        splitter.addWidget(left); splitter.addWidget(saves); splitter.setStretchFactor(0,11); splitter.setStretchFactor(1,9); splitter.setSizes([720,520])
        v.addWidget(splitter,1)
        self.camp_rules_preset.currentTextChanged.connect(self._apply_campaign_preset)
        QTimer.singleShot(0, lambda:self._apply_campaign_preset("Campaign"))
        return page

    def _apply_campaign_preset(self, name: str):
        if not hasattr(self, "camp_rule_controls"):
            return
        rules=preset_rules(name); self._updating_campaign_rules=True
        try:
            for (section,key),cb in self.camp_rule_controls.items():
                cb.setChecked(bool((rules.get(section) or {}).get(key,False)))
            preset=RULE_PRESETS.get(name) or RULE_PRESETS["Campaign"]
            self.camp_rule_desc.setText(preset.get("description", ""))
            if hasattr(self,"camp_rule_badge"):
                self.camp_rule_badge.setText(f"Official preset · {name}"); self.camp_rule_badge.setProperty("modified",False); self.camp_rule_badge.style().unpolish(self.camp_rule_badge); self.camp_rule_badge.style().polish(self.camp_rule_badge)
        finally:
            self._updating_campaign_rules=False

    def _campaign_rules_from_ui(self):
        name=self.camp_rules_preset.currentText() if hasattr(self,"camp_rules_preset") else "Campaign"
        rules=preset_rules(name)
        for (section,key),cb in getattr(self,"camp_rule_controls",{}).items():
            rules.setdefault(section,{})[key]=bool(cb.isChecked())
        return rules

    def _campaign_rules_changed(self, *_):
        if getattr(self,"_updating_campaign_rules",False) or not hasattr(self,"camp_rule_badge"):
            return
        name=self.camp_rules_preset.currentText(); rules=self._campaign_rules_from_ui(); modified=modified_from_preset(name,rules)
        self.camp_rule_badge.setText(f"{name} · {'Modified' if modified else 'Official preset'}")
        self.camp_rule_badge.setProperty("modified",modified); self.camp_rule_badge.style().unpolish(self.camp_rule_badge); self.camp_rule_badge.style().polish(self.camp_rule_badge)

    def _campaign_hq_page(self):
        page, v = page_shell(
            "Campaign HQ",
            "Play the active campaign. Normal strategy, conversations and timeline tools disappear when a major event takes over the campaign day.",
        )
        self.hq_mode_stack = QStackedWidget()

        # ---------- normal campaign view ----------
        normal_scroll = QScrollArea(); normal_scroll.setWidgetResizable(True)
        inner = QWidget(); inner.setObjectName("ScrollContent"); iv = QVBoxLayout(inner); iv.setContentsMargins(0,0,4,10); iv.setSpacing(14)

        header = Card("Active campaign")
        hh = QHBoxLayout(); hh.setSpacing(16); header.layout.addLayout(hh)
        self.hq_portrait_a = self._portrait_label(92); self.hq_portrait_b = self._portrait_label(92)
        self.hq_vp_portrait_a = self._portrait_label(58); self.hq_vp_portrait_b = self._portrait_label(58)
        self.hq_ticket_a = QLabel("Ticket A"); self.hq_ticket_a.setObjectName("SectionTitle"); self.hq_ticket_a.setWordWrap(True)
        self.hq_ticket_b = QLabel("Ticket B"); self.hq_ticket_b.setObjectName("SectionTitle"); self.hq_ticket_b.setWordWrap(True)
        apics=QHBoxLayout(); apics.setSpacing(6); apics.addWidget(self.hq_portrait_a); apics.addWidget(self.hq_vp_portrait_a,0,Qt.AlignVCenter)
        bpics=QHBoxLayout(); bpics.setSpacing(6); bpics.addWidget(self.hq_portrait_b); bpics.addWidget(self.hq_vp_portrait_b,0,Qt.AlignVCenter)
        arow = QHBoxLayout(); arow.addLayout(apics); arow.addWidget(self.hq_ticket_a,1)
        brow = QHBoxLayout(); brow.addLayout(bpics); brow.addWidget(self.hq_ticket_b,1)
        hh.addLayout(arow,1)
        self.hq_summary = QLabel("No campaign selected. Open one from Campaigns."); self.hq_summary.setAlignment(Qt.AlignCenter); self.hq_summary.setWordWrap(True); self.hq_summary.setObjectName("Muted"); hh.addWidget(self.hq_summary,1)
        hh.addLayout(brow,1)
        iv.addWidget(header)

        columns = QSplitter(Qt.Horizontal); columns.setChildrenCollapsible(False)
        strategy = Card("Strategy & time", info_text="Choose the high-level direction for the next campaign segment. The calendar can interrupt advancement when a scheduled major event is reached.")
        sf = QGridLayout(); sf.setHorizontalSpacing(12); sf.setVerticalSpacing(9); strategy.layout.addLayout(sf)
        self.turn_pace = QComboBox(); self.turn_pace.addItems(DETAIL_LEVELS); self.turn_pace.setCurrentText("Weekly")
        self.turn_region = QComboBox(); self.turn_region.addItems(list(REGIONS))
        self.turn_message = QComboBox(); self.turn_message.addItems(MESSAGES)
        self.turn_tone = QComboBox(); self.turn_tone.addItems(TONES)
        sf.addWidget(QLabel("Pace"),0,0); sf.addWidget(self.turn_pace,0,1)
        sf.addWidget(QLabel("Campaign focus"),1,0); sf.addWidget(self.turn_region,1,1)
        sf.addWidget(QLabel("Message"),2,0); sf.addWidget(self.turn_message,2,1)
        sf.addWidget(QLabel("Tone"),3,0); sf.addWidget(self.turn_tone,3,1); sf.setColumnStretch(1,1)
        self.state_pulse = QLabel("State electorate model activates after the first campaign turn."); self.state_pulse.setObjectName("Muted"); self.state_pulse.setWordWrap(True); strategy.layout.addWidget(self.state_pulse)
        self.advance_btn = QPushButton("Advance Campaign"); self.advance_btn.setObjectName("Primary"); self.advance_btn.setEnabled(False); self.advance_btn.clicked.connect(self.advance_campaign); strategy.layout.addWidget(self.advance_btn)
        self.election_day_btn = QPushButton("Run Election Day Result"); self.election_day_btn.setObjectName("Primary"); self.election_day_btn.clicked.connect(self.run_campaign_election); self.election_day_btn.hide(); strategy.layout.addWidget(self.election_day_btn)
        self.hq_branch_btn = QPushButton("Branch Current Timeline"); self.hq_branch_btn.setEnabled(False); self.hq_branch_btn.clicked.connect(self.branch_campaign_hq); strategy.layout.addWidget(self.hq_branch_btn)
        columns.addWidget(strategy)

        timeline = Card("Campaign timeline", info_text="The timeline now separates upcoming scheduled milestones from the history your campaign has actually created.")
        self.timeline_progress = QProgressBar(); self.timeline_progress.setRange(0,100); self.timeline_progress.setValue(0); self.timeline_progress.setFormat("Campaign progress %p%")
        timeline.layout.addWidget(self.timeline_progress)
        self.next_milestone = QLabel("No campaign selected."); self.next_milestone.setWordWrap(True); self.next_milestone.setObjectName("Muted"); timeline.layout.addWidget(self.next_milestone)
        narrrow=QHBoxLayout(); self.narrate_latest_btn=QPushButton("Narrate Latest Turn"); self.narrate_latest_btn.setToolTip("Re-write the latest already-computed campaign turn using the Campaign History Narration provider selected in Settings. This does not change campaign math."); self.narrate_latest_btn.clicked.connect(self.narrate_latest_turn); narrrow.addStretch(1); narrrow.addWidget(self.narrate_latest_btn); timeline.layout.addLayout(narrrow)
        timeline_split = QSplitter(Qt.Horizontal); timeline_split.setChildrenCollapsible(False)
        upcoming_box = QWidget(); upcoming_l = QVBoxLayout(upcoming_box); upcoming_l.setContentsMargins(0,0,0,0); upcoming_l.setSpacing(6)
        up_title = QLabel("Upcoming"); up_title.setObjectName("SmallCaps"); upcoming_l.addWidget(up_title)
        self.timeline_schedule = QListWidget(); self.timeline_schedule.setMinimumHeight(165); upcoming_l.addWidget(self.timeline_schedule,1)
        history_box = QWidget(); history_l = QVBoxLayout(history_box); history_l.setContentsMargins(0,0,0,0); history_l.setSpacing(6)
        hist_title = QLabel("Recent history"); hist_title.setObjectName("SmallCaps"); history_l.addWidget(hist_title)
        self.timeline_preview = QLabel("No campaign selected."); self.timeline_preview.setWordWrap(True); self.timeline_preview.setAlignment(Qt.AlignTop|Qt.AlignLeft); self.timeline_preview.setObjectName("Muted"); self.timeline_preview.setTextInteractionFlags(Qt.TextSelectableByMouse)
        history_scroll = QScrollArea(); history_scroll.setWidgetResizable(True); history_scroll.setMinimumHeight(165); history_scroll.setWidget(self.timeline_preview); history_l.addWidget(history_scroll,1)
        timeline_split.addWidget(upcoming_box); timeline_split.addWidget(history_box); timeline_split.setSizes([260,520]); timeline.layout.addWidget(timeline_split,1)
        columns.addWidget(timeline); columns.setStretchFactor(0,2); columns.setStretchFactor(1,4); columns.setSizes([420,760]); iv.addWidget(columns)

        ops_center=Card("Operations Center", info_text="Run deterministic campaign actions between turns. These affect funds, momentum, regional attention and the live state pulse without asking AI to decide the outcome.")
        ops_grid=QGridLayout(); ops_grid.setHorizontalSpacing(10); ops_grid.setVerticalSpacing(8); ops_center.layout.addLayout(ops_grid)
        self.campaign_operation_side=QComboBox(); self.campaign_operation_side.addItems(["Ticket A","Ticket B"])
        self.campaign_operation_type=QComboBox(); self.campaign_operation_type.addItems(list(CAMPAIGN_OPERATION_SPECS))
        self.campaign_operation_region=QComboBox(); self.campaign_operation_region.addItems(list(REGIONS))
        self.campaign_operation_message=QComboBox(); self.campaign_operation_message.addItems(MESSAGES)
        self.campaign_operation_tone=QComboBox(); self.campaign_operation_tone.addItems(TONES)
        self.campaign_operation_type.currentTextChanged.connect(lambda *_: self._update_campaign_operation_hint())
        self.campaign_operation_region.currentTextChanged.connect(lambda *_: self._update_campaign_operation_hint())
        ops_grid.addWidget(QLabel("Side"),0,0); ops_grid.addWidget(self.campaign_operation_side,0,1)
        ops_grid.addWidget(QLabel("Operation"),0,2); ops_grid.addWidget(self.campaign_operation_type,0,3)
        ops_grid.addWidget(QLabel("Region"),1,0); ops_grid.addWidget(self.campaign_operation_region,1,1)
        ops_grid.addWidget(QLabel("Message"),1,2); ops_grid.addWidget(self.campaign_operation_message,1,3)
        ops_grid.addWidget(QLabel("Tone"),2,0); ops_grid.addWidget(self.campaign_operation_tone,2,1); ops_grid.setColumnStretch(3,1)
        ops_row=QHBoxLayout(); self.campaign_operation_status=QLabel("Open a campaign to run operations."); self.campaign_operation_status.setObjectName("Muted"); self.campaign_operation_status.setWordWrap(True); ops_row.addWidget(self.campaign_operation_status,1)
        self.campaign_operation_btn=QPushButton("Run Operation"); self.campaign_operation_btn.setObjectName("Primary"); self.campaign_operation_btn.setEnabled(False); self.campaign_operation_btn.clicked.connect(self.run_campaign_operation); ops_row.addWidget(self.campaign_operation_btn)
        ops_center.layout.addLayout(ops_row); iv.addWidget(ops_center)

        intel=Card("War Room", info_text="A deterministic campaign-intelligence snapshot built from the same live state-agent data shown on the map. It highlights close states, under-attended opportunities and issue matches without invoking AI.")
        self.hq_strategy_intel=QLabel("Open a campaign to populate the War Room."); self.hq_strategy_intel.setWordWrap(True); self.hq_strategy_intel.setAlignment(Qt.AlignTop|Qt.AlignLeft); self.hq_strategy_intel.setTextInteractionFlags(Qt.TextSelectableByMouse); intel.layout.addWidget(self.hq_strategy_intel)
        iv.addWidget(intel)

        map_card = Card("Live campaign map", info_text="This map updates after every campaign turn. It combines the starter state baseline with the campaign's accumulated state-agent movement and momentum. Click any state to inspect priorities, attention and campaign response.")
        map_split=QSplitter(Qt.Horizontal); map_split.setChildrenCollapsible(False)
        self.hq_campaign_map=ElectoralGrid(); self.hq_campaign_map.set_display_context("Live campaign pulse","modeled pulse"); self.hq_campaign_map.setMinimumHeight(500); self.hq_campaign_map.state_clicked.connect(self.show_campaign_state_detail); map_split.addWidget(self.hq_campaign_map)
        self.hq_state_detail=QLabel("Select a state to inspect its priorities and campaign response."); self.hq_state_detail.setWordWrap(True); self.hq_state_detail.setAlignment(Qt.AlignTop|Qt.AlignLeft); self.hq_state_detail.setTextInteractionFlags(Qt.TextSelectableByMouse); self.hq_state_detail.setMinimumWidth(320)
        detail_host=Card("State pulse", info_text="State issue priorities are model inputs, not claims that every voter in the state agrees. Economic indicators are sourced; issue weights are ElectionLab heuristics until sourced issue polling is added."); detail_host.layout.addWidget(self.hq_state_detail)
        ops_title=QLabel("STATE OPERATION"); ops_title.setObjectName("SmallCaps"); detail_host.layout.addWidget(ops_title)
        ops=QGridLayout(); ops.setHorizontalSpacing(8); ops.setVerticalSpacing(7)
        self.hq_operation_side=QComboBox(); self.hq_operation_side.addItems(["Ticket A","Ticket B"])
        self.hq_operation_type=QComboBox(); self.hq_operation_type.addItems(["Rally","Town Hall","Ad Buy","Field Organizing"])
        self.hq_operation_message=QComboBox(); self.hq_operation_message.addItems(MESSAGES)
        ops.addWidget(QLabel("Side"),0,0); ops.addWidget(self.hq_operation_side,0,1)
        ops.addWidget(QLabel("Operation"),1,0); ops.addWidget(self.hq_operation_type,1,1)
        ops.addWidget(QLabel("Message"),2,0); ops.addWidget(self.hq_operation_message,2,1); ops.setColumnStretch(1,1)
        detail_host.layout.addLayout(ops)
        self.hq_operation_btn=QPushButton("Run State Operation"); self.hq_operation_btn.setObjectName("Primary"); self.hq_operation_btn.clicked.connect(self.run_state_operation); self.hq_operation_btn.setEnabled(False); detail_host.layout.addWidget(self.hq_operation_btn)
        self.hq_operation_status=QLabel("Select a state to target it directly."); self.hq_operation_status.setObjectName("Muted"); self.hq_operation_status.setWordWrap(True); detail_host.layout.addWidget(self.hq_operation_status)
        map_split.addWidget(detail_host); map_split.setStretchFactor(0,3); map_split.setStretchFactor(1,2); map_split.setSizes([760,420])
        map_card.layout.addWidget(map_split); iv.addWidget(map_card)

        polls=Card("Polling tracker", info_text="These are fictional seeded campaign polls generated from the hidden state-agent pulse plus sampling noise. They are not real-world polls and can disagree with the underlying modeled electorate.")
        polltop=QHBoxLayout(); self.hq_poll_summary=QLabel("Advance the campaign to generate the first battleground polling snapshot."); self.hq_poll_summary.setObjectName("Muted"); self.hq_poll_summary.setWordWrap(True); polltop.addWidget(self.hq_poll_summary,1)
        self.hq_refresh_poll_btn=QPushButton("Take Polling Snapshot"); self.hq_refresh_poll_btn.clicked.connect(self.take_poll_snapshot); self.hq_refresh_poll_btn.setEnabled(False); polltop.addWidget(self.hq_refresh_poll_btn); polls.layout.addLayout(polltop)
        self.hq_poll_table=QTableWidget(0,6); self.hq_poll_table.setHorizontalHeaderLabels(["State","Simulated poll","Underlying pulse","Sample","MOE","vs prior"]); self.hq_poll_table.verticalHeader().setVisible(False); self.hq_poll_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.hq_poll_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.hq_poll_table.setAlternatingRowColors(True); self.hq_poll_table.setShowGrid(False); self.hq_poll_table.setMinimumHeight(205)
        ph=self.hq_poll_table.horizontalHeader(); ph.setSectionResizeMode(0,QHeaderView.Stretch)
        for ci in range(1,6): ph.setSectionResizeMode(ci,QHeaderView.ResizeToContents)
        polls.layout.addWidget(self.hq_poll_table); iv.addWidget(polls)

        talk = Card("Campaign conversations", info_text="Talk to different simulated people around the campaign. Adviser responses focus on strategy; constituents, staff, volunteers, donors and reporters respond from their selected fictional role.")
        ar = QHBoxLayout(); talk.layout.addLayout(ar)
        self.conversation_role = QComboBox(); self.conversation_role.addItems(["Campaign adviser","Constituent","Campaign staff","Volunteer","Donor","Reporter"])
        self.conversation_state = QComboBox(); self.conversation_state.addItem("Auto encounter", None)
        for code,ctx in sorted(self.campaign_engine.state_agents.states.items(), key=lambda kv: kv[1].get("name",kv[0])):
            self.conversation_state.addItem(f"{ctx.get('name',code)} ({code})", code)
        self.conversation_state.setEnabled(False)
        self.conversation_role.currentTextChanged.connect(lambda role:self.conversation_state.setEnabled(role=="Constituent"))
        self.ai_provider = QComboBox(); self.ai_provider.addItems(["Auto — best available","Local AI","OpenAI"])
        ar.addWidget(QLabel("Talk to")); ar.addWidget(self.conversation_role); ar.addWidget(QLabel("State")); ar.addWidget(self.conversation_state); ar.addSpacing(10); ar.addWidget(QLabel("Provider")); ar.addWidget(self.ai_provider); ar.addStretch(1)
        self.advisor_log = QPlainTextEdit(); self.advisor_log.setReadOnly(True); self.advisor_log.setMaximumBlockCount(300); self.advisor_log.setPlaceholderText("Campaign conversations appear here. Try your adviser, a constituent, campaign staff, a volunteer, donor, or reporter."); self.advisor_log.setMinimumHeight(155); talk.layout.addWidget(self.advisor_log)
        askrow = QHBoxLayout(); self.advisor_input = QLineEdit(); self.advisor_input.setPlaceholderText("Say something…"); self.advisor_input.returnPressed.connect(self.ask_advisor); askrow.addWidget(self.advisor_input,1)
        self.advisor_btn = QPushButton("Send"); self.advisor_btn.setObjectName("Primary"); self.advisor_btn.clicked.connect(self.ask_advisor); askrow.addWidget(self.advisor_btn); talk.layout.addLayout(askrow); iv.addWidget(talk)

        normal_scroll.setWidget(inner)
        self.hq_mode_stack.addWidget(normal_scroll)

        # ---------- major-event takeover view ----------
        event_page = QWidget(); event_page.setObjectName("ScrollContent"); ev = QVBoxLayout(event_page); ev.setContentsMargins(40,28,40,28); ev.setSpacing(16)
        ev.addStretch(1)
        event_card = Card("DEBATE NIGHT", hero=True, info_text="A scheduled debate pauses ordinary campaign controls. Participate, auto-simulate it, or skip it before time can advance again.")
        self.debate_event_title = QLabel("Scheduled debate"); self.debate_event_title.setObjectName("EventTitle"); self.debate_event_title.setAlignment(Qt.AlignCenter); self.debate_event_title.setWordWrap(True); event_card.layout.addWidget(self.debate_event_title)
        self.debate_event_meta = QLabel(""); self.debate_event_meta.setObjectName("Muted"); self.debate_event_meta.setAlignment(Qt.AlignCenter); self.debate_event_meta.setWordWrap(True); event_card.layout.addWidget(self.debate_event_meta)
        top = QHBoxLayout(); self.debate_provider = QComboBox(); self.debate_provider.addItems(["Auto — best available","Local AI","OpenAI"]); self.debate_side = QComboBox(); self.debate_side.addItems(["Ticket A","Ticket B"])
        top.addStretch(1); top.addWidget(QLabel("AI provider")); top.addWidget(self.debate_provider); top.addSpacing(12); top.addWidget(QLabel("You answer as")); top.addWidget(self.debate_side); top.addStretch(1); event_card.layout.addLayout(top)

        self.debate_question = QLabel("Choose how to handle this debate."); self.debate_question.setWordWrap(True); self.debate_question.setObjectName("DebateQuestion"); self.debate_question.setAlignment(Qt.AlignCenter); event_card.layout.addWidget(self.debate_question)
        self.debate_answer = QPlainTextEdit(); self.debate_answer.setPlaceholderText("Type your debate answer here…"); self.debate_answer.setMinimumHeight(155); self.debate_answer.hide(); event_card.layout.addWidget(self.debate_answer)
        self.debate_result = QLabel(""); self.debate_result.setWordWrap(True); self.debate_result.setAlignment(Qt.AlignTop|Qt.AlignLeft); self.debate_result.setTextInteractionFlags(Qt.TextSelectableByMouse); self.debate_result.setObjectName("Muted"); self.debate_result.hide(); event_card.layout.addWidget(self.debate_result)

        actions = QHBoxLayout(); actions.addStretch(1)
        self.debate_begin_btn = QPushButton("Participate"); self.debate_begin_btn.setObjectName("Primary"); self.debate_begin_btn.clicked.connect(self.begin_debate_question)
        self.debate_auto_btn = QPushButton("Auto Debate"); self.debate_auto_btn.clicked.connect(self.auto_debate)
        self.debate_skip_btn = QPushButton("Skip Debate"); self.debate_skip_btn.setObjectName("Danger"); self.debate_skip_btn.clicked.connect(self.skip_debate)
        self.debate_submit_btn = QPushButton("Submit Answer"); self.debate_submit_btn.setObjectName("Primary"); self.debate_submit_btn.setEnabled(False); self.debate_submit_btn.clicked.connect(self.submit_debate_answer); self.debate_submit_btn.hide()
        actions.addWidget(self.debate_begin_btn); actions.addWidget(self.debate_auto_btn); actions.addWidget(self.debate_skip_btn); actions.addWidget(self.debate_submit_btn); actions.addStretch(1); event_card.layout.addLayout(actions)
        ev.addWidget(event_card); ev.addStretch(1)
        self.hq_mode_stack.addWidget(event_page)

        v.addWidget(self.hq_mode_stack,1)
        return page

    def _vault_page(self):
        page, v = page_shell(
            "Knowledge Vault",
            "Your offline candidate library. Built-in profiles, researched people and custom candidates stay available without a network connection.",
        )

        # Two-row action area keeps search and profile acquisition from colliding
        # at common desktop widths.
        top_card = Card("Find or add a profile", info_text="Search filters profiles already saved locally. Research + Cache uses configured online research; Local AI Enrich uses only the configured local provider.")
        search_row = QHBoxLayout(); search_row.setSpacing(8)
        self.vault_search = QLineEdit(); self.vault_search.setPlaceholderText("Search saved profiles…"); self.vault_search.setClearButtonEnabled(True); self.vault_search.textChanged.connect(self.refresh_vault_table)
        search_row.addWidget(self.vault_search, 1)
        self.vault_type_filter=QComboBox(); self.vault_type_filter.addItems(["All types","Historical political","Public figures","Custom / unknown"]); self.vault_type_filter.currentTextChanged.connect(self.refresh_vault_table); search_row.addWidget(self.vault_type_filter)
        self.vault_party_filter=QComboBox(); self.vault_party_filter.addItem("All parties"); self.vault_party_filter.currentTextChanged.connect(self.refresh_vault_table); search_row.addWidget(self.vault_party_filter)
        self.vault_source_filter=QComboBox(); self.vault_source_filter.addItems(["All sources","Built-in","Researched / web","Local AI","User-created"]); self.vault_source_filter.currentTextChanged.connect(self.refresh_vault_table); search_row.addWidget(self.vault_source_filter)
        custom = QPushButton("Create Custom Candidate"); custom.clicked.connect(self.create_custom_profile); search_row.addWidget(custom)
        top_card.layout.addLayout(search_row)

        add_row = QHBoxLayout()
        add_label = QLabel("Add someone")
        add_label.setObjectName("FieldLabel"); add_row.addWidget(add_label)
        self.research_name = QLineEdit(); self.research_name.setPlaceholderText("Type any public person's name…"); self.research_name.setClearButtonEnabled(True); add_row.addWidget(self.research_name, 1)
        self.research_btn = QPushButton("Research + Cache"); self.research_btn.setObjectName("Primary"); self.research_btn.clicked.connect(self.research_person); add_row.addWidget(self.research_btn)
        self.local_enrich_btn = QPushButton("Local AI Enrich"); self.local_enrich_btn.clicked.connect(self.local_enrich_person); add_row.addWidget(self.local_enrich_btn)
        top_card.layout.addLayout(add_row)
        v.addWidget(top_card)

        splitter = QSplitter(Qt.Horizontal); splitter.setChildrenCollapsible(False)
        self.vault_table = QTableWidget(0,5)
        self.vault_table.setHorizontalHeaderLabels(["Name","Profile","Party","Source","Updated"])
        self.vault_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.vault_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.vault_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.vault_table.setAlternatingRowColors(True); self.vault_table.setShowGrid(False)
        self.vault_table.verticalHeader().setVisible(False); self.vault_table.setSortingEnabled(True)
        hdr = self.vault_table.horizontalHeader(); hdr.setSectionsClickable(True); hdr.setSortIndicatorShown(True)
        hdr.setSectionResizeMode(0,QHeaderView.Stretch)
        hdr.setSectionResizeMode(1,QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2,QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3,QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(4,QHeaderView.ResizeToContents)
        self.vault_table.itemSelectionChanged.connect(self.vault_selection_changed)
        splitter.addWidget(self.vault_table)

        detail = Card("Profile details", info_text="Shows what ElectionLab actually knows about this person. Unknown positions remain unknown unless you explicitly allow a model inference.")
        prof_top = QHBoxLayout(); prof_top.setSpacing(14); detail.layout.addLayout(prof_top)
        self.profile_photo = self._portrait_label(132); prof_top.addWidget(self.profile_photo,0,Qt.AlignTop)
        self.profile_detail = QLabel("Select a profile to inspect its offline data.")
        self.profile_detail.setWordWrap(True); self.profile_detail.setAlignment(Qt.AlignTop | Qt.AlignLeft); self.profile_detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        prof_top.addWidget(self.profile_detail,1)
        self.profile_traits=QLabel(); self.profile_traits.setWordWrap(True); self.profile_traits.setObjectName("Muted"); self.profile_traits.setTextInteractionFlags(Qt.TextSelectableByMouse); detail.layout.addWidget(self.profile_traits)
        self.profile_evidence=QPlainTextEdit(); self.profile_evidence.setReadOnly(True); self.profile_evidence.setMinimumHeight(135); self.profile_evidence.setPlaceholderText("Documented positions, explicit model inferences and saved sources will appear here as the profile is enriched."); detail.layout.addWidget(self.profile_evidence,1)
        profile_actions = QHBoxLayout()
        self.fetch_photo_btn = QPushButton("Fetch Portrait"); self.fetch_photo_btn.clicked.connect(self.fetch_selected_portrait); self.fetch_photo_btn.setEnabled(False)
        self.fetch_all_photos_btn = QPushButton("Fetch All Missing Portraits"); self.fetch_all_photos_btn.clicked.connect(self.fetch_all_missing_portraits)
        self.import_photo_btn = QPushButton("Choose Local Portrait"); self.import_photo_btn.clicked.connect(self.import_selected_portrait); self.import_photo_btn.setEnabled(False)
        self.refresh_profile_btn = QPushButton("Refresh Selected Online"); self.refresh_profile_btn.setToolTip("Re-run Research + Cache for the selected saved person. Custom profiles require confirmation because researched public data may replace custom simulation fields."); self.refresh_profile_btn.clicked.connect(self.refresh_selected_profile_online); self.refresh_profile_btn.setEnabled(False)
        self.delete_profile_btn = QPushButton("Delete Profile"); self.delete_profile_btn.setObjectName("Danger"); self.delete_profile_btn.clicked.connect(self.delete_selected_profile); self.delete_profile_btn.setEnabled(False)
        profile_actions.addWidget(self.fetch_photo_btn); profile_actions.addWidget(self.fetch_all_photos_btn); profile_actions.addWidget(self.import_photo_btn); profile_actions.addWidget(self.refresh_profile_btn); profile_actions.addStretch(1); profile_actions.addWidget(self.delete_profile_btn); detail.layout.addLayout(profile_actions)
        self.vault_batch_progress=QProgressBar(); self.vault_batch_progress.setRange(0,100); self.vault_batch_progress.setValue(0); self.vault_batch_progress.setFormat("Portrait batch %p%"); self.vault_batch_progress.hide(); detail.layout.addWidget(self.vault_batch_progress)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 3); splitter.setStretchFactor(1, 2); splitter.setSizes([720, 455])
        v.addWidget(splitter,1)

        self.vault_status = QLabel(); self.vault_status.setObjectName("Muted"); v.addWidget(self.vault_status)
        return page

    def _data_page(self):
        page, v = page_shell(
            "Data",
            "Inspect the datasets and model inputs ElectionLab is actually using. Real source data and ElectionLab-derived heuristics are labeled separately.",
        )
        metrics=QHBoxLayout(); metrics.setSpacing(10)
        self.data_metric_states=MetricCard("State records")
        self.data_metric_snapshot=MetricCard("Economic snapshot")
        self.data_metric_vault=MetricCard("Knowledge Vault")
        self.data_metric_portraits=MetricCard("Portrait cache")
        for m in [self.data_metric_states,self.data_metric_snapshot,self.data_metric_vault,self.data_metric_portraits]: metrics.addWidget(m)
        v.addLayout(metrics)

        state_card=Card("State data explorer", info_text="Official indicators are bundled from the Census ACS starter pack. The issue-priority column is an ElectionLab heuristic derived from those indicators and is not opinion polling.")
        sr=QHBoxLayout(); self.data_state_search=QLineEdit(); self.data_state_search.setPlaceholderText("Filter states…"); self.data_state_search.setClearButtonEnabled(True); self.data_state_search.textChanged.connect(self.refresh_data_page); sr.addWidget(self.data_state_search,1)
        state_card.layout.addLayout(sr)
        self.data_state_table=QTableWidget(0,8)
        self.data_state_table.setHorizontalHeaderLabels(["State","EV","2024 D margin","Median income","Median rent","ACS unemployment","Top modeled priorities","Confidence"])
        self.data_state_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.data_state_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.data_state_table.setAlternatingRowColors(True); self.data_state_table.setShowGrid(False); self.data_state_table.verticalHeader().setVisible(False); self.data_state_table.setSortingEnabled(True)
        dh=self.data_state_table.horizontalHeader(); dh.setSectionsClickable(True); dh.setSortIndicatorShown(True); dh.setSectionResizeMode(0,QHeaderView.ResizeToContents); dh.setSectionResizeMode(1,QHeaderView.ResizeToContents); dh.setSectionResizeMode(2,QHeaderView.ResizeToContents); dh.setSectionResizeMode(3,QHeaderView.ResizeToContents); dh.setSectionResizeMode(4,QHeaderView.ResizeToContents); dh.setSectionResizeMode(5,QHeaderView.ResizeToContents); dh.setSectionResizeMode(6,QHeaderView.Stretch); dh.setSectionResizeMode(7,QHeaderView.ResizeToContents)
        self.data_state_table.setMinimumHeight(340); state_card.layout.addWidget(self.data_state_table)
        v.addWidget(state_card,1)

        bottom=QHBoxLayout(); bottom.setSpacing(12)
        sources=Card("Provenance")
        self.data_sources=QLabel(); self.data_sources.setWordWrap(True); self.data_sources.setTextInteractionFlags(Qt.TextSelectableByMouse); sources.layout.addWidget(self.data_sources)
        bottom.addWidget(sources,3)
        modules=Card("Data modules")
        self.data_modules=QLabel(); self.data_modules.setWordWrap(True); modules.layout.addWidget(self.data_modules)
        bottom.addWidget(modules,2)
        v.addLayout(bottom)
        profile_pack=Card("Candidate data pack", info_text="ElectionLab can refresh bundled starter profiles without overwriting custom or already-researched profiles. Only records still marked as built-in starter data are eligible for automatic seed-pack upgrades.")
        self.data_profile_pack=QLabel(); self.data_profile_pack.setWordWrap(True); self.data_profile_pack.setTextInteractionFlags(Qt.TextSelectableByMouse); profile_pack.layout.addWidget(self.data_profile_pack)
        pack_actions=QHBoxLayout(); pack_actions.addStretch(1); open_vault=QPushButton("Open Knowledge Vault"); open_vault.clicked.connect(lambda:self.go(4)); pack_actions.addWidget(open_vault); profile_pack.layout.addLayout(pack_actions)
        v.addWidget(profile_pack)
        return page

    def refresh_data_page(self,*_):
        if not hasattr(self,"data_state_table"):
            return
        states=self.campaign_engine.state_agents.states
        meta=self.campaign_engine.state_agents.metadata
        profiles=self.vault.list_profiles(limit=5000)
        portraits=sum(1 for p in profiles if p.get("photo_path") and Path(p.get("photo_path")).exists())
        self.data_metric_states.value.setText(str(len(states))); self.data_metric_states.sub.setText("50 states + D.C.")
        self.data_metric_snapshot.value.setText(str(meta.get("snapshot_date","—"))); self.data_metric_snapshot.sub.setText(meta.get("label","Bundled state context"))
        self.data_metric_vault.value.setText(str(len(profiles))); self.data_metric_vault.sub.setText("saved offline profiles")
        self.data_metric_portraits.value.setText(f"{portraits}/{len(profiles)}"); self.data_metric_portraits.sub.setText("cached locally")

        query=(self.data_state_search.text().strip().lower() if hasattr(self,"data_state_search") else "")
        rows=[(code,ctx) for code,ctx in states.items() if not query or query in code.lower() or query in str(ctx.get("name","")).lower() or query in " ".join(ctx.get("top_issues") or []).lower()]
        current_sort=self.data_state_table.horizontalHeader().sortIndicatorSection(); current_order=self.data_state_table.horizontalHeader().sortIndicatorOrder()
        self.data_state_table.setSortingEnabled(False); self.data_state_table.setRowCount(len(rows))
        for i,(code,ctx) in enumerate(sorted(rows,key=lambda kv:kv[1].get("name",kv[0]))):
            values=[
                SortableTableItem(f"{ctx.get('name',code)} ({code})",ctx.get('name',code)),
                SortableTableItem(str(ctx.get('ev','—')),float(ctx.get('ev',0))),
                SortableTableItem(f"{float(ctx.get('dem_margin_2024',0)):+.1f}",float(ctx.get('dem_margin_2024',0))),
                SortableTableItem(f"${float(ctx.get('median_household_income',0)):,.0f}",float(ctx.get('median_household_income',0))),
                SortableTableItem(f"${float(ctx.get('median_gross_rent',0)):,.0f}",float(ctx.get('median_gross_rent',0))),
                SortableTableItem(f"{float(ctx.get('acs_unemployment_rate',0)):.1f}%",float(ctx.get('acs_unemployment_rate',0))),
                SortableTableItem(", ".join(ctx.get('top_issues') or []),", ".join(ctx.get('top_issues') or [])),
                SortableTableItem(f"{float(ctx.get('data_confidence',0))*100:.0f}%",float(ctx.get('data_confidence',0))),
            ]
            for j,item in enumerate(values): self.data_state_table.setItem(i,j,item)
        self.data_state_table.setSortingEnabled(True)
        if current_sort >= 0:self.data_state_table.sortItems(current_sort,current_order)

        src=[]
        for item in meta.get("sources",[]):
            src.append(f"<b>{item.get('metric')}</b><br>{item.get('publisher')} · {item.get('dataset')}<br><span style='color:#8f9bad'>{item.get('url')}</span>")
        src.append(f"<br><b>Method note</b><br>{meta.get('method_note','')}")
        self.data_sources.setText("<br><br>".join(src))
        self.data_modules.setText(
            "<b>Loaded now</b><br>✓ Electoral votes / state baseline<br>✓ 2024 ACS income, rent and unemployment<br>✓ State issue-priority heuristics<br>✓ Seeded campaign polling simulator<br>✓ Knowledge Vault profiles / portrait cache<br><br>"
            "<b>Planned sourced/live modules</b><br>○ Real polling averages<br>○ Economic time series<br>○ Approval/favorability<br>○ Current events / endorsements<br>○ Issue polling where a sourced dataset exists<br><br>"
            "<span style='color:#8f9bad'>Future live modules will keep source dates and provenance instead of silently replacing the bundled snapshot.</span>"
        )
        if hasattr(self,"data_profile_pack"):
            starters=[p for p in profiles if p.get("source_type")=="built_in" and str(p.get("profile_status") or "").startswith("starter")]
            researched=[p for p in profiles if p.get("source_type")!="built_in"]
            custom=[p for p in profiles if p.get("source_type")=="user_created"]
            self.data_profile_pack.setText(
                f"<b>EL Starter Enrichment v2</b> · {len(starters)} starter-owned profiles currently eligible for future safe pack refreshes.<br>"
                f"{len(researched)} profiles are research/user-owned ({len(custom)} custom) and will <b>not</b> be replaced by starter updates.<br><br>"
                "<span style='color:#8f9bad'>Starter-pack updates upgrade old built-in placeholders in place while preserving cached portraits. Once a profile is enriched through web/OpenAI/local AI or created by you, starter-pack updates leave it alone.</span>"
            )

    def _settings_page(self):
        page,v=page_shell("Settings", "Provider changes now apply immediately. Large data/models can live on another drive; API credentials are not stored in portable_config.json.")
        scroll=QScrollArea(); scroll.setWidgetResizable(True); inner=QWidget(); inner.setObjectName("ScrollContent"); iv=QVBoxLayout(inner); iv.setContentsMargins(0,0,4,10); iv.setSpacing(14)
        storage=Card("Storage"); form=QFormLayout(); storage.layout.addLayout(form); self.data_root=QLineEdit(self.settings.settings.data_root); browse=QPushButton("Browse..."); browse.clicked.connect(self.choose_data_root); r=QHBoxLayout(); r.addWidget(self.data_root,1); r.addWidget(browse); form.addRow("Data root",r)
        note=QLabel("Keep this on F:/D:/etc. for databases, saves, caches and local models. Changing the path requires Save Settings because it rebinds the data services; network/AI toggles below apply instantly."); note.setWordWrap(True); note.setObjectName("Muted"); storage.layout.addWidget(note); iv.addWidget(storage)

        privacy=Card("Privacy / network")
        self.offline_lock=QCheckBox("Offline Lock — block all remote research and portrait downloads"); self.offline_lock.setChecked(self.settings.settings.offline_lock)
        self.internet_research=QCheckBox("Allow internet research modules"); self.internet_research.setChecked(self.settings.settings.internet_research)
        privacy.layout.addWidget(self.offline_lock); privacy.layout.addWidget(self.internet_research); iv.addWidget(privacy)

        cloud=Card("OpenAI hybrid provider (optional)"); cf=QFormLayout(); cloud.layout.addLayout(cf)
        self.openai_enabled=QCheckBox("Enable OpenAI provider"); self.openai_enabled.setChecked(self.settings.settings.openai_enabled)
        self.openai_model=QLineEdit(self.settings.settings.openai_model)
        self.api_key=QLineEdit(); self.api_key.setEchoMode(QLineEdit.Password); self.api_key.setPlaceholderText("Already stored" if load_api_key() else "Paste API key (stored via OS credential service)")
        cf.addRow(self.openai_enabled); cf.addRow("Model",self.openai_model); cf.addRow("API key",self.api_key)
        keyrow=QHBoxLayout(); sk=QPushButton("Store API Key"); sk.clicked.connect(self.store_key); ck=QPushButton("Clear Stored Key"); ck.clicked.connect(self.clear_key); keyrow.addWidget(sk);keyrow.addWidget(ck);keyrow.addStretch(1); cloud.layout.addLayout(keyrow); iv.addWidget(cloud)

        local=Card("Local AI / Ollama"); lf=QFormLayout(); local.layout.addLayout(lf)
        self.local_ai_enabled=QCheckBox("Enable local AI provider"); self.local_ai_enabled.setChecked(self.settings.settings.local_ai_enabled)
        self.ollama_url=QLineEdit(self.settings.settings.ollama_base_url); self.ollama_model=QLineEdit(self.settings.settings.ollama_model)
        self.ollama_executable=QLineEdit(self.settings.settings.ollama_executable); self.ollama_executable.setPlaceholderText("Auto-detect, or choose ollama.exe")
        obrowse=QPushButton("Browse…"); obrowse.clicked.connect(self.choose_ollama_executable); orow=QHBoxLayout(); orow.addWidget(self.ollama_executable,1); orow.addWidget(obrowse)
        lf.addRow(self.local_ai_enabled); lf.addRow("Local API",self.ollama_url); lf.addRow("Model",self.ollama_model); lf.addRow("Ollama executable",orow)
        olnote=QLabel("Election simulation math does not require Ollama. Ollama is only used for local conversations, debate dialogue, research enrichment and optional AI explanations. If ElectionLab cannot auto-detect it, choose ollama.exe here. Large Ollama models can stay on your selected non-C drive."); olnote.setWordWrap(True); olnote.setObjectName("Muted"); local.layout.addWidget(olnote); iv.addWidget(local)

        narration=Card("Campaign history narration", info_text="The campaign engine resolves the turn first. This setting only controls how the already-computed event ledger is written in Recent History; it cannot change momentum, state movement or the seed result.")
        nf=QFormLayout(); narration.layout.addLayout(nf)
        self.history_provider=QComboBox(); self.history_provider.addItems(["Deterministic local","Auto AI — local first","Local AI","OpenAI — testing override"]); self.history_provider.setCurrentText(getattr(self.settings.settings,"campaign_history_provider","Deterministic local")); self.history_provider.currentTextChanged.connect(self._autosave_provider_settings)
        nf.addRow("Recent History writer",self.history_provider)
        nnote=QLabel("Use OpenAI — testing override while local AI is unavailable. AI narration is fictional campaign flavor generated from the already-computed turn ledger."); nnote.setWordWrap(True); nnote.setObjectName("Muted"); narration.layout.addWidget(nnote); iv.addWidget(narration)

        status=Card("Provider status", info_text="This panel reports what the backend will use right now, so checked boxes and actual provider state cannot silently disagree.")
        self.provider_status=QLabel(); self.provider_status.setWordWrap(True); self.provider_status.setTextInteractionFlags(Qt.TextSelectableByMouse); status.layout.addWidget(self.provider_status)
        statusrow=QHBoxLayout(); test=QPushButton("Test / Start Local AI"); test.clicked.connect(self.test_local_ai); statusrow.addWidget(test); test_cloud=QPushButton("Test OpenAI"); test_cloud.clicked.connect(self.test_openai); statusrow.addWidget(test_cloud); statusrow.addStretch(1); status.layout.addLayout(statusrow); iv.addWidget(status)

        diagnostics=Card("Diagnostics", info_text="ElectionLab overwrites one latest-session log at every launch. It records timings, navigation, map clicks, provider failures, worker tasks and detected UI stalls without storing API-key values.")
        self.diagnostics_path_label=QLabel(str(self.diagnostics.path)); self.diagnostics_path_label.setObjectName("Muted"); self.diagnostics_path_label.setTextInteractionFlags(Qt.TextSelectableByMouse); self.diagnostics_path_label.setWordWrap(True); diagnostics.layout.addWidget(self.diagnostics_path_label)
        drow=QHBoxLayout(); openlog=QPushButton("Open Latest Session Log"); openlog.clicked.connect(self.open_latest_log); drow.addWidget(openlog); openfolder=QPushButton("Open Logs Folder"); openfolder.clicked.connect(self.open_logs_folder); drow.addWidget(openfolder); copylog=QPushButton("Copy Log Path"); copylog.clicked.connect(self.copy_log_path); drow.addWidget(copylog); drow.addStretch(1); diagnostics.layout.addLayout(drow)
        dnote=QLabel("If ElectionLab freezes, wait for it to recover, then send latest_session.log. The UI watchdog will record the stall duration and the action ElectionLab believed it was performing."); dnote.setObjectName("Muted"); dnote.setWordWrap(True); diagnostics.layout.addWidget(dnote); iv.addWidget(diagnostics)

        # Network/AI controls apply instantly; model/url text applies on editingFinished.
        for cb in [self.offline_lock,self.internet_research,self.openai_enabled,self.local_ai_enabled]:
            cb.stateChanged.connect(self._autosave_provider_settings)
        for edit in [self.openai_model,self.ollama_url,self.ollama_model,self.ollama_executable]:
            edit.editingFinished.connect(self._autosave_provider_settings)

        save=QPushButton("Save Storage + All Settings"); save.setObjectName("Primary"); save.clicked.connect(self.save_settings); iv.addWidget(save,0,Qt.AlignRight)
        self._update_provider_status()
        scroll.setWidget(inner);v.addWidget(scroll,1);return page

    def open_latest_log(self):
        path=Path(self.diagnostics.path)
        try:
            if os.name=="nt": os.startfile(str(path))  # type: ignore[attr-defined]
            else: QMessageBox.information(self,"Latest Session Log",str(path))
        except Exception as exc:
            QMessageBox.information(self,"Latest Session Log",f"{path}\n\nCould not launch the default viewer: {exc}")

    def open_logs_folder(self):
        folder=Path(self.diagnostics.path).parent
        try:
            if os.name=="nt": os.startfile(str(folder))  # type: ignore[attr-defined]
            else: QMessageBox.information(self,"Logs Folder",str(folder))
        except Exception as exc:
            QMessageBox.information(self,"Logs Folder",f"{folder}\n\nCould not open the folder: {exc}")

    def copy_log_path(self):
        QApplication.clipboard().setText(str(self.diagnostics.path))
        self.diagnostics.log("INFO","DIAGNOSTICS_PATH_COPIED")

    # ---------- data refresh ----------
    def _profile_names(self):
        return [p["canonical_name"] for p in self.vault.list_profiles(limit=1000)]

    def refresh_profiles(self):
        names = self._profile_names()
        for combo_name in ["sim_a","sim_avp","sim_b","sim_bvp","camp_a","camp_avp","camp_b","camp_bvp"]:
            combo = getattr(self, combo_name, None)
            if not combo:
                continue
            current = combo.currentText().strip()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(names)
            # Editable combo boxes otherwise jump to the alphabetically first
            # profile after every refresh, which looked like the app had chosen
            # Abraham Lincoln for every field. Keep an empty/typed selection.
            combo.setCurrentIndex(-1)
            if current:
                combo.setEditText(current)
            combo.blockSignals(False)

    def refresh_dashboard(self):
        if not hasattr(self, "metric_profiles"):
            return
        profiles=self.vault.list_profiles(limit=5000)
        camps=self.campaigns.list()
        saved_sims=self.simulation_archive.list()
        portrait_count=sum(1 for p in profiles if p.get("photo_path") and Path(p.get("photo_path")).exists())
        total=max(1,len(profiles))
        self.metric_profiles.value.setText(str(len(profiles))); self.metric_profiles.sub.setText("offline candidate/person profiles")
        self.metric_portraits.value.setText(f"{portrait_count}/{len(profiles)}"); self.metric_portraits.sub.setText(f"{portrait_count/total*100:.0f}% cached locally")
        self.metric_campaigns.value.setText(str(len(camps))); self.metric_campaigns.sub.setText(f"campaigns · {len(saved_sims)} saved election results")
        self.metric_state_data.value.setText("51/51"); self.metric_state_data.sub.setText("states + D.C. · 2024 ACS starter context")

        s=self.settings.settings
        network="OFFLINE LOCKED" if s.offline_lock else "NETWORK READY"
        ai=[]
        if s.local_ai_enabled: ai.append("Local AI enabled")
        if s.openai_enabled and load_api_key(): ai.append("OpenAI ready")
        elif s.openai_enabled: ai.append("OpenAI missing key")
        if not ai: ai.append("AI optional/off")
        self.dash_status.setText(f"{network}\n{self.settings.settings.default_mode}\n"+" · ".join(ai))

        c=self._campaign_by_id(self.active_campaign_id)
        self.dash_continue_btn.setEnabled(bool(c))
        if c:
            self.campaign_engine.ensure_state(c)
            nxt=self.campaign_engine.next_scheduled_event(c)
            moved=sorted(self.campaign_engine.state_agents.campaign_adjustments(c).items(), key=lambda kv:abs(kv[1]), reverse=True)[:3]
            move_bits=[]
            for code,val in moved:
                if abs(val)<.01: continue
                nm=self.campaign_engine.state_agents.states.get(code,{}).get("name",code)
                move_bits.append(f"{nm}: {'A' if val>=0 else 'B'} +{abs(val):.2f}")
            self.dash_active_campaign.setText(
                f"<b>{c.get('title','Campaign')}</b> · {c.get('branch_label','Main Timeline')}<br>"
                f"<b>Date:</b> {c.get('current_date')} &nbsp; <b>Status:</b> {str(c.get('status','in_progress')).replace('_',' ').title()}<br>"
                f"<b>Next:</b> {(nxt or {}).get('title','Election Day')} {(nxt or {}).get('date','')}<br>"
                f"<b>Momentum:</b> A {float(c.get('momentum_a',0)):+.1f} · B {float(c.get('momentum_b',0)):+.1f}<br>"
                + (f"<b>Largest state movement:</b> {' · '.join(move_bits)}" if move_bits else "State movement is still near the starting baseline.")
            )
        else:
            self.dash_active_campaign.setText("No campaign is currently active. Open one from Campaigns or create a new save.")

        local_desc="enabled" if s.local_ai_enabled else "disabled"
        openai_desc=("ready" if s.openai_enabled and load_api_key() and not s.offline_lock else "enabled, no key" if s.openai_enabled and not load_api_key() else "blocked by Offline Lock" if s.openai_enabled and s.offline_lock else "disabled")
        self.dash_readiness.setText(
            f"<b>Election engine:</b> local + ready<br>"
            f"<b>State context:</b> 2024 ACS starter pack loaded<br>"
            f"<b>Local AI:</b> {local_desc}<br>"
            f"<b>OpenAI:</b> {openai_desc}<br>"
            f"<b>Campaign history narration:</b> {getattr(s,'campaign_history_provider','Deterministic local')}<br><br>"
            f"<span style='color:#8f9bad'>AI providers add dialogue/narration; they are not required for the election calculations.</span>"
        )

        self.dash_recent_campaigns.clear()
        for camp in camps[:6]:
            item=QListWidgetItem(f"{camp.get('title','Campaign')}  ·  {camp.get('current_date','—')}  ·  {camp.get('branch_label','Main Timeline')}")
            item.setData(Qt.UserRole,camp); self.dash_recent_campaigns.addItem(item)
        if hasattr(self,"dash_recent_sims"):
            self.dash_recent_sims.clear()
            for sim in saved_sims[:6]:
                result=sim.get("result") or {}; a=(result.get("ticket_a") or {}).get("canonical_name") or "A"; b=(result.get("ticket_b") or {}).get("canonical_name") or "B"
                item=QListWidgetItem(f"{a} vs {b}  ·  {result.get('mode','—')}  ·  seed {result.get('seed','—')}")
                item.setData(Qt.UserRole,sim); self.dash_recent_sims.addItem(item)
        self._update_offline_badge()

    def _update_offline_badge(self):
        # The global sidebar badge was retired with the 0.11 game shell. Keep the
        # method for older refresh callers and surface network state in the main
        # menu/top bar instead.
        locked=bool(self.settings.settings.offline_lock)
        if hasattr(self,"offline_badge"):
            self.offline_badge.setText("● OFFLINE LOCK\nRemote AI/research blocked" if locked else "● NETWORK UNLOCKED\nProviders obey Settings")
        if hasattr(self,"shell_context") and self.root_stack.currentIndex()==1 and self.stack.currentIndex()!=3:
            self.shell_context.setText("OFFLINE LOCK" if locked else "")
        if hasattr(self,"menu_status"):
            self.refresh_main_menu()

    # ---------- simulation ----------
    def _get_or_make_profile(self, name: str):
        """Synchronous profile resolver retained for small setup actions."""
        return self._get_or_make_profile_worker(name, None)

    def _get_or_make_profile_worker(self, name: str, progress=None):
        """Resolve a profile without touching GUI widgets (safe in a worker thread)."""
        name=name.strip()
        if not name:
            raise RuntimeError("Both tickets need a presidential candidate.")
        p=self.vault.get_profile(name)
        if p:
            return p
        s=self.settings.settings
        if s.internet_research and not s.offline_lock:
            if progress: progress(f"Researching {name} and caching the profile…")
            try:
                p=self.profile_service.research_and_cache(name)
                if p:return p
            except Exception:
                pass
        if s.local_ai_enabled:
            if progress: progress(f"Building an offline profile for {name} with Local AI…")
            try:
                p=self.profile_service.local_enrich_and_cache(name)
                if p:return p
            except Exception:
                pass
        # Neutral local stub keeps the numerical engine usable when optional AI is absent.
        p={"canonical_name":name,"profile_type":"custom_unknown","source_type":"auto_local_stub","party":None,"home_state":None,"career":None,"national_appeal":0,"charisma":50,"debate_skill":50,"experience":50,"name_recognition":25,"confidence":0.1,"profile_status":"needs_enrichment","snapshot_date":datetime.now().date().isoformat()}
        self.vault.upsert_profile(p)
        return self.vault.get_profile(name) or p

    @staticmethod
    def _compose_ticket(pres, vp, party):
        vp=vp or {"canonical_name":"No VP","national_appeal":0,"charisma":50,"debate_skill":50,"experience":50,"name_recognition":0}
        out=copy.deepcopy(pres); out["party"]=party; out["display_name"]=f"{pres['canonical_name']} / {vp['canonical_name']}"
        for k in ["national_appeal","charisma","debate_skill","experience","name_recognition"]:
            pv=float(pres.get(k,0 if k=="national_appeal" else 50) or 0); vv=float(vp.get(k,0 if k=="national_appeal" else 50) or 0)
            out[k]=pv*0.82+vv*0.18
        out["vp_home_state"]=vp.get("home_state"); out["vp_name"]=vp.get("canonical_name"); return out

    def _simulation_job(self, params: dict, report):
        names=[params["a"],params.get("avp") or "",params["b"],params.get("bvp") or ""]
        resolved=[]
        labels=["Ticket A president","Ticket A vice president","Ticket B president","Ticket B vice president"]
        for idx,(name,label) in enumerate(zip(names,labels)):
            if not name:
                resolved.append(None); continue
            report(4 + idx*5, f"Preparing {label}: {name}")
            resolved.append(self._get_or_make_profile_worker(name, lambda msg, pct=4+idx*5: report(pct,msg)))
        pa,pva,pb,pvb=resolved
        a=self._compose_ticket(pa,pva,params["party_a"]); b=self._compose_ticket(pb,pvb,params["party_b"])
        if a["canonical_name"].lower()==b["canonical_name"].lower():
            raise RuntimeError("Ticket A and Ticket B need different presidential candidates.")
        cfg=SimulationConfig(params["mode"],params["runs"],params["seed"],params["factors"],params["environment"])
        report(25, f"Running {cfg.runs:,} simulated elections…")
        result=self.engine.run(a,b,cfg,lambda pct,msg: report(25 + int(pct*.73),msg))
        report(100,"Results ready.")
        return result

    def run_simulation(self):
        if self._simulation_thread and self._simulation_thread.isRunning():
            return
        a=self.sim_a.currentText().strip(); b=self.sim_b.currentText().strip()
        if not a or not b:
            QMessageBox.warning(self,"Candidates Required","Choose or type both presidential candidates first."); return
        params={
            "a":a,"avp":self.sim_avp.currentText().strip(),"b":b,"bvp":self.sim_bvp.currentText().strip(),
            "party_a":self.sim_aparty.currentText(),"party_b":self.sim_bparty.currentText(),
            "mode":self.sim_mode.currentText(),"runs":self.sim_runs.value(),
            "seed":self.sim_seed.text().strip() or make_seed(),
            "environment":self.sim_environment.value(),
            "factors":{k:c.isChecked() for k,c in self.factor_checks.items()},
        }
        self.sim_seed.setText(params["seed"])
        self.diagnostics.log("INFO","SIMULATION_REQUESTED",ticket_a=a,ticket_b=b,mode=params["mode"],runs=params["runs"],seed=params["seed"])
        self.run_btn.setEnabled(False)
        self.run_status.setText("Simulation running in the background…")
        self.busy_overlay.begin("Simulating Election", "Preparing candidates and election model…", 1)
        self._simulation_thread=ProgressThread(lambda report:self._simulation_job(params,report),self)
        self._simulation_thread.progress.connect(self._simulation_progress)
        self._simulation_thread.done.connect(self._simulation_done)
        self._simulation_thread.failed.connect(self._simulation_failed)
        self._simulation_thread.finished.connect(self._simulation_thread_finished)
        self._simulation_thread.start()

    def _simulation_progress(self,percent,message):
        self.busy_overlay.set_progress(percent,message)
        self.run_status.setText(message)

    def _simulation_done(self,result):
        self.busy_overlay.finish(); self.run_btn.setEnabled(True)
        self.diagnostics.log("INFO","SIMULATION_COMPLETE",seed=result.get("seed"),runs=result.get("runs"),expected_ev_a=round(float(result.get("expected_ev_a",0)),1),expected_ev_b=round(float(result.get("expected_ev_b",0)),1))
        self.last_result=result
        self.refresh_profiles()
        self.show_results(result)
        self.run_status.setText("Complete. Same seed + settings reproduces this universe.")

    def _simulation_failed(self,message):
        self.busy_overlay.finish(); self.run_btn.setEnabled(True)
        self.diagnostics.log("ERROR","SIMULATION_FAILED",error=str(message))
        self.run_status.setText("Simulation failed.")
        QMessageBox.critical(self,"Simulation Error",message)

    def _simulation_thread_finished(self):
        self._simulation_thread=None

    def show_results(self,r):
        self.results_card.setVisible(True); a=r["ticket_a"]["display_name"]; b=r["ticket_b"]["display_name"]
        self.res_a.label.setText(a); self.res_a.value.setText(f"{r['expected_ev_a']:.0f} EV"); self.res_a.sub.setText(f"median: {r['median_ev_a']} electoral votes")
        self.res_b.label.setText(b); self.res_b.value.setText(f"{r['expected_ev_b']:.0f} EV"); self.res_b.sub.setText(f"median: {r['median_ev_b']} electoral votes")
        self.res_prob.value.setText(f"A {r['a_presidency_prob']*100:.1f}%"); self.res_prob.sub.setText(f"B {r['b_presidency_prob']*100:.1f}% · {r['runs']:,} simulated elections")
        m=r['avg_popular_margin_a']; self.res_pop.value.setText(("A +" if m>=0 else "B +")+f"{abs(m):.1f}"); self.res_pop.sub.setText("modeled, not a real poll")
        insights=r.get("insights") or {}
        tip=insights.get("tipping_point") or {}; tm=float(tip.get("margin_a",0) or 0)
        self.insight_tipping.value.setText(tip.get("code") or "—"); self.insight_tipping.sub.setText((tip.get("name") or "No tipping point") + ((" · A +" if tm>=0 else " · B +")+f"{abs(tm):.1f}" if tip else ""))
        close=insights.get("closest_state") or {}; cm=float(close.get("margin_a",0) or 0)
        self.insight_closest.value.setText(close.get("code") or "—"); self.insight_closest.sub.setText((close.get("name") or "—") + ((" · A +" if cm>=0 else " · B +")+f"{abs(cm):.1f}" if close else ""))
        bg=list(insights.get("battlegrounds") or []); self.insight_battlegrounds.value.setText(str(insights.get("battleground_count",len(bg)))); self.insight_battlegrounds.sub.setText(", ".join(bg[:8]) + ("…" if len(bg)>8 else "") if bg else "No states within 5 points")
        dep=insights.get("biggest_departure") or {}; dm=float(dep.get("margin_a",0) or 0); db=float(dep.get("baseline_component",0) or 0); self.insight_departure.value.setText(dep.get("code") or "—"); self.insight_departure.sub.setText(f"{dep.get('name','—')} · modeled {dm:+.1f} vs baseline component {db:+.1f}" if dep else "—")
        self.ev_score.set_scores(r["expected_ev_a"],r["expected_ev_b"],a,b); self.electoral_grid.set_results(r["states"],a,b)
        self.election_overview.setText(f"<b>Local model recap:</b> {r.get('local_overview','No recap available.')}<br><br><span style='color:#8f9bad'>This recap is generated locally from the numerical result. Optional AI can explain it, but does not recalculate the winner.</span>")
        rows=sorted(r["states"],key=lambda x:abs(x["a_win_prob"]-.5)); self.state_table.setSortingEnabled(False); self.state_table.setRowCount(len(rows))
        for i,s in enumerate(rows):
            p=s["a_win_prob"]; margin=s["avg_margin_a"]; rating="Tossup" if .45<=p<=.55 else ("Lean A" if p>.5 and p<.7 else "Likely A" if p<.85 and p>.5 else "Safe A" if p>=.85 else "Lean B" if p>.3 else "Likely B" if p>.15 else "Safe B")
            vals=[
                SortableTableItem(s["name"],s["name"]),
                SortableTableItem(str(s["ev"]),float(s["ev"])),
                SortableTableItem(f"{p*100:.1f}%",float(p)),
                SortableTableItem(("A +" if margin>=0 else "B +")+f"{abs(margin):.1f}",float(margin)),
                SortableTableItem(rating,rating),
            ]
            for j,item in enumerate(vals):self.state_table.setItem(i,j,item)
        self.state_table.setSortingEnabled(True)
        self.show_state_detail(rows[0]); self.results_card.ensurePolished()

    def _state_table_clicked(self, row: int, _column: int):
        if not self.last_result:
            return
        item = self.state_table.item(row, 0)
        if not item:
            return
        name = item.text()
        for state in self.last_result.get("states", []):
            if state.get("name") == name:
                self.show_state_detail(state)
                break

    def show_state_detail(self,s):
        code=str((s or {}).get("code") or "?")
        action=f"RESULT_STATE_CLICK:{code}"
        self.diagnostics.set_ui_action(action); started=time.perf_counter()
        try:
            return self._show_state_detail_impl(s)
        finally:
            self.diagnostics.log("INFO","RESULT_STATE_DETAIL_DONE",state=code,duration_ms=round((time.perf_counter()-started)*1000,1))
            QTimer.singleShot(850,lambda:self.diagnostics.clear_ui_action(action))

    def _show_state_detail_impl(self,s):
        if not self.last_result:
            return
        a=self.last_result["ticket_a"]["display_name"]; b=self.last_result["ticket_b"]["display_name"]; m=s["avg_margin_a"]
        leader=a if m>=0 else b
        baseline=float(s.get("dem_margin_2024",0))
        baseline_side="Democratic" if baseline>=0 else "Republican"
        self.electoral_grid.select_state(s.get("code"))
        ctx=s.get("state_context") or {}
        priorities=ctx.get("top_issues") or []
        priority_text=", ".join(priorities) if priorities else "No issue-priority context loaded"
        data_bits=[]
        if ctx.get("median_household_income") is not None: data_bits.append(f"median household income ~${float(ctx['median_household_income']):,.0f}")
        if ctx.get("median_gross_rent") is not None: data_bits.append(f"median gross rent ~${float(ctx['median_gross_rent']):,.0f}/month")
        if ctx.get("acs_unemployment_rate") is not None: data_bits.append(f"ACS unemployment estimate {float(ctx['acs_unemployment_rate']):.1f}%")
        self.state_detail.setText(
            f"<span style='font-size:14pt;font-weight:700'>{s['name']}</span>"
            f"<br><span style='color:#9fb0c6'>{s['ev']} electoral votes</span><br><br>"
            f"<b>Modeled leader:</b> {leader} by {abs(m):.1f} percentage points<br>"
            f"<b>{a} win probability:</b> {s['a_win_prob']*100:.1f}%<br>"
            f"<b>Starter state baseline:</b> {baseline_side} +{abs(baseline):.1f} points<br><br>"
            f"<b>Why the model landed here</b><br>{s.get('reason','No local explanation available.')}<br><br>"
            f"<b>State context</b><br>Top modeled priorities: {priority_text}"
            + (f"<br>{' • '.join(data_bits)}" if data_bits else "")
            + "<br><span style='color:#8f9bad'>Economic context comes from the bundled 2024 ACS snapshot. Issue-priority weights are transparent ElectionLab heuristics, not state opinion polling. In campaign mode those priorities affect how strongly campaign messages move each state.</span>"
            + "<br><br><span style='color:#8f9bad'>Maine/Nebraska district allocation is still planned for 1.0.</span>"
        )

    def save_simulation_result(self):
        if not self.last_result:return
        saved=self.simulation_archive.save(self.last_result)
        QMessageBox.information(self,"Result Saved",f"Saved to the portable ElectionLab simulation archive:\n{saved.get('_path','')}")
        self.refresh_dashboard()

    def export_simulation_result(self):
        if not self.last_result:return
        a=(self.last_result.get("ticket_a") or {}).get("canonical_name") or "Ticket-A"
        b=(self.last_result.get("ticket_b") or {}).get("canonical_name") or "Ticket-B"
        default=self.settings.path_for("Exports") / f"{a}-vs-{b}-{self.last_result.get('seed','result')}.json"
        path,_=QFileDialog.getSaveFileName(self,"Export Election Result",str(default),"JSON files (*.json)")
        if not path:return
        self.simulation_archive.export_result(self.last_result,path)
        QMessageBox.information(self,"Export Complete",f"Election result exported to:\n{path}")

    def rematch_new_seed(self):
        if not self.last_result:return
        self.sim_seed.setText(make_seed())
        self.run_simulation()

    def generate_ai_overview(self):
        if not self.last_result:
            return
        self._autosave_provider_settings()
        self.ai_overview_btn.setEnabled(False)
        pref=self.overview_provider.currentText()
        self._interaction_thread=ResearchThread(lambda:self.debate_service.election_overview(self.last_result,pref),self)
        self._interaction_thread.done.connect(self._ai_overview_done)
        self._interaction_thread.failed.connect(self._ai_overview_failed)
        self._interaction_thread.start()

    def _ai_overview_done(self,result):
        self.ai_overview_btn.setEnabled(True)
        local=self.last_result.get("local_overview","") if self.last_result else ""
        self.election_overview.setText(
            f"<b>Local model recap:</b> {local}<br><br>"
            f"<b>AI interpretation [{result.get('provider','AI')}]:</b><br>{result.get('reply','')}<br><br>"
            f"<span style='color:#8f9bad'>The AI explained an already-computed result. It did not choose the winner or modify state margins.</span>"
        )

    def _ai_overview_failed(self,msg):
        self.diagnostics.log("ERROR","AI_OVERVIEW_FAILED",error=str(msg))
        self.ai_overview_btn.setEnabled(True)
        QMessageBox.warning(self,"AI Overview Unavailable",f"ElectionLab still has the local deterministic recap. The optional AI explanation could not run.\n\n{msg}")

    # ---------- campaigns ----------
    def _campaign_by_id(self, campaign_id: str | None):
        if not campaign_id:
            return None
        if self._active_campaign_obj is not None and self._active_campaign_obj.get("id") == campaign_id:
            return self._active_campaign_obj
        started=time.perf_counter()
        for c in self.campaigns.list():
            if c.get("id") == campaign_id:
                if campaign_id == self.active_campaign_id:
                    self._active_campaign_obj = c
                self.diagnostics.log("DEBUG","CAMPAIGN_DISK_LOOKUP",campaign_id=campaign_id,duration_ms=round((time.perf_counter()-started)*1000,1))
                return c
        self.diagnostics.log("WARNING","CAMPAIGN_LOOKUP_MISS",campaign_id=campaign_id,duration_ms=round((time.perf_counter()-started)*1000,1))
        return None

    def _selected_library_campaign(self):
        if not hasattr(self, "campaign_list"):
            return None
        item = self.campaign_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _campaign_create_job(self, params: dict, report):
        resolved=[]
        for idx,name in enumerate([params["a"],params.get("avp") or "",params["b"],params.get("bvp") or ""]):
            if not name:resolved.append(None);continue
            report(10+idx*15,f"Preparing campaign candidate: {name}")
            resolved.append(self._get_or_make_profile_worker(name,lambda msg,pct=10+idx*15:report(pct,msg)))
        pa,pva,pb,pvb=resolved
        if pa["canonical_name"].lower()==pb["canonical_name"].lower():raise RuntimeError("Ticket A and Ticket B need different presidential candidates.")
        report(78,"Creating persistent campaign timeline…")
        rules=params.get("rules") or preset_rules(params.get("rules_preset") or "Campaign")
        payload={
            "seed":params["seed"],"detail_level":params["detail_level"],"agency":params["agency"],
            "simulation_mode":rules.get("simulation_mode") or self.settings.settings.default_mode,
            "rules_preset":params.get("rules_preset") or "Campaign",
            "rules_modified":bool(params.get("rules_modified")),
            "rules":rules,
            "ticket_a":{"president":pa["canonical_name"],"vp":pva["canonical_name"] if pva else None,"party":params["party_a"]},
            "ticket_b":{"president":pb["canonical_name"],"vp":pvb["canonical_name"] if pvb else None,"party":params["party_b"]},
            "pace_can_change_mid_campaign":True,"status":"in_progress",
        }
        camp=self.campaigns.create(params["title"],payload)
        report(100,"Campaign ready.")
        return camp

    def create_campaign(self):
        if self._campaign_create_thread and self._campaign_create_thread.isRunning():return
        a=self.camp_a.currentText().strip(); b=self.camp_b.currentText().strip()
        if not a or not b:
            QMessageBox.warning(self,"Candidates Required","Choose or type both presidential candidates before creating the campaign.");return
        rules=self._campaign_rules_from_ui(); preset_name=self.camp_rules_preset.currentText()
        params={"title":self.camp_title.text().strip() or "Campaign","a":a,"avp":self.camp_avp.currentText().strip(),"b":b,"bvp":self.camp_bvp.currentText().strip(),"party_a":self.camp_aparty.currentText(),"party_b":self.camp_bparty.currentText(),"seed":self.camp_seed.text().strip() or make_seed(),"detail_level":self.camp_detail.currentText(),"agency":self.camp_agency.currentText(),"rules_preset":preset_name,"rules_modified":modified_from_preset(preset_name,rules),"rules":rules}
        self.camp_seed.setText(params["seed"]); self.create_campaign_btn.setEnabled(False)
        self.busy_overlay.begin("Creating Campaign","Preparing candidates and campaign timeline…",2)
        self._campaign_create_thread=ProgressThread(lambda report:self._campaign_create_job(params,report),self)
        self._campaign_create_thread.progress.connect(lambda p,m:self.busy_overlay.set_progress(p,m))
        self._campaign_create_thread.done.connect(self._campaign_create_done)
        self._campaign_create_thread.failed.connect(self._campaign_create_failed)
        self._campaign_create_thread.finished.connect(self._campaign_create_finished)
        self._campaign_create_thread.start()

    def _campaign_create_done(self,camp):
        self.busy_overlay.finish(); self.create_campaign_btn.setEnabled(True); self.active_campaign_id=camp.get("id"); self._active_campaign_obj=camp
        self.refresh_profiles(); self.refresh_campaigns(); self.refresh_campaign_hq(); self.refresh_dashboard(); self.refresh_main_menu()
        self.diagnostics.log("INFO","NEW_GAME_STARTED",campaign_id=camp.get("id"),rules_preset=camp.get("rules_preset"),rules_modified=camp.get("rules_modified"),seed=camp.get("seed"))
        self.go(3)

    def _campaign_create_failed(self,message):
        self.busy_overlay.finish(); self.create_campaign_btn.setEnabled(True); QMessageBox.critical(self,"Campaign Error",message)

    def _campaign_create_finished(self):
        self._campaign_create_thread=None

    def refresh_campaigns(self):
        if not hasattr(self, "campaign_list"):
            return
        selected_id = None
        current = self.campaign_list.currentItem()
        if current and current.data(Qt.UserRole):
            selected_id = current.data(Qt.UserRole).get("id")
        self.campaign_list.clear(); match_item = None
        for c in self.campaigns.list():
            title = c.get("title", "Campaign")
            rules_label=f"{c.get('rules_preset','Campaign')}{'*' if c.get('rules_modified') else ''}"
            meta = f"{c.get('branch_label','Main Timeline')}  •  {rules_label}  •  {c.get('detail_level','')}  •  {c.get('agency','')}"
            it = QListWidgetItem(f"{title}\n{meta}"); it.setData(Qt.UserRole, c)
            it.setToolTip(f"Seed: {c.get('seed','—')}\nStatus: {c.get('status','—')}\nUpdated: {c.get('updated_at','—')}")
            self.campaign_list.addItem(it)
            if selected_id and c.get("id") == selected_id: match_item = it
            elif not selected_id and self.active_campaign_id and c.get("id") == self.active_campaign_id: match_item = it
        if match_item: self.campaign_list.setCurrentItem(match_item)
        elif self.campaign_list.count(): self.campaign_list.setCurrentRow(0)
        else:
            self.open_hq_btn.setEnabled(False); self.branch_btn.setEnabled(False); self.delete_campaign_btn.setEnabled(False)
            self.campaign_info.setText("No campaigns saved yet.")

    def _campaign_selected(self,item,*_):
        enabled = bool(item)
        self.open_hq_btn.setEnabled(enabled); self.branch_btn.setEnabled(enabled); self.delete_campaign_btn.setEnabled(enabled)
        if not item:
            self.campaign_info.setText("Select a campaign to inspect it.")
            return
        c=item.data(Qt.UserRole); self.campaign_engine.ensure_state(c)
        ta=c.get('ticket_a',{}); tb=c.get('ticket_b',{})
        self.campaign_info.setText(
            f"<b>{c.get('branch_label','Main Timeline')}</b><br>"
            f"<span style='color:#9aa9bd'>Date</span> &nbsp; {c.get('current_date')} → {c.get('election_date')}<br>"
            f"<span style='color:#9aa9bd'>Ticket A</span> &nbsp; {ta.get('president') or '—'} / {ta.get('vp') or 'No VP'}<br>"
            f"<span style='color:#9aa9bd'>Ticket B</span> &nbsp; {tb.get('president') or '—'} / {tb.get('vp') or 'No VP'}<br>"
            f"<span style='color:#9aa9bd'>Status</span> &nbsp; {c.get('status','in progress').replace('_',' ').title()}<br>"
            f"<span style='color:#9aa9bd'>Rules</span> &nbsp; {c.get('rules_preset','Campaign')}{' · Modified' if c.get('rules_modified') else ' · Official'}<br>"
            f"<span style='color:#9aa9bd'>Seed</span> &nbsp; {c.get('seed','—')}"
        )

    def open_campaign_hq(self):
        c=self._selected_library_campaign()
        if not c:return
        self.active_campaign_id=c.get("id")
        self._active_campaign_obj=c
        self.go(3)

    def delete_campaign(self):
        c=self._selected_library_campaign()
        if not c:return
        result=QMessageBox.warning(self,"Delete Campaign Save",f"Permanently delete this local save?\n\n{c.get('title')}",QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)
        if result != QMessageBox.Yes:return
        if self.campaigns.delete(c):
            if self.active_campaign_id == c.get("id"): self.active_campaign_id=None; self._active_campaign_obj=None
            self.refresh_campaigns(); self.refresh_campaign_hq(); self.refresh_dashboard(); self.refresh_main_menu()
        else:
            QMessageBox.warning(self,"Delete Failed","ElectionLab could not find the selected save file.")

    def branch_campaign(self):
        c=self._selected_library_campaign()
        if not c:return
        label=f"Branch {len(self.campaigns.list())+1}"
        child=self.campaigns.branch(c,label); self.active_campaign_id=child.get("id"); self._active_campaign_obj=child; self.refresh_campaigns(); self.refresh_campaign_hq()
        QMessageBox.information(self,"Timeline Branched",f"Created {child['title']}")

    def branch_campaign_hq(self):
        c=self._campaign_by_id(self.active_campaign_id)
        if not c:return
        label=f"Branch {len(self.campaigns.list())+1}"
        child=self.campaigns.branch(c,label); self.active_campaign_id=child.get("id"); self._active_campaign_obj=child
        self.refresh_campaigns(); self.refresh_campaign_hq()
        QMessageBox.information(self,"Timeline Branched",f"Now playing {child['title']}")

    def _timeline_event_html(self, event: dict) -> str:
        kind = event.get("type")
        if kind == "campaign_turn":
            headlines = " • ".join(e.get("headline", "") for e in event.get("events", []))
            narrative=event.get("ai_narrative")
            if narrative:
                headlines=f"<span style='color:#dbe7f8'>{html.escape(str(narrative)).replace(chr(10),'<br>')}</span><br><span style='color:#71829a;font-size:8pt'>Narrated by {html.escape(str(event.get('narrative_provider','AI')))} from the already-computed turn ledger</span>"
            effects=event.get("state_agent_effects") or {}
            response=[]
            for side in ["A","B"]:
                top=(effects.get(side) or {}).get("largest_effects") or []
                if top:
                    response.append(f"{side}: "+", ".join(f"{x.get('state')} {float(x.get('delta_a',0)):+.2f}" for x in top[:3]))
            extra=f"<br><span style='color:#8f9bad'>State response — {' • '.join(response)}</span>" if response else ""
            return f"<b>{event.get('to_date')}</b><br>{headlines}{extra}"
        if kind == "milestone_reached":
            return f"<b>{event.get('date','')}</b> · <b>Major event reached</b><br>{event.get('headline','Campaign event')}"
        if kind == "debate_exchange":
            return f"<b>Debate completed</b> — {event.get('headline','Exchange completed')}<br>You {event.get('user_score','—')} • Opponent {event.get('opponent_score','—')}"
        if kind == "debate_auto":
            return f"<b>Debate auto-simulated</b> — {event.get('headline','Debate completed')}<br>A {event.get('score_a','—')} • B {event.get('score_b','—')}"
        if kind == "debate_skipped":
            return f"<b>{event.get('date','')}</b> · Debate skipped"
        if kind in {"conversation_exchange", "advisor_exchange"}:
            role = event.get("role") or "Campaign adviser"
            meta=event.get("constituent") or {}
            if meta: role += f" · {meta.get('state_name',meta.get('state_code',''))} · {meta.get('issue','')}"
            reply = event.get("reply") or event.get("advisor_reply") or ""
            return f"<b>{role}</b> — {event.get('user_message','')[:90]}<br><span style='color:#8f9bad'>{reply[:190]}</span>"
        if kind == "campaign_operation":
            movement = event.get("largest_effects") or []
            moved = ", ".join(f"{x.get('state')} {float(x.get('delta_a',0)):+.2f}" for x in movement[:3]) or "state pulse held steady"
            money = f"raised {float(event.get('funds_gained',0)):.1f}" if float(event.get("funds_gained",0) or 0) > 0 else f"cost {float(event.get('cost',0)):.1f}"
            return f"<b>{event.get('date','')} · Ticket {event.get('side','')} {event.get('operation','Campaign operation')}</b><br>{event.get('region','National')} · {event.get('message','')} · {money} · momentum {float(event.get('momentum_delta',0)):+.2f}<br><span style='color:#8f9bad'>{moved}</span>"
        if kind == "state_operation":
            delta=float(event.get("delta_a",0) or 0); direction="A" if delta>=0 else "B"
            return f"<b>{event.get('date','')} · {event.get('operation','State operation')} in {event.get('state_name',event.get('state',''))}</b><br>{event.get('message','')} · movement {direction} +{abs(delta):.2f} · cost {float(event.get('cost',0)):.1f}"
        if kind == "branch_created":
            return f"<b>Timeline branched</b> — {event.get('label','Branch')}"
        if kind == "milestone_resolved":
            return f"<b>{event.get('headline','Event')}</b> — {event.get('resolution','resolved').replace('_',' ').title()}"
        if kind == "election_day_result":
            return f"<b>Election Day</b><br>{event.get('headline','Campaign election completed')}"
        return ""

    @staticmethod
    def _modern_party_code(party: str | None) -> str | None:
        p=(party or "").strip().lower()
        if p=="democratic":return "D"
        if p=="republican":return "R"
        return None

    def _campaign_map_snapshot(self, campaign: dict) -> list[dict]:
        """Cheap live state pulse for Campaign HQ; no Monte Carlo/AI call required."""
        self.campaign_engine.ensure_state(campaign)
        ta=campaign.get("ticket_a") or {}; tb=campaign.get("ticket_b") or {}
        pa=self.vault.get_profile(ta.get("president") or "") or {}
        pb=self.vault.get_profile(tb.get("president") or "") or {}
        party_a=self._modern_party_code(ta.get("party") or pa.get("party"))
        party_b=self._modern_party_code(tb.get("party") or pb.get("party"))
        adj=self.campaign_engine.state_agents.campaign_adjustments(campaign)
        national=(float(campaign.get("momentum_a",0))-float(campaign.get("momentum_b",0)))*0.18
        rows=[]
        for code,ctx in self.campaign_engine.state_agents.states.items():
            dem=float(ctx.get("dem_margin_2024",0))
            if party_a=="D" and party_b=="R":base=dem
            elif party_a=="R" and party_b=="D":base=-dem
            else:base=0.0
            movement=float(adj.get(code,0))
            margin=base+movement+national
            # Smooth display probability, not a Monte Carlo forecast. A ~4.5 point scale
            # prevents the live map from looking falsely certain after tiny movements.
            prob=1.0/(1.0+math.exp(-margin/4.5))
            rows.append({
                "code":code,"name":ctx.get("name",code),"ev":int(ctx.get("ev",0)),
                "avg_margin_a":margin,"a_win_prob":prob,"dem_margin_2024":dem,
                "campaign_movement_a":movement,"state_context":ctx,
                "reason":self.campaign_engine.state_agents.state_reason(code,campaign),
            })
        return rows

    def show_campaign_state_detail(self, state: dict):
        code=str((state or {}).get("code") or "?")
        action=f"CAMPAIGN_STATE_CLICK:{code}"
        self.diagnostics.set_ui_action(action); started=time.perf_counter()
        try:
            return self._show_campaign_state_detail_impl(state)
        finally:
            self.diagnostics.log("INFO","CAMPAIGN_STATE_DETAIL_DONE",state=code,duration_ms=round((time.perf_counter()-started)*1000,1))
            QTimer.singleShot(850,lambda:self.diagnostics.clear_ui_action(action))

    def _show_campaign_state_detail_impl(self, state: dict):
        c=self._campaign_by_id(self.active_campaign_id)
        if not c or not hasattr(self,"hq_state_detail"):
            return
        code=state.get("code"); self._hq_selected_state_code=code; ctx=self.campaign_engine.state_agents.context_for(code,c)
        opinion=ctx.get("campaign_opinion") or {}
        priorities=ctx.get("issue_priorities") or {}
        ordered=sorted(priorities.items(),key=lambda kv:float(kv[1]),reverse=True)
        priority_lines="<br>".join(f"• <b>{issue}</b> — salience {float(weight):.2f}" for issue,weight in ordered[:5]) or "No priority data loaded."
        hits_a=opinion.get("issue_hits_a") or {}; hits_b=opinion.get("issue_hits_b") or {}
        def hit_text(d):
            return ", ".join(f"{k} {float(v):.1f}" for k,v in sorted(d.items(),key=lambda kv:float(kv[1]),reverse=True)[:4]) or "none yet"
        margin=float(state.get("avg_margin_a",0)); leader="Ticket A" if margin>=0 else "Ticket B"
        self.hq_campaign_map.select_state(code)
        self.hq_state_detail.setText(
            f"<span style='font-size:15pt;font-weight:700'>{ctx.get('name',code)}</span> "
            f"<span style='color:#8fa3bf'>({code}) · {ctx.get('ev','—')} EV</span><br><br>"
            f"<b>Current campaign pulse:</b> {leader} by ~{abs(margin):.1f} points<br>"
            f"<b>Campaign-driven movement:</b> {float(opinion.get('support_delta_a',0)):+.2f} points toward Ticket A<br>"
            f"<b>Attention:</b> A {float(opinion.get('attention_a',0)):.1f} · B {float(opinion.get('attention_b',0)):.1f}<br><br>"
            f"<b>Modeled priorities</b><br>{priority_lines}<br><br>"
            f"<b>Messages actually targeted here</b><br>Ticket A: {hit_text(hits_a)}<br>Ticket B: {hit_text(hits_b)}<br><br>"
            f"<b>Real-data context</b><br>Median household income: ${float(ctx.get('median_household_income',0)):,.0f}<br>"
            f"Median gross rent: ${float(ctx.get('median_gross_rent',0)):,.0f}/month<br>"
            f"ACS unemployment estimate: {float(ctx.get('acs_unemployment_rate',0)):.1f}%<br>"
            f"2024 Democratic margin baseline: {float(ctx.get('dem_margin_2024',0)):+.1f}<br><br>"
            f"<span style='color:#8f9bad'>The economic indicators are sourced from the bundled 2024 ACS snapshot. Priority/salience scores and this live campaign pulse are ElectionLab model outputs, not state opinion polls. Future sourced issue polling can replace or supplement these heuristics.</span>"
        )

    def _campaign_operation_allowed(self, c: dict, operation: str) -> bool:
        spec = CAMPAIGN_OPERATION_SPECS.get(operation) or {}
        rule = str(spec.get("rule") or "")
        return rule_enabled(c, "campaign", rule, True) if rule else True

    def _update_campaign_operation_hint(self, c: dict | None = None, can_operate: bool | None = None):
        if not hasattr(self, "campaign_operation_status"):
            return
        c = c or self._campaign_by_id(self.active_campaign_id)
        if not c:
            self.campaign_operation_btn.setEnabled(False)
            self.campaign_operation_status.setText("Open a campaign to run operations.")
            return
        self.campaign_engine.ensure_state(c)
        operation = self.campaign_operation_type.currentText()
        region = self.campaign_operation_region.currentText()
        spec = CAMPAIGN_OPERATION_SPECS.get(operation) or {}
        agency = str(c.get("agency") or "Spectate")
        if can_operate is None:
            can_operate = agency != "Spectate" and not bool(c.get("pending_event")) and c.get("status") not in {"completed", "election_day_ready"}
        allowed = self._campaign_operation_allowed(c, operation)
        resources_on = rule_enabled(c, "campaign", "resources", True)
        raw_cost = float(spec.get("national_cost", spec.get("cost", 0.0)) if region == "National" else spec.get("cost", 0.0))
        cost = raw_cost if resources_on else 0.0
        gain_min = float(spec.get("funds_min", 0.0) or 0.0)
        gain_max = float(spec.get("funds_max", 0.0) or 0.0)
        cost_text = f"Cost {cost:.1f}"
        if gain_max > 0 and resources_on:
            cost_text = f"Raises about {gain_min:.0f}-{gain_max:.0f} funds"
        elif not resources_on:
            cost_text = "Resource costs disabled by rules"
        if agency == "Spectate":
            status = "Operations are disabled while spectating."
        elif c.get("pending_event"):
            status = "Resolve the current major event before running operations."
        elif c.get("status") in {"completed", "election_day_ready"}:
            status = "Campaign operations are closed for Election Day."
        elif not allowed:
            status = f"{operation} is disabled by this campaign's ruleset."
        else:
            status = f"{operation} in {region}: {cost_text}. Applies deterministic momentum and state-pulse effects."
        self.campaign_operation_status.setText(status)
        self.campaign_operation_btn.setEnabled(bool(can_operate and allowed))

    def run_campaign_operation(self):
        c = self._campaign_by_id(self.active_campaign_id)
        if not c:
            return
        agency = str(c.get("agency") or "Spectate")
        if agency == "Spectate":
            QMessageBox.information(self, "Spectator Campaign", "Campaign operations are disabled while spectating.")
            return
        requested = "A" if self.campaign_operation_side.currentText() == "Ticket A" else "B"
        if agency == "Play Ticket A" and requested != "A":
            QMessageBox.information(self, "Agency", "This save is set to Play Ticket A.")
            return
        if agency == "Play Ticket B" and requested != "B":
            QMessageBox.information(self, "Agency", "This save is set to Play Ticket B.")
            return
        operation = self.campaign_operation_type.currentText()
        region = self.campaign_operation_region.currentText()
        message = self.campaign_operation_message.currentText()
        tone = self.campaign_operation_tone.currentText()
        action = f"CAMPAIGN_OPERATION:{requested}:{operation}"
        self.diagnostics.set_ui_action(action)
        started = time.perf_counter()
        try:
            result = self.campaign_engine.run_campaign_operation(c, requested, operation, region, message, tone)
            self.campaign_engine.generate_poll_snapshot(c, force=True)
            self.campaigns.save(c)
            self._active_campaign_obj = c
            moved = result.get("largest_effects") or []
            if moved:
                movement = " • ".join(f"{x.get('state')} {float(x.get('delta_a',0)):+.2f}" for x in moved[:3])
            else:
                movement = "no state movement"
            fund_text = f"cost {float(result.get('cost',0)):.1f}"
            if float(result.get("funds_gained", 0) or 0) > 0:
                fund_text = f"raised {float(result.get('funds_gained',0)):.1f}"
            self.campaign_operation_status.setText(
                f"{operation} complete: {fund_text}; momentum {float(result.get('momentum_delta',0)):+.2f}; {movement}."
            )
            self.diagnostics.log("INFO", "CAMPAIGN_OPERATION_COMPLETE", campaign_id=c.get("id"), operation_result=result)
            self.refresh_campaign_hq()
            self.refresh_dashboard()
        except Exception as exc:
            self.diagnostics.exception("CAMPAIGN_OPERATION_FAILED", exc, operation=operation, region=region)
            QMessageBox.warning(self, "Campaign Operation Failed", str(exc))
        finally:
            self.diagnostics.log("DEBUG", "CAMPAIGN_OPERATION_UI_DONE", duration_ms=round((time.perf_counter() - started) * 1000, 1))
            QTimer.singleShot(850, lambda: self.diagnostics.clear_ui_action(action))

    def run_state_operation(self):
        c=self._campaign_by_id(self.active_campaign_id)
        code=self._hq_selected_state_code
        if not c or not code:
            QMessageBox.information(self,"Choose a State","Click a state on the live campaign map first.")
            return
        agency=str(c.get("agency") or "Spectate")
        if agency=="Spectate":
            QMessageBox.information(self,"Spectator Campaign","State operations are disabled while spectating.")
            return
        requested="A" if self.hq_operation_side.currentText()=="Ticket A" else "B"
        if agency=="Play Ticket A" and requested!="A":
            QMessageBox.information(self,"Agency","This save is set to Play Ticket A."); return
        if agency=="Play Ticket B" and requested!="B":
            QMessageBox.information(self,"Agency","This save is set to Play Ticket B."); return
        operation=self.hq_operation_type.currentText(); message=self.hq_operation_message.currentText()
        action=f"STATE_OPERATION:{code}:{operation}"
        self.diagnostics.set_ui_action(action); started=time.perf_counter()
        try:
            result=self.campaign_engine.run_state_operation(c,requested,code,operation,message)
            self.campaign_engine.generate_poll_snapshot(c,force=True)
            self.campaigns.save(c); self._active_campaign_obj=c
            direction="Ticket A" if float(result.get("delta_a",0))>=0 else "Ticket B"
            self.hq_operation_status.setText(
                f"{operation} completed in {result.get('state_name',code)} · {message}. "
                f"Modeled movement {abs(float(result.get('delta_a',0))):.2f} pts toward {direction}; "
                f"cost {float(result.get('cost',0)):.1f} campaign funds."
            )
            self.diagnostics.log("INFO","STATE_OPERATION_COMPLETE",campaign_id=c.get("id"),**result)
            self.refresh_campaign_hq(); self.refresh_dashboard()
        except Exception as exc:
            self.diagnostics.exception("STATE_OPERATION_FAILED",exc,state=code,operation=operation)
            QMessageBox.warning(self,"State Operation Failed",str(exc))
        finally:
            self.diagnostics.log("DEBUG","STATE_OPERATION_UI_DONE",duration_ms=round((time.perf_counter()-started)*1000,1))
            QTimer.singleShot(850,lambda:self.diagnostics.clear_ui_action(action))

    def take_poll_snapshot(self):
        c=self._campaign_by_id(self.active_campaign_id)
        if not c:return
        try:
            snap=self.campaign_engine.generate_poll_snapshot(c,force=True)
            self.campaigns.save(c); self._active_campaign_obj=c
            self.diagnostics.log("INFO","POLL_SNAPSHOT_CREATED",campaign_id=c.get("id"),turn=c.get("turn"),polls=len(snap.get("polls",[])),manual=True)
            self._refresh_polling_table(c)
            self.timeline_preview.setText(self.timeline_preview.text())
        except Exception as exc:
            self.diagnostics.exception("POLL_SNAPSHOT_FAILED",exc)
            QMessageBox.warning(self,"Polling Snapshot Failed",str(exc))

    @staticmethod
    def _margin_text(value: float) -> str:
        return f"A +{abs(value):.1f}" if value>=0 else f"B +{abs(value):.1f}"

    def _refresh_polling_table(self,c:dict):
        if not hasattr(self,"hq_poll_table"):return
        history=c.get("polling_history") or []
        if not history:
            self.hq_poll_table.setRowCount(0)
            self.hq_poll_summary.setText("Advance the campaign or take a snapshot to generate simulated battleground polling.")
            return
        latest=history[-1]; previous=history[-2] if len(history)>1 else None
        prev_by={x.get("code"):x for x in (previous or {}).get("polls",[])}
        rows=latest.get("polls") or []
        self.hq_poll_table.setSortingEnabled(False); self.hq_poll_table.setRowCount(len(rows))
        for i,row in enumerate(rows):
            poll=float(row.get("poll_margin_a",0)); latent=float(row.get("latent_margin_a",0)); old=prev_by.get(row.get("code"))
            trend="—"
            if old is not None:
                diff=poll-float(old.get("poll_margin_a",0)); trend=f"{diff:+.1f} A"
            vals=[
                f"{row.get('state',row.get('code'))} ({row.get('code')})",
                self._margin_text(poll), self._margin_text(latent),
                f"n={int(row.get('sample_size',0))}", f"±{float(row.get('moe',0)):.1f}", trend,
            ]
            for j,text in enumerate(vals):self.hq_poll_table.setItem(i,j,QTableWidgetItem(text))
        self.hq_poll_table.setSortingEnabled(True)
        manual="manual snapshot" if latest.get("manual_snapshot") else "turn snapshot"
        self.hq_poll_summary.setText(
            f"Latest {manual}: {latest.get('date')} · turn {latest.get('turn')} · {len(rows)} battleground states. "
            "Polls contain seeded sampling noise and may differ from the underlying campaign pulse."
        )

    def refresh_campaign_hq(self, force: bool = False):
        # Many unrelated actions (portrait updates, campaign-library refreshes,
        # research completion) used to rebuild the hidden HQ map. Defer hidden
        # refreshes until the user actually opens Campaign HQ.
        if not force and hasattr(self,"stack") and self.stack.currentIndex() != 3:
            self._hq_dirty = True
            self.diagnostics.log("DEBUG","CAMPAIGN_HQ_REFRESH_DEFERRED",campaign_id=self.active_campaign_id)
            return
        self._hq_dirty = False
        action="REFRESH_CAMPAIGN_HQ"
        self.diagnostics.set_ui_action(action)
        started=time.perf_counter()
        try:
            return self._refresh_campaign_hq_impl()
        except Exception as exc:
            self.diagnostics.exception("REFRESH_CAMPAIGN_HQ_FAILED",exc)
            raise
        finally:
            self.diagnostics.log("INFO","REFRESH_CAMPAIGN_HQ_DONE",duration_ms=round((time.perf_counter()-started)*1000,1),campaign_id=self.active_campaign_id)
            QTimer.singleShot(850,lambda:self.diagnostics.clear_ui_action(action))

    def _refresh_campaign_hq_impl(self):
        if not hasattr(self, "hq_summary"):
            return
        c = self._campaign_by_id(self.active_campaign_id)
        if not c:
            self.hq_mode_stack.setCurrentIndex(0)
            self.hq_summary.setText("No campaign selected. Open one from Campaigns.")
            self.hq_ticket_a.setText("Ticket A"); self.hq_ticket_b.setText("Ticket B")
            self._set_portrait(self.hq_portrait_a, ""); self._set_portrait(self.hq_portrait_b, ""); self._set_portrait(self.hq_vp_portrait_a, ""); self._set_portrait(self.hq_vp_portrait_b, "")
            self.timeline_preview.setText("No campaign selected."); self.timeline_schedule.clear(); self.next_milestone.setText("No campaign selected."); self.timeline_progress.setValue(0)
            if hasattr(self,"hq_campaign_map"): self.hq_campaign_map.set_results([],"Ticket A","Ticket B")
            if hasattr(self,"hq_state_detail"): self.hq_state_detail.setText("Select a campaign, then click a state to inspect its priorities and campaign response.")
            if hasattr(self,"hq_strategy_intel"): self.hq_strategy_intel.setText("Open a campaign to populate the War Room.")
            if hasattr(self,"hq_poll_table"): self.hq_poll_table.setRowCount(0); self.hq_poll_summary.setText("Open a campaign to populate simulated polling.")
            if hasattr(self,"hq_operation_btn"): self.hq_operation_btn.setEnabled(False); self.hq_operation_status.setText("Select a campaign and state to run a state operation.")
            if hasattr(self,"campaign_operation_btn"): self.campaign_operation_btn.setEnabled(False); self.campaign_operation_status.setText("Open a campaign to run operations.")
            if hasattr(self,"hq_refresh_poll_btn"): self.hq_refresh_poll_btn.setEnabled(False)
            self.advance_btn.setEnabled(False); self.election_day_btn.hide(); self.hq_branch_btn.setEnabled(False); self.advisor_btn.setEnabled(False)
            if hasattr(self,"narrate_latest_btn"): self.narrate_latest_btn.setEnabled(False)
            self.debate_begin_btn.setEnabled(False); self.debate_auto_btn.setEnabled(False); self.debate_skip_btn.setEnabled(False)
            return

        self.campaign_engine.ensure_state(c)
        ta = c.get("ticket_a", {}); tb = c.get("ticket_b", {})
        an = ta.get("president") or "Ticket A"; bn = tb.get("president") or "Ticket B"
        self.hq_ticket_a.setText(f"Ticket A\n{an}\n{ta.get('vp') or 'No VP'}")
        self.hq_ticket_b.setText(f"Ticket B\n{bn}\n{tb.get('vp') or 'No VP'}")
        av=ta.get('vp') or ""; bv=tb.get('vp') or ""
        self._set_portrait(self.hq_portrait_a, an); self._set_portrait(self.hq_portrait_b, bn); self._set_portrait(self.hq_vp_portrait_a,av); self._set_portrait(self.hq_vp_portrait_b,bv)
        self._queue_portrait_if_missing(an, self.hq_portrait_a); self._queue_portrait_if_missing(bn, self.hq_portrait_b)
        if av:self._queue_portrait_if_missing(av,self.hq_vp_portrait_a)
        if bv:self._queue_portrait_if_missing(bv,self.hq_vp_portrait_b)
        rules=campaign_rules(c); rules_name=c.get("rules_preset","Campaign") + (" · Modified" if c.get("rules_modified") else " · Official")
        self.hq_summary.setText(
            f"<b>{c.get('title')}</b><br>{c.get('branch_label','Main Timeline')}<br><br>"
            f"<b>{c.get('current_date')}</b> → {c.get('election_date')}<br>"
            f"Momentum: A {c.get('momentum_a',0):+.1f} • B {c.get('momentum_b',0):+.1f}<br>"
            f"Funds: A {c.get('funds_a',100):.0f} • B {c.get('funds_b',100):.0f}<br>"
            f"Agency: {c.get('agency','Spectate')}<br>"
            f"Rules: <b>{rules_name}</b><br>"
            f"Seed: <b>{c.get('seed','—')}</b> · deterministic replay"
        )
        if hasattr(self,"shell_context") and self.stack.currentIndex()==3:
            self.shell_context.setText(f"{c.get('title','Campaign')} · {rules_name}")
        self.turn_pace.setCurrentText(c.get("detail_level") if c.get("detail_level") in DETAIL_LEVELS else "Weekly")
        adjustments=self.campaign_engine.state_agents.campaign_adjustments(c)
        moved=sorted(adjustments.items(),key=lambda kv:abs(kv[1]),reverse=True)[:5]
        if moved and any(abs(v)>.005 for _,v in moved):
            bits=[]
            for code,val in moved:
                nm=self.campaign_engine.state_agents.states.get(code,{}).get("name",code)
                bits.append(f"{nm} {'A' if val>=0 else 'B'} +{abs(val):.2f}")
            self.state_pulse.setText("<b>State electorate movement:</b> "+" • ".join(bits)+"<br><span style='color:#8f9bad'>Campaign messaging moves states most when the targeted region and issue match their modeled priorities.</span>")
        else:
            self.state_pulse.setText("State electorate model is active. Campaign issue + region choices will accumulate state-specific movement here.")

        # Always keep the Campaign HQ map current. This is deliberately a cheap
        # state-pulse calculation so every turn can redraw instantly without rerunning
        # thousands of Monte Carlo universes or invoking an AI provider.
        if hasattr(self,"hq_campaign_map"):
            live_rows=self._campaign_map_snapshot(c)
            self.hq_campaign_map.set_results(live_rows,an,bn)
            selected=next((x for x in live_rows if x.get("code")==self._hq_selected_state_code),None)
            if selected is None and live_rows:
                selected=min(live_rows,key=lambda x:abs(float(x.get("avg_margin_a",0))))
            if selected:self.show_campaign_state_detail(selected)
            if hasattr(self,"hq_strategy_intel") and live_rows:
                close=sorted(live_rows,key=lambda x:abs(float(x.get("avg_margin_a",0))))[:5]
                close_text=" • ".join(f"{x['code']} {'A' if float(x.get('avg_margin_a',0))>=0 else 'B'} +{abs(float(x.get('avg_margin_a',0))):.1f}" for x in close)
                agency=str(c.get("agency") or "")
                side="a" if "Ticket A" in agency else "b" if "Ticket B" in agency else "a"
                candidates=[]
                for row in live_rows:
                    code=row.get("code"); ctx=self.campaign_engine.state_agents.context_for(code,c); op=ctx.get("campaign_opinion") or {}
                    attention=float(op.get(f"attention_{side}",0) or 0); margin=abs(float(row.get("avg_margin_a",0) or 0)); ev=float(row.get("ev",0) or 0)
                    if margin<=10:
                        score=ev/max(2.0,margin+2.0)/max(1.0,attention+1.0)
                        candidates.append((score,row,ctx,attention))
                candidates.sort(key=lambda x:x[0],reverse=True)
                opportunity=candidates[0] if candidates else None
                if opportunity:
                    _,row,ctx,attention=opportunity; issues=ctx.get("top_issues") or list((ctx.get("issue_priorities") or {}).keys()); issue=issues[0] if issues else "no dominant issue loaded"
                    opp=f"<b>Under-attended opportunity:</b> {ctx.get('name',row.get('code'))} ({row.get('ev')} EV) · current margin {float(row.get('avg_margin_a',0)):+.1f} · your modeled attention {attention:.1f} · strongest issue match: {issue}"
                else:
                    opp="<b>Under-attended opportunity:</b> No state currently meets the close-race watch threshold."
                proj_a=sum(int(x.get("ev",0) or 0) for x in live_rows if float(x.get("avg_margin_a",0))>=0); proj_b=538-proj_a
                winner="Ticket A" if proj_a>=270 else "Ticket B" if proj_b>=270 else "No one"
                # Tipping state on the current live pulse: order the projected winner's states from safest to closest.
                tipping="—"
                if winner in {"Ticket A","Ticket B"}:
                    want_a=winner=="Ticket A"; total=0
                    held=[x for x in live_rows if (float(x.get("avg_margin_a",0))>=0)==want_a]
                    held.sort(key=lambda x:abs(float(x.get("avg_margin_a",0))),reverse=True)
                    for row in held:
                        total+=int(row.get("ev",0) or 0)
                        if total>=270: tipping=f"{row.get('name',row.get('code'))} ({row.get('code')}) · {abs(float(row.get('avg_margin_a',0))):.1f} pts"; break
                path=f"<b>Current path to 270:</b> A {proj_a} EV · B {proj_b} EV · projected leader {winner}<br><b>Current tipping state:</b> {tipping}"
                self.hq_strategy_intel.setText(f"{path}<br><br><b>Battleground watch:</b> {close_text}<br><br>{opp}<br><br><span style='color:#8f9bad'>War Room output is game-model analysis from the live state agents. It updates each turn and does not require an AI provider.</span>")

        # State operations and simulated polling are campaign-game systems. They
        # stay disabled for Spectate saves but are otherwise available between major events.
        agency=str(c.get("agency") or "Spectate")
        can_operate=agency != "Spectate" and not bool(c.get("pending_event")) and c.get("status") not in {"completed","election_day_ready"}
        if hasattr(self,"hq_operation_btn"):
            self.hq_operation_btn.setEnabled(can_operate and bool(self._hq_selected_state_code))
            self.hq_operation_side.setEnabled(agency=="Control Both")
            if agency=="Play Ticket A": self.hq_operation_side.setCurrentText("Ticket A")
            elif agency=="Play Ticket B": self.hq_operation_side.setCurrentText("Ticket B")
        if hasattr(self,"campaign_operation_btn"):
            self.campaign_operation_side.setEnabled(agency=="Control Both")
            if agency=="Play Ticket A": self.campaign_operation_side.setCurrentText("Ticket A")
            elif agency=="Play Ticket B": self.campaign_operation_side.setCurrentText("Ticket B")
            self._update_campaign_operation_hint(c, can_operate=can_operate)
        if hasattr(self,"hq_refresh_poll_btn"):
            self.hq_refresh_poll_btn.setEnabled(not bool(c.get("pending_event")))
        self._refresh_polling_table(c)
        # Campaign rules are save-local. UI controls reflect the active save rather
        # than whatever global Settings happen to contain today.
        ops_on=rule_enabled(c,"campaign","state_operations",True)
        polls_on=rule_enabled(c,"campaign","polling",True)
        talks_on=rule_enabled(c,"campaign","conversations",True) and rule_enabled(c,"ai","dialogue",True)
        history_on=rule_enabled(c,"campaign","ai_history",True) and rule_enabled(c,"ai","event_narration",True)
        if hasattr(self,"hq_operation_btn"):
            self.hq_operation_btn.setEnabled(bool(can_operate and ops_on and self._hq_selected_state_code))
            if not ops_on:self.hq_operation_status.setText("State Operations are disabled by this campaign's ruleset.")
        if hasattr(self,"hq_refresh_poll_btn"):
            self.hq_refresh_poll_btn.setEnabled(bool(polls_on and not c.get("pending_event")))
            if not polls_on:self.hq_poll_summary.setText("Simulation polling is disabled by this campaign's ruleset.")
        if hasattr(self,"advisor_btn"):
            self.advisor_btn.setEnabled(bool(talks_on and can_operate))
        if hasattr(self,"narrate_latest_btn"):
            self.narrate_latest_btn.setEnabled(history_on and any(e.get("type")=="campaign_turn" for e in c.get("timeline",[])))

        is_election_ready=c.get("status") in {"election_day_ready","completed"}
        self.advance_btn.setEnabled(not is_election_ready); self.advance_btn.setVisible(not is_election_ready)
        self.election_day_btn.setVisible(is_election_ready); self.election_day_btn.setEnabled(True)
        self.election_day_btn.setText("View / Re-run Election Day Result" if c.get("final_result") else "Run Election Day Result")
        self.hq_branch_btn.setEnabled(True)
        if hasattr(self,"advisor_btn"):
            self.advisor_btn.setEnabled(bool(talks_on and can_operate))
        if hasattr(self,"campaign_operation_btn"):
            self._update_campaign_operation_hint(c, can_operate=can_operate)
        if hasattr(self,"narrate_latest_btn"):
            has_turn=any(e.get("type")=="campaign_turn" for e in c.get("timeline",[]))
            self.narrate_latest_btn.setEnabled(bool(history_on and has_turn and self._history_preference() is not None))

        # Campaign progress.
        try:
            start = date.fromisoformat(c.get("campaign_start_date", "2028-06-01"))
            cur = date.fromisoformat(c.get("current_date"))
            election = date.fromisoformat(c.get("election_date"))
            span = max(1, (election - start).days)
            pct = max(0, min(100, round((cur - start).days / span * 100)))
        except Exception:
            pct = 0
        self.timeline_progress.setValue(pct)

        # Calendar / scheduled milestones.
        self.timeline_schedule.clear()
        pending = c.get("pending_event")
        next_event = self.campaign_engine.next_scheduled_event(c)
        if pending:
            self.next_milestone.setText(f"<b>NOW:</b> {pending.get('title','Major event')} · {pending.get('date','')}. Resolve it before campaign time can advance.")
        elif next_event:
            self.next_milestone.setText(f"<b>Next milestone:</b> {next_event.get('title')} · {next_event.get('date')}")
        else:
            self.next_milestone.setText("No remaining scheduled milestones before Election Day.")
        status_icons = {"scheduled":"○", "completed":"✓", "auto":"⚡", "skipped":"—", "missed":"×"}
        for item in c.get("schedule", []):
            status = item.get("status", "scheduled")
            if pending and item.get("id") == pending.get("id"):
                icon = "◉"
            else:
                icon = status_icons.get(status, "○")
            row = QListWidgetItem(f"{icon}  {item.get('date')}   {item.get('title')}")
            row.setToolTip(f"{item.get('type','event').replace('_',' ').title()} · {status.replace('_',' ').title()}" + (f"\nTopic: {item.get('topic')}" if item.get('topic') else ""))
            self.timeline_schedule.addItem(row)

        recent = []
        for event in reversed(c.get("timeline", [])[-12:]):
            html = self._timeline_event_html(event)
            if html:
                recent.append(html)
        self.timeline_preview.setText("<br><br>".join(recent) if recent else "No campaign history yet. Choose a strategy and advance time, or talk with people around the campaign.")

        # Major events take over Campaign HQ instead of living permanently below the normal UI.
        if pending and pending.get("type") == "debate":
            self.hq_mode_stack.setCurrentIndex(1)
            self.debate_event_title.setText(pending.get("title") or "Debate Night")
            self.debate_event_meta.setText(f"{pending.get('date','')}  •  Scheduled topic: {pending.get('topic') or 'General'}\n{an} vs. {bn}")
            if not self._active_debate_question:
                self.debate_question.setText("A scheduled debate has paused normal campaign gameplay. Participate yourself, let the AI auto-simulate it, or skip it.")
                self.debate_answer.hide(); self.debate_submit_btn.hide(); self.debate_result.hide()
                self.debate_begin_btn.show(); self.debate_auto_btn.show(); self.debate_skip_btn.show()
            agency = c.get("agency", "Spectate")
            if agency == "Play Ticket A":
                self.debate_side.setCurrentText("Ticket A"); self.debate_side.setEnabled(False); self.debate_begin_btn.setEnabled(True)
            elif agency == "Play Ticket B":
                self.debate_side.setCurrentText("Ticket B"); self.debate_side.setEnabled(False); self.debate_begin_btn.setEnabled(True)
            elif agency == "Control Both":
                self.debate_side.setEnabled(True); self.debate_begin_btn.setEnabled(True)
            else:
                self.debate_side.setEnabled(False); self.debate_begin_btn.setEnabled(False)
                self.debate_question.setText("This campaign is in Spectate mode. Auto-simulate or skip the debate.")
            self.debate_auto_btn.setEnabled(True); self.debate_skip_btn.setEnabled(True)
        else:
            self.hq_mode_stack.setCurrentIndex(0)
            self._active_debate_question = None; self._debate_campaign_id = None

        self._active_campaign_obj = c

    def _choose_instant_debate_policy(self) -> str | None:
        box=QMessageBox(self)
        box.setWindowTitle("Instant Election — Debates")
        box.setIcon(QMessageBox.Question)
        box.setText("How should ElectionLab handle scheduled debates while fast-forwarding to Election Day?")
        box.setInformativeText("Stop at each debate lets you participate normally. Auto all uses the deterministic local debate model and requires no AI provider. Skip all jumps past them.")
        manual=box.addButton("Stop at each debate", QMessageBox.AcceptRole)
        auto=box.addButton("Auto all + go to election", QMessageBox.ActionRole)
        skip=box.addButton("Skip all + go to election", QMessageBox.DestructiveRole)
        cancel=box.addButton(QMessageBox.Cancel)
        box.exec()
        clicked=box.clickedButton()
        if clicked is manual:return "manual"
        if clicked is auto:return "auto"
        if clicked is skip:return "skip"
        return None

    def advance_campaign(self):
        c = self._campaign_by_id(self.active_campaign_id)
        if not c:
            return
        pace=self.turn_pace.currentText()
        strategy = {"region": self.turn_region.currentText(), "message": self.turn_message.currentText(), "tone": self.turn_tone.currentText()}
        if pace == "Instant Election":
            policy=self._choose_instant_debate_policy()
            if policy is None:return
            if policy in {"auto","skip"}:
                pa=self.vault.get_profile((c.get("ticket_a") or {}).get("president") or "") or {}
                pb=self.vault.get_profile((c.get("ticket_b") or {}).get("president") or "") or {}
                self.campaign_engine.fast_forward_debate_policy(c,policy,pa,pb)
        try:
            ledger=self.campaign_engine.advance(c, pace, strategy)
        except RuntimeError as exc:
            QMessageBox.information(self, "Campaign Event Pending", str(exc)); return
        c["detail_level"] = pace; self.campaigns.save(c); self._active_campaign_obj=c
        self.diagnostics.log("INFO","CAMPAIGN_ADVANCED",campaign_id=c.get("id"),turn=c.get("turn"),pace=pace,region=strategy.get("region"),message=strategy.get("message"),status=c.get("status"))
        self.refresh_campaigns(); self.refresh_campaign_hq(); self.refresh_dashboard()
        self._maybe_narrate_campaign_turn(c,ledger)
        if c.get("status") == "election_day_ready":
            answer=QMessageBox.question(self,"Election Day Reached","The campaign reached Election Day. Run the election now using the state-specific campaign movement you built up?",QMessageBox.Yes|QMessageBox.No,QMessageBox.Yes)
            if answer==QMessageBox.Yes:self.run_campaign_election()

    def narrate_latest_turn(self):
        c=self._campaign_by_id(self.active_campaign_id)
        if not c:return
        ledger=next((e for e in reversed(c.get("timeline",[])) if e.get("type")=="campaign_turn"),None)
        if not ledger:
            QMessageBox.information(self,"No Campaign Turn","Advance the campaign at least once before narrating history."); return
        pref=self._history_preference()
        if pref is None:
            QMessageBox.information(self,"Deterministic History Selected","Choose Auto AI, Local AI, or OpenAI — testing override under Settings → Campaign history narration first."); return
        cid=c.get("id"); turn=ledger.get("turn")
        self._manual_history_request=(cid,turn)
        self.diagnostics.set_ui_action(f"AI_NARRATE:{cid}:{turn}")
        self.diagnostics.log("INFO","AI_NARRATE_CLICK",campaign_id=cid,turn=turn,preference=pref)
        self.narrate_latest_btn.setEnabled(False); self.narrate_latest_btn.setText("Narrating…")
        self.busy_overlay.begin("Writing campaign recap", f"Generating an AI narration for turn {turn} using {pref}…", None)
        self._maybe_narrate_campaign_turn(c,ledger)

    def _history_preference(self) -> str | None:
        mode=getattr(self.settings.settings,"campaign_history_provider","Deterministic local")
        if mode=="Deterministic local":return None
        if mode.startswith("OpenAI"):return "OpenAI"
        if mode=="Local AI":return "Local AI"
        return "Auto — best available"

    def _maybe_narrate_campaign_turn(self,campaign:dict,ledger:dict|None):
        pref=self._history_preference()
        if not pref or not ledger or ledger.get("type")!="campaign_turn":return
        cid=campaign.get("id"); turn=ledger.get("turn")
        ccopy=copy.deepcopy(campaign); lcopy=copy.deepcopy(ledger)
        def job(report):
            report(8,f"Preparing turn {turn} campaign ledger…")
            report(20,f"Sending recap request to {pref}…")
            result=self.debate_service.narrate_campaign_turn(ccopy,lcopy,pref)
            report(88,"AI recap returned; saving it to the timeline…")
            return result
        thread=ProgressThread(job,self)
        self._history_threads.append(thread)
        thread.progress.connect(lambda pct,msg,cid=cid,turn=turn:self._history_narration_progress(cid,turn,pct,msg))
        thread.done.connect(lambda result,cid=cid,turn=turn,t=thread:self._history_narration_done(cid,turn,result,t))
        thread.failed.connect(lambda msg,cid=cid,turn=turn,t=thread:self._history_narration_failed(cid,turn,msg,t))
        thread.start()

    def _history_narration_progress(self,campaign_id,turn,percent,message):
        self.diagnostics.log("DEBUG","AI_NARRATE_STAGE",campaign_id=campaign_id,turn=turn,percent=int(percent),message=str(message))
        if self._manual_history_request==(campaign_id,turn):
            self.busy_overlay.set_progress(percent,message)

    def _history_narration_done(self,campaign_id,turn,result,thread):
        if thread in self._history_threads:self._history_threads.remove(thread)
        c=self._campaign_by_id(campaign_id)
        if not c:return
        for event in c.get("timeline",[]):
            if event.get("type")=="campaign_turn" and event.get("turn")==turn:
                event["ai_narrative"]=result.get("reply","")
                event["narrative_provider"]=result.get("provider","AI")
                break
        self.campaigns.save(c)
        if self._manual_history_request==(campaign_id,turn):
            self._manual_history_request=None
            self.busy_overlay.finish()
            self.diagnostics.log("INFO","AI_NARRATE_COMPLETE",campaign_id=campaign_id,turn=turn,provider=result.get("provider","AI"))
            self.diagnostics.clear_ui_action()
            if hasattr(self,"narrate_latest_btn"):
                self.narrate_latest_btn.setEnabled(True); self.narrate_latest_btn.setText("Narration added ✓")
                QTimer.singleShot(1400, lambda: self.narrate_latest_btn.setText("Narrate Latest Turn") if hasattr(self,"narrate_latest_btn") else None)
        if campaign_id==self.active_campaign_id:self.refresh_campaign_hq()
        self.refresh_dashboard()

    def _history_narration_failed(self,campaign_id,turn,msg,thread):
        if thread in self._history_threads:self._history_threads.remove(thread)
        c=self._campaign_by_id(campaign_id)
        if c:
            for event in c.get("timeline",[]):
                if event.get("type")=="campaign_turn" and event.get("turn")==turn:
                    event["narration_error"]=str(msg)[:300]
                    break
            self.campaigns.save(c)
        manual = self._manual_history_request==(campaign_id,turn)
        if manual:
            self._manual_history_request=None
            self.busy_overlay.finish()
            self.diagnostics.log("ERROR","AI_NARRATE_FAILED",campaign_id=campaign_id,turn=turn,error=str(msg))
            self.diagnostics.clear_ui_action()
            if hasattr(self,"narrate_latest_btn"):
                self.narrate_latest_btn.setEnabled(True); self.narrate_latest_btn.setText("Narrate Latest Turn")
            QMessageBox.warning(self,"AI Narration Failed",f"ElectionLab could not generate the requested campaign narration.\n\n{msg}\n\nThe deterministic campaign history is unchanged. See latest_session.log for details.")
        elif campaign_id==self.active_campaign_id and hasattr(self,"timeline_preview"):
            # Automatic narration is optional flavor text, so do not interrupt normal play.
            self.timeline_preview.setToolTip("AI history narration could not run; deterministic campaign history is still intact.")

    def _campaign_election_job(self, payload: dict, report):
        report(5,"Preparing Election Day electorate…")
        result=self.engine.run(payload["a"],payload["b"],payload["cfg"],lambda pct,msg: report(8+int(pct*.90),msg))
        result["campaign_result"]=True
        result["campaign_title"]=payload["campaign_title"]
        result["campaign_state_adjustments"]=payload["adjustments"]
        result["campaign_momentum_environment"]=payload["national"]
        report(100,"Election Day result ready.")
        return {"result":result,"campaign_id":payload["campaign_id"],"cfg_seed":payload["cfg"].seed,"adjustments":payload["adjustments"]}

    def run_campaign_election(self):
        if self._campaign_election_thread and self._campaign_election_thread.isRunning():return
        c=self._campaign_by_id(self.active_campaign_id)
        if not c:return
        ta=c.get("ticket_a") or {}; tb=c.get("ticket_b") or {}
        pa=self.vault.get_profile(ta.get("president") or ""); pb=self.vault.get_profile(tb.get("president") or "")
        if not pa or not pb:
            QMessageBox.warning(self,"Campaign Profiles Missing","Election Day needs both presidential profiles in the Knowledge Vault."); return
        pva=self.vault.get_profile(ta.get("vp") or "") if ta.get("vp") else None
        pvb=self.vault.get_profile(tb.get("vp") or "") if tb.get("vp") else None
        party_a=ta.get("party") or pa.get("party") or "Independent"; party_b=tb.get("party") or pb.get("party") or "Independent"
        a=self._compose_ticket(pa,pva,party_a); b=self._compose_ticket(pb,pvb,party_b)
        rules=campaign_rules(c); sim_rules=rules.get("simulation") or {}
        traits_on=rule_enabled(c,"electorate","candidate_traits",True)
        factors={
            "historical_baseline":rule_enabled(c,"electorate","historical_baseline",True),
            "candidate_personality":traits_on,
            "debates":rule_enabled(c,"campaign","debates",True),
            "experience":traits_on,
            "name_recognition":traits_on,
            "home_state":traits_on,
            "random_uncertainty":bool(sim_rules.get("uncertainty",True)),
        }
        adjustments=self.campaign_engine.state_agents.campaign_adjustments(c)
        momentum_gap=float(c.get("momentum_a",0))-float(c.get("momentum_b",0)); national=max(-5.0,min(5.0,momentum_gap*0.18))
        runs=int(sim_rules.get("monte_carlo_runs") or self.settings.settings.monte_carlo_runs)
        cfg=SimulationConfig(c.get("simulation_mode") or rules.get("simulation_mode") or self.settings.settings.default_mode,runs,f"{c.get('seed','CAMPAIGN')}|ELECTION-DAY",factors,national,adjustments)
        payload={"a":a,"b":b,"cfg":cfg,"adjustments":adjustments,"national":national,"campaign_id":c.get("id"),"campaign_title":c.get("title")}
        self.busy_overlay.begin("Election Day",f"Counting {cfg.runs:,} simulated election universes…",2)
        self.election_day_btn.setEnabled(False)
        self._campaign_election_thread=ProgressThread(lambda report:self._campaign_election_job(payload,report),self)
        self._campaign_election_thread.progress.connect(lambda p,m:self.busy_overlay.set_progress(p,m))
        self._campaign_election_thread.done.connect(self._campaign_election_done)
        self._campaign_election_thread.failed.connect(self._campaign_election_failed)
        self._campaign_election_thread.finished.connect(self._campaign_election_thread_finished)
        self._campaign_election_thread.start()

    def _campaign_election_done(self,payload):
        self.busy_overlay.finish(); self.election_day_btn.setEnabled(True)
        result=payload["result"]; c=self._campaign_by_id(payload["campaign_id"])
        if c:
            c["final_result"]={"seed":payload["cfg_seed"],"expected_ev_a":result["expected_ev_a"],"expected_ev_b":result["expected_ev_b"],"a_presidency_prob":result["a_presidency_prob"],"avg_popular_margin_a":result["avg_popular_margin_a"],"state_adjustments":payload["adjustments"]}
            c["status"]="completed"
            c.setdefault("timeline",[]).append({"type":"election_day_result","date":c.get("election_date"),"headline":result.get("local_overview"),"expected_ev_a":round(result["expected_ev_a"],1),"expected_ev_b":round(result["expected_ev_b"],1),"fictional_simulation_event":True})
            self.campaigns.save(c)
        self.diagnostics.log("INFO","CAMPAIGN_ELECTION_COMPLETE",campaign_id=payload.get("campaign_id"),seed=payload.get("cfg_seed"),expected_ev_a=round(float(result.get("expected_ev_a",0)),1),expected_ev_b=round(float(result.get("expected_ev_b",0)),1))
        self.last_result=result; self.show_results(result); self.go(1); self.refresh_campaigns(); self.refresh_dashboard()
        QMessageBox.information(self,"Campaign Election Complete","Election Day used the local election engine plus the state-by-state movement accumulated during this campaign. The result is saved to the campaign.")

    def _campaign_election_failed(self,message):
        self.busy_overlay.finish(); self.election_day_btn.setEnabled(True)
        self.diagnostics.log("ERROR","CAMPAIGN_ELECTION_FAILED",error=str(message),campaign_id=self.active_campaign_id)
        QMessageBox.critical(self,"Election Day Error",message)

    def _campaign_election_thread_finished(self):
        self._campaign_election_thread=None

    def _interaction_busy(self, busy: bool, message: str = ""):
        for name in ["advisor_btn", "debate_begin_btn", "debate_auto_btn", "debate_skip_btn", "debate_submit_btn"]:
            widget = getattr(self, name, None)
            if widget:
                widget.setEnabled(not busy and (name != "debate_submit_btn" or bool(self._active_debate_question)))
        if message and hasattr(self, "hq_summary"):
            self.hq_summary.setToolTip(message)

    def ask_advisor(self):
        c = self._campaign_by_id(self.active_campaign_id); message = self.advisor_input.text().strip()
        if not c or not message:
            return
        self._autosave_provider_settings()
        role = self.conversation_role.currentText()
        self.advisor_log.appendPlainText(f"YOU → {role.upper()}: {message}\n")
        self._interaction_campaign_id = c.get("id"); self._pending_advisor_message = message; self._pending_conversation_role = role; self._interaction_kind = "conversation"
        self.advisor_input.clear(); self._interaction_busy(True, f"{role} is responding...")
        pref = self.ai_provider.currentText()
        state_code=self.conversation_state.currentData() if role=="Constituent" else None
        self._pending_conversation_state=state_code
        self._interaction_thread = ResearchThread(lambda: self.debate_service.conversation_chat(c, role, message, pref, state_code), self)
        self._interaction_thread.done.connect(self._advisor_done); self._interaction_thread.failed.connect(self._interaction_failed); self._interaction_thread.start()

    def _advisor_done(self, result):
        self._interaction_busy(False)
        role = result.get("role") or self._pending_conversation_role or "Campaign adviser"
        meta=result.get("constituent") or {}
        who=role.upper()
        if meta: who += f" — {meta.get('state_name',meta.get('state_code',''))} — {meta.get('issue','')}"
        self.advisor_log.appendPlainText(f"{who} [{result.get('provider','AI')}]: {result.get('reply','')}\n")
        c = self._campaign_by_id(self._interaction_campaign_id)
        if c:
            c.setdefault("timeline", []).append({
                "type": "conversation_exchange",
                "at": datetime.now().astimezone().isoformat(),
                "role": role,
                "user_message": self._pending_advisor_message,
                "reply": result.get("reply", ""),
                "provider": result.get("provider", "AI"),
                "constituent": result.get("constituent"),
                "fictional_simulation_content": True,
            })
            self.campaigns.save(c)
            if c.get("id") == self.active_campaign_id:
                self.refresh_campaign_hq()
        self._pending_advisor_message = None; self._pending_conversation_role = None; self._pending_conversation_state = None; self._interaction_kind = None

    def begin_debate_question(self):
        c = self._campaign_by_id(self.active_campaign_id)
        if not c or not (c.get("pending_event") or {}).get("type") == "debate":
            return
        self._autosave_provider_settings(); self._active_debate_question = None; self._debate_campaign_id = None; self._interaction_campaign_id = c.get("id"); self._interaction_kind = "debate_question"; self.debate_submit_btn.setEnabled(False)
        self.debate_question.setText("Moderator is preparing the opening question…"); self.debate_result.hide(); self.debate_answer.hide(); self.debate_submit_btn.hide(); self._interaction_busy(True)
        pref = self.debate_provider.currentText(); topic = (c.get("pending_event") or {}).get("topic") or "General"
        self._interaction_thread = ResearchThread(lambda: self.debate_service.generate_question(c, topic, pref), self)
        self._interaction_thread.done.connect(self._debate_question_done); self._interaction_thread.failed.connect(self._interaction_failed); self._interaction_thread.start()

    def _debate_question_done(self, result):
        self._interaction_busy(False); self._interaction_kind = None; self._active_debate_question = result.get("question"); self._debate_campaign_id = self._interaction_campaign_id
        self.debate_question.setText(f"<b>Moderator [{result.get('provider','AI')}]:</b><br>{self._active_debate_question}")
        self.debate_answer.show(); self.debate_submit_btn.show(); self.debate_submit_btn.setEnabled(True); self.debate_begin_btn.hide(); self.debate_answer.setFocus()

    def submit_debate_answer(self):
        c = self._campaign_by_id(self.active_campaign_id); answer = self.debate_answer.toPlainText().strip()
        if not c or not self._active_debate_question or not answer:
            return
        if self._debate_campaign_id and c.get("id") != self._debate_campaign_id:
            QMessageBox.warning(self, "Debate Campaign Changed", "This moderator question belongs to a different campaign. Return to the active debate and begin again.")
            self._active_debate_question = None; self._debate_campaign_id = None; self.debate_submit_btn.setEnabled(False); return
        self._autosave_provider_settings(); side = "A" if self.debate_side.currentText() == "Ticket A" else "B"; pref = self.debate_provider.currentText(); question = self._active_debate_question
        self.debate_result.setText("Opponent and moderator are responding…"); self.debate_result.show(); self._interaction_campaign_id = c.get("id"); self._interaction_kind = "debate_exchange"; self._interaction_busy(True)
        self._interaction_thread = ResearchThread(lambda: self.debate_service.evaluate_exchange(c, question, side, answer, pref), self)
        self._interaction_thread.done.connect(self._debate_exchange_done); self._interaction_thread.failed.connect(self._interaction_failed); self._interaction_thread.start()

    def _debate_exchange_done(self, result):
        c = self._campaign_by_id(self._interaction_campaign_id)
        if c:
            self.campaign_engine.apply_debate_result(c, result); self.campaigns.save(c)
        self._interaction_busy(False); self._interaction_kind = None
        self.debate_answer.clear(); self._active_debate_question = None; self._debate_campaign_id = None
        self.refresh_campaign_hq(); self.refresh_campaigns(); self.refresh_dashboard()
        QMessageBox.information(
            self, "Debate Complete",
            f"{result.get('notable_moment','Debate completed')}\n\nYou: {result.get('user_score','—')}   Opponent: {result.get('opponent_score','—')}\nModeled momentum: {float(result.get('user_momentum_delta',0)):+.2f}\n\nThe full exchange is saved in the campaign timeline."
        )

    def auto_debate(self):
        c = self._campaign_by_id(self.active_campaign_id)
        pending = c.get("pending_event") if c else None
        if not c or not pending or pending.get("type") != "debate":
            return
        self._autosave_provider_settings(); self._interaction_campaign_id = c.get("id"); self._interaction_kind = "debate_auto"; self._interaction_busy(True)
        self.debate_question.setText("Auto-simulating the debate…"); pref = self.debate_provider.currentText(); topic = pending.get("topic") or "General"
        self._interaction_thread = ResearchThread(lambda: self.debate_service.auto_debate(c, topic, pref), self)
        self._interaction_thread.done.connect(self._auto_debate_done); self._interaction_thread.failed.connect(self._interaction_failed); self._interaction_thread.start()

    def _auto_debate_done(self, result):
        c = self._campaign_by_id(self._interaction_campaign_id)
        if c:
            self.campaign_engine.apply_auto_debate_result(c, result); self.campaigns.save(c)
        self._interaction_busy(False); self._interaction_kind = None
        self.refresh_campaign_hq(); self.refresh_campaigns(); self.refresh_dashboard()
        QMessageBox.information(self, "Debate Auto-Simulated", f"{result.get('summary','Debate completed.')}\n\nTicket A: {result.get('score_a','—')}   Ticket B: {result.get('score_b','—')}")

    def skip_debate(self):
        c = self._campaign_by_id(self.active_campaign_id)
        pending = c.get("pending_event") if c else None
        if not c or not pending or pending.get("type") != "debate":
            return
        answer = QMessageBox.question(self, "Skip Debate", f"Skip {pending.get('title','this debate')}?\n\nThe campaign will continue and the timeline will record that it was skipped.", QMessageBox.Yes|QMessageBox.Cancel, QMessageBox.Cancel)
        if answer != QMessageBox.Yes:
            return
        self.campaign_engine.skip_pending_event(c); self.campaigns.save(c)
        self._active_debate_question = None; self._debate_campaign_id = None
        self.refresh_campaign_hq(); self.refresh_campaigns(); self.refresh_dashboard()

    def _interaction_failed(self, msg):
        self.diagnostics.log("ERROR","AI_INTERACTION_FAILED",kind=self._interaction_kind,error=str(msg),campaign_id=self._interaction_campaign_id)
        kind = self._interaction_kind
        self._interaction_kind = None
        self._interaction_busy(False)
        if kind == "conversation":
            role = self._pending_conversation_role or "AI"
            self.advisor_log.appendPlainText(f"{role.upper()} ERROR: {msg}\n")
            self._pending_advisor_message = None; self._pending_conversation_role = None
        elif kind == "debate_exchange":
            q = self._active_debate_question or "the current question"
            self.debate_question.setText(f"<b>Moderator question:</b><br>{q}<br><br><span style='color:#ffb4b4'>The AI evaluation failed. Your answer is still available; retry Submit, Auto Debate, or Skip Debate.</span>")
            self.debate_answer.show(); self.debate_submit_btn.show(); self.debate_auto_btn.show(); self.debate_skip_btn.show()
        elif kind in {"debate_question", "debate_auto"}:
            self.debate_question.setText("AI interaction failed. Retry with another provider, auto-simulate, or skip the debate.")
            self.debate_begin_btn.show(); self.debate_auto_btn.show(); self.debate_skip_btn.show()
        QMessageBox.warning(self, "AI Interaction Failed", msg)

    # ---------- vault ----------
    @staticmethod
    def _friendly_profile_type(value: str | None) -> str:
        return {
            "historical_president": "U.S. president",
            "public_figure": "Public figure",
            "custom": "Custom",
            "custom_unknown": "Unenriched",
        }.get(value or "", (value or "Unknown").replace("_", " ").title())

    @staticmethod
    def _friendly_source(value: str | None) -> str:
        return {
            "built_in": "Built-in",
            "user_created": "User-created",
            "openai_research": "Online research",
            "openai_web_research": "OpenAI + web",
            "openai_model": "OpenAI",
            "web_plus_local_ai": "Web + local AI",
            "web_reference": "Web reference",
            "local_ai": "Local AI",
            "local_ai_inference": "Local AI",
            "auto_local_stub": "Local placeholder",
        }.get(value or "", (value or "Unknown").replace("_", " ").title())

    @staticmethod
    def _friendly_status(value: str | None) -> str:
        return {
            "starter_historical": "Starter historical",
            "starter_needs_enrichment": "Needs enrichment",
            "starter_enriched": "Starter enriched",
            "custom": "Custom",
            "needs_enrichment": "Needs enrichment",
            "researched": "Researched",
            "local_enriched": "Local enriched",
            "web_basic": "Basic web profile",
        }.get(value or "", (value or "Unknown").replace("_", " ").title())

    def refresh_vault_table(self,*_):
        if not hasattr(self,"vault_table"):
            return
        selected=self._selected_vault_profile() if hasattr(self,"_vault_rows") else None
        selected_name=(selected or {}).get("canonical_name")
        query=self.vault_search.text() if hasattr(self,"vault_search") else ""
        all_profiles=self.vault.list_profiles("",limit=5000)
        rows=self.vault.list_profiles(query,limit=5000)

        # Keep party filter choices in sync with the library without recursively
        # refreshing while the combo is being rebuilt.
        if hasattr(self,"vault_party_filter"):
            current=self.vault_party_filter.currentText()
            parties=sorted({p.get("party") for p in all_profiles if p.get("party")})
            self.vault_party_filter.blockSignals(True); self.vault_party_filter.clear(); self.vault_party_filter.addItem("All parties"); self.vault_party_filter.addItems(parties)
            self.vault_party_filter.setCurrentText(current if current in ["All parties"]+parties else "All parties"); self.vault_party_filter.blockSignals(False)

        type_filter=self.vault_type_filter.currentText() if hasattr(self,"vault_type_filter") else "All types"
        party_filter=self.vault_party_filter.currentText() if hasattr(self,"vault_party_filter") else "All parties"
        source_filter=self.vault_source_filter.currentText() if hasattr(self,"vault_source_filter") else "All sources"
        def include(p):
            pt=p.get("profile_type") or ""; src=self._friendly_source(p.get("source_type"))
            if type_filter=="Historical political" and pt!="historical_political":return False
            if type_filter=="Public figures" and pt!="public_figure":return False
            if type_filter=="Custom / unknown" and pt in {"historical_political","public_figure"}:return False
            if party_filter!="All parties" and (p.get("party") or "")!=party_filter:return False
            if source_filter=="Built-in" and p.get("source_type")!="built_in":return False
            if source_filter=="User-created" and p.get("source_type")!="user_created":return False
            if source_filter=="Local AI" and p.get("source_type") not in {"local_ai","local_ai_inference","web_plus_local_ai"}:return False
            if source_filter=="Researched / web" and p.get("source_type") not in {"openai_research","openai_web_research","openai_model","web_plus_local_ai","web_reference"}:return False
            return True
        rows=[p for p in rows if include(p)]
        self._vault_rows=rows

        hdr=self.vault_table.horizontalHeader(); sort_col=hdr.sortIndicatorSection(); sort_order=hdr.sortIndicatorOrder()
        self.vault_table.setSortingEnabled(False); self.vault_table.setRowCount(len(rows))
        selected_row=None
        for i,p in enumerate(rows):
            vals=[
                (p["canonical_name"],p["canonical_name"].lower()),
                (self._friendly_profile_type(p.get("profile_type")),self._friendly_profile_type(p.get("profile_type")).lower()),
                (p.get("party") or "—",(p.get("party") or "").lower()),
                (self._friendly_source(p.get("source_type")),self._friendly_source(p.get("source_type")).lower()),
                (p.get("snapshot_date") or "—",p.get("snapshot_date") or ""),
            ]
            for j,(v,key) in enumerate(vals):
                item=SortableTableItem(str(v),key); item.setData(Qt.UserRole,p["canonical_name"])
                if j==0:item.setToolTip(f"{p.get('canonical_name')} · {self._friendly_status(p.get('profile_status'))}")
                self.vault_table.setItem(i,j,item)
            if selected_name and p.get("canonical_name")==selected_name:selected_row=i
        self.vault_table.setSortingEnabled(True)
        if sort_col>=0:self.vault_table.sortItems(sort_col,sort_order)
        if selected_name:
            for row in range(self.vault_table.rowCount()):
                it=self.vault_table.item(row,0)
                if it and it.data(Qt.UserRole)==selected_name:
                    self.vault_table.selectRow(row); break
        elif self.vault_table.rowCount():self.vault_table.selectRow(0)
        if hasattr(self,"vault_status"):
            self.vault_status.setText(f"{len(rows)} of {len(all_profiles)} profiles shown  •  click a column header to sort")
            self.vault_status.setToolTip(f"Knowledge Vault database: {self.vault.db_path}")

    def vault_selection_changed(self):
        rows = self.vault_table.selectionModel().selectedRows()
        if not rows:
            self.profile_detail.setText("Select a profile to inspect its offline data.")
            if hasattr(self,"profile_traits"): self.profile_traits.clear()
            if hasattr(self,"profile_evidence"): self.profile_evidence.clear()
            self._set_portrait(self.profile_photo, "")
            self.fetch_photo_btn.setEnabled(False); self.import_photo_btn.setEnabled(False); self.refresh_profile_btn.setEnabled(False); self.delete_profile_btn.setEnabled(False)
            return
        p = self._selected_vault_profile()
        if not p:
            return
        self._set_portrait(self.profile_photo, p.get("canonical_name") or "")
        self.fetch_photo_btn.setEnabled(True); self.import_photo_btn.setEnabled(True); self.refresh_profile_btn.setEnabled(True); self.delete_profile_btn.setEnabled(True)
        known = p.get("known_positions",{}); inferred = p.get("inferred_positions",{}); sources = p.get("sources",[])
        confidence = float(p.get('confidence') or 0) * 100
        status = self._friendly_status(p.get('profile_status'))
        self.profile_detail.setText(
            f"<span style='font-size:16pt;font-weight:700'>{p['canonical_name']}</span><br>"
            f"<span style='color:#aebbcf'>{p.get('career') or 'Background not yet enriched'}</span><br><br>"
            f"<span style='color:#8fa3bf;font-size:8pt;font-weight:700'>PROFILE</span><br>"
            f"<b>Type:</b> {self._friendly_profile_type(p.get('profile_type'))}<br>"
            f"<b>Status:</b> {status}<br>"
            f"<b>Source:</b> {self._friendly_source(p.get('source_type'))}<br>"
            f"<b>Party:</b> {p.get('party') or 'Unknown / not assigned'}<br>"
            f"<b>Home state:</b> {p.get('home_state') or 'Unknown'}<br>"
            f"<b>Snapshot:</b> {p.get('snapshot_date') or '—'}<br>"
            f"<b>Profile confidence:</b> {confidence:.0f}%<br><br>"
            f"<span style='color:#8fa3bf;font-size:8pt;font-weight:700'>EVIDENCE</span><br>"
            f"<b>Documented positions:</b> {len(known)}<br>"
            f"<b>Explicit model inferences:</b> {len(inferred)}<br>"
            f"<b>Saved sources:</b> {len(sources)}<br><br>"
            f"<span style='color:#9aa9bd'>Unknown political positions stay unknown by default. ElectionLab does not silently invent them just to complete a profile.</span>"
        )
        self.profile_traits.setText(
            f"<b>Simulation inputs</b> &nbsp; Experience {float(p.get('experience',50) or 50):.0f}/100 · "
            f"Recognition {float(p.get('name_recognition',25) or 25):.0f}/100 · "
            f"Charisma {float(p.get('charisma',50) or 50):.0f}/100 · "
            f"Debate {float(p.get('debate_skill',50) or 50):.0f}/100 · "
            f"National appeal {float(p.get('national_appeal',0) or 0):+.1f}<br>"
            f"<span style='color:#8f9bad'>These are ElectionLab model inputs, not objective ratings. Built-in starter profiles now ship with varied ElectionLab game-input heuristics; sourced research can still replace them.</span>"
        )
        def fmt_block(title,data):
            if not data:return f"{title}\n  (none saved)"
            if isinstance(data,dict):return title+"\n"+"\n".join(f"  {k}: {v}" for k,v in data.items())
            return title+"\n"+"\n".join(f"  {x}" for x in data)
        self.profile_evidence.setPlainText(
            fmt_block("DOCUMENTED POSITIONS",known)+"\n\n"+
            fmt_block("EXPLICIT MODEL INFERENCES",inferred)+"\n\n"+
            fmt_block("SAVED SOURCES",sources)
        )

    def create_custom_profile(self):
        d=CustomProfileDialog(self)
        if d.exec()!=QDialog.Accepted:return
        p=d.profile()
        if not p["canonical_name"]: QMessageBox.warning(self,"Missing Name","Enter a name."); return
        self.vault.upsert_profile(p); self.refresh_profiles(); self.refresh_vault_table()

    def research_person(self):
        name=self.research_name.text().strip()
        if not name:
            selected=self._selected_vault_profile()
            name=(selected or {}).get("canonical_name","").strip() if selected else ""
        if not name:
            self.vault_status.setText("Type a name or select a saved profile first.")
            QMessageBox.information(self,"Choose a Person","Type a public person's name, or select an existing Knowledge Vault profile to refresh it online.")
            return
        if self._research_thread and self._research_thread.isRunning():
            return
        self._autosave_provider_settings()
        action=f"PROFILE_RESEARCH:{name}"
        self.diagnostics.set_ui_action(action)
        self.diagnostics.log("INFO","PROFILE_RESEARCH_CLICK",name=name,openai_enabled=self.settings.settings.openai_enabled,internet=self.settings.settings.internet_research)
        self.research_btn.setEnabled(False); self.research_btn.setText("Researching…")
        self.local_enrich_btn.setEnabled(False)
        self.vault_status.setText(f"Researching {name}…")
        self.busy_overlay.begin("Researching profile", f"Starting research job for {name}…", 2)
        self._research_thread=ProgressThread(lambda report:self.profile_service.research_and_cache(name, report),self)
        self._research_thread.progress.connect(self._research_progress)
        self._research_thread.done.connect(self._research_done); self._research_thread.failed.connect(self._research_failed); self._research_thread.finished.connect(self._research_finished); self._research_thread.start()

    def _research_progress(self, percent:int, message:str):
        self.busy_overlay.set_progress(percent,message)
        self.vault_status.setText(message)
        self.diagnostics.log("DEBUG","PROFILE_RESEARCH_UI_STAGE",percent=int(percent),message=str(message))

    def _research_done(self,p):
        name=(p or {}).get('canonical_name') or self.research_name.text().strip()
        self.busy_overlay.finish()
        self.diagnostics.log("INFO","PROFILE_RESEARCH_COMPLETE",name=name,source=(p or {}).get("source_type"),status=(p or {}).get("profile_status"))
        self.diagnostics.clear_ui_action()
        self.research_btn.setEnabled(True); self.research_btn.setText("Research + Cache"); self.local_enrich_btn.setEnabled(True)
        self.vault_status.setText(f"Cached {name} for offline use. Portrait lookup is continuing separately if needed.")
        self.research_name.clear(); self.refresh_profiles(); self.refresh_vault_table()
        if name:
            self._queue_portrait_if_missing(name)
    def _research_failed(self,msg):
        self.busy_overlay.finish()
        self.diagnostics.log("ERROR","PROFILE_RESEARCH_FAILED",error=str(msg))
        self.diagnostics.clear_ui_action()
        self.research_btn.setEnabled(True); self.research_btn.setText("Research + Cache"); self.local_enrich_btn.setEnabled(True); self.vault_status.setText("Research/enrichment failed — see latest_session.log for provider attempts.")
        QMessageBox.warning(self,"Profile Enrichment Failed",msg)

    def _research_finished(self):
        self.diagnostics.log("DEBUG","PROFILE_RESEARCH_THREAD_FINISHED")
        self._research_thread=None

    def local_enrich_person(self):
        name=self.research_name.text().strip()
        if not name:
            selected=self._selected_vault_profile(); name=(selected or {}).get("canonical_name","").strip() if selected else ""
        if not name:
            QMessageBox.information(self,"Choose a Person","Type a name or select a saved profile first."); return
        if self._research_thread and self._research_thread.isRunning():return
        self._autosave_provider_settings()
        self.research_btn.setEnabled(False); self.local_enrich_btn.setEnabled(False); self.vault_status.setText(f"Asking local AI to enrich {name}...")
        self.diagnostics.set_ui_action(f"LOCAL_PROFILE_ENRICH:{name}")
        self.busy_overlay.begin("Local AI enrichment", f"Preparing local AI enrichment for {name}…", 5)
        def job(report):
            report(15,"Connecting to local AI…")
            result=self.profile_service.local_enrich_and_cache(name)
            report(90,"Saving local-AI enrichment…")
            return result
        self._research_thread=ProgressThread(job,self)
        self._research_thread.progress.connect(self._research_progress)
        self._research_thread.done.connect(self._research_done); self._research_thread.failed.connect(self._research_failed); self._research_thread.finished.connect(self._research_finished); self._research_thread.start()

    def _selected_vault_profile(self):
        if not hasattr(self,"vault_table"):
            return None
        rows=self.vault_table.selectionModel().selectedRows()
        if not rows:return None
        item=self.vault_table.item(rows[0].row(),0)
        name=item.data(Qt.UserRole) if item else None
        return self.vault.get_profile(name) if name else None

    def refresh_selected_profile_online(self):
        p=self._selected_vault_profile()
        if not p:return
        name=p.get("canonical_name") or ""
        if not name:return
        if p.get("source_type")=="user_created":
            answer=QMessageBox.question(self,"Refresh Custom Profile Online",f"{name} is a custom/user-created profile. Online research may replace custom simulation fields with public-person research if a matching person exists. Continue?",QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)
            if answer!=QMessageBox.Yes:return
        self.research_name.setText(name)
        self.research_person()

    def delete_selected_profile(self):
        p=self._selected_vault_profile()
        if not p:return
        name=p.get("canonical_name") or "this profile"
        result=QMessageBox.warning(self,"Delete Knowledge Vault Profile",f"Delete {name} from your local Knowledge Vault?\n\nIf this was built-in starter data, ElectionLab will remember that you deleted it instead of silently restoring it on the next seed update.",QMessageBox.Yes|QMessageBox.Cancel,QMessageBox.Cancel)
        if result != QMessageBox.Yes:return
        photo=p.get("photo_path")
        if self.vault.delete_profile(name):
            if photo:
                try:
                    path=Path(photo)
                    if path.exists() and self.settings.path_for("KnowledgeVault/photos") in path.parents:
                        path.unlink()
                except Exception:
                    pass
            self.refresh_profiles(); self.refresh_vault_table(); self.refresh_dashboard(); self.refresh_campaign_hq()

    def fetch_selected_portrait(self):
        p=self._selected_vault_profile()
        if not p:return
        self._autosave_provider_settings(); name=p.get("canonical_name")
        self.fetch_photo_btn.setEnabled(False); self.vault_status.setText(f"Fetching a public portrait for {name}…")
        self._research_thread=ResearchThread(lambda:self.photo_service.fetch_and_cache(name),self)
        self._research_thread.done.connect(lambda _path:self._portrait_done(name)); self._research_thread.failed.connect(self._portrait_failed); self._research_thread.start()

    def fetch_all_missing_portraits(self):
        self._autosave_provider_settings()
        s=self.settings.settings
        if s.offline_lock or not s.internet_research:
            QMessageBox.information(self,"Portrait Downloads Disabled","Turn off Offline Lock and enable Internet Research first."); return
        profiles=self.vault.list_profiles(limit=5000)
        missing=[]
        for p in profiles:
            path=p.get("photo_path")
            if not path or not Path(path).exists():
                missing.append(p.get("canonical_name"))
        missing=[x for x in missing if x]
        if not missing:
            QMessageBox.information(self,"Portrait Library","Everyone currently in the Knowledge Vault already has a cached portrait."); return
        answer=QMessageBox.question(self,"Fetch Missing Portraits",f"ElectionLab will try to fetch {len(missing)} missing portraits sequentially in the background. Existing portraits will not be replaced. Continue?",QMessageBox.Yes|QMessageBox.No,QMessageBox.Yes)
        if answer!=QMessageBox.Yes:return
        self.fetch_all_photos_btn.setEnabled(False); self.fetch_all_photos_btn.setText("Fetching…")
        self.vault_batch_progress.setValue(0); self.vault_batch_progress.show()
        self.diagnostics.log("INFO","PORTRAIT_BATCH_BEGIN",missing=len(missing))
        self._batch_photo_thread=BatchPortraitThread(missing,self.photo_service,self)
        def portrait_progress(i,total,name):
            self.vault_status.setText(f"Fetching portraits {i}/{total}: {name}… (slow images are retried)")
            self.vault_batch_progress.setValue(int(((i-1)/max(total,1))*100))
            self.vault_batch_progress.setFormat(f"{i}/{total} · {name}")
        self._batch_photo_thread.progress.connect(portrait_progress)
        self._batch_photo_thread.done.connect(self._batch_portraits_done)
        self._batch_photo_thread.start()

    def _batch_portraits_done(self,result):
        self.diagnostics.log("INFO","PORTRAIT_BATCH_COMPLETE",added=len(result.get("ok",[])),failed=len(result.get("failed",[])),failures=result.get("failed",[])[:20])
        self.fetch_all_photos_btn.setEnabled(True); self.fetch_all_photos_btn.setText("Fetch All Missing Portraits")
        self.vault_batch_progress.setValue(100); self.vault_batch_progress.setFormat("Portrait batch complete"); QTimer.singleShot(1800,self.vault_batch_progress.hide)
        ok=result.get("ok",[]); failed=result.get("failed",[])
        self.vault_status.setText(f"Portrait batch complete: {len(ok)} added, {len(failed)} unavailable.")
        self.refresh_vault_table(); self.vault_selection_changed(); self.refresh_campaign_hq()
        # Refresh all four simulation portraits without replacing anything already cached.
        for combo_name,label_name in [("sim_a","_ticket_portrait_a"),("sim_avp","_ticket_vp_portrait_a"),("sim_b","_ticket_portrait_b"),("sim_bvp","_ticket_vp_portrait_b")]:
            combo=getattr(self,combo_name,None); label=getattr(self,label_name,None)
            if combo and label:self._set_portrait(label,combo.currentText())
        detail=""
        if failed:
            names=", ".join(x[0] for x in failed[:10])
            detail=f"\n\nCould not automatically find/download: {names}" + ("…" if len(failed)>10 else "")
        QMessageBox.information(self,"Portrait Batch Complete",f"Added {len(ok)} portraits. {len(failed)} could not be fetched automatically.{detail}")
        self._batch_photo_thread=None

    def import_selected_portrait(self):
        p=self._selected_vault_profile()
        if not p:return
        path,_=QFileDialog.getOpenFileName(self,"Choose Portrait Image","","Images (*.png *.jpg *.jpeg *.webp)")
        if not path:return
        name=p.get("canonical_name")
        try:
            self.photo_service.import_local(name,path)
            self._portrait_done(name)
        except Exception as exc:
            QMessageBox.warning(self,"Portrait Import Failed",str(exc))

    def _portrait_done(self,name):
        self.vault_status.setText(f"Portrait cached for {name}."); self.fetch_photo_btn.setEnabled(True); self.refresh_vault_table(); self.vault_selection_changed(); self.refresh_campaign_hq()
        # Refresh any currently selected simulation ticket portraits by nudging their labels.
        for combo_name, label_name in [("sim_a","_ticket_portrait_a"),("sim_avp","_ticket_vp_portrait_a"),("sim_b","_ticket_portrait_b"),("sim_bvp","_ticket_vp_portrait_b")]:
            combo=getattr(self,combo_name,None); label=getattr(self,label_name,None)
            if combo and label:self._set_portrait(label,combo.currentText())

    def _portrait_failed(self,msg):
        self.diagnostics.log("ERROR","PORTRAIT_DOWNLOAD_FAILED",error=str(msg))
        self.fetch_photo_btn.setEnabled(True); self.vault_status.setText("Portrait fetch failed."); QMessageBox.warning(self,"Portrait Download Failed",msg)

    # ---------- settings ----------
    def choose_data_root(self):
        folder=QFileDialog.getExistingDirectory(self,"Choose ElectionLab Data Folder",self.data_root.text())
        if folder:self.data_root.setText(str(Path(folder)/"ElectionLabData" if Path(folder).name.lower()!="electionlabdata" else Path(folder)))

    def choose_ollama_executable(self):
        start=self.ollama_executable.text().strip() or str(Path.home())
        path,_=QFileDialog.getOpenFileName(self,"Choose Ollama Executable",start,"Ollama executable (ollama.exe);;Executables (*.exe);;All files (*)")
        if path:
            self.ollama_executable.setText(path)
            self._autosave_provider_settings()

    def _autosave_provider_settings(self,*_):
        # This deliberately excludes data_root because changing storage requires service rebinding.
        if not all(hasattr(self,n) for n in ["offline_lock","internet_research","openai_enabled","local_ai_enabled","openai_model","ollama_url","ollama_model","ollama_executable","history_provider"]):
            return
        self.settings.update(
            offline_lock=self.offline_lock.isChecked(),
            internet_research=self.internet_research.isChecked(),
            openai_enabled=self.openai_enabled.isChecked(),
            local_ai_enabled=self.local_ai_enabled.isChecked(),
            openai_model=self.openai_model.text().strip() or "gpt-5.4-mini",
            ollama_base_url=self.ollama_url.text().strip() or "http://127.0.0.1:11434",
            ollama_model=self.ollama_model.text().strip() or "gemma3:12b",
            ollama_executable=self.ollama_executable.text().strip(),
            campaign_history_provider=self.history_provider.currentText(),
        )
        self._update_offline_badge(); self._update_provider_status(); self.refresh_dashboard()

    def _update_provider_status(self):
        if not hasattr(self,"provider_status"):
            return
        s=self.settings.settings; key=bool(load_api_key())
        remote_state="BLOCKED by Offline Lock" if s.offline_lock else ("allowed" if s.internet_research else "disabled")
        openai_state=("enabled" if s.openai_enabled else "disabled") + (" • key stored" if key else " • NO KEY STORED")
        detected=OllamaProvider(s.ollama_base_url,s.ollama_model,s.ollama_executable).find_executable() if s.local_ai_enabled else None
        local_state=("enabled" if s.local_ai_enabled else "disabled") + f" • {s.ollama_model} @ {s.ollama_base_url}"
        if s.local_ai_enabled: local_state += (f" • executable: {detected}" if detected else " • OLLAMA EXECUTABLE NOT FOUND")
        if s.openai_enabled and not key:
            openai_state += " • research/debate calls will fail until a key is stored"
        self.provider_status.setText(
            f"<b>Remote internet:</b> {remote_state}<br>"
            f"<b>OpenAI:</b> {openai_state}<br>"
            f"<b>Local AI:</b> {local_state}<br>"
            f"<b>Campaign history writer:</b> {getattr(s,'campaign_history_provider','Deterministic local')}<br><br>"
            f"<span style='color:#8f9bad'>Election results themselves are computed locally and do not require any AI provider. Ollama/OpenAI are optional for profile enrichment, conversation/debate dialogue, campaign-history narration and AI-written explanations.</span>"
        )

    def test_local_ai(self):
        self._autosave_provider_settings()
        s=self.settings.settings
        if not s.local_ai_enabled:
            QMessageBox.information(self,"Local AI Disabled","Enable Local AI first."); return
        self.provider_status.setText(self.provider_status.text()+"<br><br>Testing local Ollama…")
        self._interaction_thread=ResearchThread(lambda:OllamaProvider(s.ollama_base_url,s.ollama_model,s.ollama_executable).ensure_running(),self)
        self._interaction_thread.done.connect(self._local_ai_test_done); self._interaction_thread.failed.connect(self._interaction_failed); self._interaction_thread.start()

    def _local_ai_test_done(self,result):
        self.diagnostics.log("INFO" if result.get("reachable") else "ERROR","LOCAL_AI_TEST_RESULT",reachable=bool(result.get("reachable")),selected_available=bool(result.get("selected_available")),started=bool(result.get("started")),error=result.get("start_error") or result.get("error"),models=result.get("models",[])[:12])
        self._update_provider_status()
        if result.get("reachable"):
            if result.get("selected_available"):
                QMessageBox.information(self,"Local AI Ready",f"Ollama is reachable and {self.settings.settings.ollama_model} is installed." + ("\n\nElectionLab started the local Ollama service automatically." if result.get("started") else ""))
            else:
                models=", ".join(result.get("models",[])[:8]) or "none reported"
                QMessageBox.warning(self,"Ollama Reachable — Model Missing",f"Ollama is running, but the selected model was not found.\n\nInstalled models: {models}")
        else:
            QMessageBox.warning(self,"Local AI Unreachable",result.get("start_error") or result.get("error") or "Could not reach or start Ollama.")

    def test_openai(self):
        self._autosave_provider_settings()
        s=self.settings.settings
        if s.offline_lock:
            QMessageBox.information(self,"OpenAI Test","Offline Lock is enabled, so remote OpenAI calls are blocked."); return
        if not s.openai_enabled:
            QMessageBox.information(self,"OpenAI Test","Enable the OpenAI provider first."); return
        if not load_api_key():
            QMessageBox.information(self,"OpenAI Test","No stored OpenAI API key was found. Store a key first."); return
        model=s.openai_model
        self.diagnostics.set_ui_action("TEST_OPENAI")
        self.diagnostics.log("INFO","OPENAI_TEST_BEGIN",model=model)
        self.busy_overlay.begin("Testing OpenAI", f"Sending a tiny Responses API request to {model}…", None)
        self._provider_test_thread=ResearchThread(lambda:OpenAIResearchProvider(model).chat("Reply with exactly: ElectionLab OpenAI test OK"),self)
        def done(text):
            self.busy_overlay.finish(); self.diagnostics.log("INFO","OPENAI_TEST_OK",model=model,response=str(text)[:120]); self.diagnostics.clear_ui_action(); self._provider_test_thread=None; self._update_provider_status(); QMessageBox.information(self,"OpenAI Test Passed",f"OpenAI responded successfully using {model}.\n\n{str(text).strip()[:300]}")
        def failed(msg):
            self.busy_overlay.finish(); self.diagnostics.log("ERROR","OPENAI_TEST_FAILED",model=model,error=str(msg)); self.diagnostics.clear_ui_action(); self._provider_test_thread=None; self._update_provider_status(); QMessageBox.warning(self,"OpenAI Test Failed",f"The configured OpenAI provider did not complete the test.\n\n{msg}\n\nSee latest_session.log for details.")
        self._provider_test_thread.done.connect(done); self._provider_test_thread.failed.connect(failed); self._provider_test_thread.start()

    def store_key(self):
        key=self.api_key.text().strip()
        if not key: QMessageBox.warning(self,"No Key","Paste an API key first."); return
        if save_api_key(key):
            self.api_key.clear(); self.api_key.setPlaceholderText("Stored in OS credential service"); self._update_provider_status(); QMessageBox.information(self,"Saved","API key stored using the OS credential service.")
        else:
            QMessageBox.warning(self,"Could Not Store","The OS credential service was unavailable. ElectionLab did not write the key to portable_config.json.")

    def clear_key(self):
        clear_api_key(); self.api_key.clear(); self.api_key.setPlaceholderText("No stored API key"); self._update_provider_status(); QMessageBox.information(self,"Cleared","Stored OpenAI key removed if one existed.")

    def save_settings(self):
        old_root=self.settings.settings.root
        self.settings.update(
            data_root=self.data_root.text().strip(),
            offline_lock=self.offline_lock.isChecked(),
            internet_research=self.internet_research.isChecked(),
            openai_enabled=self.openai_enabled.isChecked(),
            local_ai_enabled=self.local_ai_enabled.isChecked(),
            openai_model=self.openai_model.text().strip() or "gpt-5.4-mini",
            ollama_base_url=self.ollama_url.text().strip() or "http://127.0.0.1:11434",
            ollama_model=self.ollama_model.text().strip() or "gemma3:12b",
            ollama_executable=self.ollama_executable.text().strip(),
            campaign_history_provider=self.history_provider.currentText(),
            default_mode=self.sim_mode.currentText(),
            monte_carlo_runs=self.sim_runs.value(),
        )
        if self.settings.settings.root != old_root:
            self.vault=KnowledgeVault(self.settings)
            self.profile_service=ProfileService(self.settings,self.vault)
            self.photo_service=PhotoService(self.settings,self.vault)
            self.debate_service=DebateService(self.settings,self.vault)
            self.campaigns=CampaignManager(self.settings); self.extensions=ExtensionManager(self.settings)
            from electionlab.data.seed_profiles import built_in_profiles
            self.vault.seed_profiles(built_in_profiles(),"2026.08.26.1")
            self.active_campaign_id=None
            self._active_campaign_obj=None
            self.refresh_profiles(); self.refresh_vault_table(); self.refresh_campaigns(); self.refresh_campaign_hq()
        self._update_offline_badge(); self._update_provider_status(); self.refresh_dashboard()
        QMessageBox.information(self,"Settings Saved","Settings saved. Large ElectionLab data will use the selected data root.")
