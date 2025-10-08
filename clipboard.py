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
import io
import configparser
import os
import webbrowser
import traceback
import queue
import about_qt
import subprocess

# --- Core Application Paths ---
# Use AppData for user-writable configuration and custom files.
APP_DATA_PATH = os.path.join(os.getenv('APPDATA'), "eh", "eh's Clipboard")
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
}

last_text = ""
toast = None
fade_out_job = None
screen_width = 0
screen_height = 0
app_icon = None
app_photo_icon = None
UPDATE_AND_QUIT_FLAG = threading.Event()

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
        except Exception as e:
            show_error_messagebox("Config File Error", f"Failed to load or parse '{CONFIG_FILE}'.\nUsing default settings.\n\nError: {e}")

def save_config():
    try:
        os.makedirs(APP_DATA_PATH, exist_ok=True)
        config['Settings'] = {k: str(v) for k, v in CURRENT_SETTINGS.items()}
        with open(CONFIG_FILE, 'w', encoding='utf-8') as configfile:
            config.write(configfile)
    except Exception as e:
        show_error_messagebox("Save Config Error", f"Could not save settings to '{CONFIG_FILE}'.\n\nError: {e}")

def load_builtin_styles():
    STYLES.clear()
    STYLES['Default Dark'] = {'look': {'bg': '#333333', 'fg': 'white', 'border': '#888888', 'font': ('Arial', 12)}, 'animation_in': 'Slide Up + Fade', 'animation_out': 'Slide Down + Fade', 'position': {'x_rule': 'default', 'y_rule': 'default', 'x_val': 0, 'y_val': 0, 'anchor': 'se'}}
    STYLES['Light'] = {'look': {'bg': '#f0f0f0', 'fg': 'black', 'border': '#b0b0b0', 'font': ('Arial', 12)}, 'animation_in': 'Fade In', 'animation_out': 'Fade Out', 'position': {'x_rule': 'default', 'y_rule': 'default', 'x_val': 0, 'y_val': 0, 'anchor': 'se'}}

def load_styles_from_folder():
    styles_dir = os.path.join(APP_DATA_PATH, 'Styles')
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
                            ANIMATION_SETS[s.get('name', entry)] = {'animation_in': s.get('animation_in'), 'animation_out': s.get('animation_out')}
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
    'SavePosition': 'Save Position', 'Cancel': 'Cancel', 
    'PositionerInstructions': 'Click and drag to select the notification area\nPress Ctrl+Shift+R to reset to default',
    'CheckForUpdates': 'Check for Updates', 'AboutWindowTitle': "About eh's Clipboard",
    'AboutTab': 'About', 'UpdatesTab': 'Updates', 'LicenseTab': 'License', 'UpdateNow': 'Update Now',
    'ViewOnGitHub': 'View Release on GitHub', 'CheckingForUpdates': 'Checking for updates...',
    'UpdateInitialPrompt': "Press 'Check for Updates' to see if a new version is available.",
    'UpdateNewVersion': 'New version available: {latest_tag} (you are {behind} version(s) behind, running {current_version})',
    'UpdateLatest': 'You are running the latest version!', 'UpdateFailed': "Failed to fetch update: {error}",
    'UpdateNoReleases': 'No releases found.', 'DownloadPreparing': 'Preparing download...',
    'DownloadStatus': 'Downloading... {downloaded} / {total} ({speed}, ETA: {eta})',
    'DownloadComplete': 'Download complete. Starting installer...',
    'DownloadInstallerFailed': 'Failed to run installer: {error}', 'DownloadFailedGeneric': 'Download failed: {error}'
}
UI = DEFAULT_UI.copy()

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

