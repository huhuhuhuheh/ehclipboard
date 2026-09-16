import sys
import os
import json
import base64
import ctypes
import traceback
import platform
import configparser
import time
import collections
from types import SimpleNamespace

from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QCheckBox, QListWidget, QMessageBox,
    QWizard, QWizardPage, QRadioButton, QComboBox, QFileDialog,
    QPlainTextEdit, QWidget, QLayout
)
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QPixmap, QIcon, QDesktopServices

import passwords
import sesv
from sesv_guard import create_vault_guard
from about_qt import ICON_BASE64


def build_icon():
    icon_data = base64.b64decode(ICON_BASE64)
    pixmap = QPixmap()
    if pixmap.loadFromData(icon_data):
        return QIcon(pixmap)
    return QIcon()


BRO_ASSNAME = {
    'Google Chrome': ['chrome.exe'],
    'Google Chrome Canary': ['chrome.exe'],
    'Chromium': ['chrome.exe'],
    'Opera': ['opera.exe'],
    'Opera Beta': ['opera.exe'],
    'Opera Developer': ['opera.exe'],
    'Microsoft Edge': ['msedge.exe'],
    'Microsoft Edge Beta': ['msedge.exe'],
    'Microsoft Edge Dev': ['msedge.exe'],
    'Microsoft Edge Canary': ['msedge.exe'],
}


def is_process_running(exe_names):
    try:
        import subprocess
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        for name in (exe_names or []):
            try:
                out = subprocess.run(
                    ['tasklist', '/FI', 'IMAGENAME eq ' + name, '/NH'],
                    capture_output=True, text=True, timeout=5,
                    creationflags=flags,
                )
                if name.lower() in out.stdout.lower():
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def process_names_for_browser(user_data_dir):
    try:
        for name, path in passwords.chromium_user_data_dirs().items():
            if os.path.normpath(path).lower() == os.path.normpath(user_data_dir).lower():
                procs = BRO_ASSNAME.get(name)
                if procs:
                    return procs
    except Exception:
        pass
    return ['chrome.exe', 'msedge.exe', 'opera.exe']


def apply_wda(window):
    try:
        user32 = ctypes.WinDLL("user32")
        hwnd = int(window.winId())
        top = user32.GetAncestor(hwnd, 2)
        user32.SetWindowDisplayAffinity(top, 0x11)
    except Exception:
        pass


def clear_wda(window):
    try:
        user32 = ctypes.WinDLL("user32")
        hwnd = int(window.winId())
        top = user32.GetAncestor(hwnd, 2)
        user32.SetWindowDisplayAffinity(top, 0x0)
    except Exception:
        pass


def apply_wda_if_enabled(config_file, window):
    try:
        if read_pw_settings(config_file).get('hide_passwords_from_capture', True):
            apply_wda(window)
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


WDA_EXCLUDEFROMCAPTURE_MIN_BUILD = 19041


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


def unsupported_message(ui):
    base = ui.get('HideFromCaptureUnsupported', "This feature isn't for your version of Windows ({WindowsVer}), it requires the Windows 10 2020 Update (19041)")
    if '{WindowsVer}' in base:
        return base.replace('{WindowsVer}', get_windows_version_string())
    return f"{base} {get_windows_version_string()}"


def read_pw_settings(config_file):
    settings = {'hide_passwords_from_capture': True}
    try:
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(config_file, encoding='utf-8-sig')
        if 'Passwords' in cp:
            settings['hide_passwords_from_capture'] = cp['Passwords'].getboolean('hide_passwords_from_capture', True)
    except Exception:
        pass
    return settings


def plural_word(ui, count):
    if count == 1:
        return ui.get('PasswordsWordOne', 'password')
    return ui.get('PasswordsWordMany', 'passwords')


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



def backup_code_word(ui, count):
    if count == 1:
        return ui.get('PasswordsBackupCodeWordOne', 'code')
    return ui.get('PasswordsBackupCodeWordMany', 'codes')


def write_key_to_stdout(key):
    try:
        if key:
            sys.stdout.buffer.write(key)
            sys.stdout.buffer.flush()
    except Exception:
        pass


def write_key(key, key_file=None):
    if key_file:
        try:
            with open(key_file, 'wb') as f:
                f.write(key)
            return
        except Exception:
            pass
    write_key_to_stdout(key)


def read_key_from_stdin():
    try:
        data = sys.stdin.buffer.read(passwords.KEY_LENGTH)
        if len(data) == passwords.KEY_LENGTH:
            return data
    except Exception:
        pass
    return None


def read_key(key_file=None):
    if key_file:
        try:
            with open(key_file, 'rb') as f:
                data = f.read()
            if len(data) == passwords.KEY_LENGTH:
                return data
        except Exception:
            pass
    return read_key_from_stdin()


def totp_uri(ui, secret, vault_name):
    issuer = ui.get('PasswordsAppName', "Eh's Clipboard")
    if vault_name:
        account = ui.get('PasswordsTOTPAccount', 'Vault for {vaultName}').format(vaultName=vault_name)
    else:
        account = ui.get('PasswordsTOTPAccountFallback', 'User')
    return passwords.totp_otpauth_uri(secret, issuer, account)


URI2FA = ("ente", "enteauth", "onepassword", "otpauth")


def _scheme_has_url_protocol(scheme):
    try:
        import winreg
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(root, "Software\\Classes\\" + scheme) as key:
                    try:
                        winreg.QueryValueEx(key, "URL Protocol")
                        return True
                    except OSError:
                        pass
            except OSError:
                pass
    except Exception:
        pass
    return False


def _assoc_executable(scheme):
    try:
        from ctypes import wintypes, create_unicode_buffer, byref
        shlwapi = ctypes.WinDLL("shlwapi")
        buf = create_unicode_buffer(4096)
        size = wintypes.DWORD(len(buf))
        hr = shlwapi.AssocQueryStringW(None, 2, scheme + ":", None, buf, byref(size))
        return buf.value if hr == 0 and buf.value else None
    except Exception:
        return None


def _scheme_is_registered(scheme):
    return _scheme_has_url_protocol(scheme) or _assoc_executable(scheme) is not None


def find_registered_auth_scheme():
    for scheme in URI2FA:
        if _scheme_is_registered(scheme):
            return scheme
    return None


def make_secret_row(ui, secret, vault_name):
    row = QHBoxLayout()
    secret_box = QLineEdit(secret)
    secret_box.setReadOnly(True)
    secret_box.setEchoMode(QLineEdit.Password)
    show_check = QCheckBox()
    show_check.setToolTip(ui.get('PasswordsShowSecret', 'Show secret'))
    show_check.toggled.connect(
        lambda on: secret_box.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password)
    )
    copy_btn = QPushButton(ui.get('PasswordsCopySecret', 'Copy secret'))
    copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(secret))
    link_btn = QPushButton(ui.get('PasswordsOpenAuthLink', 'Open authenticator link'))
    uri = totp_uri(ui, secret, vault_name)
    link_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(uri)))
    if not find_registered_auth_scheme():
        link_btn.hide()
    row.addWidget(secret_box, 1)
    row.addWidget(show_check)
    row.addWidget(copy_btn)
    row.addWidget(link_btn)
    return row


