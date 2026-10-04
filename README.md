# P1 · Asistente de planta sobre grafo de conocimiento

Recibe un reporte de falla en lenguaje natural, identifica el equipo por su tag y devuelve su ficha, su
historial, las fallas similares en equipos de la misma clase y el **borrador** de solicitud de entrega a
operaciones con los aislamientos que se derivan de la topología. El ingeniero aprueba antes de emitir.

Primer proyecto del portafolio de planeación y control sobre la planta de referencia común
([`planta-core`](https://github.com/Edgar-Suarez-creator/planta-core)): estación de compresión de gas con cuatro unidades (1105 deshidratación con
TEG, 1205 compresión, 1305 aire de instrumentos, 1405 agua contra incendio) y tags ISA 5.1 `AREA-TIPO-NN`.

## Cifra industrial de referencia

Los ingenieros dedican entre el 40 % y el 60 % de su tiempo a buscar y validar información, cifra atribuida
al NIST y citada por [Plant Engineering](https://www.plantengineering.com/scanning-your-perspective/)
(fuente secundaria; la publicación primaria del NIST está por verificar). Este sistema ataca esa búsqueda
para el caso de un reporte de falla.

## Arquitectura

```
reporte de falla ──► resolver tag (reglas + similitud) ──► clasificar síntoma (modo ISO 14224)
                                                              │
        ┌──────────────── herramientas deterministas ─────────┴──────────────────────┐
        │ buscar_equipo(tag) · historial(tag) · fallas_similares(clase, modo) · aislamientos(tag) │
        └──────────────────────────────┬──────────────────────────────────────────────┘
                                       ▼
          grafo de conocimiento (networkx en memoria · exportable a Neo4j 5)
          Area ─ Sistema ─ Equipo ─ Componente · Documento · Falla ─ Intervencion
          catálogos ISO 14224 como nodos · CONECTA_A · AISLA · DOCUMENTA · PRESENTO_FALLA
                                       ▼
          plantilla de solicitud (campos fijos) ──► BORRADOR ──► aprobación humana registrada ──► emisión
```

Preguntas al asistente: un **enrutador** decide entre consulta estructural al grafo (plantillas Cypher para
identificación, topología, historial y completitud) y búsqueda por similitud sobre los manuales (preguntas
documentales). El agente **no calcula**: llama herramientas y redacta; toda salida cita orden, documento y
página, o el nodo del grafo.

| Paso del manual | Implementación | Estado |
|---|---|---|
| 1. Ontología en Neo4j | `src/asistente/grafo.py`, exportada a `neo4j/planta.cypher` | en memoria ✔ · Neo4j escrito, no probado aquí (sin Docker) |
| 2. Jerarquía ISO 14224 y códigos de modo, causa y mecanismo como nodos | `planta-core/planta_core/ontologia/iso14224.py` | ✔ (pesos de modos por clase: supuestos declarados) |
| 3. Topología DEXPI del proyecto 2 | `planta-core/planta_core/planta.py` (cadenas de línea escritas a mano) | sustituto hasta que exista P2 · pyDEXPI pendiente |
| 4. Propiedades de datasheets con cita, validadas con Pydantic | `src/asistente/extraccion.py` (reglas sobre texto) | ✔ · Docling/visión sobre PDFs reales pendiente |
| 5. Historial sintético 3–15 eventos por equipo crítico en 5 años | `planta-core/planta_core/generadores/historial.py` | ✔ semilla 14224 |
| 6. Tags duplicados o mal escritos + reporte de conflictos | `src/asistente/normalizacion.py` | ✔ (TF-IDF de caracteres en vez de embeddings) |
| 7. Recuperación híbrida con enrutador | `src/asistente/consulta.py` | ✔ por reglas · Cypher con LLM pendiente |
| 8. Aislamientos hasta la primera válvula de bloqueo | `src/asistente/aislamientos.py` | ✔ |
| 9. Agente con cuatro herramientas | `src/asistente/herramientas.py`, `agente.py` | ✔ |
| 10. Plantilla de solicitud de entrega | `src/asistente/agente.py` | ✔ con aprobación registrada |

## Inicio rápido

```bash
make setup   # instala planta-core y este paquete y genera los datos (semilla 14224)
make test    # 9 pruebas
make eval    # reproduce evaluacion/RESULTS.md
make demo    # http://127.0.0.1:8001, sin credenciales
```

En Windows sin `make`: `python tareas.py setup|test|eval|demo|cypher`. Se espera `planta-core` como
carpeta hermana (`../planta-core`); para eso, clone los dos repositorios en la misma carpeta:

```bash
git clone https://github.com/Edgar-Suarez-creator/planta-core.git
git clone https://github.com/Edgar-Suarez-creator/p1-asistente-planta.git
```

Autor: Edgar R. Suárez Macías · planeador e ingeniero de sistemas · portafolio: https://edgar-suarez-creator.github.io/portafolio/

Desde la terminal, un reporte de punta a punta (imprime el borrador; no aprueba ni emite):

```bash
python -m asistente "La bomba 1105p01 está botando glicol por el sello"
```

## Resultados medidos (corrida `deterministico-sin-llm`, 2026-10-04)

Detalle y artefacto: [`evaluacion/RESULTS.md`](evaluacion/RESULTS.md).

| Métrica | GraphRAG | Línea base | Línea base usada |
|---|---|---|---|
| Exactitud sobre las 100 preguntas | **100 %** | 16 % (cota superior) | RAG vectorial plano, TF-IDF top-5 sobre los mismos documentos |
| · Identificación / Topología / Historial / Completitud | 100 / 100 / 100 / 100 % | 36 / 0 / 28 / 0 % | ídem |
| Exactitud en 20 paráfrasis fuera de las plantillas | **10 %** | 20 % (cota superior) | ídem |
| Tokens de contexto por respuesta (mediana) | 15 | 190 | ídem |
| Precisión / exhaustividad de aislamientos (21 equipos críticos) | 100 % / 100 % | — | lista definida a mano sobre las cadenas de línea |
| Tags mal escritos en órdenes resueltos bien | 29 de 32 · 3 al reporte de conflictos · 0 equivocados | — | — |
| Minutos para resolver un reporte de falla | pendiente | pendiente | búsqueda manual cronometrada |

**Cómo leer estas cifras.** El 100 % se obtiene porque el banco está redactado dentro del sublenguaje que
reconoce el enrutador por reglas, sobre datos sintéticos cuyas respuestas esperadas salen de los mismos
generadores: mide que la recuperación estructural y los recorridos no tienen errores, no que el sistema
entienda lenguaje libre. Las 20 paráfrasis lo muestran: con redacción libre el enrutador manda 16 de 20 a la
ruta documental y falla en 18. Cerrar esa brecha es el trabajo de la generación de Cypher con LLM. La columna del
RAG plano no es una respuesta de LLM sino si los 5 fragmentos recuperados contienen toda la evidencia: un
RAG real no puede superarla.

## Origen de los datos

| Dato | Origen |
|---|---|
| Topología, equipos, sistemas | sintético, escrito a mano en `planta-core` |
| Historial de fallas (202 órdenes) | sintético, semilla 14224; pesos de modos por clase supuestos, calibración con OREDA pendiente |
| Hojas de datos y manuales (65 documentos) | sintéticos, fabricantes y modelos ficticios; huecos inyectados y etiquetados |
| Códigos ISO 14224 (modos, mecanismos, causas, jerarquía) | público (norma) |
| Propiedades obligatorias por clase | derivado, enfoque CFIHOS 2.0; mapeo a códigos oficiales pendiente |
| Banco de 100 preguntas | derivado de los datos sintéticos; aislamientos desde lista manual; verificación por un ingeniero pendiente |

## Lo que el sistema no hace

- No emite permisos, aislamientos ni solicitudes: produce un borrador y exige aprobación con nombre, que queda
  en `app/aprobaciones.jsonl`; `Agente.emitir` falla sin ella.
- No elige el equipo cuando el reporte no trae un tag legible: lista candidatos y pide el tag de la placa.
- No propone aislamiento en ramas que llegan a un límite de batería sin válvula (p. ej. succión atmosférica de
  los compresores de aire): las marca como rama abierta.
- No entiende preguntas redactadas fuera de sus plantillas (10 % en paráfrasis) hasta que exista la ruta LLM.
- No ha sido probado con datos de una planta real, ni contra Neo4j, ni dentro de Docker en este entorno.

## Estructura

```
src/asistente/   grafo, extracción, normalización, aislamientos, herramientas, consulta, RAG plano, agente
evaluacion/      banco de preguntas, lista manual de aislamientos, run.py, RESULTS.md, runs/
app/             servidor.py (demo local), index.html, demo.json (versión estática)
neo4j/           planta.cypher (exportado con `make cypher`)
notebooks/       exploración
tests/
```
