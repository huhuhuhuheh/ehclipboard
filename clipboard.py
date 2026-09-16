import tkinter as tk
from tkinter.scrolledtext import ScrolledText
from tkinter import messagebox
import pyperclip
import time
import threading
import pystray
from pystray import MenuItem as item
from PIL import Image, ImageTk
import tkinter.font as tkfont
import sys
import base64
import ctypes
import winreg
from winotify import Notification, audio
import io
import configparser
import os
import webbrowser
import traceback
import hashlib
import queue
import subprocess
import passwords
import shutil

import ctypes
from ctypes import wintypes
import psutil

# --- Core Application Paths ---
IS_MSIX = False
APP_DATA_PATH = os.path.join(os.getenv('APPDATA'), "eh", "eh's Clipboard")
APP_ID = "gay.eh.clipboard"

try:
    length = ctypes.c_uint32(0)
    result = ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), None)
    
    if result != 15700:
        IS_MSIX = True
        APP_ID = "Eh's Clipboard"
        
        length = ctypes.c_uint32(0)
        ctypes.windll.kernel32.GetCurrentPackageFamilyName(ctypes.byref(length), None)
        family_name_buffer = ctypes.create_unicode_buffer(length.value)
        ctypes.windll.kernel32.GetCurrentPackageFamilyName(ctypes.byref(length), family_name_buffer)
        package_family_name = family_name_buffer.value
        
        local_app_data = os.getenv('LOCALAPPDATA')
        if local_app_data and package_family_name:
            APP_DATA_PATH = os.path.join(local_app_data, "Packages", package_family_name, "LocalCache", "Roaming", "eh", "eh's Clipboard")
except Exception:
    pass

CONFIG_FILE = os.path.join(APP_DATA_PATH, 'config.ini')

# Determine the base path for bundled, read-only assets.
if getattr(sys, 'frozen', False):
    # Running in a PyInstaller bundle.
    BASE_PATH = sys._MEIPASS
else:
    # Running as a normal .py script.
    BASE_PATH = os.path.dirname(os.path.abspath(__file__))

ICON_BASE64 = '''iVBORw0KGgoAAAANSUhEUgAAADQAAAA0CAYAAADFeBvrAAACZElEQVRoQ+2Zv4vUQBTHJ4loayWS7BsMbHMsB94fYKGl2GjjCSInKtpZ26hgYWfhHyCIWFhZWMsK2p+IhYKwwpsQbLcSDXmS494wmJ+XnYVkmQ8svO/bkJkPE2bYrCc2DE9XG4ITGjpWhBDxqRDiChEd1017qCAIbkdR9F13GlhZCBFJh/XyHADu61TDSkKI+F4IcUE31gwAtM639YImzNUhok++7//gbAsi2uM6CIKtMAy/ca7CmpDv+7tRFL3hbAtzjCzLtuI4dkIapdRZItov6qrn1xzM87y9yWTykrMt/hPaieP4M+cqSpNk5vP5sel0+pdzm9DgVyhJkpt5nr/g3CYkhLgOAK91soQ5BhFtSym/cq6iNMmjMKoV6oIT6oET0lUPRiWUJMnVPM93OQPAZa4Zc7DB73KI+EgI8Zhz27Y9+BXaOCGl1F0iuscZAHa4Zkb1yHVhVCvUBSfUAyekqx6MSmjjtm0nNHShxWJxUghRfA6I4/gn14w5mDtYO2JthbrghHrghHTVg1EJddm2lVK/iOiUbqyZ5XJ5Yjab/dGNCkqTZLoIpWl6JsuyhW6slxQAQp1qKE2S6SJUkKbpLMuyxrPBAh8A4LxODVROcsw4oaHjhIZOrZBS6hIR3eJc8+b0LddBEDwLw/AjZ8a8puoe5htaIvotpbzG3/WhSWhCRMi5ats2T/G6nw/mNTX3MI+HVwBw47DuRWkAE0T8IoTYLuqayVgVqvr+qLTeABEvEtEDKeU53TwEEQ/+UC7wff9hFEXvODPmNTVvX+8Q0Wkp5RPdXIFWobHhhIbOxgn9A+2gQlN4dCYWAAAAAElFTkSuQmCC'''

config = configparser.ConfigParser(interpolation=None)

CURRENT_SETTINGS = {
    'style': 'Default Dark',
    'animation_in': 'Slide Up + Fade',
    'animation_out': 'Slide Down + Fade',
    'x_rule': 'default',
    'y_rule': 'default',
    'x_val': 0,
    'y_val': 0,
    'pos_anchor': 'se',
    'language': 'en-US.ini',
    'hide_from_capture': False,
    'pw_hide_from_toast': True,
    'pw_show_on_hover': False,
    'pw_hover_seconds': 2,
    'pw_hide_from_capture': True,
    'pw_pending_open_editor': False,
    'pw_lock_on_close': False,
    'pw_lock_after_time': False,
    'pw_lock_timeout': 3600,
}

APP_ID = "gay.eh.clipboard"
FRIENDLY_NAME = "EhClipboard"
DISPLAY_NAME = "Eh's Clipboard"

def register_app_user_model_id():
    try:
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, fr"Software\Classes\AppUserModelId\{APP_ID}")
        winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, DISPLAY_NAME)
        icon_path = os.path.join(APP_DATA_PATH, 'icon.ico')
        winreg.SetValueEx(key, "IconUri", 0, winreg.REG_SZ, icon_path)
        winreg.CloseKey(key)
    except Exception:
        pass

def get_app_display_name_from_registry():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, fr"Software\Classes\AppUserModelId\{APP_ID}")
        display_name, _ = winreg.QueryValueEx(key, "DisplayName")
        winreg.CloseKey(key)
        return display_name
    except Exception:
        return DISPLAY_NAME

def get_app_icon_uri_from_registry():
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, fr"Software\Classes\AppUserModelId\{APP_ID}")
        icon_uri, _ = winreg.QueryValueEx(key, "IconUri")
        winreg.CloseKey(key)
        return icon_uri
    except Exception:
        return None

def find_icon_path():
    appdata_icon = os.path.join(APP_DATA_PATH, 'icon.ico')
    if os.path.exists(appdata_icon):
        return appdata_icon
    
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
    else:
        exe_dir = os.path.dirname(os.path.abspath(__file__))
    exe_icon = os.path.join(exe_dir, 'icon.ico')
    if os.path.exists(exe_icon):
        return exe_icon
    
    registry_icon = get_app_icon_uri_from_registry()
    if registry_icon and os.path.exists(registry_icon):
        return registry_icon
    
    return None

def set_app_user_model_id():
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass

last_text = ""
toast = None
fade_out_job = None
screen_width = 0
screen_height = 0
app_icon = None
app_photo_icon = None
UPDATE_AND_QUIT_FLAG = threading.Event()
_options_process = None
_about_process = None
_tk_queue = queue.Queue()

def show_error_messagebox(title, message):
    """Displays a Tkinter error messagebox, ensuring it's top-level and has the app icon."""
    temp_root = tk.Tk()
    temp_root.withdraw()
    
    if app_photo_icon:
        try:
            temp_root.iconphoto(False, app_photo_icon)
        except tk.TclError:
            pass
    
    messagebox.showerror(title=title, message=message, parent=temp_root)
    temp_root.destroy()

def _animate(window, duration, update_callback, on_done=None):
    start_time = time.time()

    def step():
        if not window.winfo_exists():
            return
        elapsed = time.time() - start_time
        fraction = min(elapsed / duration, 1.0)
        eased_fraction = 1 - (1 - fraction) ** 2
        try:
            update_callback(eased_fraction)
        except tk.TclError:
            return
        if fraction < 1.0:
            root.after(15, step)
        elif on_done:
            on_done()
    step()

def an_slide_fade_in(window, w, h, x, y):
    y_start = screen_height
    window.attributes("-alpha", 0)
    def update(fraction):
        curr_y = int(y_start - (y_start - y) * fraction)
        window.geometry(f"{w}x{h}+{x}+{curr_y}")
        window.attributes("-alpha", fraction)
    _animate(window, 0.25, update)

def an_slide_fade_out(window, w, h, x, y):
    if not window.winfo_exists(): return
    y_start = window.winfo_y()
    x_pos = window.winfo_x()
    y_end = screen_height
    def update(fraction):
        curr_y = int(y_start + (y_end - y_start) * fraction)
        window.geometry(f"{w}x{h}+{x_pos}+{curr_y}")
        window.attributes("-alpha", 1.0 - fraction)
    _animate(window, 0.25, update)

def an_fade_in(window, w, h, x, y):
    window.geometry(f"{w}x{h}+{x}+{y}")
    window.attributes("-alpha", 0)
    def update(fraction):
        window.attributes("-alpha", fraction)
    _animate(window, 0.15, update)

def an_fade_out(window, w, h, x, y):
    def update(fraction):
        window.attributes("-alpha", 1.0 - fraction)
    _animate(window, 0.15, update)

def an_zoom_in(window, w, h, x, y):
    window.attributes("-alpha", 0)
    def update(fraction):
        curr_w = max(1, int(w * fraction))
        curr_h = max(1, int(h * fraction))
        curr_x = x + (w - curr_w) // 2
        curr_y = y + (h - curr_h) // 2
        window.geometry(f"{curr_w}x{curr_h}+{curr_x}+{curr_y}")
        window.attributes("-alpha", fraction)
    _animate(window, 0.20, update)

def an_zoom_out(window, w, h, x, y):
    def update(fraction):
        prog = 1.0 - fraction
        curr_w = max(1, int(w * prog))
        curr_h = max(1, int(h * prog))
        curr_x = x + (w - curr_w) // 2
        curr_y = y + (h - curr_h) // 2
        window.geometry(f"{curr_w}x{curr_h}+{curr_x}+{curr_y}")
        window.attributes("-alpha", prog)
    _animate(window, 0.20, update)

def an_slide_left_in(window, w, h, x, y):
    x_start = screen_width
    window.attributes("-alpha", 0)
    def update(fraction):
        curr_x = int(x_start - (x_start - x) * fraction)
        window.geometry(f"{w}x{h}+{curr_x}+{y}")
        window.attributes("-alpha", fraction)
    _animate(window, 0.20, update)

def an_slide_right_out(window, w, h, x, y):
    if not window.winfo_exists(): return
    x_start = window.winfo_x()
    y_pos = window.winfo_y()
    x_end = screen_width
    def update(fraction):
        curr_x = int(x_start + (x_end - x_start) * fraction)
        window.geometry(f"{w}x{h}+{curr_x}+{y_pos}")
        window.attributes("-alpha", 1.0 - fraction)
    _animate(window, 0.20, update)

ANIMATIONS_IN = {
    "Slide Up + Fade": an_slide_fade_in,
    "Fade In": an_fade_in,
    "Zoom In": an_zoom_in,
    "Slide In From Right": an_slide_left_in,
}

ANIMATIONS_OUT = {
    "Slide Down + Fade": an_slide_fade_out,
    "Fade Out": an_fade_out,
    "Zoom Out": an_zoom_out,
    "Slide Out To Right": an_slide_right_out,
}

def animate_resize(window, new_w, new_h, duration=0.15):
    if not window.winfo_exists(): return
    start_w = window.winfo_width()
    start_h = window.winfo_height()
    start_x = window.winfo_x()
    start_y = window.winfo_y()
    anchor = CURRENT_SETTINGS.get('pos_anchor', 'se')
    delta_w = new_w - start_w
    delta_h = new_h - start_h

    def update(fraction):
        curr_w = int(start_w + delta_w * fraction)
        curr_h = int(start_h + delta_h * fraction)
        if 'n' in anchor: curr_y = start_y
        else: curr_y = start_y + (start_h - curr_h)
        if 'w' in anchor: curr_x = start_x
        else: curr_x = start_x + (start_w - curr_w)
        window.geometry(f"{curr_w}x{curr_h}+{curr_x}+{curr_y}")
    _animate(window, duration, update)