def make_qr_label(ui, secret, vault_name):
    try:
        import qrcode
        from PySide6.QtGui import QImage
        uri = totp_uri(ui, secret, vault_name)
        img = qrcode.make(uri).convert("RGBA")
        data = img.tobytes("raw", "RGBA")
        qimage = QImage(data, img.size[0], img.size[1], QImage.Format_RGBA8888)
        pixmap = QPixmap.fromImage(qimage).scaled(160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        label = QLabel()
        label.setPixmap(pixmap)
        return label
    except Exception:
        return None


class IntroPage(QWizardPage):
    def __init__(self, wizard):
        super().__init__()
        self.wz = wizard
        self.setTitle(wizard.ui.get('PasswordsVaultName', 'Password Vault'))
        self.setSubTitle(wizard.ui.get('PasswordsWizardIntroTitle', "What's This?"))
        label = QLabel(wizard.ui.get('PasswordsWizardIntroBody', ''))
        label.setWordWrap(True)
        lay = QVBoxLayout(self)
        lay.addWidget(label)

    def nextId(self):
        return self.wz.PAGE_IMPORT_SOURCE


class ImportSourcePage(QWizardPage):
    def __init__(self, wizard):
        super().__init__()
        self.wz = wizard
        self.setTitle(wizard.ui.get('PasswordsImportSourceTitle', 'Where do you import passwords?'))
        self.setSubTitle(wizard.ui.get('PasswordsImportSourceSubtitle', 'Choose how you want the passwords to be setup'))
        self.import_radio = QRadioButton(wizard.ui.get('PasswordsImportFromBrowser', 'Import passwords from my browsers or a file'))
        self.none_radio = QRadioButton(wizard.ui.get('PasswordsImportNone', 'Do not import any password'))
        self.import_radio.setChecked(True)
        lay = QVBoxLayout(self)
        lay.addWidget(self.import_radio)
        lay.addWidget(self.none_radio)
        lay.addStretch()

    def nextId(self):
        if self.import_radio.isChecked():
            return self.wz.PAGE_IMPORT_DETAILS
        return self.wz.PAGE_ACCESS


class ImportDetailsPage(QWizardPage):
    def __init__(self, wizard):
        super().__init__()
        self.wz = wizard
        self.setTitle(wizard.ui.get('PasswordsImportDetailsTitle', 'Importing passwords'))
        self.setSubTitle(wizard.ui.get('PasswordsImportDetailsSubtitle', 'Choose how to import the passwords'))

        lay = QVBoxLayout(self)
        desc = QLabel(wizard.ui.get('PasswordsImportDetailsDesc', 'Choose where you want to import the passwords from'))
        desc.setWordWrap(True)
        lay.addWidget(desc)

        self.browser_radio = QRadioButton(wizard.ui.get('PasswordsImportSourceBrowser', 'Browser'))
        self.file_radio = QRadioButton(wizard.ui.get('PasswordsImportSourceFile', 'Via a file'))
        self.browser_radio.setChecked(True)
        lay.addWidget(self.browser_radio)
        lay.addWidget(self.file_radio)

        self.browser_row = QWidget()
        brow = QHBoxLayout(self.browser_row)
        brow.setContentsMargins(0, 0, 0, 0)
        brow.addWidget(QLabel(wizard.ui.get('PasswordsImportProfileLabel', 'Profile')))
        self.browser_combo = QComboBox()
        self.profile_combo = QComboBox()
        brow.addWidget(self.browser_combo, 1)
        brow.addWidget(self.profile_combo, 1)
        lay.addWidget(self.browser_row)

        self.file_row = QWidget()
        self.file_row.setVisible(False)
        frow = QHBoxLayout(self.file_row)
        frow.setContentsMargins(0, 0, 0, 0)
        frow.addWidget(QLabel(wizard.ui.get('PasswordsImportFileLabel', 'Passwords file:')))
        self.file_edit = QLineEdit()
        self.file_edit.setReadOnly(True)
        frow.addWidget(self.file_edit, 1)
        browse_btn = QPushButton(wizard.ui.get('PasswordsImportBrowse', 'Browse...'))
        browse_btn.clicked.connect(self.on_browse)
        frow.addWidget(browse_btn)
        lay.addWidget(self.file_row)

        self.no_browser_label = QLabel(wizard.ui.get('PasswordsImportNoBrowser', 'No supported browsers were found on this PC.'))
        self.no_browser_label.setWordWrap(True)
        self.no_browser_label.setStyleSheet('color: #e05c5c;')
        self.no_browser_label.setVisible(False)
        lay.addWidget(self.no_browser_label)

        lay.addStretch()

        self.browser_radio.toggled.connect(self.on_source_changed)
        self.browser_combo.currentIndexChanged.connect(self.on_browser_changed)

        self._browser_open = False
        self._proc_timer = QTimer(self)
        self._proc_timer.setInterval(1000)
        self._proc_timer.timeout.connect(self._check_browser_processes)
        self.browser_radio.toggled.connect(self._refresh_process_state)
        self.browser_combo.currentIndexChanged.connect(self._refresh_process_state)

    def on_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.wz.ui.get('PasswordsImportFileLabel', 'Passwords file:'),
            '',
            self.wz.ui.get('PasswordsImportFileFilter', 'CSV files (*.csv)'),
        )
        if path:
            self.file_edit.setText(path)

    def on_source_changed(self):
        browser = self.browser_radio.isChecked()
        self.browser_row.setVisible(browser)
        self.file_row.setVisible(not browser)

    def on_browser_changed(self):
        self.profile_combo.clear()
        data = self.browser_combo.currentData()
        if not data:
            return
        self.profile_combo.addItem(self.wz.ui.get('PasswordsImportAllProfiles', 'All profiles'), None)
        for profile in passwords.chromium_profiles(data):
            self.profile_combo.addItem(profile, profile)

    def initializePage(self):
        self.browser_combo.clear()
        dirs = passwords.chromium_user_data_dirs()
        if not dirs:
            self.no_browser_label.setVisible(True)
            self.browser_radio.setEnabled(False)
            self.browser_combo.setEnabled(False)
            self.profile_combo.setEnabled(False)
            self.file_radio.setChecked(True)
            self.on_source_changed()
            self._refresh_process_state()
            return
        self.no_browser_label.setVisible(False)
        self.browser_radio.setEnabled(True)
        self.browser_combo.setEnabled(True)
        self.profile_combo.setEnabled(True)
        for name, path in dirs.items():
            self.browser_combo.addItem(name, path)
        self.on_browser_changed()
        self._refresh_process_state()

    def _refresh_process_state(self):
        if not self.browser_radio.isChecked() or not self.browser_combo.currentData():
            self._proc_timer.stop()
            if self._browser_open:
                self._browser_open = False
                self.completeChanged.emit()
            return
        self._check_browser_processes()
        if not self._proc_timer.isActive():
            self._proc_timer.start()

    def _check_browser_processes(self):
        if not self.browser_radio.isChecked():
            self._proc_timer.stop()
            if self._browser_open:
                self._browser_open = False
                self.completeChanged.emit()
            return
        path = self.browser_combo.currentData()
        if not path:
            return
        open_now = is_process_running(process_names_for_browser(path))
        if open_now != self._browser_open:
            self._browser_open = open_now
            self.completeChanged.emit()

    def isComplete(self):
        if not self.browser_radio.isChecked():
            return True
        if not self.browser_combo.currentData():
            return True
        return not self._browser_open

    def cleanupPage(self):
        self._proc_timer.stop()
        super().cleanupPage()

    def gather_entries(self):
        if self.browser_radio.isChecked():
            path = self.browser_combo.currentData()
            if not path:
                return []
            profile = self.profile_combo.currentData()
            if profile:
                return passwords.import_from_chromium_profile(path, profile)
            return passwords.import_from_chromium(path)
        fpath = self.file_edit.text().strip()
        if fpath:
            try:
                return passwords.import_from_csv(fpath)
            except Exception:
                return []
        return []

    def nextId(self):
        return self.wz.PAGE_ACCESS


class AccessPage(QWizardPage):
    def __init__(self, wizard):
        super().__init__()
        self.wz = wizard
        self.setTitle(wizard.ui.get('PasswordsAccessTitle', 'How do you access your vault?'))
        self.setSubTitle(wizard.ui.get('PasswordsAccessSubtitle', 'Option to access your vault'))
        desc = QLabel(wizard.ui.get('PasswordsAccessDesc', 'Now you need to setup some option to access your vault!'))
        desc.setWordWrap(True)
        self.master_radio = QRadioButton(wizard.ui.get('PasswordsAccessMasterOnly', 'Master Password'))
        self.twofa_radio = QRadioButton(wizard.ui.get('PasswordsAccess2FA', '2FA Code'))
        self.master_radio.setChecked(True)
        lay = QVBoxLayout(self)
        lay.addWidget(desc)
        lay.addWidget(self.master_radio)
        lay.addWidget(self.twofa_radio)
        lay.addStretch()

    def nextId(self):
        return self.wz.PAGE_MASTER


