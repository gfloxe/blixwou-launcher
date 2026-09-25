import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from blixwou.app import MainWindow, SettingsDialog, ProfileDialog, STYLE
from blixwou.config import load_config, load_settings


def test_ram_warning_preserves_saved_value(tmp_path, monkeypatch):
    from blixwou.config import atomic_json
    monkeypatch.setattr("blixwou.app.physical_ram_mb", lambda: 16384)
    atomic_json(tmp_path / "settings.json", {"ramMb": 12288})
    app = QApplication.instance() or QApplication([])
    dialog = SettingsDialog(tmp_path, None)
    assert dialog.ram.value() == 12288
    assert not dialog.ram_warning.isHidden()
    dialog.ram.setValue(8192)
    assert dialog.ram_warning.isHidden()
    assert load_settings(tmp_path)["ramMb"] == 12288
    dialog.close()


def test_orphan_warning_survives_launch_progress(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path, load_config(), network=False)
    window.report("Mods hors pack : mods/old.jar", 0, 0)
    window.report("Minecraft est lancé", 0, 0)
    assert not window.orphan_warning.isHidden()
    assert "old.jar" in window.orphan_warning.text()
    window.report("Mods hors pack : aucun", 0, 0)
    assert window.orphan_warning.isHidden()
    window.close()


def test_launcher_waits_for_ready_window_and_restores_after_game_exit(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QSystemTrayIcon

    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path, load_config(), network=False)
    monkeypatch.setattr(QSystemTrayIcon, 'isSystemTrayAvailable', staticmethod(lambda: True))

    class Process:
        def poll(self):
            return None

    window.game_session.process = Process()
    hidden = []
    monkeypatch.setattr(window, 'hide_to_tray', lambda: hidden.append(True))
    monkeypatch.setattr('blixwou.app.game_window_ready', lambda process: False)
    window.report('Minecraft est lancé', 0, 0)
    window.check_game_ready()
    assert not window.game_ready
    assert not hidden

    monkeypatch.setattr('blixwou.app.game_window_ready', lambda process: True)
    window.check_game_ready()
    assert not window.game_ready
    window.check_game_ready()
    assert window.game_ready
    assert hidden == [True]
    assert not window.game_ready_timer.isActive()

    class Tray:
        def isVisible(self):
            return True
        def hide(self):
            pass

    class Job:
        def deleteLater(self):
            pass

    restored = []
    window.tray = Tray()
    monkeypatch.setattr(window, 'restore_from_tray', lambda: restored.append(True))
    window.job = Job()
    window.game_session.process = None
    window.job_finished()
    assert restored == [True]
    assert not window.game_ready
    assert window.play.text().startswith('Jouer')
    window.close()


def test_tray_animation_hides_and_click_restores_window(tmp_path, monkeypatch):
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QSystemTrayIcon

    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path, load_config(), network=False)

    class Tray:
        visible = False
        def show(self):
            self.visible = True
        def hide(self):
            self.visible = False
        def isVisible(self):
            return self.visible

    window.tray = Tray()
    window.game_session.process = object()
    window.game_ready = True
    window.show()
    app.processEvents()
    window.tray_animation.setDuration(1)
    monkeypatch.setattr(QSystemTrayIcon, 'isSystemTrayAvailable', staticmethod(lambda: True))

    window.hide_to_tray()
    QTest.qWait(50)
    assert window.isHidden()
    assert window.tray.isVisible()

    window.tray_activated(QSystemTrayIcon.Trigger)
    QTest.qWait(50)
    assert window.isVisible()
    window.game_session.process = None
    window.close()


def test_background_cache_survives_repaint_and_refreshes_on_resize():
    from blixwou.app import Landscape
    from PySide6.QtGui import QPixmap
    app = QApplication.instance() or QApplication([])
    view = Landscape()
    view.resize(1100, 700)
    view.render(QPixmap(view.size()))
    original = view.scaled_picture.cacheKey()
    view.render(QPixmap(view.size()))
    assert view.scaled_picture.cacheKey() == original
    view.resize(900, 600)
    view.render(QPixmap(view.size()))
    assert view.scaled_picture.cacheKey() != original
    view.close()


def test_profile_settings_and_empty_socials(tmp_path):
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(STYLE)
    window = MainWindow(tmp_path, load_config(), network=False)
    window.show()
    app.processEvents()
    assert all(button.isHidden() for button in window.social_buttons.values())
    dialog = ProfileDialog(window.accounts, window)
    dialog.name.setText("BlixPlayer")
    dialog.offline()
    window.refresh_profile()
    assert window.profile.text().strip() == "BlixPlayer"
    assert "hors ligne" not in window.profile.text().lower()
    settings = SettingsDialog(tmp_path, window)
    settings.ram.setValue(6144)
    settings.save()
    assert load_settings(tmp_path)["ramMb"] == 6144
    window.set_status({"state": "unknown", "text": "Indisponible"})
    assert "Indisponible" in window.status_label.text()
    window.accounts.logout()
    assert window.accounts.selected() is None
    window.close()
    app.processEvents()
