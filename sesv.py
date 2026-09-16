import os
import sys
import json
import time
import uuid
import struct
import hashlib
import secrets
import base64
import ctypes
import tempfile
import subprocess
import re
from ctypes import wintypes
from urllib.parse import urlparse
from collections import defaultdict

import pefile
import psutil
import win32api
import win32con
import win32process
import win32security
import win32file
import pywintypes
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

SEID_VERSION = 1
MACHINE_UUID_PATH = "machine_uuid.bin"
PROGRAM_LOG_PATH = "seid_programs.json"
SUSPICIOUS_LOG_PATH = "seid_suspicious.json"
KNOWN_PROGRAMS_PATH = "seid_known.json"
NETWORK_LOG_PATH = "seid_network.json"

SKETCHY_TIMELINE_WINDOW = 300

_SKETCHY_TLD_BLOB = "fSQqJzAmJTE1LTwlcTUlOHEjITNtKjw5L3o9H1Ujdi09MS85dz1HSkhKfSYoKSN9KCQgP2Y6PChiJzk+YiwlLzBnMDg2FVojdiw+Kik5dzxcTBxVPDlnJy06KC4xNzR3PC0jMSNsKC43LjBnNzsoGF0wOSsucS49ODJCXFdKfSMoLSs7N2syKjwlcTIhOHEkOSE/ZSowOihxEVAjdigzLS8gNyMcV1ZYL2suIyN9LDQobS8qI3okITMyMGErJCEsIChxHl4sLDN8Nnk1JXFbU0dKfSwtOHE6Jjl6KiY/MChiLTEpMGEqJTooPz07Ch82NzN8Njk5dzRCTBxaMjlnKD4nN2s4Ki48I3ogLTEpMGEvJC0nL3oyE01xNSo8I2UoNSMcXV1bL2skKzEgPyAmP2Y0MCIwajIxMGEtLjs1fToqCh8wNioucSQrMDBcTBxZPSkgKjovZTU1JC0lcSQtNis7MGEzIzBnIz08BU1xKD09I2U1LiMcQlNVOisuOHEhLjYgP2YrOiIlISg+Yj02N2I6MScjWEI8MSo8PC45dyxaTBxFOyo5OHEgIjExP2YqMChiNy8jLyo/ZT89PCY6Ch8sLD03PiY5dyxHTBxFJjcvOHEgMjl6Ny06NyhiMDoxODNtPyc1fSAwCh8rNyQrMDdrLTBCTBxCISQtISN9PzMobT4+I3o6LS8+YjktN2I/JihxAVQ9Oy4/I2UyPD1BWUZTL2s+LTEvZTI7MSMlcSM/OHE6JSE/ZTQwKShxDFgv"

def _decode_sketchy_tlds():
    key = b"SEID_SKETCHY_TLD_BLOCKLIST_v1_XOR_KEY_2026"
    raw = base64.b64decode(_SKETCHY_TLD_BLOB)
    xored = bytes([b ^ key[i % len(key)] for i, b in enumerate(raw)])
    return set(xored.decode().split("|"))

SKETCHY_TLDS = _decode_sketchy_tlds()

DEFAULT_METADATA_FINGERPRINTS = {
    "pyinstaller": {
        "descriptions": ["", "Created with PyInstaller", "Python Application"],
        "companies": ["", "Python"],
        "original_filenames": ["main.exe", "app.exe", "dist.exe"],
    },
    "electron": {
        "descriptions": ["", "Electron Application", "Electron App"],
        "companies": ["", "Electron"],
        "original_filenames": ["electron.exe", "app.exe"],
    },
    "nodejs_pkg": {
        "descriptions": ["", "Node.js Application"],
        "companies": ["", "Node.js"],
        "original_filenames": ["node.exe", "app.exe"],
    },
    "go_bundler": {
        "descriptions": ["", "Go Application"],
        "companies": [""],
        "original_filenames": ["main.exe"],
    },
}

SUSPICIOUS_LOCATIONS = [
    tempfile.gettempdir().lower(),
    os.path.join(os.environ.get("APPDATA", ""), "..", "Local", "Temp").lower(),
    os.path.join(os.environ.get("USERPROFILE", ""), "Downloads").lower(),
    os.path.join(os.environ.get("USERPROFILE", ""), "Desktop").lower(),
    "c:\\programdata",
]

KNOWN_TRUSTED_PUBLISHERS = [
    "microsoft corporation", "google llc", "google inc",
    "mozilla corporation", "mozilla foundation", "apple inc",
    "adobe inc", "adobe systems", "valve corporation",
    "electronic arts inc", "nvidia corporation", "intel corporation",
    "amd", "advanced micro devices", "oracle corporation",
    "java", "python software foundation",
]


