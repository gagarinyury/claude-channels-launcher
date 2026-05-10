# claude-channels-launcher

> Telegram bot that manages Claude Code Channels sessions on a remote Linux server — start, stop, restart and monitor Claude from your phone.

![Python](https://img.shields.io/badge/python-3.9%2B-blue?logo=python&logoColor=white)
![Zero deps](https://img.shields.io/badge/dependencies-zero-brightgreen)
![Platform](https://img.shields.io/badge/platform-Linux-lightgrey?logo=linux)
![License](https://img.shields.io/badge/license-MIT-blue)

---

## What is Claude Code Channels?

[Claude Code](https://claude.ai/code) has an experimental **Channels** feature that lets you talk to Claude directly from Telegram — it's like having a senior engineer in your pocket. This bot solves the operational problem: keeping that Claude session alive on a headless server and letting you control it remotely.

## Features

- **Full session control** — start, stop, restart Claude from Telegram
- **Live status** — see what Claude is doing right now
- **Watchdog** — get notified (or auto-restarted) when Claude dies
- **Noise-filtered logs** — strips tmux UI garbage, shows only meaningful output
- **Zero dependencies** — pure Python standard library, no pip required
- **Single-user auth** — only your Telegram ID can control the bot

## Demo

```
you:  /status
bot:  🟢 Claude Code — running

      ✻ Thinking…
      I'll analyze the codebase first

you:  /logs
bot:  📋 Last output:

      ❯ Reading src/index.ts
      ❯ Searching for API calls
      ✔ Found 3 files to update

you:  /stop
bot:  ⛔ Claude stopped.
```

## Setting up Claude Code Channels

Claude Code Channels is an experimental feature that bridges Claude Code to external messaging apps via plugins.

**1. Install Claude Code**
```bash
npm install -g @anthropic-ai/claude-code
```

**2. Authenticate**
```bash
claude
# Follow the login flow
```

**3. Create a Telegram bot for Claude** (separate from the launcher bot)

Talk to [@BotFather](https://t.me/BotFather) → `/newbot` → copy the token.

**4. Configure the Channels plugin**

```bash
mkdir -p ~/claude
cd ~/claude
claude mcp add --transport sse telegram https://claude-plugins-official.anthropic.com/telegram/sse
```

When prompted, paste your Telegram bot token.

**5. Test it**

```bash
cd ~/claude
claude --channels plugin:telegram@claude-plugins-official
```

Open Telegram, find your bot, say hi — Claude should respond. Once it works, use this launcher bot to keep it running persistently without a terminal.

---

## Requirements

- Linux (Ubuntu 20.04+)
- Python 3.9+
- [tmux](https://github.com/tmux/tmux)
- [Claude Code](https://claude.ai/code) installed and authenticated
- [bun](https://bun.sh) (required by the Claude Telegram plugin)
- Telegram bot token from [@BotFather](https://t.me/BotFather)

## Setup

### 1. Clone and configure

```bash
git clone https://github.com/gagarinyury/claude-channels-launcher
cd claude-channels-launcher
cp .env.example .env
nano .env
```

### 2. Get your Telegram user ID

Message [@userinfobot](https://t.me/userinfobot) — it replies with your numeric ID. Put it in `ALLOWED_CHAT_ID`.

### 3. Create a Telegram bot

Talk to [@BotFather](https://t.me/BotFather), send `/newbot`, follow the steps. Put the token in `LAUNCHER_BOT_TOKEN`.

### 4. Start

```bash
# Start Claude Code session in tmux
tmux new-session -d -s claude -n main \
  'while true; do cd ~/claude && PATH=~/.bun/bin:$PATH claude --channels plugin:telegram@claude-plugins-official; sleep 3; done'

# Start launcher bot in a second tmux window
tmux new-window -t claude -n launcher \
  'env $(cat ~/claude-channels-launcher/.env | xargs) python3 ~/claude-channels-launcher/launcher.py'
```

### 5. Auto-start on reboot

```bash
crontab -e
```

Add this line:

```
@reboot sleep 30 && tmux new-session -d -s claude -n main 'while true; do cd ~/claude && PATH=~/.bun/bin:$PATH claude --channels plugin:telegram@claude-plugins-official; sleep 3; done' && tmux new-window -t claude -n launcher 'env $(cat ~/claude-channels-launcher/.env | xargs) python3 ~/claude-channels-launcher/launcher.py'
```

## Commands

| Command | Description |
|---------|-------------|
| `/status` | 🟢 Claude status + last output |
| `/launch` | 🚀 Start Claude session |
| `/stop` | ⛔ Stop Claude session |
| `/restart` | 🔄 Restart Claude session |
| `/logs` | 📋 Last terminal output |

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `LAUNCHER_BOT_TOKEN` | ✅ | — | Telegram bot token from @BotFather |
| `ALLOWED_CHAT_ID` | ✅ | — | Your Telegram user ID (single-user auth) |
| `TMUX_SESSION` | — | `claude` | tmux session name |
| `CLAUDE_WORK_DIR` | — | `~/claude` | Working directory for Claude Code |
| `BUN_PATH` | — | `~/.bun/bin` | Path to bun binary |
| `WATCHDOG_AUTORESTART` | — | `false` | Auto-restart Claude if it dies |
| `WATCHDOG_COOLDOWN` | — | `300` | Seconds between watchdog notifications |

## Watchdog

A background thread checks every 30 seconds whether Claude is alive.

**Notify mode** (default) — sends a message when Claude dies:
```
⚠️ Claude session died. Use /launch to restart.
```

**Auto-restart mode** — set `WATCHDOG_AUTORESTART=true` in `.env`:
```
⚠️ Claude session died. Restarting...
✅ Claude запущен.
```

Notifications are rate-limited by `WATCHDOG_COOLDOWN` to avoid spam.

## Architecture

```
you (Telegram)
      │
      ▼
launcher bot          ← launcher.py running in tmux:launcher
      │
      ▼
tmux session "claude"
      ├── main window     ← Claude Code --channels (with auto-restart loop)
      └── launcher window ← launcher.py
```

Claude Code runs inside a `while true` shell loop — if it crashes, it restarts automatically after 3 seconds. The launcher bot manages that loop from the outside via tmux.

## systemd (alternative to crontab)

A `claude-launcher.service` file is included for systemd-based setups. Edit the paths and user, then:

```bash
cp claude-launcher.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now claude-launcher
loginctl enable-linger $USER
```

## License

MIT
