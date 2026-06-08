# app/main.py

import os
import re
import asyncio
import json
import datetime
import subprocess
import signal
from typing import Optional, List, Tuple
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.openrouter_client import OpenRouterClient
from app.parser_merge import parse_markdown_note, serialize_note, merge_notes

# Resolve directories
base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Project root directory is 2 levels up from base_dir (services/memory-wiki)
project_root_dir = os.path.abspath(os.path.join(base_dir, "..", ".."))
# The actual Obsidian vault is now in data/vaults/memory-wiki/nemotecnia
vault_dir = os.path.abspath(os.path.join(project_root_dir, "data", "vaults", "memory-wiki", "nemotecnia"))
unified_dir = os.path.join(vault_dir, "unified-words")

CARD_TYPE_TO_SUBFOLDER = {
    "bisilabo": "bisilabos",
    "polisilabo": "polisilabos",
    "chengyu": "polisilabos",
    "comparacion": "comparasiones",
    "estructura": "estructuras gramaticales",
    "correccion_alocucion": "correccion_alocaciones"
}

CARD_TYPE_SECTIONS = {
    "bisilabo": {
        "structured": ["pinyin", "hsk_level", "word_type", "collocations", "synonyms", "antonyms", "examples"],
        "narrative": ["meaning", "synthesis", "radical", "etymology", "mnemonics", "errors", "usage", "notebooklm", "pinyin"]
    },
    "polisilabo": {
        "structured": ["pinyin", "hsk_level", "word_type", "collocations", "synonyms", "antonyms", "examples"],
        "narrative": ["concept", "morphology", "contextual_logic", "register_and_nuance", "spanish_interference", "notebooklm"]
    },
    "chengyu": {
        "structured": ["pinyin", "hsk_level", "word_type", "collocations", "synonyms", "antonyms", "examples"],
        "narrative": ["definition", "classical_origin", "structural_logic", "colloquial_frequency", "pragmatic_errors", "notebooklm"]
    },
    "comparacion": {
        "structured": ["pinyin", "word_type", "examples"],
        "narrative": ["shared_core", "semantic_divergence", "syntactic_distinction", "collocation_matrix", "interference_warning", "comparative_examples", "notebooklm"]
    },
    "estructura": {
        "structured": ["pinyin", "word_type", "examples"],
        "narrative": ["formula", "logical_connection", "syntactic_constraints", "spanish_mismatch", "progressive_examples", "notebooklm"]
    },
    "correccion_alocucion": {
        "structured": [],
        "narrative": ["veredicto_optimizacion", "interferencia_sintactica", "conectores_muletillas", "registro_colocaciones", "aspecto_particulas", "prosodia_ritmo"]
    }
}

def get_clean_filename(word: str) -> str:
    word = word.strip()
    if "," in word or "，" in word:
        parts = [p.strip() for p in re.split(r'[,，]', word) if p.strip()]
        return "_vs_".join(parts)
    return word

