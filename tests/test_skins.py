import json
import base64
import pytest
from PySide6.QtGui import QImage, QColor
from blixwou.skins import Wardrobe, normalize_png, png_bytes, import_premium
from blixwou.config import LauncherError


def skin(width=64, height=64):
    image = QImage(width,height,QImage.Format_RGBA8888)
    image.fill(QColor('#7351b8'))
    return png_bytes(image)


@pytest.mark.parametrize('size',[(64,64),(64,32)])
def test_valid_png(size):
    data = normalize_png(skin(*size))
    image=QImage.fromData(data)
    assert (image.width(),image.height()) == (64,64)
    assert len(data)<=32768


@pytest.mark.parametrize('data',[b'not png',b'x'*32769,skin(128,128),skin(32,64),skin()[:33]], ids=['not-png','too-large','128-square','wrong-width','truncated'])
def test_bad_png(data):
    with pytest.raises(LauncherError):normalize_png(data)


def test_legacy_left_limbs_are_mirrored():
    image=QImage.fromData(skin(64,32))
    image.setPixelColor(4,20,QColor('red'))
    image.setPixelColor(44,20,QColor('green'))
    result=QImage.fromData(normalize_png(png_bytes(image)))
    assert result.pixelColor(23,52) == QColor('red')
    assert result.pixelColor(39,52) == QColor('green')
    assert result.pixelColor(40,8).alpha() == 0


def test_wardrobe_persistence_selection_and_export(tmp_path):
    store=Wardrobe(tmp_path)
    first=store.add(skin(),'Premier')
    second=store.add(skin(),'Deuxième','slim')
    store.edit(second['id'],active=True,name='Nouveau')
    store=Wardrobe(tmp_path)
    assert [e['active'] for e in store.entries()] == [False,True]
    assert store.entries()[1]['name']=='Nouveau'
    game=tmp_path/'game'
    store.export_active(game)
    folder=game/'config/blixwou-skin'
    assert (folder/'active.png').read_bytes()==store.path(second).read_bytes()
    assert json.loads((folder/'active.json').read_text())=={'model':'slim'}
    store.delete(second['id'])
    store.export_active(game)
    assert not (folder/'active.png').exists()
    assert not (folder/'active.json').exists()
    assert store.path(first).exists()


def test_invalid_import_does_not_change_index(tmp_path):
    store=Wardrobe(tmp_path)
    store.add(skin(),'OK')
    before=store.index.read_bytes()
    with pytest.raises(LauncherError):store.add(b'bad','Bad')
    assert store.index.read_bytes()==before


def test_premium_foreign_texture_rejected(monkeypatch):
    data={'textures':{'SKIN':{'url':'https://evil.invalid/skin.png'}}}
    responses=iter([{'id':'a'*32},{'properties':[{'name':'textures','value':base64.b64encode(json.dumps(data).encode()).decode()}]}])
    monkeypatch.setattr('blixwou.skins.get_json',lambda url:next(responses))
    with pytest.raises(LauncherError):import_premium('Steve')


def test_premium_import_upgrades_mojang_texture_to_https(monkeypatch):
    data={'textures':{'SKIN':{'url':'http://textures.minecraft.net/texture/abc','metadata':{'model':'slim'}}}}
    responses=iter([{'id':'a'*32},{'properties':[{'name':'textures','value':base64.b64encode(json.dumps(data).encode()).decode()}]}])
    monkeypatch.setattr('blixwou.skins.get_json',lambda url:next(responses))
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def iter_content(self,size):yield skin()
    def fetch(method,url,**kwargs):
        assert url=='https://textures.minecraft.net/texture/abc'
        return Response()
    monkeypatch.setattr('blixwou.skins.request',fetch)
    png,model=import_premium('Steve')
    assert model=='slim' and QImage.fromData(png).width()==64
