"""Non-blocking community account dialog; independent from Minecraft profiles."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QFrame, QGraphicsDropShadowEffect, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QVBoxLayout, QWidget,
)


class FirebaseDialog(QDialog):
    def __init__(self, accounts, parent):
        super().__init__(parent)
        self.accounts, self.job = accounts, None
        self.auth_mode = 'login'
        self.setWindowTitle('Compte BLIXWOU')
        self.setObjectName('firebaseDialog')
        self.setMinimumWidth(540)
        self.setMaximumWidth(620)
        self.setStyleSheet(self.STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 26, 30, 28)
        layout.setSpacing(18)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(12)
        brand_badge = QLabel('B')
        brand_badge.setObjectName('brandBadge')
        brand_badge.setAlignment(Qt.AlignCenter)
        brand_badge.setFixedSize(38, 38)
        brand_row.addWidget(brand_badge)
        brand = QLabel('BLIXWOU  /  COMPTE')
        brand.setObjectName('brandText')
        brand_row.addWidget(brand)
        brand_row.addStretch()
        secure = QLabel('●  SÉCURISÉ')
        secure.setObjectName('securePill')
        brand_row.addWidget(secure)
        layout.addLayout(brand_row)

        self.heading = QLabel('Votre espace BLIXWOU')
        self.heading.setObjectName('accountHeading')
        layout.addWidget(self.heading)
        self.subtitle = QLabel('Connectez-vous pour retrouver votre identité BLIXWOU sur cet appareil.')
        self.subtitle.setObjectName('accountSubtitle')
        self.subtitle.setWordWrap(True)
        layout.addWidget(self.subtitle)

        self.auth_panel = QFrame()
        self.auth_panel.setObjectName('accountCard')
        auth_layout = QVBoxLayout(self.auth_panel)
        auth_layout.setContentsMargins(20, 20, 20, 20)
        auth_layout.setSpacing(12)
        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)
        self.login_tab = QPushButton('Connexion')
        self.register_tab = QPushButton('Créer un compte')
        for button in (self.login_tab, self.register_tab):
            button.setObjectName('modeTab')
            button.setCheckable(True)
            mode_row.addWidget(button)
        self.login_tab.clicked.connect(lambda: self.set_mode('login'))
        self.register_tab.clicked.connect(lambda: self.set_mode('register'))
        auth_layout.addLayout(mode_row)

        self.email = self.field('nom@exemple.fr', 254)
        self.password = self.field('Votre mot de passe', 128)
        self.password.setEchoMode(QLineEdit.Password)
        self.username = self.field('3–16 lettres minuscules, chiffres ou _', 16)
        self.email_group = self.field_group('ADRESSE E-MAIL', self.email)
        self.password_group = self.field_group('MOT DE PASSE', self.password)
        self.username_group = self.field_group('PSEUDO UNIQUE', self.username)
        for group in (self.email_group, self.password_group, self.username_group):
            auth_layout.addWidget(group)

        self.submit_button = QPushButton('Se connecter  →')
        self.submit_button.setObjectName('primaryAction')
        self.submit_button.clicked.connect(self.submit)
        auth_layout.addWidget(self.submit_button)
        self.reset_button = QPushButton('Mot de passe oublié ?')
        self.reset_button.setObjectName('linkAction')
        self.reset_button.clicked.connect(lambda: self.perform('reset'))
        auth_layout.addWidget(self.reset_button, alignment=Qt.AlignCenter)
        layout.addWidget(self.auth_panel)

        self.claim_panel = QFrame()
        self.claim_panel.setObjectName('accountCard')
        claim_layout = QVBoxLayout(self.claim_panel)
        claim_layout.setContentsMargins(20, 20, 20, 20)
        claim_layout.setSpacing(12)
        claim_intro = QLabel('DERNIÈRE ÉTAPE')
        claim_intro.setObjectName('eyebrow')
        claim_layout.addWidget(claim_intro)
        claim_text = QLabel('Choisissez le pseudo public associé à votre compte.')
        claim_text.setObjectName('cardText')
        claim_text.setWordWrap(True)
        claim_layout.addWidget(claim_text)
        self.claim_username = self.field('3–16 lettres minuscules, chiffres ou _', 16)
        claim_layout.addWidget(self.field_group('PSEUDO UNIQUE', self.claim_username))
        self.claim_button = QPushButton('Valider mon pseudo  →')
        self.claim_button.setObjectName('primaryAction')
        self.claim_button.clicked.connect(lambda: self.perform('claim'))
        claim_layout.addWidget(self.claim_button)
        layout.addWidget(self.claim_panel)

        self.profile_panel = QFrame()
        self.profile_panel.setObjectName('profileCard')
        profile_layout = QVBoxLayout(self.profile_panel)
        profile_layout.setContentsMargins(24, 24, 24, 24)
        profile_layout.setSpacing(16)
        identity = QHBoxLayout()
        identity.setSpacing(16)
        self.avatar = QLabel('B')
        self.avatar.setObjectName('accountAvatar')
        self.avatar.setAlignment(Qt.AlignCenter)
        self.avatar.setFixedSize(66, 66)
        identity.addWidget(self.avatar)
        name_col = QVBoxLayout()
        name_col.setSpacing(4)
        self.profile_name = QLabel()
        self.profile_name.setObjectName('profileName')
        name_col.addWidget(self.profile_name)
        state = QLabel('●  COMPTE CONNECTÉ')
        state.setObjectName('connectedState')
        name_col.addWidget(state)
        identity.addLayout(name_col)
        identity.addStretch()
        profile_layout.addLayout(identity)
        divider = QFrame()
        divider.setObjectName('divider')
        divider.setFixedHeight(1)
        profile_layout.addWidget(divider)
        details = QHBoxLayout()
        details.setSpacing(10)
        details.addWidget(self.detail('✓', 'Pseudo protégé'))
        details.addWidget(self.detail('◆', 'Session chiffrée'))
        profile_layout.addLayout(details)
        layout.addWidget(self.profile_panel)

        self.notice = QLabel()
        self.notice.setObjectName('notice')
        self.notice.setWordWrap(True)
        self.notice.hide()
        layout.addWidget(self.notice)
        self.logout_button = QPushButton('Se déconnecter de cet appareil')
        self.logout_button.setObjectName('secondaryAction')
        self.logout_button.clicked.connect(lambda: self.perform('logout'))
        layout.addWidget(self.logout_button)

        self.actions = [self.login_tab, self.register_tab, self.submit_button,
                        self.claim_button, self.reset_button, self.logout_button]
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(7, 3, 14, 180))
        self.profile_panel.setGraphicsEffect(shadow)

        self.set_mode('login')
        self.refresh()
        if accounts.path.exists():
            QTimer.singleShot(0, lambda: self.perform('resume'))

    @staticmethod
    def field(placeholder, limit):
        result = QLineEdit()
        result.setPlaceholderText(placeholder)
        result.setMaxLength(limit)
        result.setMinimumHeight(46)
        return result

    @staticmethod
    def field_group(title, field):
        group = QWidget()
        box = QVBoxLayout(group)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        label = QLabel(title)
        label.setObjectName('fieldLabel')
        box.addWidget(label)
        box.addWidget(field)
        return group

    @staticmethod
    def detail(icon, text):
        label = QLabel(icon + '  ' + text)
        label.setObjectName('detailPill')
        label.setAlignment(Qt.AlignCenter)
        return label

    def set_mode(self, mode):
        self.auth_mode = mode
        self.login_tab.setChecked(mode == 'login')
        self.register_tab.setChecked(mode == 'register')
        self.username_group.setVisible(mode == 'register')
        self.submit_button.setText('Se connecter  →' if mode == 'login' else 'Créer mon compte  →')
        self.reset_button.setVisible(mode == 'login')

    def submit(self):
        self.perform(self.auth_mode)

    def set_notice(self, text, kind='info'):
        self.notice.setText(text)
        self.notice.setProperty('kind', kind)
        self.notice.style().unpolish(self.notice)
        self.notice.style().polish(self.notice)
        self.notice.setVisible(bool(text))

    def refresh(self):
        connected = self.accounts.session is not None
        claimed = connected and bool(self.accounts.username)
        self.auth_panel.setVisible(not connected)
        self.claim_panel.setVisible(connected and not claimed)
        self.profile_panel.setVisible(claimed)
        self.logout_button.setVisible(connected)
        if claimed:
            name = self.accounts.username
            self.heading.setText('Bonjour ' + name)
            self.subtitle.setText('Votre identité BLIXWOU est prête. Bon retour parmi nous.')
            self.profile_name.setText(name)
            self.avatar.setText(name[:1].upper())
        elif connected:
            self.heading.setText('Choisissez votre pseudo')
            self.subtitle.setText('Votre compte est connecté. Réservez maintenant votre identité BLIXWOU.')
        else:
            self.heading.setText('Votre espace BLIXWOU')
            self.subtitle.setText('Connectez-vous pour retrouver votre identité BLIXWOU sur cet appareil.')
        for button in self.actions:
            button.setEnabled(self.job is None)

    def perform(self, action):
        from .app import Worker
        if self.job is not None:
            return
        if action == 'logout':
            self.accounts.logout()
            self.set_notice('Vous êtes déconnecté de cet appareil.', 'success')
            self.refresh()
            return
        email, password = self.email.text().strip(), self.password.text()
        username = self.claim_username.text() if action == 'claim' else self.username.text()
        if action in ('login', 'register', 'reset') and not email:
            self.set_notice('Renseignez votre adresse e-mail.', 'error')
            return
        self.password.clear()

        def task(progress, cancelled):
            if action == 'register':
                return self.accounts.register(email, password, username)
            if action == 'login':
                return self.accounts.login(email, password)
            if action == 'claim':
                return self.accounts.claim_name(username)
            if action == 'reset':
                return self.accounts.reset_password(email)
            return self.accounts.resume()

        self.job = Worker(task, self)
        self.job.success.connect(lambda result: self.set_notice(
            result if action == 'reset' else 'Connexion réussie.' if self.accounts.username
            else 'Compte connecté. Choisissez maintenant votre pseudo.', 'success'))
        self.job.failure.connect(lambda message: self.set_notice(message, 'error'))
        self.job.finished.connect(self.finished_job)
        self.set_notice('Connexion sécurisée en cours…')
        self.refresh()
        self.job.start()

    def finished_job(self):
        self.job.deleteLater()
        self.job = None
        self.refresh()

    def reject(self):
        if self.job is None:
            super().reject()

    def closeEvent(self, event):
        event.ignore() if self.job is not None else event.accept()

    STYLE = """
    QDialog#firebaseDialog { background: #100c18; color: #f7f2ff; }
    QLabel#brandBadge { background: #8f4be8; border: 1px solid #c79bff; border-radius: 10px; color: white; font-size: 20px; font-weight: 800; }
    QLabel#brandText { color: #d8c4ed; font-size: 11px; font-weight: 700; letter-spacing: 3px; }
    QLabel#securePill { background: #17251f; border: 1px solid #2c5b46; border-radius: 12px; color: #81d8ad; font-size: 10px; font-weight: 700; padding: 6px 10px; }
    QLabel#accountHeading { color: #ffffff; font-size: 29px; font-weight: 750; margin-top: 2px; }
    QLabel#accountSubtitle { color: #b7a9c6; font-size: 13px; }
    QFrame#accountCard, QFrame#profileCard { background: #191322; border: 1px solid #3b2c4d; border-radius: 16px; }
    QFrame#profileCard { background: #1c1428; border-color: #67458a; }
    QPushButton#modeTab { background: transparent; border: 0; border-radius: 9px; color: #998ca8; padding: 10px 14px; font-weight: 600; }
    QPushButton#modeTab:checked { background: #352245; color: #f0dfff; }
    QPushButton#modeTab:hover { color: #ffffff; background: #2a1d38; }
    QLabel#fieldLabel, QLabel#eyebrow { color: #a98cce; font-size: 10px; font-weight: 750; letter-spacing: 2px; }
    QLabel#cardText { color: #c9bdd5; font-size: 13px; }
    QLineEdit { background: #100c18; border: 1px solid #453455; border-radius: 10px; color: #ffffff; padding: 11px 13px; font-size: 13px; selection-background-color: #8f4be8; }
    QLineEdit:hover { border-color: #6c4b89; }
    QLineEdit:focus { border: 1px solid #a767f5; background: #15101e; }
    QPushButton#primaryAction { background: #914cf0; border: 1px solid #c28cff; border-radius: 11px; color: white; min-height: 24px; padding: 12px 18px; font-size: 14px; font-weight: 700; }
    QPushButton#primaryAction:hover { background: #a65eff; }
    QPushButton#primaryAction:pressed { background: #7b3bcf; }
    QPushButton#primaryAction:disabled { background: #3a2950; border-color: #51396c; color: #a89ab8; }
    QPushButton#linkAction { background: transparent; border: 0; color: #b78ae9; padding: 6px 10px; }
    QPushButton#linkAction:hover { color: #e0c3ff; text-decoration: underline; }
    QPushButton#secondaryAction { background: transparent; border: 1px solid #493858; border-radius: 10px; color: #c6b8d4; padding: 11px 16px; }
    QPushButton#secondaryAction:hover { background: #251a31; border-color: #7c59a0; color: white; }
    QLabel#accountAvatar { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #a95fff, stop:1 #6130b8); border: 1px solid #d0a7ff; border-radius: 20px; color: white; font-size: 28px; font-weight: 800; }
    QLabel#profileName { color: white; font-size: 22px; font-weight: 750; }
    QLabel#connectedState { color: #73d7a5; font-size: 10px; font-weight: 700; letter-spacing: 1px; }
    QFrame#divider { background: #3a2b49; border: 0; }
    QLabel#detailPill { background: #241a30; border: 1px solid #40304f; border-radius: 10px; color: #cbb9dc; padding: 10px 12px; }
    QLabel#notice { background: #1c1725; border: 1px solid #40334d; border-radius: 9px; color: #c9bdd5; padding: 10px 12px; }
    QLabel#notice[kind="success"] { background: #14251e; border-color: #2e624a; color: #91e1b8; }
    QLabel#notice[kind="error"] { background: #2a171d; border-color: #723848; color: #ff9caf; }
    """