STYLES = {}
ANIMATION_SETS = {}

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            config.read(CONFIG_FILE, encoding='utf-8-sig')
            if 'Settings' in config:
                settings = config['Settings']
                CURRENT_SETTINGS['style'] = settings.get('style', CURRENT_SETTINGS['style'])
                CURRENT_SETTINGS['animation_in'] = settings.get('animation_in', CURRENT_SETTINGS['animation_in'])
                CURRENT_SETTINGS['animation_out'] = settings.get('animation_out', CURRENT_SETTINGS['animation_out'])
                CURRENT_SETTINGS['x_rule'] = settings.get('x_rule', CURRENT_SETTINGS['x_rule'])
                CURRENT_SETTINGS['y_rule'] = settings.get('y_rule', CURRENT_SETTINGS['y_rule'])
                CURRENT_SETTINGS['x_val'] = settings.getint('x_val', CURRENT_SETTINGS['x_val'])
                CURRENT_SETTINGS['y_val'] = settings.getint('y_val', CURRENT_SETTINGS['y_val'])
                CURRENT_SETTINGS['pos_anchor'] = settings.get('pos_anchor', CURRENT_SETTINGS['pos_anchor'])
                CURRENT_SETTINGS['language'] = settings.get('language', CURRENT_SETTINGS.get('language'))
                try:
                    CURRENT_SETTINGS['hide_from_capture'] = settings.getboolean('hide_from_capture', CURRENT_SETTINGS.get('hide_from_capture', False))
                except Exception:
                    CURRENT_SETTINGS['hide_from_capture'] = False
            if 'Passwords' in config:
                p = config['Passwords']
                CURRENT_SETTINGS['pw_hide_from_toast'] = p.getboolean('hide_passwords_from_toast', CURRENT_SETTINGS.get('pw_hide_from_toast', True))
                CURRENT_SETTINGS['pw_show_on_hover'] = p.getboolean('show_passwords_on_hover', CURRENT_SETTINGS.get('pw_show_on_hover', False))
                CURRENT_SETTINGS['pw_hover_seconds'] = p.getint('hover_reveal_seconds', CURRENT_SETTINGS.get('pw_hover_seconds', 2))
                CURRENT_SETTINGS['pw_hide_from_capture'] = p.getboolean('hide_passwords_from_capture', CURRENT_SETTINGS.get('pw_hide_from_capture', True))
                CURRENT_SETTINGS['pw_pending_open_editor'] = p.getboolean('pending_open_editor', CURRENT_SETTINGS.get('pw_pending_open_editor', False))
                CURRENT_SETTINGS['pw_lock_on_close'] = p.getboolean('lock_on_close', CURRENT_SETTINGS.get('pw_lock_on_close', False))
                CURRENT_SETTINGS['pw_lock_after_time'] = p.getboolean('lock_after_time', CURRENT_SETTINGS.get('pw_lock_after_time', False))
                CURRENT_SETTINGS['pw_lock_timeout'] = p.getint('lock_timeout', CURRENT_SETTINGS.get('pw_lock_timeout', 3600))
        except Exception as e:
            show_error_messagebox("Config File Error", f"Failed to load or parse '{CONFIG_FILE}'.\nUsing default settings.\n\nError: {e}")

