# -*- coding: utf-8 -*-
import re
import sys
import unicodedata

# 1. Intentar cargar jieba (Segmentación)
try:
    import jieba
    # Reducir salida verbose de jieba al inicializar
    jieba.setLogLevel(20)
    HAS_JIEBA = True
except ImportError:
    HAS_JIEBA = False

# 2. Intentar cargar opencc (Simplificado <-> Tradicional)
try:
    from opencc import OpenCC
    HAS_OPENCC = True
except ImportError:
    HAS_OPENCC = False

# 3. Intentar cargar pypinyin (Caracteres -> Pinyin)
try:
    import pypinyin
    HAS_PYPINYIN = True
except ImportError:
    HAS_PYPINYIN = False

# 4. Intentar cargar tiktoken (Tokenizer de LLM)
try:
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False


def segment_chinese(text):
    """
    Segmenta una cadena de texto en palabras.
    Usa jieba de forma local si está disponible.
    Si falla, utiliza una heurística basada en Regex Unicode.
    """
    if HAS_JIEBA:
        try:
            return list(jieba.cut(text))
        except Exception:
            pass
            
    # Fallback: Extraer bloques de caracteres chinos y palabras latinas usando regex
    # Mantiene los caracteres chinos individuales y palabras completas en pinyin/español
    pattern = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9áéíóúüñÁÉÍÓÚÜÑ]+")
    return pattern.findall(text)


def to_simplified(text):
    """
    Convierte texto en caracteres chinos tradicionales a simplificados.
    Usa OpenCC localmente. Si falla, retorna el texto sin modificar.
    """
    if HAS_OPENCC:
        try:
            cc = OpenCC('t2s') # Tradicional a Simplificado
            return cc.convert(text)
        except Exception:
            pass
    return text


def get_pinyin_slug(pinyin_toned):
    """
    Limpia el pinyin de marcas de tono, espacios y caracteres especiales para generar slugs.
    Usa pypinyin si es posible para resolver caracteres chinos directamente,
    y normalización NFD para limpiar diacríticos latinos.
    """
    if HAS_PYPINYIN and any(ord(c) >= 0x4e00 and ord(c) <= 0x9fff for c in pinyin_toned):
        try:
            # Si se le pasa caracteres chinos en lugar de pinyin, los traduce
            pinyins = pypinyin.pinyin(pinyin_toned, style=pypinyin.Style.NORMAL)
            pinyin_toned = " ".join([p[0] for p in pinyins])
        except Exception:
            pass

    # Normalizar diacríticos
    nfd_form = unicodedata.normalize('NFD', pinyin_toned)
    cleaned = "".join([c for c in nfd_form if not unicodedata.combining(c)])
    
    # Quitar caracteres no alfanuméricos y pasar a minúsculas
    cleaned = cleaned.lower()
    cleaned = re.sub(r'[^a-z0-9]', '', cleaned)
    return cleaned


def count_tokens(text, model="gpt-4"):
    """
    Cuenta con precisión el número de tokens en una cadena de texto.
    Usa tiktoken. Si falla, realiza una estimación aproximada (KISS).
    """
    if HAS_TIKTOKEN:
        try:
            try:
                encoding = tiktoken.encoding_for_model(model)
            except KeyError:
                encoding = tiktoken.get_encoding("cl100k_base")
            return len(encoding.encode(text))
        except Exception:
            pass
            
    # Fallback: Estimación burda (1 token ≈ 4 caracteres en inglés, o 1 token por carácter chino)
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    other_chars = len(re.sub(r"[\u4e00-\u9fff]", "", text))
    return chinese_chars + (other_chars // 3) + 1


if __name__ == "__main__":
    # Test rápido de funcionamiento
    test_text = "我喜歡學習中文, 相當 vs 適當"
    print("Texto original:", test_text)
    print("Segmentado:    ", segment_chinese(test_text))
    print("Simplificado:  ", to_simplified(test_text))
    print("Pinyin Slug:   ", get_pinyin_slug("xiāngdāng"))
    print("Tokens (est):  ", count_tokens(test_text))
