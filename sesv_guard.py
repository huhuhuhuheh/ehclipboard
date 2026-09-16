import os
import sys
import time
import threading
import ctypes
import ctypes.wintypes
import hashlib
import base64
import secrets
import concurrent.futures
import psutil
import sesv

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
ntdll = ctypes.WinDLL("ntdll", use_last_error=True)
NtSuspendProcess = ntdll.NtSuspendProcess
NtResumeProcess = ntdll.NtResumeProcess

_sesv_pool = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="sesvcheck")

FILE_NOTIFY_CHANGE_FILE_NAME = 0x00000010
FILE_NOTIFY_CHANGE_DIR_NAME = 0x00000001
FILE_NOTIFY_CHANGE_SIZE = 0x00000008
FILE_NOTIFY_CHANGE_LAST_WRITE = 0x00000010
FILE_ACTION_ADDED = 0x00000001
FILE_ACTION_REMOVED = 0x00000002
FILE_ACTION_MODIFIED = 0x00000003
FILE_LIST_DIRECTORY = 0x0001

ACTION_NAMES = {
    0x00000001: "ADDED",
    0x00000002: "REMOVED",
    0x00000003: "MODIFIED",
    0x00000004: "RENAMED_OLD",
    0x00000005: "RENAMED_NEW",
}

class FILE_NOTIFY_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("NextEntryOffset", ctypes.wintypes.DWORD),
        ("Action", ctypes.wintypes.DWORD),
        ("FileNameLength", ctypes.wintypes.DWORD),
        ("FileName", ctypes.wintypes.WCHAR * 1),
    ]


def _suspend_process(pid):
    try:
        h = kernel32.OpenProcess(0x0001, False, pid)
        if h:
            NtSuspendProcess(h)
            kernel32.CloseHandle(h)
            return True
    except Exception:
        pass
    return False


def _resume_process(pid):
    try:
        h = kernel32.OpenProcess(0x0001, False, pid)
        if h:
            NtResumeProcess(h)
            kernel32.CloseHandle(h)
            return True
    except Exception:
        pass
    return False


