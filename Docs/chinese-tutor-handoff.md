# Handoff Técnico: Arquitectura del Tutor de Chino (Hermes + Obsidian)
**Versión:** 1.0
**Fecha:** 2026-05-27
**Destinatario:** IA de IDE (Cursor/Copilot/Claude Code)
**Propietario:** Usuario (principiante en Obsidian/frontmatter, requiere robustez automática)

---

## 1. Resumen Ejecutivo

Se migra de un sistema de tablas planas y un solo archivo de vocabulario a una **arquitectura de base de datos distribuida basada en Markdown** dentro de Obsidian.

**Filosofía clave:**
- **Frontmatter ligero** en fichas principales (máximo 20-30 líneas de YAML). Dataview filtra aquí.
- **Notas satélite** para contenido que crece: oraciones, errores, textos.
- **Soberanía de datos**: el agente (Hermes) toca campos lingüísticos y multimedia; el usuario toca SRS y notas personales; nunca se pisan.
- **Idempotencia**: si una ficha ya existe, se hace merge seguro, nunca se sobrescribe el progreso del usuario.

---

## 2. Estructura Física del Vault

Crear exactamente esta estructura de carpetas. Las notas `.md` semilla se mueven a sus ubicaciones finales.

```
vault/
├── 00_Meta/
│   ├── guia_tutor_hermes.md
│   ├── schemas/
│   │   └── vocab_schema_v1.md
│   └── skills/
│       └── (skills generadas por Hermes)
├── 01_Vocab/
│   ├── 1_Monosilabos/
│   ├── 2_Bisilabos/
│   ├── 3_Polisilabos/
│   └── 4_Chengyu/
├── 02_Errors/
│   └── errors.md
├── 03_Grammar/
│   └── grammar.md
├── 05_Sentences/
│   └── (generado dinámicamente)
├── 06_Texts/
│   └── (generado dinámicamente)
└── 99_Assets/
    ├── Audios/
    │   ├── Palabras/
    │   │   ├── 1_Monosilabos/
    │   │   ├── 2_Bisilabos/
    │   │   ├── 3_Polisilabos/
    │   │   └── 4_Chengyu/
    │   ├── Oraciones/
    │   └── Textos/
    ├── Imagenes/
    └── Videos/
```

**Reglas de ubicación física:**
- La carpeta de una ficha se determina ÚNICAMENTE por `char_count`:
  - `char_count == 1` -> `01_Vocab/1_Monosilabos/`
  - `char_count == 2` -> `01_Vocab/2_Bisilabos/`
  - `char_count >= 3 AND category != "chengyu"` -> `01_Vocab/3_Polisilabos/`
  - `category == "chengyu"` -> `01_Vocab/4_Chengyu/`

---

## 3. Contrato YAML v2 — Ficha Principal (01_Vocab/)

**REGLA DE ORO:** Frontmatter máximo 25 líneas. Nada de arrays de objetos complejos aquí.

### Campos de Identidad (Agente, autoritativos)

```yaml
word: "沦为"
pinyin: "lúnwéi"
char_count: 2
category: "palabra"
word_type: ["verbo"]
word_type_alt: []
hsk: 6
tocfl: null
frequency: "media"
variant: "淪為"
stroke_count: 7
radical: "氵"
```

### Campos Multimedia (Agente, autoritativos)

Solo strings de rutas. Nunca arrays ni objetos.

```yaml
audio_word: "99_Assets/Audios/Palabras/2_Bisilabos/word_lunwei.mp3"
audio_word_slow: "99_Assets/Audios/Palabras/2_Bisilabos/word_lunwei_slow.mp3"
audio_word_male: null
audio_word_female: null
image_mnemonic: null
image_calligraphy: null
image_etymology: null
```

**Naming convention de archivos de audio:**
- Palabras: `word_{slug}.mp3`, `word_{slug}_slow.mp3`, `word_{slug}_m.mp3`, `word_{slug}_f.mp3`
- Oraciones: `sent_{slug}_{nn}.mp3` (nn = 01, 02...)
- Textos: `text_{slug}_{nn}.mp3`
- Slug = pinyin sin tonos ni espacios, minúsculas, normalizado.

### Campos SRS y Progreso del Usuario (SAGRADOS — Agente NUNCA toca)

