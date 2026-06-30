"""
MineHost Local — 1:1 Aternos-Layout (lokal)
pip install customtkinter psutil requests pillow
pyinstaller --onefile --windowed --name MineHostLocal minehost_local.py
"""

import customtkinter as ctk
import tkinter as tk

# Fix: CTkWidget TclError wenn Canvas nach Destroy noch Configure-Events bekommt
def _patch_ctk_widgets_crash():
    widget_modules = [
        "customtkinter.windows.widgets.ctk_label",
        "customtkinter.windows.widgets.ctk_button",
        "customtkinter.windows.widgets.ctk_entry",
        "customtkinter.windows.widgets.ctk_frame",
        "customtkinter.windows.widgets.ctk_scrollable_frame",
        "customtkinter.windows.widgets.ctk_switch",
        "customtkinter.windows.widgets.ctk_slider",
        "customtkinter.windows.widgets.ctk_checkbox",
        "customtkinter.windows.widgets.ctk_optionmenu",
        "customtkinter.windows.widgets.ctk_progressbar",
    ]
    for mod_name in widget_modules:
        try:
            import importlib as _il
            m = _il.import_module(mod_name)
            cls_name = [n for n in dir(m) if n.startswith("CTk")][0]
            cls = getattr(m, cls_name)
            _orig = cls._update_dimensions_event
            def _safe(self, event=None, _o=_orig):
                try: _o(self, event)
                except Exception: pass
            cls._update_dimensions_event = _safe
        except Exception:
            pass
_patch_ctk_widgets_crash()
from tkinter import filedialog, messagebox
import json, os, hashlib, threading, subprocess, time, shutil, requests, random, string
import psutil
from pathlib import Path
from PIL import Image, ImageDraw
import faulthandler, signal as _signal

# Watchdog-Thread: schreibt alle 30s einen Stack-Dump wenn UI-Thread blockiert
def _start_freeze_watchdog(log_path: Path):
    import threading as _th
    _main_tid = _th.main_thread().ident
    def _watcher():
        import traceback as _tb, datetime as _dt, io as _io
        while True:
            time.sleep(30)
            try:
                buf = _io.StringIO()
                _tb.print_stack(sys._current_frames()[_main_tid], file=buf)
                entry = f"\n[{_dt.datetime.now()}] Main-Thread Stack:\n{buf.getvalue()}"
                log_path.parent.mkdir(parents=True, exist_ok=True)
                with open(log_path, "a", encoding="utf-8") as f: f.write(entry)
            except Exception: pass
    t = _th.Thread(target=_watcher, daemon=True)
    t.start()

import sys

# Drag & Drop Support — optional, kein Crash falls nicht installiert
try:
    from tkinterdnd2 import DND_FILES as _DND_FILES
    _DND_AVAILABLE = True
except ImportError:
    _DND_AVAILABLE = False
    _DND_FILES = None

# ── Pfade ─────────────────────────────────────────────────────────────────────
APP_DIR     = Path(os.getenv("APPDATA")) / "MineHostLocal"
USERS_DB    = APP_DIR / "users.json"
SERVERS_DIR = APP_DIR / "servers"
ACCESS_DB   = APP_DIR / "access.json"
SESSION_F   = APP_DIR / "session.json"
PLAYIT_EXE  = APP_DIR / "playit.exe"
APP_DIR.mkdir(parents=True, exist_ok=True)
SERVERS_DIR.mkdir(exist_ok=True)

PLAYIT_URL  = None   # wird dynamisch via GitHub API ermittelt

# ── Mine-Host Custom Tunnel API ───────────────────────────────────────────────
MINEHOST_TUNNEL_API    = "https://minecraft-tunnel-system-190266430698.europe-west3.run.app"
MINEHOST_TUNNEL_DOMAIN = "minehost-local.uk"

# ── Free-Version-Limits ────────────────────────────────────────────────────────
FREE_VERSION       = True   # True = kostenlose Version (1 Server, nur mine-host.local)
FREE_MAX_SERVERS   = 1

# ── Aternos-Farben ────────────────────────────────────────────────────────────
BG          = "#111317"
SIDEBAR_BG  = "#191c22"
CARD        = "#22262f"
CARD2       = "#1a1d24"
GREEN       = "#2ecc40"
GREEN_HOV   = "#27b038"
RED         = "#e74c3c"
RED_HOV     = "#c0392b"
BLUE        = "#3498db"
TEXT        = "#ffffff"
TEXT_MUTED  = "#8892a4"
BORDER      = "#2a2d36"
SIDEBAR_W   = 200

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# Windows: CMD-Fenster verstecken
CREATE_NO_WINDOW = 0x08000000

# Bekannte Vanilla-Server-JARs (Fallback wenn API nicht erreichbar)
VANILLA_JARS = {
    "1.21.4": "https://piston-data.mojang.com/v1/objects/4707d00eb834b446575d89a61a11b5d548d8c001/server.jar",
    "1.21.3": "https://piston-data.mojang.com/v1/objects/45810d238246d90e811d896f87b14695b7fb6839/server.jar",
    "1.21.1": "https://piston-data.mojang.com/v1/objects/59353fb40c36d304f2035d51e7d6e6baa98dc05c/server.jar",
    "1.21":   "https://piston-data.mojang.com/v1/objects/450698d1863ab5180c25d7c804ef0fe6369dd1ba/server.jar",
    "1.20.6": "https://piston-data.mojang.com/v1/objects/145ac199e80a12f5e79869b68af6dddc2c84e81e/server.jar",
    "1.20.4": "https://piston-data.mojang.com/v1/objects/8dd1a28015f51b1803213892b50b7b4fc76e594d/server.jar",
    "1.20.2": "https://piston-data.mojang.com/v1/objects/5b868151bd02b41319f54c8d4061b8cae84e665c/server.jar",
    "1.20.1": "https://piston-data.mojang.com/v1/objects/84194a2f286ef7c14ed7ce0090dba59902951553/server.jar",
    "1.20":   "https://piston-data.mojang.com/v1/objects/15c777e2cfe0556eef19aab534b186c0c6f277e1/server.jar",
    "1.19.4": "https://piston-data.mojang.com/v1/objects/8f3112a1049751cc472ec13e397eade5336ca7ae/server.jar",
    "1.19.3": "https://piston-data.mojang.com/v1/objects/c9df48efed58511cdd0213c56b9013a7b5c9ac1f/server.jar",
    "1.19.2": "https://piston-data.mojang.com/v1/objects/f69c284232d7c7580bd89a5a4931c3581eae1378/server.jar",
    "1.19.1": "https://piston-data.mojang.com/v1/objects/8399e1211e95faa421c1507b322dbeae86d604df/server.jar",
    "1.19":   "https://piston-data.mojang.com/v1/objects/e00c4052dac1d59a1188b2aa9d5a87113aaf1122/server.jar",
    "1.18.2": "https://piston-data.mojang.com/v1/objects/c8f83c5655308435b3dcf03c06d9fe8740a77469/server.jar",
    "1.18.1": "https://piston-data.mojang.com/v1/objects/125e5adf40c659fd3bce3e66e67a16bb49ecc1b9/server.jar",
    "1.18":   "https://piston-data.mojang.com/v1/objects/3cf24a8694aca6267883b17d934efacc5e44440d/server.jar",
    "1.17.1": "https://piston-data.mojang.com/v1/objects/a16d67e5807ef57a8e89f9e92f87e3f5e9d01388/server.jar",
    "1.17":   "https://piston-data.mojang.com/v1/objects/0a269b5f2c5b93b1712d0f5dc43b6182b9ab254e/server.jar",
    "1.16.5": "https://piston-data.mojang.com/v1/objects/1b557e7b033b583cd9f66746b7a9ab1ec1673eca/server.jar",
    "1.16.4": "https://piston-data.mojang.com/v1/objects/35139deedbd5182953cf1caa23835da59ca3d7cd/server.jar",
    "1.16.3": "https://piston-data.mojang.com/v1/objects/f02f4473dbf152c23d7d484952121db0b36698cb/server.jar",
    "1.16.2": "https://piston-data.mojang.com/v1/objects/c5f6fb23c3876461d46ec380421e42b289789530/server.jar",
    "1.16.1": "https://piston-data.mojang.com/v1/objects/a412fd69db1f81db3f511c1463fd304675244077/server.jar",
    "1.15.2": "https://piston-data.mojang.com/v1/objects/bb2b6b1aefcd70dfd1892149ac3a215f6c636b07/server.jar",
    "1.14.4": "https://piston-data.mojang.com/v1/objects/3dc3d84a581f14691199cf6831b71ed1296a9fdf/server.jar",
    "1.13.2": "https://piston-data.mojang.com/v1/objects/3737db93722a9e39eeada7c27e7aca28b144ffa7/server.jar",
    "1.12.2": "https://piston-data.mojang.com/v1/objects/886945bfb2b978778c3a0288fd7fab09d315b25f/server.jar",
    "1.12.1": "https://piston-data.mojang.com/v1/objects/a1a7f6dd66b5b9cc2c3b7bba30c98e2b7555b4a1/server.jar",
    "1.12":   "https://piston-data.mojang.com/v1/objects/8494e4c9d28af7eed1effef6e51569e498bb4d07/server.jar",
    "1.11.2": "https://piston-data.mojang.com/v1/objects/f00c294a1576e03fddcac777c3cf4c7d404c4ba4/server.jar",
    "1.10.2": "https://piston-data.mojang.com/v1/objects/3dc3d84a581f14691199cf6831b71ed1296a9fdf/server.jar",
    "1.9.4":  "https://piston-data.mojang.com/v1/objects/edbb7b16de67b99006773a4dc0e0f28e01fe6a6c/server.jar",
    "1.8.9":  "https://piston-data.mojang.com/v1/objects/b58b2ceb36e01251b9a9e3d916fdca8b8e9620b2/server.jar",
    "1.7.10": "https://piston-data.mojang.com/v1/objects/952438ac4e01b4d115c5fc38f891710c4941df29/server.jar",
}

# Wird beim Start live von Mojang geladen; Fallback = VANILLA_JARS keys
MC_VERSIONS     = list(VANILLA_JARS.keys())
_MC_VER_LOADED  = False

MC_VERSION_URLS: dict = {}   # version_id -> server.jar URL (live von Mojang)

def fetch_mc_versions_bg(callback):
    """Lädt alle Release-Versionen + Download-URLs von Mojang API im Hintergrund."""
    def _run():
        global MC_VERSIONS, _MC_VER_LOADED, MC_VERSION_URLS
        try:
            manifest = requests.get(
                "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json",
                timeout=8).json()
            releases = [v for v in manifest["versions"] if v["type"] == "release"]
            if not releases:
                return
            MC_VERSIONS = [v["id"] for v in releases]
            _MC_VER_LOADED = True
            if callback:
                callback(MC_VERSIONS)
            # Download-URLs im Hintergrund nachladen (top 20 reichen für die UI)
            for entry in releases[:20]:
                vid = entry["id"]
                if vid in MC_VERSION_URLS:
                    continue
                try:
                    meta = requests.get(entry["url"], timeout=6).json()
                    url  = meta.get("downloads", {}).get("server", {}).get("url")
                    if url:
                        MC_VERSION_URLS[vid] = url
                        VANILLA_JARS[vid] = url   # auch Fallback-Dict aktualisieren
                except Exception:
                    pass
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()

def get_vanilla_jar_url(mc_ver: str) -> str | None:
    """Gibt die Server-JAR URL zurück — erst Cache, dann live von Mojang."""
    if mc_ver in VANILLA_JARS:
        return VANILLA_JARS[mc_ver]
    # Noch nicht gecacht → direkt von Manifest holen
    try:
        manifest = requests.get(
            "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json",
            timeout=8).json()
        for entry in manifest["versions"]:
            if entry["id"] == mc_ver:
                meta = requests.get(entry["url"], timeout=6).json()
                url  = meta.get("downloads", {}).get("server", {}).get("url")
                if url:
                    VANILLA_JARS[mc_ver] = url
                    MC_VERSION_URLS[mc_ver] = url
                    return url
    except Exception:
        pass
    return None

SERVER_TYPES = {
    "Vanilla":       {"tag":"vanilla",  "icon":"✔",  "color":GREEN,    "desc":"Offizieller Mojang Server"},
    "Snapshot":      {"tag":"vanilla",  "icon":"📸", "color":"#1abc9c","desc":"Neueste Snapshot-Version"},
    "Paper/Bukkit":  {"tag":"paper",    "icon":"🧩", "color":GREEN,    "desc":"Für Plugins (empfohlen)"},
    "Spigot/Bukkit": {"tag":"spigot",   "icon":"🧩", "color":GREEN,    "desc":"Für Plugins"},
    "Purpur/Bukkit": {"tag":"purpur",   "icon":"🧩", "color":"#9b59b6","desc":"Für Plugins (mehr Features)"},
    "Folia":         {"tag":"folia",    "icon":"🧩", "color":"#1abc9c","desc":"Multithreaded Paper"},
    "Fabric":        {"tag":"fabric",   "icon":"⚙",  "color":"#f39c12","desc":"Für Mods"},
    "Quilt":         {"tag":"quilt",    "icon":"⚙",  "color":"#8e44ad","desc":"Für Mods"},
    "NeoForge":      {"tag":"neoforge", "icon":"⚙",  "color":RED,      "desc":"Für Mods"},
    "Forge":         {"tag":"forge",    "icon":"⚙",  "color":"#e67e22","desc":"Für Mods (klassisch)"},
    "Modpacks":      {"tag":"modpack",  "icon":"⚙",  "color":"#27ae60","desc":"Modpack-Server"},
    "Arclight":      {"tag":"arclight", "icon":"⚙",  "color":"#1abc9c","desc":"Plugins + Mods"},
}

PERMISSIONS = [
    ("server_startstop",  "Server starten / stoppen"),
    ("options",           "Optionen bearbeiten"),
    ("console",           "Konsole einsehen"),
    ("console_cmd",       "Befehle senden"),
    ("players_op",        "OP-Rechte vergeben"),
    ("players_whitelist", "Whitelist verwalten"),
    ("players_ban",       "Spieler bannen"),
    ("software",          "Software wechseln"),
    ("worlds",            "Welten verwalten"),
    ("backups",           "Backups erstellen"),
    ("files",             "Dateien/Mods verwalten"),
]

# ── Hilfsfunktionen ───────────────────────────────────────────────────────────
def hash_pw(pw):     return hashlib.sha256(pw.encode()).hexdigest()
def rnd_suffix(n=4): return "".join(random.choices(string.ascii_uppercase+string.digits, k=n))

def load_json(p, d=None):
    try:
        if Path(p).exists(): return json.loads(Path(p).read_text(encoding="utf-8"))
    except: pass
    return d if d is not None else {}

def save_json(p, data):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def load_users():  return load_json(USERS_DB, {})
def save_users(d): save_json(USERS_DB, d)

def save_session(username): save_json(SESSION_F, {"user": username})
def load_session():
    d = load_json(SESSION_F, {})
    return d.get("user")
def clear_session(): SESSION_F.unlink(missing_ok=True)

JAVA_SEARCH_DIRS = [
    Path(os.getenv("ProgramFiles", "C:/Program Files")) / "Java",
    Path(os.getenv("ProgramFiles", "C:/Program Files")) / "Eclipse Adoptium",
    Path(os.getenv("ProgramFiles", "C:/Program Files")) / "Microsoft" / "jdk",
    Path(os.getenv("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Java",
    Path("C:/Program Files/Java"),
    Path("C:/Program Files/Eclipse Adoptium"),
    Path("C:/Program Files/Microsoft/jdk"),
    Path("C:/Program Files/Eclipse Adoptium"),
]

def _get_java_version(java_exe: str) -> int:
    """Gibt die Hauptversionsnummer (17, 21, 25, …) zurück oder 0 bei Fehler."""
    try:
        r = subprocess.run([java_exe, "-version"],
                           capture_output=True, text=True, timeout=5,
                           creationflags=CREATE_NO_WINDOW)
        out = r.stderr or r.stdout
        import re
        m = re.search(r'version "(\d+)', out)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return 0

def find_java_exe(min_version: int = 1) -> str | None:
    """
    Findet java.exe mit mindestens `min_version`.
    Gibt den Pfad mit der höchsten passenden Version zurück.
    """
    candidates: list[tuple[int, str]] = []

    # 1. java im PATH
    try:
        subprocess.run(["java", "-version"], capture_output=True, timeout=5,
                       creationflags=CREATE_NO_WINDOW)
        v = _get_java_version("java")
        if v >= min_version:
            candidates.append((v, "java"))
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # 2. Installationsordner
    for base in JAVA_SEARCH_DIRS:
        if not base.exists():
            continue
        for java_exe in base.rglob("java.exe"):
            if "bin" in java_exe.parts:
                v = _get_java_version(str(java_exe))
                if v >= min_version:
                    candidates.append((v, str(java_exe)))

    if not candidates:
        return None
    # Höchste passende Version bevorzugen
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]

def java_available():
    return find_java_exe() is not None

def required_java_for_mc(mc_ver: str) -> int:
    """Gibt die mindestens benötigte Java-Version für eine MC-Version zurück."""
    # Neue Versionsbezeichnung (z.B. "26.2", "25.1") → Java 25
    if not mc_ver.startswith("1."):
        return 25
    parts = mc_ver.lstrip("1.").split(".")
    try:
        minor = int(parts[0]) if parts else 0
    except ValueError:
        minor = 0
    if minor >= 21:   return 21   # 1.21+
    if minor >= 17:   return 17   # 1.17–1.20
    return 8

def get_playit_download_url():
    """Holt die echte 64-bit Windows EXE-URL vom GitHub Release API."""
    try:
        r = requests.get(
            "https://api.github.com/repos/playit-cloud/playit-agent/releases/latest",
            timeout=10, headers={"Accept": "application/vnd.github+json"}
        )
        assets = r.json().get("assets", [])
        for a in assets:
            name = a["name"].lower()
            if "windows" in name and ("x86_64" in name or "amd64" in name) and name.endswith(".exe"):
                return a["browser_download_url"]
        for a in assets:
            if a["name"].lower().endswith(".exe"):
                return a["browser_download_url"]
    except Exception:
        pass
    return None

def download_playit(on_done=None, on_progress=None):
    """Lädt playit.exe (64-bit) herunter falls noch nicht vorhanden."""
    def run():
        if PLAYIT_EXE.exists():
            if on_done: on_done()
            return
        try:
            if on_progress: on_progress("Ermittle playit.gg Download-URL…")
            url = get_playit_download_url()
            if not url:
                if on_progress: on_progress("playit.gg URL nicht gefunden.")
                return
            if on_progress: on_progress("Lade playit.gg herunter…")
            r = requests.get(url, stream=True, timeout=120, allow_redirects=True)
            total = int(r.headers.get("content-length", 0))
            done  = 0
            with open(PLAYIT_EXE, "wb") as fh:
                for chunk in r.iter_content(8192):
                    fh.write(chunk)
                    done += len(chunk)
                    if on_progress and total:
                        on_progress(f"Lade playit.gg… {done*100//total}%")
            if on_done: on_done()
        except Exception as e:
            if on_progress: on_progress(f"Download fehlgeschlagen: {e}")
    threading.Thread(target=run, daemon=True).start()

# ── playit.gg Tunnel-Manager ──────────────────────────────────────────────────
# Globaler Singleton-Prozess — wird NIE doppelt gestartet
_PLAYIT_SINGLETON_PROC = None
_PLAYIT_SINGLETON_LOCK = threading.Lock()

class PlayitManager:
    """
    Verwaltet den playit.gg Tunnel-Prozess als Singleton.
    Nur EINE playit.exe-Instanz läuft gleichzeitig, egal wie viele
    PlayitManager-Objekte erstellt werden.
    """
    def __init__(self, srv_dir: Path):
        self.srv_dir   = srv_dir
        self.proc      = None
        self.toml_path = srv_dir / "playit.toml"
        self._thread   = None

        # Callbacks
        self.on_claim   = None
        self.on_address = None
        self.on_log     = None

    def _kill_existing(self):
        """Beendet alle laufenden playit.exe Instanzen via psutil."""
        global _PLAYIT_SINGLETON_PROC
        # Eigenen Prozess stoppen
        if _PLAYIT_SINGLETON_PROC and _PLAYIT_SINGLETON_PROC.poll() is None:
            try: _PLAYIT_SINGLETON_PROC.terminate()
            except: pass
            try: _PLAYIT_SINGLETON_PROC.wait(timeout=3)
            except: pass
        _PLAYIT_SINGLETON_PROC = None
        # Alle restlichen playit.exe via psutil
        try:
            for p in psutil.process_iter(["name"]):
                if "playit" in (p.info.get("name") or "").lower():
                    try: p.kill()
                    except: pass
        except: pass

    def is_running(self):
        global _PLAYIT_SINGLETON_PROC
        return (_PLAYIT_SINGLETON_PROC is not None
                and _PLAYIT_SINGLETON_PROC.poll() is None)

    def start(self):
        """Startet playit.exe — nur wenn noch nicht läuft (Singleton)."""
        global _PLAYIT_SINGLETON_PROC, _PLAYIT_SINGLETON_LOCK

        def _launch():
            global _PLAYIT_SINGLETON_PROC
            import time as _t

            with _PLAYIT_SINGLETON_LOCK:
                # Prüfen ob schon eine Instanz läuft
                if _PLAYIT_SINGLETON_PROC and _PLAYIT_SINGLETON_PROC.poll() is None:
                    if self.on_log:
                        self.on_log("[playit.gg] Prozess läuft bereits — kein Neustart.\n")
                    # Trotzdem Output lesen falls callbacks gesetzt
                    self._read_output()
                    return

                # Alte Prozesse beenden
                self._kill_existing()
                _t.sleep(0.5)

            # 2. Download falls nötig
            if not PLAYIT_EXE.exists():
                if self.on_log: self.on_log("[playit.gg] Lade Agent herunter…\n")
                done_ev = threading.Event()
                download_playit(
                    on_done=done_ev.set,
                    on_progress=lambda m: self.on_log(f"[playit.gg] {m}\n") if self.on_log else None
                )
                done_ev.wait(timeout=180)
                if not PLAYIT_EXE.exists():
                    if self.on_log: self.on_log("[playit.gg] Download fehlgeschlagen.\n")
                    return

            # 3. Secret Key aus toml lesen und als --secret übergeben
            secret_key = ""
            if self.toml_path.exists():
                secret_key = self.toml_path.read_text(encoding="utf-8").strip()

            if not secret_key:
                if self.on_log: self.on_log("[playit.gg] Kein Secret Key vorhanden.\n")
                return

            if self.on_log:
                self.on_log(f"[playit.gg] Starte Tunnel mit Secret Key…\n")

            try:
                log_path = self.srv_dir / "playit_log.txt"
                self.proc = subprocess.Popen(
                    [str(PLAYIT_EXE), "--secret", secret_key,
                     "-l", str(log_path)],
                    cwd=str(self.srv_dir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    text=True, bufsize=1,
                    creationflags=CREATE_NO_WINDOW
                )
            except Exception as e:
                if self.on_log: self.on_log(f"[playit.gg] Startfehler: {e}\n")
                return

            self._read_output()

        self._thread = threading.Thread(target=_launch, daemon=True)
        self._thread.start()

    def _read_output(self):
        import re, time as _t
        addr_patterns = [
            r"([\w][\w\-]*\.at\.playit\.gg:\d+)",
            r"([\w][\w\-]*\.playit\.gg:\d+)",
            r"tunnel address[:\s]+([\w\.\-]+:\d+)",
            r"address[:\s]+([\w\.\-]+:\d+)",
            r"allocated.*?([\w\.\-]+\.playit\.gg:\d+)",
            r"([\w\-]+\.ply\.one:\d+)",
        ]
        _reported_addr = set()
        log_path = self.srv_dir / "playit_log.txt"
        seen_lines = 0

        def _parse(line):
            low = line.lower()
            if "email_not_verified" in low or "email not verified" in low:
                if self.on_log:
                    self.on_log("[playit.gg] ⚠ Bitte E-Mail auf playit.gg verifizieren!\n")
            if "playit connected" in low:
                if self.on_log:
                    self.on_log("[playit.gg] ✓ Agent verbunden. Warte auf Tunnel…\n")
            for pat in addr_patterns:
                m = re.search(pat, line, re.IGNORECASE)
                if m:
                    addr = m.group(1)
                    if addr not in _reported_addr:
                        _reported_addr.add(addr)
                        if self.on_address:
                            self.on_address(addr)
                    break

        # Drain stdout (wird meist leer sein)
        def _drain_stdout():
            try:
                for raw in self.proc.stdout:
                    line = raw.rstrip()
                    if line and self.on_log:
                        self.on_log(f"[playit.gg] {line}\n")
                    _parse(line)
            except: pass
        threading.Thread(target=_drain_stdout, daemon=True).start()

        # Alte Log-Datei löschen damit kein alter Inhalt wiederholt wird
        try:
            if log_path.exists():
                log_path.unlink()
        except: pass

        # Log-Datei tailing — nur NEUE Zeilen nach dem Start lesen
        _t.sleep(0.5)  # kurz warten bis playit die Datei erstellt
        while self.proc.poll() is None:
            try:
                if log_path.exists():
                    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                    new_lines = lines[seen_lines:]
                    seen_lines = len(lines)
                    for line in new_lines:
                        if line and self.on_log:
                            self.on_log(f"[playit.gg] {line}\n")
                        _parse(line)
            except Exception:
                pass
            _t.sleep(1)

    def stop(self):
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except:
                try: self.proc.kill()
                except: pass
            self.proc = None
        # playit.toml NIEMALS löschen — Adresse bleibt für immer

    def is_running(self):
        return self.proc is not None and self.proc.poll() is None

def install_java_background(on_done=None, on_error=None, version: int = 21):
    """Installiert Eclipse Temurin via winget. version = 21, 25, …"""
    def run():
        # Pakete in Präferenz-Reihenfolge versuchen
        pkg_candidates = [
            f"EclipseAdoptium.Temurin.{version}.JRE",
            f"EclipseAdoptium.Temurin.{version}.JDK",
            f"Oracle.JDK.{version}",
            f"Microsoft.OpenJDK.{version}",
        ]
        for pkg in pkg_candidates:
            try:
                result = subprocess.run(
                    ["winget", "install", "--id", pkg,
                     "-e", "--silent", "--accept-source-agreements", "--accept-package-agreements"],
                    capture_output=True, text=True, timeout=300,
                    creationflags=CREATE_NO_WINDOW
                )
                ok = (result.returncode == 0
                      or "bereits" in (result.stdout+result.stderr).lower()
                      or "already" in (result.stdout+result.stderr).lower())
                if ok:
                    if on_done: on_done()
                    return
            except subprocess.TimeoutExpired:
                if on_error: on_error(f"Timeout bei Java {version} Installation.")
                return
            except Exception:
                pass
        if on_error: on_error(f"Java {version} konnte nicht installiert werden.")
    threading.Thread(target=run, daemon=True).start()

def load_server_cfg(name):
    return load_json(SERVERS_DIR / name / "minehost.json", {})

def save_server_cfg(name, cfg):
    p = SERVERS_DIR / name
    p.mkdir(parents=True, exist_ok=True)
    save_json(p / "minehost.json", cfg)
    print(f"[SAVE] {p / 'minehost.json'} => {cfg}")   # debug

def list_servers():
    result = []
    if not SERVERS_DIR.exists(): return result
    for d in SERVERS_DIR.iterdir():
        if d.is_dir() and (d / "minehost.json").exists():
            result.append(d.name)
    return result

def _get_paper_url_new(mc_ver: str) -> str | None:
    """Neue PaperMC CDN (fill-data.papermc.io) für 26.x Versionen."""
    import re as _re
    # Methode 1: fill.papermc.io API (liefert SHA256 für CDN-URL)
    for base in ("https://fill.papermc.io", "https://api.papermc.io"):
        try:
            r = requests.get(f"{base}/v2/projects/paper/versions/{mc_ver}/builds",
                             headers={"User-Agent": "MineHostLocal/1.0"}, timeout=10)
            if r.status_code != 200: continue
            builds = r.json().get("builds", [])
            if not builds: continue
            latest = builds[-1]
            fname = latest["downloads"]["application"]["name"]
            sha = latest["downloads"]["application"].get("sha256", "")
            if sha:
                return f"https://fill-data.papermc.io/v1/objects/{sha}/{fname}"
        except: continue
    # Methode 2: Downloads-Seite scrapen (Fallback)
    try:
        r = requests.get("https://papermc.io/downloads/paper",
                         headers={"User-Agent": "MineHostLocal/1.0"}, timeout=10)
        pattern = rf'https://fill-data\.papermc\.io/v1/objects/[0-9a-f]+/paper-{_re.escape(mc_ver)}-(\d+)\.jar'
        matches = _re.findall(pattern, r.text)
        if not matches: return None
        latest_build = max(int(b) for b in matches)
        url_pattern = rf'(https://fill-data\.papermc\.io/v1/objects/[0-9a-f]+/paper-{_re.escape(mc_ver)}-{latest_build}\.jar)'
        url_match = _re.search(url_pattern, r.text)
        return url_match.group(1) if url_match else None
    except: return None

def _get_paper_versions_from_page() -> list[str]:
    """Holt alle verfügbaren Paper-Versionen (1.x UND 26.x) von der Downloads-Seite."""
    import re as _re
    try:
        r = requests.get("https://papermc.io/downloads/paper",
                         headers={"User-Agent": "MineHostLocal/1.0"}, timeout=10)
        # Extrahiere Versionen aus Dateinamen
        vers = _re.findall(r'paper-([\d.]+(?:\.\d+)?)-\d+\.jar', r.text)
        seen, result = set(), []
        for v in vers:
            if v not in seen:
                seen.add(v); result.append(v)
        return result
    except: return []

def get_paper_url(mc_ver):
    # Neue Versionen (26.x) → direkt von Downloads-Seite
    if not mc_ver.startswith("1."):
        url = _get_paper_url_new(mc_ver)
        if url: return url
    try:
        r = requests.get(f"https://api.papermc.io/v2/projects/paper/versions/{mc_ver}/builds", timeout=10)
        builds = r.json().get("builds", [])
        if not builds: return None
        b = builds[-1]
        return f"https://api.papermc.io/v2/projects/paper/versions/{mc_ver}/builds/{b['build']}/downloads/{b['downloads']['application']['name']}"
    except: return None

_LOGO_PATH = Path(__file__).parent / "viscode_logo.png"
_logo_cache: dict = {}

def make_logo(size=40):
    if size in _logo_cache:
        return _logo_cache[size]
    if _LOGO_PATH.exists():
        try:
            raw = Image.open(str(_LOGO_PATH)).convert("RGBA")
            raw = raw.resize((size, size), Image.LANCZOS)
            img = ctk.CTkImage(light_image=raw, dark_image=raw, size=(size, size))
            _logo_cache[size] = img
            return img
        except Exception:
            pass
    # Fallback: einfaches grünes "VC"-Icon
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d   = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, size, size], radius=size//5, fill="#1a2233")
    result = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    _logo_cache[size] = result
    return result

# ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
# LOGIN
# ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
class LoginWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MineHost Local")
        self.geometry("420x560")
        self.resizable(False,False)
        self.configure(fg_color=BG)
        self._mode = "login"
        self._build()

    def _build(self):
        logo = make_logo(64)
        ctk.CTkLabel(self, image=logo, text="").pack(pady=(40,6))
        ctk.CTkLabel(self, text="MineHost Local",
                     font=ctk.CTkFont("Segoe UI",24,"bold"), text_color=GREEN).pack()
        ctk.CTkLabel(self, text="Dein lokaler Minecraft-Manager",
                     font=ctk.CTkFont("Segoe UI",12), text_color=TEXT_MUTED).pack(pady=(2,24))

        box = ctk.CTkFrame(self, fg_color=SIDEBAR_BG, corner_radius=12)
        box.pack(padx=12, fill="x")

        self.tabs = ctk.CTkSegmentedButton(box, values=["Login","Registrieren"],
                                            command=self._switch,
                                            fg_color=CARD, selected_color=GREEN,
                                            selected_hover_color=GREEN_HOV,
                                            unselected_color=CARD,
                                            font=ctk.CTkFont("Segoe UI",13,"bold"))
        self.tabs.set("Login")
        self.tabs.pack(padx=18, pady=(18,14), fill="x")

        def field(parent, label, ph, show=""):
            ctk.CTkLabel(parent, text=label, anchor="w", text_color=TEXT_MUTED,
                         font=ctk.CTkFont("Segoe UI",11)).pack(padx=18, fill="x")
            e = ctk.CTkEntry(parent, placeholder_text=ph, show=show,
                              fg_color=CARD, border_color=BORDER,
                              text_color=TEXT, font=ctk.CTkFont("Segoe UI",13))
            e.pack(padx=18, pady=(2,10), fill="x")
            return e

        self.e_user  = field(box, "Benutzername", "z.B. Steve")
        self.e_pw    = field(box, "Passwort", "••••••••", "•")
        self.e_email = ctk.CTkEntry(box, placeholder_text="E-Mail (optional)",
                                     fg_color=CARD, border_color=BORDER,
                                     text_color=TEXT, font=ctk.CTkFont("Segoe UI",13))

        self.btn = ctk.CTkButton(box, text="Einloggen", fg_color=GREEN,
                                  hover_color=GREEN_HOV, text_color="#000",
                                  font=ctk.CTkFont("Segoe UI",14,"bold"),
                                  height=44, corner_radius=8, command=self._submit)
        self.btn.pack(padx=18, pady=(4,18), fill="x")

        self.err_lbl = ctk.CTkLabel(self, text="", text_color=RED,
                                     font=ctk.CTkFont("Segoe UI",12))
        self.err_lbl.pack()
        self.bind("<Return>", lambda _: self._submit())

    def _switch(self, val):
        self._mode = "register" if val == "Registrieren" else "login"
        if self._mode == "register":
            self.e_email.pack(in_=self.e_pw.master, padx=18, pady=(2,10), fill="x", before=self.btn)
            self.btn.configure(text="Registrieren")
        else:
            self.e_email.pack_forget()
            self.btn.configure(text="Einloggen")

    def _submit(self):
        user, pw = self.e_user.get().strip(), self.e_pw.get()
        if not user or not pw:
            self.err_lbl.configure(text="Bitte alle Felder ausfüllen.")
            return
        users = load_users()
        if self._mode == "login":
            if user not in users or users[user]["pw"] != hash_pw(pw):
                self.err_lbl.configure(text="Falscher Benutzername oder Passwort.")
                return
        else:
            if user in users:
                self.err_lbl.configure(text="Benutzername bereits vergeben.")
                return
            users[user] = {"pw": hash_pw(pw), "email": self.e_email.get().strip(), "role": "admin"}
            save_users(users)
        save_session(user)
        self._next_user = user
        self.quit()  # Mainloop sauber beenden, äußerer Code startet MainApp

# ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
# SERVER ERSTELLEN (Aternos-Stil)
# ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
class CreateServerWindow(ctk.CTkToplevel):
    def __init__(self, master, on_done):
        super().__init__(master)
        self.on_done  = on_done
        self._sel_type = "Vanilla"
        self.title("Server erstellen")
        self.geometry("700x760")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self.grab_set()
        self._build()

    def _build(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=SIDEBAR_BG, corner_radius=0, height=60)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="Erstelle einen Server",
                     font=ctk.CTkFont("Segoe UI",18,"bold"), text_color=GREEN).pack(side="left", padx=20, pady=16)

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        # ── Spieltyp (für Tunnel) ─────────────────────────────────────────────
        sec0 = self._section(scroll, "Spieltyp")
        ctk.CTkLabel(sec0,
            text="Welches Spiel soll der Server hosten?\n(Wird für den playit.gg Tunnel verwendet)",
            text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10)
            ).pack(padx=18, pady=(8,6), anchor="w")
        self._game_type = tk.StringVar(value="minecraft-java")
        game_row = ctk.CTkFrame(sec0, fg_color="transparent")
        game_row.pack(padx=18, pady=(0,12), fill="x")
        GAME_TYPES = [
            ("⛏ ?  Minecraft Java",    "minecraft-java"),
            ("📱  Minecraft Bedrock", "minecraft-bedrock"),
            ("🌍 ?  Terraria",          "terraria"),
            ("🎮  Hytale",            "hytale"),
        ]
        for lbl, val in GAME_TYPES:
            ctk.CTkRadioButton(game_row, text=lbl, variable=self._game_type, value=val,
                               text_color=TEXT, fg_color=GREEN, hover_color=GREEN_HOV,
                               font=ctk.CTkFont("Segoe UI",12)
                               ).pack(side="left", padx=(0,16))

        # Server-Name + Adresse
        sec1 = self._section(scroll, "Server-Details")
        self._field_lbl(sec1, "Server-Name")
        self.e_name = self._entry(sec1, "Mein Server")

        self._field_lbl(sec1, "Server-Adresse  (playit.gg — wird beim ersten Start generiert)")
        ctk.CTkLabel(sec1,
                     text="  Die echte Domain wird beim ersten Serverstart automatisch von playit.gg vergeben.",
                     text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10),
                     anchor="w").pack(padx=18, pady=(0,12), fill="x")
        ctk.CTkLabel(sec1, text="Port", anchor="w", text_color=TEXT_MUTED,
                     font=ctk.CTkFont("Segoe UI",11)).pack(padx=18, fill="x")
        self.e_port = self._entry(sec1, "25565", default="25565")
        ctk.CTkLabel(sec1, text="Max. Spieler", anchor="w", text_color=TEXT_MUTED,
                     font=ctk.CTkFont("Segoe UI",11)).pack(padx=18, fill="x")
        self.e_players = self._entry(sec1, "20", default="20")
        ctk.CTkLabel(sec1, text="Beschreibung (MotD)", anchor="w", text_color=TEXT_MUTED,
                     font=ctk.CTkFont("Segoe UI",11)).pack(padx=18, fill="x")
        self.e_motd = self._entry(sec1, "Ein epischer Minecraft Server!")

        # Server-Typ
        sec2 = self._section(scroll, "Java Edition")
        grid = ctk.CTkFrame(sec2, fg_color="transparent")
        grid.pack(padx=14, pady=(4,14), fill="x")
        self._type_btns = {}
        cols = 3
        for i, (name, info) in enumerate(SERVER_TYPES.items()):
            r, c = divmod(i, cols)
            btn = ctk.CTkButton(grid,
                text=f"{info['icon']}  {name}",
                height=56, corner_radius=8,
                fg_color=CARD, hover_color=info["color"],
                text_color=TEXT, font=ctk.CTkFont("Segoe UI",12),
                command=lambda n=name: self._pick(n))
            btn.grid(row=r, column=c, padx=3, pady=3, sticky="ew")
            grid.grid_columnconfigure(c, weight=1)
            self._type_btns[name] = btn

            # Tooltip-ähnliches Label darunter
            sub = ctk.CTkLabel(grid, text=info["desc"], text_color=TEXT_MUTED,
                                font=ctk.CTkFont("Segoe UI",9))
            sub.grid(row=r*2+1 if False else r+20, column=c)   # skip subtitles for clean grid
        self._pick("Vanilla")

        # Version (dynamisch je nach gewähltem Server-Typ)
        sec3 = self._section(scroll, "Version")
        self.ver_var = ctk.StringVar(value=MC_VERSIONS[0])
        self._ver_om = ctk.CTkOptionMenu(sec3, variable=self.ver_var, values=MC_VERSIONS,
                                fg_color=CARD, button_color=BLUE,
                                font=ctk.CTkFont("Segoe UI",13), text_color=TEXT,
                                dropdown_fg_color=CARD, dropdown_text_color=TEXT)
        self._ver_om.pack(padx=18, pady=(4,6), fill="x")
        self._ver_status = ctk.CTkLabel(sec3, text="⟳ Lade verfügbare Versionen…",
                                         text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",9))
        self._ver_status.pack(padx=18, pady=(0,10), anchor="w")

        def _load_versions_for_type(sw_name="Vanilla"):
            """Lädt nur Versionen die für den gewählten Server-Typ verfügbar sind."""
            self._ver_status.configure(text=f"⟳ Lade Versionen für {sw_name}…",
                                        text_color=TEXT_MUTED)
            tag = SERVER_TYPES.get(sw_name, {}).get("tag", "vanilla")

            def _fetch():
                versions = []
                try:
                    if tag in ("paper","folia"):
                        proj = "folia" if tag=="folia" else "paper"
                        r = requests.get(f"https://api.papermc.io/v2/projects/{proj}",
                                         timeout=8)
                        # Nur Versionen die wirklich Builds haben
                        raw = r.json().get("versions", [])
                        versions = list(reversed(raw))  # neueste zuerst
                    elif tag == "purpur":
                        r = requests.get("https://api.purpurmc.org/v2/purpur", timeout=8)
                        versions = list(reversed(r.json().get("versions",[])))
                    elif tag == "fabric":
                        r = requests.get("https://meta.fabricmc.net/v2/versions/game", timeout=8)
                        versions = [v["version"] for v in r.json() if v.get("stable")]
                    elif tag == "quilt":
                        r = requests.get("https://meta.quiltmc.org/v3/versions/game", timeout=8)
                        stable = [v for v in r.json() if not any(
                            x in v.get("version","") for x in ("pre","rc","alpha","beta"))]
                        versions = [v["version"] for v in stable]
                    elif tag == "neoforge":
                        r = requests.get(
                            "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge",
                            timeout=8)
                        vers = r.json().get("versions",[])
                        mc_map = {}
                        for v in vers:
                            mc = ".".join(v.split(".")[:3]) if v.count(".")>=2 else v.split(".")[0]
                            mc_map[mc] = v
                        versions = list(reversed(list(mc_map.keys())))
                    elif tag == "forge":
                        r = requests.get(
                            "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json",
                            timeout=8)
                        promos = r.json().get("promos",{})
                        mc_vers = sorted(set(k.split("-")[0] for k in promos.keys()), reverse=True)
                        versions = mc_vers
                    else:
                        # Vanilla/Snapshot
                        r = requests.get(
                            "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json",
                            timeout=8)
                        vtype = "snapshot" if tag=="snapshot" else "release"
                        versions = [v["id"] for v in r.json().get("versions",[])
                                    if v["type"]==vtype]
                except: pass

                if not versions:
                    versions = MC_VERSIONS

                def _apply(vs=versions, sw=sw_name):
                    try:
                        self._ver_om.configure(values=vs)
                        self.ver_var.set(vs[0])
                        self._ver_status.configure(
                            text=f"✓  {len(vs)} Versionen für {sw}",
                            text_color=GREEN)
                    except: pass
                self.after(0, _apply)

            threading.Thread(target=_fetch, daemon=True).start()

        # Initial Vanilla laden
        _load_versions_for_type("Vanilla")
        # Merken für _pick
        self._load_versions_for_type = _load_versions_for_type

        # Installationsordner
        sec_loc = self._section(scroll, "Speicherort")
        loc_row = ctk.CTkFrame(sec_loc, fg_color="transparent")
        loc_row.pack(padx=18, pady=(6,12), fill="x")
        loc_row.grid_columnconfigure(0, weight=1)
        default_loc = str(SERVERS_DIR)
        self._install_path = ctk.StringVar(value=default_loc)
        loc_entry = ctk.CTkEntry(loc_row, textvariable=self._install_path,
                                  fg_color=CARD, border_color=BORDER,
                                  text_color=TEXT, font=ctk.CTkFont("Segoe UI",12))
        loc_entry.grid(row=0, column=0, sticky="ew", padx=(0,8))
        def _browse_loc():
            d = filedialog.askdirectory(title="Server-Ordner wählen",
                                         initialdir=self._install_path.get())
            if d: self._install_path.set(d)
        ctk.CTkButton(loc_row, text="📁 Wählen", width=90, height=34,
                      fg_color=CARD, hover_color=BORDER, text_color=TEXT,
                      font=ctk.CTkFont("Segoe UI",11), corner_radius=6,
                      command=_browse_loc).grid(row=0, column=1)

        # Welt aus Minecraft-Launcher importieren
        sec_world = self._section(scroll, "Welt importieren  (optional)")
        _mc_saves = Path(os.getenv("APPDATA","")) / ".minecraft" / "saves"
        _launcher_worlds = []
        if _mc_saves.exists():
            try: _launcher_worlds = [d.name for d in _mc_saves.iterdir() if d.is_dir()]
            except: pass
        if _launcher_worlds:
            ctk.CTkLabel(sec_world,
                         text="Welt aus deinem Minecraft-Launcher übernehmen:",
                         text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10)
                         ).pack(padx=18, pady=(8,4), anchor="w")
            self._import_world = ctk.StringVar(value="— Keine (neue Welt) —")
            world_opts = ["— Keine (neue Welt) —"] + _launcher_worlds
            ctk.CTkOptionMenu(sec_world, variable=self._import_world, values=world_opts,
                               fg_color=CARD, button_color=BLUE,
                               font=ctk.CTkFont("Segoe UI",12), text_color=TEXT,
                               dropdown_fg_color=CARD, dropdown_text_color=TEXT
                               ).pack(padx=18, pady=(0,12), fill="x")
            ctk.CTkLabel(sec_world,
                         text=f"📂  Launcher-Welten gefunden in: {_mc_saves}",
                         text_color="#2ecc71", font=ctk.CTkFont("Segoe UI",9)
                         ).pack(padx=18, pady=(0,10), anchor="w")
        else:
            self._import_world = ctk.StringVar(value="— Keine —")
            ctk.CTkLabel(sec_world,
                         text="Kein Minecraft-Launcher gefunden  (%APPDATA%\\.minecraft\\saves\\)",
                         text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10)
                         ).pack(padx=18, pady=12, anchor="w")
        self._mc_saves_path = _mc_saves

        # Region (immer Lokal)
        sec4 = self._section(scroll, "Region")
        rg = ctk.CTkFrame(sec4, fg_color="transparent")
        rg.pack(padx=18, pady=(4,14))
        ctk.CTkLabel(rg, text="🖥  Lokal  (dieser PC)", text_color=TEXT,
                     font=ctk.CTkFont("Segoe UI",13)).pack(side="left", padx=4)

        # ── Import von Exaroton / Aternos ────────────────────────────────────
        sec_import = self._section(scroll, "📥  Von Exaroton / Aternos importieren  (optional)")

        ctk.CTkLabel(sec_import,
            text="Server von Exaroton oder Aternos übernehmen.\n"
                 "Die App öffnet die Dateiseite im Browser und lädt alles herunter.",
            text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10),
            justify="left").pack(padx=18, pady=(10,8), anchor="w")

        # Anbieter-Auswahl
        self._import_host = ctk.StringVar(value="none")
        host_row = ctk.CTkFrame(sec_import, fg_color="transparent")
        host_row.pack(padx=18, fill="x", pady=(0,8))
        for key, label, col in [
            ("none",      "Nicht importieren",  CARD),
            ("exaroton",  "Exaroton",           "#1a7a3a"),
            ("aternos",   "Aternos",            "#1a3a7a"),
        ]:
            ctk.CTkRadioButton(host_row, text=label,
                variable=self._import_host, value=key,
                text_color=TEXT, fg_color=GREEN, hover_color=GREEN_HOV,
                font=ctk.CTkFont("Segoe UI",12)
            ).pack(side="left", padx=(0,16))

        # URL-Eingabe
        url_lbl = ctk.CTkLabel(sec_import,
            text="Server-URL oder Exaroton Server-ID:",
            text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10))
        url_lbl.pack(padx=18, anchor="w")
        url_row = ctk.CTkFrame(sec_import, fg_color="transparent")
        url_row.pack(padx=18, pady=(2,4), fill="x")
        url_row.grid_columnconfigure(0, weight=1)
        self._import_url = ctk.CTkEntry(url_row,
            placeholder_text="z.B.  https://exaroton.com/server/abc123  oder  abc123",
            fg_color=CARD, text_color=TEXT, height=34,
            font=ctk.CTkFont("Segoe UI",11))
        self._import_url.grid(row=0, column=0, sticky="ew", padx=(0,8))

        # Exaroton API-Key
        ctk.CTkLabel(sec_import,
            text="Exaroton API-Key  (Einstellungen → API → Token erstellen):",
            text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10)
            ).pack(padx=18, anchor="w", pady=(4,0))
        self._import_apikey = ctk.CTkEntry(sec_import,
            placeholder_text="exaroton API Token…",
            fg_color=CARD, text_color=TEXT, height=34, show="•",
            font=ctk.CTkFont("Segoe UI",11))
        self._import_apikey.pack(padx=18, pady=(2,6), fill="x")

        # Browser öffnen Button
        def _open_hosting_files():
            host = self._import_host.get()
            url  = self._import_url.get().strip()
            import webbrowser as _wb
            if host == "exaroton":
                if url and not url.startswith("http"):
                    _wb.open(f"https://exaroton.com/server/{url}/files/")
                elif url:
                    # URL direkt öffnen + /files/ anhängen
                    base = url.rstrip("/")
                    if "/files" not in base:
                        base += "/files/"
                    _wb.open(base)
                else:
                    _wb.open("https://exaroton.com")
            elif host == "aternos":
                if url:
                    base = url.rstrip("/")
                    if "/files" not in base:
                        base += "/files"
                    _wb.open(base)
                else:
                    _wb.open("https://aternos.org/files/")

        ctk.CTkButton(url_row, text="🌐 Öffnen", width=80, height=34,
            fg_color=BLUE, hover_color="#1a6bbf", text_color="#fff",
            font=ctk.CTkFont("Segoe UI",11,"bold"), corner_radius=6,
            command=_open_hosting_files).grid(row=0, column=1)

        self._import_status = ctk.CTkLabel(sec_import, text="",
            text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10))
        self._import_status.pack(padx=18, pady=(0,4), anchor="w")

        # ── Ordner-Import (Server-Ordner direkt auswählen) ────────────────
        ctk.CTkFrame(sec_import, fg_color=BORDER, height=1).pack(fill="x", padx=18, pady=4)
        ctk.CTkLabel(sec_import,
            text="Oder: Server-Ordner direkt importieren",
            text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10,"bold")
            ).pack(padx=18, anchor="w")
        ctk.CTkLabel(sec_import,
            text="Wähle den entpackten Server-Ordner von Exaroton/Aternos.\n"
                 "Alle Dateien werden 1:1 übernommen. Version und Typ werden danach gefragt.",
            text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",9), justify="left"
            ).pack(padx=18, anchor="w")

        self._folder_import_path = ctk.StringVar(value="")
        folder_row = ctk.CTkFrame(sec_import, fg_color="transparent")
        folder_row.pack(padx=18, pady=(4,10), fill="x")
        folder_row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(folder_row, textvariable=self._folder_import_path,
                     placeholder_text="Kein Ordner gewählt",
                     fg_color=CARD, text_color=TEXT, height=32
                     ).grid(row=0, column=0, sticky="ew", padx=(0,8))
        def _pick_folder():
            d = filedialog.askdirectory(title="Server-Ordner wählen (von Exaroton/Aternos)")
            if d: self._folder_import_path.set(d)
        ctk.CTkButton(folder_row, text="📁 Wählen", width=80, height=32,
            fg_color=CARD, hover_color=BORDER, text_color=TEXT,
            font=ctk.CTkFont("Segoe UI",11), corner_radius=6,
            command=_pick_folder).grid(row=0, column=1)

        # Fortschritt
        self.prog_frame = ctk.CTkFrame(scroll, fg_color=SIDEBAR_BG, corner_radius=10)
        self.prog_frame.pack(padx=20, pady=(4,8), fill="x")
        self.prog_bar = ctk.CTkProgressBar(self.prog_frame, fg_color=CARD, progress_color=GREEN)
        self.prog_bar.set(0)
        self.prog_bar.pack(padx=16, pady=(14,4), fill="x")
        self.prog_lbl = ctk.CTkLabel(self.prog_frame, text="Bereit.",
                                      text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",11))
        self.prog_lbl.pack(padx=16, pady=(2,14))

        # Create Button
        ctk.CTkButton(scroll, text="Server erstellen",
                      fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                      font=ctk.CTkFont("Segoe UI",15,"bold"), height=52, corner_radius=8,
                      command=self._create).pack(padx=20, pady=(4,24), fill="x")

        # Auto-fill Adresse wenn Name eingegeben
        self.e_name.bind("<KeyRelease>", self._auto_addr)

    def _section(self, parent, title):
        ctk.CTkLabel(parent, text=title, text_color=TEXT_MUTED,
                     font=ctk.CTkFont("Segoe UI",11,"bold")).pack(padx=20, pady=(16,4), anchor="w")
        f = ctk.CTkFrame(parent, fg_color=SIDEBAR_BG, corner_radius=10)
        f.pack(padx=20, pady=(0,4), fill="x")
        return f

    def _field_lbl(self, parent, text):
        ctk.CTkLabel(parent, text=text, anchor="w", text_color=TEXT_MUTED,
                     font=ctk.CTkFont("Segoe UI",11)).pack(padx=18, pady=(12,0), fill="x")

    def _entry(self, parent, ph, default=""):
        e = ctk.CTkEntry(parent, placeholder_text=ph, fg_color=CARD, border_color=BORDER,
                          text_color=TEXT, font=ctk.CTkFont("Segoe UI",13))
        if default: e.insert(0, default)
        e.pack(padx=18, pady=(2,10), fill="x")
        return e

    def _auto_addr(self, _=None):
        pass   # Adresse kommt von playit.gg, nicht mehr hier generiert

    def _pick(self, name):
        self._sel_type = name
        for n, btn in self._type_btns.items():
            info = SERVER_TYPES[n]
            if n == name:
                btn.configure(fg_color=info["color"], text_color="#000")
            else:
                btn.configure(fg_color=CARD, text_color=TEXT)
        # Versionen für gewählten Typ laden
        if hasattr(self, "_load_versions_for_type"):
            self._load_versions_for_type(name)

    def _create(self):
        raw_name = self.e_name.get().strip()
        if not raw_name:
            self.prog_lbl.configure(text="Bitte einen Server-Namen eingeben!", text_color=RED)
            return

        addr     = ""   # playit.gg vergibt die echte Adresse beim ersten Start
        port     = self.e_port.get().strip() or "25565"
        players  = self.e_players.get().strip() or "20"
        motd     = self.e_motd.get().strip() or "A Minecraft Server"
        mc_ver   = self.ver_var.get()
        srv_type = self._sel_type
        tag      = SERVER_TYPES[srv_type]["tag"]

        # Ordner-Name: sicher
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in raw_name)
        if not safe: safe = "Server"

        # Benutzergewählter Installationsordner
        install_base = Path(getattr(self, "_install_path", type("", (), {"get": lambda s: str(SERVERS_DIR)})()).get())
        srv_dir = install_base / safe
        srv_dir.mkdir(parents=True, exist_ok=True)

        # Welt-Import merken
        world_to_import = getattr(self, "_import_world", None)
        world_name = world_to_import.get() if world_to_import else "— Keine —"

        # Hosting-Import Infos
        import_host   = getattr(self, "_import_host", None)
        import_host   = import_host.get() if import_host else "none"
        import_url    = getattr(self, "_import_url",   None)
        import_url    = import_url.get().strip() if import_url else ""
        import_apikey = getattr(self, "_import_apikey", None)
        import_apikey = import_apikey.get().strip() if import_apikey else ""
        folder_src    = getattr(self, "_folder_import_path", None)
        folder_src    = folder_src.get().strip() if folder_src else ""

        def run():
            # ── Ordner-Import (1:1 kopieren) ────────────────────────────────
            if folder_src and Path(folder_src).exists():
                self.prog_lbl.configure(text="Kopiere Server-Ordner…", text_color=TEXT_MUTED)
                self.prog_bar.set(0.05)
                src_p = Path(folder_src)
                try:
                    all_files = list(src_p.rglob("*"))
                    total = len(all_files)
                    for i, f in enumerate(all_files):
                        rel = f.relative_to(src_p)
                        dst_f = srv_dir / rel
                        if f.is_dir():
                            dst_f.mkdir(parents=True, exist_ok=True)
                        else:
                            dst_f.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(str(f), str(dst_f))
                        if i % 10 == 0:
                            self.prog_bar.set(0.05 + 0.85 * (i / max(total,1)))
                            self.prog_lbl.configure(text=f"Kopiere {rel.name}…")
                    (srv_dir/"eula.txt").write_text("eula=true\n", encoding="utf-8")
                    self.prog_lbl.configure(text="✓ Ordner kopiert!", text_color=GREEN)
                    self.prog_bar.set(0.92)
                    self._finalize_server(srv_dir, raw_name, safe, port, players, motd,
                                         mc_ver, srv_type, tag, addr)
                    return
                except Exception as e:
                    self.prog_lbl.configure(text=f"Kopier-Fehler: {e}", text_color=RED)
                    return

            # ── Hosting-Import (Exaroton / Aternos) ─────────────────────────
            if import_host != "none" and (import_url or import_apikey):
                self.prog_lbl.configure(text=f"Lade Server von {import_host}…", text_color=TEXT_MUTED)
                self.prog_bar.set(0.02)
                imported = self._import_from_hosting(
                    import_host, import_url, import_apikey, srv_dir)
                if imported:
                    # Server-Dateien sind importiert — server.jar suchen
                    existing_jar = list(srv_dir.rglob("server.jar"))
                    if existing_jar and existing_jar[0] != srv_dir/"server.jar":
                        try: existing_jar[0].rename(srv_dir/"server.jar")
                        except: pass
                    # eula bestätigen
                    (srv_dir/"eula.txt").write_text("eula=true\n", encoding="utf-8")
                    self.prog_lbl.configure(text="✓ Import abgeschlossen!", text_color=GREEN)
                    self.prog_bar.set(0.9)
                    # Direkt zu Config springen
                    self._finalize_server(srv_dir, raw_name, safe, port, players, motd,
                                          mc_ver, srv_type, tag, addr)
                    return
                # Falls Import fehlschlug → normal weitermachen

            self.prog_lbl.configure(text=f"Suche Download-URL für {mc_ver}…", text_color=TEXT_MUTED)
            self.prog_bar.set(0.05)

            if tag in ("paper","spigot","folia","purpur","arclight"):
                url = get_paper_url(mc_ver) or get_vanilla_jar_url(mc_ver)
            else:
                url = get_vanilla_jar_url(mc_ver)

            if not url:
                self.prog_lbl.configure(
                    text=f"Keine JAR für {mc_ver} gefunden. Bitte andere Version wählen.",
                    text_color=RED)
                return

            self.prog_lbl.configure(text="Lade server.jar herunter…")
            try:
                r     = requests.get(url, stream=True, timeout=120)
                total = int(r.headers.get("content-length",0))
                done  = 0
                with open(srv_dir/"server.jar","wb") as fh:
                    for chunk in r.iter_content(8192):
                        fh.write(chunk)
                        done += len(chunk)
                        if total: self.prog_bar.set(0.1 + 0.85*(done/total))
            except Exception as e:
                self.prog_lbl.configure(text=f"Download-Fehler: {e}", text_color=RED)
                return

            # eula.txt
            (srv_dir/"eula.txt").write_text("eula=true\n", encoding="utf-8")

            # Welt aus Launcher importieren
            if world_name and world_name not in ("— Keine (neue Welt) —","— Keine —"):
                world_src = self._mc_saves_path / world_name
                world_dst = srv_dir / "world"
                if world_src.exists() and not world_dst.exists():
                    self.prog_lbl.configure(text=f"Importiere Welt '{world_name}'…")
                    try:
                        shutil.copytree(str(world_src), str(world_dst))
                        self.prog_lbl.configure(text=f"✓ Welt '{world_name}' importiert.")
                    except Exception as e:
                        self.prog_lbl.configure(text=f"Welt-Import Fehler: {e}", text_color="#ffd600")

            # server.properties
            (srv_dir/"server.properties").write_text(
                f"server-port={port}\nmax-players={players}\nmotd={motd}\n"
                "online-mode=true\ndifficulty=normal\npvp=true\n"
                "white-list=false\ngamemode=survival\nlevel-name=world\n"
                "view-distance=10\nenable-command-block=false\nspawn-protection=16\n"
                "allow-flight=false\nforce-gamemode=false\nplayer-idle-timeout=0\n"
                "max-tick-time=-1\npause-when-empty-seconds=-1\n",
                encoding="utf-8"
            )

            # Config speichern
            game_type_val = getattr(self, "_game_type", None)
            game_type_val = game_type_val.get() if game_type_val else "minecraft-java"
            cfg = {
                "name":        raw_name,
                "safe":        safe,
                "mc_version":  mc_ver,
                "type":        tag,
                "type_label":  srv_type,
                "port":        port,
                "address":     "",
                "max_players": players,
                "motd":        motd,
                "dir":         str(srv_dir),
                "game_type":   game_type_val,
                "tunnel_provider": "mine_host",
                "imported_world": world_name if world_name not in ("— Keine (neue Welt) —","— Keine —") else "",
            }
            save_server_cfg(safe, cfg)

            self.prog_bar.set(1.0)
            self.prog_lbl.configure(text="Fertig! Server wurde erstellt.", text_color=GREEN)
            time.sleep(0.8)
            self.destroy()
            self.on_done(safe)

        threading.Thread(target=run, daemon=True).start()

    def _finalize_server(self, srv_dir, raw_name, safe, port, players, motd,
                         mc_ver, srv_type, tag, addr):
        """Speichert die Server-Config und schließt das Fenster."""
        game_type_val = getattr(self, "_game_type", None)
        game_type_val = game_type_val.get() if game_type_val else "minecraft-java"
        cfg = {
            "name": raw_name, "safe": safe,
            "mc_version": mc_ver, "type": tag, "type_label": srv_type,
            "port": port, "address": addr, "max_players": players,
            "motd": motd, "dir": str(srv_dir),
            "game_type": game_type_val,
            "tunnel_provider": "mine_host",  # Standard: playit.gg (kostenlos, öffentlich)
        }
        save_server_cfg(safe, cfg)
        self.prog_bar.set(1.0)
        self.prog_lbl.configure(text="✓ Fertig!", text_color=GREEN)
        time.sleep(0.6)
        self.destroy()
        self.on_done(safe)

    def _import_from_hosting(self, host: str, url: str, apikey: str, srv_dir: "Path") -> bool:
        """
        Lädt alle Server-Dateien von Exaroton oder Aternos herunter.
        Gibt True zurück wenn erfolgreich.
        """
        import webbrowser as _wb, io as _io, zipfile as _zf

        def _upd(msg, pct=None):
            try:
                self.prog_lbl.configure(text=msg, text_color=TEXT_MUTED)
                if pct is not None: self.prog_bar.set(pct)
            except: pass

        # ── Exaroton via API ──────────────────────────────────────────────────
        if host == "exaroton":
            if not apikey:
                _upd("Exaroton: Kein API-Key eingegeben. Öffne Browser…")
                # Fallback: Browser öffnen damit User manuell downloadet
                if url:
                    base = url.rstrip("/")
                    if "/files" not in base: base += "/files/"
                    _wb.open(base)
                else:
                    _wb.open("https://exaroton.com")
                _upd("⚠ Bitte Server manuell als ZIP herunterladen und unten importieren.", 0.1)
                return False

            # Server-ID aus URL/Input extrahieren
            server_id = url
            if "exaroton.com/server/" in url:
                parts = url.split("exaroton.com/server/")
                server_id = parts[1].strip("/").split("/")[0]

            _upd(f"Exaroton: Verbinde mit Server {server_id[:8]}…", 0.05)
            headers = {"Authorization": f"Bearer {apikey}"}

            # Server-Info holen
            try:
                r = requests.get(f"https://api.exaroton.com/v1/servers/{server_id}/",
                                 headers=headers, timeout=10)
                data = r.json()
                if not data.get("success"):
                    _upd(f"✗ Exaroton API Fehler: {data.get('error','Unbekannt')}", 0.1)
                    return False
                srv_info = data.get("data", {})
                _upd(f"✓ Server gefunden: {srv_info.get('name','?')}", 0.1)
            except Exception as e:
                _upd(f"✗ API-Fehler: {e}", 0.1)
                return False

            # Dateiliste holen und alle wichtigen Dateien herunterladen
            try:
                r = requests.get(f"https://api.exaroton.com/v1/servers/{server_id}/files/info//",
                                 headers=headers, timeout=10)
                files_data = r.json().get("data", {})
                children = files_data.get("children", [])
            except Exception as e:
                _upd(f"✗ Dateiliste Fehler: {e}", 0.1)
                return False

            # Wichtige Dateien/Ordner herunterladen
            total_files = len(children)
            for i, f in enumerate(children):
                fname = f.get("name","")
                if not fname: continue
                pct = 0.1 + 0.8 * (i / max(total_files, 1))
                _upd(f"Lade {fname}… ({i+1}/{total_files})", pct)
                try:
                    dl_url = f"https://api.exaroton.com/v1/servers/{server_id}/files/data/{fname}"
                    dr = requests.get(dl_url, headers=headers, timeout=60, stream=True)
                    dest = srv_dir / fname
                    if f.get("isDirectory"):
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        with open(str(dest), "wb") as fh:
                            for chunk in dr.iter_content(8192):
                                fh.write(chunk)
                except Exception as e:
                    _upd(f"⚠ {fname}: {e}", pct)

            _upd("✓ Exaroton-Import abgeschlossen!", 0.95)
            return True

        # ── Aternos (kein API → Browser + manueller Download-Watcher) ─────────
        elif host == "aternos":
            if url:
                base = url.rstrip("/")
                if "/files" not in base: base += "/files"
                _wb.open(base)
            else:
                _wb.open("https://aternos.org/files/")

            _upd("Browser geöffnet → Lade den Server als ZIP herunter,\n"
                 "dann wähle die ZIP-Datei hier aus.", 0.05)

            # Datei-Dialog für manuellen Import
            import tkinter.filedialog as _fd
            zip_path = _fd.askopenfilename(
                title="Aternos-Server-ZIP auswählen",
                filetypes=[("ZIP-Archiv","*.zip"),("Alle","*.*")])
            if not zip_path:
                _upd("Abgebrochen.", 0.0)
                return False

            _upd("Entpacke Server-Dateien…", 0.3)
            try:
                import zipfile as _zf2
                with _zf2.ZipFile(zip_path, "r") as zf:
                    members = zf.namelist()
                    for i, m in enumerate(members):
                        zf.extract(m, str(srv_dir))
                        if i % 20 == 0:
                            _upd(f"Entpacke {m[:40]}…", 0.3 + 0.6*(i/len(members)))
                _upd("✓ Aternos-Import abgeschlossen!", 0.95)
                return True
            except Exception as e:
                _upd(f"✗ Entpack-Fehler: {e}", 0.1)
                return False

        return False

# ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
# Mine-Host Python Tunnel Connector (async, kein Node.js nötig)
# ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
async def _mh_bridge_player(ws_domain, tid, conn_id, mc_host, mc_port, on_log):
    """Bridget einen Spieler: TCP (MC-Server) ↔ WebSocket (Relay)."""
    import asyncio as _aio
    data_url = (f"wss://{ws_domain}/api/tunnel-ws"
                f"?type=host_data&tunnelId={tid}&connectionId={conn_id}")
    writer = None
    try:
        import websockets as _ws
        reader, writer = await _aio.open_connection(mc_host, mc_port)

        async with _ws.connect(data_url, max_size=2**23) as dws:
            on_log(f"[Tunnel] Spieler-Bridge aktiv ({conn_id[:8]})\n")

            async def _tcp_to_ws():
                while True:
                    chunk = await reader.read(32768)
                    if not chunk: break
                    await dws.send(chunk)

            async def _ws_to_tcp():
                async for data in dws:
                    writer.write(data if isinstance(data, bytes) else data.encode())
                    await writer.drain()

            done, pending = await _aio.wait(
                [_aio.ensure_future(_tcp_to_ws()),
                 _aio.ensure_future(_ws_to_tcp())],
                return_when=_aio.FIRST_COMPLETED)
            for t in pending: t.cancel()
    except Exception:
        pass
    finally:
        if writer:
            try: writer.close()
            except: pass

async def _mh_host_loop(ws_domain, tid, mc_host, mc_port, on_log, stop_ev):
    """Haupt-Loop: Verbindet mit Relay, leitet Spieler-Verbindungen weiter."""
    import asyncio as _aio
    ctrl_url = f"wss://{ws_domain}/api/tunnel-ws?type=host&tunnelId={tid}"

    while not stop_ev.is_set():
        try:
            import websockets as _ws
            import json as _json
            async with _ws.connect(ctrl_url, ping_interval=20, ping_timeout=15,
                                   max_size=2**20) as ctrl:
                on_log(f"[Tunnel] ✅ ERFOLGREICH VERBUNDEN! Warte auf Spieler…\n")
                async for raw in ctrl:
                    if stop_ev.is_set(): break
                    try: msg = _json.loads(raw)
                    except: continue

                    if msg.get("action") == "connect":
                        cid = msg.get("connectionId","")
                        _aio.ensure_future(
                            _mh_bridge_player(ws_domain, tid, cid,
                                              mc_host, mc_port, on_log))

                    elif msg.get("action") == "ping":
                        try:
                            sock_r, sock_w = await _aio.open_connection(mc_host, mc_port)
                            sock_w.close()
                            stats = {"online": True}
                        except:
                            stats = {"online": False}
                        try:
                            await ctrl.send(_json.dumps({"action":"ping_response","stats":stats}))
                        except: pass

        except Exception as e:
            if not stop_ev.is_set():
                on_log(f"[Tunnel] Verbindung unterbrochen — Reconnect in 5s… ({e})\n")

        if not stop_ev.is_set():
            await _aio.sleep(5)

# ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
# HAUPT-APP  (Aternos-Layout)
# ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
class MainApp(ctk.CTk):
    def __init__(self, username):
        super().__init__()
        self.username      = username
        self.server_name   = None
        self.cfg           = {}
        self.proc          = None
        self._playit_mgr   = None
        self._playit_addr  = None
        self._playit_claim = None
        self._server_state = "offline"
        # Mehrere Server gleichzeitig
        self._extra_servers: list = []  # [{name, proc, cfg, state}]
        # ID des Servers dessen proc in self.proc läuft
        # (kann sich vom angezeigten server_name unterscheiden nach einem Wechsel)
        self._running_server_name: str = ""
        self.title("MineHost Local")
        # Fenstergröße: 85% des Monitors, aber min 800x500
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        w  = max(900,  int(sw * 0.75))
        h  = max(560,  int(sh * 0.80))
        x  = (sw - w) // 2
        y  = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.minsize(700, 480)
        self.resizable(True, True)
        self.configure(fg_color=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # ── Globaler Crash-Reporter ───────────────────────────────────────────
        self.report_callback_exception = self._crash_report
        import sys as _sys
        _sys.excepthook = lambda t, v, tb: self._crash_report(t, v, tb)
        self._build()
        # Minecraft-Versionen live von Mojang laden
        fetch_mc_versions_bg(callback=None)
        # {server_name: {"proc": Popen|None, "stop_ev": Event}}
        self._tunnel_connectors   = {}
        self._mh_host_connected   = False
        self._mh_players_online   = 0
        # Beim App-Start alle Spieler auf offline setzen (stale Daten)
        try:
            import glob as _gl
            for _pf in _gl.glob(str(APP_DIR / "servers" / "*_players.json")):
                try:
                    _pd = json.loads(open(_pf, encoding="utf-8").read())
                    for _n in _pd: _pd[_n]["online"] = False
                    open(_pf, "w", encoding="utf-8").write(json.dumps(_pd, indent=2, ensure_ascii=False))
                except: pass
        except: pass
        servers = list_servers()
        if servers:
            self._load_server(servers[0])
            # Auto-Start: Server automatisch starten wenn eingestellt
            autostart = load_server_cfg(servers[0]).get("autostart", False)
            if autostart:
                self.after(500, self._start)
            # Tunnel + Status-Poller beim App-Start (minehost-local.uk)
            if self.cfg.get("tunnel_provider", "mine_host") == "mine_host":
                if self.cfg.get("minehost_tunnel_id"):
                    self.after(2000, self._start_tunnel_connector)
                else:
                    self.after(2000, lambda: threading.Thread(
                        target=self._auto_setup_mine_host, daemon=True).start())
                self.after(3000, self._start_tunnel_status_poller)
        else:
            self._show("no_server")
        self._update_nav_state()
        # playit startet erst wenn der Server gestartet wird (verhindert mehrere Instanzen)

    def _crash_report(self, exc_type, exc_value, exc_tb):
        import traceback, datetime, hashlib, os as _os
        tb_str   = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        ts       = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        code     = "MHL-" + hashlib.sha1(tb_str.encode()).hexdigest()[:6].upper()
        log_dir  = APP_DIR / "crash_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / f"crash_{ts}.txt"
        log_path.write_text(
            f"MineHost Local — Crash Report\n"
            f"Zeit:       {ts}\n"
            f"Fehlercode: {code}\n"
            f"{'='*60}\n{tb_str}", encoding="utf-8")
        try:
            win = ctk.CTkToplevel(self)
            win.title("MineHost Local — Absturzbericht")
            win.resizable(False, False)
            win.geometry("620x440")
            win.configure(fg_color=BG)
            win.grab_set(); win.lift()
            win.attributes("-topmost", True)
            ctk.CTkLabel(win, text="App-Absturz",
                         font=ctk.CTkFont("Segoe UI",18,"bold"), text_color=RED).pack(pady=(20,4))
            ctk.CTkLabel(win, text=f"Fehlercode:  {code}",
                         font=ctk.CTkFont("Consolas",13,"bold"), text_color=TEXT).pack()
            ctk.CTkLabel(win, text=f"Log: {log_path}",
                         font=ctk.CTkFont("Segoe UI",9), text_color=TEXT_MUTED).pack(pady=(2,8))
            box = ctk.CTkTextbox(win, fg_color="#111", text_color="#ff6b6b",
                                 font=ctk.CTkFont("Consolas",10), corner_radius=6)
            box.pack(fill="both", expand=True, padx=16, pady=(0,8))
            box.insert("end", tb_str); box.configure(state="disabled")
            btn_row = ctk.CTkFrame(win, fg_color="transparent")
            btn_row.pack(pady=(0,16))
            ctk.CTkButton(btn_row, text="Log-Ordner öffnen", width=160,
                          fg_color=CARD, hover_color=BORDER, text_color=TEXT,
                          command=lambda: _os.startfile(str(log_dir))
                          ).pack(side="left", padx=6)
            ctk.CTkButton(btn_row, text="Schließen", width=110,
                          fg_color=RED, hover_color="#b91c1c", text_color="#fff",
                          command=win.destroy).pack(side="left", padx=6)
        except Exception:
            pass  # falls das Fenster selbst crasht, still ignorieren


    # ── Root-Layout (vollständig responsiv) ───────────────────────────────────
    def _build(self):
        self.grid_columnconfigure(0, weight=0, minsize=180)  # Sidebar: feste Mindestbreite
        self.grid_columnconfigure(1, weight=1)               # Content: nimmt Rest
        self.grid_rowconfigure(0, weight=1)

        # Sidebar — Breite = max(180, 15% der Fensterbreite)
        self.update_idletasks()
        sw = max(180, int(self.winfo_width() * 0.15)) if self.winfo_width() > 10 else SIDEBAR_W
        self.sidebar = ctk.CTkFrame(self, width=sw, fg_color=SIDEBAR_BG, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # Main — füllt den Rest
        self.content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")

        # Sidebar-Breite nur EINMAL nach Fenster-Resize anpassen.
        # WICHTIG: nur auf self (Hauptfenster) reagieren, nicht auf Child-Widgets —
        # sonst entsteht ein Feedback-Loop: configure(sidebar) → <Configure> → configure → ...
        self._resize_job  = None
        self._sidebar_w   = [sw]
        self._resize_ov   = [None]   # Vollbild-Overlay Widget

        def _show_resize_overlay():
            """Halb-transparentes Lade-Overlay über der ganzen App."""
            if self._resize_ov[0]:
                try: self._resize_ov[0].destroy()
                except: pass
            import tkinter as _tk
            ov = _tk.Frame(self, bg="#0d0d0d")
            ov.place(x=0, y=0, relwidth=1, relheight=1)
            self._resize_ov[0] = ov
            _SPIN = ["◐?","◓","◑","◒"]
            lbl = ctk.CTkLabel(ov, text=_SPIN[0],
                               font=ctk.CTkFont("Segoe UI", 64),
                               text_color=GREEN, fg_color="transparent")
            lbl.place(relx=0.5, rely=0.5, anchor="center")
            idx = [0]
            def _tick():
                if self._resize_ov[0] is not ov: return
                idx[0] = (idx[0] + 1) % 4
                try: lbl.configure(text=_SPIN[idx[0]])
                except: return
                self.after(80, _tick)
            self.after(80, _tick)
            try: self.update_idletasks()
            except: pass

        def _hide_resize_overlay():
            if self._resize_ov[0]:
                try: self._resize_ov[0].destroy()
                except: pass
            self._resize_ov[0] = None

        def _on_resize(e):
            if e.widget is not self: return
            new_w = max(180, int(e.width * 0.15))
            if abs(new_w - self._sidebar_w[0]) <= 5: return  # keine echte Änderung
            # Overlay zeigen
            _show_resize_overlay()
            if self._resize_job:
                try: self.after_cancel(self._resize_job)
                except: pass
            def _apply():
                self._resize_job = None
                try:
                    final_w = max(180, int(self.winfo_width() * 0.15))
                    if abs(final_w - self._sidebar_w[0]) > 5:
                        self._sidebar_w[0] = final_w
                        self.sidebar.configure(width=final_w)
                except: pass
                _hide_resize_overlay()
            self._resize_job = self.after(400, _apply)

        self.bind("<Configure>", _on_resize)

        self._build_sidebar()

    def _build_sidebar(self):
        # Logo + App-Name
        top = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        top.pack(pady=(16,0), padx=14, fill="x")
        logo_box = ctk.CTkFrame(top, fg_color="transparent", width=36, height=36)
        logo_box.pack(side="left", padx=(0,8))
        logo_box.pack_propagate(False)
        ctk.CTkLabel(logo_box, image=make_logo(36), text="").place(x=0, y=0)
        if FREE_VERSION:
            badge = ctk.CTkLabel(logo_box, text="FREE", fg_color="#000000",
                                 text_color=GREEN, corner_radius=5,
                                 font=ctk.CTkFont("Segoe UI", 7, "bold"),
                                 width=26, height=12)
            badge.place(relx=1.0, rely=1.0, anchor="center")
        ctk.CTkLabel(top, text="MineHost Local",
                     font=ctk.CTkFont("Segoe UI",13,"bold"), text_color=GREEN).pack(side="left")

        # Server-Auswahl
        self._srv_box = ctk.CTkFrame(self.sidebar, fg_color=CARD, corner_radius=8)
        self._srv_box.pack(padx=10, pady=(12,2), fill="x")
        self._srv_dot = ctk.CTkLabel(self._srv_box, text="●", text_color=RED,
                                      font=ctk.CTkFont("Segoe UI",10))
        self._srv_dot.grid(row=0, column=0, padx=(8,0), pady=6)
        self._srv_name_lbl = ctk.CTkLabel(self._srv_box, text="Kein Server",
                                           text_color=TEXT, font=ctk.CTkFont("Segoe UI",12,"bold"),
                                           anchor="w")
        self._srv_name_lbl.grid(row=0, column=1, padx=6, pady=6, sticky="w")
        self._srv_sub_lbl  = ctk.CTkLabel(self._srv_box, text="—",
                                           text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",9),
                                           anchor="w")
        self._srv_sub_lbl.grid(row=1, column=1, padx=6, pady=(0,6), sticky="w")
        self._srv_box.grid_columnconfigure(1, weight=1)

        # Wechsle Server (wenn mehrere)
        self._srv_switch_btn = ctk.CTkButton(self.sidebar, text="▾  Server wechseln",
                                              fg_color="transparent", hover_color=CARD,
                                              text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",11),
                                              height=28, anchor="w",
                                              command=self._switch_server_popup)
        self._srv_switch_btn.pack(padx=10, pady=(0,8), fill="x")

        sep = ctk.CTkFrame(self.sidebar, fg_color=BORDER, height=1)
        sep.pack(padx=10, fill="x", pady=4)

        # Navigations-Buttons
        self._nav = {}
        self._nav_frames = {}  # für hide/show
        pages = [
            ("dashboard", "Server"),
            ("options",   "Optionen"),
            ("console",   "Konsole"),
            ("log",       "Log"),
            ("players",   "Spieler"),
            ("software",  "Software"),
            ("plugins",   "Plugins"),   # wird dynamisch umbenant/versteckt
            ("files",     "Dateien"),
            ("worlds",    "Welten"),
            ("backups",   "Backups"),
            ("access",    "Zugriff"),
            ("lobby",     "⚡ Lobby"),
        ]
        for key, label in pages:
            btn = ctk.CTkButton(self.sidebar, text=label, anchor="w",
                                fg_color="transparent", hover_color=CARD,
                                text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",13),
                                height=36, corner_radius=6,
                                command=lambda k=key: self._show(k))
            btn.pack(padx=8, pady=1, fill="x")
            self._nav[key] = btn

        sep2 = ctk.CTkFrame(self.sidebar, fg_color=BORDER, height=1)
        sep2.pack(padx=10, fill="x", pady=8)

        ctk.CTkButton(self.sidebar, text="+ Erstellen", anchor="w",
                      fg_color="transparent", hover_color=CARD,
                      text_color=GREEN, font=ctk.CTkFont("Segoe UI",13,"bold"),
                      height=36, corner_radius=6,
                      command=self._new_server).pack(padx=8, fill="x")

        # Benutzer + Logout + Duplizieren unten
        bot = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bot.pack(side="bottom", padx=8, pady=10, fill="x")
        ctk.CTkLabel(bot, text=f"@ {self.username}",
                     text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10)).pack(anchor="w")
        ctk.CTkButton(bot, text="⧉  Fenster duplizieren", anchor="w",
                      fg_color="transparent", hover_color=CARD,
                      text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",11),
                      height=28, corner_radius=6,
                      command=self._duplicate_window).pack(fill="x", pady=(2,0))
        row_bot = ctk.CTkFrame(bot, fg_color="transparent")
        row_bot.pack(fill="x", pady=(2,0))
        row_bot.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(row_bot, text="Ausloggen", anchor="w",
                      fg_color="transparent", hover_color=CARD,
                      text_color=RED, font=ctk.CTkFont("Segoe UI",11),
                      height=28, corner_radius=6,
                      command=self._logout).grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(row_bot, text="By VisCode",
                     text_color="#444", font=ctk.CTkFont("Segoe UI",9),
                     anchor="e").grid(row=0, column=1, padx=(4,0))

    # ── Navigation ────────────────────────────────────────────────────────────
    def _clear(self):
        # Generation hochzählen → alle laufenden after()-Callbacks dieser Seite werden ungültig
        self._page_gen = getattr(self, "_page_gen", 0) + 1
        for w in self.content.winfo_children():
            try: w.destroy()
            except: pass
        # KEIN update_idletasks() hier — das würde den Content-Frame kurz mit Höhe 0
        # berechnen lassen, was CTkScrollableFrame als halbe Höhe erbt.

    def _page_after(self, ms, fn):
        """Wie self.after(), aber bricht automatisch ab wenn die Seite gewechselt hat."""
        gen = getattr(self, "_page_gen", 0)
        def _guarded():
            if getattr(self, "_page_gen", 0) == gen:
                try: fn()
                except Exception: pass
        self.after(ms, _guarded)

    def _show(self, key):
        self._active_page = key
        for k, b in self._nav.items():
            if b.cget("state") == "disabled":
                continue
            b.configure(
                text_color=GREEN if k == key else TEXT_MUTED,
                fg_color=CARD if k == key else "transparent",
                font=ctk.CTkFont("Segoe UI", 13, "bold" if k == key else "normal")
            )
        self._clear()
        page_fn = getattr(self, f"_p_{key}", self._p_no_server)
        try:
            page_fn()
        except Exception:
            import sys
            self._crash_report(*sys.exc_info())

    def _update_nav_state(self):
        """Aktiviert/Deaktiviert Nav-Buttons + zeigt Plugins/Mods je nach Server-Typ."""
        has_server = bool(self.server_name)
        srv_type   = self.cfg.get("type","vanilla").lower() if has_server else "vanilla"

        has_plugins    = srv_type in ("paper","spigot","purpur","folia","arclight","bukkit")
        has_mods       = srv_type in ("fabric","forge","neoforge","quilt","modpack")
        show_plugin_nav = has_server and (has_plugins or has_mods)

        locked = {"console","log","players","software","plugins",
                  "files","worlds","backups","access","options"}

        for key, btn in self._nav.items():
            if key == "plugins":
                # Plugins/Mods Label anpassen
                label = "Mods" if has_mods else "Plugins"
                btn.configure(text=label)
                if not show_plugin_nav:
                    # Unsichtbar machen (nicht entfernen → behält Position)
                    btn.configure(state="disabled", text_color=BG,
                                  fg_color=BG, hover_color=BG)
                    continue
                else:
                    btn.configure(state="normal", text_color=TEXT_MUTED,
                                  fg_color="transparent", hover_color=CARD)

            if key in locked and not has_server:
                btn.configure(state="disabled", text_color="#555",
                              fg_color="transparent")
            else:
                is_active = getattr(self, "_active_page", "") == key
                btn.configure(state="normal",
                              fg_color=CARD if is_active else "transparent",
                              hover_color=CARD,
                              text_color=GREEN if is_active else TEXT_MUTED)

    def _load_server(self, safe_name):
        self.server_name = safe_name
        self.cfg         = load_server_cfg(safe_name)
        # Tunnel-State für diesen Server laden (nie vom vorherigen übernehmen)
        self._playit_addr        = self.cfg.get("playit_address", None)
        self._playit_limit_error = None
        self._playit_connected   = False
        self._playit_agent_id    = None
        self._playit_secret_key  = None
        self._srv_name_lbl.configure(text=self.cfg.get("name", safe_name))
        self._srv_sub_lbl.configure(text=self.cfg.get("address","localhost"))
        _dot_state = getattr(self, "_server_state", "offline")
        _dot_color = {"online": GREEN, "starting": "#f39c12", "error": "#8e0000"}.get(_dot_state, RED)
        self._srv_dot.configure(text_color=_dot_color)
        self._update_nav_state()
        self._show("dashboard")
        # Tunnel-Connector für diesen Server starten (minehost-local.uk)
        if self.cfg.get("tunnel_provider", "mine_host") == "mine_host":
            if self.cfg.get("minehost_tunnel_id") and self.cfg.get("playit_address"):
                # Tunnel bereits bekannt → Connector sofort starten
                self.after(800, self._start_tunnel_connector)
            else:
                # Kein Tunnel oder keine Adresse → immer Auto-Setup
                self.after(1000, lambda: threading.Thread(
                    target=self._auto_setup_mine_host, daemon=True).start())

    def _switch_server_popup(self):
        """Server wechseln — läuft der aktuelle noch, bleibt er rechts sichtbar."""
        servers = list_servers()
        if not servers:
            messagebox.showinfo("Keine Server","Erstelle zuerst einen Server.")
            return

        win = ctk.CTkToplevel(self)
        win.title("Server wechseln")
        win.geometry("380x500")
        win.configure(fg_color=SIDEBAR_BG)
        win.lift(); win.focus_force()
        win.grab_set()

        ctk.CTkLabel(win, text="Server auswählen",
                     font=ctk.CTkFont("Segoe UI",15,"bold"), text_color=TEXT
                     ).pack(pady=(16,4))
        ctk.CTkLabel(win,
            text="Läuft ein Server gerade → bleibt er im Hintergrund aktiv.",
            font=ctk.CTkFont("Segoe UI",10), text_color=TEXT_MUTED
            ).pack(pady=(0,8))

        scroll = ctk.CTkScrollableFrame(win, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12, pady=(0,12))

        def _switch_to(safe_name):
            win.destroy()
            # Aktuell laufender Server → in extra_servers verschieben
            cur_running = (self.proc is not None and self.proc.poll() is None)
            if cur_running and self.server_name and self.server_name != safe_name:
                # Prüfen ob schon in extra_servers
                already = any(e.get("name") == self.cfg.get("name") for e in self._extra_servers)
                if not already:
                    self._extra_servers.append({
                        "name": self.cfg.get("name", self.server_name),
                        "proc": self.proc,
                        "cfg":  dict(self.cfg),
                        "port": int(self.cfg.get("port",25565)),
                    })
                # Hauptserver-Proc freigeben (ohne stoppen!)
                # _set_state NICHT aufrufen — das würde _p_dashboard() triggern,
                # was sofort danach von _load_server nochmal aufgerufen wird (Freeze).
                self.proc = None
                self._server_state = "offline"
                try: self._srv_dot.configure(text_color=RED)
                except: pass

            self._load_server(safe_name)

        def _rebuild():
            for w in scroll.winfo_children(): w.destroy()
            cur_state = getattr(self, "_server_state","offline")
            extra_names = {e.get("name") for e in self._extra_servers}

            for s in list_servers():
                cfg2  = load_server_cfg(s)
                name  = cfg2.get("name", s)
                mc    = cfg2.get("mc_version","?")
                stype = cfg2.get("type_label","?")
                is_cur = s == self.server_name
                is_run = is_cur and cur_state in ("online","starting")
                in_extra = name in extra_names

                row = ctk.CTkFrame(scroll, corner_radius=10,
                                   fg_color="#1a3a1a" if is_cur else CARD)
                row.pack(fill="x", pady=4)
                row.grid_columnconfigure(0, weight=1)

                # Status-Dot
                dot_col = GREEN if (is_run or in_extra) else "#555"
                ctk.CTkLabel(row, text="●", text_color=dot_col,
                             font=ctk.CTkFont("Segoe UI",10), width=20
                             ).grid(row=0, column=0, padx=(8,0), pady=10, sticky="w")

                # Info
                info = ctk.CTkFrame(row, fg_color="transparent")
                info.grid(row=0, column=1, sticky="w", padx=4)
                status_txt = " 🟢 Läuft" if is_run else (" (Hintergrund)" if in_extra else "")
                ctk.CTkLabel(info, text=f"{'✓ ' if is_cur else ''}{name}{status_txt}",
                             font=ctk.CTkFont("Segoe UI",13,"bold" if is_cur else "normal"),
                             text_color=GREEN if is_cur else TEXT, anchor="w"
                             ).pack(anchor="w")
                ctk.CTkLabel(info, text=f"{stype}  •  {mc}",
                             font=ctk.CTkFont("Segoe UI",9), text_color=TEXT_MUTED, anchor="w"
                             ).pack(anchor="w")

                if not is_cur:
                    ctk.CTkButton(row, text="Wechseln →", width=90, height=32,
                                  fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                                  font=ctk.CTkFont("Segoe UI",11,"bold"), corner_radius=8,
                                  command=lambda n=s: _switch_to(n)
                                  ).grid(row=0, column=2, padx=8)
                else:
                    ctk.CTkLabel(row, text="Aktiv", text_color=GREEN,
                                 font=ctk.CTkFont("Segoe UI",10,"bold"), width=80
                                 ).grid(row=0, column=2, padx=8)

                # Löschen (nicht für aktuellen)
                if not is_cur:
                    def _del(n=s, nm=name):
                        if not messagebox.askyesno("Löschen", f"'{nm}' wirklich löschen?"): return
                        c2 = load_server_cfg(n)
                        sp = Path(c2.get("dir",""))
                        if sp.exists():
                            try: shutil.rmtree(str(sp))
                            except Exception as e:
                                messagebox.showerror("Fehler",str(e)); return
                        _rebuild()
                    ctk.CTkButton(row, text="🗑", width=30, height=30,
                                  fg_color="transparent", hover_color="#3a1010",
                                  text_color=RED, corner_radius=6,
                                  command=_del).grid(row=0, column=3, padx=4)

        _rebuild()

        ctk.CTkButton(win, text="＋ Neuen Server erstellen",
                      fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                      font=ctk.CTkFont("Segoe UI",12,"bold"), height=38, corner_radius=8,
                      command=lambda: (win.destroy(), self._new_server())
                      ).pack(padx=16, pady=(0,12), fill="x")

    def _new_server(self):
        if FREE_VERSION and len(list_servers()) >= FREE_MAX_SERVERS:
            messagebox.showinfo(
                "Free-Version Limit",
                f"Die kostenlose Version unterstützt nur {FREE_MAX_SERVERS} Server.\n\n"
                f"Lösche den bestehenden Server um einen neuen zu erstellen,\n"
                f"oder upgrade auf die Pro-Version für unbegrenzte Server.")
            return
        CreateServerWindow(self, on_done=self._on_created)

    def _on_created(self, safe_name):
        self._load_server(safe_name)
        # Tunnel automatisch anlegen + Agent sofort starten
        if self.cfg.get("tunnel_provider", "mine_host") == "mine_host":
            threading.Thread(target=self._auto_setup_mine_host, daemon=True).start()

    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    # PAGE: KEIN SERVER
    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    def _p_no_server(self):
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        outer = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        outer.grid(row=0, column=0, sticky="nsew")

        # ── Header: "Server" + Stift + Erstellen ─────────────────────────────
        hdr = ctk.CTkFrame(outer, fg_color="transparent")
        hdr.pack(fill="x", padx=12, pady=(28,8))
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(hdr, text="Server",
                     font=ctk.CTkFont("Segoe UI", 26, "bold"),
                     text_color=GREEN).grid(row=0, column=0)

        btn_row = ctk.CTkFrame(hdr, fg_color="transparent")
        btn_row.grid(row=0, column=1, sticky="e")

        # Import-Button
        def _import_server():
            p = filedialog.askopenfilename(
                title="Server importieren",
                filetypes=[("MinLocal / ZIP", "*.minlocal *.zip"), ("Alle", "*.*")])
            if not p: return
            self._import_server_file(Path(p))
        ctk.CTkButton(btn_row, text="📥 Importieren", width=110, height=34,
                      fg_color=CARD, hover_color=BORDER, text_color=TEXT_MUTED,
                      font=ctk.CTkFont("Segoe UI",11), corner_radius=8,
                      command=_import_server).pack(side="left", padx=(0,6))

        ctk.CTkButton(btn_row, text="⚙", width=36, height=34,
                      fg_color=CARD, hover_color=BORDER, text_color=TEXT_MUTED,
                      font=ctk.CTkFont("Segoe UI",14), corner_radius=8,
                      command=self._switch_server_popup).pack(side="left", padx=(0,6))

        ctk.CTkButton(btn_row, text="＋ Erstellen", width=110, height=34,
                      fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                      font=ctk.CTkFont("Segoe UI",12,"bold"), corner_radius=20,
                      command=self._new_server).pack(side="left")

        servers = list_servers()

        if not servers:
            empty = ctk.CTkFrame(outer, fg_color="transparent")
            empty.pack(pady=60)
            ctk.CTkLabel(empty, text="Noch keine Server vorhanden.",
                         font=ctk.CTkFont("Segoe UI",13), text_color=TEXT_MUTED).pack()
            return

        # ── Aktive Server: 2-Spalten-Grid ─────────────────────────────────────
        grid = ctk.CTkFrame(outer, fg_color="transparent")
        grid.pack(fill="x", padx=24, pady=4)
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)

        is_running = self.proc is not None and self.proc.poll() is None

        for i, s in enumerate(servers):
            cfg  = load_server_cfg(s)
            name = cfg.get("name", s)
            mc_ver   = cfg.get("mc_version", "?")
            srv_type = cfg.get("type_label", "Vanilla")
            is_cur   = s == self.server_name
            live = is_cur and is_running

            col = i % 2
            row_i = i // 2

            card = ctk.CTkFrame(grid, fg_color="#1a1a1a", corner_radius=10,
                                border_width=2 if is_cur else 0,
                                border_color=GREEN if is_cur else BORDER)
            card.grid(row=row_i, column=col, padx=8, pady=6, sticky="nsew")
            card.grid_columnconfigure(0, weight=1)

            # Linke Seite: Name + Hash + Type
            info = ctk.CTkFrame(card, fg_color="transparent")
            info.grid(row=0, column=0, padx=14, pady=12, sticky="w")
            ctk.CTkLabel(info, text=name,
                         font=ctk.CTkFont("Segoe UI",14,"bold"),
                         text_color=TEXT, anchor="w").pack(anchor="w")
            short_hash = s[:16] if len(s) > 16 else s
            ctk.CTkLabel(info, text=f"#{short_hash}",
                         font=ctk.CTkFont("Segoe UI",9),
                         text_color="#555", anchor="w").pack(anchor="w")
            ctk.CTkLabel(info, text=f"⚙ {srv_type} {mc_ver}",
                         font=ctk.CTkFont("Segoe UI",11),
                         text_color=TEXT_MUTED, anchor="w").pack(anchor="w", pady=(4,0))

            # Rechts: Live-Dot + Buttons
            right = ctk.CTkFrame(card, fg_color="transparent")
            right.grid(row=0, column=1, padx=10, pady=8, sticky="e")

            # Live-Indikator
            dot_col = RED if live else "#333"
            ctk.CTkLabel(right, text="???", font=ctk.CTkFont("Segoe UI",20),
                         text_color=dot_col).pack(pady=(0,6))

            if not is_cur:
                ctk.CTkButton(right, text="Öffnen", width=80, height=28,
                              fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                              font=ctk.CTkFont("Segoe UI",11,"bold"), corner_radius=6,
                              command=lambda n=s: self._load_server(n)).pack(pady=2)
            else:
                ctk.CTkLabel(right, text="Aktiv",
                             font=ctk.CTkFont("Segoe UI",10,"bold"),
                             text_color=GREEN).pack()

            # Duplizieren + Löschen (kleine Buttons)
            mini = ctk.CTkFrame(card, fg_color="transparent")
            mini.grid(row=1, column=0, columnspan=2, padx=14, pady=(0,8), sticky="w")

            def _dup(n=s, cfg2=cfg):
                new_name = f"{cfg2.get('name',n)}-Kopie"
                import shutil as _sh, uuid as _uuid
                new_safe = new_name.replace(" ","_") + "_" + _uuid.uuid4().hex[:4]
                src = Path(cfg2.get("dir",""))
                dst = src.parent / new_safe
                if src.exists(): _sh.copytree(str(src), str(dst))
                new_cfg = dict(cfg2); new_cfg["name"] = new_name; new_cfg["dir"] = str(dst)
                save_server_cfg(new_safe, new_cfg)
                self._p_no_server()
            ctk.CTkButton(mini, text="⧉ Duplizieren", width=100, height=24,
                          fg_color="#222", hover_color=CARD, text_color=TEXT_MUTED,
                          font=ctk.CTkFont("Segoe UI",10), corner_radius=6,
                          command=_dup).pack(side="left", padx=(0,6))

            def _del(n=s, cfg2=cfg, cur=is_cur):
                srv_display = cfg2.get('name', n)
                warn = (f"Server '{srv_display}' wirklich löschen?\n\n"
                        f"⚠️ Alle Server-Dateien werden gelöscht!\n"
                        + ("⚠️ Server läuft gerade und wird gestoppt!\n" if cur and is_running else ""))
                if not messagebox.askyesno("Server löschen", warn): return
                # Server stoppen falls aktiv
                if cur and is_running:
                    try: self.proc.stdin.write("stop\n"); self.proc.stdin.flush()
                    except: pass
                    try: self.proc.wait(timeout=5)
                    except: pass
                    try: self.proc.kill()
                    except: pass
                    self.proc = None
                # Mine-Host Tunnel löschen
                tunnel_id = cfg2.get("minehost_tunnel_id","")
                if tunnel_id:
                    try:
                        requests.delete(f"{MINEHOST_TUNNEL_API}/api/tunnels/{tunnel_id}",
                                       headers={"Content-Type":"application/json","User-Agent":"MineHostLocal/1.0"},
                                       timeout=8)
                    except: pass
                # Server-Dateien löschen
                import shutil as _sh
                p = Path(cfg2.get("dir",""))
                if p.exists():
                    try: _sh.rmtree(str(p))
                    except Exception as e:
                        messagebox.showerror("Fehler", str(e)); return
                cfg_f = SERVERS_DIR / n / "minehost.json"
                if cfg_f.exists(): cfg_f.unlink(missing_ok=True)
                try: (SERVERS_DIR / n).rmdir()
                except: pass
                # Nächsten Server laden oder leere Ansicht
                if cur:
                    self.server_name = None
                    self.cfg = {}
                    self._playit_addr = None
                remaining = [x for x in list_servers() if x != n]
                if remaining:
                    self._load_server(remaining[0])
                else:
                    self._show("no_server")
            ctk.CTkButton(mini, text="🗑 Löschen", width=90, height=24,
                          fg_color="#2a1010", hover_color="#3a1010", text_color=RED,
                          font=ctk.CTkFont("Segoe UI",10), corner_radius=6,
                          command=_del).pack(side="left")

        # ── Alte Server (Backups vorhanden, Server gelöscht) ──────────────────
        bkp_dir = APP_DIR / "backups"
        old_backups = []
        if bkp_dir.exists():
            for z in sorted(bkp_dir.glob("*.zip"), reverse=True):
                # Prüfen ob der Server noch existiert
                stem_parts = z.stem.split("_")
                if len(stem_parts) >= 2:
                    possible_name = "_".join(stem_parts[:-2])
                    if possible_name not in servers:
                        old_backups.append(z)

        if old_backups:
            ctk.CTkLabel(outer, text="Alte Server",
                         font=ctk.CTkFont("Segoe UI",16,"bold"),
                         text_color=GREEN).pack(pady=(24,4), anchor="center")
            ctk.CTkLabel(outer, text="?",
                         font=ctk.CTkFont("Segoe UI",11),
                         text_color=TEXT_MUTED).pack(pady=(0,8))

            old_grid = ctk.CTkFrame(outer, fg_color="transparent")
            old_grid.pack(fill="x", padx=24)
            old_grid.grid_columnconfigure(0, weight=1)
            old_grid.grid_columnconfigure(1, weight=1)

            for i, z in enumerate(old_backups[:6]):
                parts = z.stem.split("_")
                bname = "_".join(parts[:-2]) if len(parts) >= 2 else z.stem
                col = i % 2
                ocard = ctk.CTkFrame(old_grid, fg_color="#111", corner_radius=8)
                ocard.grid(row=i//2, column=col, padx=8, pady=4, sticky="nsew")
                ocard.grid_columnconfigure(0, weight=1)
                info2 = ctk.CTkFrame(ocard, fg_color="transparent")
                info2.grid(row=0, column=0, padx=12, pady=8, sticky="w")
                ctk.CTkLabel(info2, text=bname,
                             font=ctk.CTkFont("Segoe UI",12,"bold"),
                             text_color="#888").pack(anchor="w")
                ctk.CTkLabel(info2, text=z.name[:30],
                             font=ctk.CTkFont("Segoe UI",9),
                             text_color="#444").pack(anchor="w")
                def _restore(zp=z):
                    if not messagebox.askyesno("Wiederherstellen",
                        f"Server aus '{zp.name}' wiederherstellen?"): return
                    import shutil as _sh, uuid as _uuid
                    safe = zp.stem + "_" + _uuid.uuid4().hex[:4]
                    dst = SERVERS_DIR / safe
                    _sh.unpack_archive(str(zp), str(dst))
                    save_server_cfg(safe, {"name": zp.stem, "dir": str(dst)})
                    self._load_server(safe)
                ctk.CTkButton(ocard, text="↩", width=36, height=36,
                              fg_color="#1a1a2a", hover_color="#2a2a4a",
                              text_color="#4a9eff", font=ctk.CTkFont("Segoe UI",16),
                              corner_radius=6, command=_restore
                              ).grid(row=0, column=1, padx=8)

    def _import_server_file(self, path: "Path"):
        """Importiert einen Server aus .minlocal oder .zip."""
        import shutil as _sh, uuid as _uuid, json as _json
        safe = path.stem.replace(" ","_") + "_" + _uuid.uuid4().hex[:4]
        dst  = SERVERS_DIR / safe
        try:
            _sh.unpack_archive(str(path), str(dst))
        except Exception as e:
            messagebox.showerror("Import-Fehler", str(e)); return
        # Versuche eingebettete Config zu lesen
        cfg_file = dst / "minehost_config.json"
        if cfg_file.exists():
            try:
                cfg = _json.loads(cfg_file.read_text(encoding="utf-8"))
                cfg["dir"] = str(dst)
            except:
                cfg = {"name": path.stem, "dir": str(dst)}
        else:
            cfg = {"name": path.stem, "dir": str(dst)}
        save_server_cfg(safe, cfg)
        messagebox.showinfo("Import erfolgreich", f"Server '{cfg['name']}' importiert!")
        self._load_server(safe)

    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    # PAGE: DASHBOARD  (Aternos-Stil)
    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    def _p_dashboard(self):
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        if not self.server_name or not self.cfg:
            f = ctk.CTkFrame(self.content, fg_color="transparent")
            f.place(relx=0.5, rely=0.5, anchor="center")
            ctk.CTkLabel(f, text="Kein Server vorhanden.",
                         font=ctk.CTkFont("Segoe UI",18), text_color=TEXT_MUTED).pack(pady=12)
            ctk.CTkButton(f, text="+ Server erstellen",
                          fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                          font=ctk.CTkFont("Segoe UI",14,"bold"), height=48, width=220,
                          command=self._new_server).pack()
            return

        is_on  = self.proc is not None and self.proc.poll() is None
        cfg    = self.cfg

        # ── Layout: Haupt-Dashboard + Multi-Server-Panel rechts ──
        dash_outer = ctk.CTkFrame(self.content, fg_color="transparent")
        dash_outer.grid(row=0, column=0, sticky="nsew")   # grid statt pack!
        dash_outer.grid_columnconfigure(0, weight=1)
        dash_outer.grid_columnconfigure(1, weight=0)
        dash_outer.grid_rowconfigure(0, weight=1)

        # Multi-Server-Panel rechts (falls extra Server laufen oder Taste gedrückt)
        extra = getattr(self, "_extra_servers", [])
        if extra:
            panel = ctk.CTkFrame(dash_outer, fg_color=SIDEBAR_BG, corner_radius=0, width=200)
            panel.grid(row=0, column=1, sticky="nsew")
            panel.grid_propagate(False)
            ctk.CTkLabel(panel, text="Laufende Server",
                         font=ctk.CTkFont("Segoe UI",11,"bold"), text_color=TEXT_MUTED
                         ).pack(padx=10, pady=(12,4), anchor="w")
            for es in extra:
                es_on = es.get("proc") and es["proc"].poll() is None
                ec = ctk.CTkFrame(panel, fg_color=CARD, corner_radius=8)
                ec.pack(fill="x", padx=6, pady=3)
                ec.grid_columnconfigure(0, weight=1)
                dot = "●" ; dot_col = GREEN if es_on else "#555"
                ctk.CTkLabel(ec, text=f"{dot} {es.get('name','?')[:16]}",
                             text_color=dot_col, font=ctk.CTkFont("Segoe UI",11,"bold"),
                             anchor="w").grid(row=0, column=0, padx=8, pady=(6,2), sticky="w")
                ctk.CTkLabel(ec, text=es.get("cfg",{}).get("mc_version",""),
                             text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",9),
                             anchor="w").grid(row=1, column=0, padx=8, pady=(0,6), sticky="w")
                def _stop_extra(e=es):
                    if e.get("proc") and e["proc"].poll() is None:
                        try: e["proc"].stdin.write("stop\n"); e["proc"].stdin.flush()
                        except: e["proc"].kill()
                    self._extra_servers = [x for x in self._extra_servers if x is not e]
                    self._refresh_dashboard()
                ctk.CTkButton(ec, text="●●", width=28, height=22,
                              fg_color="#3a1010", text_color=RED, corner_radius=4,
                              command=_stop_extra).grid(row=0, column=1, padx=6, rowspan=2)

            # "+" Server hinzufügen
            def _add_server_popup():
                servers = [s for s in list_servers() if s != self.server_name]
                if not servers: messagebox.showinfo("Keine weiteren Server", "Keine anderen Server gefunden."); return
                win = ctk.CTkToplevel(self); win.title("Server starten"); win.geometry("300x250")
                win.configure(fg_color=BG); win.grab_set()
                ctk.CTkLabel(win, text="Server auswählen:", font=ctk.CTkFont("Segoe UI",12,"bold"),
                             text_color=TEXT).pack(pady=(16,8))
                for s in servers:
                    sc = load_server_cfg(s)
                    def _launch(n=s, c=sc):
                        win.destroy()
                        self._start_extra_server(n, c)
                    ctk.CTkButton(win, text=f"{sc.get('name',s)}  ({sc.get('mc_version','?')})",
                                  fg_color=CARD, text_color=TEXT, height=38, corner_radius=8,
                                  command=_launch).pack(fill="x", padx=16, pady=3)
            ctk.CTkButton(panel, text="＋ Server hinzufügen", height=32,
                          fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                          font=ctk.CTkFont("Segoe UI",10,"bold"), corner_radius=8,
                          command=_add_server_popup).pack(fill="x", padx=6, pady=(4,8))
        else:
            # Kleiner "+" Button oben rechts im Dashboard
            pass

        # ── Scrollbarer Wrapper (scrollbar_side="right" sichert Sichtbarkeit) ──
        wrap = ctk.CTkScrollableFrame(dash_outer, fg_color="transparent",
                                      scrollbar_button_color=CARD,
                                      scrollbar_button_hover_color=BORDER)
        wrap.grid(row=0, column=0, sticky="nsew", padx=(0,0))
        wrap.grid_columnconfigure(0, weight=1)

        # ── Server-Titel + Multi-Server Button (eigener Frame oben rechts) ──
        def _add_server_popup_new():
            servers = [s for s in list_servers() if s != self.server_name]
            if not servers: messagebox.showinfo("Info","Keine weiteren Server vorhanden."); return
            win2 = ctk.CTkToplevel(self); win2.title("Server hinzufügen"); win2.geometry("320x280")
            win2.configure(fg_color=BG); win2.grab_set()
            ctk.CTkLabel(win2, text="Weiteren Server starten:",
                         font=ctk.CTkFont("Segoe UI",13,"bold"), text_color=TEXT).pack(pady=(16,8))
            for s in servers:
                sc = load_server_cfg(s)
                def _go(n=s, c=sc): win2.destroy(); self._start_extra_server(n,c)
                ctk.CTkButton(win2, text=f"{sc.get('name',s)}  ({sc.get('mc_version','?')})",
                              fg_color=CARD, text_color=TEXT, height=38, corner_radius=8,
                              command=_go).pack(fill="x", padx=16, pady=3)

        # Titel zentriert
        title_row = ctk.CTkFrame(wrap, fg_color="transparent")
        title_row.pack(pady=(24,0), fill="x", padx=20)
        ctk.CTkLabel(title_row, text=cfg.get("name","Server"),
                     font=ctk.CTkFont("Segoe UI",26,"bold"), text_color=TEXT
                     ).pack(side="left", expand=True)
        ctk.CTkButton(title_row, text="＋ Server", width=90, height=28,
                      fg_color=CARD, hover_color=SIDEBAR_BG, text_color=TEXT_MUTED,
                      font=ctk.CTkFont("Segoe UI",10), corner_radius=8,
                      command=_add_server_popup_new).pack(side="right")

        # Adresse
        _hdr_addr = getattr(self, "_playit_addr", None)
        addr_row = ctk.CTkFrame(wrap, fg_color="transparent")
        addr_row.pack(pady=(4,0))
        if _hdr_addr:
            ctk.CTkLabel(addr_row, text=_hdr_addr,
                         font=ctk.CTkFont("Segoe UI",13), text_color=TEXT_MUTED).pack(side="left", padx=(0,10))
            ctk.CTkButton(addr_row, text="Kopieren",
                          fg_color=CARD, hover_color=BORDER, text_color=TEXT,
                          font=ctk.CTkFont("Segoe UI",11), height=26, width=80, corner_radius=4,
                          command=lambda a=_hdr_addr: (self.clipboard_clear(), self.clipboard_append(a))
                          ).pack(side="left")
            if self.cfg.get("tunnel_provider", "mine_host") == "mine_host":
                ctk.CTkButton(addr_row, text="✏ Name ändern",
                              fg_color=CARD, hover_color=BORDER, text_color=TEXT_MUTED,
                              font=ctk.CTkFont("Segoe UI",11), height=26, width=110, corner_radius=4,
                              command=self._rename_tunnel_dialog
                              ).pack(side="left", padx=(6,0))

        # minehost-local.uk Tunnel-Status + Verbindungsanleitung
        if self.cfg.get("tunnel_provider", "mine_host") == "mine_host":
            _tid   = self.cfg.get("minehost_tunnel_id", "")
            _port  = str(self.cfg.get("port", "25565"))
            _lport = str(getattr(self, "_mh_client_port", int(_port)+5))
            if _tid:
                _hc      = getattr(self, "_mh_host_connected", False)
                _pl      = getattr(self, "_mh_players_online", 0)
                _entry   = self._tunnel_connectors.get(self.server_name, {})
                _ev      = _entry.get("stop_ev")
                _proc    = _entry.get("proc")
                _cl_proc = getattr(self, "_mh_client_proc", None)
                _running = ((_ev and not _ev.is_set()) or
                            (_proc and _proc.poll() is None))
                _cl_run  = _cl_proc is not None and _cl_proc.poll() is None

                # Zeile 1: Agent-Status
                tst_row = ctk.CTkFrame(wrap, fg_color="transparent")
                tst_row.pack(pady=(2,0))
                _dot    = "O" if _hc else ("~" if _running else "X")
                _dotcol = GREEN if _hc else (TEXT_MUTED if _running else RED)
                _stxt   = "Agent verbunden" if _hc else ("Agent laeuft..." if _running else "Agent offline")
                ctk.CTkLabel(tst_row, text=f"[{_dot}] {_stxt}",
                             font=ctk.CTkFont("Segoe UI",10,"bold"), text_color=_dotcol
                             ).pack(side="left", padx=(0,8))
                if _pl > 0:
                    ctk.CTkLabel(tst_row, text=f"{_pl} Spieler",
                                 font=ctk.CTkFont("Segoe UI",10), text_color=TEXT_MUTED
                                 ).pack(side="left", padx=(0,8))
                if not _running:
                    ctk.CTkButton(tst_row, text="Agent starten", height=24, width=100,
                                  fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                                  font=ctk.CTkFont("Segoe UI",10,"bold"), corner_radius=6,
                                  command=self._start_tunnel_connector
                                  ).pack(side="left", padx=(0,4))
                ctk.CTkButton(tst_row, text="Dashboard",
                              height=24, width=80,
                              fg_color=CARD, hover_color=BORDER, text_color=TEXT_MUTED,
                              font=ctk.CTkFont("Segoe UI",10), corner_radius=6,
                              command=lambda: __import__("webbrowser").open(MINEHOST_TUNNEL_API)
                              ).pack(side="left")

                # Zeile 2: Lokal testen
                loc_row = ctk.CTkFrame(wrap, fg_color="transparent")
                loc_row.pack(pady=(2,0))
                ctk.CTkLabel(loc_row, text="Lokal testen:",
                             font=ctk.CTkFont("Segoe UI",10), text_color=TEXT_MUTED
                             ).pack(side="left", padx=(0,4))
                _local_addr = f"localhost:{_lport}"
                ctk.CTkLabel(loc_row, text=_local_addr,
                             font=ctk.CTkFont("Courier New",10), text_color=GREEN
                             ).pack(side="left", padx=(0,6))
                if not _cl_run:
                    ctk.CTkButton(loc_row, text="Client starten", height=22, width=100,
                                  fg_color=CARD, hover_color=GREEN, text_color=TEXT_MUTED,
                                  font=ctk.CTkFont("Segoe UI",10), corner_radius=6,
                                  command=lambda t=_tid, lp=_lport: self._start_client_connector(t, int(lp))
                                  ).pack(side="left", padx=(0,4))
                else:
                    ctk.CTkLabel(loc_row, text="[Client laeuft]",
                                 font=ctk.CTkFont("Segoe UI",10), text_color=GREEN
                                 ).pack(side="left", padx=(0,4))
                ctk.CTkButton(loc_row, text="Kopieren", height=22, width=70,
                              fg_color=CARD, hover_color=BORDER, text_color=TEXT_MUTED,
                              font=ctk.CTkFont("Segoe UI",10), corner_radius=6,
                              command=lambda a=_local_addr: (self.clipboard_clear(), self.clipboard_append(a))
                              ).pack(side="left")

                # Zeile 3: Freunde einladen
                fr_row = ctk.CTkFrame(wrap, fg_color="transparent")
                fr_row.pack(pady=(1,0))
                ctk.CTkLabel(fr_row, text="Freunde:",
                             font=ctk.CTkFont("Segoe UI",10), text_color=TEXT_MUTED
                             ).pack(side="left", padx=(0,4))
                ctk.CTkLabel(fr_row, text=f"tunnel-connector.exe client {_tid}",
                             font=ctk.CTkFont("Courier New",9), text_color="#507050"
                             ).pack(side="left", padx=(0,6))
                ctk.CTkButton(fr_row, text="Paket", height=22, width=65,
                              fg_color=CARD, hover_color=GREEN, text_color=TEXT_MUTED,
                              font=ctk.CTkFont("Segoe UI",10), corner_radius=6,
                              command=lambda: __import__("subprocess").Popen(
                                  ["explorer", str(Path(sys.executable).parent / "player-connector")],
                                  creationflags=CREATE_NO_WINDOW)
                              ).pack(side="left")
        else:
            _hdr_state = getattr(self, "_server_state", "offline")
            _hdr_txt   = "Tunnel inaktiv" if _hdr_state == "offline" else "Tunnel verbindet…"
            ctk.CTkLabel(addr_row, text=_hdr_txt,
                         font=ctk.CTkFont("Segoe UI",13), text_color=TEXT_MUTED).pack()

        # ── Status-Banner ──
        # _server_state ist autoritativ; wenn Prozess tot ist → offline erzwingen
        _saved = getattr(self, "_server_state", "offline")
        if not is_on and _saved in ("online", "starting"):
            _saved = "offline"
        state = _saved

        STATES = {
            "offline":  (RED,          "● Ausgeschaltet",  "#fff"),
            "starting": ("#f39c12",    "⟳ Startet…",  "#000"),
            "online":   (GREEN,        "● Online",          "#000"),
            "error":    ("#8e0000",    "✖ Fehler",          "#fff"),
        }
        s_color, s_text, s_fg = STATES.get(state, STATES["offline"])

        banner = ctk.CTkFrame(wrap, fg_color=s_color, corner_radius=0, height=46)
        banner.pack(fill="x", pady=16)
        banner.pack_propagate(False)
        ctk.CTkLabel(banner, text=s_text,
                     font=ctk.CTkFont("Segoe UI",15,"bold"),
                     text_color=s_fg).pack(expand=True)

        # ── Buttons je nach Zustand ──
        btn_row = ctk.CTkFrame(wrap, fg_color="transparent")
        btn_row.pack(pady=8)

        if state == "offline":
            self._start_btn = ctk.CTkButton(btn_row, text="Starten",
                fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                font=ctk.CTkFont("Segoe UI",18,"bold"),
                width=180, height=56, corner_radius=28,
                command=self._toggle)
            self._start_btn.pack(pady=(0,8))
            ctk.CTkButton(btn_row, text="↻ Aktualisieren",
                fg_color=CARD, hover_color=SIDEBAR_BG, text_color=TEXT_MUTED,
                font=ctk.CTkFont("Segoe UI",12),
                width=140, height=32, corner_radius=16,
                command=self._refresh_dashboard).pack()

        elif state == "starting":
            # Animierter Button (deaktiviert) mit drehendem Ladekreis
            _spin_frames = ["⟳ Laden…", "↻ Laden…", "⟳ Laden…", "↺ Laden…"]
            _spin_ref    = [0]
            self._start_btn = ctk.CTkButton(
                btn_row,
                text=_spin_frames[0],
                fg_color="#555", hover_color="#555", text_color="#aaa",
                font=ctk.CTkFont("Segoe UI",18,"bold"),
                width=180, height=56, corner_radius=28,
                state="disabled", command=lambda: None)
            self._start_btn.pack()
            def _spin_btn():
                if getattr(self, "_server_state", "") == "starting":
                    _spin_ref[0] = (_spin_ref[0]+1) % len(_spin_frames)
                    try: self._start_btn.configure(text=_spin_frames[_spin_ref[0]])
                    except: return
                    self._page_after(500, _spin_btn)
            self._page_after(500, _spin_btn)

        elif state == "online":
            self._start_btn = ctk.CTkButton(btn_row, text="Stoppen",
                fg_color=RED, hover_color=RED_HOV, text_color="#fff",
                font=ctk.CTkFont("Segoe UI",18,"bold"),
                width=180, height=56, corner_radius=28,
                command=self._toggle)
            self._start_btn.pack()

        elif state == "error":
            ctk.CTkButton(btn_row, text="⚠ Fehler anzeigen",
                fg_color="#8e0000", hover_color="#6b0000", text_color="#fff",
                font=ctk.CTkFont("Segoe UI",14,"bold"),
                width=180, height=48, corner_radius=28,
                command=self._show_error).pack(pady=(0,4))
            ctk.CTkButton(btn_row, text="Neu starten",
                fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                font=ctk.CTkFont("Segoe UI",13),
                width=180, height=38, corner_radius=28,
                command=self._toggle).pack()

        # ── "Minecraft öffnen"-Button (immer sichtbar wenn Server-Info vorhanden) ──
        mc_ver = cfg.get("mc_version","")
        if mc_ver:
            ctk.CTkButton(btn_row, text=f"🎮  Minecraft {mc_ver} öffnen",
                fg_color=CARD, hover_color=SIDEBAR_BG, text_color=TEXT_MUTED,
                font=ctk.CTkFont("Segoe UI",11), height=34, corner_radius=20,
                command=lambda v=mc_ver: self._open_minecraft_version(v)
                ).pack(pady=(10,0))

        # ── Info-Karten (wie Aternos) ──
        info_frame = ctk.CTkFrame(wrap, fg_color=SIDEBAR_BG, corner_radius=10)
        info_frame.pack(padx=16, pady=12, fill="x")

        def info_row(label, value, btn_text=None, btn_cmd=None, copy=False):
            f = ctk.CTkFrame(info_frame, fg_color="transparent")
            f.pack(fill="x", padx=0)
            f.grid_columnconfigure(1, weight=1)
            # Farbiger Streifen links
            stripe = ctk.CTkFrame(f, width=4, fg_color=GREEN, corner_radius=0)
            stripe.grid(row=0, column=0, sticky="ns", padx=(0,0))
            lbl_f = ctk.CTkFrame(f, fg_color="transparent")
            lbl_f.grid(row=0, column=1, padx=14, pady=10, sticky="w")
            ctk.CTkLabel(lbl_f, text=label, text_color=TEXT_MUTED,
                         font=ctk.CTkFont("Segoe UI",10,"bold")).pack(anchor="w")
            ctk.CTkLabel(lbl_f, text=value, text_color=TEXT,
                         font=ctk.CTkFont("Segoe UI",14)).pack(anchor="w")
            btn_f = ctk.CTkFrame(f, fg_color="transparent")
            btn_f.grid(row=0, column=2, padx=14, pady=10)
            if copy:
                ctk.CTkButton(btn_f, text="Kopieren", fg_color=CARD, hover_color=BORDER,
                               text_color=TEXT, font=ctk.CTkFont("Segoe UI",11),
                               height=30, width=90, corner_radius=4,
                               command=lambda v=value: self.clipboard_append(v) or self.update()
                               ).pack()
            if btn_text and btn_cmd:
                ctk.CTkButton(btn_f, text=btn_text, fg_color=CARD, hover_color=BORDER,
                               text_color=TEXT, font=ctk.CTkFont("Segoe UI",11),
                               height=30, width=90, corner_radius=4,
                               command=btn_cmd).pack()
            # Trennlinie
            ctk.CTkFrame(info_frame, fg_color=BORDER, height=1).pack(fill="x")

        local_val  = f"localhost:{cfg.get('port','25565')}"
        info_row("Lokale Adresse", local_val, copy=(state!="offline"))

        # Öffentliche Adresse – mit Ladekreis solange Tunnel noch verbindet
        pub_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
        pub_frame.pack(fill="x")
        pub_frame.grid_columnconfigure(0, weight=1)
        pub_lf = ctk.CTkFrame(pub_frame, fg_color="transparent")
        pub_lf.grid(row=0, column=0, padx=14, pady=10, sticky="w")
        # Tunnel-Anbieter Auswahl (Free-Version: nur minehost-local.uk, fest)
        if FREE_VERSION:
            self.cfg["tunnel_provider"] = "mine_host"
            tunnel_provider = "mine_host"
        else:
            tunnel_provider = self.cfg.get("tunnel_provider", "mine_host")
        # (key, Anzeigename, Website zum Öffnen bei Auswahl, Beschreibung)
        if FREE_VERSION:
            TUNNEL_PROVIDERS = {
                "mine_host": ("minehost-local.uk", MINEHOST_TUNNEL_API, "WebSocket-Relay (lokal)"),
            }
        else:
            TUNNEL_PROVIDERS = {
                "direct":    ("Direkt (UPnP) ⭐",  "",                   "Kostenlos, kein VPS — Fritz!Box/Router"),
                "playit":    ("playit.gg",          "https://playit.gg",  "Kostenlos, vollautomatisch"),
                "mine_host": ("minehost-local.uk",  MINEHOST_TUNNEL_API,  "WebSocket-Relay (lokal)"),
            }
        prov_row = ctk.CTkFrame(pub_lf, fg_color="transparent")
        prov_row.pack(anchor="w", pady=(0,4))
        ctk.CTkLabel(prov_row, text="Tunnel-Anbieter: ",
                     text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10)).pack(side="left")
        prov_display = [v[0] for v in TUNNEL_PROVIDERS.values()]
        cur_display  = TUNNEL_PROVIDERS.get(tunnel_provider, list(TUNNEL_PROVIDERS.values())[0])[0]
        prov_dvar    = ctk.StringVar(value=cur_display)

        def _on_prov(val):
            for k, (name, url, desc) in TUNNEL_PROVIDERS.items():
                if name == val:
                    self.cfg["tunnel_provider"] = k
                    save_server_cfg(self.server_name, self.cfg)
                    # Immer direkt zur passenden Website weiterleiten
                    if url: __import__("webbrowser").open(url)
                    break

        if FREE_VERSION:
            ctk.CTkLabel(prov_row, text=cur_display + "  🔒",
                         text_color=GREEN, font=ctk.CTkFont("Segoe UI",10,"bold")
                         ).pack(side="left", padx=4)
            ctk.CTkLabel(prov_row, text="(Free-Version)",
                         text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",9)
                         ).pack(side="left", padx=2)
        else:
            ctk.CTkOptionMenu(prov_row, variable=prov_dvar, values=prov_display,
                              fg_color=CARD, button_color=GREEN, text_color=TEXT,
                              font=ctk.CTkFont("Segoe UI",10), width=170, height=24,
                              command=_on_prov).pack(side="left", padx=4)

        # DuckDNS (für Direkt-UPnP) + Eigene Domain (für minehost-local.uk)
        _tprov = self.cfg.get("tunnel_provider","playit")
        if _tprov == "direct":
            duck_f = ctk.CTkFrame(pub_lf, fg_color="transparent")
            duck_f.pack(anchor="w", pady=(4,0), fill="x")
            ctk.CTkLabel(duck_f, text="DuckDNS Subdomain (optional):",
                         text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10)
                         ).pack(side="left", padx=(0,4))
            _duck_dom = ctk.StringVar(value=self.cfg.get("duckdns_domain",""))
            ctk.CTkEntry(duck_f, textvariable=_duck_dom, placeholder_text="meinserver",
                         fg_color=CARD, text_color=TEXT, height=26, width=120
                         ).pack(side="left", padx=(0,2))
            ctk.CTkLabel(duck_f, text=".duckdns.org", text_color=TEXT_MUTED,
                         font=ctk.CTkFont("Segoe UI",10)).pack(side="left", padx=(0,8))
            _duck_tok = ctk.StringVar(value=self.cfg.get("duckdns_token",""))
            ctk.CTkEntry(duck_f, textvariable=_duck_tok, placeholder_text="Token (von duckdns.org)",
                         fg_color=CARD, text_color=TEXT, height=26, width=220, show="*"
                         ).pack(side="left")
            def _save_duck(*_):
                self.cfg["duckdns_domain"] = _duck_dom.get().strip()
                self.cfg["duckdns_token"]  = _duck_tok.get().strip()
                save_server_cfg(self.server_name, self.cfg)
            duck_f.bind("<FocusOut>", _save_duck)
            ctk.CTkButton(duck_f, text="Speichern", height=24, width=80,
                          fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                          font=ctk.CTkFont("Segoe UI",10,"bold"), corner_radius=6,
                          command=_save_duck).pack(side="left", padx=(6,0))
            ctk.CTkButton(pub_lf, text="duckdns.org öffnen (Token holen)", height=24,
                          fg_color="transparent", hover_color=CARD, text_color=GREEN,
                          font=ctk.CTkFont("Segoe UI",9,"bold"), anchor="w",
                          command=lambda: __import__("webbrowser").open("https://duckdns.org")
                          ).pack(anchor="w", pady=(2,0))

        elif _tprov == "mine_host":
            dom_row = ctk.CTkFrame(pub_lf, fg_color="transparent")
            dom_row.pack(anchor="w", pady=(4,0), fill="x")
            ctk.CTkLabel(dom_row, text="Eigene Domain (optional):",
                         text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10)
                         ).pack(side="left", padx=(0,6))
            _dom_var = ctk.StringVar(value=self.cfg.get("tunnel_custom_domain",""))
            dom_entry = ctk.CTkEntry(dom_row, textvariable=_dom_var,
                                     placeholder_text="mc.meinserver.de",
                                     fg_color=CARD, text_color=TEXT, height=26, width=180)
            dom_entry.pack(side="left")
            def _save_dom(*_):
                self.cfg["tunnel_custom_domain"] = _dom_var.get().strip()
                save_server_cfg(self.server_name, self.cfg)
            dom_entry.bind("<FocusOut>", _save_dom)
            dom_entry.bind("<Return>",   _save_dom)

        ctk.CTkLabel(pub_lf, text="Öffentliche Adresse",
                     text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",11,"bold")).pack(anchor="w")

        if self._playit_addr:
            # Adresse bekannt → Text + Kopieren + Adresse anpassen
            ctk.CTkLabel(pub_lf, text=self._playit_addr,
                         text_color=TEXT, font=ctk.CTkFont("Segoe UI",13)).pack(anchor="w")
            def _copy_pub():
                self.clipboard_clear(); self.clipboard_append(self._playit_addr)
            def _open_tunnel_settings():
                # Öffnet playit.gg direkt am Tunnel des Servers
                agent_id  = getattr(self, "_playit_agent_id", None)
                tunnel_id = self.cfg.get("playit_tunnel_id")
                if tunnel_id:
                    __import__("webbrowser").open(
                        f"https://playit.gg/account/tunnels/{tunnel_id}")
                elif agent_id:
                    __import__("webbrowser").open(
                        f"https://playit.gg/account/agents/{agent_id}")
                else:
                    __import__("webbrowser").open("https://playit.gg/account/tunnels")
            btn_col = ctk.CTkFrame(pub_frame, fg_color="transparent")
            btn_col.grid(row=0, column=1, padx=10)
            ctk.CTkButton(btn_col, text="Kopieren", width=90, height=28,
                          fg_color=BLUE, hover_color="#1a6bbf", corner_radius=6,
                          font=ctk.CTkFont("Segoe UI",11),
                          command=_copy_pub).pack(pady=(0,4))
            ctk.CTkButton(btn_col, text="✏ Adresse anpassen", width=130, height=28,
                          fg_color=CARD, hover_color=BORDER, text_color=TEXT_MUTED,
                          font=ctk.CTkFont("Segoe UI",10), corner_radius=6,
                          command=_open_tunnel_settings).pack(pady=(0,4))
            def _replace_tunnel():
                if not messagebox.askyesno("Adresse ersetzen",
                    "Aktuelle Adresse löschen und NEUE erstellen?\n\n"
                    "Die alte Adresse wird sofort ungültig."):
                    return
                prov = self.cfg.get("tunnel_provider", "mine_host")
                # Alte Adresse/Tunnel aus API löschen
                def _do_replace():
                    if prov == "mine_host":
                        old_tid = self.cfg.get("minehost_tunnel_id", "")
                        if old_tid:
                            try:
                                requests.delete(
                                    f"{MINEHOST_TUNNEL_API}/api/tunnels/{old_tid}",
                                    headers={"Content-Type":"application/json",
                                             "User-Agent":"MineHostLocal/1.0"},
                                    timeout=8)
                                self._append_log(f"[Tunnel] Alte Adresse gelöscht: {old_tid[:8]}…\n")
                            except Exception as e:
                                self._append_log(f"[Tunnel] Löschen fehlgeschlagen: {e}\n")
                        self.cfg.pop("minehost_tunnel_id", None)
                        self.cfg.pop("playit_address", None)
                        self._playit_addr = None
                        save_server_cfg(self.server_name, self.cfg)
                        self.after(0, self._refresh_dashboard)
                        # Neue Adresse erstellen
                        self._start_custom_tunnel_bg()
                    else:
                        self.cfg.pop("playit_tunnel_id", None)
                        self.cfg.pop("playit_address", None)
                        self._playit_addr = None
                        self._tunnel_creation_running = False
                        save_server_cfg(self.server_name, self.cfg)
                        self.after(0, self._refresh_dashboard)
                        sk = getattr(self, "_playit_secret_key", None)
                        aid = getattr(self, "_playit_agent_id", None)
                        if sk and aid:
                            threading.Thread(target=self._create_tunnel_for_server,
                                             args=(sk, aid, lambda addr: None),
                                             daemon=True).start()
                threading.Thread(target=_do_replace, daemon=True).start()
            ctk.CTkButton(btn_col, text="🔄 Adresse ersetzen", width=130, height=28,
                          fg_color="#3a1a1a", hover_color="#5a1a1a", text_color=RED,
                          font=ctk.CTkFont("Segoe UI",10), corner_radius=6,
                          command=_replace_tunnel).pack()
        elif state == "offline":
            ctk.CTkLabel(pub_lf, text="Startet Server zuerst…",
                         text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",13)).pack(anchor="w")
        elif getattr(self, "_playit_limit_error", None):
            # Free-Tier-Limit oder Agent gelöscht
            reason = self._playit_limit_error
            err_frame = ctk.CTkFrame(pub_lf, fg_color="#3a1a1a", corner_radius=8)
            err_frame.pack(fill="x", pady=(0,6))
            if reason == "agent_deleted":
                title = "❌❌  Agent gelöscht"
                msg   = ("Der playit.gg Agent wurde im Dashboard gelöscht.\n"
                         "Klicke 'Auto Tunnel' um alles automatisch neu einzurichten,\n"
                         "oder registriere den Agenten manuell neu.")
            elif reason in ("tunnel_limit", "over_limit"):
                title = "❌❌  Free-Plan Limit erreicht"
                msg   = ("Zu viele Tunnel auf deinem kostenlosen playit.gg Account.\n"
                         "Klicke '⚡ Auto Tunnel' – der älteste Tunnel wird automatisch\n"
                         "gelöscht und ein neuer für diesen Server erstellt.")
            else:
                title = "???  Tunnel nicht verfügbar"
                msg   = ("Der öffentliche Tunnel konnte nicht erstellt werden.\n"
                         "Klicke '⚡ Auto Tunnel' für einen automatischen Neuversuch.")
            ctk.CTkLabel(err_frame, text=title, text_color=RED,
                         font=ctk.CTkFont("Segoe UI",13,"bold"), anchor="w").pack(padx=12, pady=(10,2), anchor="w")
            ctk.CTkLabel(err_frame, text=msg, text_color="#ff9999",
                         font=ctk.CTkFont("Segoe UI",11), justify="left", anchor="w").pack(padx=12, pady=(0,6), anchor="w")
            btn_row = ctk.CTkFrame(err_frame, fg_color="transparent"); btn_row.pack(padx=12, pady=(0,10), anchor="w")

            _sk_snap  = getattr(self, "_playit_secret_key", None)
            _aid_snap = getattr(self, "_playit_agent_id",   None)

            def _do_auto_tunnel(sk=_sk_snap, aid=_aid_snap):
                """
                Auto Tunnel:
                1. playit.gg im Browser öffnen (damit User eingeloggt ist)
                2. Kurz warten damit Seite laden kann
                3. Dann vollautomatisch Agent prüfen + Tunnel erstellen
                """
                import webbrowser as _wb
                # Öffne playit.gg Agents-Seite damit User den Status sehen kann
                _wb.open("https://playit.gg/account/agents")
                # 2s warten damit Browser sich öffnet, dann auto flow
                def _start():
                    threading.Thread(target=self._playit_auto_tunnel,
                                     args=(sk, aid), daemon=True).start()
                self.after(2000, _start)

            ctk.CTkButton(btn_row, text="⚡ Auto Tunnel",
                          fg_color=GREEN, hover_color="#1a8c3a", text_color="#000",
                          font=ctk.CTkFont("Segoe UI",11,"bold"), height=30, corner_radius=6,
                          command=_do_auto_tunnel).pack(side="left", padx=(0,6))

            _cleanup_lbl = ctk.CTkLabel(btn_row, text="", font=ctk.CTkFont("Segoe UI",9),
                                        text_color=GREEN)
            _cleanup_lbl.pack(side="left", padx=(0,6))

            def _do_cleanup(_sk=_sk_snap):
                if not _sk:
                    _cleanup_lbl.configure(text="Kein Secret Key."); return
                _cleanup_lbl.configure(text="Bereinige…", text_color="#f39c12")
                def _run():
                    result = self._playit_cleanup_and_reuse(
                        _sk, self._append_log, reuse_for=self.server_name)
                    def _done():
                        if result:
                            self._playit_addr = result
                            self._playit_limit_error = None
                            self._refresh_dashboard()
                        else:
                            _cleanup_lbl.configure(text="✓ Bereinigt", text_color=GREEN)
                    self.after(0, _done)
                threading.Thread(target=_run, daemon=True).start()

            ctk.CTkButton(btn_row, text="🗑 Tunnel bereinigen",
                          fg_color=CARD, hover_color=RED, text_color=TEXT_MUTED,
                          font=ctk.CTkFont("Segoe UI",11,"bold"), height=30, corner_radius=6,
                          command=_do_cleanup).pack(side="left", padx=(0,6))

            ctk.CTkButton(btn_row, text="⚙ playit.gg öffnen",
                          fg_color=BLUE, hover_color="#1a6bbf", text_color="#fff",
                          font=ctk.CTkFont("Segoe UI",11,"bold"), height=30, corner_radius=6,
                          command=lambda: __import__("webbrowser").open("https://playit.gg/account/tunnels")
                          ).pack(side="left", padx=(0,6))

            if reason == "agent_deleted":
                def _reregister():
                    """
                    Neu registrieren:
                    1. Alten Key löschen
                    2. Browser öffnen → playit.gg/login
                    3. Automatisch Claim-Flow starten (wartet auf Browser-Login)
                    """
                    import webbrowser as _wb
                    srv_dir   = Path(self.cfg.get("dir",""))
                    toml_path = srv_dir / "playit.toml"
                    global_key = APP_DIR / "playit_secret.txt"
                    # Alte Keys löschen
                    for p in [toml_path, global_key]:
                        try:
                            if p.exists(): p.unlink()
                        except: pass
                    self._playit_limit_error = None
                    self._playit_secret_key  = None
                    self._playit_agent_id    = None
                    self._playit_addr        = None
                    self.cfg.pop("playit_address", None)
                    self.cfg.pop("playit_tunnel_id", None)
                    save_server_cfg(self.server_name, self.cfg)
                    # Browser öffnen + Claim-Flow starten
                    _wb.open("https://playit.gg/login")
                    self._append_log("[playit.gg] Browser geöffnet → bitte einloggen…\n")
                    threading.Thread(
                        target=self._auto_claim_flow,
                        args=(srv_dir, toml_path, global_key),
                        daemon=True).start()
                    self._refresh_dashboard()

                ctk.CTkButton(btn_row, text="🔄 Neu registrieren",
                              fg_color="#333", text_color=TEXT,
                              font=ctk.CTkFont("Segoe UI",11), height=30, corner_radius=6,
                              command=_reregister).pack(side="left")
        elif getattr(self, "_playit_connected", False):
            # Agent verbunden, aber noch kein Tunnel angelegt
            agent_id = getattr(self, "_playit_agent_id", None)
            dash_url = f"https://playit.gg/account/agents/{agent_id}" if agent_id else "https://playit.gg/account/tunnels"
            if getattr(self, "_playit_email_unverified", False):
                ctk.CTkLabel(pub_lf, text="⚠ E-Mail auf playit.gg verifizieren!",
                             text_color="#f39c12", font=ctk.CTkFont("Segoe UI",12,"bold")).pack(anchor="w")
            ctk.CTkLabel(pub_lf, text="✓ Agent verbunden – Tunnel wird erstellt…",
                         text_color=GREEN, font=ctk.CTkFont("Segoe UI",12)).pack(anchor="w", pady=(2,4))
        else:
            # Tunnel verbindet oder Warte auf Browser-Erstellung
            spin_row = ctk.CTkFrame(pub_lf, fg_color="transparent")
            spin_row.pack(anchor="w")
            _spin_chars = ["??","◓","◑","◒"]
            _spin_lbl = ctk.CTkLabel(spin_row, text=_spin_chars[0],
                                     text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",15))
            _spin_lbl.pack(side="left", padx=(0,6))
            has_tid = bool(self.cfg.get("playit_tunnel_id"))
            wait_msg = "Verbinde Tunnel…" if has_tid else "Warte auf Tunnel-Erstellung im Browser…"
            ctk.CTkLabel(spin_row, text=wait_msg,
                         text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",13)).pack(side="left")

            # Anleitung wenn kein Tunnel vorhanden
            if not has_tid and getattr(self,"_playit_connected", False):
                srv_name = self.cfg.get("name","MineHost Server")
                guide_f  = ctk.CTkFrame(pub_lf, fg_color="#1a2a1a", corner_radius=8)
                guide_f.pack(fill="x", pady=(4,0))
                steps = [
                    f"1. Tunnel-Name eingeben: {srv_name}",
                    f"2. Typ wählen: {self.cfg.get('game_type','minecraft-java').replace('-',' ').title()}",
                    "3. Free Network → Weiter",
                    "4. Agent auswählen → Weiter",
                    "5. Origin Config → Weiter",
                    "6. 'Create Tunnel' klicken",
                ]
                for s in steps:
                    ctk.CTkLabel(guide_f, text=s, text_color="#86efac",
                                 font=ctk.CTkFont("Segoe UI",10), anchor="w"
                                 ).pack(padx=10, pady=1, anchor="w")
                ctk.CTkButton(guide_f, text="?? playit.gg öffnen", height=28,
                              fg_color="#1a3a1a", hover_color="#2a5a2a", text_color=GREEN,
                              font=ctk.CTkFont("Segoe UI",10,"bold"), corner_radius=6,
                              command=lambda: __import__("webbrowser").open(
                                  "https://playit.gg/account/tunnels?view=tunnel-type&sort=age")
                              ).pack(padx=10, pady=(4,8), anchor="w")

            _spin_idx = [0]
            def _animate():
                if not self._playit_addr and getattr(self,"_server_state","offline")!="offline":
                    _spin_idx[0] = (_spin_idx[0]+1) % len(_spin_chars)
                    try: _spin_lbl.configure(text=_spin_chars[_spin_idx[0]])
                    except: return
                    self._page_after(250, _animate)
            self._page_after(250, _animate)

        ctk.CTkFrame(info_frame, fg_color=BORDER, height=1).pack(fill="x")

        # Claim-Button falls playit noch nicht registriert
        if self._playit_claim:
            _claim_url = self._playit_claim
            claim_btn = ctk.CTkButton(
                wrap,
                text="🔗  Tunnel registrieren  (Hier klicken)",
                fg_color="#f39c12", hover_color="#d68910", text_color="#000",
                font=ctk.CTkFont("Segoe UI", 13, "bold"),
                height=42, corner_radius=8,
                command=lambda u=_claim_url: __import__("webbrowser").open(u))
            claim_btn.pack(padx=16, pady=(0, 4), fill="x")

        info_row("Software", cfg.get("type_label", cfg.get("type","Vanilla")).capitalize(),
                 btn_text="Ändern", btn_cmd=lambda: self._show("software"))
        info_row("Version", cfg.get("mc_version","?"),
                 btn_text="Ändern", btn_cmd=lambda: self._show("software"))

        # Spieleranzahl
        online_count = getattr(self, "_online_count", 0)
        max_pl = cfg.get("max_players", 20)
        info_row("Spieler online", f"{online_count} / {max_pl}",
                 btn_text="Verwalten", btn_cmd=lambda: self._show("players"))

        # ── System-Monitor kompakt ──
        mon = ctk.CTkFrame(wrap, fg_color=SIDEBAR_BG, corner_radius=10)
        mon.pack(padx=16, pady=8, fill="x")
        ctk.CTkLabel(mon, text="System-Auslastung", text_color=TEXT_MUTED,
                     font=ctk.CTkFont("Segoe UI",11,"bold")).pack(padx=16, pady=(10,4), anchor="w")
        mon_row = ctk.CTkFrame(mon, fg_color="transparent")
        mon_row.pack(padx=16, pady=(0,12), fill="x")
        mon_row.grid_columnconfigure((0,1,2), weight=1)

        def mini_stat(parent, col, label, color=BLUE):
            f = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=8)
            f.grid(row=0, column=col, padx=4, sticky="ew")
            ctk.CTkLabel(f, text=label, text_color=TEXT_MUTED,
                         font=ctk.CTkFont("Segoe UI",10)).pack(padx=12, pady=(8,2), anchor="w")
            bar = ctk.CTkProgressBar(f, fg_color=SIDEBAR_BG, progress_color=color)
            bar.set(0)
            bar.pack(padx=12, pady=(0,2), fill="x")
            lbl = ctk.CTkLabel(f, text="0%", text_color=TEXT,
                                font=ctk.CTkFont("Segoe UI",12,"bold"))
            lbl.pack(padx=12, pady=(0,8), anchor="w")
            return bar, lbl

        self._cpu_bar, self._cpu_lbl = mini_stat(mon_row, 0, "CPU", BLUE)
        self._ram_bar, self._ram_lbl = mini_stat(mon_row, 1, "RAM", "#8b5cf6")
        # Server-Prozess RAM separat
        self._srv_ram_bar, self._srv_ram_lbl = mini_stat(mon_row, 2, "Server-RAM", GREEN)
        self._update_monitor()

    def _update_monitor(self):
        if not hasattr(self, "_cpu_bar"): return
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory()
        # Server-Prozess RAM
        srv_ram_pct = 0.0
        srv_ram_txt = "0 MB"
        if self.proc and self.proc.poll() is None:
            try:
                p = psutil.Process(self.proc.pid)
                mem = p.memory_info().rss
                total = ram.total
                srv_ram_pct = mem / total
                mb = mem / 1024 / 1024
                srv_ram_txt = f"{mb:.0f} MB" if mb < 1024 else f"{mb/1024:.1f} GB"
            except: pass
        try:
            self._cpu_bar.set(cpu/100)
            self._cpu_lbl.configure(text=f"{cpu:.0f}%")
            self._ram_bar.set(ram.percent/100)
            self._ram_lbl.configure(text=f"{ram.percent:.0f}%")
            self._srv_ram_bar.set(srv_ram_pct)
            self._srv_ram_lbl.configure(text=srv_ram_txt)
        except:
            return
        self._page_after(2000, self._update_monitor)

    # ── Server starten/stoppen ────────────────────────────────────────────────
    def _set_state(self, state):
        """state: 'offline' | 'starting' | 'online' | 'error'"""
        self._server_state = state
        dot_colors = {"offline": RED, "starting": "#f39c12", "online": GREEN, "error": "#8e0000"}
        try: self._srv_dot.configure(text_color=dot_colors.get(state, RED))
        except: pass
        # Dashboard einmalig neu laden wenn aktiv — aber nur über _show() damit
        # kein doppeltes _clear() + Rebuild entsteht
        if getattr(self, "_active_page", "") == "dashboard":
            self.after(0, lambda: self._show("dashboard"))

    def _toggle(self):
        state = getattr(self, "_server_state", "offline")
        if state in ("online", "starting"):
            self._stop()
        else:
            self._start()

    def _start(self):
        srv_dir = Path(self.cfg.get("dir",""))
        if not (srv_dir/"server.jar").exists():
            messagebox.showerror("Fehler","server.jar nicht gefunden.")
            return

        # Warnung: Vanilla mit Plugins → Plugins werden nicht geladen
        srv_type = self.cfg.get("type","vanilla").lower()
        if srv_type in ("vanilla","snapshot"):
            plugins_dir = srv_dir / "plugins"
            if plugins_dir.exists() and any(plugins_dir.glob("*.jar")):
                if not messagebox.askyesno("⚠ Vanilla lädt keine Plugins",
                    "Dein Server ist Vanilla — Plugins (.jar) werden NICHT geladen!\n\n"
                    "Um Plugins zu nutzen, wechsle zu Paper, Spigot oder Purpur.\n\n"
                    "Trotzdem starten (ohne Plugins)?"):
                    self._show("software")
                    return
        mc_ver     = self.cfg.get("mc_version", "1.21")
        need_java  = required_java_for_mc(mc_ver)
        java       = find_java_exe(min_version=need_java)
        if not java:
            got = find_java_exe(min_version=1)
            got_ver = _get_java_version(got) if got else 0
            msg = (f"Minecraft {mc_ver} benötigt Java {need_java}+.\n"
                   + (f"Installiert: Java {got_ver} (zu alt).\n" if got_ver else "Java nicht gefunden.\n")
                   + f"Java {need_java} jetzt automatisch installieren?")
            if messagebox.askyesno("Java-Version fehlt", msg):
                install_java_background(
                    on_done=lambda: self.after(0, self._start),
                    on_error=lambda e: self.after(0, lambda: messagebox.showerror(
                        "Fehler", f"Java {need_java} Installation fehlgeschlagen:\n{e}")),
                    version=need_java
                )
            return
        # Laufenden Server stoppen — blocking → in Thread, dann _do_start() aufrufen
        old_proc = self.proc
        if old_proc is not None and old_proc.poll() is None:
            self.proc = None
            self._append_log("[MineHost] Vorherigen Server wird gestoppt…\n")

            def _stop_then_start():
                import time as _tw
                try: old_proc.stdin.write("stop\n"); old_proc.stdin.flush()
                except: pass
                try: old_proc.wait(timeout=10)
                except: pass
                try: old_proc.kill()
                except: pass
                _tw.sleep(0.8)   # Locks freigeben — im Thread, nicht auf UI-Thread
                # Verbleibende Java-Prozesse im Server-Ordner killen
                try:
                    for _p in psutil.process_iter(["name","cmdline"]):
                        try:
                            _cmd = " ".join(_p.info.get("cmdline") or [])
                            if "java" in (_p.info.get("name") or "").lower() and str(srv_dir) in _cmd:
                                _p.kill()
                        except: pass
                except: pass
                # Locks löschen
                for lf in [
                    srv_dir/"logs"/"latest.log",
                    srv_dir/"world"/"session.lock",
                    srv_dir/"world_nether"/"session.lock",
                    srv_dir/"world_the_end"/"session.lock",
                ]:
                    if lf.exists():
                        try: lf.unlink()
                        except: pass
                # Jetzt auf UI-Thread den eigentlichen Start anstoßen
                self.after(0, lambda: self._do_start_server(java, srv_dir))

            threading.Thread(target=_stop_then_start, daemon=True).start()
            return   # _do_start_server wird vom Thread aufgerufen

        # Kein laufender Server → direkt starten
        self._cleanup_locks(srv_dir)
        self._do_start_server(java, srv_dir)

    def _cleanup_locks(self, srv_dir):
        for lock_file in [
            srv_dir / "logs" / "latest.log",
            srv_dir / "world" / "session.lock",
            srv_dir / "world_nether" / "session.lock",
            srv_dir / "world_the_end" / "session.lock",
        ]:
            if lock_file.exists():
                try: lock_file.unlink()
                except: pass

        # Kritische server.properties-Werte vor jedem Start sicherstellen.
        # "pause-when-empty-seconds" > 0 verursacht beim Neustart "Can't keep up"
        # mit der Zeit seit dem letzten Pause (oft 10+ Stunden).
        props = srv_dir / "server.properties"
        if props.exists():
            try:
                import re as _re
                txt = props.read_text(encoding="utf-8", errors="ignore")
                changed = False
                for key, val in [("pause-when-empty-seconds", "-1"),
                                  ("max-tick-time", "-1")]:
                    if f"{key}=" in txt:
                        new = _re.sub(rf"{key}=[^\n]*", f"{key}={val}", txt)
                        if new != txt:
                            txt = new; changed = True
                    else:
                        txt += f"\n{key}={val}\n"; changed = True
                if changed:
                    props.write_text(txt, encoding="utf-8")
            except Exception:
                pass

    def _do_start_server(self, java=None, srv_dir=None):
        """Startet den Minecraft-Prozess (muss auf dem UI-Thread aufgerufen werden)."""
        if java is None:
            mc_ver    = self.cfg.get("mc_version", "1.21")
            need_java = required_java_for_mc(mc_ver)
            java      = find_java_exe(min_version=need_java)
            if not java:
                self._set_state("error"); return
        if srv_dir is None:
            srv_dir = Path(self.cfg.get("dir",""))

        # ── Port-Check: freien Port finden ───────────────────────────────────
        import socket as _sock
        port = int(self.cfg.get("port", 25565))

        def _port_free(p):
            try:
                with _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM) as s:
                    s.setsockopt(_sock.SOL_SOCKET, _sock.SO_REUSEADDR, 1)
                    s.bind(("0.0.0.0", p))
                return True
            except OSError:
                return False

        if not _port_free(port):
            # Nächsten freien Port ab port+1 suchen
            free = next((p for p in range(port + 1, port + 20) if _port_free(p)), None)
            if free is None:
                self._error_log = [f"Kein freier Port gefunden (geprüft: {port}–{port+19})."]
                self._set_state("error")
                return
            self._append_log(
                f"[MineHost] ⚠ Port {port} belegt → weiche auf Port {free} aus\n")
            port = free
            # Config + server.properties aktualisieren
            self.cfg["port"] = str(free)
            save_server_cfg(self.server_name, self.cfg)
            props = srv_dir / "server.properties"
            if props.exists():
                try:
                    import re as _re
                    txt = props.read_text(encoding="utf-8", errors="ignore")
                    txt = _re.sub(r"server-port=\d+", f"server-port={free}", txt)
                    props.write_text(txt, encoding="utf-8")
                except: pass

        self._cleanup_locks(srv_dir)

        srv_type = self.cfg.get("type","vanilla").lower()

        # ── Ressourcen aus Server-Einstellungen + automatische Aufteilung ─────
        total_ram_mb   = psutil.virtual_memory().total // (1024 * 1024)
        total_log_cores = psutil.cpu_count(logical=True) or 4

        cfg_ram_mb    = self.cfg.get("ram_mb", 2048)
        cfg_cpu_cores = int(self.cfg.get("cpu_cores", max(2, total_log_cores // 2)))

        # RAM: Konfigurierter Wert, aber nie mehr als 75% des Systems
        safe_max  = int(total_ram_mb * 0.75)
        start_xmx = min(cfg_ram_mb, safe_max)
        start_xmx = max(1024, start_xmx)
        start_xms = max(512, start_xmx // 8)

        # CPU-Kerne: Berechne welche Kerne noch frei sind (andere Server berücksichtigen)
        used_cores: set = set()
        for es in getattr(self, "_extra_servers", []):
            if es.get("proc") and es["proc"].poll() is None:
                used_cores.update(es.get("_cpu_cores_set", []))

        all_logical = list(range(total_log_cores))
        free_cores  = [c for c in all_logical if c not in used_cores]
        my_cores    = free_cores[:cfg_cpu_cores] or all_logical[:cfg_cpu_cores]

        self._cpu_cores_total = total_log_cores
        self._cpu_cores_cur   = [len(my_cores)]

        self._append_log(
            f"[MineHost] RAM: {start_xmx}MB (Xms {start_xms}MB) | "
            f"CPU: Kerne {my_cores[0]}-{my_cores[-1]} ({len(my_cores)} Stück)\n")

        # Aikar's Flags (kein AlwaysPreTouch — würde bei 30GB sofort ALLES reservieren)
        extra_jvm = [
            "--enable-native-access=ALL-UNNAMED",
            "-Dfile.encoding=UTF-8",
            "-XX:+IgnoreUnrecognizedVMOptions",
            "-XX:+UseG1GC",
            "-XX:+ParallelRefProcEnabled",
            "-XX:MaxGCPauseMillis=200",
            "-XX:+UnlockExperimentalVMOptions",
            "-XX:+DisableExplicitGC",
            f"-XX:G1HeapRegionSize={max(1, min(32, start_xmx // 256))}M",
            "-XX:G1ReservePercent=20",
            "-XX:G1HeapWastePercent=5",
            "-XX:G1MixedGCCountTarget=4",
            "-XX:InitiatingHeapOccupancyPercent=15",
            "-XX:G1MixedGCLiveThresholdPercent=90",
            "-XX:G1RSetUpdatingPauseTimePercent=5",
            "-XX:SurvivorRatio=32",
            "-XX:+PerfDisableSharedMem",
            "-XX:MaxTenuringThreshold=1",
            "-Dusing.aikars.flags=https://mcflags.emc.gs",
        ]

        safe_mode = getattr(self, "_safe_mode_start", False)
        self._safe_mode_start    = False
        self._world_gen_fix_tried = False
        self._error_log           = []
        try:
            mc_args = ["--nogui"]
            if safe_mode:
                mc_args.append("--safeMode")
                self._append_log("[MineHost] ⚠ Starte im Safe-Mode…\n")
            self.proc = subprocess.Popen(
                [java,
                 f"-Xmx{start_xmx}M",
                 f"-Xms{start_xms}M",
                 *extra_jvm,
                 "-jar", "server.jar", *mc_args],
                cwd=str(srv_dir), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
                creationflags=CREATE_NO_WINDOW
            )
        except Exception as e:
            self._error_log = [str(e)]
            self._set_state("error")
            return

        # CPU-Affinity auf die zugewiesenen Kerne setzen
        self._my_cpu_cores = my_cores
        try:
            ps_proc = psutil.Process(self.proc.pid)
            ps_proc.cpu_affinity(my_cores)
        except Exception:
            pass

        self._online_count        = 0
        self._running_server_name = self.server_name
        self._set_state("starting")
        threading.Thread(target=self._read_log,       daemon=True).start()
        threading.Thread(target=self._watchdog,       daemon=True).start()
        threading.Thread(target=self._resource_scaler, daemon=True).start()
        prov = "mine_host" if FREE_VERSION else self.cfg.get("tunnel_provider", "mine_host")
        if prov == "direct":
            self._start_direct_tunnel()
        elif prov == "mine_host":
            if self.cfg.get("minehost_tunnel_id"):
                self._start_tunnel_connector()
            self._start_custom_tunnel()
        else:
            self._start_playit()

    def _watchdog(self):
        """Wartet darauf dass der Prozess endet; überwacht auch Auto-Stop."""
        if not self.proc:
            return
        import time as _time
        empty_since = None   # Zeitpunkt wann zuletzt 0 Spieler festgestellt

        while self.proc.poll() is None:
            _time.sleep(10)
            # Auto-Stop: Spielerzahl aus _online_count prüfen
            if getattr(self, "_server_state", "") == "online":
                autostop_en  = self.cfg.get("autostop_enabled", False)
                autostop_min = int(self.cfg.get("autostop_minutes", 3))
                if autostop_en:
                    count = getattr(self, "_online_count", 0)
                    if count == 0:
                        if empty_since is None:
                            empty_since = _time.monotonic()
                        elif _time.monotonic() - empty_since >= autostop_min * 60:
                            self._append_log(f"[MineHost] Kein Spieler seit {autostop_min} Min → Auto-Stop\n")
                            self.after(0, self._stop)
                            return
                    else:
                        empty_since = None

        # Server-Prozess beendet → Agent für diesen Server schließen
        self._stop_tunnel_connector(self.server_name)
        # Alle Spieler offline setzen
        try:
            db = self._load_known_players()
            for n in db: db[n]["online"] = False
            self._save_known_players(db)
        except: pass

        state = getattr(self, "_server_state", "offline")
        if state == "starting":
            self.after(0, lambda: self._set_state("error"))
        elif state == "online":
            self.after(0, lambda: self._set_state("offline"))

    def _resource_scaler(self):
        """RAM-Nutzung überwachen und warnen. CPU-Affinität NICHT ändern —
        das OS verteilt Kerne besser als wir es könnten."""
        import time as _t
        proc = self.proc
        if not proc: return
        try:
            ps = psutil.Process(proc.pid)
        except Exception: return

        # Warten bis Server online ist
        for _ in range(120):
            if proc.poll() is not None: return
            if getattr(self, "_server_state","") == "online": break
            _t.sleep(2)

        while proc.poll() is None:
            _t.sleep(30)
            if proc.poll() is not None: break
            try:
                mem_mb  = ps.memory_info().rss // (1024*1024)
                xmx_mb  = int(self.cfg.get("ram_mb", 4096))

                # RAM-Warnung
                ram_pct = mem_mb / xmx_mb * 100 if xmx_mb else 0
                if ram_pct > 90:
                    self._append_log(
                        f"[MineHost] ⚠ RAM {mem_mb}MB / {xmx_mb}MB "
                        f"({ram_pct:.0f}%) — kritisch!\n")
                elif ram_pct > 75:
                    self._append_log(
                        f"[MineHost] RAM {mem_mb}MB / {xmx_mb}MB "
                        f"({ram_pct:.0f}%) — hoch\n")
            except Exception:
                break

    # ── Mine-Host Custom Tunnel ───────────────────────────────────────────────

    def _auto_setup_mine_host(self):
        """
        Vollautomatische Einrichtung nach Server-Erstellung:
        1. Tunnel anlegen (falls kein gespeicherter vorhanden)
        2. Adresse sofort im Dashboard anzeigen
        3. Agent (Connector) starten
        """
        import time as _t
        _t.sleep(0.3)  # kurz warten bis Config geschrieben

        # Tunnel-ID schon vorhanden? → nur Connector starten
        if self.cfg.get("minehost_tunnel_id"):
            self._append_log(
                f"[Mine-Host] Tunnel bereits konfiguriert: "
                f"{self.cfg.get('playit_address','?')}\n")
            self._start_tunnel_connector()
            return

        # Noch kein Tunnel → anlegen über API
        self._append_log("[Mine-Host] Richte Tunnel automatisch ein…\n")
        self._start_custom_tunnel_bg()   # erstellt Tunnel + setzt Adresse + startet Connector

    def _make_tunnel_subdomain(self, server_name: str) -> str:
        """Subdomain = Server-Name (slugified). Eindeutigkeit via API-Check."""
        import re as _re
        slug = _re.sub(r'[^a-z0-9-]', '-', server_name.lower())
        slug = _re.sub(r'-+', '-', slug).strip('-')[:20] or "server"
        return slug

    # ── Direkt-Tunnel via UPnP (kostenlos, kein VPS) ──────────────────────────

    def _start_direct_tunnel(self):
        """Öffnet Server-Port via UPnP (Fritz!Box etc.) — kein VPS, keine Kosten."""
        threading.Thread(target=self._start_direct_tunnel_bg, daemon=True).start()

    def _start_direct_tunnel_bg(self):
        port = int(self.cfg.get("port", 25565))
        _log = self._append_log
        _log(f"[UPnP] Öffne Port {port} via Router...\n")
        try:
            import miniupnpc as _u
            u = _u.UPnP()
            u.discoverdelay = 300
            n = u.discover()
            if n == 0:
                _log("[UPnP] Kein UPnP-Gerät gefunden. Bitte am Router UPnP aktivieren.\n"); return
            u.selectigd()
            ext_ip = u.externalipaddress()
            local_ip = u.lanaddr
            _log(f"[UPnP] Router gefunden! Externe IP: {ext_ip}  Lokal: {local_ip}\n")
            # Port öffnen (überschreibt falls schon vorhanden)
            try: u.deleteportmapping(port, "TCP")
            except: pass
            ok = u.addportmapping(port, "TCP", local_ip, port,
                                  f"MineHostLocal {self.server_name}", "")
            if not ok:
                _log(f"[UPnP] Port-Mapping fehlgeschlagen — prüfe Router-Einstellungen.\n"); return
            _log(f"[UPnP] Port {port} geöffnet!\n")

            # DuckDNS-Domain updaten (optional)
            duck_token  = self.cfg.get("duckdns_token", "").strip()
            duck_domain = self.cfg.get("duckdns_domain", "").strip()
            if duck_token and duck_domain:
                try:
                    r = requests.get(
                        f"https://www.duckdns.org/update?domains={duck_domain}&token={duck_token}&ip={ext_ip}",
                        timeout=10)
                    if "OK" in r.text:
                        addr = f"{duck_domain}.duckdns.org:{port}"
                        _log(f"[DuckDNS] Domain aktualisiert: {addr}\n")
                    else:
                        addr = f"{ext_ip}:{port}"
                        _log(f"[DuckDNS] Update fehlgeschlagen — nutze IP: {addr}\n")
                except Exception as de:
                    addr = f"{ext_ip}:{port}"
                    _log(f"[DuckDNS] Fehler: {de} — nutze IP: {addr}\n")
            else:
                addr = f"{ext_ip}:{port}"
                _log(f"[UPnP] Keine DuckDNS-Domain konfiguriert — Adresse: {addr}\n")

            self.cfg["playit_address"] = addr
            save_server_cfg(self.server_name, self.cfg)
            self._playit_addr = addr
            self._playit_limit_error = None
            self.after(0, self._refresh_dashboard)
        except ImportError:
            _log("[UPnP] miniupnpc fehlt. Installiere: pip install miniupnpc\n")
        except Exception as e:
            _log(f"[UPnP] Fehler: {e}\n")

    def _stop_direct_tunnel(self):
        """Schließt den UPnP Port-Mapping wieder."""
        port = int(self.cfg.get("port", 25565))
        try:
            import miniupnpc as _u
            u = _u.UPnP()
            u.discoverdelay = 200
            if u.discover() > 0:
                u.selectigd()
                u.deleteportmapping(port, "TCP")
                self._append_log(f"[UPnP] Port {port} geschlossen.\n")
        except: pass

    def _start_custom_tunnel(self):
        """Startet den minehost-local.uk Tunnel im Hintergrund."""
        threading.Thread(target=self._start_custom_tunnel_bg, daemon=True).start()

    def _start_custom_tunnel_bg(self):
        """Hintergrund-Thread: Tunnel abrufen/erstellen, Adresse setzen."""
        import time as _t
        API    = MINEHOST_TUNNEL_API
        DOMAIN      = MINEHOST_TUNNEL_DOMAIN
        subdomain   = self._make_tunnel_subdomain(self.server_name)
        srv_name    = self.cfg.get("name", self.server_name) or self.server_name
        port        = int(self.cfg.get("port", 25565))
        max_pl      = int(self.cfg.get("max_players", 20))
        custom_dom  = self.cfg.get("tunnel_custom_domain", "")  # z.B. mc.meinserver.de
        srv_type    = self.cfg.get("type", "vanilla").lower()
        game_type   = "bedrock" if "bedrock" in srv_type else "java"
        hdrs        = {"Content-Type": "application/json", "User-Agent": "MineHostLocal/1.0"}

        self._append_log(f"[Tunnel] Verbinde mit {DOMAIN} (Subdomain: {subdomain})…\n")

        # ── Tunnel suchen — NUR nach gespeicherter ID, NIE nach Subdomain ───────
        # (Subdomain-Match würde fremde Server-Tunnel finden!)
        existing_id = self.cfg.get("minehost_tunnel_id", "")
        tunnel_id   = None
        if existing_id:
            try:
                r = requests.get(f"{API}/api/tunnels", headers=hdrs, timeout=10)
                tunnels = r.json() if isinstance(r.json(), list) else []
                for t in tunnels:
                    if t.get("id") == existing_id:
                        tunnel_id = t["id"]
                        self._append_log(f"[Tunnel] Eigener Tunnel gefunden (ID: {tunnel_id[:8]}…)\n")
                        break
                if not tunnel_id:
                    self._append_log(f"[Tunnel] Gespeicherter Tunnel nicht mehr vorhanden → erstelle neuen\n")
            except Exception as e:
                self._append_log(f"[Tunnel] ✗ Tunnel-Liste: {e}\n"); return

        # ── Tunnel erstellen falls nicht vorhanden ────────────────────────────
        if not tunnel_id:
            self._append_log(f"[Tunnel] Erstelle neuen Tunnel…\n")
            try:
                body = {"name": srv_name, "subdomain": subdomain,
                        "targetHost": "127.0.0.1", "targetPort": port,
                        "type": game_type, "playersMax": max_pl}
                if custom_dom:
                    body["customDomain"] = custom_dom
                r = requests.post(f"{API}/api/tunnels", json=body,
                                  headers=hdrs, timeout=12)
                if r.status_code in (200, 201):
                    data = r.json()
                    tunnel_id = data.get("id", "")
                    self._append_log(f"[Tunnel] ✓ Tunnel erstellt (ID: {tunnel_id[:8]}…)\n")
                else:
                    self._append_log(f"[Tunnel] ✗ Erstellen fehlgeschlagen: {r.status_code} {r.text[:100]}\n")
                    return
            except Exception as e:
                self._append_log(f"[Tunnel] ✗ Fehler: {e}\n"); return

        if not tunnel_id:
            return

        # ── Tunnel aktivieren (toggle) ────────────────────────────────────────
        try:
            requests.post(f"{API}/api/tunnels/{tunnel_id}/toggle",
                          headers=hdrs, timeout=8)
        except: pass

        # ── Adresse setzen (Subdomain stimmt mit Server-Name überein) ──────────
        addr = f"{subdomain}.{DOMAIN}"
        self.cfg["playit_address"]     = addr
        self.cfg["minehost_tunnel_id"] = tunnel_id
        save_server_cfg(self.server_name, self.cfg)
        self._playit_addr         = addr
        self._playit_limit_error  = None
        self._playit_connected    = True
        self._append_log(f"[Tunnel] ✓ Adresse: {addr}\n")
        self.after(0, self._refresh_dashboard)
        # Connector nur starten falls noch nicht läuft (kann schon zeitgleich gestartet sein)
        entry = self._tunnel_connectors.get(self.server_name, {})
        proc  = entry.get("proc")
        ev    = entry.get("stop_ev")
        if not ((ev and not ev.is_set()) or (proc and proc.poll() is None)):
            self.after(300, self._start_tunnel_connector)

    def _stop_custom_tunnel(self):
        """Deaktiviert den minehost-local.uk Tunnel im Hintergrund."""
        tid = self.cfg.get("minehost_tunnel_id", "")
        if not tid: return
        def _do():
            try:
                requests.post(f"{MINEHOST_TUNNEL_API}/api/tunnels/{tid}/toggle",
                              headers={"Content-Type": "application/json",
                                       "User-Agent": "MineHostLocal/1.0"},
                              timeout=8)
            except: pass
        threading.Thread(target=_do, daemon=True).start()

    # ── Tunnel-Connector (tunnel-connector.js / Node.js) ──────────────────────

    def _start_tunnel_connector(self, server_name=None, cfg=None):
        """Startet Tunnel-Connector für einen Server. Mehrere Server laufen parallel."""
        import subprocess as _sp, re as _re
        srv  = server_name or self.server_name
        cfg_ = cfg or (self.cfg if srv == self.server_name else load_server_cfg(srv))
        tid  = cfg_.get("minehost_tunnel_id", "")

        if not tid:
            self._append_log(f"[Tunnel:{srv}] ✗ Keine Tunnel-ID.\n"); return

        # Bereits laufend für diesen Server?
        entry = self._tunnel_connectors.get(srv, {})
        if ((entry.get("stop_ev") and not entry["stop_ev"].is_set()) or
                (entry.get("proc") and entry["proc"].poll() is None)):
            return

        _log = self._append_log

        # ── Variante 1: tunnel-connector.exe ────────────────────────────────
        exe = next((p for p in [
            Path(sys.executable).parent / "tunnel-connector.exe",
            APP_DIR.parent / "tunnel-connector.exe",
            APP_DIR / "tunnel-connector.exe",
            Path(__file__).parent / "dist" / "tunnel-connector.exe",
        ] if p.exists()), None)

        if exe:
            _log(f"[Tunnel:{srv}] Starte Connector (ID: {tid[:8]}…)\n")
            try:
                port_str = str(int(cfg_.get("port", 25565)))
                proc = _sp.Popen([str(exe), "host", tid, "--port", port_str],
                                 stdout=_sp.PIPE, stderr=_sp.STDOUT,
                                 creationflags=CREATE_NO_WINDOW)
                stop_ev = threading.Event()
                self._tunnel_connectors[srv] = {"proc": proc, "stop_ev": stop_ev}

                def _read(p=proc, s=srv):
                    ansi = _re.compile(r'\x1b\[[0-9;]*[mK]')
                    for raw in p.stdout:
                        try:
                            line = ansi.sub('', raw.decode("utf-8", errors="replace")).rstrip()
                            if line: _log(f"[Tunnel:{s}] {line}\n")
                        except: pass
                    _log(f"[Tunnel:{s}] Connector beendet.\n")
                threading.Thread(target=_read, daemon=True).start()
                return
            except Exception as e:
                _log(f"[Tunnel:{srv}] ⚠ EXE fehlgeschlagen ({e}) — Python-Fallback\n")

        # ── Variante 2: Python-async Fallback ───────────────────────────────
        port   = int(cfg_.get("port", 25565))
        domain = MINEHOST_TUNNEL_API.replace("https://","").replace("http://","").rstrip("/")
        _log(f"[Tunnel:{srv}] Python-Connector (ID: {tid[:8]}… :{port})\n")

        stop_ev = threading.Event()
        self._tunnel_connectors[srv] = {"proc": None, "stop_ev": stop_ev}

        def _run(d=domain, t=tid, se=stop_ev, s=srv, p=port):
            import asyncio as _aio
            loop = _aio.new_event_loop()
            _aio.set_event_loop(loop)
            try:
                loop.run_until_complete(_mh_host_loop(d, t, "127.0.0.1", p, _log, se))
            except Exception as ex:
                _log(f"[Tunnel:{s}] Beendet: {ex}\n")
            finally:
                loop.close()
        threading.Thread(target=_run, daemon=True).start()

    def _stop_tunnel_connector(self, server_name=None):
        """Beendet Connector eines einzelnen Servers."""
        srv = server_name or self.server_name
        entry = self._tunnel_connectors.pop(srv, {})
        if entry.get("stop_ev"): entry["stop_ev"].set()
        proc = entry.get("proc")
        if proc and proc.poll() is None:
            try: proc.terminate()
            except: pass

    def _stop_all_tunnel_connectors(self):
        """Beendet alle laufenden Connectors."""
        for srv in list(self._tunnel_connectors.keys()):
            self._stop_tunnel_connector(srv)

    def _start_tunnel_status_poller(self):
        """Pollt alle 15s den Tunnel-Status von der API und aktualisiert Dashboard."""
        def _poll():
            import time as _t
            while True:
                _t.sleep(15)
                if self.cfg.get("tunnel_provider","playit") != "mine_host":
                    continue
                tid = self.cfg.get("minehost_tunnel_id","")
                if not tid:
                    continue
                try:
                    r = requests.get(f"{MINEHOST_TUNNEL_API}/api/tunnels",
                                     timeout=8, headers={"User-Agent":"MineHostLocal/1.0"})
                    for t in (r.json() if isinstance(r.json(), list) else []):
                        if t.get("id") == tid:
                            hc = t.get("hostConnected", False)
                            self._mh_host_connected = hc
                            self._mh_players_online = t.get("playersOnline", 0)
                            # Connector nicht verbunden → neu starten
                            if not hc:
                                entry = self._tunnel_connectors.get(self.server_name, {})
                                ev = entry.get("stop_ev")
                                pr = entry.get("proc")
                                if not ((ev and not ev.is_set()) or (pr and pr.poll() is None)):
                                    self.after(0, self._start_tunnel_connector)
                            break
                except: pass
        threading.Thread(target=_poll, daemon=True).start()

    def _start_client_connector(self, tunnel_id: str, local_port: int):
        """Startet den Client-Connector auf einem lokalen Port (zum Testen)."""
        import subprocess as _sp, re as _re
        exe = next((p for p in [
            Path(sys.executable).parent / "tunnel-connector.exe",
            APP_DIR.parent / "tunnel-connector.exe",
            APP_DIR / "tunnel-connector.exe",
            Path(__file__).parent / "dist" / "tunnel-connector.exe",
        ] if p.exists()), None)
        if not exe:
            self._append_log("[Tunnel] tunnel-connector.exe nicht gefunden.\n"); return

        # Alten Client-Connector stoppen
        old = getattr(self, "_mh_client_proc", None)
        if old and old.poll() is None:
            try: old.terminate()
            except: pass

        self._mh_client_port = local_port
        self._append_log(f"[Tunnel] Client-Connector auf localhost:{local_port} starten...\n")
        try:
            proc = _sp.Popen([str(exe), "client", tunnel_id, "--port", str(local_port)],
                             stdout=_sp.PIPE, stderr=_sp.STDOUT,
                             creationflags=CREATE_NO_WINDOW)
            self._mh_client_proc = proc

            def _read():
                ansi = _re.compile(r'\x1b\[[0-9;]*[mK]')
                for raw in proc.stdout:
                    try:
                        line = ansi.sub('', raw.decode("utf-8", errors="replace")).rstrip()
                        if line: self._append_log(f"[TunnelClient] {line}\n")
                    except: pass
            threading.Thread(target=_read, daemon=True).start()
            self.after(1000, self._refresh_dashboard)
        except Exception as e:
            self._append_log(f"[Tunnel] Client-Start-Fehler: {e}\n")

    def _rename_tunnel_dialog(self):
        """Öffnet die Tunnel-Verwaltungsseite im Browser."""
        import webbrowser as _wb
        _wb.open(MINEHOST_TUNNEL_API)

    def _start_playit_background(self):
        """
        Startet playit.exe beim App-Start im Hintergrund → Agent bleibt online.
        Läuft ohne Server, nur damit der Agent aktiv ist.
        """
        srv_dir         = Path(self.cfg.get("dir", "")) if self.cfg else None
        global_key_path = APP_DIR / "playit_secret.txt"

        # Key laden
        secret_key = ""
        if global_key_path.exists():
            secret_key = global_key_path.read_text(encoding="utf-8").strip()
        if not secret_key and srv_dir:
            toml = srv_dir / "playit.toml"
            if toml.exists():
                secret_key = toml.read_text(encoding="utf-8").strip()

        if not secret_key:
            return  # Noch nicht eingeloggt → nichts tun

        # Falls playit schon läuft → nicht nochmal starten
        if getattr(self, "_playit_mgr", None) and getattr(self._playit_mgr, "proc", None) and \
                self._playit_mgr.proc.poll() is None:
            return

        # playit.exe im Hintergrund starten (kein Tunnel erstellen — nur Agent online)
        work_dir = srv_dir if srv_dir and srv_dir.exists() else APP_DIR
        mgr = PlayitManager(work_dir)

        def _on_log(line):
            # Agent-ID merken falls noch nicht bekannt
            import re as _re
            m = _re.search(r"agent_id=([\w\-]+)", line)
            if m and not getattr(self, "_playit_agent_id", None):
                self._playit_agent_id = m.group(1)
            if "playit connected" in line.lower():
                self._playit_connected = True

        mgr.on_log     = _on_log
        mgr.on_address = None   # keine Adresse setzen — das macht _start_playit() später
        self._playit_bg_mgr = mgr
        mgr.start()

    def _start_playit(self):
        """
        Pro-Server Tunnel-Start:
        1. Alle Flags zurücksetzen
        2. Secret Key laden
        3. playit.exe starten
        4. Tunnel-ID gespeichert → Adresse holen, sonst neu erstellen
        """
        # Alle Flags zurücksetzen — verhindert dass alte Sessions blockieren
        self._tunnel_creation_running = False
        self._fetching_address        = False
        self._playit_launch_lock      = False

        srv_dir         = Path(self.cfg.get("dir", ""))
        toml_path       = srv_dir / "playit.toml"
        global_key_path = APP_DIR / "playit_secret.txt"

        # Gespeicherte Adresse sofort anzeigen
        saved_addr = self.cfg.get("playit_address")
        if saved_addr:
            self._playit_addr = saved_addr
            self.after(0, self._refresh_dashboard)

        # Secret Key laden
        secret_key = ""
        if toml_path.exists():
            secret_key = toml_path.read_text(encoding="utf-8").strip()
        if not secret_key and global_key_path.exists():
            secret_key = global_key_path.read_text(encoding="utf-8").strip()
            if secret_key:
                toml_path.write_text(secret_key, encoding="utf-8")

        if not secret_key:
            # Kein Key → einmaliger Browser-Login
            threading.Thread(
                target=self._auto_claim_flow,
                args=(srv_dir, toml_path, global_key_path),
                daemon=True).start()
            return

        # Tunnel-ID für diesen Server aus Config
        saved_tunnel_id = self.cfg.get("playit_tunnel_id", "")

        self._launch_playit_with_secret(srv_dir, toml_path, secret_key,
                                        server_tunnel_id=saved_tunnel_id)

    def _auto_claim_flow(self, srv_dir, toml_path, global_key_path):
        """
        Einmaliger automatischer Claim-Flow im Hintergrund.
        Browser öffnet sich NUR einmal, danach läuft alles automatisch.
        """
        import time as _t, webbrowser as _wb
        PLAYIT_API = "https://api.playit.gg"

        self._append_log("[playit.gg] Erster Start: Einmalige Browser-Anmeldung erforderlich…\n")
        self.after(0, self._refresh_dashboard)

        code = "".join(random.choices(string.ascii_letters + string.digits, k=16))
        try:
            r = requests.post(f"{PLAYIT_API}/claim/setup",
                              json={"code": code, "agent_type": "self-managed",
                                    "version": "MineHostLocal/1.0"},
                              timeout=10)
            if r.json().get("data") not in ("WaitingForUserVisit", "WaitingForUser"):
                self._append_log(f"[playit.gg] ✗ API-Fehler: {r.text}\n"); return
        except Exception as e:
            self._append_log(f"[playit.gg] ✗ Netzwerk-Fehler: {e}\n"); return

        # Browser öffnen — NUR dieser eine Schritt ist manuell
        _wb.open(f"https://playit.gg/claim/{code}")
        self._append_log(f"[playit.gg] Browser geöffnet → playit.gg/claim/{code}\n"
                         f"[playit.gg] Bitte im Browser einloggen & bestätigen…\n")

        # Pollen bis bestätigt
        for _ in range(90):
            _t.sleep(2)
            try:
                r = requests.post(f"{PLAYIT_API}/claim/setup",
                                  json={"code": code, "agent_type": "self-managed",
                                        "version": "MineHostLocal/1.0"},
                                  timeout=8)
                status = r.json().get("data")
                if status == "UserAccepted":
                    break
                if status == "UserRejected":
                    self._append_log("[playit.gg] ✗ Abgelehnt.\n"); return
            except: pass
        else:
            self._append_log("[playit.gg] ✗ Timeout bei der Bestätigung.\n"); return

        # Secret Key holen
        try:
            r = requests.post(f"{PLAYIT_API}/claim/exchange",
                              json={"code": code}, timeout=10)
            secret_key = r.json()["data"]["secret_key"]
        except Exception as e:
            self._append_log(f"[playit.gg] ✗ Exchange-Fehler: {e}\n"); return

        # Global + Server-lokal speichern
        global_key_path.write_text(secret_key, encoding="utf-8")
        toml_path.write_text(secret_key, encoding="utf-8")
        self._append_log("[playit.gg] ✓ Angemeldet! Tunnel startet automatisch…\n")

        self.after(0, lambda: self._launch_playit_with_secret(srv_dir, toml_path, secret_key))

    def _launch_playit_with_secret(self, srv_dir, toml_path, secret_key,
                                   server_tunnel_id: str = ""):
        """
        Startet playit.exe. Jeder Server hat seinen eigenen Tunnel:
        - server_tunnel_id gesetzt  → diese Tunnel-ID direkt nutzen
        - server_tunnel_id leer     → neuen Tunnel für diesen Server erstellen
        """
        self._playit_secret_key = secret_key

        # Globaler Lock: verhindert dass mehrere playit.exe gleichzeitig starten
        if getattr(self, "_playit_launch_lock", False):
            self._append_log("[playit.gg] ⚠ playit startet bereits — überspringe doppelten Start.\n")
            return
        self._playit_launch_lock = True

        # Bestehenden Manager sauber stoppen
        old_mgr = getattr(self, "_playit_mgr", None)
        if old_mgr:
            try: old_mgr.stop()
            except: pass
            self._playit_mgr = None

        # Alle playit.exe-Prozesse via psutil beenden
        try:
            for p in psutil.process_iter(["name"]):
                if "playit" in (p.info.get("name") or "").lower():
                    try: p.kill()
                    except: pass
        except: pass

        import time as _tkill; _tkill.sleep(1.0)
        self._playit_launch_lock = False  # Lock freigeben nach Kill

        mgr = PlayitManager(srv_dir)

        def on_address(addr):
            self._playit_addr  = addr
            self._playit_claim = None
            self.cfg["playit_address"] = addr
            save_server_cfg(self.server_name, self.cfg)
            self._append_log(f"[playit.gg] ✓ Adresse für {self.cfg.get('name','?')}: {addr}\n")
            self.after(0, self._refresh_dashboard)

        def on_log(line):
            self._append_log(line)
            low = line.lower()
            if "playit connected" in low or "tunnel state updated" in low:
                import re as _re
                m = _re.search(r"agent_id=([\w\-]+)", line)
                if m:
                    self._playit_agent_id = m.group(1)
                mc = _re.search(r"tunnel_count=(\d+)", line)
                count = int(mc.group(1)) if mc else -1
                self._playit_connected = True

                if "agent_over_limit=true" in line:
                    self._show_playit_limit_error("over_limit")
                    self.after(0, self._refresh_dashboard)
                    return

                if not getattr(self,"_playit_limit_error",None) and not getattr(self,"_fetching_address",False):
                    aid = self._playit_agent_id
                    if server_tunnel_id:
                        # Tunnel-ID bekannt → Adresse immer frisch holen (auch wenn gespeichert)
                        self._append_log(f"[playit.gg] Bekannter Tunnel ({server_tunnel_id[:8]}…) → hole Adresse\n")
                        threading.Thread(
                            target=self._fetch_address_by_tunnel_id,
                            args=(secret_key, server_tunnel_id, on_address),
                            daemon=True).start()
                    else:
                        # Kein Tunnel → nur einmalig erstellen
                        if not getattr(self, "_tunnel_creation_running", False):
                            self._tunnel_creation_running = True
                            self._append_log("[playit.gg] Neuer Server → erstelle Tunnel…\n")
                            threading.Thread(
                                target=self._create_tunnel_for_server,
                                args=(secret_key, aid, on_address),
                                daemon=True).start()

                self.after(0, self._refresh_dashboard)

        mgr.on_address = on_address
        mgr.on_log     = on_log
        self._playit_connected = False
        self._playit_email_unverified = False
        self._playit_limit_error = None
        self._tunnel_creation_running = False
        self._playit_mgr = mgr
        mgr.start()

        # 30s-Watchdog: NUR wenn dieser Server schon eine Tunnel-ID hat
        # (neuer Server = Browser-Flow läuft bereits, kein zweiter Trigger nötig)
        if server_tunnel_id:
            def _tunnel_watchdog():
                import time as _t
                _t.sleep(30)
                if (not self._playit_addr
                        and not getattr(self, "_playit_limit_error", None)
                        and self.proc is not None
                        and self.proc.poll() is None):
                    self._append_log("[playit.gg] ??? 30s ohne Adresse → hole Adresse erneut…\n")
                    threading.Thread(
                        target=self._fetch_address_by_tunnel_id,
                        args=(secret_key, server_tunnel_id, on_address),
                        daemon=True).start()
            threading.Thread(target=_tunnel_watchdog, daemon=True).start()

    def _fetch_address_by_tunnel_id(self, secret_key: str, tunnel_id: str, on_address_cb):
        """Holt die Adresse für eine bekannte Tunnel-ID — aktiviert sie wenn nötig."""
        # Nur EINE Instanz gleichzeitig
        if getattr(self, "_fetching_address", False):
            return
        self._fetching_address = True

        import time as _t
        PLAYIT_API = "https://api.playit.gg"
        headers    = {"Authorization": f"agent-key {secret_key}"}
        _enabled   = False  # Haben wir schon versucht zu aktivieren?

        try:
            for attempt in range(40):
                try:
                    r = requests.post(f"{PLAYIT_API}/tunnels/list",
                                      json={"tunnel_id": None, "agent_id": None},
                                      headers=headers, timeout=8)
                    data = r.json()
                    if data.get("status") != "success":
                        _t.sleep(3); continue

                    found = False
                    for t in data["data"].get("tunnels", []):
                        if t.get("id") != tunnel_id:
                            continue
                        found = True
                        alloc      = t.get("alloc") or {}
                        alloc_data = alloc.get("data") or {}
                        status     = alloc.get("status","")
                        enabled    = t.get("enabled", True)

                        # Tunnel deaktiviert → einmalig aktivieren
                        if not enabled or status == "disabled":
                            if not _enabled:
                                _enabled = True
                                self._append_log("[playit.gg] Tunnel deaktiviert → aktiviere…\n")
                                requests.post(f"{PLAYIT_API}/tunnels/enable",
                                              json={"id": tunnel_id},
                                              headers=headers, timeout=8)
                                # Fallback: update mit enabled=True
                                requests.post(f"{PLAYIT_API}/tunnels/update",
                                              json={"tunnel_id": tunnel_id, "enabled": True},
                                              headers=headers, timeout=8)
                                _t.sleep(3)
                            break  # Nächste Iteration abwarten

                        # Adresse lesen — mehrere mögliche Feldnamen abfangen
                        domain = (alloc_data.get("assigned_domain") or
                                  alloc_data.get("ip_hostname") or
                                  alloc_data.get("domain") or
                                  alloc_data.get("host") or
                                  alloc_data.get("address",""))
                        port   = (alloc_data.get("port_start") or
                                  alloc_data.get("port") or
                                  alloc_data.get("assigned_port",""))

                        if domain and port:
                            addr = f"{domain}:{port}"
                            self._append_log(f"[playit.gg] ✓ Adresse: {addr}\n")
                            self.cfg["playit_address"] = addr
                            save_server_cfg(self.server_name, self.cfg)
                            self._playit_addr = addr
                            self._playit_limit_error = None
                            self.after(0, self._refresh_dashboard)
                            if on_address_cb: on_address_cb(addr)
                            return

                        # Pending: nur alle 5 Versuche loggen
                        if attempt % 5 == 0:
                            self._append_log(
                                f"[playit.gg] Warte auf Adresse (Status: {status or 'pending'})…\n")
                        break

                    if not found and attempt % 5 == 0:
                        self._append_log(f"[playit.gg] Tunnel noch nicht sichtbar… ({attempt+1}/40)\n")

                except Exception as e:
                    if attempt % 5 == 0:
                        self._append_log(f"[playit.gg] Fehler: {e}\n")
                _t.sleep(3)

            # Timeout → löschen und neu erstellen
            self._append_log("[playit.gg] ??? Timeout — erstelle neuen Tunnel…\n")
            self.cfg.pop("playit_tunnel_id", None)
            self.cfg.pop("playit_address", None)
            save_server_cfg(self.server_name, self.cfg)
            self._create_tunnel_for_server(secret_key, getattr(self, "_playit_agent_id", None), on_address_cb)
        finally:
            self._fetching_address = False

    # ── playit.gg Smart-Tunnel-Management ────────────────────────────────────

    def _get_all_used_tunnel_addresses(self) -> dict:
        """Gibt {address: server_name} für alle Server zurück die eine playit-Adresse haben."""
        result = {}
        for name in list_servers():
            try:
                cfg = load_server_cfg(name)
                addr = cfg.get("playit_address", "")
                if addr:
                    result[addr] = name
            except: pass
        return result

    def _playit_cleanup_and_reuse(self, secret_key: str, on_log, reuse_for: str = "") -> str | None:
        """
        Bereinigt alle playit.gg-Tunnel:
        1. Tunnel ohne Adresse → löschen
        2. Tunnel mit Adresse, die in keinem Server verwendet wird:
           - Ersten davon: Adresse bei reuse_for-Server speichern, zurückgeben
           - Weitere: löschen
        Gibt die wiederverwendbare Adresse zurück oder None.
        """
        import time as _t
        PLAYIT_API = "https://api.playit.gg"
        headers    = {"Authorization": f"agent-key {secret_key}"}
        used       = self._get_all_used_tunnel_addresses()

        on_log("[playit.gg] ?? Tunnel-Bereinigung startet…\n")
        try:
            r = requests.post(f"{PLAYIT_API}/tunnels/list",
                              json={"tunnel_id": None, "agent_id": None},
                              headers=headers, timeout=10)
            data = r.json()
            if data.get("status") != "success":
                on_log(f"[playit.gg] ✗ Tunnel-Liste: {data}\n"); return None

            tunnels   = data["data"].get("tunnels", [])
            deleted   = 0
            reuse_addr = None
            reuse_tid  = None

            for t in tunnels:
                tid   = t.get("id", "")
                tname = t.get("name", tid[:8] if tid else "?")
                alloc      = t.get("alloc") or {}
                alloc_data = alloc.get("data") or {}
                domain = (alloc_data.get("assigned_domain") or
                          alloc_data.get("ip_hostname") or
                          alloc_data.get("domain") or "")
                port   = (alloc_data.get("port_start") or
                          alloc_data.get("port") or "")
                addr = f"{domain}:{port}" if (domain and port) else ""

                if not addr:
                    on_log(f"[playit.gg] 🗑 Lösche Tunnel ohne Adresse: '{tname}'\n")
                    try:
                        requests.post(f"{PLAYIT_API}/tunnels/delete",
                                      json={"id": tid}, headers=headers, timeout=8)
                        deleted += 1; _t.sleep(0.3)
                    except: pass
                elif addr not in used:
                    if reuse_addr is None:
                        reuse_addr = addr; reuse_tid = tid
                        on_log(f"[playit.gg] ♻  Unbenutzter Tunnel: '{tname}' → {addr}\n")
                    else:
                        on_log(f"[playit.gg] 🗑 Weiterer unbenutzter Tunnel → lösche: '{tname}'\n")
                        try:
                            requests.post(f"{PLAYIT_API}/tunnels/delete",
                                          json={"id": tid}, headers=headers, timeout=8)
                            deleted += 1; _t.sleep(0.3)
                        except: pass
                else:
                    on_log(f"[playit.gg] ✓ Tunnel '{tname}' in Verwendung → behalten\n")

            on_log(f"[playit.gg] Bereinigung: {deleted} gelöscht"
                   + (f", 1 wiederverwendbar ({reuse_addr})" if reuse_addr else "") + "\n")

            if reuse_addr and reuse_for:
                target_cfg = load_server_cfg(reuse_for)
                target_cfg["playit_address"]   = reuse_addr
                target_cfg["playit_tunnel_id"] = reuse_tid or ""
                save_server_cfg(reuse_for, target_cfg)
                on_log(f"[playit.gg] ✓ Adresse {reuse_addr} → '{reuse_for}' gespeichert\n")
                return reuse_addr
            return None
        except Exception as e:
            on_log(f"[playit.gg] ✗ Bereinigung fehlgeschlagen: {e}\n")
            return None

    def _playit_new_agent_fallback(self, secret_key: str, on_log, on_address_cb):
        """
        Absoluter Notfall: Erstellt einen zweiten playit.gg-Agenten (neuen Secret Key).
        Läuft vollautomatisch über den Claim-Flow.
        """
        import time as _t, random as _r, string as _s, webbrowser as _wb
        PLAYIT_API = "https://api.playit.gg"
        fallback_key_path = APP_DIR / "playit_secret_2.txt"

        on_log("[playit.gg] 🚨 Notfall: Erstelle neuen Agenten (zweiter Key)…\n")

        # Bereits vorhandenen zweiten Key nutzen
        if fallback_key_path.exists():
            sk2 = fallback_key_path.read_text(encoding="utf-8").strip()
            if sk2:
                on_log("[playit.gg] Zweiter Agent bereits vorhanden — nutze ihn.\n")
                srv_dir = Path(self.cfg.get("dir",""))
                (srv_dir / "playit.toml").write_text(sk2, encoding="utf-8")
                (APP_DIR / "playit_secret.txt").write_text(sk2, encoding="utf-8")
                self._playit_secret_key = sk2
                self.after(0, lambda: threading.Thread(
                    target=self._create_tunnel_for_server,
                    args=(sk2, None, on_address_cb), daemon=True).start())
                return

        # Neuen Agenten über Claim-Flow registrieren
        code = "".join(_r.choices(_s.ascii_letters + _s.digits, k=16))
        try:
            r = requests.post(f"{PLAYIT_API}/claim/setup",
                              json={"code": code, "agent_type": "self-managed",
                                    "version": "MineHostLocal/1.0"}, timeout=10)
            if r.json().get("data") not in ("WaitingForUserVisit", "WaitingForUser"):
                on_log(f"[playit.gg] ✗ Claim-Setup fehlgeschlagen: {r.text}\n"); return
        except Exception as e:
            on_log(f"[playit.gg] ✗ Netzwerk-Fehler: {e}\n"); return

        _wb.open(f"https://playit.gg/claim/{code}")
        on_log(f"[playit.gg] Browser geöffnet → playit.gg/claim/{code}\n"
               f"[playit.gg] Bitte bestätigen — danach startet Tunnel automatisch.\n")

        for _ in range(90):
            _t.sleep(2)
            try:
                r = requests.post(f"{PLAYIT_API}/claim/setup",
                                  json={"code": code, "agent_type": "self-managed",
                                        "version": "MineHostLocal/1.0"}, timeout=8)
                st = r.json().get("data")
                if st == "UserAccepted": break
                if st == "UserRejected":
                    on_log("[playit.gg] ✗ Abgelehnt.\n"); return
            except: pass
        else:
            on_log("[playit.gg] ✗ Timeout.\n"); return

        try:
            r = requests.post(f"{PLAYIT_API}/claim/exchange",
                              json={"code": code}, timeout=10)
            sk2 = r.json()["data"]["secret_key"]
        except Exception as e:
            on_log(f"[playit.gg] ✗ Exchange: {e}\n"); return

        fallback_key_path.write_text(sk2, encoding="utf-8")
        srv_dir = Path(self.cfg.get("dir",""))
        (srv_dir / "playit.toml").write_text(sk2, encoding="utf-8")
        (APP_DIR / "playit_secret.txt").write_text(sk2, encoding="utf-8")
        self._playit_secret_key = sk2
        on_log("[playit.gg] ✓ Neuer Agent registriert!\n")
        self.after(0, lambda: threading.Thread(
            target=self._create_tunnel_for_server,
            args=(sk2, None, on_address_cb), daemon=True).start())

    def _create_tunnel_for_server(self, secret_key: str, agent_id: str, on_address_cb):
        """
        Erstellt vollautomatisch einen Tunnel via playit.gg API.
        Kein Browser, kein manueller Schritt.
        """
        import time as _t
        PLAYIT_API = "https://api.playit.gg"
        headers    = {"Authorization": f"agent-key {secret_key}"}
        srv_port   = int(self.cfg.get("port", 25565))
        srv_name   = self.cfg.get("name", "MineHost")

        self._append_log(f"[playit.gg] Erstelle Tunnel automatisch via API…\n")

        # Warten bis agent_id bekannt (max 15s)
        for _ in range(15):
            agent_id = agent_id or getattr(self, "_playit_agent_id", None)
            if agent_id: break
            _t.sleep(1)

        if not agent_id:
            self._append_log("[playit.gg] ✗ Agent-ID unbekannt — kann keinen Tunnel erstellen.\n")
            self._tunnel_creation_running = False
            self._show_playit_limit_error("agent_deleted")
            return

        # ── Schritt 1: Smart-Bereinigung + Adresse wiederverwenden ──────────
        reused = self._playit_cleanup_and_reuse(
            secret_key, self._append_log, reuse_for=self.server_name)
        if reused:
            self._playit_addr = reused
            self._playit_limit_error = None
            self._tunnel_creation_running = False
            self.after(0, self._refresh_dashboard)
            if on_address_cb: on_address_cb(reused)
            return
        _t.sleep(1)  # kurz warten nach Löschungen

        # Tunnel erstellen — mit Server-Name damit Tunnel benannt sind
        srv_name = self.cfg.get("name", self.server_name) or self.server_name
        body = {
            "tunnel_type": "minecraft-java",
            "port_type": "tcp",
            "port_count": 1,
            "name": srv_name,
            "origin": {
                "type": "agent",
                "data": {
                    "agent_id": agent_id,
                    "local_ip": "127.0.0.1",
                    "local_port": srv_port,
                }
            },
            "enabled": True,
        }
        try:
            r = requests.post(f"{PLAYIT_API}/tunnels/create",
                              json=body, headers=headers, timeout=12)
            data = r.json()
            if data.get("status") == "success":
                tid = data["data"]["id"]
                self._append_log(f"[playit.gg] ✓ Tunnel erstellt! ({tid[:8]}…)\n")
                self.cfg["playit_tunnel_id"] = tid
                save_server_cfg(self.server_name, self.cfg)
                self._tunnel_creation_running = False
                _t.sleep(3)
                self._fetch_address_by_tunnel_id(secret_key, tid, on_address_cb)
                return
            else:
                err = str(data).lower()
                self._append_log(f"[playit.gg] ✗ API-Fehler: {data}\n")
                if any(x in err for x in ("limit","quota","maximum")):
                    # Letzter Ausweg: neuen Agenten erstellen
                    self._append_log("[playit.gg] ⚠ Limit nach Bereinigung immer noch erreicht → neuer Agent…\n")
                    self._tunnel_creation_running = False
                    threading.Thread(
                        target=self._playit_new_agent_fallback,
                        args=(secret_key, self._append_log, on_address_cb),
                        daemon=True).start()
                    return
                else:
                    self._show_playit_limit_error("unknown")
        except Exception as e:
            self._append_log(f"[playit.gg] ✗ Fehler: {e}\n")
            self._show_playit_limit_error("unknown")

        self._tunnel_creation_running = False

    def _show_playit_limit_error(self, reason="limit"):
        self._playit_limit_error = reason
        self.after(0, self._refresh_dashboard)

    def _playit_auto_tunnel(self, secret_key=None, agent_id=None):
        """
        Vollautomatischer Tunnel-Flow:
          1. Secret Key sicherstellen
          2. Agent-Status prüfen via API
             a) Agent vorhanden aber offline → playit.exe neu starten → online bringen
             b) Kein Agent vorhanden → neuen Agent registrieren (Claim-Flow)
          3. Warten bis Agent online
          4. Tunnel-Liste prüfen
             a) Minecraft-Tunnel existiert → Adresse holen, fertig
             b) Limit erreicht → ältesten fremden Tunnel löschen
          5. Neuen Minecraft-Java Tunnel erstellen
          6. Adresse holen und im Dashboard anzeigen
        """
        import time as _t
        PLAYIT_API = "https://api.playit.gg"

        # ── Schritt 0: Secret Key ─────────────────────────────────────────
        if secret_key is None:
            secret_key = getattr(self, "_playit_secret_key", None)
        if not secret_key:
            srv_dir = Path(self.cfg.get("dir", ""))
            for p in [srv_dir / "playit.toml", APP_DIR / "playit_secret.txt"]:
                if p.exists():
                    secret_key = p.read_text(encoding="utf-8").strip()
                    if secret_key: break
        if not secret_key:
            self._append_log("[playit.gg] ✗ Kein Secret Key — bitte einmalig einloggen.\n")
            threading.Thread(target=self._auto_claim_flow,
                             args=(Path(self.cfg.get("dir","")),
                                   Path(self.cfg.get("dir",""))/"playit.toml",
                                   APP_DIR/"playit_secret.txt"),
                             daemon=True).start()
            return

        self._playit_secret_key = secret_key
        headers = {"Authorization": f"agent-key {secret_key}"}
        self._playit_limit_error = None
        self.after(0, self._refresh_dashboard)

        # ── Schritt 1: Agent-Status via API prüfen ────────────────────────
        self._append_log("[playit.gg] Auto-Tunnel 1/5: Agent wird geprüft…\n")
        try:
            r = requests.get(f"{PLAYIT_API}/account/agents",
                             headers=headers, timeout=10)
            resp = r.json()
            agents = []
            if resp.get("status") == "success":
                agents = resp.get("data", {}).get("agents", [])
                if not isinstance(agents, list):
                    agents = list(resp.get("data", {}).values()) if isinstance(resp.get("data"), dict) else []
        except Exception as e:
            self._append_log(f"[playit.gg] Agent-API nicht verfügbar ({e}) — starte lokal…\n")
            agents = []

        # Agent-Zustand analysieren
        online_agents  = [a for a in agents if a.get("online", False) or a.get("status") == "online"]
        offline_agents = [a for a in agents if not (a.get("online", False) or a.get("status") == "online")]

        if online_agents:
            # Agent bereits online
            agent_id = agent_id or online_agents[0].get("id") or online_agents[0].get("agent_id")
            self._playit_agent_id = agent_id
            self._append_log(f"[playit.gg] ✓ Agent online (ID: {str(agent_id)[:8]}…)\n")

        elif offline_agents:
            # Agent vorhanden aber offline → playit.exe starten um ihn online zu bringen
            agent_id = offline_agents[0].get("id") or offline_agents[0].get("agent_id")
            self._append_log(f"[playit.gg] Agent offline → starte playit.exe…\n")
            self._ensure_playit_running(secret_key)
            # Warten bis online (max 25s)
            for i in range(25):
                _t.sleep(1)
                if getattr(self, "_playit_connected", False):
                    agent_id = getattr(self, "_playit_agent_id", agent_id)
                    self._append_log(f"[playit.gg] ✓ Agent jetzt online!\n")
                    break
            else:
                self._append_log("[playit.gg] ✗ Agent konnte nicht online gebracht werden.\n")
                self._show_playit_limit_error("agent_deleted"); return

        else:
            # Kein Agent vorhanden → neuen erstellen via playit.exe starten
            self._append_log("[playit.gg] Kein Agent vorhanden → erstelle neuen Agent…\n")
            self._ensure_playit_running(secret_key)
            # Warten bis Agent sich registriert (max 30s)
            for i in range(30):
                _t.sleep(1)
                agent_id = getattr(self, "_playit_agent_id", None)
                if agent_id:
                    self._append_log(f"[playit.gg] ✓ Neuer Agent erstellt (ID: {agent_id[:8]}…)\n")
                    break
            else:
                self._append_log("[playit.gg] ✗ Agent-Erstellung fehlgeschlagen.\n")
                self._show_playit_limit_error("agent_deleted"); return

        if not agent_id:
            agent_id = getattr(self, "_playit_agent_id", None)
        if not agent_id:
            self._append_log("[playit.gg] ✗ Agent-ID unbekannt.\n")
            self._show_playit_limit_error("agent_deleted"); return

        self._append_log(f"[playit.gg] ✓ Agent bereit (ID: {str(agent_id)[:8]}…)\n")

        # ── Schritt 2: Tunnel auflisten ───────────────────────────────────
        self._append_log("[playit.gg] Auto-Tunnel 2/5: Tunnel werden aufgelistet…\n")
        try:
            r = requests.post(f"{PLAYIT_API}/tunnels/list",
                              json={"tunnel_id": None, "agent_id": None},
                              headers=headers, timeout=10)
            resp = r.json()
            if resp.get("status") == "success":
                all_tunnels = resp["data"].get("tunnels", [])
                tcp_alloc   = resp["data"].get("tcp_alloc", {})
            else:
                self._append_log(f"[playit.gg] ✗ Tunnel-Liste: {resp}\n")
                self._show_playit_limit_error("unknown"); return
        except Exception as e:
            self._append_log(f"[playit.gg] ✗ Tunnel-Liste Fehler: {e}\n")
            self._show_playit_limit_error("unknown"); return

        self._append_log(f"[playit.gg] ✓ {len(all_tunnels)} Tunnel gefunden\n")

        # ── Schritt 3: Tunnel für DIESEN Server suchen ───────────────────
        self._append_log("[playit.gg] Auto-Tunnel 3/5: Suche Tunnel für diesen Server…\n")
        srv_port    = int(self.cfg.get("port", 25565))
        saved_tid   = self.cfg.get("playit_tunnel_id", "")

        # Priorität: gespeicherte Tunnel-ID → passender Port → erster MC-Tunnel dieses Agents
        my_tunnel = None
        for t in all_tunnels:
            origin = t.get("origin", {}).get("data", {})
            if origin.get("agent_id") != agent_id: continue
            if t.get("tunnel_type") != "minecraft-java": continue
            if saved_tid and t.get("id") == saved_tid:
                my_tunnel = t; break          # exakter Treffer via gespeicherter ID
            if origin.get("local_port") == srv_port:
                my_tunnel = t                 # Port-Treffer (kein break, ID-Treffer bevorzugt)

        if my_tunnel:
            tid = my_tunnel.get("id", "")
            self._append_log(f"[playit.gg] ✓ Tunnel für diesen Server gefunden (Port {srv_port})\n")
            self.cfg["playit_tunnel_id"] = tid
            save_server_cfg(self.server_name, self.cfg)
            self._fetch_tunnel_address(secret_key, agent_id, None)
            return

        # ── Schritt 4: Limit prüfen → ältesten Tunnel löschen ────────────
        allowed = tcp_alloc.get("allowed", 4)
        claimed = tcp_alloc.get("claimed", len(all_tunnels))
        self._append_log(f"[playit.gg] Auto-Tunnel 4/5: Kapazität {claimed}/{allowed}\n")

        if claimed >= allowed and all_tunnels:
            non_own   = [t for t in all_tunnels
                         if t.get("origin", {}).get("data", {}).get("agent_id") != agent_id]
            to_delete = non_own[0] if non_own else all_tunnels[0]
            del_name  = to_delete.get("name") or to_delete.get("id","?")[:8]
            self._append_log(f"[playit.gg] Limit → lösche ältesten Tunnel '{del_name}'…\n")
            try:
                dr = requests.post(f"{PLAYIT_API}/tunnels/delete",
                                   json={"id": to_delete["id"]},
                                   headers=headers, timeout=10)
                if dr.json().get("status") == "success":
                    self._append_log(f"[playit.gg] ✓ Tunnel gelöscht\n")
                    _t.sleep(2)
                else:
                    self._append_log(f"[playit.gg] ✗ Löschen fehlgeschlagen\n")
                    self._show_playit_limit_error("tunnel_limit"); return
            except Exception as e:
                self._append_log(f"[playit.gg] ✗ Löschen-Fehler: {e}\n")
                self._show_playit_limit_error("tunnel_limit"); return

        # ── Schritt 5: Neuen Tunnel erstellen ────────────────────────────
        self._append_log("[playit.gg] Auto-Tunnel 5/5: Erstelle neuen Minecraft-Tunnel…\n")
        srv_name2 = self.cfg.get("name", self.server_name) or self.server_name
        body = {
            "tunnel_type": "minecraft-java",
            "port_type": "tcp",
            "port_count": 1,
            "name": srv_name2,
            "origin": {
                "type": "agent",
                "data": {
                    "agent_id": agent_id,
                    "local_ip": "127.0.0.1",
                    "local_port": int(self.cfg.get("port", 25565))
                }
            },
            "enabled": True
        }
        try:
            r = requests.post(f"{PLAYIT_API}/tunnels/create",
                              json=body, headers=headers, timeout=10)
            data = r.json()
            if data.get("status") == "success":
                tid = data["data"]["id"]
                self._append_log(f"[playit.gg] ✓ Tunnel erstellt (ID: {tid[:8]}…)\n")
                self.cfg["playit_tunnel_id"] = tid
                save_server_cfg(self.server_name, self.cfg)
                _t.sleep(3)
                self._fetch_tunnel_address(secret_key, agent_id, None)
            else:
                err_str = str(data).lower()
                self._append_log(f"[playit.gg] ✗ Tunnel-Fehler: {data}\n")
                if any(x in err_str for x in ("not_found","invalid_agent","deleted","agent_not")):
                    self._show_playit_limit_error("agent_deleted")
                else:
                    self._show_playit_limit_error("tunnel_limit")
        except Exception as e:
            self._append_log(f"[playit.gg] ✗ Fehler: {e}\n")
            self._show_playit_limit_error("unknown")

    def _ensure_playit_running(self, secret_key):
        """Stellt sicher dass playit.exe läuft — startet es falls nötig."""
        mgr = getattr(self, "_playit_mgr", None)
        already_running = (mgr is not None
                           and hasattr(mgr, "proc")
                           and mgr.proc is not None
                           and mgr.proc.poll() is None)
        if not already_running:
            srv_dir   = Path(self.cfg.get("dir", ""))
            toml_path = srv_dir / "playit.toml"
            if not toml_path.exists():
                toml_path.write_text(secret_key, encoding="utf-8")
            import threading as _th
            done = _th.Event()
            self.after(0, lambda: (self._launch_playit_with_secret(srv_dir, toml_path, secret_key), done.set()))
            done.wait(timeout=6)

    def _auto_create_tunnel(self, secret_key, agent_id):
        """Legacy-Wrapper."""
        self._playit_auto_tunnel(secret_key, agent_id)

    def _fetch_tunnel_address(self, secret_key, agent_id, on_address_cb=None):
        """Holt die öffentliche Tunnel-Adresse via API."""
        import time as _t
        PLAYIT_API = "https://api.playit.gg"
        headers = {"Authorization": f"agent-key {secret_key}"}
        for attempt in range(15):
            try:
                r = requests.post(f"{PLAYIT_API}/tunnels/list",
                                  json={"tunnel_id": None, "agent_id": agent_id},
                                  headers=headers, timeout=8)
                data = r.json()
                if data.get("status") == "success":
                    tunnels = data["data"].get("tunnels", [])
                    # Prüfe ob agent_over_limit gesetzt ist
                    for tunnel in tunnels:
                        if tunnel.get("agent_over_limit"):
                            self._append_log("[playit.gg] ⚠ Account-Limit erreicht (Free-Plan)\n")
                            self._show_playit_limit_error("over_limit")
                            return
                    for tunnel in tunnels:
                        alloc = tunnel.get("alloc", {})
                        if alloc.get("status") == "allocated":
                            ad = alloc["data"]
                            domain = ad.get("assigned_domain") or ad.get("ip_hostname")
                            port   = ad.get("port_start")
                            if domain and port:
                                addr = f"{domain}:{port}"
                                self.cfg["playit_address"] = addr
                                save_server_cfg(self.server_name, self.cfg)
                                self._playit_addr = addr
                                self._playit_limit_error = None
                                self._append_log(f"[playit.gg] ✓ Öffentliche Adresse: {addr}\n")
                                self.after(0, self._refresh_dashboard)
                                if on_address_cb:
                                    on_address_cb(addr)
                                return
                        elif alloc.get("status") == "pending":
                            self._append_log(f"[playit.gg] Warte auf Tunnel-Zuteilung…\n")
                elif data.get("status") == "error":
                    err = str(data.get("data","")).lower()
                    if "not_found" in err or "deleted" in err or "invalid" in err:
                        self._append_log("[playit.gg] ⚠ Agent nicht gefunden / gelöscht\n")
                        self._show_playit_limit_error("agent_deleted")
                        return
            except Exception as e:
                self._append_log(f"[playit.gg] API-Fehler: {e}\n")
            _t.sleep(3)

    def _refresh_dashboard(self):
        """Dashboard nur neu bauen wenn es wirklich nötig ist."""
        if getattr(self, "_active_page", "") != "dashboard":
            return
        # Debouncen: nicht öfter als alle 1,5s komplett neu bauen
        now = time.monotonic()
        last = getattr(self, "_last_dash_rebuild", 0)
        if now - last < 1.5:
            # Nur Sidebar-Dot leise aktualisieren
            state = getattr(self, "_server_state", "offline")
            dot_colors = {"offline": RED, "starting": "#f39c12", "online": GREEN, "error": "#8e0000"}
            try: self._srv_dot.configure(text_color=dot_colors.get(state, RED))
            except: pass
            return
        self._last_dash_rebuild = now
        try:
            self._p_dashboard()
        except Exception:
            pass

    def _stop(self):
        # Proc-Referenz sofort freigeben → GUI bleibt reaktionsfähig
        proc = self.proc
        self.proc = None

        # Tunnel-Flags sofort zurücksetzen (UI-Thread)
        self._playit_addr             = self.cfg.get("playit_address")
        self._playit_claim            = None
        self._playit_connected        = False
        self._playit_limit_error      = None
        self._tunnel_creation_running = False
        self._fetching_address        = False
        self._playit_launch_lock      = False
        self._log_buffer              = []
        self._online_count            = 0
        self._set_state("offline")
        # Alle Spieler beim Stop auf offline setzen (verhindert stale Daten)
        try:
            db = self._load_known_players()
            for name in db:
                db[name]["online"] = False
            self._save_known_players(db)
        except: pass

        # Eigentliches Stoppen + Kill in Hintergrund-Thread → kein UI-Freeze
        def _do_kill():
            if proc:
                try: proc.stdin.write("stop\n"); proc.stdin.flush()
                except: pass
                try: proc.wait(timeout=15)
                except: pass
                try: proc.kill()
                except: pass
            # Tunnel stoppen je nach Provider
            _prov = self.cfg.get("tunnel_provider", "mine_host")
            if _prov == "direct":
                self._stop_direct_tunnel()
            elif _prov == "mine_host":
                self._stop_custom_tunnel()
                self._stop_tunnel_connector()
            else:
                # playit stoppen — toml BLEIBT erhalten
                mgr = self._playit_mgr
                if mgr:
                    self._playit_mgr = None
                    try: mgr.stop()
                    except: pass
            # Auto-Backup nach dem Stoppen
            if self.cfg.get("auto_backup", False) and self.server_name:
                self.after(0, self._auto_backup_if_due)

        threading.Thread(target=_do_kill, daemon=True).start()

    def _start_extra_server(self, safe_name: str, cfg: dict):
        """Startet einen zusätzlichen Server parallel zum Hauptserver."""
        srv_dir = Path(cfg.get("dir",""))
        mc_ver  = cfg.get("mc_version","1.21")
        java    = find_java_exe(min_version=required_java_for_mc(mc_ver))
        if not java:
            messagebox.showerror("Fehler", f"Java nicht gefunden für {safe_name}"); return
        # Port-Konflikt vermeiden → anderen Port nutzen
        base_port = int(cfg.get("port", 25565))
        used_ports = {int(self.cfg.get("port",25565))}
        for es in self._extra_servers:
            used_ports.add(int(es.get("cfg",{}).get("port",25565)))
        port = base_port
        while port in used_ports: port += 1

        # Temporäre server.properties mit anderem Port
        import copy as _copy
        run_cfg = _copy.deepcopy(cfg)
        run_cfg["port"] = port
        props_path = srv_dir / "server.properties"
        if props_path.exists():
            lines = props_path.read_text(encoding="utf-8").splitlines()
            for i,l in enumerate(lines):
                if l.startswith("server-port="): lines[i]=f"server-port={port}"
            # In temp-Datei schreiben
            temp_props = srv_dir / f"server_extra_{port}.properties"
            temp_props.write_text("\n".join(lines)+"\n", encoding="utf-8")

        # Ressourcen aus Server-Config
        total_ram_mb    = psutil.virtual_memory().total // (1024 * 1024)
        total_log_cores = psutil.cpu_count(logical=True) or 4
        extra_ram_mb    = min(int(cfg.get("ram_mb", 2048)), int(total_ram_mb * 0.75))
        extra_ram_mb    = max(512, extra_ram_mb)
        extra_xms       = max(256, extra_ram_mb // 8)
        extra_cpu_cores = int(cfg.get("cpu_cores", max(2, total_log_cores // 4)))

        # Freie Kerne berechnen (Haupt-Server + andere Extra-Server)
        used_cores: set = set(getattr(self, "_my_cpu_cores", []))
        for es in self._extra_servers:
            used_cores.update(es.get("_cpu_cores_set", []))
        free_cores  = [c for c in range(total_log_cores) if c not in used_cores]
        my_cores    = free_cores[:extra_cpu_cores] or list(range(min(extra_cpu_cores, total_log_cores)))

        self._append_log(
            f"[Multi] '{cfg.get('name',safe_name)}': {extra_ram_mb}MB RAM, "
            f"Kerne {my_cores[0] if my_cores else '?'}-{my_cores[-1] if my_cores else '?'}\n")

        try:
            extra_proc = subprocess.Popen(
                [java,
                 f"-Xmx{extra_ram_mb}M", f"-Xms{extra_xms}M",
                 "--enable-native-access=ALL-UNNAMED",
                 "-Dfile.encoding=UTF-8",
                 "-XX:+UseG1GC", "-XX:MaxGCPauseMillis=200",
                 "-jar", "server.jar", "--nogui"],
                cwd=str(srv_dir), stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW)

            # CPU-Affinity setzen
            try:
                psutil.Process(extra_proc.pid).cpu_affinity(my_cores)
            except Exception: pass

            self._extra_servers.append({
                "name":          cfg.get("name", safe_name),
                "proc":          extra_proc,
                "cfg":           run_cfg,
                "port":          port,
                "_cpu_cores_set": my_cores,
            })
            self._append_log(f"[Multi] ✓ '{cfg.get('name',safe_name)}' auf Port {port} gestartet\n")
            # Tunnel-Connector für Extra-Server starten (minehost-local.uk)
            if run_cfg.get("tunnel_provider","playit") == "mine_host":
                self.after(500, lambda n=safe_name, c=run_cfg:
                           self._start_tunnel_connector(server_name=n, cfg=c))
            self._refresh_dashboard()
        except Exception as e:
            messagebox.showerror("Fehler", f"Konnte {safe_name} nicht starten:\n{e}")

    def _is_live_server(self) -> bool:
        """True wenn der angezeigte Server auch der laufende ist."""
        return (self.server_name == self._running_server_name
                and self.proc is not None
                and self.proc.poll() is None)

    def _get_active_proc(self):
        """Gibt den Prozess des angezeigten Servers zurück (egal ob Haupt oder Extra)."""
        # Ist der angezeigte Server der Haupt-Server?
        if self._is_live_server():
            return self.proc
        # Sonst in extra_servers suchen
        for es in self._extra_servers:
            if es.get("name") == self.cfg.get("name","") or es.get("cfg",{}).get("name","") == self.cfg.get("name",""):
                p = es.get("proc")
                if p and p.poll() is None:
                    return p
        return None

    def _get_display_srv_dir(self) -> "Path":
        """Gibt den Server-Ordner des angezeigten Servers zurück."""
        return Path(self.cfg.get("dir",""))

    def _auto_backup_if_due(self):
        """Erstellt ein Auto-Backup falls das letzte älter als min_hours ist."""
        min_hours = int(self.cfg.get("auto_backup_min_hours", 24))
        max_count = int(self.cfg.get("auto_backup_max", 5))
        bkp_dir   = APP_DIR / "backups"
        bkp_dir.mkdir(exist_ok=True)
        # Letztes Backup prüfen
        existing = sorted(bkp_dir.glob(f"{self.server_name}_*.zip"), reverse=True)
        if existing:
            try:
                mtime = existing[0].stat().st_mtime
                if (time.time() - mtime) < min_hours * 3600:
                    return  # Zu frisch
            except: pass
        # Backup erstellen
        ts   = time.strftime("%Y%m%d_%H%M%S")
        fname = f"{self.server_name}_{ts}"
        def _run():
            try:
                shutil.make_archive(str(bkp_dir/fname), "zip",
                                    str(Path(self.cfg.get("dir",""))))
                # Älteste löschen wenn zu viele
                all_bkps = sorted(bkp_dir.glob(f"{self.server_name}_*.zip"))
                while len(all_bkps) > max_count:
                    all_bkps[0].unlink()
                    all_bkps = all_bkps[1:]
                self._append_log(f"[Backup] ✓ Auto-Backup erstellt: {fname}.zip\n")
            except Exception as e:
                self._append_log(f"[Backup] ✗ Fehler: {e}\n")
        threading.Thread(target=_run, daemon=True).start()

    # ── Spieler-Tracking ──────────────────────────────────────────────────────
    def _player_joined(self, name: str):
        """Spieler hat gejoint → in bekannte Spieler speichern + UI aktualisieren."""
        if not self.server_name: return
        db = self._load_known_players()
        if name not in db:
            db[name] = {"name": name, "first_seen": time.strftime("%Y-%m-%d %H:%M")}
        db[name]["last_seen"] = time.strftime("%Y-%m-%d %H:%M")
        db[name]["online"] = True
        self._save_known_players(db)
        if getattr(self, "_active_page", "") == "players":
            self.after(0, self._p_players)

    def _player_left(self, name: str):
        """Spieler hat den Server verlassen."""
        if not self.server_name: return
        db = self._load_known_players()
        if name in db:
            db[name]["online"] = False
            db[name]["last_seen"] = time.strftime("%Y-%m-%d %H:%M")
            self._save_known_players(db)
        if getattr(self, "_active_page", "") == "players":
            self.after(0, self._p_players)

    def _known_players_file(self):
        return APP_DIR / "servers" / f"{self.server_name}_players.json"

    def _load_known_players(self) -> dict:
        f = self._known_players_file()
        if f.exists():
            try: return json.loads(f.read_text(encoding="utf-8"))
            except: pass
        return {}

    def _save_known_players(self, db: dict):
        f = self._known_players_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")

    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    # PAGE: LOBBY  (Wartelobby — läuft immer beim PC-Start)
    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    def _p_lobby(self):
        self._clear()
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        LOBBY_DIR  = APP_DIR / "lobbies"
        LOBBY_DIR.mkdir(exist_ok=True)
        LOBBY_CFG  = APP_DIR / "lobby_config.json"
        MAX_LOBBIES = 5
        CPU_TOTAL   = 10   # % gesamt

        def _load_cfg():
            if LOBBY_CFG.exists():
                try: return json.loads(LOBBY_CFG.read_text(encoding="utf-8"))
                except: pass
            return {"lobbies": []}

        def _save_cfg(d):
            LOBBY_CFG.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")

        cfg = _load_cfg()
        lobbies = cfg.get("lobbies", [])

        outer = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        outer.grid(row=0, column=0, sticky="nsew")

        # ── Header ────────────────────────────────────────────────────────────
        hdr = ctk.CTkFrame(outer, fg_color="transparent")
        hdr.pack(fill="x", padx=20, pady=(16,8))
        hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(hdr, text="⚡  Wartelobby",
                     font=ctk.CTkFont("Segoe UI",20,"bold"), text_color=GREEN
                     ).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr,
            text=f"Läuft immer beim PC-Start • Max {MAX_LOBBIES} Lobbys • "
                 f"Gesamt max {CPU_TOTAL}% CPU • Jede Lobby bekommt {CPU_TOTAL // max(1,len(lobbies))}%",
            font=ctk.CTkFont("Segoe UI",10), text_color=TEXT_MUTED
            ).grid(row=1, column=0, sticky="w")

        # ── Status: Läuft die Lobby gerade? ──────────────────────────────────
        def _is_lobby_running(port):
            for p in psutil.process_iter(["cmdline"]):
                try:
                    cmd = " ".join(p.info.get("cmdline") or [])
                    if "java" in cmd.lower() and f"-Dlobby_port={port}" in cmd:
                        return True
                except: pass
            return False

        # ── Lobby-Karten ──────────────────────────────────────────────────────
        for i, lobby in enumerate(lobbies):
            port     = lobby.get("port", 25600 + i)
            name     = lobby.get("name", f"Lobby {i+1}")
            running  = _is_lobby_running(port)
            cpu_each = CPU_TOTAL // max(1, len(lobbies))

            card = ctk.CTkFrame(outer, fg_color=SIDEBAR_BG, corner_radius=10)
            card.pack(fill="x", padx=20, pady=4)
            card.grid_columnconfigure(1, weight=1)

            # Status-Dot
            dot_col = "#22c55e" if running else "#555"
            ctk.CTkLabel(card, text="●", text_color=dot_col,
                         font=ctk.CTkFont("Segoe UI",14)
                         ).grid(row=0, column=0, padx=(12,4), pady=10)

            # Info
            info = ctk.CTkFrame(card, fg_color="transparent")
            info.grid(row=0, column=1, sticky="w", pady=10)
            ctk.CTkLabel(info, text=name, font=ctk.CTkFont("Segoe UI",13,"bold"),
                         text_color=TEXT, anchor="w").pack(anchor="w")
            ctk.CTkLabel(info,
                text=f"Port {port}  •  CPU ≤ {cpu_each}%  •  RAM ≤ 512MB  •  "
                     + ("🟢 Läuft" if running else "⚫ Gestoppt"),
                font=ctk.CTkFont("Segoe UI",10), text_color=TEXT_MUTED, anchor="w"
                ).pack(anchor="w")

            # Buttons
            btn_f = ctk.CTkFrame(card, fg_color="transparent")
            btn_f.grid(row=0, column=2, padx=8)

            def _start_lobby(lb=lobby, idx=i):
                threading.Thread(target=lambda: self._lobby_start(lb, idx, len(lobbies), CPU_TOTAL),
                                 daemon=True).start()
                self.after(2000, self._p_lobby)

            def _stop_lobby(p=port):
                for proc in psutil.process_iter(["cmdline","pid"]):
                    try:
                        cmd = " ".join(proc.info.get("cmdline") or [])
                        if "java" in cmd.lower() and f"-Dlobby_port={p}" in cmd:
                            proc.kill()
                    except: pass
                self.after(500, self._p_lobby)

            def _del_lobby(idx=i):
                if messagebox.askyesno("Löschen", f"Lobby '{name}' löschen?"):
                    lobbies.pop(idx)
                    cfg["lobbies"] = lobbies
                    _save_cfg(cfg)
                    self._p_lobby()

            if not running:
                ctk.CTkButton(btn_f, text="▶ Starten", width=90, height=30,
                              fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                              font=ctk.CTkFont("Segoe UI",11,"bold"), corner_radius=6,
                              command=_start_lobby).pack(pady=2)
            else:
                ctk.CTkButton(btn_f, text="??? Stoppen", width=90, height=30,
                              fg_color=RED, hover_color=RED_HOV, text_color="#fff",
                              font=ctk.CTkFont("Segoe UI",11,"bold"), corner_radius=6,
                              command=_stop_lobby).pack(pady=2)

            # Welt hochladen
            def _upload_world(lb=lobby, ld=LOBBY_DIR / name):
                p = filedialog.askdirectory(title="Lobby-Welt wählen (Minecraft-Welt-Ordner)")
                if not p: return
                ld.mkdir(parents=True, exist_ok=True)
                world_dst = ld / "world"
                if world_dst.exists(): shutil.rmtree(str(world_dst))
                shutil.copytree(p, str(world_dst))
                messagebox.showinfo("✓", f"Welt in '{name}' hochgeladen!")

            ctk.CTkButton(btn_f, text="?? Welt", width=90, height=28,
                          fg_color=BLUE, text_color="#fff",
                          font=ctk.CTkFont("Segoe UI",10), corner_radius=6,
                          command=_upload_world).pack(pady=2)
            ctk.CTkButton(btn_f, text="🗑", width=32, height=28,
                          fg_color="#3a1010", text_color=RED, corner_radius=6,
                          command=_del_lobby).pack(pady=2)

        # ── Neue Lobby hinzufügen ─────────────────────────────────────────────
        if len(lobbies) < MAX_LOBBIES:
            add_f = ctk.CTkFrame(outer, fg_color=CARD, corner_radius=10)
            add_f.pack(fill="x", padx=20, pady=8)
            add_f.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(add_f, text=f"Neue Lobby ({len(lobbies)}/{MAX_LOBBIES})",
                         font=ctk.CTkFont("Segoe UI",12,"bold"), text_color=TEXT_MUTED
                         ).grid(row=0, column=0, padx=14, pady=(10,4), sticky="w")
            name_entry = ctk.CTkEntry(add_f, placeholder_text="Lobby-Name…",
                                      fg_color=SIDEBAR_BG, text_color=TEXT, height=32)
            name_entry.grid(row=1, column=0, padx=14, pady=(0,4), sticky="ew")
            def _add_lobby():
                n = name_entry.get().strip() or f"Lobby {len(lobbies)+1}"
                port = 25600 + len(lobbies)
                lobbies.append({"name": n, "port": port, "mc_version": "1.21.11"})
                cfg["lobbies"] = lobbies
                _save_cfg(cfg)
                self._lobby_setup(lobbies[-1], LOBBY_DIR / n)
                self._p_lobby()
            ctk.CTkButton(add_f, text="＋ Lobby erstellen", height=36,
                          fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                          font=ctk.CTkFont("Segoe UI",12,"bold"), corner_radius=8,
                          command=_add_lobby).grid(row=2, column=0, padx=14, pady=(0,14), sticky="ew")
        else:
            ctk.CTkLabel(outer,
                text=f"Maximum erreicht ({MAX_LOBBIES} Lobbys)",
                font=ctk.CTkFont("Segoe UI",11), text_color=TEXT_MUTED
                ).pack(pady=8)

        # ── Auto-Start Einstellung ────────────────────────────────────────────
        autostart_f = ctk.CTkFrame(outer, fg_color=SIDEBAR_BG, corner_radius=10)
        autostart_f.pack(fill="x", padx=20, pady=(8,4))
        autostart_f.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(autostart_f, text="🔄  Beim PC-Start automatisch starten",
                     font=ctk.CTkFont("Segoe UI",12,"bold"), text_color=TEXT
                     ).grid(row=0, column=0, padx=14, pady=(10,2), sticky="w")
        ctk.CTkLabel(autostart_f,
            text="Lobbys starten automatisch beim Windows-Boot, auch ohne die App zu öffnen.",
            font=ctk.CTkFont("Segoe UI",10), text_color=TEXT_MUTED
            ).grid(row=1, column=0, padx=14, sticky="w")
        autostart_en = ctk.BooleanVar(value=self._lobby_autostart_enabled())
        def _toggle_autostart():
            if autostart_en.get():
                self._lobby_register_autostart(lobbies)
                messagebox.showinfo("✓", "Auto-Start aktiviert!\nLobbys starten beim nächsten PC-Boot.")
            else:
                self._lobby_unregister_autostart()
        ctk.CTkSwitch(autostart_f, variable=autostart_en, text="",
                      progress_color=GREEN, command=_toggle_autostart
                      ).grid(row=0, column=1, padx=14, rowspan=2)
        ctk.CTkFrame(autostart_f, fg_color="transparent", height=10).grid(row=2, column=0)

    def _lobby_setup(self, lobby: dict, lobby_dir: Path):
        """Erstellt Server-Ordner + server.properties + eula.txt für eine Lobby."""
        lobby_dir.mkdir(parents=True, exist_ok=True)
        port = lobby.get("port", 25600)
        mc_ver = lobby.get("mc_version","1.21.11")

        # server.properties für Lobby (minimale Einstellungen)
        props = (
            f"server-port={port}\n"
            "max-players=50\n"
            "motd=§aWartelobby — Server startet gleich!\n"
            "online-mode=true\n"
            "difficulty=peaceful\n"
            "gamemode=adventure\n"
            "pvp=false\n"
            "spawn-protection=0\n"
            "view-distance=6\n"
            "simulation-distance=4\n"
            "max-tick-time=-1\n"
            "pause-when-empty-seconds=-1\n"
            "enable-command-block=false\n"
        )
        (lobby_dir / "server.properties").write_text(props, encoding="utf-8")
        (lobby_dir / "eula.txt").write_text("eula=true\n", encoding="utf-8")

        # JAR herunterladen wenn nicht vorhanden
        jar = lobby_dir / "server.jar"
        if not jar.exists():
            self._append_log(f"[Lobby] Lade Paper {mc_ver} für Lobby herunter…\n")
            try:
                r = requests.get(f"https://api.papermc.io/v2/projects/paper/versions/{mc_ver}/builds",
                                 timeout=10)
                builds = r.json().get("builds",[])
                if builds:
                    b = builds[-1]
                    fname = b["downloads"]["application"]["name"]
                    url = f"https://api.papermc.io/v2/projects/paper/versions/{mc_ver}/builds/{b['build']}/downloads/{fname}"
                    r2 = requests.get(url, stream=True, timeout=120)
                    with open(str(jar), "wb") as fh:
                        for chunk in r2.iter_content(8192): fh.write(chunk)
                    self._append_log(f"[Lobby] ✓ Paper {mc_ver} heruntergeladen\n")
            except Exception as e:
                self._append_log(f"[Lobby] ✗ JAR-Download fehlgeschlagen: {e}\n")

    def _lobby_start(self, lobby: dict, idx: int, total: int, cpu_total: int):
        """Startet eine Lobby mit Ressourcen-Limitierung."""
        port    = lobby.get("port", 25600 + idx)
        name    = lobby.get("name", f"Lobby {idx+1}")
        mc_ver  = lobby.get("mc_version", "1.21.11")
        lb_dir  = APP_DIR / "lobbies" / name

        self._lobby_setup(lobby, lb_dir)

        java = find_java_exe(min_version=required_java_for_mc(mc_ver))
        if not java:
            self._append_log(f"[Lobby] ✗ Java nicht gefunden\n"); return

        # RAM: 512MB pro Lobby, CPU: anteilig limitiert
        ram_mb  = 512
        # CPU-Kerne anteilig (mindestens 1)
        cpu_pct = cpu_total // max(1, total)
        cores   = max(1, round(psutil.cpu_count(logical=True) * cpu_pct / 100))

        jvm_args = [
            java,
            f"-Xmx{ram_mb}M", f"-Xms128M",
            f"-XX:ActiveProcessorCount={cores}",   # CPU-Limitierung
            f"-Dlobby_port={port}",                # Marker für Prozess-Erkennung
            "--enable-native-access=ALL-UNNAMED",
            "-Dfile.encoding=UTF-8",
            "-XX:+IgnoreUnrecognizedVMOptions",
            "-jar", "server.jar", "--nogui",
        ]
        self._append_log(f"[Lobby] Starte '{name}' auf Port {port} ({cpu_pct}% CPU, {ram_mb}MB RAM)…\n")
        try:
            subprocess.Popen(jvm_args, cwd=str(lb_dir),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             stdin=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
            self._append_log(f"[Lobby] ✓ '{name}' gestartet\n")
        except Exception as e:
            self._append_log(f"[Lobby] ✗ Start fehlgeschlagen: {e}\n")

    def _lobby_autostart_enabled(self) -> bool:
        """Prüft ob Auto-Start im Task Scheduler registriert ist."""
        try:
            r = subprocess.run(
                ["schtasks", "/query", "/tn", "MineHostLocalLobbies"],
                capture_output=True, text=True, creationflags=CREATE_NO_WINDOW)
            return r.returncode == 0
        except: return False

    def _lobby_register_autostart(self, lobbies: list):
        """Registriert Lobbys im Windows Task Scheduler (startet beim Boot ohne Login)."""
        # Startup-Skript erstellen
        script_path = APP_DIR / "lobby_autostart.bat"
        java_exe    = find_java_exe(min_version=21) or "java"
        lines = ["@echo off", "echo MineHost Lobbies starting...", ""]
        for i, lb in enumerate(lobbies):
            name   = lb.get("name", f"Lobby {i+1}")
            port   = lb.get("port", 25600 + i)
            mc_ver = lb.get("mc_version","1.21.11")
            lb_dir = APP_DIR / "lobbies" / name
            ram    = 512
            cores  = max(1, psutil.cpu_count(logical=True) // max(1, len(lobbies)))
            lines.append(
                f'start "Lobby_{name}" /min "{java_exe}" '
                f'-Xmx{ram}M -Xms128M '
                f'-XX:ActiveProcessorCount={cores} '
                f'-Dlobby_port={port} '
                f'--enable-native-access=ALL-UNNAMED '
                f'-jar "{lb_dir}\\server.jar" --nogui'
            )
        script_path.write_text("\n".join(lines), encoding="utf-8")

        # Task Scheduler Eintrag
        try:
            subprocess.run([
                "schtasks", "/create", "/f",
                "/tn", "MineHostLocalLobbies",
                "/tr", str(script_path),
                "/sc", "ONSTART",
                "/ru", "SYSTEM",
                "/rl", "HIGHEST",
            ], check=True, capture_output=True, creationflags=CREATE_NO_WINDOW)
        except Exception:
            # Admin-Rechte nötig → neu starten fragen
            ans = messagebox.askyesno(
                "Administrator-Rechte benötigt",
                "Für den PC-Start-Autostart werden Administrator-Rechte benötigt.\n\n"
                "App jetzt als Administrator neu starten?")
            if ans:
                import ctypes, sys
                ctypes.windll.shell32.ShellExecuteW(
                    None, "runas",
                    sys.executable,
                    "", None, 1)
                self.destroy()

    def _lobby_unregister_autostart(self):
        """Entfernt den Auto-Start aus dem Task Scheduler."""
        try:
            subprocess.run(
                ["schtasks", "/delete", "/f", "/tn", "MineHostLocalLobbies"],
                check=True, capture_output=True, creationflags=CREATE_NO_WINDOW)
        except: pass

    def _open_minecraft_version(self, mc_ver: str):
        """Öffnet den Minecraft Launcher mit dem passenden Profil für mc_ver."""
        import json as _json, uuid as _uuid, webbrowser as _wb
        mc_dir = Path(os.environ.get("APPDATA","")) / ".minecraft"
        profiles_path = mc_dir / "launcher_profiles.json"

        # Launcher-Pfade suchen
        launcher_paths = [
            Path(os.environ.get("LOCALAPPDATA","")) / "Programs" / "Minecraft Launcher" / "MinecraftLauncher.exe",
            Path(os.environ.get("LOCALAPPDATA","")) / "Programs" / "Minecraft" / "MinecraftLauncher.exe",
            Path("C:/Program Files/Minecraft Launcher/MinecraftLauncher.exe"),
            Path("C:/Program Files (x86)/Minecraft Launcher/MinecraftLauncher.exe"),
        ]
        launcher_exe = next((p for p in launcher_paths if p.exists()), None)

        # Profil in launcher_profiles.json anlegen
        profile_id   = f"MineHostLocal_{mc_ver.replace('.','_')}"
        profile_name = f"MineHost {mc_ver}"

        if profiles_path.exists():
            try:
                data = _json.loads(profiles_path.read_text(encoding="utf-8"))
                profiles = data.get("profiles", {})

                # Profil erstellen/updaten
                profiles[profile_id] = {
                    "name":        profile_name,
                    "type":        "custom",
                    "lastVersionId": mc_ver,
                    "icon":        "Grass",
                    "created":     "2026-01-01T00:00:00.000Z",
                    "lastUsed":    "2026-01-01T00:00:00.000Z",
                }
                # Als zuletzt genutztes Profil setzen
                data["profiles"] = profiles
                data["selectedProfile"] = profile_id
                data["settings"] = data.get("settings", {})
                profiles_path.write_text(
                    _json.dumps(data, indent=2, ensure_ascii=False),
                    encoding="utf-8")
                self._append_log(f"[MineHost] ✓ Launcher-Profil '{profile_name}' erstellt/aktualisiert\n")
            except Exception as e:
                self._append_log(f"[MineHost] ⚠ Profil-Fehler: {e}\n")

        # Launcher starten
        if launcher_exe:
            try:
                subprocess.Popen([str(launcher_exe)], creationflags=CREATE_NO_WINDOW)
                self._append_log(f"[MineHost] ✓ Minecraft Launcher geöffnet ({mc_ver})\n")
            except Exception as e:
                self._append_log(f"[MineHost] Launcher-Fehler: {e} — öffne Website\n")
                _wb.open("https://www.minecraft.net/de-de/download")
        else:
            # Fallback: minecraft:// Protokoll versuchen
            try:
                os.startfile(f"minecraft://")
                self._append_log(f"[MineHost] ✓ Minecraft via Protokoll geöffnet\n")
            except:
                _wb.open("https://www.minecraft.net/de-de/download")
                self._append_log(f"[MineHost] Minecraft nicht gefunden → Download-Seite geöffnet\n")

    def _show_error(self):
        log = "\n".join(getattr(self, "_error_log", [])[-40:]) or "Keine Details verfügbar."
        win = ctk.CTkToplevel(self)
        win.title("Fehler-Details")
        win.geometry("640x420")
        win.configure(fg_color=BG)
        win.grab_set()
        ctk.CTkLabel(win, text="✖  Server-Fehler", font=ctk.CTkFont("Segoe UI",16,"bold"),
                     text_color=RED).pack(padx=20, pady=(16,8), anchor="w")
        box = ctk.CTkTextbox(win, fg_color=CARD, text_color="#ff8a80",
                              font=ctk.CTkFont("Consolas",11))
        box.pack(fill="both", expand=True, padx=20, pady=(0,8))
        box.insert("end", log)
        box.configure(state="disabled")
        ctk.CTkButton(win, text="Schließen", fg_color=CARD, text_color=TEXT,
                      command=win.destroy).pack(pady=(0,16))

    def _read_log(self):
        if not hasattr(self, "_error_log"):  self._error_log  = []
        if not hasattr(self, "_log_buffer"): self._log_buffer = []
        for line in self.proc.stdout:
            self._error_log.append(line)
            self._log_buffer.append(line)
            if len(self._error_log)  > 500: self._error_log  = self._error_log[-500:]
            if len(self._log_buffer) > 2000: self._log_buffer = self._log_buffer[-2000:]
            self._append_log(line)
            if "Done" in line and "For help" in line:
                self.after(0, lambda: self._set_state("online"))
            # Port bereits belegt → klare Fehlermeldung setzen
            if "BindException" in line or "Address already in use" in line:
                port = self.cfg.get("port", 25565)
                self._error_log = [
                    f"Port {port} ist bereits belegt!\n\n"
                    f"Ein anderer Minecraft-Server oder Prozess nutzt diesen Port.\n"
                    f"Lösung: Anderen Server stoppen, oder in Optionen einen anderen Port wählen."
                ] + self._error_log
                self.after(0, lambda: self._set_state("error"))
            if "joined the game" in line:
                self._online_count = getattr(self, "_online_count", 0) + 1
                import re as _re2
                m = _re2.search(r":\s+(\w+)\s+joined the game", line)
                if m:
                    self._player_joined(m.group(1))
            elif "left the game" in line:
                self._online_count = max(0, getattr(self, "_online_count", 1) - 1)
                import re as _re2
                m = _re2.search(r":\s+(\w+)\s+left the game", line)
                if m:
                    self._player_left(m.group(1))
            # Altes world/players Verzeichnis → automatisch löschen und neu starten
            if ("DETECTED OLD PLAYER DIRECTORY" in line or
                    "remove the directory" in line and "players" in line):
                if not getattr(self, "_players_dir_fix_tried", False):
                    self._players_dir_fix_tried = True
                    def _fix_players_dir():
                        srv_dir = Path(self.cfg.get("dir",""))
                        players_dir = srv_dir / "world" / "players"
                        if players_dir.exists():
                            try:
                                shutil.rmtree(str(players_dir))
                                self._append_log("[MineHost] ✓ world/players/ gelöscht — starte neu…\n")
                                self._stop()
                                self.after(1500, self._start)
                            except Exception as e:
                                self._append_log(f"[MineHost] ✗ Konnte world/players nicht löschen: {e}\n")
                    self.after(0, _fix_players_dir)

            # Welt-Einstellungen korrupt → automatisch reparieren
            if ("world_gen_settings" in line or "Overworld settings missing" in line
                    or "Failed to load datapacks" in line):
                if not getattr(self, "_world_gen_fix_tried", False):
                    self._world_gen_fix_tried = True
                    def _fix_world_gen():
                        srv_dir = Path(self.cfg.get("dir",""))
                        deleted = []
                        # 1. world/data/minecraft/ komplett löschen
                        mc_data = srv_dir / "world" / "data" / "minecraft"
                        if mc_data.exists():
                            try: shutil.rmtree(str(mc_data)); deleted.append("world/data/minecraft/")
                            except: pass
                        # 2. world/data/ komplett löschen
                        world_data = srv_dir / "world" / "data"
                        if world_data.exists():
                            try: shutil.rmtree(str(world_data)); deleted.append("world/data/")
                            except: pass
                        # 3. level.dat löschen (wird neu generiert, Chunks bleiben)
                        level_dat = srv_dir / "world" / "level.dat"
                        level_bak = srv_dir / "world" / "level.dat_old"
                        for lf in [level_dat, level_bak]:
                            if lf.exists():
                                try: lf.unlink(); deleted.append(lf.name)
                                except: pass
                        msg = ("Welt-Einstellungen beschädigt — automatische Reparatur:\n\n"
                               f"Gelöscht: {', '.join(deleted) or 'world/data/'}\n\n"
                               "✅ Bleibt erhalten: Chunks (world/region/), Spielerdaten\n"
                               "⚠??  Welt wird neu initialisiert — Server startet neu.")
                        if messagebox.askyesno("Welt reparieren", msg):
                            self._stop()
                            # KEIN safeMode — world/data wurde bereits gelöscht
                            self.after(1500, self._start)
                        else:
                            self._stop()
                    self.after(0, _fix_world_gen)

            # Java zu alt erkannt → automatisch richtige Version installieren
            if "UnsupportedClassVersionError" in line or "class file version" in line:
                import re as _re
                m = _re.search(r"class file version (\d+)", line)
                need = 8
                if m:
                    cf = int(m.group(1))
                    need = cf - 44   # class file version = java_ver + 44
                mc_ver = self.cfg.get("mc_version","")
                need = max(need, required_java_for_mc(mc_ver))
                def _upgrade(n=need):
                    if messagebox.askyesno("Java zu alt",
                        f"Der Server braucht Java {n}+.\nJetzt automatisch installieren und Server neu starten?"):
                        self._stop()
                        install_java_background(
                            on_done=lambda: self.after(1000, self._start),
                            on_error=lambda e: messagebox.showerror("Fehler",f"Java {n} Installation:\n{e}"),
                            version=n)
                self.after(0, _upgrade)

    def _log_tag(self, line):
        u = line.upper()
        if "ERROR" in u or "EXCEPTION" in u or "FAILED" in u or "FATAL" in u:
            return "error"
        if "WARN" in u:
            return "warn"
        if "DONE" in u and "FOR HELP" in u:
            return "done"
        return "info"

    def _append_log(self, text):
        if hasattr(self, "_log_box"):
            try:
                self._log_box.configure(state="normal")
                self._log_box.insert("end", text, self._log_tag(text))
                self._log_box.see("end")
                self._log_box.configure(state="disabled")
            except: pass

    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    # PAGE: KONSOLE
    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    def _p_console(self):
        self._console_page(log_only=False)

    def _p_log(self):
        self._console_page(log_only=True)

    def _console_page(self, log_only):
        self.content.grid_rowconfigure(1, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        # ── Server-ID-Prüfung: Zeige welcher Server-Log angezeigt wird ─────────
        is_live = self._is_live_server()
        run_name = self._running_server_name
        show_name = self.cfg.get("name", self.server_name)

        title = "Log" if log_only else "Konsole"
        if not is_live and run_name and run_name != self.server_name:
            title += f"  [{show_name}]"

        hdr = self._page_header(title)

        # Info-Banner wenn angezeigter ≠ laufender Server
        if not is_live and run_name:
            banner_col = "#1a1a2a" if not is_live else "transparent"
            banner = ctk.CTkFrame(self.content, fg_color=banner_col, corner_radius=6, height=28)
            banner.grid(row=1, column=0, sticky="ew", padx=20, pady=(0,4))
            banner.grid_propagate(False)
            ctk.CTkLabel(banner,
                text=f"ℹ??  Log von '{show_name}' — dieser Server läuft nicht gerade.",
                font=ctk.CTkFont("Segoe UI",10), text_color=TEXT_MUTED
                ).pack(padx=10, pady=4, anchor="w")
            self.content.grid_rowconfigure(1, minsize=32)
            self.content.grid_rowconfigure(2, weight=1)
            log_row = 2
        else:
            log_row = 1

        # tk.Text für farbiges Log
        self._log_box = tk.Text(self.content, bg="#21263a", fg="#a5d6a7",
                                 font=("Consolas",11), state="disabled",
                                 relief="flat", bd=0, insertbackground="#a5d6a7",
                                 selectbackground="#2979ff", wrap="none")
        self._log_box.grid(row=log_row, column=0, sticky="nsew", padx=20, pady=(0,8))
        self._log_box.tag_config("error", foreground="#ff5252")
        self._log_box.tag_config("warn",  foreground="#ffd600")
        self._log_box.tag_config("info",  foreground="#a5d6a7")
        self._log_box.tag_config("done",  foreground="#00e676")
        sb = tk.Scrollbar(self.content, command=self._log_box.yview, bg="#1a1d24")
        self._log_box.configure(yscrollcommand=sb.set)
        sb.grid(row=log_row, column=1, sticky="ns", pady=(0,8))

        # Log-Inhalt laden:
        # - Live-Server → aus _log_buffer (RAM)
        # - Anderer Server → aus Datei logs/latest.log
        if is_live and hasattr(self, "_log_buffer") and self._log_buffer:
            self._log_box.configure(state="normal")
            for line in self._log_buffer:
                self._log_box.insert("end", line, self._log_tag(line))
            self._log_box.see("end")
            self._log_box.configure(state="disabled")
        elif not is_live:
            # Aus Datei laden
            log_file = self._get_display_srv_dir() / "logs" / "latest.log"
            if log_file.exists():
                try:
                    content = log_file.read_text(encoding="utf-8", errors="replace")
                    self._log_box.configure(state="normal")
                    for line in content.splitlines(keepends=True)[-500:]:  # letzte 500 Zeilen
                        self._log_box.insert("end", line, self._log_tag(line))
                    self._log_box.see("end")
                    self._log_box.configure(state="disabled")
                except: pass
            else:
                self._log_box.configure(state="normal")
                self._log_box.insert("end", f"[Kein Log vorhanden für '{show_name}']\n", "warn")
                self._log_box.configure(state="disabled")

        if not log_only:
            cmd_row = log_row + 1
            inp = ctk.CTkFrame(self.content, fg_color="transparent")
            inp.grid(row=cmd_row, column=0, sticky="ew", padx=20, pady=(0,16))
            inp.grid_columnconfigure(0, weight=1)
            self._cmd_e = ctk.CTkEntry(inp, placeholder_text="Befehl eingeben…",
                                        fg_color=CARD, border_color=BORDER, text_color=TEXT,
                                        font=ctk.CTkFont("Consolas",12),
                                        state="normal" if is_live else "disabled")
            self._cmd_e.grid(row=0,column=0,sticky="ew",padx=(0,8))
            self._cmd_e.bind("<Return>", lambda _: self._send())
            ctk.CTkButton(inp,text="Senden",fg_color=GREEN if is_live else "#555",
                          hover_color=GREEN_HOV,text_color="#000" if is_live else "#888",
                          width=90,state="normal" if is_live else "disabled",
                          command=self._send).grid(row=0,column=1)

    def _send(self):
        if not hasattr(self,"_cmd_e"): return
        cmd = self._cmd_e.get().strip()
        if not cmd: return
        # Richtigen Prozess finden (angezeigter Server)
        target_proc = self._get_active_proc() or self.proc
        if target_proc and target_proc.poll() is None:
            try:
                target_proc.stdin.write(cmd+"\n"); target_proc.stdin.flush()
                self._append_log(f"> {cmd}\n")
            except Exception as e:
                self._append_log(f"[Fehler] {e}\n")
        else:
            self._append_log("[Server ist nicht gestartet]\n")
        self._cmd_e.delete(0,"end")

    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    # PAGE: OPTIONEN
    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    def _p_options(self):
        self._page_header("Optionen")
        if not self.server_name:
            ctk.CTkLabel(self.content, text="Kein Server.", text_color=TEXT_MUTED).grid(row=1,column=0); return

        self.content.grid_rowconfigure(1, weight=1)
        cfg = self.cfg
        srv_dir = Path(cfg.get("dir",""))
        props_file = srv_dir/"server.properties"

        def read_props():
            d={}
            if props_file.exists():
                for line in props_file.read_text(encoding="utf-8").splitlines():
                    if "=" in line and not line.startswith("#"):
                        k,_,v = line.partition("=")
                        d[k.strip()] = v.strip()
            return d

        props = read_props()
        scroll = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0,8))
        widgets = {}

        def section(title):
            ctk.CTkLabel(scroll, text=title, text_color=TEXT_MUTED,
                         font=ctk.CTkFont("Segoe UI",11,"bold")).pack(anchor="w", pady=(14,4))
            f = ctk.CTkFrame(scroll, fg_color=SIDEBAR_BG, corner_radius=10)
            f.pack(fill="x")
            return f

        def divider(parent):
            ctk.CTkFrame(parent, fg_color=BORDER, height=1).pack(fill="x")

        def _autosave_prop(key, value):
            """Sofort in server.properties schreiben ohne Speichern-Button."""
            prop_path = props_file
            if not prop_path.exists(): return
            lines = prop_path.read_text(encoding="utf-8").splitlines()
            found = False
            for i, l in enumerate(lines):
                if l.startswith(f"{key}="):
                    lines[i] = f"{key}={value}"; found = True; break
            if not found: lines.append(f"{key}={value}")
            prop_path.write_text("\n".join(lines)+"\n", encoding="utf-8")
            # Auch live im Server anwenden falls möglich
            if self.proc and self.proc.poll() is None:
                live_cmds = {
                    "difficulty":   f"difficulty {value}",
                    "pvp":          None,  # kein live-Befehl
                    "max-players":  f"setmaxplayers {value}",
                    "gamemode":     f"defaultgamemode {value}",
                }
                cmd = live_cmds.get(key)
                if cmd:
                    try: self.proc.stdin.write(f"{cmd}\n"); self.proc.stdin.flush()
                    except: pass

        def toggle_row(parent, key, label, default="false"):
            var = ctk.BooleanVar(value=props.get(key,default)=="true")
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x")
            row.grid_columnconfigure(0, weight=1)
            lf = ctk.CTkFrame(row, fg_color="transparent")
            lf.grid(row=0,column=0,padx=14,pady=10,sticky="w")
            ctk.CTkLabel(lf,text=label,text_color=TEXT,font=ctk.CTkFont("Segoe UI",13)).pack(anchor="w")
            ctk.CTkLabel(lf,text=key,text_color=TEXT_MUTED,font=ctk.CTkFont("Segoe UI",9)).pack(anchor="w")
            # Gespeichert-Indikator
            saved_lbl = ctk.CTkLabel(lf, text="", text_color=GREEN,
                                     font=ctk.CTkFont("Segoe UI",9))
            saved_lbl.pack(anchor="w")
            def _on_toggle():
                val = "true" if var.get() else "false"
                _autosave_prop(key, val)
                saved_lbl.configure(text="✓ Gespeichert")
                saved_lbl.after(2000, lambda: saved_lbl.configure(text=""))
            sw = ctk.CTkSwitch(row, variable=var, text="",
                                progress_color=GREEN, button_color=TEXT,
                                command=_on_toggle)
            sw.grid(row=0,column=1,padx=14)
            divider(parent)
            widgets[key]=("bool",var)

        def drop_row(parent, key, label, opts, display_opts=None, default=""):
            var = ctk.StringVar(value=props.get(key,default))
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x")
            row.grid_columnconfigure(0, weight=1)
            lf = ctk.CTkFrame(row, fg_color="transparent")
            lf.grid(row=0,column=0,padx=14,pady=10,sticky="w")
            ctk.CTkLabel(lf,text=label,text_color=TEXT,font=ctk.CTkFont("Segoe UI",13)).pack(anchor="w")
            ctk.CTkLabel(lf,text=key,text_color=TEXT_MUTED,font=ctk.CTkFont("Segoe UI",9)).pack(anchor="w")
            saved_lbl2 = ctk.CTkLabel(lf, text="", text_color=GREEN,
                                      font=ctk.CTkFont("Segoe UI",9))
            saved_lbl2.pack(anchor="w")
            shown = display_opts or opts
            dvar = ctk.StringVar(value=shown[opts.index(var.get())] if var.get() in opts else (shown[0] if shown else ""))
            def on_drop(val):
                idx = shown.index(val) if val in shown else 0
                var.set(opts[idx])
                _autosave_prop(key, opts[idx])
                saved_lbl2.configure(text="✓ Gespeichert")
                saved_lbl2.after(2000, lambda: saved_lbl2.configure(text=""))
            ctk.CTkOptionMenu(row, variable=dvar, values=shown,
                               fg_color=CARD, button_color=BLUE, command=on_drop,
                               width=180, font=ctk.CTkFont("Segoe UI",12)
                               ).grid(row=0,column=1,padx=14)
            divider(parent)
            widgets[key]=("str",var)

        def entry_row(parent, key, label, default=""):
            val = props.get(key,default)
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x")
            row.grid_columnconfigure(0, weight=1)
            lf = ctk.CTkFrame(row, fg_color="transparent")
            lf.grid(row=0,column=0,padx=14,pady=10,sticky="w")
            ctk.CTkLabel(lf,text=label,text_color=TEXT,font=ctk.CTkFont("Segoe UI",13)).pack(anchor="w")
            ctk.CTkLabel(lf,text=key,text_color=TEXT_MUTED,font=ctk.CTkFont("Segoe UI",9)).pack(anchor="w")
            e = ctk.CTkEntry(row, fg_color=CARD, border_color=BORDER,
                              width=180, font=ctk.CTkFont("Segoe UI",12))
            e.insert(0,val)
            e.grid(row=0,column=1,padx=14,pady=8)
            divider(parent)
            widgets[key]=("entry",e)

        def stepper_row(parent, key, label, default="20", min_v=1, max_v=999):
            try: cur = int(props.get(key, default))
            except: cur = int(default)
            var = ctk.IntVar(value=cur)
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x")
            row.grid_columnconfigure(0, weight=1)
            lf = ctk.CTkFrame(row, fg_color="transparent")
            lf.grid(row=0,column=0,padx=14,pady=10,sticky="w")
            ctk.CTkLabel(lf,text=label,text_color=TEXT,font=ctk.CTkFont("Segoe UI",13)).pack(anchor="w")
            ctk.CTkLabel(lf,text=key,text_color=TEXT_MUTED,font=ctk.CTkFont("Segoe UI",9)).pack(anchor="w")
            ctrl = ctk.CTkFrame(row, fg_color="transparent")
            ctrl.grid(row=0,column=1,padx=14)
            val_lbl = ctk.CTkLabel(ctrl, textvariable=var, text_color=TEXT,
                                   font=ctk.CTkFont("Segoe UI",14,"bold"), width=52)
            def dec():
                v = max(min_v, var.get()-1); var.set(v)
            def inc():
                v = min(max_v, var.get()+1); var.set(v)
            ctk.CTkButton(ctrl,text="−",width=32,height=32,fg_color=CARD,hover_color=BORDER,
                          font=ctk.CTkFont("Segoe UI",16),corner_radius=6,command=dec).pack(side="left")
            val_lbl.pack(side="left",padx=6)
            ctk.CTkButton(ctrl,text="+",width=32,height=32,fg_color=CARD,hover_color=BORDER,
                          font=ctk.CTkFont("Segoe UI",16),corner_radius=6,command=inc).pack(side="left")
            divider(parent)
            widgets[key]=("int",var)

        # ── RESSOURCEN ─────────────────────────────────────────────────────
        total_ram_mb = psutil.virtual_memory().total // (1024*1024)
        cpu_count    = psutil.cpu_count(logical=True) or 4

        # GPU-Name via wmic
        gpu_name = "Keine GPU erkannt"
        try:
            import subprocess as _sp
            _r = _sp.run(["wmic","path","win32_VideoController","get","name","/format:list"],
                         capture_output=True, text=True, timeout=4,
                         creationflags=CREATE_NO_WINDOW)
            for _l in _r.stdout.splitlines():
                if _l.startswith("Name=") and _l.strip()!="Name=":
                    gpu_name = _l.split("=",1)[1].strip(); break
        except Exception: pass

        saved_ram  = cfg.get("ram_mb",  min(2048, total_ram_mb//2))
        saved_cpu  = cfg.get("cpu_cores", max(1, cpu_count//2))
        saved_gpu  = cfg.get("gpu_pct", 0)

        ram_var = ctk.IntVar(value=saved_ram)
        cpu_var = ctk.IntVar(value=saved_cpu)
        gpu_var = ctk.IntVar(value=saved_gpu)

        # ── Performance Modus (nur für Plugin-Server) ─────────────────────────
        _opt_srv_type = cfg.get("type", "vanilla").lower()
        _opt_is_plugin = _opt_srv_type not in ("vanilla","snapshot","fabric","forge","neoforge","quilt","arclight")
        if _opt_is_plugin:
            _PERF_DIR2 = Path(os.getenv("APPDATA","")) / "MineHostLocal" / "perf_plugins"
            _opt_perf_var = ctk.BooleanVar(value=bool(cfg.get("perf_mode", False)))
            pperf = section("⚡  Performance Modus")

            pperf_top = ctk.CTkFrame(pperf, fg_color="transparent")
            pperf_top.pack(fill="x")
            pperf_top.grid_columnconfigure(0, weight=1)

            lf_perf = ctk.CTkFrame(pperf_top, fg_color="transparent")
            lf_perf.grid(row=0, column=0, padx=14, pady=(12,4), sticky="w")
            ctk.CTkLabel(lf_perf, text="Performance Modus aktivieren",
                         text_color=TEXT, font=ctk.CTkFont("Segoe UI", 13)).pack(anchor="w")
            ctk.CTkLabel(lf_perf,
                         text="Kopiert Optimierungs-Plugins in den Server • Einstellungen → Plugins ⚡",
                         text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI", 10)).pack(anchor="w")
            ctk.CTkLabel(lf_perf,
                         text="Besonders geeignet für Server mit sehr vielen gleichzeitigen Spielern (10+).",
                         text_color="#507050", font=ctk.CTkFont("Segoe UI", 10)).pack(anchor="w", pady=(2,0))

            _opt_perf_saved = ctk.CTkLabel(lf_perf, text="", text_color=GREEN,
                                           font=ctk.CTkFont("Segoe UI", 9))
            _opt_perf_saved.pack(anchor="w")

            def _opt_toggle_perf():
                enabled = _opt_perf_var.get()
                cfg["perf_mode"] = enabled
                save_server_cfg(self.server_name, cfg)
                import shutil as _sh
                srv_dir2 = Path(cfg.get("dir",""))
                folder2 = srv_dir2 / "plugins"
                folder2.mkdir(exist_ok=True)
                jars2 = [f for f in sorted(_PERF_DIR2.iterdir()) if f.suffix.lower()==".jar"] if _PERF_DIR2.exists() else []
                if enabled:
                    for jar in jars2:
                        dst = folder2 / jar.name
                        if not dst.exists():
                            try: _sh.copy2(str(jar), str(dst))
                            except: pass
                    _opt_perf_saved.configure(text=f"✓ {len(jars2)} Plugin(s) kopiert — Neustart nötig")
                else:
                    for jar in jars2:
                        dst = folder2 / jar.name
                        if dst.exists():
                            try: dst.unlink()
                            except: pass
                    _opt_perf_saved.configure(text="✓ Deaktiviert")
                _opt_perf_saved.after(3000, lambda: _opt_perf_saved.configure(text=""))

            ctk.CTkSwitch(pperf_top, variable=_opt_perf_var, text="",
                          progress_color=GREEN, button_color=TEXT,
                          command=_opt_toggle_perf
                          ).grid(row=0, column=1, padx=14)

            # Link zu Plugin-Einstellungen
            link_f = ctk.CTkFrame(pperf, fg_color="transparent")
            link_f.pack(fill="x", padx=14, pady=(0,10))
            ctk.CTkButton(link_f, text="→ Detaillierte Einstellungen (Plugins ⚡)",
                          height=28, fg_color="transparent", hover_color=CARD,
                          text_color=GREEN, font=ctk.CTkFont("Segoe UI", 10, "bold"),
                          anchor="w", command=lambda: self._show("plugins")
                          ).pack(side="left")

        pres = section("🖥?  Server-Ressourcen")

        # Hinweis wenn Server läuft
        is_running = self.proc is not None and self.proc.poll() is None
        if is_running:
            hint = ctk.CTkFrame(pres, fg_color="#1a2a1a", corner_radius=8)
            hint.pack(fill="x", padx=14, pady=(10,4))
            ctk.CTkLabel(hint,
                text="ℹ??  Server läuft — Änderungen werden gespeichert und beim nächsten Start aktiv.",
                text_color="#86efac", font=ctk.CTkFont("Segoe UI",10),
                wraplength=600, justify="left").pack(padx=12, pady=8, anchor="w")

        def _save_resources():
            """Sofort in Config speichern, ohne den großen Speichern-Button."""
            self.cfg["ram_mb"]    = ram_var.get()
            self.cfg["cpu_cores"] = cpu_var.get()
            self.cfg["gpu_pct"]   = gpu_var.get()
            save_server_cfg(self.server_name, self.cfg)

        def _warn_label(parent, var_ref, total, unit, threshold=0.5):
            warn = ctk.CTkLabel(parent, text="", text_color="#ffd600",
                                font=ctk.CTkFont("Segoe UI",10,"bold"))
            warn.pack(padx=14, anchor="w")
            def _upd(*_):
                pct = var_ref.get()/total if total else 0
                warn.configure(text=(
                    f"⚠??  Über {int(threshold*100)}% — kann deinen PC verlangsamen!"
                    if pct >= threshold else ""))
            var_ref.trace_add("write", _upd); _upd()

        def _res_slider(parent, label, var, from_, to, steps, upd_fn, lbl_var, unit=""):
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=(10,2))
            row.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(row, text=label, text_color=TEXT,
                         font=ctk.CTkFont("Segoe UI",13,"bold"), width=120
                         ).grid(row=0, column=0, sticky="w")
            sl = ctk.CTkSlider(row, from_=from_, to=to, variable=var,
                               number_of_steps=steps,
                               progress_color=GREEN, button_color=GREEN,
                               command=upd_fn)
            sl.grid(row=0, column=1, sticky="ew", padx=12)
            ctk.CTkLabel(row, textvariable=lbl_var, text_color=TEXT_MUTED,
                         font=ctk.CTkFont("Segoe UI",11), width=150
                         ).grid(row=0, column=2)
            # Sofort speichern wenn Slider losgelassen
            sl.bind("<ButtonRelease-1>", lambda e: _save_resources())

        # RAM
        ram_lbl_var = ctk.StringVar(value=f"{saved_ram} MB / {total_ram_mb} MB")
        def _ram_upd(v):
            v = round(float(v)/128)*128
            ram_var.set(v)
            ram_lbl_var.set(f"{v} MB  /  {total_ram_mb} MB")
        _res_slider(pres, "RAM", ram_var, 512, total_ram_mb,
                    (total_ram_mb-512)//128, _ram_upd, ram_lbl_var)
        _warn_label(pres, ram_var, total_ram_mb, "MB")
        divider(pres)

        # CPU
        cpu_lbl_var = ctk.StringVar(value=f"{saved_cpu} / {cpu_count} Kerne")
        def _cpu_upd(v):
            v = max(1, int(float(v))); cpu_var.set(v)
            cpu_lbl_var.set(f"{v} / {cpu_count} Kern{'e' if v!=1 else ''}")
        _res_slider(pres, "CPU-Kerne", cpu_var, 1, cpu_count,
                    cpu_count-1, _cpu_upd, cpu_lbl_var)
        _warn_label(pres, cpu_var, cpu_count, "Kerne")
        divider(pres)

        # GPU
        gpu_row = ctk.CTkFrame(pres, fg_color="transparent"); gpu_row.pack(fill="x",padx=14,pady=(10,4))
        gpu_row.grid_columnconfigure(1, weight=1)
        gl = ctk.CTkFrame(gpu_row, fg_color="transparent"); gl.grid(row=0,column=0,sticky="w")
        ctk.CTkLabel(gl,text="GPU-Anteil",text_color=TEXT,
                     font=ctk.CTkFont("Segoe UI",13,"bold")).pack(anchor="w")
        ctk.CTkLabel(gl,text=gpu_name,text_color=TEXT_MUTED,
                     font=ctk.CTkFont("Segoe UI",9)).pack(anchor="w")
        gpu_lbl_var = ctk.StringVar(value=f"{saved_gpu} %")
        def _gpu_upd(v):
            v = int(float(v)); gpu_var.set(v); gpu_lbl_var.set(f"{v} %")
        gpu_sl = ctk.CTkSlider(gpu_row, from_=0, to=100, variable=gpu_var,
                               number_of_steps=100,
                               progress_color=GREEN, button_color=GREEN, command=_gpu_upd)
        gpu_sl.grid(row=0,column=1,sticky="ew",padx=12)
        gpu_sl.bind("<ButtonRelease-1>", lambda e: _save_resources())
        ctk.CTkLabel(gpu_row, textvariable=gpu_lbl_var, text_color=TEXT_MUTED,
                     font=ctk.CTkFont("Segoe UI",11), width=80).grid(row=0,column=2)
        _warn_label(pres, gpu_var, 100, "%")

        # ── AUTOMATISIERUNG ─────────────────────────────────────────────────
        pauto = section("⚙?  Automatisierung")

        # Auto-Start beim App-Start
        appstart_en = ctk.BooleanVar(value=cfg.get("autostart", False))
        _ap_row = ctk.CTkFrame(pauto, fg_color="transparent"); _ap_row.pack(fill="x")
        _ap_row.grid_columnconfigure(0, weight=1)
        _ap_lf  = ctk.CTkFrame(_ap_row, fg_color="transparent"); _ap_lf.grid(row=0,column=0,padx=14,pady=10,sticky="w")
        ctk.CTkLabel(_ap_lf, text="Server beim App-Start automatisch starten",
                     text_color=TEXT, font=ctk.CTkFont("Segoe UI",13)).pack(anchor="w")
        ctk.CTkLabel(_ap_lf, text="Server startet automatisch wenn MineHost Local geöffnet wird",
                     text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",9)).pack(anchor="w")
        ctk.CTkSwitch(_ap_row, variable=appstart_en, text="",
                      progress_color=GREEN, button_color=TEXT).grid(row=0,column=1,padx=14)
        divider(pauto)

        # Auto-Start wenn Spieler verbindet
        autostart_en  = ctk.BooleanVar(value=cfg.get("autostart_enabled", False))
        autostart_who = ctk.StringVar(value=cfg.get("autostart_who", "any"))
        _as_row = ctk.CTkFrame(pauto, fg_color="transparent"); _as_row.pack(fill="x")
        _as_row.grid_columnconfigure(0, weight=1)
        _as_lf  = ctk.CTkFrame(_as_row, fg_color="transparent"); _as_lf.grid(row=0,column=0,padx=14,pady=10,sticky="w")
        ctk.CTkLabel(_as_lf,text="Starte wenn Spieler beitritt",text_color=TEXT,
                     font=ctk.CTkFont("Segoe UI",13)).pack(anchor="w")
        ctk.CTkLabel(_as_lf,text="Server startet automatisch sobald ein Spieler verbindet",
                     text_color=TEXT_MUTED,font=ctk.CTkFont("Segoe UI",9)).pack(anchor="w")
        _as_ctrl = ctk.CTkFrame(_as_row, fg_color="transparent"); _as_ctrl.grid(row=0,column=1,padx=14)
        _who_labels = ["Jeder Spieler","Nur Whitelist","Nur OP-Spieler"]
        _who_values = ["any","whitelist","op"]
        _who_dvar   = ctk.StringVar(value=_who_labels[_who_values.index(autostart_who.get())] if autostart_who.get() in _who_values else _who_labels[0])
        def _on_who(val):
            autostart_who.set(_who_values[_who_labels.index(val)] if val in _who_labels else "any")
        _who_menu = ctk.CTkOptionMenu(_as_ctrl, variable=_who_dvar, values=_who_labels,
                                       fg_color=CARD, button_color=BLUE, command=_on_who,
                                       width=160, font=ctk.CTkFont("Segoe UI",12))
        _who_menu.pack(side="left", padx=(0,8))
        def _toggle_who_menu(*_):
            _who_menu.configure(state="normal" if autostart_en.get() else "disabled")
        autostart_en.trace_add("write", _toggle_who_menu); _toggle_who_menu()
        ctk.CTkSwitch(_as_ctrl, variable=autostart_en, text="",
                      progress_color=GREEN, button_color=TEXT).pack(side="left")
        divider(pauto)

        # Auto-Stop
        autostop_en  = ctk.BooleanVar(value=cfg.get("autostop_enabled", False))
        autostop_min = ctk.IntVar(value=cfg.get("autostop_minutes", 3))
        _st_row = ctk.CTkFrame(pauto, fg_color="transparent"); _st_row.pack(fill="x")
        _st_row.grid_columnconfigure(0, weight=1)
        _st_lf  = ctk.CTkFrame(_st_row, fg_color="transparent"); _st_lf.grid(row=0,column=0,padx=14,pady=10,sticky="w")
        ctk.CTkLabel(_st_lf,text="Stoppe nach Minuten ohne Spieler",text_color=TEXT,
                     font=ctk.CTkFont("Segoe UI",13)).pack(anchor="w")
        ctk.CTkLabel(_st_lf,text="Server stoppt automatisch wenn niemand online ist",
                     text_color=TEXT_MUTED,font=ctk.CTkFont("Segoe UI",9)).pack(anchor="w")
        _st_ctrl = ctk.CTkFrame(_st_row, fg_color="transparent"); _st_ctrl.grid(row=0,column=1,padx=14)
        _stmin_lbl = ctk.CTkLabel(_st_ctrl, textvariable=autostop_min, text_color=TEXT,
                                   font=ctk.CTkFont("Segoe UI",14,"bold"), width=36)
        def _st_dec():
            autostop_min.set(max(1, autostop_min.get()-1))
        def _st_inc():
            autostop_min.set(min(60, autostop_min.get()+1))
        ctk.CTkButton(_st_ctrl,text="−",width=32,height=32,fg_color=CARD,hover_color=BORDER,
                      font=ctk.CTkFont("Segoe UI",16),corner_radius=6,command=_st_dec).pack(side="left")
        _stmin_lbl.pack(side="left",padx=6)
        ctk.CTkButton(_st_ctrl,text="+",width=32,height=32,fg_color=CARD,hover_color=BORDER,
                      font=ctk.CTkFont("Segoe UI",16),corner_radius=6,command=_st_inc).pack(side="left")
        ctk.CTkLabel(_st_ctrl,text="min",text_color=TEXT_MUTED,
                     font=ctk.CTkFont("Segoe UI",11)).pack(side="left",padx=(6,12))
        ctk.CTkSwitch(_st_ctrl, variable=autostop_en, text="",
                      progress_color=GREEN, button_color=TEXT).pack(side="left")
        divider(pauto)

        # Offline-Wartelobby
        lobby_en = ctk.BooleanVar(value=cfg.get("offline_lobby", False))
        _lo_row = ctk.CTkFrame(pauto, fg_color="transparent"); _lo_row.pack(fill="x")
        _lo_row.grid_columnconfigure(0, weight=1)
        _lo_lf  = ctk.CTkFrame(_lo_row, fg_color="transparent"); _lo_lf.grid(row=0,column=0,padx=14,pady=10,sticky="w")
        ctk.CTkLabel(_lo_lf,text="Offline-Wartelobby",text_color=TEXT,
                     font=ctk.CTkFont("Segoe UI",13)).pack(anchor="w")
        ctk.CTkLabel(_lo_lf,text="Spieler sehen eine Wartelobby wenn Server offline ist",
                     text_color=TEXT_MUTED,font=ctk.CTkFont("Segoe UI",9)).pack(anchor="w")
        ctk.CTkSwitch(_lo_row, variable=lobby_en, text="",
                      progress_color=GREEN, button_color=TEXT).grid(row=0,column=1,padx=14)

        # ── SERVER.PROPERTIES ───────────────────────────────────────────────
        p1 = section("??  Allgemein")
        drop_row(p1,"difficulty","Schwierigkeitsgrad",
                 ["peaceful","easy","normal","hard"],
                 ["Friedlich","Einfach","Normal","Schwer"],"normal")
        drop_row(p1,"gamemode","Spielmodus",
                 ["survival","creative","adventure","spectator"],
                 ["Überleben","Kreativ","Abenteuer","Zuschauer"],"survival")
        stepper_row(p1,"max-players","Spieler",default="20",min_v=1,max_v=200)
        stepper_row(p1,"view-distance","Sichtweite (Chunks)",default="10",min_v=3,max_v=32)
        stepper_row(p1,"player-idle-timeout","Zeitlimit für Inaktivität (Min, 0=aus)",default="0",min_v=0,max_v=999)
        stepper_row(p1,"spawn-protection","Spawn-Schutz (Blöcke)",default="16",min_v=0,max_v=100)

        p2 = section("⚔??  Spielmechaniken")
        toggle_row(p2,"pvp","PVP","true")
        toggle_row(p2,"allow-flight","Fliegen","false")
        toggle_row(p2,"allow-nether","Nether","true")
        toggle_row(p2,"spawn-monsters","Monster spawnen","true")
        toggle_row(p2,"force-gamemode","Spielmodus erzwingen","false")
        toggle_row(p2,"enable-command-block","Befehlsblöcke","false")

        p3 = section("??  Zugang")
        toggle_row(p3,"online-mode","Online-Mode  (aus = Cracked)","true")
        toggle_row(p3,"white-list","Whitelist","false")

        p4 = section("📋  Server-Details")
        entry_row(p4,"server-port","Port","25565")
        entry_row(p4,"motd","Beschreibung (MotD)","A Minecraft Server")
        entry_row(p4,"level-name","Weltname","world")
        entry_row(p4,"level-seed","Welt-Seed (leer = zufällig)","")
        entry_row(p4,"resource-pack","Ressourcenpaket URL","")

        # ── Server-Icon ───────────────────────────────────────────────────────
        icon_path = srv_dir / "server-icon.png"
        icon_row = ctk.CTkFrame(p4, fg_color="transparent")
        icon_row.pack(fill="x", padx=14, pady=8)
        icon_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(icon_row, text="Server-Icon",
                     text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",12),
                     width=160, anchor="w").grid(row=0, column=0, sticky="w")

        # Vorschau
        icon_preview = [None]
        preview_lbl = ctk.CTkLabel(icon_row, text="", width=64, height=64,
                                   fg_color=CARD, corner_radius=6)
        preview_lbl.grid(row=0, column=1, sticky="w", padx=(0,8))

        def _load_icon_preview():
            if icon_path.exists():
                try:
                    img = Image.open(str(icon_path)).convert("RGBA").resize((64,64), Image.LANCZOS)
                    cimg = ctk.CTkImage(light_image=img, dark_image=img, size=(64,64))
                    icon_preview[0] = cimg
                    preview_lbl.configure(image=cimg, text="")
                except: pass
            else:
                preview_lbl.configure(text="64×64", text_color=TEXT_MUTED,
                                      font=ctk.CTkFont("Segoe UI",10))

        _load_icon_preview()

        btn_col = ctk.CTkFrame(icon_row, fg_color="transparent")
        btn_col.grid(row=0, column=2, padx=8)

        status_lbl = ctk.CTkLabel(btn_col, text="", text_color=GREEN,
                                  font=ctk.CTkFont("Segoe UI",10))
        status_lbl.pack(pady=(0,4))

        def _pick_icon():
            p = filedialog.askopenfilename(
                title="Server-Icon wählen (wird auf 64×64 skaliert)",
                filetypes=[("Bild", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                           ("Alle", "*.*")])
            if not p: return
            try:
                img = Image.open(p).convert("RGBA").resize((64,64), Image.LANCZOS)
                img.save(str(icon_path), "PNG")
                status_lbl.configure(text="✓ Gespeichert!", text_color=GREEN)
                _load_icon_preview()
                # Server neu starten damit Icon aktiv wird
                if self.proc and self.proc.poll() is None:
                    status_lbl.configure(
                        text="✓ Gespeichert! Server neu starten.",
                        text_color="#f39c12")
            except Exception as e:
                status_lbl.configure(text=f"Fehler: {e}", text_color=RED)

        def _remove_icon():
            if icon_path.exists():
                icon_path.unlink()
                preview_lbl.configure(image=None, text="64×64",  # type: ignore
                                      text_color=TEXT_MUTED)
                icon_preview[0] = None
                status_lbl.configure(text="Entfernt", text_color=TEXT_MUTED)

        ctk.CTkButton(btn_col, text="📁 Bild wählen", width=110, height=30,
                      fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                      font=ctk.CTkFont("Segoe UI",11,"bold"), corner_radius=6,
                      command=_pick_icon).pack(pady=2)
        ctk.CTkButton(btn_col, text="🗑 Entfernen", width=110, height=28,
                      fg_color=CARD, text_color=TEXT_MUTED,
                      font=ctk.CTkFont("Segoe UI",10), corner_radius=6,
                      command=_remove_icon).pack(pady=2)

        # ── SPEICHERN ───────────────────────────────────────────────────────
        def save():
            # server.properties
            new = dict(props)
            for k,(t,w) in widgets.items():
                if t=="bool":  new[k] = "true" if w.get() else "false"
                elif t=="int": new[k] = str(w.get())
                else:          new[k] = w.get()
            props_file.write_text(
                "\n".join(f"{k}={v}" for k,v in new.items())+"\n", encoding="utf-8")
            # minehost.json
            self.cfg["port"]              = new.get("server-port","25565")
            self.cfg["motd"]              = new.get("motd","")
            self.cfg["ram_mb"]            = ram_var.get()
            self.cfg["cpu_cores"]         = cpu_var.get()
            self.cfg["gpu_pct"]           = gpu_var.get()
            self.cfg["autostart"]         = appstart_en.get()
            self.cfg["autostart_enabled"] = autostart_en.get()
            self.cfg["autostart_who"]     = autostart_who.get()
            self.cfg["autostop_enabled"]  = autostop_en.get()
            self.cfg["autostop_minutes"]  = autostop_min.get()
            self.cfg["offline_lobby"]     = lobby_en.get()
            save_server_cfg(self.server_name, self.cfg)
            messagebox.showinfo("Gespeichert",
                "Einstellungen gespeichert.\nServer neu starten, damit Änderungen wirksam werden.")

        btn_row = ctk.CTkFrame(self.content, fg_color="transparent")
        btn_row.grid(row=2, column=0, padx=20, pady=(4,16), sticky="ew")
        btn_row.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(btn_row, text="Speichern",
                      fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                      font=ctk.CTkFont("Segoe UI",14,"bold"), height=46, corner_radius=8,
                      command=save).grid(row=0, column=0, sticky="ew", padx=(0,8))
        ctk.CTkButton(btn_row, text="ℹ Kredits",
                      fg_color=CARD, hover_color=BORDER, text_color=TEXT_MUTED,
                      font=ctk.CTkFont("Segoe UI",12), height=46, corner_radius=8, width=110,
                      command=self._show_credits).grid(row=0, column=1)

    def _show_credits(self):
        win = ctk.CTkToplevel(self)
        win.title("Kredits & Quellen")
        win.geometry("580x680")
        win.configure(fg_color=BG)
        win.resizable(False, False)

        ctk.CTkLabel(win, text="Kredits & Download-Quellen",
                     font=ctk.CTkFont("Segoe UI",18,"bold"), text_color=GREEN
                     ).pack(padx=24, pady=(20,4), anchor="w")
        ctk.CTkLabel(win, text="MineHost Local verwendet folgende Dienste und Projekte:",
                     font=ctk.CTkFont("Segoe UI",11), text_color=TEXT_MUTED
                     ).pack(padx=24, anchor="w")

        scroll = ctk.CTkScrollableFrame(win, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=16, pady=8)

        CREDITS = [
            ("🖥?  Server-Software", [
                ("Vanilla / Snapshot",    "Mojang",       "https://www.minecraft.net",                      "Offizielle Minecraft Server-JAR"),
                ("Paper / Folia",         "PaperMC",      "https://papermc.io/downloads/paper",             "Hochleistungs-Fork für Plugins"),
                ("Purpur",                "PurpurMC",     "https://purpurmc.org",                           "Paper-Fork mit mehr Features"),
                ("Fabric",                "FabricMC",     "https://fabricmc.net",                           "Mod-Loader (modern)"),
                ("Quilt",                 "QuiltMC",      "https://quiltmc.org",                            "Fabric-Fork"),
                ("NeoForge",              "NeoForged",    "https://neoforged.net",                          "Forge-Nachfolger"),
                ("Forge",                 "MinecraftForge","https://files.minecraftforge.net",              "Klassischer Mod-Loader"),
                ("Arclight",              "ArclightMC",   "https://github.com/IzzelAliz/Arclight",          "Plugins + Mods kombiniert"),
                ("Spigot",                "SpigotMC",     "https://www.spigotmc.org/wiki/buildtools/",      "BuildTools nötig"),
            ]),
            ("🔌  Plugin-Quellen", [
                ("Hangar",                "PaperMC",      "https://hangar.papermc.io",                      "Offizielle Plugin-Plattform für Paper"),
                ("Modrinth",              "Modrinth",     "https://modrinth.com",                           "Mods & Plugins"),
                ("SpigotMC",              "SpigotMC",     "https://www.spigotmc.org/resources/",            "Spigot Plugins"),
                ("BukkitDev",             "CurseForge",   "https://dev.bukkit.org",                         "Bukkit Plugins"),
            ]),
            ("??  Tunnel / Netzwerk", [
                ("playit.gg",             "playit.gg",    "https://playit.gg",                              "Kostenloser Tunnel-Dienst"),
                ("ngrok",                 "ngrok",        "https://ngrok.com",                              "Tunnel-Dienst"),
                ("Cloudflare Tunnel",     "Cloudflare",   "https://cloudflare.com/products/tunnel",         "Kostenloser Tunnel"),
                ("zrok",                  "zrok",         "https://zrok.io",                                "Open-Source Tunnel"),
            ]),
            ("????  Backup-Dienste", [
                ("Google Drive",          "Google",       "https://drive.google.com",                       "Cloud-Backup"),
                ("OneDrive",              "Microsoft",    "https://onedrive.live.com",                      "Cloud-Backup"),
                ("Dropbox",               "Dropbox",      "https://www.dropbox.com",                        "Cloud-Backup"),
            ]),
            ("🛠?  Technologien", [
                ("Python",                "PSF",          "https://python.org",                             "Programmiersprache"),
                ("CustomTkinter",         "Tom Schimansky","https://github.com/TomSchimansky/CustomTkinter","GUI-Framework"),
                ("mc-heads.net",          "mc-heads",     "https://mc-heads.net",                           "Spieler-Kopf API"),
                ("Mojang API",            "Mojang",       "https://wiki.vg/Mojang_API",                     "Version & Profil Daten"),
            ]),
        ]

        for cat_title, entries in CREDITS:
            ctk.CTkLabel(scroll, text=cat_title,
                         font=ctk.CTkFont("Segoe UI",12,"bold"), text_color=GREEN
                         ).pack(anchor="w", pady=(12,4))
            for name, by, url, desc in entries:
                row = ctk.CTkFrame(scroll, fg_color=SIDEBAR_BG, corner_radius=8)
                row.pack(fill="x", pady=2)
                row.grid_columnconfigure(1, weight=1)
                ctk.CTkLabel(row, text=name,
                             font=ctk.CTkFont("Segoe UI",11,"bold"), text_color=TEXT,
                             width=160, anchor="w").grid(row=0, column=0, padx=(10,4), pady=8, sticky="w")
                ctk.CTkLabel(row, text=desc,
                             font=ctk.CTkFont("Segoe UI",10), text_color=TEXT_MUTED,
                             anchor="w").grid(row=0, column=1, padx=4, sticky="w")
                ctk.CTkButton(row, text="??", width=30, height=28,
                              fg_color="transparent", hover_color=CARD, text_color=BLUE,
                              corner_radius=6,
                              command=lambda u=url: __import__("webbrowser").open(u)
                              ).grid(row=0, column=2, padx=6)

        ctk.CTkLabel(win, text="© 2026 VisCode — MineHost Local",
                     font=ctk.CTkFont("Segoe UI",10), text_color="#444"
                     ).pack(pady=(4,12))
        ctk.CTkButton(win, text="Schließen", fg_color=CARD, text_color=TEXT,
                      command=win.destroy).pack(pady=(0,12))

    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    # PAGE: SPIELER
    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    def _p_players(self):
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        if not self.server_name:
            ctk.CTkLabel(self.content, text="Kein Server.", text_color=TEXT_MUTED).grid(row=0, column=0)
            return

        srv_dir    = Path(self.cfg.get("dir",""))
        known_db   = self._load_known_players()
        # Auch aus ops/whitelist/banned bekannte Spieler laden
        for fname in ["ops.json","whitelist.json"]:
            fp = srv_dir / fname
            if fp.exists():
                try:
                    for p in json.loads(fp.read_text(encoding="utf-8")):
                        n = p.get("name","")
                        if n and n not in known_db:
                            known_db[n] = {"name": n}
                except: pass

        outer = ctk.CTkFrame(self.content, fg_color="transparent")
        outer.grid(row=0, column=0, sticky="nsew")
        outer.grid_rowconfigure(1, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        # ── Tab-Buttons oben ──────────────────────────────────────────────────
        tab_names  = ["Whitelist", "Operator", "Gebannte Spieler", "Gebannte IP-Adressen"]
        tab_colors = [GREEN, GREEN, RED, RED]
        _cur_tab   = [0]
        tab_bar    = ctk.CTkFrame(outer, fg_color="transparent")
        tab_bar.grid(row=0, column=0, sticky="ew")
        tab_btns   = []
        for i, (tn, tc) in enumerate(zip(tab_names, tab_colors)):
            b = ctk.CTkButton(tab_bar, text=tn, fg_color=tc if i==0 else "#333",
                              text_color="#000" if i==0 else "#aaa",
                              hover_color=tc, font=ctk.CTkFont("Segoe UI",12,"bold"),
                              height=44, corner_radius=0,
                              command=lambda idx=i: _switch_tab(idx))
            b.pack(side="left", fill="x", expand=True)
            tab_btns.append((b, tc))

        content_area = ctk.CTkFrame(outer, fg_color="transparent")
        content_area.grid(row=1, column=0, sticky="nsew")
        content_area.grid_rowconfigure(0, weight=1)
        content_area.grid_columnconfigure(0, weight=1)

        _avatar_cache: dict = {}

        def _get_avatar(name: str, size=32) -> "ctk.CTkImage | None":
            key = f"{name}_{size}"
            if key in _avatar_cache:
                return _avatar_cache[key]
            try:
                # mc-heads.net für Spieler-Köpfe (face = nur das Gesicht, 8x8 Ausschnitt)
                url  = f"https://mc-heads.net/avatar/{name}/{size}"
                data = requests.get(url, timeout=4).content
                img  = Image.open(__import__("io").BytesIO(data)).convert("RGBA")
                cimg = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
                _avatar_cache[key] = cimg
                return cimg
            except:
                return None

        def _load_json_list(fname) -> list:
            fp = srv_dir / fname
            if fp.exists():
                try: return json.loads(fp.read_text(encoding="utf-8"))
                except: pass
            return []

        def _save_json_list(fname, data):
            (srv_dir / fname).write_text(json.dumps(data, indent=2), encoding="utf-8")

        def _switch_tab(idx):
            _cur_tab[0] = idx
            for i, (b, tc) in enumerate(tab_btns):
                b.configure(fg_color=tc if i==idx else "#333",
                            text_color="#000" if i==idx else "#aaa")
            for w in content_area.winfo_children():
                try: w.destroy()
                except: pass
            [_tab_whitelist, _tab_ops, _tab_banned, _tab_banned_ips][idx]()

        # ── Spieler-Karte ──────────────────────────────────────────────────────
        def _player_card(parent, name: str, extra_txt="", online=False,
                         remove_cmd=None, action_btn=None):
            card = ctk.CTkFrame(parent, fg_color="#1a1a1a", corner_radius=8)
            card.pack(fill="x", pady=2, padx=4)
            card.grid_columnconfigure(2, weight=1)

            # Avatar (async laden)
            av_lbl = ctk.CTkLabel(card, text="👤", font=ctk.CTkFont("Segoe UI",22), width=40)
            av_lbl.grid(row=0, column=0, padx=8, pady=8)
            def _load_av(n=name, lbl=av_lbl):
                img = _get_avatar(n, 32)
                if img:
                    try: lbl.configure(image=img, text="")
                    except: pass
            threading.Thread(target=_load_av, daemon=True).start()

            # Online-Dot
            dot_col = "#22c55e" if online else "#555"
            ctk.CTkLabel(card, text="●", text_color=dot_col,
                         font=ctk.CTkFont("Segoe UI",10), width=12
                         ).grid(row=0, column=1, sticky="w", padx=(0,4))

            # Name (klickbar → Detail)
            name_lbl = ctk.CTkLabel(card, text=name, font=ctk.CTkFont("Segoe UI",13,"bold"),
                         text_color=TEXT, anchor="w", cursor="hand2")
            name_lbl.grid(row=0, column=2, sticky="w")
            name_lbl.bind("<Button-1>", lambda e, n=name: _open_player_detail(n))

            if extra_txt:
                ctk.CTkLabel(card, text=extra_txt, font=ctk.CTkFont("Segoe UI",9),
                             text_color=TEXT_MUTED, anchor="w"
                             ).grid(row=0, column=3, padx=8, sticky="w")

            # Aktions-Buttons rechts
            btn_f = ctk.CTkFrame(card, fg_color="transparent")
            btn_f.grid(row=0, column=4, padx=8)
            ctk.CTkButton(btn_f, text="→", width=28, height=28,
                          fg_color=CARD, text_color=TEXT_MUTED, corner_radius=6,
                          command=lambda n=name: _open_player_detail(n)
                          ).pack(side="left", padx=2)
            if action_btn:
                ctk.CTkButton(btn_f, text=action_btn[0], width=90, height=28,
                              fg_color=action_btn[1], text_color=action_btn[2],
                              font=ctk.CTkFont("Segoe UI",10,"bold"), corner_radius=6,
                              command=action_btn[3]).pack(side="left", padx=2)
            if remove_cmd:
                ctk.CTkButton(btn_f, text="✕", width=28, height=28,
                              fg_color="#3a1010", text_color=RED, corner_radius=6,
                              command=remove_cmd).pack(side="left", padx=2)
            return card

        def _open_player_detail(name: str):
            """Öffnet das Spieler-Detail-Fenster."""
            srv_dir_pd = Path(self.cfg.get("dir",""))
            known      = self._load_known_players()
            info       = known.get(name, {})
            # Online-Status: aus bekannten Spielern + prüfen ob Server läuft
            server_running = self.proc is not None and self.proc.poll() is None
            online = info.get("online", False) and server_running

            # UUID aus ops/whitelist/usercache ermitteln
            uuid = ""
            for fname in ["usercache.json","ops.json","whitelist.json"]:
                fp = srv_dir_pd / fname
                if fp.exists():
                    try:
                        for p in json.loads(fp.read_text(encoding="utf-8")):
                            if p.get("name","").lower() == name.lower():
                                uuid = p.get("uuid",""); break
                    except: pass
                if uuid: break

            # NBT-Daten lesen (Spieler-Datei)
            nbt_data = {}
            stats_data = {}
            if uuid:
                # Stats
                for world_dir in srv_dir_pd.iterdir():
                    if not world_dir.is_dir(): continue
                    stats_f = world_dir / "stats" / f"{uuid}.json"
                    if stats_f.exists():
                        try: stats_data = json.loads(stats_f.read_text(encoding="utf-8"))
                        except: pass
                        break
                # NBT (playerdata)
                try:
                    import nbtlib
                    for world_dir in srv_dir_pd.iterdir():
                        if not world_dir.is_dir(): continue
                        dat_f = world_dir / "playerdata" / f"{uuid}.dat"
                        if dat_f.exists():
                            nbt_data = nbtlib.load(str(dat_f))
                            break
                except: pass

            # Spieler-Daten aus NBT
            health   = 20.0
            food     = 20
            xp_level = 0
            xp_prog  = 0.0
            gamemode = 0
            pos_x = pos_y = pos_z = 0.0
            dimension = "minecraft:overworld"
            try:
                root = nbt_data.get("", nbt_data)
                health   = float(root.get("Health", 20))
                food     = int(root.get("foodLevel", 20))
                xp_level = int(root.get("XpLevel", 0))
                xp_prog  = float(root.get("XpP", 0))
                gamemode = int(root.get("playerGameType", 0))
                pos      = root.get("Pos", [0,0,0])
                pos_x, pos_y, pos_z = float(pos[0]), float(pos[1]), float(pos[2])
                dimension = str(root.get("Dimension", "minecraft:overworld"))
            except: pass

            GAMEMODES = {0:"Überleben", 1:"Kreativ", 2:"Abenteuer", 3:"Zuschauer"}

            # Stats auslesen — sucht in allen Kategorien
            def _stat(key):
                try:
                    stats = stats_data.get("stats", {})
                    # Direkt in stats.minecraft:custom oder anderen Kategorien
                    for cat_key, cat_val in stats.items():
                        if isinstance(cat_val, dict):
                            if key in cat_val:
                                return cat_val[key]
                            # Kurzform ohne namespace
                            short = key.replace("minecraft:","")
                            for k,v in cat_val.items():
                                if k.replace("minecraft:","") == short:
                                    return v
                    return 0
                except: return 0

            play_ticks  = (_stat("minecraft:play_time")
                           or _stat("minecraft:play_one_minute")
                           or _stat("play_time")
                           or _stat("playOneMinute"))
            play_h = play_ticks // 72000
            play_m = (play_ticks % 72000) // 1200
            deaths = _stat("minecraft:deaths") or _stat("deaths")
            kills  = _stat("minecraft:player_kills") or _stat("playerKills")
            kd     = round(kills / max(deaths,1), 2)

            # ── Fenster ────────────────────────────────────────────────────
            win = ctk.CTkToplevel(self)
            win.title(f"Spieler: {name}")
            win.geometry("1000x700")
            win.configure(fg_color=BG)
            win.lift()                      # Vor die Haupt-GUI bringen
            win.focus_force()              # Fokus geben
            win.attributes("-topmost", True)   # Immer im Vordergrund
            win.after(300, lambda: win.attributes("-topmost", False))  # Nach 300ms normal

            # ── Header ─────────────────────────────────────────────────────
            hdr = ctk.CTkFrame(win, fg_color="#1a1a1a", corner_radius=0, height=80)
            hdr.pack(fill="x")
            hdr.pack_propagate(False)
            hdr.grid_columnconfigure(1, weight=1)

            av_lbl_big = ctk.CTkLabel(hdr, text="👤", font=ctk.CTkFont("Segoe UI",40), width=64)
            av_lbl_big.grid(row=0, column=0, padx=16, pady=10)
            def _load_big(lbl=av_lbl_big):
                img = _get_avatar(name, 56)
                if img:
                    try: lbl.configure(image=img, text="")
                    except: pass
            threading.Thread(target=_load_big, daemon=True).start()

            nfo = ctk.CTkFrame(hdr, fg_color="transparent")
            nfo.grid(row=0, column=1, sticky="w")
            status_txt = "Online" if online else "Offline"
            status_col = "#22c55e" if online else "#888"
            ctk.CTkLabel(nfo, text=name, font=ctk.CTkFont("Segoe UI",20,"bold"),
                         text_color=TEXT).pack(anchor="w")
            st_row = ctk.CTkFrame(nfo, fg_color="transparent"); st_row.pack(anchor="w")
            ctk.CTkLabel(st_row, text=f"?? {status_txt}", text_color=status_col,
                         font=ctk.CTkFont("Segoe UI",11)).pack(side="left", padx=(0,10))
            if uuid:
                ctk.CTkLabel(st_row, text=uuid, text_color="#555",
                             font=ctk.CTkFont("Segoe UI",9)).pack(side="left")

            gm_var = ctk.StringVar(value=GAMEMODES.get(gamemode,"Überleben"))
            ctk.CTkOptionMenu(hdr, variable=gm_var, values=list(GAMEMODES.values()),
                              fg_color=CARD, button_color=CARD, text_color=TEXT,
                              width=120, font=ctk.CTkFont("Segoe UI",11),
                              command=lambda v: (
                                  self.proc and self.proc.poll() is None and
                                  self.proc.stdin.write(
                                      f"gamemode {[k for k,vv in GAMEMODES.items() if vv==v][0]} {name}\n"
                                  ) and self.proc.stdin.flush())
                              ).grid(row=0, column=2, padx=16)

            # ── Body: Links + Rechts ────────────────────────────────────────
            body = ctk.CTkFrame(win, fg_color="transparent")
            body.pack(fill="both", expand=True, padx=0, pady=0)
            body.grid_columnconfigure(0, weight=3)
            body.grid_columnconfigure(1, weight=2)
            body.grid_rowconfigure(0, weight=1)

            left_scroll = ctk.CTkScrollableFrame(body, fg_color="transparent")
            left_scroll.grid(row=0, column=0, sticky="nsew", padx=(16,8), pady=12)

            right_frame = ctk.CTkFrame(body, fg_color="transparent")
            right_frame.grid(row=0, column=1, sticky="nsew", padx=(0,16), pady=12)

            def _section(parent, title):
                ctk.CTkLabel(parent, text=title, font=ctk.CTkFont("Segoe UI",13,"bold"),
                             text_color=TEXT).pack(anchor="w", pady=(12,6))
                f = ctk.CTkFrame(parent, fg_color="#1a1a1a", corner_radius=10)
                f.pack(fill="x")
                return f

            # ── Leben & XP ──────────────────────────────────────────────────
            life_sec = _section(left_scroll, "Leben und Erfahrung")
            # XP-Bar
            xp_bar_f = ctk.CTkFrame(life_sec, fg_color="transparent")
            xp_bar_f.pack(fill="x", padx=14, pady=(10,4))
            ctk.CTkLabel(xp_bar_f, text=f"Level {xp_level}",
                         font=ctk.CTkFont("Segoe UI",11,"bold"), text_color=TEXT).pack()
            xp_bar = ctk.CTkProgressBar(xp_bar_f, fg_color="#2a2a2a",
                                         progress_color="#84cc16", height=14)
            xp_bar.set(max(0, min(1, xp_prog)))
            xp_bar.pack(fill="x")

            # Herzen
            hp_row = ctk.CTkFrame(life_sec, fg_color="transparent")
            hp_row.pack(fill="x", padx=14, pady=4)
            # Kill/Heal buttons
            def _cmd(c):
                if self.proc and self.proc.poll() is None:
                    try: self.proc.stdin.write(f"{c}\n"); self.proc.stdin.flush()
                    except: pass
            ctk.CTkButton(hp_row, text="💀 Töten", width=90, height=32,
                          fg_color="#f97316", hover_color="#ea580c", text_color="#fff",
                          font=ctk.CTkFont("Segoe UI",11,"bold"), corner_radius=6,
                          command=lambda: _cmd(f"kill {name}")
                          ).pack(side="left", padx=(0,8))
            # Herz-Icons
            full_hearts = int(health // 2)
            half_heart  = (health % 2) >= 1
            max_hearts  = 10
            for i in range(max_hearts):
                if i < full_hearts: sym, col = "???", RED
                elif i == full_hearts and half_heart: sym, col = "♥", "#f97316"
                else: sym, col = "♡", "#555"
                ctk.CTkLabel(hp_row, text=sym, text_color=col,
                             font=ctk.CTkFont("Segoe UI",16)).pack(side="left")
            ctk.CTkButton(hp_row, text="??? Heilen", width=90, height=32,
                          fg_color="#22c55e", hover_color="#16a34a", text_color="#000",
                          font=ctk.CTkFont("Segoe UI",11,"bold"), corner_radius=6,
                          command=lambda: _cmd(f"effect give {name} minecraft:instant_health 1 10")
                          ).pack(side="right", padx=8)

            # Hunger-Icons
            food_row = ctk.CTkFrame(life_sec, fg_color="transparent")
            food_row.pack(fill="x", padx=14, pady=(0,10))
            ctk.CTkButton(food_row, text="💀 Aushungern", width=110, height=32,
                          fg_color="#f97316", hover_color="#ea580c", text_color="#fff",
                          font=ctk.CTkFont("Segoe UI",11,"bold"), corner_radius=6,
                          command=lambda: _cmd(f"effect give {name} minecraft:hunger 10 255")
                          ).pack(side="left", padx=(0,8))
            for i in range(10):
                if i < food // 2: sym, col = "???", "#f97316"
                else: sym, col = "🦴", "#555"
                ctk.CTkLabel(food_row, text=sym, font=ctk.CTkFont("Segoe UI",14),
                             text_color=col).pack(side="left")
            ctk.CTkButton(food_row, text="??? Füttern", width=90, height=32,
                          fg_color="#22c55e", hover_color="#16a34a", text_color="#000",
                          font=ctk.CTkFont("Segoe UI",11,"bold"), corner_radius=6,
                          command=lambda: _cmd(f"effect give {name} minecraft:saturation 1 10")
                          ).pack(side="right", padx=8)

            # ── Statistiken ─────────────────────────────────────────────────
            stat_sec = _section(left_scroll, "Statistiken")
            stat_grid = ctk.CTkFrame(stat_sec, fg_color="transparent")
            stat_grid.pack(fill="x", padx=14, pady=10)
            for col in range(4): stat_grid.grid_columnconfigure(col, weight=1)
            for i, (icon, label, val) in enumerate([
                ("???", "Spielzeit",      f"{play_h}h {play_m}m"),
                ("⚔",  "Spieler Kills",  str(kills)),
                ("💀",  "Tode",           str(deaths)),
                ("📊", "K/D",            str(kd)),
            ]):
                col = i % 4
                f = ctk.CTkFrame(stat_grid, fg_color="transparent")
                f.grid(row=0, column=col, padx=4, sticky="nsew")
                ctk.CTkLabel(f, text=icon, font=ctk.CTkFont("Segoe UI",22),
                             text_color=GREEN).pack()
                ctk.CTkLabel(f, text=label, font=ctk.CTkFont("Segoe UI",9),
                             text_color=TEXT_MUTED).pack()
                ctk.CTkLabel(f, text=val, font=ctk.CTkFont("Segoe UI",14,"bold"),
                             text_color=TEXT).pack()

            # Blöcke abgebaut aus Stats
            mined = stats_data.get("stats",{}).get("minecraft:mined",{})
            if mined:
                ctk.CTkLabel(stat_sec, text="Blöcke abgebaut",
                             font=ctk.CTkFont("Segoe UI",11,"bold"),
                             text_color=GREEN).pack(padx=14, anchor="w", pady=(8,2))
                for block, count in sorted(mined.items(), key=lambda x:-x[1])[:10]:
                    bname = block.replace("minecraft:","").replace("_"," ").title()
                    r = ctk.CTkFrame(stat_sec, fg_color="transparent")
                    r.pack(fill="x", padx=14, pady=1)
                    r.grid_columnconfigure(0, weight=1)
                    ctk.CTkLabel(r, text=bname, font=ctk.CTkFont("Segoe UI",11),
                                 text_color=TEXT, anchor="w").grid(row=0, column=0, sticky="w")
                    ctk.CTkLabel(r, text=f"{count:,}", font=ctk.CTkFont("Segoe UI",11),
                                 text_color=TEXT_MUTED).grid(row=0, column=1)

            ctk.CTkFrame(stat_sec, fg_color="transparent", height=10).pack()

            # ── Spieler-Daten löschen ───────────────────────────────────────
            del_sec = _section(left_scroll, "Spieler-Daten löschen")
            del_row = ctk.CTkFrame(del_sec, fg_color="transparent")
            del_row.pack(fill="x", padx=14, pady=10)
            del_opts = [
                ("Erfahrungspunkte",  f"xp set {name} 0"),
                ("Inventar löschen",  f"clear {name}"),
                ("Effekte löschen",   f"effect clear {name}"),
            ]
            for txt, cmd in del_opts:
                ctk.CTkButton(del_row, text=txt, height=28, fg_color="#2a1010",
                              text_color="#ff8888", font=ctk.CTkFont("Segoe UI",10),
                              corner_radius=6,
                              command=lambda c=cmd: _cmd(c)
                              ).pack(side="left", padx=4)

            # ── RECHTE SEITE: Kontrolle + Info ──────────────────────────────
            ctrl_sec = _section(right_frame, "Kontrolle")

            def _ctrl_row(label, is_on, on_cmd, off_cmd):
                r = ctk.CTkFrame(ctrl_sec, fg_color="transparent")
                r.pack(fill="x", padx=14, pady=4)
                r.grid_columnconfigure(0, weight=1)
                ctk.CTkLabel(r, text=label, font=ctk.CTkFont("Segoe UI",12),
                             text_color=TEXT, anchor="w").grid(row=0, column=0, sticky="w")
                var = ctk.BooleanVar(value=is_on)
                def _tog(v=var, oc=on_cmd, fc=off_cmd):
                    _cmd(oc if v.get() else fc)
                sw = ctk.CTkSwitch(r, variable=var, text="",
                                   progress_color="#22c55e" if not is_on else RED,
                                   command=_tog)
                sw.grid(row=0, column=1, padx=8)
                # X-Button
                ctk.CTkButton(r, text="✕", width=24, height=24,
                              fg_color=RED if is_on else "#333", text_color="#fff",
                              corner_radius=4,
                              command=lambda fc=off_cmd, v=var: (_cmd(fc), v.set(False))
                              ).grid(row=0, column=2)

            srv_dir2 = Path(self.cfg.get("dir",""))
            wl_names = set()
            op_names = set()
            bn_names = set()
            for fname, s in [("whitelist.json",wl_names),("ops.json",op_names),("banned-players.json",bn_names)]:
                fp = srv_dir2/fname
                if fp.exists():
                    try:
                        for p in json.loads(fp.read_text(encoding="utf-8")):
                            s.add(p.get("name",""))
                    except: pass

            _ctrl_row("👤 Whitelisted", name in wl_names,
                      f"whitelist add {name}", f"whitelist remove {name}")
            _ctrl_row("⛔ Gebannt", name in bn_names,
                      f"ban {name}", f"pardon {name}")
            _ctrl_row("👑 Administrator", name in op_names,
                      f"op {name}", f"deop {name}")

            # Info
            info_sec = _section(right_frame, "Informationen")
            def _info_row(icon, label, value, btn_txt=None, btn_cmd=None):
                f = ctk.CTkFrame(info_sec, fg_color="transparent")
                f.pack(fill="x", padx=14, pady=4)
                f.grid_columnconfigure(1, weight=1)
                ctk.CTkLabel(f, text=f"{icon} {label}",
                             font=ctk.CTkFont("Segoe UI",12,"bold"),
                             text_color=GREEN, anchor="w").grid(row=0, column=0, sticky="w")
                if btn_txt:
                    ctk.CTkButton(f, text=btn_txt, width=80, height=24,
                                  fg_color=CARD, text_color=TEXT,
                                  font=ctk.CTkFont("Segoe UI",10), corner_radius=6,
                                  command=btn_cmd).grid(row=0, column=2)
                ctk.CTkLabel(info_sec, text=value,
                             font=ctk.CTkFont("Segoe UI",10),
                             text_color=TEXT_MUTED, anchor="w"
                             ).pack(padx=28, anchor="w")

            pos_str = f"X {pos_x:.2f}  Y {pos_y:.2f}  Z {pos_z:.2f}\n{dimension}"
            _info_row("??", "Aktuelle Position", pos_str,
                      "Teleportieren" if online else None,
                      lambda: _cmd(f"tp {name} {pos_x:.0f} {pos_y:.0f} {pos_z:.0f}") if online else None)

        def _add_player_row(parent, fname, cmd_prefix, refresh_fn):
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=8)
            row.grid_columnconfigure(0, weight=1)
            ent = ctk.CTkEntry(row, placeholder_text="Spielername eingeben…",
                               fg_color=CARD, text_color=TEXT, height=34)
            ent.grid(row=0, column=0, sticky="ew", padx=(0,8))
            def _add():
                n = ent.get().strip()
                if not n: return
                data = _load_json_list(fname)
                if not any(p.get("name")==n for p in data):
                    data.append({"uuid":"","name":n})
                    _save_json_list(fname, data)
                if self.proc and self.proc.poll() is None:
                    try: self.proc.stdin.write(f"{cmd_prefix} {n}\n"); self.proc.stdin.flush()
                    except: pass
                ent.delete(0,"end")
                refresh_fn()
            ctk.CTkButton(row, text="Hinzufügen", width=110, height=34,
                          fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                          font=ctk.CTkFont("Segoe UI",11,"bold"), corner_radius=8,
                          command=_add).grid(row=0, column=1)
            ent.bind("<Return>", lambda e: _add())

        # ── TAB: Whitelist ────────────────────────────────────────────────────
        def _tab_whitelist():
            frame = ctk.CTkScrollableFrame(content_area, fg_color="transparent")
            frame.grid(row=0, column=0, sticky="nsew", padx=16, pady=8)

            # Bekannte Spieler zuerst anzeigen (mit Avatar, Online-Status)
            online_names = set(n for n,d in known_db.items() if d.get("online"))
            wl_data  = _load_json_list("whitelist.json")
            wl_names = {p.get("name","") for p in wl_data}

            if known_db:
                ctk.CTkLabel(frame, text="Alle Spieler", text_color=TEXT_MUTED,
                             font=ctk.CTkFont("Segoe UI",11,"bold")).pack(anchor="w", pady=(0,4))
                for name, info in sorted(known_db.items()):
                    is_online = name in online_names
                    in_wl     = name in wl_names
                    last      = info.get("last_seen","")
                    extra     = f"Zuletzt: {last}" if last else ""
                    def _wl_toggle(n=name, iw=in_wl):
                        data = _load_json_list("whitelist.json")
                        if iw:
                            data = [p for p in data if p.get("name") != n]
                            if self.proc and self.proc.poll() is None:
                                try: self.proc.stdin.write(f"whitelist remove {n}\n"); self.proc.stdin.flush()
                                except: pass
                        else:
                            if not any(p.get("name")==n for p in data):
                                data.append({"uuid":"","name":n})
                            if self.proc and self.proc.poll() is None:
                                try: self.proc.stdin.write(f"whitelist add {n}\n"); self.proc.stdin.flush()
                                except: pass
                        _save_json_list("whitelist.json", data)
                        _tab_whitelist()
                    btn_txt = ("✓ In Whitelist", "#1a3a1a", GREEN, lambda n=name, iw=in_wl: _wl_toggle(n, iw)) if in_wl else \
                              ("+ Whitelist", CARD, TEXT_MUTED, lambda n=name, iw=in_wl: _wl_toggle(n, iw))
                    _player_card(frame, name, extra, is_online, action_btn=btn_txt)
            else:
                ctk.CTkLabel(frame, text="Noch keine Spieler. Spieler müssen zuerst joinen.",
                             text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",12)).pack(pady=20)

            _add_player_row(frame, "whitelist.json", "whitelist add", _tab_whitelist)

        # ── TAB: Operator ─────────────────────────────────────────────────────
        def _tab_ops():
            frame = ctk.CTkScrollableFrame(content_area, fg_color="transparent")
            frame.grid(row=0, column=0, sticky="nsew", padx=16, pady=8)
            online_names = set(n for n,d in known_db.items() if d.get("online"))
            ops_data  = _load_json_list("ops.json")
            ops_names = {p.get("name","") for p in ops_data}

            for name in sorted(ops_names):
                def _remove_op(n=name):
                    data = [p for p in _load_json_list("ops.json") if p.get("name")!=n]
                    _save_json_list("ops.json", data)
                    if self.proc and self.proc.poll() is None:
                        try: self.proc.stdin.write(f"deop {n}\n"); self.proc.stdin.flush()
                        except: pass
                    _tab_ops()
                _player_card(frame, name, "", name in online_names, remove_cmd=_remove_op)

            if not ops_names:
                ctk.CTkLabel(frame, text="Keine Operatoren.", text_color=TEXT_MUTED,
                             font=ctk.CTkFont("Segoe UI",12)).pack(pady=20)

            _add_player_row(frame, "ops.json", "op", _tab_ops)

        # ── TAB: Gebannte Spieler ─────────────────────────────────────────────
        def _tab_banned():
            frame = ctk.CTkScrollableFrame(content_area, fg_color="transparent")
            frame.grid(row=0, column=0, sticky="nsew", padx=16, pady=8)
            banned = _load_json_list("banned-players.json")

            for p in banned:
                name   = p.get("name","?")
                reason = p.get("reason","")
                def _unban(n=name):
                    data = [x for x in _load_json_list("banned-players.json") if x.get("name")!=n]
                    _save_json_list("banned-players.json", data)
                    if self.proc and self.proc.poll() is None:
                        try: self.proc.stdin.write(f"pardon {n}\n"); self.proc.stdin.flush()
                        except: pass
                    _tab_banned()
                _player_card(frame, name, reason, remove_cmd=_unban,
                             action_btn=("Entbannen", "#1a3a1a", GREEN, lambda n=name: _unban()))

            if not banned:
                ctk.CTkLabel(frame, text="Keine gebannten Spieler.", text_color=TEXT_MUTED,
                             font=ctk.CTkFont("Segoe UI",12)).pack(pady=20)

            _add_player_row(frame, "banned-players.json", "ban", _tab_banned)

        # ── TAB: Gebannte IPs ─────────────────────────────────────────────────
        def _tab_banned_ips():
            frame = ctk.CTkScrollableFrame(content_area, fg_color="transparent")
            frame.grid(row=0, column=0, sticky="nsew", padx=16, pady=8)
            banned = _load_json_list("banned-ips.json")

            for p in banned:
                ip   = p.get("ip","?")
                reason = p.get("reason","")
                row  = ctk.CTkFrame(frame, fg_color="#1a1a1a", corner_radius=8)
                row.pack(fill="x", pady=2, padx=4)
                row.grid_columnconfigure(0, weight=1)
                ctk.CTkLabel(row, text=f"🔒  {ip}", font=ctk.CTkFont("Segoe UI",12,"bold"),
                             text_color=RED, anchor="w").grid(row=0, column=0, padx=12, pady=8, sticky="w")
                if reason:
                    ctk.CTkLabel(row, text=reason, font=ctk.CTkFont("Segoe UI",10),
                                 text_color=TEXT_MUTED).grid(row=0, column=1, padx=8)
                def _unban_ip(i=ip):
                    data = [x for x in _load_json_list("banned-ips.json") if x.get("ip")!=i]
                    _save_json_list("banned-ips.json", data)
                    if self.proc and self.proc.poll() is None:
                        try: self.proc.stdin.write(f"pardon-ip {i}\n"); self.proc.stdin.flush()
                        except: pass
                    _tab_banned_ips()
                ctk.CTkButton(row, text="✕", width=28, height=28,
                              fg_color="#3a1010", text_color=RED, corner_radius=6,
                              command=_unban_ip).grid(row=0, column=2, padx=8)

            if not banned:
                ctk.CTkLabel(frame, text="Keine gebannten IPs.", text_color=TEXT_MUTED,
                             font=ctk.CTkFont("Segoe UI",12)).pack(pady=20)

            # IP manuell bannen
            row2 = ctk.CTkFrame(frame, fg_color="transparent")
            row2.pack(fill="x", padx=4, pady=8)
            row2.grid_columnconfigure(0, weight=1)
            ip_ent = ctk.CTkEntry(row2, placeholder_text="IP-Adresse…",
                                  fg_color=CARD, text_color=TEXT, height=34)
            ip_ent.grid(row=0, column=0, sticky="ew", padx=(0,8))
            def _ban_ip():
                ip = ip_ent.get().strip()
                if not ip: return
                data = _load_json_list("banned-ips.json")
                if not any(p.get("ip")==ip for p in data):
                    data.append({"ip":ip,"reason":"Manually banned"})
                    _save_json_list("banned-ips.json", data)
                if self.proc and self.proc.poll() is None:
                    try: self.proc.stdin.write(f"ban-ip {ip}\n"); self.proc.stdin.flush()
                    except: pass
                ip_ent.delete(0,"end"); _tab_banned_ips()
            ctk.CTkButton(row2, text="IP bannen", width=110, height=34,
                          fg_color=RED, hover_color=RED_HOV, text_color="#fff",
                          font=ctk.CTkFont("Segoe UI",11,"bold"), corner_radius=8,
                          command=_ban_ip).grid(row=0, column=1)

        _switch_tab(0)

    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    # PAGE: SOFTWARE
    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    def _fetch_versions_for(self, sw_name: str) -> list:
        """Holt Versionen (neueste zuerst) für eine Software via API."""
        tag = SERVER_TYPES.get(sw_name, {}).get("tag","vanilla")
        try:
            if tag in ("paper","folia"):
                proj = "folia" if tag=="folia" else "paper"
                result = []

                # Neue 26.x Versionen von der Downloads-Seite (nur Paper)
                if proj == "paper":
                    page_vers = _get_paper_versions_from_page()
                    new_vers = [v for v in page_vers if not v.startswith("1.")]
                    for v in new_vers:
                        result.append((v, 1))  # Build-Count immer >=1

                # Klassische 1.x Versionen via API
                r = requests.get(f"https://api.papermc.io/v2/projects/{proj}", timeout=8)
                versions = r.json().get("versions", [])
                recent = list(reversed(versions[-15:]))
                older  = list(reversed(versions[:-15]))
                for v in recent:
                    try:
                        rb = requests.get(
                            f"https://api.papermc.io/v2/projects/{proj}/versions/{v}/builds",
                            timeout=4)
                        cnt = len(rb.json().get("builds",[]))
                    except: cnt = 0
                    result.append((v, cnt))
                for v in older:
                    result.append((v, 0))
                return result

            elif tag == "purpur":
                r = requests.get("https://api.purpurmc.org/v2/purpur", timeout=8)
                return [(v,0) for v in reversed(r.json().get("versions",[]))]

            elif tag == "fabric":
                r = requests.get("https://meta.fabricmc.net/v2/versions/game", timeout=8)
                return [(v["version"],0) for v in r.json() if v.get("stable")]  # API: neueste zuerst

            elif tag == "quilt":
                r = requests.get("https://meta.quiltmc.org/v3/versions/game", timeout=8)
                stable = [v for v in r.json() if not any(x in v.get("version","") for x in ("pre","rc","alpha","beta"))]
                return [(v["version"],0) for v in stable]  # API: neueste zuerst

            elif tag == "neoforge":
                r = requests.get("https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge",
                                  timeout=8)
                vers = r.json().get("versions",[])
                mc_map: dict = {}
                for v in vers:
                    mc = ".".join(v.split(".")[:3]) if v.count(".") >= 2 else v.split(".")[0]
                    mc_map[mc] = v
                return [(mc,0) for mc in reversed(list(mc_map.keys()))]

            elif tag == "forge":
                r = requests.get(
                    "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json",
                    timeout=8)
                promos = r.json().get("promos",{})
                mc_vers = sorted(set(k.split("-")[0] for k in promos.keys()), reverse=True)
                return [(v,0) for v in mc_vers]

            elif tag in ("vanilla","snapshot"):
                r = requests.get("https://piston-meta.mojang.com/mc/game/version_manifest_v2.json",
                                  timeout=8)
                vtype = "release" if tag=="vanilla" else "snapshot"
                # Mojang API: neueste zuerst
                return [(v["id"],0) for v in r.json().get("versions",[]) if v["type"]==vtype]

        except: pass
        return [(v,0) for v in MC_VERSIONS]

    def _p_software(self):
        # Guard: verhindert Doppel-Rendering wenn zweimal aufgerufen
        if getattr(self, "_software_rendering", False):
            return
        self._software_rendering = True
        try:
            self._p_software_impl()
        finally:
            self._software_rendering = False

    def _p_software_impl(self):
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        if not self.server_name:
            ctk.CTkLabel(self.content,text="Kein Server.",text_color=TEXT_MUTED).grid(row=0,column=0); return

        outer = ctk.CTkFrame(self.content, fg_color="transparent")
        outer.grid(row=0, column=0, sticky="nsew")
        outer.grid_rowconfigure(0, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        # ── STEP 1: Software-Typ wählen ───────────────────────────────────────
        step1 = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        step1.grid(row=0, column=0, sticky="nsew", padx=20, pady=8)

        cur_label = self.cfg.get("type_label","Vanilla")
        cur_ver   = self.cfg.get("mc_version","?")

        # Aktuell-Banner
        cur_info = ctk.CTkFrame(step1, fg_color=SIDEBAR_BG, corner_radius=10)
        cur_info.pack(fill="x", pady=(0,12))
        ctk.CTkLabel(cur_info, text=f"Aktuell: {cur_label}  {cur_ver}",
                     font=ctk.CTkFont("Segoe UI",13,"bold"), text_color=GREEN
                     ).pack(padx=14, pady=(10,2), anchor="w")
        ctk.CTkLabel(cur_info,
            text="✅ Welten, Spielerdaten, Plugins bleiben erhalten  |  ⚠?? server.jar wird ersetzt  |  📦 Backup vorher",
            text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10)).pack(padx=14, pady=(0,10), anchor="w")

        ctk.CTkLabel(step1, text="Software wählen:",
                     font=ctk.CTkFont("Segoe UI",12,"bold"), text_color=TEXT_MUTED
                     ).pack(anchor="w", pady=(0,6))

        grid = ctk.CTkFrame(step1, fg_color="transparent")
        grid.pack(fill="x")

        def _open_version_picker(sw_name):
            """Schritt 2: Versionen für gewählte Software anzeigen."""
            # step1 ausblenden, step2 zeigen
            step1.grid_remove()
            _show_step2(sw_name)

        for i,(name,info) in enumerate(SERVER_TYPES.items()):
            r,c = divmod(i,3)
            is_cur = name == cur_label
            btn = ctk.CTkButton(grid, text=f"{info['icon']}  {name}\n{info['desc']}",
                                fg_color=info["color"] if is_cur else CARD,
                                hover_color=info["color"],
                                text_color="#000" if is_cur else TEXT,
                                font=ctk.CTkFont("Segoe UI",11,"bold" if is_cur else "normal"),
                                corner_radius=8, height=70,
                                command=lambda n=name: _open_version_picker(n))
            btn.grid(row=r, column=c, padx=3, pady=3, sticky="nsew")
            grid.grid_columnconfigure(c, weight=1)

        # Status-Labels (für Fortschritt nach Schritt 2)
        self._sw_lbl = ctk.CTkLabel(step1, text="", text_color=TEXT_MUTED,
                                     font=ctk.CTkFont("Segoe UI",11))
        self._sw_lbl.pack(pady=(8,0))
        self._sw_prog = ctk.CTkProgressBar(step1, fg_color=CARD, progress_color=GREEN,
                                            mode="determinate")
        self._sw_prog.set(0)
        self._sw_prog.pack(fill="x", pady=(4,8))

        # ── STEP 2: Version wählen ────────────────────────────────────────────
        def _show_step2(sw_name):
            step2 = ctk.CTkFrame(outer, fg_color="transparent")
            step2.grid(row=0, column=0, sticky="nsew")
            step2.grid_rowconfigure(1, weight=1)
            step2.grid_columnconfigure(0, weight=1)

            info = SERVER_TYPES.get(sw_name, {})
            tag  = info.get("tag","vanilla")

            # Header
            hdr = ctk.CTkFrame(step2, fg_color=SIDEBAR_BG, corner_radius=10)
            hdr.grid(row=0, column=0, sticky="ew", padx=20, pady=(12,8))
            hdr.grid_columnconfigure(1, weight=1)

            ctk.CTkButton(hdr, text="?? Zurück", width=80, height=32,
                          fg_color=CARD, text_color=TEXT_MUTED,
                          font=ctk.CTkFont("Segoe UI",11), corner_radius=6,
                          command=lambda: (step2.destroy(), step1.grid())
                          ).grid(row=0, column=0, padx=10, pady=10)

            ctk.CTkLabel(hdr, text=f"{info.get('icon','')}  {sw_name}",
                         font=ctk.CTkFont("Segoe UI",14,"bold"), text_color=GREEN,
                         anchor="w").grid(row=0, column=1, sticky="w")

            self._sel_sw = sw_name
            self._sw_ver = tk.StringVar(value=cur_ver)
            sel_lbl = ctk.CTkLabel(hdr, text=f"Gewählt: {cur_ver}",
                                   text_color=GREEN, font=ctk.CTkFont("Segoe UI",11,"bold"))
            sel_lbl.grid(row=0, column=2, padx=14)

            # Spigot-Sonderfall
            if tag == "spigot":
                f = ctk.CTkFrame(step2, fg_color=SIDEBAR_BG, corner_radius=10)
                f.grid(row=1, column=0, sticky="nsew", padx=20, pady=8)
                ctk.CTkLabel(f, text="Spigot benötigt BuildTools",
                             font=ctk.CTkFont("Segoe UI",14,"bold"), text_color=TEXT
                             ).pack(pady=(20,8))
                ctk.CTkLabel(f,
                    text="Spigot kann nicht direkt heruntergeladen werden.\n"
                         "Lade BuildTools herunter, führe es aus und\n"
                         "kopiere die erstellte spigot-X.X.jar als server.jar.",
                    text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",12), justify="center"
                    ).pack(pady=4)
                ctk.CTkButton(f, text="⬇ BuildTools.jar herunterladen", height=42,
                    fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                    font=ctk.CTkFont("Segoe UI",12,"bold"),
                    command=lambda: __import__("webbrowser").open(
                        "https://hub.spigotmc.org/jenkins/job/BuildTools/lastSuccessfulBuild/artifact/target/BuildTools.jar")
                    ).pack(padx=16, pady=16, fill="x")
                return

            # Versionen-Grid
            loading_lbl = ctk.CTkLabel(step2, text="Lade Versionen…",
                                       text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",12))
            loading_lbl.grid(row=1, column=0, pady=30)

            _ver_btns: dict = {}

            def _select_ver(v):
                self._sw_ver.set(v)
                sel_lbl.configure(text=f"Gewählt: {v}")
                for vv, b in _ver_btns.items():
                    b.configure(fg_color=GREEN if vv==v else "#2a6a2a",
                                text_color="#000" if vv==v else "#aeffae")

            def _build_grid(versions_with_counts):
                try: loading_lbl.grid_remove()
                except: pass
                vf = ctk.CTkScrollableFrame(step2, fg_color="transparent")
                vf.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0,8))
                COLS = 5
                g = ctk.CTkFrame(vf, fg_color="transparent")
                g.pack(fill="x")
                for col in range(COLS): g.grid_columnconfigure(col, weight=1)
                cur_sel = self._sw_ver.get()
                for i,(ver,cnt) in enumerate(versions_with_counts):  # neueste bereits zuerst
                    ri,ci = divmod(i, COLS)
                    lbl = f"{ver} ({cnt})" if cnt else ver
                    is_sel = ver == cur_sel
                    b = ctk.CTkButton(g, text=lbl, height=34,
                                      fg_color=GREEN if is_sel else "#2a6a2a",
                                      hover_color=GREEN,
                                      text_color="#000" if is_sel else "#aeffae",
                                      font=ctk.CTkFont("Segoe UI",10,"bold" if is_sel else "normal"),
                                      corner_radius=6,
                                      command=lambda v=ver: _select_ver(v))
                    b.grid(row=ri, column=ci, padx=2, pady=2, sticky="ew")
                    _ver_btns[ver] = b

                # Install-Button unten
                install_f = ctk.CTkFrame(step2, fg_color="transparent")
                install_f.grid(row=2, column=0, sticky="ew", padx=20, pady=(0,12))
                install_f.grid_columnconfigure(0, weight=1)
                self._sw_lbl = ctk.CTkLabel(install_f, text="", text_color=TEXT_MUTED,
                                            font=ctk.CTkFont("Segoe UI",11))
                self._sw_lbl.grid(row=0, column=0, sticky="w")
                self._sw_prog = ctk.CTkProgressBar(install_f, fg_color=CARD, progress_color=GREEN,
                                                    mode="determinate")
                self._sw_prog.set(0)
                self._sw_prog.grid(row=1, column=0, sticky="ew", pady=(2,4))
                ctk.CTkButton(install_f, text=f"⬇  {sw_name} installieren",
                              fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                              font=ctk.CTkFont("Segoe UI",13,"bold"), height=46, corner_radius=10,
                              command=self._apply_sw).grid(row=2, column=0, sticky="ew")

            # Versionen im Hintergrund laden
            def _fetch():
                result = self._fetch_versions_for(sw_name)
                self.after(0, lambda r=result: _build_grid(r))
            threading.Thread(target=_fetch, daemon=True).start()

        scroll = step1  # Kompatibilität mit _apply_sw

        # ── Aktuell installiert ───────────────────────────────────────────────
        cur_label = self.cfg.get("type_label","Vanilla")
        cur_ver   = self.cfg.get("mc_version","?")
        cur_tag   = self.cfg.get("type","vanilla").lower()

        # Prüfen ob Paper wirklich verfügbar ist für diese Version
        paper_warning = ""
        if cur_tag in ("paper","folia","purpur"):
            def _check_paper_async():
                try:
                    proj = "folia" if cur_tag=="folia" else ("purpur" if cur_tag=="purpur" else "paper")
                    if proj == "purpur":
                        r = requests.get(f"https://api.purpurmc.org/v2/purpur/{cur_ver}", timeout=6)
                        ok = r.status_code == 200
                    else:
                        r = requests.get(f"https://api.papermc.io/v2/projects/{proj}/versions/{cur_ver}/builds", timeout=6)
                        ok = bool(r.json().get("builds"))
                    if not ok:
                        rv = requests.get(f"https://api.papermc.io/v2/projects/{proj}", timeout=6)
                        versions = rv.json().get("versions",[])
                        latest = versions[-1] if versions else "?"
                        dl_url = f"https://papermc.io/downloads/{proj}"
                        def _show_warn(lv=latest, u=dl_url, p=proj):
                            try:
                                warn = ctk.CTkFrame(cur_info, fg_color="#2a1a0a", corner_radius=6)
                                warn.pack(fill="x", padx=14, pady=(0,10))
                                ctk.CTkLabel(warn,
                                    text=f"⚠??  {cur_label} ist für MC {cur_ver} noch nicht verfügbar!\n"
                                         f"   server.jar ist möglicherweise Vanilla → Plugins werden NICHT geladen!\n"
                                         f"   Neueste verfügbare Version: {lv}",
                                    text_color="#f97316", font=ctk.CTkFont("Segoe UI",10),
                                    justify="left").pack(padx=10, pady=(8,4), anchor="w")
                                btn_row = ctk.CTkFrame(warn, fg_color="transparent")
                                btn_row.pack(padx=10, pady=(0,8), anchor="w")
                                ctk.CTkButton(btn_row, text=f"⚙ {p.capitalize()} Downloads öffnen",
                                    height=28, fg_color=BLUE, text_color="#fff",
                                    font=ctk.CTkFont("Segoe UI",10,"bold"), corner_radius=6,
                                    command=lambda url=u: __import__("webbrowser").open(url)
                                    ).pack(side="left", padx=(0,8))
                                ctk.CTkLabel(btn_row,
                                    text=f"→ JAR herunterladen, umbenennen zu server.jar und in den Server-Ordner legen",
                                    text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",9)
                                    ).pack(side="left")
                            except: pass
                        self.after(0, _show_warn)
                except: pass
            threading.Thread(target=_check_paper_async, daemon=True).start()

        cur_info  = ctk.CTkFrame(scroll, fg_color=SIDEBAR_BG, corner_radius=10)
        cur_info.pack(fill="x", pady=(0,12))
        ctk.CTkLabel(cur_info, text=f"Aktuell: {cur_label} {cur_ver}",
                     font=ctk.CTkFont("Segoe UI",13,"bold"), text_color=GREEN
                     ).pack(padx=14, pady=(10,2), anchor="w")
        ctk.CTkLabel(cur_info,
            text="✅ Bleibt erhalten beim Wechsel: Welten, Spielerdaten, Plugins, Configs\n"
                 "⚠??  Wird ersetzt: server.jar  |  Vor dem Wechsel wird automatisch ein Backup erstellt.",
            text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10), justify="left"
            ).pack(padx=14, pady=(0,10), anchor="w")

        # ── Software-Auswahl ──────────────────────────────────────────────────
        ctk.CTkLabel(scroll, text="Software wählen", text_color=TEXT_MUTED,
                     font=ctk.CTkFont("Segoe UI",11,"bold")).pack(anchor="w", pady=(0,4))

        grid = ctk.CTkFrame(scroll, fg_color="transparent")
        grid.pack(fill="x")
        self._sw_btns = {}
        self._sel_sw  = cur_label

        # Warn-Banner (erscheint wenn andere Software gewählt wird)
        warn_frame = ctk.CTkFrame(scroll, fg_color="#2a0a0a", corner_radius=10)
        warn_title = ctk.CTkLabel(warn_frame, text="",
                                   font=ctk.CTkFont("Segoe UI",15,"bold"), text_color=RED)
        warn_desc  = ctk.CTkLabel(warn_frame, text="",
                                   font=ctk.CTkFont("Segoe UI",11), text_color="#ff9999",
                                   justify="left", wraplength=600)

        def _pick(n):
            self._sel_sw = n
            for nm, btn in self._sw_btns.items():
                ni = SERVER_TYPES[nm]
                is_sel = nm == n
                btn.configure(fg_color=ni["color"] if is_sel else CARD)
            # Warn-Banner aktualisieren
            if n != cur_label:
                new_tag = SERVER_TYPES[n]["tag"]
                old_tag = SERVER_TYPES[cur_label]["tag"]
                # Was wird gelöscht?
                deleted = ["server.jar"]
                if new_tag in ("fabric","forge","neoforge","quilt") and old_tag not in ("fabric","forge","neoforge","quilt"):
                    deleted.append("plugins/  (Plugins nicht kompatibel mit Mods)")
                elif old_tag in ("fabric","forge","neoforge","quilt") and new_tag not in ("fabric","forge","neoforge","quilt"):
                    deleted.append("mods/  (Mods nicht kompatibel mit Plugins)")
                warn_title.configure(text="⚠  NEUINSTALLATION ERFORDERLICH!")
                warn_desc.configure(
                    text=f"Wechsel von {cur_label} → {n}\n\n"
                         f"✅  Bleibt erhalten:  Welten, Spielerdaten, Configs\n"
                         f"🗑  Wird ersetzt:  {', '.join(deleted)}\n"
                         f"📦  Vor dem Wechsel wird automatisch ein Backup erstellt.\n"
                         f"🔄  Server wird gestoppt, neue JAR heruntergeladen und neu gestartet.")
                warn_frame.pack(fill="x", pady=8)
                warn_title.pack(padx=14, pady=(12,2), anchor="w")
                warn_desc.pack(padx=14, pady=(0,12), anchor="w")
            else:
                warn_frame.pack_forget()

        for i,(name,info) in enumerate(SERVER_TYPES.items()):
            r,c = divmod(i,3)
            is_cur = name == cur_label
            f = ctk.CTkButton(grid, text="",
                               fg_color=info["color"] if is_cur else CARD,
                               hover_color=info["color"],
                               corner_radius=8, height=70,
                               command=lambda n=name: _pick(n))
            f.grid(row=r, column=c, padx=3, pady=3, sticky="nsew")
            grid.grid_columnconfigure(c, weight=1)
            inner = ctk.CTkFrame(f, fg_color="transparent")
            inner.place(relx=0, rely=0, relwidth=1, relheight=1)
            ctk.CTkLabel(inner, text=f"{info['icon']}  {name}",
                         text_color="#000" if is_cur else TEXT,
                         font=ctk.CTkFont("Segoe UI",12,"bold")).pack(pady=(12,0))
            ctk.CTkLabel(inner, text=info["desc"],
                         text_color="#000" if is_cur else TEXT_MUTED,
                         font=ctk.CTkFont("Segoe UI",8), wraplength=140).pack(pady=(0,8))
            for w in [inner] + list(inner.winfo_children()):
                try: w.bind("<Button-1>", lambda e, n=name: _pick(n))
                except: pass
            self._sw_btns[name] = f

        # ── Version-Picker (dynamisch von API) ───────────────────────────────
        self._sw_ver = ctk.StringVar(value=cur_ver)

        ver_section = ctk.CTkFrame(scroll, fg_color=SIDEBAR_BG, corner_radius=10)
        ver_section.pack(fill="x", pady=8)

        ver_hdr = ctk.CTkFrame(ver_section, fg_color="transparent")
        ver_hdr.pack(fill="x", padx=14, pady=(12,4))
        ver_hdr.grid_columnconfigure(0, weight=1)

        ver_title_lbl = ctk.CTkLabel(ver_hdr, text="Version wählen:",
                                      text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",12,"bold"),
                                      anchor="w")
        ver_title_lbl.grid(row=0, column=0, sticky="w")

        sel_lbl = ctk.CTkLabel(ver_hdr, text=f"Gewählt: {cur_ver}",
                               text_color=GREEN, font=ctk.CTkFont("Segoe UI",11,"bold"))
        sel_lbl.grid(row=0, column=1, sticky="e")

        ver_grid_frame = ctk.CTkScrollableFrame(ver_section, fg_color="transparent", height=200)
        ver_grid_frame.pack(fill="x", padx=10, pady=(0,10))

        _ver_btns: dict = {}

        def _select_ver(v):
            self._sw_ver.set(v)
            sel_lbl.configure(text=f"Gewählt: {v}")
            for vv, btn in _ver_btns.items():
                btn.configure(fg_color=GREEN if vv == v else "#2a7a2a")

        def _build_ver_grid(versions_with_counts: list):
            """versions_with_counts: list of (version_str, build_count)"""
            try:
                if not ver_grid_frame.winfo_exists(): return
            except Exception: return
            for w in ver_grid_frame.winfo_children(): w.destroy()
            _ver_btns.clear()
            COLS = 6
            grid = ctk.CTkFrame(ver_grid_frame, fg_color="transparent")
            grid.pack(fill="x")
            for col in range(COLS): grid.grid_columnconfigure(col, weight=1)
            cur_sel = self._sw_ver.get()
            for i, (ver, count) in enumerate(versions_with_counts):  # neueste bereits zuerst
                row_i, col_i = divmod(i, COLS)
                lbl = f"{ver} ({count})" if count else ver
                is_sel = ver == cur_sel
                btn = ctk.CTkButton(grid, text=lbl, height=32,
                                    fg_color=GREEN if is_sel else "#2a7a2a",
                                    hover_color=GREEN, text_color="#000" if is_sel else "#cfc",
                                    font=ctk.CTkFont("Segoe UI", 10, "bold" if is_sel else "normal"),
                                    corner_radius=6,
                                    command=lambda v=ver: _select_ver(v))
                btn.grid(row=row_i, column=col_i, padx=2, pady=2, sticky="ew")
                _ver_btns[ver] = btn

        # Versionen laden (im Hintergrund)
        def _load_versions(sw_name=self._sel_sw):
            tag = SERVER_TYPES.get(sw_name, {}).get("tag","vanilla")
            try:
                if tag in ("paper","folia"):
                    proj = "folia" if tag=="folia" else "paper"
                    result = []

                    # Neue 26.x Versionen von Downloads-Seite (nur Paper)
                    if proj == "paper":
                        page_vers = _get_paper_versions_from_page()
                        new_vers  = [v for v in page_vers if not v.startswith("1.")]
                        for v in new_vers:
                            result.append((v, 1))

                    # Klassische 1.x via API
                    r = requests.get(f"https://api.papermc.io/v2/projects/{proj}", timeout=8)
                    versions = r.json().get("versions", [])
                    for v in versions[-30:]:
                        try:
                            rb = requests.get(
                                f"https://api.papermc.io/v2/projects/{proj}/versions/{v}/builds",
                                timeout=5)
                            cnt = len(rb.json().get("builds",[]))
                        except: cnt = 0
                        result.append((v, cnt))
                    for v in versions[:-30]:
                        result.append((v, 0))
                    self.after(0, lambda r=result: _build_ver_grid(r))
                    return
                elif tag == "purpur":
                    r = requests.get("https://api.purpurmc.org/v2/purpur", timeout=8)
                    versions = r.json().get("versions", [])
                    result = [(v,0) for v in versions]
                    self.after(0, lambda r=result: _build_ver_grid(r))
                    return
            except: pass
            # Fallback: MC_VERSIONS
            result = [(v,0) for v in MC_VERSIONS]
            self.after(0, lambda r=result: _build_ver_grid(r))

        # Sofort Fallback anzeigen, dann API laden
        _build_ver_grid([(v,0) for v in MC_VERSIONS])
        threading.Thread(target=_load_versions, daemon=True).start()

        # Wenn Software gewechselt wird → Versionen neu laden
        _orig_pick = _pick.__code__
        def _pick_with_ver_reload(n, _orig=_pick):
            _orig(n)
            threading.Thread(target=lambda: _load_versions(n), daemon=True).start()

        # Buttons neu binden
        for name, btn in self._sw_btns.items():
            btn.configure(command=lambda n=name: _pick_with_ver_reload(n))
        for name, btn in self._sw_btns.items():
            inner_frames = [c for c in btn.winfo_children()]
            for fr in inner_frames:
                for w in [fr] + list(fr.winfo_children()):
                    try: w.bind("<Button-1>", lambda e, n=name: _pick_with_ver_reload(n))
                    except: pass

        # ── Status + Button ───────────────────────────────────────────────────
        self._sw_lbl = ctk.CTkLabel(scroll, text="", text_color=TEXT_MUTED,
                                     font=ctk.CTkFont("Segoe UI",11))
        self._sw_lbl.pack(pady=(4,0))
        self._sw_prog = ctk.CTkProgressBar(scroll, fg_color=CARD, progress_color=GREEN,
                                            mode="determinate")
        self._sw_prog.set(0)
        self._sw_prog.pack(fill="x", pady=(4,8))
        ctk.CTkButton(scroll, text="⬇  Wechseln & Neu installieren",
                      fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                      font=ctk.CTkFont("Segoe UI",13,"bold"), height=48, corner_radius=10,
                      command=self._apply_sw).pack(fill="x", pady=4)

    def _get_jar_url(self, name: str, ver: str) -> "str | None":
        """Holt die direkte Download-URL via offizieller API für jeden Server-Typ."""
        tag = SERVER_TYPES.get(name, {}).get("tag", "vanilla")

        # Paper, Folia → zuerst neue API (26.x), dann klassische API
        if tag in ("paper", "folia"):
            proj = "folia" if tag == "folia" else "paper"
            # Neue Versionen (26.x) → Downloads-Seite
            if proj == "paper" and not ver.startswith("1."):
                url = _get_paper_url_new(ver)
                if url: return url
                return f"__NOT_AVAILABLE__{proj}|{ver}|26.1.2"
            # Klassische 1.x → API
            try:
                r = requests.get(f"https://api.papermc.io/v2/projects/{proj}/versions/{ver}/builds",
                                 timeout=10)
                if r.status_code == 404:
                    rv = requests.get(f"https://api.papermc.io/v2/projects/{proj}", timeout=8)
                    versions = rv.json().get("versions", [])
                    latest = versions[-1] if versions else "?"
                    return f"__NOT_AVAILABLE__{proj}|{ver}|{latest}"
                builds = r.json().get("builds", [])
                if builds:
                    b = builds[-1]
                    fname = b["downloads"]["application"]["name"]
                    return f"https://api.papermc.io/v2/projects/{proj}/versions/{ver}/builds/{b['build']}/downloads/{fname}"
            except: pass
            return f"__NOT_AVAILABLE__{proj}|{ver}|?"

        # Purpur → purpurmc.org API
        if tag == "purpur":
            try:
                r = requests.get(f"https://api.purpurmc.org/v2/purpur/{ver}/latest/download",
                                 timeout=10, allow_redirects=False)
                if r.status_code in (200, 302):
                    return r.headers.get("Location") or f"https://api.purpurmc.org/v2/purpur/{ver}/latest/download"
                return f"https://api.purpurmc.org/v2/purpur/{ver}/latest/download"
            except: pass

        # Fabric → meta.fabricmc.net
        if tag == "fabric":
            try:
                # Loader-Version
                lr = requests.get("https://meta.fabricmc.net/v2/versions/loader", timeout=8)
                loader = lr.json()[0]["version"]
                # Installer-Version
                ir = requests.get("https://meta.fabricmc.net/v2/versions/installer", timeout=8)
                installer = ir.json()[0]["version"]
                return f"https://meta.fabricmc.net/v2/versions/loader/{ver}/{loader}/{installer}/server/jar"
            except: pass

        # Quilt → quiltmc.org
        if tag == "quilt":
            try:
                lr = requests.get("https://meta.quiltmc.org/v3/versions/loader", timeout=8)
                loader = lr.json()[0]["version"]
                ir = requests.get("https://meta.quiltmc.org/v3/versions/installer", timeout=8)
                installer = ir.json()[0]["version"]
                return f"https://quiltmc.org/api/v1/download-latest-installer/java-universal"
            except: pass

        # NeoForge → neoforged.net
        if tag == "neoforge":
            try:
                r = requests.get(
                    f"https://maven.neoforged.net/api/maven/latest/version/releases/net/neoforged/neoforge",
                    timeout=8)
                nf_ver = r.json().get("version","")
                if nf_ver:
                    return f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{nf_ver}/neoforge-{nf_ver}-installer.jar"
            except: pass

        # Forge → files.minecraftforge.net (kein direkter API-Link — BuildTools nötig)
        if tag == "forge":
            try:
                r = requests.get(
                    f"https://files.minecraftforge.net/net/minecraftforge/forge/index_{ver}.html",
                    timeout=8)
                import re as _re
                m = _re.search(r'href="(https://maven\.minecraftforge\.net/net/minecraftforge/forge/[^"]+installer\.jar)"', r.text)
                if m: return m.group(1)
            except: pass

        # Arclight → arclightmc.org (GitHub Releases)
        if tag == "arclight":
            try:
                r = requests.get(
                    "https://api.github.com/repos/IzzelAliz/Arclight/releases/latest",
                    headers={"Accept":"application/vnd.github+json"}, timeout=8)
                for asset in r.json().get("assets", []):
                    if asset["name"].endswith(".jar") and ver.replace(".","") in asset["name"].replace(".",""):
                        return asset["browser_download_url"]
                # Neueste nehmen
                for asset in r.json().get("assets", []):
                    if asset["name"].endswith(".jar"):
                        return asset["browser_download_url"]
            except: pass

        # Spigot → BuildTools (kein direkter Download, Hinweis)
        if tag == "spigot":
            return None  # Wird unten als Hinweis behandelt

        # Vanilla / Snapshot → Mojang manifest
        return get_vanilla_jar_url(ver)

    def _apply_sw(self):
        name = self._sel_sw; ver = self._sw_ver.get()
        tag  = SERVER_TYPES.get(name, {}).get("tag", "vanilla")

        # Spigot braucht BuildTools → nicht automatisch
        if tag == "spigot":
            messagebox.showinfo("Spigot / BuildTools",
                "Spigot kann nicht automatisch heruntergeladen werden.\n\n"
                "Bitte BuildTools von spigotmc.org herunterladen,\n"
                "ausführen und die erstellte spigot-*.jar als server.jar\n"
                "in den Server-Ordner kopieren.")
            return

        # Bestätigung mit Warnung
        confirm = messagebox.askyesno("Software wechseln",
            f"Wechseln zu {name} {ver}?\n\n"
            "✅ Bleibt erhalten:\n   Welten, Spielerdaten, Plugins, Configs\n\n"
            "⚠??  Wird ersetzt:\n   server.jar (Backup wird vorher erstellt)\n\n"
            "Server wird gestoppt und neu gestartet.")
        if not confirm: return

        # Server stoppen
        if self.proc is not None and self.proc.poll() is None:
            self._stop()

        srv_dir = Path(self.cfg["dir"])

        def dl():
            def _upd(msg, pct=None, col=TEXT_MUTED):
                try:
                    self._sw_lbl.configure(text=msg, text_color=col)
                    if pct is not None and hasattr(self, "_sw_prog"):
                        self._sw_prog.set(pct)
                except: pass

            # Schritt 1: Backup
            _upd("📦 Backup wird erstellt…", 0.05)
            try:
                bkp_dir = APP_DIR / "backups"; bkp_dir.mkdir(exist_ok=True)
                ts   = time.strftime("%Y%m%d_%H%M%S")
                bkp  = bkp_dir / f"{self.server_name}_before_sw_change_{ts}.zip"
                shutil.make_archive(str(bkp.with_suffix("")), "zip", str(srv_dir))
                _upd(f"✓ Backup: {bkp.name}", 0.2, GREEN)
            except Exception as e:
                _upd(f"⚠ Backup fehlgeschlagen: {e}", 0.2, "#f39c12")

            # Schritt 2: Download-URL holen
            _upd(f"?? Suche {name} {ver}…", 0.25)
            url = self._get_jar_url(name, ver)
            if not url or (url and url.startswith("__NOT_AVAILABLE__")):
                if url and url.startswith("__NOT_AVAILABLE__"):
                    parts = url.replace("__NOT_AVAILABLE__","").split("|")
                    proj, req_ver, latest = parts[0], parts[1], parts[2]
                    dl_url = f"https://papermc.io/downloads/{proj}"
                    msg = (f"???  {name} {req_ver} ist NICHT verfügbar!\n\n"
                           f"PaperMC hat noch kein Build für Minecraft {req_ver}.\n"
                           f"Neueste verfügbare Version: {latest}\n\n"
                           f"Optionen:\n"
                           f"• Version {latest} im Dropdown wählen\n"
                           f"• Manuell von {dl_url} herunterladen\n"
                           f"  → JAR als 'server.jar' in den Server-Ordner legen")
                    def _open_and_msg(m=msg, u=dl_url):
                        if messagebox.askyesno("Version nicht verfügbar",
                                m + "\n\nDownload-Seite jetzt öffnen?"):
                            __import__("webbrowser").open(u)
                    self.after(0, _open_and_msg)
                else:
                    msg = f"Keine JAR für {name} {ver} gefunden."
                    self.after(0, lambda m=msg: messagebox.showerror("Fehler", m))
                _upd(f"✗ {name} {ver} nicht verfügbar.", 0, RED)
                # Backup wiederherstellen falls bereits gemacht
                bak_early = srv_dir / "server.jar.bak"
                if bak_early.exists() and not (srv_dir/"server.jar").exists():
                    bak_early.rename(srv_dir/"server.jar")
                return

            # Schritt 3: server.jar ersetzen
            jar = srv_dir / "server.jar"
            bak = srv_dir / "server.jar.bak"
            if jar.exists():
                jar.rename(bak)

            _upd(f"⬇ Lade {name} {ver}…", 0.3)
            try:
                r = requests.get(url, stream=True, timeout=180, allow_redirects=True)
                total = int(r.headers.get("content-length", 0))
                done  = 0
                with open(str(jar), "wb") as fh:
                    for chunk in r.iter_content(8192):
                        fh.write(chunk); done += len(chunk)
                        if total:
                            pct = 0.3 + 0.65 * (done / total)
                            _upd(f"⬇ {name} {ver} — {done//1024} / {total//1024} kB", pct)

                # eula.txt sicherstellen
                eula = srv_dir / "eula.txt"
                if not eula.exists():
                    eula.write_text("eula=true\n", encoding="utf-8")

                # Nur Software + Version updaten — Adresse + Tunnel BLEIBT erhalten
                self.cfg["type_label"] = name
                self.cfg["type"]       = tag
                self.cfg["mc_version"] = ver
                # playit_address und playit_tunnel_id explizit behalten
                # (werden nicht angefasst — nur zur Sicherheit nochmal aus dem aktuellen cfg)
                save_server_cfg(self.server_name, self.cfg)

                _upd(f"✓ {name} {ver} installiert — Server startet…", 1.0, GREEN)
                if bak.exists():
                    try: bak.unlink()
                    except: pass
                # Software-Seite neu laden damit aktuelle Version grün ist
                self.after(800, lambda: (self._update_nav_state(), self._show("software")))
                self.after(1500, self._start)

            except Exception as e:
                _upd(f"✗ Fehler: {e}", 0, RED)
                # Altes server.jar wiederherstellen
                if bak.exists() and not jar.exists():
                    bak.rename(jar)

        threading.Thread(target=dl, daemon=True).start()

        threading.Thread(target=dl, daemon=True).start()

    # ─── Script-DB & Custom-Categories ───────────────────────────────────────
    def _script_db_path(self):
        return APP_DIR / "script_plugins.json"

    def _load_script_db(self):
        p = self._script_db_path()
        if p.exists():
            try: return json.loads(p.read_text(encoding="utf-8"))
            except: pass
        return []

    def _save_script_db(self, db):
        p = self._script_db_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(db, indent=2, ensure_ascii=False), encoding="utf-8")

    def _custom_cats_path(self):
        return APP_DIR / "custom_categories.json"

    def _load_custom_cats(self):
        p = self._custom_cats_path()
        if p.exists():
            try: return json.loads(p.read_text(encoding="utf-8"))
            except: pass
        return []

    def _save_custom_cats(self, cats):
        p = self._custom_cats_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cats, indent=2, ensure_ascii=False), encoding="utf-8")

    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    # PAGE: PLUGINS + MODS  (mit Modrinth-Suche)
    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    def _p_plugins(self):
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        if not self.server_name:
            ctk.CTkLabel(self.content, text="Kein Server.", text_color=TEXT_MUTED).grid(row=0, column=0); return
        # Vanilla hat keine Plugins
        srv_type = self.cfg.get("type","vanilla").lower()
        if srv_type in ("vanilla", "snapshot"):
            f = ctk.CTkFrame(self.content, fg_color="transparent")
            f.grid(row=0, column=0)
            ctk.CTkLabel(f, text="⚙",  font=ctk.CTkFont("Segoe UI",40), text_color=TEXT_MUTED).pack(pady=(0,8))
            ctk.CTkLabel(f, text="Vanilla unterstützt keine Plugins.",
                         font=ctk.CTkFont("Segoe UI",15,"bold"), text_color=TEXT).pack()
            ctk.CTkLabel(f, text="Wechsle zu Paper, Spigot oder Purpur um Plugins zu nutzen.",
                         font=ctk.CTkFont("Segoe UI",12), text_color=TEXT_MUTED).pack(pady=4)
            ctk.CTkButton(f, text="→ Software wechseln",
                          fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                          font=ctk.CTkFont("Segoe UI",12,"bold"), height=38, corner_radius=20,
                          command=lambda: self._show("software")).pack(pady=12)
            return

        srv_dir  = Path(self.cfg.get("dir",""))
        mc_ver   = self.cfg.get("mc_version","1.21")
        srv_type = self.cfg.get("type","vanilla").lower()
        is_mod   = srv_type in ("fabric","forge","neoforge","quilt","arclight")
        folder   = srv_dir / ("mods" if is_mod else "plugins")
        folder.mkdir(exist_ok=True)
        # Meta-Datenbank für manuell hochgeladene Plugins
        meta_file = folder / ".minehost_meta.json"
        def _load_meta():
            if meta_file.exists():
                try: return json.loads(meta_file.read_text(encoding="utf-8"))
                except: pass
            return {}
        def _save_meta(d):
            meta_file.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")

        # CurseForge API Key — aus Config oder eingebetteter Standard-Key
        _CF_DEFAULT = "$2a$10$Elf7v2U/s7MzU19f9pxnp.WTzd9zCJvnExuUKZYTSn4Q7e1yj0tLC"
        CF_KEY = self.cfg.get("curseforge_api_key", "") or _CF_DEFAULT
        # Standard-Key in Config speichern falls noch nicht gesetzt
        if not self.cfg.get("curseforge_api_key"):
            self.cfg["curseforge_api_key"] = _CF_DEFAULT
            save_server_cfg(self.server_name, self.cfg)
        CF_GAME_ID      = 432
        CF_CLASS_BUKKIT = 5
        CF_CLASS_MOD    = 6

        # CurseForge modLoaderType je Server-Typ
        CF_LOADER_TYPE = {"fabric": 4, "forge": 1, "neoforge": 6,
                          "quilt": 5, "arclight": 1}
        # Modrinth loader-facet je Server-Typ
        MR_LOADER = {"fabric": "fabric", "forge": "forge", "neoforge": "neoforge",
                     "quilt": "quilt", "arclight": "forge"}

        # Kategorien für Bukkit/Paper-Plugins (CurseForge)
        CF_CATEGORIES = [
            ("Admin Tools",                 4557),
            ("Anti-Griefing Tools",         4579),
            ("Chat Related",                4578),
            ("Developer Tools",             4553),
            ("Economy",                     4555),
            ("Fixes",                       4576),
            ("Fun",                         4556),
            ("General",                     4554),
            ("Informational",               4577),
            ("Mechanics",                   4575),
            ("Miscellaneous",               4574),
            ("Role Playing",                4572),
            ("Teleportation",               4573),
            ("Website Administration",      4570),
            ("World Editing And Management",4569),
            ("World Generators",            4568),
        ]

        # Kategorien für Mods (CurseForge classId=6)
        CF_MOD_CATEGORIES = [
            ("Adventure & RPG",     422),
            ("API & Library",       421),
            ("Armor, Tools & Weapons", 434),
            ("Decoration",          424),
            ("Environment",         426),
            ("Food",                428),
            ("Magic",               419),
            ("Map & Information",   423),
            ("Miscellaneous",       425),
            ("Mobs",                411),
            ("Optimization",        5191),
            ("Server Utility",      435),
            ("Storage",             420),
            ("Technology",          412),
            ("World Gen",           406),
        ]

        # Kategorien für Plugins (Modrinth)
        MR_CATEGORIES = [
            ("Adventure",       "adventure"),
            ("Economy",         "economy"),
            ("Game Mechanics",  "game-mechanics"),
            ("Library",         "library"),
            ("Magic",           "magic"),
            ("Management",      "management"),
            ("Minigame",        "minigame"),
            ("Mobs",            "mobs"),
            ("Optimization",    "optimization"),
            ("Social",          "social"),
            ("Storage",         "storage"),
            ("Technology",      "technology"),
            ("Transportation",  "transportation"),
            ("Utility",         "utility"),
            ("World Gen",       "worldgen"),
        ]

        # Kategorien für Mods (Modrinth)
        MR_MOD_CATEGORIES = [
            ("Adventure",       "adventure"),
            ("Decoration",      "decoration"),
            ("Equipment",       "equipment"),
            ("Food",            "food"),
            ("Game Mechanics",  "game-mechanics"),
            ("Library",         "library"),
            ("Magic",           "magic"),
            ("Mobs",            "mobs"),
            ("Optimization",    "optimization"),
            ("Storage",         "storage"),
            ("Technology",      "technology"),
            ("Transportation",  "transportation"),
            ("Utility",         "utility"),
            ("World Gen",       "worldgen"),
        ]

        outer = ctk.CTkFrame(self.content, fg_color="transparent")
        outer.grid(row=0, column=0, sticky="nsew")
        outer.grid_rowconfigure(0, weight=0)
        outer.grid_rowconfigure(1, weight=0)
        outer.grid_rowconfigure(2, weight=0)
        outer.grid_rowconfigure(3, weight=1)
        outer.grid_columnconfigure(0, weight=0)
        outer.grid_columnconfigure(1, weight=1)

        facet_type = "mod" if is_mod else "plugin"

        # ── Quellen-Umschalter + Suche ────────────────────────────────────────
        _source = ["modrinth" if is_mod else "curseforge"]  # aktive Quelle

        topbar = ctk.CTkFrame(outer, fg_color="transparent")
        topbar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(8,4))
        topbar.grid_columnconfigure(2, weight=1)

        title_lbl = "Plugins" if not is_mod else "Mods"
        ctk.CTkLabel(topbar, text=title_lbl,
                     font=ctk.CTkFont("Segoe UI",16,"bold"), text_color=GREEN
                     ).grid(row=0, column=0, sticky="w", padx=(0,8))

        # Quellen-Buttons
        _src_btns = {}
        sources = ([("CurseForge","curseforge"),("Modrinth","modrinth"),("Hangar","hangar"),("Meine Uploads","uploads")]
                   if not is_mod else [("CurseForge","curseforge"),("Modrinth","modrinth"),("Meine Uploads","uploads")])
        src_btn_f = ctk.CTkFrame(topbar, fg_color="transparent")
        src_btn_f.grid(row=0, column=1, padx=(0,8))

        def _switch_source(src):
            _source[0] = src
            for s, b in _src_btns.items():
                b.configure(fg_color=GREEN if s==src else CARD,
                            text_color="#000" if s==src else TEXT_MUTED)
            _update_sidebar(src)
            if src.startswith("custom_"):
                _show_custom_category(src)
            elif src == "uploads":
                _show_uploads()
            else:
                _do_search(search_entry.get())

        for src_name, src_key in sources:
            is_active = (src_key == _source[0])
            b = ctk.CTkButton(src_btn_f, text=src_name, width=90, height=28,
                               fg_color=GREEN if is_active else CARD,
                               hover_color=GREEN_HOV,
                               text_color="#000" if is_active else TEXT_MUTED,
                               font=ctk.CTkFont("Segoe UI",11,"bold" if is_active else "normal"),
                               corner_radius=6,
                               command=lambda sk=src_key: _switch_source(sk))
            b.pack(side="left", padx=2)
            _src_btns[src_key] = b

        # Custom Categories als Tabs
        custom_cats = self._load_custom_cats()
        for cat in custom_cats:
            cid = cat["id"]
            is_active = (cid == _source[0])
            b = ctk.CTkButton(src_btn_f, text=cat["name"], width=90, height=28,
                               fg_color=GREEN if is_active else CARD,
                               hover_color=GREEN_HOV,
                               text_color="#000" if is_active else TEXT_MUTED,
                               font=ctk.CTkFont("Segoe UI",11,"bold" if is_active else "normal"),
                               corner_radius=6,
                               command=lambda c=cid: _switch_source(c))
            b.pack(side="left", padx=2)
            _src_btns[cid] = b

        # ＋ Neue Kategorie erstellen
        def _add_category():
            win = ctk.CTkToplevel(self)
            win.title("Neue Kategorie")
            win.geometry("360x160")
            win.configure(fg_color=BG)
            win.lift(); win.focus_force(); win.grab_set()
            ctk.CTkLabel(win, text="Kategorie-Name:",
                         font=ctk.CTkFont("Segoe UI",13,"bold"), text_color=TEXT).pack(pady=(20,6))
            e = ctk.CTkEntry(win, placeholder_text="z.B. Meine Plugins",
                             fg_color="#111", text_color=TEXT, height=36)
            e.pack(fill="x", padx=20); e.focus()
            def _ok():
                name = e.get().strip()
                if not name: return
                cats = self._load_custom_cats()
                cid = f"custom_{len(cats)}_{name[:8].replace(' ','_')}"
                cats.append({"id": cid, "name": name, "plugins": []})
                self._save_custom_cats(cats)
                win.destroy()
                self._show("plugins")  # Seite neu laden mit neuem Tab
            ctk.CTkButton(win, text="Erstellen", fg_color=GREEN, hover_color=GREEN_HOV,
                          text_color="#000", font=ctk.CTkFont("Segoe UI",12,"bold"),
                          height=36, corner_radius=8, command=_ok).pack(pady=12, padx=20, fill="x")
            win.bind("<Return>", lambda ev: _ok())

        ctk.CTkButton(src_btn_f, text="＋", width=32, height=28,
                      fg_color=CARD, hover_color=GREEN, text_color=GREEN,
                      font=ctk.CTkFont("Segoe UI",14,"bold"), corner_radius=6,
                      command=_add_category).pack(side="left", padx=(4,0))

        search_entry = ctk.CTkEntry(topbar, placeholder_text="Suchen…",
                                    fg_color="#111", text_color=TEXT, height=32)
        search_entry.grid(row=0, column=2, sticky="ew", padx=(0,6))
        ctk.CTkButton(topbar, text="??", width=32, height=32,
                      fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                      corner_radius=6,
                      command=lambda: _do_search(search_entry.get())
                      ).grid(row=0, column=3)
        search_entry.bind("<Return>", lambda e: _do_search(search_entry.get()))

        # ── Performance Modus (nur Plugin-Server) ─────────────────────────────
        _PERF_DIR = Path(os.getenv("APPDATA","")) / "MineHostLocal" / "perf_plugins"
        if not is_mod:
            _perf_enabled = ctk.BooleanVar(value=bool(self.cfg.get("perf_mode", False)))

            def _get_perf_jars():
                if not _PERF_DIR.exists(): return []
                return [f for f in sorted(_PERF_DIR.iterdir()) if f.suffix.lower() == ".jar"]

            def _patch_props(props_path, patches):
                if not props_path.exists(): return
                lines = props_path.read_text(encoding="utf-8").splitlines()
                applied = set()
                for i, line in enumerate(lines):
                    s = line.strip()
                    if s.startswith("#") or "=" not in s: continue
                    k = s.split("=", 1)[0].strip()
                    if k in patches:
                        lines[i] = f"{k}={patches[k]}"; applied.add(k)
                for k, v in patches.items():
                    if k not in applied: lines.append(f"{k}={v}")
                props_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            def _patch_yml(yml_path, patches):
                import re as _re
                if not yml_path.exists(): return
                content = yml_path.read_text(encoding="utf-8")
                for key, val in patches.items():
                    content = _re.sub(
                        rf'^(\s*{_re.escape(str(key))}:\s*).*$',
                        rf'\g<1>{val}', content, flags=_re.MULTILINE)
                yml_path.write_text(content, encoding="utf-8")

            def _apply_perf_config(vd, sd, msr, ea, em, er):
                srv_path = Path(self.cfg.get("dir", ""))
                if not srv_path.exists(): return
                _patch_props(srv_path / "server.properties", {
                    "view-distance": str(vd), "simulation-distance": str(sd)})
                _patch_yml(srv_path / "spigot.yml", {
                    "mob-spawn-range": str(msr),
                    "animals": str(ea), "monsters": str(em), "raiders": str(er)})

            def _toggle_perf():
                enabled = _perf_enabled.get()
                self.cfg["perf_mode"] = enabled
                save_server_cfg(self.server_name, self.cfg)
                import shutil as _sh
                jars = _get_perf_jars()
                running = self.proc and self.proc.poll() is None
                suffix = " — Neustart nötig" if running else ""
                if enabled:
                    for jar in jars:
                        dst = folder / jar.name
                        if not dst.exists():
                            try: _sh.copy2(str(jar), str(dst))
                            except Exception: pass
                    _perf_status_lbl.configure(
                        text=f"✓ {len(jars)} Plugin(s) kopiert{suffix}", text_color=GREEN)
                else:
                    for jar in jars:
                        dst = folder / jar.name
                        if dst.exists():
                            try: dst.unlink()
                            except Exception: pass
                    _perf_status_lbl.configure(text=f"Deaktiviert{suffix}", text_color=TEXT_MUTED)
                # Sidebar neu aufbauen (Perf-Kategorie ein-/ausblenden)
                self.after(0, lambda: _update_sidebar(_source[0]))

            def _open_perf_settings():
                win = ctk.CTkToplevel(self)
                win.title("⚡ Performance Modus — Einstellungen")
                win.geometry("540x640")
                win.configure(fg_color=BG)
                win.lift(); win.focus_force(); win.grab_set()

                sf = ctk.CTkScrollableFrame(win, fg_color="transparent")
                sf.pack(fill="both", expand=True, padx=16, pady=12)
                sf.grid_columnconfigure(0, weight=0)
                sf.grid_columnconfigure(1, weight=0)
                sf.grid_columnconfigure(2, weight=1)

                ctk.CTkLabel(sf, text="⚡ Performance Modus — Einstellungen",
                             font=ctk.CTkFont("Segoe UI", 14, "bold"), text_color=GREEN
                             ).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0,10))

                # ── Auto-Preset nach Spielerzahl ──────────────────────────────
                ctk.CTkLabel(sf, text="Auto-Einstellungen nach Spielerzahl:",
                             font=ctk.CTkFont("Segoe UI", 11, "bold"), text_color=TEXT
                             ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(0,4))

                _PRESETS = [
                    ("1–10",  8,  6,  6, 32, 32, 48, "Fokus auf Spielspaß"),
                    ("11–30", 6,  4,  4, 16, 24, 32, "Stabil"),
                    ("31–60", 5,  3,  3, 12, 18, 24, "Performance"),
                    ("60+",   4,  2,  2,  8, 12, 16, "Hardcore"),
                ]

                _vd  = [int(self.cfg.get("perf_vd",  6))]
                _sd  = [int(self.cfg.get("perf_sd",  4))]
                _msr = [int(self.cfg.get("perf_msr", 4))]
                _ea  = [int(self.cfg.get("perf_ea",  16))]
                _em  = [int(self.cfg.get("perf_em",  24))]
                _er  = [int(self.cfg.get("perf_er",  32))]

                slider_refs = {}

                def _apply_preset(vd, sd, msr, ea, em, er):
                    _vd[0]=vd; _sd[0]=sd; _msr[0]=msr
                    _ea[0]=ea; _em[0]=em; _er[0]=er
                    for k, (sl, lbl) in slider_refs.items():
                        v = {"vd":vd,"sd":sd,"msr":msr,"ea":ea,"em":em,"er":er}[k]
                        sl.set(v); lbl.configure(text=str(v))

                pf = ctk.CTkFrame(sf, fg_color="transparent")
                pf.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0,10))
                for (lbl, vd, sd, msr, ea, em, er, tip) in _PRESETS:
                    ctk.CTkButton(pf, text=lbl, width=108, height=34,
                                  fg_color=CARD, hover_color=GREEN, text_color=TEXT,
                                  font=ctk.CTkFont("Segoe UI", 11), corner_radius=6,
                                  command=lambda v=vd,s=sd,m=msr,a=ea,mo=em,r=er: _apply_preset(v,s,m,a,mo,r)
                                  ).pack(side="left", padx=3)

                # ── Schieberegler ─────────────────────────────────────────────
                ctk.CTkFrame(sf, height=1, fg_color=CARD).grid(row=3, column=0, columnspan=3, sticky="ew", pady=6)
                ctk.CTkLabel(sf, text="Manuelle Einstellungen:",
                             font=ctk.CTkFont("Segoe UI", 11, "bold"), text_color=TEXT
                             ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(0,6))

                def _make_slider(r, key, label, min_v, max_v, init, hint):
                    ctk.CTkLabel(sf, text=label, font=ctk.CTkFont("Segoe UI", 11),
                                 text_color=TEXT, anchor="w", width=170
                                 ).grid(row=r, column=0, sticky="w", padx=(4,0), pady=(3,0))
                    val_lbl = ctk.CTkLabel(sf, text=str(init), width=28,
                                           font=ctk.CTkFont("Segoe UI", 11, "bold"), text_color=GREEN)
                    val_lbl.grid(row=r, column=1, sticky="w", padx=(6,4), pady=(3,0))
                    sl = ctk.CTkSlider(sf, from_=min_v, to=max_v,
                                       number_of_steps=max_v-min_v,
                                       button_color=GREEN, progress_color=GREEN, fg_color=CARD)
                    sl.set(init)
                    sl.grid(row=r, column=2, sticky="ew", padx=(0,6), pady=(3,0))
                    ctk.CTkLabel(sf, text=hint, font=ctk.CTkFont("Segoe UI", 9),
                                 text_color=TEXT_MUTED, anchor="w"
                                 ).grid(row=r+1, column=0, columnspan=3, sticky="w",
                                        padx=(4,0), pady=(0,4))
                    def _chg(v, lbl=val_lbl, k=key):
                        iv = int(round(float(v)))
                        lbl.configure(text=str(iv))
                        if k=="vd": _vd[0]=iv
                        elif k=="sd": _sd[0]=iv
                        elif k=="msr": _msr[0]=iv
                        elif k=="ea": _ea[0]=iv
                        elif k=="em": _em[0]=iv
                        elif k=="er": _er[0]=iv
                    sl.configure(command=_chg)
                    slider_refs[key] = (sl, val_lbl)

                _make_slider(5,  "vd",  "View-Distance",       2, 16, _vd[0],  "Sichtweite in Chunks  (Standard: 10 | Empfehlung: 6)")
                _make_slider(7,  "sd",  "Simulation-Distance", 1, 10, _sd[0],  "Aktiver Chunk-Radius für Mobs/Redstone  (Standard: 8 | Empfehlung: 4)")
                _make_slider(9,  "msr", "Mob-Spawn-Range",     1,  8, _msr[0], "Max. Spawn-Abstand in Chunks  (Standard: 6 | Empfehlung: 4)")
                _make_slider(11, "ea",  "Entity: Animals",     4, 64, _ea[0],  "Aktivierungsreichweite Tiere in Blöcken  (Standard: 32)")
                _make_slider(13, "em",  "Entity: Monsters",    4, 64, _em[0],  "Aktivierungsreichweite Monster  (Standard: 32)")
                _make_slider(15, "er",  "Entity: Raiders",     8, 96, _er[0],  "Aktivierungsreichweite Raids  (Standard: 48)")

                # ── Velocity ──────────────────────────────────────────────────
                ctk.CTkFrame(sf, height=1, fg_color=CARD).grid(row=17, column=0, columnspan=3, sticky="ew", pady=8)
                ctk.CTkLabel(sf, text="Velocity Proxy",
                             font=ctk.CTkFont("Segoe UI", 11, "bold"), text_color=TEXT
                             ).grid(row=18, column=0, columnspan=2, sticky="w")
                vel_lbl = ctk.CTkLabel(sf, text="", font=ctk.CTkFont("Segoe UI", 10),
                                       text_color=TEXT_MUTED)
                vel_lbl.grid(row=18, column=2, sticky="e", padx=4)

                vel_dest = Path(self.cfg.get("dir","")) / "velocity"

                def _dl_velocity():
                    vel_lbl.configure(text="Lade…", text_color="#f39c12")
                    def _do():
                        try:
                            r = requests.get(
                                "https://api.papermc.io/v2/projects/velocity",
                                timeout=10, headers={"User-Agent":"MineHostLocal/1.0"})
                            vers = r.json().get("versions", [])
                            if not vers: raise Exception("Keine Version")
                            ver = vers[-1]
                            r2 = requests.get(
                                f"https://api.papermc.io/v2/projects/velocity/versions/{ver}/builds",
                                timeout=10, headers={"User-Agent":"MineHostLocal/1.0"})
                            builds = r2.json().get("builds", [])
                            if not builds: raise Exception("Kein Build")
                            build = builds[-1]["build"]
                            url = (f"https://api.papermc.io/v2/projects/velocity"
                                   f"/versions/{ver}/builds/{build}"
                                   f"/downloads/velocity-{ver}-{build}.jar")
                            vel_dest.mkdir(parents=True, exist_ok=True)
                            out = vel_dest / f"velocity-{ver}-{build}.jar"
                            r3 = requests.get(url, timeout=120, stream=True,
                                              headers={"User-Agent":"MineHostLocal/1.0"})
                            r3.raise_for_status()
                            with open(out, "wb") as f:
                                for chunk in r3.iter_content(65536): f.write(chunk)
                            self.after(0, lambda: vel_lbl.configure(
                                text=f"✓ {out.name}", text_color=GREEN))
                        except Exception as ex:
                            self.after(0, lambda: vel_lbl.configure(
                                text=f"Fehler: {ex}", text_color=RED))
                    import threading as _th; _th.Thread(target=_do, daemon=True).start()

                ctk.CTkButton(sf, text="⬇ Velocity herunterladen", height=32,
                              fg_color=CARD, hover_color=GREEN, text_color=TEXT,
                              font=ctk.CTkFont("Segoe UI", 11), corner_radius=6,
                              command=_dl_velocity
                              ).grid(row=19, column=0, columnspan=3, sticky="ew", pady=(6,0), padx=4)

                # ── Anwenden ──────────────────────────────────────────────────
                ctk.CTkFrame(sf, height=1, fg_color=CARD).grid(row=20, column=0, columnspan=3, sticky="ew", pady=8)
                apply_lbl = ctk.CTkLabel(sf, text="", font=ctk.CTkFont("Segoe UI", 9),
                                         text_color=GREEN, wraplength=480, justify="left")
                apply_lbl.grid(row=22, column=0, columnspan=3, sticky="w", padx=4)

                def _do_apply():
                    self.cfg.update({"perf_vd":_vd[0],"perf_sd":_sd[0],"perf_msr":_msr[0],
                                     "perf_ea":_ea[0],"perf_em":_em[0],"perf_er":_er[0]})
                    save_server_cfg(self.server_name, self.cfg)
                    _apply_perf_config(_vd[0],_sd[0],_msr[0],_ea[0],_em[0],_er[0])
                    apply_lbl.configure(
                        text=(f"✓ view-distance={_vd[0]}  simulation-distance={_sd[0]}"
                              f"  mob-spawn-range={_msr[0]}\n"
                              f"  animals={_ea[0]}  monsters={_em[0]}  raiders={_er[0]}"
                              f"  → server.properties + spigot.yml aktualisiert"))

                ctk.CTkButton(sf, text="✅ Einstellungen anwenden", height=38,
                              fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                              font=ctk.CTkFont("Segoe UI", 12, "bold"), corner_radius=8,
                              command=_do_apply
                              ).grid(row=21, column=0, columnspan=3, sticky="ew", pady=(0,4), padx=4)

            # ── Sidebar-Panel für Performance-Kategorie ──────────────────────
            def _show_perf_panel():
                for w in scroll.winfo_children():
                    try: w.destroy()
                    except: pass

                vd2  = [int(self.cfg.get("perf_vd",  6))]
                sd2  = [int(self.cfg.get("perf_sd",  4))]
                msr2 = [int(self.cfg.get("perf_msr", 4))]
                ea2  = [int(self.cfg.get("perf_ea",  16))]
                em2  = [int(self.cfg.get("perf_em",  24))]
                er2  = [int(self.cfg.get("perf_er",  32))]
                sr2  = {}

                # Beschreibung
                ctk.CTkFrame(scroll, fg_color="#061206", corner_radius=8,
                             border_width=1, border_color="#1a3a1a",
                             height=2).pack(fill="x", padx=6, pady=(6,0))
                hdr_f = ctk.CTkFrame(scroll, fg_color="#061206", corner_radius=0)
                hdr_f.pack(fill="x", padx=6)
                ctk.CTkLabel(hdr_f, text="⚡ Server-Performance optimieren",
                             font=ctk.CTkFont("Segoe UI", 13, "bold"), text_color=GREEN
                             ).pack(side="left", padx=12, pady=(8,4))
                ctk.CTkFrame(scroll, fg_color="#061206", corner_radius=0,
                             height=2).pack(fill="x", padx=6, pady=(0,8))

                ctk.CTkLabel(scroll,
                    text="Besonders geeignet für Server mit sehr vielen gleichzeitigen Spielern (10+).\n"
                         "Reduziert CPU-Last durch kürzere Sichtweiten, kleinere Spawn-Radien und\n"
                         "optimierte Entitäts-Aktivierungszonen — ohne spürbaren Spielspaß-Verlust.",
                    font=ctk.CTkFont("Segoe UI", 11), text_color=TEXT_MUTED,
                    justify="left", anchor="w", wraplength=520
                    ).pack(fill="x", padx=12, pady=(0,10))

                # ── Auto-Presets ──────────────────────────────────────────────
                ctk.CTkLabel(scroll, text="📊 Geplante Spielerzahl:",
                             font=ctk.CTkFont("Segoe UI", 12, "bold"), text_color=TEXT, anchor="w"
                             ).pack(fill="x", padx=12, pady=(0,4))

                _PRESETS2 = [
                    ("1–10",  8, 6, 6, 32, 32, 48, "Spielspaß: hohe Sichtweite möglich"),
                    ("11–30", 6, 4, 4, 16, 24, 32, "Stabil: leichte Reduktion"),
                    ("31–60", 5, 3, 3, 12, 18, 24, "Performance: Mobs nur nah"),
                    ("60+",   4, 2, 2,  8, 12, 16, "Hardcore: Lobbys / Minigames"),
                ]

                def _apply2(vd, sd, msr, ea, em, er):
                    vd2[0]=vd; sd2[0]=sd; msr2[0]=msr
                    ea2[0]=ea; em2[0]=em; er2[0]=er
                    for k2, (sl2, lb2) in sr2.items():
                        v2 = {"vd":vd,"sd":sd,"msr":msr,"ea":ea,"em":em,"er":er}[k2]
                        sl2.set(v2); lb2.configure(text=str(v2))

                for (lp, vd, sd, msr, ea, em, er, tip) in _PRESETS2:
                    rf2 = ctk.CTkFrame(scroll, fg_color="transparent")
                    rf2.pack(fill="x", padx=12, pady=2)
                    ctk.CTkButton(rf2, text=lp, width=88, height=30,
                                  fg_color=CARD, hover_color=GREEN, text_color=TEXT,
                                  font=ctk.CTkFont("Segoe UI", 11), corner_radius=6,
                                  command=lambda v=vd,s=sd,m=msr,a=ea,mo=em,r=er: _apply2(v,s,m,a,mo,r)
                                  ).pack(side="left", padx=(0,10))
                    ctk.CTkLabel(rf2,
                                 text=f"View {vd}  •  Sim {sd}  •  Spawn {msr}  —  {tip}",
                                 font=ctk.CTkFont("Segoe UI", 10), text_color=TEXT_MUTED, anchor="w"
                                 ).pack(side="left")

                # ── Custom Schieberegler ──────────────────────────────────────
                ctk.CTkFrame(scroll, height=1, fg_color=CARD).pack(fill="x", padx=12, pady=10)
                ctk.CTkLabel(scroll, text="🔧 Custom Einstellungen:",
                             font=ctk.CTkFont("Segoe UI", 12, "bold"), text_color=TEXT, anchor="w"
                             ).pack(fill="x", padx=12, pady=(0,6))

                slf = ctk.CTkFrame(scroll, fg_color="transparent")
                slf.pack(fill="x", padx=12)
                slf.grid_columnconfigure(2, weight=1)

                def _mk(r2, key, label, lo, hi, init, hint):
                    ctk.CTkLabel(slf, text=label, font=ctk.CTkFont("Segoe UI",11),
                                 text_color=TEXT, anchor="w", width=175
                                 ).grid(row=r2, column=0, sticky="w", pady=(3,0))
                    vlbl = ctk.CTkLabel(slf, text=str(init), width=28,
                                       font=ctk.CTkFont("Segoe UI",11,"bold"), text_color=GREEN)
                    vlbl.grid(row=r2, column=1, sticky="w", padx=(6,4), pady=(3,0))
                    sl = ctk.CTkSlider(slf, from_=lo, to=hi, number_of_steps=hi-lo,
                                       button_color=GREEN, progress_color=GREEN, fg_color=CARD)
                    sl.set(init); sl.grid(row=r2, column=2, sticky="ew", padx=(0,6), pady=(3,0))
                    ctk.CTkLabel(slf, text=hint, font=ctk.CTkFont("Segoe UI",9),
                                 text_color=TEXT_MUTED, anchor="w"
                                 ).grid(row=r2+1, column=0, columnspan=3, sticky="w", pady=(0,3))
                    def _c(v, lb=vlbl, k=key):
                        iv=int(round(float(v))); lb.configure(text=str(iv))
                        if k=="vd": vd2[0]=iv
                        elif k=="sd": sd2[0]=iv
                        elif k=="msr": msr2[0]=iv
                        elif k=="ea": ea2[0]=iv
                        elif k=="em": em2[0]=iv
                        elif k=="er": er2[0]=iv
                    sl.configure(command=_c)
                    sr2[key] = (sl, vlbl)

                _mk(0,  "vd",  "View-Distance",       2, 16, vd2[0],  "Sichtweite in Chunks  (Standard: 10 | Empfehlung: 6)")
                _mk(2,  "sd",  "Simulation-Distance", 1, 10, sd2[0],  "Aktiver Chunk-Radius  (Standard: 8 | Empfehlung: 4)")
                _mk(4,  "msr", "Mob-Spawn-Range",     1,  8, msr2[0], "Max. Spawn-Abstand in Chunks  (Standard: 6 | Empfehlung: 4)")
                _mk(6,  "ea",  "Entity: Animals",     4, 64, ea2[0],  "Aktivierungsreichweite Tiere  (Standard: 32)")
                _mk(8,  "em",  "Entity: Monsters",    4, 64, em2[0],  "Aktivierungsreichweite Monster  (Standard: 32)")
                _mk(10, "er",  "Entity: Raiders",     8, 96, er2[0],  "Aktivierungsreichweite Raids  (Standard: 48)")

                # ── Anwenden ──────────────────────────────────────────────────
                ctk.CTkFrame(scroll, height=1, fg_color=CARD).pack(fill="x", padx=12, pady=10)
                albl2 = ctk.CTkLabel(scroll, text="", font=ctk.CTkFont("Segoe UI",9),
                                     text_color=GREEN, wraplength=500, justify="left")

                def _do2():
                    self.cfg.update({"perf_vd":vd2[0],"perf_sd":sd2[0],"perf_msr":msr2[0],
                                     "perf_ea":ea2[0],"perf_em":em2[0],"perf_er":er2[0]})
                    save_server_cfg(self.server_name, self.cfg)
                    _apply_perf_config(vd2[0],sd2[0],msr2[0],ea2[0],em2[0],er2[0])
                    albl2.configure(
                        text=(f"✓ view-distance={vd2[0]}  simulation-distance={sd2[0]}"
                              f"  mob-spawn-range={msr2[0]}\n"
                              f"  animals={ea2[0]}  monsters={em2[0]}  raiders={er2[0]}"
                              f"  → server.properties + spigot.yml aktualisiert"))

                ctk.CTkButton(scroll, text="✅ Einstellungen anwenden", height=38,
                              fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                              font=ctk.CTkFont("Segoe UI",12,"bold"), corner_radius=8,
                              command=_do2
                              ).pack(fill="x", padx=12, pady=(0,4))
                albl2.pack(fill="x", padx=12, pady=(0,12))

            _perf_panel_fn = [_show_perf_panel]

            _perf_jars = _get_perf_jars()
            _perf_active = bool(self.cfg.get("perf_mode", False))
            _perf_bar = ctk.CTkFrame(outer, fg_color="#061206", corner_radius=8,
                                     border_width=1, border_color="#1a3a1a")
            _perf_bar.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0,4))
            _perf_bar.grid_columnconfigure(2, weight=1)

            ctk.CTkLabel(_perf_bar, text="⚡ Performance Modus",
                         font=ctk.CTkFont("Segoe UI", 12, "bold"), text_color=GREEN
                         ).grid(row=0, column=0, padx=(12,8), pady=7, sticky="w")
            ctk.CTkSwitch(_perf_bar, text="", variable=_perf_enabled, width=46, height=22,
                          fg_color=CARD, progress_color=GREEN,
                          button_color="#ccc", button_hover_color=GREEN,
                          command=_toggle_perf
                          ).grid(row=0, column=1, padx=(0,6), pady=7)

            _jar_label_txt = "  •  ".join(j.stem for j in _perf_jars) if _perf_jars else "Keine Plugins in perf_plugins/"
            ctk.CTkLabel(_perf_bar, text=_jar_label_txt,
                         font=ctk.CTkFont("Segoe UI", 10), text_color="#507050", anchor="w"
                         ).grid(row=0, column=2, padx=4, pady=7, sticky="w")

            _init_status = f"✓ {len(_perf_jars)} aktiv" if _perf_active else "Deaktiviert"
            _perf_status_lbl = ctk.CTkLabel(_perf_bar, text=_init_status,
                                            font=ctk.CTkFont("Segoe UI", 10),
                                            text_color=GREEN if _perf_active else TEXT_MUTED)
            _perf_status_lbl.grid(row=0, column=3, padx=(4,4), pady=7)

            ctk.CTkButton(_perf_bar, text="⚙ Einstellungen", width=110, height=26,
                          fg_color=CARD, hover_color=GREEN, text_color=TEXT_MUTED,
                          font=ctk.CTkFont("Segoe UI", 10), corner_radius=6,
                          command=_open_perf_settings
                          ).grid(row=0, column=4, padx=(4,12), pady=7)

        use_cf = not is_mod

        # API-Key Warnung wenn kein Key
        if use_cf and not CF_KEY:
            key_bar = ctk.CTkFrame(outer, fg_color="#1a1a2a", corner_radius=6)
            key_bar.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0,4))
            key_bar.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(key_bar,
                text="🔑 CurseForge API-Key nötig: console.curseforge.com → API Keys → Create",
                text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10)
                ).grid(row=0, column=0, padx=10, pady=6, sticky="w")
            key_entry = ctk.CTkEntry(key_bar, placeholder_text="API-Key eingeben…",
                                     fg_color=CARD, text_color=TEXT, height=28, width=300)
            key_entry.grid(row=0, column=1, padx=6, sticky="e")
            def _save_key():
                k = key_entry.get().strip()
                if k:
                    self.cfg["curseforge_api_key"] = k
                    save_server_cfg(self.server_name, self.cfg)
                    self._show("plugins")  # Seite neu laden
            ctk.CTkButton(key_bar, text="Speichern", width=80, height=28,
                          fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                          font=ctk.CTkFont("Segoe UI",10,"bold"), corner_radius=6,
                          command=_save_key).grid(row=0, column=2, padx=8)

        # Server läuft Hinweis
        _is_running = self.proc is not None and self.proc.poll() is None
        if _is_running:
            warn = ctk.CTkFrame(outer, fg_color="#1a1a0a", corner_radius=6)
            warn.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0,4))
            ctk.CTkLabel(warn, text="⚠??  Server läuft — Plugins erst nach Neustart aktiv.",
                         text_color="#f39c12", font=ctk.CTkFont("Segoe UI",10)
                         ).pack(side="left", padx=10, pady=5)
            ctk.CTkButton(warn, text="🔄 Neu starten", height=24, width=100,
                          fg_color=RED, hover_color=RED_HOV, text_color="#fff",
                          font=ctk.CTkFont("Segoe UI",9,"bold"), corner_radius=6,
                          command=lambda: (self._stop(), self.after(1500, self._start))
                          ).pack(side="right", padx=8, pady=4)

        _sel_category = [None]
        _cat_vars: dict = {}

        # ── Kategorie-Sidebar ────────────────────────────────────────────────
        sidebar = ctk.CTkFrame(outer, fg_color=SIDEBAR_BG, corner_radius=0, width=210)
        sidebar.grid(row=3, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        sh = ctk.CTkFrame(sidebar, fg_color=CARD, corner_radius=0, height=38)
        sh.pack(fill="x")
        sh.pack_propagate(False)
        ctk.CTkLabel(sh, text="Categories  ∧",
                     font=ctk.CTkFont("Segoe UI",12,"bold"), text_color=TEXT
                     ).pack(side="left", padx=12, pady=9)

        cats_sf = ctk.CTkScrollableFrame(sidebar, fg_color="transparent")
        cats_sf.pack(fill="both", expand=True, padx=4, pady=4)

        def _on_cat(cat_id, var):
            if var.get():
                for k, v in _cat_vars.items():
                    if k != cat_id: v.set(False)
                _sel_category[0] = cat_id
            else:
                _sel_category[0] = None
            if cat_id == "__perf__" and var.get():
                _perf_panel_fn[0]()
            else:
                _do_search(search_entry.get())

        def _update_sidebar(src):
            """Kategorien je nach Quelle aktualisieren."""
            for w in cats_sf.winfo_children(): w.destroy()
            _cat_vars.clear()
            _sel_category[0] = None
            # ⚡ Performance-Kategorie ganz oben (wenn Modus aktiv)
            if not is_mod and self.cfg.get("perf_mode", False):
                pv = ctk.BooleanVar()
                _cat_vars["__perf__"] = pv
                ctk.CTkCheckBox(cats_sf, text="⚡ Performance",
                                variable=pv, text_color=GREEN,
                                fg_color=GREEN, hover_color=GREEN_HOV,
                                font=ctk.CTkFont("Segoe UI", 11, "bold"),
                                command=lambda v=pv: _on_cat("__perf__", v)
                                ).pack(anchor="w", pady=(4,2), padx=4)
                ctk.CTkFrame(cats_sf, height=1, fg_color=CARD
                             ).pack(fill="x", padx=4, pady=(4,6))
            if src == "curseforge":
                cats = CF_MOD_CATEGORIES if is_mod else CF_CATEGORIES
            elif src == "modrinth":
                cats = MR_MOD_CATEGORIES if is_mod else MR_CATEGORIES
            else:
                cats = []
            for cat_name, cat_id in cats:
                var = ctk.BooleanVar()
                _cat_vars[cat_id] = var
                ctk.CTkCheckBox(cats_sf, text=cat_name, variable=var,
                                 text_color=TEXT, fg_color=GREEN, hover_color=GREEN_HOV,
                                 font=ctk.CTkFont("Segoe UI",11),
                                 command=lambda cid=cat_id, v=var: _on_cat(cid, v)
                                 ).pack(anchor="w", pady=2, padx=4)

        # Initial: Kategorien für aktive Quelle laden
        _update_sidebar(_source[0])

        # ── Plugin-Grid Bereich rechts ────────────────────────────────────────
        right = ctk.CTkFrame(outer, fg_color="transparent")
        right.grid(row=3, column=1, sticky="nsew")
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(right, fg_color="transparent")
        scroll.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)

        detail_panel = [None]

        def _show_grid(items):
            """Plugin-Karten vertikal in den Scroll-Frame packen."""
            for w in scroll.winfo_children():
                try: w.destroy()
                except: pass

            if not items:
                ctk.CTkLabel(scroll, text="Keine Ergebnisse.",
                             text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",13)).pack(pady=30)
                return

            # Jede Karte direkt in scroll packen
            for item in items:
                def _open(it=item): _show_detail(it)

                card = ctk.CTkFrame(scroll, fg_color=GREEN, corner_radius=8, cursor="hand2")
                card.pack(fill="x", padx=6, pady=3)

                title_lbl = ctk.CTkLabel(card, text=item["title"],
                             font=ctk.CTkFont("Segoe UI",12,"bold"),
                             text_color="#000", anchor="w")
                title_lbl.pack(fill="x", padx=10, pady=(8,2))

                desc = (item.get("description","") or "")
                if len(desc) > 100: desc = desc[:97] + "…"
                desc_lbl = ctk.CTkLabel(card, text=desc,
                             font=ctk.CTkFont("Segoe UI",9), text_color="#003300",
                             anchor="w", justify="left")
                desc_lbl.pack(fill="x", padx=10, pady=(0,4))

                dl = item.get("downloads", 0)
                meta_txt = (f"⬇ {dl:,}  " if dl else "") + item.get("origin","")
                meta_lbl = ctk.CTkLabel(card, text=meta_txt,
                             font=ctk.CTkFont("Segoe UI",8), text_color="#005500",
                             anchor="w")
                meta_lbl.pack(fill="x", padx=10, pady=(0,6))

                # Löschen-Button für lokale Uploads (origin="Lokal" / jar_path gesetzt)
                if item.get("origin") == "Lokal" or item.get("jar_path"):
                    jar = Path(item["jar_path"]) if item.get("jar_path") else None
                    def _del_jar(j=jar, it=item):
                        if not j or not messagebox.askyesno("Löschen", f"'{it['title']}' löschen?"): return
                        try: j.unlink()
                        except Exception as ex: messagebox.showerror("Fehler", str(ex)); return
                        d = _load_meta(); d.pop(j.name, None); _save_meta(d)
                        _show_uploads()
                    ctk.CTkButton(card, text="🗑", width=32, height=26,
                                  fg_color="#3a1010", hover_color="#5a1a1a", text_color=RED,
                                  font=ctk.CTkFont("Segoe UI",11), corner_radius=4,
                                  command=_del_jar).pack(anchor="e", padx=10, pady=(0,6))
                else:
                    for w in [card, title_lbl, desc_lbl, meta_lbl]:
                        try: w.bind("<Button-1>", lambda e, fn=_open: fn())
                        except: pass

        def _show_custom_category(cat_id):
            """Zeigt Plugins einer Custom-Kategorie mit + Button."""
            for w in scroll.winfo_children():
                try: w.destroy()
                except: pass
            # Pagination entfernen
            for w in right.winfo_children():
                if getattr(w, "_is_pagination", False):
                    try: w.destroy()
                    except: pass

            cats = self._load_custom_cats()
            cat  = next((c for c in cats if c["id"] == cat_id), None)
            if not cat:
                return

            # Header mit + und 🗑 Kategorie-Buttons
            hdr = ctk.CTkFrame(scroll, fg_color="transparent")
            hdr.pack(fill="x", padx=6, pady=(6,10))
            hdr.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(hdr, text=cat["name"],
                         font=ctk.CTkFont("Segoe UI",15,"bold"), text_color=GREEN,
                         anchor="w").grid(row=0, column=0, sticky="w")
            def _del_cat():
                if messagebox.askyesno("Kategorie löschen", f"'{cat['name']}' und alle Einträge löschen?"):
                    cats2 = [c for c in self._load_custom_cats() if c["id"] != cat_id]
                    self._save_custom_cats(cats2)
                    self._show("plugins")
            ctk.CTkButton(hdr, text="🗑", width=32, height=28,
                          fg_color="#3a1010", text_color=RED, corner_radius=4,
                          command=_del_cat).grid(row=0, column=1, padx=(4,0))
            ctk.CTkButton(hdr, text="＋ Plugin hinzufügen", height=32, corner_radius=8,
                          fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                          font=ctk.CTkFont("Segoe UI",11,"bold"),
                          command=lambda: _add_to_category_popup(cat_id)
                          ).grid(row=0, column=2, padx=(8,0))

            q = search_entry.get().strip().lower()
            plugins = [p for p in cat.get("plugins",[])
                       if not q or q in p.get("title","").lower()]

            if not plugins:
                ctk.CTkLabel(scroll, text="Noch keine Plugins. Klicke '＋ Plugin hinzufügen'.",
                             text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",12)
                             ).pack(pady=30)
                return

            for item in plugins:
                def _open(it=item, cid=cat_id): _show_custom_detail(it, cid)
                card = ctk.CTkFrame(scroll, fg_color=GREEN, corner_radius=8, cursor="hand2")
                card.pack(fill="x", padx=6, pady=3)
                ctk.CTkLabel(card, text=item["title"],
                             font=ctk.CTkFont("Segoe UI",12,"bold"),
                             text_color="#000", anchor="w").pack(fill="x", padx=10, pady=(8,2))
                desc = (item.get("description","") or "")[:100]
                ctk.CTkLabel(card, text=desc,
                             font=ctk.CTkFont("Segoe UI",9), text_color="#003300",
                             anchor="w").pack(fill="x", padx=10, pady=(0,4))
                foot = ctk.CTkFrame(card, fg_color="transparent")
                foot.pack(fill="x", padx=10, pady=(0,6))
                foot.grid_columnconfigure(0, weight=1)
                ctk.CTkLabel(foot, text=item.get("origin",""),
                             font=ctk.CTkFont("Segoe UI",8), text_color="#005500",
                             anchor="w").grid(row=0, column=0, sticky="w")
                def _del_plugin(it=item, cid=cat_id):
                    cats2 = self._load_custom_cats()
                    for c in cats2:
                        if c["id"] == cid:
                            c["plugins"] = [p for p in c["plugins"] if p.get("title") != it["title"]]
                    self._save_custom_cats(cats2)
                    _show_custom_category(cid)
                ctk.CTkButton(foot, text="✕", width=28, height=22,
                              fg_color="#3a1010", text_color=RED, corner_radius=4,
                              command=_del_plugin).grid(row=0, column=1)
                for w in [card]:
                    try: w.bind("<Button-1>", lambda e, fn=_open: fn())
                    except: pass

        def _show_custom_detail(item, cat_id):
            """Detail-Ansicht für Custom-Category-Plugins mit Versionen."""
            _show_detail(item)  # nutzt die normale Detail-Ansicht

        def _add_to_category_popup(cat_id):
            """Popup zum Hinzufügen: URL oder Datei-Upload."""
            cats = self._load_custom_cats()
            cat  = next((c for c in cats if c["id"] == cat_id), None)
            if not cat: return

            win = ctk.CTkToplevel(self)
            win.title(f"Plugin zu '{cat['name']}' hinzufügen")
            win.geometry("520x400")
            win.configure(fg_color=BG)
            win.lift(); win.focus_force(); win.grab_set()

            ctk.CTkLabel(win, text="Wie möchtest du das Plugin hinzufügen?",
                         font=ctk.CTkFont("Segoe UI",14,"bold"), text_color=TEXT).pack(pady=(16,12))

            tab_f = ctk.CTkFrame(win, fg_color="transparent")
            tab_f.pack(fill="x", padx=20)
            mode = [0]  # 0=URL, 1=Upload
            tab_f.grid_columnconfigure((0,1), weight=1)
            t1 = ctk.CTkButton(tab_f, text="🔗 Link eingeben", height=36,
                               fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                               font=ctk.CTkFont("Segoe UI",11,"bold"), corner_radius=8)
            t2 = ctk.CTkButton(tab_f, text="⬆ Datei hochladen", height=36,
                               fg_color=CARD, hover_color=BORDER, text_color=TEXT_MUTED,
                               font=ctk.CTkFont("Segoe UI",11), corner_radius=8)
            t1.grid(row=0, column=0, padx=(0,4), sticky="ew")
            t2.grid(row=0, column=1, padx=(4,0), sticky="ew")

            content = ctk.CTkFrame(win, fg_color="transparent")
            content.pack(fill="both", expand=True, padx=20, pady=12)
            status_lbl = ctk.CTkLabel(win, text="", font=ctk.CTkFont("Segoe UI",10), text_color=TEXT_MUTED)
            status_lbl.pack()

            def _build_url_mode():
                for w in content.winfo_children(): w.destroy()
                content.grid_columnconfigure(0, weight=1)
                ctk.CTkLabel(content, text="Plugin-URL (jede Webseite erlaubt):",
                             font=ctk.CTkFont("Segoe UI",11), text_color=TEXT_MUTED,
                             anchor="w").pack(anchor="w", pady=(0,4))
                url_e = ctk.CTkEntry(content, placeholder_text="https://modrinth.com/plugin/…",
                                     fg_color="#111", text_color=TEXT, height=36)
                url_e.pack(fill="x"); url_e.focus()

                def _fetch():
                    url = url_e.get().strip()
                    if not url.startswith("http"):
                        status_lbl.configure(text="Bitte gültige URL eingeben.", text_color=RED); return
                    status_lbl.configure(text="Lade Info…", text_color=TEXT_MUTED)
                    win.update_idletasks()
                    def _do():
                        item = _scrape_plugin_url(url)
                        if item:
                            cats2 = self._load_custom_cats()
                            for c in cats2:
                                if c["id"] == cat_id:
                                    if not any(p.get("title")==item["title"] for p in c["plugins"]):
                                        c["plugins"].append(item)
                            self._save_custom_cats(cats2)
                            self.after(0, lambda: (
                                status_lbl.configure(text=f'"{item["title"]}" hinzugefuegt!', text_color=GREEN),
                                _show_custom_category(cat_id)
                            ))
                        else:
                            self.after(0, lambda: status_lbl.configure(
                                text="Fehler beim Laden.", text_color=RED))
                    threading.Thread(target=_do, daemon=True).start()

                ctk.CTkButton(content, text="Hinzufügen", fg_color=GREEN, hover_color=GREEN_HOV,
                              text_color="#000", height=36, corner_radius=8,
                              font=ctk.CTkFont("Segoe UI",12,"bold"), command=_fetch
                              ).pack(fill="x", pady=8)
                win.bind("<Return>", lambda e: _fetch())

            def _build_upload_mode():
                for w in content.winfo_children(): w.destroy()
                ctk.CTkLabel(content, text="JAR-Datei auswählen:",
                             font=ctk.CTkFont("Segoe UI",11), text_color=TEXT_MUTED,
                             anchor="w").pack(anchor="w", pady=(0,4))
                jar_lbl = ctk.CTkLabel(content, text="Keine Datei ausgewählt",
                                       text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10))
                jar_lbl.pack(anchor="w")
                jar_path = [None]

                def _pick():
                    p = filedialog.askopenfilename(filetypes=[("JAR","*.jar"),("Alle","*.*")])
                    if p:
                        jar_path[0] = p
                        jar_lbl.configure(text=Path(p).name, text_color=TEXT)

                ctk.CTkButton(content, text="Datei wählen…", fg_color=CARD, hover_color=BORDER,
                              text_color=TEXT, height=32, corner_radius=6, command=_pick
                              ).pack(anchor="w", pady=(4,8))

                def row(lbl, ph):
                    f = ctk.CTkFrame(content, fg_color="transparent"); f.pack(fill="x", pady=2)
                    ctk.CTkLabel(f, text=lbl, width=90, anchor="w",
                                 text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10)).pack(side="left")
                    e = ctk.CTkEntry(f, placeholder_text=ph, fg_color="#111", text_color=TEXT, height=28)
                    e.pack(side="left", fill="x", expand=True)
                    return e

                e_name = row("Name", "z.B. WorldEdit")
                e_ver  = row("Version", "z.B. 7.3.1")
                e_desc = row("Beschreibung", "optional")

                def _upload():
                    name = e_name.get().strip()
                    if not name or not jar_path[0]:
                        status_lbl.configure(text="Name und Datei sind Pflicht.", text_color=RED); return
                    dst = folder / Path(jar_path[0]).name
                    try: shutil.copy(jar_path[0], dst)
                    except Exception as ex:
                        status_lbl.configure(text=f"Fehler: {ex}", text_color=RED); return
                    item = {"title": name, "description": e_desc.get().strip(),
                            "version": e_ver.get().strip(), "jar_path": str(dst),
                            "source": "upload", "origin": "Lokal"}
                    cats2 = self._load_custom_cats()
                    for c in cats2:
                        if c["id"] == cat_id:
                            c["plugins"].append(item)
                    self._save_custom_cats(cats2)
                    status_lbl.configure(text=f'"{name}" hochgeladen!', text_color=GREEN)
                    _show_custom_category(cat_id)

                ctk.CTkButton(content, text="Hochladen & Hinzufügen",
                              fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                              height=36, corner_radius=8, font=ctk.CTkFont("Segoe UI",12,"bold"),
                              command=_upload).pack(fill="x", pady=8)

            def _set_mode(m):
                mode[0] = m
                t1.configure(fg_color=GREEN if m==0 else CARD, text_color="#000" if m==0 else TEXT_MUTED)
                t2.configure(fg_color=GREEN if m==1 else CARD, text_color="#000" if m==1 else TEXT_MUTED)
                if m == 0: _build_url_mode()
                else:      _build_upload_mode()

            t1.configure(command=lambda: _set_mode(0))
            t2.configure(command=lambda: _set_mode(1))
            _build_url_mode()

        def _show_uploads():
            """Zeigt alle hochgeladenen/installierten Plugins mit Löschen-Button."""
            for w in scroll.winfo_children():
                try: w.destroy()
                except: pass
            for w in right.winfo_children():
                if getattr(w, "_is_pagination", False):
                    try: w.destroy()
                    except: pass

            meta  = _load_meta()
            jars  = sorted(folder.glob("*.jar"))
            q     = search_entry.get().strip().lower()

            if not jars:
                ctk.CTkLabel(scroll, text="Keine installierten Plugins vorhanden.",
                             text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",13)).pack(pady=30)
                return

            for j in jars:
                m = meta.get(j.name, {})
                name = m.get("name", j.stem)
                if q and q not in name.lower(): continue

                card = ctk.CTkFrame(scroll, fg_color=CARD, corner_radius=8)
                card.pack(fill="x", padx=6, pady=3)
                card.grid_columnconfigure(0, weight=1)

                ctk.CTkLabel(card, text=name,
                             font=ctk.CTkFont("Segoe UI",12,"bold"),
                             text_color=TEXT, anchor="w"
                             ).grid(row=0, column=0, padx=10, pady=(8,2), sticky="w")

                info = f"{m.get('version','')}  •  {j.name}  •  {j.stat().st_size//1024} kB"
                ctk.CTkLabel(card, text=info.strip(" • "),
                             font=ctk.CTkFont("Segoe UI",9), text_color=TEXT_MUTED,
                             anchor="w").grid(row=1, column=0, padx=10, pady=(0,6), sticky="w")

                def _del(jar=j):
                    if messagebox.askyesno("Plugin löschen",
                                           f"'{jar.name}' wirklich löschen?"):
                        try: jar.unlink()
                        except Exception as ex:
                            messagebox.showerror("Fehler", str(ex)); return
                        d = _load_meta(); d.pop(jar.name, None); _save_meta(d)
                        _show_uploads()

                ctk.CTkButton(card, text="🗑 Löschen", width=90, height=28,
                              fg_color="#3a1010", hover_color="#5a1a1a", text_color=RED,
                              font=ctk.CTkFont("Segoe UI",10), corner_radius=6,
                              command=_del).grid(row=0, column=1, rowspan=2, padx=(6,10))

        def _show_add_link_popup():
            """Popup 'Neue Plugins?' — URL eingeben, App scrapt Info automatisch."""
            win = ctk.CTkToplevel(self)
            win.title("Neue Plugins?")
            win.geometry("560x480")
            win.configure(fg_color=BG)
            win.lift(); win.focus_force(); win.grab_set()

            ctk.CTkLabel(win, text="Neue Plugins?",
                         font=ctk.CTkFont("Segoe UI",17,"bold"), text_color=GREEN
                         ).pack(pady=(18,2))
            ctk.CTkLabel(win,
                text="Link einfügen — von jeder Seite (Modrinth, CurseForge, Hangar, GitHub, SpigotMC, …)",
                font=ctk.CTkFont("Segoe UI",10), text_color=TEXT_MUTED).pack()

            url_f = ctk.CTkFrame(win, fg_color="transparent")
            url_f.pack(fill="x", padx=20, pady=12)
            url_f.grid_columnconfigure(0, weight=1)
            url_e = ctk.CTkEntry(url_f, placeholder_text="https://modrinth.com/plugin/…",
                                 fg_color="#111", text_color=TEXT, height=36)
            url_e.grid(row=0, column=0, sticky="ew", padx=(0,6))
            status_lbl = ctk.CTkLabel(win, text="", font=ctk.CTkFont("Segoe UI",10),
                                      text_color=TEXT_MUTED)
            status_lbl.pack()

            # Liste bereits gespeicherter Links
            list_f = ctk.CTkScrollableFrame(win, fg_color=CARD, corner_radius=8)
            list_f.pack(fill="both", expand=True, padx=20, pady=(8,4))

            def _refresh_list():
                for w in list_f.winfo_children():
                    try: w.destroy()
                    except: pass
                db = self._load_script_db()
                if not db:
                    ctk.CTkLabel(list_f, text="Noch keine Links gespeichert.",
                                 text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10)
                                 ).pack(pady=12)
                    return
                for entry in db:
                    row = ctk.CTkFrame(list_f, fg_color="#1a1a1a", corner_radius=6)
                    row.pack(fill="x", pady=2, padx=4)
                    row.grid_columnconfigure(0, weight=1)
                    ctk.CTkLabel(row, text=entry.get("title","?"),
                                 font=ctk.CTkFont("Segoe UI",11,"bold"), text_color=GREEN,
                                 anchor="w").grid(row=0, column=0, padx=8, pady=(6,0), sticky="w")
                    ctk.CTkLabel(row, text=entry.get("origin",""),
                                 font=ctk.CTkFont("Segoe UI",9), text_color=TEXT_MUTED,
                                 anchor="w").grid(row=1, column=0, padx=8, pady=(0,6), sticky="w")
                    def _del(e=entry):
                        db2 = self._load_script_db()
                        self._save_script_db([x for x in db2 if x.get("title") != e.get("title")])
                        _refresh_list()
                        _do_search("", 0)
                    ctk.CTkButton(row, text="✕", width=28, height=28,
                                  fg_color="#3a1010", text_color=RED, corner_radius=4,
                                  command=_del).grid(row=0, column=1, rowspan=2, padx=6)

            _refresh_list()

            def _fetch_and_add():
                url = url_e.get().strip()
                if not url or not url.startswith("http"):
                    status_lbl.configure(text="Bitte eine gültige URL eingeben.", text_color=RED)
                    return
                status_lbl.configure(text="Lade Info…", text_color=TEXT_MUTED)
                win.update_idletasks()

                def _do():
                    item = _scrape_plugin_url(url)
                    if item:
                        db = self._load_script_db()
                        if not any(e.get("title") == item["title"] for e in db):
                            db.append(item)
                            self._save_script_db(db)
                        self.after(0, lambda: (
                            status_lbl.configure(text=f'"{item["title"]}" hinzugefuegt!', text_color=GREEN),
                            url_e.delete(0,"end"),
                            _refresh_list(),
                            _do_search("", 0)
                        ))
                    else:
                        self.after(0, lambda: status_lbl.configure(
                            text="Info konnte nicht geladen werden.", text_color=RED))

                threading.Thread(target=_do, daemon=True).start()

            add_btn = ctk.CTkButton(url_f, text="Hinzufügen", width=110, height=36,
                                    fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                                    font=ctk.CTkFont("Segoe UI",12,"bold"), corner_radius=6,
                                    command=_fetch_and_add)
            add_btn.grid(row=0, column=1)
            win.bind("<Return>", lambda e: _fetch_and_add())

        def _scrape_plugin_url(url: str) -> dict | None:
            """Holt Plugin-Info von einer URL — erkennt bekannte Sites automatisch."""
            import urllib.parse as _up
            try:
                parsed = _up.urlparse(url)
                domain = parsed.netloc.lower().replace("www.","")
                path   = parsed.path.strip("/")
                parts  = path.split("/")
                hdrs   = {"User-Agent": "MineHostLocal/1.0"}

                # ── Modrinth ──────────────────────────────────────────────────
                if "modrinth.com" in domain:
                    slug = parts[1] if len(parts) >= 2 else parts[0]
                    r = requests.get(f"https://api.modrinth.com/v2/project/{slug}",
                                     headers=hdrs, timeout=8)
                    d = r.json()
                    return {"title": d.get("title", slug),
                            "description": d.get("description",""),
                            "slug": slug, "website": url,
                            "source": "script", "origin": "modrinth.com",
                            "downloads": d.get("downloads", 0)}

                # ── Hangar ────────────────────────────────────────────────────
                if "hangar.papermc.io" in domain and len(parts) >= 2:
                    owner, slug = parts[0], parts[1]
                    r = requests.get(f"https://hangar.papermc.io/api/v1/projects/{owner}/{slug}",
                                     headers=hdrs, timeout=8)
                    d = r.json()
                    return {"title": d.get("name", slug),
                            "description": d.get("description",""),
                            "hangar_owner": owner, "hangar_slug": slug,
                            "website": url, "source": "script", "origin": "hangar.papermc.io",
                            "downloads": d.get("stats",{}).get("downloads",0)}

                # ── GitHub ────────────────────────────────────────────────────
                if "github.com" in domain and len(parts) >= 2:
                    owner, repo = parts[0], parts[1]
                    r = requests.get(f"https://api.github.com/repos/{owner}/{repo}",
                                     headers={"User-Agent": "MineHostLocal/1.0",
                                              "Accept": "application/vnd.github+json"}, timeout=8)
                    d = r.json()
                    return {"title": d.get("name", repo),
                            "description": d.get("description",""),
                            "website": url, "source": "script", "origin": "github.com",
                            "github_owner": owner, "github_repo": repo, "downloads": 0}

                # ── CurseForge (URL → Slug → API) ─────────────────────────────
                if "curseforge.com" in domain:
                    slug = parts[-1] if parts else ""
                    r = requests.get("https://api.curseforge.com/v1/mods/search",
                                     params={"gameId": 432, "classId": 5,
                                             "searchFilter": slug, "pageSize": 1},
                                     headers={"x-api-key": CF_KEY,
                                              "Accept": "application/json",
                                              "User-Agent": "MineHostLocal/1.0"}, timeout=8)
                    mods = r.json().get("data", [])
                    if mods:
                        m = mods[0]
                        return {"title": m.get("name","?"),
                                "description": m.get("summary",""),
                                "cf_id": m.get("id"), "website": url,
                                "source": "script", "origin": "curseforge.com",
                                "downloads": m.get("downloadCount",0)}

                # ── SpigotMC ──────────────────────────────────────────────────
                if "spigotmc.org" in domain:
                    rid = next((p for p in parts if p.isdigit()), None)
                    if rid:
                        r = requests.get(f"https://api.spiget.org/v2/resources/{rid}",
                                         headers={"User-Agent": "MineHostLocal/1.0"}, timeout=8)
                        d = r.json()
                        return {"title": d.get("name","Resource "+rid),
                                "description": d.get("tag",""),
                                "website": url, "source": "script", "origin": "spigotmc.org",
                                "downloads": d.get("downloads",0)}

                # ── Fallback: HTML title + meta description ────────────────────
                r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                text = r.text[:40000]
                import re as _re
                title = (_re.search(r"<title[^>]*>([^<]+)</title>", text, _re.I) or ["",""])[1].strip()

                # Cloudflare/Bot-Schutz erkennen → abbrechen
                if any(x in title.lower() for x in ("cloudflare", "attention required",
                                                      "just a moment", "ddos-guard",
                                                      "access denied", "403 forbidden")):
                    return None

                desc = ""
                m = _re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', text, _re.I)
                if not m:
                    m = _re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']description', text, _re.I)
                if m: desc = m.group(1).strip()
                if not title or title == url:
                    return None  # Kein sinnvoller Titel → nicht speichern
                return {"title": title, "description": desc,
                        "website": url, "source": "script", "origin": domain, "downloads": 0}
            except Exception as e:
                return None

        def _show_detail(item):
            """Plugin-Detail wie CurseForge: Titel, Beschreibung, Versionen-Liste."""
            win = ctk.CTkToplevel(self)
            win.title(item["title"])
            win.geometry("1100x720")
            win.configure(fg_color=BG)
            win.lift(); win.focus_force()
            win.attributes("-topmost", True)
            win.after(300, lambda: win.attributes("-topmost", False))
            win.grab_set()

            srv_mc_ver = self.cfg.get("mc_version","")  # Server MC-Version für Farbmarkierung

            # ── Header: Suche oben rechts ──────────────────────────────────────
            hdr = ctk.CTkFrame(win, fg_color="transparent")
            hdr.pack(fill="x", padx=20, pady=(16,0))
            hdr.grid_columnconfigure(0, weight=1)

            title_col = GREEN
            ctk.CTkLabel(hdr, text=item["title"],
                         font=ctk.CTkFont("Segoe UI",22,"bold"), text_color=title_col,
                         anchor="w").grid(row=0, column=0, sticky="w")

            # ── Beschreibung + Autor + Link ───────────────────────────────────
            if item.get("description"):
                ctk.CTkLabel(win, text=item["description"],
                             font=ctk.CTkFont("Segoe UI",11), text_color=TEXT_MUTED,
                             wraplength=900, justify="left", anchor="w"
                             ).pack(padx=20, pady=(4,0), anchor="w")

            meta_row = ctk.CTkFrame(win, fg_color="transparent")
            meta_row.pack(padx=16, anchor="w", pady=2)

            # Autor anzeigen
            author = (item.get("author") or item.get("hangar_owner") or
                      item.get("origin","").split(".")[0] or "")
            if author:
                ctk.CTkLabel(meta_row, text=f"👤 {author}",
                             font=ctk.CTkFont("Segoe UI",10), text_color=TEXT_MUTED
                             ).pack(side="left", padx=(0,12))

            if item.get("downloads"):
                ctk.CTkLabel(meta_row, text=f"⬇ {item['downloads']:,} Downloads",
                             font=ctk.CTkFont("Segoe UI",10), text_color=TEXT_MUTED
                             ).pack(side="left", padx=(0,12))

            if item.get("website"):
                ctk.CTkButton(meta_row, text=f"?? Originalseite", height=22,
                              fg_color="transparent", text_color=BLUE,
                              font=ctk.CTkFont("Segoe UI",10), anchor="w",
                              command=lambda u=item["website"]: __import__("webbrowser").open(u)
                              ).pack(side="left")

            # ── "Versionen" Header ─────────────────────────────────────────────
            vh = ctk.CTkFrame(win, fg_color="transparent")
            vh.pack(fill="x", padx=20, pady=(14,4))
            vh.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(vh, text="Versionen",
                         font=ctk.CTkFont("Segoe UI",15,"bold"), text_color=GREEN,
                         anchor="w").grid(row=0, column=0, sticky="w")
            status_lbl = ctk.CTkLabel(vh, text="Lade…",
                                      font=ctk.CTkFont("Segoe UI",10), text_color=TEXT_MUTED)
            status_lbl.grid(row=0, column=1, sticky="e")

            # ── Versions-Liste ─────────────────────────────────────────────────
            ver_scroll = ctk.CTkScrollableFrame(win, fg_color="transparent")
            ver_scroll.pack(fill="both", expand=True, padx=20, pady=(0,12))

            def _ver_row(ver_name, mc_versions, date_str, dl_cmd,
                        ext_url=None, changelog=None, author=None):
                """Erstellt eine Versions-Zeile."""
                row = ctk.CTkFrame(ver_scroll, fg_color="transparent", corner_radius=0)
                row.pack(fill="x", pady=1)
                row.grid_columnconfigure(0, weight=1)

                # Name + Autor
                name_f = ctk.CTkFrame(row, fg_color="transparent")
                name_f.grid(row=0, column=0, padx=4, sticky="w")
                ctk.CTkLabel(name_f, text=ver_name,
                             font=ctk.CTkFont("Segoe UI",12), text_color=TEXT, anchor="w"
                             ).pack(side="left", padx=(0,8))
                if author:
                    ctk.CTkLabel(name_f, text=f"von {author}",
                                 font=ctk.CTkFont("Segoe UI",9), text_color=TEXT_MUTED
                                 ).pack(side="left")

                # MC-Versionen als Tags
                tags_f = ctk.CTkFrame(row, fg_color="transparent")
                tags_f.grid(row=0, column=1, padx=8)
                for mc_v in mc_versions:
                    is_server = mc_v == srv_mc_ver or mc_v in srv_mc_ver or srv_mc_ver in mc_v
                    tag_col = GREEN if is_server else "#2a2a2a"
                    txt_col = "#000" if is_server else TEXT_MUTED
                    ctk.CTkLabel(tags_f, text=mc_v, fg_color=tag_col,
                                 text_color=txt_col, corner_radius=4,
                                 font=ctk.CTkFont("Segoe UI",9,"bold"),
                                 padx=6, pady=2).pack(side="left", padx=2)

                # Datum
                if date_str:
                    ctk.CTkLabel(row, text=date_str,
                                 font=ctk.CTkFont("Segoe UI",10), text_color=TEXT_MUTED,
                                 width=90, anchor="e").grid(row=0, column=2, padx=8)

                # Buttons
                btn_f = ctk.CTkFrame(row, fg_color="transparent")
                btn_f.grid(row=0, column=3, padx=4)

                if dl_cmd:
                    ctk.CTkButton(btn_f, text="⬇", width=32, height=28,
                                  fg_color="#1a3a1a", hover_color=GREEN,
                                  text_color=GREEN, corner_radius=6,
                                  command=dl_cmd).pack(side="left", padx=2)
                if ext_url:
                    ctk.CTkButton(btn_f, text="??", width=32, height=28,
                                  fg_color=CARD, hover_color=BORDER,
                                  text_color=BLUE, corner_radius=6,
                                  command=lambda u=ext_url: __import__("webbrowser").open(u)
                                  ).pack(side="left", padx=2)

                # Changelog-Button falls vorhanden und kein direkter Download
                if changelog and not dl_cmd:
                    _show_cl = [False]
                    cl_frame = [None]
                    def _toggle_cl(c=changelog, sf=ver_scroll):
                        _show_cl[0] = not _show_cl[0]
                        if cl_frame[0]:
                            try: cl_frame[0].destroy()
                            except: pass
                            cl_frame[0] = None
                        if _show_cl[0]:
                            f = ctk.CTkFrame(sf, fg_color="#1a1a1a", corner_radius=6)
                            f.pack(fill="x", padx=8, pady=2)
                            cl_frame[0] = f
                            ctk.CTkLabel(f, text="📋 Update-Notes:",
                                         font=ctk.CTkFont("Segoe UI",10,"bold"),
                                         text_color=TEXT_MUTED).pack(padx=8, pady=(6,2), anchor="w")
                            # Changelog auf max 500 Zeichen kürzen
                            cl_txt = str(c)[:500] + ("…" if len(str(c))>500 else "")
                            ctk.CTkLabel(f, text=cl_txt,
                                         font=ctk.CTkFont("Segoe UI",9), text_color=TEXT_MUTED,
                                         wraplength=800, justify="left").pack(padx=8, pady=(0,8), anchor="w")
                    ctk.CTkButton(btn_f, text="📋", width=32, height=28,
                                  fg_color=CARD, hover_color=SIDEBAR_BG,
                                  text_color=TEXT_MUTED, corner_radius=6,
                                  command=_toggle_cl).pack(side="left", padx=2)

                # Trennlinie
                ctk.CTkFrame(ver_scroll, fg_color=BORDER, height=1).pack(fill="x", padx=4)

            def _install(url, fname):
                """Datei herunterladen und in plugins-Ordner."""
                status_lbl.configure(text=f"??? Lade {fname}…", text_color="#f39c12")
                def _do():
                    try:
                        r = requests.get(url, stream=True, timeout=60,
                                         headers={"User-Agent":"MineHostLocal/1.0"},
                                         allow_redirects=True)
                        if "text/html" in r.headers.get("content-type",""):
                            self.after(0, lambda u=r.url: __import__("webbrowser").open(u))
                            self.after(0, lambda: status_lbl.configure(
                                text="Browser geöffnet → manuell herunterladen", text_color="#f39c12"))
                            return
                        with open(str(folder / fname), "wb") as fh:
                            for chunk in r.iter_content(8192): fh.write(chunk)
                        self.after(0, lambda: status_lbl.configure(
                            text=f"✓ {fname} installiert!", text_color=GREEN))
                        self.after(0, _load_installed)
                    except Exception as e:
                        self.after(0, lambda err=e: status_lbl.configure(
                            text=f"Fehler: {err}", text_color=RED))
                threading.Thread(target=_do, daemon=True).start()

            slug       = item.get("slug")
            jar_path   = item.get("jar_path")
            h_owner    = item.get("hangar_owner")
            h_slug     = item.get("hangar_slug")
            cf_id      = item.get("cf_id")
            cf_api_key = self.cfg.get("curseforge_api_key","")

            if cf_id and cf_api_key:
                def _fetch_cf():
                    try:
                        r = requests.get(f"https://api.curseforge.com/v1/mods/{cf_id}/files",
                            params={"pageSize": 50},
                            headers={"x-api-key": cf_api_key, "Accept": "application/json",
                                     "User-Agent": "MineHostLocal/1.0"}, timeout=10)
                        files = r.json().get("data", [])
                        self.after(0, lambda f=files: _show_cf(f))
                    except Exception as e:
                        self.after(0, lambda err=e: status_lbl.configure(text=f"Fehler: {err}", text_color=RED))
                threading.Thread(target=_fetch_cf, daemon=True).start()

                def _show_cf(files):
                    status_lbl.configure(text=f"{len(files)} Versionen")
                    cf_author = ", ".join(a.get("name","") for a in item.get("_authors",[]))
                    for f in files:
                        fname  = f.get("displayName", f.get("fileName","?"))
                        mc_vs  = [v for v in f.get("gameVersions",[]) if not v.startswith("Java")]
                        dl_url = f.get("downloadUrl","")
                        date   = (f.get("fileDate","")[:10] if f.get("fileDate") else "")
                        changelog = f.get("changelog","") or f.get("changelogHtml","")
                        dl_cmd = (lambda u=dl_url, fn=fname: _install(u, fn if fn.endswith(".jar") else fn+".jar")) if dl_url else None
                        ext = None if dl_url else item.get("website","")
                        _ver_row(fname, mc_vs[:5], date, dl_cmd, ext_url=ext,
                                 changelog=changelog, author=cf_author)

            elif h_owner and h_slug:
                def _fetch_h():
                    try:
                        r = requests.get(
                            f"https://hangar.papermc.io/api/v1/projects/{h_owner}/{h_slug}/versions",
                            params={"limit": 50, "platform": "PAPER"},
                            headers={"User-Agent": "MineHostLocal/1.0"}, timeout=10)
                        self.after(0, lambda v=r.json().get("result",[]): _show_h(v))
                    except Exception as e:
                        self.after(0, lambda err=e: status_lbl.configure(text=f"Fehler: {err}", text_color=RED))
                threading.Thread(target=_fetch_h, daemon=True).start()

                def _show_h(versions):
                    status_lbl.configure(text=f"{len(versions)} Versionen")
                    for v in versions:
                        vname   = v.get("name","?")
                        mc_vs   = v.get("platformDependencies",{}).get("PAPER",[])
                        dl_info = v.get("downloads",{}).get("PAPER",{})
                        dl_url  = dl_info.get("downloadUrl")
                        ext_url = dl_info.get("externalUrl")
                        if not dl_url:
                            dl_url = f"https://hangar.papermc.io/api/v1/projects/{h_owner}/{h_slug}/versions/{vname}/PAPER/download"
                        fname = f"{h_slug}-{vname}.jar"
                        dl_cmd = lambda u=dl_url, fn=fname: _install(u, fn)
                        _ver_row(vname, mc_vs[:5], "", dl_cmd, ext_url if not dl_info.get("downloadUrl") else None)

            elif slug:
                def _fetch_mr():
                    try:
                        r = requests.get(f"https://api.modrinth.com/v2/project/{slug}/version",
                            headers={"User-Agent":"MineHostLocal/1.0"}, timeout=8)
                        self.after(0, lambda v=r.json(): _show_mr(v))
                    except Exception as e:
                        self.after(0, lambda err=e: status_lbl.configure(text=f"Fehler: {err}", text_color=RED))
                threading.Thread(target=_fetch_mr, daemon=True).start()

                def _show_mr(versions):
                    status_lbl.configure(text=f"{len(versions)} Versionen")
                    for v in versions:
                        vname     = v.get("version_number","?")
                        mc_vs     = v.get("game_versions",[])
                        date      = v.get("date_published","")[:10]
                        changelog = v.get("changelog","")
                        author    = ", ".join(v.get("author_id",[])) if isinstance(v.get("author_id"), list) else ""
                        files     = v.get("files",[])
                        fi        = next((f for f in files if f.get("primary")), files[0] if files else {})
                        url       = fi.get("url","")
                        fname     = fi.get("filename", f"{slug}.jar")
                        dl_cmd    = (lambda u=url, fn=fname: _install(u, fn)) if url else None
                        _ver_row(vname, mc_vs[:5], date, dl_cmd,
                                 changelog=changelog, author=author)

            elif jar_path:
                j = Path(jar_path)
                meta = _load_meta().get(j.name, {})
                def _del():
                    if messagebox.askyesno("Löschen", f"'{j.name}' löschen?"):
                        try: j.unlink()
                        except: pass
                        d = _load_meta(); d.pop(j.name, None); _save_meta(d)
                        win.destroy(); _load_installed()
                _ver_row(meta.get("version","Lokal"), [], "", None)
                status_lbl.configure(text="Lokal installiert")

        def _load_installed():
            """Installierte Plugins als Grid anzeigen."""
            meta = _load_meta()
            jars = sorted(folder.glob("*.jar"))
            items = []
            for j in jars:
                m = meta.get(j.name, {})
                items.append({
                    "title":       m.get("name", j.stem),
                    "description": m.get("description", "Lokales Plugin/Mod"),
                    "version":     m.get("version",""),
                    "website":     m.get("website",""),
                    "source":      "Plugin" if not is_mod else "Mod",
                    "origin":      "Lokal",
                    "jar_path":    str(j),
                })
            _show_grid(items)

        _page    = [0]   # aktuelle Seite (0-basiert)
        _total   = [0]   # Gesamtanzahl Ergebnisse
        PAGE_SIZE = 15
        _cache   = {}    # (src, cat, query, page) → (items, total)
        _search_gen = [0]  # Such-Generation — veraltete Threads verwerfen ihr Ergebnis

        # ── Kategorie-Overlay (Ladekreis) ────────────────────────────────────
        _ov      = [None]   # aktueller Overlay-Frame
        _ov_job  = [None]   # after()-Job für Spinner-Animation
        _SPIN    = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","◐?"]

        def _show_cat_loading():
            _hide_cat_loading()
            try:
                if not sidebar.winfo_exists(): return
            except Exception: return
            import tkinter as _tk
            # Normales tk.Frame — CTkFrame unterstützt height in place() nicht
            ov = _tk.Frame(sidebar, bg="#0d0d0d")
            ov.place(x=0, y=38, relwidth=1, relheight=1, height=-38)
            _ov[0] = ov
            idx = [0]
            spin_lbl = ctk.CTkLabel(ov, text=_SPIN[0],
                                    font=ctk.CTkFont("Segoe UI", 38),
                                    text_color=GREEN)
            spin_lbl.place(relx=0.5, rely=0.45, anchor="center")
            # Seitengeneration merken → Spinner stoppt automatisch bei Seitenwechsel
            _gen = getattr(self, "_page_gen", 0)

            def _tick():
                if getattr(self, "_page_gen", 0) != _gen: return  # Seite gewechselt
                if _ov[0] is not ov: return                        # Overlay weg
                idx[0] = (idx[0] + 1) % len(_SPIN)
                try:
                    spin_lbl.configure(text=_SPIN[idx[0]])
                    _ov_job[0] = self.after(80, _tick)
                except Exception: pass
            _ov_job[0] = self.after(80, _tick)

        def _hide_cat_loading():
            if _ov_job[0]:
                try: self.after_cancel(_ov_job[0])
                except: pass
                _ov_job[0] = None
            if _ov[0]:
                try: _ov[0].destroy()
                except: pass
                _ov[0] = None

        def _show_results(items, total):
            _hide_cat_loading()
            q = ""
            try: q = search_entry.get().strip().lower()
            except: pass
            pinned = [e for e in self._load_script_db()
                      if not q or q in e.get("title","").lower()]
            _show_grid(pinned + items)
            total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
            cur_p = _page[0]
            for w in right.winfo_children():
                if getattr(w, "_is_pagination", False):
                    try: w.destroy()
                    except: pass
            pag = ctk.CTkFrame(right, fg_color=SIDEBAR_BG, corner_radius=8, height=44)
            pag._is_pagination = True
            pag.grid(row=1, column=0, sticky="ew", padx=4, pady=(0,4))
            pag.grid_propagate(False)
            pag.grid_columnconfigure(1, weight=1)
            ctk.CTkButton(pag, text="??", width=40, height=32,
                          fg_color=CARD if cur_p > 0 else "#1a1a1a",
                          hover_color=BORDER, text_color=TEXT if cur_p > 0 else "#555",
                          font=ctk.CTkFont("Segoe UI",14,"bold"), corner_radius=6,
                          state="normal" if cur_p > 0 else "disabled",
                          command=lambda: _do_search(search_entry.get(), cur_p-1)
                          ).grid(row=0, column=0, padx=8, pady=6)
            ctk.CTkLabel(pag, text=f"Seite  {cur_p+1}  /  {total_pages}",
                         font=ctk.CTkFont("Segoe UI",12,"bold"), text_color=TEXT
                         ).grid(row=0, column=1)
            ctk.CTkButton(pag, text="→", width=40, height=32,
                          fg_color=CARD if cur_p < total_pages-1 else "#1a1a1a",
                          hover_color=BORDER, text_color=TEXT if cur_p < total_pages-1 else "#555",
                          font=ctk.CTkFont("Segoe UI",14,"bold"), corner_radius=6,
                          state="normal" if cur_p < total_pages-1 else "disabled",
                          command=lambda: _do_search(search_entry.get(), cur_p+1)
                          ).grid(row=0, column=2, padx=8, pady=6)

        def _do_search(query="", page=0):
            _page[0] = page
            cat_id  = _sel_category[0]
            src     = _source[0]
            api_key = self.cfg.get("curseforge_api_key","")

            # Cache-Treffer → sofort anzeigen ohne Netzwerkaufruf
            cache_key = (src, cat_id, query, page)
            if cache_key in _cache:
                cached_items, cached_total = _cache[cache_key]
                _total[0] = cached_total
                _show_results(cached_items, cached_total)
                return

            # Generation hochzählen — ältere laufende Threads verwerfen ihr Ergebnis
            _search_gen[0] += 1
            my_gen = _search_gen[0]

            _show_cat_loading()   # Overlay einblenden
            for w in scroll.winfo_children(): w.destroy()
            ctk.CTkLabel(scroll, text="Suche…", text_color=TEXT_MUTED,
                         font=ctk.CTkFont("Segoe UI",12)).pack(pady=20)

            def _fetch(cache_key=cache_key, my_gen=my_gen):
                items = []
                total = 0
                offset = page * PAGE_SIZE
                try:
                    if src == "curseforge":
                        if not api_key:
                            self.after(0, lambda: ctk.CTkLabel(scroll,
                                text="CurseForge API-Key fehlt.",
                                text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",12)).pack(pady=30))
                            return
                        cf_class = CF_CLASS_MOD if is_mod else CF_CLASS_BUKKIT
                        params = {"gameId": CF_GAME_ID, "classId": cf_class,
                                  "searchFilter": query or "", "pageSize": PAGE_SIZE,
                                  "index": offset, "sortField": 2, "sortOrder": "desc"}
                        if cat_id: params["categoryId"] = cat_id
                        if is_mod and srv_type in CF_LOADER_TYPE:
                            params["modLoaderType"] = CF_LOADER_TYPE[srv_type]
                        r = requests.get("https://api.curseforge.com/v1/mods/search",
                            params=params,
                            headers={"x-api-key": api_key, "Accept": "application/json",
                                     "User-Agent": "MineHostLocal/1.0"}, timeout=10)
                        if r.status_code == 403:
                            self.after(0, lambda: ctk.CTkLabel(scroll,
                                text="??? CurseForge API-Key ungültig oder noch nicht aktiv.\n"
                                     "Bitte 15-60 Min warten.",
                                text_color=RED, font=ctk.CTkFont("Segoe UI",12),
                                justify="center").pack(pady=30))
                            return
                        data = r.json()
                        total = data.get("pagination", {}).get("totalCount", 0)
                        for m in data.get("data", []):
                            authors = [a.get("name","") for a in m.get("authors",[])]
                            items.append({
                                "title":       m.get("name","?"),
                                "description": m.get("summary",""),
                                "source":      "Mod" if is_mod else "Plugin", "origin": "curseforge.com",
                                "cf_id":       m.get("id"),
                                "website":     m.get("links",{}).get("websiteUrl",""),
                                "downloads":   m.get("downloadCount",0),
                                "author":      ", ".join(authors),
                                "_authors":    m.get("authors",[]),
                            })

                    elif src == "modrinth":
                        import json as _json
                        facets_list = [[f"project_type:{facet_type}"]]
                        if is_mod and srv_type in MR_LOADER:
                            facets_list.append([f"categories:{MR_LOADER[srv_type]}"])
                        if cat_id: facets_list.append([f"categories:{cat_id}"])
                        r = requests.get("https://api.modrinth.com/v2/search",
                            params={"query": query or "", "limit": PAGE_SIZE,
                                    "offset": offset, "facets": _json.dumps(facets_list)},
                            headers={"User-Agent": "MineHostLocal/1.0"}, timeout=8)
                        data = r.json()
                        total = data.get("total_hits", 0)
                        for h in data.get("hits", []):
                            items.append({
                                "title":       h.get("title","?"),
                                "description": h.get("description",""),
                                "source":      "Mod" if is_mod else "Plugin", "origin": "modrinth.com",
                                "slug":        h.get("slug",""),
                                "website":     f"https://modrinth.com/plugin/{h.get('slug','')}",
                                "downloads":   h.get("downloads",0),
                            })

                    elif src == "hangar":
                        r = requests.get("https://hangar.papermc.io/api/v1/projects",
                            params={"q": query or "", "limit": PAGE_SIZE,
                                    "offset": offset, "platform": "PAPER", "sort": "-stars"},
                            headers={"User-Agent": "MineHostLocal/1.0"}, timeout=10)
                        data = r.json()
                        total = data.get("pagination", {}).get("count", 0)
                        for h in data.get("result", []):
                            ns = h.get("namespace", {})
                            owner, hslug = ns.get("owner",""), ns.get("slug","")
                            items.append({
                                "title":        h.get("name","?"),
                                "description":  h.get("description",""),
                                "source":       "Plugin", "origin": "hangar.papermc.io",
                                "hangar_owner": owner, "hangar_slug": hslug,
                                "website":      f"https://hangar.papermc.io/{owner}/{hslug}",
                                "downloads":    h.get("stats",{}).get("downloads",0),
                            })
                    else:  # hangar (catch-all)
                        pass

                    if _search_gen[0] != my_gen:
                        return  # neuere Suche gestartet → Ergebnis verwerfen
                    _total[0] = total
                    _cache[cache_key] = (items, total)
                    self._page_after(0, lambda i=items, t=total: _show_results(i, t))
                except Exception as e:
                    if _search_gen[0] != my_gen:
                        return
                    self._page_after(0, lambda err=e: (
                        _hide_cat_loading(),
                        ctk.CTkLabel(scroll, text=f"Fehler: {err}",
                            text_color=RED, font=ctk.CTkFont("Segoe UI",12)).pack(pady=20)
                    ))

            threading.Thread(target=_fetch, daemon=True).start()

        search_entry.bind("<Return>", lambda e: _do_search(search_entry.get(), 0))

        # ── Upload-Button ──────────────────────────────────────────────────────
        def _upload_plugin():
            # Datei(en) ODER Ordner wählen
            import tkinter.simpledialog as _sd
            choice = messagebox.askquestion(
                "Hochladen", "Ordner hochladen?\n\n[Ja] = Ordner wählen\n[Nein] = Dateien wählen")
            if choice == "yes":
                src_dir = filedialog.askdirectory(title="Ordner wählen (alle Dateien werden kopiert)")
                paths = [src_dir] if src_dir else []
            else:
                paths = list(filedialog.askopenfilenames(
                    title="Plugin/Mod hochladen",
                    filetypes=[("JAR","*.jar"),("Alle","*.*")]))
            if not paths: return
            meta = _load_meta()
            for p in paths:
                src = Path(p)
                dst = folder / src.name
                try:
                    if src.is_dir():
                        # Rekursiv ALLE Dateien kopieren (auch tief verschachtelte Ordner)
                        def _copy_all(s, d):
                            d.mkdir(parents=True, exist_ok=True)
                            for item in s.iterdir():
                                target = d / item.name
                                if item.is_dir():
                                    _copy_all(item, target)
                                else:
                                    shutil.copy2(str(item), str(target))
                        _copy_all(src, dst)
                    else:
                        shutil.copy2(str(src), str(dst))
                except Exception as e:
                    messagebox.showerror("Fehler", str(e)); continue
                # Meta-Dialog
                win = ctk.CTkToplevel(self)
                win.title("Plugin-Info")
                win.geometry("400x320")
                win.configure(fg_color=BG)
                win.grab_set()
                ctk.CTkLabel(win, text=f"Info für: {src.name}",
                             font=ctk.CTkFont("Segoe UI",13,"bold"), text_color=TEXT
                             ).pack(padx=20, pady=(16,8), anchor="w")
                def _field(label, required=False, pw=False):
                    ctk.CTkLabel(win, text=label + (" *" if required else ""),
                                 text_color=TEXT_MUTED if not required else TEXT,
                                 font=ctk.CTkFont("Segoe UI",11)).pack(padx=20, anchor="w")
                    e = ctk.CTkEntry(win, fg_color=CARD, text_color=TEXT, height=32, show="•" if pw else "")
                    e.pack(padx=20, pady=(2,6), fill="x"); return e
                e_name = _field("Name", required=True)
                e_name.insert(0, src.stem)
                e_ver  = _field("Version")
                e_web  = _field("Website")
                e_desc = _field("Beschreibung")
                def _save(p2=dst, name_e=e_name, ver_e=e_ver, web_e=e_web, desc_e=e_desc):
                    nm = name_e.get().strip()
                    if not nm:
                        messagebox.showwarning("Pflichtfeld", "Name ist erforderlich!"); return
                    meta[p2.name] = {
                        "name": nm, "version": ver_e.get().strip(),
                        "website": web_e.get().strip(), "description": desc_e.get().strip()
                    }
                    _save_meta(meta)
                    win.destroy()
                    _load_installed()
                ctk.CTkButton(win, text="Speichern", fg_color=GREEN, hover_color=GREEN_HOV,
                              text_color="#000", font=ctk.CTkFont("Segoe UI",12,"bold"),
                              command=_save).pack(padx=20, pady=8, fill="x")
                win.bind("<Return>", lambda e: _save())

        ctk.CTkButton(topbar, text="⬆ Upload", width=80, height=36,
                      fg_color=CARD, hover_color=BORDER, text_color=TEXT,
                      font=ctk.CTkFont("Segoe UI",11), corner_radius=6,
                      command=_upload_plugin).grid(row=0, column=3, padx=(4,0))

        # Sofort initiale Suche starten (standard: CurseForge, leer = alles)
        self._page_after(150, lambda: _do_search("", 0))

    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    # PAGE: DATEIEN  (Screenshot-Design)
    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    def _p_files(self):
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        if not self.server_name:
            ctk.CTkLabel(self.content, text="Kein Server.", text_color=TEXT_MUTED).grid(row=0, column=0)
            return

        srv_dir = Path(self.cfg.get("dir", ""))
        self._file_cur_dir = [srv_dir]

        # ── Outer wrapper ──
        outer = ctk.CTkFrame(self.content, fg_color="transparent")
        outer.grid(row=0, column=0, sticky="nsew")
        outer.grid_rowconfigure(1, weight=1)
        outer.grid_columnconfigure(0, weight=1)

        # ── Topbar: Titel + Datei-Anzahl ──
        topbar = ctk.CTkFrame(outer, fg_color="#111", corner_radius=0, height=42)
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.grid_propagate(False)
        topbar.grid_columnconfigure(0, weight=1)
        self._file_path_lbl = ctk.CTkLabel(topbar, text="",
            text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI", 11), anchor="w")
        self._file_path_lbl.grid(row=0, column=0, padx=12, sticky="w")
        self._file_count_lbl = ctk.CTkLabel(topbar, text="",
            text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI", 11))
        self._file_count_lbl.grid(row=0, column=1, padx=12)

        # ── Actionbar: Auswählen + Upload + Neu erstellen ──
        actbar = ctk.CTkFrame(outer, fg_color="#0d0d0d", corner_radius=0, height=38)
        actbar.grid(row=1, column=0, sticky="ew")
        actbar.grid_propagate(False)
        ctk.CTkButton(actbar, text="☰  Auswählen", width=110, height=28,
            fg_color="#1e1e1e", hover_color=CARD, text_color=TEXT,
            font=ctk.CTkFont("Segoe UI", 11), corner_radius=6,
            command=lambda: None).pack(side="left", padx=(10,0), pady=5)
        ctk.CTkButton(actbar, text="＋ Datei erstellen", width=120, height=28,
            fg_color="#1e1e1e", hover_color=CARD, text_color=TEXT,
            font=ctk.CTkFont("Segoe UI", 11), corner_radius=6,
            command=lambda: self._new_file_dialog()).pack(side="left", padx=6, pady=5)
        ctk.CTkButton(actbar, text="⬆  Hochladen", width=110, height=28,
            fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
            font=ctk.CTkFont("Segoe UI", 11, "bold"), corner_radius=6,
            command=lambda: self._upload_file()).pack(side="right", padx=10, pady=5)
        ctk.CTkButton(actbar, text="Im Explorer öffnen", width=130, height=28,
            fg_color="#1e1e1e", hover_color=CARD, text_color=TEXT_MUTED,
            font=ctk.CTkFont("Segoe UI", 11), corner_radius=6,
            command=lambda: os.startfile(str(self._file_cur_dir[-1]))
            ).pack(side="right", padx=(0,6), pady=5)

        # ── Drag & Drop Hinweis-Banner ──
        dnd_banner = ctk.CTkLabel(outer,
            text="📂  Dateien hier hineinziehen zum Hochladen",
            font=ctk.CTkFont("Segoe UI", 11), text_color="#444",
            fg_color="#0a0a0a", height=28)
        dnd_banner.grid(row=2, column=0, sticky="ew")

        # ── Dateiliste ──
        list_frame = ctk.CTkScrollableFrame(outer, fg_color="#111", corner_radius=0)
        list_frame.grid(row=3, column=0, sticky="nsew")
        outer.grid_rowconfigure(3, weight=1)
        self._file_list_frame = list_frame

        # ── Drag & Drop via tkinterdnd2 ──
        def _handle_drop(event):
            import re as _re
            # tkinterdnd2 liefert Pfade als {path1} {path2} oder einfach path
            raw = event.data.strip()
            # Mehrere Pfade in {} trennen
            paths = _re.findall(r'\{([^}]+)\}|(\S+)', raw)
            paths = [a or b for a, b in paths]
            if not paths:
                paths = [raw]
            cur = self._file_cur_dir[-1] if hasattr(self, "_file_cur_dir") else srv_dir
            copied = 0
            for p in paths:
                p = p.strip().strip("{}")
                src = Path(p)
                if src.exists():
                    try:
                        dst = cur / src.name
                        if src.is_dir():
                            shutil.copytree(str(src), str(dst),
                                            dirs_exist_ok=True)
                        else:
                            shutil.copy2(str(src), str(dst))
                        copied += 1
                    except Exception as e:
                        self._append_log(f"[Dateien] Drop-Fehler: {e}\n")
            if copied:
                dnd_banner.configure(
                    text=f"✓  {copied} Datei(en) hinzugefügt",
                    text_color=GREEN)
                dnd_banner.after(2500, lambda: dnd_banner.configure(
                    text="📂  Dateien hier hineinziehen zum Hochladen",
                    text_color="#444"))
                if hasattr(self, "_render_files_fn"):
                    self.after(0, self._render_files_fn)

        def _dnd_enter(event):
            dnd_banner.configure(
                text="📂  Loslassen zum Hochladen",
                text_color=GREEN, fg_color="#0a1a0a")

        def _dnd_leave(event):
            dnd_banner.configure(
                text="📂  Dateien hier hineinziehen zum Hochladen",
                text_color="#444", fg_color="#0a0a0a")

        # Drag & Drop via Windows Shell
        def _setup_windnd():
            try:
                import windnd
            except ImportError:
                return

            def _on_drop(files):
                # Sofort auf Background-Thread → GUI friert nicht ein
                def _do_copy():
                    cur = self._file_cur_dir[-1] if hasattr(self, "_file_cur_dir") else srv_dir
                    copied = 0
                    errors = []
                    for f in files:
                        try:
                            path_str = f.decode("utf-8", errors="replace") if isinstance(f, bytes) else str(f)
                            src = Path(path_str.strip())
                            if not src.exists():
                                continue
                            dst = cur / src.name
                            if src.is_dir():
                                if dst.exists():
                                    # Ordner zusammenführen statt ersetzen
                                    for item in src.rglob("*"):
                                        rel = item.relative_to(src)
                                        target = dst / rel
                                        if item.is_dir():
                                            target.mkdir(parents=True, exist_ok=True)
                                        else:
                                            target.parent.mkdir(parents=True, exist_ok=True)
                                            shutil.copy2(str(item), str(target))
                                else:
                                    shutil.copytree(str(src), str(dst))
                            else:
                                shutil.copy2(str(src), str(dst))
                            copied += 1
                        except Exception as e:
                            errors.append(str(e))

                    def _update_ui():
                        try:
                            if copied:
                                dnd_banner.configure(
                                    text=f"✓  {copied} Element(e) hinzugefügt"
                                         + (f" ({len(errors)} Fehler)" if errors else ""),
                                    text_color=GREEN)
                                dnd_banner.after(3000, lambda: dnd_banner.configure(
                                    text="📂  Dateien hier hineinziehen zum Hochladen",
                                    text_color="#444"))
                                if hasattr(self, "_render_files_fn"):
                                    self.after(0, self._render_files_fn)
                            elif errors:
                                dnd_banner.configure(
                                    text=f"✗  Fehler: {errors[0][:60]}",
                                    text_color=RED)
                                dnd_banner.after(4000, lambda: dnd_banner.configure(
                                    text="📂  Dateien hier hineinziehen zum Hochladen",
                                    text_color="#444"))
                        except Exception:
                            pass

                    self.after(0, _update_ui)

                # Status sofort anzeigen
                try:
                    dnd_banner.configure(text="???  Wird kopiert…", text_color="#f39c12")
                except Exception:
                    pass
                threading.Thread(target=_do_copy, daemon=True).start()

            try:
                inner = getattr(list_frame, "_parent_canvas", list_frame)
                windnd.hook_dropfiles(inner, func=_on_drop)
                windnd.hook_dropfiles(dnd_banner, func=_on_drop)
            except Exception:
                pass

        _setup_windnd()

        def _render_files():
            for w in list_frame.winfo_children(): w.destroy()
            cur = self._file_cur_dir[-1]
            rel = str(cur).replace(str(srv_dir), "") or "/"
            self._file_path_lbl.configure(text=f"??  {self.cfg.get('name','')}  {rel}")

            # Zurück-Zeile
            if self._file_cur_dir[-1] != srv_dir:
                back_row = ctk.CTkFrame(list_frame, fg_color="#1a1a1a",
                                        corner_radius=0, height=38)
                back_row.pack(fill="x", pady=(0,1))
                back_row.pack_propagate(False)
                ctk.CTkButton(back_row, text="⬅  ..",
                    fg_color="transparent", hover_color="#222", text_color=TEXT_MUTED,
                    font=ctk.CTkFont("Segoe UI", 12), anchor="w",
                    command=lambda: (self._file_cur_dir.pop(), _render_files())
                    ).pack(fill="both", expand=True, padx=8)

            try:
                entries = sorted(cur.iterdir(),
                                 key=lambda p: (p.is_file(), p.name.lower()))
            except:
                entries = []

            self._file_count_lbl.configure(text=f"?? {len(entries)}")

            EXT_ICONS = {
                ".jar": "☕", ".json": "{}", ".yml": "📋", ".yaml": "📋",
                ".properties": "⚙", ".txt": "📄", ".log": "📋",
                ".sk": "📜", ".java": "☕", ".py": "???",
                ".zip": "📦", ".tar": "📦", ".gz": "📦",
                ".png": "🖼", ".jpg": "🖼", ".ico": "🖼",
                ".sh": "⚡", ".bat": "⚡",
            }

            for p in entries:
                is_dir = p.is_dir()
                row = ctk.CTkFrame(list_frame, fg_color="#1a1a1a",
                                   corner_radius=0, height=42)
                row.pack(fill="x", pady=(0, 1))
                row.pack_propagate(False)
                row.grid_columnconfigure(1, weight=1)

                # Icon
                ext  = p.suffix.lower()
                icon = "??" if is_dir else EXT_ICONS.get(ext, "📄")
                icon_color = "#4a9eff" if is_dir else (
                    "#f39c12" if ext in (".jar",) else TEXT_MUTED)
                ctk.CTkLabel(row, text=icon, font=ctk.CTkFont("Segoe UI", 14),
                             text_color=icon_color, width=36).grid(
                             row=0, column=0, padx=(10,0))

                # Name
                name_lbl = ctk.CTkLabel(row, text=p.name,
                    font=ctk.CTkFont("Segoe UI", 12),
                    text_color="#4a9eff" if is_dir else TEXT, anchor="w")
                name_lbl.grid(row=0, column=1, sticky="w", padx=6)

                # Größe
                if not is_dir:
                    sz = p.stat().st_size
                    if sz >= 1024*1024: sz_txt = f"{sz/1024/1024:.1f} MB"
                    elif sz >= 1024:    sz_txt = f"{sz/1024:.1f} kB"
                    else:               sz_txt = f"{sz} B"
                    ctk.CTkLabel(row, text=sz_txt, text_color=TEXT_MUTED,
                                 font=ctk.CTkFont("Segoe UI", 10), width=70).grid(
                                 row=0, column=2, padx=4)

                # Aktions-Buttons
                btn_frame = ctk.CTkFrame(row, fg_color="transparent")
                btn_frame.grid(row=0, column=3, padx=(0,8))

                if not is_dir:
                    # Download
                    def _dl(path=p):
                        dst = filedialog.asksaveasfilename(
                            defaultextension=path.suffix, initialfile=path.name)
                        if dst:
                            import shutil as _sh
                            _sh.copy2(str(path), dst)
                    ctk.CTkButton(btn_frame, text="⬇", width=30, height=28,
                        fg_color="#1e3a1e", hover_color="#2a5a2a",
                        text_color=GREEN, font=ctk.CTkFont("Segoe UI", 13),
                        corner_radius=6, command=_dl).pack(side="left", padx=2)

                # Löschen
                def _del(path=p, is_d=is_dir):
                    msg = f"Ordner '{path.name}' und Inhalt löschen?" if is_d else f"'{path.name}' löschen?"
                    if not messagebox.askyesno("Löschen", msg): return
                    import shutil as _sh
                    try:
                        if is_d: _sh.rmtree(str(path))
                        else:    path.unlink()
                    except Exception as e:
                        messagebox.showerror("Fehler", str(e)); return
                    _render_files()
                ctk.CTkButton(btn_frame, text="🗑", width=30, height=28,
                    fg_color="#3a1a1a", hover_color="#5a1a1a",
                    text_color=RED, font=ctk.CTkFont("Segoe UI", 13),
                    corner_radius=6, command=_del).pack(side="left", padx=2)

                # Textbearbeitbare Dateien → Editor öffnen
                TEXT_EXTS = {
                    ".sk",".yml",".yaml",".json",".properties",".txt",".cfg",
                    ".conf",".ini",".sh",".bat",".py",".js",".css",".html",
                    ".htm",".xml",".md",".toml",".log",".java",".ts",".jsx",
                    ".tsx",".csv",".env",".gitignore",".htaccess",""
                }
                if not is_dir and (ext in TEXT_EXTS or ext == ""):
                    def _edit(path=p):
                        _open_editor(path)
                    ctk.CTkButton(btn_frame, text="??", width=30, height=28,
                        fg_color="#1a1a3a", hover_color="#2a2a5a",
                        text_color="#4a9eff", font=ctk.CTkFont("Segoe UI", 13),
                        corner_radius=6, command=_edit).pack(side="left", padx=2)
                    row.bind("<Double-Button-1>", lambda e, fn=_edit: fn())
                    name_lbl.bind("<Double-Button-1>", lambda e, fn=_edit: fn())

                # Doppelklick auf Ordner → rein
                if is_dir:
                    def _enter(path=p):
                        self._file_cur_dir.append(path); _render_files()
                    row.bind("<Double-Button-1>", lambda e, fn=_enter: fn())
                    name_lbl.bind("<Double-Button-1>", lambda e, fn=_enter: fn())
                    row.bind("<Button-1>", lambda e, fn=_enter: fn())
                    name_lbl.bind("<Button-1>", lambda e, fn=_enter: fn())

        # ── Text-Editor ───────────────────────────────────────────────────────
        _open_tabs  = {}   # path → {"box": CTkTextbox, "frame": CTkFrame, "modified": bool}
        _active_tab = [None]
        _editor_visible = [False]

        editor_outer = ctk.CTkFrame(outer, fg_color="#0d0d0d", corner_radius=0)
        # Wird erst sichtbar wenn eine Datei geöffnet wird

        # Tab-Leiste
        tab_bar = ctk.CTkFrame(editor_outer, fg_color="#111", corner_radius=0, height=36)
        tab_bar.pack(fill="x", side="top")

        # Titel + Pfad + Speichern-Button oben
        editor_topbar = ctk.CTkFrame(editor_outer, fg_color="#0d0d0d", corner_radius=0, height=40)
        editor_topbar.pack(fill="x", side="top")
        editor_topbar.pack_propagate(False)
        editor_topbar.grid_columnconfigure(0, weight=1)

        editor_title = ctk.CTkLabel(editor_topbar, text="",
            font=ctk.CTkFont("Segoe UI", 13, "bold"), text_color=GREEN, anchor="w")
        editor_title.grid(row=0, column=0, padx=14, sticky="w")

        save_btn = ctk.CTkButton(editor_topbar, text="💾 Speichern", width=110, height=28,
            fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
            font=ctk.CTkFont("Segoe UI",11,"bold"), corner_radius=6)
        save_btn.grid(row=0, column=1, padx=10)

        close_btn = ctk.CTkButton(editor_topbar, text="✕ Schließen", width=90, height=28,
            fg_color=CARD, hover_color=BORDER, text_color=TEXT_MUTED,
            font=ctk.CTkFont("Segoe UI",11), corner_radius=6)
        close_btn.grid(row=0, column=2, padx=(0,10))

        # Editor-Bereich: Zeilennummern + Textbox nebeneinander
        edit_area = ctk.CTkFrame(editor_outer, fg_color="#0d0d0d", corner_radius=0)
        edit_area.pack(fill="both", expand=True)
        edit_area.grid_columnconfigure(1, weight=1)
        edit_area.grid_rowconfigure(0, weight=1)

        ln_box = ctk.CTkTextbox(edit_area, width=48, fg_color="#111",
            text_color="#555", font=ctk.CTkFont("Consolas", 12),
            corner_radius=0, state="disabled", wrap="none")
        ln_box.grid(row=0, column=0, sticky="nsew")

        main_box = ctk.CTkTextbox(edit_area, fg_color="#0d0d0d",
            text_color=TEXT, font=ctk.CTkFont("Consolas", 12),
            corner_radius=0, wrap="none")
        main_box.grid(row=0, column=1, sticky="nsew")

        def _update_line_numbers(*_):
            """Zeilennummern synchron mit dem Editor-Inhalt halten."""
            try:
                lines = int(main_box.index("end-1c").split(".")[0])
                ln_box.configure(state="normal")
                ln_box.delete("1.0", "end")
                ln_box.insert("1.0", "\n".join(str(i) for i in range(1, lines + 1)))
                ln_box.configure(state="disabled")
            except: pass

        main_box.bind("<<Modified>>", lambda e: (_update_line_numbers(), main_box.edit_modified(False)))
        main_box.bind("<KeyRelease>", _update_line_numbers)

        def _rebuild_tabs():
            for w in tab_bar.winfo_children(): w.destroy()
            # Home/Zurück Button
            ctk.CTkButton(tab_bar, text="???", width=32, height=28,
                fg_color="transparent", hover_color="#222", text_color=TEXT_MUTED,
                font=ctk.CTkFont("Segoe UI",13), corner_radius=0,
                command=_hide_editor).pack(side="left")
            for path, info in _open_tabs.items():
                is_active = path == _active_tab[0]
                name = path.name + ("*" if info.get("modified") else "")
                f = ctk.CTkFrame(tab_bar, fg_color="#1e1e1e" if is_active else "#111",
                                 corner_radius=0, cursor="hand2")
                f.pack(side="left")
                lbl = ctk.CTkLabel(f, text=name,
                    font=ctk.CTkFont("Segoe UI",11,"bold" if is_active else "normal"),
                    text_color=TEXT if is_active else TEXT_MUTED,
                    cursor="hand2", padx=10)
                lbl.pack(side="left", ipady=6)
                def _switch(p=path): _show_tab(p)
                def _close_tab(p=path): _do_close_tab(p)
                lbl.bind("<Button-1>", lambda e, fn=_switch: fn())
                ctk.CTkButton(f, text="×", width=20, height=20,
                    fg_color="transparent", hover_color="#3a1010", text_color="#888",
                    font=ctk.CTkFont("Segoe UI",11), corner_radius=0,
                    command=_close_tab).pack(side="left", padx=(0,4))

        def _show_tab(path):
            _active_tab[0] = path
            info = _open_tabs[path]
            main_box.configure(state="normal")
            main_box.delete("1.0", "end")
            main_box.insert("1.0", info["content"])
            _update_line_numbers()
            editor_title.configure(text=f"Dateien  /  {path.name}")
            save_btn.configure(command=lambda p=path: _save_file(p))
            _rebuild_tabs()

        def _open_editor(path: Path):
            if not _editor_visible[0]:
                # Editor einblenden, Dateiliste ausblenden
                list_frame.grid_remove()
                dnd_banner.grid_remove()
                actbar.grid_remove()
                editor_outer.grid(row=1, column=0, rowspan=10, sticky="nsew")
                outer.grid_rowconfigure(1, weight=1)
                _editor_visible[0] = True
            if path not in _open_tabs:
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                except Exception as e:
                    messagebox.showerror("Fehler", f"Datei konnte nicht geöffnet werden:\n{e}"); return
                _open_tabs[path] = {"content": content, "modified": False}
            _show_tab(path)

        def _save_file(path):
            content = main_box.get("1.0", "end-1c")
            try:
                path.write_text(content, encoding="utf-8")
                _open_tabs[path]["content"] = content
                _open_tabs[path]["modified"] = False
                _rebuild_tabs()
                save_btn.configure(text="✓ Gespeichert", fg_color="#166534")
                save_btn.after(1500, lambda: save_btn.configure(text="💾 Speichern", fg_color=GREEN))
            except Exception as e:
                messagebox.showerror("Fehler", str(e))

        def _do_close_tab(path):
            if path in _open_tabs:
                if _open_tabs[path].get("modified"):
                    if not messagebox.askyesno("Ungespeichert", f"'{path.name}' hat ungespeicherte Änderungen. Trotzdem schließen?"):
                        return
                del _open_tabs[path]
            if not _open_tabs:
                _hide_editor()
            elif _active_tab[0] == path:
                _show_tab(next(iter(_open_tabs)))
            else:
                _rebuild_tabs()

        def _hide_editor():
            editor_outer.grid_remove()
            list_frame.grid(row=3, column=0, sticky="nsew")
            dnd_banner.grid(row=2, column=0, sticky="ew")
            actbar.grid(row=1, column=0, sticky="ew")
            _editor_visible[0] = False
            _open_tabs.clear()
            _active_tab[0] = None

        close_btn.configure(command=_hide_editor)

        # Änderungen tracken
        def _on_key(*_):
            if _active_tab[0] and _active_tab[0] in _open_tabs:
                _open_tabs[_active_tab[0]]["modified"] = True
                _rebuild_tabs()
        main_box.bind("<KeyRelease>", _on_key)

        # Strg+S → Speichern
        main_box.bind("<Control-s>", lambda e: _save_file(_active_tab[0]) if _active_tab[0] else None)

        # Page-Generation merken — damit alte Threads nicht mehr rendern
        _my_gen = getattr(self, "_page_gen", 0)
        def _safe_render():
            if getattr(self, "_page_gen", 0) != _my_gen:
                return  # Seite wurde gewechselt → abbrechen
            try:
                _render_files()
            except Exception:
                pass
        self._render_files_fn = _safe_render
        _render_files()

    def _new_file_dialog(self):
        cur = self._file_cur_dir[-1] if hasattr(self, "_file_cur_dir") else Path(self.cfg.get("dir",""))
        win = ctk.CTkToplevel(self)
        win.title("Neue Datei erstellen")
        win.geometry("320x160")
        win.configure(fg_color=SIDEBAR_BG)
        win.grab_set()
        ctk.CTkLabel(win, text="Dateiname (z.B. config.yml):",
                     text_color=TEXT, font=ctk.CTkFont("Segoe UI",12)).pack(padx=20, pady=(16,4), anchor="w")
        entry = ctk.CTkEntry(win, fg_color=CARD, text_color=TEXT,
                             font=ctk.CTkFont("Segoe UI",12), width=280)
        entry.pack(padx=20, pady=4)
        entry.focus()
        def _create():
            name = entry.get().strip()
            if not name: return
            target = cur / name
            if not target.exists():
                try: target.touch()
                except Exception as e:
                    messagebox.showerror("Fehler", str(e)); return
            win.destroy()
            if hasattr(self, "_render_files_fn"): self.after(0, self._render_files_fn)
        ctk.CTkButton(win, text="Erstellen", fg_color=GREEN, hover_color=GREEN_HOV,
                      text_color="#000", font=ctk.CTkFont("Segoe UI",12,"bold"),
                      command=_create).pack(pady=12)
        win.bind("<Return>", lambda e: _create())

    def _upload_file(self):
        cur = self._file_cur_dir[-1] if hasattr(self, "_file_cur_dir") else Path(self.cfg.get("dir",""))
        paths = filedialog.askopenfilenames(title="Dateien hochladen")
        if not paths: return
        import shutil as _sh
        for p in paths:
            try: _sh.copy2(p, cur / Path(p).name)
            except Exception as e: messagebox.showerror("Fehler", str(e))
        if hasattr(self, "_render_files_fn"): self.after(0, self._render_files_fn)

    def _file_manager(self, folder, file_type="Datei"):
        folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
        frame = ctk.CTkFrame(self.content, fg_color=SIDEBAR_BG, corner_radius=10)
        frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0,16))
        frame.grid_columnconfigure(0,weight=1); frame.grid_rowconfigure(0,weight=1)
        box = ctk.CTkTextbox(frame, fg_color=CARD, text_color=TEXT, font=ctk.CTkFont("Segoe UI",12))
        box.grid(row=0,column=0,sticky="nsew",padx=12,pady=(12,8))
        def refresh():
            box.configure(state="normal"); box.delete("1.0","end")
            fs = list(folder.iterdir())
            for f in sorted(fs): box.insert("end",f"📄 {f.name}\n")
            if not fs: box.insert("end","(Leer)")
            box.configure(state="disabled")
        refresh()
        btn_row = ctk.CTkFrame(frame,fg_color="transparent")
        btn_row.grid(row=1,column=0,padx=12,pady=(0,12),sticky="ew")
        ctk.CTkButton(btn_row,text=f"+ {file_type} hinzufügen",
                      fg_color=GREEN,hover_color=GREEN_HOV,text_color="#000",height=36,
                      command=lambda:[
                          [shutil.copy(s,folder/Path(s).name)
                           for s in filedialog.askopenfilenames(title="Dateien hinzufügen")],
                          refresh()
                      ]).pack(side="left",padx=(0,8))
        ctk.CTkButton(btn_row,text="Ordner öffnen",fg_color=CARD,text_color=TEXT,height=36,
                      command=lambda:os.startfile(str(folder))).pack(side="left")

    def _folder_tab_inner(self, parent, folder):
        folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
        box = ctk.CTkTextbox(parent,fg_color=CARD,text_color=TEXT,font=ctk.CTkFont("Segoe UI",12))
        box.grid(row=0,column=0,columnspan=2,sticky="nsew",pady=(0,8))
        def refresh():
            box.configure(state="normal"); box.delete("1.0","end")
            fs=list(folder.iterdir())
            for f in sorted(fs): box.insert("end",f"📄 {f.name}\n")
            if not fs: box.insert("end","(Leer)")
            box.configure(state="disabled")
        refresh()
        ctk.CTkButton(parent,text="+ Hinzufügen",fg_color=GREEN,hover_color=GREEN_HOV,
                      text_color="#000",height=32,
                      command=lambda:[
                          [shutil.copy(s,folder/Path(s).name) for s in filedialog.askopenfilenames()],
                          refresh()
                      ]).grid(row=1,column=0,sticky="ew",padx=(0,8))
        ctk.CTkButton(parent,text="Öffnen",fg_color=CARD,text_color=TEXT,height=32,
                      command=lambda:os.startfile(str(folder))).grid(row=1,column=1)

    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    # PAGE: WELTEN
    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    def _p_worlds(self):
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        if not self.server_name:
            ctk.CTkLabel(self.content,text="Kein Server.",text_color=TEXT_MUTED).grid(row=0,column=0); return

        srv_dir = Path(self.cfg.get("dir",""))

        # ── Haupt-Layout: Links Weltliste, Rechts Detail ───────────────────────
        outer = ctk.CTkFrame(self.content, fg_color="transparent")
        outer.grid(row=0, column=0, sticky="nsew")
        outer.grid_columnconfigure(0, weight=0)
        outer.grid_columnconfigure(1, weight=1)
        outer.grid_rowconfigure(0, weight=1)

        # ── Linke Spalte: Weltliste ────────────────────────────────────────────
        left = ctk.CTkFrame(outer, fg_color=SIDEBAR_BG, corner_radius=0, width=260)
        left.grid(row=0, column=0, sticky="nsew")
        left.grid_propagate(False)

        ctk.CTkLabel(left, text="Welten",
                     font=ctk.CTkFont("Segoe UI",14,"bold"), text_color=TEXT
                     ).pack(padx=16, pady=(16,8), anchor="w")

        worlds_scroll = ctk.CTkScrollableFrame(left, fg_color="transparent")
        worlds_scroll.pack(fill="both", expand=True, padx=4)

        # ── Rechte Seite: Detail-Panel ─────────────────────────────────────────
        right = ctk.CTkFrame(outer, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=0)
        right.grid_rowconfigure(0, weight=1)
        right.grid_columnconfigure(0, weight=1)

        _detail_frame = [None]
        _selected_world = [None]

        DIM_INFO = {
            "world":        ("Overworld",  "??", "#22c55e"),
            "world_nether": ("Nether",     "🔥", "#ef4444"),
            "world_the_end":("The End",    "🌌", "#8b5cf6"),
        }

        def _write_prop(key, val):
            prop_path = srv_dir / "server.properties"
            if not prop_path.exists(): return
            lines = prop_path.read_text(encoding="utf-8").splitlines()
            found = False
            for i, l in enumerate(lines):
                if l.startswith(f"{key}="):
                    lines[i] = f"{key}={val}"; found = True; break
            if not found: lines.append(f"{key}={val}")
            prop_path.write_text("\n".join(lines)+"\n", encoding="utf-8")

        def _read_props():
            p = srv_dir / "server.properties"
            d = {}
            if p.exists():
                for line in p.read_text(encoding="utf-8").splitlines():
                    if "=" in line and not line.startswith("#"):
                        k, _, v = line.partition("=")
                        d[k.strip()] = v.strip()
            return d

        def _show_world_detail(world_path):
            _selected_world[0] = world_path
            if _detail_frame[0]: _detail_frame[0].destroy()

            dim_name, icon, color = DIM_INFO.get(world_path.name, (world_path.name, "🗺", TEXT_MUTED))
            try: size_mb = sum(f.stat().st_size for f in world_path.rglob("*") if f.is_file()) / 1e6
            except: size_mb = 0

            frame = ctk.CTkScrollableFrame(right, fg_color="transparent")
            frame.grid(row=0, column=0, sticky="nsew", padx=16, pady=12)
            _detail_frame[0] = frame

            # Header
            h = ctk.CTkFrame(frame, fg_color=SIDEBAR_BG, corner_radius=10)
            h.pack(fill="x", pady=(0,8))
            h.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(h, text=icon, font=ctk.CTkFont("Segoe UI",32), width=60
                         ).grid(row=0, column=0, rowspan=2, padx=16, pady=12)
            ctk.CTkLabel(h, text=dim_name, font=ctk.CTkFont("Segoe UI",16,"bold"),
                         text_color=TEXT, anchor="w").grid(row=0, column=1, sticky="w", pady=(10,0))
            ctk.CTkLabel(h, text=f"{world_path.name}  •  {size_mb:.1f} MB",
                         text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",11), anchor="w"
                         ).grid(row=1, column=1, sticky="w", pady=(0,10))

            # Aktiv-Toggle
            props = _read_props()
            current_level = props.get("level-name","world")
            is_active = world_path.name == current_level
            act_row = ctk.CTkFrame(frame, fg_color=SIDEBAR_BG, corner_radius=10)
            act_row.pack(fill="x", pady=4)
            act_row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(act_row, text="Als aktive Welt setzen",
                         text_color=TEXT, font=ctk.CTkFont("Segoe UI",12), anchor="w"
                         ).grid(row=0, column=0, padx=14, pady=10, sticky="w")
            act_var = ctk.BooleanVar(value=is_active)
            def _toggle_active(v=None):
                _write_prop("level-name", world_path.name)
                act_lbl.configure(text="✓ Aktiv gesetzt", text_color=GREEN)
            ctk.CTkSwitch(act_row, variable=act_var, text="",
                          progress_color=GREEN, command=_toggle_active
                          ).grid(row=0, column=1, padx=14)
            act_lbl = ctk.CTkLabel(act_row, text="Aktiv" if is_active else "",
                                   text_color=GREEN, font=ctk.CTkFont("Segoe UI",10))
            act_lbl.grid(row=0, column=2, padx=8)

            # Aktions-Buttons (wie Screenshot)
            btns = ctk.CTkFrame(frame, fg_color=SIDEBAR_BG, corner_radius=10)
            btns.pack(fill="x", pady=4)
            btn_defs = [
                ("⬇ Herunterladen", GREEN,  "#000", lambda: _dl_world(world_path)),
                ("⬆ Hochladen",     GREEN,  "#000", lambda: _ul_world(world_path)),
                ("⚙ Optimieren",    "#555", TEXT,   lambda: _optimize_world(world_path)),
                ("?? Dateien",       BLUE,   "#fff", lambda: _show_world_files(world_path, frame)),
                ("🔄 Zurücksetzen",  "#555", TEXT,   lambda: _reset_world(world_path, dim_name)),
                ("🗑 Löschen",       RED,    "#fff", lambda: _del_world_confirm(world_path, dim_name)),
            ]
            for txt, bg, fg, cmd in btn_defs:
                ctk.CTkButton(btns, text=txt, fg_color=bg, text_color=fg,
                              height=36, corner_radius=8,
                              font=ctk.CTkFont("Segoe UI",11,"bold"),
                              command=cmd).pack(fill="x", padx=14, pady=3)

            # ── Spielregeln (Gamerules) ──
            _show_gamerules(frame, world_path)

        def _dl_world(wp):
            dst = filedialog.asksaveasfilename(
                defaultextension=".zip", initialfile=f"{wp.name}.zip",
                filetypes=[("ZIP","*.zip")])
            if dst:
                def _do(): shutil.make_archive(dst[:-4], "zip", str(wp.parent), wp.name)
                threading.Thread(target=_do, daemon=True).start()
                messagebox.showinfo("Download", f"Welt wird als ZIP exportiert:\n{dst}")

        def _ul_world(wp):
            src = filedialog.askopenfilename(
                title="Welt hochladen (ZIP)",
                filetypes=[("ZIP","*.zip"),("Alle","*.*")])
            if src:
                if messagebox.askyesno("Überschreiben", f"Welt '{wp.name}' ersetzen?"):
                    shutil.rmtree(str(wp), ignore_errors=True)
                    shutil.unpack_archive(src, str(wp.parent))
                    _rebuild_world_list()

        def _optimize_world(wp):
            messagebox.showinfo("Optimieren",
                "Welt-Optimierung wird beim nächsten Server-Start ausgeführt.\n"
                "(Minecraft startet mit --forceUpgrade)")

        def _reset_world(wp, name):
            if messagebox.askyesno("Zurücksetzen",
                f"Welt '{name}' wirklich zurücksetzen?\nAlle Chunks werden neu generiert!"):
                shutil.rmtree(str(wp), ignore_errors=True)
                messagebox.showinfo("Zurückgesetzt", f"'{name}' wird beim nächsten Start neu generiert.")
                _rebuild_world_list()

        def _del_world_confirm(wp, name):
            if messagebox.askyesno("Löschen", f"'{name}' wirklich löschen?"):
                shutil.rmtree(str(wp), ignore_errors=True)
                _rebuild_world_list()

        def _show_world_files(wp, parent_frame):
            # Öffnet Datei-Manager für die Welt
            self._file_cur_dir = [wp]
            self._show("files")

        def _show_gamerules(parent, world_path):
            # Gamerules aus level.dat lesen (via Konsole wenn Server läuft, sonst defaults)
            ctk.CTkLabel(parent, text="Spielregeln (Gamerules)",
                         font=ctk.CTkFont("Segoe UI",13,"bold"), text_color=TEXT_MUTED
                         ).pack(anchor="w", pady=(12,4), padx=4)

            GAMERULES = [
                # (key, label, type, default)
                ("announceAdvancements",        "Errungenschaften ankündigen",       "bool", "true"),
                ("commandBlockOutput",           "Command-Block Ausgabe",             "bool", "true"),
                ("doDaylightCycle",             "Tageszyklus",                       "bool", "true"),
                ("doEntityDrops",               "Entity-Drops",                      "bool", "true"),
                ("doFireTick",                  "Feuer breitet sich aus",            "bool", "true"),
                ("doImmediateRespawn",          "Sofort respawnen",                  "bool", "false"),
                ("doInsomnia",                  "Schlaflosigkeit (Phantom-Spawn)",   "bool", "true"),
                ("doLimitedCrafting",           "Limitiertes Crafting",              "bool", "false"),
                ("doMobLoot",                   "Mob-Drops",                         "bool", "true"),
                ("doMobSpawning",               "Mob-Spawn",                         "bool", "true"),
                ("doPatrolSpawning",            "Patrol-Spawn",                      "bool", "true"),
                ("doTileDrops",                 "Block-Drops",                       "bool", "true"),
                ("doTraderSpawning",            "Händler-Spawn",                     "bool", "true"),
                ("doWeatherCycle",              "Wetterwechsel",                     "bool", "true"),
                ("drowningDamage",              "Ertrinkungsschaden",                "bool", "true"),
                ("fallDamage",                  "Fallschaden",                       "bool", "true"),
                ("fireDamage",                  "Feuerschaden",                      "bool", "true"),
                ("freezeDamage",                "Gefrierchaden",                     "bool", "true"),
                ("keepInventory",               "Inventar behalten beim Tod",        "bool", "false"),
                ("mobGriefing",                 "Mob-Griefing",                      "bool", "true"),
                ("naturalRegeneration",         "Natürliche Regeneration",           "bool", "true"),
                ("reducedDebugInfo",            "Reduzierte Debug-Info",             "bool", "false"),
                ("sendCommandFeedback",         "Befehls-Feedback",                  "bool", "true"),
                ("showDeathMessages",           "Todesnachrichten anzeigen",         "bool", "true"),
                ("disableRaids",                "Überfälle deaktivieren",            "bool", "false"),
                ("disableElytraMovementCheck",  "Elytra-Bewegungsprüfung aus",       "bool", "false"),
                ("forgiveDeadPlayers",          "Tote Spieler vergeben",             "bool", "true"),
                ("universalAnger",              "Universeller Zorn",                 "bool", "false"),
                ("tntExplodes",                 "TNT explodiert",                    "bool", "true"),
                ("pvp",                         "PvP (via server.properties)",       "bool", "true"),
                ("maxEntityCramming",           "Max. Entity-Crammed",               "int",  "24"),
                ("randomTickSpeed",             "Zufalls-Tick-Geschwindigkeit",      "int",  "3"),
                ("spawnRadius",                 "Spawn-Radius",                      "int",  "10"),
                ("maxCommandChainLength",       "Max. Befehlsketten-Länge",         "int",  "65536"),
                ("playersSleepingPercentage",   "Schlaf-Prozentsatz",                "int",  "100"),
                ("snowAccumulationHeight",      "Schneehöhe",                        "int",  "1"),
            ]

            gf = ctk.CTkScrollableFrame(parent, fg_color=SIDEBAR_BG, corner_radius=10, height=400)
            gf.pack(fill="x", padx=4, pady=4)

            # Gamerules aus Konsole lesen falls Server läuft
            cached = getattr(self, "_gamerule_cache", {})

            def _send_gamerule(rule, val):
                """Setzt eine Spielregel im laufenden Server."""
                if self.proc and self.proc.poll() is None:
                    try:
                        self.proc.stdin.write(f"gamerule {rule} {val}\n")
                        self.proc.stdin.flush()
                    except: pass

            for key, label, rtype, default in GAMERULES:
                row = ctk.CTkFrame(gf, fg_color="transparent")
                row.pack(fill="x", padx=10, pady=3)
                row.grid_columnconfigure(0, weight=1)

                ctk.CTkLabel(row, text=label, text_color=TEXT,
                             font=ctk.CTkFont("Segoe UI",12), anchor="w"
                             ).grid(row=0, column=0, sticky="w")
                ctk.CTkLabel(row, text=key, text_color="#555",
                             font=ctk.CTkFont("Segoe UI",9), anchor="w"
                             ).grid(row=1, column=0, sticky="w")

                cur = cached.get(key, default)

                if rtype == "bool":
                    var = ctk.BooleanVar(value=cur.lower() == "true")
                    sw_lbl = [None]
                    def _on_toggle(v=None, k=key, bv=None, sl=None):
                        val = "true" if bv.get() else "false"
                        _send_gamerule(k, val)
                        if sl[0]:
                            sl[0].configure(text="✓", text_color=GREEN)
                            sl[0].after(1500, lambda: sl[0].configure(text=""))
                    sw = ctk.CTkSwitch(row, variable=var, text="",
                                       progress_color=GREEN, button_color=TEXT,
                                       command=lambda k=key, bv=var, sl=sw_lbl: _on_toggle(k=k, bv=bv, sl=sl))
                    sw.grid(row=0, column=1, rowspan=2, padx=(0,8))
                    lbl = ctk.CTkLabel(row, text="", text_color=GREEN,
                                       font=ctk.CTkFont("Segoe UI",11), width=20)
                    lbl.grid(row=0, column=2, rowspan=2)
                    sw_lbl[0] = lbl
                else:
                    var = tk.StringVar(value=cur)
                    ent = ctk.CTkEntry(row, textvariable=var, width=80, height=28,
                                       fg_color=CARD, text_color=TEXT,
                                       font=ctk.CTkFont("Segoe UI",11))
                    ent.grid(row=0, column=1, rowspan=2, padx=(0,4))
                    save_lbl = ctk.CTkLabel(row, text="", text_color=GREEN,
                                            font=ctk.CTkFont("Segoe UI",11), width=20)
                    save_lbl.grid(row=0, column=2, rowspan=2)
                    def _save_int(k=key, v=var, sl=save_lbl):
                        _send_gamerule(k, v.get())
                        sl.configure(text="✓", text_color=GREEN)
                        sl.after(1500, lambda: sl.configure(text=""))
                    ctk.CTkButton(row, text="✓", width=28, height=28,
                                  fg_color=CARD, text_color=GREEN, corner_radius=6,
                                  command=_save_int).grid(row=0, column=3, rowspan=2, padx=4)

                ctk.CTkFrame(gf, fg_color=BORDER, height=1).pack(fill="x", padx=10)

        def _rebuild_world_list():
            for w in worlds_scroll.winfo_children(): w.destroy()
            # Server-Welten
            worlds = []
            try: worlds = sorted([d for d in srv_dir.iterdir() if d.is_dir() and (d/"level.dat").exists()])
            except: pass

            # Launcher-Welten
            mc_saves = Path(os.environ.get("APPDATA","")) / ".minecraft" / "saves"
            launcher_worlds = []
            try:
                if mc_saves.exists():
                    launcher_worlds = sorted([d for d in mc_saves.iterdir() if d.is_dir() and (d/"level.dat").exists()])
            except: pass

            if not worlds and not launcher_worlds:
                ctk.CTkLabel(worlds_scroll, text="Keine Welten.\nServer starten.",
                             text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",11),
                             wraplength=200).pack(pady=20)
                _show_create_panel()
                return

            def _world_btn(w, dim_name, icon, color, is_launcher=False):
                is_sel = _selected_world[0] == w
                lbl = f"{icon}  {dim_name}"
                btn = ctk.CTkButton(worlds_scroll, text=lbl, anchor="w", height=44,
                                    fg_color=CARD if is_sel else "transparent",
                                    hover_color=CARD,
                                    text_color=color if is_sel else (TEXT_MUTED if is_launcher else TEXT),
                                    font=ctk.CTkFont("Segoe UI",12,"bold" if is_sel else "normal"),
                                    corner_radius=8,
                                    command=lambda wp=w: (_show_world_detail(wp), _rebuild_world_list()))
                btn.pack(fill="x", pady=2)

            # Server-Welten
            if worlds:
                ctk.CTkLabel(worlds_scroll, text="Server-Welten",
                             text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10,"bold")
                             ).pack(anchor="w", padx=4, pady=(4,2))
                for w in worlds:
                    dim_name, icon, color = DIM_INFO.get(w.name, (w.name, "🗺", TEXT_MUTED))
                    _world_btn(w, dim_name, icon, color)

            # Launcher-Welten
            if launcher_worlds:
                ctk.CTkFrame(worlds_scroll, fg_color=BORDER, height=1).pack(fill="x", pady=6)
                ctk.CTkLabel(worlds_scroll, text="🎮 Minecraft Launcher",
                             text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10,"bold")
                             ).pack(anchor="w", padx=4, pady=(0,2))
                for w in launcher_worlds:
                    _world_btn(w, w.name, "??", "#86efac", is_launcher=True)

            # Neue Welt / Import
            ctk.CTkFrame(worlds_scroll, fg_color=BORDER, height=1).pack(fill="x", pady=8)
            ctk.CTkButton(worlds_scroll, text="＋ Neue Welt",
                          fg_color="transparent", hover_color=CARD, text_color=GREEN,
                          font=ctk.CTkFont("Segoe UI",11,"bold"), height=36, corner_radius=8,
                          command=_show_create_panel).pack(fill="x")
            ctk.CTkButton(worlds_scroll, text="📥 Welt importieren",
                          fg_color="transparent", hover_color=CARD, text_color=TEXT_MUTED,
                          font=ctk.CTkFont("Segoe UI",11), height=36, corner_radius=8,
                          command=_show_import_panel).pack(fill="x", pady=2)

            # Erste Welt auto-selektieren
            all_worlds = worlds + launcher_worlds
            if all_worlds and _selected_world[0] is None:
                _show_world_detail(all_worlds[0])
                _selected_world[0] = all_worlds[0]

        def _show_create_panel():
            if _detail_frame[0]: _detail_frame[0].destroy()
            frame = ctk.CTkScrollableFrame(right, fg_color="transparent")
            frame.grid(row=0, column=0, sticky="nsew", padx=16, pady=12)
            _detail_frame[0] = frame

            ctk.CTkLabel(frame, text="Neue Welt erstellen",
                         font=ctk.CTkFont("Segoe UI",16,"bold"), text_color=TEXT).pack(anchor="w", pady=(0,12))

            def section(title):
                ctk.CTkLabel(frame, text=title, text_color=TEXT_MUTED,
                             font=ctk.CTkFont("Segoe UI",11,"bold")).pack(anchor="w", pady=(10,2))
                f = ctk.CTkFrame(frame, fg_color=SIDEBAR_BG, corner_radius=10)
                f.pack(fill="x")
                return f

            def row_e(p, label, default="", ph=""):
                r = ctk.CTkFrame(p, fg_color="transparent"); r.pack(fill="x", padx=12, pady=5)
                ctk.CTkLabel(r, text=label, text_color=TEXT_MUTED,
                             font=ctk.CTkFont("Segoe UI",12), width=180, anchor="w").pack(side="left")
                var = tk.StringVar(value=default)
                ctk.CTkEntry(r, textvariable=var, placeholder_text=ph, fg_color=CARD,
                             text_color=TEXT, height=30, width=240).pack(side="left")
                return var

            def row_o(p, label, opts, default=None):
                r = ctk.CTkFrame(p, fg_color="transparent"); r.pack(fill="x", padx=12, pady=5)
                ctk.CTkLabel(r, text=label, text_color=TEXT_MUTED,
                             font=ctk.CTkFont("Segoe UI",12), width=180, anchor="w").pack(side="left")
                var = tk.StringVar(value=default or opts[0])
                ctk.CTkOptionMenu(r, variable=var, values=opts, fg_color=CARD,
                                  button_color=GREEN, text_color=TEXT, width=240).pack(side="left")
                return var

            def row_t(p, label, default=True):
                r = ctk.CTkFrame(p, fg_color="transparent"); r.pack(fill="x", padx=12, pady=5)
                ctk.CTkLabel(r, text=label, text_color=TEXT_MUTED,
                             font=ctk.CTkFont("Segoe UI",12), width=180, anchor="w").pack(side="left")
                var = ctk.BooleanVar(value=default)
                ctk.CTkSwitch(r, variable=var, text="", progress_color=GREEN).pack(side="left")
                return var

            f1 = section("Grundeinstellungen")
            v_name     = row_e(f1, "Weltname", "world", "z.B. meine_welt")
            v_seed     = row_e(f1, "Seed (leer = zufällig)", "", "z.B. 12345")
            v_mode     = row_o(f1, "Spielmodus", ["survival","creative","adventure","spectator"])
            v_diff     = row_o(f1, "Schwierigkeit", ["normal","easy","hard","peaceful"])
            v_type     = row_o(f1, "Welttyp", ["default","flat","largeBiomes","amplified"])

            f2 = section("Features")
            v_structs  = row_t(f2, "Strukturen (Dörfer, Tempel…)", True)
            v_nether   = row_t(f2, "Nether aktivieren", True)
            v_end      = row_t(f2, "The End aktivieren", True)
            v_pvp      = row_t(f2, "PvP", True)
            v_hardcore = row_t(f2, "Hardcore", False)
            v_bonus    = row_t(f2, "Bonus-Kiste", False)

            f3 = section("Spawn")
            v_monsters = row_t(f3, "Monster", True)
            v_animals  = row_t(f3, "Tiere", True)
            v_npcs     = row_t(f3, "Dorfbewohner", True)

            def _create():
                wname = v_name.get().strip() or "world"
                old = srv_dir / wname
                if old.exists():
                    if not messagebox.askyesno("Überschreiben", f"Welt '{wname}' löschen und neu erstellen?"): return
                    shutil.rmtree(old)
                props = {
                    "level-name": wname, "level-seed": v_seed.get().strip(),
                    "gamemode": v_mode.get(), "difficulty": v_diff.get(),
                    "level-type": v_type.get(),
                    "generate-structures": "true" if v_structs.get() else "false",
                    "allow-nether": "true" if v_nether.get() else "false",
                    "pvp": "true" if v_pvp.get() else "false",
                    "spawn-monsters": "true" if v_monsters.get() else "false",
                    "spawn-animals": "true" if v_animals.get() else "false",
                    "spawn-npcs": "true" if v_npcs.get() else "false",
                    "hardcore": "true" if v_hardcore.get() else "false",
                    "generate-bonus-chest": "true" if v_bonus.get() else "false",
                }
                for k, v in props.items(): _write_prop(k, v)
                messagebox.showinfo("Fertig", f"✓ Welt '{wname}' wird beim nächsten Start generiert.")
                _rebuild_world_list()

            ctk.CTkButton(frame, text="✓ Welt erstellen",
                          fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                          font=ctk.CTkFont("Segoe UI",13,"bold"), height=44, corner_radius=10,
                          command=_create).pack(fill="x", pady=(16,4))

        def _show_import_panel():
            if _detail_frame[0]: _detail_frame[0].destroy()
            frame = ctk.CTkFrame(right, fg_color="transparent")
            frame.grid(row=0, column=0, sticky="nsew", padx=16, pady=12)
            frame.grid_rowconfigure(2, weight=1)
            frame.grid_columnconfigure(0, weight=1)
            _detail_frame[0] = frame

            ctk.CTkLabel(frame, text="Welt importieren",
                         font=ctk.CTkFont("Segoe UI",16,"bold"), text_color=TEXT
                         ).grid(row=0, column=0, sticky="w", pady=(0,12))

            # Drag-and-Drop Bereich
            dnd_frame = ctk.CTkFrame(frame, fg_color=CARD, corner_radius=12,
                                     border_width=2, border_color=BORDER)
            dnd_frame.grid(row=1, column=0, sticky="ew", pady=8)
            ctk.CTkLabel(dnd_frame,
                text="📂\n\nDatei hier hineinziehen\noder Knopf unten drücken",
                text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",13),
                justify="center").pack(pady=30)

            # Launcher-Welten
            mc_saves = Path(os.environ.get("APPDATA","")) / ".minecraft" / "saves"
            launcher_worlds = []
            if mc_saves.exists():
                try: launcher_worlds = [d.name for d in mc_saves.iterdir() if d.is_dir()]
                except: pass

            if launcher_worlds:
                ctk.CTkLabel(frame, text="Aus Minecraft Launcher:",
                             text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",11,"bold")
                             ).grid(row=2, column=0, sticky="w", pady=(8,2))
                sel = tk.StringVar(value=launcher_worlds[0])
                sel_row = ctk.CTkFrame(frame, fg_color="transparent")
                sel_row.grid(row=3, column=0, sticky="ew")
                sel_row.grid_columnconfigure(0, weight=1)
                ctk.CTkOptionMenu(sel_row, variable=sel, values=launcher_worlds,
                                  fg_color=CARD, button_color=GREEN, text_color=TEXT
                                  ).grid(row=0, column=0, sticky="ew", padx=(0,8))
                def _import_launcher():
                    src = mc_saves / sel.get()
                    dst = srv_dir / "world"
                    if dst.exists():
                        if not messagebox.askyesno("Überschreiben", "Aktuelle Welt ersetzen?"): return
                        shutil.rmtree(dst)
                    shutil.copytree(str(src), str(dst))
                    _write_prop("level-name", "world")
                    messagebox.showinfo("Import", "✓ Welt importiert!")
                    _rebuild_world_list()
                ctk.CTkButton(sel_row, text="Importieren", width=100, height=34,
                              fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                              command=_import_launcher).grid(row=0, column=1)

            # ZIP-Import
            def _import_zip():
                p = filedialog.askopenfilename(
                    title="Welt-ZIP wählen",
                    filetypes=[("ZIP","*.zip"),("Alle","*.*")])
                if not p: return
                dst = srv_dir / "world"
                if dst.exists():
                    if not messagebox.askyesno("Überschreiben","Aktuelle Welt ersetzen?"): return
                    shutil.rmtree(dst)
                shutil.unpack_archive(p, str(srv_dir))
                messagebox.showinfo("Import","✓ Welt importiert!")
                _rebuild_world_list()

            ctk.CTkButton(frame, text="📂 ZIP-Datei wählen & importieren",
                          fg_color=CARD, text_color=TEXT, height=36, corner_radius=8,
                          command=_import_zip).grid(row=4, column=0, sticky="ew", pady=(12,0))

        _rebuild_world_list()


    def _bkp_world(self,path,name):
        d=APP_DIR/"world_backups"; d.mkdir(exist_ok=True)
        ts=time.strftime("%Y%m%d_%H%M%S"); out=d/f"{name}_{ts}"
        threading.Thread(target=lambda:shutil.make_archive(str(out),"zip",str(path.parent),path.name),daemon=True).start()
        messagebox.showinfo("Backup",f"Backup wird erstellt:\n{out}.zip")

    def _del_world(self,path,name):
        if messagebox.askyesno("Löschen",f"'{name}' wirklich löschen? Nicht rückgängig!"):
            shutil.rmtree(path,ignore_errors=True); self._p_worlds()

    def _import_world(self,srv_dir):
        p=filedialog.askopenfilename(title="Welt importieren",filetypes=[("ZIP","*.zip")])
        if p: shutil.unpack_archive(p,str(srv_dir)); messagebox.showinfo("Import","Welt importiert."); self._p_worlds()

    def _get_seed(self):
        if self.proc and self.proc.poll() is None:
            try: self.proc.stdin.write("seed\n"); self.proc.stdin.flush()
            except: pass
            messagebox.showinfo("Seed","Seed-Befehl gesendet — sieh in der Konsole nach.")
        else:
            messagebox.showinfo("Seed","Server starten und dann Seed über Konsole abrufen.")

    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    # PAGE: BACKUPS
    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    def _p_backups(self):
        self._page_header("Backups")
        self.content.grid_rowconfigure(1, weight=1)

        outer = ctk.CTkFrame(self.content, fg_color="transparent")
        outer.grid(row=1, column=0, sticky="nsew")
        outer.grid_columnconfigure(0, weight=1)
        outer.grid_columnconfigure(1, weight=0)
        outer.grid_rowconfigure(0, weight=1)

        # ── Linke Spalte: Backup-Anbieter + Erstellen + Liste ────────────────
        left_scroll = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        left_scroll.grid(row=0, column=0, sticky="nsew", padx=(20,8), pady=(0,16))

        # Backup-Anbieter
        bkp_cfg = self.cfg.get("backup_providers", {})

        prov_hdr = ctk.CTkFrame(left_scroll, fg_color=SIDEBAR_BG, corner_radius=10)
        prov_hdr.pack(fill="x", pady=(0,8))
        prov_hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(prov_hdr, text="?? Backup-Anbieter",
                     font=ctk.CTkFont("Segoe UI",13,"bold"), text_color=TEXT
                     ).grid(row=0, column=0, padx=14, pady=(12,4), sticky="w")

        providers_frame = ctk.CTkFrame(prov_hdr, fg_color="transparent")
        providers_frame.grid(row=1, column=0, padx=14, pady=(0,8), sticky="ew")

        # Lokaler Speicher immer verfügbar
        bkp_dir_v = ctk.StringVar(value=bkp_cfg.get("local_dir", str(APP_DIR/"backups")))
        loc_row = ctk.CTkFrame(providers_frame, fg_color=CARD, corner_radius=8)
        loc_row.pack(fill="x", pady=3)
        loc_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(loc_row, text="💾", font=ctk.CTkFont("Segoe UI",18), width=36
                     ).grid(row=0, column=0, padx=8, pady=10)
        ctk.CTkLabel(loc_row, text=self.username, font=ctk.CTkFont("Segoe UI",11,"bold"),
                     text_color=TEXT, anchor="w").grid(row=0, column=1, sticky="w")
        sz_txt = ""
        try:
            bkp_sz = sum(f.stat().st_size for f in (APP_DIR/"backups").rglob("*") if f.is_file())
            sz_txt = f"{bkp_sz/1e9:.2f} GB / ∞"
        except: pass
        ctk.CTkLabel(loc_row, text=sz_txt, font=ctk.CTkFont("Segoe UI",9),
                     text_color=TEXT_MUTED).grid(row=1, column=1, sticky="w")

        # Google Drive / OneDrive / Dropbox Buttons
        def _add_provider_popup():
            win = ctk.CTkToplevel(self)
            win.title("Backup-Anbieter verknüpfen")
            win.geometry("320x200")
            win.configure(fg_color=SIDEBAR_BG)
            win.grab_set()
            ctk.CTkLabel(win, text="Neuen Backup-Anbieter verknüpfen",
                         font=ctk.CTkFont("Segoe UI",13,"bold"), text_color=TEXT).pack(pady=16)
            for name, url in [
                ("Google Drive", "https://drive.google.com"),
                ("OneDrive",     "https://onedrive.live.com"),
                ("Dropbox",      "https://www.dropbox.com"),
            ]:
                ctk.CTkButton(win, text=name, height=36, fg_color=CARD,
                              text_color=TEXT, font=ctk.CTkFont("Segoe UI",12,"bold"),
                              command=lambda u=url, n=name: (
                                  __import__("webbrowser").open(u),
                                  messagebox.showinfo("Hinweis",
                                    f"{n} wurde geöffnet.\nNach der Anmeldung kannst du manuell\nDateien in den Backup-Ordner hochladen."),
                                  win.destroy()
                              )).pack(padx=20, pady=4, fill="x")

        ctk.CTkButton(providers_frame, text="＋ Anbieter hinzufügen",
                      fg_color="transparent", hover_color=CARD, text_color=GREEN,
                      font=ctk.CTkFont("Segoe UI",11,"bold"), height=32, corner_radius=6,
                      command=_add_provider_popup).pack(anchor="w", pady=4)

        # ── Backup erstellen ──────────────────────────────────────────────────
        create_f = ctk.CTkFrame(left_scroll, fg_color=SIDEBAR_BG, corner_radius=10)
        create_f.pack(fill="x", pady=8)
        ctk.CTkLabel(create_f, text="?? Backup erstellen",
                     font=ctk.CTkFont("Segoe UI",13,"bold"), text_color=TEXT
                     ).pack(padx=14, pady=(12,4), anchor="w")

        name_row = ctk.CTkFrame(create_f, fg_color="transparent")
        name_row.pack(fill="x", padx=14, pady=4)
        name_row.grid_columnconfigure(0, weight=1)
        bkp_name_v = ctk.StringVar()
        ctk.CTkEntry(name_row, textvariable=bkp_name_v,
                     placeholder_text="Backupname (optional)",
                     fg_color=CARD, text_color=TEXT, height=34
                     ).grid(row=0, column=0, sticky="ew", padx=(0,8))

        status_lbl = ctk.CTkLabel(create_f, text="",
                                  text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",11))
        status_lbl.pack(padx=14)

        def _do_backup():
            if not self.server_name: return
            out = APP_DIR / "backups"; out.mkdir(parents=True, exist_ok=True)
            ts    = time.strftime("%Y%m%d_%H%M%S")
            name  = bkp_name_v.get().strip() or self.cfg.get("name", self.server_name)
            fname = f"{name}_{ts}"
            status_lbl.configure(text="Backup läuft…", text_color="#f39c12")
            def _run():
                import zipfile as _zf
                srv_path = Path(self.cfg.get("dir", ""))
                zip_path = out / (fname + ".zip")
                skipped  = 0
                total    = 0
                try:
                    with _zf.ZipFile(str(zip_path), "w", _zf.ZIP_DEFLATED) as zf:
                        for f in srv_path.rglob("*"):
                            if not f.is_file(): continue
                            total += 1
                            try:
                                zf.write(f, f.relative_to(srv_path))
                            except (PermissionError, OSError):
                                skipped += 1  # Von Java gesperrte Dateien überspringen
                    hint = f" ({skipped} Dateien übersprungen)" if skipped else ""
                    status_lbl.configure(text=f"✓ {fname}.zip{hint}", text_color=GREEN)
                    self.after(500, self._p_backups)
                except Exception as e:
                    status_lbl.configure(text=f"Fehler: {e}", text_color=RED)
            threading.Thread(target=_run, daemon=True).start()

        ctk.CTkButton(create_f, text="?? Backup erstellen",
                      fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                      font=ctk.CTkFont("Segoe UI",13,"bold"), height=40, corner_radius=8,
                      command=_do_backup).pack(padx=14, pady=(4,14), fill="x")

        # ── Teilen-Funktion (.minlocal Export) ────────────────────────────────
        share_f = ctk.CTkFrame(left_scroll, fg_color=SIDEBAR_BG, corner_radius=10)
        share_f.pack(fill="x", pady=8)
        ctk.CTkLabel(share_f, text="📤 Server teilen (.minlocal)",
                     font=ctk.CTkFont("Segoe UI",13,"bold"), text_color=TEXT
                     ).pack(padx=14, pady=(12,4), anchor="w")
        ctk.CTkLabel(share_f,
            text="Exportiert den Server als .minlocal-Datei.\nBeinhaltet: Karte, Einstellungen, Plugins.",
            text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",11), justify="left"
            ).pack(padx=14, anchor="w")
        share_lbl = ctk.CTkLabel(share_f, text="", text_color=GREEN, font=ctk.CTkFont("Segoe UI",11))
        share_lbl.pack(padx=14)
        def _export_minlocal():
            if not self.server_name: return
            dst = filedialog.asksaveasfilename(
                defaultextension=".minlocal",
                initialfile=f"{self.cfg.get('name', self.server_name)}.minlocal",
                filetypes=[("MineHost Local", "*.minlocal"), ("ZIP", "*.zip")])
            if not dst: return
            share_lbl.configure(text="Exportiere…", text_color="#f39c12")
            def _run():
                import zipfile as _zf, json as _json
                srv_path = Path(self.cfg.get("dir",""))
                try:
                    with _zf.ZipFile(dst, "w", _zf.ZIP_DEFLATED) as zf:
                        # Config einbetten
                        cfg_data = dict(self.cfg)
                        cfg_data["exported_by"] = self.username
                        cfg_data["export_date"] = time.strftime("%Y-%m-%d %H:%M")
                        zf.writestr("minehost_config.json",
                                    _json.dumps(cfg_data, indent=2, ensure_ascii=False))
                        # Alle Server-Dateien
                        for f in srv_path.rglob("*"):
                            if f.is_file():
                                try: zf.write(f, f.relative_to(srv_path))
                                except: pass
                    share_lbl.configure(text=f"✓ Exportiert!", text_color=GREEN)
                except Exception as e:
                    share_lbl.configure(text=f"Fehler: {e}", text_color=RED)
            threading.Thread(target=_run, daemon=True).start()
        ctk.CTkButton(share_f, text="📤 Als .minlocal exportieren",
                      fg_color=BLUE, text_color="#fff",
                      font=ctk.CTkFont("Segoe UI",12,"bold"), height=38, corner_radius=8,
                      command=_export_minlocal).pack(padx=14, pady=(4,14), fill="x")

        # ── Vorhandene Backups ────────────────────────────────────────────────
        bkp_dir = APP_DIR / "backups"; bkp_dir.mkdir(exist_ok=True)
        zips = sorted(bkp_dir.glob("*.zip"), reverse=True)
        if zips:
            ctk.CTkLabel(left_scroll, text=f"Automatisches Backup",
                         font=ctk.CTkFont("Segoe UI",12,"bold"), text_color=TEXT
                         ).pack(anchor="w", pady=(8,4))
            for z in zips[:15]:
                sz = z.stat().st_size
                sz_txt = f"{sz/1e9:.2f} GB" if sz > 1e9 else f"{sz/1e6:.1f} MB"
                parts = z.stem.split("_")
                date_str = ""
                if len(parts) >= 2:
                    try:
                        raw = parts[-2] + parts[-1]
                        date_str = f"{raw[:4]}.{raw[4:6]}.{raw[6:8]}, {raw[8:10]}:{raw[10:12]}"
                    except: date_str = z.stem

                row = ctk.CTkFrame(left_scroll, fg_color="#1a1a1a", corner_radius=8)
                row.pack(fill="x", pady=2)
                row.grid_columnconfigure(0, weight=1)

                info = ctk.CTkFrame(row, fg_color="transparent")
                info.grid(row=0, column=0, padx=12, pady=8, sticky="w")
                ctk.CTkLabel(info, text=f"🤖 {date_str}",
                             font=ctk.CTkFont("Segoe UI",11,"bold"), text_color=TEXT, anchor="w").pack(anchor="w")
                ctk.CTkLabel(info, text=f"@ {self.username}  •  {self.cfg.get('name','')}  •  {self.cfg.get('type_label','Vanilla')} {self.cfg.get('mc_version','')}",
                             font=ctk.CTkFont("Segoe UI",9), text_color=TEXT_MUTED, anchor="w").pack(anchor="w")

                right_btns = ctk.CTkFrame(row, fg_color="transparent")
                right_btns.grid(row=0, column=1, padx=8)
                ctk.CTkLabel(right_btns, text=sz_txt, text_color=TEXT_MUTED,
                             font=ctk.CTkFont("Segoe UI",9)).pack(anchor="e")

                def _restore(zp=z):
                    if not messagebox.askyesno("Wiederherstellen",
                        f"Server aus '{zp.name}' wiederherstellen?\nAktuelle Dateien werden ÜBERSCHRIEBEN!"): return
                    srv_path = Path(self.cfg.get("dir",""))
                    shutil.unpack_archive(str(zp), str(srv_path))
                    messagebox.showinfo("Fertig", "✓ Backup wiederhergestellt!")

                def _del_bkp(zp=z):
                    if messagebox.askyesno("Löschen", f"Backup '{zp.name}' löschen?"):
                        zp.unlink(); self._p_backups()

                ctk.CTkButton(right_btns, text="↩ Wiederherstellen", width=120, height=28,
                              fg_color="#f39c12", text_color="#000",
                              font=ctk.CTkFont("Segoe UI",10,"bold"), corner_radius=6,
                              command=_restore).pack(pady=2)
                ctk.CTkButton(right_btns, text="🗑", width=32, height=28,
                              fg_color="#3a1010", text_color=RED, corner_radius=6,
                              command=_del_bkp).pack()

        # ── Rechte Spalte: Auto-Backup ────────────────────────────────────────
        right_col = ctk.CTkFrame(outer, fg_color=SIDEBAR_BG, corner_radius=10, width=260)
        right_col.grid(row=0, column=1, sticky="nsew", padx=(0,20), pady=(0,16))
        right_col.grid_propagate(False)

        auto_var = ctk.BooleanVar(value=self.cfg.get("auto_backup", False))
        auto_hdr = ctk.CTkFrame(right_col, fg_color="transparent")
        auto_hdr.pack(fill="x", padx=14, pady=(14,4))
        auto_hdr.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(auto_hdr, text="🤖 Automatische Backups",
                     font=ctk.CTkFont("Segoe UI",12,"bold"), text_color=TEXT
                     ).grid(row=0, column=0, sticky="w")
        def _toggle_auto():
            self.cfg["auto_backup"] = auto_var.get()
            save_server_cfg(self.server_name, self.cfg)
        ctk.CTkSwitch(auto_hdr, variable=auto_var, text="",
                      progress_color=GREEN, command=_toggle_auto).grid(row=0, column=1)

        ctk.CTkLabel(right_col,
            text="Erstelle automatisch Backups,\nwenn der Server gestoppt wird\nund das letzte Backup älter\nals die eingestellte Zeit ist.",
            text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10),
            justify="left").pack(padx=14, pady=(0,8), anchor="w")

        ctk.CTkFrame(right_col, fg_color=BORDER, height=1).pack(fill="x", padx=14, pady=4)

        # Min. Zeit zwischen Backups
        min_h_var = ctk.IntVar(value=self.cfg.get("auto_backup_min_hours", 24))
        ctk.CTkLabel(right_col, text="Min. Stunden zwischen Backups:",
                     text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10)).pack(padx=14, anchor="w")
        h_row = ctk.CTkFrame(right_col, fg_color="transparent")
        h_row.pack(fill="x", padx=14, pady=4)
        h_row.grid_columnconfigure(0, weight=1)
        ctk.CTkSlider(h_row, from_=6, to=48, number_of_steps=42,
                      variable=min_h_var, progress_color=GREEN
                      ).grid(row=0, column=0, sticky="ew")
        h_lbl = ctk.CTkLabel(h_row, text=f"{min_h_var.get()}h",
                              text_color=TEXT, font=ctk.CTkFont("Segoe UI",11), width=36)
        h_lbl.grid(row=0, column=1, padx=6)
        def _update_h(v):
            h_lbl.configure(text=f"{int(float(v))}h")
            self.cfg["auto_backup_min_hours"] = int(float(v))
            save_server_cfg(self.server_name, self.cfg)
        ctk.CTkSlider(h_row, from_=6, to=48, number_of_steps=42,
                      variable=min_h_var, progress_color=GREEN,
                      command=_update_h).grid(row=0, column=0, sticky="ew")

        ctk.CTkFrame(right_col, fg_color=BORDER, height=1).pack(fill="x", padx=14, pady=4)

        # Max Backups
        max_bkp_var = ctk.IntVar(value=self.cfg.get("auto_backup_max", 5))
        ctk.CTkLabel(right_col,
            text="Lösche automatisch ältere Backups,\nwenn mehr als N vorhanden sind:",
            text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10),
            justify="left").pack(padx=14, anchor="w")
        n_row = ctk.CTkFrame(right_col, fg_color="transparent")
        n_row.pack(fill="x", padx=14, pady=4)
        n_row.grid_columnconfigure(0, weight=1)
        n_lbl = ctk.CTkLabel(n_row, text=str(max_bkp_var.get()),
                             text_color=TEXT, font=ctk.CTkFont("Segoe UI",11), width=36)
        def _update_n(v):
            n_lbl.configure(text=str(int(float(v))))
            self.cfg["auto_backup_max"] = int(float(v))
            save_server_cfg(self.server_name, self.cfg)
        ctk.CTkSlider(n_row, from_=1, to=20, number_of_steps=19,
                      variable=max_bkp_var, progress_color=GREEN,
                      command=_update_n).grid(row=0, column=0, sticky="ew")
        n_lbl.grid(row=0, column=1, padx=6)

        ctk.CTkLabel(right_col, text="Alle meine Backups →",
                     text_color=BLUE, font=ctk.CTkFont("Segoe UI",10),
                     cursor="hand2").pack(padx=14, pady=(12,4), anchor="e")

    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    # PAGE: ZUGRIFF
    # ??????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
    def _p_access(self):
        self._page_header("Zugriff")
        self.content.grid_rowconfigure(1, weight=1)
        access = load_json(ACCESS_DB, {})
        srv_access = access.get(self.server_name or "_", {})
        all_users  = [u for u in load_users() if u != self.username]

        scroll = ctk.CTkScrollableFrame(self.content,fg_color="transparent")
        scroll.grid(row=1,column=0,sticky="nsew",padx=20,pady=(0,16))

        ctk.CTkLabel(scroll,
            text="Gib anderen Benutzern Zugriff und lege fest, was sie auf diesem Server dürfen.",
            text_color=TEXT_MUTED,font=ctk.CTkFont("Segoe UI",12),wraplength=700
        ).pack(anchor="w",pady=(0,12))

        # ── Benutzer hinzufügen ───────────────────────────────────────────────
        add_card = ctk.CTkFrame(scroll, fg_color=SIDEBAR_BG, corner_radius=10)
        add_card.pack(fill="x", pady=(0,10))
        ctk.CTkLabel(add_card, text="+ Benutzer hinzufügen",
                     font=ctk.CTkFont("Segoe UI",13,"bold"), text_color=GREEN
                     ).pack(anchor="w", padx=16, pady=(12,6))

        add_row = ctk.CTkFrame(add_card, fg_color="transparent")
        add_row.pack(fill="x", padx=16, pady=(0,4))
        add_row.grid_columnconfigure(0, weight=1)
        add_row.grid_columnconfigure(1, weight=1)

        u_entry = ctk.CTkEntry(add_row, placeholder_text="Benutzername",
                               fg_color="#111", text_color=TEXT, height=34)
        u_entry.grid(row=0, column=0, padx=(0,6), sticky="ew")
        p_entry = ctk.CTkEntry(add_row, placeholder_text="Passwort",
                               fg_color="#111", text_color=TEXT, height=34, show="•")
        p_entry.grid(row=0, column=1, padx=(0,6), sticky="ew")

        add_err = ctk.CTkLabel(add_card, text="", text_color=RED,
                               font=ctk.CTkFont("Segoe UI",10))
        add_err.pack(anchor="w", padx=16)

        def _add_user():
            uname = u_entry.get().strip()
            pw    = p_entry.get()
            if not uname or not pw:
                add_err.configure(text="Benutzername und Passwort ausfüllen.")
                return
            users = load_users()
            if uname in users:
                add_err.configure(text=f"'{uname}' existiert bereits.")
                return
            users[uname] = {"pw": hash_pw(pw), "email": "", "role": "user"}
            save_users(users)
            self._p_access()   # Seite neu laden

        ctk.CTkButton(add_card, text="Hinzufügen", fg_color=GREEN, hover_color=GREEN_HOV,
                      text_color="#000", height=34, width=130, font=ctk.CTkFont("Segoe UI",12,"bold"),
                      command=_add_user).pack(anchor="w", padx=16, pady=(4,12))

        for user in all_users:
            user_perms = srv_access.get(user, {})
            card = ctk.CTkFrame(scroll, fg_color=SIDEBAR_BG, corner_radius=10)
            card.pack(fill="x", pady=6)
            ctk.CTkLabel(card, text=f"👤  {user}",
                         font=ctk.CTkFont("Segoe UI",14,"bold"), text_color=TEXT
                         ).pack(padx=16, pady=(12,4), anchor="w")
            perm_vars = {}
            grid2 = ctk.CTkFrame(card, fg_color="transparent")
            grid2.pack(padx=14, fill="x")
            for ci, (key, label) in enumerate(PERMISSIONS):
                r2, c2 = divmod(ci, 2)
                pf = ctk.CTkFrame(grid2, fg_color=CARD, corner_radius=8)
                pf.grid(row=r2, column=c2, padx=3, pady=3, sticky="ew")
                grid2.grid_columnconfigure(c2, weight=1)
                var = ctk.BooleanVar(value=user_perms.get(key, False))
                ctk.CTkCheckBox(pf, text=label, variable=var,
                                text_color=TEXT, font=ctk.CTkFont("Segoe UI",11),
                                fg_color=GREEN, hover_color=GREEN_HOV,
                                checkmark_color="#000").pack(padx=10, pady=6, anchor="w")
                perm_vars[key] = var
            br = ctk.CTkFrame(card, fg_color="transparent")
            br.pack(padx=16, pady=(8,12), fill="x")
            def save_perm(u=user, pv=perm_vars):
                ad = load_json(ACCESS_DB, {}); sk = self.server_name or "_"
                if sk not in ad: ad[sk] = {}
                ad[sk][u] = {k: v.get() for k, v in pv.items()}
                save_json(ACCESS_DB, ad)
                messagebox.showinfo("Gespeichert", f"Berechtigungen für {u} gespeichert.")
            def revoke(u=user):
                ad = load_json(ACCESS_DB, {}); sk = self.server_name or "_"
                if sk in ad and u in ad[sk]: del ad[sk][u]; save_json(ACCESS_DB, ad)
                self._p_access()
            ctk.CTkButton(br, text="Speichern", fg_color=GREEN, hover_color=GREEN_HOV,
                          text_color="#000", height=34, width=120, command=save_perm
                          ).pack(side="left", padx=(0,8))
            ctk.CTkButton(br, text="Zugriff entziehen", fg_color=RED, text_color="#fff",
                          height=34, width=140, command=revoke).pack(side="left")

    # ── Hilfs-Widgets ─────────────────────────────────────────────────────────
    def _page_header(self, title):
        self.content.grid_columnconfigure(0, weight=1)
        hdr = ctk.CTkFrame(self.content, fg_color=SIDEBAR_BG, corner_radius=0, height=56)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_propagate(False)
        ctk.CTkLabel(hdr, text=title,
                     font=ctk.CTkFont("Segoe UI",18,"bold"), text_color=TEXT
                     ).pack(side="left", padx=24, pady=14)
        return hdr

    def _tabs(self, names):
        t = ctk.CTkTabview(self.content, fg_color=SIDEBAR_BG,
                            segmented_button_fg_color=CARD,
                            segmented_button_selected_color=GREEN,
                            segmented_button_selected_hover_color=GREEN_HOV,
                            segmented_button_unselected_color=CARD,
                            text_color=TEXT)
        for n in names: t.add(n)
        return t

    def _card(self, parent, title, subtitle=""):
        if subtitle:
            ctk.CTkLabel(parent,text=subtitle,text_color=TEXT_MUTED,
                         font=ctk.CTkFont("Segoe UI",11),wraplength=600).pack(anchor="w",pady=(4,4))
        f = ctk.CTkFrame(parent,fg_color=SIDEBAR_BG,corner_radius=10)
        f.pack(fill="x",pady=(0,8))
        ctk.CTkLabel(f,text=title,text_color=TEXT,
                     font=ctk.CTkFont("Segoe UI",13,"bold")).pack(padx=16,pady=(12,4),anchor="w")
        ctk.CTkFrame(f,fg_color=BORDER,height=1).pack(fill="x")
        return f

    def _duplicate_window(self):
        """Öffnet ein zweites Live-Fenster (Spieler / Dateien) für zweiten Monitor."""
        SecondaryWindow(self)

    def _logout(self):
        clear_session()
        self._logged_out = True
        self.quit()  # Mainloop sauber beenden, äußerer Code zeigt LoginWindow

    # ── Schließen ─────────────────────────────────────────────────────────────
    def _on_close(self):
        # Prüfen ob irgendein Server läuft (Haupt oder Extra)
        running = []
        if self.proc and self.proc.poll() is None:
            running.append(self.server_name or "Server")
        for es in getattr(self, "_extra_servers", []):
            if es.get("proc") and es["proc"].poll() is None:
                running.append(es.get("name", "Extra-Server"))

        if running:
            names = ", ".join(running)
            if not messagebox.askyesno("Server läuft",
                f"Diese Server laufen noch:\n{names}\n\nJetzt ALLE stoppen und beenden?"):
                return

        # Alle Server stoppen (Haupt + Extra)
        def _kill_all():
            # Hauptserver
            if self.proc and self.proc.poll() is None:
                try: self.proc.stdin.write("stop\n"); self.proc.stdin.flush()
                except: pass
                try: self.proc.wait(timeout=8)
                except: pass
                try: self.proc.kill()
                except: pass
            # Extra-Server
            for es in getattr(self, "_extra_servers", []):
                p = es.get("proc")
                if p and p.poll() is None:
                    try: p.stdin.write("stop\n"); p.stdin.flush()
                    except: pass
                    try: p.wait(timeout=5)
                    except: pass
                    try: p.kill()
                    except: pass
            # Sicherheitsnetz: alle verbleibenden java-Prozesse die von uns gestartet wurden
            import psutil as _ps
            try:
                for _p in _ps.process_iter(["name","pid"]):
                    if "java" in (_p.info.get("name","") or "").lower():
                        try:
                            _pp = _ps.Process(_p.info["pid"])
                            if any("MineHostLocal" in str(c) for c in _pp.cmdline()):
                                _pp.kill()
                        except: pass
            except: pass

        import threading as _t
        _t.Thread(target=_kill_all, daemon=True).start()

        # playit + Tunnel-Agents beenden
        mgr = getattr(self, "_playit_mgr", None)
        if mgr:
            try: mgr.stop()
            except: pass
        self._stop_all_tunnel_connectors()
        import time as _time; _time.sleep(0.5)
        self.destroy()

# ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
class SplashScreen(ctk.CTk):
    """Startanimation mit VisCode-Logo."""

    W, H = 480, 320

    def __init__(self):
        super().__init__()
        self.title("MineHost Local")
        self.resizable(False, False)
        self.configure(fg_color="#0d1117")
        self.overrideredirect(True)
        self.attributes("-alpha", 0.0)          # start unsichtbar → fade-in
        self.update_idletasks()
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self.geometry(f"{self.W}x{self.H}+{(sw-self.W)//2}+{(sh-self.H)//2}")

        import random as _rnd
        import tkinter as _tk

        # ── Canvas für Hintergrund-Orbs (normales tkinter.Canvas) ─────────────
        self._canvas = _tk.Canvas(self, width=self.W, height=self.H,
                                  bg="#0d1117", highlightthickness=0)
        self._canvas.place(x=0, y=0)

        # Kleine Orbs NUR an den Rändern, nie über der Mitte
        self._orbs = []
        _orb_defs = [
            (55,  45,  28, "#0d6efd"),
            (self.W-55, 55, 24, "#00c8ff"),
            (30,  self.H-50, 20, "#7b2fff"),
            (self.W-40, self.H-60, 32, "#0a4a8a"),
            (self.W//2-160, self.H-35, 18, "#0d6efd"),
            (self.W//2+150, 30, 16, "#00c8ff"),
        ]
        for (x, y, r, col) in _orb_defs:
            oid = self._canvas.create_oval(x-r, y-r, x+r, y+r,
                                           fill=col, outline="")
            self._orbs.append({"id": oid, "x": float(x), "y": float(y), "r": r,
                                "dx": _rnd.uniform(-0.35, 0.35),
                                "dy": _rnd.uniform(-0.25, 0.25)})

        # ── Zentrierte Content-Card ───────────────────────────────────────────
        card = ctk.CTkFrame(self, fg_color="#131920", corner_radius=18,
                            border_width=1, border_color="#1e2d45",
                            width=320, height=250)
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.pack_propagate(False)

        # ── Logo in der Card ──────────────────────────────────────────────────
        self._logo_img = make_logo(90)
        ctk.CTkLabel(card, image=self._logo_img, text="",
                     fg_color="transparent").pack(pady=(24, 8))

        # ── Texte ─────────────────────────────────────────────────────────────
        ctk.CTkLabel(card, text="MineHost Local",
            font=ctk.CTkFont("Segoe UI", 20, "bold"),
            text_color="#ffffff", fg_color="transparent").pack()

        ctk.CTkLabel(card, text="by VisCode",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color="#4a9eff", fg_color="transparent").pack(pady=(2, 10))

        self._status_lbl = ctk.CTkLabel(card, text="Starte…",
            font=ctk.CTkFont("Segoe UI", 10),
            text_color="#445", fg_color="transparent")
        self._status_lbl.pack()

        # ── Fortschrittsbalken ───────────────────────────────────────────────
        self._prog = ctk.CTkProgressBar(card, width=220, height=3,
            fg_color="#1a2233", progress_color="#0d6efd",
            mode="indeterminate", corner_radius=2)
        self._prog.pack(pady=(6, 0))
        self._prog.start()

        # ── Animationsschritte ────────────────────────────────────────────────
        self._alpha     = 0.0
        self._logo_scale= 0.6   # startet kleiner → wächst
        self._anim_tick = 0
        self._fade_in()

    # ── Fade-In + Logo-Pop-In ────────────────────────────────────────────────
    def _fade_in(self):
        try:
            self._alpha = min(1.0, self._alpha + 0.06)
            self.attributes("-alpha", self._alpha)
            if self._alpha < 1.0:
                self.after(16, self._fade_in)
        except Exception:
            return
        else:
            self._animate_orbs()
            self.after(200, self._check_java)

    # ── Schwebende Orbs ──────────────────────────────────────────────────────
    def _animate_orbs(self):
        if getattr(self, "_closing", False): return   # wird gerade beendet
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        cx, cy = self.W / 2, self.H / 2
        safe   = 110
        for o in self._orbs:
            o["x"] += o["dx"]; o["y"] += o["dy"]
            if o["x"] - o["r"] < 0 or o["x"] + o["r"] > self.W: o["dx"] *= -1
            if o["y"] - o["r"] < 0 or o["y"] + o["r"] > self.H: o["dy"] *= -1
            dist = ((o["x"]-cx)**2 + (o["y"]-cy)**2) ** 0.5
            if dist < safe:
                o["dx"] += (o["x"] - cx) * 0.04
                o["dy"] += (o["y"] - cy) * 0.04
                spd = (o["dx"]**2 + o["dy"]**2) ** 0.5
                if spd > 0.8:
                    o["dx"] = o["dx"] / spd * 0.8
                    o["dy"] = o["dy"] / spd * 0.8
            self._canvas.coords(o["id"],
                o["x"]-o["r"], o["y"]-o["r"],
                o["x"]+o["r"], o["y"]+o["r"])
        self._anim_id = self.after(33, self._animate_orbs)   # ~30 fps

    # ── Java-Check ───────────────────────────────────────────────────────────
    def _check_java(self):
        if java_available():
            self._status_lbl.configure(text="Java gefunden ✓", text_color="#4a9eff")
            self.after(600, self._fade_out)
        else:
            self._status_lbl.configure(text="Java nicht gefunden — wird installiert…",
                                        text_color="#f39c12")
            install_java_background(
                on_done=lambda: self.after(0, self._java_ok),
                on_error=lambda e: self.after(0, lambda: self._java_fail(e))
            )

    def _java_ok(self):
        self._status_lbl.configure(text="Java installiert ✓", text_color="#2ecc71")
        self.after(800, self._fade_out)

    def _java_fail(self, err):
        self._status_lbl.configure(
            text="Java-Installation fehlgeschlagen — bitte manuell installieren",
            text_color=RED)
        self._prog.stop()
        self.after(3000, self._fade_out)

    # ── Fade-Out → weiter ────────────────────────────────────────────────────
    def _fade_out(self):
        try:
            self._alpha = max(0.0, self._alpha - 0.07)
            self.attributes("-alpha", self._alpha)
            if self._alpha > 0.0:
                self._fade_id = self.after(16, self._fade_out)
            else:
                self._proceed()
        except Exception:
            self._proceed()

    def _proceed(self):
        # Animations beenden, Ergebnis speichern, Mainloop beenden.
        # KEIN verschachtelter MainApp().mainloop() hier — das würde MainApp im
        # SplashScreen-Kontext starten und alle alten Callbacks weiter feuern lassen.
        self._closing = True
        self._prog.stop()
        # Alle noch ausstehenden after()-Jobs canceln
        try:
            for job in self.tk.call("after", "info"):
                try: self.after_cancel(job)
                except: pass
        except: pass
        # Ergebnis für den äußeren Code speichern
        self._next_user = load_session() if load_session() in load_users() else None
        # Mainloop sauber beenden (statt destroy() dann mainloop() nesten)
        self.quit()


# ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
# SEKUNDÄR-FENSTER  (Duplizierung für zweiten Monitor)
# ????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????????
class SecondaryWindow(ctk.CTkToplevel):
    """Live-Ansicht eines laufenden Servers auf einem zweiten Monitor."""
    _SPIN = ["◐?","◓","◑","◒"]

    def __init__(self, main: "MainApp"):
        super().__init__(main)
        self._main = main
        self.title(f"MineHost — {main.server_name or 'Kein Server'}")
        self.geometry("820x600")
        self.configure(fg_color=BG)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        # ── Titelleiste ──────────────────────────────────────────────────────
        bar = ctk.CTkFrame(self, fg_color=SIDEBAR_BG, height=48, corner_radius=0)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        ctk.CTkLabel(bar, image=make_logo(22), text="").pack(side="left", padx=(12,6), pady=10)
        ctk.CTkLabel(bar, text="MineHost Local  —  Live-Ansicht",
                     font=ctk.CTkFont("Segoe UI",12,"bold"), text_color=GREEN).pack(side="left")
        # Status-Chip
        self._status_lbl = ctk.CTkLabel(bar, text="?? Offline",
                                         font=ctk.CTkFont("Segoe UI",11), text_color=RED)
        self._status_lbl.pack(side="left", padx=16)
        ctk.CTkLabel(bar, text="By VisCode",
                     font=ctk.CTkFont("Segoe UI",9), text_color="#444").pack(side="right", padx=12)

        # ── Tab-Leiste ───────────────────────────────────────────────────────
        tab_bar = ctk.CTkFrame(self, fg_color=SIDEBAR_BG, height=38, corner_radius=0)
        tab_bar.pack(fill="x")
        self._active_tab = ctk.StringVar(value="players")
        for key, label in [("players","👥  Spieler"), ("files","??  Dateien"), ("log","📋  Log")]:
            ctk.CTkButton(tab_bar, text=label,
                          fg_color="transparent", hover_color=CARD,
                          text_color=TEXT, font=ctk.CTkFont("Segoe UI",12),
                          height=38, corner_radius=0,
                          command=lambda k=key: self._switch_tab(k)).pack(side="left", padx=2)

        # ── Inhalts-Bereich ──────────────────────────────────────────────────
        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.pack(fill="both", expand=True, padx=16, pady=12)

        self._switch_tab("players")
        self._poll()   # Live-Updates starten

    # ── Tab wechseln ─────────────────────────────────────────────────────────
    def _switch_tab(self, key):
        self._active_tab.set(key)
        for w in self._content.winfo_children(): w.destroy()
        if key == "players":  self._tab_players()
        elif key == "files":  self._tab_files()
        elif key == "log":    self._tab_log()

    # ── Tab: Spieler ─────────────────────────────────────────────────────────
    def _tab_players(self):
        srv_dir = Path(self._main.cfg.get("dir","")) if self._main.cfg else None
        ctk.CTkLabel(self._content, text="Aktuell verbundene Spieler",
                     font=ctk.CTkFont("Segoe UI",14,"bold"), text_color=TEXT).pack(anchor="w", pady=(0,8))
        box = ctk.CTkScrollableFrame(self._content, fg_color=SIDEBAR_BG, corner_radius=10)
        box.pack(fill="both", expand=True)

        players = []
        # Spieler aus latest.log parsen (join/leave tracking)
        if srv_dir:
            log_file = srv_dir / "logs" / "latest.log"
            if log_file.exists():
                try:
                    online = set()
                    for line in log_file.read_text(encoding="utf-8", errors="ignore").splitlines():
                        m = __import__("re").search(r": (\w+) joined the game", line)
                        if m: online.add(m.group(1))
                        m = __import__("re").search(r": (\w+) left the game", line)
                        if m: online.discard(m.group(1))
                    players = sorted(online)
                except: pass

        if not players:
            ctk.CTkLabel(box, text="Keine Spieler online" if self._main.proc and self._main.proc.poll() is None
                         else "Server ist offline",
                         text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",13)).pack(pady=40)
        else:
            for p in players:
                row = ctk.CTkFrame(box, fg_color=CARD, corner_radius=8)
                row.pack(fill="x", padx=8, pady=3)
                ctk.CTkLabel(row, text="🟢", font=ctk.CTkFont("Segoe UI",12)).pack(side="left", padx=(12,6), pady=10)
                ctk.CTkLabel(row, text=p, font=ctk.CTkFont("Segoe UI",13,"bold"),
                             text_color=TEXT).pack(side="left")

    # ── Tab: Dateien ─────────────────────────────────────────────────────────
    def _tab_files(self):
        srv_dir = Path(self._main.cfg.get("dir","")) if self._main.cfg else None
        ctk.CTkLabel(self._content, text="Server-Ordner",
                     font=ctk.CTkFont("Segoe UI",14,"bold"), text_color=TEXT).pack(anchor="w", pady=(0,8))

        if not srv_dir or not srv_dir.exists():
            ctk.CTkLabel(self._content, text="Kein Server-Ordner gefunden.",
                         text_color=TEXT_MUTED).pack(pady=40)
            return

        self._cur_dir = [srv_dir]
        box = ctk.CTkScrollableFrame(self._content, fg_color=SIDEBAR_BG, corner_radius=10)
        box.pack(fill="both", expand=True)
        self._file_box   = box
        self._render_files()

    def _render_files(self):
        for w in self._file_box.winfo_children(): w.destroy()
        cur = self._cur_dir[-1]
        # Pfad-Zeile
        path_row = ctk.CTkFrame(self._file_box, fg_color="transparent")
        path_row.pack(fill="x", padx=8, pady=(6,4))
        if len(self._cur_dir) > 1:
            ctk.CTkButton(path_row, text="?? Zurück", width=80, height=28,
                          fg_color=CARD, hover_color=BORDER, text_color=TEXT,
                          font=ctk.CTkFont("Segoe UI",11), corner_radius=6,
                          command=self._go_up).pack(side="left", padx=(0,8))
        ctk.CTkLabel(path_row, text=str(cur), text_color=TEXT_MUTED,
                     font=ctk.CTkFont("Segoe UI",10)).pack(side="left")
        # Einträge
        try:
            entries = sorted(cur.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except: entries = []
        for p in entries:
            row = ctk.CTkFrame(self._file_box, fg_color=CARD, corner_radius=6)
            row.pack(fill="x", padx=8, pady=2)
            icon = "??" if p.is_dir() else "📄"
            ctk.CTkLabel(row, text=icon, font=ctk.CTkFont("Segoe UI",12)).pack(side="left", padx=(10,6), pady=8)
            ctk.CTkLabel(row, text=p.name, font=ctk.CTkFont("Segoe UI",12),
                         text_color=TEXT).pack(side="left")
            if p.is_file():
                sz = p.stat().st_size
                sz_txt = f"{sz//1024} KB" if sz > 1024 else f"{sz} B"
                ctk.CTkLabel(row, text=sz_txt, text_color=TEXT_MUTED,
                             font=ctk.CTkFont("Segoe UI",10)).pack(side="right", padx=10)
            if p.is_dir():
                def go(path=p): self._cur_dir.append(path); self._render_files()
                row.bind("<Button-1>", lambda e, fn=go: fn())
                for child in row.winfo_children():
                    child.bind("<Button-1>", lambda e, fn=go: fn())

    def _go_up(self):
        if len(self._cur_dir) > 1: self._cur_dir.pop()
        self._render_files()

    # ── Tab: Log ─────────────────────────────────────────────────────────────
    def _tab_log(self):
        ctk.CTkLabel(self._content, text="Server-Log",
                     font=ctk.CTkFont("Segoe UI",14,"bold"), text_color=TEXT).pack(anchor="w", pady=(0,8))
        import tkinter as _tk
        self._sec_log_box = _tk.Text(self._content, bg="#1a1a2e", fg="#a5d6a7",
                                      font=("Consolas",10), state="disabled",
                                      wrap="word", relief="flat", borderwidth=0)
        self._sec_log_box.pack(fill="both", expand=True)
        self._sec_log_box.tag_config("error", foreground="#ff5252")
        self._sec_log_box.tag_config("warn",  foreground="#ffd600")
        self._sec_log_box.tag_config("done",  foreground="#00e676")
        # Buffer aus Hauptfenster laden
        buf = getattr(self._main, "_log_buffer", [])
        self._sec_log_box.configure(state="normal")
        for line in buf:
            tag = self._main._log_tag(line) if hasattr(self._main, "_log_tag") else "info"
            self._sec_log_box.insert("end", line, tag)
        self._sec_log_box.see("end")
        self._sec_log_box.configure(state="disabled")
        self._last_log_len = len(buf)

    # ── Live-Polling (alle 2s) ────────────────────────────────────────────────
    def _poll(self):
        try:
            # Status-Chip aktualisieren
            state = getattr(self._main, "_server_state", "offline")
            is_on = self._main.proc is not None and self._main.proc.poll() is None
            if is_on and state == "online":
                self._status_lbl.configure(text="?? Online", text_color=GREEN)
            elif state == "starting":
                self._status_lbl.configure(text="⟳ Startet…", text_color="#f39c12")
            else:
                self._status_lbl.configure(text="?? Offline", text_color=RED)

            # Log-Tab live nachführen
            if self._active_tab.get() == "log" and hasattr(self, "_sec_log_box"):
                buf = getattr(self._main, "_log_buffer", [])
                if len(buf) > self._last_log_len:
                    new_lines = buf[self._last_log_len:]
                    self._sec_log_box.configure(state="normal")
                    for line in new_lines:
                        tag = self._main._log_tag(line) if hasattr(self._main, "_log_tag") else "info"
                        self._sec_log_box.insert("end", line, tag)
                    self._sec_log_box.see("end")
                    self._sec_log_box.configure(state="disabled")
                    self._last_log_len = len(buf)

            # Spieler-Tab alle 5s aktualisieren
            if self._active_tab.get() == "players":
                self._switch_tab("players")
        except Exception:
            pass
        self.after(2000, self._poll)


if __name__ == "__main__":
    _log = Path(os.getenv("APPDATA","")) / "MineHostLocal" / "freeze_watchdog.log"
    _start_freeze_watchdog(_log)

    # ── Splash ────────────────────────────────────────────────────────────────
    splash = SplashScreen()
    splash.mainloop()       # quit() in _proceed() beendet diesen Loop
    user = getattr(splash, "_next_user", None)
    try: splash.destroy()
    except: pass

    # ── Login (falls kein gespeicherter User) ─────────────────────────────────
    while not user:
        login = LoginWindow()
        login.mainloop()    # quit() in _on_login/_on_register beendet diesen Loop
        user = getattr(login, "_next_user", None)
        try: login.destroy()
        except: pass
        if not user:
            break           # User hat Fenster geschlossen ohne Login → beenden

    # ── Haupt-App ─────────────────────────────────────────────────────────────
    while user:
        app = MainApp(username=user)
        app.mainloop()      # quit() in _logout oder _on_close beendet diesen Loop
        user = None
        # Nach Logout: zurück zum Login
        if not getattr(app, "_logged_out", False):
            break           # normales Schließen → beenden
        try: app.destroy()
        except: pass
        login2 = LoginWindow()
        login2.mainloop()
        user = getattr(login2, "_next_user", None)
        try: login2.destroy()
        except: pass

