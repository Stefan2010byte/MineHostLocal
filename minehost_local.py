"""
MineHost Local — Lokale Minecraft-Server-Verwaltung
pip install customtkinter psutil requests pillow google-cloud-storage
pyinstaller --onefile --windowed --name MineHostLocal minehost_local.py
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import json, os, sys, hashlib, threading, subprocess, time, shutil, requests
import psutil
from pathlib import Path
from PIL import Image, ImageDraw
import socket

# ── Pfade ────────────────────────────────────────────────────────────────────
APP_DIR    = Path(os.getenv("APPDATA")) / "MineHostLocal"
USERS_DB   = APP_DIR / "users.json"
SERVERS_DIR= APP_DIR / "servers"
ACCESS_DB  = APP_DIR / "access.json"
APP_DIR.mkdir(parents=True, exist_ok=True)
SERVERS_DIR.mkdir(exist_ok=True)

# ── Theme ─────────────────────────────────────────────────────────────────────
BG_DARK    = "#0f1117"
BG_PANEL   = "#1a1d27"
BG_CARD    = "#21263a"
ACCENT     = "#00c853"
ACCENT_RED = "#f44336"
ACCENT_BLUE= "#2979ff"
ACCENT_YEL = "#ffd600"
TEXT_PRI   = "#e8eaf6"
TEXT_SEC   = "#7986cb"
NAV_W      = 210

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ── SERVER-TYPEN ──────────────────────────────────────────────────────────────
SERVER_TYPES = {
    "Vanilla":      {"icon": "✔", "tag": "vanilla",  "color": ACCENT},
    "Snapshot":     {"icon": "📸","tag": "vanilla",  "color": "#80cbc4"},
    "Paper/Bukkit": {"icon": "🧩","tag": "paper",    "color": ACCENT,    "plugins": True},
    "Spigot/Bukkit":{"icon": "🧩","tag": "spigot",   "color": ACCENT,    "plugins": True},
    "Purpur/Bukkit":{"icon": "🧩","tag": "purpur",   "color": "#ce93d8", "plugins": True},
    "Folia":        {"icon": "🧩","tag": "folia",    "color": "#80deea", "plugins": True},
    "Fabric":       {"icon": "⚙", "tag": "fabric",   "color": "#ffcc80", "mods": True},
    "Quilt":        {"icon": "⚙", "tag": "quilt",    "color": "#b39ddb", "mods": True},
    "NeoForge":     {"icon": "⚙", "tag": "neoforge", "color": "#ef9a9a", "mods": True},
    "Forge":        {"icon": "⚙", "tag": "forge",    "color": "#ffab91", "mods": True},
    "Modpacks":     {"icon": "⚙", "tag": "modpack",  "color": "#a5d6a7", "mods": True},
    "Arclight":     {"icon": "⚙", "tag": "arclight", "color": "#80cbc4", "plugins": True, "mods": True},
}

VANILLA_VERSIONS = {
    "1.21.4": "https://piston-data.mojang.com/v1/objects/4707d00eb834b446575d89a61a11b5d548d8c001/server.jar",
    "1.21.1": "https://piston-data.mojang.com/v1/objects/59353fb40c36d304f2035d51e7d6e6baa98dc05c/server.jar",
    "1.20.4": "https://piston-data.mojang.com/v1/objects/8dd1a28015f51b1803213892b50b7b4fc76e594d/server.jar",
    "1.20.1": "https://piston-data.mojang.com/v1/objects/84194a2f286ef7c14ed7ce0090dba59902951553/server.jar",
    "1.19.4": "https://piston-data.mojang.com/v1/objects/8f3112a1049751cc472ec13e397eade5336ca7ae/server.jar",
}

PERMISSIONS = [
    ("server_startstop",  "Server starten / stoppen"),
    ("options",           "Optionen bearbeiten"),
    ("console",           "Konsole einsehen"),
    ("console_cmd",       "Befehle in Konsole senden"),
    ("players_op",        "OP-Rechte vergeben"),
    ("players_whitelist", "Whitelist verwalten"),
    ("players_ban",       "Spieler bannen"),
    ("software",          "Software wechseln"),
    ("worlds",            "Welten verwalten"),
    ("backups",           "Backups erstellen"),
    ("files",             "Dateien/Mods verwalten"),
]

# ── Hilfsfunktionen ──────────────────────────────────────────────────────────
def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def load_json(path, default):
    if Path(path).exists():
        try: return json.loads(Path(path).read_text())
        except: pass
    return default

def save_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2))

def load_users(): return load_json(USERS_DB, {})
def save_users(d): save_json(USERS_DB, d)
def load_access(): return load_json(ACCESS_DB, {})
def save_access(d): save_json(ACCESS_DB, d)

def load_server_cfg(name):
    return load_json(SERVERS_DIR / name / "minehost.json", {})

def save_server_cfg(name, cfg):
    p = SERVERS_DIR / name
    p.mkdir(exist_ok=True)
    save_json(p / "minehost.json", cfg)

def list_servers():
    return [d.name for d in SERVERS_DIR.iterdir() if d.is_dir() and (SERVERS_DIR/d.name/"minehost.json").exists()]

def get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except: return "127.0.0.1"

def get_paper_url(mc_version):
    try:
        r = requests.get(f"https://api.papermc.io/v2/projects/paper/versions/{mc_version}/builds", timeout=10)
        builds = r.json().get("builds", [])
        if not builds: return None
        latest = builds[-1]
        jar_name = latest["downloads"]["application"]["name"]
        return f"https://api.papermc.io/v2/projects/paper/versions/{mc_version}/builds/{latest['build']}/downloads/{jar_name}"
    except: return None

def make_logo(size=48):
    img = Image.new("RGBA", (size, size), (0,0,0,0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2,2,size-2,size-2], radius=12, fill="#21263a")
    b = size//3
    cols = ["#5d4037","#4caf50","#388e3c","#8d6e63","#4caf50","#2e7d32","#6d4c41","#33691e","#5d4037"]
    for i,c in enumerate(cols):
        r,col = divmod(i,3)
        x0,y0 = 8+col*b, 8+r*b
        d.rectangle([x0,y0,x0+b-2,y0+b-2], fill=c)
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size,size))

# ══════════════════════════════════════════════════════════════════════════════
# LOGIN
# ══════════════════════════════════════════════════════════════════════════════
class LoginWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MineHost Local")
        self.geometry("440x580")
        self.resizable(False, False)
        self.configure(fg_color=BG_DARK)
        self._mode = "login"
        self._build()

    def _build(self):
        logo = make_logo(72)
        ctk.CTkLabel(self, image=logo, text="").pack(pady=(36,6))
        ctk.CTkLabel(self, text="MineHost Local", font=ctk.CTkFont("Segoe UI",26,"bold"),
                     text_color=ACCENT).pack()
        ctk.CTkLabel(self, text="Dein lokaler Minecraft-Manager",
                     font=ctk.CTkFont("Segoe UI",12), text_color=TEXT_SEC).pack(pady=(2,20))

        f = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=16)
        f.pack(padx=36, fill="x")

        self.tab = ctk.CTkSegmentedButton(f, values=["Login","Registrieren"],
                                          command=self._switch,
                                          fg_color=BG_CARD, selected_color=ACCENT,
                                          selected_hover_color="#00a846",
                                          unselected_color=BG_CARD,
                                          font=ctk.CTkFont("Segoe UI",13,"bold"))
        self.tab.set("Login")
        self.tab.pack(padx=18, pady=(18,14), fill="x")

        def row(label, ph, show=""):
            ctk.CTkLabel(f, text=label, anchor="w", text_color=TEXT_SEC,
                         font=ctk.CTkFont("Segoe UI",12)).pack(padx=18, fill="x")
            e = ctk.CTkEntry(f, placeholder_text=ph, show=show,
                              fg_color=BG_CARD, border_color=ACCENT_BLUE,
                              font=ctk.CTkFont("Segoe UI",13))
            e.pack(padx=18, pady=(2,10), fill="x")
            return e

        self.e_user  = row("Benutzername", "z.B. Steve")
        self.e_pw    = row("Passwort", "••••••••", "•")
        self.e_email = ctk.CTkEntry(f, placeholder_text="E-Mail (optional)",
                                     fg_color=BG_CARD, border_color=ACCENT_BLUE,
                                     font=ctk.CTkFont("Segoe UI",13))

        self.btn = ctk.CTkButton(f, text="Einloggen", fg_color=ACCENT,
                                  hover_color="#00a846", text_color="#000",
                                  font=ctk.CTkFont("Segoe UI",14,"bold"),
                                  height=44, corner_radius=10, command=self._submit)
        self.btn.pack(padx=18, pady=(4,18), fill="x")

        self.err = ctk.CTkLabel(self, text="", text_color=ACCENT_RED,
                                 font=ctk.CTkFont("Segoe UI",12))
        self.err.pack()
        self.bind("<Return>", lambda e: self._submit())

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
            self.err.configure(text="Bitte alle Felder ausfüllen.")
            return
        users = load_users()
        if self._mode == "login":
            if user not in users or users[user]["pw"] != hash_pw(pw):
                self.err.configure(text="Falscher Benutzername oder Passwort.")
                return
        else:
            if user in users:
                self.err.configure(text="Benutzername bereits vergeben.")
                return
            users[user] = {"pw": hash_pw(pw), "email": self.e_email.get().strip(), "role": "admin"}
            save_users(users)
        self.destroy()
        MainApp(username=user).mainloop()

# ══════════════════════════════════════════════════════════════════════════════
# SETUP-ASSISTENT
# ══════════════════════════════════════════════════════════════════════════════
class SetupWizard(ctk.CTkToplevel):
    MC_VERSIONS = ["1.21.4","1.21.1","1.20.4","1.20.1","1.19.4"]

    def __init__(self, master, on_done):
        super().__init__(master)
        self.title("Neuen Server erstellen")
        self.geometry("680x780")
        self.resizable(False, False)
        self.configure(fg_color=BG_DARK)
        self.on_done = on_done
        self._selected_type = "Vanilla"
        self._build()
        self.grab_set()

    def _build(self):
        ctk.CTkLabel(self, text="Server erstellen",
                     font=ctk.CTkFont("Segoe UI",22,"bold"), text_color=ACCENT).pack(pady=(24,2))
        ctk.CTkLabel(self, text="Wähle einen Server-Typ und konfiguriere deinen Server.",
                     text_color=TEXT_SEC, font=ctk.CTkFont("Segoe UI",12)).pack(pady=(0,16))

        # Server-Typ Auswahl (Grid wie Aternos)
        type_frame = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=12)
        type_frame.pack(padx=24, fill="x", pady=(0,12))
        ctk.CTkLabel(type_frame, text="Java Edition", text_color=ACCENT,
                     font=ctk.CTkFont("Segoe UI",12,"bold")).pack(padx=16, pady=(12,6), anchor="w")

        grid = ctk.CTkFrame(type_frame, fg_color="transparent")
        grid.pack(padx=12, pady=(0,12), fill="x")
        self._type_btns = {}
        types = list(SERVER_TYPES.keys())
        cols = 3
        for i, name in enumerate(types):
            info = SERVER_TYPES[name]
            r, c = divmod(i, cols)
            btn = ctk.CTkButton(grid, text=f"{info['icon']}  {name}",
                                 fg_color=BG_CARD, hover_color=BG_DARK,
                                 text_color=TEXT_PRI, font=ctk.CTkFont("Segoe UI",12),
                                 height=52, corner_radius=8,
                                 command=lambda n=name: self._pick_type(n))
            btn.grid(row=r, column=c, padx=4, pady=4, sticky="ew")
            grid.grid_columnconfigure(c, weight=1)
            self._type_btns[name] = btn
        self._pick_type("Vanilla")

        # Konfiguration
        f = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=12)
        f.pack(padx=24, fill="x", pady=(0,12))

        def row(label, ph, default=""):
            ctk.CTkLabel(f, text=label, anchor="w", text_color=TEXT_SEC,
                         font=ctk.CTkFont("Segoe UI",12)).pack(padx=16, fill="x", pady=(10,0))
            e = ctk.CTkEntry(f, placeholder_text=ph, fg_color=BG_CARD,
                              border_color=ACCENT_BLUE, font=ctk.CTkFont("Segoe UI",13))
            if default: e.insert(0, default)
            e.pack(padx=16, pady=(2,0), fill="x")
            return e

        self.e_name    = row("Server-Name", "Mein Server")
        self.e_motd    = row("Beschreibung (MotD)", "Ein epischer Minecraft Server!")
        self.e_address = row("Server-Adresse (Subdomain/IP)", get_local_ip(), get_local_ip())
        self.e_port    = row("Port", "25565", "25565")
        self.e_players = row("Max. Spieler", "20", "20")

        ctk.CTkLabel(f, text="Minecraft-Version", anchor="w", text_color=TEXT_SEC,
                     font=ctk.CTkFont("Segoe UI",12)).pack(padx=16, fill="x", pady=(10,0))
        self.ver_var = ctk.StringVar(value=self.MC_VERSIONS[0])
        ctk.CTkOptionMenu(f, variable=self.ver_var, values=self.MC_VERSIONS,
                           fg_color=BG_CARD, button_color=ACCENT_BLUE,
                           font=ctk.CTkFont("Segoe UI",13)).pack(padx=16, pady=(2,16), fill="x")

        # Fortschritt
        pf = ctk.CTkFrame(self, fg_color="transparent")
        pf.pack(padx=24, fill="x")
        self.progress = ctk.CTkProgressBar(pf, fg_color=BG_CARD, progress_color=ACCENT)
        self.progress.set(0)
        self.progress.pack(fill="x")
        self.lbl_status = ctk.CTkLabel(pf, text="", text_color=TEXT_SEC,
                                        font=ctk.CTkFont("Segoe UI",11))
        self.lbl_status.pack(pady=(4,0))

        ctk.CTkButton(self, text="Server erstellen & JAR herunterladen",
                      fg_color=ACCENT, hover_color="#00a846", text_color="#000",
                      font=ctk.CTkFont("Segoe UI",14,"bold"), height=48, corner_radius=10,
                      command=self._create).pack(padx=24, pady=16, fill="x")

    def _pick_type(self, name):
        self._selected_type = name
        for n, btn in self._type_btns.items():
            info = SERVER_TYPES[n]
            if n == name:
                btn.configure(fg_color=info["color"], text_color="#000")
            else:
                btn.configure(fg_color=BG_CARD, text_color=TEXT_PRI)

    def _create(self):
        name     = self.e_name.get().strip() or "Mein_Server"
        motd     = self.e_motd.get().strip() or "A Minecraft Server"
        address  = self.e_address.get().strip() or get_local_ip()
        port     = self.e_port.get().strip() or "25565"
        players  = self.e_players.get().strip() or "20"
        mc_ver   = self.ver_var.get()
        srv_type = SERVER_TYPES[self._selected_type]["tag"]
        safe     = name.replace(" ","_")
        srv_dir  = SERVERS_DIR / safe
        srv_dir.mkdir(exist_ok=True)

        def download():
            self.lbl_status.configure(text="Ermittle Download-URL…")
            self.progress.set(0.05)

            if srv_type == "paper" or self._selected_type in ("Paper/Bukkit","Folia","Purpur/Bukkit","Spigot/Bukkit","Arclight"):
                url = get_paper_url(mc_ver) or VANILLA_VERSIONS.get(mc_ver)
            else:
                url = VANILLA_VERSIONS.get(mc_ver)

            if not url:
                self.lbl_status.configure(text="Keine JAR-URL gefunden.")
                return

            self.lbl_status.configure(text=f"Lade server.jar herunter…")
            try:
                r = requests.get(url, stream=True, timeout=90)
                total = int(r.headers.get("content-length", 0))
                done  = 0
                with open(srv_dir/"server.jar","wb") as fh:
                    for chunk in r.iter_content(8192):
                        fh.write(chunk)
                        done += len(chunk)
                        if total: self.progress.set(0.1 + 0.85*(done/total))
            except Exception as e:
                self.lbl_status.configure(text=f"Fehler: {e}")
                return

            (srv_dir/"eula.txt").write_text("eula=true\n")
            (srv_dir/"server.properties").write_text(
                f"server-port={port}\nmax-players={players}\nmotd={motd}\n"
                "online-mode=true\ndifficulty=normal\npvp=true\nwhite-list=false\n"
                "gamemode=survival\nlevel-name=world\nview-distance=10\n"
                "enable-command-block=false\nspawn-protection=16\n"
            )

            cfg = {"name":name,"mc_version":mc_ver,"type":srv_type,
                   "server_type_label":self._selected_type,
                   "port":port,"address":address,"max_players":players,
                   "motd":motd,"dir":str(srv_dir)}
            save_server_cfg(safe, cfg)

            self.lbl_status.configure(text="Fertig! Server bereit.")
            self.progress.set(1.0)
            time.sleep(0.8)
            self.destroy()
            self.on_done(safe)

        threading.Thread(target=download, daemon=True).start()

# ══════════════════════════════════════════════════════════════════════════════
# HAUPT-APP
# ══════════════════════════════════════════════════════════════════════════════
class MainApp(ctk.CTk):
    def __init__(self, username):
        super().__init__()
        self.username    = username
        self.server_name = None
        self.server_cfg  = {}
        self.proc        = None
        self._users      = load_users()

        self.title("MineHost Local")
        self.geometry("1160x740")
        self.minsize(960,620)
        self.configure(fg_color=BG_DARK)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_layout()
        servers = list_servers()
        if servers:
            self._select_server(servers[0])
        else:
            self._show_page("dashboard")

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, minsize=230)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=NAV_W, fg_color=BG_PANEL, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self._build_sidebar()

        self.main_frame = ctk.CTkFrame(self, fg_color=BG_DARK, corner_radius=0)
        self.main_frame.grid(row=0, column=1, sticky="nsew")

        self.right = ctk.CTkFrame(self, width=230, fg_color=BG_PANEL, corner_radius=0)
        self.right.grid(row=0, column=2, sticky="nsew")
        self.right.grid_propagate(False)
        self._build_right()

    def _build_sidebar(self):
        logo = make_logo(44)
        top = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        top.pack(pady=(18,2), padx=12, fill="x")
        ctk.CTkLabel(top, image=logo, text="").pack(side="left", padx=(0,8))
        ctk.CTkLabel(top, text="MineHost\nLocal", font=ctk.CTkFont("Segoe UI",13,"bold"),
                     text_color=ACCENT, justify="left").pack(side="left")

        ctk.CTkLabel(self.sidebar, text=f"@ {self.username}", text_color=TEXT_SEC,
                     font=ctk.CTkFont("Segoe UI",11)).pack(pady=(0,10))

        # Server-Auswahl Dropdown
        servers = list_servers()
        self._srv_var = ctk.StringVar(value=self.server_name or (servers[0] if servers else "—"))
        self._srv_menu = ctk.CTkOptionMenu(self.sidebar, variable=self._srv_var,
                                            values=servers or ["—"],
                                            fg_color=BG_CARD, button_color=ACCENT_BLUE,
                                            font=ctk.CTkFont("Segoe UI",12),
                                            command=self._select_server)
        self._srv_menu.pack(padx=10, pady=(0,10), fill="x")

        self._nav_btns = {}
        pages = [
            ("dashboard","  ● Server"),
            ("options",  "  ⚙ Optionen"),
            ("console",  "  > Konsole"),
            ("log",      "  📋 Log"),
            ("players",  "  👥 Spieler"),
            ("software", "  💾 Software"),
            ("plugins",  "  🧩 Plugins"),
            ("files",    "  📁 Dateien"),
            ("worlds",   "  🌍 Welten"),
            ("backups",  "  🔒 Backups"),
            ("access",   "  🔑 Zugriff"),
        ]
        for key, label in pages:
            btn = ctk.CTkButton(self.sidebar, text=label, anchor="w",
                                fg_color="transparent", hover_color=BG_CARD,
                                text_color=TEXT_PRI, font=ctk.CTkFont("Segoe UI",12),
                                height=34, corner_radius=8,
                                command=lambda k=key: self._show_page(k))
            btn.pack(padx=8, pady=1, fill="x")
            self._nav_btns[key] = btn

        ctk.CTkButton(self.sidebar, text="  + Neuer Server", anchor="w",
                      fg_color="transparent", hover_color=BG_CARD, text_color=ACCENT,
                      font=ctk.CTkFont("Segoe UI",12), height=34, corner_radius=8,
                      command=self._new_server).pack(padx=8, pady=(14,4), fill="x", side="bottom")

    def _build_right(self):
        ctk.CTkLabel(self.right, text="System-Monitor",
                     font=ctk.CTkFont("Segoe UI",13,"bold"), text_color=TEXT_PRI
                     ).pack(pady=(18,10), padx=14)

        def stat_card(label, color=ACCENT_BLUE):
            c = ctk.CTkFrame(self.right, fg_color=BG_CARD, corner_radius=10)
            c.pack(padx=14, pady=4, fill="x")
            ctk.CTkLabel(c, text=label, text_color=TEXT_SEC,
                         font=ctk.CTkFont("Segoe UI",11)).pack(padx=12, pady=(8,0), anchor="w")
            bar = ctk.CTkProgressBar(c, fg_color=BG_PANEL, progress_color=color)
            bar.set(0)
            bar.pack(padx=12, pady=(4,2), fill="x")
            lbl = ctk.CTkLabel(c, text="0%", text_color=TEXT_PRI,
                               font=ctk.CTkFont("Segoe UI",12,"bold"))
            lbl.pack(padx=12, pady=(0,8), anchor="w")
            return bar, lbl

        self.cpu_bar, self.cpu_lbl = stat_card("CPU-Auslastung", ACCENT_BLUE)
        self.ram_bar, self.ram_lbl = stat_card("RAM-Auslastung", ACCENT)
        self.ram_det = ctk.CTkLabel(self.right, text="", text_color=TEXT_SEC,
                                     font=ctk.CTkFont("Segoe UI",10))
        self.ram_det.pack(padx=14, anchor="w")

        sep = ctk.CTkFrame(self.right, height=1, fg_color=BG_CARD)
        sep.pack(padx=14, pady=14, fill="x")

        ctk.CTkLabel(self.right, text="Server-Info",
                     font=ctk.CTkFont("Segoe UI",13,"bold"), text_color=TEXT_PRI
                     ).pack(padx=14, pady=(0,8), anchor="w")
        self.info_ip   = ctk.CTkLabel(self.right, text="IP: localhost", text_color=ACCENT,
                                       font=ctk.CTkFont("Segoe UI",12,"bold"))
        self.info_ip.pack(padx=14, anchor="w")
        self.info_port = ctk.CTkLabel(self.right, text="Port: —", text_color=TEXT_SEC,
                                       font=ctk.CTkFont("Segoe UI",11))
        self.info_port.pack(padx=14, anchor="w")
        self.info_ver  = ctk.CTkLabel(self.right, text="Version: —", text_color=TEXT_SEC,
                                       font=ctk.CTkFont("Segoe UI",11))
        self.info_ver.pack(padx=14, anchor="w")
        self.info_type = ctk.CTkLabel(self.right, text="Typ: —", text_color=TEXT_SEC,
                                       font=ctk.CTkFont("Segoe UI",11))
        self.info_type.pack(padx=14, anchor="w")
        self.info_addr = ctk.CTkLabel(self.right, text="Adresse: —", text_color=TEXT_SEC,
                                       font=ctk.CTkFont("Segoe UI",11), wraplength=200)
        self.info_addr.pack(padx=14, anchor="w", pady=(0,4))

        self._update_monitor()

    def _update_monitor(self):
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory()
        self.cpu_bar.set(cpu/100)
        self.cpu_lbl.configure(text=f"{cpu:.1f}%")
        self.ram_bar.set(ram.percent/100)
        self.ram_lbl.configure(text=f"{ram.percent:.1f}%")
        self.ram_det.configure(text=f"{ram.used/1e9:.1f} GB / {ram.total/1e9:.1f} GB")
        self.after(2000, self._update_monitor)

    def _update_info(self):
        cfg = self.server_cfg
        self.info_ip.configure(text=f"IP: {cfg.get('address', get_local_ip())}")
        self.info_port.configure(text=f"Port: {cfg.get('port','25565')}")
        self.info_ver.configure(text=f"Version: {cfg.get('mc_version','?')}")
        self.info_type.configure(text=f"Typ: {cfg.get('server_type_label', cfg.get('type','?'))}")
        self.info_addr.configure(text=f"Adresse: {cfg.get('address','localhost')}:{cfg.get('port','25565')}")

    # ── Navigation ────────────────────────────────────────────────────────────
    def _clear_main(self):
        for w in self.main_frame.winfo_children():
            w.destroy()

    def _show_page(self, key):
        for k, b in self._nav_btns.items():
            b.configure(fg_color=ACCENT if k==key else "transparent",
                        text_color="#000" if k==key else TEXT_PRI)
        self._clear_main()
        getattr(self, f"_page_{key}")()

    def _select_server(self, name):
        self.server_name = name
        self.server_cfg  = load_server_cfg(name)
        self._srv_var.set(name)
        self._update_info()
        self._show_page("dashboard")

    def _new_server(self):
        SetupWizard(self, on_done=self._on_server_created)

    def _on_server_created(self, name):
        servers = list_servers()
        self._srv_menu.configure(values=servers)
        self._select_server(name)

    # ── DASHBOARD ─────────────────────────────────────────────────────────────
    def _page_dashboard(self):
        if not self.server_name:
            ctk.CTkLabel(self.main_frame, text="Kein Server vorhanden.",
                         font=ctk.CTkFont("Segoe UI",16), text_color=TEXT_SEC).pack(expand=True)
            ctk.CTkButton(self.main_frame, text="+ Server erstellen",
                          fg_color=ACCENT, text_color="#000", hover_color="#00a846",
                          font=ctk.CTkFont("Segoe UI",14,"bold"), height=50,
                          command=self._new_server).pack(pady=12, padx=60, fill="x")
            return

        cfg  = self.server_cfg
        name = cfg.get("name", self.server_name)
        is_on= self.proc is not None and self.proc.poll() is None

        f = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        f.pack(expand=True)

        ctk.CTkLabel(f, text=name, font=ctk.CTkFont("Segoe UI",26,"bold"),
                     text_color=TEXT_PRI).pack(pady=(0,4))
        ctk.CTkLabel(f, text=cfg.get("address","localhost"),
                     font=ctk.CTkFont("Segoe UI",13), text_color=TEXT_SEC).pack()

        # Status-Banner
        banner = ctk.CTkFrame(f, fg_color=ACCENT if is_on else ACCENT_RED,
                               corner_radius=10, height=48)
        banner.pack(fill="x", padx=40, pady=16)
        banner.pack_propagate(False)
        ctk.CTkLabel(banner,
                     text=f"{'● Online' if is_on else '● Ausgeschaltet'}",
                     font=ctk.CTkFont("Segoe UI",16,"bold"),
                     text_color="#000" if is_on else "#fff").pack(expand=True)

        # Start/Stopp
        self.start_btn = ctk.CTkButton(f,
            text="Stoppen" if is_on else "Starten",
            fg_color=ACCENT_RED if is_on else ACCENT,
            hover_color="#c62828" if is_on else "#00a846",
            text_color="#fff" if is_on else "#000",
            font=ctk.CTkFont("Segoe UI",18,"bold"),
            width=200, height=56, corner_radius=28,
            command=self._toggle_server)
        self.start_btn.pack(pady=12)

        # Verbinden-Info
        addr_frame = ctk.CTkFrame(f, fg_color=BG_PANEL, corner_radius=10)
        addr_frame.pack(padx=40, pady=8, fill="x")
        ctk.CTkLabel(addr_frame, text="Adresse", text_color=TEXT_SEC,
                     font=ctk.CTkFont("Segoe UI",11)).pack(padx=14, pady=(8,0), anchor="w")
        addr_row = ctk.CTkFrame(addr_frame, fg_color="transparent")
        addr_row.pack(padx=14, pady=(2,10), fill="x")
        addr_text = f"{cfg.get('address','localhost')}:{cfg.get('port','25565')}"
        ctk.CTkLabel(addr_row, text=addr_text, text_color=ACCENT,
                     font=ctk.CTkFont("Segoe UI",14,"bold")).pack(side="left")
        ctk.CTkButton(addr_row, text="Kopieren", fg_color=ACCENT_BLUE, text_color="#fff",
                      height=28, width=80, font=ctk.CTkFont("Segoe UI",11),
                      command=lambda: self.clipboard_append(addr_text) or self.update()
                      ).pack(side="right")

        # Info-Karten
        cards_frame = ctk.CTkFrame(f, fg_color="transparent")
        cards_frame.pack(padx=40, pady=4, fill="x")
        def info_card(label, value, color=TEXT_PRI):
            c = ctk.CTkFrame(cards_frame, fg_color=BG_PANEL, corner_radius=8)
            c.pack(side="left", expand=True, fill="x", padx=4)
            ctk.CTkLabel(c, text=label, text_color=TEXT_SEC,
                         font=ctk.CTkFont("Segoe UI",10)).pack(pady=(8,0))
            ctk.CTkLabel(c, text=value, text_color=color,
                         font=ctk.CTkFont("Segoe UI",13,"bold")).pack(pady=(2,8))

        info_card("Software", cfg.get("server_type_label", cfg.get("type","vanilla")).capitalize())
        info_card("Version",  cfg.get("mc_version","?"))
        info_card("Spieler",  f"0 / {cfg.get('max_players','20')}", ACCENT)

    def _toggle_server(self):
        if self.proc and self.proc.poll() is None:
            self._stop_server()
        else:
            self._start_server()

    def _start_server(self):
        srv_dir = Path(self.server_cfg.get("dir", str(SERVERS_DIR/self.server_name)))
        if not (srv_dir/"server.jar").exists():
            messagebox.showerror("Fehler","server.jar nicht gefunden.")
            return
        try:
            self.proc = subprocess.Popen(
                ["java","-Xmx2G","-Xms512M","-jar","server.jar","--nogui"],
                cwd=str(srv_dir), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )
        except FileNotFoundError:
            messagebox.showerror("Java fehlt",
                "Java nicht gefunden.\nBitte installieren: https://adoptium.net")
            return
        threading.Thread(target=self._read_log, daemon=True).start()
        self._show_page("dashboard")

    def _stop_server(self):
        if self.proc:
            try:
                self.proc.stdin.write("stop\n"); self.proc.stdin.flush()
                self.proc.wait(timeout=15)
            except: self.proc.kill()
            self.proc = None
        self._show_page("dashboard")

    def _read_log(self):
        for line in self.proc.stdout:
            self._append_console(line)

    def _append_console(self, text):
        if hasattr(self, "_con_box"):
            self._con_box.configure(state="normal")
            self._con_box.insert("end", text)
            self._con_box.see("end")
            self._con_box.configure(state="disabled")

    # ── LOG ───────────────────────────────────────────────────────────────────
    def _page_log(self):
        self._page_console(log_only=True)

    # ── KONSOLE ───────────────────────────────────────────────────────────────
    def _page_console(self, log_only=False):
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.main_frame,
                     text="Log" if log_only else "Konsole",
                     font=ctk.CTkFont("Segoe UI",18,"bold"), text_color=TEXT_PRI
                     ).grid(row=0, column=0, sticky="w", padx=20, pady=(16,4))

        self._con_box = ctk.CTkTextbox(self.main_frame, fg_color=BG_CARD,
                                        text_color="#a5d6a7",
                                        font=ctk.CTkFont("Consolas",11), state="disabled")
        self._con_box.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0,8))

        if not log_only:
            inp = ctk.CTkFrame(self.main_frame, fg_color="transparent")
            inp.grid(row=2, column=0, sticky="ew", padx=20, pady=(0,16))
            inp.grid_columnconfigure(0, weight=1)
            self._cmd_e = ctk.CTkEntry(inp, placeholder_text="Befehl (z.B. op Steve)…",
                                        fg_color=BG_CARD, border_color=ACCENT_BLUE,
                                        font=ctk.CTkFont("Consolas",12))
            self._cmd_e.grid(row=0, column=0, sticky="ew", padx=(0,8))
            self._cmd_e.bind("<Return>", lambda e: self._send_cmd())
            ctk.CTkButton(inp, text="Senden", fg_color=ACCENT_BLUE, text_color="#fff",
                          width=90, command=self._send_cmd).grid(row=0, column=1)

    def _send_cmd(self):
        cmd = self._cmd_e.get().strip()
        if not cmd: return
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write(cmd+"\n"); self.proc.stdin.flush()
                self._append_console(f"> {cmd}\n")
            except Exception as e:
                self._append_console(f"[Fehler] {e}\n")
        else:
            self._append_console("[Server nicht gestartet]\n")
        self._cmd_e.delete(0,"end")

    # ── SPIELER ───────────────────────────────────────────────────────────────
    def _page_players(self):
        ctk.CTkLabel(self.main_frame, text="Spieler verwalten",
                     font=ctk.CTkFont("Segoe UI",18,"bold"), text_color=TEXT_PRI
                     ).pack(pady=(16,10), padx=20, anchor="w")
        if not self.server_name:
            ctk.CTkLabel(self.main_frame, text="Kein Server.", text_color=TEXT_SEC).pack(); return

        tabs = self._make_tabs(self.main_frame, ["OP-Liste","Whitelist","Gebannte Spieler"])
        srv_dir = SERVERS_DIR / self.server_name

        def player_tab(tab_name, fname):
            tab = tabs.tab(tab_name)
            tab.grid_columnconfigure(0, weight=1); tab.grid_rowconfigure(0, weight=1)
            fp = srv_dir / fname
            data = []
            if fp.exists():
                try: data = json.loads(fp.read_text())
                except: pass
            names = [p.get("name","?") for p in data]
            box = ctk.CTkTextbox(tab, fg_color=BG_CARD, text_color=TEXT_PRI,
                                  font=ctk.CTkFont("Segoe UI",13))
            box.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0,8))
            box.insert("end", "\n".join(names) or "(Leer)")
            box.configure(state="disabled")
            ent = ctk.CTkEntry(tab, placeholder_text="Spielername…",
                                fg_color=BG_CARD, border_color=ACCENT_BLUE)
            ent.grid(row=1, column=0, sticky="ew", padx=(0,8), pady=(0,4))
            def add(e=ent, b=box, fp2=fp, d=data):
                n = e.get().strip()
                if not n: return
                if not any(p.get("name")==n for p in d):
                    d.append({"uuid":"","name":n})
                    fp2.write_text(json.dumps(d, indent=2))
                b.configure(state="normal"); b.insert("end",f"\n{n}"); b.configure(state="disabled")
                e.delete(0,"end")
            ctk.CTkButton(tab, text="Hinzufügen", fg_color=ACCENT, text_color="#000",
                          width=110, command=add).grid(row=1, column=1, pady=(0,4))

        player_tab("OP-Liste","ops.json")
        player_tab("Whitelist","whitelist.json")
        player_tab("Gebannte Spieler","banned-players.json")

    # ── SOFTWARE ──────────────────────────────────────────────────────────────
    def _page_software(self):
        ctk.CTkLabel(self.main_frame, text="Software",
                     font=ctk.CTkFont("Segoe UI",18,"bold"), text_color=TEXT_PRI
                     ).pack(pady=(16,4), padx=20, anchor="w")
        ctk.CTkLabel(self.main_frame,
                     text="Wähle den Server-Typ. Änderungen erfordern einen Neustart.",
                     text_color=TEXT_SEC, font=ctk.CTkFont("Segoe UI",12)
                     ).pack(padx=20, anchor="w", pady=(0,12))
        if not self.server_name:
            ctk.CTkLabel(self.main_frame, text="Kein Server.", text_color=TEXT_SEC).pack(); return

        scroll = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=(0,12))

        ctk.CTkLabel(scroll, text="Java Edition", text_color=ACCENT,
                     font=ctk.CTkFont("Segoe UI",13,"bold")).pack(anchor="w", pady=(0,8))

        grid_f = ctk.CTkFrame(scroll, fg_color="transparent")
        grid_f.pack(fill="x")
        self._sw_btns = {}
        cur = self.server_cfg.get("server_type_label","Vanilla")
        types = list(SERVER_TYPES.keys())
        cols  = 3
        for i, name in enumerate(types):
            info = SERVER_TYPES[name]
            r, c = divmod(i, cols)
            selected = name == cur
            btn = ctk.CTkButton(grid_f,
                text=f"{info['icon']}  {name}",
                fg_color=info["color"] if selected else BG_CARD,
                hover_color=info["color"],
                text_color="#000" if selected else TEXT_PRI,
                font=ctk.CTkFont("Segoe UI",12), height=54,
                corner_radius=8, command=lambda n=name: self._pick_software(n))
            btn.grid(row=r, column=c, padx=4, pady=4, sticky="ew")
            grid_f.grid_columnconfigure(c, weight=1)
            self._sw_btns[name] = btn

        ver_f = ctk.CTkFrame(scroll, fg_color=BG_PANEL, corner_radius=10)
        ver_f.pack(fill="x", pady=12)
        ctk.CTkLabel(ver_f, text="Version", text_color=TEXT_SEC,
                     font=ctk.CTkFont("Segoe UI",12)).pack(padx=14, pady=(10,2), anchor="w")
        self._sw_ver = ctk.StringVar(value=self.server_cfg.get("mc_version","1.21.4"))
        ctk.CTkOptionMenu(ver_f, variable=self._sw_ver,
                           values=["1.21.4","1.21.1","1.20.4","1.20.1","1.19.4"],
                           fg_color=BG_CARD, button_color=ACCENT_BLUE
                           ).pack(padx=14, pady=(0,12), fill="x")

        self._sw_lbl = ctk.CTkLabel(scroll, text="", text_color=TEXT_SEC,
                                     font=ctk.CTkFont("Segoe UI",11))
        self._sw_lbl.pack()
        ctk.CTkButton(scroll, text="Übernehmen & JAR aktualisieren",
                      fg_color=ACCENT_BLUE, text_color="#fff",
                      font=ctk.CTkFont("Segoe UI",13,"bold"), height=44,
                      command=self._apply_software).pack(fill="x", pady=8)
        self._selected_sw = cur

    def _pick_software(self, name):
        self._selected_sw = name
        cur_info = SERVER_TYPES[name]
        for n, btn in self._sw_btns.items():
            info = SERVER_TYPES[n]
            if n == name: btn.configure(fg_color=info["color"], text_color="#000")
            else: btn.configure(fg_color=BG_CARD, text_color=TEXT_PRI)

    def _apply_software(self):
        name = self._selected_sw
        ver  = self._sw_ver.get()
        self.server_cfg["server_type_label"] = name
        self.server_cfg["type"] = SERVER_TYPES[name]["tag"]
        self.server_cfg["mc_version"] = ver
        save_server_cfg(self.server_name, self.server_cfg)
        self._sw_lbl.configure(text="Lade neue JAR…", text_color=ACCENT)
        def dl():
            info = SERVER_TYPES[name]
            if info["tag"] in ("paper","spigot","folia","purpur","arclight"):
                url = get_paper_url(ver) or VANILLA_VERSIONS.get(ver)
            else:
                url = VANILLA_VERSIONS.get(ver)
            if url:
                srv_dir = Path(self.server_cfg["dir"])
                jar = srv_dir/"server.jar"
                if jar.exists(): jar.rename(srv_dir/"server.jar.bak")
                r = requests.get(url, stream=True, timeout=90)
                with open(str(jar),"wb") as fh:
                    for chunk in r.iter_content(8192): fh.write(chunk)
            self._sw_lbl.configure(text="Fertig! Bitte Server neu starten.", text_color=ACCENT)
        threading.Thread(target=dl, daemon=True).start()

    # ── PLUGINS ───────────────────────────────────────────────────────────────
    def _page_plugins(self):
        self._file_page("Plugins", "plugins",
                        "Lege hier deine Plugin-.jar-Dateien ab.",
                        "🧩 Plugins")

    # ── DATEIEN ───────────────────────────────────────────────────────────────
    def _page_files(self):
        ctk.CTkLabel(self.main_frame, text="📁 Dateien & Mods",
                     font=ctk.CTkFont("Segoe UI",18,"bold"), text_color=TEXT_PRI
                     ).pack(pady=(16,4), padx=20, anchor="w")
        if not self.server_name:
            ctk.CTkLabel(self.main_frame, text="Kein Server.", text_color=TEXT_SEC).pack(); return

        tabs = self._make_tabs(self.main_frame, ["Mods","Resourcepacks","Datapacks","Alle Dateien"])
        srv_dir = SERVERS_DIR / self.server_name

        for folder_name, tab_name in [("mods","Mods"),("resourcepacks","Resourcepacks"),
                                       ("datapacks","Datapacks")]:
            self._folder_tab(tabs, tab_name, srv_dir/folder_name)

        # Alle Dateien
        tab = tabs.tab("Alle Dateien")
        tab.grid_columnconfigure(0, weight=1); tab.grid_rowconfigure(0, weight=1)
        box = ctk.CTkTextbox(tab, fg_color=BG_CARD, text_color=TEXT_PRI,
                              font=ctk.CTkFont("Consolas",11))
        box.grid(row=0, column=0, sticky="nsew", pady=(0,8))
        try:
            for item in sorted(srv_dir.iterdir()):
                box.insert("end", f"{'[DIR] ' if item.is_dir() else '[   ] '}{item.name}\n")
        except: pass
        box.configure(state="disabled")
        ctk.CTkButton(tab, text="Im Explorer öffnen", fg_color=BG_CARD, text_color=TEXT_PRI,
                      height=34, command=lambda: os.startfile(str(srv_dir))
                      ).grid(row=1, column=0, sticky="ew")

    def _file_page(self, title, folder, desc, icon=""):
        ctk.CTkLabel(self.main_frame, text=f"{icon}  {title}",
                     font=ctk.CTkFont("Segoe UI",18,"bold"), text_color=TEXT_PRI
                     ).pack(pady=(16,2), padx=20, anchor="w")
        ctk.CTkLabel(self.main_frame, text=desc, text_color=TEXT_SEC,
                     font=ctk.CTkFont("Segoe UI",12)).pack(padx=20, anchor="w", pady=(0,10))
        if not self.server_name:
            ctk.CTkLabel(self.main_frame, text="Kein Server.", text_color=TEXT_SEC).pack(); return

        tabs = self._make_tabs(self.main_frame, [title])
        self._folder_tab(tabs, title, SERVERS_DIR/self.server_name/folder)

    def _folder_tab(self, tabs, tab_name, folder_path):
        folder_path = Path(folder_path)
        folder_path.mkdir(exist_ok=True)
        tab = tabs.tab(tab_name)
        tab.grid_columnconfigure(0, weight=1); tab.grid_rowconfigure(0, weight=1)
        box = ctk.CTkTextbox(tab, fg_color=BG_CARD, text_color=TEXT_PRI,
                              font=ctk.CTkFont("Segoe UI",12))
        box.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0,8))

        def refresh():
            box.configure(state="normal"); box.delete("1.0","end")
            files = list(folder_path.iterdir())
            if files:
                for f in sorted(files):
                    box.insert("end", f"{'📁' if f.is_dir() else '📄'} {f.name}\n")
            else: box.insert("end","(Leer)")
            box.configure(state="disabled")

        refresh()
        ctk.CTkButton(tab, text="+ Hinzufügen", fg_color=ACCENT_BLUE, text_color="#fff",
                      height=34, command=lambda: [
                          [shutil.copy(s, folder_path/Path(s).name)
                           for s in filedialog.askopenfilenames(title="Dateien hinzufügen")],
                          refresh()
                      ]).grid(row=1, column=0, sticky="ew", padx=(0,8))
        ctk.CTkButton(tab, text="Ordner öffnen", fg_color=BG_CARD, text_color=TEXT_PRI,
                      height=34, command=lambda: os.startfile(str(folder_path))
                      ).grid(row=1, column=1)

    # ── WELTEN ────────────────────────────────────────────────────────────────
    def _page_worlds(self):
        ctk.CTkLabel(self.main_frame, text="🌍 Welten",
                     font=ctk.CTkFont("Segoe UI",18,"bold"), text_color=TEXT_PRI
                     ).pack(pady=(16,4), padx=20, anchor="w")
        ctk.CTkLabel(self.main_frame, text="Verwalte alle Welten deines Servers.",
                     text_color=TEXT_SEC, font=ctk.CTkFont("Segoe UI",12)
                     ).pack(padx=20, anchor="w", pady=(0,12))
        if not self.server_name:
            ctk.CTkLabel(self.main_frame, text="Kein Server.", text_color=TEXT_SEC).pack(); return

        srv_dir = SERVERS_DIR / self.server_name
        scroll  = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=(0,16))

        # Suche nach Weltordnern: enthalten level.dat
        world_dirs = []
        for d in srv_dir.iterdir():
            if d.is_dir() and (d/"level.dat").exists():
                world_dirs.append(d)

        # Dimensionen-Map
        DIM_NAMES = {
            "world": ("Overworld","🌱"),
            "world_nether": ("Nether","🔥"),
            "world_the_end": ("The End","🌌"),
        }

        if not world_dirs:
            ctk.CTkLabel(scroll, text="Keine Welten gefunden. Starte den Server einmal, um Welten zu generieren.",
                         text_color=TEXT_SEC, font=ctk.CTkFont("Segoe UI",12),
                         wraplength=500).pack(pady=20)
        else:
            for world in sorted(world_dirs):
                dim_name, icon = DIM_NAMES.get(world.name, (world.name, "🗺"))
                size_mb = sum(f.stat().st_size for f in world.rglob("*") if f.is_file()) / 1e6

                card = ctk.CTkFrame(scroll, fg_color=BG_PANEL, corner_radius=12)
                card.pack(fill="x", pady=5)
                card.grid_columnconfigure(1, weight=1)

                ctk.CTkLabel(card, text=icon, font=ctk.CTkFont("Segoe UI",28)
                             ).grid(row=0, column=0, rowspan=2, padx=16, pady=12)
                ctk.CTkLabel(card, text=dim_name,
                             font=ctk.CTkFont("Segoe UI",15,"bold"), text_color=TEXT_PRI,
                             anchor="w").grid(row=0, column=1, sticky="w", pady=(10,0))
                ctk.CTkLabel(card, text=f"{world.name}  •  {size_mb:.1f} MB",
                             text_color=TEXT_SEC, font=ctk.CTkFont("Segoe UI",11),
                             anchor="w").grid(row=1, column=1, sticky="w", pady=(0,10))

                btns = ctk.CTkFrame(card, fg_color="transparent")
                btns.grid(row=0, column=2, rowspan=2, padx=10)

                ctk.CTkButton(btns, text="Öffnen", fg_color=BG_CARD, text_color=TEXT_PRI,
                              width=80, height=30,
                              command=lambda p=world: os.startfile(str(p))
                              ).pack(pady=2)
                ctk.CTkButton(btns, text="Backup", fg_color=ACCENT_BLUE, text_color="#fff",
                              width=80, height=30,
                              command=lambda p=world, n=dim_name: self._backup_world(p, n)
                              ).pack(pady=2)
                ctk.CTkButton(btns, text="Löschen", fg_color=ACCENT_RED, text_color="#fff",
                              width=80, height=30,
                              command=lambda p=world, n=dim_name: self._delete_world(p, n)
                              ).pack(pady=2)

        # Welt zurücksetzen / importieren
        act_frame = ctk.CTkFrame(scroll, fg_color=BG_PANEL, corner_radius=10)
        act_frame.pack(fill="x", pady=8)
        ctk.CTkLabel(act_frame, text="Aktionen", text_color=TEXT_SEC,
                     font=ctk.CTkFont("Segoe UI",12,"bold")).pack(padx=14, pady=(10,4), anchor="w")
        row = ctk.CTkFrame(act_frame, fg_color="transparent")
        row.pack(padx=14, pady=(0,10), fill="x")
        ctk.CTkButton(row, text="Welt importieren (.zip)", fg_color=BG_CARD, text_color=TEXT_PRI,
                      height=36, command=lambda: self._import_world(srv_dir)).pack(side="left", padx=(0,8))
        ctk.CTkButton(row, text="Seed abrufen", fg_color=BG_CARD, text_color=TEXT_PRI,
                      height=36, command=self._get_seed).pack(side="left")

    def _backup_world(self, world_path, name):
        backup_dir = APP_DIR / "world_backups"
        backup_dir.mkdir(exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        out = backup_dir / f"{name}_{ts}.zip"
        threading.Thread(
            target=lambda: shutil.make_archive(str(out.with_suffix("")), "zip", str(world_path.parent), world_path.name),
            daemon=True
        ).start()
        messagebox.showinfo("Backup", f"Backup wird erstellt:\n{out}")

    def _delete_world(self, world_path, name):
        if messagebox.askyesno("Welt löschen", f"'{name}' wirklich löschen?\nDiese Aktion kann nicht rückgängig gemacht werden!"):
            shutil.rmtree(world_path, ignore_errors=True)
            self._show_page("worlds")

    def _import_world(self, srv_dir):
        path = filedialog.askopenfilename(title="Welt importieren", filetypes=[("ZIP","*.zip")])
        if path:
            shutil.unpack_archive(path, str(srv_dir))
            messagebox.showinfo("Import","Welt importiert.")
            self._show_page("worlds")

    def _get_seed(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write("seed\n"); self.proc.stdin.flush()
                messagebox.showinfo("Seed","Seed-Befehl gesendet. Sieh in der Konsole nach.")
            except: pass
        else:
            messagebox.showinfo("Seed","Server starten, dann Seed über Konsole abrufen.")

    # ── BACKUPS ───────────────────────────────────────────────────────────────
    def _page_backups(self):
        ctk.CTkLabel(self.main_frame, text="🔒 Backups",
                     font=ctk.CTkFont("Segoe UI",18,"bold"), text_color=TEXT_PRI
                     ).pack(pady=(16,4), padx=20, anchor="w")
        ctk.CTkLabel(self.main_frame, text="Erstelle lokale oder Cloud-Backups deines Servers.",
                     text_color=TEXT_SEC, font=ctk.CTkFont("Segoe UI",12)
                     ).pack(padx=20, anchor="w", pady=(0,12))

        scroll = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=(0,16))

        # Lokales Backup
        loc = ctk.CTkFrame(scroll, fg_color=BG_PANEL, corner_radius=12)
        loc.pack(fill="x", pady=6)
        ctk.CTkLabel(loc, text="💾  Lokales Backup", text_color=TEXT_PRI,
                     font=ctk.CTkFont("Segoe UI",14,"bold")).pack(padx=16, pady=(12,4), anchor="w")
        ctk.CTkLabel(loc, text="Erstellt ein ZIP-Archiv des gesamten Server-Ordners.",
                     text_color=TEXT_SEC, font=ctk.CTkFont("Segoe UI",11)
                     ).pack(padx=16, anchor="w")

        bkp_dir_var = ctk.StringVar(value=str(APP_DIR/"backups"))
        row = ctk.CTkFrame(loc, fg_color="transparent")
        row.pack(padx=16, pady=(8,4), fill="x")
        row.grid_columnconfigure(0, weight=1)
        ctk.CTkEntry(row, textvariable=bkp_dir_var, fg_color=BG_CARD,
                     border_color=ACCENT_BLUE).grid(row=0, column=0, sticky="ew", padx=(0,8))
        ctk.CTkButton(row, text="Durchsuchen…", fg_color=BG_CARD, text_color=TEXT_PRI,
                      width=110, command=lambda: bkp_dir_var.set(
                          filedialog.askdirectory() or bkp_dir_var.get())
                      ).grid(row=0, column=1)

        self._bkp_lbl = ctk.CTkLabel(loc, text="", text_color=TEXT_SEC,
                                      font=ctk.CTkFont("Segoe UI",11))
        self._bkp_lbl.pack(padx=16)

        def local_backup():
            if not self.server_name: return
            out_dir = Path(bkp_dir_var.get())
            out_dir.mkdir(parents=True, exist_ok=True)
            ts  = time.strftime("%Y%m%d_%H%M%S")
            out = out_dir / f"{self.server_name}_{ts}"
            self._bkp_lbl.configure(text="Backup läuft…", text_color=ACCENT)
            def do():
                shutil.make_archive(str(out), "zip", str(SERVERS_DIR/self.server_name))
                self._bkp_lbl.configure(text=f"Fertig: {out}.zip", text_color=ACCENT)
                self._page_backups()
            threading.Thread(target=do, daemon=True).start()

        ctk.CTkButton(loc, text="Lokales Backup erstellen", fg_color=ACCENT,
                      text_color="#000", hover_color="#00a846",
                      font=ctk.CTkFont("Segoe UI",13,"bold"), height=42,
                      command=local_backup).pack(padx=16, pady=(4,14), fill="x")

        # Google Cloud Backup
        gcs = ctk.CTkFrame(scroll, fg_color=BG_PANEL, corner_radius=12)
        gcs.pack(fill="x", pady=6)
        ctk.CTkLabel(gcs, text="☁  Google Cloud Storage Backup",
                     text_color=TEXT_PRI, font=ctk.CTkFont("Segoe UI",14,"bold")
                     ).pack(padx=16, pady=(12,4), anchor="w")
        ctk.CTkLabel(gcs, text="Lade Backups automatisch in einen Google Cloud Storage Bucket hoch.",
                     text_color=TEXT_SEC, font=ctk.CTkFont("Segoe UI",11), wraplength=480
                     ).pack(padx=16, anchor="w")

        def gcs_entry(label, ph, pw=False):
            ctk.CTkLabel(gcs, text=label, text_color=TEXT_SEC,
                         font=ctk.CTkFont("Segoe UI",11)).pack(padx=16, pady=(8,0), anchor="w")
            e = ctk.CTkEntry(gcs, placeholder_text=ph, fg_color=BG_CARD,
                              border_color=ACCENT_BLUE, show="•" if pw else "")
            e.pack(padx=16, pady=(2,0), fill="x")
            return e

        self._gcs_bucket = gcs_entry("Bucket-Name", "mein-minecraft-backup")
        self._gcs_prefix = gcs_entry("Ordner-Präfix (optional)", "backups/")
        self._gcs_key    = gcs_entry("Pfad zur Service-Account-JSON", "/pfad/zu/key.json")

        key_row = ctk.CTkFrame(gcs, fg_color="transparent")
        key_row.pack(padx=16, pady=(4,0), fill="x")
        ctk.CTkButton(key_row, text="JSON auswählen…", fg_color=BG_CARD, text_color=TEXT_PRI,
                      height=32, command=lambda: self._gcs_key.delete(0,"end") or
                          self._gcs_key.insert(0, filedialog.askopenfilename(
                              filetypes=[("JSON","*.json")]) or "")
                      ).pack(side="left")

        self._gcs_lbl = ctk.CTkLabel(gcs, text="", text_color=TEXT_SEC,
                                      font=ctk.CTkFont("Segoe UI",11))
        self._gcs_lbl.pack(padx=16)

        def cloud_backup():
            bucket = self._gcs_bucket.get().strip()
            prefix = self._gcs_prefix.get().strip()
            key    = self._gcs_key.get().strip()
            if not bucket or not key:
                self._gcs_lbl.configure(text="Bitte Bucket und Key-Datei angeben.", text_color=ACCENT_RED)
                return
            self._gcs_lbl.configure(text="Upload läuft…", text_color=ACCENT)
            def do():
                try:
                    from google.cloud import storage
                    import os
                    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = key
                    client = storage.Client()
                    bkt    = client.bucket(bucket)
                    ts     = time.strftime("%Y%m%d_%H%M%S")
                    zip_path = APP_DIR / f"tmp_{ts}.zip"
                    shutil.make_archive(str(zip_path.with_suffix("")), "zip",
                                        str(SERVERS_DIR/self.server_name))
                    blob_name = f"{prefix}{self.server_name}_{ts}.zip"
                    bkt.blob(blob_name).upload_from_filename(str(zip_path))
                    zip_path.unlink(missing_ok=True)
                    self._gcs_lbl.configure(text=f"Hochgeladen: gs://{bucket}/{blob_name}", text_color=ACCENT)
                except ImportError:
                    self._gcs_lbl.configure(
                        text="Bitte installieren: pip install google-cloud-storage", text_color=ACCENT_RED)
                except Exception as e:
                    self._gcs_lbl.configure(text=f"Fehler: {e}", text_color=ACCENT_RED)
            threading.Thread(target=do, daemon=True).start()

        ctk.CTkButton(gcs, text="In Cloud hochladen", fg_color=ACCENT_BLUE, text_color="#fff",
                      font=ctk.CTkFont("Segoe UI",13,"bold"), height=42,
                      command=cloud_backup).pack(padx=16, pady=(4,14), fill="x")

        # Vorhandene Backups auflisten
        bkp_list = ctk.CTkFrame(scroll, fg_color=BG_PANEL, corner_radius=12)
        bkp_list.pack(fill="x", pady=6)
        ctk.CTkLabel(bkp_list, text="Vorhandene Backups", text_color=TEXT_PRI,
                     font=ctk.CTkFont("Segoe UI",13,"bold")).pack(padx=16, pady=(10,6), anchor="w")
        bkp_dir = APP_DIR/"backups"
        bkp_dir.mkdir(exist_ok=True)
        zips = sorted(bkp_dir.glob("*.zip"), reverse=True)
        if zips:
            for z in zips[:10]:
                row2 = ctk.CTkFrame(bkp_list, fg_color=BG_CARD, corner_radius=8)
                row2.pack(padx=16, pady=2, fill="x")
                size_mb = z.stat().st_size/1e6
                ctk.CTkLabel(row2, text=z.name, text_color=TEXT_PRI,
                             font=ctk.CTkFont("Segoe UI",11)).pack(side="left", padx=10, pady=6)
                ctk.CTkLabel(row2, text=f"{size_mb:.1f} MB", text_color=TEXT_SEC,
                             font=ctk.CTkFont("Segoe UI",10)).pack(side="right", padx=10)
        else:
            ctk.CTkLabel(bkp_list, text="Keine lokalen Backups gefunden.", text_color=TEXT_SEC,
                         font=ctk.CTkFont("Segoe UI",11)).pack(padx=16, pady=(0,10))

    # ── OPTIONEN ──────────────────────────────────────────────────────────────
    def _page_options(self):
        ctk.CTkLabel(self.main_frame, text="⚙ Optionen",
                     font=ctk.CTkFont("Segoe UI",18,"bold"), text_color=TEXT_PRI
                     ).pack(pady=(16,4), padx=20, anchor="w")
        if not self.server_name:
            ctk.CTkLabel(self.main_frame, text="Kein Server.", text_color=TEXT_SEC).pack(); return

        srv_dir   = SERVERS_DIR/self.server_name
        props_file= srv_dir/"server.properties"

        def read_props():
            if not props_file.exists(): return {}
            d = {}
            for line in props_file.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k,_,v = line.partition("=")
                    d[k.strip()] = v.strip()
            return d

        props   = read_props()
        scroll  = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=(0,8))
        widgets = {}

        def bool_row(key, label, default="false"):
            var = ctk.BooleanVar(value=props.get(key,default)=="true")
            f = ctk.CTkFrame(scroll, fg_color=BG_PANEL, corner_radius=10)
            f.pack(fill="x", pady=3)
            ctk.CTkLabel(f, text=label, text_color=TEXT_PRI,
                         font=ctk.CTkFont("Segoe UI",13)).pack(side="left", padx=14, pady=10)
            ctk.CTkSwitch(f, variable=var, text="", onvalue=True, offvalue=False,
                          progress_color=ACCENT, button_color=TEXT_PRI).pack(side="right", padx=14)
            widgets[key] = ("bool", var)

        def entry_row(key, label, default=""):
            val = props.get(key, default)
            f = ctk.CTkFrame(scroll, fg_color=BG_PANEL, corner_radius=10)
            f.pack(fill="x", pady=3)
            ctk.CTkLabel(f, text=label, text_color=TEXT_PRI,
                         font=ctk.CTkFont("Segoe UI",13)).pack(side="left", padx=14, pady=10)
            e = ctk.CTkEntry(f, width=200, fg_color=BG_CARD, border_color=ACCENT_BLUE)
            e.insert(0, val)
            e.pack(side="right", padx=14, pady=8)
            widgets[key] = ("entry", e)

        def drop_row(key, label, opts, default=""):
            var = ctk.StringVar(value=props.get(key,default))
            f = ctk.CTkFrame(scroll, fg_color=BG_PANEL, corner_radius=10)
            f.pack(fill="x", pady=3)
            ctk.CTkLabel(f, text=label, text_color=TEXT_PRI,
                         font=ctk.CTkFont("Segoe UI",13)).pack(side="left", padx=14, pady=10)
            ctk.CTkOptionMenu(f, variable=var, values=opts, fg_color=BG_CARD,
                               button_color=ACCENT_BLUE, width=160
                               ).pack(side="right", padx=14, pady=8)
            widgets[key] = ("str", var)

        bool_row("online-mode",          "Online-Mode  (aus = Cracked/Offline)", "true")
        bool_row("pvp",                  "PvP aktiviert", "true")
        bool_row("white-list",           "Whitelist aktiviert", "false")
        bool_row("enable-command-block", "Command Blocks", "false")
        bool_row("allow-flight",         "Fliegen erlaubt", "false")
        bool_row("spawn-protection",     "Spawn-Schutz", "true")
        bool_row("force-gamemode",       "Spielmodus erzwingen", "false")
        drop_row("difficulty",  "Schwierigkeitsgrad", ["peaceful","easy","normal","hard"], "normal")
        drop_row("gamemode",    "Standard-Spielmodus",
                 ["survival","creative","adventure","spectator"], "survival")
        entry_row("max-players",   "Max. Spieler", "20")
        entry_row("server-port",   "Port", "25565")
        entry_row("motd",          "Server-Beschreibung (MotD)", "A Minecraft Server")
        entry_row("view-distance", "Sichtweite (Chunks)", "10")
        entry_row("level-name",    "Weltname", "world")
        entry_row("level-seed",    "Welt-Seed (leer = zufällig)", "")
        entry_row("player-idle-timeout", "Idle-Timeout (Minuten, 0=aus)", "0")
        entry_row("resource-pack", "Ressourcenpaket URL", "")

        def save_opts():
            new = dict(props)
            for k,(typ,w) in widgets.items():
                new[k] = ("true" if w.get() else "false") if typ=="bool" else w.get()
            props_file.write_text("\n".join(f"{k}={v}" for k,v in new.items())+"\n")
            self.server_cfg["port"] = new.get("server-port","25565")
            self.server_cfg["motd"] = new.get("motd","")
            save_server_cfg(self.server_name, self.server_cfg)
            messagebox.showinfo("Gespeichert","server.properties gespeichert.\nServer neu starten zum Übernehmen.")

        ctk.CTkButton(self.main_frame, text="Speichern", fg_color=ACCENT, text_color="#000",
                      hover_color="#00a846", font=ctk.CTkFont("Segoe UI",14,"bold"),
                      height=46, command=save_opts).pack(padx=20, pady=(4,14), fill="x")

    # ── ZUGRIFF ───────────────────────────────────────────────────────────────
    def _page_access(self):
        ctk.CTkLabel(self.main_frame, text="🔑 Zugriff verwalten",
                     font=ctk.CTkFont("Segoe UI",18,"bold"), text_color=TEXT_PRI
                     ).pack(pady=(16,4), padx=20, anchor="w")
        ctk.CTkLabel(self.main_frame,
                     text="Gib anderen Benutzern Zugriff auf diesen Server und lege fest, was sie dürfen.",
                     text_color=TEXT_SEC, font=ctk.CTkFont("Segoe UI",12), wraplength=600
                     ).pack(padx=20, anchor="w", pady=(0,12))

        access_data = load_access()
        srv_access  = access_data.get(self.server_name or "__global__", {})
        all_users   = [u for u in load_users() if u != self.username]

        scroll = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=(0,8))

        if not all_users:
            ctk.CTkLabel(scroll,
                         text="Keine anderen Benutzer registriert.\nRegistriere weitere Konten, um hier Zugriff zu vergeben.",
                         text_color=TEXT_SEC, font=ctk.CTkFont("Segoe UI",12)).pack(pady=20)
        else:
            for user in all_users:
                user_perms = srv_access.get(user, {})
                card = ctk.CTkFrame(scroll, fg_color=BG_PANEL, corner_radius=12)
                card.pack(fill="x", pady=6)
                ctk.CTkLabel(card, text=f"👤  {user}",
                             font=ctk.CTkFont("Segoe UI",14,"bold"), text_color=TEXT_PRI
                             ).pack(padx=16, pady=(12,4), anchor="w")

                perm_vars = {}
                grid = ctk.CTkFrame(card, fg_color="transparent")
                grid.pack(padx=16, pady=(0,4), fill="x")
                for col_idx, (key, label) in enumerate(PERMISSIONS):
                    r, c = divmod(col_idx, 2)
                    pf = ctk.CTkFrame(grid, fg_color=BG_CARD, corner_radius=8)
                    pf.grid(row=r, column=c, padx=4, pady=3, sticky="ew")
                    grid.grid_columnconfigure(c, weight=1)
                    var = ctk.BooleanVar(value=user_perms.get(key, False))
                    ctk.CTkCheckBox(pf, text=label, variable=var,
                                    text_color=TEXT_PRI, font=ctk.CTkFont("Segoe UI",11),
                                    fg_color=ACCENT, hover_color="#00a846",
                                    checkmark_color="#000"
                                    ).pack(padx=10, pady=6, anchor="w")
                    perm_vars[key] = var

                def save_perms(u=user, pv=perm_vars):
                    ad = load_access()
                    sk = self.server_name or "__global__"
                    if sk not in ad: ad[sk] = {}
                    ad[sk][u] = {k: v.get() for k, v in pv.items()}
                    save_access(ad)
                    messagebox.showinfo("Gespeichert", f"Berechtigungen für {u} gespeichert.")

                def revoke(u=user):
                    ad = load_access()
                    sk = self.server_name or "__global__"
                    if sk in ad and u in ad[sk]:
                        del ad[sk][u]
                        save_access(ad)
                    self._show_page("access")

                btn_row = ctk.CTkFrame(card, fg_color="transparent")
                btn_row.pack(padx=16, pady=(4,12), fill="x")
                ctk.CTkButton(btn_row, text="Speichern", fg_color=ACCENT, text_color="#000",
                              height=34, width=120, command=save_perms).pack(side="left", padx=(0,8))
                ctk.CTkButton(btn_row, text="Zugriff entziehen", fg_color=ACCENT_RED,
                              text_color="#fff", height=34, width=140,
                              command=revoke).pack(side="left")

        # Benutzer einladen
        inv = ctk.CTkFrame(scroll, fg_color=BG_PANEL, corner_radius=10)
        inv.pack(fill="x", pady=8)
        ctk.CTkLabel(inv, text="Benutzer hinzufügen", text_color=TEXT_SEC,
                     font=ctk.CTkFont("Segoe UI",12,"bold")).pack(padx=14, pady=(10,4), anchor="w")
        ctk.CTkLabel(inv, text="Der Benutzer muss zuerst ein lokales Konto erstellen (Registrieren beim Login).",
                     text_color=TEXT_SEC, font=ctk.CTkFont("Segoe UI",10),
                     wraplength=480).pack(padx=14, anchor="w", pady=(0,10))

    # ── Hilfsmethode: Tabs ────────────────────────────────────────────────────
    def _make_tabs(self, parent, names):
        tabs = ctk.CTkTabview(parent, fg_color=BG_PANEL,
                               segmented_button_fg_color=BG_CARD,
                               segmented_button_selected_color=ACCENT,
                               segmented_button_selected_hover_color="#00a846",
                               segmented_button_unselected_color=BG_CARD)
        tabs.pack(fill="both", expand=True, padx=20, pady=(0,16))
        for n in names: tabs.add(n)
        return tabs

    # ── Schließen ─────────────────────────────────────────────────────────────
    def _on_close(self):
        if self.proc and self.proc.poll() is None:
            if not messagebox.askyesno("Server läuft",
                "Der Server läuft noch. Jetzt stoppen und beenden?"):
                return
            try:
                self.proc.stdin.write("stop\n"); self.proc.stdin.flush()
                self.proc.wait(timeout=10)
            except: self.proc.kill()
        self.destroy()

# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    LoginWindow().mainloop()
