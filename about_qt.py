import sys
import base64
import datetime
import xml.etree.ElementTree as ET
import tempfile
import subprocess
import os
import webbrowser
from pathlib import Path
from urllib.request import urlopen
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QTextEdit, QProgressBar, QHBoxLayout
)
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt, QThread, Signal
from version import __version__

ICON_BASE64 = '''iVBORw0KGgoAAAANSUhEUgAAADQAAAA0CAYAAADFeBvrAAACZElEQVRoQ+2Zv4vUQBTHJ4loayWS7BsMbHMsB94fYKGl2GjjCSInKtpZ26hgYWfhHyCIWFhZWMsK2p+IhYKwwpsQbLcSDXmS494wmJ+XnYVkmQ8svO/bkJkPE2bYrCc2DE9XG4ITGjpWhBDxqRDiChEd1017qCAIbkdR9F13GlhZCBFJh/XyHADu61TDSkKI+F4IcUE31gwAtM639YImzNUhok++7//gbAsi2uM6CIKtMAy/ca7CmpDv+7tRFL3hbAtzjCzLtuI4dkIapdRZItov6qrn1xzM87y9yWTykrMt/hPaieP4M+cqSpNk5vP5sel0+pdzm9DgVyhJkpt5nr/g3CYkhLgOAK91soQ5BhFtSym/cq6iNMmjMKoV6oIT6oET0lUPRiWUJMnVPM93OQPAZa4Zc7DB73KI+EgI8Zhz27Y9+BXaOCGl1F0iuscZAHa4Zkb1yHVhVCvUBSfUAyekqx6MSmjjtm0nNHShxWJxUghRfA6I4/gn14w5mDtYO2JthbrghHrghHTVg1EJddm2lVK/iOiUbqyZ5XJ5Yjab/dGNCkqTZLoIpWl6JsuyhW6slxQAQp1qKE2S6SJUkKbpLMuyxrPBAh8A4LxODVROcsw4oaHjhIZOrZBS6hIR3eJc8+b0LddBEDwLw/AjZ8a8puoe5htaIvotpbzG3/WhSWhCRMi5ats2T/G6nw/mNTX3MI+HVwBw47DuRWkAE0T8IoTYLuqayVgVqvr+qLTeABEvEtEDKeU53TwEEQ/+UC7wff9hFEXvODPmNTVvX+8Q0Wkp5RPdXIFWobHhhIbOxgn9A+2gQlN4dCYWAAAAAElFTkSuQmCC'''