class MasterPasswordPage(QWizardPage):
    def __init__(self, wizard):
        super().__init__()
        self.wz = wizard
        self.setTitle(wizard.ui.get('PasswordsMasterPageTitle', 'Master Password'))
        self.setSubTitle(wizard.ui.get('PasswordsMasterPageSubtitle', 'Type your Master Password'))

        lay = QVBoxLayout(self)
        h1 = QLabel(wizard.ui.get('PasswordsMasterPageHint', 'Your Master Password must be unique and not exactly the same as your password!'))
        h1.setWordWrap(True)
        lay.addWidget(h1)
        h2 = QLabel(wizard.ui.get('PasswordsMasterPageHint2', 'For the privacy, also, the password is not visible so choose something you will remember!'))
        h2.setWordWrap(True)
        lay.addWidget(h2)
        lay.addSpacing(8)

        self.pw_input = QLineEdit()
        self.pw_input.setEchoMode(QLineEdit.Password)
        self.pw_input.setPlaceholderText(wizard.ui.get('PasswordsMasterPassword', 'Master password'))
        lay.addWidget(self.pw_input)

        add_caps_lock_label(wizard.ui, self.pw_input, lay)

        self.confirm_input = QLineEdit()
        self.confirm_input.setEchoMode(QLineEdit.Password)
        self.confirm_input.setPlaceholderText(wizard.ui.get('PasswordsMasterPasswordConfirm', 'Repeat master password'))
        lay.addWidget(self.confirm_input)

        add_caps_lock_label(wizard.ui, self.confirm_input, lay)

        self.status = QLabel('')
        self.status.setStyleSheet('color: #e05c5c;')
        self.status.setWordWrap(True)
        lay.addWidget(self.status)

        self.pw_input.textChanged.connect(self._on_change)
        self.confirm_input.textChanged.connect(self._on_change)

    def _on_change(self):
        pw = self.pw_input.text()
        confirm = self.confirm_input.text()
        if len(pw) < 8:
            self.status.setStyleSheet('color: #e05c5c;')
            self.status.setText(self.wz.ui.get('PasswordsPasswordTooShort', 'Master password must be at least 8 characters.'))
        elif not confirm:
            self.status.setStyleSheet('color: #c9a227;')
            self.status.setText(self.wz.ui.get('PasswordsPasswordRepeat', 'Now repeat your master password'))
        elif pw != confirm:
            self.status.setStyleSheet('color: #e05c5c;')
            self.status.setText(self.wz.ui.get('PasswordsPasswordMismatch', 'Passwords do not match.'))
        else:
            self.status.setStyleSheet('color: #4caf50;')
            self.status.setText(self.wz.ui.get('PasswordsPasswordMatches', 'Passwords match'))
            self.wz.master_pw = pw
        self.completeChanged.emit()

    def isComplete(self):
        return len(self.pw_input.text()) >= 8 and self.pw_input.text() == self.confirm_input.text()

    def validatePage(self):
        pw = self.pw_input.text()
        confirm = self.confirm_input.text()
        if len(pw) < 8:
            self.status.setText(self.wz.ui.get('PasswordsPasswordTooShort', 'Master password must be at least 8 characters.'))
            return False
        if pw != confirm:
            self.status.setText(self.wz.ui.get('PasswordsPasswordMismatch', 'Passwords do not match.'))
            return False
        self.wz.master_pw = pw
        return True

    def nextId(self):
        access = self.wz.page(self.wz.PAGE_ACCESS)
        if access and access.twofa_radio.isChecked():
            return self.wz.PAGE_VAULT_NAME
        return -1


class VaultNamePage(QWizardPage):
    def __init__(self, wizard):
        super().__init__()
        self.wz = wizard
        self.setTitle(wizard.ui.get('PasswordsVaultNameTitle', 'Your Vault Name'))
        self.setSubTitle(wizard.ui.get('PasswordsVaultNameSubtitle', 'A Name for your Vault!'))
        self.lay = QVBoxLayout(self)
        self.built = False

    def initializePage(self):
        if self.built:
            return
        self.built = True
        hint = QLabel(self.wz.ui.get('PasswordsVaultNameLabel', 'The Vault name is not necessary, but it gives you a little reminder if when setting up the 2FA codes'))
        hint.setWordWrap(True)
        self.lay.addWidget(hint)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(self.wz.ui.get('PasswordsVaultNamePlaceholder', 'Cool Vault...'))
        self.lay.addWidget(self.name_edit)

    def validatePage(self):
        name = self.name_edit.text().strip()
        self.wz.vault_name = name or None
        return True

    def nextId(self):
        return self.wz.PAGE_TOTP


class TotpPage(QWizardPage):
    def __init__(self, wizard):
        super().__init__()
        self.wz = wizard
        self.setTitle(wizard.ui.get('PasswordsTOTPTitle', 'Set Up 2FA'))
        self.setSubTitle(wizard.ui.get('PasswordsTOTPSubtitle', 'Use 2FA to unlock the vault'))
        self.lay = QVBoxLayout(self)
        self.built = False

    def initializePage(self):
        if self.built:
            return
        self.built = True
        if not self.wz.totp_secret:
            self.wz.totp_secret = passwords.generate_totp_secret()
        instr = QLabel(self.wz.ui.get('PasswordsTOTPInstructions', 'Scan the QR code or add the secret to your authenticator app (like Bitwarden or Google Authenticator) then type the code below:'))
        instr.setWordWrap(True)
        self.lay.addWidget(instr)
        self.lay.addLayout(make_secret_row(self.wz.ui, self.wz.totp_secret, self.wz.vault_name))
        try:
            qr = make_qr_label(self.wz.ui, self.wz.totp_secret, self.wz.vault_name)
            if qr is not None:
                self.lay.addWidget(qr, alignment=Qt.AlignCenter)
        except Exception:
            pass
        code_row = QHBoxLayout()
        code_row.addWidget(QLabel(self.wz.ui.get('PasswordsTOTPCodeLabel', 'Code:')))
        self.code_edit = QLineEdit()
        self.code_edit.setMaxLength(6)
        self.code_edit.setPlaceholderText(self.wz.ui.get('PasswordsTOTPCodePlaceholder', 'Code'))
        self.code_edit.textChanged.connect(lambda: self.completeChanged.emit())
        code_row.addWidget(self.code_edit, 1)
        self.lay.addLayout(code_row)
        self.valid_label = QLabel()
        self.valid_label.setWordWrap(True)
        self.lay.addWidget(self.valid_label)

    def isComplete(self):
        text = self.code_edit.text().strip()
        if not text:
            self.valid_label.setText('')
            return False
        if not passwords.totp_verify(self.wz.totp_secret, text):
            self.valid_label.setText(self.wz.ui.get('PasswordsTOTPInvalid', 'That code is not valid, check the app and try again.'))
            return False
        self.valid_label.setText(self.wz.ui.get('PasswordsTOTPValid', 'Code accepted!'))
        return True

    def nextId(self):
        return self.wz.PAGE_BACKUP


