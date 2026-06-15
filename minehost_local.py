"""
MineHost Local — Lokale Minecraft-Server-Verwaltung
Abhängigkeiten: pip install customtkinter psutil requests pillow
PyInstaller: pyinstaller --onefile --windowed --name MineHostLocal minehost_local.py
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import json, os, sys, hashlib, threading, subprocess, time, shutil, requests
import psutil
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import io

# ── Pfade ────────────────────────────────────────────────────────────────────
APP_DIR   = Path(os.getenv("APPDATA")) / "MineHostLocal"
USERS_DB  = APP_DIR / "users.json"
SERVERS_DIR = APP_DIR / "servers"
APP_DIR.mkdir(parents=True, exist_ok=True)
SERVERS_DIR.mkdir(exist_ok=True)

# ── Farb-Theme ────────────────────────────────────────────────────────────────
BG_DARK    = "#0f1117"
BG_PANEL   = "#1a1d27"
BG_CARD    = "#21263a"
ACCENT     = "#00c853"
ACCENT_RED = "#f44336"
ACCENT_BLUE= "#2979ff"
TEXT_PRI   = "#e8eaf6"
TEXT_SEC   = "#7986cb"
NAV_W      = 200

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ── Hilfsfunktionen ──────────────────────────────────────────────────────────
def hash_pw(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def load_users() -> dict:
    if USERS_DB.exists():
        return json.loads(USERS_DB.read_text())
    return {}

def save_users(data: dict):
    USERS_DB.write_text(json.dumps(data, indent=2))

def load_server_cfg(name: str) -> dict:
    p = SERVERS_DIR / name / "minehost.json"
    if p.exists():
        return json.loads(p.read_text())
    return {}

def save_server_cfg(name: str, cfg: dict):
    p = SERVERS_DIR / name
    p.mkdir(exist_ok=True)
    (p / "minehost.json").write_text(json.dumps(cfg, indent=2))

def list_servers() -> list[str]:
    return [d.name for d in SERVERS_DIR.iterdir() if d.is_dir()]

def make_logo_image(size=64) -> ctk.CTkImage:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, size-2, size-2], radius=14, fill="#21263a")
    block = size // 3
    colors = ["#5d4037","#4caf50","#388e3c","#8d6e63","#4caf50","#2e7d32",
              "#6d4c41","#33691e","#5d4037"]
    for i, c in enumerate(colors):
        r, col = divmod(i, 3)
        x0, y0 = 8 + col*block, 8 + r*block
        d.rectangle([x0, y0, x0+block-2, y0+block-2], fill=c)
    d.text((size//2-10, size-18), "MH", fill="#00c853")
    return ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))

# ── Paper & Vanilla Download-URLs ────────────────────────────────────────────
VANILLA_VERSIONS = {
    "1.21.4": "https://piston-data.mojang.com/v1/objects/4707d00eb834b446575d89a61a11b5d548d8c001/server.jar",
    "1.21.1": "https://piston-data.mojang.com/v1/objects/59353fb40c36d304f2035d51e7d6e6baa98dc05c/server.jar",
    "1.20.4": "https://piston-data.mojang.com/v1/objects/8dd1a28015f51b1803213892b50b7b4fc76e594d/server.jar",
    "1.20.1": "https://piston-data.mojang.com/v1/objects/84194a2f286ef7c14ed7ce0090dba59902951553/server.jar",
    "1.19.4": "https://piston-data.mojang.com/v1/objects/8f3112a1049751cc472ec13e397eade5336ca7ae/server.jar",
}

def get_paper_url(mc_version: str) -> str | None:
    try:
        r = requests.get(f"https://api.papermc.io/v2/projects/paper/versions/{mc_version}/builds", timeout=10)
        builds = r.json().get("builds", [])
        if not builds:
            return None
        latest = builds[-1]
        build_num = latest["build"]
        jar_name = latest["downloads"]["application"]["name"]
        return f"https://api.papermc.io/v2/projects/paper/versions/{mc_version}/builds/{build_num}/downloads/{jar_name}"
    except Exception:
        return None

# ══════════════════════════════════════════════════════════════════════════════
# LOGIN / REGISTER
# ══════════════════════════════════════════════════════════════════════════════
class LoginWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("MineHost Local — Login")
        self.geometry("440x560")
        self.resizable(False, False)
        self.configure(fg_color=BG_DARK)
        self._mode = "login"
        self._build()

    def _build(self):
        logo = make_logo_image(72)
        ctk.CTkLabel(self, image=logo, text="").pack(pady=(40,8))
        ctk.CTkLabel(self, text="MineHost Local", font=ctk.CTkFont("Segoe UI", 26, "bold"),
                     text_color=ACCENT).pack()
        ctk.CTkLabel(self, text="Dein lokaler Minecraft-Manager",
                     font=ctk.CTkFont("Segoe UI", 12), text_color=TEXT_SEC).pack(pady=(2,24))

        frame = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=16)
        frame.pack(padx=40, fill="x")

        self.tab = ctk.CTkSegmentedButton(frame, values=["Login","Registrieren"],
                                          command=self._switch_mode,
                                          fg_color=BG_CARD, selected_color=ACCENT,
                                          selected_hover_color="#00a846",
                                          unselected_color=BG_CARD,
                                          font=ctk.CTkFont("Segoe UI",13,"bold"))
        self.tab.set("Login")
        self.tab.pack(padx=20, pady=(20,16), fill="x")

        self.lbl_user = ctk.CTkLabel(frame, text="Benutzername", anchor="w",
                                      font=ctk.CTkFont("Segoe UI",12), text_color=TEXT_SEC)
        self.lbl_user.pack(padx=20, fill="x")
        self.entry_user = ctk.CTkEntry(frame, placeholder_text="z.B. Steve",
                                        fg_color=BG_CARD, border_color=ACCENT_BLUE,
                                        font=ctk.CTkFont("Segoe UI",13))
        self.entry_user.pack(padx=20, pady=(2,10), fill="x")

        self.lbl_pw = ctk.CTkLabel(frame, text="Passwort", anchor="w",
                                    font=ctk.CTkFont("Segoe UI",12), text_color=TEXT_SEC)
        self.lbl_pw.pack(padx=20, fill="x")
        self.entry_pw = ctk.CTkEntry(frame, placeholder_text="••••••••", show="•",
                                      fg_color=BG_CARD, border_color=ACCENT_BLUE,
                                      font=ctk.CTkFont("Segoe UI",13))
        self.entry_pw.pack(padx=20, pady=(2,10), fill="x")

        self.entry_email = ctk.CTkEntry(frame, placeholder_text="E-Mail (optional)",
                                         fg_color=BG_CARD, border_color=ACCENT_BLUE,
                                         font=ctk.CTkFont("Segoe UI",13))

        self.btn = ctk.CTkButton(frame, text="Einloggen", fg_color=ACCENT,
                                  hover_color="#00a846", text_color="#000",
                                  font=ctk.CTkFont("Segoe UI",14,"bold"),
                                  height=44, corner_radius=10,
                                  command=self._submit)
        self.btn.pack(padx=20, pady=(6,20), fill="x")

        self.lbl_err = ctk.CTkLabel(self, text="", text_color=ACCENT_RED,
                                     font=ctk.CTkFont("Segoe UI",12))
        self.lbl_err.pack()
        self.bind("<Return>", lambda e: self._submit())

    def _switch_mode(self, val):
        self._mode = "register" if val == "Registrieren" else "login"
        if self._mode == "register":
            self.entry_email.pack(in_=self.entry_pw.master, padx=20, pady=(2,10),
                                   fill="x", before=self.btn)
            self.btn.configure(text="Registrieren")
        else:
            self.entry_email.pack_forget()
            self.btn.configure(text="Einloggen")
        self.lbl_err.configure(text="")

    def _submit(self):
        user = self.entry_user.get().strip()
        pw   = self.entry_pw.get()
        if not user or not pw:
            self.lbl_err.configure(text="Bitte alle Felder ausfüllen.")
            return
        users = load_users()
        if self._mode == "login":
            if user not in users or users[user]["pw"] != hash_pw(pw):
                self.lbl_err.configure(text="Falscher Benutzername oder Passwort.")
                return
        else:
            if user in users:
                self.lbl_err.configure(text="Benutzername bereits vergeben.")
                return
            users[user] = {"pw": hash_pw(pw), "email": self.entry_email.get().strip()}
            save_users(users)
        self.destroy()
        app = MainApp(username=user)
        app.mainloop()

# ══════════════════════════════════════════════════════════════════════════════
# SETUP-ASSISTENT
# ══════════════════════════════════════════════════════════════════════════════
class SetupWizard(ctk.CTkToplevel):
    VERSIONS = list(VANILLA_VERSIONS.keys()) + ["1.21.4 (Paper)", "1.21.1 (Paper)",
                                                  "1.20.4 (Paper)", "1.20.1 (Paper)"]

    def __init__(self, master, on_done):
        super().__init__(master)
        self.title("Neuen Server erstellen")
        self.geometry("540x620")
        self.resizable(False, False)
        self.configure(fg_color=BG_DARK)
        self.on_done = on_done
        self._build()
        self.grab_set()

    def _build(self):
        ctk.CTkLabel(self, text="Server einrichten",
                     font=ctk.CTkFont("Segoe UI",22,"bold"), text_color=ACCENT).pack(pady=(28,4))
        ctk.CTkLabel(self, text="Der Assistent lädt automatisch die Server-JAR herunter.",
                     text_color=TEXT_SEC, font=ctk.CTkFont("Segoe UI",12)).pack(pady=(0,20))

        f = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=14)
        f.pack(padx=32, fill="x")

        def row(label, widget_fn):
            ctk.CTkLabel(f, text=label, anchor="w", text_color=TEXT_SEC,
                         font=ctk.CTkFont("Segoe UI",12)).pack(padx=18, fill="x", pady=(10,0))
            w = widget_fn(f)
            w.pack(padx=18, pady=(2,0), fill="x")
            return w

        self.e_name    = row("Server-Name", lambda p: ctk.CTkEntry(p, placeholder_text="Mein Server",
                              fg_color=BG_CARD, border_color=ACCENT_BLUE, font=ctk.CTkFont("Segoe UI",13)))
        self.e_motd    = row("Beschreibung (MotD)", lambda p: ctk.CTkEntry(p, placeholder_text="Ein epischer Server!",
                              fg_color=BG_CARD, border_color=ACCENT_BLUE, font=ctk.CTkFont("Segoe UI",13)))
        self.e_players = row("Max. Spieler", lambda p: ctk.CTkEntry(p, placeholder_text="20",
                              fg_color=BG_CARD, border_color=ACCENT_BLUE, font=ctk.CTkFont("Segoe UI",13)))
        self.e_port    = row("Port", lambda p: ctk.CTkEntry(p, placeholder_text="25565",
                              fg_color=BG_CARD, border_color=ACCENT_BLUE, font=ctk.CTkFont("Segoe UI",13)))

        ctk.CTkLabel(f, text="Minecraft-Version", anchor="w", text_color=TEXT_SEC,
                     font=ctk.CTkFont("Segoe UI",12)).pack(padx=18, fill="x", pady=(10,0))
        self.ver_var = ctk.StringVar(value=self.VERSIONS[0])
        self.e_ver = ctk.CTkOptionMenu(f, variable=self.ver_var, values=self.VERSIONS,
                                        fg_color=BG_CARD, button_color=ACCENT_BLUE,
                                        font=ctk.CTkFont("Segoe UI",13))
        self.e_ver.pack(padx=18, pady=(2,16), fill="x")

        self.prog_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.prog_frame.pack(padx=32, fill="x", pady=(16,0))
        self.progress = ctk.CTkProgressBar(self.prog_frame, fg_color=BG_CARD, progress_color=ACCENT)
        self.progress.set(0)
        self.lbl_status = ctk.CTkLabel(self.prog_frame, text="", text_color=TEXT_SEC,
                                        font=ctk.CTkFont("Segoe UI",11))

        ctk.CTkButton(self, text="Server erstellen & JAR herunterladen",
                      fg_color=ACCENT, hover_color="#00a846", text_color="#000",
                      font=ctk.CTkFont("Segoe UI",14,"bold"), height=46, corner_radius=10,
                      command=self._create).pack(padx=32, pady=20, fill="x")

    def _create(self):
        name    = self.e_name.get().strip() or "Mein Server"
        motd    = self.e_motd.get().strip() or "A Minecraft Server"
        players = self.e_players.get().strip() or "20"
        port    = self.e_port.get().strip() or "25565"
        ver_raw = self.ver_var.get()
        is_paper = "(Paper)" in ver_raw
        mc_ver  = ver_raw.replace(" (Paper)", "")

        safe_name = name.replace(" ","_")
        srv_dir = SERVERS_DIR / safe_name
        srv_dir.mkdir(exist_ok=True)

        self.progress.pack(fill="x")
        self.lbl_status.pack(pady=(4,0))

        def download():
            self.lbl_status.configure(text="Ermittle Download-URL…")
            if is_paper:
                url = get_paper_url(mc_ver)
                if not url:
                    self.lbl_status.configure(text="Paper-URL nicht gefunden, nutze Vanilla.")
                    url = VANILLA_VERSIONS.get(mc_ver)
                    is_p = False
                else:
                    is_p = True
            else:
                url = VANILLA_VERSIONS.get(mc_ver)
                is_p = False

            if not url:
                self.lbl_status.configure(text="Keine JAR-URL für diese Version gefunden.")
                return

            jar_path = srv_dir / "server.jar"
            self.lbl_status.configure(text=f"Lade server.jar ({mc_ver}) herunter…")
            try:
                r = requests.get(url, stream=True, timeout=60)
                total = int(r.headers.get("content-length", 0))
                done  = 0
                with open(jar_path, "wb") as fh:
                    for chunk in r.iter_content(8192):
                        fh.write(chunk)
                        done += len(chunk)
                        if total:
                            self.progress.set(done / total)
            except Exception as e:
                self.lbl_status.configure(text=f"Download fehlgeschlagen: {e}")
                return

            (srv_dir / "eula.txt").write_text("eula=true\n")

            props = (
                f"server-port={port}\n"
                f"max-players={players}\n"
                f"motd={motd}\n"
                "online-mode=true\n"
                "difficulty=normal\n"
                "pvp=true\n"
                "white-list=false\n"
                "gamemode=survival\n"
                "level-name=world\n"
            )
            (srv_dir / "server.properties").write_text(props)

            cfg = {
                "name": name, "mc_version": mc_ver, "type": "paper" if is_p else "vanilla",
                "port": port, "max_players": players, "motd": motd, "dir": str(srv_dir)
            }
            save_server_cfg(safe_name, cfg)

            self.lbl_status.configure(text="Fertig! Server bereit.")
            self.progress.set(1.0)
            time.sleep(1)
            self.destroy()
            self.on_done(safe_name)

        threading.Thread(target=download, daemon=True).start()

# ══════════════════════════════════════════════════════════════════════════════
# HAUPT-APP
# ══════════════════════════════════════════════════════════════════════════════
class MainApp(ctk.CTk):
    def __init__(self, username: str):
        super().__init__()
        self.username    = username
        self.server_name = None
        self.server_cfg  = {}
        self.proc: subprocess.Popen | None = None
        self._log_thread = None

        self.title("MineHost Local")
        self.geometry("1100x720")
        self.minsize(900, 600)
        self.configure(fg_color=BG_DARK)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._build_layout()
        self._load_first_server()

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, minsize=220)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=NAV_W, fg_color=BG_PANEL, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self._build_sidebar()

        # Main
        self.main_frame = ctk.CTkFrame(self, fg_color=BG_DARK, corner_radius=0)
        self.main_frame.grid(row=0, column=1, sticky="nsew")

        # Right panel
        self.right_panel = ctk.CTkFrame(self, width=220, fg_color=BG_PANEL, corner_radius=0)
        self.right_panel.grid(row=0, column=2, sticky="nsew")
        self.right_panel.grid_propagate(False)
        self._build_system_monitor()

    def _build_sidebar(self):
        logo = make_logo_image(44)
        top = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        top.pack(pady=(20,4), padx=12, fill="x")
        ctk.CTkLabel(top, image=logo, text="").pack(side="left", padx=(0,8))
        ctk.CTkLabel(top, text="MineHost\nLocal", font=ctk.CTkFont("Segoe UI",13,"bold"),
                     text_color=ACCENT, justify="left").pack(side="left")

        ctk.CTkLabel(self.sidebar, text=f"@ {self.username}",
                     text_color=TEXT_SEC, font=ctk.CTkFont("Segoe UI",11)).pack(pady=(0,16))

        self._nav_btns = {}
        pages = [("dashboard","  Dashboard"),("console","  Konsole"),
                 ("players","  Spieler"),("software","  Software"),
                 ("options","  Optionen"),("files","  Dateien/Mods")]
        for key, label in pages:
            btn = ctk.CTkButton(self.sidebar, text=label, anchor="w",
                                fg_color="transparent", hover_color=BG_CARD,
                                text_color=TEXT_PRI, font=ctk.CTkFont("Segoe UI",13),
                                height=38, corner_radius=8,
                                command=lambda k=key: self._show_page(k))
            btn.pack(padx=10, pady=2, fill="x")
            self._nav_btns[key] = btn

        ctk.CTkButton(self.sidebar, text="  + Server hinzufügen", anchor="w",
                      fg_color="transparent", hover_color=BG_CARD,
                      text_color=ACCENT, font=ctk.CTkFont("Segoe UI",12),
                      height=36, corner_radius=8, command=self._new_server).pack(
                      padx=10, pady=(24,2), fill="x", side="bottom")

    def _build_system_monitor(self):
        ctk.CTkLabel(self.right_panel, text="System-Monitor",
                     font=ctk.CTkFont("Segoe UI",13,"bold"), text_color=TEXT_PRI).pack(
                     pady=(20,12), padx=16)

        def stat_card(label):
            c = ctk.CTkFrame(self.right_panel, fg_color=BG_CARD, corner_radius=10)
            c.pack(padx=16, pady=6, fill="x")
            ctk.CTkLabel(c, text=label, text_color=TEXT_SEC,
                         font=ctk.CTkFont("Segoe UI",11)).pack(padx=12, pady=(8,0), anchor="w")
            bar = ctk.CTkProgressBar(c, fg_color=BG_PANEL, progress_color=ACCENT_BLUE)
            bar.set(0)
            bar.pack(padx=12, pady=(4,2), fill="x")
            lbl = ctk.CTkLabel(c, text="0%", text_color=TEXT_PRI,
                               font=ctk.CTkFont("Segoe UI",12,"bold"))
            lbl.pack(padx=12, pady=(0,8), anchor="w")
            return bar, lbl

        self.cpu_bar, self.cpu_lbl = stat_card("CPU-Auslastung")
        self.ram_bar, self.ram_lbl = stat_card("RAM-Auslastung")

        self.ram_detail = ctk.CTkLabel(self.right_panel, text="", text_color=TEXT_SEC,
                                        font=ctk.CTkFont("Segoe UI",10))
        self.ram_detail.pack(padx=16, anchor="w")

        ctk.CTkLabel(self.right_panel, text="Server-Info",
                     font=ctk.CTkFont("Segoe UI",13,"bold"), text_color=TEXT_PRI).pack(
                     pady=(20,8), padx=16)
        self.srv_ip_lbl = ctk.CTkLabel(self.right_panel, text="IP: localhost",
                                        text_color=ACCENT, font=ctk.CTkFont("Segoe UI",12,"bold"))
        self.srv_ip_lbl.pack(padx=16, anchor="w")
        self.srv_port_lbl = ctk.CTkLabel(self.right_panel, text="Port: —",
                                          text_color=TEXT_SEC, font=ctk.CTkFont("Segoe UI",11))
        self.srv_port_lbl.pack(padx=16, anchor="w")
        self.srv_ver_lbl  = ctk.CTkLabel(self.right_panel, text="Version: —",
                                          text_color=TEXT_SEC, font=ctk.CTkFont("Segoe UI",11))
        self.srv_ver_lbl.pack(padx=16, anchor="w")
        self.srv_type_lbl = ctk.CTkLabel(self.right_panel, text="Typ: —",
                                          text_color=TEXT_SEC, font=ctk.CTkFont("Segoe UI",11))
        self.srv_type_lbl.pack(padx=16, anchor="w")

        self._update_monitor()

    def _update_monitor(self):
        cpu = psutil.cpu_percent()
        ram = psutil.virtual_memory()
        self.cpu_bar.set(cpu / 100)
        self.cpu_lbl.configure(text=f"{cpu:.1f}%")
        self.ram_bar.set(ram.percent / 100)
        self.ram_lbl.configure(text=f"{ram.percent:.1f}%")
        used_gb = ram.used / 1e9
        total_gb = ram.total / 1e9
        self.ram_detail.configure(text=f"{used_gb:.1f} GB / {total_gb:.1f} GB")
        self.after(2000, self._update_monitor)

    # ── Pages ─────────────────────────────────────────────────────────────────
    def _clear_main(self):
        for w in self.main_frame.winfo_children():
            w.destroy()

    def _show_page(self, key: str):
        for k, b in self._nav_btns.items():
            b.configure(fg_color=ACCENT if k == key else "transparent",
                        text_color="#000" if k == key else TEXT_PRI)
        self._clear_main()
        getattr(self, f"_page_{key}")()

    def _load_first_server(self):
        servers = list_servers()
        if servers:
            self._select_server(servers[0])
        else:
            self._show_page("dashboard")

    def _select_server(self, name: str):
        self.server_name = name
        self.server_cfg  = load_server_cfg(name)
        self.srv_port_lbl.configure(text=f"Port: {self.server_cfg.get('port','25565')}")
        self.srv_ver_lbl.configure(text=f"Version: {self.server_cfg.get('mc_version','?')}")
        self.srv_type_lbl.configure(text=f"Typ: {self.server_cfg.get('type','vanilla').capitalize()}")
        self._show_page("dashboard")

    # ── Dashboard ─────────────────────────────────────────────────────────────
    def _page_dashboard(self):
        if not self.server_name:
            ctk.CTkLabel(self.main_frame, text="Kein Server vorhanden.",
                         font=ctk.CTkFont("Segoe UI",16), text_color=TEXT_SEC).pack(expand=True)
            ctk.CTkButton(self.main_frame, text="+ Server erstellen",
                          fg_color=ACCENT, text_color="#000", hover_color="#00a846",
                          font=ctk.CTkFont("Segoe UI",14,"bold"), height=48,
                          command=self._new_server).pack(pady=12)
            return

        f = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        f.pack(expand=True)

        name = self.server_cfg.get("name", self.server_name)
        ctk.CTkLabel(f, text=name, font=ctk.CTkFont("Segoe UI",28,"bold"),
                     text_color=TEXT_PRI).pack(pady=(0,6))

        is_on = self.proc is not None and self.proc.poll() is None
        status_color = ACCENT if is_on else ACCENT_RED
        status_text  = "Online" if is_on else "Offline"
        self.status_dot = ctk.CTkLabel(f, text=f"● {status_text}",
                                        font=ctk.CTkFont("Segoe UI",18,"bold"),
                                        text_color=status_color)
        self.status_dot.pack(pady=(0,24))

        btn_color = ACCENT_RED if is_on else ACCENT
        btn_text  = "STOPP" if is_on else "START"
        self.start_btn = ctk.CTkButton(f, text=btn_text, width=200, height=64,
                                        fg_color=btn_color, hover_color="#00a846",
                                        text_color="#000", font=ctk.CTkFont("Segoe UI",22,"bold"),
                                        corner_radius=14,
                                        command=self._toggle_server)
        self.start_btn.pack(pady=8)

        ctk.CTkLabel(f, text="localhost / 127.0.0.1",
                     font=ctk.CTkFont("Segoe UI",14), text_color=ACCENT).pack(pady=(16,2))
        ctk.CTkLabel(f, text=f"Port: {self.server_cfg.get('port','25565')}",
                     font=ctk.CTkFont("Segoe UI",12), text_color=TEXT_SEC).pack()

        if list_servers():
            ctk.CTkLabel(f, text="Server wechseln:", text_color=TEXT_SEC,
                         font=ctk.CTkFont("Segoe UI",11)).pack(pady=(20,2))
            srv_var = ctk.StringVar(value=self.server_name)
            ctk.CTkOptionMenu(f, variable=srv_var, values=list_servers(),
                              fg_color=BG_CARD, button_color=ACCENT_BLUE,
                              command=self._select_server).pack()

    def _toggle_server(self):
        if self.proc and self.proc.poll() is None:
            self._stop_server()
        else:
            self._start_server()

    def _start_server(self):
        if not self.server_name:
            return
        srv_dir = Path(self.server_cfg.get("dir", str(SERVERS_DIR / self.server_name)))
        jar = srv_dir / "server.jar"
        if not jar.exists():
            messagebox.showerror("Fehler","server.jar nicht gefunden. Bitte Server neu erstellen.")
            return
        try:
            self.proc = subprocess.Popen(
                ["java", "-Xmx2G", "-Xms512M", "-jar", "server.jar", "--nogui"],
                cwd=str(srv_dir),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
        except FileNotFoundError:
            messagebox.showerror("Java fehlt",
                "Java wurde nicht gefunden.\nBitte Java installieren:\nhttps://adoptium.net")
            return
        self._start_log_reader()
        self._show_page("dashboard")

    def _stop_server(self):
        if self.proc:
            try:
                self.proc.stdin.write("stop\n")
                self.proc.stdin.flush()
                self.proc.wait(timeout=15)
            except Exception:
                self.proc.kill()
            self.proc = None
        self._show_page("dashboard")

    def _start_log_reader(self):
        def read():
            for line in self.proc.stdout:
                self._append_console(line)
        self._log_thread = threading.Thread(target=read, daemon=True)
        self._log_thread.start()

    def _append_console(self, text: str):
        if hasattr(self, "_console_box"):
            self._console_box.configure(state="normal")
            self._console_box.insert("end", text)
            self._console_box.see("end")
            self._console_box.configure(state="disabled")

    # ── Konsole ───────────────────────────────────────────────────────────────
    def _page_console(self):
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.main_frame, text="Konsole",
                     font=ctk.CTkFont("Segoe UI",18,"bold"), text_color=TEXT_PRI
                     ).grid(row=0, column=0, sticky="w", padx=20, pady=(16,4))

        self._console_box = ctk.CTkTextbox(self.main_frame, fg_color=BG_CARD,
                                            text_color="#a5d6a7",
                                            font=ctk.CTkFont("Consolas",11), state="disabled")
        self._console_box.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0,8))
        self.main_frame.grid_rowconfigure(1, weight=1)

        inp_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        inp_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0,16))
        inp_frame.grid_columnconfigure(0, weight=1)

        self._cmd_entry = ctk.CTkEntry(inp_frame, placeholder_text="Befehl eingeben (z.B. op Steve)…",
                                        fg_color=BG_CARD, border_color=ACCENT_BLUE,
                                        font=ctk.CTkFont("Consolas",12))
        self._cmd_entry.grid(row=0, column=0, sticky="ew", padx=(0,8))
        self._cmd_entry.bind("<Return>", lambda e: self._send_cmd())

        ctk.CTkButton(inp_frame, text="Senden", fg_color=ACCENT_BLUE, text_color="#fff",
                      width=90, command=self._send_cmd).grid(row=0, column=1)

    def _send_cmd(self):
        if not hasattr(self, "_cmd_entry"):
            return
        cmd = self._cmd_entry.get().strip()
        if not cmd:
            return
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write(cmd + "\n")
                self.proc.stdin.flush()
                self._append_console(f"> {cmd}\n")
            except Exception as e:
                self._append_console(f"[Fehler] {e}\n")
        else:
            self._append_console("[Server nicht gestartet]\n")
        self._cmd_entry.delete(0, "end")

    # ── Spieler ───────────────────────────────────────────────────────────────
    def _page_players(self):
        ctk.CTkLabel(self.main_frame, text="Spieler verwalten",
                     font=ctk.CTkFont("Segoe UI",18,"bold"), text_color=TEXT_PRI
                     ).pack(pady=(16,12), padx=20, anchor="w")

        tabs = ctk.CTkTabview(self.main_frame, fg_color=BG_PANEL,
                               segmented_button_fg_color=BG_CARD,
                               segmented_button_selected_color=ACCENT,
                               segmented_button_selected_hover_color="#00a846")
        tabs.pack(fill="both", expand=True, padx=20, pady=(0,16))
        tabs.add("OP-Liste")
        tabs.add("Whitelist")
        tabs.add("Gebannte Spieler")

        for tab_name, file_name in [("OP-Liste","ops.json"),
                                     ("Whitelist","whitelist.json"),
                                     ("Gebannte Spieler","banned-players.json")]:
            tab = tabs.tab(tab_name)
            tab.grid_columnconfigure(0, weight=1)
            tab.grid_rowconfigure(0, weight=1)

            srv_dir = SERVERS_DIR / (self.server_name or "")
            fp = srv_dir / file_name
            players = []
            if fp.exists():
                try:
                    data = json.loads(fp.read_text())
                    players = [p.get("name","?") for p in data]
                except Exception:
                    players = []

            box = ctk.CTkTextbox(tab, fg_color=BG_CARD, text_color=TEXT_PRI,
                                  font=ctk.CTkFont("Segoe UI",13))
            box.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0,8))
            box.insert("end", "\n".join(players) or "(Leer)")
            box.configure(state="disabled")

            entry = ctk.CTkEntry(tab, placeholder_text="Spielername…",
                                  fg_color=BG_CARD, border_color=ACCENT_BLUE)
            entry.grid(row=1, column=0, sticky="ew", padx=(0,8), pady=(0,4))

            def _add(e=entry, b=box, fn=file_name, sn=self.server_name):
                name = e.get().strip()
                if not name or not sn:
                    return
                fp2 = SERVERS_DIR / sn / fn
                data = []
                if fp2.exists():
                    try: data = json.loads(fp2.read_text())
                    except: pass
                if not any(p.get("name") == name for p in data):
                    data.append({"uuid":"","name":name})
                    fp2.write_text(json.dumps(data, indent=2))
                b.configure(state="normal")
                b.insert("end", f"\n{name}")
                b.configure(state="disabled")
                if self.proc and self.proc.poll() is None:
                    cmd = {"OP-Liste":"op","Whitelist":"whitelist add","Gebannte Spieler":"ban"}
                    prefix = cmd.get(tab_name,"")
                    if prefix:
                        try:
                            self.proc.stdin.write(f"{prefix} {name}\n")
                            self.proc.stdin.flush()
                        except: pass
                e.delete(0,"end")

            ctk.CTkButton(tab, text="Hinzufügen", fg_color=ACCENT, text_color="#000",
                          width=110, command=_add).grid(row=1, column=1, pady=(0,4))

    # ── Software ──────────────────────────────────────────────────────────────
    def _page_software(self):
        ctk.CTkLabel(self.main_frame, text="Software",
                     font=ctk.CTkFont("Segoe UI",18,"bold"), text_color=TEXT_PRI
                     ).pack(pady=(16,4), padx=20, anchor="w")
        ctk.CTkLabel(self.main_frame, text="Wechsle zwischen Vanilla und Paper (erfordert Neustart).",
                     text_color=TEXT_SEC, font=ctk.CTkFont("Segoe UI",12)
                     ).pack(padx=20, anchor="w", pady=(0,16))

        if not self.server_name:
            ctk.CTkLabel(self.main_frame, text="Kein Server ausgewählt.", text_color=TEXT_SEC).pack()
            return

        cur = self.server_cfg.get("type","vanilla")
        sw_var = ctk.StringVar(value=cur.capitalize())
        f = ctk.CTkFrame(self.main_frame, fg_color=BG_PANEL, corner_radius=12)
        f.pack(padx=20, pady=8, fill="x")

        ctk.CTkLabel(f, text="Server-Typ:", text_color=TEXT_SEC,
                     font=ctk.CTkFont("Segoe UI",13)).pack(padx=16, pady=(12,4), anchor="w")
        ctk.CTkSegmentedButton(f, values=["Vanilla","Paper"], variable=sw_var,
                                fg_color=BG_CARD, selected_color=ACCENT,
                                selected_hover_color="#00a846",
                                font=ctk.CTkFont("Segoe UI",13,"bold")
                                ).pack(padx=16, pady=(0,8), fill="x")

        ctk.CTkLabel(f, text="Minecraft-Version:", text_color=TEXT_SEC,
                     font=ctk.CTkFont("Segoe UI",13)).pack(padx=16, pady=(8,4), anchor="w")
        ver_var = ctk.StringVar(value=self.server_cfg.get("mc_version","1.21.4"))
        ctk.CTkOptionMenu(f, variable=ver_var,
                           values=list(VANILLA_VERSIONS.keys()),
                           fg_color=BG_CARD, button_color=ACCENT_BLUE,
                           font=ctk.CTkFont("Segoe UI",12)).pack(padx=16, pady=(0,12), fill="x")

        def apply_sw():
            new_type = sw_var.get().lower()
            new_ver  = ver_var.get()
            self.server_cfg["type"] = new_type
            self.server_cfg["mc_version"] = new_ver
            save_server_cfg(self.server_name, self.server_cfg)
            srv_dir = SERVERS_DIR / self.server_name
            jar = srv_dir / "server.jar"
            if jar.exists():
                jar.rename(srv_dir / "server.jar.bak")
            lbl.configure(text="Lade neue JAR…", text_color=ACCENT)

            def dl():
                if new_type == "paper":
                    url = get_paper_url(new_ver) or VANILLA_VERSIONS.get(new_ver)
                else:
                    url = VANILLA_VERSIONS.get(new_ver)
                if url:
                    r = requests.get(url, stream=True, timeout=60)
                    with open(str(srv_dir / "server.jar"), "wb") as fh:
                        for chunk in r.iter_content(8192):
                            fh.write(chunk)
                lbl.configure(text="Fertig! Bitte Server neu starten.", text_color=ACCENT)
            threading.Thread(target=dl, daemon=True).start()

        ctk.CTkButton(f, text="Übernehmen & JAR aktualisieren",
                      fg_color=ACCENT_BLUE, text_color="#fff",
                      font=ctk.CTkFont("Segoe UI",13,"bold"), height=40,
                      command=apply_sw).pack(padx=16, pady=(4,8), fill="x")
        lbl = ctk.CTkLabel(f, text="", text_color=TEXT_SEC, font=ctk.CTkFont("Segoe UI",11))
        lbl.pack(padx=16, pady=(0,12))

    # ── Optionen ──────────────────────────────────────────────────────────────
    def _page_options(self):
        ctk.CTkLabel(self.main_frame, text="Server-Optionen",
                     font=ctk.CTkFont("Segoe UI",18,"bold"), text_color=TEXT_PRI
                     ).pack(pady=(16,4), padx=20, anchor="w")

        if not self.server_name:
            ctk.CTkLabel(self.main_frame, text="Kein Server ausgewählt.", text_color=TEXT_SEC).pack()
            return

        srv_dir = SERVERS_DIR / self.server_name
        props_file = srv_dir / "server.properties"

        def read_props():
            if not props_file.exists():
                return {}
            d = {}
            for line in props_file.read_text().splitlines():
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    d[k.strip()] = v.strip()
            return d

        def write_props(d: dict):
            lines = []
            for k, v in d.items():
                lines.append(f"{k}={v}")
            props_file.write_text("\n".join(lines) + "\n")

        props = read_props()

        scroll = ctk.CTkScrollableFrame(self.main_frame, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=20, pady=(0,12))

        widgets = {}

        def bool_row(key, label, default="false"):
            val = props.get(key, default) == "true"
            var = ctk.BooleanVar(value=val)
            f = ctk.CTkFrame(scroll, fg_color=BG_PANEL, corner_radius=10)
            f.pack(fill="x", pady=4)
            ctk.CTkLabel(f, text=label, text_color=TEXT_PRI,
                         font=ctk.CTkFont("Segoe UI",13)).pack(side="left", padx=14, pady=10)
            ctk.CTkSwitch(f, variable=var, text="", onvalue=True, offvalue=False,
                          progress_color=ACCENT, button_color=TEXT_PRI).pack(side="right", padx=14)
            widgets[key] = ("bool", var)

        def entry_row(key, label, default=""):
            val = props.get(key, default)
            f = ctk.CTkFrame(scroll, fg_color=BG_PANEL, corner_radius=10)
            f.pack(fill="x", pady=4)
            ctk.CTkLabel(f, text=label, text_color=TEXT_PRI,
                         font=ctk.CTkFont("Segoe UI",13)).pack(side="left", padx=14, pady=10)
            e = ctk.CTkEntry(f, width=180, fg_color=BG_CARD, border_color=ACCENT_BLUE)
            e.insert(0, val)
            e.pack(side="right", padx=14, pady=8)
            widgets[key] = ("entry", e)

        def dropdown_row(key, label, options, default=""):
            val = props.get(key, default)
            var = ctk.StringVar(value=val)
            f = ctk.CTkFrame(scroll, fg_color=BG_PANEL, corner_radius=10)
            f.pack(fill="x", pady=4)
            ctk.CTkLabel(f, text=label, text_color=TEXT_PRI,
                         font=ctk.CTkFont("Segoe UI",13)).pack(side="left", padx=14, pady=10)
            ctk.CTkOptionMenu(f, variable=var, values=options, fg_color=BG_CARD,
                               button_color=ACCENT_BLUE, width=160).pack(side="right", padx=14, pady=8)
            widgets[key] = ("str", var)

        bool_row("online-mode", "Online-Mode (deaktivieren = Cracked)")
        bool_row("pvp", "PvP aktiviert", "true")
        bool_row("white-list", "Whitelist aktiviert", "false")
        bool_row("enable-command-block", "Command Blocks", "false")
        dropdown_row("difficulty", "Schwierigkeitsgrad",
                     ["peaceful","easy","normal","hard"], "normal")
        dropdown_row("gamemode", "Standard-Spielmodus",
                     ["survival","creative","adventure","spectator"], "survival")
        entry_row("max-players", "Max. Spieler", "20")
        entry_row("server-port", "Port", "25565")
        entry_row("motd", "Serverbeschreibung (MotD)", "A Minecraft Server")
        entry_row("view-distance", "Sichtweite (Chunks)", "10")
        entry_row("level-name", "Weltname", "world")

        def save_opts():
            new_props = dict(props)
            for k, (typ, w) in widgets.items():
                if typ == "bool":
                    new_props[k] = "true" if w.get() else "false"
                elif typ == "entry":
                    new_props[k] = w.get()
                else:
                    new_props[k] = w.get()
            write_props(new_props)
            self.server_cfg["port"] = new_props.get("server-port","25565")
            self.server_cfg["motd"] = new_props.get("motd","")
            save_server_cfg(self.server_name, self.server_cfg)
            messagebox.showinfo("Gespeichert","server.properties aktualisiert.\nServer neu starten, um Änderungen zu übernehmen.")

        ctk.CTkButton(self.main_frame, text="Speichern", fg_color=ACCENT, text_color="#000",
                      hover_color="#00a846", font=ctk.CTkFont("Segoe UI",14,"bold"),
                      height=44, command=save_opts).pack(padx=20, pady=(4,16), fill="x")

    # ── Dateien / Mods ────────────────────────────────────────────────────────
    def _page_files(self):
        ctk.CTkLabel(self.main_frame, text="Dateien & Plugins/Mods",
                     font=ctk.CTkFont("Segoe UI",18,"bold"), text_color=TEXT_PRI
                     ).pack(pady=(16,4), padx=20, anchor="w")

        if not self.server_name:
            ctk.CTkLabel(self.main_frame, text="Kein Server ausgewählt.", text_color=TEXT_SEC).pack()
            return

        srv_dir = SERVERS_DIR / self.server_name
        tabs = ctk.CTkTabview(self.main_frame, fg_color=BG_PANEL,
                               segmented_button_fg_color=BG_CARD,
                               segmented_button_selected_color=ACCENT,
                               segmented_button_selected_hover_color="#00a846")
        tabs.pack(fill="both", expand=True, padx=20, pady=(0,16))
        tabs.add("Plugins")
        tabs.add("Mods")
        tabs.add("Resourcepacks")
        tabs.add("Alle Dateien")

        def folder_tab(tab, folder_name):
            folder = srv_dir / folder_name
            folder.mkdir(exist_ok=True)
            t = tabs.tab(tab)
            t.grid_columnconfigure(0, weight=1)
            t.grid_rowconfigure(0, weight=1)

            box = ctk.CTkTextbox(t, fg_color=BG_CARD, text_color=TEXT_PRI,
                                  font=ctk.CTkFont("Segoe UI",12))
            box.grid(row=0, column=0, columnspan=2, sticky="nsew", pady=(0,8))

            def refresh():
                box.configure(state="normal")
                box.delete("1.0","end")
                files = list(folder.iterdir())
                if files:
                    for f in files:
                        box.insert("end", f"{'[D]' if f.is_dir() else '[F]'} {f.name}\n")
                else:
                    box.insert("end","(Leer)")
                box.configure(state="disabled")

            refresh()

            def add_file():
                paths = filedialog.askopenfilenames(title=f"Datei(en) in {folder_name} kopieren")
                for src in paths:
                    shutil.copy(src, folder / Path(src).name)
                refresh()

            ctk.CTkButton(t, text="+ Datei hinzufügen", fg_color=ACCENT_BLUE, text_color="#fff",
                          height=36, command=add_file).grid(row=1, column=0, sticky="ew",
                          padx=(0,8), pady=(0,4))
            ctk.CTkButton(t, text="Ordner öffnen", fg_color=BG_CARD, text_color=TEXT_PRI,
                          height=36, command=lambda: os.startfile(str(folder))
                          ).grid(row=1, column=1, pady=(0,4))

        def all_files_tab():
            t = tabs.tab("Alle Dateien")
            t.grid_columnconfigure(0, weight=1)
            t.grid_rowconfigure(0, weight=1)
            box = ctk.CTkTextbox(t, fg_color=BG_CARD, text_color=TEXT_PRI,
                                  font=ctk.CTkFont("Consolas",11))
            box.grid(row=0, column=0, sticky="nsew", pady=(0,8))
            box.configure(state="normal")
            try:
                for item in sorted(srv_dir.iterdir()):
                    prefix = "[D] " if item.is_dir() else "[F] "
                    box.insert("end", prefix + item.name + "\n")
            except Exception as e:
                box.insert("end", str(e))
            box.configure(state="disabled")
            ctk.CTkButton(t, text="Explorer öffnen", fg_color=BG_CARD, text_color=TEXT_PRI,
                          height=36, command=lambda: os.startfile(str(srv_dir))
                          ).grid(row=1, column=0, sticky="ew")

        folder_tab("Plugins","plugins")
        folder_tab("Mods","mods")
        folder_tab("Resourcepacks","resourcepacks")
        all_files_tab()

    # ── Neuer Server ──────────────────────────────────────────────────────────
    def _new_server(self):
        SetupWizard(self, on_done=self._select_server)

    # ── Schließen ─────────────────────────────────────────────────────────────
    def _on_close(self):
        if self.proc and self.proc.poll() is None:
            if messagebox.askyesno("Server läuft noch",
                "Der Minecraft-Server läuft noch.\nJetzt stoppen und beenden?"):
                self._stop_server()
            else:
                return
        self.destroy()


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app = LoginWindow()
    app.mainloop()
