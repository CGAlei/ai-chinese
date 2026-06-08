#!/usr/bin/env python3
import os
import sys
import sqlite3
import argparse

DB_PATH = os.path.expanduser('~/.hermes/state.db')
from datetime import datetime

# === CONFIGURACIÓN BETA FASE 3 ===
# Cambiar a False para desactivar por completo la persistencia y la tabla de patrones.
ENABLE_PHASE_3 = True
# =================================

def init_db_schema(conn):
    cursor = conn.cursor()
    try:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS question_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern_type TEXT NOT NULL,
                entities TEXT NOT NULL,
                dimensions TEXT,
                filepath TEXT,
                usage_count INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                last_used_at TEXT NOT NULL,
                last_session_id TEXT
            );
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_question_patterns_entities 
            ON question_patterns(entities, pattern_type);
        """)
        conn.commit()
    except Exception as e:
        print(f"Error al inicializar esquema de base de datos: {e}", file=sys.stderr)

def get_connection():
    db_dir = os.path.dirname(DB_PATH)
    if not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    if ENABLE_PHASE_3:
        init_db_schema(conn)
    return conn

def list_sessions(limit=10):
    conn = get_connection()
    cursor = conn.cursor()
    
    # Intentar obtener la información de las sesiones ordenadas por fecha
    query = "SELECT id, title FROM sessions LIMIT ?;"
    
    # Obtener el esquema de la tabla sessions para ordenar correctamente
    try:
        cursor.execute("PRAGMA table_info(sessions);")
        columns = [row[1] for row in cursor.fetchall()]
        if 'created_at' in columns:
            query = "SELECT id, title, created_at FROM sessions ORDER BY created_at DESC LIMIT ?;"
        elif 'timestamp' in columns:
            query = "SELECT id, title, timestamp FROM sessions ORDER BY timestamp DESC LIMIT ?;"
    except Exception:
        pass

    try:
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()
    except Exception as e:
        print(f"Error al consultar las sesiones: {e}", file=sys.stderr)
        conn.close()
        sys.exit(1)
        
    print("\n📜 ÚLTIMAS SESIONES DE CHAT:")
    print("=" * 70)
    for row in rows:
        session_id = row[0]
        title = row[1]
        time_str = row[2] if len(row) > 2 else "Fecha no registrada"
        print(f"🆔 ID: {session_id} | 📅 {time_str}")
        print(f"   💬 Título: {title}")
        print("-" * 70)
    conn.close()

def show_session(session_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT role, content FROM messages WHERE session_id = ? ORDER BY id ASC;", (session_id,))
        rows = cursor.fetchall()
    except Exception as e:
        print(f"Error al consultar mensajes de la sesión {session_id}: {e}", file=sys.stderr)
        conn.close()
        sys.exit(1)
        
    if not rows:
        print(f"No se encontraron mensajes para la sesión ID: {session_id}")
        conn.close()
        return

    print(f"\n💬 CONVERSACIÓN DE LA SESIÓN: {session_id}")
    print("=" * 80)
    for role, content in rows:
        if content is None or content.strip() == "":
            continue
        role_label = "👤 USUARIO" if role == 'user' else ("🤖 TUTOR" if role == 'assistant' else f"🔧 HERRAMIENTA ({role})")
        print(f"[{role_label}]:")
        print(content.strip())
        print("-" * 80)
    conn.close()

def search_history(query):
    conn = get_connection()
    cursor = conn.cursor()
    
    sql = """
        SELECT session_id, role, content 
        FROM messages 
        WHERE content LIKE ? AND (role = 'assistant' OR role = 'user')
        ORDER BY id DESC;
    """
    
    try:
        cursor.execute(sql, (f"%{query}%",))
        rows = cursor.fetchall()
    except Exception as e:
        print(f"Error al realizar la búsqueda: {e}", file=sys.stderr)
        conn.close()
        sys.exit(1)
        
    print(f"\n🔍 RESULTADOS DE BÚSQUEDA HISTÓRICA PARA: '{query}'")
    print("=" * 80)
    if not rows:
        print("  No se encontraron coincidencias en mensajes anteriores.")
        print("=" * 80)
        conn.close()
        return
        
    for session_id, role, content in rows:
        if content is None:
            continue
        role_label = "Usuario" if role == 'user' else "Tutor"
        
        # Extraer un fragmento con contexto de la coincidencia
        idx = content.lower().find(query.lower())
        start = max(0, idx - 80)
        end = min(len(content), idx + 120)
        snippet = content[start:end].replace('\n', ' ').strip()
        if start > 0:
            snippet = "... " + snippet
        if end < len(content):
            snippet = snippet + " ..."
            
        print(f"🆔 Sesión: {session_id} | Rol: {role_label}")
        print(f"   Coincidencia: {snippet}")
        print("-" * 80)
    conn.close()

# =============================================================================
# === [INICIO BETA FASE 3: FUNCIONES DE PERSISTENCIA Y MEMORIA DE PATRONES] ===
# =============================================================================

def save_or_update_pattern(pattern_type, entities, dimensions, filepath, session_id):
    if not ENABLE_PHASE_3:
        print("⚠ Operación omitida: La Fase 3 está desactivada en la configuración.")
        return None

    if isinstance(entities, list):
        entities_str = ",".join(sorted([str(e).strip() for e in entities if str(e).strip()]))
    else:
        entities_str = ",".join(sorted([str(e).strip() for e in entities.split(",") if str(e).strip()]))

    if isinstance(dimensions, list):
        dims_str = ",".join(sorted([str(d).strip() for d in dimensions if str(d).strip()]))
    else:
        dims_str = dimensions if dimensions else ""

    conn = get_connection()
    cursor = conn.cursor()
    try:
        now = datetime.now().isoformat()
        cursor.execute("""
            SELECT id, usage_count, dimensions, filepath FROM question_patterns 
            WHERE entities = ? AND pattern_type = ?;
        """, (entities_str, pattern_type))
        row = cursor.fetchone()
        
        if row:
            pattern_id, usage_count, existing_dims, existing_filepath = row
            existing_dims_list = [d.strip() for d in existing_dims.split(",") if d.strip()] if existing_dims else []
            incoming_dims_list = [d.strip() for d in dims_str.split(",") if d.strip()] if dims_str else []
            merged_dims = ",".join(sorted(list(set(existing_dims_list + incoming_dims_list))))
            
            cursor.execute("""
                UPDATE question_patterns 
                SET usage_count = usage_count + 1,
                    dimensions = ?,
                    filepath = COALESCE(?, filepath),
                    last_used_at = ?,
                    last_session_id = ?
                WHERE id = ?;
            """, (merged_dims, filepath, now, session_id, pattern_id))
            conn.commit()
            print(f"✓ Patrón existente actualizado (ID: {pattern_id}, Usos: {usage_count + 1})")
            return pattern_id
        else:
            cursor.execute("""
                INSERT INTO question_patterns (pattern_type, entities, dimensions, filepath, usage_count, created_at, last_used_at, last_session_id)
                VALUES (?, ?, ?, ?, 1, ?, ?, ?);
            """, (pattern_type, entities_str, dims_str, filepath, now, now, session_id))
            conn.commit()
            pattern_id = cursor.lastrowid
            print(f"✓ Nuevo patrón de pregunta registrado (ID: {pattern_id}, Entidades: {entities_str})")
            return pattern_id
    except Exception as e:
        print(f"Error al registrar/actualizar el patrón: {e}", file=sys.stderr)
        return None
    finally:
        conn.close()

def find_similar_pattern(entities, pattern_type="comparison"):
    if not ENABLE_PHASE_3:
        return None

    if isinstance(entities, list):
        entities_str = ",".join(sorted([str(e).strip() for e in entities if str(e).strip()]))
    else:
        entities_str = ",".join(sorted([str(e).strip() for e in entities.split(",") if str(e).strip()]))
        
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT id, pattern_type, entities, dimensions, filepath, usage_count, created_at, last_used_at, last_session_id
            FROM question_patterns
            WHERE entities = ? AND pattern_type = ?;
        """, (entities_str, pattern_type))
        row = cursor.fetchone()
        if row:
            return {
                'id': row[0],
                'pattern_type': row[1],
                'entities': [e.strip() for e in row[2].split(",") if e.strip()],
                'dimensions': [d.strip() for d in row[3].split(",") if d.strip()] if row[3] else [],
                'filepath': row[4],
                'usage_count': row[5],
                'created_at': row[6],
                'last_used_at': row[7],
                'last_session_id': row[8]
            }
        return None
    except Exception as e:
        print(f"Error al buscar patrón similar: {e}", file=sys.stderr)
        return None
    finally:
        conn.close()