class MachineIdentity:
    def __init__(self, app_data_path):
        self.app_data_path = app_data_path
        self.uuid_path = os.path.join(app_data_path, MACHINE_UUID_PATH)

    def _collect_hardware_seeds(self):
        seeds = []
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            machine_guid = winreg.QueryValueEx(key, "MachineGuid")[0]
            winreg.CloseKey(key)
            seeds.append(f"machine_guid:{machine_guid}")
        except Exception:
            pass
        try:
            cpu_info = psutil.cpu_info()
            if cpu_info:
                cores = psutil.cpu_count(logical=False) or 0
                brand = cpu_info[0].brand_raw if cpu_info else "unknown"
                seeds.append(f"cpu:{cores}:{brand}")
        except Exception:
            pass
        try:
            partitions = psutil.disk_partitions(all=False)
            for p in partitions:
                try:
                    usage = psutil.disk_usage(p.mountpoint)
                    if usage.total > 0:
                        seeds.append(f"disk:{p.device}:{usage.total}")
                        break
                except Exception:
                    continue
        except Exception:
            pass
        try:
            mac = psutil.net_if_addrs()
            for iface, addrs in mac.items():
                for addr in addrs:
                    if addr.family == psutil.AF_LINK and addr.address:
                        mac_str = addr.address.replace(":", "")
                        if mac_str not in ("000000000000", "FFFFFFFFFFFF"):
                            seeds.append(f"mac:{addr.address}")
                            break
                if len(seeds) > 2:
                    break
        except Exception:
            pass
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion")
            product_id = winreg.QueryValueEx(key, "ProductId")[0]
            winreg.CloseKey(key)
            seeds.append(f"product:{product_id}")
        except Exception:
            pass
        return seeds

    def _seed_to_uuid(self, seeds):
        combined = "|".join(sorted(seeds)).encode("utf-8")
        digest = hashlib.sha512(combined).digest()
        b = bytearray(digest[:16])
        b[6] = (b[6] & 0x0F) | 0x40
        b[8] = (b[8] & 0x3F) | 0x80
        return str(uuid.UUID(bytes=bytes(b)))

    def get_machine_uuid(self):
        if os.path.exists(self.uuid_path):
            try:
                with open(self.uuid_path, "rb") as f:
                    return f.read().decode("utf-8")
            except Exception:
                pass
        seeds = self._collect_hardware_seeds()
        if not seeds:
            machine_uuid = str(uuid.uuid4())
        else:
            machine_uuid = self._seed_to_uuid(seeds)
        os.makedirs(os.path.dirname(self.uuid_path), exist_ok=True)
        with open(self.uuid_path, "w", encoding="utf-8") as f:
            f.write(machine_uuid)
        return machine_uuid


