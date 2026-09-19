"""Lightweight textured cuboid preview rendered in a QOpenGLWidget."""
import math
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QPointF, QRectF, QSize
from PySide6.QtGui import QImage, QPixmap, QIcon, QPainter, QPolygonF, QTransform, QColor
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFileDialog, QInputDialog, QMessageBox, QComboBox,
    QFrame, QSizePolicy)
from .config import LauncherError
from .skins import Wardrobe, LIMIT, import_premium


class SkinPreview(QOpenGLWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(280, 300)
        self.image = QImage()
        self.model = 'classic'
        self.angle = -25.0
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.rotate)

    def showEvent(self, event):
        super().showEvent(event)
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def rotate(self):
        self.angle = (self.angle + .6) % 360
        self.update()

    def set_skin(self, path=None, model='classic'):
        self.image = QImage(str(path)) if path else QImage()
        self.model = model
        self.update()

    def paintGL(self):
        # Rasterize small textured faces together to avoid driver-dependent
        # seams from Qt's OpenGL texture atlas, then present one GL surface.
        canvas = QImage(self.size(), QImage.Format_ARGB32_Premultiplied)
        painter = QPainter(canvas)
        self.paint_scene(painter)
        painter.end()
        display = QPainter(self)
        display.drawImage(0, 0, canvas)
        display.end()

    def paint_scene(self, painter):
        painter.fillRect(self.rect(), QColor('#120d1c'))
        if self.image.isNull():
            painter.setPen(QColor('#c9b4e3'))
            painter.drawText(self.rect(), Qt.AlignCenter, 'Ajoute un skin pour le découvrir ici')
            return
        painter.setRenderHint(QPainter.Antialiasing)
        faces = []
        yaw = math.radians(self.angle)
        pitch = .12
        scale = min(self.width()/30, self.height()/40)
        def project(x,y,z):
            rx, rz = x*math.cos(yaw)+z*math.sin(yaw), -x*math.sin(yaw)+z*math.cos(yaw)
            ry, depth = y*math.cos(pitch)-rz*math.sin(pitch), y*math.sin(pitch)+rz*math.cos(pitch)
            return QPointF(self.width()/2+rx*scale,self.height()/2+ry*scale), depth
        def box(x,y,z,w,h,d,u,v,inflate=0):
            vertices=[(x-inflate,y-inflate,z-inflate),(x+w+inflate,y-inflate,z-inflate),
                      (x+w+inflate,y+h+inflate,z-inflate),(x-inflate,y+h+inflate,z-inflate),
                      (x-inflate,y-inflate,z+d+inflate),(x+w+inflate,y-inflate,z+d+inflate),
                      (x+w+inflate,y+h+inflate,z+d+inflate),(x-inflate,y+h+inflate,z+d+inflate)]
            for indices, uv in [((4,5,6,7),(u+d,v+d,w,h)),((1,0,3,2),(u+2*d+w,v+d,w,h)),
                                ((0,4,7,3),(u,v+d,d,h)),((5,1,2,6),(u+d+w,v+d,d,h)),
                                ((0,1,5,4),(u+d,v,w,d)),((7,6,2,3),(u+d+w,v,w,d))]:
                points,depths=zip(*(project(*vertices[i]) for i in indices))
                cross=(points[1].x()-points[0].x())*(points[2].y()-points[0].y())-(points[1].y()-points[0].y())*(points[2].x()-points[0].x())
                if cross > 0:
                    faces.append((sum(depths)/4,QPolygonF(points),self.image.copy(*uv)))
        arm = 3 if self.model == 'slim' else 4
        parts=[(-4,-16,-4,8,8,8,0,0,32,0),(-4,-8,-2,8,12,4,16,16,16,32),
               (-4-arm,-8,-2,arm,12,4,40,16,40,32),(4,-8,-2,arm,12,4,32,48,48,48),
               (-4,4,-2,4,12,4,0,16,0,32),(0,4,-2,4,12,4,16,48,0,48)]
        for x,y,z,w,h,d,u,v,ou,ov in parts:
            box(x,y,z,w,h,d,u,v)
            box(x,y,z,w,h,d,ou,ov,.22)
        for _,polygon,image in sorted(faces,key=lambda f:f[0]):
            source=QPolygonF([QPointF(0,0),QPointF(image.width(),0),QPointF(image.width(),image.height()),QPointF(0,image.height())])
            transform=QTransform()
            if QTransform.quadToQuad(source,polygon,transform):
                painter.save()
                painter.setTransform(transform)
                painter.drawImage(QPointF(0,0),image)
                painter.restore()