class BackupCodesPage(QWizardPage):
    def __init__(self, wizard):
        super().__init__()
        self.wz = wizard
        self.setTitle(wizard.ui.get('PasswordsBackupCodesTitle', 'Your backup codes'))
        self.setSubTitle(wizard.ui.get('PasswordsBackupCodesSubtitle', 'Save those!'))
        self.lay = QVBoxLayout(self)
        self.built = False

    def initializePage(self):
        if self.built:
            return
        self.built = True
        if not self.wz.backup_codes:
            self.wz.backup_codes = passwords.generate_backup_codes()
        hint = QLabel(self.wz.ui.get('PasswordsBackupCodesHint', "Those are your backup codes for when you can't have access, make sure you save those securely! (Like a USB)"))
        hint.setWordWrap(True)
        self.lay.addWidget(hint)
        self.codes_edit = QPlainTextEdit('\n'.join(self.wz.backup_codes))
        self.codes_edit.setReadOnly(True)
        self.codes_edit.setMaximumHeight(220)
        self.lay.addWidget(self.codes_edit)
        note = QLabel(self.wz.ui.get('PasswordsBackupCodesNote', 'Those codes can be used once (15 each)'))
        note.setWordWrap(True)
        self.lay.addWidget(note)
        save_btn = QPushButton(self.wz.ui.get('PasswordsBackupCodesSave', 'Save codes to a file'))
        save_btn.clicked.connect(self.save_codes_to_file)
        self.lay.addWidget(save_btn)
        self.saved_check = QCheckBox(self.wz.ui.get('PasswordsBackupCodesDone', 'I saved them'))
        self.saved_check.toggled.connect(lambda: self.completeChanged.emit())
        self.lay.addWidget(self.saved_check)

    def save_codes_to_file(self):
        if not self.wz.backup_codes:
            return
        default_name = f"backup-codes-{self.wz.vault_name or 'User'}.txt"
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.wz.ui.get('PasswordsBackupCodesFileTitle', 'Save backup codes'),
            default_name,
            "Text Files (*.txt)",
        )
        if not path:
            return
        template = self.wz.ui.get(
            'PasswordsBackupCodesFile',
            'Those are your backup codes for accessing your {vaultName} vault, make sure those are entirely safe! {codes}',
        )
        codes_text = '\n\n' + '\n'.join(self.wz.backup_codes)
        content = template.format(vaultName=self.wz.vault_name or 'User', codes=codes_text)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception:
            QMessageBox.warning(
                self,
                self.wz.ui.get('PasswordsBackupCodesSave', 'Save codes to a file'),
                self.wz.ui.get('PasswordsBackupCodesSaveFailed', 'Could not save the file.'),
            )

    def isComplete(self):
        return self.saved_check.isChecked()

    def nextId(self):
        return -1


class SetupWizard(QWizard):
    PAGE_INTRO = 0
    PAGE_IMPORT_SOURCE = 1
    PAGE_IMPORT_DETAILS = 2
    PAGE_ACCESS = 3
    PAGE_MASTER = 4
    PAGE_VAULT_NAME = 5
    PAGE_TOTP = 6
    PAGE_BACKUP = 7

    def __init__(self, ui, vault_path, config_file, key_file=None):
        super().__init__()
        self.ui = ui
        self.vault_path = vault_path
        self.config_file = config_file
        self.key_file = key_file
        self.totp_secret = None
        self.backup_codes = None
        self.master_pw = None
        self.vault_name = None

        self.setWindowTitle(ui.get('PasswordsSetupTitle', 'Set up password vault'))
        self.setWindowModality(Qt.ApplicationModal)
        self.setWizardStyle(QWizard.ModernStyle)
        self.setOption(QWizard.NoBackButtonOnStartPage, True)
        self.setButtonText(QWizard.FinishButton, ui.get('PasswordsSetupCreate', 'Create vault'))
        self.resize(640, 560)

        self.setPage(self.PAGE_INTRO, IntroPage(self))
        self.setPage(self.PAGE_IMPORT_SOURCE, ImportSourcePage(self))
        self.setPage(self.PAGE_IMPORT_DETAILS, ImportDetailsPage(self))
        self.setPage(self.PAGE_ACCESS, AccessPage(self))
        self.setPage(self.PAGE_MASTER, MasterPasswordPage(self))
        self.setPage(self.PAGE_VAULT_NAME, VaultNamePage(self))
        self.setPage(self.PAGE_TOTP, TotpPage(self))
        self.setPage(self.PAGE_BACKUP, BackupCodesPage(self))
        self.setStartId(self.PAGE_INTRO)

        try:
            apply_wda(self)
        except Exception:
            pass

    def accept(self):
        entries = []
        try:
            source_page = self.page(self.PAGE_IMPORT_SOURCE)
            if source_page.import_radio.isChecked():
                details = self.page(self.PAGE_IMPORT_DETAILS)
                entries = details.gather_entries()
        except Exception:
            entries = []
        if entries:
            word = plural_word(self.ui, len(entries))
            msg = self.ui.get('PasswordsImportConfirm', 'Import {count} {passwords} into your vault?').format(count=len(entries), passwords=word)
            box = QMessageBox(QMessageBox.Question, self.ui.get('PasswordsImportConfirmTitle', 'Import passwords?'), msg, QMessageBox.Yes | QMessageBox.No, self)
            box.setDefaultButton(QMessageBox.Yes)
            apply_wda_if_enabled(self.config_file, box)
            apply_yes_no(self.ui, box)
            if box.exec() != QMessageBox.Yes:
                entries = []
        try:
            passwords.create_vault(
                self.vault_path,
                self.master_pw,
                entries=entries,
                totp_secret=self.totp_secret,
                totp_enabled=bool(self.totp_secret),
                backup_codes=self.backup_codes,
            )
            key = passwords.derive_key_from_file(self.vault_path, self.master_pw)
            write_key(key, self.key_file)
        except Exception as e:
            QMessageBox.critical(self, self.ui.get('Error', 'Error'), str(e))
            return
        super().accept()


class UnlockDialog(QDialog):
    def __init__(self, ui, vault_path, config_file, key_file=None):
        super().__init__()
        self.ui = ui
        self.vault_path = vault_path
        self.config_file = config_file
        self.key_file = key_file
        self.decrypted = None
        self.key = None
        self.stage = 'master'
        self.setWindowTitle(ui.get('PasswordsUnlockTitle', 'Unlock your vault'))
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(560)
        self.resize(560, 300)

        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SetFixedSize)

        self.prompt_label = QLabel(ui.get('PasswordsUnlockMasterLabel', 'Type your master password to unlock your vault'))
        self.prompt_label.setWordWrap(True)
        layout.addWidget(self.prompt_label)

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
        self.btn_unlock = QPushButton(ui.get('PasswordsUnlockButton', 'Unlock'))
        btn_cancel = QPushButton(ui.get('Cancel', 'Cancel'))
        self.btn_unlock.setDefault(True)
        btn_cancel.clicked.connect(self.reject)
        self.btn_unlock.clicked.connect(self.on_submit)
        buttons.addStretch()
        buttons.addWidget(btn_cancel)
        buttons.addWidget(self.btn_unlock)
        layout.addLayout(buttons)

        try:
            settings = read_pw_settings(config_file)
            if settings.get('hide_passwords_from_capture'):
                apply_wda(self)
        except Exception:
            pass

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
            self.prompt_label.setText(self.ui.get('PasswordsUnlockMasterLabel', 'Type your master password to unlock your vault'))
            self.input.setEchoMode(QLineEdit.Password)
            self.input.setPlaceholderText(self.ui.get('PasswordsMasterPassword', 'Master password'))
            self.forgot_btn.setVisible(False)
        elif stage == 'totp':
            self.prompt_label.setText(self.ui.get('PasswordsUnlockTOTPLabel', 'Type your 2FA code to unlock your vault'))
            self.input.setEchoMode(QLineEdit.Normal)
            self.input.setPlaceholderText(self.ui.get('PasswordsTOTPCode', '2FA code'))
            self.forgot_btn.setVisible(True)
            self.btn_totp.setVisible(False)
            self.btn_backup.setVisible(True)
        elif stage == 'backup':
            self.prompt_label.setText(self.ui.get('PasswordsUnlockBackupLabel', 'Type your backup code to unlock your vault'))
            self.input.setEchoMode(QLineEdit.Normal)
            self.input.setPlaceholderText(self.ui.get('PasswordsBackupCodePlaceholder', 'Backup code'))
            self.forgot_btn.setVisible(True)
            self.btn_totp.setVisible(True)
            self.btn_backup.setVisible(False)
        self.input.setFocus()

    def on_submit(self):
        self.status.setText('')
        self.btn_unlock.setEnabled(False)
        try:
            text = self.input.text()
            if self.stage == 'master':
                try:
                    self.decrypted = passwords.unlock_vault(self.vault_path, text)
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
                    self.finish_unlock()
                return
            elif self.stage == 'totp':
                secret_b64 = (self.decrypted or {}).get('totp_secret_b64')
                secret = base64.b64decode(secret_b64).decode() if secret_b64 else None
                if not passwords.totp_verify(secret, text):
                    self.status.setText(self.ui.get('PasswordsWrongTOTP', 'Wrong 2FA code.'))
                    return
                self.finish_unlock()
                return
            elif self.stage == 'backup':
                hashes = list((self.decrypted or {}).get('backup_codes', []))
                if not hashes:
                    self.status.setText(self.ui.get('PasswordsNoBackupCodes', 'No backup codes left.'))
                    return
                if passwords.consume_backup_code(hashes, text):
                    self.decrypted['backup_codes'] = hashes
                    try:
                        passwords.save_vault_with_key(self.vault_path, self.key, self.decrypted)
                    except Exception:
                        pass
                    self.finish_unlock()
                else:
                    self.status.setText(self.ui.get('PasswordsWrongBackup', 'That backup code does not match, or was already used.'))
                return
        finally:
            self.btn_unlock.setEnabled(True)

    def finish_unlock(self):
        if self.key:
            write_key(self.key, self.key_file)
            self.accept()


