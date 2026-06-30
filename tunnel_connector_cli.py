#!/usr/bin/env python3
"""
Mine-Host Tunnel Agent v3.0
===========================
Agenten-Teil (PC-Seite) des Minecraft-Tunnel-Systems.
Baut eine persistente Steuerverbindung zum Gateway auf und
multiplext eingehende Spieler-Verbindungen über WebSocket-Datenkanäle.

Gateway-Teil (Server/VPS-Seite) → liegt beim Cloud-Dienst, wird NICHT hier verwaltet.

Ablauf:
  1. Steuerkanal: Agent → Gateway (persistente WS-Verbindung)
  2. Gateway sendet "connect" → Agent öffnet TCP zu lokalem MC + Datenkanal-WS
  3. Daten werden bidirektional gebrückt: TCP(MC) ↔ WS-Datenkanal ↔ Gateway ↔ Spieler
  4. Heartbeat alle 30s, Auto-Reconnect mit Exponential Backoff
"""
import sys, asyncio, json, socket, argparse, urllib.request, time, io
from collections import defaultdict

# UTF-8 erzwingen (Windows cp1252 kann sonst Unicode-Sonderzeichen nicht ausgeben)
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)
except Exception:
    pass

MINEHOST_API = "https://minecraft-tunnel-system-190266430698.europe-west3.run.app"

# ── ANSI Farben ─────────────────────────────────────────────────────────────
G  = "\033[32m"; Y  = "\033[33m"; R  = "\033[31m"
B  = "\033[34m"; C  = "\033[36m"; W  = "\033[37m"
DIM= "\033[2m";  RST= "\033[0m";  BLD= "\033[1m"

def _ts():
    return time.strftime("%H:%M:%S")

def ok(msg):   print(f"{G}[{_ts()}][OK] {msg}{RST}", flush=True)
def info(msg): print(f"{C}[{_ts()}][..] {msg}{RST}", flush=True)
def warn(msg): print(f"{Y}[{_ts()}][!!] {msg}{RST}", flush=True)
def err(msg):  print(f"{R}[{_ts()}][XX] {msg}{RST}", flush=True)
def data(msg): print(f"{B}[{_ts()}][>>] {msg}{RST}", flush=True)

# ── Verbindungs-Tracking ─────────────────────────────────────────────────────
class AgentStats:
    def __init__(self):
        self.total_connections = 0
        self.active_bridges    = 0
        self.bytes_in          = 0
        self.bytes_out         = 0
        self.start_time        = time.time()

    def uptime(self):
        s = int(time.time() - self.start_time)
        return f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"

    def summary(self):
        mb_in  = self.bytes_in  / (1024*1024)
        mb_out = self.bytes_out / (1024*1024)
        return (f"Laufzeit: {self.uptime()} | Verbindungen: {self.total_connections} "
                f"| Aktiv: {self.active_bridges} | ↓{mb_in:.1f}MB ↑{mb_out:.1f}MB")

STATS = AgentStats()

