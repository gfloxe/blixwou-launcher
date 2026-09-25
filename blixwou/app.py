import argparse
import ctypes
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import struct
import sys
import time

from PySide6.QtCore import Qt, QEvent, QLockFile, QPropertyAnimation, QThread, Signal, QTimer, QUrl, QRectF, QSize
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontDatabase, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFileDialog, QGridLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QSpinBox, QVBoxLayout, QWidget, QStackedWidget, QSizePolicy, QMenu, QSystemTrayIcon)

from .auth import Accounts
from .config import LauncherError, atomic_json, data_root, load_config, load_settings, resource
from .minecraft import prepare_minecraft, build_command, launch_game, GameSession, game_window_ready
from .network import https_url
from .pack import PackManager
from .status import server_status
from .home_ui import GlowButton, dark_titlebar, skin_head, cached_news, fetch_news
from .updater import LauncherUpdater, available_update
from .process_guard import require_game_stopped

STYLE = """
QWidget { color: #f6f3ff; font-family: 'Segoe UI'; font-size: 14px; }
QDialog, QMessageBox { background: #14111e; }
QPushButton { background: #282132; border: 1px solid #45384f; border-radius: 9px; padding: 11px 18px; text-align: center; }
QPushButton:hover { background: #382647; border-color: #ae79ff; }
QPushButton:pressed { background: #543174; }
QPushButton:disabled { color: #8d8398; background: #231d2d; border-color: #342a40; }
QPushButton#profile { background: rgba(14, 11, 24, 195); border-color: rgba(187, 157, 223, 60); text-align: left; padding: 12px 20px; }
QPushButton#settings, QPushButton#social { background: rgba(17, 13, 28, 190); font-size: 19px; padding: 4px; }
QPushButton#play { background: #9454ef; border: 1px solid #c293ff; border-radius: 12px; font-size: 25px; font-weight: 700; padding: 18px 64px; }
QPushButton#play:hover { background: #ab6bff; }
QPushButton#play:disabled { background: #432d5e; color: #b5a3cb; border-color: #6d5089; }
QLineEdit, QSpinBox { background: #211a2d; border: 1px solid #483755; border-radius: 7px; padding: 9px; selection-background-color: #8244cc; }
QLabel#muted { color: #bdb2ce; font-size: 12px; }
QFrame#dock { background: rgba(13, 10, 23, 222); border: 1px solid rgba(194, 159, 236, 60); border-radius: 16px; }
QFrame#operationCard { background: rgba(18, 12, 30, 238); border: 1px solid #744da0; border-radius: 16px; }
QFrame#operationCard[mode="update"] { background: rgba(10, 24, 35, 242); border-color: #3fa5c9; }
QFrame#operationCard[mode="error"] { background: rgba(43, 17, 31, 242); border-color: #c65e86; }
QLabel#operationBadge { background: #7040a5; border-radius: 10px; color: white; font-size: 11px; font-weight: 700; padding: 5px 10px; }
QLabel#operationBadge[mode="update"] { background: #237b9a; }
QLabel#operationBadge[mode="error"] { background: #9d3d62; }
QLabel#operationTitle { font-size: 17px; font-weight: 700; }
QLabel#operationDetail { color: #c9bbd8; font-size: 12px; }
QLabel#operationPercent { color: #d9c1ff; font-size: 13px; font-weight: 700; }
QProgressBar { background: #2d223c; border: none; border-radius: 3px; height: 5px; }
QProgressBar::chunk { background: #b782ff; border-radius: 3px; }
QToolTip { background: #21162e; color: #ffffff; border: 1px solid #79539c; padding: 5px; }
"""


def open_folder(path):
    path.mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))


def physical_ram_mb():
    if os.name != "nt":
        return None
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in
            ("total", "available", "page_total", "page_available", "virtual_total", "virtual_available", "extended")]
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return status.total // (1024 ** 2)
    return None


class Worker(QThread):
    progress = Signal(str, object, object)
    success = Signal(object)
    failure = Signal(str)

    def __init__(self, task, parent=None):
        super().__init__(parent)
        self.task = task
        self.last = 0
        self.last_step = ""

    def report(self, step, current=0, total=0):
        now = time.monotonic()
        if step != self.last_step or now - self.last > 0.06 or (total and current >= total):
            self.last, self.last_step = now, step
            self.progress.emit(step, current, total)

    def run(self):
        try:
            self.success.emit(self.task(self.report, self.isInterruptionRequested))
        except LauncherError as error:
            logging.warning("%s", error)
            self.failure.emit(str(error))
        except Exception as error:
            # Exception text/tracebacks may contain OAuth request bodies or tokens.
            logging.error("Opération interrompue : %s", type(error).__name__)
            self.failure.emit(f"L’opération a échoué ({type(error).__name__}). Vérifiez la connexion et consultez les journaux, puis réessayez.")


