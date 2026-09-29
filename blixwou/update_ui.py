"""Dedicated BLIXWOU launcher-update screen."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget

from .config import resource


class UpdateScreen(QWidget):
    def __init__(self, current, parent=None):
        super().__init__(parent)
        self.setObjectName('updateScreen')
        self.setStyleSheet(self.STYLE)
        self.background = QPixmap(str(resource('assets/landscape.png')))
        self.scaled_background = QPixmap()
        self.background_size = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(42, 30, 42, 30)
        outer.addStretch(1)

        card = QFrame()
        card.setObjectName('updateCard')
        card.setFixedWidth(680)
        content = QVBoxLayout(card)
        content.setContentsMargins(42, 36, 42, 36)
        content.setSpacing(16)

        eyebrow = QLabel('BLIXWOU  /  MISE À JOUR')
        eyebrow.setObjectName('updateEyebrow')
        content.addWidget(eyebrow)
        title = QLabel('Mise à jour en cours')
        title.setObjectName('updateTitle')
        title.setWordWrap(True)
        content.addWidget(title)
        self.subtitle = QLabel('Le launcher va se mettre à jour automatiquement.')
        self.subtitle.setObjectName('updateSubtitle')
        self.subtitle.setWordWrap(True)
        content.addWidget(self.subtitle)

        self.version = QLabel(f'BLIXWOU {current}   →   NOUVELLE VERSION')
        self.version.setObjectName('updateVersion')
        content.addWidget(self.version)
        content.addSpacing(8)

        self.stages = []
        for label in ('Recherche de version', 'Téléchargement sécurisé', 'Vérification et installation'):
            stage = QLabel('○  ' + label)
            stage.setObjectName('updateStage')
            content.addWidget(stage)
            self.stages.append(stage)

        content.addSpacing(8)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName('updateBar')
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 1000)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(11)
        content.addWidget(self.progress_bar)
        meter = QHBoxLayout()
        self.detail = QLabel('Vérification des mises à jour…')
        self.detail.setObjectName('updateDetail')
        meter.addWidget(self.detail)
        meter.addStretch()
        self.percent = QLabel('')
        self.percent.setObjectName('updatePercent')
        meter.addWidget(self.percent)
        content.addLayout(meter)

        self.error = QLabel()
        self.error.setObjectName('updateError')
        self.error.setWordWrap(True)
        self.error.hide()
        content.addWidget(self.error)
        actions = QHBoxLayout()
        self.retry_button = QPushButton('Réessayer')
        self.retry_button.setObjectName('updatePrimary')
        self.continue_button = QPushButton('Continuer sans mettre à jour')
        self.continue_button.setObjectName('updateSecondary')
        actions.addWidget(self.retry_button)
        actions.addWidget(self.continue_button)
        content.addLayout(actions)
        self.retry_button.hide()
        self.continue_button.hide()

        outer.addWidget(card, 0, Qt.AlignHCenter)
        outer.addStretch(1)
        self.set_stage(0)

    def paintEvent(self, event):
        painter = QPainter(self)
        if not self.background.isNull():
            if self.background_size != self.size():
                self.scaled_background = self.background.scaled(
                    self.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                self.background_size = self.size()
            picture = self.scaled_background
            painter.drawPixmap((self.width() - picture.width()) // 2,
                               (self.height() - picture.height()) // 2, picture)
        shade = QLinearGradient(0, 0, self.width(), self.height())
        shade.setColorAt(0, QColor(12, 7, 26, 220))
        shade.setColorAt(.5, QColor(19, 9, 38, 205))
        shade.setColorAt(1, QColor(10, 8, 24, 232))
        painter.fillRect(self.rect(), shade)

    def set_version(self, current, latest):
        self.version.setText(f'BLIXWOU {current}   →   BLIXWOU {latest}')

    def set_stage(self, stage):
        for index, label in enumerate(self.stages):
            mark = '✓' if index < stage else '●' if index == stage else '○'
            label.setText(mark + '  ' + ('Recherche de version', 'Téléchargement sécurisé',
                                        'Vérification et installation')[index])
            label.setProperty('state', 'done' if index < stage else 'active' if index == stage else 'pending')
            label.style().unpolish(label)
            label.style().polish(label)

    def set_progress(self, step, current, total):
        self.detail.setText(step)
        if step.startswith('Téléchargement'):
            self.set_stage(1)
        elif step.startswith(('Vérification', 'Installation')):
            self.set_stage(2)
        if total:
            value = min(1000, int(current * 1000 / total))
            self.progress_bar.setRange(0, 1000)
            self.progress_bar.setValue(value)
            self.percent.setText(f'{value // 10} %  ·  {current / 1048576:.1f} / {total / 1048576:.1f} Mo')
        else:
            self.progress_bar.setRange(0, 0)
            self.percent.setText('EN COURS')

    def show_error(self, message):
        self.error.setText(message)
        self.error.show()
        self.subtitle.setText('La mise à jour a été interrompue. Vos données sont conservées.')
        self.retry_button.show()
        self.continue_button.show()
        self.progress_bar.setRange(0, 1000)

    STYLE = """
    QWidget#updateScreen { background: #100c1c; }
    QFrame#updateCard { background: #171121; border: 1px solid #6c488e; border-radius: 22px; }
    QLabel#updateEyebrow { color: #c89eff; font-size: 12px; font-weight: 700; letter-spacing: 3px; }
    QLabel#updateTitle { color: #fffaff; font-size: 30px; font-weight: 750; }
    QLabel#updateSubtitle { color: #c7bad5; font-size: 15px; }
    QLabel#updateVersion { color: #f3e6ff; background: #342149; border: 1px solid #76539a;
        border-radius: 10px; padding: 10px 14px; font-size: 14px; font-weight: 700; }
    QLabel#updateStage { color: #85758e; font-size: 15px; padding: 5px 0; }
    QLabel#updateStage[state="active"] { color: #ead6ff; font-weight: 700; }
    QLabel#updateStage[state="done"] { color: #92ddbe; }
    QProgressBar#updateBar { background: #332840; border: 0; border-radius: 5px; }
    QProgressBar#updateBar::chunk { background: #a957f2; border-radius: 5px; }
    QLabel#updateDetail { color: #bbadc9; font-size: 13px; }
    QLabel#updatePercent { color: #e9d9fa; font-weight: 700; }
    QLabel#updateError { color: #ffb7c5; background: #3a1c2b; padding: 10px; border-radius: 8px; }
    QPushButton#updatePrimary { background: #8f49dc; color: white; font-weight: 700; }
    QPushButton#updatePrimary:hover { background: #a760f1; }
    QPushButton#updateSecondary { background: #2a2235; color: #dbcce9; }
    """
