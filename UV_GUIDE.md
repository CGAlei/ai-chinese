# Guide: Using `uv` & Background Server for your Python Environment

Welcome! This guide explains how to use `uv` to manage your Python dependencies, manage the automated background server, move your project to a new laptop, and troubleshoot issues.

---

## 1. What is `uv`?
`uv` is an extremely fast Python package manager and virtual environment creator (written in Rust). It replaces `conda`, `pip`, and `venv` with a single tool.

**Crucial Concept**: You **do not need to activate** virtual environments manually anymore. `uv run` handles virtual environment activation behind the scenes on-the-fly.

---

## 2. The Unified Background Server (Port 8082)

To prevent you from having to manually start servers every time you boot up, and to bypass Obsidian's `file://` security block, a unified backend and static file server is configured to run silently in the background on **port `8082`**.

This single background process serves both your **FastAPI API** and all your **static HTML files** (Mo-Reader, Mo-Cards, etc.) over HTTP.

### Live URLs inside Obsidian (or your browser):
*   **MemoryWiki Generator Frontend**: `http://localhost:8082/`
*   **Mo-Reader**: [http://localhost:8082/app/Mo-Reader.html](http://localhost:8082/app/Mo-Reader.html)
*   **Mo-Cards**: [http://localhost:8082/app/Mo-Cards.html](http://localhost:8082/app/Mo-Cards.html)
*   **Mo-Dict**: [http://localhost:8082/app/Mo-Dict.html](http://localhost:8082/app/Mo-Dict.html)
*   **MoDB Inspector**: [http://localhost:8082/app/MoDB-inspector.html](http://localhost:8082/app/MoDB-inspector.html)

---

## 3. Controlling the Background Service (systemd)

Since the server runs as a `systemd` user service, you can manage it using standard system control commands:

*   **Check status & logs**:
    ```bash
    systemctl --user status ai-chinese-server.service
    ```
*   **Restart the server** (e.g. if code changes or it hangs):
    ```bash
    systemctl --user restart ai-chinese-server.service
    ```
*   **Stop the server**:
    ```bash
    systemctl --user stop ai-chinese-server.service
    ```
*   **Start the server**:
    ```bash
    systemctl --user start ai-chinese-server.service
    ```
*   **View live logs** (very useful for debugging API calls):
    ```bash
    journalctl --user -u ai-chinese-server.service -n 50 -f
    ```

---

## 4. Package Management (Installing New Libraries)

If you need to install a new Python package (e.g., `requests`) in the future:

```bash
# In the Ai-chinese directory:
uv add requests
```
*This command does two things automatically:*
1. Installs the package into your local `.venv/` folder.
2. Adds `requests` to the `dependencies` list inside your `pyproject.toml` file so it is saved for future builds.

---

## 5. Portability: Migrating to a New Laptop (Step-by-Step)

When copying your project folder (`Ai-chinese`) to another machine, **do not copy the `.venv` folder** (it contains system-specific paths). Follow these steps to restore the environment and background service on the new machine:

### Step 1: Install `uv`
On the new laptop, open a terminal and run:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```
Restart your terminal so the `uv` command is recognized.

### Step 2: Install system tools
Ensure `ffmpeg` and `sox` are installed on the host system:
```bash
# On Arch Linux:
sudo pacman -S ffmpeg sox

# On Ubuntu/Debian:
sudo apt install ffmpeg sox
```

### Step 3: Recreate the python environment
Navigate to your project directory (`/home/alex/Ai-chinese`) and run:
```bash
uv sync
```
`uv` will automatically read your `pyproject.toml`, download Python 3.11, set up a fresh `.venv` folder, and link all required packages (including PyTorch with CUDA support if a GPU is available).

### Step 4: Setup the Background Server
We saved a copy of the service file in your repository. To configure it on the new machine:
1. Create the systemd user configuration directory:
   ```bash
   mkdir -p ~/.config/systemd/user
   ```
2. Copy the service file from the repository to your systemd folder:
   ```bash
   cp MemoryWiki/generator/ai-chinese-server.service ~/.config/systemd/user/
   ```
3. Reload systemd, start, and enable the service:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now ai-chinese-server.service
   ```

Now, your new laptop is fully configured, and the background server is active!