def save_config():
    try:
        os.makedirs(APP_DATA_PATH, exist_ok=True)
        config['Settings'] = {k: str(v) for k, v in CURRENT_SETTINGS.items() if not k.startswith('pw_')}
        config['Passwords'] = {
            'hide_passwords_from_toast': str(CURRENT_SETTINGS.get('pw_hide_from_toast', True)),
            'show_passwords_on_hover': str(CURRENT_SETTINGS.get('pw_show_on_hover', False)),
            'hover_reveal_seconds': str(CURRENT_SETTINGS.get('pw_hover_seconds', 2)),
            'hide_passwords_from_capture': str(CURRENT_SETTINGS.get('pw_hide_from_capture', True)),
            'pending_open_editor': str(CURRENT_SETTINGS.get('pw_pending_open_editor', False)),
            'lock_on_close': str(CURRENT_SETTINGS.get('pw_lock_on_close', False)),
            'lock_after_time': str(CURRENT_SETTINGS.get('pw_lock_after_time', False)),
            'lock_timeout': str(CURRENT_SETTINGS.get('pw_lock_timeout', 3600)),
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
            config.write(configfile)
    except Exception as e:
        show_error_messagebox("Save Config Error", f"Could not save settings to '{CONFIG_FILE}'.\n\nError: {e}")

def refresh_settings_from_disk():
    if not os.path.exists(CONFIG_FILE):
        return
    try:
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(CONFIG_FILE, encoding='utf-8-sig')
        if 'Settings' not in cp:
            return
        s = cp['Settings']
        prev_lang = CURRENT_SETTINGS.get('language')
        readers = {
            'style': lambda: s.get('style', CURRENT_SETTINGS['style']),
            'animation_in': lambda: s.get('animation_in', CURRENT_SETTINGS['animation_in']),
            'animation_out': lambda: s.get('animation_out', CURRENT_SETTINGS['animation_out']),
            'x_rule': lambda: s.get('x_rule', CURRENT_SETTINGS['x_rule']),
            'y_rule': lambda: s.get('y_rule', CURRENT_SETTINGS['y_rule']),
            'x_val': lambda: s.getint('x_val', CURRENT_SETTINGS['x_val']),
            'y_val': lambda: s.getint('y_val', CURRENT_SETTINGS['y_val']),
            'pos_anchor': lambda: s.get('pos_anchor', CURRENT_SETTINGS['pos_anchor']),
            'language': lambda: s.get('language', CURRENT_SETTINGS['language']),
            'hide_from_capture': lambda: s.getboolean('hide_from_capture', CURRENT_SETTINGS.get('hide_from_capture', False)),
        }
        for key, reader in readers.items():
            try:
                CURRENT_SETTINGS[key] = reader()
            except Exception:
                pass
        if 'Passwords' in cp:
            p = cp['Passwords']
            pw_readers = {
                'pw_hide_from_toast': lambda: p.getboolean('hide_passwords_from_toast', CURRENT_SETTINGS.get('pw_hide_from_toast', True)),
                'pw_show_on_hover': lambda: p.getboolean('show_passwords_on_hover', CURRENT_SETTINGS.get('pw_show_on_hover', False)),
                'pw_hover_seconds': lambda: p.getint('hover_reveal_seconds', CURRENT_SETTINGS.get('pw_hover_seconds', 2)),
                'pw_hide_from_capture': lambda: p.getboolean('hide_passwords_from_capture', CURRENT_SETTINGS.get('pw_hide_from_capture', True)),
                'pw_pending_open_editor': lambda: p.getboolean('pending_open_editor', CURRENT_SETTINGS.get('pw_pending_open_editor', False)),
                'pw_lock_on_close': lambda: p.getboolean('lock_on_close', CURRENT_SETTINGS.get('pw_lock_on_close', False)),
                'pw_lock_after_time': lambda: p.getboolean('lock_after_time', CURRENT_SETTINGS.get('pw_lock_after_time', False)),
                'pw_lock_timeout': lambda: p.getint('lock_timeout', CURRENT_SETTINGS.get('pw_lock_timeout', 3600)),
            }
            for key, reader in pw_readers.items():
                try:
                    CURRENT_SETTINGS[key] = reader()
                except Exception:
                    pass
        if CURRENT_SETTINGS.get('language') != prev_lang:
            try:
                load_messages()
                update_systray_menu()
            except Exception:
                pass
    except Exception:
        pass

def load_builtin_styles():
    STYLES.clear()
    STYLES['Default Dark'] = {'look': {'bg': '#333333', 'fg': 'white', 'border': '#888888', 'font': ('Arial', 12)}, 'animation_in': 'Slide Up + Fade', 'animation_out': 'Slide Down + Fade', 'position': {'x_rule': 'default', 'y_rule': 'default', 'x_val': 0, 'y_val': 0, 'anchor': 'se'}}
    STYLES['Light'] = {'look': {'bg': '#f0f0f0', 'fg': 'black', 'border': '#b0b0b0', 'font': ('Arial', 12)}, 'animation_in': 'Fade In', 'animation_out': 'Fade Out', 'position': {'x_rule': 'default', 'y_rule': 'default', 'x_val': 0, 'y_val': 0, 'anchor': 'se'}}

def load_styles_from_folder():
    styles_dir = os.path.join(APP_DATA_PATH, 'Styles')
    if not os.path.isdir(styles_dir): return
    for entry in os.listdir(styles_dir):
        full = os.path.join(styles_dir, entry)
        if os.path.isdir(full):
            cfg_path = os.path.join(full, 'config.ini')
            if os.path.exists(cfg_path):
                try:
                    cp = configparser.ConfigParser(interpolation=None)
                    cp.read(cfg_path, encoding='utf-8-sig')
                    if 'Style' in cp:
                        s = cp['Style']
                        STYLES[entry] = {
                            'look': {'bg': s.get('bg', '#333333'), 'fg': s.get('fg', 'white'), 'border': s.get('border', '#888888'), 'font': (s.get('font_name', 'Arial'), s.getint('font_size', 12))},
                            'animation_in': s.get('animation_in', CURRENT_SETTINGS['animation_in']),
                            'animation_out': s.get('animation_out', CURRENT_SETTINGS['animation_out']),
                            'position': {'x_rule': s.get('x_rule', 'default'), 'y_rule': s.get('y_rule', 'default'), 'x_val': s.getint('x_val', 0), 'y_val': s.getint('y_val', 0), 'anchor': s.get('anchor', 'se')}
                        }
                except Exception as e:
                    show_error_messagebox("Style Loading Error", f"Failed to load style from '{cfg_path}'.\n\nError: {e}")

def load_animation_sets_from_folder():
    ANIMATION_SETS.clear()
    anim_dir = os.path.join(APP_DATA_PATH, 'Animations')
    if not os.path.isdir(anim_dir): return
    for entry in os.listdir(anim_dir):
        full = os.path.join(anim_dir, entry)
        if os.path.isdir(full):
            cfg_path = os.path.join(full, 'config.ini')
            if os.path.exists(cfg_path):
                try:
                    cp = configparser.ConfigParser(interpolation=None)
                    cp.read(cfg_path, encoding='utf-8-sig')
                    if 'AnimationSet' in cp:
                        s = cp['AnimationSet']
                        if s.get('animation_in') in ANIMATIONS_IN and s.get('animation_out') in ANIMATIONS_OUT:
                            name = s.get('name', entry)
                            ANIMATION_SETS[name] = {'animation_in': s.get('animation_in'), 'animation_out': s.get('animation_out')}
                            try:
                                in_name = s.get('animation_in')
                                out_name = s.get('animation_out')
                                params = {}
                                if 'in_offset_x' in s: params['in_offset_x'] = s.getint('in_offset_x')
                                if 'in_offset_y' in s: params['in_offset_y'] = s.getint('in_offset_y')
                                if 'out_offset_x' in s: params['out_offset_x'] = s.getint('out_offset_x')
                                if 'out_offset_y' in s: params['out_offset_y'] = s.getint('out_offset_y')
                                if params:
                                    CUSTOM_ANIM_PARAMS[in_name] = {'in_offset_x': params.get('in_offset_x', 0), 'in_offset_y': params.get('in_offset_y', 0)}
                                    CUSTOM_ANIM_PARAMS[out_name] = {'out_offset_x': params.get('out_offset_x', 0), 'out_offset_y': params.get('out_offset_y', 0)}
                            except Exception:
                                pass
                            try:
                                if 'In' in cp:
                                    ANIMATION_SETS[name]['in_keyframes'] = dict(cp['In'])
                                if 'Out' in cp:
                                    ANIMATION_SETS[name]['out_keyframes'] = dict(cp['Out'])
                            except Exception:
                                pass
                except Exception as e:
                    show_error_messagebox("Animation Set Loading Error", f"Failed to load animation set from '{cfg_path}'.\n\nError: {e}")

LANGS = {}
DEFAULT_MESSAGES = {'CopiedSuffix': 'has been copied to the clipboard', 'PreviewText': '"Preview..." has been copied to the clipboard'}
MESSAGES = DEFAULT_MESSAGES.copy()
DEFAULT_UI = {
    'SetPosition': 'Set Position', 'Style': 'Style', 'AnimationIn': 'Animation In', 'AnimationOut': 'Animation Out', 
    'AnimationSet': 'Animation Set', 'Language': 'Language', 'EditSettings': "Edit Program's Settings", 
    'EditConfig': 'Edit config.ini', 'OpenStyles': 'Open Styles Folder', 'OpenLangs': 'Open Languages Folder', 
    'OpenGlobal': 'Open Global Folder', 'OpenAnims': 'Open Animations Folder', 'Quit': 'Quit', 'About': 'About', 
    'SavePosition': 'Save Position', 'Cancel': 'Cancel', 'Error': 'Error', 'Yes': 'Yes', 'No': 'No', 'CapsLockOn': 'Caps Lock is on!', 
    'PositionerInstructions': 'Click and drag to select the notification area\nPress Ctrl+Shift+R to reset to default',
    'CheckForUpdates': 'Check for Updates', 'AboutWindowTitle': "About eh's Clipboard",
    'AboutTab': 'About', 'UpdatesTab': 'Updates', 'LicenseTab': 'License', 'UpdateNow': 'Update Now',
    'LicensesWindowTitle': 'Third-Party Licenses', 'LicensesHeader': "Third-party open source licenses used by eh's Clipboard",
    'DeltaruneLicenseTitle': 'Deltarune Sounds', 'DeltaruneCopyright': 'Copyright (c) Toby Fox',
    'DeltaruneLicenseBody': 'The Deltarune sounds, including Flowery\'s Voices and its sprite, and Spamton\'s sprites, included in Eh\'s Clipboard ("Official Builds by the source"), custom copies or forks of this program ("Forks"), or custom-built programs made for a machine or to add something ("Private Builds"), are part of DELTARUNE, which is owned by Toby Fox.',
    'ViewOnGitHub': 'View Release on GitHub', 'CheckingForUpdates': 'Checking for updates...',
    'UpdateInitialPrompt': "Press 'Check for Updates' to see if a new version is available.",
    'UpdateNewVersion': 'New version available: {latest_tag} (you are {behind} version(s) behind, running {current_version})',
    'UpdateLatest': 'You are running the latest version!', 'UpdateFailed': "Failed to fetch update: {error}",
    'UpdateMSStoreMessage': 'Updates are automatically managed by the Microsoft Store',
    'UpdateMSStoreButton': 'Open Store Updates',
    'FirstRunToastTitle': "eh's Clipboard",
    'FirstRunToastMessage': "You're good to go, this program runs on the system tray, try copying something!",
    'UpdateNoReleases': 'No releases found.', 'DownloadPreparing': 'Preparing download...',
    'DownloadStatus': 'Downloading... {downloaded} / {total} ({speed}, ETA: {eta})',
    'DownloadComplete': 'Download complete. Starting installer...',
    'DownloadInstallerFailed': 'Failed to run installer: {error}', 'DownloadFailedGeneric': 'Download failed: {error}',
    'Options': 'Options',
    'OptionsWindowTitle': "eh's Clipboard Options",
    'GeneralTab': 'General', 'PositionTab': 'Position', 'PrivacyTab': 'Privacy',
    'XRuleLabel': 'X Rule', 'YRuleLabel': 'Y Rule', 'XValueLabel': 'X Value', 'YValueLabel': 'Y Value',
    'PosAnchorLabel': 'Position Anchor',
    'HideFromCapture': 'Hide Toast from being screenshotted',
    'HideFromCaptureUnsupported': "This feature isn't for your version of Windows ({WindowsVer}), it requires the Windows 10 2020 Update (19041)",
    'HelpStyle': 'The look of the toast notification.',
    'HelpAnimationIn': 'Animation used when the toast appears.',
    'HelpAnimationOut': 'Animation used when the toast disappears.',
    'HelpXRule': 'The position of the X is calculated (default = near its right edge, absolute = fixed number of pixels, edge = distance from the right edge)',
    'HelpYRule': 'The position of the Y is calculated (default = near the bottom, absolute = fixed number of pixels, edge = distance from its bottom)',
    'HelpXValue': 'Value of the X Rule when it is absolute or edge',
    'HelpYValue': 'Value of the Y Rule when it is absolute or edge',
    'HelpPosAnchor': 'Corner or the edge where it stays fixed',
    'HelpLanguage': 'Language used for the program interface.',
    'HelpHideFromCapture': 'When on, the toast will be hidden from screenshots and screen recorders (when possible)',
    'PasswordsSection': 'Passwords',
    'PasswordsSetupTitle': 'Set up password vault',
    'PasswordsVaultName': 'Password Vault',
    'PasswordsWizardIntroTitle': "What's This?",
    'PasswordsWizardIntroBody': 'The Password Vault is an option that allows you to hide your passwords from being shown on screen into the toast notification on screen by accident, either to someone, or to an capture or screen recording\n\nIt is easy, simply add the passwords, and it will hide it, that\'s it\n\nThe Password Vault itself is hidden from screenshots or screen recorders',
    'PasswordsImportSourceTitle': 'Where do you import passwords?',
    'PasswordsImportSourceSubtitle': 'Choose how you want the passwords to be setup',
    'PasswordsImportFromBrowser': 'Import passwords from my browsers or a file',
    'PasswordsImportNone': 'Do not import any password',
    'PasswordsImportDetailsTitle': 'Importing passwords',
    'PasswordsImportDetailsSubtitle': 'Choose how to import the passwords',
    'PasswordsImportDetailsDesc': 'Choose where you want to import the passwords from',
    'PasswordsImportSourceBrowser': 'Browser',
    'PasswordsImportSourceFile': 'Via a file',
    'PasswordsImportProfileLabel': 'Profile',
    'PasswordsImportAllProfiles': 'All profiles',
    'PasswordsImportFileLabel': 'Passwords file to import',
    'PasswordsImportBrowse': 'Browse...',
    'PasswordsImportFileFilter': 'CSV files (*.csv)',
    'PasswordsImportNoBrowser': 'No supported browsers were found on this PC.',
    'PasswordsAccessTitle': 'How do you access your vault?',
    'PasswordsAccessSubtitle': 'Option to access your vault',
    'PasswordsAccessDesc': 'Now you need to setup some option to access your vault!',
    'PasswordsAccessMasterOnly': 'Master Password',
    'PasswordsAccess2FA': '2FA Code',
    'PasswordsMasterPageTitle': 'Master Password',
    'PasswordsMasterPageSubtitle': 'Type your Master Password',
    'PasswordsMasterPageHint': 'Your Master Password must be unique and not exactly the same as your passwords you use!',
    'PasswordsMasterPageHint2': 'For the privacy, also, the password is not visible so choose something you will remember!',
    'PasswordsMasterPassword': 'Master password',
    'PasswordsMasterPasswordConfirm': 'Repeat master password',
    'PasswordsPasswordTooShort': 'Master password must be at least 8 characters.',
    'PasswordsPasswordMismatch': 'Passwords do not match.',
    'PasswordsPasswordRepeat': 'Now repeat your master password',
    'PasswordsPasswordMatches': 'Passwords match',
    'PasswordsTOTPTitle': 'Set Up 2FA',
    'PasswordsTOTPSubtitle': 'Use 2FA to unlock the vault',
    'PasswordsTOTPInstructions': 'Scan the QR code or add the secret to your authenticator app (like Bitwarden or Google Authenticator) then type the code below:',
    'PasswordsTOTPCodeLabel': 'Code:',
    'PasswordsTOTPCodePlaceholder': 'Code',
    'PasswordsTOTPValid': 'Code accepted!',
    'PasswordsTOTPInvalid': 'That code is not valid, check the app and try again.',
    'PasswordsVaultNameTitle': 'Your Vault Name',
    'PasswordsVaultNameSubtitle': 'A Name for your Vault!',
    'PasswordsVaultNameLabel': 'The Vault name is not necessary, but it gives you a little reminder if when setting up the 2FA codes',
    'PasswordsVaultNamePlaceholder': 'Cool Vault...',
    'PasswordsTOTPAccount': 'Vault for {vaultName}',
    'PasswordsTOTPAccountFallback': 'User',
    'PasswordsBackupCodesTitle': 'Your backup codes',
    'PasswordsBackupCodesSubtitle': 'Save those!',
    'PasswordsBackupCodesHint': 'Those are your backup codes for when you can\'t have access, make sure you save those securely! (Like a USB)',
    'PasswordsBackupCodesNote': 'Those codes can be used once (15 each)',
    'PasswordsBackupCodesDone': 'I saved them',
    'PasswordsBackupCodesSave': 'Save codes to a file',
    'PasswordsBackupCodesFileTitle': 'Save backup codes',
    'PasswordsBackupCodesFile': 'Those are your backup codes for accessing your {vaultName} vault, make sure those are entirely safe! {codes}',
    'PasswordsBackupCodesSaveFailed': 'Could not save the file.',
    'PasswordsImportConfirmTitle': 'Import passwords?',
    'PasswordsImportConfirm': 'Import {count} {passwords} into your vault?',
    'PasswordsWordOne': 'password',
    'PasswordsWordMany': 'passwords',
    'PasswordsSetupCreate': 'Create Vault',
    'PasswordsUnlockTitle': 'Unlock your vault',
    'PasswordsUnlockMasterLabel': 'Type your master password to unlock your vault',
    'PasswordsUnlockTOTPLabel': 'Type your 2FA code to unlock your vault',
    'PasswordsUnlockBackupLabel': 'Type your backup code to unlock your vault',
    'PasswordsForgotThatOne': 'Forgot that one?',
    'PasswordsUnlockTOTPButton': '2FA Code',
    'PasswordsUnlockBackupButton': 'Backup code',
    'PasswordsBackupCodePlaceholder': 'Backup code',
    'PasswordsNoBackupCodes': 'No backup codes left.',
    'PasswordsUnlockButton': 'Unlock',
    'PasswordsWrongPassword': 'Wrong master password.',
    'PasswordsWrongTOTP': 'Wrong 2FA code.',
    'PasswordsWrongBackup': 'That backup code does not match, or was already used.',
    'PasswordsBackupCodesLeft': '{count} backup {codes} left.',
    'PasswordsBackupCodeWordOne': 'code',
    'PasswordsBackupCodeWordMany': 'codes',
    'PasswordsRegenerateBackupCodes': 'Regenerate backup codes',
    'PasswordsRegenerateTitle': 'Regenerate backup codes',
    'PasswordsRegenerateConfirmTitle': 'Regenerate backup codes?',
    'PasswordsRegenerateConfirmBody': 'This will change your backup codes to new ones and makes your other ones invalid, are you sure?',
    'PasswordsRegenerateTOTPLabel': 'Type your 2FA code to continue',
    'PasswordsTOTPCode': '2FA code',
    'PasswordsOpenEditor': 'Open passwords',
    'PasswordsLockVault': 'Lock vault',
    'PasswordsChangeMaster': 'Change master password',
    'PasswordsChangeMasterTitle': 'Change master password',
    'PasswordsChangeMasterHint': 'Type your current master password, then set a new one',
    'PasswordsChangeMasterOld': 'Current master password',
    'PasswordsChangeMasterNew': 'New master password',
    'PasswordsChangeMasterRepeat': 'Repeat new master password',
    'PasswordsChangeMasterButton': 'Change',
    'PasswordsChangeMasterEnterOld': 'Type your current master password first.',
    'PasswordsChangeMasterDoneTitle': 'Changed',
    'PasswordsChangeMasterDone': 'Your master password was changed.',
    'PasswordsDisable': 'Disable vault',
    'PasswordsHideFromToast': 'Hide passwords from the toast',
    'PasswordsShowOnHover': 'Reveal passwords when hovering the toast',
    'PasswordsHideFromCapture': 'Hide passwords from being captured',
    'PasswordsLockOnClose': 'Lock your vault right after you close it',
    'PasswordsLockAfterTime': 'Lock your vault after a certain time',
    'PasswordsLockDuration': 'Auto-lock after',
    'PasswordsLockTime1Hour': '1 Hour',
    'PasswordsLockTime5Hours': '5 Hours',
    'PasswordsLockTime8Hours': '8 Hours',
    'PasswordsLockTime1Day': '1 Day',
    'PasswordsLockTime5Days': '5 Days',
    'PasswordsLockTime1Week': '1 Week',
    'HelpPasswordsHideToast': 'When on, any password stored in your vault is hidden when it shows up on the toast',
    'HelpPasswordsShowOnHover': 'When on, hovering the toast reveals the hidden passwords for a few seconds',
    'HelpPasswordsHideFromCapture': 'When on, the vault windows are hidden from screenshots and screen recorders (when possible)',
    'HelpPasswordsLockOnClose': 'Simply lock the vault the moment you close that',
    'HelpPasswordsLockAfterTime': 'Lock the vault after a certain time the moment it is unlocked',
    'HelpPasswordsLockDuration': 'How long the vault stays unlocked before it locks by itself',
    'HelpPasswordsOpenEditor': 'Opens your vault to add, edit, delete or import passwords',
    'HelpPasswordsDisable': 'Deletes your vault permanently!',
    'PasswordsDisableVaultTitle': 'Disable your vault?',
    'PasswordsDisableVaultMessage': 'Disabling your vault means deleting, so all of your {count} {passwords} will be gone forever! Are you sure you gonna do this?',
    'PasswordsShowSecret': 'Show secret',
    'PasswordsCopySecret': 'Copy secret',
    'PasswordsOpenAuthLink': 'Open authenticator link',
    'PasswordsAppName': "Eh's Clipboard",
    'PasswordsEntryDialogTitle': 'Password entry',
    'PasswordsEntryName': 'Name',
    'PasswordsEntryUsername': 'Username',
    'PasswordsEntryPassword': 'Password',
    'PasswordsShowPassword': 'Show password',
    'PasswordsEntryHideCapture': 'Hide this password from being captured',
    'PasswordsSave': 'Save',
    'PasswordsEmptyName': 'Name cannot be empty.',
    'PasswordsEditorTitle': 'Passwords',
    'PasswordsSearchPlaceholder': 'Search...',
    'PasswordsAdd': 'Add',
    'PasswordsImportButton': 'Import',
    'PasswordsImportNothing': 'No passwords to import.',
    'PasswordsEdit': 'Edit',
    'PasswordsDelete': 'Delete',
    'PasswordsEmpty': 'No entries yet.',
    'PasswordsDeleteConfirmTitle': 'Delete entry',
    'PasswordsDeleteConfirmBody': 'Delete this entry?',
    'OK': 'OK'
}
UI = DEFAULT_UI.copy()

CUSTOM_ANIM_PARAMS = {}

def parse_lang_display_from_file(path):
    try:
        cp = configparser.ConfigParser(interpolation=None)
        cp.read(path, encoding='utf-8-sig')
        if 'Language' in cp and 'LangNameDisplay' in cp['Language']:
            return cp['Language']['LangNameDisplay']
    except Exception as e:
        print(f"Error parsing language display name from {path}: {e}")
    return os.path.splitext(os.path.basename(path))[0]

def load_languages():
    LANGS.clear()
    lang_dir = os.path.join(APP_DATA_PATH, 'lang')
    for fname in os.listdir(lang_dir):
        if fname.lower().endswith('.ini'):
            full = os.path.join(lang_dir, fname)
            display = parse_lang_display_from_file(full)
            LANGS[fname] = display

def set_os_language_on_first_run():
    if IS_MSIX:
        return
    if CURRENT_SETTINGS['language'] != 'en-US.ini':
        return
    import locale
    try:
        os_lang_code = locale.getlocale()[0]
        if os_lang_code:
            os_lang_code = os_lang_code.replace('_', '-').lower()
            lang_dir = os.path.join(APP_DATA_PATH, 'lang')
            if os.path.exists(lang_dir):
                for fname in os.listdir(lang_dir):
                    if fname.lower().endswith('.ini'):
                        fname_base = fname[:-4].lower()
                        if fname_base == os_lang_code or fname_base.startswith(os_lang_code.split('-')[0]):
                            CURRENT_SETTINGS['language'] = fname
                            save_config()
                            return
    except Exception:
        pass

def _sha256_file(path):
    h = hashlib.sha256()
    try:
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(65536), b''):
                h.update(chunk)
    except Exception:
        return ''
    return h.hexdigest()


