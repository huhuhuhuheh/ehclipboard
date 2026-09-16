import sys
import base64
import datetime
import io
import json
import random
import re
import struct
import wave
import winsound
import xml.etree.ElementTree as ET
import tempfile
import subprocess
import threading
import os
import webbrowser
import traceback
import ctypes
from pathlib import Path
import urllib.request
from urllib.request import urlopen
from dotenv import load_dotenv
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QLabel, QPushButton,
    QTabWidget, QWidget, QTextEdit, QTextBrowser, QProgressBar, QHBoxLayout,
    QListWidget, QSplitter
)
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt, QThread, Signal
from version import __version__
from sounds import SND_BELL, SND_ACT_PERFORM_BETTER, SND_ERROR, SND_FLOWERY_GO_HOME, FLOWERY_VOICES, SND_KROMER_LAUGH
from licenses_data import LICENSES

WHERETHELEGAL_LICNESESAT = "licenses"
ANOTHER_LITTLE_WORLD = "flowery"
KROMER = "kromer"


FLOWERY_SPRITE = 'iVBORw0KGgoAAAANSUhEUgAAAGkAAABuCAYAAAAkhz2CAAACr0lEQVR4nO2dMW7bQBBFSUMHUJ9jpAucCzlFCktNUjuNmcJNTmS4yzHS5wSmAXcBR8CEu6L2ad8rCZKS/DzYr9nlahzkHMzBsXHtzW7K3otsgZIAKAmAkgDsLv0GriAQnB0rCYCSACgJgJIArP4W3ONA//pn+T998+H17H9XKwmAkgAoCYCSAOyuZaC/v7tdHHv8/jJcA1YSACUBUBIAJQHYtRQSosE/Ig4E5w8Jx4dPwdHns6+FsJIAKAmAkgAoCcBWUxVzpu3fOscwOCz5+et5LOimGByIKAmAkgAoqdOOQ7KT8HItIWFYG5ROrI9Ynpc6Sy6KkgAoCYCSOu04VO0uHIMBnLh2IfocJ0KHHQciSgKgJABKAtDa4siq3YBHYMCIsJIAKAmAkgAoqYOOQ2rePttxiALB9OPj4tjh2+/hEmSDSEl3IcJKAqAkAEoCoKQeOw5bLHqcgjBRm2w4+Y+QsBorCYCSACgJgJIA7FqfbigZ1Eu6FdG1434ZCO7vUrd7v3xYiZUEQEkAlARAST1OVWSfHoietMgO9NMGHYeIcf+UPrXm61pJAJQEQEkAlARgbGljp2wgGJMD+Pz3a9VroxBzYs+GqlhJAJQEQEkAlNTBVMW8dsDNMgYDffQaWbLXXmoBZoSVBEBJAJQEQEk9TlWUDMy1pyAOBesZsvez4yDvKAmAkgAoqYOOw2LQHPdPq8NEbabkmomW1lFEWEkAlARASQCU1OlTFakwkV33UJuWAkEWKwmAkgAoCYCSADS1c2T2m/9Yed1D61hJAJQEQEkAlASgqeCQZS54WqLwflv9mug/WEkAlARASQCUBOBiwaFkd8Up6EKUdBxaeoIiwkoCoCQASgKgJACb/Kx2eNK8PO3w5fPqgDFV3gOi5LO5AVSHKAmAkgAoaWifNx09p7JHPkSGAAAAAElFTkSuQmCC'
FLOWERY_W, FLOWERY_H = 105, 110


