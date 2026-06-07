### Guía del Tutor de Chino: Instalación, Operación y Migración Completa de Hermes Agent

> [!NOTE]
> Esta guía detalla paso a paso todo lo realizado para poner en marcha el framework **Hermes Agent** optimizado como Tutor de Chino con memoria episódica e integración local, y cómo replicarlo o respaldarlo en otra computadora desde cero.

---

## 1. Qué Hemos Creado (Resumen del Sistema)

> [!NOTE]
> Hemos configurado un asistente de idiomas agéntico autónomo que opera bajo un bucle **ReAct** (Pensamiento $\rightarrow$ Acción $\rightarrow$ Observación). El tutor no solo chatea, sino que consulta y edita tu base de conocimientos en tiempo real a través de comandos de terminal invisibles.
> 
> El sistema se compone de:
> 
> *   **El motor:** Hermes Agent configurado para usar la API gratuita de **Google Gemini 3.5 Flash** (rápida, contexto de 1 millón de tokens y excelente soporte para chino).
> 
> *   El Baúl (Vault) de Notas:** Una estructura limpia de archivos Markdown en `vault/` (`vocab.md`, `errors.md` y `grammar.md`).
>  
> *   **Las Herramientas en Python (`tools/`):**
>     *   `vault_search.py`: Busca términos y coincidencias dentro del Vault de notas.
>     *   `vault_write.py`: Permite al agente registrar vocabulario, guardar notas gramaticales y registrar errores cometidos.
>     *   `history.py`: Accede directamente a la base de datos de Hermes para buscar o recuperar transcripciones completas de chats pasados (Memoria Episódica).

---

## 2. Cómo Empezar Desde Cero (Nueva Instalación)

Si necesitas instalar este sistema en una nueva máquina (basada en Arch Linux / Omarchy), sigue estos pasos ordenados:

### Paso 2.1: Prerrequisitos de Sistema

Actualiza los repositorios e instala las herramientas base de compilación, Python, Git y Node.js:

```bash
sudo pacman -Syu
sudo pacman -S --needed base-devel python python-pip git nodejs npm
```

### Paso 2.2: Instalación de Hermes Agent

Descarga e instala el framework usando el instalador oficial de Nous Research (instala dependencias de forma local y configura el entorno virtual con `uv` aisladamente):

```bash
curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash
```

Añade el binario local al `PATH` recargando tu archivo de terminal:

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.bashrc 2>/dev/null || source ~/.zshrc
```

### Paso 2.3: Configurar Claves y Modelos (Google Gemini)

1. Ve a [Google AI Studio](https://aistudio.google.com/) y genera una API Key gratuita.
2. Abre el archivo de secretos en tu editor:

   ```bash
   nano ~/.hermes/.env
   ```

3. Configura tu clave en la línea correspondiente:

   ```text
   GOOGLE_API_KEY=Tu_Clave_API_De_Google_Aqui
   GEMINI_API_KEY=Tu_Clave_API_De_Google_Aqui
   ```

4. Edita la configuración del modelo de Hermes en `~/.hermes/config.yaml` para establecer el proveedor nativo de Google Gemini:

   ```yaml
	model:
     default: gemini-3.5-flash
     provider: gemini
     base_url: https://generativelanguage.googleapis.com/v1beta
     api_mode: chat_completions
   ```

---

## 3. Cómo Migrar todo tu Progreso a Otra Computadora (Backup)

Para no perder tu vocabulario, tu historial de chats de tutoría, ni tus configuraciones al cambiar de equipo, debes respaldar y transferir las siguientes carpetas clave:

### Qué Respaldar (Archivos a Copiar)

| Origen en PC Actual          | Qué Contiene                                                                                               | Destino en Nueva PC                         |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| `~/Ai-chinese/ChineseTutor/` | Todo tu espacio de trabajo: notas (`vault/`), scripts de herramientas (`tools/`) y el prompt (`prompts/`). | En la misma ruta o tu carpeta de proyectos. |
| `~/.hermes/config.yaml`      | Tus configuraciones de modelos, plugins y visuales de Hermes.                                              | `~/.hermes/config.yaml`                     |
| `~/.hermes/.env`             | Tus API Keys (Google Gemini, OpenRouter, etc.).                                                            | `~/.hermes/.env`                            |
| `~/.hermes/state.db`         | **Crucial:** La base de datos SQLite con todo tu historial de chats pasados.                               | `~/.hermes/state.db`                        |
| `~/.hermes/SOUL.md`          | El archivo de identidad/persona (Tutor de Chino).                                                          | `~/.hermes/SOUL.md`                         |

### Procedimiento Rápido de Backup (Consola)

1.  **En tu computadora actual (Crear el comprimido de respaldo):**

    ```bash
    # Crear carpeta temporal de backup
    mkdir -p ~/hermes_backup
    
    # Copiar archivos de configuración y base de datos
    cp ~/.hermes/config.yaml ~/hermes_backup/
    cp ~/.hermes/.env ~/hermes_backup/
    cp ~/.hermes/state.db ~/hermes_backup/
    cp ~/.hermes/SOUL.md ~/hermes_backup/ 2>/dev/null || true
    
    # Comprimir el espacio de trabajo del tutor y el backup de configuraciones
    tar -czf ~/tutor_backup_completo.tar.gz -C ~/ Ai-chinese/ChineseTutor -C ~/ hermes_backup
    ```
   
 *Esto generará un archivo `tutor_backup_completo.tar.gz` en tu carpeta personal conteniendo TODO.*

2.  **En tu nueva computadora (Restaurar el respaldo):**
    *   Primero, completa los **Pasos 2.1 y 2.2** de instalación de Hermes en el nuevo equipo.
    *   Copia el archivo `tutor_backup_completo.tar.gz` a la nueva PC.
    *   Descomprime los archivos:
        ```bash
        # Asegurarse de que la carpeta de destino existe
        mkdir -p ~/.hermes
        
        # Descomprimir en sus ubicaciones correspondientes
        tar -xzf tutor_backup_completo.tar.gz -C ~/
        
        # Mover los archivos de configuración desde la carpeta temporal de backup a ~/.hermes/
        cp -r ~/hermes_backup/* ~/.hermes/
        rm -rf ~/hermes_backup
        ```
    *   ¡Listo! Al ejecutar `hermes`, el agente se conectará usando tus llaves, tendrá acceso a tu historial exacto (`state.db`) y podrá seguir leyendo y escribiendo en tu carpeta `ChineseTutor/vault/` restaurada.

---

## 4. Comandos Útiles de Operación Diaria

*   **Chatear con el Tutor (Terminal):**
    ```bash
    hermes
    ```
*   **Iniciar el Servidor Web (Dashboard) en el puerto 9119:**
    ```bash
    hermes dashboard
    ```
*   **Ver el Historial de Tutorías en Terminal (Sin gastar tokens):**
    *   Listar sesiones: `python tools/history.py --list`
    *   Ver un chat específico: `python tools/history.py --session <ID_SESION>`
    *   Buscar un tema en todos los chats del pasado: `python tools/history.py --search "<término>"`