class Landscape(QWidget):
    def __init__(self):
        super().__init__()
        self.picture = QPixmap(str(resource("assets/landscape.png")))
        self.scaled_picture = QPixmap()
        self.scaled_size = None

    def paintEvent(self, event):
        painter = QPainter(self)
        if not self.picture.isNull():
            if self.scaled_size != self.size():
                self.scaled_picture = self.picture.scaled(self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                self.scaled_size = self.size()
            picture = self.scaled_picture
            painter.drawPixmap((self.width()-picture.width())//2, (self.height()-picture.height())//2, picture)
        else:
            painter.fillRect(self.rect(), QColor("#221731"))
        shade = QLinearGradient(0, 0, self.width(), self.height())
        shade.setColorAt(0, QColor(10, 6, 22, 65))
        shade.setColorAt(.55, QColor(14, 8, 30, 25))
        shade.setColorAt(1, QColor(7, 5, 17, 190))
        painter.fillRect(self.rect(), shade)
        bottom = QLinearGradient(0, self.height() * .55, 0, self.height())
        bottom.setColorAt(0, QColor(8, 4, 18, 0))
        bottom.setColorAt(1, QColor(8, 4, 18, 200))
        painter.fillRect(self.rect(), bottom)


class Wordmark(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumHeight(112)
        self.setAccessibleName("BLIXWOU")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        font = QFont("Bahnschrift", max(42, min(78, self.width() // 9)), QFont.Black)
        font.setLetterSpacing(QFont.AbsoluteSpacing, 4)
        painter.setFont(font)
        painter.setPen(QColor(8, 4, 18, 100))
        painter.drawText(QRectF(3, 5, self.width()-3, self.height()), Qt.AlignLeft | Qt.AlignVCenter, "BLIXWOU")
        painter.setPen(QColor("#ffffff"))
        painter.drawText(QRectF(0, 0, self.width(), self.height()), Qt.AlignLeft | Qt.AlignVCenter, "BLIXWOU")


class SettingsDialog(QDialog):
    def __init__(self, root, parent):
        super().__init__(parent)
        self.setWindowTitle("Paramètres · BLIXWOU")
        self.setObjectName("settingsDialog")
        self.setMinimumWidth(640)
        self.setMaximumWidth(760)
        self.setStyleSheet(self.SETTINGS_STYLE)
        self.root = root
        settings = load_settings(root)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 18, 28, 20)
        layout.setSpacing(10)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(12)
        badge = QLabel("⚙")
        badge.setObjectName("settingsBadge")
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedSize(38, 38)
        brand_row.addWidget(badge)
        brand = QLabel("BLIXWOU  /  PARAMÈTRES")
        brand.setObjectName("settingsBrand")
        brand_row.addWidget(brand)
        brand_row.addStretch()
        runtime = QLabel("JAVA 21  •  64 BITS")
        runtime.setObjectName("runtimePill")
        brand_row.addWidget(runtime)
        layout.addLayout(brand_row)

        heading = QLabel("Personnalisez votre expérience")
        heading.setObjectName("settingsHeading")
        layout.addWidget(heading)
        subtitle = QLabel("Ajustez les performances, la fenêtre du jeu et les fichiers de BLIXWOU.")
        subtitle.setObjectName("settingsSubtitle")
        layout.addWidget(subtitle)

        performance = QFrame()
        performance.setObjectName("settingsCard")
        performance_layout = QVBoxLayout(performance)
        performance_layout.setContentsMargins(16, 11, 16, 11)
        performance_layout.setSpacing(5)
        performance_header = QHBoxLayout()
        performance_header.addWidget(self.section_title("PERFORMANCES", "Mémoire allouée à Minecraft"))
        self.ram = QSpinBox()
        self.ram.setRange(2048, 32768)
        self.ram.setSingleStep(512)
        self.ram.setSuffix(" Mo")
        self.ram.setValue(settings["ramMb"])
        self.ram.setFixedWidth(142)
        performance_header.addWidget(self.ram, alignment=Qt.AlignVCenter)
        performance_layout.addLayout(performance_header)
        self.ram_warning = QLabel()
        self.ram_warning.setObjectName("settingsWarning")
        self.ram_warning.setWordWrap(True)
        performance_layout.addWidget(self.ram_warning)
        total_ram = physical_ram_mb()

        def update_ram_warning(value):
            excessive = total_ram is not None and value > total_ram / 2
            recommended = min(6144, int(total_ram // 2048) * 1024) if total_ram else 4096
            self.ram_warning.setText(
                f"Trop de RAM allouée : Windows risque de ralentir. {recommended} Mo recommandés sur {total_ram / 1024:.0f} Go."
                if excessive else "")
            self.ram_warning.setVisible(excessive)
        self.ram.valueChanged.connect(update_ram_warning)
        update_ram_warning(self.ram.value())
        layout.addWidget(performance)

        display = QFrame()
        display.setObjectName("settingsCard")
        display_layout = QHBoxLayout(display)
        display_layout.setContentsMargins(16, 11, 16, 11)
        display_layout.addWidget(self.section_title("AFFICHAGE", "Résolution de la fenêtre du jeu"))
        display_layout.addStretch()
        resolution = QHBoxLayout()
        resolution.setSpacing(8)
        self.width_box, self.height_box = QSpinBox(), QSpinBox()
        self.width_box.setRange(854, 7680)
        self.height_box.setRange(480, 4320)
        self.width_box.setValue(settings["width"])
        self.height_box.setValue(settings["height"])
        self.width_box.setFixedWidth(100)
        self.height_box.setFixedWidth(100)
        resolution.addWidget(self.width_box)
        multiply = QLabel("×")
        multiply.setObjectName("multiply")
        resolution.addWidget(multiply)
        resolution.addWidget(self.height_box)
        display_layout.addLayout(resolution)
        layout.addWidget(display)

        java_card = QFrame()
        java_card.setObjectName("settingsCard")
        java_layout = QVBoxLayout(java_card)
        java_layout.setContentsMargins(16, 11, 16, 11)
        java_layout.setSpacing(6)
        java_layout.addWidget(self.section_title("MOTEUR JAVA", "Laissez vide pour utiliser Java 21 automatiquement"))
        self.java = QLineEdit(settings["javaPath"])
        self.java.setPlaceholderText("Sélection automatique · Java 21 x64")
        java_row = QHBoxLayout()
        java_row.setSpacing(8)
        java_row.addWidget(self.java)
        browse = QPushButton("Parcourir")
        browse.setObjectName("compactAction")
        browse.setFixedWidth(102)
        browse.clicked.connect(self.browse_java)
        java_row.addWidget(browse)
        java_layout.addLayout(java_row)
        layout.addWidget(java_card)

        files = QFrame()
        files.setObjectName("settingsCard")
        files_layout = QVBoxLayout(files)
        files_layout.setContentsMargins(16, 11, 16, 11)
        files_layout.setSpacing(7)
        files_layout.addWidget(self.section_title("FICHIERS & MAINTENANCE", "Accès rapide aux dossiers locaux"))
        folders = QGridLayout()
        folders.setHorizontalSpacing(8)
        folders.setVerticalSpacing(8)
        items = [
            ("↗  Dossier du jeu", root / "game"),
            ("↗  Journaux", root / "logs"),
            ("↗  Mods", root / "game" / "mods"),
            ("↗  Shaders", root / "game" / "shaderpacks"),
        ]
        for index, (name, path) in enumerate(items):
            button = QPushButton(name)
            button.setObjectName("folderAction")
            button.clicked.connect(lambda checked=False, p=path: open_folder(p))
            folders.addWidget(button, index // 2, index % 2)
        files_layout.addLayout(folders)
        maintenance = QHBoxLayout()
        maintenance_text = QLabel("La désinstallation conserve les données du jeu.")
        maintenance_text.setObjectName("settingsHint")
        maintenance.addWidget(maintenance_text)
        maintenance.addStretch()
        uninstall_button = QPushButton("Désinstaller BLIXWOU")
        uninstall_button.setObjectName("dangerAction")
        uninstall_button.setToolTip("Ouvrir le désinstalleur Windows. Les données du jeu sont conservées.")
        uninstall_button.clicked.connect(self.uninstall)
        maintenance.addWidget(uninstall_button)
        files_layout.addLayout(maintenance)
        layout.addWidget(files)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Enregistrer")
        buttons.button(QDialogButtonBox.Cancel).setText("Annuler")
        buttons.button(QDialogButtonBox.Save).setObjectName("saveSettings")
        buttons.button(QDialogButtonBox.Cancel).setObjectName("cancelSettings")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @staticmethod
    def section_title(eyebrow, description):
        container = QWidget()
        box = QVBoxLayout(container)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(3)
        title = QLabel(eyebrow)
        title.setObjectName("settingsEyebrow")
        box.addWidget(title)
        detail = QLabel(description)
        detail.setObjectName("settingsHint")
        box.addWidget(detail)
        return container

    SETTINGS_STYLE = """
    QDialog#settingsDialog { background: #100c18; color: #f7f2ff; }
    QLabel#settingsBadge { background: #8f4be8; border: 1px solid #c79bff;
        border-radius: 10px; color: white; font-size: 19px; font-weight: 800; }
    QLabel#settingsBrand { color: #d8c4ed; font-size: 11px; font-weight: 700;
        letter-spacing: 3px; }
    QLabel#runtimePill { background: #1f1830; border: 1px solid #4b3862;
        border-radius: 12px; color: #c8a5ee; font-size: 10px; font-weight: 700;
        padding: 6px 10px; }
    QLabel#settingsHeading { color: white; font-size: 25px; font-weight: 750;
        margin-top: 1px; }
    QLabel#settingsSubtitle { color: #b7a9c6; font-size: 13px; }
    QFrame#settingsCard { background: #191322; border: 1px solid #3b2c4d;
        border-radius: 14px; }
    QFrame#settingsCard:hover { border-color: #59406e; }
    QLabel#settingsEyebrow { color: #b990e7; font-size: 10px; font-weight: 750;
        letter-spacing: 2px; }
    QLabel#settingsHint { color: #a99db7; font-size: 12px; }
    QLabel#multiply { color: #a98cce; font-size: 16px; font-weight: 700; }
    QLabel#settingsWarning { background: #2c1d19; border: 1px solid #714735;
        border-radius: 8px; color: #ffc29f; padding: 8px 10px; font-size: 12px; }
    QLineEdit, QSpinBox { background: #100c18; border: 1px solid #453455;
        border-radius: 9px; color: white; padding: 9px 11px; min-height: 20px;
        selection-background-color: #8f4be8; }
    QLineEdit:hover, QSpinBox:hover { border-color: #6c4b89; }
    QLineEdit:focus, QSpinBox:focus { border: 1px solid #a767f5; background: #15101e; }
    QPushButton#compactAction, QPushButton#folderAction { background: #261c31;
        border: 1px solid #473557; border-radius: 9px; color: #d3c5df;
        padding: 7px 12px; text-align: left; }
    QPushButton#compactAction { text-align: center; }
    QPushButton#compactAction:hover, QPushButton#folderAction:hover {
        background: #332141; border-color: #8f5db8; color: white; }
    QPushButton#dangerAction { background: transparent; border: 1px solid #633645;
        border-radius: 9px; color: #e99bad; padding: 8px 12px; }
    QPushButton#dangerAction:hover { background: #321a22; border-color: #a64b65; color: #ffc0cf; }
    QPushButton#saveSettings { background: #914cf0; border: 1px solid #c28cff;
        border-radius: 10px; color: white; padding: 11px 24px; font-weight: 700; }
    QPushButton#saveSettings:hover { background: #a65eff; }
    QPushButton#cancelSettings { background: transparent; border: 1px solid #493858;
        border-radius: 10px; color: #c6b8d4; padding: 11px 20px; }
    QPushButton#cancelSettings:hover { background: #251a31; border-color: #7c59a0; color: white; }
    """

    def uninstall(self):
        parent = self.parent()
        if getattr(parent, 'busy', False):
            QMessageBox.information(self, "BLIXWOU est actif", "Fermez Minecraft ou attendez la fin de l’installation avant de désinstaller.")
            return
        uninstaller = Path(sys.executable).parent / 'unins000.exe'
        if getattr(sys, 'frozen', False) and uninstaller.is_file():
            try:
                os.startfile(str(uninstaller))
            except OSError:
                QMessageBox.warning(self, "BLIXWOU", "Impossible d’ouvrir le désinstalleur. Utilisez les applications installées de Windows.")
                return
            self.reject()
            parent.close()
        else:
            QMessageBox.information(self, "Version portable", "Cette copie ne possède pas de désinstalleur. Une version installée peut être retirée depuis les applications Windows. Pour cette copie portable, fermez-la puis supprimez son dossier.")
            QDesktopServices.openUrl(QUrl('ms-settings:appsfeatures'))

    def browse_java(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Choisir Java 21 x64", "", "Java (java.exe)")
        if filename:
            self.java.setText(filename)

    def save(self):
        atomic_json(self.root / "settings.json", {"ramMb": self.ram.value(), "width": self.width_box.value(), "height": self.height_box.value(), "javaPath": self.java.text().strip()})
        self.accept()


class ProfileDialog(QDialog):
    def __init__(self, accounts, parent):
        super().__init__(parent)
        self.accounts = accounts
        self.choice = None
        self.setWindowTitle("Votre profil · BLIXWOU")
        self.setMinimumWidth(450)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        title = QLabel("Choisissez votre profil")
        title.setStyleSheet("font-size: 23px; font-weight: 600;")
        layout.addWidget(title)
        microsoft = QPushButton("Choisir un compte Microsoft")
        microsoft.clicked.connect(self.microsoft)
        layout.addWidget(microsoft)
        note = QLabel("Choisissez un compte existant ou utilisez un autre compte.\nConnexion dans le navigateur · Accès Java vérifié")
        note.setObjectName("muted")
        layout.addWidget(note)
        layout.addSpacing(18)
        layout.addWidget(QLabel("Profil hors ligne"))
        self.name = QLineEdit()
        self.name.setPlaceholderText("Votre pseudo")
        self.name.setMaxLength(16)
        selected = accounts.selected()
        if selected and selected["mode"] == "offline":
            self.name.setText(selected["name"])
        layout.addWidget(self.name)
        offline = QPushButton("Utiliser ce pseudo hors ligne")
        offline.clicked.connect(self.offline)
        layout.addWidget(offline)
        self.name.returnPressed.connect(self.offline)
        notice = QLabel("Ce profil ne constitue pas une identité Microsoft.\nLa protection des pseudos dépend du serveur.")
        notice.setObjectName("muted")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        if selected:
            logout = QPushButton("Déconnecter le profil")
            logout.clicked.connect(self.logout)
            layout.addWidget(logout)

    def microsoft(self):
        self.choice = "microsoft"
        self.accept()

    def offline(self):
        try:
            self.accounts.save_offline(self.name.text().strip())
            self.choice = "offline"
            self.accept()
        except LauncherError as error:
            QMessageBox.warning(self, "Pseudo invalide", str(error))

    def logout(self):
        self.accounts.logout()
        self.accept()


class MainWindow(QMainWindow):
    shutdown_requested = Signal()
    update_problem = Signal(str)

    def __init__(self, root, config, network=True):
        super().__init__()
        self.root, self.config, self.network = root, config, network
        self.accounts = Accounts(root, config["microsoft"])
        self.manifest = None
        self.busy = False
        self.game_session = GameSession()
        self.job = None
        self.status_job = None
        self.maintenance_job = None
        self.integrity_cache = {}
        self.repair_pending = False
        self.updater = None
        self.updating = False
        self.update_check = None
        self.update_version = None
        self.closing = False
        self.game_ready = False
        self.game_ready_observations = 0
        self.tray_hiding = False
        self.setWindowTitle("BLIXWOU")
        self.setWindowIcon(QIcon(str(resource("assets/blixwou.ico"))))
        self.tray = QSystemTrayIcon(self.windowIcon(), self)
        self.tray.setToolTip('BLIXWOU · Minecraft en cours')
        tray_menu = QMenu(self)
        self.tray_show_action = tray_menu.addAction('Afficher BLIXWOU')
        self.tray_show_action.triggered.connect(self.restore_from_tray)
        self.tray_stop_action = tray_menu.addAction('Arrêter Minecraft')
        self.tray_stop_action.triggered.connect(self.stop_game)
        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray_animation = QPropertyAnimation(self, b'windowOpacity', self)
        self.tray_animation.setDuration(240)
        self.tray_animation.finished.connect(self.finish_tray_animation)
        self.game_ready_timer = QTimer(self)
        self.game_ready_timer.setInterval(750)
        self.game_ready_timer.timeout.connect(self.check_game_ready)
        self.resize(1280, 720)
        self.setMinimumSize(960, 620)
        scene = Landscape()
        shell = QWidget()
        shell.setObjectName('navigationShell')
        shell.setStyleSheet('QWidget#navigationShell { background-color: #14111e; }')
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        nav = QHBoxLayout()
        nav.setContentsMargins(36, 12, 36, 12)
        brand = QLabel("B  /  BLIXWOU")
        brand.setStyleSheet("font-weight: 700; letter-spacing: 3px; color: #d7b7ff; margin-right: 32px;")
        nav.addWidget(brand)
        self.home_button = GlowButton('Accueil')
        self.wardrobe_button = GlowButton('Skin')
        for button in (self.home_button, self.wardrobe_button):
            button.setCheckable(True)
            button.setObjectName("navTab")
            button.setStyleSheet("QPushButton { background: transparent; border: 0; padding: 10px 22px; color: #c6bad7; } QPushButton:checked { background: #372349; color: #ecdfff; border-bottom: 2px solid #b782ff; } QPushButton:hover { background: #2e203e; }")
            nav.addWidget(button)
        nav.addStretch()
        self.community_accounts = None
        self.community_button = QPushButton('Compte BLIXWOU')
        self.community_button.setToolTip('Connexion au compte communautaire BLIXWOU')
        self.community_button.clicked.connect(self.open_community_account)
        self.community_button.setVisible(bool(config.get('firebase')))
        nav.addWidget(self.community_button)
        shell_layout.addLayout(nav)
        self.pages = QStackedWidget()
        self.pages.addWidget(scene)
        shell_layout.addWidget(self.pages)
        self.wardrobe_page = None
        self.home_button.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        self.wardrobe_button.clicked.connect(self.open_wardrobe)
        self.pages.currentChanged.connect(self.refresh_navigation)
        self.home_button.setChecked(True)
        self.setCentralWidget(shell)
        layout = QVBoxLayout(scene)
        self.home_layout = layout
        layout.setContentsMargins(44, 28, 44, 24)
        top = QHBoxLayout()
        self.profile = QPushButton()
        self.profile.setObjectName("profile")
        self.profile.setMinimumWidth(230)
        self.profile.setAccessibleName("Ouvrir les skins du joueur")
        self.profile.setIconSize(QSize(48, 48))
        self.profile.clicked.connect(self.open_wardrobe)
        top.addWidget(self.profile)
        top.addStretch()
        self.settings_button = GlowButton("⚙")
        self.settings_button.setObjectName("settings")
        self.settings_button.setFixedSize(46, 46)
        self.settings_button.setToolTip("Paramètres")
        self.settings_button.setAccessibleName("Paramètres")
        self.settings_button.clicked.connect(lambda: SettingsDialog(root, self).exec())
        nav.addWidget(self.settings_button)
        layout.addLayout(top)
        layout.addStretch(1)
        hero = QHBoxLayout()
        hero.setSpacing(44)
        title_col = QVBoxLayout()
        title_col.setSpacing(4)
        title_col.addWidget(Wordmark())
        edition = QLabel("MINECRAFT JAVA  /  1.21.1")
        edition.setStyleSheet("color: #e2cfee; font-size: 12px; letter-spacing: 3px;")
        title_col.addWidget(edition)
        title_col.addStretch()
        hero.addLayout(title_col, 3)
        self.news_card = QFrame()
        self.news_card.setObjectName('dock')
        self.news_card.setMaximumWidth(460)
        self.news_layout = QVBoxLayout(self.news_card)
        self.news_layout.setContentsMargins(24, 22, 24, 22)
        self.news_layout.setSpacing(14)
        hero.addWidget(self.news_card, 2)
        layout.addLayout(hero)
        layout.addStretch(1)

        self.progress_panel = QWidget()
        progress_layout = QVBoxLayout(self.progress_panel)
        progress_layout.setContentsMargins(0, 4, 0, 0)
        self.step = QLabel("Prêt à jouer")
        self.step.setWordWrap(True)
        progress_layout.addWidget(self.step)
        self.orphan_warning = QLabel()
        self.orphan_warning.setObjectName("muted")
        self.orphan_warning.setWordWrap(True)
        self.orphan_warning.hide()
        self.update_notice = QLabel()
        self.update_notice.setObjectName('muted')
        self.update_notice.setWordWrap(True)
        self.update_notice.hide()

        self.operation_card = QFrame()
        self.operation_card.setObjectName("operationCard")
        self.operation_card.setProperty("mode", "install")
        operation_layout = QHBoxLayout(self.operation_card)
        operation_layout.setContentsMargins(22, 16, 22, 16)
        operation_layout.setSpacing(16)
        self.operation_badge = QLabel("PACK")
        self.operation_badge.setObjectName("operationBadge")
        self.operation_badge.setProperty("mode", "install")
        self.operation_badge.setAlignment(Qt.AlignCenter)
        self.operation_badge.setFixedWidth(74)
        operation_layout.addWidget(self.operation_badge)
        operation_text = QVBoxLayout()
        operation_text.setSpacing(4)
        self.operation_title = QLabel("Préparation de BLIXWOU")
        self.operation_title.setObjectName("operationTitle")
        operation_text.addWidget(self.operation_title)
        self.operation_detail = QLabel("Analyse des fichiers locaux")
        self.operation_detail.setObjectName("operationDetail")
        self.operation_detail.setWordWrap(True)
        operation_text.addWidget(self.operation_detail)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(7)
        operation_text.addWidget(self.bar)
        operation_layout.addLayout(operation_text, 1)
        self.operation_percent = QLabel("EN COURS")
        self.operation_percent.setObjectName("operationPercent")
        operation_layout.addWidget(self.operation_percent, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.operation_card.hide()
        layout.addWidget(self.operation_card)

        dock = QFrame()
        dock.setObjectName("dock")
        dock.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        dock_layout = QHBoxLayout(dock)
        dock_layout.setContentsMargins(26, 20, 22, 20)
        server_col = QVBoxLayout()
        server_col.setSpacing(8)
        server_col.setAlignment(Qt.AlignVCenter)
        caption = QLabel("SERVEUR BLIXWOU")
        caption.setObjectName("muted")
        caption.setStyleSheet("letter-spacing: 2px;")
        server_col.addWidget(caption)
        self.status_label = QLabel("●  Indisponible")
        self.status_label.setStyleSheet("font-size: 19px; color: #c3b5d7;")
        self.status_label.setToolTip("Aucune réponse de statut reçue pour le moment.")
        server_col.addWidget(self.status_label)
        server_col.addWidget(self.progress_panel)
        server_col.addWidget(self.orphan_warning)
        server_col.addWidget(self.update_notice)
        dock_layout.addLayout(server_col, 1)
        dock_layout.setSpacing(32)
        self.play = QPushButton("Jouer  ›")
        self.play.setObjectName("play")
        self.play.clicked.connect(self.play_clicked)
        dock_layout.addWidget(self.play)
        layout.addWidget(dock)
        socials = QHBoxLayout()
        socials.setContentsMargins(0, 12, 0, 0)
        self.social_buttons = {}
        for name, label, glyph in [("discord", "Discord", "◉"), ("website", "Site web", "◎"), ("tiktok", "TikTok", "♪"), ("youtube", "YouTube", "▶")]:
            button = QPushButton(glyph)
            button.setObjectName("social")
            button.setFixedSize(36, 36)
            button.setToolTip(label)
            button.setAccessibleName(label)
            button.clicked.connect(lambda checked=False, key=name: self.open_social(key))
            socials.addWidget(button)
            self.social_buttons[name] = button
        socials.addStretch()
        layout.addLayout(socials)
        self.refresh_profile()
        self.refresh_socials()
        self.news_job = None
        self.show_news(cached_news(root))
        if network:
            self.news_job = Worker(lambda progress, cancelled: fetch_news(root), self)
            self.news_job.success.connect(self.show_news)
            self.news_job.start()
        self.shutdown_requested.connect(self.close)
        self.update_problem.connect(self.update_failed)
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.check_status)
        self.maintenance_timer = QTimer(self)
        self.maintenance_timer.setInterval(5000)
        self.maintenance_timer.timeout.connect(self.check_maintenance)
        if network:
            self.timer.start()
            self.maintenance_timer.start()
            QTimer.singleShot(0, self.startup)

    def startup(self):
        self.check_status()
        self.updating = True
        self.update_controls(False)
        self.update_check = Worker(lambda progress, cancelled: available_update(
            self.config['launcherUpdate'].get('appcastUrl'), self.config['appVersion']), self)
        self.update_check.success.connect(lambda value: setattr(self, 'update_version', value))
        self.update_check.finished.connect(self.update_checked)
        self.update_check.start()

    def update_controls(self, enabled):
        for widget in (self.play, self.profile, self.settings_button, self.wardrobe_button, self.community_button):
            widget.setEnabled(enabled)
        if self.wardrobe_page is not None:
            self.wardrobe_page.setEnabled(enabled)

    def can_update_shutdown(self):
        if self.busy or self.game_session.process is not None:
            return False
        try:
            require_game_stopped(self.root)
        except LauncherError:
            return False
        return True

    def update_checked(self):
        self.update_check.deleteLater()
        self.update_check = None
        if self.closing:
            return
        if not self.update_version or not self.can_update_shutdown():
            self.updating = False
            self.update_controls(True)
            self.startup_pack()
            return
        self.show_operation('update', 'Mise à jour du launcher',
                            'Installation sécurisée de BLIXWOU ' + self.update_version, 0, 0)
        try:
            self.updater = LauncherUpdater(self.config['launcherUpdate'], self.config['appVersion'],
                self.can_update_shutdown, self.shutdown_requested.emit,
                lambda: self.update_problem.emit('Mise à jour indisponible. Vous pouvez continuer à jouer.'),
                lambda: self.update_problem.emit('Mise à jour interrompue. Vous pouvez continuer à jouer.'))
            self.updater.install()
        except Exception:
            self.update_failed('Mise à jour indisponible. Vous pouvez continuer à jouer.')

    def update_failed(self, message):
        if not self.updating or self.closing:
            return
        self.updating = False
        if self.updater:
            self.updater.close()
            self.updater = None
        self.update_notice.setText(message)
        self.update_notice.show()
        self.hide_operation()
        self.update_controls(True)
        self.startup_pack()

    def startup_pack(self):
        if self.config.get("manifestUrl"):
            self.start_job(lambda progress, cancelled: self.sync_pack(progress), self.pack_ready)
        else:
            self.step.setText("Le pack BLIXWOU n’est pas encore disponible. La connexion Microsoft reste accessible depuis le profil.")
            self.hide_operation()
            self.progress_panel.show()

    def sync_pack(self, progress):
        require_game_stopped(self.root)
        return PackManager(self.root, progress).fetch_and_sync(self.config["manifestUrl"])

    def pack_ready(self, manifest):
        self.manifest = manifest
        self.integrity_cache = {}
        self.repair_pending = False
        self.refresh_socials()
        self.check_status()

    def refresh_socials(self):
        self.socials = self.manifest["socials"] if self.manifest else self.config["socials"]
        for name, button in self.social_buttons.items():
            button.setVisible(bool(self.socials.get(name)))

    def open_social(self, key):
        try:
            QDesktopServices.openUrl(QUrl(https_url(self.socials[key])))
        except LauncherError as error:
            self.show_error(str(error))

    def refresh_profile(self):
        profile = self.accounts.selected()
        if profile:
            self.profile.setText(f"  {profile['name']}")
        else:
            self.profile.setText("  Choisir un profil")

        self.profile.setIcon(QIcon(skin_head(self.root)))

    def choose_profile(self):
        dialog = ProfileDialog(self.accounts, self)
        if dialog.exec() == QDialog.Accepted:
            self.refresh_profile()
            if dialog.choice == "microsoft":
                self.start_job(lambda progress, cancelled: self.accounts.login(progress, cancelled), lambda result: self.refresh_profile())

    def check_status(self):
        if self.status_job is not None:
            return
        server = self.manifest["server"] if self.manifest else self.config["server"]
        job = Worker(lambda progress, cancelled: server_status(server["host"], server["port"]), self)
        self.status_job = job
        job.success.connect(self.set_status)
        job.failure.connect(lambda error: self.set_status({"state": "unknown", "text": "Indisponible"}))
        def finished():
            self.status_job = None
            job.deleteLater()
        job.finished.connect(finished)
        job.start()

    def check_maintenance(self):
        """Check launcher and pack integrity every five seconds without blocking Qt."""
        if (self.maintenance_job is not None or self.updating or self.busy
                or self.game_session.process is not None or not self.config.get("manifestUrl")):
            return
        cache = dict(self.integrity_cache)
        def inspect(progress, cancelled):
            manager = PackManager(self.root)
            manifest = manager.fetch_manifest(self.config["manifestUrl"], fresh=True)
            issues, verified = manager.audit(manifest, cache)
            version = available_update(self.config['launcherUpdate'].get('appcastUrl'), self.config['appVersion'])
            return {"manifest": manifest, "issues": issues, "cache": verified, "update": version}
        job = Worker(inspect, self)
        self.maintenance_job = job
        job.success.connect(self.maintenance_ready)
        def finished():
            self.maintenance_job = None
            job.deleteLater()
        job.finished.connect(finished)
        job.start()

    def maintenance_ready(self, result):
        self.manifest = result["manifest"]
        self.integrity_cache = result["cache"]
        self.refresh_socials()
        if result["update"]:
            self.update_notice.setText("Mise à jour du launcher disponible : " + result["update"])
            self.update_notice.show()
        if not result["issues"]:
            if not self.busy:
                self.step.setText("Pack vérifié · à jour")
            return
        self.integrity_cache = {}
        self.step.setText("Écart détecté · réparation automatique du pack")
        if not self.repair_pending and not self.busy and self.game_session.process is None:
            self.repair_pending = True
            self.start_job(lambda progress, cancelled: self.sync_pack(progress), self.pack_ready)

    def set_status(self, status):
        color = {"online": "#89e1b1", "offline": "#e2a4b9", "unknown": "#c3b5d7"}[status["state"]]
        text = status["text"]
        if status['state'] == 'online':
            text = 'En ligne'
            if all(status.get(key) is not None for key in ('online', 'max', 'latency')):
                text += f" · {status['online']}/{status['max']} joueurs · {status['latency']} ms"
        self.status_label.setText("●  " + text)
        self.status_label.setStyleSheet(f"font-size: 19px; color: {color};")
        self.status_label.setToolTip("Dernière vérification : " + time.strftime("%H:%M:%S") + "\nUn délai réseau ne permet pas de conclure que le serveur est hors ligne.")

    def start_job(self, task, success):
        if self.updating or self.busy:
            return
        if self.wardrobe_page is not None:
            self.wardrobe_page.setEnabled(False)
        self.busy = True
        for widget in (self.play, self.profile, self.settings_button, self.wardrobe_button, self.community_button):
            widget.setEnabled(False)
        self.progress_panel.show()
        self.show_operation('install', 'Installation du pack', 'Analyse des fichiers locaux', 0, 0)
        job = Worker(task, self)
        self.job = job
        job.progress.connect(self.report)
        job.success.connect(success)
        job.failure.connect(self.show_error)
        job.finished.connect(self.job_finished)
        job.start()

    def report(self, step, current, total):
        if step.startswith(("Mods hors pack :", "Fichiers hors pack :")):
            self.orphan_warning.setText(step + " · Vérifiez le dossier des mods dans les paramètres.")
            self.orphan_warning.setVisible(not step.endswith(": aucun"))
            return
        if step == "Minecraft est lancé":
            self.play.setText("Arrêter  ■")
            self.play.setEnabled(True)
            self.hide_operation()
            self.game_ready = False
            self.game_ready_observations = 0
            if self.game_session.process is not None:
                self.game_ready_timer.start()
        text = step
        if total:
            if total > 100000:
                text += f" · {current / 1024**2:.1f} / {total / 1024**2:.1f} Mo"
            else:
                text += f" · {current} / {total}"
            self.bar.setRange(0, 1000)
            self.bar.setValue(min(1000, int(current * 1000 / total)))
            self.operation_percent.setText(f"{min(100, int(current * 100 / total))} %")
        else:
            self.bar.setRange(0, 0)  # Indeterminate, never a fabricated percentage.
            self.operation_percent.setText("EN COURS")
        self.step.setText(text)
        if step != "Minecraft est lancé":
            self.operation_title.setText(step)
            self.operation_detail.setText(text if text != step else "Préparation et vérification des fichiers")
            self.operation_card.show()

    def show_operation(self, mode, title, detail, current=0, total=0):
        self.operation_card.setProperty('mode', mode)
        self.operation_badge.setProperty('mode', mode)
        self.operation_badge.setText({'install': 'PACK', 'update': 'UPDATE', 'error': 'ATTENTION'}.get(mode, 'PACK'))
        for widget in (self.operation_card, self.operation_badge):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.operation_title.setText(title)
        self.operation_detail.setText(detail)
        if total:
            self.bar.setRange(0, 1000)
            self.bar.setValue(min(1000, int(current * 1000 / total)))
            self.operation_percent.setText(f"{min(100, int(current * 100 / total))} %")
        else:
            self.bar.setRange(0, 0)
            self.operation_percent.setText("EN COURS")
        self.bar.show()
        self.operation_card.show()

    def hide_operation(self):
        self.bar.hide()
        self.operation_card.hide()

    def show_error(self, message):
        if self.tray.isVisible():
            self.restore_from_tray()
        self.step.setText(message)
        self.show_operation('error', 'Une action est requise', message)
        self.bar.hide()
        self.operation_percent.setText("ERREUR")
        self.progress_panel.show()
        QMessageBox.warning(self, "BLIXWOU", message)

    def job_finished(self):
        self.game_ready_timer.stop()
        self.game_ready = False
        self.game_ready_observations = 0
        if self.tray.isVisible() or self.tray_hiding:
            self.restore_from_tray()
            self.tray.hide()
        if self.wardrobe_page is not None:
            self.wardrobe_page.setEnabled(True)
        self.busy = False
        self.repair_pending = False
        self.play.setText("Jouer  ›")
        for widget in (self.play, self.profile, self.settings_button, self.wardrobe_button, self.community_button):
            widget.setEnabled(True)
        self.hide_operation()
        self.job.deleteLater()
        self.job = None

    def play_clicked(self):
        if self.updating:
            return
        if self.game_session.process is not None:
            self.stop_game()
            return
        if not self.config.get("manifestUrl"):
            self.show_error("Le pack du serveur BLIXWOU n’est pas encore disponible. Ses mods et sa configuration doivent être ajoutés avant de jouer. Vous pouvez déjà connecter votre compte depuis le profil.")
            return
        if not self.accounts.selected():
            self.choose_profile()
            return
        def play(progress, cancelled):
            manifest = self.sync_pack(progress)
            java, version = prepare_minecraft(self.root, manifest, load_settings(self.root), progress)
            # Refresh after installation so access tokens don't expire during downloads.
            progress("Vérification du profil", 0, 0)
            profile = self.accounts.for_launch()
            args = build_command(self.root, version, java, load_settings(self.root), profile, manifest["server"])
            from .skins import Wardrobe
            Wardrobe(self.root).export_active(self.root / 'game')
            launch_game(self.root, args, profile, progress, self.game_session)
            return manifest
        def done(manifest):
            self.pack_ready(manifest)
            self.step.setText("Session terminée · prêt à jouer")
            self.refresh_profile()
        self.start_job(play, done)

    def stop_game(self):
        if self.game_session.process is None:
            return
        self.game_session.stop()
        self.play.setText("Arrêt en cours…")
        self.play.setEnabled(False)
        self.step.setText("Fermeture de Minecraft…")

    def check_game_ready(self):
        process = self.game_session.process
        if process is None or process.poll() is not None:
            self.game_ready_timer.stop()
            return
        if game_window_ready(process):
            self.game_ready_observations += 1
            if self.game_ready_observations < 2:
                return
            self.game_ready_timer.stop()
            self.game_ready = True
            if QSystemTrayIcon.isSystemTrayAvailable():
                self.step.setText("Minecraft est prêt · BLIXWOU reste dans les icônes cachées")
                self.hide_to_tray()
            else:
                self.step.setText("Minecraft est prêt · zone de notification indisponible")
        else:
            self.game_ready_observations = 0

    def hide_to_tray(self):
        if (not self.game_ready or self.game_session.process is None
                or not QSystemTrayIcon.isSystemTrayAvailable() or self.isHidden() or self.tray_hiding):
            return
        self.tray.show()
        self.tray_hiding = True
        self.tray_animation.stop()
        if self.isMinimized():
            self.hide()
            self.tray_hiding = False
            return
        self.tray_animation.setStartValue(self.windowOpacity())
        self.tray_animation.setEndValue(0.0)
        self.tray_animation.start()

    def finish_tray_animation(self):
        if self.tray_hiding:
            if self.game_ready and self.game_session.process is not None:
                self.hide()
            self.setWindowOpacity(1.0)
            self.tray_hiding = False

    def restore_from_tray(self):
        self.tray_animation.stop()
        self.tray_hiding = False
        was_hidden = self.isHidden() or self.isMinimized()
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()
        if was_hidden:
            self.setWindowOpacity(0.2)
            self.tray_animation.setStartValue(0.2)
            self.tray_animation.setEndValue(1.0)
            self.tray_animation.start()
        else:
            self.setWindowOpacity(1.0)

    def tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            if self.isHidden() or self.isMinimized() or self.tray_hiding:
                self.restore_from_tray()
            elif self.game_ready:
                self.hide_to_tray()

    def open_community_account(self):
        from .firebase_accounts import FirebaseAccounts
        from .firebase_ui import FirebaseDialog
        if self.community_accounts is None:
            self.community_accounts = FirebaseAccounts(self.root, self.config['firebase'])
        FirebaseDialog(self.community_accounts, self).exec()

    def open_wardrobe(self):
        if self.wardrobe_page is None:
            from .wardrobe_ui import WardrobePage
            self.wardrobe_page = WardrobePage(self.root, self)
            self.pages.addWidget(self.wardrobe_page)
        self.pages.setCurrentWidget(self.wardrobe_page)

    def refresh_navigation(self, index):
        self.home_button.setChecked(index == 0)
        self.wardrobe_button.setChecked(index != 0)
        self.refresh_profile()

    def show_news(self, items):
        while self.news_layout.count():
            widget = self.news_layout.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        self.news_card.setVisible(bool(items))
        if not items:
            return
        heading = QLabel('DERNIÈRE MISE À JOUR')
        heading.setStyleSheet('color: #caa0ff; font-size: 12px; font-weight: 700; letter-spacing: 2px;')
        self.news_layout.addWidget(heading)
        for item in items:
            date = item['published_at'][:10].split('-')
            label = QLabel(item['name'] + '  ·  ' + '/'.join(reversed(date)))
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            label.setStyleSheet('font-weight: 600; font-size: 15px;')
            self.news_layout.addWidget(label)
            notes = QLabel(item['body'] or 'Une nouvelle version de BLIXWOU est disponible.')
            notes.setTextFormat(Qt.PlainText)
            notes.setWordWrap(True)
            notes.setStyleSheet('color: #c1b3d0; font-size: 13px;')
            self.news_layout.addWidget(notes)

    def showEvent(self, event):
        super().showEvent(event)
        dark_titlebar(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'home_layout'):
            margin = max(36, min(96, int(self.width() * .04)))
            self.home_layout.setContentsMargins(margin, 28, margin, 24)

    def changeEvent(self, event):
        super().changeEvent(event)
        if (event.type() == QEvent.WindowStateChange and self.isMinimized()
                and self.game_ready and self.tray.isVisible()):
            QTimer.singleShot(0, self.hide_to_tray)

    def closeEvent(self, event):
        if self.game_ready and self.game_session.process is not None and self.tray.isVisible():
            event.ignore()
            self.hide_to_tray()
            return
        if self.busy:
            if self.job:
                self.job.requestInterruption()  # Cancels pending OAuth only.
            QMessageBox.information(self, "BLIXWOU est actif", "Fermez Minecraft ou attendez la fin de l’installation avant de quitter le launcher. Une connexion Microsoft en attente vient d’être annulée.")
            event.ignore()
            return
        self.closing = True
        if self.update_check and not self.update_check.wait(6000):
            event.ignore()
            QTimer.singleShot(250, self.close)
            return
        self.timer.stop()
        self.maintenance_timer.stop()
        self.game_ready_timer.stop()
        self.tray_animation.stop()
        self.tray.hide()
        if self.news_job and self.news_job.isRunning():
            event.ignore()
            QTimer.singleShot(250, self.close)
            return
        if self.status_job:
            if not self.status_job.wait(10000):
                event.ignore()
                QTimer.singleShot(250, self.close)
                return
        if self.maintenance_job:
            if not self.maintenance_job.wait(10000):
                event.ignore()
                QTimer.singleShot(250, self.close)
                return
        if self.updater:
            self.updater.close()
        event.accept()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", type=Path, help="Rendu de l’interface pour contrôle visuel")
    parser.add_argument("--data-dir", type=Path, help="Dossier isolé pour tests locaux")
    parser.add_argument("--no-network", action="store_true")
    parser.add_argument("--size", default="1280x720", help="Taille de fenêtre, par exemple 1920x1080")
    args = parser.parse_args()
    app = QApplication(sys.argv[:1])
    # Use the installed Windows fonts for the headless visual check as well.
    fonts = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
    for filename in ("segoeui.ttf", "seguisb.ttf", "seguisym.ttf", "bahnschrift.ttf"):
        if (fonts / filename).exists():
            QFontDatabase.addApplicationFont(str(fonts / filename))
    app.setApplicationName("BLIXWOU")
    app.setOrganizationName("gfloxe")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    if os.name != "nt" or struct.calcsize("P") != 8:
        QMessageBox.critical(None, "BLIXWOU", "Windows 64 bits est requis.")
        return
    root = (args.data_dir or data_root()).resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)
    lock = QLockFile(str(root / "launcher.lock"))
    lock.setStaleLockTime(0)
    if not lock.tryLock(0):
        QMessageBox.information(None, "BLIXWOU", "BLIXWOU est déjà ouvert. Revenez à la fenêtre existante.")
        return
    handler = RotatingFileHandler(root / "logs" / "launcher.log", maxBytes=2 * 1024**2, backupCount=3, encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler], format="%(asctime)s %(levelname)s %(message)s")
    try:
        config = load_config()
        try:
            require_game_stopped(root)
        except LauncherError:
            pass  # Open the UI; subsequent pack/launch operations remain blocked.
        else:
            PackManager(root).recover()
        window = MainWindow(root, config, network=not args.no_network and not args.screenshot)
        width, height = map(int, args.size.lower().split("x"))
        window.resize(width, height)
        window.show()
        if args.screenshot:
            def capture():
                args.screenshot.parent.mkdir(parents=True, exist_ok=True)
                window.grab().save(str(args.screenshot))
                app.quit()
            QTimer.singleShot(700, capture)
        app.exec()
    except LauncherError as error:
        QMessageBox.critical(None, "BLIXWOU", str(error))
    finally:
        lock.unlock()


if __name__ == "__main__":
    main()