```yaml
srs_status: "nuevo"
srs_level: 0
srs_interval: 0
srs_ease: 2.5
srs_due: null
srs_last_review: null
srs_reviews_count: 0
srs_lapses: 0
user_mnemonic: null
user_difficulty: null
user_notes: null
```

### Campos de Administración (Mixtos)

```yaml
created: "2026-05-27"
created_by: "hermes"
modified: "2026-05-27"
modified_by: "hermes"
version: 1
tags: ["hsk6", "verbo", "formal"]
source_session: "sess_20260527_1422"
source_lesson: "HSK6_U12_Degradacion"
```

---

## 4. Notas Satélite

### 4.1 Oraciones de Ejemplo (`05_Sentences/`)

Cada oración es una nota individual. Archivo: `sent_{slug}_{nn}.md`.

```yaml
---
sentence: "他最终沦为街头乞丐。"
pinyin: "Tā zuìzhōng lúnwéi jiētóu qǐgài."
translation: "Finalmente se redujo a mendigo de la calle."
target_word: "沦为"
audio: "99_Assets/Audios/Oraciones/sent_lunwei_01.mp3"
context: "Degradación personal"
hsk_level: 6
register: "formal"
tags: ["oracion", "hsk6", "degradacion"]
created: "2026-05-27"
created_by: "hermes"
---
```

Cuerpo: `![[sent_lunwei_01.mp3]]`

### 4.2 Registro de Errores (`02_Errors/`)

Notas individuales: `err_{slug}_{YYYYMMDD}.md`.

```yaml
---
date: "2026-05-20"
target_word: "沦为"
error_type: "confusion_grafemica"
mistake: "Escribió 纶为 en lugar de 沦为"
context: "Escritura libre"
created_by: "user"
---
```

---

## 5. Reglas de Soberanía y Merge Idempotente

### 5.1 Clasificación de campos

```python
AGENT_KEYS = [
    'word', 'pinyin', 'pinyin_toned', 'char_count', 'category',
    'word_type', 'word_type_alt', 'hsk', 'tocfl', 'frequency',
    'variant', 'stroke_count', 'radical',
    'audio_word', 'audio_word_slow', 'audio_word_male', 'audio_word_female',
    'image_mnemonic', 'image_calligraphy', 'image_etymology',
    'created', 'created_by', 'source_session', 'source_lesson', 'version'
]

USER_SOVEREIGN_KEYS = [
    'srs_status', 'srs_level', 'srs_interval', 'srs_ease',
    'srs_due', 'srs_last_review', 'srs_reviews_count',
    'srs_lapses', 'user_mnemonic', 'user_difficulty', 'user_notes'
]

MIXED_KEYS = {
    'tags': 'union',
    'modified': 'timestamp',
    'modified_by': 'last_actor'
}
```

### 5.2 Algoritmo de Merge

```python
def write_or_merge_ficha(word_data: dict, actor: str = "hermes"):
    folder = resolve_folder(word_data['char_count'], word_data['category'])
    filepath = f"{folder}/{word_data['word']}.md"

    if os.path.exists(filepath):
        existing_fm, existing_body = parse_frontmatter_and_body(filepath)
        merged_fm = {}

        # 1. Agente sobrescribe sus campos
        for key in AGENT_KEYS:
            if key in word_data:
                merged_fm[key] = word_data[key]

        # 2. Campos sagrados del usuario se preservan
        for key in USER_SOVEREIGN_KEYS:
            if key in existing_fm:
                merged_fm[key] = existing_fm[key]
            elif key in word_data and key not in existing_fm:
                merged_fm[key] = word_data[key]

        # 3. Merge inteligente de mixtos
        if 'tags' in existing_fm or 'tags' in word_data:
            existing_tags = set(existing_fm.get('tags', []))
            new_tags = set(word_data.get('tags', []))
            merged_fm['tags'] = sorted(list(existing_tags | new_tags))

        # 4. Metadatos de modificación
        merged_fm['modified'] = datetime.now().strftime("%Y-%m-%d")
        merged_fm['modified_by'] = actor

        # 5. Cuerpo Markdown NUNCA se toca
        write_file(filepath, merged_fm, existing_body)

    else:
        # Creación nueva
        word_data['created'] = datetime.now().strftime("%Y-%m-%d")
        word_data['created_by'] = actor
        word_data['modified'] = word_data['created']
        word_data['modified_by'] = actor
        word_data['version'] = 1

        defaults = {
            'srs_status': 'nuevo', 'srs_level': 0, 'srs_interval': 0,
            'srs_ease': 2.5, 'srs_due': None, 'srs_last_review': None,
            'srs_reviews_count': 0, 'srs_lapses': 0,
            'user_mnemonic': None, 'user_difficulty': None, 'user_notes': None
        }
        for k, v in defaults.items():
            word_data.setdefault(k, v)

        body = generate_default_body(word_data)
        write_file(filepath, word_data, body)

    # 6. Notas satélite (siempre nuevas, nunca merge)
    for i, sent in enumerate(word_data.get('sentences', []), 1):
        sent_path = f"05_Sentences/sent_{slugify(word_data['word'])}_{i:02d}.md"
        if not os.path.exists(sent_path):
            write_sentence_note(sent_path, sent, target_word=word_data['word'])
            append_link_to_ficha(filepath, sent_path)
```