class WardrobePage(QWidget):
    def __init__(self, root, owner):
        super().__init__(owner)
        self.root = Path(root)
        self.store = Wardrobe(root)
        self.owner = owner
        self.loading = False
        self.setObjectName('skinPage')
        self.setStyleSheet(self.STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 24, 34, 28)
        layout.setSpacing(18)

        header = QHBoxLayout()
        header_text = QVBoxLayout()
        eyebrow = QLabel('PERSONNALISATION  /  BLIXWOU')
        eyebrow.setObjectName('eyebrow')
        header_text.addWidget(eyebrow)
        title = QLabel('Vos skins')
        title.setObjectName('skinTitle')
        header_text.addWidget(title)
        subtitle = QLabel('Choisissez l’apparence envoyée au serveur au prochain lancement du jeu.')
        subtitle.setObjectName('skinSubtitle')
        header_text.addWidget(subtitle)
        header.addLayout(header_text)
        header.addStretch()
        self.count = QLabel()
        self.count.setObjectName('countPill')
        header.addWidget(self.count, 0, Qt.AlignTop)
        layout.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(18)
        library = QFrame()
        library.setObjectName('skinCard')
        library.setMinimumWidth(310)
        library.setMaximumWidth(390)
        library_layout = QVBoxLayout(library)
        library_layout.setContentsMargins(18, 18, 18, 18)
        library_layout.setSpacing(12)
        library_title = QLabel('MA COLLECTION')
        library_title.setObjectName('cardCaption')
        library_layout.addWidget(library_title)
        self.list=QListWidget()
        self.list.setIconSize(QSize(48,48))
        self.list.currentRowChanged.connect(self.select)
        library_layout.addWidget(self.list, 1)
        import_row = QHBoxLayout()
        import_file = QPushButton('＋  Importer un PNG')
        import_file.setObjectName('secondaryAction')
        import_file.clicked.connect(self.import_file)
        import_row.addWidget(import_file)
        import_name = QPushButton('Depuis un pseudo')
        import_name.setObjectName('secondaryAction')
        import_name.clicked.connect(self.import_name)
        import_row.addWidget(import_name)
        library_layout.addLayout(import_row)
        body.addWidget(library)

        preview_card = QFrame()
        preview_card.setObjectName('skinCard')
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(18, 16, 18, 18)
        preview_layout.setSpacing(10)
        preview_header = QHBoxLayout()
        preview_header.addWidget(QLabel('APERÇU 3D'))
        preview_header.addStretch()
        self.active_badge = QLabel('AUCUN SKIN ACTIF')
        self.active_badge.setObjectName('activePill')
        preview_header.addWidget(self.active_badge)
        preview_layout.addLayout(preview_header)
        self.preview=SkinPreview(self)
        self.preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        preview_layout.addWidget(self.preview, 1)
        body.addWidget(preview_card, 2)
        layout.addLayout(body,1)

        controls = QFrame()
        controls.setObjectName('skinCard')
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(18, 14, 18, 14)
        controls_layout.setSpacing(10)
        self.model=QComboBox()
        self.model.addItem('Classic · bras larges','classic')
        self.model.addItem('Slim · bras fins','slim')
        self.model.currentIndexChanged.connect(self.change_model)
        controls_layout.addWidget(self.model)
        for label, callback in [('Renommer', self.rename), ('Supprimer', self.delete)]:
            button = QPushButton(label)
            button.setObjectName('secondaryAction')
            button.clicked.connect(callback)
            controls_layout.addWidget(button)
        reset=QPushButton('Sans skin personnalisé')
        reset.setObjectName('secondaryAction')
        reset.clicked.connect(self.clear_active)
        controls_layout.addWidget(reset)
        controls_layout.addStretch()
        use = QPushButton('Utiliser ce skin  ›')
        use.setObjectName('primaryAction')
        use.clicked.connect(self.use)
        controls_layout.addWidget(use)
        layout.addWidget(controls)
        self.notice=QLabel('')
        self.notice.setObjectName('skinNotice')
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.reload()

    STYLE = """
    QWidget#skinPage { background: #100c18; }
    QLabel#eyebrow, QLabel#cardCaption { color: #bf8cff; font-size: 11px; font-weight: 700; letter-spacing: 2px; }
    QLabel#skinTitle { font-size: 32px; font-weight: 750; color: #ffffff; }
    QLabel#skinSubtitle, QLabel#skinNotice { color: #b9acc8; font-size: 13px; }
    QLabel#countPill, QLabel#activePill { background: #2a1b3a; border: 1px solid #5d3a7e; border-radius: 12px; color: #d9b9ff; font-size: 11px; font-weight: 700; padding: 6px 12px; }
    QFrame#skinCard { background: #181120; border: 1px solid #342541; border-radius: 16px; }
    QFrame#skinCard:hover { border-color: #51396a; }
    QListWidget { background: #110c18; border: 1px solid #2e213a; border-radius: 12px; padding: 5px; outline: 0; }
    QListWidget::item { border-radius: 9px; color: #d9cfdf; margin: 3px; padding: 9px; }
    QListWidget::item:hover { background: #24172f; }
    QListWidget::item:selected { background: #60358a; color: white; }
    QComboBox { background: #21172b; border: 1px solid #49355c; border-radius: 9px; padding: 10px 14px; min-width: 175px; }
    QPushButton#secondaryAction { background: #21172b; border: 1px solid #49355c; padding: 10px 14px; }
    QPushButton#secondaryAction:hover { background: #322040; border-color: #9d67da; }
    QPushButton#primaryAction { background: #9454ef; border: 1px solid #c69cff; font-size: 15px; font-weight: 700; padding: 12px 24px; }
    QPushButton#primaryAction:hover { background: #ab6bff; }
    """

    def attempt(self, action):
        try:
            action()
            self.reload()
        except (LauncherError,OSError,ValueError) as error:
            QMessageBox.warning(self,'Skin',str(error))

    def reload(self):
        self.loading=True
        previous=self.selected()
        self.entries=self.store.entries()
        self.count.setText(f"{len(self.entries)} SKIN" + ('S' if len(self.entries) != 1 else ''))
        self.list.clear()
        for entry in self.entries:
            image=QImage(str(self.store.path(entry)))
            face=image.copy(8,8,8,8)
            if not face.isNull():
                painter=QPainter(face)
                painter.drawImage(0,0,image.copy(40,8,8,8))
                painter.end()
            label=entry['name'] + ('  · Actif' if entry['active'] else '')
            self.list.addItem(QListWidgetItem(QIcon(QPixmap.fromImage(face).scaled(48,48)),label))
        row=next((i for i,e in enumerate(self.entries) if previous and e['id']==previous['id']),
                 next((i for i,e in enumerate(self.entries) if e['active']),0))
        self.loading=False
        self.list.setCurrentRow(row)
        self.select(row)

    def selected(self):
        row=self.list.currentRow()
        entries=getattr(self,'entries',[])
        return entries[row] if 0<=row<len(entries) else None

    def select(self,row):
        if self.loading:return
        entry=self.selected()
        self.model.blockSignals(True)
        if entry:self.model.setCurrentIndex(1 if entry['model']=='slim' else 0)
        self.model.blockSignals(False)
        self.preview.set_skin(self.store.path(entry) if entry else None,entry['model'] if entry else 'classic')
        self.active_badge.setText('ACTIF' if entry and entry.get('active') else 'APERÇU')

    def import_file(self):
        path,_=QFileDialog.getOpenFileName(self,'Importer un skin','','Skin PNG (*.png)')
        if path:
            def add():
                with Path(path).open('rb') as stream:data=stream.read(LIMIT+1)
                self.store.add(data,Path(path).stem)
            self.attempt(add)

    def import_name(self):
        if self.owner.busy:return
        name,ok=QInputDialog.getText(self,'Skin premium','Pseudo Minecraft premium :')
        if not ok:return
        def done(result):
            self.attempt(lambda:self.store.add(result[0],name,result[1]))
            self.notice.setText('Skin importé. Choisis « Utiliser » pour le porter.')
        self.owner.start_job(lambda progress,cancelled:import_premium(name.strip()),done)

    def rename(self):
        entry=self.selected()
        if entry:
            name,ok=QInputDialog.getText(self,'Renommer','Nom du skin :',text=entry['name'])
            if ok:self.attempt(lambda:self.store.edit(entry['id'],name=name))

    def delete(self):
        entry=self.selected()
        if entry and QMessageBox.question(self,'Supprimer ce skin ?',entry['name'],QMessageBox.Yes|QMessageBox.No,QMessageBox.No)==QMessageBox.Yes:
            was_active = entry.get('active')
            def remove():
                self.store.delete(entry['id'])
                if was_active:
                    self.store.export_active(self.root / 'game')
            self.attempt(remove)
            if was_active:
                self.owner.refresh_profile()

    def use(self):
        entry=self.selected()
        if entry:
            def activate():
                self.store.edit(entry['id'], active=True)
                self.store.export_active(self.root / 'game')
            self.attempt(activate)
            self.owner.refresh_profile()
            self.notice.setText('Skin actif : il sera appliqué dans Minecraft au prochain lancement.')

    def change_model(self,index):
        entry=self.selected()
        if entry:
            def change():
                self.store.edit(entry['id'], model=self.model.currentData())
                if entry.get('active'):
                    self.store.export_active(self.root / 'game')
            self.attempt(change)

    def clear_active(self):
        def clear():
            for entry in self.store.entries():
                if entry['active']:self.store.edit(entry['id'],active=False)
            self.store.export_active(self.root / 'game')
        self.attempt(clear)
        self.owner.refresh_profile()
        self.notice.setText('Le skin personnalisé a été retiré.')
