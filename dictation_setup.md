# Guía de Instalación: Dictado por Voz con Qwen3-ASR en Hyprland

Esta guía explica cómo instalar y configurar el sistema de dictado por voz ultraligero que utiliza la API de **Qwen3-ASR (OpenRouter)** en cualquier laptop con Linux y Hyprland/Wayland.

---

## 1. Dependencias del Sistema

Asegúrate de instalar los siguientes paquetes en el sistema de destino (en Arch Linux):

```bash
sudo pacman -S pipewire wireplumber wl-clipboard wtype libnotify
```

* **pipewire / wireplumber**: Necesario para ejecutar `pw-record` (captura de audio).
* **wl-clipboard**: Proporciona `wl-copy` para copiar el texto transcrito.
* **wtype**: Permite simular la pulsación de teclas (`Ctrl+V`) para pegar automáticamente en Wayland.
* **libnotify**: Proporciona `notify-send` para mostrar notificaciones en el escritorio (🎙️ Grabando, ⏳ Transcribiendo, etc.).

---

## 2. Crear el Script de Dictado

Crea el archivo del script en tu directorio local de binarios:

1. Crea el archivo en `~/.local/bin/dictate.py`:
   ```bash
   nano ~/.local/bin/dictate.py
   ```

2. Pega el siguiente código en el archivo:

```python
#!/usr/bin/env python3
import os
import sys
import subprocess
import json
import base64
import urllib.request
import urllib.error
import time

PID_FILE = "/tmp/dictation.pid"
AUDIO_FILE = "/tmp/dictation.wav"
API_KEY = "YOUR_OPENROUTER_API_KEY_HERE"
MODEL = "qwen/qwen3-asr-flash-2026-02-10"

def notify(message, urgency="normal"):
    import sys
    print(f"[Dictate] {message}", file=sys.stderr, flush=True)
    subprocess.run(["notify-send", "-u", urgency, "-t", "2000", "Voice Dictation", message])

def is_process_running(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def start_recording():
    if os.path.exists(AUDIO_FILE):
        try:
            os.remove(AUDIO_FILE)
        except OSError:
            pass

    notify("🎙️ Recording started...")
    
    try:
        proc = subprocess.Popen([
            "pw-record", 
            "--rate", "16000", 
            "--channels", "1", 
            "--format", "s16", 
            AUDIO_FILE
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception as e:
        notify(f"❌ Failed to start recording: {e}", "critical")
        return

    with open(PID_FILE, "w") as f:
        f.write(str(proc.pid))

def stop_recording_and_transcribe():
    try:
        with open(PID_FILE, "r") as f:
            pid = int(f.read().strip())
    except Exception:
        notify("❌ Error: No active recording found.", "critical")
        return

    if is_process_running(pid):
        try:
            os.kill(pid, 15)
            time.sleep(0.5)
        except OSError:
            pass

    try:
        os.remove(PID_FILE)
    except OSError:
        pass

    if not os.path.exists(AUDIO_FILE) or os.path.getsize(AUDIO_FILE) == 0:
        notify("❌ Error: Audio file is empty or missing.", "critical")
        return

    notify("⏳ Transcribing...")

    try:
        with open(AUDIO_FILE, "rb") as f:
            audio_bytes = f.read()
        audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
    except Exception as e:
        notify(f"❌ Base64 encoding failed: {e}", "critical")
        return

    or_url = "https://openrouter.ai/api/v1/audio/transcriptions"
    or_headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/quailyquaily/coe",
        "X-Title": "Lightweight Voice Input"
    }
    or_payload = {
        "model": MODEL,
        "input_audio": {
            "data": audio_base64,
            "format": "wav"
        }
    }

    req = urllib.request.Request(
        or_url,
        data=json.dumps(or_payload).encode('utf-8'),
        headers=or_headers,
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            resp_data = response.read()
            or_resp = json.loads(resp_data.decode('utf-8'))
        transcribed_text = or_resp.get("text", "").strip()
    except urllib.error.HTTPError as e:
        err_content = e.read().decode('utf-8')
        try:
            err_json = json.loads(err_content)
            err_msg = err_json.get("error", {}).get("message", err_content)
        except Exception:
            err_msg = err_content
        notify(f"❌ API Error ({e.code}): {err_msg}", "critical")
        return
    except Exception as e:
        notify(f"❌ Connection error: {e}", "critical")
        return

    if not transcribed_text:
        notify("⚠️ No speech detected.", "normal")
        return

    import sys
    print(f"[Dictate] Transcribed text: '{transcribed_text}'", file=sys.stderr, flush=True)

    try:
        subprocess.run(["wl-copy", transcribed_text], check=True)
    except Exception as e:
        notify(f"❌ Failed to copy to clipboard: {e}", "critical")
        return

    try:
        time.sleep(0.1)
        subprocess.run(["wtype", "-M", "ctrl", "v", "-m", "ctrl"], check=True)
        notify("📝 Text pasted!", "normal")
    except Exception as e:
        notify(f"Clipboard copied (Paste simulation failed: {e})", "normal")

    try:
        os.remove(AUDIO_FILE)
    except OSError:
        pass

def main():
    if os.path.exists(PID_FILE):
        stop_recording_and_transcribe()
    else:
        start_recording()

if __name__ == "__main__":
    main()
```

3. Dale permisos de ejecución al script:
   ```bash
   chmod +x ~/.local/bin/dictate.py
   ```

---

## 3. Configurar el Atajo de Teclado en Hyprland

Para que el script se ejecute al presionar la combinación de teclas:

1. Abre tu archivo de bindings en Hyprland (ej. `~/.config/hypr/bindings.conf`):
   ```bash
   nano ~/.config/hypr/bindings.conf
   ```

2. Añade la siguiente línea:
   ```ini
   # Qwen3-ASR Dictation Shortcut (Toggle)
   bindd = SUPER SHIFT, I, Voice Dictation, exec, /home/alex/.local/bin/dictate.py
   ```

3. Guarda el archivo y recarga Hyprland (`hyprctl reload`).

---

## 4. Estimación de Costos de la API (OpenRouter)

El costo de transcripción usando `qwen/qwen3-asr-flash-2026-02-10` es de **$0.000035 por segundo** de audio. Aquí tienes una desglose de lo que cuesta usarlo para practicar chino hablado:

| Tiempo de Dictado | Costo estimado en USD |
| :--- | :--- |
| **1 minuto** | `$0.0021` (aproximadamente **0.2 centavos**) |
| **10 minutos** | `$0.021` (aproximadamente **2 centavos**) |
| **1 hora (60 mins)** | `$0.126` (aproximadamente **12.6 centavos**) |
| **10 horas** | `$1.26` (aproximadamente **1.2 dólares**) |

El costo es prácticamente insignificante, lo que te permite hablar y dictar todo el día sin preocuparte por el presupuesto de la API.


