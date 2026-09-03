from __future__ import annotations

import sys
import traceback
from datetime import datetime

from PySide6.QtWidgets import QApplication, QMessageBox

from electionlab.core.database import KnowledgeVault
from electionlab.core.diagnostics import SessionDiagnostics
from electionlab.core.settings import SettingsManager
from electionlab.data.seed_profiles import built_in_profiles
from electionlab.ui.main_window import MainWindow
from electionlab.ui.styles import APP_QSS
from electionlab.version import BUILD_SERIES


def _install_exception_hook(settings: SettingsManager, diagnostics: SessionDiagnostics):
    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        diagnostics.log("ERROR", "UNCAUGHT_EXCEPTION", error=str(exc), traceback=text)
        try:
            path = settings.path_for("Logs") / f"crash_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            path.write_text(text, encoding="utf-8")
        except Exception:
            path = None
        QMessageBox.critical(None, "ElectionLab Error", f"Unexpected error:\n{exc}\n\n" + (f"Crash log: {path}" if path else ""))
    sys.excepthook = hook


def main() -> int:
    settings = SettingsManager()
    diagnostics = SessionDiagnostics(settings.path_for("Logs"), BUILD_SERIES)
    diagnostics.log_settings_snapshot(settings.settings)
    _install_exception_hook(settings, diagnostics)
    with diagnostics.span("VAULT_INIT_AND_SEED"):
        vault = KnowledgeVault(settings)
        vault.seed_profiles(built_in_profiles(), "2026.08.27.2")
    app = QApplication(sys.argv)
    app.setApplicationName("ElectionLab")
    app.setOrganizationName("ElectionLab")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_QSS)
    win = MainWindow(settings, vault, diagnostics)
    win.show()
    code = app.exec()
    diagnostics.close()
    return code
