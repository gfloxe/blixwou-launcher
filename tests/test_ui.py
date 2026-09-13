import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from blixwou.app import MainWindow, SettingsDialog, ProfileDialog, STYLE
from blixwou.config import load_config, load_settings


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
    assert "BlixPlayer" in window.profile.text()
    assert "hors ligne" in window.profile.text()
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