def find_word_file(word: str, card_type: Optional[str] = None) -> Tuple[str, str]:
    # Special handling for correccion_alocucion
    if card_type == "correccion_alocucion" or (word.startswith("alocucion_") and len(word) < 50):
        if not (word.startswith("alocucion_") and len(word) < 50):
            import datetime
            date_str = datetime.datetime.now().strftime("%Y%m%d")
            cleaned = "".join(c for c in word if c.isalnum() or '\u4e00' <= c <= '\u9fff')
            suffix = cleaned[:10].strip()
            if suffix:
                filename = f"alocucion_{date_str}_{suffix}"
            else:
                filename = f"alocucion_{date_str}"
        else:
            filename = word
            
        target_dir = os.path.join(unified_dir, "correccion_alocaciones")
        return os.path.join(target_dir, f"{filename}.md"), "correccion_alocucion"

    filename = get_clean_filename(word)
    subdirs = ["bisilabos", "polisilabos", "comparasiones", "estructuras gramaticales", "correccion_alocaciones"]
    
    # CJK character count to accurately classify Chengyu (exactly 4 CJK characters)
    cjk_len = sum(1 for c in filename if '\u4e00' <= c <= '\u9fff')
    
    # If card_type is provided, check its subfolder first (recursively for backward compatibility)
    if card_type and card_type in CARD_TYPE_TO_SUBFOLDER:
        subfolder = CARD_TYPE_TO_SUBFOLDER[card_type]
        target_dir = os.path.join(unified_dir, subfolder)
        if os.path.exists(target_dir):
            for root, _, files in os.walk(target_dir):
                if f"{filename}.md" in files:
                    return os.path.join(root, f"{filename}.md"), card_type

    # Scan all subfolders recursively to find existing file
    for sd in subdirs:
        target_dir = os.path.join(unified_dir, sd)
        if os.path.exists(target_dir):
            for root, _, files in os.walk(target_dir):
                if f"{filename}.md" in files:
                    resolved_path = os.path.join(root, f"{filename}.md")
                    if sd == "bisilabos":
                        return resolved_path, "bisilabo"
                    elif sd == "polisilabos":
                        return resolved_path, "chengyu" if cjk_len == 4 else "polisilabo"
                    elif sd == "comparasiones":
                        return resolved_path, "comparacion"
                    elif sd == "estructuras gramaticales":
                        return resolved_path, "estructura"
                    elif sd == "correccion_alocaciones":
                        return resolved_path, "correccion_alocucion"
            
    # Default path if not found (new file)
    default_ct = card_type or "bisilabo"
    if not card_type:
        if "_" in filename or "vs" in filename or "," in word or "，" in word:
            default_ct = "comparacion"
        elif cjk_len >= 4 and "..." not in filename:
            default_ct = "chengyu" if cjk_len == 4 else "polisilabo"
        elif cjk_len >= 3 and "..." not in filename:
            default_ct = "polisilabo"
        elif "..." in filename:
            default_ct = "estructura"
            
    target_dir = os.path.join(unified_dir, CARD_TYPE_TO_SUBFOLDER.get(default_ct, "bisilabos"))
    return os.path.join(target_dir, f"{filename}.md"), default_ct

