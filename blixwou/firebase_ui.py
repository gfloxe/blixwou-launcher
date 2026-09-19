"""Non-blocking community account dialog; independent from Minecraft profiles."""
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QLineEdit, QLabel, QPushButton


class FirebaseDialog(QDialog):
    def __init__(self, accounts, parent):
        super().__init__(parent)
        self.accounts, self.job = accounts, None
        self.setWindowTitle('Compte BLIXWOU')
        self.setMinimumWidth(470)
        layout = QVBoxLayout(self)
        self.heading = QLabel('Votre compte BLIXWOU')
        self.heading.setStyleSheet('font-size: 24px; font-weight: 700; color: #cda4ff;')
        layout.addWidget(self.heading)
        note = QLabel('Compte communautaire BLIXWOU. Votre profil Minecraft reste indépendant.')
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.email, self.password, self.username = QLineEdit(), QLineEdit(), QLineEdit()
        self.email.setMaxLength(254)
        self.password.setMaxLength(128)
        self.password.setEchoMode(QLineEdit.Password)
        self.username.setMaxLength(16)
        self.username.setPlaceholderText('3–16 lettres minuscules, chiffres ou _')
        for label, field in [('E-mail', self.email), ('Mot de passe', self.password), ('Pseudo unique', self.username)]:
            form.addRow(label, field)
        layout.addLayout(form)
        self.actions = []
        for label, action in [('Se connecter', 'login'), ('Créer mon compte', 'register'),
                              ('Valider mon pseudo', 'claim'), ('Mot de passe oublié', 'reset'), ('Se déconnecter', 'logout')]:
            button = QPushButton(label)
            button.clicked.connect(lambda checked=False, name=action: self.perform(name))
            self.actions.append(button)
            layout.addWidget(button)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        self.refresh()
        if accounts.path.exists():
            QTimer.singleShot(0, lambda: self.perform('resume'))

    def refresh(self):
        self.heading.setText('Bonjour ' + self.accounts.username if self.accounts.username else 'Votre compte BLIXWOU')
        for button in self.actions:
            button.setEnabled(self.job is None)
        self.actions[2].setEnabled(self.job is None and self.accounts.session is not None and not self.accounts.username)
        self.actions[4].setEnabled(self.job is None and (self.accounts.session is not None or self.accounts.path.exists()))

    def perform(self, action):
        from .app import Worker
        if self.job is not None:
            return
        if action == 'logout':
            self.accounts.logout()
            self.notice.setText('Déconnecté de ce PC.')
            self.refresh()
            return
        email, password, username = self.email.text().strip(), self.password.text(), self.username.text()
        if action in ('login', 'register', 'reset') and not email:
            self.notice.setText('Renseignez votre adresse e-mail.')
            return
        self.password.clear()
        def task(progress, cancelled):
            if action == 'register': return self.accounts.register(email, password, username)
            if action == 'login': return self.accounts.login(email, password)
            if action == 'claim': return self.accounts.claim_name(username)
            if action == 'reset': return self.accounts.reset_password(email)
            return self.accounts.resume()
        self.job = Worker(task, self)
        self.job.success.connect(lambda result: self.notice.setText(
            result if action == 'reset' else 'Connexion réussie.' if self.accounts.username
            else 'Compte connecté. Choisissez un pseudo et cliquez sur « Valider mon pseudo ».'))
        self.job.failure.connect(self.notice.setText)
        self.job.finished.connect(self.finished_job)
        self.notice.setText('Connexion à Firebase…')
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
        if self.job is not None:
            event.ignore()
        else:
            event.accept()
