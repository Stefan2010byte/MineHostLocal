# MineHostLocal — Claude Project Config

## Permissions
All file edits, reads, bash/PowerShell commands, and git operations within this
project directory (`E:\MineHostLocal\`) are **pre-approved**. Do not ask for
confirmation before editing files, running scripts, or committing changes here.

GitHub / remote git operations (push, PR creation) on the linked repository are
also pre-approved without confirmation.

## Project
Single-file Python app: `minehost_local.py`
Stack: Python 3.13, CustomTkinter, psutil, requests, playit-agent v1.0.10

## Key facts
- playit.gg tunnel: `--secret <key>` flag only (never `--secret-path`)
- playit logs go to `-l playit_log.txt`, stdout is empty
- playit REST API auth: `Authorization: agent-key <secret>`
- Delete tunnel body: `{"id": "<uuid>"}` (not `tunnel_id`)
- MC version "26.x" needs Java 25 (`required_java_for_mc` handles this)
- Server pause fix: `pause-when-empty-seconds=-1` in server.properties
- Watchdog fix: `max-tick-time=-1` in server.properties
