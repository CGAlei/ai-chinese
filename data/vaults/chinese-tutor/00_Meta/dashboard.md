# Panel de Control (Dashboard) del Tutor de Chino

Este panel resume de forma dinámica tu progreso de vocabulario, comparaciones realizadas, patrones de error diagnosticados y campos semánticos explorados.

> [!NOTE]
> Para visualizar las tablas dinámicas inferiores, asegúrate de tener instalado y activo el plugin de comunidad **Dataview** en la configuración de Obsidian.

---

## 🔍 Comparaciones Recientes
Recopilación de comparaciones lingüísticas y diferencias de uso entre términos.

```dataview
TABLE entities as Palabras, dimensions as Dimensiones, created as Fecha
FROM "07_Comparisons"
SORT created DESC
LIMIT 10
```

---

## ⚠️ Patrones de Error Activos
Análisis de tus errores más recurrentes para entrenar tu conciencia lingüística.

```dataview
TABLE entities as "Palabras problemáticas", underlying_cause as Causa, frequency as Veces, status as Estado
FROM "10_ErrorPatterns"
WHERE status = "activo"
SORT frequency DESC
```

---

## 🌐 Campos Semánticos Explorados
Redes de palabras asociadas y sus pesos conceptuales.

```dataview
TABLE length(related_words) as "Palabras relacionadas", seed_word as Semilla
FROM "09_SemanticFields"
SORT length(related_words) DESC
```

---

## 📈 Resumen General de Vocabulario
Progreso del vocabulario activo clasificado por el nivel de SRS.

```dataview
TABLE pinyin_toned as Pinyin, word_type as Tipo, hsk as HSK, srs_status as "Estado SRS"
FROM "01_Vocab"
SORT modified DESC
LIMIT 15
```