def ensure_default_files():
    """Ensures all necessary files and folders exist in AppData, creating them on first run."""
    os.makedirs(APP_DATA_PATH, exist_ok=True)

    if not os.path.exists(CONFIG_FILE):
        save_config() # Save the default config

    # Create default folders if they don't exist
    for folder in ['Styles', 'Animations', 'lang']:
        os.makedirs(os.path.join(APP_DATA_PATH, folder), exist_ok=True)
    
    # Create default language file if it's missing in AppData
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
    
    # Create default style files if they are missing
    for style_name, content in [
        ('Default Dark', '[Style]\nname = Default Dark\nbg = #333333\nfg = white\nborder = #888888\nfont_name = Arial\nfont_size = 12\nanimation_in = Slide Up + Fade\nanimation_out = Slide Down + Fade\nx_rule = default\ny_rule = default\nx_val = 0\ny_val = 0\nanchor = se\n'),
        ('Light', '[Style]\nname = Light\nbg = #f0f0f0\nfg = black\nborder = #b0b0b0\nfont_name = Arial\nfont_size = 12\nanimation_in = Fade In\nanimation_out = Fade Out\nx_rule = default\ny_rule = default\nx_val = 0\ny_val = 0\nanchor = se\n')
    ]:
        style_path = os.path.join(APP_DATA_PATH, 'Styles', style_name)
        os.makedirs(style_path, exist_ok=True)
        style_config_path = os.path.join(style_path, 'config.ini')
        if not os.path.exists(style_config_path):
            with open(style_config_path, 'w', encoding='utf-8') as f: f.write(content)

    # Create default animation set
    anim_path = os.path.join(APP_DATA_PATH, 'Animations', 'Default')
    os.makedirs(anim_path, exist_ok=True)
    anim_config_path = os.path.join(anim_path, 'config.ini')
    if not os.path.exists(anim_config_path):
        with open(anim_config_path, 'w', encoding='utf-8') as f: f.write('[AnimationSet]\nname = Default\nanimation_in = Slide Up + Fade\nanimation_out = Slide Down + Fade\n')

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
        cp = configparser.ConfigParser(interpolation=None)
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
        os.startfile(path)
    except Exception:
        try:
            if sys.platform == 'win32': os.system(f'start "" "{path}"')
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

def show_toast(text):
    global toast, fade_out_job
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
    style_name = CURRENT_SETTINGS.get('style', 'Default Dark')
    style_look = STYLES.get(style_name, STYLES['Default Dark'])['look']
    toast.config(bg=style_look['border'])
    content_frame = tk.Frame(toast, bg=style_look['bg'])
    content_frame.pack(padx=1, pady=1, fill=tk.BOTH, expand=True)

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

    anim_out_func = ANIMATIONS_OUT.get(CURRENT_SETTINGS.get('animation_out'), an_fade_out)
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
        if not is_truncated:
            x_pos, y_pos = calculate_position(w_small, h_small)
            fade_out_job = root.after(3000, lambda: anim_out_func(toast, w_small, h_small, x_pos, y_pos))
            return
        hover_state['job'] = root.after(50, shrink_toast)

    toast.bind("<Enter>", on_enter); toast.bind("<Leave>", on_leave)
    x, y = calculate_position(w_small, h_small)
    toast.geometry(f"{w_small}x{h_small}+{x}+{y}")
    toast.attributes("-alpha", 0); toast.deiconify()
    anim_in_func = ANIMATIONS_IN.get(CURRENT_SETTINGS.get('animation_in'), an_fade_in)
    anim_in_func(toast, w_small, h_small, x, y)
    fade_out_job = root.after(3000, lambda: anim_out_func(toast, w_small, h_small, x, y))

def monitor_clipboard():
    global last_text
    try: last_text = pyperclip.paste()
    except Exception: last_text = ""
    while True:
        try:
            current_text = pyperclip.paste()
            if current_text != last_text and current_text.strip() != "":
                last_text = current_text
                root.after(0, show_toast, current_text)
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
    if any(t.name == 'QtAboutThread' and t.is_alive() for t in threading.enumerate()):
        return
            
    about_thread = threading.Thread(
        target=about_qt.show_about_dialog, 
        args=(ui_dict, UPDATE_AND_QUIT_FLAG), 
        name='QtAboutThread', 
        daemon=True
    )
    about_thread.start()