def increment_pattern_usage(pattern_id, session_id):
    if not ENABLE_PHASE_3:
        return

    conn = get_connection()
    cursor = conn.cursor()
    try:
        now = datetime.now().isoformat()
        cursor.execute("""
            UPDATE question_patterns 
            SET usage_count = usage_count + 1,
                last_used_at = ?,
                last_session_id = ?
            WHERE id = ?;
        """, (now, session_id, pattern_id))
        conn.commit()
        print(f"✓ Contador de uso incrementado para el patrón ID: {pattern_id}")
    except Exception as e:
        print(f"Error al incrementar uso del patrón: {e}", file=sys.stderr)
    finally:
        conn.close()

def list_patterns():
    if not ENABLE_PHASE_3:
        print("⚠ Operación omitida: La Fase 3 está desactivada en la configuración.")
        return

    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id, pattern_type, entities, dimensions, filepath, usage_count, last_used_at FROM question_patterns ORDER BY last_used_at DESC;")
        rows = cursor.fetchall()
    except Exception as e:
        print(f"Error al consultar patrones: {e}", file=sys.stderr)
        conn.close()
        return
        
    print("\n📋 PATRONES DE PREGUNTA REGISTRADOS:")
    print("=" * 90)
    if not rows:
        print("  No hay patrones de pregunta registrados aún.")
        print("=" * 90)
        conn.close()
        return
        
    for row in rows:
        print(f"🆔 ID: {row[0]} | 🏷️ Tipo: {row[1]} | 🔄 Usos: {row[5]}")
        print(f"   🏮 Entidades: {row[2]}")
        if row[3]:
            print(f"   📐 Dimensiones: {row[3]}")
        print(f"   📂 Ruta: {row[4]}")
        print(f"   📅 Último uso: {row[6]}")
        print("-" * 90)
    conn.close()

# ===========================================================================
# === [FIN BETA FASE 3: FUNCIONES DE PERSISTENCIA Y MEMORIA DE PATRONES] ===
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(description="Consulta y busca en el historial de sesiones de Hermes Agent.")
    
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", type=int, nargs="?", const=10, help="Listar las últimas N sesiones (por defecto 10)")
    group.add_argument("--session", help="Ver la conversación completa de un ID de sesión")
    group.add_argument("--search", help="Buscar un término o carácter en todos los chats pasados")
    group.add_argument("--patterns", action="store_true", help="Listar todos los patrones de preguntas registrados")
    
    args = parser.parse_args()
    
    if args.list is not None:
        list_sessions(args.list)
    elif args.session:
        show_session(args.session)
    elif args.search:
        search_history(args.search)
    elif args.patterns:
        list_patterns()

if __name__ == "__main__":
    main()