class EntryDialog(QDialog):
    def __init__(self, ui, entry=None):
        super().__init__()
        self.ui = ui
        self.entry = entry or {}
        self.setWindowTitle(ui.get('PasswordsEntryDialogTitle', 'Password entry'))
        self.setWindowModality(Qt.ApplicationModal)
        self.resize(420, 260)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(ui.get('PasswordsEntryName', 'Name')))
        self.name_input = QLineEdit(self.entry.get('name', ''))
        layout.addWidget(self.name_input)

        layout.addWidget(QLabel(ui.get('PasswordsEntryUsername', 'Username')))
        self.username_input = QLineEdit(self.entry.get('username', ''))
        layout.addWidget(self.username_input)

        layout.addWidget(QLabel(ui.get('PasswordsEntryPassword', 'Password')))
        pw_row = QHBoxLayout()
        self.pw_input = QLineEdit(self.entry.get('password', ''))
        self.pw_input.setEchoMode(QLineEdit.Password)
        show_check = QCheckBox(ui.get('PasswordsShowPassword', 'Show password'))
        show_check.toggled.connect(
            lambda on: self.pw_input.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password)
        )
        pw_row.addWidget(self.pw_input, 1)
        pw_row.addWidget(show_check)
        layout.addLayout(pw_row)

        self.hide_capture_check = QCheckBox(ui.get('PasswordsEntryHideCapture', 'Hide this password from being captured'))
        if supports_exclude_from_capture():
            self.hide_capture_check.setChecked(bool(self.entry.get('hide_capture', True)))
        else:
            self.hide_capture_check.setEnabled(False)
            self.hide_capture_check.setChecked(False)
            self.hide_capture_check.setToolTip(unsupported_message(ui))
        layout.addWidget(self.hide_capture_check)

        self.status = QLabel('')
        self.status.setStyleSheet('color: #e05c5c;')
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        btn_save = QPushButton(ui.get('PasswordsSave', 'Save'))
        btn_cancel = QPushButton(ui.get('Cancel', 'Cancel'))
        btn_save.setDefault(True)
        btn_cancel.clicked.connect(self.reject)
        btn_save.clicked.connect(self.on_save)
        buttons.addStretch()
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_save)
        layout.addLayout(buttons)

        try:
            apply_wda(self)
        except Exception:
            pass

    def on_save(self):
        name = self.name_input.text().strip()
        if not name:
            self.status.setText(self.ui.get('PasswordsEmptyName', 'Name cannot be empty.'))
            return
        self.entry['name'] = name
        self.entry['username'] = self.username_input.text()
        self.entry['password'] = self.pw_input.text()
        if self.hide_capture_check.isEnabled():
            self.entry['hide_capture'] = self.hide_capture_check.isChecked()
        self.accept()


class ImportDialog(QDialog):
    def __init__(self, ui, config_file, parent=None):
        super().__init__(parent)
        self.ui = ui
        self.config_file = config_file
        self.entries = []
        self.setWindowTitle(ui.get('PasswordsImportDetailsTitle', 'Importing passwords'))
        self.setWindowModality(Qt.ApplicationModal)
        self.resize(480, 300)

        layout = QVBoxLayout(self)
        self.page = ImportDetailsPage(SimpleNamespace(ui=ui))
        layout.addWidget(self.page)
        self.page.initializePage()

        buttons = QHBoxLayout()
        btn_cancel = QPushButton(ui.get('Cancel', 'Cancel'))
        btn_import = QPushButton(ui.get('PasswordsImportButton', 'Import'))
        btn_import.setDefault(True)
        btn_import.setEnabled(self.page.isComplete())
        btn_cancel.clicked.connect(self.reject)
        btn_import.clicked.connect(self.on_import)
        self.page.completeChanged.connect(lambda: btn_import.setEnabled(self.page.isComplete()))
        buttons.addStretch()
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_import)
        layout.addLayout(buttons)

    def on_import(self):
        try:
            entries = self.page.gather_entries()
        except Exception:
            entries = []
        if not entries:
            QMessageBox.information(
                self,
                self.ui.get('PasswordsImportConfirmTitle', 'Import passwords?'),
                self.ui.get('PasswordsImportNothing', 'No passwords to import.'),
            )
            return
        word = plural_word(self.ui, len(entries))
        msg = self.ui.get('PasswordsImportConfirm', 'Import {count} {passwords} into your vault?').format(count=len(entries), passwords=word)
        box = QMessageBox(QMessageBox.Question, self.ui.get('PasswordsImportConfirmTitle', 'Import passwords?'), msg, QMessageBox.Yes | QMessageBox.No, self)
        box.setDefaultButton(QMessageBox.Yes)
        apply_wda_if_enabled(self.config_file, box)
        apply_yes_no(self.ui, box)
        if box.exec() == QMessageBox.Yes:
            self.entries = entries
            self.accept()

class ChangeMasterDialog(QDialog):
    def __init__(self, ui, vault_path, config_file):
        super().__init__()
        self.ui = ui
        self.vault_path = vault_path
        self.config_file = config_file
        self.new_key = None
        self.setWindowTitle(ui.get('PasswordsChangeMasterTitle', 'Change master password'))
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(420)
        self.resize(420, 300)

        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SetFixedSize)

        hint = QLabel(ui.get('PasswordsChangeMasterHint', 'Type your current master password, then set a new one'))
        hint.setWordWrap(True)
        layout.addWidget(hint)

        layout.addWidget(QLabel(ui.get('PasswordsChangeMasterOld', 'Current master password')))
        self.old_input = QLineEdit()
        self.old_input.setEchoMode(QLineEdit.Password)
        self.old_input.setPlaceholderText(ui.get('PasswordsMasterPassword', 'Master password'))
        self.old_input.returnPressed.connect(self.on_submit)
        layout.addWidget(self.old_input)

        add_caps_lock_label(ui, self.old_input, layout)

        layout.addWidget(QLabel(ui.get('PasswordsChangeMasterNew', 'New master password')))
        self.new_input = QLineEdit()
        self.new_input.setEchoMode(QLineEdit.Password)
        self.new_input.setPlaceholderText(ui.get('PasswordsChangeMasterNew', 'New master password'))
        layout.addWidget(self.new_input)

        add_caps_lock_label(ui, self.new_input, layout)

        layout.addWidget(QLabel(ui.get('PasswordsChangeMasterRepeat', 'Repeat new master password')))
        self.repeat_input = QLineEdit()
        self.repeat_input.setEchoMode(QLineEdit.Password)
        self.repeat_input.setPlaceholderText(ui.get('PasswordsChangeMasterRepeat', 'Repeat new master password'))
        self.repeat_input.returnPressed.connect(self.on_submit)
        layout.addWidget(self.repeat_input)

        add_caps_lock_label(ui, self.repeat_input, layout)

        self.status = QLabel('')
        self.status.setStyleSheet('color: #e05c5c;')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        btn_change = QPushButton(ui.get('PasswordsChangeMasterButton', 'Change'))
        btn_cancel = QPushButton(ui.get('Cancel', 'Cancel'))
        btn_change.setDefault(True)
        btn_cancel.clicked.connect(self.reject)
        btn_change.clicked.connect(self.on_submit)
        buttons.addStretch()
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_change)
        layout.addLayout(buttons)

        try:
            apply_wda_if_enabled(self.config_file, self)
        except Exception:
            pass

    def on_submit(self):
        self.status.setText('')
        old_pw = self.old_input.text()
        new_pw = self.new_input.text()
        repeat_pw = self.repeat_input.text()
        if not old_pw:
            self.status.setText(self.ui.get('PasswordsChangeMasterEnterOld', 'Type your current master password first.'))
            return
        if len(new_pw) < 8:
            self.status.setText(self.ui.get('PasswordsPasswordTooShort', 'Master password must be at least 8 characters.'))
            return
        if new_pw != repeat_pw:
            self.status.setText(self.ui.get('PasswordsPasswordMismatch', 'Passwords do not match.'))
            return
        try:
            passwords.change_master_password(self.vault_path, old_pw, new_pw)
        except passwords.WrongPasswordError:
            self.status.setText(self.ui.get('PasswordsWrongPassword', 'Wrong master password.'))
            return
        except passwords.VaultError as e:
            self.status.setText(str(e))
            return
        except Exception as e:
            self.status.setText(str(e))
            return
        try:
            self.new_key = passwords.derive_key_from_file(self.vault_path, new_pw)
        except Exception:
            self.new_key = None
        QMessageBox.information(
            self,
            self.ui.get('PasswordsChangeMasterDoneTitle', 'Changed'),
            self.ui.get('PasswordsChangeMasterDone', 'Your master password was changed.'),
        )
        self.accept()


