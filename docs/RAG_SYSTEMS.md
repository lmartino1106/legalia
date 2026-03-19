# Sistema de 3 RAGs — LegalIA

LegalIA opera con 3 sistemas RAG independientes que alimentan al mismo orquestador. Cada uno tiene su propia collection en Qdrant, su propio pipeline de ingestion, y su propia lógica de retrieval.

```
                    Pregunta del usuario
                           │
                           ▼
                    ┌──────────────┐
                    │  Orquestador │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
     ┌────────────┐ ┌───────────┐ ┌───────────┐
     │  RAG Laws  │ │ RAG Docs  │ │RAG Train  │
     │ Legislación│ │ Libros/PDF│ │ Feedback  │
     └─────┬──────┘ └─────┬─────┘ └─────┬─────┘
           │              │              │
           ▼              ▼              ▼
     ┌───────────────────────────────────────┐
     │        Merge & Rerank Results         │
     └───────────────────┬───────────────────┘
                         │
                         ▼
                  ┌──────────────┐
                  │  LLM (Claude)│
                  │  + Citations │
                  └──────────────┘
```

El orquestador decide qué RAGs consultar según la pregunta. Puede consultar uno, dos, o los tres simultáneamente. Los resultados se mergean y rerankean antes de llegar al LLM.

---

## RAG 1: Laws (Legislación Chilena)

**Ubicación:** `app/rag/laws/`
**Collection Qdrant:** `chilean_laws`
**Propósito:** Corpus legal oficial — leyes, códigos, jurisprudencia, dictámenes.

### Fuentes
| Fuente | Tipo | Ejemplo |
|--------|------|---------|
| BCN / Ley Chile | Leyes, DFL, DL | Ley 21.643 (Karin) |
| Códigos | Códigos completos | Código del Trabajo |
| Corte Suprema | Jurisprudencia | Fallos relevantes |
| Dir. del Trabajo | Dictámenes | Interpretaciones DT |
| Contraloría | Dictámenes | Pronunciamientos CGR |
| SII | Circulares | Interpretaciones tributarias |

### Ingestion Pipeline
```
Fuente (BCN API / scraping)
    │
    ▼
[Legal Scraper]  ──── scripts/ingest_laws.py
    │ extrae texto + metadata estructurada
    ▼
[Legal Chunker]  ──── app/rag/laws/chunker.py
    │ split por artículo/inciso
    │ preserva jerarquía: ley → libro → título → párrafo → art → inciso
    │ chunk size: 500-800 tokens, overlap: 100
    ▼
[Metadata Enricher]  ──── app/rag/laws/enricher.py
    │ área legal, vigencia, relevancia, relaciones entre normas
    ▼
[Embeddings]  ──── app/rag/laws/embedder.py
    │ Voyage AI (legal-optimized) o OpenAI
    ▼
[Qdrant: chilean_laws]
    │ payload: {ley, articulo, area, vigencia, fuente, fecha_pub}
    ▼
Indexado ✓
```

### Retrieval
- Hybrid: vector similarity + BM25
- Filtro por área legal (metadata)
- Filtro por vigencia (solo normas vigentes por defecto)
- Rerank con Cohere

### Actualización
- Cron semanal: revisa BCN por nuevas leyes/modificaciones
- Script de diff: detecta cambios en leyes existentes
- Re-embedding selectivo (solo chunks afectados)

---

## RAG 2: Documents (Libros y PDFs con OCR)

**Ubicación:** `app/rag/documents/`
**Collection Qdrant:** `legal_documents`
**Propósito:** Conocimiento profundo de doctrina, manuales, libros de derecho, papers académicos, y documentos escaneados.

### Tipos de documentos
| Tipo | Formato | Ejemplo |
|------|---------|---------|
| Libros de derecho | PDF (texto/escaneado) | Manual de Derecho Laboral |
| Manuales prácticos | PDF | Guía de pensiones alimenticias |
| Papers académicos | PDF | Artículos de revistas de derecho |
| Documentos escaneados | PDF/imágenes | Contratos tipo, formularios |
| Apuntes/resúmenes | PDF/DOCX | Material de estudio legal |