def migrate_existing_notes():
    # Make sure all subfolders exist
    for subfolder in CARD_TYPE_TO_SUBFOLDER.values():
        folder_path = os.path.join(unified_dir, subfolder)
        os.makedirs(folder_path, exist_ok=True)
    
    # Move any .md files directly in unified_dir to unified-words/bisilabos/
    if os.path.exists(unified_dir):
        for item in os.listdir(unified_dir):
            item_path = os.path.join(unified_dir, item)
            # Only migrate actual files ending in .md
            if os.path.isfile(item_path) and item.endswith(".md"):
                dest_path = os.path.join(unified_dir, "bisilabos", item)
                print(f"[MIGRATION] Moving {item} to bisilabos/")
                try:
                    os.rename(item_path, dest_path)
                except Exception as e:
                    print(f"[MIGRATION] Error migrating {item}: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    migrate_existing_notes()
    yield

app = FastAPI(title="MemoryWiki Vocabulary Generator", lifespan=lifespan)

# Allow CORS for ease of development/debugging
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup static files directory
static_dir = os.path.join(base_dir, "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

# Mount static files
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Mount web directory for HTML webapps (Mo-Reader, Mo-Cards, etc.)
web_dir = os.path.abspath(os.path.join(project_root_dir, "web"))
app.mount("/app", StaticFiles(directory=web_dir), name="project_root")

class CheckWordRequest(BaseModel):
    word: str
    card_type: Optional[str] = None

class ProcessRequest(BaseModel):
    words: list[str]
    sections: list[str]
    card_type: str = "bisilabo"
    regenerate_all: bool = False
    api_key: Optional[str] = None
    model: Optional[str] = None
    concurrency_limit: int = 2

@app.get("/", response_class=HTMLResponse)
def read_root():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return f.read()
    return """
    <html>
        <head><title>MemoryWiki Generator</title></head>
        <body style="background:#1A1410; color:#F2D4B0; font-family:sans-serif; text-align:center; padding-top:100px;">
            <h1>MemoryWiki Generator</h1>
            <p>El archivo frontend static/index.html no fue encontrado.</p>
        </body>
    </html>
    """

@app.post("/api/check-word")
async def check_word(req: CheckWordRequest):
    word = req.word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="Word cannot be empty")
        
    filepath, found_card_type = find_word_file(word, req.card_type)
    exists = os.path.exists(filepath)
    
    sections_found = []
    metadata = {}
    if exists:
        try:
            metadata, sections = parse_markdown_note(filepath)
            sections_found = list(sections.keys())
        except Exception as e:
            # Handle parsed error gracefully
            pass
            
    return {
        "word": word,
        "exists": exists,
        "sections": sections_found,
        "metadata": metadata,
        "filepath": filepath,
        "card_type": found_card_type
    }

async def generate_word_file(
    word: str,
    card_type: str,
    sections_to_generate: List[str],
    regenerate_all: bool,
    client: OpenRouterClient,
    model: Optional[str],
    concurrency_limit: int,
    stats: dict
):
    filepath, resolved_ct = find_word_file(word, card_type)
    exists = os.path.exists(filepath)
    
    # Ensure target directory exists
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    old_metadata = {}
    old_sections = {}
    
    if exists:
        yield ("log", f"La nota para {word} ya existe en {os.path.basename(os.path.dirname(filepath))}. Cargando contenido existente...")
        try:
            old_metadata, old_sections = parse_markdown_note(filepath)
        except Exception as e:
            yield ("log", f"Error parseando nota existente: {str(e)}. Se creará un backup.")
            import time
            backup_path = f"{filepath}.backup.{int(time.time())}"
            os.rename(filepath, backup_path)
            exists = False

    sec_info = CARD_TYPE_SECTIONS.get(card_type, CARD_TYPE_SECTIONS["bisilabo"])
    structured_keys = sec_info["structured"]
    all_narrative_keys = sec_info["narrative"]

    needs_structured_call = (not exists or regenerate_all or any(k in sections_to_generate for k in structured_keys)) and len(structured_keys) > 0

    new_metadata = {}
    new_sections = {}
    
    if needs_structured_call:
        try:
            yield ("log", "Solicitando metadatos estructurados a OpenRouter...")
            
            res, p_tok, c_tok = await client.get_structured_data(word, card_type=card_type, model=model)
            stats["prompt_tokens"] += p_tok
            stats["completion_tokens"] += c_tok
            yield ("usage", {
                "prompt_tokens": stats["prompt_tokens"],
                "completion_tokens": stats["completion_tokens"],
                "total_tokens": stats["prompt_tokens"] + stats["completion_tokens"]
            })
            
            new_metadata = {
                "word": word,
                "pinyin": res.get("pinyin", ""),
                "word_type": res.get("word_type", "adjetivo"),
                "favorite": old_metadata.get("favorite", False),
                "tags": old_metadata.get("tags", ["review"]),
                "created_time": old_metadata.get("created_time") or old_metadata.get("created") or (datetime.datetime.utcnow().isoformat() + "Z")
            }
            if "hsk_level" in res:
                new_metadata["hsk_level"] = res["hsk_level"]
                
            if "collocations" in res:
                new_sections["collocations"] = "\n".join([f"- {c}" for c in res.get("collocations", [])])
            if "synonyms" in res:
                new_sections["synonyms"] = "\n".join([f"- {s}" for s in res.get("synonyms", [])])
            if "antonyms" in res:
                new_sections["antonyms"] = "\n".join([f"- {a}" for a in res.get("antonyms", [])])
                
            if "examples" in res:
                ex_lines = []
                for ex in res.get("examples", []):
                    ex_lines.append(f"- **ZH:** {ex.get('zh', '')}")
                    ex_lines.append(f"  - **PYN:** {ex.get('pyn', '')}")
                    ex_lines.append(f"  - **ES:** {ex.get('es', '')}")
                new_sections["examples"] = "\n".join(ex_lines)
                
            pinyin_val = res.get("pinyin", "")
            hsk_val = res.get("hsk_level", "")
            yield ("log", f"Metadatos obtenidos. Pinyin: {pinyin_val}" + (f", HSK: {hsk_val}" if hsk_val else ""))
        except Exception as e:
            yield ("error", f"Error en llamada estructurada: {str(e)}")
            return
    else:
        new_metadata = {
            "word": word,
            "pinyin": old_metadata.get("pinyin", ""),
            "word_type": old_metadata.get("word_type", "alocución" if card_type == "correccion_alocucion" else "adjetivo"),
            "favorite": old_metadata.get("favorite", False),
            "tags": old_metadata.get("tags", ["review"]),
            "created_time": old_metadata.get("created_time") or old_metadata.get("created") or (datetime.datetime.utcnow().isoformat() + "Z")
        }
        if "hsk_level" in old_metadata:
            new_metadata["hsk_level"] = old_metadata["hsk_level"]

    narratives_to_fetch = []
    for k in all_narrative_keys:
        is_requested = k in sections_to_generate
        section_exists = (
            k in old_sections or
            (k == "mnemonics" and "mnemonic" in old_sections) or
            (k == "errors" and "error" in old_sections) or
            (k == "examples" and "example" in old_sections) or
            (k == "pinyin" and "pinyin" in old_sections)
        )
        
        if is_requested and (not section_exists or regenerate_all):
            narratives_to_fetch.append(k)

    if narratives_to_fetch:
        yield ("log", f"Iniciando llamadas para secciones narrativas (concurrencia: {concurrency_limit}): {narratives_to_fetch}")
        
        sem = asyncio.Semaphore(concurrency_limit)
        
        async def fetch_task(sec):
            async with sem:
                try:
                    pinyin_val = new_metadata.get("pinyin") or old_metadata.get("pinyin", "")
                    content, p_tok, c_tok = await client.get_narrative_section(
                        word, pinyin_val, sec, card_type=card_type, model=model
                    )
                    return sec, content, p_tok, c_tok, None
                except Exception as e:
                    return sec, "", 0, 0, str(e)
                    
        tasks = [asyncio.create_task(fetch_task(sec)) for sec in narratives_to_fetch]
        
        error_occurred = False
        for completed in asyncio.as_completed(tasks):
            sec, content, p_tok, c_tok, err = await completed
            if err:
                yield ("log", f"Error en sección {sec}: {err}")
                error_occurred = True
            else:
                new_sections[sec] = content
                stats["prompt_tokens"] += p_tok
                stats["completion_tokens"] += c_tok
                yield ("log", f"Sección narración completada: {sec}")
                yield ("usage", {
                    "prompt_tokens": stats["prompt_tokens"],
                    "completion_tokens": stats["completion_tokens"],
                    "total_tokens": stats["prompt_tokens"] + stats["completion_tokens"]
                })
                
        if error_occurred:
            yield ("log", "Ocurrió un error en una o más secciones. Procediendo con datos parciales...")

    yield ("log", "Realizando fusión idempotente con nota existente...")
    
    all_card_keys = structured_keys + all_narrative_keys
    merged_metadata, merged_sections = merge_notes(
        old_metadata, old_sections,
        new_metadata, new_sections,
        sections_to_generate if regenerate_all or exists else all_card_keys
    )
    
    note_content = serialize_note(merged_metadata, merged_sections, card_type=card_type)
    
    tmp_filepath = f"{filepath}.tmp"
    try:
        with open(tmp_filepath, "w", encoding="utf-8") as f:
            f.write(note_content)
        os.replace(tmp_filepath, filepath)
    except Exception as e:
        if os.path.exists(tmp_filepath):
            try:
                os.remove(tmp_filepath)
            except:
                pass
        raise e
        
    yield ("log", f"Ficha guardada con éxito en: unified-words/{os.path.basename(os.path.dirname(filepath))}/{os.path.basename(filepath)}")
    yield ("result", {"word": word, "filepath": filepath})

async def generate_pipeline(
    words: list[str],
    sections_to_generate: list[str],
    card_type: str,
    regenerate_all: bool,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    concurrency_limit: int = 2
):
    # Verify API key
    resolved_api_key = api_key or os.getenv("OPENROUTER_API_KEY")
    if not resolved_api_key:
        yield f"data: {json.dumps({'type': 'error', 'message': 'Falta la clave API de OpenRouter. Configúrala en la interfaz o en el archivo .env.'})}\n\n"
        return

    client = OpenRouterClient(api_key=resolved_api_key, default_model=model)

    # Ensure output directory exists
    if not os.path.exists(unified_dir):
        os.makedirs(unified_dir)

    stats = {"prompt_tokens": 0, "completion_tokens": 0}

    for word in words:
        word = word.strip()
        if not word:
            continue

        msg_start = f"==== Iniciando procesamiento de: {word} (Tipo: {card_type}) ===="
        yield f"data: {json.dumps({'type': 'log', 'message': msg_start})}\n\n"
        
        # 1. Comparison pipeline check
        if card_type == "comparacion":
            indiv_words = [w.strip() for w in re.split(r'[,，]', word) if w.strip()]
            msg_comp = f"Ficha de comparación detectada. Verificando palabras individuales: {indiv_words}"
            yield f"data: {json.dumps({'type': 'log', 'message': msg_comp})}\n\n"
            
            for indiv_word in indiv_words:
                filepath_indiv, indiv_inferred_type = find_word_file(indiv_word)
                if not os.path.exists(filepath_indiv):
                    msg_missing = f'La palabra individual "{indiv_word}" no existe. Generándola como "{indiv_inferred_type}"...'
                    yield f"data: {json.dumps({'type': 'log', 'message': msg_missing})}\n\n"
                    
                    indiv_sec_info = CARD_TYPE_SECTIONS[indiv_inferred_type]
                    indiv_sections = indiv_sec_info["structured"] + indiv_sec_info["narrative"]
                    
                    async for msg_type, msg_val in generate_word_file(
                        word=indiv_word,
                        card_type=indiv_inferred_type,
                        sections_to_generate=indiv_sections,
                        regenerate_all=False,
                        client=client,
                        model=model,
                        concurrency_limit=concurrency_limit,
                        stats=stats
                    ):
                        if msg_type == "log":
                            msg_indiv_log = f"[{indiv_word}] {msg_val}"
                            yield f"data: {json.dumps({'type': 'log', 'message': msg_indiv_log})}\n\n"
                        elif msg_type == "usage":
                            yield f"data: {json.dumps({'type': 'usage', **msg_val})}\n\n"
                        elif msg_type == "error":
                            msg_indiv_err = f"[{indiv_word}] {msg_val}"
                            yield f"data: {json.dumps({'type': 'error', 'message': msg_indiv_err})}\n\n"
                        elif msg_type == "result":
                            yield f"data: {json.dumps({'type': 'result', **msg_val})}\n\n"
                else:
                    msg_exists = f'La palabra individual "{indiv_word}" ya existe.'
                    yield f"data: {json.dumps({'type': 'log', 'message': msg_exists})}\n\n"
                    
        # 2. Generate the requested card itself
        async for msg_type, msg_val in generate_word_file(
            word=word,
            card_type=card_type,
            sections_to_generate=sections_to_generate,
            regenerate_all=regenerate_all,
            client=client,
            model=model,
            concurrency_limit=concurrency_limit,
            stats=stats
        ):
            if msg_type == "log":
                yield f"data: {json.dumps({'type': 'log', 'message': msg_val})}\n\n"
            elif msg_type == "usage":
                yield f"data: {json.dumps({'type': 'usage', **msg_val})}\n\n"
            elif msg_type == "error":
                yield f"data: {json.dumps({'type': 'error', 'message': msg_val})}\n\n"
            elif msg_type == "result":
                yield f"data: {json.dumps({'type': 'result', **msg_val})}\n\n"

    yield f"data: {json.dumps({'type': 'done', 'message': 'Procesamiento completo de todas las palabras.'})}\n\n"

@app.post("/api/process")
async def process_word(req: ProcessRequest):
    if not req.words:
        raise HTTPException(status_code=400, detail="Words list cannot be empty")
        
    return StreamingResponse(
        generate_pipeline(
            words=req.words,
            sections_to_generate=req.sections,
            card_type=req.card_type,
            regenerate_all=req.regenerate_all,
            api_key=req.api_key,
            model=req.model,
            concurrency_limit=req.concurrency_limit
        ),
        media_type="text/event-stream"
    )

active_recording_process = None
active_recording_filename = None

@app.post("/api/audio/start")
async def start_recording(word: str):
    global active_recording_process, active_recording_filename
    word = word.strip()
    if not word:
        raise HTTPException(status_code=400, detail="Word cannot be empty")
        
    if active_recording_process is not None:
        if active_recording_process.poll() is None:
            raise HTTPException(status_code=400, detail="A recording is already in progress.")
        else:
            active_recording_process = None
            active_recording_filename = None
            
    audio_dir = os.path.join(unified_dir, "audio")
    os.makedirs(audio_dir, exist_ok=True)
    
    name_part = get_clean_filename(word)
    timestamp = int(datetime.datetime.now().timestamp())
    output_filename = f"{name_part}_audio_{timestamp}.mp3"
    filepath = os.path.join(audio_dir, output_filename)
    
    pulse_device = os.getenv("PULSE_AUDIO_DEVICE", "alsa_output.pci-0000_00_1b.0.analog-stereo.monitor")
    
    volume_boost = os.getenv("AUDIO_RECORD_VOLUME_BOOST", "1.5")
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "pulse",
        "-i", pulse_device
    ]
    if volume_boost and volume_boost != "1.0":
        cmd.extend(["-af", f"volume={volume_boost}"])
    cmd.append(filepath)
    
    try:
        active_recording_process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid
        )
        active_recording_filename = output_filename
        return {"status": "recording", "filename": output_filename, "filepath": filepath}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start recording: {str(e)}")

