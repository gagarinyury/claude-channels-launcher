#!/usr/bin/env python3
"""
Claude Code Launcher Bot
Manages Claude Code tmux session via Telegram commands.
"""

import json
import logging
import os
import subprocess
import time
import urllib.parse
import urllib.request

LOG_FILE = os.path.expanduser("~/claude-launcher/launcher.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ]
)
log = logging.getLogger("launcher")
_starting = False
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

BOT_TOKEN = os.getenv("LAUNCHER_BOT_TOKEN", "").strip()
ALLOWED_CHAT_ID = os.getenv("ALLOWED_CHAT_ID", "").strip()
TMUX_SESSION = os.getenv("TMUX_SESSION", "claude")
WORK_DIR = os.getenv("CLAUDE_WORK_DIR", "~/claude")
BUN_PATH = os.getenv("BUN_PATH", os.path.expanduser("~/.bun/bin"))
CLAUDE_CMD = f"cd {WORK_DIR} && PATH={BUN_PATH}:$PATH claude --channels plugin:telegram@claude-plugins-official"
WATCHDOG_AUTORESTART = os.getenv("WATCHDOG_AUTORESTART", "false").lower() == "true"
WATCHDOG_COOLDOWN = int(os.getenv("WATCHDOG_COOLDOWN", "300"))

updates_offset = 0
_was_alive = False


# ── Telegram API ──────────────────────────────────────────────────────────────

def tg(method: str, data: dict = {}) -> dict:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body)
    timeout = 35 if method == "getUpdates" else 10
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def send(chat_id: str, text: str) -> None:
    tg("sendMessage", {"chat_id": chat_id, "text": text})


# ── tmux helpers ──────────────────────────────────────────────────────────────

def session_alive() -> bool:
    result = subprocess.run(
        ["tmux", "has-session", "-t", f"{TMUX_SESSION}:main"],
        capture_output=True
    )
    return result.returncode == 0


def start_session() -> str:
    global _starting
    if _starting:
        return "⏳ Already starting, please wait..."
    if session_alive():
        return "✅ Already running."
    _starting = True
    # Session exists (launcher window) — just add main window
    session_exists = subprocess.run(
        ["tmux", "has-session", "-t", TMUX_SESSION],
        capture_output=True
    ).returncode == 0

    cmd = f"while true; do {CLAUDE_CMD}; sleep 3; done"
    if session_exists:
        subprocess.run(["tmux", "new-window", "-t", TMUX_SESSION, "-n", "main", cmd])
    else:
        subprocess.run(["tmux", "new-session", "-d", "-s", TMUX_SESSION, "-n", "main", cmd])

    time.sleep(5)
    _starting = False
    if not session_alive():
        return "❌ Failed to start."
    global _was_alive
    _was_alive = True
    lines = clean_logs()
    preview = "\n".join(lines[-5:]) if lines else ""
    return f"✅ Claude started.\n\n{preview}"


def stop_session() -> str:
    if not session_alive():
        return "Session is not running."
    subprocess.run(["tmux", "send-keys", "-t", f"{TMUX_SESSION}:main", "q", ""])
    time.sleep(1)
    subprocess.run(["tmux", "send-keys", "-t", f"{TMUX_SESSION}:main", "C-c", ""])
    time.sleep(1)
    # Kill only the while-true loop by sending kill to all processes in the pane
    result = subprocess.run(
        ["tmux", "display-message", "-t", f"{TMUX_SESSION}:main", "-p", "#{pane_pid}"],
        capture_output=True, text=True
    )
    pane_pid = result.stdout.strip()
    if pane_pid:
        subprocess.run(["kill", pane_pid])
    return "⛔ Claude stopped."


def restart_session() -> str:
    stop_session()
    time.sleep(2)
    return start_session()


def get_logs() -> str:
    if not session_alive():
        return "Session is not running."
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", f"{TMUX_SESSION}:main", "-p"],
        capture_output=True, text=True
    )
    lines = [l for l in result.stdout.splitlines() if l.strip()]
    return "\n".join(lines[-20:]) or "(empty)"


NOISE = {"bypass permissions", "esc to interrupt", "shift+tab", "ctrl+o", "tmux focus", "set -g", "Try \""}