### Ingestion Pipeline
```
Documento (PDF/imagen)
    │
    ▼
[File Detector]  ──── app/rag/documents/detector.py
    │ detecta tipo: texto nativo, escaneado, mixto
    │
    ├── Si tiene texto nativo ──────────┐
    │                                    ▼
    │                          [PDF Text Extractor]
    │                          PyMuPDF / pdfplumber
    │
    ├── Si es escaneado/imagen ─────────┐
    │                                    ▼
    │                          [OCR Pipeline]
    │                          ├── Pre-procesamiento imagen
    │                          │   (deskew, denoise, binarize)
    │                          ├── OCR Engine
    │                          │   Tesseract + EasyOCR (español)
    │                          │   o Surya (mejor para layouts)
    │                          └── Post-procesamiento
    │                              (corrección ortográfica legal)
    │
    └── Si es mixto ────────────────────┐
                                         ▼
                               [Hybrid Extractor]
                               texto nativo + OCR para imágenes/tablas
    │
    ▼
[Document Chunker]  ──── app/rag/documents/chunker.py
    │ Estrategia por tipo de documento:
    │ ├── Libro: por capítulo → sección → párrafo
    │ ├── Paper: abstract, intro, secciones, conclusión
    │ ├── Manual: por tema/pregunta
    │ └── Formulario: campos + instrucciones
    │ chunk size: 800-1200 tokens (más grandes que laws)
    │ overlap: 150 tokens
    ▼
[Metadata Extractor]  ──── app/rag/documents/metadata.py
    │ título, autor, año, editorial, área legal
    │ tabla de contenidos (si existe)
    │ calidad OCR score (confianza)
    ▼
[Embeddings]  ──── app/rag/documents/embedder.py
    │ mismo modelo que laws para compatibilidad
    ▼
[Qdrant: legal_documents]
    │ payload: {titulo, autor, año, tipo, area, capitulo, pagina, ocr_score}
    ▼
Indexado ✓
```

### OCR Stack
| Componente | Tecnología | Uso |
|-----------|-----------|-----|
| Texto nativo | PyMuPDF (fitz) | Extracción rápida de PDF con texto |
| OCR principal | Tesseract 5 + spa.traineddata | OCR general en español |
| OCR backup | EasyOCR | Mejor para layouts complejos, tablas |
| OCR premium | Surya (VikParuchuri) | Estado del arte, multi-idioma, layout detection |
| Pre-procesamiento | OpenCV + Pillow | Deskew, denoise, binarización |
| Layout detection | LayoutParser o Surya | Detectar columnas, tablas, headers, footnotes |
| Tablas | Camelot o Tabula | Extraer tablas de PDFs |
| Post-OCR | SymSpell + diccionario legal | Corrección de errores OCR en términos legales |

### Pipeline OCR detallado
```
PDF/Imagen entrada
    │
    ▼
[1. Detección de tipo]
    │ ¿tiene texto embebido? → PyMuPDF text extraction
    │ ¿es imagen/escaneado? → OCR pipeline
    ▼
[2. Pre-procesamiento] (solo escaneados)
    │ ├── Convertir PDF → imágenes (pdf2image)
    │ ├── Deskew (corregir rotación)
    │ ├── Denoise (reducir ruido)
    │ ├── Binarize (Otsu threshold)
    │ └── Resize (300 DPI mínimo)
    ▼
[3. Layout Analysis]
    │ ├── Detectar regiones: texto, tablas, imágenes, headers, footers
    │ ├── Determinar orden de lectura
    │ └── Separar columnas si existen
    ▼
[4. OCR por región]
    │ ├── Texto: Tesseract/Surya
    │ ├── Tablas: Camelot → markdown table
    │ └── Headers/footers: metadata, no contenido
    ▼
[5. Post-procesamiento]
    │ ├── Merge texto de todas las regiones
    │ ├── Corrección ortográfica legal (SymSpell + diccionario jurídico)
    │ ├── Normalización (números de artículos, referencias cruzadas)
    │ └── Quality score (% confianza OCR)
    ▼
[6. Output]
    │ ├── Markdown estructurado
    │ ├── Metadata del documento
    │ └── Quality report
    ▼
Listo para chunking
```

