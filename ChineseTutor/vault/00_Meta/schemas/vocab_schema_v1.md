# Contrato YAML v2: Esquema de Vocabulario para Tutor de Chino (Hermes + Obsidian)

Este documento contiene la especificación oficial del esquema y comportamiento de los archivos de notas en la sección `01_Vocab/`.

## 1. Reglas de Frontmatter YAML de las Fichas

El Frontmatter de cada nota de vocabulario (ej: `沦为.md`) no debe exceder las 30 líneas de texto. Se clasifica en campos autoritativos del agente, campos sagrados del usuario (SRS) y campos mixtos.

### Campos de Identidad (Agente, autoritativos)
*   `word` (string): Caracteres de la palabra (ej. "沦为").
*   `pinyin` (string): Pinyin normalizado sin tonos ni espacios para búsquedas y slugs (ej. "lunwei").
*   `pinyin_toned` (string): Pinyin con marcas de tonos claras (ej. "lúnwéi").
*   `char_count` (int): Cantidad de caracteres (1, 2, 3, etc.).
*   `category` (string): Categoría (ej. "palabra", "caracter", "chengyu").
*   `word_type` (array de strings): Clases gramaticales en minúsculas (ej. `[verbo]`, `[adjetivo]`, `[sustantivo]`).
*   `word_type_alt` (array de strings): Clases gramaticales alternativas si las hay.
*   `hsk` (int/null): Nivel HSK (1 a 6 o null).
*   `tocfl` (int/null): Nivel TOCFL (1 a 6 o null).
*   `frequency` (string): Frecuencia de uso (ej. "alta", "media", "baja").
*   `variant` (string/null): Caracteres tradicionales o variantes (ej. "淪為").
*   `stroke_count` (int): Cantidad de trazos del carácter principal o palabra.
*   `radical` (string): Radical del carácter principal (ej. "氵").

### Campos Multimedia (Agente, autoritativos)
*   `audio_word` (string): Ruta relativa del audio de pronunciación normal.
*   `audio_word_slow` (string): Ruta relativa del audio de pronunciación lenta.
*   `audio_word_male` (string/null): Ruta al audio con voz masculina si está disponible.
*   `audio_word_female` (string/null): Ruta al audio con voz femenina si está disponible.
*   `image_mnemonic` (string/null): Ruta a imágenes mnemotécnicas.
*   `image_calligraphy` (string/null): Ruta a diagramas de caligrafía.
*   `image_etymology` (string/null): Ruta a diagramas de evolución filológica.

### Campos SRS y Progreso del Usuario (SAGRADOS — El agente NUNCA los sobrescribe)
*   `srs_status` (string): Estado de aprendizaje (ej. "nuevo", "aprendizaje", "graduado").
*   `srs_level` (int): Nivel de SRS.
*   `srs_interval` (int): Intervalo de repaso en días.
*   `srs_ease` (float): Factor de facilidad de repaso (por defecto 2.5).
*   `srs_due` (string/null): Fecha de próximo repaso (YYYY-MM-DD).
*   `srs_last_review` (string/null): Fecha del último repaso.
*   `srs_reviews_count` (int): Contador de repasos realizados.
*   `srs_lapses` (int): Contador de olvidos o fallos.
*   `user_mnemonic` (string/null): Mnemotecnia escrita por el usuario.
*   `user_difficulty` (string/null): Dificultad percibida por el usuario.
*   `user_notes` (string/null): Notas adicionales del usuario.

### Campos de Administración (Mixtos)
*   `created` (string): Fecha de creación (YYYY-MM-DD).
*   `created_by` (string): Autor ("hermes" o "user").
*   `modified` (string): Fecha de última modificación (YYYY-MM-DD).
*   `modified_by` (string): Último autor en editar.
*   `version` (int): Versión del esquema del archivo.
*   `tags` (array de strings): Etiquetas asociadas (unión entre etiquetas previas y nuevas).
*   `source_session` (string): ID de sesión origen de Hermes.
*   `source_lesson` (string/null): Lección o tema asociado.

---

## 2. Naming Conventions y Rutas Físicas

*   Las carpetas se determinan por el número de caracteres (`char_count`):
    *   `1` $\rightarrow$ `01_Vocab/1_Monosilabos/`
    *   `2` $\rightarrow$ `01_Vocab/2_Bisilabos/`
    *   `>= 3` (no chengyu) $\rightarrow$ `01_Vocab/3_Polisilabos/`
    *   `Chengyu` $\rightarrow$ `01_Vocab/4_Chengyu/`
*   Los nombres de archivos de audio se normalizan eliminando diacríticos del pinyin:
    *   `word_{slug}.mp3` para velocidad normal.
    *   `word_{slug}_slow.mp3` para velocidad lenta.