def _parse_seed_ver(path):
    manifest = {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('[') or '=' not in line:
                    continue
                key, _, value = line.partition('=')
                manifest[key.strip()] = value.strip().lower()
    except Exception:
        pass
    return manifest


def _write_seed_ver(path, manifest):
    try:
        lines = ['[seed-ver]']
        lines.extend('{} = {}'.format(k, v) for k, v in manifest.items())
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
    except Exception:
        pass


def eh_msix_default_files():
    if not IS_MSIX:
        return
    try:
        if getattr(sys, 'frozen', False):
            exe_path = sys.executable
        else:
            exe_path = os.path.abspath(__file__)
        pkg_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(exe_path))))
        src = os.path.join(pkg_root, "Defaults", "eh's Clipboard")
        seed_ver = os.path.join(src, '.seed-ver')
        if not os.path.isfile(seed_ver):
            return
        desired = _parse_seed_ver(seed_ver)
        if not desired:
            return
        stored_path = os.path.join(APP_DATA_PATH, '.seed-ver')
        stored = _parse_seed_ver(stored_path)
        migrated = not os.path.exists(stored_path)
        os.makedirs(APP_DATA_PATH, exist_ok=True)
        new_manifest = {}
        changed = migrated
        for key, value in desired.items():
            if key in ('program_sha256', 'folder_sha256'):
                new_manifest[key] = value
                continue
            s = os.path.join(src, *key.split('/'))
            d = os.path.join(APP_DATA_PATH, *key.split('/'))
            if not os.path.isfile(s):
                continue
            prev = stored.get(key)
            replace = False
            if not os.path.exists(d):
                replace = True
            elif migrated:
                replace = True
            elif prev and _sha256_file(d) == prev:
                replace = True
            if replace:
                try:
                    os.makedirs(os.path.dirname(d), exist_ok=True)
                    shutil.copy2(s, d)
                    changed = True
                except Exception:
                    pass
            new_manifest[key] = value
        if changed:
            _write_seed_ver(stored_path, new_manifest)
    except Exception:
        pass


def ensure_default_files():
    eh_msix_default_files()
    os.makedirs(APP_DATA_PATH, exist_ok=True)

    if not os.path.exists(CONFIG_FILE):
        save_config()

    for folder in ['Styles', 'Animations', 'lang']:
        os.makedirs(os.path.join(APP_DATA_PATH, folder), exist_ok=True)
    
    en_path_dest = os.path.join(APP_DATA_PATH, 'lang', 'en-US.ini')
    if not os.path.exists(en_path_dest):
        try:
            with open(en_path_dest, 'w', encoding='utf-8') as f:
                f.write('[Language]\nLangNameDisplay = English (US)\n\n[Messages]\n')
                for k, v in DEFAULT_MESSAGES.items(): f.write(f'{k} = {v}\n')
                f.write('\n[UI]\n')
                for k, v in DEFAULT_UI.items(): f.write(f'{k} = {v.replace("%", "%%").replace(chr(10), chr(10) + "  ")}\n')
        except Exception as e:
            show_error_messagebox("File Creation Error", f"Could not create default language file.\n\nError: {e}")
    
    for style_name, content in [
        ('Default Dark', '[Style]\nname = Default Dark\nbg = #333333\nfg = white\nborder = #888888\nfont_name = Arial\nfont_size = 12\nanimation_in = Slide Up + Fade\nanimation_out = Slide Down + Fade\nx_rule = default\ny_rule = default\nx_val = 0\ny_val = 0\nanchor = se\n'),
        ('Light', '[Style]\nname = Light\nbg = #f0f0f0\nfg = black\nborder = #b0b0b0\nfont_name = Arial\nfont_size = 12\nanimation_in = Fade In\nanimation_out = Fade Out\nx_rule = default\ny_rule = default\nx_val = 0\ny_val = 0\nanchor = se\n')
    ]:
        style_path = os.path.join(APP_DATA_PATH, 'Styles', style_name)
        os.makedirs(style_path, exist_ok=True)
        style_config_path = os.path.join(style_path, 'config.ini')
        if not os.path.exists(style_config_path):
            with open(style_config_path, 'w', encoding='utf-8') as f: f.write(content)

    anim_path = os.path.join(APP_DATA_PATH, 'Animations', 'Default')
    os.makedirs(anim_path, exist_ok=True)
    anim_config_path = os.path.join(anim_path, 'config.ini')
    if not os.path.exists(anim_config_path):
        with open(anim_config_path, 'w', encoding='utf-8') as f:
            f.write('[AnimationSet]\n')
            f.write('name = Default\n')
            f.write('animation_in = Slide Up + Fade\n')
            f.write('animation_out = Slide Down + Fade\n')
            f.write('in_offset_x = 0\n')
            f.write('in_offset_y = 0\n')
            f.write('out_offset_x = 0\n')
            f.write('out_offset_y = 0\n\n')
            f.write('[In]\n')
            f.write('# Keyframes for IN animation. Use any keys describing properties.\n')
            f.write('frame1 = pos=se;seconds=0.0;offset_x=0;offset_y=0\n\n')
            f.write('[Out]\n')
            f.write('# Keyframes for OUT animation.\n')
            f.write('frame1 = pos=se;seconds=0.25;offset_x=0;offset_y=0\n')
    first_run_flag = os.path.join(APP_DATA_PATH, '.first_run_shown')
    if not os.path.exists(first_run_flag):
        set_os_language_on_first_run()
        load_messages()
        register_app_user_model_id()
        set_app_user_model_id()
        
        if IS_MSIX:
            title_text = UI.get('FirstRunToastTitle', "eh's Clipboard")
            message_text = UI.get('FirstRunToastMessage', "You're good to go, this program runs on the system tray, try copying something!")
            try:
                notification = Notification(
                    app_id="Eh's Clipboard",
                    title=title_text,
                    msg=message_text,
                    duration="short"
                )
                notification.set_audio(audio.Default, loop=False)
                notification.show()
                try: open(first_run_flag, 'w', encoding='utf-8').close()
                except Exception: pass
            except Exception:
                pass
        else:
            icon_path = find_icon_path()
            if icon_path:
                title_text = UI.get('FirstRunToastTitle', "eh's Clipboard")
                message_text = UI.get('FirstRunToastMessage', "You're good to go, this program runs on the system tray, try copying something!")
                try:
                    notification = Notification(
                        app_id=APP_ID,
                        title=title_text,
                        msg=message_text,
                        duration="short",
                        icon=icon_path
                    )
                    notification.set_audio(audio.Default, loop=False)
                    notification.show()
                    try: open(first_run_flag, 'w', encoding='utf-8').close()
                    except Exception: pass
                except Exception:
                    pass