### 5.3 Reglas de parseo YAML

- Usar `python-frontmatter` o `ruamel.yaml`.
- Nunca regex para parsear frontmatter.
- Si YAML corrupto: backup con `.backup.{timestamp}` y recrear.

---

## 6. Especificación para vault_write.py

### Funciones requeridas

```python
def resolve_folder(char_count: int, category: str) -> str:
    if category == "chengyu":
        return "01_Vocab/4_Chengyu"
    mapping = {1: "1_Monosilabos", 2: "2_Bisilabos"}
    return f"01_Vocab/{mapping.get(char_count, '3_Polisilabos')}"

def slugify(pinyin: str) -> str:
    # Quitar tonos, espacios, minúsculas
    pass

def generate_default_body(word_data: dict) -> str:
    # Plantilla markdown con título, audio, definiciones, colocaciones, links oraciones
    pass

def write_sentence_note(filepath: str, sentence: dict, target_word: str):
    pass

def append_link_to_ficha(ficha_path: str, note_path: str):
    # Añade wikilink [[...]] a sección de oraciones, evita duplicados
    pass
```

### Generación de audio TTS

- Siempre generar `audio_word` (velocidad normal).
- Generar `audio_word_slow` si `hsk >= 4` o si usuario lo solicita.
- Generar 2-3 oraciones de ejemplo con audio en `99_Assets/Audios/Oraciones/`.
- Guardar rutas relativas al vault root.

---

## 7. Actualización de system_prompt.txt

Añadir estas reglas al system prompt:

```
## Reglas de escritura en el Vault de Obsidian

1. Estructura física según char_count:
   - 1 carácter -> 01_Vocab/1_Monosilabos/
   - 2 caracteres -> 01_Vocab/2_Bisilabos/
   - 3+ caracteres (no chengyu) -> 01_Vocab/3_Polisilabos/
   - Chengyu -> 01_Vocab/4_Chengyu/

2. Frontmatter YAML: Usar ÚNICAMENTE campos de vocab_schema_v1. Nunca inventar campos nuevos. Nunca arrays de objetos complejos en frontmatter de ficha principal.

3. Soberanía de datos:
   - NUNCA modificar campos que empiecen con srs_ o user_.
   - Si ficha existe, solo actualizar campos lingüísticos y multimedia. Preservar cuerpo Markdown existente.

4. Notas satélite: Las oraciones de ejemplo deben crearse como notas individuales en 05_Sentences/ y vincularse con wikilinks [[...]] desde la ficha principal.

5. Audio: Generar audio TTS para palabra y 2-3 oraciones de ejemplo. Guardar en 99_Assets/Audios/ con naming convention definida.

6. Tags: Usar tags estandarizados: hsk{N}, {categoria_gramatical}, {register}. Ej: hsk6, verbo, formal.
```

---

## 8. Ejemplo Completo — Caso Real: 沦为

### Ficha principal
**Archivo:** `01_Vocab/2_Bisilabos/沦为.md`

