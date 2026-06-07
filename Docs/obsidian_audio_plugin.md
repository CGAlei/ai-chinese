# Guía de Instalación y Uso: MemoryWiki Audio Recorder (Obsidian)

El plugin **MemoryWiki Audio Recorder** te permite grabar el audio interno del sistema (como la pronunciación hablada por Qwen u otros LLM) directamente desde Obsidian e insertarla en la posición activa de tu cursor mediante un único botón visual (🎙️).

---

## 📌 Requisitos Previos

1. **Servidor MemoryWiki Activo**: El backend de FastAPI debe estar ejecutándose en `http://localhost:8082` (controlado por systemd con `systemctl --user start ai-chinese-server`).
2. **FFmpeg**: El binario `ffmpeg` debe estar instalado en el sistema operativo (confirmado en tu sistema Arch Linux).
3. **Dispositivo PulseAudio**: El archivo `.env` debe apuntar al dispositivo loopback correcto (por defecto `alsa_output.pci-0000_00_1b.0.analog-stereo.monitor`).

---

## 🚀 Instalación en una Nueva Bóveda o Computadora

El plugin consta de tres archivos básicos (`manifest.json`, `main.js`, y `styles.css`) ubicados en tu carpeta `.obsidian/plugins/memorywiki-audio/`.

Para instalarlo o clonarlo en una nueva bóveda de Obsidian, ejecuta el siguiente comando en la terminal:

```bash
# 1. Crear el directorio de plugins en tu nueva bóveda
mkdir -p "/ruta/a/tu/nueva-boveda/.obsidian/plugins/memorywiki-audio"

# 2. Copiar los archivos del plugin desde el repositorio origen
cp -r "/home/alex/Ai-chinese/MemoryWiki/vault/nemotecnia/.obsidian/plugins/memorywiki-audio/"* "/ruta/a/tu/nueva-boveda/.obsidian/plugins/memorywiki-audio/"
```

### Activación en Obsidian:
1. Abre **Obsidian** y entra en la nueva bóveda.
2. Ve a **Ajustes** -> **Plugins de la comunidad** (Community Plugins).
3. Haz clic en el botón **Recargar** (Reload) al lado de "Plugins instalados".
4. Busca **"MemoryWiki Audio Recorder"** en la lista y actívalo.

---

## 🛠️ Guía de Uso Rápido

1. Abre cualquier nota de vocabulario en Obsidian (ej: `明白.md`).
2. Coloca el **cursor** de texto en la línea donde deseas que se incruste el reproductor de audio.
3. Haz un clic sobre el icono de **Micrófono (🎙️)** en la barra lateral izquierda de Obsidian.
   * El icono cambiará a color **rojo parpadeante**, indicando que la grabación del escritorio ha comenzado.
4. Cambia al panel de Qwen (en el panel derecho o navegador) y reproduce el audio de la pronunciación.
5. Haz clic de nuevo en el icono del micrófono (🎙️) para detener la grabación.
   * El archivo se guardará en `unified-words/audio/` y el enlace `![[unified-words/audio/nombre_audio.mp3]]` se insertará automáticamente en tu cursor.

---

## 🔍 Solución de Problemas (Troubleshooting)

### El micrófono no cambia a rojo y muestra un error de conexión
* **Causa**: El servidor backend de MemoryWiki está apagado.
* **Solución**: Levanta el servidor desde tu terminal con:
  ```bash
  systemctl --user restart ai-chinese-server
  ```

### El audio grabado se escucha muy bajo
* **Causa**: La mezcla de monitor de PulseAudio tiene ganancia baja.
* **Solución**: Edita tu archivo `generator/.env`, incrementa el valor de `AUDIO_RECORD_VOLUME_BOOST` (ej: a `2.0` o `2.5`) y reinicia el servidor:
  ```bash
  systemctl --user restart ai-chinese-server
  ```

### El audio grabado está completamente en silencio
* **Causa**: El nombre del monitor de audio ha cambiado en tu sistema Arch Linux.
* **Solución**: 
  1. Lista tus fuentes de audio disponibles ejecutando en terminal:
     ```bash
     pactl list sources | grep -i monitor
     ```
  2. Copia el nombre del dispositivo de salida activo (monitor).
  3. Abre `generator/.env` y actualiza la variable `PULSE_AUDIO_DEVICE` con el nuevo nombre.
  4. Reinicia el servidor.
