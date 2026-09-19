import json

from blixwou import home_ui


def test_news_offline_cache_and_corrupt_cache(tmp_path, monkeypatch):
    saved = [{'name': 'BLIXWOU 0.1.2', 'published_at': '2026-09-13T12:00:00Z', 'body': 'Notes'}]
    (tmp_path / 'news.json').write_text(json.dumps(saved))
    def offline(*args, **kwargs):
        raise OSError('offline')
    monkeypatch.setattr(home_ui, 'request', offline)
    assert home_ui.fetch_news(tmp_path) == saved
    (tmp_path / 'news.json').write_text('{invalid')
    assert home_ui.fetch_news(tmp_path) == []


def test_news_fetch_limits_and_caches(tmp_path, monkeypatch):
    items = [dict(name=f'Version {i}', published_at=f'2026-09-{i:02}T12:00:00Z', body='Notes ' * 100) for i in range(1, 6)]
    items.append(dict(name='Draft', draft=True, published_at='2026-09-30T00:00:00Z'))
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size): yield json.dumps(items).encode()
    def request(*args, **kwargs):
        assert kwargs['timeout'] == 5
        return Response()
    monkeypatch.setattr(home_ui, 'request', request)
    news = home_ui.fetch_news(tmp_path)
    assert [item['name'] for item in news] == ['Version 5']
    assert all(len(item['body']) <= 140 for item in news)
    assert home_ui.cached_news(tmp_path) == news


def test_home_status_and_navigation(tmp_path):
    from PySide6.QtWidgets import QApplication
    from blixwou.app import MainWindow
    from blixwou.config import load_config
    app = QApplication.instance() or QApplication([])
    window = MainWindow(tmp_path, load_config(), network=False)
    assert window.news_card.isHidden()
    assert not hasattr(window, 'nav_settings')
    assert not window.profile.icon().isNull()
    window.set_status(dict(state='online', text='En ligne', online=3, max=20, latency=42))
    assert window.status_label.text() == '●  En ligne · 3/20 joueurs · 42 ms'
    window.set_status(dict(state='online', text='En ligne', online=3))
    assert window.status_label.text() == '●  En ligne'
    assert window.progress_panel.parentWidget().objectName() == 'dock'
    assert window.news_layout.count() == 0
    window.show_operation('install', 'Installation du pack', 'Analyse', 1, 4)
    assert not window.operation_card.isHidden()
    assert window.operation_badge.text() == 'PACK'
    assert window.operation_percent.text() == '25 %'
    window.show_operation('update', 'Mise à jour du launcher', 'Téléchargement')
    assert window.operation_badge.text() == 'UPDATE'
    assert window.operation_card.property('mode') == 'update'
    window.close()