```markdown
---
word: 沦为
pinyin: lúnwéi
char_count: 2
category: palabra
word_type: [verbo]
word_type_alt: []
hsk: 6
tocfl: null
frequency: media
variant: 淪為
stroke_count: 7
radical: 氵
audio_word: "99_Assets/Audios/Palabras/2_Bisilabos/word_lunwei.mp3"
audio_word_slow: "99_Assets/Audios/Palabras/2_Bisilabos/word_lunwei_slow.mp3"
audio_word_male: null
audio_word_female: null
image_mnemonic: null
image_calligraphy: null
image_etymology: null
srs_status: nuevo
srs_level: 0
srs_interval: 0
srs_ease: 2.5
srs_due: null
srs_last_review: null
srs_reviews_count: 0
srs_lapses: 0
user_mnemonic: null
user_difficulty: null
user_notes: null
created: "2026-05-27"
created_by: hermes
modified: "2026-05-27"
modified_by: hermes
version: 1
tags: [hsk6, verbo, formal]
source_session: "sess_20260527_1422"
source_lesson: "HSK6_U12_Degradacion"
---

# 沦为 (lúnwéi)

**Audio:** ![[word_lunwei.mp3]] | *Lento:* ![[word_lunwei_slow.mp3]]

### Definiciones
- **Reducirse a; degenerar en** (formal, política/literatura)

### Colocaciones
- 沦为奴隶
- 沦为笑柄
- 沦为附庸

### Oraciones de ejemplo
- [[sent_lunwei_01|他最终沦为街头乞丐。]]
- [[sent_lunwei_02|那个国家沦为殖民地。]]
```

### Nota satélite de oración
**Archivo:** `05_Sentences/sent_lunwei_01.md`

```markdown
---
sentence: "他最终沦为街头乞丐。"
pinyin: "Tā zuìzhōng lúnwéi jiētóu qǐgài."
translation: "Finalmente se redujo a mendigo de la calle."
target_word: "沦为"
audio: "99_Assets/Audios/Oraciones/sent_lunwei_01.mp3"
context: "Degradación personal"
hsk_level: 6
register: formal
tags: [oracion, hsk6, degradacion]
created: "2026-05-27"
created_by: hermes
---

![[sent_lunwei_01.mp3]]
```

### Escenario de merge
Usuario edita y añade:
```yaml
user_mnemonic: "沦 = agua (氵) que te arrastra hacia abajo = degradación"
srs_status: "aprendizaje"
srs_level: 2
srs_due: "2026-05-30"
```

Hermes vuelve y quiere añadir colocación `沦为殖民地`. El merge debe:
- Añadir la colocación al cuerpo Markdown.
- Preservar `user_mnemonic`, `srs_status`, `srs_level`, `srs_due` intactos.
- Actualizar `modified` y `modified_by`.

---

## 9. Checklist de Implementación

- [ ] Crear estructura de carpetas física en el vault.
- [ ] Mover archivos semilla a ubicaciones finales.
- [ ] Crear `00_Meta/schemas/vocab_schema_v1.md` con este documento.
- [ ] Implementar `resolve_folder()` en `vault_write.py`.
- [ ] Implementar `slugify()` para naming de archivos de audio.
- [ ] Implementar parser/escritor de frontmatter con `python-frontmatter`.
- [ ] Implementar `write_or_merge_ficha()` con merge idempotente.
- [ ] Implementar `write_sentence_note()` para notas satélite.
- [ ] Implementar `append_link_to_ficha()` para wikilinks sin duplicados.
- [ ] Implementar generación de audio TTS con rutas correctas.
- [ ] Actualizar `system_prompt.txt` con las 6 reglas.
- [ ] Crear ficha de prueba (`沦为`) y verificar Dataview filtra por `word_type` y `hsk`.
- [ ] Test de merge: crear ficha, simular edición usuario en SRS, ejecutar escritura agente, verificar preservación.

---

## 10. Notas para el Usuario

- No tocar el frontmatter manualmente salvo campos `user_` o `srs_`. Para notas personales usar `user_notes` o el cuerpo libre.
- Dataview es plugin de comunidad. Instalar desde Configuración > Plugins de comunidad.
- Git como backup: Configurar Git en el vault. Cada ficha es texto plano; Git maneja esto perfectamente.
- Mobile: Las notas satélite mantienen el frontmatter pequeño, mejorando performance en iOS/Android.

---

**Fin del handoff.**