class EditorDialog(QDialog):
    def __init__(self, ui, vault_path, key, config_file, status_file=None):
        super().__init__()
        self.ui = ui
        self.vault_path = vault_path
        self.key = key
        self.config_file = config_file
        self.status_file = status_file
        try:
            self.data = passwords.decrypt_vault_with_key(vault_path, key)
        except Exception:
            self.data = None
        self.entries = (self.data or {}).get('entries', [])
        self.setWindowTitle(ui.get('PasswordsEditorTitle', 'Passwords'))
        self.resize(520, 420)

        layout = QVBoxLayout(self)

        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(ui.get('PasswordsSearchPlaceholder', 'Search...'))
        self.search_input.textChanged.connect(self.refresh_list)
        search_row.addWidget(self.search_input, 1)
        btn_add = QPushButton(ui.get('PasswordsAdd', 'Add'))
        btn_add.clicked.connect(self.on_add)
        btn_import = QPushButton(ui.get('PasswordsImportButton', 'Import'))
        btn_import.clicked.connect(self.on_import)
        search_row.addWidget(btn_add)
        search_row.addWidget(btn_import)
        layout.addLayout(search_row)

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(lambda _: self.on_edit())
        layout.addWidget(self.list_widget, 1)

        btn_row = QHBoxLayout()
        btn_regenerate = QPushButton(ui.get('PasswordsRegenerateBackupCodes', 'Regenerate backup codes'))
        btn_regenerate.clicked.connect(self.on_regenerate_backup_codes)
        if not (self.data or {}).get('totp_enabled'):
            btn_regenerate.setVisible(False)
        btn_edit = QPushButton(ui.get('PasswordsEdit', 'Edit'))
        btn_edit.clicked.connect(self.on_edit)
        btn_delete = QPushButton(ui.get('PasswordsDelete', 'Delete'))
        btn_delete.clicked.connect(self.on_delete)
        btn_row.addStretch()
        btn_row.addWidget(btn_regenerate)
        btn_row.addWidget(btn_edit)
        btn_row.addWidget(btn_delete)
        layout.addLayout(btn_row)

        backup_row = QHBoxLayout()
        self.backup_codes_label = QLabel('')
        backup_row.addWidget(self.backup_codes_label, 1)
        layout.addLayout(backup_row)

        btn_ok = QPushButton(ui.get('OK', 'OK'))
        btn_cancel = QPushButton(ui.get('Cancel', 'Cancel'))
        btn_lock = QPushButton(ui.get('PasswordsLockVault', 'Lock vault'))
        btn_change = QPushButton(ui.get('PasswordsChangeMaster', 'Change master password'))
        btn_ok.setDefault(True)
        btn_cancel.clicked.connect(self.reject)
        btn_lock.clicked.connect(self.on_lock)
        btn_change.clicked.connect(self.on_change_master)
        btn_ok.clicked.connect(self.accept)
        bottom = QHBoxLayout()
        bottom.addStretch()
        bottom.addWidget(btn_cancel)
        bottom.addWidget(btn_change)
        bottom.addWidget(btn_lock)
        bottom.addWidget(btn_ok)
        layout.addLayout(bottom)

        self.refresh_list()
        self.refresh_backup_codes()

        try:
            settings = read_pw_settings(self.config_file)
            if settings.get('hide_passwords_from_capture') or any(
                e.get('hide_capture', True) for e in self.entries
            ):
                apply_wda(self)
        except Exception:
            pass

    def refresh_backup_codes(self):
        hashes = list((self.data or {}).get('backup_codes', []))
        if not hashes:
            self.backup_codes_label.setText('')
            return
        count = len(hashes)
        word = backup_code_word(self.ui, count)
        self.backup_codes_label.setText(self.ui.get('PasswordsBackupCodesLeft', '{count} backup {codes} left.').format(count=count, codes=word))

    def refresh_list(self):
        self.list_widget.clear()
        query = self.search_input.text().strip().lower()
        for e in self.entries:
            name = e.get('name', '')
            username = e.get('username', '')
            if query and query not in name.lower() and query not in username.lower():
                continue
            display = f"{name}"
            if username:
                display += f"  ({username})"
            self.list_widget.addItem(display)
        if self.list_widget.count() == 0:
            self.list_widget.addItem(self.ui.get('PasswordsEmpty', 'No entries yet.'))

    def selected_entry(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self.entries):
            return None
        return self.entries[row]

    def on_add(self):
        dlg = EntryDialog(self.ui)
        if dlg.exec() == QDialog.Accepted:
            entry = passwords.new_entry(
                dlg.entry.get('name', ''),
                dlg.entry.get('username', ''),
                dlg.entry.get('password', ''),
                hide_capture=dlg.entry.get('hide_capture', True),
            )
            self.entries.append(entry)
            self.refresh_list()

    def on_import(self):
        dlg = ImportDialog(self.ui, self.config_file, self)
        if dlg.exec() == QDialog.Accepted:
            for e in dlg.entries:
                self.entries.append(passwords.new_entry(
                    e.get('name', ''),
                    e.get('username', ''),
                    e.get('password', ''),
                    hide_capture=e.get('hide_capture', True),
                ))
            self.refresh_list()

    def on_edit(self):
        entry = self.selected_entry()
        if entry is None:
            return
        dlg = EntryDialog(self.ui, entry=entry)
        if dlg.exec() == QDialog.Accepted:
            passwords.update_entry(
                entry,
                name=dlg.entry.get('name'),
                username=dlg.entry.get('username'),
                password=dlg.entry.get('password'),
                hide_capture=dlg.entry.get('hide_capture'),
            )
            self.refresh_list()

    def on_delete(self):
        entry = self.selected_entry()
        if entry is None:
            return
        box = QMessageBox(
            QMessageBox.Question,
            self.ui.get('PasswordsDeleteConfirmTitle', 'Delete entry'),
            self.ui.get('PasswordsDeleteConfirmBody', 'Delete this entry?').format(name=entry.get('name', '')),
            QMessageBox.Yes | QMessageBox.No,
            self,
        )
        box.setDefaultButton(QMessageBox.No)
        apply_wda_if_enabled(self.config_file, box)
        apply_yes_no(self.ui, box)
        if box.exec() == QMessageBox.Yes:
            self.entries = passwords.delete_entry(self.entries, entry.get('id'))
            self.refresh_list()

    def accept(self):
        if self.data is not None:
            try:
                self.data['entries'] = self.entries
                passwords.save_vault_with_key(self.vault_path, self.key, self.data)
            except Exception as e:
                QMessageBox.critical(self, self.ui.get('Error', 'Error'), str(e))
                return
        super().accept()

    def on_lock(self):
        try:
            if self.status_file:
                with open(self.status_file, 'wb') as f:
                    f.write(b'LOCKED')
            else:
                sys.stdout.buffer.write(b'LOCKED')
                sys.stdout.buffer.flush()
        except Exception:
            pass
        self.accept()

    def on_change_master(self):
        dlg = ChangeMasterDialog(self.ui, self.vault_path, self.config_file)
        if dlg.exec() == QDialog.Accepted and dlg.new_key:
            self.key = dlg.new_key
            try:
                self.data = passwords.decrypt_vault_with_key(self.vault_path, self.key)
            except Exception:
                pass
            self.refresh_list()
            self.refresh_backup_codes()

    def on_regenerate_backup_codes(self):
        if (self.data or {}).get('totp_enabled'):
            dlg = TOTPVerifyDialog(self.ui, self.config_file, self.data)
            apply_wda_if_enabled(self.config_file, dlg)
            if dlg.exec() != QDialog.Accepted:
                return
        box = QMessageBox(
            QMessageBox.Question,
            self.ui.get('PasswordsRegenerateConfirmTitle', 'Regenerate backup codes?'),
            self.ui.get('PasswordsRegenerateConfirmBody', 'This will change your backup codes to new ones and makes your other ones invalid, are you sure?'),
            QMessageBox.Yes | QMessageBox.No,
            self,
        )
        box.setDefaultButton(QMessageBox.No)
        apply_wda_if_enabled(self.config_file, box)
        apply_yes_no(self.ui, box)
        if box.exec() != QMessageBox.Yes:
            return
        codes = passwords.generate_backup_codes()
        try:
            self.data['backup_codes'] = [passwords.hash_backup_code(c) for c in codes]
            passwords.save_vault_with_key(self.vault_path, self.key, self.data)
        except Exception as e:
            QMessageBox.critical(self, self.ui.get('Error', 'Error'), str(e))
            return
        self.refresh_backup_codes()
        dlg = BackupCodesDialog(self.ui, self.config_file, codes)
        apply_wda_if_enabled(self.config_file, dlg)
        dlg.exec()