KROMER_SPAMTON = 'iVBORw0KGgoAAAANSUhEUgAAAH0AAACqCAYAAACAu0CyAAADQ0lEQVR4nO3dy23cMBRAUb7AFcRbZ2dXNlOWpoX04RqSXbx1FmlAKUAywBnq88h7z9IwPJ8LAg+URZUiSZKkLkXp01zyiJL7e1m8v2/HvBdlYnQgowMZHSjTEJJtQBu2pysdyOhARgcyOtCZg5xD20mdXOlARgcyOpDRgRzkxuelVRkdyehARgfq8tLqPOeeASMO+VoffhFXOpDRgYwOZHSgp5LcNE2lN/PKoNk43HlpVW2MDmR0IKMDdbkjd+JAtenu4A47d97soHVGBzI6kNGBztyRW0xA88/3TV9gbVCa/5X9X2P7S7/uyKmN0YGMDmR0oPSXVnsUiS6jrnGlAxkdyOhARgdykNtB7Y7cFwNf1aG+LVzpQEYHMjqQ0YH8H7lGW19G/eL9OcipjdGBjA5kdKBUg9zny+tiKnr++F2yHEny98db1e99//Pr4ddwkNMujA5kdCCjA512aXWunLwynRj3vDJUfr68nvJe7vhqPBBYRkcyOpDRgeKsAS27qLwE6/Ej6oLRgYwOZHQgH9F1hx6HtjWudCCjAxkdyOhAZ961Go/u5h1xdlsc85itWv6PnNoYHcjoQEYHSjWtrB4S3HaUR/bdtygncKUDGR3I6EBGB8p2jtxisImIh4e7s4bA7EOzKx3I6EBGBzI6ULZBbtPro0cMaFH/Grsf9FvLlQ5kdCCjAxkdKNWzVpv+2Bg3yx7ClQ5kdCCjAxkdyLtW8/FZq9qe0YGMDmR0oKdRhrZpmhY/u1wuD/+92+22+Nn1ei0jcKUDGR3I6EBGB4qRd9pqh7vb9kNbbPy9ePyI2hgdyOhARgdq3ZHbejjZdAisHcaux+y07f55a7nSgYwOZHQgowPV33K5cjfBHTtZMcIO3x2O+Lw+2UH1jA5kdCCjA60OAy1PWNjhcm32QS72/ry1l4ij8iwUVzqQ0YGMDmR0oDSH1HY83EXyJ14s3p8rHcjoQEYHMjqQgxzwO3SlAxkdyOhARgfqbgg5ebiLMgBXOpDRgYwOZHSgbI/oKpmf9hDHPJN1d650IKMDGR3I6EAjDXJVx3vEyjBGe7yXKx3I6EBGBzI60EiD3KZilO23Fa50IKMDGR3I6JIkSVLpxH9vfZfmx36WQQAAAABJRU5ErkJggg=='
KROMER_PIPIS = 'iVBORw0KGgoAAAANSUhEUgAAAFoAAABGCAYAAABMvIPiAAABZklEQVR4nO3cwW3CQBBAURNx9jl95EYTiegjFUTJIYgK6AMlTXCjj5zdQFIAc5jsrr695r8jwhi+RhqBZYZBkqQ7t5ntzMev39JDp5/rzWPj41Pu4LeX4s88vb7fvOfxdEi93kPpSfU/hoYYGmJoyHa2Jbd7Lj/H+ZpbkPvP4vcXvV4NJxpiaIihIYbuYhlGi6VmyTU2nT9SCzJ6XmtONMTQEENDDL24ZbjwxZdFLL6IEw0xNMTQEEPPugxXsvgizb8ZRq2C65JONMTQEENDDN3tNcMFGaNrhsnntf4G6URDDA0xNMTQkO29Lb6s1gvSiYYYGmJoiKEhXS7DsfHiqzrv5Tt1rBMNMTTE0BBDQ/L33K34OmJatPiS9y060RBDQwwNMXQXN92veUFeyhdfxImGGBpiaIihu/0HGuKm+xrJnzVrFl/EiYYYGmJoiKEhXf4dW5XGSy7LiYYYGmJoiKElSdKA+AO3b0mQoUA/UgAAAABJRU5ErkJggg=='
KROMER_SPAM_W, KROMER_SPAM_H = 125, 170
KROMER_PIPIS_W, KROMER_PIPIS_H = 90, 70