def ensure_ini_defaults():
    lang_dir = os.path.join(APP_DATA_PATH, 'lang')
    if os.path.exists(lang_dir):
        for fname in os.listdir(lang_dir):
            if not fname.lower().endswith('.ini'): continue
            path = os.path.join(lang_dir, fname)
            try:
                cp = configparser.ConfigParser(interpolation=None, strict=False)
                cp.optionxform = str
                cp.read(path, encoding='utf-8-sig')
                changed = False
                if 'UI' not in cp: cp['UI'] = {}; changed = True
                for k, v in DEFAULT_UI.items():
                    if k not in cp['UI']: cp['UI'][k] = str(v); changed = True

                if 'Messages' not in cp: cp['Messages'] = {}; changed = True
                for k, v in DEFAULT_MESSAGES.items():
                    if k not in cp['Messages']: cp['Messages'][k] = str(v); changed = True

                if changed:
                    with open(path, 'w', encoding='utf-8') as f: cp.write(f)
            except Exception: pass

    styles_dir = os.path.join(APP_DATA_PATH, 'Styles')
    if os.path.exists(styles_dir):
        for entry in os.listdir(styles_dir):
            full = os.path.join(styles_dir, entry)
            if not os.path.isdir(full): continue
            cfg_path = os.path.join(full, 'config.ini')

            defaults = {'name': entry, 'bg': '#333333', 'fg': 'white', 'border': '#888888', 'font_name': 'Arial', 'font_size': '12', 'animation_in': 'Slide Up + Fade', 'animation_out': 'Slide Down + Fade', 'x_rule': 'default', 'y_rule': 'default', 'x_val': '0', 'y_val': '0', 'anchor': 'se'}

            if not os.path.exists(cfg_path):
                try:
                    with open(cfg_path, 'w', encoding='utf-8') as f:
                        f.write('[Style]\n')
                        for k, v in defaults.items(): f.write(f"{k} = {v}\n")
                except: pass
            else:
                try:
                    cp = configparser.ConfigParser(interpolation=None, strict=False)
                    cp.optionxform = str
                    cp.read(cfg_path, encoding='utf-8-sig')
                    changed = False
                    if 'Style' not in cp: cp['Style'] = {}; changed = True
                    for k, v in defaults.items():
                        if k not in cp['Style']: cp['Style'][k] = v; changed = True
                    if changed:
                        with open(cfg_path, 'w', encoding='utf-8') as f: cp.write(f)
                except: pass

    anim_dir = os.path.join(APP_DATA_PATH, 'Animations')
    if os.path.exists(anim_dir):
        for entry in os.listdir(anim_dir):
            full = os.path.join(anim_dir, entry)
            if not os.path.isdir(full): continue
            cfg_path = os.path.join(full, 'config.ini')

            aset_defaults = {'name': entry, 'animation_in': 'Slide Up + Fade', 'animation_out': 'Slide Down + Fade', 'in_offset_x': '0', 'in_offset_y': '0', 'out_offset_x': '0', 'out_offset_y': '0'}

            if not os.path.exists(cfg_path):
                try:
                    with open(cfg_path, 'w', encoding='utf-8') as f:
                        f.write(f'[AnimationSet]\nname = {entry}\n')
                        for k, v in aset_defaults.items(): 
                            if k != 'name': f.write(f"{k} = {v}\n")
                        f.write('\n[In]\nframe1 = pos=se;seconds=0.0;offset_x=0;offset_y=0\n')
                        f.write('\n[Out]\nframe1 = pos=se;seconds=0.25;offset_x=0;offset_y=0\n')
                except: pass
            else:
                try:
                    cp = configparser.ConfigParser(interpolation=None, strict=False)
                    cp.optionxform = str
                    cp.read(cfg_path, encoding='utf-8-sig')
                    changed = False

                    if 'AnimationSet' not in cp: cp['AnimationSet'] = {}; changed = True
                    for k, v in aset_defaults.items():
                        if k not in cp['AnimationSet']: cp['AnimationSet'][k] = v; changed = True

                    if 'In' not in cp: 
                        cp['In'] = {'frame1': 'pos=se;seconds=0.0;offset_x=0;offset_y=0'}
                        changed = True
                    if 'Out' not in cp: 
                        cp['Out'] = {'frame1': 'pos=se;seconds=0.25;offset_x=0;offset_y=0'}
                        changed = True

                    if changed:
                        with open(cfg_path, 'w', encoding='utf-8') as f: cp.write(f)
                except: pass

ensure_ini_defaults()

def load_messages():
    global UI, MESSAGES
    UI, MESSAGES = DEFAULT_UI.copy(), DEFAULT_MESSAGES.copy()
    lang_file = CURRENT_SETTINGS.get('language') or 'en-US.ini'
    path = os.path.join(APP_DATA_PATH, 'lang', lang_file)
    
    if not os.path.exists(path):
        show_error_messagebox("Language File Not Found", f"Selected language '{lang_file}' not found.\nReverting to English.")
        CURRENT_SETTINGS['language'] = 'en-US.ini'
        save_config()
        path = os.path.join(APP_DATA_PATH, 'lang', 'en-US.ini')
        if not os.path.exists(path):
            show_error_messagebox("Critical Error", "Default language file 'en-US.ini' is missing.")
            return

    try:
        cp = configparser.ConfigParser(interpolation=None, strict=False)
        cp.optionxform = str
        cp.read(path, encoding='utf-8-sig')
        if 'Messages' in cp:
            for key in MESSAGES: MESSAGES[key] = cp['Messages'].get(key, MESSAGES[key])
        if 'UI' in cp:
            for key in UI: UI[key] = cp['UI'].get(key, UI[key])
    except Exception as e:
        show_error_messagebox("Language File Error", f"Failed to parse '{path}'.\nUsing default English text.\n\nError: {e}")

def validate_settings():
    made_changes = False
    if CURRENT_SETTINGS.get('style') not in STYLES:
        show_error_messagebox("Configuration Error", f"Style '{CURRENT_SETTINGS.get('style')}' not found.\nReverting to 'Default Dark'.")
        CURRENT_SETTINGS['style'] = 'Default Dark'
        made_changes = True
    if CURRENT_SETTINGS.get('animation_in') not in ANIMATIONS_IN:
        show_error_messagebox("Configuration Error", f"Animation In '{CURRENT_SETTINGS.get('animation_in')}' not found.\nReverting to default.")
        CURRENT_SETTINGS['animation_in'] = 'Slide Up + Fade'
        made_changes = True
    if CURRENT_SETTINGS.get('animation_out') not in ANIMATIONS_OUT:
        show_error_messagebox("Configuration Error", f"Animation Out '{CURRENT_SETTINGS.get('animation_out')}' not found.\nReverting to default.")
        CURRENT_SETTINGS['animation_out'] = 'Slide Down + Fade'
        made_changes = True
    if made_changes:
        save_config()
        load_messages()

def open_path(path):
    try:
        if not os.path.exists(path):
            os.makedirs(path, exist_ok=True)
        os.startfile(path)
    except Exception:
        try:
            if sys.platform == 'win32':
                os.system(f'start "" "{path}"')
        except Exception as e:
            show_error_messagebox("Error", f"Could not open path: {path}\n\nError: {e}")

def calculate_position(w, h):
    x_anchor, y_anchor = 0, 0
    if CURRENT_SETTINGS['x_rule'] == 'default': x_anchor = screen_width - 20
    elif CURRENT_SETTINGS['x_rule'] == 'absolute': x_anchor = CURRENT_SETTINGS['x_val']
    elif CURRENT_SETTINGS['x_rule'] == 'edge': x_anchor = screen_width - CURRENT_SETTINGS['x_val']
    if CURRENT_SETTINGS['y_rule'] == 'default': y_anchor = screen_height - 50
    elif CURRENT_SETTINGS['y_rule'] == 'absolute': y_anchor = CURRENT_SETTINGS['y_val']
    elif CURRENT_SETTINGS['y_rule'] == 'edge': y_anchor = screen_height - CURRENT_SETTINGS['y_val']
    anchor = CURRENT_SETTINGS.get('pos_anchor', 'se')
    y = y_anchor if 'n' in anchor else y_anchor - h
    x = x_anchor if 'w' in anchor else x_anchor - w
    return int(x), int(y)

def set_hide_from_capture(window, force=False):
    try:
        user32 = ctypes.WinDLL("user32")
        hwnd = user32.GetAncestor(window.winfo_id(), 2)
        affinity = 0x11 if (force or CURRENT_SETTINGS.get('hide_from_capture')) else 0x0
        user32.SetWindowDisplayAffinity(hwnd, affinity)
    except Exception:
        pass

def _pw_swap_text_widget(widget, find, repl):
    try:
        if isinstance(widget, tk.Label):
            t = widget.cget('text')
            if find in t:
                widget.configure(text=t.replace(find, repl))
        elif isinstance(widget, ScrolledText):
            widget.config(state=tk.NORMAL)
            content = widget.get('1.0', 'end')
            widget.delete('1.0', 'end')
            widget.insert('1.0', content.replace(find, repl))
            widget.config(state=tk.DISABLED)
    except Exception:
        pass

def _pw_swap_in_frame(frame, find, repl):
    try:
        for child in frame.winfo_children():
            _pw_swap_text_widget(child, find, repl)
            _pw_swap_in_frame(child, find, repl)
    except Exception:
        pass

def _pw_should_hide_capture():
    try:
        if CURRENT_SETTINGS.get('pw_hide_from_capture', True):
            return True
        entries = passwords.session_entries()
        revealed = {pw for _, pw in getattr(toast, '_pw_reveal', [])}
        return any(e.get('hide_capture', True) and e.get('password') in revealed for e in entries)
    except Exception:
        return False

def _pw_resize_to_fit():
    try:
        if toast is None or not toast.winfo_exists():
            return
        def _first_text_widget(w):
            for c in w.winfo_children():
                if isinstance(c, tk.Label) or isinstance(c, ScrolledText):
                    return c
                r = _first_text_widget(c)
                if r:
                    return r
            return None
        widget = _first_text_widget(toast._pw_frame)
        if widget is None or not isinstance(widget, tk.Label):
            return
        max_w_long = int(screen_width * 0.6)
        widget.config(wraplength=0)
        toast.update_idletasks()
        w_new = min(widget.winfo_reqwidth() + 20, max_w_long)
        widget.config(wraplength=0 if w_new < max_w_long else w_new - 20)
        toast.update_idletasks()
        h_new = widget.winfo_reqheight() + 10
        if (w_new, h_new) != (toast.winfo_width(), toast.winfo_height()):
            animate_resize(toast, w_new, h_new)
    except Exception:
        pass

def reveal_passwords():
    try:
        if toast is None or not toast.winfo_exists():
            return
        if not getattr(toast, '_pw_hover', False) or getattr(toast, '_pw_visible', False):
            return
        toast._pw_visible = True
        for block, pw in toast._pw_reveal:
            _pw_swap_in_frame(toast._pw_frame, block, pw)
        _pw_resize_to_fit()
        if _pw_should_hide_capture():
            set_hide_from_capture(toast, force=True)
    except Exception:
        pass

def remask_passwords():
    try:
        if toast is None or not toast.winfo_exists():
            return
        if not getattr(toast, '_pw_visible', False):
            return
        toast._pw_visible = False
        for block, pw in reversed(toast._pw_reveal):
            _pw_swap_in_frame(toast._pw_frame, pw, block)
        set_hide_from_capture(toast)
        _pw_resize_to_fit()
    except Exception:
        pass