### Interfaz de carga
- **Admin:** Script CLI para cargar PDFs en batch (`scripts/ingest_books.py`)
- **Futuro:** Panel web para subir documentos
- **Validación:** Cada documento pasa por quality check antes de indexarse

### Retrieval
- Vector similarity (mismos embeddings que laws)
- Filtro por tipo de documento, autor, área
- Penalización por OCR score bajo (documentos mal escaneados rankean menor)
- Boost para documentos más recientes

---

## RAG 3: Training (Mejora Continua)

**Ubicación:** `app/rag/training/`
**Collection Qdrant:** `training_knowledge`
**Propósito:** Aprendizaje continuo basado en interacciones reales, correcciones, y feedback. Este RAG hace que el sistema sea cada vez mejor.

### Concepto

El RAG de Training NO almacena leyes ni libros. Almacena **conocimiento derivado de la operación del sistema:**

1. **Pares Q&A validados** — Preguntas reales + respuestas corregidas/aprobadas
2. **Correcciones de abogados** — Cuando un abogado de la red corrige una respuesta
3. **Patrones de reformulación** — Cómo traducir lenguaje coloquial a legal
4. **Casos resueltos** — Flujos completos de consulta que terminaron bien
5. **Anti-patrones** — Respuestas que generaron feedback negativo

### Fuentes de datos
```
┌─────────────────────────────────────────────────┐
│              FUENTES DE TRAINING DATA            │
│                                                   │
│  ┌─────────────┐  ┌──────────────┐               │
│  │  Feedback    │  │  Correcciones│               │
│  │  usuarios    │  │  de abogados │               │
│  │  (👍/👎)     │  │  (edits)     │               │
│  └──────┬──────┘  └──────┬───────┘               │
│         │                │                        │
│  ┌──────┴──────┐  ┌──────┴───────┐               │
│  │  Langfuse   │  │  Dashboard   │               │
│  │  traces     │  │  de review   │               │
│  │  (quality)  │  │  (manual)    │               │
│  └──────┬──────┘  └──────┬───────┘               │
│         │                │                        │
│         └────────┬───────┘                        │
│                  ▼                                │
│         [Training Pipeline]                       │
│                  │                                │
│                  ▼                                │
│         [Qdrant: training_knowledge]             │
└─────────────────────────────────────────────────┘
```

### Ingestion Pipeline
```
Evento de feedback/corrección
    │
    ▼
[Event Collector]  ──── app/rag/training/collector.py
    │ captura: pregunta, respuesta, feedback, corrección, contexto
    │
    ├── Feedback positivo (👍) ──────────┐
    │   pregunta + respuesta validada     │
    │                                     ▼
    │                          [Q&A Pair Creator]
    │                          crea par validado
    │
    ├── Feedback negativo (👎) ──────────┐
    │   pregunta + respuesta mala         │
    │                                     ▼
    │                          [Failure Analyzer]
    │                          ├── ¿Retrieval falló? (docs irrelevantes)
    │                          ├── ¿Generation falló? (mala respuesta con buenos docs)
    │                          └── ¿Ambos? → flaggear para revisión humana
    │
    ├── Corrección de abogado ───────────┐
    │   respuesta original + corrección   │
    │                                     ▼
    │                          [Correction Processor]
    │                          ├── Crear par Q&A con respuesta corregida
    │                          ├── Identificar patrón de error
    │                          └── Generar "regla" para guardrails
    │
    └── Trace de Langfuse ───────────────┐
        métricas de calidad               │
                                          ▼
                               [Quality Analyzer]
                               ├── Detectar consultas con bajo retrieval score
                               ├── Detectar áreas con alta tasa de 👎
                               └── Generar reporte de gaps
    │
    ▼
[Training Chunker]  ──── app/rag/training/chunker.py
    │ Cada pieza de training data es un chunk:
    │ ├── Q&A pair: pregunta + respuesta + metadata
    │ ├── Corrección: original + corregida + razón
    │ ├── Patrón: reformulación coloquial → legal
    │ └── Anti-patrón: qué NO hacer + por qué
    ▼
[Embeddings]
    │ mismo modelo
    ▼
[Qdrant: training_knowledge]
    │ payload: {tipo, area, fecha, score, fuente, validado_por}
    ▼
Indexado ✓
```

