# MineHost Local

**Lokale Alternative zu Aternos** - verwalte deinen Minecraft-Server direkt auf dem eigenen PC.

## Features
- Login/Registrierung (lokal)
- Automatischer Download von Vanilla & Paper JARs
- Live-Konsole mit Befehlseingabe
- System-Monitor (CPU & RAM)
- Optionen schreiben direkt in server.properties
- Plugin/Mod-Manager

## Installation
pip install customtkinter psutil requests pillow
python minehost_local.py

## Als .exe bauen
pip install pyinstaller
pyinstaller --onefile --windowed --name MineHostLocal minehost_local.py

## Voraussetzungen
- Python 3.10+
- Java fuer den Minecraft-Server: https://adoptium.net