def clean_logs() -> list[str]:
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", f"{TMUX_SESSION}:main", "-p"],
        capture_output=True, text=True
    )
    lines = []
    for l in result.stdout.splitlines():
        l = l.strip()
        if not l:
            continue
        if any(noise in l for noise in NOISE):
            continue
        lines.append(l)
    return lines


def get_status() -> str:
    if not session_alive():
        return "🔴 Claude Code — offline\n/launch — start"
    lines = clean_logs()
    preview = "\n".join(lines[-5:]) if lines else "(no output)"
    return f"🟢 Claude Code — running\n\n{preview}"


# ── command handler ───────────────────────────────────────────────────────────

def handle(chat_id: str, text: str) -> None:
    if chat_id != ALLOWED_CHAT_ID:
        return

    cmd = text.strip().lower().split()[0] if text.strip() else ""

    WELCOME = (
        "🤖 Claude Launcher\n\n"
        "Manages your Claude Code session on a remote server.\n\n"
        "/status — Claude status\n"
        "/launch — start Claude\n"
        "/stop — stop Claude\n"
        "/restart — restart Claude\n"
        "/logs — last terminal output"
    )
    if cmd in ("/start", "/help"):
        send(chat_id, WELCOME)
    elif cmd == "/status":
        send(chat_id, get_status())
    elif cmd == "/launch":
        send(chat_id, "⏳ Starting Claude...")
        send(chat_id, start_session())
    elif cmd == "/stop":
        send(chat_id, stop_session())
    elif cmd == "/restart":
        send(chat_id, "🔄 Restarting Claude...")
        send(chat_id, restart_session())
    elif cmd == "/logs":
        send(chat_id, f"📋 Last output:\n\n```\n{get_logs()}\n```")
    else:
        send(chat_id, WELCOME)


# ── polling loop ──────────────────────────────────────────────────────────────

def set_commands() -> None:
    try:
        tg("setMyCommands", {
            "commands": '[{"command":"status","description":"🟢 Claude status"},{"command":"launch","description":"🚀 Start Claude session"},{"command":"stop","description":"⛔ Stop Claude session"},{"command":"restart","description":"🔄 Restart Claude session"},{"command":"logs","description":"📋 Last terminal output"}]'
        })
    except Exception as e:
        log.warning(f"setMyCommands failed: {e}")


def watchdog():
    global _was_alive
    last_notified = 0
    while True:
        time.sleep(30)
        alive = session_alive()
        if _was_alive and not alive:
            now = time.time()
            if now - last_notified >= WATCHDOG_COOLDOWN:
                last_notified = now
                if WATCHDOG_AUTORESTART:
                    log.warning("Claude session died — restarting")
                    try:
                        send(ALLOWED_CHAT_ID, "⚠️ Claude session died. Restarting...")
                    except Exception as e:
                        log.error(f"watchdog notify failed: {e}")
                    result = start_session()
                    log.info(f"watchdog restart: {result}")
                    try:
                        send(ALLOWED_CHAT_ID, result)
                    except Exception as e:
                        log.error(f"watchdog notify failed: {e}")
                else:
                    log.warning("Claude session died — notifying")
                    try:
                        send(ALLOWED_CHAT_ID, "⚠️ Claude session died. Use /launch to restart.")
                    except Exception as e:
                        log.error(f"watchdog notify failed: {e}")
        _was_alive = alive


def poll():
    global updates_offset
    global _was_alive
    log.info("Launcher bot started")
    _was_alive = session_alive()
    set_commands()
    while True:
        try:
            resp = tg("getUpdates", {"offset": updates_offset, "timeout": 30})
            for update in resp.get("result", []):
                updates_offset = update["update_id"] + 1
                msg = update.get("message") or update.get("edited_message")
                if not msg:
                    continue
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "")
                if text:
                    handle(chat_id, text)
        except Exception as e:
            log.error(f"poll error: {e}")
            time.sleep(5)


if __name__ == "__main__":
    if not BOT_TOKEN:
        print("LAUNCHER_BOT_TOKEN is required", flush=True)
        exit(1)
    Thread(target=watchdog, daemon=True).start()
    poll()