ICON_BASE64 = '''iVBORw0KGgoAAAANSUhEUgAAADQAAAA0CAYAAADFeBvrAAACZElEQVRoQ+2Zv4vUQBTHJ4loayWS7BsMbHMsB94fYKGl2GjjCSInKtpZ26hgYWfhHyCIWFhZWMsK2p+IhYKwwpsQbLcSDXmS494wmJ+XnYVkmQ8svO/bkJkPE2bYrCc2DE9XG4ITGjpWhBDxqRDiChEd1017qCAIbkdR9F13GlhZCBFJh/XyHADu61TDSkKI+F4IcUE31gwAtM639YImzNUhok++7//gbAsi2uM6CIKtMAy/ca7CmpDv+7tRFL3hbAtzjCzLtuI4dkIapdRZItov6qrn1xzM87y9yWTykrMt/hPaieP4M+cqSpNk5vP5sel0+pdzm9DgVyhJkpt5nr/g3CYkhLgOAK91soQ5BhFtSym/cq6iNMmjMKoV6oIT6oET0lUPRiWUJMnVPM93OQPAZa4Zc7DB73KI+EgI8Zhz27Y9+BXaOCGl1F0iuscZAHa4Zkb1yHVhVCvUBSfUAyekqx6MSmjjtm0nNHShxWJxUghRfA6I4/gn14w5mDtYO2JthbrghHrghHTVg1EJddm2lVK/iOiUbqyZ5XJ5Yjab/dGNCkqTZLoIpWl6JsuyhW6slxQAQp1qKE2S6SJUkKbpLMuyxrPBAh8A4LxODVROcsw4oaHjhIZOrZBS6hIR3eJc8+b0LddBEDwLw/AjZ8a8puoe5htaIvotpbzG3/WhSWhCRMi5ats2T/G6nw/mNTX3MI+HVwBw47DuRWkAE0T8IoTYLuqayVgVqvr+qLTeABEvEtEDKeU53TwEEQ/+UC7wff9hFEXvODPmNTVvX+8Q0Wkp5RPdXIFWobHhhIbOxgn9A+2gQlN4dCYWAAAAAElFTkSuQmCC'''

STUPID_REPO = "https://github.com/huhuhuhuheh/ehclipboard"
UPDATE_CACHE_FILE = Path.home() / ".ehclipboard_update.json"

def load_env():
    candidates = [
        Path(sys.executable).resolve().parent / ".env",
        Path(__file__).resolve().parent / ".env",
        Path.cwd() / ".env",
    ]
    for candidate in candidates:
        if candidate.exists():
            load_dotenv(candidate)
            return

load_env()

def get_update_server_url():
    return os.environ.get("UPDATE_SERVER_URL", "").strip()

def is_msix_package():
    try:
        length = ctypes.c_uint32(0)
        result = ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), None)
        return result != 15700
    except Exception:
        return False

def cache_icon():
    pass

def get_cached_or_fallback_icon():
    return ICON_BASE64
