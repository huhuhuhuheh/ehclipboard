import os
import json
import base64
import struct
import time
import hmac
import hashlib
import secrets
import uuid
import shutil
import sqlite3
import tempfile
import urllib.parse
from urllib.parse import urlparse

import ctypes
from ctypes import wintypes

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id

MAGIC = "EHCV"
VERSION = 1
KEY_LENGTH = 32
SALT_LENGTH = 16
NONCE_LENGTH = 12
ARGON2_MEMORY_KIB = 65536
ARGON2_TIME = 3
ARGON2_PARALLELISM = 2
MIN_MASK_LENGTH = 6
TOTP_PERIOD = 30
TOTP_DIGITS = 6
BACKUP_CODE_COUNT = 15


class VaultError(Exception):
    pass


class WrongPasswordError(VaultError):
    pass


class VaultCorruptError(VaultError):
    pass


class MaskKeyDecryptError(VaultError):
    pass


class TOTPError(VaultError):
    pass


def vault_file_path(app_data_path):
    return os.path.join(app_data_path, 'Passwords', 'vault.bin')


def generate_totp_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')


def totp_secret_to_bytes(secret_b32):
    if not secret_b32:
        raise TOTPError("Missing TOTP secret")
    padding = '=' * (-len(secret_b32) % 8)
    return base64.b32decode(secret_b32.upper() + padding)


def totp_code(secret_b32, at_time=None):
    if at_time is None:
        at_time = time.time()
    counter = int(at_time) // TOTP_PERIOD
    msg = struct.pack(">Q", counter)
    digest = hmac.new(totp_secret_to_bytes(secret_b32), msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code % (10 ** TOTP_DIGITS)).zfill(TOTP_DIGITS)


def totp_verify(secret_b32, code, window=1):
    if code is None:
        return False
    code = str(code).strip()
    if not code:
        return False
    now = int(time.time())
    for delta in range(-window, window + 1):
        if hmac.compare_digest(totp_code(secret_b32, now + delta * TOTP_PERIOD), code):
            return True
    return False


def totp_otpauth_uri(secret_b32, issuer, account):
    return (
        f"otpauth://totp/{urllib.parse.quote(issuer)}:{urllib.parse.quote(account)}"
        f"?secret={secret_b32}&issuer={urllib.parse.quote(issuer)}"
        f"&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_PERIOD}"
    )