def show_toast(text):
    global toast, fade_out_job
    _toast_t0 = time.perf_counter()
    refresh_settings_from_disk()
    pw_reveal = []
    if passwords.is_unlocked() and CURRENT_SETTINGS.get('pw_hide_from_toast', True):
        try:
            entries = [e for e in passwords.session_entries() if e.get('hide_capture', True)]
            if entries:
                masked, reveal = passwords.mask_text_detailed(text, entries)
                if reveal:
                    text = masked
                    pw_reveal = reveal
        except Exception:
            pw_reveal = []
    global _pw_mask_broken_notice
    if _pw_mask_broken_notice and not passwords.is_unlocked() and CURRENT_SETTINGS.get('pw_hide_from_toast', True):
        _pw_mask_broken_notice = False
        show_error_messagebox(
            "The program threw an error!",
            "Open your vault once so the passwords can be hidden again"
        )
    if fade_out_job:
        try: root.after_cancel(fade_out_job)
        except Exception: pass
        fade_out_job = None
    if not toast or not toast.winfo_exists():
        toast = tk.Toplevel()
        toast.overrideredirect(True)
        toast.attributes("-topmost", True)
        toast.attributes("-toolwindow", 1)

    for widget in toast.winfo_children(): widget.destroy()
    toast._pw_reveal = pw_reveal
    toast._pw_visible = False
    toast._pw_hover = False
    toast._pw_job = None
    style_name = CURRENT_SETTINGS.get('style', 'Default Dark')
    style_look = STYLES.get(style_name, STYLES['Default Dark'])['look']
    toast.config(bg=style_look['border'])
    content_frame = tk.Frame(toast, bg=style_look['bg'])
    content_frame.pack(padx=1, pady=1, fill=tk.BOTH, expand=True)
    toast._pw_frame = content_frame

    lines = text.splitlines()
    is_multiline, is_long = len(lines) > 1, not (len(lines) > 1) and len(text) > 20
    is_truncated = is_multiline or is_long
    if is_multiline: short_text = f'"{lines[0]}..."'
    elif is_long: short_text = f'"{text[:20]}..."'
    else: short_text = f'"{text}"'
    
    font_obj = tkfont.Font(root=toast, font=style_look['font'])
    measured = font_obj.measure(f"{short_text} {MESSAGES.get('CopiedSuffix')}")
    w_calc = int(min(min(int(screen_width * 0.5), 480), max(260, measured + 40)))
    wraplen = max(80, w_calc - 40)
    
    clean_style = style_look.copy()
    clean_style.pop('border', None)
    label = tk.Label(content_frame, text=f"{short_text} {MESSAGES.get('CopiedSuffix')}", **clean_style, wraplength=wraplen, justify='left', anchor='w')
    label.pack(padx=10, pady=5, fill=tk.X)
    toast.update_idletasks()
    w_small, h_small = toast.winfo_reqwidth(), toast.winfo_reqheight()

    anim_out_name = CURRENT_SETTINGS.get('animation_out')
    anim_out_func = ANIMATIONS_OUT.get(anim_out_name, an_fade_out)
    p_out = CUSTOM_ANIM_PARAMS.get(anim_out_name)
    if p_out:
        def _wrapped_out(window, w, h, x, y, func=anim_out_func, p=p_out):
            if 'out_offset_x' in p: x += p['out_offset_x']
            if 'out_offset_y' in p: y += p['out_offset_y']
            return func(window, w, h, x, y)
        anim_out_func = _wrapped_out
    hover_state = {'job': None, 'is_expanded': False}

    def shrink_toast():
        if not hover_state['is_expanded']: return
        hover_state['is_expanded'] = False
        global fade_out_job
        for widget in content_frame.winfo_children(): widget.destroy()
        label_short = tk.Label(content_frame, text=f"{short_text} {MESSAGES.get('CopiedSuffix')}", **clean_style, wraplength=wraplen, justify='left', anchor='w')
        label_short.pack(padx=10, pady=5, fill=tk.X)
        animate_resize(toast, w_small, h_small)
        x_pos, y_pos = calculate_position(w_small, h_small)
        fade_out_job = root.after(3000, lambda: anim_out_func(toast, w_small, h_small, x_pos, y_pos))

    def on_enter(event):
        global fade_out_job
        if fade_out_job: root.after_cancel(fade_out_job); fade_out_job = None
        if hover_state['job']: root.after_cancel(hover_state['job']); hover_state['job'] = None
        toast._pw_hover = True
        if toast._pw_job:
            try: root.after_cancel(toast._pw_job)
            except Exception: pass
            toast._pw_job = None
        if CURRENT_SETTINGS.get('pw_show_on_hover') and toast._pw_reveal and not getattr(toast, '_pw_visible', False):
            delay = max(0, int(CURRENT_SETTINGS.get('pw_hover_seconds', 2))) * 1000
            toast._pw_job = root.after(delay, reveal_passwords)
        if not is_truncated or hover_state['is_expanded']: return
        hover_state['is_expanded'] = True
        for widget in content_frame.winfo_children(): widget.destroy()
        if text.count('\n') > 5 or len(text) > 400:
            w_long, h_long = int(screen_width * 0.4), int(screen_height * 0.3)
            text_area = ScrolledText(content_frame, wrap=tk.WORD, font=style_look['font'], bg=style_look['bg'], fg=style_look['fg'], bd=0, highlightthickness=0, padx=10, pady=5)
            text_area.pack(fill=tk.BOTH, expand=True)
            text_area.insert("1.0", f'"{text}"\n\n{MESSAGES.get("CopiedSuffix")}')
            text_area.config(state=tk.DISABLED)
            animate_resize(toast, w_long, h_long)
        else:
            max_w_long = int(screen_width * 0.6)
            expanded_label = tk.Label(content_frame, text=f'"{text}" {MESSAGES.get("CopiedSuffix")}', bg=style_look['bg'], fg=style_look['fg'], font=style_look['font'], justify='left', anchor='w')
            expanded_label.pack(padx=10, pady=5, fill=tk.X)
            expanded_label.config(wraplength=0)
            toast.update_idletasks()
            w_long = min(expanded_label.winfo_reqwidth() + 20, max_w_long)
            expanded_label.config(wraplength=0 if w_long < max_w_long else w_long - 20)
            toast.update_idletasks()
            h_long = expanded_label.winfo_reqheight() + 10
            animate_resize(toast, w_long, h_long)

    def on_leave(event):
        global fade_out_job
        toast._pw_hover = False
        if toast._pw_job:
            try: root.after_cancel(toast._pw_job)
            except Exception: pass
            toast._pw_job = None
        remask_passwords()
        if not is_truncated:
            x_pos, y_pos = calculate_position(w_small, h_small)
            fade_out_job = root.after(3000, lambda: anim_out_func(toast, w_small, h_small, x_pos, y_pos))
            return
        hover_state['job'] = root.after(50, shrink_toast)

    toast.bind("<Enter>", on_enter); toast.bind("<Leave>", on_leave)
    x, y = calculate_position(w_small, h_small)
    toast.geometry(f"{w_small}x{h_small}+{x}+{y}")
    toast.attributes("-alpha", 0); toast.deiconify()
    toast.update_idletasks()
    set_hide_from_capture(toast, force=bool(pw_reveal) and _pw_should_hide_capture())
    anim_in_name = CURRENT_SETTINGS.get('animation_in')
    anim_in_func = ANIMATIONS_IN.get(anim_in_name, an_fade_in)
    p_in = CUSTOM_ANIM_PARAMS.get(anim_in_name)
    if p_in:
        def _wrapped_in(window, w, h, x, y, func=anim_in_func, p=p_in):
            if 'in_offset_x' in p: x += p['in_offset_x']
            if 'in_offset_y' in p: y += p['in_offset_y']
            return func(window, w, h, x, y)
        anim_in_func = _wrapped_in
    anim_in_func(toast, w_small, h_small, x, y)
    fade_out_job = root.after(3000, lambda: anim_out_func(toast, w_small, h_small, x, y))
    _pw_capture_force = bool(pw_reveal) and _pw_should_hide_capture()
    set_hide_from_capture(toast, force=_pw_capture_force)
    root.after(50, lambda: set_hide_from_capture(toast, force=_pw_capture_force))
    _perf('show_toast done %.0fms' % ((time.perf_counter() - _toast_t0) * 1000))

def apply_external_changes():
    try:
        refresh_settings_from_disk()
        load_languages()
        update_systray_menu()
        global toast
        if toast is not None:
            try:
                if toast.winfo_exists():
                    set_hide_from_capture(toast)
            except Exception:
                pass
        if CURRENT_SETTINGS.get('pw_pending_open_editor'):
            CURRENT_SETTINGS['pw_pending_open_editor'] = False
            save_config()
            open_passwords_threaded(UI)
        try:
            if passwords.is_unlocked() and not os.path.exists(passwords.vault_file_path(APP_DATA_PATH)):
                passwords.clear_session()
                passwords.clear_mask_key(APP_DATA_PATH)
        except Exception:
            pass
    except Exception:
        pass

def _clipboard_sequence():
    try:
        return int(ctypes.windll.user32.GetClipboardSequenceNumber())
    except Exception:
        return -1

def _pump_tk_queue():
    try:
        for _ in range(100):
            kind, payload = _tk_queue.get_nowait()
            try:
                if kind == 'toast':
                    show_toast(payload)
                elif kind == 'config':
                    apply_external_changes()
            except Exception:
                traceback.print_exc()
    except queue.Empty:
        pass
    root.after(10, _pump_tk_queue)

def monitor_clipboard():
    global last_text
    last_seq = _clipboard_sequence()
    try: last_text = pyperclip.paste()
    except Exception: last_text = ""
    last_config_mtime = os.path.getmtime(CONFIG_FILE) if os.path.exists(CONFIG_FILE) else None
    while True:
        try:
            seq = _clipboard_sequence()
            if seq != last_seq:
                last_seq = seq
                current_text = pyperclip.paste()
                if current_text != last_text and current_text.strip() != "":
                    last_text = current_text
                    _tk_queue.put(('toast', current_text))
        except Exception: pass
        try:
            mtime = os.path.getmtime(CONFIG_FILE) if os.path.exists(CONFIG_FILE) else None
            if mtime != last_config_mtime:
                last_config_mtime = mtime
                _tk_queue.put(('config', None))
        except Exception: pass
        time.sleep(0.1)

def create_image_for_tray(): return Image.open(io.BytesIO(base64.b64decode(ICON_BASE64)))
def create_image_for_tk(): return ImageTk.PhotoImage(create_image_for_tray())

def apply_style(style_name):
    if style_name not in STYLES: return
    style_preset = STYLES[style_name]
    CURRENT_SETTINGS['style'] = style_name
    CURRENT_SETTINGS.update(style_preset.get('position', {}))
    CURRENT_SETTINGS['animation_in'] = style_preset.get('animation_in', CURRENT_SETTINGS['animation_in'])
    CURRENT_SETTINGS['animation_out'] = style_preset.get('animation_out', CURRENT_SETTINGS['animation_out'])
    save_config()
    update_systray_menu()

def open_about_threaded(ui_dict):
    import tempfile, json
    global _about_process
    if _about_process is not None and _about_process.poll() is None:
        return
    _about_process = None
    try:
        tf = tempfile.NamedTemporaryFile(delete=False, suffix='.json', mode='w', encoding='utf-8')
        json.dump(ui_dict or {}, tf)
        tf.close()
    except Exception:
        return

    if getattr(sys, 'frozen', False):
        try:
            _about_process = subprocess.Popen([sys.executable, "about", tf.name], close_fds=True)
        except Exception:
            pass
    else:
        try:
            _about_process = subprocess.Popen([sys.executable, os.path.join(BASE_PATH, 'about_qt.py'), tf.name], close_fds=True)
        except Exception:
            pass