def update_systray_menu():
    global app_icon
    styles_dir = os.path.join(APP_DATA_PATH, 'Styles')
    lang_dir = os.path.join(APP_DATA_PATH, 'lang')
    anim_dir = os.path.join(APP_DATA_PATH, 'Animations')

    def create_anim_action(key, value):
        def action(icon, item): CURRENT_SETTINGS[key] = value; save_config(); update_systray_menu()
        return action
    def style_menu_generator():
        load_builtin_styles(); load_styles_from_folder()
        for name in sorted(STYLES.keys()):
            def create_action(n): return lambda icon, item: apply_style(n)
            yield item(name, create_action(name), checked=lambda item, n=name: CURRENT_SETTINGS['style'] == n, radio=True)
    def lang_menu_generator():
        load_languages()
        current_lang = CURRENT_SETTINGS.get('language', 'en-US.ini')
        if current_lang not in LANGS:
            show_error_messagebox("Language File Not Found", f"Active language '{current_lang}' was deleted. Reverting to English.")
            CURRENT_SETTINGS['language'] = 'en-US.ini'; save_config(); load_messages(); update_systray_menu()
        for fname, display in sorted(LANGS.items(), key=lambda x: x[1]):
            def create_action(f): return lambda icon, item: (CURRENT_SETTINGS.update({'language': f}), save_config(), load_messages(), update_systray_menu())
            yield item(display, create_action(fname), checked=lambda item, f=fname: CURRENT_SETTINGS.get('language') == f, radio=True)
    def anim_set_menu_generator():
        load_animation_sets_from_folder()
        for name, anim_set in sorted(ANIMATION_SETS.items()):
            def create_action(a): return lambda icon, item: (CURRENT_SETTINGS.update(a), save_config(), update_systray_menu())
            yield item(name, create_action(anim_set), checked=lambda item, a=anim_set: CURRENT_SETTINGS['animation_in'] == a['animation_in'] and CURRENT_SETTINGS['animation_out'] == a['animation_out'], radio=True)

    settings_menu = [item(UI.get('EditConfig'), lambda: open_path(CONFIG_FILE)), pystray.Menu.SEPARATOR, item(UI.get('OpenStyles'), lambda: open_path(styles_dir)), item(UI.get('OpenLangs'), lambda: open_path(lang_dir)), item(UI.get('OpenAnims'), lambda: open_path(anim_dir)), item(UI.get('OpenGlobal'), lambda: open_path(APP_DATA_PATH))]
    
    menu_items = (
        item(UI.get('SetPosition'), lambda: open_positioner()),
        item(UI.get('Style'), pystray.Menu(lambda: style_menu_generator())),
        item(UI.get('AnimationSet'), pystray.Menu(lambda: anim_set_menu_generator())),
        item(UI.get('AnimationIn'), pystray.Menu(*(item(name, create_anim_action('animation_in', name), checked=lambda item, n=name: CURRENT_SETTINGS['animation_in'] == n, radio=True) for name in ANIMATIONS_IN.keys()))),
        item(UI.get('AnimationOut'), pystray.Menu(*(item(name, create_anim_action('animation_out', name), checked=lambda item, n=name: CURRENT_SETTINGS['animation_out'] == n, radio=True) for name in ANIMATIONS_OUT.keys()))),
        item(UI.get('Language'), pystray.Menu(lambda: lang_menu_generator())),
        pystray.Menu.SEPARATOR,
        item(UI.get('EditSettings'), pystray.Menu(*settings_menu)),
        pystray.Menu.SEPARATOR,
        item(UI.get('About'), lambda: open_about_threaded(UI)),
        item(UI.get('Quit'), lambda: (app_icon.stop(), root.destroy())),
    )
    if app_icon: app_icon.menu = pystray.Menu(*menu_items)

def setup_tray_and_monitoring(icon):
    global app_icon; app_icon = icon; icon.visible = True
    update_systray_menu()
    threading.Thread(target=monitor_clipboard, daemon=True).start()

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
        self.rect = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline="white", width=2, dash=(5, 5))

    def on_drag(self, event): self.canvas.coords(self.rect, self.start_x, self.start_y, event.x_root, event.y_root)

    def on_release(self, event):
        self.end_x, self.end_y = event.x_root, event.y_root
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
    global root, screen_width, screen_height, app_photo_icon
    root = tk.Tk(); root.withdraw()
    app_photo_icon = create_image_for_tk()
    screen_width, screen_height = root.winfo_screenwidth(), root.winfo_screenheight()
    
    ensure_default_files()
    load_config()
    load_builtin_styles()
    load_styles_from_folder()
    load_animation_sets_from_folder()
    load_messages()
    validate_settings()
    
    tray_image = create_image_for_tray()
    icon = pystray.Icon("ehs_clipboard", tray_image, "eh's clipboard")
    
    def check_quit_flag():
        if UPDATE_AND_QUIT_FLAG.is_set():
            app_icon.stop()
            root.destroy()
        else:
            root.after(250, check_quit_flag)
    
    check_quit_flag()
    threading.Thread(target=lambda: icon.run(setup=setup_tray_and_monitoring), daemon=True).start()
    root.mainloop()

if __name__ == "__main__":
    main()