class CertVerifier:
    def __init__(self):
        self._wintrust = ctypes.WinDLL("wintrust")

    def _verify_authenticode(self, exe_path):
        try:
            from signify.authenticode import AuthenticodeFile
            from signify.authenticode import AuthenticodeVerificationResult as R
            with open(exe_path, "rb") as f:
                status, err = AuthenticodeFile.from_stream(f).explain_verify()
            if status == R.OK:
                return 0
            if status == R.NOT_SIGNED:
                return -1
            return -2
        except Exception:
            return -2

    def get_embedded_cert_info(self, exe_path):
        if not os.path.exists(exe_path):
            return None
        info = {}
        try:
            info_raw = win32api.GetFileVersionInfo(exe_path, "\\")
            ms = info_raw["FileVersionMS"]
            ls = info_raw["FileVersionLS"]
            info["file_version"] = f"{win32api.HIWORD(ms)}.{win32api.LOWORD(ms)}.{win32api.HIWORD(ls)}.{win32api.LOWORD(ls)}"
        except Exception:
            pass
        try:
            lang, codepage = win32api.GetFileVersionInfo(exe_path, "\\VarFileInfo\\Translation")[0]
            for prop_name in ["CompanyName", "FileDescription", "FileVersion", "InternalName", "LegalCopyright", "OriginalFilename", "ProductName", "ProductVersion"]:
                try:
                    block = f"\\StringFileInfo\\{lang:04X}{codepage:04X}\\{prop_name}"
                    val = win32api.GetFileVersionInfo(exe_path, block)
                    if val:
                        info[prop_name] = val.strip()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            status = self._verify_authenticode(exe_path)
            info["sig_status"] = status
            info["sig_valid"] = (status == 0)
        except Exception:
            pass
        return info if info else None

    def validate_cert_trust(self, exe_path):
        if not os.path.exists(exe_path):
            return False, None, "file not found"
        cert_info = self.get_embedded_cert_info(exe_path)
        if not cert_info:
            return False, None, "no information available"

        sig_status = cert_info.get("sig_status", -1)
        company = cert_info.get("CompanyName", "").lower()
        path_lower = exe_path.lower()

        is_system_path = (
            path_lower.startswith(r"c:\windows\system32") or
            path_lower.startswith(r"c:\windows\syswow64") or
            path_lower.startswith(r"c:\program files") or
            path_lower.startswith(r"c:\program files (x86)")
        )

        if sig_status == 0:
            issuer = cert_info.get("issuer", "").lower()
            subject = cert_info.get("subject", "").lower()
            for publisher in KNOWN_TRUSTED_PUBLISHERS:
                if publisher in issuer or publisher in subject or publisher in company:
                    return True, cert_info, f"trusted publisher: {cert_info.get('CompanyName', 'unknown')}"
            known_cas = [
                "digicert", "lets encrypt", "sectigo", "comodo",
                "globalsign", "entrust", "godaddy", "thawte",
                "verisign", "symantec", "cisco", "amazon",
            ]
            for ca in known_cas:
                if ca in issuer or ca in company:
                    return True, cert_info, f"known CA: {cert_info.get('CompanyName', 'unknown')}"
            if company:
                return True, cert_info, f"valid signature: {cert_info.get('CompanyName', 'unknown')}"
            return True, cert_info, "valid signature"
        elif sig_status in (-1, -2):
            if company and is_system_path:
                return True, cert_info, f"catalog-signed system file from trusted path: {cert_info.get('CompanyName', 'unknown')}"
            if not company:
                return False, cert_info, "no embedded certificate and no company metadata"
            for publisher in KNOWN_TRUSTED_PUBLISHERS:
                if publisher in company:
                    return True, cert_info, f"trusted publisher metadata: {cert_info.get('CompanyName', 'unknown')}"
            return False, cert_info, f"no valid signature, company metadata: {cert_info.get('CompanyName', 'unknown')}"
        elif sig_status >= 1 and sig_status <= 10:
            reasons = {
                1: "hash mismatch (signature corrupted)",
                2: "private key not found",
                3: "bad digest",
                4: "bad purpose",
                5: "expired certificate",
                6: "not valid for this purpose",
                7: "untrusted root",
                8: "bad encoding",
                9: "basic constraints error",
                10: "trust not established",
            }
            return False, cert_info, reasons.get(sig_status, f"signature error {sig_status}")
        else:
            return False, cert_info, f"unknown signature status: {sig_status}"

    def check_cert_origin(self, cert_info):
        if not cert_info:
            return "none", "no certificate"
        issuer = cert_info.get("issuer", "").lower()
        subject = cert_info.get("subject", "").lower()
        for publisher in KNOWN_TRUSTED_PUBLISHERS:
            if publisher in issuer or publisher in subject:
                return "trusted_publisher", f"published by {cert_info.get('issuer', 'unknown')}"
        if issuer and subject and issuer == subject:
            return "self_signed", "certificate is self-signed"
        known_cas = [
            "digicert", "lets encrypt", "sectigo", "comodo",
            "globalsign", "entrust", "godaddy", "thawte",
            "verisign", "symantec", "cisco", "amazon",
        ]
        for ca in known_cas:
            if ca in issuer.lower():
                return "known_ca", f"issued by {cert_info.get('issuer', 'unknown')}"
        return "unknown_issuer", f"issuer: {cert_info.get('issuer', 'unknown')}"