class VaultGuard:
    def __init__(self, app_data_path, sesv_interceptor):
        self.app_data_path = app_data_path
        self.vault_dir = os.path.join(app_data_path, "Passwords")
        self.sesv = sesv_interceptor
        self.honeypot = sesv_interceptor.honeypot
        self.running = False
        self._thread = None
        self._scan_thread = None
        self._wmi_thread = None
        self._trusted_cache = {}
        self._verdict_cache = {}
        self._blocked_pids = set()
        self._held_pids = {}
        self._swap_lock = threading.Lock()
        self.on_blocked = None
        self.on_trusted = None
        self.on_event = None
        self.on_intrusion = None
        self._dir_handle = None

    def _recover_stranded_vault(self):
        try:
            hidden = os.path.join(self.vault_dir, "vault.bin.hidden")
            real = os.path.join(self.vault_dir, "vault.bin")
            if not os.path.exists(hidden):
                return
            if not os.path.exists(real):
                os.replace(hidden, real)
                return
            if os.path.getsize(real) < 1000:
                os.remove(real)
                os.replace(hidden, real)
        except Exception:
            pass

    def _is_trusted_pid(self, pid):
        if pid in self._blocked_pids:
            return False
        if pid in self._trusted_cache:
            if time.time() - self._trusted_cache[pid] < 60:
                return True
        try:
            proc = psutil.Process(pid)
            exe = proc.exe()
        except Exception:
            return False
        cached = self._verdict_cache.get(exe)
        if cached is not None:
            if cached:
                self._trusted_cache[pid] = time.time()
                return True
            return False
        try:
            future = _sesv_pool.submit(self.sesv.intercept_fast, exe)
            try:
                result = future.result(timeout=3.0)
            except concurrent.futures.TimeoutError:
                self._set_verdict(exe, False)
                return False
            if result.is_trusted():
                self._set_verdict(exe, True)
                self._trusted_cache[pid] = time.time()
                if self.on_trusted:
                    self.on_trusted(pid, proc.name(), exe)
                return True
            self._set_verdict(exe, False)
            return False
        except Exception:
            self._set_verdict(exe, False)
            return False

    def _set_verdict(self, exe, trusted):
        if len(self._verdict_cache) >= 2000:
            try:
                oldest = next(iter(self._verdict_cache))
                self._verdict_cache.pop(oldest, None)
            except Exception:
                pass
        self._verdict_cache[exe] = trusted

    def _find_process_by_file(self, filepath):
        filepath_lower = filepath.lower()
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                if proc.info["pid"] == os.getpid():
                    continue
                try:
                    for f in proc.open_files():
                        if f.path.lower() == filepath_lower or filepath_lower in f.path.lower():
                            return proc.info["pid"], proc.info["name"], proc.info.get("exe", "")
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    pass
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue
        return None, None, None

    def _fake_vault_bytes(self):
        data = self.honeypot.generate_garbage_data()
        salt = secrets.token_bytes(16)
        nonce = secrets.token_bytes(12)
        return json_dumps({
            "magic": "EHCV",
            "version": 1,
            "kdf": {"memory_cost": 65536, "time_cost": 3, "parallelism": 2},
            "salt_b64": base64.b64encode(salt).decode(),
            "nonce_b64": base64.b64encode(nonce).decode(),
            "ciphertext_b64": base64.b64encode(secrets.token_bytes(256)).decode(),
        })

    def _fake_mask_bytes(self):
        return secrets.token_bytes(64)

    def _fake_uuid_bytes(self):
        return str(__import__("uuid").uuid4()).encode()

    def _serve_honeypot(self, pid, filepath):
        with self._swap_lock:
            backed_up = False
            hidden_path = filepath + ".hidden"
            try:
                if os.path.exists(filepath):
                    os.replace(filepath, hidden_path)
                    backed_up = True
                    fake = self._fake_vault_bytes()
                    with open(filepath, "wb") as f:
                        f.write(fake.encode() if isinstance(fake, str) else fake)
            except Exception:
                pass
            _resume_process(pid)
            if self.on_blocked:
                self.on_blocked(pid, None, None, f"honeypot served for {os.path.basename(filepath)}")
            if backed_up:
                def restore():
                    hidden_path_local = hidden_path
                    filepath_local = filepath
                    deadline = time.time() + 60
                    restored = False
                    while time.time() < deadline:
                        try:
                            if os.path.exists(filepath_local):
                                os.remove(filepath_local)
                            if os.path.exists(hidden_path_local):
                                os.replace(hidden_path_local, filepath_local)
                            restored = True
                            break
                        except Exception:
                            time.sleep(0.5)
                    self._restore_pending = not restored
                threading.Thread(target=restore, daemon=True).start()

    def _hold_intruder(self, pid, filepath, reason):
        if pid in self._held_pids:
            return
        _suspend_process(pid)
        self._held_pids[pid] = {"filepath": filepath, "reason": reason, "held_at": time.time()}
        if self.on_intrusion:
            try:
                decision = self.on_intrusion(pid, filepath, reason)
                if decision == "approve":
                    self.approve_pid(pid)
                elif decision == "deny":
                    self.deny_pid(pid)
                elif decision == "pending":
                    pass
                else:
                    self._kill_process(pid, reason)
            except Exception:
                self._kill_process(pid, reason)
        else:
            self._kill_process(pid, reason)

    def approve_pid(self, pid):
        _resume_process(pid)
        self._held_pids.pop(pid, None)
        self._trusted_cache[pid] = time.time()
        self._blocked_pids.discard(pid)
        if self.on_trusted:
            try:
                proc = psutil.Process(pid)
                self.on_trusted(pid, proc.name(), proc.exe())
            except Exception:
                pass

    def deny_pid(self, pid):
        held = self._held_pids.get(pid)
        filepath = held["filepath"] if held else os.path.join(self.vault_dir, "vault.bin")
        self._serve_honeypot(pid, filepath)
        self._blocked_pids.add(pid)
        self._held_pids.pop(pid, None)

    def _kill_process(self, pid, reason):
        try:
            proc = psutil.Process(pid)
            exe = proc.exe()
            name = proc.name()
            proc.kill()
            self._blocked_pids.add(pid)
            self._held_pids.pop(pid, None)
            if self.on_blocked:
                self.on_blocked(pid, name, exe, reason)
            return True
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            return False

    def _handle_file_event(self, action, filename):
        filepath = os.path.join(self.vault_dir, filename)
        action_name = ACTION_NAMES.get(action, f"UNKNOWN({action})")

        if self.on_event:
            self.on_event(action_name, filename)

        if action not in (FILE_ACTION_ADDED, FILE_ACTION_MODIFIED):
            return

        pid, name, exe = self._find_process_by_file(filepath)
        if pid is None:
            return

        if pid == os.getpid():
            return

        if pid in self._held_pids or pid in self._blocked_pids:
            return

        if not self._is_trusted_pid(pid):
            self._hold_intruder(pid, filepath, f"{action_name} on {filename}")

    def _parse_events(self, buffer, size):
        offset = 0
        while offset < size:
            info = ctypes.cast(
                ctypes.c_char_p(buffer) + offset,
                ctypes.POINTER(FILE_NOTIFY_INFORMATION)
            ).contents
            name_len = info.FileNameLength // 2
            name = ctypes.wstring_at(
                ctypes.addressof(info.FileName) if name_len > 0 else 0,
                name_len
            )
            self._handle_file_event(info.Action, name)
            if info.NextEntryOffset == 0:
                break
            offset += info.NextEntryOffset

    def _watch_loop(self):
        try:
            self._dir_handle = kernel32.CreateFileW(
                self.vault_dir,
                FILE_LIST_DIRECTORY,
                7,
                None,
                3,
                FILE_NOTIFY_CHANGE_FILE_NAME | FILE_NOTIFY_CHANGE_SIZE | FILE_NOTIFY_CHANGE_LAST_WRITE,
                None,
                None
            )
        except Exception:
            return

        buf_size = 4096
        buffer = ctypes.create_string_buffer(buf_size)
        bytes_returned = ctypes.wintypes.DWORD()

        while self.running:
            try:
                success = kernel32.ReadDirectoryChangesW(
                    self._dir_handle,
                    buffer,
                    buf_size,
                    True,
                    FILE_NOTIFY_CHANGE_FILE_NAME | FILE_NOTIFY_CHANGE_SIZE | FILE_NOTIFY_CHANGE_LAST_WRITE,
                    ctypes.byref(bytes_returned),
                    None,
                    None
                )
                if success and bytes_returned.value > 0:
                    self._parse_events(buffer.raw, bytes_returned.value)
            except Exception:
                time.sleep(0.1)

        if self._dir_handle:
            kernel32.CloseHandle(self._dir_handle)
            self._dir_handle = None

    def _scan_loop(self):
        while self.running:
            try:
                self.scan_now()
            except Exception:
                pass
            time.sleep(30.0)

    def _wmi_watch_loop(self):
        seen = set()
        for proc in psutil.process_iter(["pid"]):
            try:
                seen.add(proc.info["pid"])
            except Exception:
                pass
        while self.running:
            try:
                for proc in psutil.process_iter(["pid"]):
                    try:
                        pid = proc.info["pid"]
                    except Exception:
                        continue
                    if pid == os.getpid():
                        continue
                    if pid not in seen:
                        seen.add(pid)
                        self._spawn_pid_watch(pid)
                if len(seen) > 20000:
                    seen = set(p for p in seen if p in {x for x in self._held_pids} or self._pid_exists(p))
            except Exception:
                pass
            time.sleep(0.5)

    def _pid_exists(self, pid):
        try:
            psutil.Process(pid)
            return True
        except Exception:
            return False

    def _spawn_pid_watch(self, pid):
        if pid in self._blocked_pids or pid in self._held_pids:
            return
        t = threading.Thread(target=self._watch_pid_loop, args=(pid,), daemon=True)
        t.start()

    def _watch_pid_loop(self, pid, window=15.0):
        vault_lower = self.vault_dir.lower()
        deadline = time.time() + window
        while self.running and time.time() < deadline:
            if pid in self._blocked_pids or pid in self._held_pids:
                return
            try:
                proc = psutil.Process(pid)
            except psutil.NoSuchProcess:
                return
            except Exception:
                time.sleep(0.1)
                continue
            try:
                for f in proc.open_files():
                    if vault_lower in f.path.lower():
                        if not self._is_trusted_pid(pid):
                            self._hold_intruder(pid, f.path, f"vault file open: {f.path}")
                        return
            except psutil.NoSuchProcess:
                return
            except Exception:
                pass
            time.sleep(0.1)

    def start(self):
        if self.running:
            return
        if not os.path.exists(self.vault_dir):
            return
        self.running = True
        self._recover_stranded_vault()
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._scan_thread = threading.Thread(target=self._scan_loop, daemon=True)
        self._wmi_thread = threading.Thread(target=self._wmi_watch_loop, daemon=True)
        self._thread.start()
        self._scan_thread.start()
        self._wmi_thread.start()

    def stop(self):
        self.running = False
        for t in (self._thread, self._scan_thread, self._wmi_thread):
            if t:
                t.join(timeout=5)
        self._thread = None
        self._scan_thread = None
        self._wmi_thread = None
        for pid in list(self._held_pids.keys()):
            _resume_process(pid)
        self._held_pids.clear()
        if self._dir_handle:
            kernel32.CloseHandle(self._dir_handle)
            self._dir_handle = None

    def get_protected_dir(self):
        return self.vault_dir

    def scan_now(self):
        if not os.path.exists(self.vault_dir):
            return
        vault_lower = self.vault_dir.lower()
        for proc in psutil.process_iter(["pid", "name", "exe"]):
            try:
                pid = proc.info["pid"]
                if pid == os.getpid():
                    continue
                if pid in self._blocked_pids or pid in self._held_pids:
                    continue
                try:
                    for f in proc.open_files():
                        if vault_lower in f.path.lower():
                            if not self._is_trusted_pid(pid):
                                self._hold_intruder(pid, f.path, f"vault file open: {f.path}")
                            break
                except (psutil.AccessDenied, psutil.NoSuchProcess):
                    pass
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                continue


def json_dumps(obj):
    import json
    return json.dumps(obj)


def create_vault_guard(app_data_path):
    interceptor = sesv.create_seid_interceptor(os.path.join(app_data_path, "SESV"))
    return VaultGuard(app_data_path, interceptor)