def dpapi_unprotect(encrypted):
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]
    buf = (ctypes.c_ubyte * len(encrypted)).from_buffer_copy(encrypted)
    blob_in = DATA_BLOB(len(encrypted), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    blob_out = DATA_BLOB()
    crypt32 = ctypes.WinDLL('crypt32')
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
    )
    if not ok:
        raise VaultError("DPAPI unprotect failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.WinDLL('kernel32').LocalFree(blob_out.pbData)


def dpapi_protect(data):
    class DATA_BLOB(ctypes.Structure):
        _fields_ = [('cbData', wintypes.DWORD), ('pbData', ctypes.POINTER(ctypes.c_ubyte))]
    buf = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
    blob_out = DATA_BLOB()
    crypt32 = ctypes.WinDLL('crypt32')
    ok = crypt32.CryptProtectData(
        ctypes.byref(blob_in), None, None, None, None, 0x01, ctypes.byref(blob_out)
    )
    if not ok:
        raise VaultError("DPAPI protect failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.WinDLL('kernel32').LocalFree(blob_out.pbData)


def mask_key_cache_path(app_data_path):
    return os.path.join(app_data_path, 'Passwords', 'mask_key.bin')


def save_mask_key(app_data_path, key):
    if not key:
        return
    try:
        os.makedirs(os.path.join(app_data_path, 'Passwords'), exist_ok=True)
        blob = dpapi_protect(bytes(key))
        with open(mask_key_cache_path(app_data_path), 'wb') as f:
            f.write(blob)
    except Exception:
        pass


def load_mask_key(app_data_path):
    path = mask_key_cache_path(app_data_path)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'rb') as f:
            blob = f.read()
    except Exception as exc:
        raise MaskKeyDecryptError(path) from exc
    if not blob:
        return None
    try:
        return dpapi_unprotect(blob)
    except VaultError as exc:
        raise MaskKeyDecryptError(path) from exc
    except Exception:
        return None


def clear_mask_key(app_data_path):
    try:
        path = mask_key_cache_path(app_data_path)
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def host_of(url):
    try:
        return urlparse(url).netloc or url
    except Exception:
        return url


def get_chromium_key(local_state_path):
    with open(local_state_path, 'r', encoding='utf-8') as f:
        ls = json.load(f)
    enc = base64.b64decode(ls['os_crypt']['encrypted_key'])
    if enc[:5] != b'DPAPI':
        raise VaultError("Unsupported Chromium key format")
    return dpapi_unprotect(enc[5:])


def decrypt_chromium_password(payload, key):
    if not payload:
        return ''
    if payload[:3] in (b'v10', b'v11'):
        if not key:
            return ''
        nonce = payload[3:15]
        ciphertext = payload[15:]
        return AESGCM(key).decrypt(nonce, ciphertext, None).decode('utf-8', errors='replace')
    if payload[:2] == b'v1':
        return dpapi_unprotect(payload[3:]).decode('utf-8', errors='replace')
    return dpapi_unprotect(payload).decode('utf-8', errors='replace')


def chromium_user_data_dirs():
    local = os.environ.get('LOCALAPPDATA') or ''
    appdata = os.environ.get('APPDATA') or ''
    supported = {
        'chrome': ('Google Chrome', os.path.join(local, 'Google', 'Chrome', 'User Data')),
        'chrome-canary': ('Google Chrome Canary', os.path.join(local, 'Google', 'Chrome SxS', 'User Data')),
        'chromium': ('Chromium', os.path.join(local, 'Chromium', 'User Data')),
        'opera-stable': ('Opera', os.path.join(appdata, 'Opera Software', 'Opera Stable')),
        'opera-beta': ('Opera Beta', os.path.join(appdata, 'Opera Software', 'Opera Beta')),
        'opera-developer': ('Opera Developer', os.path.join(appdata, 'Opera Software', 'Opera Developer')),
        'msedge': ('Microsoft Edge', os.path.join(local, 'Microsoft', 'Edge', 'User Data')),
        'msedge-beta': ('Microsoft Edge Beta', os.path.join(local, 'Microsoft', 'Edge Beta', 'User Data')),
        'msedge-dev': ('Microsoft Edge Dev', os.path.join(local, 'Microsoft', 'Edge Dev', 'User Data')),
        'msedge-canary': ('Microsoft Edge Canary', os.path.join(local, 'Microsoft', 'Edge SxS', 'User Data')),
    }
    present = {}
    try:
        import installed_browsers
        for entry in installed_browsers.browsers():
            key = entry.get('name') if isinstance(entry, dict) else getattr(entry, 'name', None)
            if key in supported:
                present[key] = supported[key]
    except Exception:
        pass
    for key, pair in supported.items():
        present.setdefault(key, pair)
    return {name: d for key, (name, d) in present.items() if os.path.isdir(d)}


def chromium_profiles(user_data_dir):
    out = []
    try:
        for entry in sorted(os.listdir(user_data_dir)):
            path = os.path.join(user_data_dir, entry)
            if os.path.isdir(path) and os.path.exists(os.path.join(path, 'Login Data')):
                out.append(entry)
    except Exception:
        pass
    return out


def _copy_login_data(login_db):
    tmp_dir = tempfile.mkdtemp(prefix='ehsclip-')
    tmp_main = os.path.join(tmp_dir, 'Login Data')
    shutil.copy2(login_db, tmp_main)
    for suffix in ('-wal', '-shm'):
        extra = login_db + suffix
        if os.path.exists(extra):
            try:
                shutil.copy2(extra, tmp_main + suffix)
            except Exception:
                pass
    return tmp_dir


def import_from_chromium_profile(user_data_dir, profile):
    entries = []
    key = None
    local_state = os.path.join(user_data_dir, 'Local State')
    if os.path.exists(local_state):
        try:
            key = get_chromium_key(local_state)
        except Exception:
            key = None
    login_db = os.path.join(user_data_dir, profile, 'Login Data')
    if not os.path.exists(login_db):
        return entries
    tmp_dir = None
    try:
        tmp_dir = _copy_login_data(login_db)
        conn = sqlite3.connect(os.path.join(tmp_dir, 'Login Data'))
        try:
            rows = conn.execute(
                "SELECT origin_url, action_url, username_value, password_value "
                "FROM logins WHERE blacklisted_by_user = 0"
            ).fetchall()
        finally:
            conn.close()
        for origin_url, action_url, username, pwd in rows:
            if not pwd:
                continue
            try:
                plain = decrypt_chromium_password(pwd, key)
            except Exception:
                plain = None
            if not plain:
                continue
            entries.append({
                'name': host_of(origin_url or action_url) or 'Website',
                'username': username or '',
                'password': plain,
            })
    except Exception:
        pass
    finally:
        if tmp_dir and os.path.isdir(tmp_dir):
            try:
                shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
    return entries


def import_from_chromium(user_data_dir):
    entries = []
    for profile in chromium_profiles(user_data_dir):
        entries.extend(import_from_chromium_profile(user_data_dir, profile))
    return entries


def import_from_csv(path):
    import csv
    entries = []
    with open(path, 'r', encoding='utf-8-sig', newline='') as f:
        rows = list(csv.reader(f))
    if not rows:
        return entries
    header = [h.strip().lower() for h in rows[0]]
    idx = {col: (header.index(col) if col in header else None) for col in ('name', 'url', 'username', 'password')}
    if idx['password'] is None:
        raise VaultError('CSV needs a "password" column')
    for row in rows[1:]:
        if not row or idx['password'] >= len(row):
            continue
        pw = row[idx['password']].strip()
        if not pw:
            continue
        def _get(col):
            i = idx[col]
            return row[i].strip() if i is not None and i < len(row) else ''
        name = _get('name')
        url = _get('url')
        if not name and url:
            name = host_of(url)
        entries.append({'name': name or 'Website', 'username': _get('username'), 'password': pw})
    return entries


def generate_backup_codes(count=BACKUP_CODE_COUNT):
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return [''.join(secrets.choice(alphabet) for _ in range(10)) for _ in range(count)]


def hash_backup_code(code):
    return hashlib.sha256(code.encode('utf-8')).hexdigest()


def verify_backup_code(hashes, code):
    if not code:
        return None
    target = hash_backup_code(code)
    for stored in hashes:
        if hmac.compare_digest(stored, target):
            return stored
    return None


def consume_backup_code(hashes, code):
    stored = verify_backup_code(hashes, code)
    if stored is not None:
        hashes.remove(stored)
        return True
    return False


def derive_key(master_password, salt, memory_kib, time_cost, parallelism):
    if isinstance(master_password, str):
        master_password = master_password.encode('utf-8')
    kdf = Argon2id(
        salt=salt,
        length=KEY_LENGTH,
        memory_cost=memory_kib,
        iterations=time_cost,
        lanes=parallelism,
    )
    return kdf.derive(master_password)


def build_header_aad(salt, memory_kib, time_cost, parallelism):
    header = {
        "magic": MAGIC,
        "version": VERSION,
        "kdf": {
            "memory_cost": memory_kib,
            "time_cost": time_cost,
            "parallelism": parallelism,
        },
        "salt_b64": base64.b64encode(salt).decode(),
    }
    return json.dumps(header, sort_keys=True).encode()


def check_kdf_params(memory_kib, time_cost, parallelism):
    if memory_kib < 16384 or time_cost < 2 or not (1 <= parallelism <= 16):
        raise VaultCorruptError("Unsafe or corrupted KDF parameters")


def encrypt_vault(plaintext_bytes, master_password):
    salt = secrets.token_bytes(SALT_LENGTH)
    key = derive_key(master_password, salt, ARGON2_MEMORY_KIB, ARGON2_TIME, ARGON2_PARALLELISM)
    nonce = secrets.token_bytes(NONCE_LENGTH)
    aad = build_header_aad(salt, ARGON2_MEMORY_KIB, ARGON2_TIME, ARGON2_PARALLELISM)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext_bytes, aad)
    payload = {
        "magic": MAGIC,
        "version": VERSION,
        "kdf": {
            "memory_cost": ARGON2_MEMORY_KIB,
            "time_cost": ARGON2_TIME,
            "parallelism": ARGON2_PARALLELISM,
        },
        "salt_b64": base64.b64encode(salt).decode(),
        "nonce_b64": base64.b64encode(nonce).decode(),
        "ciphertext_b64": base64.b64encode(ciphertext).decode(),
    }
    return json.dumps(payload)


