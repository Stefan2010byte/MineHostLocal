"""
MineHost Local — 1:1 Aternos-Layout (lokal)
pip install customtkinter psutil requests pillow
pyinstaller --onefile --windowed --name MineHostLocal minehost_local.py
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import json, os, hashlib, threading, subprocess, time, shutil, requests, random, string
import psutil
from pathlib import Path
from PIL import Image, ImageDraw

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

MC_VERSIONS = ["1.21.4","1.21.1","1.20.4","1.20.1","1.19.4","1.18.2","1.17.1","1.16.5","1.12.2","1.8.9"]

VANILLA_JARS = {
    "1.21.4": "https://piston-data.mojang.com/v1/objects/4707d00eb834b446575d89a61a11b5d548d8c001/server.jar",
    "1.21.1": "https://piston-data.mojang.com/v1/objects/59353fb40c36d304f2035d51e7d6e6baa98dc05c/server.jar",
    "1.20.4": "https://piston-data.mojang.com/v1/objects/8dd1a28015f51b1803213892b50b7b4fc76e594d/server.jar",
    "1.20.1": "https://piston-data.mojang.com/v1/objects/84194a2f286ef7c14ed7ce0090dba59902951553/server.jar",
    "1.19.4": "https://piston-data.mojang.com/v1/objects/8f3112a1049751cc472ec13e397eade5336ca7ae/server.jar",
    "1.18.2": "https://piston-data.mojang.com/v1/objects/c8f83c5655308435b3dcf03c06d9fe8740a77469/server.jar",
    "1.16.5": "https://piston-data.mojang.com/v1/objects/1b557e7b033b583cd9f66746b7a9ab1ec1673eca/server.jar",
    "1.12.2": "https://piston-data.mojang.com/v1/objects/886945bfb2b978778c3a0288fd7fab09d315b25f/server.jar",
    "1.8.9":  "https://piston-data.mojang.com/v1/objects/b58b2ceb36e01251b9a9e3d916fdca8b8e9620b2/server.jar",
}

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
]

def find_java_exe():
    """Findet java.exe — erst im PATH, dann in bekannten Installationsordnern."""
    # 1. PATH prüfen
    try:
        subprocess.run(["java", "-version"], capture_output=True, timeout=5)
        return "java"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    # 2. Typische Installationsordner durchsuchen
    for base in JAVA_SEARCH_DIRS:
        if base.exists():
            for java_exe in base.rglob("java.exe"):
                if "bin" in java_exe.parts:
                    return str(java_exe)
    return None

def java_available():
    return find_java_exe() is not None

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
            # Suche nach 64-bit Windows EXE
            if "windows" in name and ("x86_64" in name or "amd64" in name) and name.endswith(".exe"):
                return a["browser_download_url"]
        # Fallback: erstes .exe Asset
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
            if on_progress: on_progress(f"Lade playit.gg herunter…")
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

def install_java_background(on_done=None, on_error=None):
    """Installiert Eclipse Temurin 21 (LTS) via winget im Hintergrund."""
    def run():
        try:
            result = subprocess.run(
                ["winget", "install", "--id", "EclipseAdoptium.Temurin.21.JRE",
                 "-e", "--silent", "--accept-source-agreements", "--accept-package-agreements"],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0 or "bereits" in result.stdout.lower() or "already" in result.stdout.lower():
                if on_done: on_done()
            else:
                if on_error: on_error(result.stdout + result.stderr)
        except subprocess.TimeoutExpired:
            if on_error: on_error("Timeout bei Java-Installation.")
        except Exception as e:
            if on_error: on_error(str(e))
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

def get_paper_url(mc_ver):
    try:
        r = requests.get(f"https://api.papermc.io/v2/projects/paper/versions/{mc_ver}/builds", timeout=10)
        builds = r.json().get("builds", [])
        if not builds: return None
        b = builds[-1]
        return f"https://api.papermc.io/v2/projects/paper/versions/{mc_ver}/builds/{b['build']}/downloads/{b['downloads']['application']['name']}"
    except: return None

def make_logo(size=40):
    img = Image.new("RGBA", (size,size), (0,0,0,0))
    d   = ImageDraw.Draw(img)
    d.rounded_rectangle([0,0,size,size], radius=8, fill="#22262f")
    b   = size//3
    cs  = ["#5d4037","#4caf50","#388e3c","#8d6e63","#4caf50","#2e7d32","#6d4c41","#33691e","#5d4037"]
    for i,c in enumerate(cs):
        r,col = divmod(i,3)
        x0,y0 = 4+col*(b-1), 4+r*(b-1)
        d.rectangle([x0,y0,x0+b-3,y0+b-3], fill=c)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size,size))

# ══════════════════════════════════════════════════════════════════════════════
# LOGIN
# ══════════════════════════════════════════════════════════════════════════════
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
        box.pack(padx=36, fill="x")

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
        self.destroy()
        MainApp(username=user).mainloop()

# ══════════════════════════════════════════════════════════════════════════════
# SERVER ERSTELLEN (Aternos-Stil)
# ══════════════════════════════════════════════════════════════════════════════
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

        # Server-Name + Adresse
        sec1 = self._section(scroll, "Server-Details")
        self._field_lbl(sec1, "Server-Name")
        self.e_name = self._entry(sec1, "Mein Server")

        self._field_lbl(sec1, "Server-Adresse  (wird automatisch generiert)")
        addr_row = ctk.CTkFrame(sec1, fg_color="transparent")
        addr_row.pack(padx=18, pady=(2,12), fill="x")
        addr_row.grid_columnconfigure(0, weight=1)
        self.e_addr = ctk.CTkEntry(addr_row, fg_color=CARD, border_color=BORDER,
                                    text_color=TEXT, font=ctk.CTkFont("Segoe UI",13))
        self.e_addr.grid(row=0, column=0, sticky="ew", padx=(0,8))
        ctk.CTkLabel(addr_row, text=".minehost.local",
                     text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",12)
                     ).grid(row=0, column=1)
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

        # Version
        sec3 = self._section(scroll, "Version")
        self.ver_var = ctk.StringVar(value=MC_VERSIONS[0])
        om = ctk.CTkOptionMenu(sec3, variable=self.ver_var, values=MC_VERSIONS,
                                fg_color=CARD, button_color=BLUE,
                                font=ctk.CTkFont("Segoe UI",13), text_color=TEXT,
                                dropdown_fg_color=CARD, dropdown_text_color=TEXT)
        om.pack(padx=18, pady=(4,16), fill="x")

        # Region (immer Lokal)
        sec4 = self._section(scroll, "Region")
        rg = ctk.CTkFrame(sec4, fg_color="transparent")
        rg.pack(padx=18, pady=(4,14))
        ctk.CTkLabel(rg, text="🖥  Lokal  (dieser PC)", text_color=TEXT,
                     font=ctk.CTkFont("Segoe UI",13)).pack(side="left", padx=4)

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
        name = self.e_name.get().strip().replace(" ","-")
        if name:
            self.e_addr.delete(0,"end")
            self.e_addr.insert(0, f"{name}-{rnd_suffix(4)}")

    def _pick(self, name):
        self._sel_type = name
        for n, btn in self._type_btns.items():
            info = SERVER_TYPES[n]
            if n == name:
                btn.configure(fg_color=info["color"], text_color="#000")
            else:
                btn.configure(fg_color=CARD, text_color=TEXT)

    def _create(self):
        raw_name = self.e_name.get().strip()
        if not raw_name:
            self.prog_lbl.configure(text="Bitte einen Server-Namen eingeben!", text_color=RED)
            return

        addr     = self.e_addr.get().strip() or f"{raw_name.replace(' ','-')}-{rnd_suffix(4)}"
        port     = self.e_port.get().strip() or "25565"
        players  = self.e_players.get().strip() or "20"
        motd     = self.e_motd.get().strip() or "A Minecraft Server"
        mc_ver   = self.ver_var.get()
        srv_type = self._sel_type
        tag      = SERVER_TYPES[srv_type]["tag"]

        # Ordner-Name: sicher
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in raw_name)
        if not safe: safe = "Server"

        srv_dir = SERVERS_DIR / safe
        srv_dir.mkdir(parents=True, exist_ok=True)

        def run():
            self.prog_lbl.configure(text="Ermittle Download-URL…", text_color=TEXT_MUTED)
            self.prog_bar.set(0.05)

            if tag in ("paper","spigot","folia","purpur","arclight"):
                url = get_paper_url(mc_ver) or VANILLA_JARS.get(mc_ver)
            else:
                url = VANILLA_JARS.get(mc_ver)

            if not url:
                self.prog_lbl.configure(text=f"Keine JAR für {mc_ver} gefunden.", text_color=RED)
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

            # server.properties
            (srv_dir/"server.properties").write_text(
                f"server-port={port}\nmax-players={players}\nmotd={motd}\n"
                "online-mode=true\ndifficulty=normal\npvp=true\n"
                "white-list=false\ngamemode=survival\nlevel-name=world\n"
                "view-distance=10\nenable-command-block=false\nspawn-protection=16\n"
                "allow-flight=false\nforce-gamemode=false\nplayer-idle-timeout=0\n",
                encoding="utf-8"
            )

            # Config speichern
            cfg = {
                "name":        raw_name,
                "safe":        safe,
                "mc_version":  mc_ver,
                "type":        tag,
                "type_label":  srv_type,
                "port":        port,
                "address":     f"{addr}.minehost.local",
                "max_players": players,
                "motd":        motd,
                "dir":         str(srv_dir),
            }
            save_server_cfg(safe, cfg)

            self.prog_bar.set(1.0)
            self.prog_lbl.configure(text="Fertig! Server wurde erstellt.", text_color=GREEN)
            time.sleep(0.8)
            self.destroy()
            self.on_done(safe)

        threading.Thread(target=run, daemon=True).start()

# ══════════════════════════════════════════════════════════════════════════════
# HAUPT-APP  (Aternos-Layout)
# ══════════════════════════════════════════════════════════════════════════════
class MainApp(ctk.CTk):
    def __init__(self, username):
        super().__init__()
        self.username     = username
        self.server_name  = None
        self.cfg          = {}
        self.proc         = None
        self.playit_proc  = None
        self._playit_addr = None   # öffentliche Adresse von playit.gg
        self._server_state = "offline"
        self.title("MineHost Local")
        self.geometry("1200x750")
        self.minsize(1000,640)
        self.configure(fg_color=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build()
        servers = list_servers()
        if servers:
            self._load_server(servers[0])
        else:
            self._show("dashboard")

    # ── Root-Layout ───────────────────────────────────────────────────────────
    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=SIDEBAR_W, fg_color=SIDEBAR_BG, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        # Main
        self.content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")

        self._build_sidebar()

    def _build_sidebar(self):
        # Logo + App-Name
        top = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        top.pack(pady=(16,0), padx=14, fill="x")
        ctk.CTkLabel(top, image=make_logo(36), text="").pack(side="left", padx=(0,8))
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
        pages = [
            ("dashboard", "Server"),
            ("options",   "Optionen"),
            ("console",   "Konsole"),
            ("log",       "Log"),
            ("players",   "Spieler"),
            ("software",  "Software"),
            ("plugins",   "Plugins"),
            ("files",     "Dateien"),
            ("worlds",    "Welten"),
            ("backups",   "Backups"),
            ("access",    "Zugriff"),
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

        # Benutzer + Logout unten
        bot = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bot.pack(side="bottom", padx=8, pady=10, fill="x")
        ctk.CTkLabel(bot, text=f"@ {self.username}",
                     text_color=TEXT_MUTED, font=ctk.CTkFont("Segoe UI",10)).pack(anchor="w")
        ctk.CTkButton(bot, text="Ausloggen", anchor="w",
                      fg_color="transparent", hover_color=CARD,
                      text_color=RED, font=ctk.CTkFont("Segoe UI",11),
                      height=28, corner_radius=6,
                      command=self._logout).pack(fill="x", pady=(2,0))

    # ── Navigation ────────────────────────────────────────────────────────────
    def _clear(self):
        for w in self.content.winfo_children(): w.destroy()

    def _show(self, key):
        self._active_page = key
        for k,b in self._nav.items():
            b.configure(
                text_color=GREEN if k==key else TEXT_MUTED,
                fg_color=CARD if k==key else "transparent",
                font=ctk.CTkFont("Segoe UI",13,"bold" if k==key else "normal")
            )
        self._clear()
        getattr(self, f"_p_{key}")()

    def _load_server(self, safe_name):
        self.server_name = safe_name
        self.cfg         = load_server_cfg(safe_name)
        is_on = self.proc is not None and self.proc.poll() is None
        self._srv_name_lbl.configure(text=self.cfg.get("name", safe_name))
        self._srv_sub_lbl.configure(text=self.cfg.get("address","localhost"))
        self._srv_dot.configure(text_color=GREEN if is_on else RED)
        self._show("dashboard")

    def _switch_server_popup(self):
        servers = list_servers()
        if not servers:
            messagebox.showinfo("Keine Server","Erstelle zuerst einen Server.")
            return
        win = ctk.CTkToplevel(self)
        win.title("Server wechseln")
        win.geometry("320x400")
        win.configure(fg_color=SIDEBAR_BG)
        win.grab_set()
        ctk.CTkLabel(win, text="Server auswählen",
                     font=ctk.CTkFont("Segoe UI",15,"bold"), text_color=TEXT).pack(pady=16)
        for s in servers:
            cfg = load_server_cfg(s)
            def pick(n=s, w=win):
                w.destroy(); self._load_server(n)
            btn = ctk.CTkButton(win, text=cfg.get("name",s),
                                 fg_color=CARD, hover_color=BORDER, text_color=TEXT,
                                 font=ctk.CTkFont("Segoe UI",13), height=44,
                                 command=pick)
            btn.pack(padx=16, pady=4, fill="x")

    def _new_server(self):
        CreateServerWindow(self, on_done=self._on_created)

    def _on_created(self, safe_name):
        self._load_server(safe_name)

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE: DASHBOARD  (Aternos-Stil)
    # ═════════════════════════════════════════════════════════════════════════
    def _p_dashboard(self):
        self._clear()   # verhindert doppeltes Rendering
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

        # ── Scrollbarer Wrapper ──
        wrap = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        wrap.pack(fill="both", expand=True)
        wrap.grid_columnconfigure(0, weight=1)

        # ── Server-Titel + Adresse ──
        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.pack(pady=(24,0))
        ctk.CTkLabel(head, text=cfg.get("name","Server"),
                     font=ctk.CTkFont("Segoe UI",26,"bold"), text_color=TEXT).pack()
        addr_row = ctk.CTkFrame(head, fg_color="transparent")
        addr_row.pack(pady=(4,0))
        ctk.CTkLabel(addr_row, text=cfg.get("address","localhost"),
                     font=ctk.CTkFont("Segoe UI",13), text_color=TEXT_MUTED).pack(side="left", padx=(0,10))
        ctk.CTkButton(addr_row, text="Verbinden",
                      fg_color=CARD, hover_color=BORDER, text_color=TEXT,
                      font=ctk.CTkFont("Segoe UI",11), height=26, width=80, corner_radius=4,
                      command=lambda: self.clipboard_append(cfg.get("address","")) or self.update()
                      ).pack(side="left")

        # ── Status-Banner ──
        # Zustände: "offline" | "starting" | "online" | "error"
        state = "online" if is_on else getattr(self, "_server_state", "offline")

        STATES = {
            "offline":  (RED,          "● Ausgeschaltet",   "#fff"),
            "starting": ("#f39c12",    "⟳ Startet…",        "#000"),
            "online":   (GREEN,        "● Online",           "#000"),
            "error":    ("#8e0000",    "✖ Fehler",           "#fff"),
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
            self._start_btn.pack()

        elif state == "starting":
            # Ladekreis + "Laden"-Text
            loader_frame = ctk.CTkFrame(btn_row, fg_color="transparent")
            loader_frame.pack()
            spinner = ctk.CTkProgressBar(loader_frame, mode="indeterminate",
                                          width=180, height=6,
                                          fg_color=CARD, progress_color="#f39c12")
            spinner.pack(pady=(0,8))
            spinner.start()
            ctk.CTkLabel(loader_frame, text="Laden",
                         font=ctk.CTkFont("Segoe UI",22,"bold"),
                         text_color="#f39c12").pack()
            ctk.CTkLabel(loader_frame, text="Server wird gestartet…",
                         font=ctk.CTkFont("Segoe UI",12),
                         text_color=TEXT_MUTED).pack(pady=(2,0))

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


        # ── Info-Karten (wie Aternos) ──
        info_frame = ctk.CTkFrame(wrap, fg_color=SIDEBAR_BG, corner_radius=10)
        info_frame.pack(padx=40, pady=16, fill="x")

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
        public_val = self._playit_addr or ("Startet Server zuerst…" if state=="offline" else "Tunnel verbindet…")
        info_row("Lokale Adresse", local_val, copy=(state!="offline"))
        info_row("Öffentliche Adresse (playit.gg)", public_val,
                 copy=bool(self._playit_addr))
        info_row("Software", cfg.get("type_label", cfg.get("type","Vanilla")).capitalize(),
                 btn_text="Ändern", btn_cmd=lambda: self._show("software"))
        info_row("Version", cfg.get("mc_version","?"),
                 btn_text="Ändern", btn_cmd=lambda: self._show("software"))

        # ── System-Monitor kompakt ──
        mon = ctk.CTkFrame(wrap, fg_color=SIDEBAR_BG, corner_radius=10)
        mon.pack(padx=40, pady=8, fill="x")
        ctk.CTkLabel(mon, text="System-Monitor", text_color=TEXT_MUTED,
                     font=ctk.CTkFont("Segoe UI",11,"bold")).pack(padx=16, pady=(10,4), anchor="w")
        mon_row = ctk.CTkFrame(mon, fg_color="transparent")
        mon_row.pack(padx=16, pady=(0,12), fill="x")
        mon_row.grid_columnconfigure((0,1), weight=1)

        def mini_stat(parent, col, label):
            f = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=8)
            f.grid(row=0, column=col, padx=(0,8) if col==0 else (8,0), sticky="ew")
            ctk.CTkLabel(f, text=label, text_color=TEXT_MUTED,
                         font=ctk.CTkFont("Segoe UI",10)).pack(padx=12, pady=(8,2), anchor="w")
            bar = ctk.CTkProgressBar(f, fg_color=SIDEBAR_BG, progress_color=BLUE)
            bar.set(0)
            bar.pack(padx=12, pady=(0,2), fill="x")
            lbl = ctk.CTkLabel(f, text="0%", text_color=TEXT,
                                font=ctk.CTkFont("Segoe UI",12,"bold"))
            lbl.pack(padx=12, pady=(0,8), anchor="w")
            return bar, lbl

        self._cpu_bar, self._cpu_lbl = mini_stat(mon_row, 0, "CPU")
        self._ram_bar, self._ram_lbl = mini_stat(mon_row, 1, "RAM")
        self._update_monitor()

    def _update_monitor(self):
        if not hasattr(self,"_cpu_bar"): return
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory()
        try:
            self._cpu_bar.set(cpu/100); self._cpu_lbl.configure(text=f"{cpu:.0f}%")
            self._ram_bar.set(ram.percent/100); self._ram_lbl.configure(text=f"{ram.percent:.0f}%")
        except: return
        self.after(2000, self._update_monitor)

    # ── Server starten/stoppen ────────────────────────────────────────────────
    def _set_state(self, state):
        """state: 'offline' | 'starting' | 'online' | 'error'"""
        self._server_state = state
        dot_colors = {"offline": RED, "starting": "#f39c12", "online": GREEN, "error": "#8e0000"}
        self._srv_dot.configure(text_color=dot_colors.get(state, RED))
        # Dashboard nur neu laden wenn gerade sichtbar
        if hasattr(self, "_active_page") and self._active_page == "dashboard":
            self._p_dashboard()

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
        java = find_java_exe()
        if not java:
            if messagebox.askyesno("Java fehlt",
                "Java wurde nicht gefunden.\nJetzt automatisch installieren?"):
                install_java_background(
                    on_done=lambda: self.after(0, self._start),
                    on_error=lambda e: self.after(0, lambda: messagebox.showerror(
                        "Fehler", f"Java-Installation fehlgeschlagen:\n{e}"))
                )
            return
        # Vorherige Java-Prozesse killen die die Log-Datei sperren könnten
        for p in psutil.process_iter(["name","pid"]):
            try:
                if p.info["name"] and "java" in p.info["name"].lower():
                    p.kill()
            except: pass
        # Log-Datei entsperren
        log_file = srv_dir / "logs" / "latest.log"
        if log_file.exists():
            try: log_file.unlink()
            except: pass

        self._error_log = []
        try:
            self.proc = subprocess.Popen(
                [java, "-Xmx2G", "-Xms512M", "-jar", "server.jar", "--nogui"],
                cwd=str(srv_dir), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )
        except Exception as e:
            self._error_log = [str(e)]
            self._set_state("error")
            return
        self._set_state("starting")
        threading.Thread(target=self._read_log, daemon=True).start()
        threading.Thread(target=self._watchdog, daemon=True).start()
        # playit.gg starten
        self._start_playit(port=self.cfg.get("port","25565"))

    def _watchdog(self):
        """Wartet darauf dass der Prozess endet ohne 'Done' → Fehler."""
        if self.proc:
            self.proc.wait()
            state = getattr(self, "_server_state", "offline")
            if state == "starting":   # Prozess gestorben bevor Online
                self.after(0, lambda: self._set_state("error"))
            elif state == "online":   # Normal beendet
                self.after(0, lambda: self._set_state("offline"))

    def _start_playit(self, port="25565"):
        """Startet playit.gg Agent und liest die öffentliche Adresse aus dem Output."""
        def do():
            if not PLAYIT_EXE.exists():
                self._append_log("[playit.gg] Wird heruntergeladen…\n")
                done_event = threading.Event()
                download_playit(
                    on_done=done_event.set,
                    on_progress=lambda m: self._append_log(f"[playit.gg] {m}\n")
                )
                done_event.wait(timeout=120)
                if not PLAYIT_EXE.exists():
                    self._append_log("[playit.gg] Download fehlgeschlagen.\n")
                    return

            try:
                self.playit_proc = subprocess.Popen(
                    [str(PLAYIT_EXE)],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1
                )
            except Exception as e:
                self._append_log(f"[playit.gg] Startfehler: {e}\n")
                return

            self._append_log("[playit.gg] Agent gestartet — warte auf Tunnel-Adresse…\n")
            for line in self.playit_proc.stdout:
                self._append_log(f"[playit.gg] {line}")
                # Adresse parsen: "tunnel address: xxx.at.playit.gg:25565"
                low = line.lower()
                if "tunnel address" in low or "alloc address" in low or ".playit.gg" in low:
                    import re
                    m = re.search(r"([\w\-]+\.playit\.gg:\d+)", line)
                    if m:
                        self._playit_addr = m.group(1)
                        self._append_log(f"[playit.gg] ✓ Öffentliche Adresse: {self._playit_addr}\n")
                        self.after(0, lambda: self._refresh_dashboard_addr())
                # Claim-Link anzeigen
                if "playit.gg/claim/" in line or "playit.gg/account" in line:
                    import re
                    m = re.search(r"https://\S+", line)
                    if m:
                        self._append_log(f"[playit.gg] → Konto verknüpfen: {m.group(0)}\n")

        threading.Thread(target=do, daemon=True).start()

    def _refresh_dashboard_addr(self):
        if getattr(self, "_active_page", "") == "dashboard":
            self._p_dashboard()

    def _stop(self):
        if self.proc:
            try: self.proc.stdin.write("stop\n"); self.proc.stdin.flush(); self.proc.wait(timeout=15)
            except: self.proc.kill()
            self.proc = None
        if self.playit_proc:
            try: self.playit_proc.kill()
            except: pass
            self.playit_proc = None
        self._playit_addr = None
        self._log_buffer  = []
        self._set_state("offline")

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

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE: KONSOLE
    # ═════════════════════════════════════════════════════════════════════════
    def _p_console(self):
        self._console_page(log_only=False)

    def _p_log(self):
        self._console_page(log_only=True)

    def _console_page(self, log_only):
        self.content.grid_rowconfigure(1, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        hdr = self._page_header("Log" if log_only else "Konsole")

        # tk.Text statt CTkTextbox — unterstützt farbige Tags
        self._log_box = tk.Text(self.content, bg="#21263a", fg="#a5d6a7",
                                 font=("Consolas",11), state="disabled",
                                 relief="flat", bd=0, insertbackground="#a5d6a7",
                                 selectbackground="#2979ff", wrap="none")
        self._log_box.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0,8))
        # Farb-Tags
        self._log_box.tag_config("error", foreground="#ff5252")
        self._log_box.tag_config("warn",  foreground="#ffd600")
        self._log_box.tag_config("info",  foreground="#a5d6a7")
        self._log_box.tag_config("done",  foreground="#00e676")
        # Scrollbar
        sb = tk.Scrollbar(self.content, command=self._log_box.yview, bg="#1a1d24")
        self._log_box.configure(yscrollcommand=sb.set)
        sb.grid(row=1, column=1, sticky="ns", pady=(0,8))

        # Bisherigen Log-Inhalt wiederherstellen
        if hasattr(self, "_log_buffer") and self._log_buffer:
            self._log_box.configure(state="normal")
            for line in self._log_buffer:
                self._log_box.insert("end", line, self._log_tag(line))
            self._log_box.see("end")
            self._log_box.configure(state="disabled")

        if not log_only:
            inp = ctk.CTkFrame(self.content, fg_color="transparent")
            inp.grid(row=2, column=0, sticky="ew", padx=20, pady=(0,16))
            inp.grid_columnconfigure(0, weight=1)
            self._cmd_e = ctk.CTkEntry(inp, placeholder_text="Befehl eingeben…",
                                        fg_color=CARD, border_color=BORDER, text_color=TEXT,
                                        font=ctk.CTkFont("Consolas",12))
            self._cmd_e.grid(row=0,column=0,sticky="ew",padx=(0,8))
            self._cmd_e.bind("<Return>", lambda _: self._send())
            ctk.CTkButton(inp,text="Senden",fg_color=GREEN,hover_color=GREEN_HOV,
                          text_color="#000",width=90,command=self._send).grid(row=0,column=1)

    def _send(self):
        if not hasattr(self,"_cmd_e"): return
        cmd = self._cmd_e.get().strip()
        if not cmd: return
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write(cmd+"\n"); self.proc.stdin.flush()
                self._append_log(f"> {cmd}\n")
            except Exception as e:
                self._append_log(f"[Fehler] {e}\n")
        else:
            self._append_log("[Server ist nicht gestartet]\n")
        self._cmd_e.delete(0,"end")

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE: OPTIONEN
    # ═════════════════════════════════════════════════════════════════════════
    def _p_options(self):
        hdr = self._page_header("Optionen")
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

        # Aternos-Optionen-Panel
        def section(title):
            ctk.CTkLabel(scroll, text=title, text_color=TEXT_MUTED,
                         font=ctk.CTkFont("Segoe UI",11,"bold")).pack(anchor="w", pady=(14,4))
            f = ctk.CTkFrame(scroll, fg_color=SIDEBAR_BG, corner_radius=10)
            f.pack(fill="x")
            return f

        def toggle_row(parent, key, label, default="false"):
            var = ctk.BooleanVar(value=props.get(key,default)=="true")
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x")
            row.grid_columnconfigure(0, weight=1)
            lf = ctk.CTkFrame(row, fg_color="transparent")
            lf.grid(row=0,column=0,padx=14,pady=10,sticky="w")
            ctk.CTkLabel(lf,text=label,text_color=TEXT,font=ctk.CTkFont("Segoe UI",13)).pack(anchor="w")
            ctk.CTkLabel(lf,text=key,text_color=TEXT_MUTED,font=ctk.CTkFont("Segoe UI",9)).pack(anchor="w")
            sw = ctk.CTkSwitch(row, variable=var, text="",
                                progress_color=GREEN, button_color=TEXT)
            sw.grid(row=0,column=1,padx=14)
            ctk.CTkFrame(parent,fg_color=BORDER,height=1).pack(fill="x")
            widgets[key]=("bool",var)

        def drop_row(parent, key, label, opts, default=""):
            var = ctk.StringVar(value=props.get(key,default))
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x")
            row.grid_columnconfigure(0, weight=1)
            lf = ctk.CTkFrame(row, fg_color="transparent")
            lf.grid(row=0,column=0,padx=14,pady=10,sticky="w")
            ctk.CTkLabel(lf,text=label,text_color=TEXT,font=ctk.CTkFont("Segoe UI",13)).pack(anchor="w")
            ctk.CTkLabel(lf,text=key,text_color=TEXT_MUTED,font=ctk.CTkFont("Segoe UI",9)).pack(anchor="w")
            ctk.CTkOptionMenu(row, variable=var, values=opts,
                               fg_color=CARD, button_color=BLUE,
                               width=160,font=ctk.CTkFont("Segoe UI",12)
                               ).grid(row=0,column=1,padx=14)
            ctk.CTkFrame(parent,fg_color=BORDER,height=1).pack(fill="x")
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
            ctk.CTkFrame(parent,fg_color=BORDER,height=1).pack(fill="x")
            widgets[key]=("entry",e)

        p1 = section("Allgemein")
        drop_row(p1,"difficulty","Schwierigkeitsgrad",["peaceful","easy","normal","hard"],"normal")
        drop_row(p1,"gamemode","Spielmodus",["survival","creative","adventure","spectator"],"survival")
        entry_row(p1,"max-players","Spieler (max-players)","20")
        entry_row(p1,"view-distance","Sichtweite (Chunks)","10")
        entry_row(p1,"player-idle-timeout","Idle Timeout (Minuten, 0=aus)","0")
        entry_row(p1,"spawn-protection","Spawn-Schutz (Radius in Blöcken)","16")

        p2 = section("Spielmechaniken")
        toggle_row(p2,"pvp","PvP","true")
        toggle_row(p2,"allow-flight","Fliegen","false")
        toggle_row(p2,"force-gamemode","Spielmodus erzwingen","false")
        toggle_row(p2,"enable-command-block","Command Blocks","false")

        p3 = section("Zugang")
        toggle_row(p3,"online-mode","Online-Mode  (aus = Cracked)","true")
        toggle_row(p3,"white-list","Whitelist","false")

        p4 = section("Server-Details")
        entry_row(p4,"server-port","Port","25565")
        entry_row(p4,"motd","Beschreibung (MotD)","A Minecraft Server")
        entry_row(p4,"level-name","Weltname","world")
        entry_row(p4,"level-seed","Welt-Seed (leer = zufällig)","")
        entry_row(p4,"resource-pack","Ressourcenpaket URL","")

        def save():
            new = dict(props)
            for k,(t,w) in widgets.items():
                new[k] = ("true" if w.get() else "false") if t=="bool" else w.get()
            props_file.write_text("\n".join(f"{k}={v}" for k,v in new.items())+"\n",encoding="utf-8")
            self.cfg["port"] = new.get("server-port","25565")
            self.cfg["motd"] = new.get("motd","")
            save_server_cfg(self.server_name, self.cfg)
            messagebox.showinfo("Gespeichert","server.properties gespeichert.\nServer neu starten, damit Änderungen wirksam werden.")

        ctk.CTkButton(self.content, text="Speichern",
                      fg_color=GREEN, hover_color=GREEN_HOV, text_color="#000",
                      font=ctk.CTkFont("Segoe UI",14,"bold"), height=46, corner_radius=8,
                      command=save).grid(row=2, column=0, padx=20, pady=(4,16), sticky="ew")

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE: SPIELER
    # ═════════════════════════════════════════════════════════════════════════
    def _p_players(self):
        self._page_header("Spieler")
        self.content.grid_rowconfigure(1, weight=1)
        if not self.server_name:
            ctk.CTkLabel(self.content,text="Kein Server.",text_color=TEXT_MUTED).grid(row=1,column=0); return

        tabs = self._tabs(["OP-Liste","Whitelist","Gebannte Spieler"])
        tabs.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0,16))
        srv_dir = Path(self.cfg.get("dir",""))

        for tab_name, fname, cmd_prefix in [
            ("OP-Liste","ops.json","op"),
            ("Whitelist","whitelist.json","whitelist add"),
            ("Gebannte Spieler","banned-players.json","ban")
        ]:
            t = tabs.tab(tab_name)
            t.grid_columnconfigure(0, weight=1); t.grid_rowconfigure(0, weight=1)
            fp = srv_dir/fname
            data = []
            if fp.exists():
                try: data = json.loads(fp.read_text(encoding="utf-8"))
                except: pass
            names = [p.get("name","?") for p in data]
            box = ctk.CTkTextbox(t, fg_color=CARD, text_color=TEXT, font=ctk.CTkFont("Segoe UI",13))
            box.grid(row=0,column=0,columnspan=2,sticky="nsew",pady=(0,8))
            box.insert("end","\n".join(names) or "(Leer)")
            box.configure(state="disabled")
            ent = ctk.CTkEntry(t,placeholder_text="Spielername…",fg_color=CARD,
                                border_color=BORDER,text_color=TEXT)
            ent.grid(row=1,column=0,sticky="ew",padx=(0,8),pady=(0,4))
            def add(e=ent,b=box,fp2=fp,d=data,cp=cmd_prefix):
                n=e.get().strip()
                if not n: return
                if not any(p.get("name")==n for p in d):
                    d.append({"uuid":"","name":n})
                    fp2.write_text(json.dumps(d,indent=2),encoding="utf-8")
                b.configure(state="normal"); b.insert("end",f"\n{n}"); b.configure(state="disabled")
                if self.proc and self.proc.poll() is None:
                    try: self.proc.stdin.write(f"{cp} {n}\n"); self.proc.stdin.flush()
                    except: pass
                e.delete(0,"end")
            ctk.CTkButton(t,text="Hinzufügen",fg_color=GREEN,hover_color=GREEN_HOV,
                          text_color="#000",width=110,command=add
                          ).grid(row=1,column=1,pady=(0,4))

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE: SOFTWARE
    # ═════════════════════════════════════════════════════════════════════════
    def _p_software(self):
        self._page_header("Software")
        self.content.grid_rowconfigure(1, weight=1)
        if not self.server_name:
            ctk.CTkLabel(self.content,text="Kein Server.",text_color=TEXT_MUTED).grid(row=1,column=0); return

        scroll = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0,16))

        ctk.CTkLabel(scroll, text="Java Edition", text_color=GREEN,
                     font=ctk.CTkFont("Segoe UI",13,"bold")).pack(anchor="w", pady=(0,8))

        grid = ctk.CTkFrame(scroll, fg_color="transparent")
        grid.pack(fill="x")
        self._sw_btns = {}
        cur = self.cfg.get("type_label","Vanilla")
        self._sel_sw = cur
        for i,(name,info) in enumerate(SERVER_TYPES.items()):
            r,c = divmod(i,3)
            f = ctk.CTkFrame(grid, fg_color=info["color"] if name==cur else CARD, corner_radius=8)
            f.grid(row=r,column=c,padx=3,pady=3,sticky="nsew")
            grid.grid_columnconfigure(c, weight=1)
            ctk.CTkLabel(f,text=f"{info['icon']}  {name}",
                         text_color="#000" if name==cur else TEXT,
                         font=ctk.CTkFont("Segoe UI",13,"bold")).pack(pady=(12,2))
            ctk.CTkLabel(f,text=info["desc"],text_color="#000" if name==cur else TEXT_MUTED,
                         font=ctk.CTkFont("Segoe UI",9),wraplength=150).pack(pady=(0,12))
            def pick(n=name,fi=info,fr=f):
                self._sel_sw = n
                for nm,(btn_f,_) in self._sw_btns.items():
                    ni = SERVER_TYPES[nm]
                    btn_f.configure(fg_color=ni["color"] if nm==n else CARD)
                    for child in btn_f.winfo_children():
                        child.configure(text_color="#000" if nm==n else
                                        (TEXT if isinstance(child,ctk.CTkLabel) and
                                         child.cget("font") and "bold" in str(child.cget("font")) else TEXT_MUTED))
            btn_click = ctk.CTkButton(f,text="",width=0,height=0,fg_color="transparent",
                                       hover_color="transparent",command=pick)
            f.bind("<Button-1>", lambda _,p=pick: p())
            for child in f.winfo_children():
                child.bind("<Button-1>", lambda _,p=pick: p())
            self._sw_btns[name] = (f, pick)

        ver_f = ctk.CTkFrame(scroll, fg_color=SIDEBAR_BG, corner_radius=10)
        ver_f.pack(fill="x", pady=12)
        ctk.CTkLabel(ver_f,text="Version",text_color=TEXT_MUTED,
                     font=ctk.CTkFont("Segoe UI",11,"bold")).pack(padx=14,pady=(10,2),anchor="w")
        self._sw_ver = ctk.StringVar(value=self.cfg.get("mc_version","1.21.4"))
        ctk.CTkOptionMenu(ver_f,variable=self._sw_ver,values=MC_VERSIONS,
                           fg_color=CARD,button_color=BLUE,text_color=TEXT,
                           font=ctk.CTkFont("Segoe UI",13)
                           ).pack(padx=14,pady=(0,12),fill="x")

        self._sw_lbl = ctk.CTkLabel(scroll,text="",text_color=TEXT_MUTED,
                                     font=ctk.CTkFont("Segoe UI",11))
        self._sw_lbl.pack()
        ctk.CTkButton(scroll,text="Ändern",fg_color=GREEN,hover_color=GREEN_HOV,
                      text_color="#000",font=ctk.CTkFont("Segoe UI",13,"bold"),height=44,
                      command=self._apply_sw).pack(fill="x",pady=8)

    def _apply_sw(self):
        name = self._sel_sw; ver = self._sw_ver.get()
        self.cfg["type_label"]=name; self.cfg["type"]=SERVER_TYPES[name]["tag"]
        self.cfg["mc_version"]=ver
        save_server_cfg(self.server_name, self.cfg)
        self._sw_lbl.configure(text="Lade neue JAR…",text_color=GREEN)
        def dl():
            info = SERVER_TYPES[name]
            url = get_paper_url(ver) if info["tag"] in ("paper","spigot","folia","purpur","arclight") else None
            url = url or VANILLA_JARS.get(ver)
            if url:
                srv_dir = Path(self.cfg["dir"])
                jar = srv_dir/"server.jar"
                if jar.exists(): jar.rename(srv_dir/"server.jar.bak")
                r=requests.get(url,stream=True,timeout=120)
                with open(str(jar),"wb") as fh:
                    for chunk in r.iter_content(8192): fh.write(chunk)
            self._sw_lbl.configure(text="Fertig! Server neu starten.",text_color=GREEN)
        threading.Thread(target=dl,daemon=True).start()

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE: PLUGINS
    # ═════════════════════════════════════════════════════════════════════════
    def _p_plugins(self):
        self._page_header("Plugins")
        self.content.grid_rowconfigure(1, weight=1)
        if not self.server_name:
            ctk.CTkLabel(self.content,text="Kein Server.",text_color=TEXT_MUTED).grid(row=1,column=0); return
        folder = Path(self.cfg.get("dir",""))/"plugins"
        self._file_manager(folder, "Plugin (.jar)")

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE: DATEIEN
    # ═════════════════════════════════════════════════════════════════════════
    def _p_files(self):
        self._page_header("Dateien")
        self.content.grid_rowconfigure(1, weight=1)
        if not self.server_name:
            ctk.CTkLabel(self.content,text="Kein Server.",text_color=TEXT_MUTED).grid(row=1,column=0); return

        tabs = self._tabs(["Mods","Resourcepacks","Datapacks","Alle Dateien"])
        tabs.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0,16))
        srv_dir = Path(self.cfg.get("dir",""))
        for folder, tab in [("mods","Mods"),("resourcepacks","Resourcepacks"),("datapacks","Datapacks")]:
            t = tabs.tab(tab)
            t.grid_columnconfigure(0,weight=1); t.grid_rowconfigure(0,weight=1)
            self._folder_tab_inner(t, srv_dir/folder)
        # Alle Dateien
        t = tabs.tab("Alle Dateien")
        t.grid_columnconfigure(0,weight=1); t.grid_rowconfigure(0,weight=1)
        box = ctk.CTkTextbox(t,fg_color=CARD,text_color=TEXT,font=ctk.CTkFont("Consolas",11))
        box.grid(row=0,column=0,sticky="nsew",pady=(0,8))
        try:
            for it in sorted(srv_dir.iterdir()):
                box.insert("end",f"{'[D]' if it.is_dir() else '[F]'} {it.name}\n")
        except: pass
        box.configure(state="disabled")
        ctk.CTkButton(t,text="Im Explorer öffnen",fg_color=CARD,text_color=TEXT,
                      height=34,command=lambda:os.startfile(str(srv_dir))
                      ).grid(row=1,column=0,sticky="ew")

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

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE: WELTEN
    # ═════════════════════════════════════════════════════════════════════════
    def _p_worlds(self):
        self._page_header("Welten")
        self.content.grid_rowconfigure(1, weight=1)
        if not self.server_name:
            ctk.CTkLabel(self.content,text="Kein Server.",text_color=TEXT_MUTED).grid(row=1,column=0); return

        srv_dir = Path(self.cfg.get("dir",""))
        scroll = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0,16))

        DIM = {"world":("Overworld","🌱"),
               "world_nether":("Nether","🔥"),
               "world_the_end":("The End","🌌")}

        worlds = [d for d in srv_dir.iterdir() if d.is_dir() and (d/"level.dat").exists()]
        if not worlds:
            ctk.CTkLabel(scroll,
                text="Keine Welten gefunden.\nStarte den Server einmal, um Welten zu generieren.",
                text_color=TEXT_MUTED,font=ctk.CTkFont("Segoe UI",13),wraplength=500).pack(pady=30)
        else:
            for w in sorted(worlds):
                dim_name,icon = DIM.get(w.name,(w.name,"🗺"))
                size_mb = sum(f.stat().st_size for f in w.rglob("*") if f.is_file())/1e6
                card = ctk.CTkFrame(scroll,fg_color=SIDEBAR_BG,corner_radius=10)
                card.pack(fill="x",pady=4)
                card.grid_columnconfigure(1,weight=1)
                ctk.CTkLabel(card,text=icon,font=ctk.CTkFont("Segoe UI",28)
                             ).grid(row=0,column=0,rowspan=2,padx=16,pady=12)
                ctk.CTkLabel(card,text=dim_name,font=ctk.CTkFont("Segoe UI",14,"bold"),
                             text_color=TEXT,anchor="w").grid(row=0,column=1,sticky="w",pady=(10,0))
                ctk.CTkLabel(card,text=f"{w.name}  •  {size_mb:.1f} MB",
                             text_color=TEXT_MUTED,font=ctk.CTkFont("Segoe UI",11),anchor="w"
                             ).grid(row=1,column=1,sticky="w",pady=(0,10))
                bf = ctk.CTkFrame(card,fg_color="transparent")
                bf.grid(row=0,column=2,rowspan=2,padx=12)
                ctk.CTkButton(bf,text="Öffnen",fg_color=CARD,text_color=TEXT,width=80,height=28,
                              command=lambda p=w:os.startfile(str(p))).pack(pady=2)
                ctk.CTkButton(bf,text="Backup",fg_color=BLUE,text_color="#fff",width=80,height=28,
                              command=lambda p=w,n=dim_name:self._bkp_world(p,n)).pack(pady=2)
                ctk.CTkButton(bf,text="Löschen",fg_color=RED,text_color="#fff",width=80,height=28,
                              command=lambda p=w,n=dim_name:self._del_world(p,n)).pack(pady=2)

        act = ctk.CTkFrame(scroll,fg_color=SIDEBAR_BG,corner_radius=10)
        act.pack(fill="x",pady=8)
        r = ctk.CTkFrame(act,fg_color="transparent")
        r.pack(padx=14,pady=12,fill="x")
        ctk.CTkButton(r,text="Welt importieren (.zip)",fg_color=CARD,text_color=TEXT,height=36,
                      command=lambda:self._import_world(srv_dir)).pack(side="left",padx=(0,8))
        ctk.CTkButton(r,text="Seed abrufen",fg_color=CARD,text_color=TEXT,height=36,
                      command=self._get_seed).pack(side="left")

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

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE: BACKUPS
    # ═════════════════════════════════════════════════════════════════════════
    def _p_backups(self):
        self._page_header("Backups")
        self.content.grid_rowconfigure(1, weight=1)
        scroll = ctk.CTkScrollableFrame(self.content, fg_color="transparent")
        scroll.grid(row=1,column=0,sticky="nsew",padx=20,pady=(0,16))

        # Lokales Backup
        s1 = self._card(scroll, "💾  Lokales Backup",
                        "Erstellt ein ZIP des gesamten Server-Ordners.")
        bkp_dir_v = ctk.StringVar(value=str(APP_DIR/"backups"))
        r = ctk.CTkFrame(s1,fg_color="transparent"); r.pack(padx=16,pady=(4,4),fill="x")
        r.grid_columnconfigure(0,weight=1)
        ctk.CTkEntry(r,textvariable=bkp_dir_v,fg_color=CARD,border_color=BORDER,text_color=TEXT
                     ).grid(row=0,column=0,sticky="ew",padx=(0,8))
        ctk.CTkButton(r,text="…",fg_color=CARD,text_color=TEXT,width=36,
                      command=lambda:bkp_dir_v.set(filedialog.askdirectory() or bkp_dir_v.get())
                      ).grid(row=0,column=1)
        lbl1=ctk.CTkLabel(s1,text="",text_color=TEXT_MUTED,font=ctk.CTkFont("Segoe UI",11))
        lbl1.pack(padx=16)
        def local_bkp():
            if not self.server_name: return
            out=Path(bkp_dir_v.get()); out.mkdir(parents=True,exist_ok=True)
            ts=time.strftime("%Y%m%d_%H%M%S"); name=f"{self.server_name}_{ts}"
            lbl1.configure(text="Backup läuft…",text_color=GREEN)
            def do():
                shutil.make_archive(str(out/name),"zip",str(SERVERS_DIR/self.server_name))
                lbl1.configure(text=f"Fertig: {out/name}.zip",text_color=GREEN)
                self._p_backups()
            threading.Thread(target=do,daemon=True).start()
        ctk.CTkButton(s1,text="Backup erstellen",fg_color=GREEN,hover_color=GREEN_HOV,
                      text_color="#000",font=ctk.CTkFont("Segoe UI",13,"bold"),height=42,
                      command=local_bkp).pack(padx=16,pady=(4,14),fill="x")

        # Google Cloud
        s2 = self._card(scroll, "☁  Google Cloud Storage",
                        "Lade Backups automatisch in einen GCS-Bucket hoch.")
        def gf(parent, lbl, ph, pw=False):
            ctk.CTkLabel(parent,text=lbl,text_color=TEXT_MUTED,
                         font=ctk.CTkFont("Segoe UI",10)).pack(padx=16,pady=(8,0),anchor="w")
            e=ctk.CTkEntry(parent,placeholder_text=ph,fg_color=CARD,border_color=BORDER,
                            text_color=TEXT,show="•" if pw else "")
            e.pack(padx=16,pady=(2,0),fill="x"); return e
        self._gcs_bucket=gf(s2,"Bucket-Name","mein-server-backup")
        self._gcs_prefix=gf(s2,"Ordner-Präfix","backups/")
        self._gcs_key   =gf(s2,"Service-Account JSON","/pfad/zu/key.json")
        ctk.CTkButton(s2,text="JSON auswählen",fg_color=CARD,text_color=TEXT,height=30,
                      command=lambda:self._gcs_key.delete(0,"end") or
                          self._gcs_key.insert(0,filedialog.askopenfilename(filetypes=[("JSON","*.json")]) or "")
                      ).pack(padx=16,pady=4,anchor="w")
        lbl2=ctk.CTkLabel(s2,text="",text_color=TEXT_MUTED,font=ctk.CTkFont("Segoe UI",11)); lbl2.pack(padx=16)
        def cloud_bkp():
            bucket=self._gcs_bucket.get().strip(); key=self._gcs_key.get().strip()
            prefix=self._gcs_prefix.get().strip()
            if not bucket or not key:
                lbl2.configure(text="Bitte Bucket und Key angeben.",text_color=RED); return
            lbl2.configure(text="Upload läuft…",text_color=GREEN)
            def do():
                try:
                    from google.cloud import storage; import os as _os
                    _os.environ["GOOGLE_APPLICATION_CREDENTIALS"]=key
                    client=storage.Client(); bkt=client.bucket(bucket)
                    ts=time.strftime("%Y%m%d_%H%M%S"); zp=APP_DIR/f"tmp_{ts}.zip"
                    shutil.make_archive(str(zp.with_suffix("")),"zip",str(SERVERS_DIR/self.server_name))
                    bn=f"{prefix}{self.server_name}_{ts}.zip"
                    bkt.blob(bn).upload_from_filename(str(zp)); zp.unlink(missing_ok=True)
                    lbl2.configure(text=f"Hochgeladen: gs://{bucket}/{bn}",text_color=GREEN)
                except ImportError:
                    lbl2.configure(text="pip install google-cloud-storage",text_color=RED)
                except Exception as e:
                    lbl2.configure(text=f"Fehler: {e}",text_color=RED)
            threading.Thread(target=do,daemon=True).start()
        ctk.CTkButton(s2,text="In Cloud hochladen",fg_color=BLUE,text_color="#fff",
                      font=ctk.CTkFont("Segoe UI",13,"bold"),height=42,
                      command=cloud_bkp).pack(padx=16,pady=(4,14),fill="x")

        # Vorhandene Backups
        s3=self._card(scroll,"Vorhandene Backups","")
        bkp_dir=APP_DIR/"backups"; bkp_dir.mkdir(exist_ok=True)
        zips=sorted(bkp_dir.glob("*.zip"),reverse=True)
        if zips:
            for z in zips[:10]:
                r2=ctk.CTkFrame(s3,fg_color=CARD,corner_radius=6)
                r2.pack(padx=16,pady=2,fill="x")
                ctk.CTkLabel(r2,text=z.name,text_color=TEXT,font=ctk.CTkFont("Segoe UI",11)
                             ).pack(side="left",padx=10,pady=6)
                ctk.CTkLabel(r2,text=f"{z.stat().st_size/1e6:.1f} MB",
                             text_color=TEXT_MUTED,font=ctk.CTkFont("Segoe UI",10)
                             ).pack(side="right",padx=10)
        else:
            ctk.CTkLabel(s3,text="Noch keine Backups.",text_color=TEXT_MUTED,
                         font=ctk.CTkFont("Segoe UI",11)).pack(padx=16,pady=(0,10))

    # ═════════════════════════════════════════════════════════════════════════
    # PAGE: ZUGRIFF
    # ═════════════════════════════════════════════════════════════════════════
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

        if not all_users:
            ctk.CTkLabel(scroll,
                text="Keine anderen Benutzer registriert.\nMelde dich aus und erstelle weitere Konten über 'Registrieren'.",
                text_color=TEXT_MUTED,font=ctk.CTkFont("Segoe UI",12)).pack(pady=20)
        else:
            for user in all_users:
                user_perms = srv_access.get(user,{})
                card = ctk.CTkFrame(scroll,fg_color=SIDEBAR_BG,corner_radius=10)
                card.pack(fill="x",pady=6)
                ctk.CTkLabel(card,text=f"👤  {user}",
                             font=ctk.CTkFont("Segoe UI",14,"bold"),text_color=TEXT
                             ).pack(padx=16,pady=(12,4),anchor="w")
                perm_vars={}
                grid2=ctk.CTkFrame(card,fg_color="transparent"); grid2.pack(padx=14,fill="x")
                for ci,(key,label) in enumerate(PERMISSIONS):
                    r2,c2=divmod(ci,2)
                    pf=ctk.CTkFrame(grid2,fg_color=CARD,corner_radius=8)
                    pf.grid(row=r2,column=c2,padx=3,pady=3,sticky="ew")
                    grid2.grid_columnconfigure(c2,weight=1)
                    var=ctk.BooleanVar(value=user_perms.get(key,False))
                    ctk.CTkCheckBox(pf,text=label,variable=var,
                                    text_color=TEXT,font=ctk.CTkFont("Segoe UI",11),
                                    fg_color=GREEN,hover_color=GREEN_HOV,
                                    checkmark_color="#000").pack(padx=10,pady=6,anchor="w")
                    perm_vars[key]=var
                br=ctk.CTkFrame(card,fg_color="transparent"); br.pack(padx=16,pady=(8,12),fill="x")
                def save_perm(u=user,pv=perm_vars):
                    ad=load_json(ACCESS_DB,{}); sk=self.server_name or "_"
                    if sk not in ad: ad[sk]={}
                    ad[sk][u]={k:v.get() for k,v in pv.items()}
                    save_json(ACCESS_DB,ad)
                    messagebox.showinfo("Gespeichert",f"Berechtigungen für {u} gespeichert.")
                def revoke(u=user):
                    ad=load_json(ACCESS_DB,{}); sk=self.server_name or "_"
                    if sk in ad and u in ad[sk]: del ad[sk][u]; save_json(ACCESS_DB,ad)
                    self._p_access()
                ctk.CTkButton(br,text="Speichern",fg_color=GREEN,hover_color=GREEN_HOV,
                              text_color="#000",height=34,width=120,command=save_perm).pack(side="left",padx=(0,8))
                ctk.CTkButton(br,text="Zugriff entziehen",fg_color=RED,text_color="#fff",
                              height=34,width=140,command=revoke).pack(side="left")

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

    def _logout(self):
        clear_session()
        self.destroy()
        LoginWindow().mainloop()

    # ── Schließen ─────────────────────────────────────────────────────────────
    def _on_close(self):
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("Server läuft",
                "Der Server läuft noch.\nJetzt stoppen und beenden?"):
                return
            try: self.proc.stdin.write("stop\n"); self.proc.stdin.flush(); self.proc.wait(timeout=10)
            except: self.proc.kill()
        self.destroy()

# ══════════════════════════════════════════════════════════════════════════════
class SplashScreen(ctk.CTk):
    """Zeigt beim Start eine kurze Ladeansicht und prüft/installiert Java."""
    def __init__(self):
        super().__init__()
        self.title("MineHost Local")
        self.geometry("420x280")
        self.resizable(False, False)
        self.configure(fg_color=BG)
        self.overrideredirect(True)          # kein Fensterrahmen
        # Zentrieren
        self.update_idletasks()
        sw = self.winfo_screenwidth(); sh = self.winfo_screenheight()
        self.geometry(f"420x280+{(sw-420)//2}+{(sh-280)//2}")

        logo = make_logo(56)
        ctk.CTkLabel(self, image=logo, text="").pack(pady=(36,8))
        ctk.CTkLabel(self, text="MineHost Local",
                     font=ctk.CTkFont("Segoe UI",22,"bold"), text_color=GREEN).pack()
        self.status_lbl = ctk.CTkLabel(self, text="Starte…",
                                        font=ctk.CTkFont("Segoe UI",12), text_color=TEXT_MUTED)
        self.status_lbl.pack(pady=(12,6))
        self.prog = ctk.CTkProgressBar(self, fg_color=CARD, progress_color=GREEN, mode="indeterminate")
        self.prog.pack(padx=60, fill="x")
        self.prog.start()
        self.after(200, self._check_java)

    def _check_java(self):
        if java_available():
            self._proceed()
        else:
            self.status_lbl.configure(text="Java nicht gefunden — wird installiert…")
            install_java_background(
                on_done=lambda: self.after(0, self._java_ok),
                on_error=lambda e: self.after(0, lambda: self._java_fail(e))
            )

    def _java_ok(self):
        self.status_lbl.configure(text="Java installiert ✓", text_color=GREEN)
        self.after(800, self._proceed)

    def _java_fail(self, err):
        self.status_lbl.configure(
            text="Java-Installation fehlgeschlagen.\nBitte manuell installieren: https://adoptium.net",
            text_color=RED)
        self.prog.stop()
        # Trotzdem weitermachen — vielleicht ist java doch irgendwo
        self.after(3000, self._proceed)

    def _proceed(self):
        self.prog.stop()
        self.destroy()
        saved = load_session()
        if saved and saved in load_users():
            MainApp(username=saved).mainloop()
        else:
            LoginWindow().mainloop()


if __name__ == "__main__":
    SplashScreen().mainloop()
