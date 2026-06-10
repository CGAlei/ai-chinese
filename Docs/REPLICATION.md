# Project Replication & Migration Guide

This document describes how to set up the **Ai-chinese** environment on a new computer. Since your study progress database, Obsidian vaults, and API keys are local-only and excluded from Git, you must replicate both the codebase (via GitHub) and your local data.

---

## 📂 Replicable Components

To transfer your complete setup, you need to combine the code from GitHub with these **four local items** from your current machine:
1. 📁 **`data/`** folder (contains Obsidian markdown vaults and transcription sessions).
2. 🔑 **`.env`** (contains shared API keys for OpenRouter/Gemini and Azure).
3. 📄 **`web/audio-srs/data/vocabulary.json`** (keeps your favorite stars, reps, and SRS intervals).
4. 📄 **`services/audio-srs-mdd/mdd_progress.db`** (keeps your SQLite pronunciation coach attempt history).

---

## 🛠️ Step-by-Step Setup

### Step 1: Clone the Codebase on the New Computer
On the new machine, open a terminal and clone the repository:
```bash
git clone https://github.com/CGAlei/ai-chinese.git
cd ai-chinese
```

---

### Step 2: Transfer Local Data (Choose Method A or B)

#### Method A: Using a Tarball Archive (Recommended for Command Line)
1. On your **old computer**, package your local configurations from the project root:
   ```bash
   tar -czvf ai-chinese-local-state.tar.gz \
     .env \
     data/ \
     web/audio-srs/data/vocabulary.json \
     services/audio-srs-mdd/mdd_progress.db*
   ```
2. Transfer `ai-chinese-local-state.tar.gz` to the new computer.
3. Move the archive to the root of your newly cloned `ai-chinese` directory on the **new computer**, then extract it:
   ```bash
   tar -xzvf ai-chinese-local-state.tar.gz
   rm ai-chinese-local-state.tar.gz
   ```

#### Method B: Direct Directory Copy (Recommended for GUI/USB/Syncthing)
Simply copy the following folders and files from the old computer and drop them into the exact same relative paths inside the cloned repository on the **new computer**:
- `data/` *(directory)*
- `.env` *(file at project root)*
- `web/audio-srs/data/vocabulary.json` *(file)*
- `services/audio-srs-mdd/mdd_progress.db` *(file, copy .db-wal and .db-shm if present)*

---

### Step 3: Install Dependencies

#### 1. Python Environment (Pipelines)
Ensure you have the [uv package manager](https://github.com/astral-sh/uv) installed. Run the following command from the project root to install the virtual environment and dependencies:
```bash
uv sync
```

#### 2. Node.js Environment (MDD Pronunciation Backend)
Change to the MDD directory and install node packages:
```bash
cd services/audio-srs-mdd
npm install
cd ../..
```

---

### Step 4: Run the Local Servers

#### 1. Start the ZenHanzi Offline App (Port 8082)
Serve the static offline trainer app:
```bash
# Using Python
python -m http.server -d web/audio-srs/ 8082

# Or using Node
npx http-server web/audio-srs/ -p 8082
```

#### 2. Start the MDD Pronunciation backend (Port 3000)
Run it manually in the foreground:
```bash
cd services/audio-srs-mdd
node server.js
```

Or configure it as a **Systemd User Service** to run automatically in the background on boot:
1. Create user systemd directories:
   ```bash
   mkdir -p ~/.config/systemd/user
   ```
2. Create `~/.config/systemd/user/ai-chinese-mdd.service` and paste:
   ```ini
   [Unit]
   Description=AI Chinese MDD Pronunciation Coach Server
   After=network.target

   [Service]
   Type=simple
   WorkingDirectory=/home/alex/Ai-chinese/services/audio-srs-mdd
   ExecStart=/usr/bin/node server.js
   Restart=always
   Environment=NODE_ENV=production

   [Install]
   WantedBy=default.target
   ```
   *(Note: Verify the absolute path to `WorkingDirectory` matches your clone location).*
3. Reload systemd, enable, and start the service:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable ai-chinese-mdd.service
   systemctl --user start ai-chinese-mdd.service
   ```

---

### Step 5: Verify Setup
Run a quick test of the unified pipeline from the project root to verify:
```bash
./sync.sh --limit 1
```
Navigate your browser to:
- Offline Trainer: `http://localhost:8082`
- Pronunciation Coach: `http://localhost:3000`