@app.post("/api/audio/stop")
async def stop_recording():
    global active_recording_process, active_recording_filename
    if active_recording_process is None:
        raise HTTPException(status_code=400, detail="No active recording in progress.")
        
    try:
        if active_recording_process.poll() is None:
            try:
                active_recording_process.communicate(input=b'q', timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(active_recording_process.pid), signal.SIGINT)
                active_recording_process.wait()
                
        filename = active_recording_filename
        obsidian_link = f"![[unified-words/audio/{filename}]]"
        return {"status": "stopped", "filename": filename, "obsidian_link": obsidian_link}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error stopping recording: {str(e)}")
    finally:
        active_recording_process = None
        active_recording_filename = None

# Case-insensitive redirects for entry point HTML files
@app.get("/Mo-dict.html")
@app.get("/mo-dict.html")
@app.get("/app/Mo-dict.html")
@app.get("/app/mo-dict.html")
def redirect_mo_dict():
    return RedirectResponse(url="/Mo-Dict.html")

@app.get("/Mo-cards.html")
@app.get("/mo-cards.html")
@app.get("/app/Mo-cards.html")
@app.get("/app/mo-cards.html")
def redirect_mo_cards():
    return RedirectResponse(url="/Mo-Cards.html")

@app.get("/Mo-reader.html")
@app.get("/mo-reader.html")
@app.get("/app/Mo-reader.html")
@app.get("/app/mo-reader.html")
def redirect_mo_reader():
    return RedirectResponse(url="/Mo-Reader.html")

@app.get("/Mo-reader-v2.html")
@app.get("/mo-reader-v2.html")
@app.get("/app/Mo-reader-v2.html")
@app.get("/app/mo-reader-v2.html")
def redirect_mo_reader_v2():
    return RedirectResponse(url="/Mo-Reader-v2.html")

@app.get("/Modb-inspector.html")
@app.get("/modb-inspector.html")
@app.get("/app/Modb-inspector.html")
@app.get("/app/modb-inspector.html")
def redirect_modb_inspector():
    return RedirectResponse(url="/MoDB-inspector.html")

@app.get("/editor.html")
@app.get("/app/editor.html")
def redirect_editor():
    return RedirectResponse(url="/Editor.html")

# Serve the web directory at the root level /
# This matches files like /Mo-Dict.html, /mo-common.js, /mo-layout.css, etc.
app.mount("/", StaticFiles(directory=web_dir, html=True), name="project_root_at_root")