class MetadataFingerprint:
    def __init__(self):
        pass

    def get_pe_metadata(self, exe_path):
        if not os.path.exists(exe_path):
            return None
        try:
            pe = pefile.PE(exe_path, fast_load=True)
            metadata = {}
            if hasattr(pe, "VS_FIXEDFILEINFO"):
                metadata["file_version"] = f"{pe.BIN_FILE_VERSION}"
                metadata["product_version"] = f"{pe.BIN_PRODUCT_VERSION}"
            if hasattr(pe, "VS_INFO"):
                pe_info = pe.VS_INFO
                if hasattr(pe_info, "StringTable"):
                    for st in pe_info.StringTable:
                        for entry in st.entries:
                            key = entry.Key.decode("utf-8", errors="replace")
                            val = entry.Value.decode("utf-8", errors="replace")
                            metadata[key] = val
            pe.close()
            return metadata if metadata else None
        except pefile.PEFormatError:
            return None
        except Exception:
            return None

    def fingerprint_match(self, metadata):
        if not metadata:
            return False, None, []
        matched_bundlers = []
        for bundler, patterns in DEFAULT_METADATA_FINGERPRINTS.items():
            matched_fields = []
            desc = (metadata.get("FileDescription") or "").strip()
            if desc in patterns.get("descriptions", []):
                matched_fields.append("description")
            company = (metadata.get("CompanyName") or "").strip()
            if company in patterns.get("companies", []):
                matched_fields.append("company")
            orig_name = (metadata.get("OriginalFilename") or "").strip()
            if orig_name in patterns.get("original_filenames", []):
                matched_fields.append("original_filename")
            product = (metadata.get("ProductName") or "").strip()
            if not product or product in ["", "Python Application", "Electron App", "Node.js Application"]:
                matched_fields.append("empty_product")
            if len(matched_fields) >= 2:
                matched_bundlers.append((bundler, matched_fields))
        if matched_bundlers:
            best = max(matched_bundlers, key=lambda x: len(x[1]))
            return True, best[0], best[1]
        return False, None, []


class TimelineTracker:
    def __init__(self, app_data_path):
        self.app_data_path = app_data_path
        self.log_path = os.path.join(app_data_path, PROGRAM_LOG_PATH)
        self.programs = self._load()

    def _load(self):
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save(self):
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(self.programs, f, indent=2)

    def _program_key(self, exe_path):
        try:
            with open(exe_path, "rb") as f:
                header = f.read(8192)
            return hashlib.md5(os.path.normpath(exe_path).lower().encode()).hexdigest()[:16]
        except Exception:
            return hashlib.md5(exe_path.lower().encode()).hexdigest()[:16]

    def record_program(self, exe_path, cert_info=None):
        key = self._program_key(exe_path)
        if key not in self.programs:
            self.programs[key] = {
                "path": exe_path,
                "first_seen": time.time(),
                "cert_thumbprint": cert_info.get("thumbprint") if cert_info else None,
                "cert_subject": cert_info.get("subject") if cert_info else None,
                "access_count": 0,
            }
            self._save()
        self.programs[key]["access_count"] = self.programs[key].get("access_count", 0) + 1
        self.programs[key]["last_seen"] = time.time()
        self._save()

    def was_program_seen_before(self, exe_path):
        key = self._program_key(exe_path)
        if key not in self.programs:
            return False, None
        return True, self.programs[key]["first_seen"]

    def get_program_info(self, exe_path):
        return self.programs.get(self._program_key(exe_path))

    def is_program_new_after_sketchy(self, exe_path, sketchy_timestamp):
        key = self._program_key(exe_path)
        if key not in self.programs:
            return True, None
        first_seen = self.programs[key]["first_seen"]
        if first_seen > sketchy_timestamp:
            return True, first_seen - sketchy_timestamp
        return False, None


class SuspiciousTracker:
    def __init__(self, app_data_path):
        self.app_data_path = app_data_path
        self.log_path = os.path.join(app_data_path, SUSPICIOUS_LOG_PATH)
        self.entries = self._load()

    def _load(self):
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"sketchy_files": [], "suspicious_events": []}

    def _save(self):
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, indent=2)

    def add_sketchy_file(self, file_path, reason):
        self.entries["sketchy_files"].append({
            "path": file_path,
            "timestamp": time.time(),
            "reason": reason,
        })
        self.entries["sketchy_files"] = self.entries["sketchy_files"][-100:]
        self._save()

    def get_latest_sketchy_timestamp(self):
        if not self.entries["sketchy_files"]:
            return None
        return max(e["timestamp"] for e in self.entries["sketchy_files"])

    def add_suspicious_event(self, event_type, details):
        self.entries["suspicious_events"].append({
            "type": event_type,
            "details": details,
            "timestamp": time.time(),
        })
        self.entries["suspicious_events"] = self.entries["suspicious_events"][-200:]
        self._save()