# ── API-Zugriff ──────────────────────────────────────────────────────────────
def api_get(path):
    req = urllib.request.Request(
        f"{MINEHOST_API}{path}",
        headers={"User-Agent": "MineHostAgent/3.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def api_post(path, body):
    data_bytes = json.dumps(body).encode()
    req = urllib.request.Request(
        f"{MINEHOST_API}{path}", data=data_bytes, method="POST",
        headers={"User-Agent": "MineHostAgent/3.0",
                 "Content-Type": "application/json",
                 "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def fetch_tunnel(tunnel_id):
    tunnels = api_get("/api/tunnels")
    for t in (tunnels if isinstance(tunnels, list) else []):
        if t.get("id") == tunnel_id:
            return t
    return None

def recreate_tunnel(old_tid, mc_host, mc_port):
    """Legt automatisch einen neuen Tunnel an wenn der alte gelöscht wurde."""
    import re as _re
    # Kompatiblen bestehenden Tunnel suchen
    try:
        for t in (api_get("/api/tunnels") or []):
            if t.get("targetPort") == mc_port and t.get("targetHost") == mc_host:
                info(f"Bestehender Tunnel gefunden: {t['id']}")
                return t["id"], t.get("subdomain","")
    except Exception: pass
    # Neuen anlegen
    sub = _re.sub(r'[^a-z0-9-]', '-', f"auto-{old_tid[:8]}")
    try:
        resp = api_post("/api/tunnels", {
            "name": f"Auto-Tunnel ({mc_host}:{mc_port})",
            "subdomain": sub, "targetHost": mc_host, "targetPort": mc_port,
            "type": "java", "playersMax": 20
        })
        new_id  = resp.get("id","")
        new_sub = resp.get("subdomain", sub)
        ok(f"Neuer Tunnel: {new_sub}.minehost-local.uk  (ID: {new_id})")
        return new_id, new_sub
    except Exception as ex:
        err(f"Tunnel-Erstellung fehlgeschlagen: {ex}")
        return None, None

# ── Minecraft Server List Ping ───────────────────────────────────────────────
def mc_ping(host, port, timeout=3):
    try:
        with socket.create_connection((host, port), timeout=timeout) as s:
            def vi(n):
                buf=b""
                while True:
                    b=n&0x7F; n>>=7
                    if n: b|=0x80
                    buf+=bytes([b])
                    if not n: break
                return buf
            he = host.encode()
            hs = vi(0x00)+vi(0)+vi(len(he))+he+port.to_bytes(2,"big")+vi(1)
            s.sendall(vi(len(hs))+hs+b"\x01\x00")
            def rv(sk):
                val=sh=0
                while True:
                    b=sk.recv(1)
                    if not b: return val
                    byte=b[0]; val|=(byte&0x7F)<<sh
                    if not(byte&0x80): return val
                    sh+=7
            rv(s); rv(s); slen=rv(s)
            raw=b""
            while len(raw)<slen:
                c=s.recv(slen-len(raw))
                if not c: break
                raw+=c
            st=json.loads(raw.decode())
            pl=st.get("players",{}); desc=st.get("description",{})
            motd=desc if isinstance(desc,str) else desc.get("text","")
            return {"online":True,"playersOnline":pl.get("online",0),
                    "playersMax":pl.get("max",0),"motd":motd}
    except Exception:
        return {"online":False,"playersOnline":0,"playersMax":0,"motd":""}

# ── Bidirektionale Bridge: TCP (MC) ↔ WebSocket (Gateway) ────────────────────
async def bridge_tcp_ws(reader, writer, ws, conn_id):
    """
    Multiplexing-Brücke für einen Spieler.
    TCP→WS: Daten vom lokalen MC-Server → WebSocket-Datenkanal → Gateway → Spieler
    WS→TCP: Spieler-Daten → Gateway → WebSocket-Datenkanal → lokaler MC-Server
    """
    STATS.active_bridges += 1
    closed = asyncio.Event()

    async def tcp_to_ws():
        try:
            while not closed.is_set():
                chunk = await asyncio.wait_for(reader.read(32768), timeout=60)
                if not chunk:
                    break
                await ws.send(chunk)
                STATS.bytes_out += len(chunk)
        except Exception:
            pass
        finally:
            closed.set()

    async def ws_to_tcp():
        try:
            async for payload in ws:
                if closed.is_set(): break
                raw = payload if isinstance(payload, bytes) else payload.encode()
                writer.write(raw)
                await writer.drain()
                STATS.bytes_in += len(raw)
        except Exception:
            pass
        finally:
            closed.set()

    t2w = asyncio.ensure_future(tcp_to_ws())
    w2t = asyncio.ensure_future(ws_to_tcp())
    await asyncio.wait([t2w, w2t], return_when=asyncio.FIRST_COMPLETED)
    t2w.cancel(); w2t.cancel()

    STATS.active_bridges -= 1
    try: writer.close()
    except: pass

# ── Spieler-Verbindung verarbeiten ───────────────────────────────────────────
async def handle_player_connection(ws_base, tid, conn_id, mc_host, mc_port):
    """
    Für jeden eingehenden Spieler:
      1. TCP-Verbindung zu lokalem MC-Server
      2. WebSocket-Datenkanal zum Gateway
      3. Bridge starten
    """
    import websockets as _ws
    data_url = (f"wss://{ws_base}/api/tunnel-ws"
                f"?type=host_data&tunnelId={tid}&connectionId={conn_id}")
    writer = None
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(mc_host, mc_port), timeout=5)
        STATS.total_connections += 1
        data(f"Spieler Bridge aktiv  [{conn_id[:8]}…]  "
             f"Total: {STATS.total_connections}")

        async with _ws.connect(data_url,
                               max_size=2**23,
                               ping_interval=None,
                               open_timeout=10) as dws:
            await bridge_tcp_ws(reader, writer, dws, conn_id)

    except asyncio.TimeoutError:
        warn(f"Lokaler MC-Server antwortet nicht  [{conn_id[:8]}…]")
    except ConnectionRefusedError:
        warn(f"MC-Server Port {mc_port} nicht erreichbar  [{conn_id[:8]}…]")
    except Exception as e:
        pass
    finally:
        if writer:
            try: writer.close()
            except: pass

# ── Heartbeat-Task ───────────────────────────────────────────────────────────
async def heartbeat_task(ws, mc_host, mc_port, interval=30):
    """
    Keep-Alive: Sendet alle 30s einen Ping an den Gateway.
    Verhindert, dass die Verbindung durch Timeouts oder NAT-Tables abgebaut wird.
    """
    while True:
        await asyncio.sleep(interval)
        try:
            await ws.send(json.dumps({"action": "heartbeat",
                                      "uptime": STATS.uptime(),
                                      "activeBridges": STATS.active_bridges}))
        except Exception:
            break

# ── HOST-MODUS Haupt-Loop ────────────────────────────────────────────────────
async def run_host(ws_base, tid_ref, mc_host, mc_port):
    """
    Agenten-Loop mit Steuerkanal, Heartbeat und Auto-Reconnect.
    tid_ref ist eine Liste [tid] damit die Tunnel-ID bei Neuanlage aktualisiert werden kann.
    """
    import websockets as _ws
    backoff = 1

    while True:
        tid = tid_ref[0]
        ctrl_url = f"wss://{ws_base}/api/tunnel-ws?type=host&tunnelId={tid}"
        hb_task  = None

        try:
            info(f"Steuerkanal → {ws_base[:50]}")
            async with _ws.connect(ctrl_url,
                                   ping_interval=20,
                                   ping_timeout=15,
                                   open_timeout=15,
                                   max_size=2**20) as ctrl:
                backoff = 1
                ok(f"STEUERKANAL VERBUNDEN  Tunnel: {tid}  Server: {mc_host}:{mc_port}")
                info(STATS.summary())
                print(f"{DIM}  Drücke Strg+C zum Beenden{RST}\n")

                # Heartbeat starten
                hb_task = asyncio.ensure_future(
                    heartbeat_task(ctrl, mc_host, mc_port, interval=30))

                async for raw in ctrl:
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue

                    action = msg.get("action", "")

                    # ── Neuer Spieler verbindet sich ─────────────────────────
                    if action == "connect":
                        cid = msg.get("connectionId", "")
                        data(f"Eingehende Spieler-Verbindung  [{cid[:8]}…]")
                        asyncio.ensure_future(
                            handle_player_connection(
                                ws_base, tid, cid, mc_host, mc_port))

                    # ── Ping-Anfrage vom Gateway ─────────────────────────────
                    elif action == "ping":
                        stats_mc = await asyncio.get_event_loop().run_in_executor(
                            None, mc_ping, mc_host, mc_port)
                        status = "Online" if stats_mc["online"] else "Offline"
                        info(f"Ping: {status} | "
                             f"Spieler {stats_mc['playersOnline']}/{stats_mc['playersMax']} | "
                             f"{STATS.summary()}")
                        try:
                            await ctrl.send(json.dumps({
                                "action": "ping_response",
                                "stats": {**stats_mc,
                                          "agentUptime": STATS.uptime(),
                                          "activeBridges": STATS.active_bridges}}))
                        except Exception: pass

                    # ── Heartbeat-Bestätigung vom Gateway ────────────────────
                    elif action in ("heartbeat_ack", "pong"):
                        pass  # Verbindung bestätigt, nichts zu tun

        except Exception as e:
            if hb_task: hb_task.cancel()
            err_str = str(e)

            # ── Tunnel nicht gefunden → auto-neu anlegen ─────────────────────
            if "tunnel not found" in err_str.lower() or "1008" in err_str:
                warn(f"Tunnel '{tid}' nicht mehr auf dem Gateway vorhanden.")
                info("Erstelle neuen Tunnel automatisch…")
                new_tid, new_sub = await asyncio.get_event_loop().run_in_executor(
                    None, recreate_tunnel, tid, mc_host, mc_port)
                if new_tid:
                    tid_ref[0] = new_tid
                    ok(f"Neuer Tunnel bereit: {new_sub}.minehost-local.uk")
                    backoff = 1
                    continue
                else:
                    err("Kein Tunnel verfügbar — warte 30s…")
                    await asyncio.sleep(30)
                    continue

            # ── Normaler Verbindungsabbruch → Exponential Backoff ────────────
            warn(f"Steuerkanal getrennt: {e}")
            warn(f"Reconnect in {backoff}s…")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)

        finally:
            if hb_task: hb_task.cancel()

# ── CLIENT-MODUS ─────────────────────────────────────────────────────────────
async def run_client(ws_base, tid, local_port):
    """
    Client-Modus: Lokaler TCP-Listener für Spieler, die über den Tunnel connecten wollen.
    Jeder Spieler bekommt seinen eigenen WebSocket-Datenkanal.
    """
    import websockets as _ws, random, string

    async def handle(reader, writer):
        import random, string
        cid  = "".join(random.choices(string.ascii_lowercase + string.digits, k=7))
        addr = writer.get_extra_info("peername", ("?","?"))
        data(f"Spieler: {addr[0]}:{addr[1]}  cid={cid}")
        data_url = (f"wss://{ws_base}/api/tunnel-ws"
                    f"?type=client&tunnelId={tid}&connectionId={cid}")
        try:
            async with _ws.connect(data_url, max_size=2**23, ping_interval=None) as dws:
                # Warte kurz bis der Relay den Host-Datenkanal bereit hat (Relay-Timing-Fix)
                await asyncio.sleep(0.3)
                # Puffere ankommende MC-Daten damit nichts vor dem Relay verlorengeht
                initial_buf = b""
                try:
                    initial_buf = await asyncio.wait_for(reader.read(4096), timeout=0.5)
                except asyncio.TimeoutError:
                    pass
                # Sende gepufferte Daten + bridge
                if initial_buf:
                    await dws.send(initial_buf)
                await bridge_tcp_ws(reader, writer, dws, cid)
        except Exception as e:
            pass
        finally:
            try: writer.close()
            except: pass

    server = await asyncio.start_server(handle, "127.0.0.1", local_port)
    ok(f"Client-Modus aktiv — lausche auf 127.0.0.1:{local_port}")
    info("Richte Minecraft-Client auf diese Adresse ein.")
    async with server:
        await server.serve_forever()

# ── BANNER ───────────────────────────────────────────────────────────────────
def banner(mode, tid, mc_host, mc_port, subdomain):
    mode_col = G if mode == "host" else B
    print(f"\n{BLD}{C}┌───────────────────────────────────────────────────┐")
    print(f"│   Mine-Host Tunnel Agent  v3.0                    │")
    print(f"│   Modus   : {mode_col}{mode.upper():<8}{C}  "
          f"Tunnel  : {W}{tid:<14}{C}    │")
    print(f"│   MC-Port : {W}{mc_port:<6}{C}   "
          f"Subdomain: {W}{subdomain[:18]:<18}{C}   │")
    print(f"└───────────────────────────────────────────────────┘{RST}\n")

# ── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Mine-Host Tunnel Agent v3.0 — "
                    "Agenten-Teil des Minecraft-Tunnel-Systems")
    parser.add_argument("mode",      nargs="?", help="host | client")
    parser.add_argument("tunnel_id", nargs="?", help="Tunnel-ID (z.B. 1tug3n9kp)")
    parser.add_argument("--port",    type=int,  help="Lokaler Port (überschreibt API)")
    parser.add_argument("--host",    default="", help="Lokaler Host (Standard: 127.0.0.1)")
    parser.add_argument("--server",  default=MINEHOST_API,
                        help="Gateway-URL (Standard: minehost-local.uk)")
    args = parser.parse_args()

    # Interaktiv wenn keine Args
    if not args.mode or not args.tunnel_id:
        print(f"\n{BLD}{C}Mine-Host Tunnel Agent v3.0{RST}")
        print(f"{DIM}Gateway: {MINEHOST_API}{RST}\n")
        if not args.mode:
            args.mode = input(f"{W}Modus {DIM}(host/client){RST}: ").strip().lower()
        if not args.tunnel_id:
            args.tunnel_id = input(f"{W}Tunnel-ID{DIM} (leer = neu anlegen){RST}: ").strip()

    if not args.mode or args.mode not in ("host","client"):
        err("Modus muss 'host' oder 'client' sein."); sys.exit(1)

    # ── Tunnel-Infos von Gateway holen ───────────────────────────────────────
    info(f"Verbinde mit Gateway {args.server} …")
    tunnel    = None
    tunnel_id = args.tunnel_id
    subdomain = tunnel_id

    if tunnel_id:
        try:
            tunnel = fetch_tunnel(tunnel_id)
        except Exception as e:
            warn(f"Gateway nicht erreichbar: {e}")

    # Kein Tunnel-ID oder nicht gefunden → neuen anlegen
    if not tunnel and args.mode == "host":
        mc_port_default = args.port or 25565
        warn(f"Tunnel nicht gefunden — lege neuen an für Port {mc_port_default}…")
        try:
            tunnel_id, subdomain = recreate_tunnel("new", "127.0.0.1", mc_port_default)
            if not tunnel_id:
                err("Tunnel-Anlage fehlgeschlagen."); sys.exit(1)
            try:
                tunnel = fetch_tunnel(tunnel_id)
            except: pass
        except Exception as e:
            err(f"Fehler: {e}"); sys.exit(1)

    if tunnel:
        mc_host   = args.host  or tunnel.get("targetHost","127.0.0.1")
        mc_port   = args.port  or tunnel.get("targetPort", 25565)
        subdomain = tunnel.get("subdomain", tunnel_id)
        ok(f"Tunnel: '{tunnel.get('name','?')}' → {subdomain}.minehost-local.uk")
        ok(f"MC-Server: {mc_host}:{mc_port}")
    else:
        mc_host = args.host or "127.0.0.1"
        mc_port = args.port or 25565

    # WebSocket-Domain (ohne Protokoll)
    ws_base = (args.server
               .replace("https://","").replace("http://","").rstrip("/"))

    banner(args.mode, tunnel_id, mc_host, mc_port, subdomain)

    try:
        if args.mode == "host":
            asyncio.run(run_host(ws_base, [tunnel_id], mc_host, mc_port))
        else:
            asyncio.run(run_client(ws_base, tunnel_id, mc_port))
    except KeyboardInterrupt:
        print(f"\n{Y}Agent beendet.  {STATS.summary()}{RST}")

if __name__ == "__main__":
    main()
