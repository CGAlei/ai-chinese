# Walkthrough de la Implementación de Qwen3-ASR

Hemos completado y validado exitosamente el nuevo script de transcripción y alineación de audio en chino **`mksession-q.py`**. Este script implementa la lógica de **Qwen3-ASR** y **Qwen3-ForcedAligner** de forma independiente a la versión actual de WhisperX, asegurando una compatibilidad completa con el resto de las herramientas de la plataforma.

---

## Cambios Realizados

1.  **Dependencias del Proyecto:**
    *   Modificado el archivo [pyproject.toml](file:///home/alex/Ai-chinese/pyproject.toml) para agregar `qwen-asr` como dependencia oficial.
    *   Ejecutado `uv sync` para sincronizar el entorno virtual.

2.  **Nuevo Script de Transcripción:**
    *   Creado [mksession-q.py](file:///home/alex/Ai-chinese/mksession-q.py) para encapsular la lógica de transcripción local y online mediante Qwen3.
    *   **Protección contra CUDA OOM (Lógica Secuencial y en Chunks):**
        Dado que la GPU RTX 3050 Ti Laptop cuenta con **4GB de VRAM**, cargar simultáneamente el modelo de transcripción y el alineador (~2.4 GB total) causa inmediatamente un desbordamiento de memoria. Para solucionar esto:
        *   El script divide el audio de entrada en **chunks de 30 segundos** antes de realizar la transcripción (usando `split_audio_into_chunks` de `qwen-asr` de forma nativa).
        *   Carga en memoria únicamente el modelo ASR (`Qwen3ASRModel-0.6B`) y procesa los chunks uno por uno.
        *   Una vez terminada la transcripción, el modelo ASR se descarga de memoria usando recolector de basura (`gc.collect()`) y liberando la caché de PyTorch (`torch.cuda.empty_cache()`).
        *   A continuación, se carga individualmente el alineador (`Qwen3-ForcedAligner-0.6B`) en GPU para alinear el texto de cada chunk con su audio correspondiente, aplicando una compensación de tiempo (`offset_sec`) para reconstruir la línea de tiempo absoluta del audio completo.
        *   Finalmente, el alineador se descarga de la misma forma para dejar la GPU completamente libre.
    *   **Procesamiento de Texto y Compatibilidad de Esquema:**
        *   Mantiene la conversión Traditional-to-Simplified usando `opencc`.
        *   Agrupa las marcas de tiempo de caracteres individuales en marcas de tiempo a nivel de palabra utilizando la segmentación robusta de `jieba`.
        *   Guarda la estructura del JSON resultante de forma idéntica a la generada por `mksession.py` (con campos `segments` y `word_segments`), asegurando compatibilidad del 100% con los visores del proyecto (como `Mo-Reader.html`).

---

## Guía de Uso: Cómo ejecutar el comando

Al igual que con el script anterior, debes ejecutarlo desde el directorio raíz del proyecto (`/home/alex/Ai-chinese`) usando `uv run` para asegurar que cargue las dependencias correctas del entorno virtual.

### Comando Básico
Para transcribir un archivo de audio en local usando el modelo predeterminado de **0.6B** en GPU (`cuda`):
```bash
uv run mksession-q.py ruta/al/audio.mp3
```

---

### Opciones y Parámetros Disponibles

El script admite los siguientes argumentos y banderas en la línea de comandos:

#### 1. Archivo de Audio (Requerido)
*   **Sintaxis:** `ruta/al/audio.mp3` (o `.wav`, `.m4a`, etc.)
*   **Descripción:** La ruta local del archivo que deseas transcribir. El archivo JSON resultante se guardará en la misma carpeta con el mismo nombre (ej. `audio.json`).

#### 2. Selección de Modelo (`--model`)
*   **Sintaxis:** `--model {0.6b, 1.7b}`
*   **Predeterminado:** `0.6b`
*   **Descripción:**
    *   `0.6b` (Recomendado): Carga el modelo ligero. Es muy rápido y seguro contra errores de falta de memoria (OOM).
    *   `1.7b`: Carga el modelo de 1.7B parámetros. Ofrece mayor precisión en audios complejos o con ruido, pero requiere casi toda la VRAM libre de tu tarjeta gráfica.

#### 3. Selección de Dispositivo (`--device`)
*   **Sintaxis:** `--device {cuda, cpu}`
*   **Predeterminado:** `cuda`
*   **Descripción:**
    *   `cuda`: Intenta usar la GPU NVIDIA. Si CUDA no está disponible, o si la tarjeta gráfica experimenta falta de memoria (OOM) o errores durante la ejecución/carga del modelo ASR o del Aligner, el script liberará de inmediato los recursos y realizará un **fallback automático y transparente a la CPU** para completar el procesamiento.
    *   `cpu`: Fuerza el procesamiento en el procesador. Útil si deseas mantener la GPU totalmente libre para otras tareas (tardará más tiempo).

#### 4. Modo Online / Transcripción en Nube (`--online`)
*   **Sintaxis:** `--online`
*   **Descripción:** En lugar de ejecutar los modelos Qwen locales en tu máquina, realiza una consulta a la API online de OpenAI Whisper (`whisper-1`) utilizando la clave de API definida en tu archivo `.env`. Ideal para cuando necesitas procesar audios extremadamente largos o si no quieres sobrecargar la máquina local.

#### 5. Carpeta de Salida (`--output-dir`)
*   **Sintaxis:** `--output-dir ruta/a/la/carpeta`
*   **Predeterminado:** Ninguno (guarda el archivo JSON en el mismo directorio que el archivo de audio).
*   **Descripción:** Permite especificar una carpeta distinta donde guardar el archivo JSON resultante (ej. la carpeta de trabajo actual).

---

### Ejemplos Prácticos

*   **Uso estándar local (rápido y optimizado para VRAM):**
    ```bash
    uv run mksession-q.py ./Sessions/testing/test/liu.mp3
    ```
*   **Uso local con el modelo más preciso (requiere GPU libre):**
    ```bash
    uv run mksession-q.py ./Sessions/testing/test/liu.mp3 --model 1.7b
    ```
*   **Uso forzando procesamiento en CPU (sin usar GPU):**
    ```bash
    uv run mksession-q.py ./Sessions/testing/test/liu.mp3 --device cpu
    ```
*   **Uso en la nube (OpenAI API - rápido, sin consumo local):**
    ```bash
    uv run mksession-q.py ./Sessions/testing/test/liu.mp3 --online
    ```

---

## Corrección de Errores: Alineación de Palabras No Chinas y Puntuación

Durante las pruebas, se detectaron dos problemas importantes:
1. **Pérdida de Sincronización en Palabras No Chinas:** En palabras en inglés con espacios y paréntesis (ej. `（Peter Thiel）`), el alineador eliminaba los espacios y paréntesis (dejando `PeterThiel`). Al carecer de coincidencia con la cadena de texto original, el lector de karaoke en el frontend se desfasaba.
2. **Pérdida de Puntuación:** Los signos de puntuación se descartaban o perdían sus marcas de tiempo en el flujo de alineación, por lo que no se mostraban en el visor HTML.

### Solución Implementada:
* **Mapeo Inteligente con `reconstruct_aligned_words`:** Implementamos un algoritmo en Python que recorre la transcripción completa del audio carácter por carácter. Empareja los caracteres o palabras habladas con los tiempos provistos por el alineador de Qwen3/OpenAI, e intercala de forma dinámica los caracteres silenciosos (como espacios, comas, puntos y paréntesis) en sus posiciones relativas correctas, asignándoles marcas de tiempo coherentes sin alterar la sincronización del audio.
* **Actualización en `group_chars_into_words`:** Modificamos la lógica de segmentación para procesar únicamente secuencias continuas de caracteres chinos (usando una detección por rango Unicode de caracteres CJK). Los elementos no chinos (palabras en inglés completas, espacios y signos de puntuación con marcas de tiempo interpoladas) se mantienen intactos con su grafía y tiempos originales.
* **Integración Global:** Conectamos esta lógica de reconstrucción tanto en el pipeline local de Qwen3 como en el fallback online de OpenAI Whisper.

---

## Validación y Pruebas Realizadas

1. **Prueba Inicial de Rendimiento:**
   Se transcribió exitosamente `./Sessions/testing/test/liu.mp3` (duración: **477.1 segundos**, ~8 minutos) usando la GPU local (RTX 3050 Ti Mobile) en modo secuencial por chunks de 30 segundos, sin alertas de memoria (OOM).

2. **Prueba de Corrección de Alineación y Puntuación (Argentina Session):**
   Ejecutamos la transcripción y alineación del archivo de larga duración:
   ```bash
   uv run mksession-q.py Sessions/Argentina/算法噩梦/算法噩梦.mp3
   ```
   * **Duración:** 781.2 segundos (13 minutos).
   * **Comportamiento en GPU:** Ejecutó sin problemas, cargando secuencialmente ASR y Forced Aligner en 26 chunks de 30 segundos.
   * **Verificación de Salida JSON ([算法噩梦.json](file:///home/alex/Ai-chinese/Sessions/Argentina/算法噩梦/算法噩梦.json)):**
     * Los signos de puntuación como `，`, `。`, `（` y `）` se guardaron correctamente en la lista de palabras final con marcas de tiempo válidas (ej. `（` con `start: 10.16` y `end: 10.48`).
     * Las palabras en inglés se preservaron con sus espacios correspondientes (ej. `"Peter"` y `"Thiel"` separados por `" "` con marcas de tiempo precisas).
     * El esquema es 100% compatible con `Mo-Reader.html` y `Editor.html`, logrando que el lector de karaoke se mantenga sincronizado durante toda la sesión.

---

## Ejecución Global mediante el comando `mks-q`

Para facilitar la ejecución desde cualquier carpeta y evitar problemas con rutas relativas, se ha creado un comando global llamado **`mks-q`** en `/home/alex/.local/bin/mks-q`.

Este comando:
1. Resuelve de forma automática el entorno virtual de `uv` en `/home/alex/Ai-chinese`.
2. Ejecuta el script `mksession-q.py` pasando todos los parámetros recibidos.
3. **Guarda el JSON de salida en la carpeta de trabajo actual** (donde se ejecuta el comando) en lugar de junto al archivo de audio.

### Ejemplo de uso global:
Si estás en una carpeta de tu preferencia y deseas procesar un audio, puedes ejecutar:
```bash
mks-q /home/alex/Ai-chinese/Sessions/Philosophy/抛弃导师做自己的引路人/抛弃导师做自己的引路人.m4a --online
```
El archivo `抛弃导师做自己的引路人.json` se guardará directamente en la carpeta donde estás ejecutando tu terminal.

## Integración Online de Coe con OpenRouter (Qwen3-ASR-Flash)

Para habilitar el dictado por voz en tiempo real sin saturar los recursos de hardware de tu sistema local (GPU de 4GB y CPU), se ha configurado la herramienta de dictado **Coe** (`quailyquaily/coe`) para comunicarse directamente con la API online de **OpenRouter** utilizando el modelo de Alibaba **`qwen/qwen3-asr-flash-2026-02-10`**.

Esto ofrece precisión máxima, latencia de respuesta sub-segundo y un consumo de 0% de CPU y GPU local.

### 1. Instalación de Coe
Para descargar e instalar el cliente de `coe` en tu ruta de usuario local (`~/.local/bin`):
```bash
curl -fsSL -o /tmp/install.sh https://raw.githubusercontent.com/quailyquaily/coe/refs/heads/master/scripts/install.sh
bash /tmp/install.sh
```

### 2. Configuración en la Nube
Crea o edita tu archivo de configuración en `~/.config/coe/config.yaml` para apuntar a la API de OpenRouter:

```yaml
asr:
  provider: qwen3-asr-vllm
  endpoint: https://openrouter.ai/api/v1/chat/completions
  model: qwen/qwen3-asr-flash-2026-02-10
  api_key: "TU_CLAVE_DE_OPENROUTER_AQUÍ"

llm:
  provider: openai
  endpoint: https://openrouter.ai/api/v1/chat/completions
  model: qwen/qwen-2.5-72b-instruct  # O el modelo de limpieza de tu preferencia
  api_key: "TU_CLAVE_DE_OPENROUTER_AQUÍ"
```

### 3. Diagnóstico e Inicio del Cliente
Una vez configurado, puedes verificar el estado de conexión del cliente ejecutando:
```bash
coe doctor
```
