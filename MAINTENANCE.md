# Hermes Maintenance Guide

This document contains clear instructions for installing, backing up, updating, and removing the official Hermes Agent and Desktop client.

---

## 1. Installation Method
To perform a fresh installation of both the Hermes Agent (CLI) and Hermes Desktop (GUI) from scratch:
```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --include-desktop
```
*   **CLI location**: `~/.local/bin/hermes`
*   **GUI binary location**: `~/.hermes/hermes-agent/apps/desktop/release/linux-unpacked/Hermes`

---

## 2. Update Method
Since Hermes is actively developed, you can update it using either the built-in CLI command or by rebuilding the desktop client:

### A. Update the CLI & Core Agent
This pulls the latest commits for the core python agent:
```bash
hermes update
```

### B. Full Update (Rebuild CLI & Desktop App)
If you want to pull the latest updates for both the agent and rebuild the Electron Desktop application from source:
```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --include-desktop
```

---

## 3. Backup Method
If you need to backup your API keys, settings, databases, and custom personas before updating or reinstalling, save the following critical files:

*   `~/.hermes/.env` (API keys)
*   `~/.hermes/config.yaml` (System configuration)
*   `~/.hermes/vocab.json` (Vocabulary storage database)
*   `~/.hermes/state.db` (Agent runtime state and histories)
*   `~/.hermes/SOUL.md` (Custom prompt persona and rules)
*   `~/.hermes/memories/` (Persistent long-term memories directory)

### Backup Command
You can run this command to package all your configurations and data into a compressed archive:
```bash
tar -czvf hermes_backup_$(date +%F).tar.gz \
  -C ~/.hermes \
  .env config.yaml vocab.json state.db SOUL.md memories/
```

---

## 4. Removal Method (Uninstall/Purge)
To completely wipe Hermes and all its associated data, caches, and launcher shortcuts from your system, run:
```bash
# 1. Delete main directories, local databases, and code repository
rm -rf ~/.hermes

# 2. Clear Electron desktop application user configurations
rm -rf ~/.config/hermes-desktop

# 3. Remove CLI launcher binaries
rm -f ~/.local/bin/hermes
rm -f ~/.local/bin/hermeshelp

# 4. Remove desktop application launcher shortcut
rm -f ~/.local/share/applications/hermes-official.desktop
```