### Tipos de Training Data

#### 1. Q&A Pairs Validados
```json
{
  "type": "qa_validated",
  "question": "¿me pueden despedir estando con licencia médica?",
  "answer": "No. Según el Art. 161 del Código del Trabajo, el empleador no puede...",
  "area": "laboral",
  "validated_by": "user_feedback",
  "score": 0.95,
  "date": "2026-03-19"
}
```

#### 2. Correcciones de Abogados
```json
{
  "type": "lawyer_correction",
  "question": "¿cuánto es la pensión alimenticia mínima?",
  "original_answer": "La pensión mínima es el 40% del ingreso mínimo...",
  "corrected_answer": "La pensión mínima legal es el 40% de un ingreso mínimo remuneracional por hijo, según Art. 3 Ley 14.908...",
  "correction_reason": "Faltaba especificar que es por hijo y la ley exacta",
  "corrected_by": "abogado_id_123",
  "area": "familia",
  "date": "2026-03-19"
}
```

#### 3. Patrones de Reformulación
```json
{
  "type": "reformulation_pattern",
  "colloquial": "mi jefe no me paga las horas extra",
  "legal_query": "incumplimiento obligación pago horas extraordinarias empleador",
  "relevant_laws": ["Código del Trabajo Art. 30-33"],
  "area": "laboral"
}
```

#### 4. Anti-patrones
```json
{
  "type": "anti_pattern",
  "scenario": "Usuario pregunta por plazo para demandar por despido injustificado",
  "bad_response": "Tiene 60 días para demandar",
  "why_bad": "El plazo es de 60 días hábiles, no corridos. Omitir 'hábiles' puede causar que pierda el plazo",
  "correct_approach": "Siempre especificar 'días hábiles' y recomendar verificar con abogado para plazos judiciales",
  "area": "laboral"
}
```

### Ciclo de Mejora Continua

```
     ┌──────────────────────────────────────────┐
     │                                          │
     ▼                                          │
[Usuario pregunta]                              │
     │                                          │
     ▼                                          │
[RAG responde] ──── Langfuse traza ────┐       │
     │                                  │       │
     ▼                                  │       │
[Usuario da feedback]                   │       │
     │                                  │       │
     ├── 👍 → Q&A pair validado ───────┤       │
     │                                  │       │
     ├── 👎 → Análisis de fallo ───────┤       │
     │         │                        │       │
     │         ├── Auto-fix posible ────┤       │
     │         └── Necesita review ─────┼──┐   │
     │                                  │  │   │
     └── Derivó a abogado ─────────────┤  │   │
              │                         │  │   │
              ▼                         │  │   │
     [Abogado corrige] ────────────────┤  │   │
                                        │  │   │
                                        ▼  ▼   │
                               [Training Pipeline]
                                        │       │
                                        ▼       │
                               [Qdrant updated] │
                                        │       │
                                        └───────┘
                                    Próxima consulta
                                    similar usa el
                                    conocimiento nuevo
```

### Retrieval del Training RAG
- Se consulta SIEMPRE junto con Laws RAG
- Los Q&A pairs validados tienen boost de relevancia
- Las correcciones de abogados tienen el boost más alto
- Los anti-patrones se inyectan en el system prompt como "NO hacer esto"
- Score mínimo de confianza: 0.85 para incluir en contexto