class TOTPVerifyDialog(QDialog):
    def __init__(self, ui, config_file, data, parent=None):
        super().__init__(parent)
        self.ui = ui
        self.config_file = config_file
        self.data = data
        self.setWindowTitle(ui.get('PasswordsRegenerateTitle', 'Regenerate backup codes'))
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(400)
        self.resize(440, 180)

        layout = QVBoxLayout(self)
        layout.setSizeConstraint(QLayout.SetFixedSize)

        prompt = QLabel(ui.get('PasswordsRegenerateTOTPLabel', 'Type your 2FA code to continue'))
        prompt.setWordWrap(True)
        layout.addWidget(prompt)

        self.input = QLineEdit()
        self.input.setEchoMode(QLineEdit.Normal)
        self.input.setPlaceholderText(ui.get('PasswordsTOTPCode', '2FA code'))
        self.input.returnPressed.connect(self.on_submit)
        layout.addWidget(self.input)

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

    def on_submit(self):
        self.status.setText('')
        self.btn_ok.setEnabled(False)
        try:
            secret_b64 = (self.data or {}).get('totp_secret_b64')
            secret = base64.b64decode(secret_b64).decode() if secret_b64 else None
            if not passwords.totp_verify(secret, self.input.text()):
                self.status.setText(self.ui.get('PasswordsWrongTOTP', 'Wrong 2FA code.'))
                return
            self.accept()
        finally:
            self.btn_ok.setEnabled(True)


class BackupCodesDialog(QDialog):
    def __init__(self, ui, config_file, codes, parent=None):
        super().__init__(parent)
        self.ui = ui
        self.config_file = config_file
        self.codes = codes
        self.setWindowTitle(ui.get('PasswordsRegenerateTitle', 'Regenerate backup codes'))
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(460)
        self.resize(520, 380)

        layout = QVBoxLayout(self)

        hint = QLabel(ui.get('PasswordsBackupCodesHint', "Those are your backup codes for when you can't have access, make sure you save those securely! (Like a USB)"))
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.codes_edit = QPlainTextEdit('\n'.join(codes))
        self.codes_edit.setReadOnly(True)
        self.codes_edit.setMaximumHeight(220)
        layout.addWidget(self.codes_edit)

        note = QLabel(ui.get('PasswordsBackupCodesNote', 'Those codes can be used once (15 each)'))
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QHBoxLayout()
        save_btn = QPushButton(ui.get('PasswordsBackupCodesSave', 'Save codes to a file'))
        save_btn.clicked.connect(self.save_codes_to_file)
        btn_ok = QPushButton(ui.get('OK', 'OK'))
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)
        buttons.addStretch()
        buttons.addWidget(save_btn)
        buttons.addWidget(btn_ok)
        layout.addLayout(buttons)

    def save_codes_to_file(self):
        if not self.codes:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.ui.get('PasswordsBackupCodesFileTitle', 'Save backup codes'),
            'backup-codes.txt',
            "Text Files (*.txt)",
        )
        if not path:
            return
        template = self.ui.get(
            'PasswordsBackupCodesFile',
            'Those are your backup codes for accessing your {vaultName} vault, make sure those are entirely safe! {codes}',
        )
        codes_text = '\n\n' + '\n'.join(self.codes)
        content = template.format(vaultName='User', codes=codes_text)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception:
            QMessageBox.warning(
                self,
                self.ui.get('PasswordsBackupCodesSave', 'Save codes to a file'),
                self.ui.get('PasswordsBackupCodesSaveFailed', 'Could not save the file.'),
            )


class SESVWarningDialog(QDialog):
    def __init__(self, ui, sesv_result, parent=None):
        super().__init__(parent)
        self.ui = ui
        self.result = sesv_result
        self.setWindowTitle(ui.get('SESVWarningTitle', 'Warning'))
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(520)
        self.resize(560, 380)

        layout = QVBoxLayout(self)

        icon_label = QLabel()
        icon_label.setText('<span style="font-size:48px;">&#x26A0;</span>')
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        title = QLabel(ui.get('SESVWarningTitle', 'Warning'))
        title.setStyleSheet('font-size: 16px; font-weight: bold;')
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        prog_name = os.path.basename(sesv_result.program_path) if hasattr(sesv_result, 'program_path') else 'Unknown'
        prog_path = getattr(sesv_result, 'program_path', 'Unknown')
        verdict_raw = sesv_result.verdict or 'Unknown'
        verdict_key = f'SESVVerdict{verdict_raw.capitalize()}'
        verdict_text = ui.get(verdict_key, verdict_raw.lower())
        if sesv_result.reason_key:
            reason = ui.get(sesv_result.reason_key, sesv_result.block_reason or '')
            if sesv_result.reason_args:
                try:
                    reason = reason.format(**sesv_result.reason_args)
                except Exception:
                    pass
        else:
            reason = sesv_result.block_reason or ui.get('SESVPassedChecks', 'Passed all checks')

        detail = QLabel(
            ui.get('SESVWarningBody',
                   'Some program is trying to access your vault.\n\n'
                   'If this was you and it was originated from you doing something where it reaches this, click Allow.\n\n'
                   'Otherwise, if you fully do NOT know where this originated from, deny it.\n\n'
                   'Information:\n\n'
                   'Program: {prog}\n'
                   'Path: {path}\n'
                   'Verdict: {verdict}\n'
                   'Reason: {reason}').format(
                prog=prog_name,
                path=prog_path,
                verdict=verdict_text,
                reason=reason,
            )
        )
        detail.setWordWrap(True)
        detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(detail, 1)

        buttons = QHBoxLayout()
        btn_deny = QPushButton(ui.get('SESVDeny', 'Deny'))
        btn_allow = QPushButton(ui.get('SESVAllow', 'Allow'))
        btn_allow.setDefault(False)
        btn_deny.setDefault(True)
        btn_deny.clicked.connect(self.reject)
        btn_allow.clicked.connect(self.accept)
        buttons.addStretch()
        buttons.addWidget(btn_deny)
        buttons.addWidget(btn_allow)
        layout.addLayout(buttons)

        try:
            apply_wda(self)
        except Exception:
            pass