class NetworkInspector:
    def __init__(self, app_data_path):
        self.app_data_path = app_data_path
        self.log_path = os.path.join(app_data_path, NETWORK_LOG_PATH)
        self.log = self._load()

    def _load(self):
        if os.path.exists(self.log_path):
            try:
                with open(self.log_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"destinations": [], "blocked": []}

    def _save(self):
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump(self.log, f, indent=2)

    def check_destination(self, url_or_ip):
        if not url_or_ip:
            return False, None, None
        dest_info = {"raw": url_or_ip, "timestamp": time.time()}
        try:
            parsed = urlparse(url_or_ip if "://" in url_or_ip else f"http://{url_or_ip}")
            host = parsed.netloc or parsed.path
            dest_info["host"] = host
            dest_info["scheme"] = parsed.scheme
        except Exception:
            host = url_or_ip
            dest_info["host"] = host
        if dest_info.get("scheme") == "http":
            self.log["destinations"].append(dest_info)
            self._save()
            return True, "no i shall refuse the HTTP!", dest_info
        discord_patterns = [
            "discord.com/api/webhooks",
            "discordapp.com/api/webhooks",
            "hooks.slack.com",
        ]
        for pattern in discord_patterns:
            if pattern in url_or_ip.lower():
                self.log["destinations"].append(dest_info)
                self._save()
                return True, "discord/slack webhook detected", dest_info
        exfil_services = [
            "pastebin.com", "hastebin.com", "dpaste.org", "rentry.co",
            "ix.io", "0x0.st", "transfer.sh", "ngrok.io",
            "localtunnel", "serveo.net",
        ]
        for service in exfil_services:
            if service in host.lower():
                self.log["destinations"].append(dest_info)
                self._save()
                return True, f"known exfiltration service: {service}", dest_info
        ip_pattern = r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(:\d+)?$"
        if re.match(ip_pattern, host):
            ip_only = host.split(":")[0] if ":" in host else host
            parts = ip_only.split(".")
            if parts[0] in ("10", "172", "192"):
                self.log["destinations"].append(dest_info)
                self._save()
                return True, "raw private IP address", dest_info
            else:
                self.log["destinations"].append(dest_info)
                self._save()
                return True, "raw public IP address (no domain)", dest_info
        sketchy_tlds = SKETCHY_TLDS
        for tld in sketchy_tlds:
            if host.lower().endswith(tld):
                self.log["destinations"].append(dest_info)
                self._save()
                return True, f"suspicious TLD: {tld}", dest_info
        self.log["destinations"].append(dest_info)
        self.log["destinations"] = self.log["destinations"][-500:]
        self._save()
        return False, None, dest_info

    def block_destination(self, url_or_ip, reason):
        self.log["blocked"].append({
            "url": url_or_ip,
            "reason": reason,
            "timestamp": time.time(),
        })
        self._save()


class HoneypotGenerator:
    def __init__(self, machine_uuid):
        self.machine_uuid = machine_uuid
        self._seed = int(hashlib.md5(machine_uuid.encode()).hexdigest()[:8], 16)

    def _deterministic_random(self, index):
        self._seed = (self._seed * 1103515245 + 12345 + index) & 0x7FFFFFFF
        return self._seed

    def generate_fake_entries(self, count=5):
        fake_sites = [
            {"name": "google.com", "user_patterns": ["user@gmail.com", "admin@gmail.com"]},
            {"name": "github.com", "user_patterns": ["developer", "user123"]},
            {"name": "amazon.com", "user_patterns": ["shopper@email.com"]},
            {"name": "netflix.com", "user_patterns": ["viewer@email.com"]},
            {"name": "spotify.com", "user_patterns": ["musiclover@email.com"]},
            {"name": "twitter.com", "user_patterns": ["@user123"]},
            {"name": "reddit.com", "user_patterns": ["redditor42"]},
            {"name": "discord.com", "user_patterns": ["user#1234"]},
            {"name": "facebook.com", "user_patterns": ["user@email.com"]},
            {"name": "instagram.com", "user_patterns": ["instauser"]},
        ]
        entries = []
        for i in range(count):
            idx = self._deterministic_random(i)
            site = fake_sites[idx % len(fake_sites)]
            username = site["user_patterns"][idx % len(site["user_patterns"])]
            fake_pw = self._generate_fake_password(idx)
            entries.append({
                "id": hashlib.md5(f"fake_{i}_{self.machine_uuid}".encode()).hexdigest()[:16],
                "name": site["name"],
                "username": username,
                "password": fake_pw,
                "hide_capture": True,
                "created": int(time.time()) - (idx % 86400),
                "updated": int(time.time()) - (idx % 43200),
            })
        return entries

    def _generate_fake_password(self, seed):
        patterns = [
            lambda s: f"Pass{s % 1000:03d}!",
            lambda s: f"User{s % 100:02d}#{s % 10000:04d}",
            lambda s: f"qwerty{s % 1000:03d}",
            lambda s: f"Secure{s % 100:02d}${s % 1000:03d}",
            lambda s: f"Hello{s % 100:02d}!",
            lambda s: f"Love{s % 1000:03d}#",
            lambda s: f"Admin{s % 100:02d}@{s % 1000:03d}",
            lambda s: f"Secret{s % 1000:03d}$",
        ]
        pattern = patterns[seed % len(patterns)]
        return pattern(seed)

    def generate_fake_vault_data(self):
        return {
            "verify": "ehs clipboard vault",
            "totp_enabled": False,
            "totp_secret_b64": None,
            "backup_codes": [],
            "entries": self.generate_fake_entries(8),
        }

    def generate_corrupted_mask_key(self):
        return secrets.token_bytes(32)

    def generate_garbage_data(self):
        return {
            "verify": "ehs clipboard vault",
            "totp_enabled": True,
            "totp_secret_b64": base64.b64encode(secrets.token_bytes(20)).decode(),
            "backup_codes": [hashlib.sha256(secrets.token_bytes(10)).hexdigest() for _ in range(15)],
            "entries": self.generate_fake_entries(12),
        }