def open_options_threaded(ui_dict):
    import tempfile, json
    global _options_process
    if _options_process is not None and _options_process.poll() is None:
        return
    _options_process = None
    try:
        load_builtin_styles()
        load_styles_from_folder()
        load_languages()
    except Exception:
        pass
    payload = {
        'ui': ui_dict or {},
        'config_file': CONFIG_FILE,
        'styles': sorted(STYLES.keys()),
        'anims_in': list(ANIMATIONS_IN.keys()),
        'anims_out': list(ANIMATIONS_OUT.keys()),
        'langs': dict(LANGS),
        'anchors': ['se', 'sw', 'ne', 'nw', 'n', 's', 'e', 'w'],
        'vault': passwords.vault_file_path(APP_DATA_PATH),
        'vault_count': len(passwords.session_entries()) if passwords.is_unlocked() else 0,
    }
    try:
        tf = tempfile.NamedTemporaryFile(delete=False, suffix='.json', mode='w', encoding='utf-8')
        json.dump(payload, tf)
        tf.close()
    except Exception:
        return

    if getattr(sys, 'frozen', False):
        try:
            _options_process = subprocess.Popen([sys.executable, "options", tf.name], close_fds=True)
        except Exception:
            pass
    else:
        try:
            _options_process = subprocess.Popen([sys.executable, os.path.join(BASE_PATH, 'options_qt.py'), tf.name], close_fds=True)
        except Exception:
            pass

def _get_requesting_program():
    try:
        return sys.executable
    except Exception:
        return ''

def _ask_intruder_qt(pid, filepath, exe_path=None):
    try:
        import tempfile, json
        status_file = tempfile.mkstemp(suffix='.intr')[1]
        payload = {
            'mode': 'pw_intruder',
            'ui': UI,
            'vault': passwords.vault_file_path(APP_DATA_PATH),
            'config_file': CONFIG_FILE,
            'intruder_pid': pid,
            'intruder_file': filepath,
            'intruder_path': exe_path or '',
            'status_file': status_file,
        }
        tf = tempfile.NamedTemporaryFile(delete=False, suffix='.json', mode='w', encoding='utf-8')
        json.dump(payload, tf)
        tf.close()
        if getattr(sys, 'frozen', False):
            cmd = [sys.executable, 'pw_intruder', tf.name]
        else:
            cmd = [sys.executable, os.path.join(BASE_PATH, 'passwords_qt.py'), tf.name]
        proc = subprocess.Popen(cmd, close_fds=True)
        proc.wait(timeout=120)
        decision = 'deny'
        if os.path.exists(status_file):
            try:
                with open(status_file, 'rb') as f:
                    raw = f.read().decode('utf-8', errors='replace').strip()
                if raw:
                    decision = raw
            except Exception:
                pass
        for p in (tf.name, status_file):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except Exception:
                pass
        return decision
    except Exception:
        return 'deny'

def _start_vault_guard(root):
    try:
        from sesv_guard import create_vault_guard
        vault_path = passwords.vault_file_path(APP_DATA_PATH)
        if not os.path.exists(vault_path):
            return None
        clip_dir = os.path.dirname(os.path.dirname(vault_path))
        guard = create_vault_guard(clip_dir)
        queue = __import__('queue').Queue()
        shown = set()

        def on_intrusion(pid, filepath, reason):
            queue.put((pid, filepath, reason))
            return "pending"

        guard.on_intrusion = on_intrusion
        guard.start()

        def poll():
            try:
                while not queue.empty():
                    pid, filepath, reason = queue.get()
                    if pid in shown:
                        continue
                    shown.add(pid)
                    exe_path = ''
                    try:
                        exe_path = psutil.Process(pid).exe()
                    except Exception:
                        pass
                    decision = _ask_intruder_qt(pid, filepath, exe_path)
                    if decision == 'approve':
                        guard.approve_pid(pid)
                    else:
                        guard.deny_pid(pid)
            except Exception:
                pass
            root.after(150, poll)

        root.after(150, poll)
        return guard
    except Exception:
        return None

def _run_password_subprocess(mode, ui_dict, key=None):
    import tempfile, json
    payload = {
        'mode': mode,
        'ui': ui_dict or {},
        'vault': passwords.vault_file_path(APP_DATA_PATH),
        'config_file': CONFIG_FILE,
        'requesting_program': _get_requesting_program(),
    }
    tf = None
    key_file = None
    status_file = None
    try:
        tf = tempfile.NamedTemporaryFile(delete=False, suffix='.json', mode='w', encoding='utf-8')
        if mode == 'pw_editor' and key:
            key_file = tempfile.NamedTemporaryFile(delete=False, suffix='.key', mode='wb')
            key_file.write(key)
            key_file.close()
            payload['key_file'] = key_file.name
        elif mode in ('pw_setup', 'pw_unlock'):
            key_file = tempfile.NamedTemporaryFile(delete=False, suffix='.key', mode='wb')
            key_file.close()
            payload['key_file'] = key_file.name
        status_file = tempfile.NamedTemporaryFile(delete=False, suffix='.lock', mode='wb')
        status_file.close()
        payload['status_file'] = status_file.name
        json.dump(payload, tf)
        tf.close()
    except Exception:
        for f in (tf, key_file, status_file):
            try:
                if f is not None and os.path.exists(f.name):
                    os.remove(f.name)
            except Exception:
                pass
        return None

    if getattr(sys, 'frozen', False):
        cmd = [sys.executable, mode, tf.name]
    else:
        cmd = [sys.executable, os.path.join(BASE_PATH, 'passwords_qt.py'), tf.name]
    try:
        proc = subprocess.Popen(cmd, close_fds=True)
        try:
            out, _err = proc.communicate()
        except Exception:
            out = b''
        if key_file and os.path.exists(key_file.name):
            try:
                with open(key_file.name, 'rb') as f:
                    raw = f.read()
            except Exception:
                raw = b''
        else:
            raw = b''
        if mode == 'pw_editor' and (b'LOCKED' in (out or b'')):
            try:
                passwords.lock_session()
            except Exception:
                pass
            _cancel_pw_lock()
        if status_file and os.path.exists(status_file.name):
            try:
                with open(status_file.name, 'rb') as f:
                    status_data = f.read()
                if b'LOCKED' in status_data:
                    try:
                        passwords.lock_session()
                    except Exception:
                        pass
                    _cancel_pw_lock()
            except Exception:
                pass
        if mode in ('pw_setup', 'pw_unlock') and raw and len(raw) == passwords.KEY_LENGTH:
            return raw
    except Exception:
        pass
    finally:
        for f in (tf, key_file, status_file):
            try:
                if f is not None and os.path.exists(f.name):
                    os.remove(f.name)
            except Exception:
                pass
    return None

def _set_password_session(vault, key):
    def _do():
        try:
            global _pw_mask_broken_notice
            _pw_mask_broken_notice = False
            passwords.set_session(key, passwords.decrypt_vault_with_key(vault, key))
            passwords.save_mask_key(APP_DATA_PATH, key)
            _pw_reschedule_lock()
        except Exception:
            passwords.clear_session()
    try:
        root.after(0, _do)
    except Exception:
        _do()

def _restore_mask_session():
    try:
        if passwords.is_unlocked():
            return
        vault = passwords.vault_file_path(APP_DATA_PATH)
        if not os.path.exists(vault):
            if os.path.exists(passwords.mask_key_cache_path(APP_DATA_PATH)):
                try:
                    raise FileNotFoundError(
                        "No such file: {0}".format(passwords.vault_file_path(APP_DATA_PATH))
                    )
                except FileNotFoundError as e:
                    traceback_text = "".join(traceback.format_exception(type(e), e, e.__traceback__))
                show_error_messagebox(
                    "The program threw an error!",
                    "We aren't able to find the vault, where did you just put at?\n\nTechnical details:\n{0}".format(
                        traceback_text
                    )
                )
            return
        try:
            key = passwords.load_mask_key(APP_DATA_PATH)
        except passwords.MaskKeyDecryptError as e:
            traceback_text = "".join(traceback.format_exception(type(e), e, e.__traceback__))
            show_error_messagebox(
                "The program threw an error!",
                "We are not able to decrypt ({0}), did you change your password in some special way?\n\nTechnical details:\n{1}".format(
                    getattr(e, 'args', (None,))[0] or passwords.mask_key_cache_path(APP_DATA_PATH),
                    traceback_text
                )
            )
            passwords.clear_mask_key(APP_DATA_PATH)
            global _pw_mask_broken_notice
            _pw_mask_broken_notice = True
            return
        if not key:
            return
        passwords.set_session(None, passwords.decrypt_vault_with_key(passwords.vault_file_path(APP_DATA_PATH), key))
    except Exception:
        try:
            passwords.clear_session()
        except Exception:
            pass

_pw_lock_timer = None

def _pw_do_lock():
    global _pw_lock_timer
    _pw_lock_timer = None
    try:
        passwords.lock_session()
    except Exception:
        pass

def _cancel_pw_lock():
    global _pw_lock_timer
    if _pw_lock_timer is not None:
        try:
            _pw_lock_timer.cancel()
        except Exception:
            pass
_pw_lock_timer = None
_pw_mask_broken_notice = False

def _pw_reschedule_lock():
    global _pw_lock_timer
    _cancel_pw_lock()
    if not CURRENT_SETTINGS.get('pw_lock_after_time', False):
        return
    try:
        timeout = max(0, int(CURRENT_SETTINGS.get('pw_lock_timeout', 3600)))
    except Exception:
        timeout = 3600
    if timeout <= 0:
        return
    _pw_lock_timer = threading.Timer(timeout, _pw_do_lock)
    _pw_lock_timer.daemon = True
    _pw_lock_timer.start()

def _passwords_flow(ui_dict):
    try:
        vault = passwords.vault_file_path(APP_DATA_PATH)
        key = passwords.session_key()
        if not key:
            if os.path.exists(vault):
                key = _run_password_subprocess('pw_unlock', ui_dict)
            else:
                key = _run_password_subprocess('pw_setup', ui_dict)
            if not key:
                return
            _set_password_session(vault, key)
        _run_password_subprocess('pw_editor', ui_dict, key=key)
        if CURRENT_SETTINGS.get('pw_lock_on_close', False):
            passwords.lock_session()
            _cancel_pw_lock()
        elif passwords.session_key():
            _set_password_session(vault, passwords.session_key())
    except Exception:
        pass

def open_passwords_threaded(ui_dict):
    threading.Thread(target=_passwords_flow, args=(ui_dict,), daemon=True).start()

