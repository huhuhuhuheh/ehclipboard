import sys
import os
import json
import base64
import ctypes
import traceback
import platform
import configparser
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTabWidget, QWidget, QComboBox, QSpinBox,
    QCheckBox, QToolButton, QMessageBox, QLineEdit, QLayout,
    QRadioButton, QButtonGroup
)
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt, QTimer
from about_qt import ICON_BASE64
import passwords

WDA_EXCLUDEFROMCAPTURE_MIN_BUILD = 19041

LOCK_TIMEOUTS = [
    (3600, 'PasswordsLockTime1Hour'),
    (18000, 'PasswordsLockTime5Hours'),
    (28800, 'PasswordsLockTime8Hours'),
    (86400, 'PasswordsLockTime1Day'),
    (432000, 'PasswordsLockTime5Days'),
    (604800, 'PasswordsLockTime1Week'),
]

def apply_wda(window):
    try:
        user32 = ctypes.WinDLL("user32")
        hwnd = int(window.winId())
        top = user32.GetAncestor(hwnd, 2)
        user32.SetWindowDisplayAffinity(top, 0x11)
    except Exception:
        pass

def apply_yes_no(ui, box):
    try:
        yes_btn = box.button(QMessageBox.Yes)
        no_btn = box.button(QMessageBox.No)
        if yes_btn is not None:
            yes_btn.setText(ui.get('Yes', 'Yes'))
        if no_btn is not None:
            no_btn.setText(ui.get('No', 'No'))
    except Exception:
        pass


def add_caps_lock_label(ui, edit, layout):
    label = QLabel(ui.get('CapsLockOn', 'Caps Lock is on!'))
    label.setStyleSheet('color: #e05c5c; font-weight: bold;')
    label.setVisible(False)
    label.setWordWrap(True)
    layout.addWidget(label)

    def refresh():
        on = False
        try:
            on = bool(ctypes.windll.user32.GetKeyState(0x14) & 1)
        except Exception:
            try:
                on = QApplication.capsLock()
            except Exception:
                on = False
        label.setVisible(on and edit.hasFocus() and edit.echoMode() == QLineEdit.Password)

    timer = QTimer(edit)
    timer.setInterval(150)
    timer.timeout.connect(refresh)
    timer.start()
    refresh()

def get_windows_version_string():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
        display_ver = winreg.QueryValueEx(key, "DisplayVersion")[0]
        build = winreg.QueryValueEx(key, "CurrentBuildNumber")[0]
        winreg.CloseKey(key)
        ver = f"Version {display_ver} (Build {build})"
        if not ver.lower().startswith("windows"):
            ver = "Windows " + ver
        return ver
    except Exception:
        ver = platform.platform()
        if not ver.lower().startswith("windows"):
            ver = "Windows " + ver
        return ver

def supports_exclude_from_capture():
    try:
        v = sys.getwindowsversion()
        return v.major > 10 or (v.major == 10 and v.build >= WDA_EXCLUDEFROMCAPTURE_MIN_BUILD)
    except Exception:
        return False

def load_current_settings(config_file):
    settings = {}
    try:
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(config_file, encoding='utf-8-sig')
        if 'Settings' in cp:
            s = cp['Settings']
            for key in ['style', 'animation_in', 'animation_out', 'x_rule', 'y_rule', 'pos_anchor', 'language']:
                settings[key] = s.get(key, '')
            settings['x_val'] = s.getint('x_val', 0)
            settings['y_val'] = s.getint('y_val', 0)
            try:
                settings['hide_from_capture'] = s.getboolean('hide_from_capture', False)
            except Exception:
                settings['hide_from_capture'] = False
    except Exception:
        pass
    return settings

def parse_lang_display_from_file(path):
    try:
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(path, encoding='utf-8-sig')
        if 'Language' in cp and 'LangNameDisplay' in cp['Language']:
            return cp['Language']['LangNameDisplay']
    except Exception:
        pass
    return os.path.splitext(os.path.basename(path))[0]

def build_icon():
    icon_data = base64.b64decode(ICON_BASE64)
    pixmap = QPixmap()
    if pixmap.loadFromData(icon_data):
        return QIcon(pixmap)
    return QIcon()

def clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.hide()
            w.setParent(None)
            w.deleteLater()
            continue
        sub = item.layout()
        if sub is not None:
            clear_layout(sub)
            sub.deleteLater()

class PasswordsAuthDialog(QDialog):
    def __init__(self, ui, vault, config_file, parent=None):
        super().__init__(parent)
        self.ui = ui
        self.vault = vault
        self.config_file = config_file
        self.decrypted = None
        self.key = None
        self.stage = 'master'
        self.setWindowTitle(ui.get('PasswordsUnlockTitle', 'Unlock your vault'))
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(440)
        self.resize(460, 300)

        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SetFixedSize)

        self.prompt = QLabel(ui.get('PasswordsUnlockMasterLabel', 'Type your master password to unlock your vault'))
        self.prompt.setWordWrap(True)
        layout.addWidget(self.prompt)

        self.input = QLineEdit()
        self.input.setEchoMode(QLineEdit.Password)
        self.input.setPlaceholderText(ui.get('PasswordsMasterPassword', 'Master password'))
        self.input.returnPressed.connect(self.on_submit)
        layout.addWidget(self.input)
        add_caps_lock_label(ui, self.input, layout)

        self.forgot_btn = QPushButton(ui.get('PasswordsForgotThatOne', 'Forgot that one?'))
        self.forgot_btn.setVisible(False)
        self.forgot_btn.clicked.connect(self.toggle_methods)
        layout.addWidget(self.forgot_btn, alignment=Qt.AlignLeft)

        self.methods_row = QWidget()
        methods_layout = QHBoxLayout(self.methods_row)
        methods_layout.setContentsMargins(0, 0, 0, 0)
        self.btn_totp = QPushButton(ui.get('PasswordsUnlockTOTPButton', '2FA Code'))
        self.btn_backup = QPushButton(ui.get('PasswordsUnlockBackupButton', 'Backup code'))
        self.btn_totp.clicked.connect(lambda: self.set_stage('totp'))
        self.btn_backup.clicked.connect(lambda: self.set_stage('backup'))
        methods_layout.addWidget(self.btn_totp)
        methods_layout.addWidget(self.btn_backup)
        methods_layout.addStretch()
        self.methods_row.setVisible(False)
        layout.addWidget(self.methods_row)

        self.status = QLabel('')
        self.status.setStyleSheet('color: #e05c5c;')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        btn_cancel = QPushButton(ui.get('Cancel', 'Cancel'))
        self.btn_ok = QPushButton(ui.get('PasswordsUnlockButton', 'Unlock'))
        self.btn_ok.setDefault(True)
        btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self.on_submit)
        buttons.addStretch()
        buttons.addWidget(btn_cancel)
        buttons.addWidget(self.btn_ok)
        layout.addLayout(buttons)
        self.input.setFocus()

    def toggle_methods(self):
        self.methods_row.setVisible(not self.methods_row.isVisible())
        self.adjustSize()

    def set_stage(self, stage):
        self.methods_row.setVisible(False)
        self.status.setText('')
        self.stage = stage
        self.input.clear()
        if stage == 'master':
            self.decrypted = None
            self.key = None
            self.prompt.setText(self.ui.get('PasswordsUnlockMasterLabel', 'Type your master password to unlock your vault'))
            self.input.setEchoMode(QLineEdit.Password)
            self.input.setPlaceholderText(self.ui.get('PasswordsMasterPassword', 'Master password'))
            self.forgot_btn.setVisible(False)
        elif stage == 'totp':
            self.prompt.setText(self.ui.get('PasswordsUnlockTOTPLabel', 'Type your 2FA code to unlock your vault'))
            self.input.setEchoMode(QLineEdit.Normal)
            self.input.setPlaceholderText(self.ui.get('PasswordsTOTPCode', '2FA code'))
            self.forgot_btn.setVisible(True)
            self.btn_totp.setVisible(False)
            self.btn_backup.setVisible(True)
        elif stage == 'backup':
            self.prompt.setText(self.ui.get('PasswordsUnlockBackupLabel', 'Type your backup code to unlock your vault'))
            self.input.setEchoMode(QLineEdit.Normal)
            self.input.setPlaceholderText(self.ui.get('PasswordsBackupCodePlaceholder', 'Backup code'))
            self.forgot_btn.setVisible(True)
            self.btn_totp.setVisible(True)
            self.btn_backup.setVisible(False)
        self.input.setFocus()

    def on_submit(self):
        self.status.setText('')
        self.btn_ok.setEnabled(False)
        try:
            text = self.input.text()
            if self.stage == 'master':
                try:
                    self.decrypted = passwords.unlock_vault(self.vault, text)
                    self.key = self.decrypted.pop('_key', None)
                except passwords.WrongPasswordError:
                    self.status.setText(self.ui.get('PasswordsWrongPassword', 'Wrong master password.'))
                    return
                except passwords.VaultError as e:
                    self.status.setText(str(e))
                    return
                if self.decrypted.get('totp_enabled'):
                    self.set_stage('totp')
                else:
                    self.accept()
                return
            elif self.stage == 'totp':
                secret_b64 = (self.decrypted or {}).get('totp_secret_b64')
                secret = base64.b64decode(secret_b64).decode() if secret_b64 else None
                if not passwords.totp_verify(secret, text):
                    self.status.setText(self.ui.get('PasswordsWrongTOTP', 'Wrong 2FA code.'))
                    return
                self.accept()
                return
            elif self.stage == 'backup':
                hashes = list((self.decrypted or {}).get('backup_codes', []))
                if not hashes:
                    self.status.setText(self.ui.get('PasswordsNoBackupCodes', 'No backup codes left.'))
                    return
                if passwords.consume_backup_code(hashes, text):
                    self.decrypted['backup_codes'] = hashes
                    try:
                        passwords.save_vault_with_key(self.vault, self.key, self.decrypted)
                    except Exception:
                        pass
                    self.accept()
                else:
                    self.status.setText(self.ui.get('PasswordsWrongBackup', 'That backup code does not match, or was already used.'))
        finally:
            self.btn_ok.setEnabled(True)


