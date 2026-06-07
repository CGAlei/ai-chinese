# Comandos Rápidos de Audio y Transcripción

Guía rápida para usar los scripts personalizados en `~/.local/bin`.

## 1. Grabación de Audio (`record_audio`)
Graba el audio interno del escritorio directamente a un archivo MP3.

- **Uso básico (guarda como `output.mp3`):**
  ```bash
  record_audio
  ```
- **Especificar nombre de archivo:**
  ```bash
  record_audio mi_clase.mp3
  ```

## 2. Transcripción China (`chread`)
Activa el entorno `whisperx` y transcribe audio a JSON con segmentación de palabras en Chino Simplificado.

- **Uso básico:**
  ```bash
  chread audio.mp3
  ```
- **Con parámetros adicionales (ej. usar CPU):**
  ```bash
  chread audio.mp3 --device cpu
  ```

## 3. Grabación Integrada en Obsidian (Plugin)
Para configurar la grabación de audio de escritorio con un solo clic directamente dentro de las notas de tu bóveda, consulta la [Guía del Plugin de Obsidian](file:///home/alex/Ai-chinese/Docs/obsidian_audio_plugin.md).

---
*Nota: Asegúrate de que los archivos tengan permisos de ejecución con `chmod +x`.*