class AntiExtraction:
    def __init__(self, app_data_path):
        self.app_data_path = app_data_path
        self.vault_running = False
        self.extraction_attempts = []
        self._vault_pid = None

    def set_vault_running(self, running, pid=None):
        self.vault_running = running
        self._vault_pid = pid or (os.getpid() if running else None)

    def check_extraction_attempt(self, program_path, destination=None):
        if not self.vault_running:
            if destination:
                return True, "vault not running - data extraction to external destination blocked"
            vault_files = ["vault.bin", "mask_key.bin"]
            for vf in vault_files:
                vault_path = os.path.join(self.app_data_path, "Passwords", vf)
                if os.path.exists(vault_path):
                    try:
                        stat = os.stat(vault_path)
                        if time.time() - stat.st_mtime < 5:
                            self.extraction_attempts.append({
                                "program": program_path,
                                "timestamp": time.time(),
                                "vault_file": vf,
                            })
                            return True, f"vault file {vf} accessed while vault not running"
                    except Exception:
                        pass
            try:
                vault_dir = os.path.join(self.app_data_path, "Passwords")
                if not os.path.exists(vault_dir):
                    return False, None
                for proc in psutil.process_iter(["pid", "name", "exe"]):
                    try:
                        if proc.info["pid"] == os.getpid():
                            continue
                        try:
                            open_files = proc.open_files()
                            for f in open_files:
                                if vault_dir.lower() in f.path.lower():
                                    self.extraction_attempts.append({
                                        "program": proc.info.get("exe", "unknown"),
                                        "pid": proc.info["pid"],
                                        "timestamp": time.time(),
                                        "vault_file": f.path,
                                        "access_type": "open_file",
                                    })
                                    return True, f"process {proc.info['name']} (PID {proc.info['pid']}) has vault file open"
                        except (psutil.AccessDenied, psutil.NoSuchProcess):
                            pass
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        continue
            except Exception:
                pass
        return False, None

    def get_extraction_attempts(self):
        return self.extraction_attempts

    def get_vault_accessors(self):
        accessors = []
        try:
            vault_dir = os.path.join(self.app_data_path, "Passwords")
            if not os.path.exists(vault_dir):
                return accessors
            for proc in psutil.process_iter(["pid", "name", "exe"]):
                try:
                    if proc.info["pid"] == os.getpid():
                        continue
                    try:
                        open_files = proc.open_files()
                        for f in open_files:
                            if vault_dir.lower() in f.path.lower():
                                accessors.append({
                                    "pid": proc.info["pid"],
                                    "name": proc.info["name"],
                                    "exe": proc.info.get("exe", "unknown"),
                                    "file": f.path,
                                })
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        pass
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    continue
        except Exception:
            pass
        return accessors


class SEIDResult:
    def __init__(self):
        self.verdict = "UNKNOWN"
        self.blocked = False
        self.block_reason = None
        self.reason_key = None
        self.reason_args = None
        self.data = None
        self.cert_info = None
        self.metadata = None

    def is_trusted(self):
        return self.verdict in ("TRUSTED", "KNOWN_TRUSTED") and not self.blocked

    def should_serve_honeypot(self):
        return self.data is not None

    def __repr__(self):
        return f"SEIDResult(verdict={self.verdict}, blocked={self.blocked}, has_data={self.data is not None})"