class OptionsDialog(QDialog):
    def __init__(self, ui_strings, config_file, styles, anims_in, anims_out, langs, anchors, vault='', vault_count=0):
        super().__init__()
        self.ui = ui_strings
        self.config_file = config_file
        self.supports_hide = supports_exclude_from_capture()
        self.styles = styles
        self.anims_in = anims_in
        self.anims_out = anims_out
        self.anchors = anchors
        self.lang_to_file = {display: fname for fname, display in langs.items()}
        self.file_to_lang = dict(langs)
        self.current = load_current_settings(config_file)
        self.vault = vault or passwords.vault_file_path(os.path.dirname(config_file) or '')
        self.vault_count = int(vault_count or 0)
        self._vault_existed = os.path.exists(self.vault)
        self._vault_poll = QTimer(self)
        self._vault_poll.timeout.connect(self._poll_vault)
        self._vault_poll.start(500)

        self.setWindowTitle(self.ui.get('OptionsWindowTitle', "eh's Clipboard Options"))
        self.setWindowModality(Qt.ApplicationModal)
        self.resize(460, 320)
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowCloseButtonHint)

        tabs = QTabWidget()
        tabs.addTab(self.create_general_tab(), self.ui.get('GeneralTab', 'General'))
        tabs.addTab(self.create_position_tab(), self.ui.get('PositionTab', 'Position'))
        tabs.addTab(self.create_language_tab(), self.ui.get('Language', 'Language'))
        tabs.addTab(self.create_privacy_tab(), self.ui.get('PrivacyTab', 'Privacy'))
        tabs.currentChanged.connect(self.on_tab_changed)
        self.tabs = tabs

        btn_ok = QPushButton(self.ui.get('OK', 'OK'))
        btn_cancel = QPushButton(self.ui.get('Cancel', 'Cancel'))
        btn_ok.setDefault(True)
        btn_cancel.clicked.connect(self.reject)
        btn_ok.clicked.connect(self.on_ok)

        buttons = QHBoxLayout()
        buttons.addStretch()
        buttons.addWidget(btn_ok)
        buttons.addWidget(btn_cancel)

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(tabs)
        main_layout.addLayout(buttons)

    def add_row(self, layout, label_text, control, help_text):
        row = QHBoxLayout()
        label = QLabel(label_text)
        label.setMinimumWidth(120)
        help_btn = QToolButton()
        help_btn.setText("?")
        help_btn.setToolTip(help_text)
        help_btn.setAutoRaise(True)
        help_btn.setFixedSize(20, 20)
        row.addWidget(label)
        row.addWidget(control, 1)
        row.addWidget(help_btn)
        layout.addLayout(row)

    def make_combo(self, items, current, allow_extra=False):
        combo = QComboBox()
        combo.addItems(items)
        if current and current not in items:
            if allow_extra:
                combo.addItem(current)
            combo.setCurrentText(current if current in items or allow_extra else '')
        else:
            combo.setCurrentText(current or '')
        return combo

    def create_general_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.style_combo = self.make_combo(self.styles, self.current.get('style', ''))
        self.add_row(layout, self.ui.get('Style', 'Style'), self.style_combo, self.ui.get('HelpStyle', ''))

        self.anim_in_combo = self.make_combo(self.anims_in, self.current.get('animation_in', ''))
        self.add_row(layout, self.ui.get('AnimationIn', 'Animation In'), self.anim_in_combo, self.ui.get('HelpAnimationIn', ''))

        self.anim_out_combo = self.make_combo(self.anims_out, self.current.get('animation_out', ''))
        self.add_row(layout, self.ui.get('AnimationOut', 'Animation Out'), self.anim_out_combo, self.ui.get('HelpAnimationOut', ''))

        layout.addStretch()
        return tab

    def create_position_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        rules = ['default', 'absolute', 'edge']
        self.x_rule_combo = self.make_combo(rules, self.current.get('x_rule', 'default'))
        self.add_row(layout, self.ui.get('XRuleLabel', 'X Rule'), self.x_rule_combo, self.ui.get('HelpXRule', ''))

        self.x_val_spin = QSpinBox()
        self.x_val_spin.setRange(0, 100000)
        self.x_val_spin.setValue(int(self.current.get('x_val', 0)))
        self.add_row(layout, self.ui.get('XValueLabel', 'X Value'), self.x_val_spin, self.ui.get('HelpXValue', ''))

        self.y_rule_combo = self.make_combo(rules, self.current.get('y_rule', 'default'))
        self.add_row(layout, self.ui.get('YRuleLabel', 'Y Rule'), self.y_rule_combo, self.ui.get('HelpYRule', ''))

        self.y_val_spin = QSpinBox()
        self.y_val_spin.setRange(0, 100000)
        self.y_val_spin.setValue(int(self.current.get('y_val', 0)))
        self.add_row(layout, self.ui.get('YValueLabel', 'Y Value'), self.y_val_spin, self.ui.get('HelpYValue', ''))

        self.anchor_combo = self.make_combo(self.anchors, self.current.get('pos_anchor', 'se'))
        self.add_row(layout, self.ui.get('PosAnchorLabel', 'Position Anchor'), self.anchor_combo, self.ui.get('HelpPosAnchor', ''))

        layout.addStretch()
        return tab

    def create_language_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        current_lang = self.current.get('language', 'en-US.ini')
        current_display = self.file_to_lang.get(current_lang, current_lang)
        self.lang_combo = self.make_combo(list(self.file_to_lang.values()), current_display)
        self.add_row(layout, self.ui.get('Language', 'Language'), self.lang_combo, self.ui.get('HelpLanguage', ''))

        layout.addStretch()
        self.lang_tab = tab
        return tab

    def on_tab_changed(self, index):
        try:
            if self.tabs.widget(index) is self.lang_tab:
                self.refresh_languages()
        except Exception:
            pass

    def refresh_languages(self):
        try:
            lang_dir = os.path.join(os.path.dirname(self.config_file), 'lang')
            new_langs = {}
            if os.path.isdir(lang_dir):
                for fname in sorted(os.listdir(lang_dir)):
                    if fname.lower().endswith('.ini') and os.path.isfile(os.path.join(lang_dir, fname)):
                        full = os.path.join(lang_dir, fname)
                        display = parse_lang_display_from_file(full)
                        new_langs[fname] = display
            if not new_langs:
                new_langs = dict(self.file_to_lang)
            if set(new_langs.values()) != set(self.file_to_lang.values()):
                old = self.lang_combo.currentText()
                self.file_to_lang = new_langs
                self.lang_to_file = {display: fname for fname, display in new_langs.items()}
                self.lang_combo.blockSignals(True)
                self.lang_combo.clear()
                self.lang_combo.addItems(sorted(new_langs.values()))
                if old in self.lang_to_file:
                    self.lang_combo.setCurrentText(old)
                self.lang_combo.blockSignals(False)
        except Exception:
            pass

    def unsupported_message(self):
        base = self.ui.get('HideFromCaptureUnsupported', "This feature isn't for your version of Windows ({WindowsVer}), it requires the Windows 10 2020 Update (19041)")
        if '{WindowsVer}' in base:
            return base.replace('{WindowsVer}', get_windows_version_string())
        return f"{base} {get_windows_version_string()}"

    def create_privacy_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.hide_check = QCheckBox(self.ui.get('HideFromCapture', 'Hide Toast from being screenshotted'))
        if self.supports_hide:
            self.hide_check.setChecked(bool(self.current.get('hide_from_capture', False)))
            self.hide_check.setToolTip(self.ui.get('HelpHideFromCapture', ''))
        else:
            self.hide_check.setEnabled(False)
            self.hide_check.setChecked(False)
            self.hide_check.setToolTip(self.unsupported_message())

        row = QHBoxLayout()
        help_btn = QToolButton()
        help_btn.setText("?")
        help_btn.setAutoRaise(True)
        help_btn.setFixedSize(20, 20)
        if self.supports_hide:
            help_btn.setToolTip(self.ui.get('HelpHideFromCapture', ''))
        else:
            help_btn.setToolTip(self.unsupported_message())
        row.addWidget(self.hide_check, 1)
        row.addWidget(help_btn)
        layout.addLayout(row)

        vault_title = QLabel(self.ui.get('PasswordsVaultName', 'Password Vault'))
        vf = vault_title.font()
        vf.setBold(True)
        vault_title.setFont(vf)
        layout.addWidget(vault_title)

        self.pw_container = QWidget()
        layout.addWidget(self.pw_container)
        self._build_pw_section()

        layout.addStretch()
        return tab

    def _pw_get(self, key, default):
        try:
            cp = configparser.ConfigParser(interpolation=None)
            cp.read(self.config_file, encoding='utf-8-sig')
            if 'Passwords' in cp and key in cp['Passwords']:
                if isinstance(default, bool):
                    return cp['Passwords'].getboolean(key, default)
                if isinstance(default, int):
                    return cp['Passwords'].getint(key, default)
                return cp['Passwords'][key]
        except Exception:
            pass
        return default

    def _pw_write(self, values, pending_editor=None):
        try:
            cp = configparser.ConfigParser(interpolation=None)
            if os.path.exists(self.config_file):
                cp.read(self.config_file, encoding='utf-8-sig')
            if 'Passwords' not in cp:
                cp['Passwords'] = {}
            p = cp['Passwords']
            p['hide_passwords_from_toast'] = str(values.get('hide_passwords_from_toast', True))
            p['show_passwords_on_hover'] = str(values.get('show_passwords_on_hover', False))
            p['hover_reveal_seconds'] = str(values.get('hover_reveal_seconds', 2))
            p['hide_passwords_from_capture'] = str(values.get('hide_passwords_from_capture', True))
            p['lock_on_close'] = str(values.get('lock_on_close', False))
            p['lock_after_time'] = str(values.get('lock_after_time', False))
            p['lock_timeout'] = str(values.get('lock_timeout', 3600))
            if pending_editor is not None:
                p['pending_open_editor'] = str(pending_editor)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                cp.write(f)
        except Exception as e:
            print(f"ERROR saving passwords options: {e}", file=sys.stderr)

    def _build_pw_section(self):
        layout = self.pw_container.layout() or QVBoxLayout(self.pw_container)
        clear_layout(layout)
        self.pw_hide_toast = None
        self.pw_hover_check = None
        self.pw_hover_seconds = None
        self.pw_hide_capture = None
        self.pw_lock_on_close = None
        self.pw_lock_after_time = None
        self.pw_lock_timeout = None
        if not os.path.exists(self.vault):
            btn = QPushButton(self.ui.get('PasswordsSetupCreate', 'Create vault'))
            btn.clicked.connect(self._pw_request_open)
            layout.addWidget(btn)
            return

        row = QHBoxLayout()
        self.pw_hide_toast = QCheckBox(self.ui.get('PasswordsHideFromToast', 'Hide passwords from the toast'))
        self.pw_hide_toast.setChecked(bool(self._pw_get('hide_passwords_from_toast', True)))
        row.addWidget(self.pw_hide_toast, 1)
        row.addWidget(self._make_help_btn(self.ui.get('HelpPasswordsHideToast', 'When on, any password stored in your vault is hidden when it shows up on the toast')))
        layout.addLayout(row)

        hover_row = QHBoxLayout()
        self.pw_hover_check = QCheckBox(self.ui.get('PasswordsShowOnHover', 'Reveal passwords when hovering the toast'))
        self.pw_hover_check.setChecked(bool(self._pw_get('show_passwords_on_hover', False)))
        hover_row.addWidget(self.pw_hover_check, 1)
        self.pw_hover_seconds = QSpinBox()
        self.pw_hover_seconds.setRange(1, 30)
        self.pw_hover_seconds.setValue(int(self._pw_get('hover_reveal_seconds', 2)))
        self.pw_hover_seconds.setEnabled(self.pw_hover_check.isChecked())
        self.pw_hover_check.toggled.connect(self.pw_hover_seconds.setEnabled)
        hover_row.addWidget(self.pw_hover_seconds)
        hover_row.addWidget(self._make_help_btn(self.ui.get('HelpPasswordsShowOnHover', 'When on, hovering the toast reveals the hidden passwords for a few seconds')))
        layout.addLayout(hover_row)

        row = QHBoxLayout()
        self.pw_hide_capture = QCheckBox(self.ui.get('PasswordsHideFromCapture', 'Hide passwords from being captured'))
        if self.supports_hide:
            self.pw_hide_capture.setChecked(bool(self._pw_get('hide_passwords_from_capture', True)))
            capture_help = self.ui.get('HelpPasswordsHideFromCapture', 'When on, the vault windows are hidden from screenshots and screen recorders (when possible)')
            self.pw_hide_capture.setToolTip(capture_help)
        else:
            self.pw_hide_capture.setEnabled(False)
            self.pw_hide_capture.setChecked(False)
            capture_help = self.unsupported_message()
            self.pw_hide_capture.setToolTip(capture_help)
        row.addWidget(self.pw_hide_capture, 1)
        row.addWidget(self._make_help_btn(capture_help))
        layout.addLayout(row)

        lock_group = QButtonGroup(self.pw_container)
        row = QHBoxLayout()
        self.pw_lock_on_close = QRadioButton(self.ui.get('PasswordsLockOnClose', 'Lock your vault right after you close it'))
        self.pw_lock_on_close.setChecked(bool(self._pw_get('lock_on_close', False)))
        lock_group.addButton(self.pw_lock_on_close)
        row.addWidget(self.pw_lock_on_close, 1)
        row.addWidget(self._make_help_btn(self.ui.get('HelpPasswordsLockOnClose', 'Simply lock the vault the moment you close that')))
        layout.addLayout(row)

        row = QHBoxLayout()
        self.pw_lock_after_time = QRadioButton(self.ui.get('PasswordsLockAfterTime', 'Lock your vault after a certain time'))
        self.pw_lock_after_time.setChecked(bool(self._pw_get('lock_after_time', False)))
        lock_group.addButton(self.pw_lock_after_time)
        row.addWidget(self.pw_lock_after_time, 1)
        row.addWidget(self._make_help_btn(self.ui.get('HelpPasswordsLockAfterTime', 'Lock the vault after a certain time the moment it is unlocked')))
        layout.addLayout(row)

        time_row = QHBoxLayout()
        time_label = QLabel(self.ui.get('PasswordsLockDuration', 'Auto-lock after'))
        time_label.setMinimumWidth(120)
        self.pw_lock_timeout = QComboBox()
        current_timeout = int(self._pw_get('lock_timeout', 3600))
        for seconds, key in LOCK_TIMEOUTS:
            self.pw_lock_timeout.addItem(self.ui.get(key, '1 Hour'), seconds)
        idx = self.pw_lock_timeout.findData(current_timeout)
        self.pw_lock_timeout.setCurrentIndex(idx if idx >= 0 else 0)
        self.pw_lock_timeout.setEnabled(self.pw_lock_after_time.isChecked())
        self.pw_lock_after_time.toggled.connect(self.pw_lock_timeout.setEnabled)
        time_row.addWidget(time_label)
        time_row.addWidget(self.pw_lock_timeout, 1)
        time_row.addWidget(self._make_help_btn(self.ui.get('HelpPasswordsLockDuration', 'How long the vault stays unlocked before it locks by itself')))
        layout.addLayout(time_row)

        row = QHBoxLayout()
        btn_open = QPushButton(self.ui.get('PasswordsOpenEditor', 'Open passwords'))
        btn_open.clicked.connect(self._pw_request_open)
        btn_disable = QPushButton(self.ui.get('PasswordsDisable', 'Disable vault'))
        btn_disable.clicked.connect(self._pw_disable)
        row.addWidget(btn_open)
        row.addWidget(self._make_help_btn(self.ui.get('HelpPasswordsOpenEditor', 'Opens your vault to add, edit, delete or import passwords')))
        row.addWidget(btn_disable)
        row.addWidget(self._make_help_btn(self.ui.get('HelpPasswordsDisable', 'Deletes your vault permanently!')))
        layout.addLayout(row)

    def _make_help_btn(self, help_text):
        help_btn = QToolButton()
        help_btn.setText("?")
        help_btn.setToolTip(help_text)
        help_btn.setAutoRaise(True)
        help_btn.setFixedSize(20, 20)
        return help_btn

    def _poll_vault(self):
        try:
            exists = os.path.exists(self.vault)
            if exists != self._vault_existed:
                self._vault_existed = exists
                self._build_pw_section()
        except Exception:
            pass

    def _pw_checked(self, name, default):
        w = getattr(self, name, None)
        if w is not None:
            try:
                return w.isChecked()
            except Exception:
                pass
        return self._pw_get(name, default)

    def _pw_spin(self, name, default):
        w = getattr(self, name, None)
        if w is not None:
            try:
                return w.value()
            except Exception:
                pass
        return self._pw_get(name, default)

    def _pw_radio_checked(self, name, default):
        w = getattr(self, name, None)
        if w is not None:
            try:
                return w.isChecked()
            except Exception:
                pass
        return self._pw_get(name, default)

    def _pw_combo_data(self, name, default):
        w = getattr(self, name, None)
        if w is not None:
            try:
                return w.currentData()
            except Exception:
                pass
        return self._pw_get(name, default)

    def _save_pw_settings(self, pending_editor=None):
        self._pw_write({
            'hide_passwords_from_toast': self._pw_checked('pw_hide_toast', True),
            'show_passwords_on_hover': self._pw_checked('pw_hover_check', False),
            'hover_reveal_seconds': self._pw_spin('pw_hover_seconds', 2),
            'hide_passwords_from_capture': self._pw_checked('pw_hide_capture', True),
            'lock_on_close': self._pw_radio_checked('pw_lock_on_close', False),
            'lock_after_time': self._pw_radio_checked('pw_lock_after_time', False),
            'lock_timeout': self._pw_combo_data('pw_lock_timeout', 3600),
        }, pending_editor)

    def _pw_request_open(self):
        self._save_pw_settings(pending_editor=True)

    def _pw_disable(self):
        dlg = PasswordsAuthDialog(self.ui, self.vault, self.config_file, self)
        apply_wda(dlg)
        if dlg.exec() != QDialog.Accepted:
            return
        count = len((dlg.decrypted or {}).get('entries', []))
        word = self.ui.get('PasswordsWordOne', 'password') if count == 1 else self.ui.get('PasswordsWordMany', 'passwords')
        msg = self.ui.get('PasswordsDisableVaultMessage', 'Disabling your vault means deleting, so all of your {count} {passwords} will be gone forever! Are you sure you gonna do this?').format(count=count, passwords=word)
        box = QMessageBox(QMessageBox.Question, self.ui.get('PasswordsDisableVaultTitle', 'Disable your vault?'), msg, QMessageBox.Yes | QMessageBox.No, self)
        box.setDefaultButton(QMessageBox.No)
        apply_wda(box)
        apply_yes_no(self.ui, box)
        if box.exec() != QMessageBox.Yes:
            return
        try:
            if os.path.exists(self.vault):
                os.remove(self.vault)
            d = os.path.dirname(self.vault)
            if os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
            self.vault_count = 0
            self._vault_existed = False
            self._save_pw_settings()
            self._build_pw_section()
        except Exception as e:
            QMessageBox.critical(self, self.ui.get('Error', 'Error'), str(e))

    def on_ok(self):
        try:
            cp = configparser.ConfigParser(interpolation=None)
            if os.path.exists(self.config_file):
                cp.read(self.config_file, encoding='utf-8-sig')
            if 'Settings' not in cp:
                cp['Settings'] = {}
            s = cp['Settings']
            s['style'] = self.style_combo.currentText()
            s['animation_in'] = self.anim_in_combo.currentText()
            s['animation_out'] = self.anim_out_combo.currentText()
            s['x_rule'] = self.x_rule_combo.currentText()
            s['x_val'] = str(self.x_val_spin.value())
            s['y_rule'] = self.y_rule_combo.currentText()
            s['y_val'] = str(self.y_val_spin.value())
            s['pos_anchor'] = self.anchor_combo.currentText()
            s['language'] = self.lang_to_file.get(self.lang_combo.currentText(), 'en-US.ini')
            s['hide_from_capture'] = 'True' if self.hide_check.isChecked() else 'False'
            with open(self.config_file, 'w', encoding='utf-8') as f:
                cp.write(f)
            self._save_pw_settings()
        except Exception as e:
            print(f"ERROR saving options: {e}", file=sys.stderr)
        self.accept()