class SESVBlockedDialog(QDialog):
    def __init__(self, ui, sesv_result, parent=None):
        super().__init__(parent)
        self.ui = ui
        self.result = sesv_result
        self.setWindowTitle(ui.get('SESVBlockedTitle', 'Program blocked'))
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(420)
        self.resize(460, 260)

        layout = QVBoxLayout(self)

        icon_label = QLabel()
        icon_label.setText('<span style="font-size:48px;">&#x1F6AB;</span>')
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        title = QLabel(ui.get('SESVBlockedTitle', 'Program blocked'))
        title.setStyleSheet('font-size: 16px; font-weight: bold;')
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        body = QLabel(ui.get('SESVBlockedBody', 'The program will not take your passwords.'))
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignCenter)
        layout.addWidget(body)

        btn_ok = QPushButton(ui.get('OK', 'OK'))
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)
        layout.addWidget(btn_ok, alignment=Qt.AlignCenter)

        try:
            apply_wda(self)
        except Exception:
            pass


class SESVIntruderDialog(QDialog):
    def __init__(self, ui, vault_path, pid, filepath, parent=None, exe_path=None):
        super().__init__(parent)
        self.ui = ui
        self.vault_path = vault_path
        self.pid = pid
        self.filepath = filepath
        self.exe_path = exe_path or ''
        self.decision = "deny"
        self.setWindowTitle(ui.get('SESVWarningTitle', 'Warning'))
        self.setWindowModality(Qt.ApplicationModal)
        self.setMinimumWidth(520)
        self.resize(560, 380)

        layout = QVBoxLayout(self)

        icon_label = QLabel()
        icon_label.setText('<span style="font-size:48px;">&#x26A0;</span>')
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        title = QLabel(ui.get('SESVWarningTitle', 'Warning'))
        title.setStyleSheet('font-size: 16px; font-weight: bold;')
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        if self.exe_path:
            prog_name = 'Path of program: {} (PID: {})'.format(self.exe_path, pid)
        else:
            prog_name = 'PID {}'.format(pid)

        detail = QLabel(
            ui.get('SESVWarningBody',
                   'Some program is trying to access your vault.\n\n'
                   'If this was you and it was originated from you doing something where it reaches this, click Allow.\n\n'
                   'Otherwise, if you fully do NOT know where this originated from, deny it.\n\n'
                   'Information:\n\n'
                   'Program: {prog}\n'
                   'Path: {path}\n'
                   'Verdict: {verdict}\n'
                   'Reason: {reason}').format(
                prog=prog_name,
                path=filepath or '',
                verdict=self.ui.get('SESVVerdictAccess', 'access'),
                reason=self.ui.get('SESVExtractionBlocked', 'Vault is not running.'),
            )
        )
        detail.setWordWrap(True)
        detail.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(detail, 1)

        buttons = QHBoxLayout()
        btn_deny = QPushButton(ui.get('SESVDeny', 'Deny'))
        btn_allow = QPushButton(ui.get('SESVAllow', 'Approve'))
        btn_deny.setDefault(True)
        btn_deny.clicked.connect(self.on_deny)
        btn_allow.clicked.connect(self.on_approve)
        buttons.addStretch()
        buttons.addWidget(btn_deny)
        buttons.addWidget(btn_allow)
        layout.addLayout(buttons)

        try:
            apply_wda(self)
        except Exception:
            pass

    def on_deny(self):
        self.decision = "deny"
        self.accept()

    def on_approve(self):
        ok = False
        try:
            dlg = UnlockDialog(self.ui, self.vault_path, '', key_file='')
            dlg.setWindowTitle(self.ui.get('SESVApproveTitle', 'Approve with master password'))
            if dlg.exec() == QDialog.Accepted and dlg.key:
                ok = True
        except Exception:
            ok = False
        if ok:
            self.decision = "approve"
            self.accept()
        else:
            self.decision = "deny"
            self.accept()


def _make_intrusion_handler(app, ui, vault_path, vault_guard):
    queue = collections.deque()
    handled = set()

    def _prompt_next():
        try:
            while queue:
                pid, filepath, reason = queue.popleft()
                if pid in handled:
                    continue
                handled.add(pid)
                dlg = SESVIntruderDialog(ui, vault_path, pid, filepath)
                dlg.exec()
                if dlg.decision == "approve":
                    vault_guard.approve_pid(pid)
                else:
                    vault_guard.deny_pid(pid)
        except Exception:
            pass

    timer = QTimer()
    timer.setInterval(150)
    timer.timeout.connect(_prompt_next)
    timer.start()
    vault_guard._prompt_timer = timer

    def on_intrusion(pid, filepath, reason):
        queue.append((pid, filepath, reason))
        return "pending"

    vault_guard._prompt_timer = timer
    return on_intrusion


def run_mode(mode, data):
    ui = data.get('ui') or {}
    config_file = data.get('config_file') or ''
    vault = data.get('vault') or passwords.vault_file_path(os.path.dirname(config_file) or '')
    key_file = data.get('key_file') or ''
    status_file = data.get('status_file') or ''

    app = QApplication.instance() or QApplication(sys.argv)
    app.setWindowIcon(build_icon())

    vault_guard = None
    if os.path.exists(vault) and data.get('with_guard'):
        try:
            app_data = os.path.dirname(vault) or ''
            vault_dir = os.path.dirname(vault)
            parent_data = os.path.dirname(vault_dir)
            vault_guard = create_vault_guard(parent_data)
            vault_guard.on_intrusion = _make_intrusion_handler(app, ui, vault, vault_guard)
            vault_guard.start()
        except Exception:
            vault_guard = None

    if mode == 'pw_setup':
        dlg = SetupWizard(ui, vault, config_file, key_file=key_file)
        dlg.exec()
    elif mode == 'pw_unlock':
        requesting_prog = data.get('requesting_program', '')
        destination = data.get('destination', '')
        if requesting_prog:
            try:
                is_self = (requesting_prog == sys.executable)
                if is_self:
                    pass
                else:
                    app_data = os.path.dirname(config_file) or ''
                    sesv_interceptor = sesv.create_seid_interceptor(app_data)
                    sesv_result = sesv_interceptor.intercept(requesting_prog, destination or None)
                    if sesv_result.should_serve_honeypot():
                        blocked_dlg = SESVBlockedDialog(ui, sesv_result)
                        blocked_dlg.exec()
                        del blocked_dlg
                        del sesv_interceptor
                        del sesv_result
                        app.processEvents()
                        return
                    else:
                        warn_dlg = SESVWarningDialog(ui, sesv_result)
                        accepted = warn_dlg.exec() == QDialog.Accepted
                        del warn_dlg
                        del sesv_interceptor
                        del sesv_result
                        app.processEvents()
                        if not accepted:
                            return
            except Exception:
                pass
        dlg = UnlockDialog(ui, vault, config_file, key_file=key_file)
        dlg.exec()
    elif mode == 'pw_editor':
        key = read_key(key_file)
        if key:
            dlg = EditorDialog(ui, vault, key, config_file, status_file=status_file)
            dlg.exec()
    elif mode == 'pw_intruder':
        pid = data.get('intruder_pid')
        filepath = data.get('intruder_file', '')
        exe_path = data.get('intruder_path', '')
        if pid is not None:
            try:
                dlg = SESVIntruderDialog(ui, vault, int(pid), filepath, exe_path=exe_path)
                dlg.exec()
                decision = dlg.decision
            except Exception:
                decision = 'deny'
            if status_file:
                try:
                    with open(status_file, 'wb') as f:
                        f.write(decision.encode('utf-8'))
                except Exception:
                    pass
            else:
                try:
                    sys.stdout.buffer.write(decision.encode('utf-8'))
                    sys.stdout.buffer.flush()
                except Exception:
                    pass

    if vault_guard:
        vault_guard.stop()


def main():
    data = {}
    if len(sys.argv) > 1:
        try:
            with open(sys.argv[1], 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            pass
    mode = data.get('mode', 'pw_editor')
    run_mode(mode, data)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)