def read_vault_header(vault_path):
    try:
        with open(vault_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if data.get('magic') != MAGIC:
            raise VaultCorruptError("Not an eh's Clipboard vault")
        kdf = data.get('kdf', {})
        memory_kib = int(kdf.get('memory_cost', 0))
        time_cost = int(kdf.get('time_cost', 0))
        parallelism = int(kdf.get('parallelism', 0))
        check_kdf_params(memory_kib, time_cost, parallelism)
        data['_kdf'] = (memory_kib, time_cost, parallelism)
        return data
    except VaultError:
        raise
    except Exception as e:
        raise VaultCorruptError(f"Could not read vault: {e}")


def derive_key_from_file(vault_path, master_password):
    data = read_vault_header(vault_path)
    salt = base64.b64decode(data['salt_b64'])
    memory_kib, time_cost, parallelism = data['_kdf']
    return derive_key(master_password, salt, memory_kib, time_cost, parallelism)


def decrypt_vault_with_key(vault_path, key):
    data = read_vault_header(vault_path)
    salt = base64.b64decode(data['salt_b64'])
    memory_kib, time_cost, parallelism = data['_kdf']
    aad = build_header_aad(salt, memory_kib, time_cost, parallelism)
    nonce = base64.b64decode(data['nonce_b64'])
    ciphertext = base64.b64decode(data['ciphertext_b64'])
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag:
        raise WrongPasswordError("Wrong master password or corrupted vault")
    try:
        return json.loads(plaintext)
    except Exception as e:
        raise VaultCorruptError(f"Decrypted data is corrupt: {e}")


def unlock_vault(vault_path, master_password):
    key = derive_key_from_file(vault_path, master_password)
    data = decrypt_vault_with_key(vault_path, key)
    data['_key'] = key
    return data


def create_vault(vault_path, master_password, entries=None, totp_secret=None, totp_enabled=False, backup_codes=None):
    if not master_password:
        raise VaultError("Master password cannot be empty")
    if totp_enabled and not totp_secret:
        raise VaultError("2FA enabled but no TOTP secret provided")
    plaintext = {
        "verify": "ehs clipboard vault",
        "totp_enabled": bool(totp_enabled),
        "totp_secret_b64": base64.b64encode(totp_secret.encode()).decode() if totp_secret else None,
        "backup_codes": [hash_backup_code(c) for c in (backup_codes or [])],
        "entries": entries or [],
    }
    blob = encrypt_vault(json.dumps(plaintext).encode(), master_password)
    os.makedirs(os.path.dirname(vault_path), exist_ok=True)
    with open(vault_path, 'w', encoding='utf-8') as f:
        f.write(blob)
    save_mask_key(os.path.dirname(os.path.dirname(vault_path)), derive_key_from_file(vault_path, master_password))


def save_vault_with_key(vault_path, key, data):
    header = read_vault_header(vault_path)
    salt = base64.b64decode(header['salt_b64'])
    memory_kib, time_cost, parallelism = header['_kdf']
    nonce = secrets.token_bytes(NONCE_LENGTH)
    aad = build_header_aad(salt, memory_kib, time_cost, parallelism)
    plaintext = json.dumps({
        "verify": data.get("verify", "ehs clipboard vault"),
        "totp_enabled": bool(data.get("totp_enabled", False)),
        "totp_secret_b64": data.get("totp_secret_b64"),
        "backup_codes": data.get("backup_codes", []),
        "entries": data.get("entries", []),
    }).encode()
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
    header.pop('_kdf', None)
    header['nonce_b64'] = base64.b64encode(nonce).decode()
    header['ciphertext_b64'] = base64.b64encode(ciphertext).decode()
    os.makedirs(os.path.dirname(vault_path), exist_ok=True)
    with open(vault_path, 'w', encoding='utf-8') as f:
        json.dump(header, f)
    save_mask_key(os.path.dirname(os.path.dirname(vault_path)), key)


def change_master_password(vault_path, old_master_password, new_master_password):
    if not new_master_password:
        raise VaultError("Master password cannot be empty")
    data = unlock_vault(vault_path, old_master_password)
    data.pop('_key', None)
    save_vault(vault_path, new_master_password, data)
    new_key = derive_key_from_file(vault_path, new_master_password)
    save_mask_key(os.path.dirname(os.path.dirname(vault_path)), new_key)
    return new_key


def save_vault(vault_path, master_password, data):
    plaintext = {
        "verify": data.get("verify", "ehs clipboard vault"),
        "totp_enabled": bool(data.get("totp_enabled", False)),
        "totp_secret_b64": data.get("totp_secret_b64"),
        "backup_codes": data.get("backup_codes", []),
        "entries": data.get("entries", []),
    }
    blob = encrypt_vault(json.dumps(plaintext).encode(), master_password)
    os.makedirs(os.path.dirname(vault_path), exist_ok=True)
    with open(vault_path, 'w', encoding='utf-8') as f:
        f.write(blob)


def replace_backup_codes(vault_path, key, data, new_codes=None):
    data['backup_codes'] = [hash_backup_code(c) for c in (new_codes if new_codes is not None else generate_backup_codes())]
    save_vault_with_key(vault_path, key, data)
    return data['backup_codes']


def new_entry(name, username, password, hide_capture=True):
    now = int(time.time())
    return {
        "id": uuid.uuid4().hex,
        "name": name,
        "username": username,
        "password": password,
        "hide_capture": bool(hide_capture),
        "created": now,
        "updated": now,
    }


def update_entry(entry, name=None, username=None, password=None, hide_capture=None):
    if name is not None:
        entry['name'] = name
    if username is not None:
        entry['username'] = username
    if password is not None:
        entry['password'] = password
    if hide_capture is not None:
        entry['hide_capture'] = bool(hide_capture)
    entry['updated'] = int(time.time())
    return entry


def delete_entry(entries, entry_id):
    return [e for e in entries if e.get('id') != entry_id]


def mask_text(text, entries, min_length=MIN_MASK_LENGTH):
    masked, _ = mask_text_detailed(text, entries, min_length)
    return masked


def mask_text_detailed(text, entries, min_length=MIN_MASK_LENGTH):
    if not entries or not text:
        return text, []
    passwords = sorted(
        {e.get('password', '') for e in entries if e.get('password') and len(e.get('password', '')) >= min_length},
        key=len,
        reverse=True,
    )
    masked = text
    replacements = []
    seen_pws = set()
    for pw in passwords:
        if pw in seen_pws:
            continue
        seen_pws.add(pw)
        if pw not in masked:
            continue
        block = '*' * len(pw)
        masked = masked.replace(pw, block)
        replacements.append((block, pw))
    return masked, replacements


_session_key = None
_session_data = None


def set_session(key, data):
    global _session_key, _session_data
    _session_key = key
    _session_data = data


def clear_session():
    global _session_key, _session_data
    _session_key = None
    _session_data = None


def lock_session():
    global _session_key
    _session_key = None


def session_key():
    return _session_key


def is_unlocked():
    return _session_data is not None


def session_data():
    return _session_data


def session_entries():
    if _session_data is None:
        return []
    return _session_data.get('entries', [])