def update_systray_menu():
    global app_icon
    styles_dir = os.path.join(APP_DATA_PATH, 'Styles')
    lang_dir = os.path.join(APP_DATA_PATH, 'lang')
    anim_dir = os.path.join(APP_DATA_PATH, 'Animations')

    def create_anim_action(key, value):
        def action(icon, item): CURRENT_SETTINGS[key] = value; save_config(); update_systray_menu()
        return action

    load_builtin_styles(); load_styles_from_folder()
    style_items = []
    for name in sorted(STYLES.keys()):
        def create_style_action(n): return lambda icon, item: apply_style(n)
        style_items.append(item(name, create_style_action(name), checked=lambda item, n=name: CURRENT_SETTINGS['style'] == n, radio=True))

    load_languages()
    current_lang = CURRENT_SETTINGS.get('language', 'en-US.ini')
    if current_lang not in LANGS:
        show_error_messagebox("Language File Not Found", f"Active language '{current_lang}' was deleted. Reverting to English.")
        CURRENT_SETTINGS['language'] = 'en-US.ini'; save_config(); load_messages(); update_systray_menu()
    lang_items = []
    for fname, display in sorted(LANGS.items(), key=lambda x: x[1]):
        def create_lang_action(f): return lambda icon, item: (CURRENT_SETTINGS.update({'language': f}), save_config(), load_messages(), update_systray_menu())
        lang_items.append(item(display, create_lang_action(fname), checked=lambda item, f=fname: CURRENT_SETTINGS.get('language') == f, radio=True))

    load_animation_sets_from_folder()
    anim_set_items = []
    for name, anim_set in sorted(ANIMATION_SETS.items()):
        def create_anim_set_action(a): return lambda icon, item: (CURRENT_SETTINGS.update(a), save_config(), update_systray_menu())
        anim_set_items.append(item(name, create_anim_set_action(anim_set), checked=lambda item, a=anim_set: CURRENT_SETTINGS['animation_in'] == a['animation_in'] and CURRENT_SETTINGS['animation_out'] == a['animation_out'], radio=True))

    settings_menu = [item(UI.get('EditConfig'), lambda: open_path(CONFIG_FILE)), item(UI.get('Options'), lambda: open_options_threaded(UI)), pystray.Menu.SEPARATOR, item(UI.get('OpenStyles'), lambda: open_path(styles_dir)), item(UI.get('OpenLangs'), lambda: open_path(lang_dir)), item(UI.get('OpenAnims'), lambda: open_path(anim_dir)), item(UI.get('OpenGlobal'), lambda: open_path(APP_DATA_PATH))]
    
    menu_items = (
        item(UI.get('SetPosition'), lambda: open_positioner()),
        item(UI.get('Style'), pystray.Menu(*style_items)),
        item(UI.get('AnimationSet'), pystray.Menu(*anim_set_items)),
        item(UI.get('AnimationIn'), pystray.Menu(*(item(name, create_anim_action('animation_in', name), checked=lambda item, n=name: CURRENT_SETTINGS['animation_in'] == n, radio=True) for name in ANIMATIONS_IN.keys()))),
        item(UI.get('AnimationOut'), pystray.Menu(*(item(name, create_anim_action('animation_out', name), checked=lambda item, n=name: CURRENT_SETTINGS['animation_out'] == n, radio=True) for name in ANIMATIONS_OUT.keys()))),
        item(UI.get('Language'), pystray.Menu(*lang_items)),
        pystray.Menu.SEPARATOR,
        item(UI.get('EditSettings'), pystray.Menu(*settings_menu)),
        pystray.Menu.SEPARATOR,
        item(UI.get('About'), lambda: open_about_threaded(UI)),
        item(UI.get('Quit'), lambda: UPDATE_AND_QUIT_FLAG.set())
    )
    if app_icon: app_icon.menu = pystray.Menu(*menu_items)

def _patch_tray_menu_foreground(icon):
    try:
        handlers = getattr(icon, '_message_handlers', None)
        if not handlers:
            return
        orig = handlers.get(0x040B)
        if orig is None:
            return

        def wrapped(wparam, lparam):
            try:
                if lparam == 0x0205:
                    hwnd = getattr(icon, '_hwnd', None)
                    if hwnd:
                        user32 = ctypes.WinDLL("user32", use_last_error=True)
                        user32.SetForegroundWindow(hwnd)
                        user32.SetWindowPos(
                            hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010
                        )
                        user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
            return orig(wparam, lparam)

        handlers[0x040B] = wrapped
    except Exception:
        pass


def setup_tray_and_monitoring(icon):
    global app_icon; app_icon = icon
    _perf('setup start')
    icon.visible = True; _perf('icon visible')
    _patch_tray_menu_foreground(icon)
    threading.Thread(target=monitor_clipboard, daemon=True).start()
    _perf('monitor started')

def open_positioner(): PositionerWindow(root, app_photo_icon)

class PositionerWindow(tk.Toplevel):
    def __init__(self, master, icon):
        super().__init__(master)
        self.title(''); self.overrideredirect(True)
        try: self.iconphoto(False, icon)
        except Exception: pass
        self.attributes("-alpha", 0.3); self.config(bg="black")
        self.geometry(f"{screen_width}x{screen_height}+0+0"); self.focus_force()
        self.canvas = tk.Canvas(self, bg="black", highlightthickness=0); self.canvas.pack(fill=tk.BOTH, expand=True)
        self.rect = None
        self.canvas.bind("<ButtonPress-1>", self.on_press); self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release); self.bind("<Control-Shift-R>", self.reset_position)
        self.instructions = tk.Label(self.canvas, text=UI.get('PositionerInstructions'), bg="black", fg="white", font=("Arial", 24))
        self.instructions.place(relx=0.5, rely=0.4, anchor=tk.CENTER)

    def on_press(self, event):
        self.instructions.place_forget()
        self.start_x, self.start_y = event.x_root, event.y_root
        if self.rect: self.canvas.delete(self.rect)
        if hasattr(self, 'preview_toast') and self.preview_toast:
            try: self.preview_toast.destroy()
            except Exception: pass
            self.preview_toast = None
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline="white", width=2, dash=(5, 5))

    def on_drag(self, event): self.canvas.coords(self.rect, self.start_x, self.start_y, event.x_root, event.y_root)

    def on_release(self, event):
        self.end_x, self.end_y = event.x_root, event.y_root
        dx = abs(self.end_x - self.start_x)
        dy = abs(self.end_y - self.start_y)
        if dx < 6 and dy < 6:
            self.start_x = self.end_x = event.x_root
            self.start_y = self.end_y = event.y_root
        self.preview_toast = tk.Toplevel(self); self.preview_toast.overrideredirect(True)
        self.preview_toast.attributes("-toolwindow", 1); self.preview_toast.config(bg="#888888")
        frame = tk.Frame(self.preview_toast, bg="#333333"); frame.pack(padx=1, pady=1)
        tk.Label(frame, text=MESSAGES.get('PreviewText'), bg="#333333", fg="white", font=("Arial", 12)).pack(padx=10, pady=5)
        btn_frame = tk.Frame(frame, bg="#333333"); btn_frame.pack(pady=5)
        tk.Button(btn_frame, text=UI.get('SavePosition'), command=self.save_position, bg="#444444", fg="white", relief=tk.FLAT).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text=UI.get('Cancel'), command=self.destroy, bg="#444444", fg="white", relief=tk.FLAT).pack(side=tk.LEFT, padx=5)
        self.update_preview_position()

    def update_preview_position(self):
        self.preview_toast.update_idletasks()
        w, h = self.preview_toast.winfo_reqwidth(), self.preview_toast.winfo_reqheight()
        center_x, center_y = (self.start_x + self.end_x) / 2, (self.start_y + self.end_y) / 2
        self.anchor = ('n' if center_y < screen_height / 2 else 's') + ('w' if center_x < screen_width / 2 else 'e')
        self.x_val = min(self.start_x, self.end_x) if 'w' in self.anchor else max(self.start_x, self.end_x)
        self.y_val = min(self.start_y, self.end_y) if 'n' in self.anchor else max(self.start_y, self.end_y)
        pos_x = self.x_val if 'w' in self.anchor else self.x_val - w
        pos_y = self.y_val if 'n' in self.anchor else self.y_val - h
        self.preview_toast.geometry(f"+{pos_x}+{pos_y}")

    def save_position(self):
        CURRENT_SETTINGS.update({'x_rule': 'absolute', 'y_rule': 'absolute', 'x_val': self.x_val, 'y_val': self.y_val, 'pos_anchor': self.anchor})
        save_config(); self.destroy()

    def reset_position(self, event=None):
        CURRENT_SETTINGS.update({'x_rule': 'default', 'y_rule': 'default', 'x_val': 0, 'y_val': 0, 'pos_anchor': 'se'})
        save_config(); self.destroy()

def main():
    global root, screen_width, screen_height, app_photo_icon, VAULT_GUARD
    register_app_user_model_id()
    set_app_user_model_id()
    root = tk.Tk(); root.withdraw()
    app_photo_icon = create_image_for_tk()
    screen_width, screen_height = root.winfo_screenwidth(), root.winfo_screenheight()

    tray_image = create_image_for_tray()
    icon = pystray.Icon("ehs_clipboard", tray_image, "eh's clipboard")

    def check_quit_flag():
        if UPDATE_AND_QUIT_FLAG.is_set():
            app_icon.stop()
            root.destroy()
        else:
            root.after(250, check_quit_flag)

    check_quit_flag()
    _perf('pre run_detached')
    icon.run_detached(setup=setup_tray_and_monitoring)
    _perf('after run_detached')
    _pump_tk_queue()
    root.after(0, _startup_background)
    root.mainloop()

_PERF_LOG = None
if os.environ.get('EH_CLIPBOARD_PERF'):
    try:
        _PERF_LOG = open(os.path.join(APP_DATA_PATH, 'perf.log'), 'a', encoding='utf-8')
        _PERF_LOG.write(f'\n=== run at {time.strftime("%H:%M:%S")} ===\n')
    except Exception:
        _PERF_LOG = None

def _perf(marker):
    if _PERF_LOG is not None:
        try:
            _PERF_LOG.write(f'{time.perf_counter():8.3f}  {marker}\n')
            _PERF_LOG.flush()
        except Exception:
            pass

def _startup_background():
    """Heavy startup work on a worker thread; tkinter-touching tail on main."""
    def _work():
        _perf('worker start')
        try:
            load_config(); _perf('load_config')
            ensure_default_files(); _perf('ensure_default_files')
            load_builtin_styles()

            load_styles_from_folder(); _perf('styles')
            load_animation_sets_from_folder(); _perf('anims')
            load_messages(); _perf('messages')
        except Exception:
            traceback.print_exc()
        finally:
            try:
                root.after(0, _startup_finalize)
            except Exception:
                pass

    threading.Thread(target=_work, daemon=True).start()

def _startup_finalize():
    global VAULT_GUARD
    try:
        validate_settings(); _perf('validate')
        update_systray_menu(); _perf('update_menu')
        try:
            VAULT_GUARD = _start_vault_guard(root); _perf('vault_guard')
        except Exception:
            VAULT_GUARD = None
        _restore_mask_session(); _perf('restore_mask')
    except Exception:
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "playsound":
        try:
            import winsound
            winsound.PlaySound(sys.argv[2], winsound.SND_FILENAME | winsound.SND_NODEFAULT)
        except Exception:
            pass
    elif len(sys.argv) > 1 and sys.argv[1] == "about":
        try:
            import json
            import about_qt
            
            ui_data = {}
            if len(sys.argv) > 2 and os.path.exists(sys.argv[2]):
                try:
                    with open(sys.argv[2], 'r', encoding='utf-8') as f:
                        ui_data = json.load(f)
                except Exception:
                    pass
            
            about_qt.show_about_dialog(ui_data, None)
        except Exception:
            pass
    elif len(sys.argv) > 1 and sys.argv[1] == "options":
        try:
            import json
            import options_qt
            
            data = {}
            if len(sys.argv) > 2 and os.path.exists(sys.argv[2]):
                try:
                    with open(sys.argv[2], 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except Exception:
                    pass
            
            options_qt.show_options_dialog(
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
        except Exception:
            pass
    elif len(sys.argv) > 2 and sys.argv[1] in ("pw_setup", "pw_unlock", "pw_editor", "pw_intruder"):
        try:
            import json
            import passwords_qt

            data = {}
            if os.path.exists(sys.argv[2]):
                try:
                    with open(sys.argv[2], 'r', encoding='utf-8') as f:
                        data = json.load(f)
                except Exception:
                    pass

            passwords_qt.run_mode(sys.argv[1], data)
        except Exception:
            pass
    else:
        main()