class SEIDInterceptor:
    def __init__(self, app_data_path):
        self.app_data_path = app_data_path
        self.seid_dir = os.path.join(app_data_path, "SEID")
        os.makedirs(self.seid_dir, exist_ok=True)
        self.machine_identity = MachineIdentity(self.seid_dir)
        self.cert_verifier = CertVerifier()
        self.metadata_fingerprint = MetadataFingerprint()
        self.timeline_tracker = TimelineTracker(self.seid_dir)
        self.suspicious_tracker = SuspiciousTracker(self.seid_dir)
        self.network_inspector = NetworkInspector(self.seid_dir)
        self.honeypot = HoneypotGenerator(self.machine_identity.get_machine_uuid())
        self.anti_extraction = AntiExtraction(app_data_path)
        self.known_programs_path = os.path.join(self.seid_dir, KNOWN_PROGRAMS_PATH)
        self.known_programs = self._load_known()

    def _load_known(self):
        if os.path.exists(self.known_programs_path):
            try:
                with open(self.known_programs_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_known(self):
        with open(self.known_programs_path, "w", encoding="utf-8") as f:
            json.dump(self.known_programs, f, indent=2)

    def _is_known_trusted(self, exe_path):
        key = hashlib.md5(os.path.normpath(exe_path).lower().encode()).hexdigest()
        if key in self.known_programs:
            info = self.known_programs[key]
            if time.time() - info.get("last_verified", 0) < 86400:
                return True, info
        return False, None

    def _mark_known_trusted(self, exe_path, cert_info, metadata):
        key = hashlib.md5(os.path.normpath(exe_path).lower().encode()).hexdigest()
        self.known_programs[key] = {
            "path": exe_path,
            "cert_subject": cert_info.get("subject") if cert_info else None,
            "cert_thumbprint": cert_info.get("thumbprint") if cert_info else None,
            "metadata": metadata,
            "first_verified": self.known_programs.get(key, {}).get("first_verified", time.time()),
            "last_verified": time.time(),
        }
        self._save_known()

    def intercept_fast(self, requesting_program_path):
        result = self._intercept_core(requesting_program_path)
        return result

    def intercept(self, requesting_program_path, destination=None):
        result = SEIDResult()

        should_block, block_reason = self.anti_extraction.check_extraction_attempt(
            requesting_program_path, destination
        )
        if should_block:
            result.blocked = True
            result.block_reason = block_reason
            result.reason_key = "SESVExtractionBlocked"
            result.data = self.honeypot.generate_garbage_data()
            result.verdict = "BLOCKED"
            self.suspicious_tracker.add_suspicious_event("extraction_blocked", {
                "program": requesting_program_path,
                "reason": block_reason,
            })
            return result

        if destination:
            is_sus, reason, dest_info = self.network_inspector.check_destination(destination)
            if is_sus:
                result.blocked = True
                result.block_reason = f"suspicious destination: {reason}"
                result.reason_key = "SESVNetworkBlocked"
                result.data = self.honeypot.generate_garbage_data()
                result.verdict = "BLOCKED_NETWORK"
                self.network_inspector.block_destination(destination, reason)
                self.suspicious_tracker.add_suspicious_event("suspicious_network", {
                    "program": requesting_program_path,
                    "destination": destination,
                    "reason": reason,
                })
                return result

        return self._intercept_core(requesting_program_path)

    def _intercept_core(self, requesting_program_path):
        result = SEIDResult()

        is_known, known_info = self._is_known_trusted(requesting_program_path)
        if is_known:
            result.verdict = "KNOWN_TRUSTED"
            result.data = None
            result.cert_info = known_info
            self.timeline_tracker.record_program(requesting_program_path, known_info)
            return result

        is_trusted, cert_info, cert_reason = self.cert_verifier.validate_cert_trust(
            requesting_program_path
        )

        if not is_trusted:
            result.verdict = "NO_CERT"
            result.cert_info = cert_info
            result.block_reason = cert_reason
            result.data = self.honeypot.generate_fake_vault_data()
            origin, origin_detail = self.cert_verifier.check_cert_origin(cert_info)
            if origin in ("self_signed", "none"):
                result.verdict = "SUSPICIOUS_CERT"
                result.reason_key = "SESVSelfSigned"
                result.data = self.honeypot.generate_garbage_data()
            elif not cert_info or not cert_info.get("CompanyName"):
                result.reason_key = "SESVNoCert"
            else:
                result.reason_key = "SESVUnknownIssuer"
            self.suspicious_tracker.add_suspicious_event("no_cert", {
                "program": requesting_program_path,
                "reason": cert_reason,
                "cert_info": cert_info,
            })
            return result

        origin, origin_detail = self.cert_verifier.check_cert_origin(cert_info)
        if origin == "unknown_issuer":
            program_dir = os.path.dirname(requesting_program_path)
            for root, dirs, files in os.walk(program_dir):
                for f in files:
                    if f.lower().endswith((".exe", ".dll")):
                        exe_path = os.path.join(root, f)
                        file_cert = self.cert_verifier.get_embedded_cert_info(exe_path)
                        if file_cert and file_cert.get("thumbprint") == cert_info.get("thumbprint"):
                            try:
                                stat = os.stat(exe_path)
                                created = stat.st_ctime
                                if time.time() - created < 3600:
                                    result.verdict = "RECENTLY_INSTALLED_CERT"
                                    result.data = self.honeypot.generate_garbage_data()
                                    result.reason_key = "SESVRecentCert"
                                    result.block_reason = f"certificate installed recently from {program_dir}"
                                    self.suspicious_tracker.add_suspicious_event("recent_cert", {
                                        "program": requesting_program_path,
                                        "cert_age": time.time() - created,
                                        "origin": program_dir,
                                    })
                                    return result
                            except Exception:
                                pass

        metadata = self.metadata_fingerprint.get_pe_metadata(requesting_program_path)
        is_default, bundler, matched_fields = self.metadata_fingerprint.fingerprint_match(metadata)
        if is_default:
            result.verdict = "DEFAULT_METADATA"
            result.data = self.honeypot.generate_fake_vault_data()
            result.reason_key = "SESVDefaultMetadata"
            result.reason_args = {"template": bundler}
            result.block_reason = f"default {bundler} metadata: {', '.join(matched_fields)}"
            self.suspicious_tracker.add_suspicious_event("default_metadata", {
                "program": requesting_program_path,
                "bundler": bundler,
                "matched_fields": matched_fields,
            })
            return result

        sketchy_ts = self.suspicious_tracker.get_latest_sketchy_timestamp()
        if sketchy_ts:
            is_new, time_delta = self.timeline_tracker.is_program_new_after_sketchy(
                requesting_program_path, sketchy_ts
            )
            if is_new:
                result.verdict = "NEW_AFTER_SKETCHY"
                result.data = self.honeypot.generate_fake_vault_data()
                result.reason_key = "SESVNewAfterSketchy"
                result.block_reason = "program appeared after sketchy file"
                self.suspicious_tracker.add_suspicious_event("new_after_sketchy", {
                    "program": requesting_program_path,
                    "sketchy_timestamp": sketchy_ts,
                })
                return result

        program_dir = os.path.dirname(requesting_program_path).lower()
        for sus_loc in SUSPICIOUS_LOCATIONS:
            if program_dir.startswith(sus_loc):
                result.verdict = "SUSPICIOUS_LOCATION"
                result.data = self.honeypot.generate_fake_vault_data()
                result.reason_key = "SESVSketchyLocation"
                result.block_reason = f"program running from suspicious location: {program_dir}"
                self.suspicious_tracker.add_suspicious_event("suspicious_location", {
                    "program": requesting_program_path,
                    "location": program_dir,
                })
                return result

        self.timeline_tracker.record_program(requesting_program_path, cert_info)
        self._mark_known_trusted(requesting_program_path, cert_info, metadata)
        result.verdict = "TRUSTED"
        result.data = None
        result.cert_info = cert_info
        result.metadata = metadata
        return result

    def mark_sketchy_file(self, file_path, reason):
        self.suspicious_tracker.add_sketchy_file(file_path, reason)

    def check_network_destination(self, url_or_ip):
        return self.network_inspector.check_destination(url_or_ip)

    def set_vault_running(self, running):
        self.anti_extraction.set_vault_running(running)

    def get_suspicious_log(self):
        return self.suspicious_tracker.entries

    def get_network_log(self):
        return self.network_inspector.log

    def get_program_log(self):
        return self.timeline_tracker.programs


def create_seid_interceptor(app_data_path):
    return SEIDInterceptor(app_data_path)


def quick_check_program(exe_path):
    verifier = CertVerifier()
    fingerprint = MetadataFingerprint()
    is_trusted, cert_info, reason = verifier.validate_cert_trust(exe_path)
    if not is_trusted:
        return False, reason
    metadata = fingerprint.get_pe_metadata(exe_path)
    is_default, bundler, fields = fingerprint.fingerprint_match(metadata)
    if is_default:
        return False, f"default {bundler} metadata"
    return True, "looks legit"