LICENSE_TEXT = """MIT License

Copyright (c) 2026 eh

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


def _scale_wav_pcm(data, volume):
    """Scale a 16-bit PCM wav's samples by volume (0.0-1.0), return full wav bytes."""
    reader = io.BytesIO(data)
    with wave.open(reader, 'rb') as w:
        channels = w.getnchannels()
        sampwidth = w.getsampwidth()
        framerate = w.getframerate()
        frames = w.readframes(w.getnframes())
    fmt = '<' + ('h' * (len(frames) // 2))
    vals = struct.unpack(fmt, frames)
    scaled = struct.pack(fmt, *(max(-32768, min(32767, int(v * volume))) for v in vals))
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(framerate)
        w.writeframes(scaled)
    return out.getvalue()


def _prep_sfx_file(b64, volume=1.0):
    """Decode+scale an embedded wav into a temp file path."""
    data = base64.b64decode(b64)
    if volume < 0.999:
        data = _scale_wav_pcm(data, max(0.0, min(1.0, volume)))
    tmp = os.path.join(tempfile.gettempdir(), "EhClipboardAudioSfx.wav")
    with open(tmp, 'wb') as f:
        f.write(data)
    return tmp


def play_wav_detached(b64, volume=1.0):
    """Play a wav in a separate process so it survives this app quitting
    (used for the close-out voiceclip)."""
    try:
        tmp = _prep_sfx_file(b64, volume)
        if getattr(sys, "frozen", False):
            cmd = [sys.executable, "playsound", tmp]
        else:
            cmd = [sys.executable, "-c",
                   "import winsound,sys;winsound.PlaySound(sys.argv[1], winsound.SND_FILENAME | winsound.SND_NODEFAULT)",
                   tmp]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen(
            cmd,
            creationflags=flags,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            close_fds=True,
        )
    except Exception:
        pass


def play_wav_volume(b64, volume=1.0):
    """Play an embedded wav (base64) asynchronously from a temp file."""
    try:
        tmp = _prep_sfx_file(b64, volume)
        winsound.PlaySound(tmp, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except Exception:
        pass

def record_update_check():
    import json
    data = {"last_check": datetime.datetime.now().isoformat()}
    with open(UPDATE_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f)

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

    def user_agent(self):
        return f"EhClipboard ({get_current_version()})"

    @staticmethod
    def _validate_version(version):
        version = (version or "").strip()
        if not version:
            return "The version cannot be empty!"
        cleaned = version.lstrip('v')
        if not cleaned:
            return "The version cannot be empty!"
        bad = re.search(r"[^0-9.]+", cleaned)
        if bad:
            return f"You sure you wanna add {bad.group(0)}?"
        bad = re.search(r"(?:^\.)|(?:\.$)|(?:\.\.)", cleaned)
        if bad:
            return f"You sure you wanna add {bad.group(0)}?"
        return None

    @staticmethod
    def _parse_version(version):
        parts = []
        for part in (version or "").lstrip('v').split('.'):
            try:
                parts.append(int(part))
            except ValueError:
                parts.append(0)
        return tuple(parts)

    @staticmethod
    def _version_diff(current, latest):
        cur = UpdateFetcher._parse_version(current)
        lat = UpdateFetcher._parse_version(latest)
        if lat <= cur:
            return 0
        n = max(len(cur), len(lat))
        cur = cur + (0,) * (n - len(cur))
        lat = lat + (0,) * (n - len(lat))
        diff = 0
        weight = 10 ** (n - 1)
        for c, l in zip(cur, lat):
            diff += (l - c) * weight
            weight //= 10
        return max(0, diff)

    def fetch_from_server(self):
        server_url = get_update_server_url()
        if not server_url:
            return None
        try:
            req = urllib.request.Request(server_url, headers={"User-Agent": self.user_agent()})
            with urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception:
            return None

        latest_tag = (data.get("version") or "").strip()
        if not latest_tag:
            return None

        result = {}
        result["latest_tag"] = latest_tag
        result["body"] = (data.get("release_notes") or "").strip()
        tag = latest_tag if latest_tag.startswith('v') else f"v{latest_tag}"
        result["release_url"] = f"{STUPID_REPO}/releases/tag/{tag}"
        result["behind"] = self._version_diff(get_current_version(), latest_tag)
        result["expected_hash"] = ""

        assets = data.get("assets") or []
        installer_asset = next((a for a in assets if a.get("os") == "windows_x64"), assets[0] if assets else None)
        if installer_asset:
            url = (installer_asset.get("url") or "").strip()
            if url:
                result["installer_url"] = url
            result["expected_hash"] = (installer_asset.get("hash") or "").strip().lower()
        result["source"] = "server"
        return result

    def fetch_from_github(self):
        result = {}
        try:
            with urlopen("https://github.com/huhuhuhuheh/ehclipboard/releases.atom", timeout=10) as response:
                xml_data = response.read()
        except Exception as e:
            result["error"] = f"Network error: {str(e)}"
            return result

        try:
            root = ET.fromstring(xml_data)
        except Exception as e:
            result["error"] = f"Failed to parse releases: {str(e)}"
            return result

        ns = {"atom": "http://www.w3.org/2005/Atom"}
        entries = root.findall("atom:entry", ns)
        if not entries:
            result["error"] = "No releases found."
            return result

        latest = entries[0]
        title = latest.find("atom:title", ns)
        if title is None:
            result["error"] = "Invalid release format."
            return result

        result["latest_tag"] = title.text.strip()
        link = latest.find("atom:link", ns)
        result["release_url"] = link.attrib.get("href", STUPID_REPO) if link is not None else STUPID_REPO
        content = latest.find("atom:content", ns)
        result["body"] = (content.text or "").strip() if content is not None else ""

        behind_count = 0
        current_version_clean = get_current_version().lstrip('v')
        for entry in entries:
            tag_elem = entry.find("atom:title", ns)
            if tag_elem is None:
                continue
            tag = tag_elem.text.strip()
            if tag.lstrip('v') == current_version_clean:
                break
            behind_count += 1
        result["behind"] = behind_count
        result["source"] = "github"
        return result

    def run(self):
        try:
            current_error = self._validate_version(get_current_version())
            if current_error:
                result = {"error": current_error}
            else:
                result = self.fetch_from_server()
                if result is None:
                    result = self.fetch_from_github()
                if "error" not in result:
                    latest_tag = result.get("latest_tag", "")
                    latest_error = self._validate_version(latest_tag)
                    if latest_error:
                        result = {"error": latest_error}
                    elif latest_tag and self._parse_version(get_current_version()) > self._parse_version(latest_tag):
                        result = {"error": "This is too far in the future!"}
        except Exception as e:
            result = {"error": f"Unexpected error: {str(e)}"}
        self.finished.emit(result)

class InstallerDownloader(QThread):
    progress = Signal(int)
    status = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, url, ui_strings, expected_hash=""):
        super().__init__()
        self.url = url
        self.ui = ui_strings
        self.expected_hash = (expected_hash or "").strip().lower()

    def format_bytes(self, size):
        if size < 1024: return f"{size} B"
        elif size < 1024 * 1024: return f"{size / 1024:.1f} KB"
        else: return f"{size / (1024 * 1024):.1f} MB"

    def format_eta(self, seconds):
        if seconds < 60: return f"{int(seconds)}s"
        else: return f"{int(seconds // 60)}m {int(seconds % 60)}s"

    def run(self):
        import urllib.request, time, hashlib
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

            if self.expected_hash:
                sha256 = hashlib.sha256()
                with open(temp_file.name, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        sha256.update(chunk)
                actual_hash = sha256.hexdigest()
                if actual_hash != self.expected_hash:
                    try:
                        os.remove(temp_file.name)
                    except Exception:
                        pass
                    self.failed.emit(f"Hash mismatch: expected {self.expected_hash}, got {actual_hash}")
                    return

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
        self._egg_typed = ""
        self._licenses_revealed = False
        self._sprouted = False
        self._kromered = False
        self._egg_mode = None
        self._sprout_label = None
        self.setup_ui(icon)
        if should_check_update(): self.start_update_check()

    def setup_ui(self, icon):
        tabs = QTabWidget()
        self._tabs = tabs
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
        label_icon.setCursor(Qt.ArrowCursor)
        label_icon.mousePressEvent = self._on_logo_clicked
        self._sprout_label = label_icon
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
        
        if is_msix_package():
            self.update_info = QLabel(self.ui.get('UpdateMSStoreMessage', 'Updates are automatically managed by the Microsoft Store'))
            self.update_info.setAlignment(Qt.AlignCenter)
            self.btn_store = QPushButton(self.ui.get('UpdateMSStoreButton', 'Open Store Updates'))
            self.btn_store.clicked.connect(lambda: webbrowser.open('ms-windows-store://pdp/?productid=9MWGR59WHT00'))
            layout.addStretch()
            layout.addWidget(self.update_info)
            layout.addWidget(self.btn_store)
            layout.addStretch()
            self.update_button = None
            self.progress = None
            self.notes = None
            self.btn_update_now = None
            self.btn_release_notes = None
        else:
            self.update_info = QLabel(self.ui.get('UpdateInitialPrompt', ''))
            self.update_info.setAlignment(Qt.AlignCenter)
            self.update_button = QPushButton(self.ui.get('CheckForUpdates', 'Check for Updates'))
            self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.hide()
            self.notes = QTextBrowser(); self.notes.setOpenExternalLinks(True); self.notes.hide()
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

    def _reveal_licenses(self):
        if self._licenses_revealed:
            return
        self._licenses_revealed = True
        try:
            self._lic_win = LicensesWindow(self.ui, self)
            self._lic_win.setAttribute(Qt.WA_DeleteOnClose)
            self._lic_win.destroyed.connect(self._on_licenses_closed)
            self._lic_win.show()
            self._lic_win.raise_()
            self._lic_win.activateWindow()
        except Exception:
            self._licenses_revealed = False

    def _on_licenses_closed(self, *args):
        self._licenses_revealed = False

    def _on_logo_clicked(self, event):
        try:
            if self._egg_mode == "flowery":
                self._sprout_voice()
                event.accept()
                return
            if self._egg_mode == "kromer":
                self._kromer_voice()
                event.accept()
                return
        except Exception:
            pass
        event.accept()

    def _set_logo_pixmap(self, b64):
        try:
            raw = base64.b64decode(b64)
            pm = QPixmap()
            if pm.loadFromData(raw, "PNG") and self._sprout_label is not None:
                self._sprout_label.setPixmap(pm)
                self._sprout_label.setCursor(Qt.PointingHandCursor)
                return True
        except Exception:
            pass
        return False

    def _sprout_voice(self):
        try:
            if FLOWERY_VOICES:
                _, clip = random.choice(FLOWERY_VOICES)
                play_wav_volume(clip, 0.6)
        except Exception:
            pass

    def _kromer_voice(self):
        try:
            play_wav_volume(SND_KROMER_LAUGH, 0.6)
        except Exception:
            pass

    def _sprout_now(self):
        self._sprouted = True
        self._egg_mode = "flowery"
        self._set_logo_pixmap(FLOWERY_SPRITE)
        play_wav_volume(SND_ACT_PERFORM_BETTER, 0.7)
        self._sprout_voice()

    def _kromer_now(self):
        self._kromered = True
        self._egg_mode = "kromer"
        if random.random() < 0.66:
            self._set_logo_pixmap(KROMER_SPAMTON)
        else:
            self._set_logo_pixmap(KROMER_PIPIS)
        play_wav_volume(SND_KROMER_LAUGH, 0.6)

    def keyPressEvent(self, event):
        text = event.text()
        if text and text.isprintable() and not event.modifiers():
            ch = text.lower()
            if self._tabs.currentIndex() == 0:
                self._spell_keypress(ch)
        super().keyPressEvent(event)

    def _spell_keypress(self, ch):
        flowery = ANOTHER_LITTLE_WORLD
        kromer = KROMER
        licenses = WHERETHELEGAL_LICNESESAT

        candidate = self._egg_typed + ch

        if not self._sprouted and candidate == flowery[:len(candidate)]:
            self._egg_typed = candidate
            if len(candidate) == len(flowery):
                self._sprout_now()
                self._egg_typed = ""
            else:
                play_wav_volume(SND_BELL, 0.04 + 0.5 * (len(candidate) / len(flowery)))
            return

        if not self._kromered and candidate == kromer[:len(candidate)]:
            self._egg_typed = candidate
            if len(candidate) == len(kromer):
                self._kromer_now()
                self._egg_typed = ""
            else:
                play_wav_volume(SND_BELL, 0.04 + 0.5 * (len(candidate) / len(kromer)))
            return

        if candidate == licenses[:len(candidate)]:
            self._egg_typed = candidate
            if len(candidate) == len(licenses):
                play_wav_volume(SND_ACT_PERFORM_BETTER, 0.7)
                self._reveal_licenses()
                self._egg_typed = ""
            else:
                play_wav_volume(SND_BELL, 0.04 + 0.5 * (len(candidate) / len(licenses)))
            return

        if self._egg_typed:
            play_wav_volume(SND_ERROR, 0.5)
            self._egg_typed = ""

    def start_update_check(self):
        try:
            if self.update_button is not None:
                self.update_button.setEnabled(False)
                self.update_info.setText(self.ui.get('CheckingForUpdates', '...'))
                self.progress.show()
                self._update_thread = UpdateFetcher()
                self._update_thread.finished.connect(self.on_update_result)
                self._update_thread.start()
        except Exception as e:
            if self.update_button is not None:
                self.update_button.setEnabled(True)
                self.progress.hide()
                self.update_info.setText(self.ui.get('UpdateFailed', 'Update check failed: {error}').format(error=str(e)))

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
        body = result.get('body', '')
        if result.get('source') == 'server':
            self.notes.setMarkdown(body)
        else:
            self.notes.setHtml(body)
        self.notes.show()
        
        def open_release(): webbrowser.open(result.get('release_url', STUPID_REPO))
        self.btn_release_notes.clicked.connect(open_release); self.btn_release_notes.show()
        
        installer_url = result.get("installer_url") or f"https://github.com/huhuhuhuheh/ehclipboard/releases/download/{result.get('latest_tag')}/EhClipboardSetup.exe"
        self.btn_update_now.clicked.connect(lambda: self.start_installer_download(installer_url, result.get("expected_hash", ""))); self.btn_update_now.show()

    def start_installer_download(self, url, expected_hash=""):
        try:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint); self.show()
            self.progress.show(); self.update_button.hide(); self.notes.hide()
            self.btn_update_now.hide(); self.btn_release_notes.hide()
            self.update_info.setText(self.ui.get('DownloadPreparing', '...'))

            self._installer_thread = InstallerDownloader(url, self.ui, expected_hash)
            self._installer_thread.progress.connect(self.progress.setValue)
            self._installer_thread.status.connect(self.update_info.setText)
            self._installer_thread.finished.connect(self.on_installer_downloaded)
            self._installer_thread.failed.connect(self.on_installer_failed)
            self._installer_thread.start()
        except Exception as e:
            self.update_info.setText(self.ui.get('DownloadFailedGeneric', 'Download failed: {error}').format(error=str(e)))
            self.setWindowFlags(self.windowFlags() | Qt.WindowCloseButtonHint); self.show()

    def on_installer_downloaded(self, file_path):
        self.update_info.setText(self.ui.get('DownloadComplete', '...'))
        try:
            os.startfile(file_path)
        except Exception as e:
            self.update_info.setText(self.ui.get('DownloadInstallerFailed', '').format(error=e))
        finally:
            self.quit_event.set()
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
        if getattr(self, '_sprouted', False) and not getattr(self, '_go_home_played', False):
            self._go_home_played = True
            try:
                play_wav_detached(SND_FLOWERY_GO_HOME, 0.6)
            except Exception:
                pass
        self.safe_close()
        event.accept()
        
    def reject(self):
        self.safe_close()


class LicensesWindow(QDialog):
    """the package licenses that for some reason are hidden, you dont know where, but do you?"""

    def __init__(self, ui_strings, parent=None):
        super().__init__(parent)
        self.ui = ui_strings
        self.setWindowTitle(ui_strings.get('LicensesWindowTitle', 'Third-Party Licenses'))
        self.resize(900, 640)
        self.setMinimumSize(640, 480)

        layout = QVBoxLayout(self)
        header = QLabel(ui_strings.get('LicensesHeader', "Third-party open source licenses used by eh's Clipboard"))
        header.setWordWrap(True)
        layout.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)
        self._lic_list = QListWidget()
        self._lic_browser = QTextBrowser()
        self._lic_browser.setOpenExternalLinks(True)
        splitter.addWidget(self._lic_list)
        splitter.addWidget(self._lic_browser)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter, 1)

        self._lic_list.currentRowChanged.connect(self._show_license_at)
        names = sorted(LICENSES.keys())
        for name in names:
            self._lic_list.addItem(name)
        self._deltarune_row = len(names)
        self._lic_list.addItem(ui_strings.get('DeltaruneLicenseTitle', "Deltarune Sounds"))
        if names:
            self._lic_list.setCurrentRow(0)

    def _show_license_at(self, row):
        names = sorted(LICENSES.keys())
        if row < 0 or row >= len(names) + 1:
            return
        if row == self._deltarune_row:
            body = self.ui.get('DeltaruneLicenseBody', "The Deltarune sounds, including Flowery's Voices and its sprite, and Spamton's sprites, included in Eh's Clipboard (\"Official Builds by the source\"), custom copies or forks of this program (\"Forks\"), or custom-built programs made for a machine or to add something (\"Private Builds\"), are part of DELTARUNE, which is owned by Toby Fox.")
            header = f"<b>{self.ui.get('DeltaruneLicenseTitle', 'Deltarune Sounds')}</b><br><i>{self.ui.get('DeltaruneCopyright', 'Copyright (c) Toby Fox')}</i><hr>"
            self._lic_browser.setHtml(header + "<p style='white-space:pre-wrap'>" + body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + "</p>")
            return
        entry = LICENSES[names[row]]
        body = entry.get("license_text", "") or ""
        lic = entry.get("license", "")
        ver = entry.get("version", "")
        deps = entry.get("deps") or []
        used_by = entry.get("used_by") or []
        header = f"<b>{names[row]}</b> {ver}<br><i>{lic}</i>"
        if used_by:
            header += "<br><i>Used by:</i> " + ", ".join(used_by)
        if deps:
            header += "<br><i>Depends on:</i> " + ", ".join(deps)
        header += "<hr>"
        self._lic_browser.setHtml(header + "<pre style='white-space:pre-wrap'>" + body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") + "</pre>")


def show_about_dialog(ui_strings, quit_event):
    try:
        app = QApplication.instance() or QApplication(sys.argv)
        icon_b64 = get_cached_or_fallback_icon()
        icon_data = base64.b64decode(icon_b64)
        pixmap_icon = QPixmap()
        if not pixmap_icon.loadFromData(icon_data):
            raise ValueError("Failed to load icon from base64 data")
        icon = QIcon(pixmap_icon)
        cache_icon()
        app.setWindowIcon(icon)

        dialog = AboutDialog(icon, ui_strings, quit_event)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        app.exec()
    except Exception as e:
        print(f"ERROR in show_about_dialog: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

if __name__ == '__main__':
    try:
        import threading
        ui_dict = {}
        quit_event = threading.Event()
        
        if len(sys.argv) > 1:
            json_file = sys.argv[1]
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    ui_dict = json.load(f)
            except Exception as e:
                print(f"Warning: Could not load UI strings from {json_file}: {e}", file=sys.stderr)
        
        show_about_dialog(ui_dict, quit_event)
    except Exception as e:
        print(f"FATAL ERROR in about_qt.py main: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)