STUPID_REPO = "https://github.com/huhuhuhuheh/ehclipboard"
UPDATE_CACHE_FILE = Path.home() / ".ehclipboard_update.json"
LICENSE_TEXT = """MIT License

Copyright (c) 2025 eh

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

def get_current_version():
    return __version__

def record_update_check():
    with open(UPDATE_CACHE_FILE, "w", encoding="utf-8") as f: f.write(f'{{"last_check": "{datetime.datetime.now().isoformat()}"}}')

def should_check_update():
    if not UPDATE_CACHE_FILE.exists(): return True
    try:
        import json
        with open(UPDATE_CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            last_check = datetime.datetime.fromisoformat(data.get("last_check"))
            return (datetime.datetime.now() - last_check).days >= 1
    except Exception: return True

def fetch_update_info():
    fetcher = UpdateFetcher()
    result = {}
    
    def on_finished(data):
        nonlocal result
        result = data
    
    fetcher.finished.connect(on_finished)
    fetcher.start()
    fetcher.wait()
    return result

class UpdateFetcher(QThread):
    finished = Signal(dict)

    def run(self):
        result = {}
        try:
            with urlopen(f"https://github.com/huhuhuhuheh/ehclipboard/releases.atom") as response:
                xml_data = response.read()
            root = ET.fromstring(xml_data)
            ns = {"atom": "http://www.w3.org/2005/Atom"}
            entries = root.findall("atom:entry", ns)
            if not entries:
                result["error"] = "No releases found."
                self.finished.emit(result)
                return

            latest = entries[0]
            title = latest.find("atom:title", ns).text
            result["latest_tag"] = title.strip()
            result["release_url"] = latest.find("atom:link", ns).attrib.get("href", STUPID_REPO)
            result["body"] = (latest.find("atom:content", ns).text or "").strip()

            behind_count = 0
            current_version_clean = get_current_version().lstrip('v')
            for entry in entries:
                tag = entry.find("atom:title", ns).text.strip()
                if tag.lstrip('v') == current_version_clean:
                    break
                behind_count += 1
            result["behind"] = behind_count
        except Exception as e:
            result["error"] = str(e)
        self.finished.emit(result)

class InstallerDownloader(QThread):
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, url, ui_strings):
        super().__init__()
        self.url = url
        self.ui = ui_strings

    def format_bytes(self, size):
        if size < 1024: return f"{size} B"
        elif size < 1024 * 1024: return f"{size / 1024:.1f} KB"
        else: return f"{size / (1024 * 1024):.1f} MB"

    def format_eta(self, seconds):
        if seconds < 60: return f"{int(seconds)}s"
        else: return f"{int(seconds // 60)}m {int(seconds % 60)}s"

    def run(self):
        import urllib.request, time
        try:
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".exe")
            start_time = time.time()
            last_update_time = start_time
            def report(block_num, block_size, total_size):
                nonlocal last_update_time
                current_time = time.time()
                if current_time - last_update_time < 0.2 and block_num * block_size < total_size: return

                downloaded = min(block_num * block_size, total_size)
                percent = int(downloaded * 100 / total_size)
                self.progress.emit(percent)
                elapsed = current_time - start_time
                speed = downloaded / max(elapsed, 0.001)
                
                eta_str = "..."
                if speed > 0:
                    eta_seconds = (total_size - downloaded) / speed
                    eta_str = self.format_eta(eta_seconds)

                status_text = self.ui.get('DownloadStatus', '').format(
                    downloaded=self.format_bytes(downloaded),
                    total=self.format_bytes(total_size),
                    speed=f"{self.format_bytes(speed)}/s",
                    eta=eta_str
                )
                self.status.emit(status_text)
                last_update_time = current_time

            urllib.request.urlretrieve(self.url, temp_file.name, reporthook=report)
            self.finished.emit(temp_file.name)
        except Exception as e:
            self.failed.emit(str(e))

class AboutDialog(QDialog):
    def __init__(self, icon, ui_strings, quit_event):
        super().__init__()
        self.ui = ui_strings
        self.quit_event = quit_event
        self.setWindowTitle(self.ui.get('AboutWindowTitle', "About"))
        self.setWindowModality(Qt.ApplicationModal)
        self.setWindowIcon(icon)
        self.resize(500, 500)
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowCloseButtonHint)

        self._update_thread, self._installer_thread = None, None
        self.setup_ui(icon)
        if should_check_update(): self.start_update_check()

    def setup_ui(self, icon):
        tabs = QTabWidget()
        tabs.addTab(self.create_about_tab(icon.pixmap(48, 48)), self.ui.get('AboutTab', 'About'))
        tabs.addTab(self.create_update_tab(), self.ui.get('UpdatesTab', 'Updates'))
        tabs.addTab(self.create_license_tab(), self.ui.get('LicenseTab', 'License'))
        
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(tabs)

    def create_about_tab(self, pixmap):
        about_tab = QWidget()
        layout = QVBoxLayout(about_tab)
        label_icon = QLabel()
        label_icon.setPixmap(pixmap)
        label_icon.setAlignment(Qt.AlignCenter)
        meow = "Stupid program that alerts you whatever something has been copied to the clipboard, i mean get it?"
        label_text = QLabel(f"eh's Clipboard\nVersion: {__version__}\n\n{meow}")
        label_text.setAlignment(Qt.AlignCenter)
        label_text.setWordWrap(True)
        label_link = QLabel(f'<a href="{STUPID_REPO}">GitHub Repository</a>')
        label_link.setAlignment(Qt.AlignCenter)
        label_link.setOpenExternalLinks(True)
        layout.addWidget(label_icon); layout.addWidget(label_text); layout.addWidget(label_link)
        return about_tab

    def create_update_tab(self):
        update_tab = QWidget()
        layout = QVBoxLayout(update_tab)
        self.update_info = QLabel(self.ui.get('UpdateInitialPrompt', ''))
        self.update_info.setAlignment(Qt.AlignCenter)
        self.update_button = QPushButton(self.ui.get('CheckForUpdates', 'Check for Updates'))
        self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.hide()
        self.notes = QTextEdit(); self.notes.setReadOnly(True); self.notes.hide()
        self.btn_update_now = QPushButton(self.ui.get('UpdateNow', 'Update Now')); self.btn_update_now.hide()
        self.btn_release_notes = QPushButton(self.ui.get('ViewOnGitHub', 'View on GitHub')); self.btn_release_notes.hide()

        hbox_buttons = QHBoxLayout()
        hbox_buttons.addWidget(self.btn_update_now); hbox_buttons.addWidget(self.btn_release_notes)
        layout.addWidget(self.update_info); layout.addWidget(self.progress)
        layout.addWidget(self.update_button); layout.addWidget(self.notes); layout.addLayout(hbox_buttons)

        self.update_button.clicked.connect(self.start_update_check)
        return update_tab

    def create_license_tab(self):
        license_tab = QWidget()
        layout = QVBoxLayout(license_tab)
        license_text = QTextEdit()
        license_text.setPlainText(LICENSE_TEXT)
        license_text.setReadOnly(True)
        layout.addWidget(license_text)
        return license_tab

    def start_update_check(self):
        self.update_button.setEnabled(False)
        self.update_info.setText(self.ui.get('CheckingForUpdates', '...'))
        self.progress.show()
        self._update_thread = UpdateFetcher()
        self._update_thread.finished.connect(self.on_update_result)
        self._update_thread.start()

    def on_update_result(self, result):
        self.progress.hide()
        self.update_button.setEnabled(True); self.update_button.show()
        if "error" in result:
            self.update_info.setText(self.ui.get('UpdateFailed', '').format(error=result['error']))
            self.notes.hide(); self.btn_update_now.hide(); self.btn_release_notes.hide()
            return
        
        latest_tag = result.get("latest_tag")
        if latest_tag and latest_tag.lstrip('v') != get_current_version().lstrip('v'):
            self.show_update_available(result)
        else:
            self.update_info.setText(self.ui.get('UpdateLatest', ''))
            self.notes.hide(); self.btn_update_now.hide(); self.btn_release_notes.hide()
        record_update_check()

    def show_update_available(self, result):
        info_text = self.ui.get('UpdateNewVersion', '').format(
            latest_tag=result.get('latest_tag', 'N/A'), 
            behind=result.get('behind', 0),
            current_version=get_current_version()
        )
        self.update_info.setText(info_text)
        self.notes.setHtml(result.get('body', '')); self.notes.show()
        
        def open_release(): webbrowser.open(result.get('release_url', STUPID_REPO))
        self.btn_release_notes.clicked.connect(open_release); self.btn_release_notes.show()
        
        installer_url = f"https://github.com/huhuhuhuheh/ehclipboard/releases/download/{result.get('latest_tag')}/EhClipboardSetup.exe"
        self.btn_update_now.clicked.connect(lambda: self.start_installer_download(installer_url)); self.btn_update_now.show()

    def start_installer_download(self, url):
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint); self.show()
        self.progress.show(); self.update_button.hide(); self.notes.hide()
        self.btn_update_now.hide(); self.btn_release_notes.hide()
        self.update_info.setText(self.ui.get('DownloadPreparing', '...'))

        self._installer_thread = InstallerDownloader(url, self.ui)
        self._installer_thread.progress.connect(self.progress.setValue)
        self._installer_thread.status.connect(self.update_info.setText)
        self._installer_thread.finished.connect(self.on_installer_downloaded)
        self._installer_thread.failed.connect(self.on_installer_failed)
        self._installer_thread.start()

    def on_installer_downloaded(self, file_path):
        self.update_info.setText(self.ui.get('DownloadComplete', '...'))
        try:
            os.startfile(file_path)
            self.quit_event.set()
        except Exception as e:
            self.update_info.setText(self.ui.get('DownloadInstallerFailed', '').format(error=e))
        finally:
            self.safe_close()
    
    def on_installer_failed(self, error_msg):
        self.update_info.setText(self.ui.get('DownloadFailedGeneric', '').format(error=error_msg))
        self.setWindowFlags(self.windowFlags() | Qt.WindowCloseButtonHint); self.show()

    def safe_close(self):
        try:
            for thread in [self._update_thread, self._installer_thread]:
                if thread and thread.isRunning():
                    thread.quit()
                    thread.wait(1000)
        except Exception:
            pass
        self.close()
        QApplication.instance().quit()

    def closeEvent(self, event):
        self.safe_close()
        event.accept()
        
    def reject(self):
        self.safe_close()

def show_about_dialog(ui_strings, quit_event):
    app = QApplication.instance() or QApplication(sys.argv)
    icon_data = base64.b64decode(ICON_BASE64)
    pixmap_icon = QPixmap(); pixmap_icon.loadFromData(icon_data); icon = QIcon(pixmap_icon)
    app.setWindowIcon(icon)

    dialog = AboutDialog(icon, ui_strings, quit_event)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    app.exec()