def show_options_dialog(ui_strings, config_file, styles, anims_in, anims_out, langs, anchors, vault='', vault_count=0):
    try:
        app = QApplication.instance() or QApplication(sys.argv)
        app.setWindowIcon(build_icon())

        if not styles:
            styles = ['Default Dark', 'Light']
        if not anims_in:
            anims_in = ['Slide Up + Fade', 'Fade In', 'Zoom In', 'Slide In From Right']
        if not anims_out:
            anims_out = ['Slide Down + Fade', 'Fade Out', 'Zoom Out', 'Slide Out To Right']
        if not anchors:
            anchors = ['se', 'sw', 'ne', 'nw', 'n', 's', 'e', 'w']

        dialog = OptionsDialog(ui_strings or {}, config_file, styles, anims_in, anims_out, langs, anchors, vault, vault_count)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        app.exec()
    except Exception as e:
        print(f"ERROR in show_options_dialog: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

if __name__ == '__main__':
    try:
        data = {}
        if len(sys.argv) > 1:
            with open(sys.argv[1], 'r', encoding='utf-8') as f:
                data = json.load(f)
        show_options_dialog(
            data.get('ui', {}),
            data.get('config_file', ''),
            data.get('styles', []),
            data.get('anims_in', []),
            data.get('anims_out', []),
            data.get('langs', {}),
            data.get('anchors', []),
            data.get('vault', ''),
            int(data.get('vault_count') or 0),
        )
    except Exception as e:
        print(f"FATAL ERROR in options_qt.py main: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)