### Métricas de mejora
- **Hit rate:** % de consultas donde Training RAG aporta contexto útil
- **Correction rate:** % de respuestas que necesitan corrección (debe bajar con el tiempo)
- **Feedback ratio:** 👍 vs 👎 (target: >90% positivo)
- **Gap coverage:** Áreas legales donde el sistema es débil → priorizar ingestion

### Jobs automáticos
| Job | Frecuencia | Qué hace |
|-----|-----------|----------|
| Feedback processor | Tiempo real | Procesa 👍/👎 inmediatamente |
| Correction ingester | Diario | Indexa correcciones de abogados |
| Quality report | Semanal | Genera reporte de áreas débiles |
| Anti-pattern extractor | Semanal | Analiza 👎 y extrae patrones |
| Retraining embeddings | Mensual | Re-embedea training data con nuevos patrones |

---

## Cómo interactúan los 3 RAGs

### Query Pipeline Unificado

```
Pregunta del usuario
    │
    ▼
[Query Rewriter]
    │ reformula para búsqueda legal
    ▼
[Router de RAGs]  ──── app/rag/router.py
    │ decide qué RAGs consultar:
    │
    │ Reglas:
    │ ├── SIEMPRE consulta Laws (fuente primaria)
    │ ├── SIEMPRE consulta Training (mejora continua)
    │ ├── Consulta Documents SI:
    │ │   ├── La pregunta es sobre doctrina/teoría
    │ │   ├── Laws no tiene suficientes resultados (score < umbral)
    │ │   └── El clasificador detecta necesidad de contexto profundo
    │ └── Solo Laws SI:
    │     └── Pregunta directa sobre un artículo específico
    │
    ▼
[Parallel Retrieval]
    │ ├── Laws:      top-5 chunks
    │ ├── Documents:  top-3 chunks (si aplica)
    │ └── Training:   top-3 chunks (si hay match >0.85)
    ▼
[Merge & Deduplicate]
    │ combina resultados, elimina duplicados
    ▼
[Cross-RAG Reranker]
    │ reranker unificado sobre todos los resultados
    │ ponderación: Laws (1.0) > Training (0.9) > Documents (0.8)
    │ boost: correcciones de abogado (1.2x)
    ▼
[Context Builder]
    │ arma el contexto para el LLM:
    │ ├── Documentos legales relevantes (Laws)
    │ ├── Doctrina/explicaciones (Documents)
    │ ├── Q&A previos validados (Training)
    │ └── Anti-patrones como instrucciones negativas
    ▼
[LLM (Claude)]
    │ genera respuesta final con citations multi-fuente
    ▼
Respuesta
```

### Collections en Qdrant

| Collection | Contenido | Tamaño estimado | Actualización |
|-----------|-----------|-----------------|---------------|
| `chilean_laws` | Legislación oficial | ~50K chunks | Semanal (cron) |
| `legal_documents` | Libros, PDFs, papers | ~20K chunks (crece) | Bajo demanda (upload) |
| `training_knowledge` | Q&A, correcciones, patrones | ~5K chunks (crece) | Tiempo real |

---

## Stack adicional para Documents + Training

| Componente | Tecnología | RAG |
|-----------|-----------|-----|
| OCR principal | Tesseract 5 (spa) | Documents |
| OCR avanzado | Surya | Documents |
| Layout detection | Surya / LayoutParser | Documents |
| Tablas PDF | Camelot | Documents |
| Pre-proc imagen | OpenCV + Pillow | Documents |
| Post-OCR spelling | SymSpell + dict legal | Documents |
| PDF texto | PyMuPDF (fitz) | Documents |
| Feedback capture | Custom (WhatsApp buttons) | Training |
| Quality tracking | Langfuse | Training |
| Correction UI | Dashboard web (futuro) | Training |
| Job scheduler | APScheduler / Celery | Training |
