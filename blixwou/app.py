import argparse
import ctypes
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import struct
import sys
import time

from PySide6.QtCore import Qt, QLockFile, QThread, Signal, QTimer, QUrl, QRectF
from PySide6.QtGui import QColor, QDesktopServices, QFont, QFontDatabase, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QSpinBox, QVBoxLayout, QWidget, QStackedWidget)

from .auth import Accounts
from .config import LauncherError, atomic_json, data_root, load_config, load_settings, resource
from .minecraft import prepare_minecraft, build_command, launch_game, GameSession
from .network import https_url
from .pack import PackManager
from .status import server_status
from .updater import LauncherUpdater
from .process_guard import require_game_stopped, InstallerMutex

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
        font = QFont("Bahnschrift", 58, QFont.Black)
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
        self.setMinimumWidth(490)
        self.root = root
        settings = load_settings(root)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 26, 28, 26)
        form = QFormLayout()
        self.ram = QSpinBox()
        self.ram.setRange(2048, 32768)
        self.ram.setSingleStep(512)
        self.ram.setSuffix(" Mo")
        self.ram.setValue(settings["ramMb"])
        form.addRow("Mémoire RAM", self.ram)
        self.ram_warning = QLabel()
        self.ram_warning.setObjectName("muted")
        self.ram_warning.setWordWrap(True)
        form.addRow("", self.ram_warning)
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
        resolution = QHBoxLayout()
        self.width_box, self.height_box = QSpinBox(), QSpinBox()
        self.width_box.setRange(854, 7680)
        self.height_box.setRange(480, 4320)
        self.width_box.setValue(settings["width"])
        self.height_box.setValue(settings["height"])
        resolution.addWidget(self.width_box)
        resolution.addWidget(QLabel("×"))
        resolution.addWidget(self.height_box)
        form.addRow("Résolution", resolution)
        self.java = QLineEdit(settings["javaPath"])
        self.java.setPlaceholderText("Automatique · Java 21 x64")
        java_row = QHBoxLayout()
        java_row.addWidget(self.java)
        browse = QPushButton("…")
        browse.setFixedWidth(42)
        browse.clicked.connect(self.browse_java)
        java_row.addWidget(browse)
        form.addRow("Java", java_row)
        layout.addLayout(form)
        note = QLabel("Laissez le chemin vide pour installer Java automatiquement.")
        note.setObjectName("muted")
        layout.addWidget(note)
        folders = QHBoxLayout()
        for name, path in [("Dossier du jeu", root / "game"), ("Journaux", root / "logs")]:
            button = QPushButton(name)
            button.clicked.connect(lambda checked=False, p=path: open_folder(p))
            folders.addWidget(button)
        layout.addLayout(folders)
        mods_button = QPushButton("Ouvrir le dossier des mods")
        mods_button.clicked.connect(lambda: open_folder(root / "game" / "mods"))
        layout.addWidget(mods_button)
        shaders_button = QPushButton("Ouvrir le dossier des shaders")
        shaders_button.clicked.connect(lambda: open_folder(root / "game" / "shaderpacks"))
        layout.addWidget(shaders_button)
        uninstall_button = QPushButton("Désinstaller BLIXWOU")
        uninstall_button.setToolTip("Ouvrir le désinstalleur Windows. Les données du jeu sont conservées.")
        uninstall_button.clicked.connect(self.uninstall)
        layout.addWidget(uninstall_button)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Enregistrer")
        buttons.button(QDialogButtonBox.Cancel).setText("Annuler")
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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

    def __init__(self, root, config, network=True):
        super().__init__()
        self.root, self.config, self.network = root, config, network
        self.accounts = Accounts(root, config["microsoft"])
        self.manifest = None
        self.busy = False
        self.game_session = GameSession()
        self.job = None
        self.status_job = None
        self.updater = None
        self.setWindowTitle("BLIXWOU")
        self.setWindowIcon(QIcon(str(resource("assets/blixwou.ico"))))
        self.resize(1120, 700)
        self.setMinimumSize(960, 620)
        scene = Landscape()
        shell = QWidget()
        shell.setObjectName('navigationShell')
        shell.setStyleSheet('QWidget#navigationShell { background-color: #14111e; }')
        shell_layout = QVBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        nav = QHBoxLayout()
        self.home_button = QPushButton('Accueil')
        self.wardrobe_button = QPushButton('Garde-robe')
        self.nav_settings = QPushButton('Paramètres')
        for button in (self.home_button, self.wardrobe_button, self.nav_settings):
            nav.addWidget(button)
        nav.addStretch()
        shell_layout.addLayout(nav)
        self.pages = QStackedWidget()
        self.pages.addWidget(scene)
        shell_layout.addWidget(self.pages)
        self.wardrobe_page = None
        self.home_button.clicked.connect(lambda: self.pages.setCurrentIndex(0))
        self.wardrobe_button.clicked.connect(self.open_wardrobe)
        self.nav_settings.clicked.connect(lambda: SettingsDialog(root, self).exec())
        self.setCentralWidget(shell)
        layout = QVBoxLayout(scene)
        layout.setContentsMargins(44, 32, 44, 28)
        top = QHBoxLayout()
        self.profile = QPushButton()
        self.profile.setObjectName("profile")
        self.profile.setMinimumWidth(230)
        self.profile.setAccessibleName("Choisir le profil du joueur")
        self.profile.clicked.connect(self.choose_profile)
        top.addWidget(self.profile)
        top.addStretch()
        self.settings_button = QPushButton("⚙")
        self.settings_button.setObjectName("settings")
        self.settings_button.setFixedSize(46, 46)
        self.settings_button.setToolTip("Paramètres")
        self.settings_button.setAccessibleName("Paramètres")
        self.settings_button.clicked.connect(lambda: SettingsDialog(root, self).exec())
        top.addWidget(self.settings_button)
        layout.addLayout(top)
        layout.addStretch(2)
        layout.addWidget(Wordmark())
        edition = QLabel("MINECRAFT JAVA  /  1.21.1")
        edition.setStyleSheet("color: #e2cfee; font-size: 12px; letter-spacing: 3px;")
        layout.addWidget(edition)
        layout.addStretch(3)

        self.progress_panel = QWidget()
        progress_layout = QVBoxLayout(self.progress_panel)
        progress_layout.setContentsMargins(2, 0, 2, 16)
        self.step = QLabel()
        self.step.setWordWrap(True)
        progress_layout.addWidget(self.step)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(5)
        progress_layout.addWidget(self.bar)
        self.progress_panel.hide()
        layout.addWidget(self.progress_panel)
        self.orphan_warning = QLabel()
        self.orphan_warning.setObjectName("muted")
        self.orphan_warning.setWordWrap(True)
        self.orphan_warning.hide()
        layout.addWidget(self.orphan_warning)

        dock = QFrame()
        dock.setObjectName("dock")
        dock_layout = QHBoxLayout(dock)
        dock_layout.setContentsMargins(26, 20, 22, 20)
        server_col = QVBoxLayout()
        caption = QLabel("SERVEUR BLIXWOU")
        caption.setObjectName("muted")
        caption.setStyleSheet("letter-spacing: 2px;")
        server_col.addWidget(caption)
        self.status_label = QLabel("●  Indisponible")
        self.status_label.setStyleSheet("font-size: 19px; color: #c3b5d7;")
        self.status_label.setToolTip("Aucune réponse de statut reçue pour le moment.")
        server_col.addWidget(self.status_label)
        dock_layout.addLayout(server_col)
        dock_layout.addStretch()
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
        self.shutdown_requested.connect(self.close)
        self.timer = QTimer(self)
        self.timer.setInterval(5000)
        self.timer.timeout.connect(self.check_status)
        if network:
            self.timer.start()
            QTimer.singleShot(0, self.startup)

    def startup(self):
        self.check_status()
        try:
            self.updater = LauncherUpdater(self.config["launcherUpdate"], self.config["appVersion"], lambda: not self.busy, self.shutdown_requested.emit)
        except LauncherError as error:
            self.show_error(str(error))
        if self.config.get("manifestUrl"):
            self.start_job(lambda progress, cancelled: self.sync_pack(progress), self.pack_ready)
        else:
            self.step.setText("Le pack BLIXWOU n’est pas encore disponible. La connexion Microsoft reste accessible depuis le profil.")
            self.bar.hide()
            self.progress_panel.show()

    def sync_pack(self, progress):
        require_game_stopped(self.root)
        return PackManager(self.root, progress).fetch_and_sync(self.config["manifestUrl"])

    def pack_ready(self, manifest):
        self.manifest = manifest
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
            mode = "Microsoft" if profile["mode"] == "microsoft" else "Profil hors ligne"
            self.profile.setText(f"▣   {profile['name']}\n     {mode}")
        else:
            self.profile.setText("▣   Choisir un profil\n     Microsoft ou hors ligne")

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

    def set_status(self, status):
        color = {"online": "#89e1b1", "offline": "#e2a4b9", "unknown": "#c3b5d7"}[status["state"]]
        self.status_label.setText("●  " + status["text"])
        self.status_label.setStyleSheet(f"font-size: 19px; color: {color};")
        self.status_label.setToolTip("Dernière vérification : " + time.strftime("%H:%M:%S") + "\nUn délai réseau ne permet pas de conclure que le serveur est hors ligne.")

    def start_job(self, task, success):
        if self.wardrobe_page is not None:
            self.wardrobe_page.setEnabled(False)
        if self.busy:
            return
        self.busy = True
        for widget in (self.play, self.profile, self.settings_button, self.wardrobe_button, self.nav_settings):
            widget.setEnabled(False)
        self.bar.show()
        self.progress_panel.show()
        self.report("Préparation", 0, 0)
        job = Worker(task, self)
        self.job = job
        job.progress.connect(self.report)
        job.success.connect(success)
        job.failure.connect(self.show_error)
        job.finished.connect(self.job_finished)
        job.start()

    def report(self, step, current, total):
        if step.startswith("Mods hors pack :"):
            self.orphan_warning.setText(step + " · Vérifiez le dossier des mods dans les paramètres.")
            self.orphan_warning.setVisible(step != "Mods hors pack : aucun")
            return
        if step == "Minecraft est lancé":
            self.play.setText("Arrêter  ■")
            self.play.setEnabled(True)
            self.bar.hide()
        text = step
        if total:
            if total > 100000:
                text += f" · {current / 1024**2:.1f} / {total / 1024**2:.1f} Mo"
            else:
                text += f" · {current} / {total}"
            self.bar.setRange(0, 1000)
            self.bar.setValue(min(1000, int(current * 1000 / total)))
        else:
            self.bar.setRange(0, 0)  # Indeterminate, never a fabricated percentage.
        self.step.setText(text)

    def show_error(self, message):
        self.step.setText(message)
        self.bar.hide()
        self.progress_panel.show()
        QMessageBox.warning(self, "BLIXWOU", message)

    def job_finished(self):
        if self.wardrobe_page is not None:
            self.wardrobe_page.setEnabled(True)
        self.busy = False
        self.play.setText("Jouer  ›")
        for widget in (self.play, self.profile, self.settings_button, self.wardrobe_button, self.nav_settings):
            widget.setEnabled(True)
        self.bar.hide()
        self.job.deleteLater()
        self.job = None

    def play_clicked(self):
        if self.game_session.process is not None:
            self.game_session.stop()
            self.play.setText("Arrêt en cours…")
            self.play.setEnabled(False)
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

    def open_wardrobe(self):
        if self.wardrobe_page is None:
            from .wardrobe_ui import WardrobePage
            self.wardrobe_page = WardrobePage(self.root, self)
            self.pages.addWidget(self.wardrobe_page)
        self.pages.setCurrentWidget(self.wardrobe_page)

    def closeEvent(self, event):
        if self.busy:
            if self.job:
                self.job.requestInterruption()  # Cancels pending OAuth only.
            QMessageBox.information(self, "BLIXWOU est actif", "Fermez Minecraft ou attendez la fin de l’installation avant de quitter le launcher. Une connexion Microsoft en attente vient d’être annulée.")
            event.ignore()
            return
        self.timer.stop()
        if self.status_job:
            if not self.status_job.wait(10000):
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
    installer_mutex = None
    try:
        installer_mutex = InstallerMutex()
        config = load_config()
        try:
            require_game_stopped(root)
        except LauncherError:
            pass  # Open the UI; subsequent pack/launch operations remain blocked.
        else:
            PackManager(root).recover()
        window = MainWindow(root, config, network=not args.no_network and not args.screenshot)
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
        if installer_mutex:
            installer_mutex.close()
        lock.unlock()


if __name__ == "__main__":
    main()
