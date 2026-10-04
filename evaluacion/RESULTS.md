# Resultados · P1 Asistente de planta

Corrida `deterministico-sin-llm` del 2026-10-04 · artefacto `evaluacion/runs/2026-10-04-deterministico.json` · regenerar con `make eval` (o `python -m evaluacion.run`).

Datos **sintéticos** de planta-core (semilla 14224). Sin LLM: consulta por plantillas Cypher y redacción por plantilla.

Grafo: 854 nodos · 1745 relaciones.

## Exactitud sobre las 100 preguntas

| Familia | n | GraphRAG | RAG plano (cota superior) | Tokens mediana GraphRAG | Tokens mediana RAG | Enrutamiento |
|---|---|---|---|---|---|---|
| Identificación | 25 | 100.0 % | 36.0 % | 16 | 176 | 100.0 % |
| Topología | 25 | 100.0 % | 0.0 % | 17 | 152 | 100.0 % |
| Historial | 25 | 100.0 % | 28.0 % | 14 | 222 | 100.0 % |
| Completitud | 25 | 100.0 % | 0.0 % | 14 | 216 | 100.0 % |
| **Total** | 100 | **100.0 %** | 16.0 % | 15.0 | 189.5 | 100.0 % |

**Cómo leer la columna del RAG plano.** No hay LLM en esta corrida, así que no se mide la respuesta del RAG sino si los 5 fragmentos recuperados contienen toda la evidencia que necesitaría un lector perfecto. Es una cota superior: un RAG real con LLM no puede superarla. Las preguntas de ausencia (equipos sin hoja de datos) cuentan como fallo del RAG porque la ausencia no se demuestra con fragmentos recuperados.

**Cómo leer la columna del GraphRAG.** Respuesta exacta: lista igual, número igual o texto igual. Las respuestas esperadas se calcularon desde los datos crudos de planta-core y, para topología, desde una lista escrita a mano; la verificación pregunta por pregunta por un ingeniero de planta está pendiente.

## Robustez: 20 paráfrasis fuera de las plantillas

El banco de 100 está redactado dentro del sublenguaje que reconoce el enrutador por reglas; por eso el 100 % mide recuperación estructural y ausencia de errores, no comprensión de lenguaje libre. Las 20 paráfrasis (`evaluacion/banco.py: PARAFRASIS`) están escritas a mano fuera de esas plantillas:

| n | GraphRAG | RAG plano (cota superior) | Enrutamiento correcto |
|---|---|---|---|
| 20 | 10.0 % | 20.0 % | 20.0 % |

Fallos del GraphRAG en paráfrasis:

- `PAR-01` «Dame la descripción del 1205-C-01» → enrutada a *documental* (esperado *identificacion*), respuesta `MANUAL DE OPERACIÓN Y MANTENIMIENTO
Modelo AC-8 · Calderería`
- `PAR-02` «¿Para qué sirve el 1105-V-03?» → enrutada a *documental* (esperado *identificacion*), respuesta `OPERACIÓN
Antes de arrancar el modelo AC-8, verificar alinea`
- `PAR-04` «¿Dónde queda el 1305-K-01, en qué unidad?» → enrutada a *documental* (esperado *identificacion*), respuesta `OPERACIÓN
Antes de arrancar el modelo AC-8, verificar alinea`
- `PAR-05` «¿Qué marca es la bomba 1105-P-02?» → enrutada a *documental* (esperado *identificacion*), respuesta `SOLUCIÓN DE PROBLEMAS · modelo RC-2400
- Síntoma: parada esp`
- `PAR-06` «¿Qué tengo que cerrar para intervenir la 1405-P-02?» → enrutada a *documental* (esperado *topologia*), respuesta `SOLUCIÓN DE PROBLEMAS · modelo CV-2-300
- Síntoma: falla al `
- `PAR-07` «Lista de bloqueos para trabajar en el 1205-C-02» → enrutada a *documental* (esperado *topologia*), respuesta `OPERACIÓN
Antes de arrancar el modelo AC-8, verificar alinea`
- `PAR-08` «¿Con qué válvulas se bloquea el 1105-E-01?» → enrutada a *documental* (esperado *topologia*), respuesta `OPERACIÓN
Antes de arrancar el modelo AC-8, verificar alinea`
- `PAR-09` «Si aíslo el 1305-E-01, ¿qué más se para?» → enrutada a *documental* (esperado *topologia*), respuesta `SOLUCIÓN DE PROBLEMAS · modelo AC-8
- Síntoma: fuga externa `
- `PAR-10` «Válvulas a cerrar para sacar de servicio el 1105-V-02» → enrutada a *documental* (esperado *topologia*), respuesta `OPERACIÓN
Antes de arrancar el modelo AC-8, verificar alinea`
- `PAR-11` «¿Cuántas averías ha tenido el 1205-C-01?» → enrutada a *documental* (esperado *historial*), respuesta `OPERACIÓN
Antes de arrancar el modelo AC-8, verificar alinea`
- `PAR-12` «¿Cuál fue la última intervención del 1105-P-01?» → enrutada a *documental* (esperado *historial*), respuesta `MANUAL DE OPERACIÓN Y MANTENIMIENTO
Modelo AC-8 · Calderería`
- `PAR-13` «¿Cuántas órdenes correctivas tuvo el 1405-P-01 durante 2024?» → enrutada a *documental* (esperado *historial*), respuesta `OPERACIÓN
Antes de arrancar el modelo AC-8, verificar alinea`
- `PAR-14` «Número de fallas registradas del 1305-V-02» → enrutada a *documental* (esperado *historial*), respuesta `MANUAL DE OPERACIÓN Y MANTENIMIENTO
Modelo AC-8 · Calderería`
- `PAR-15` «¿Qué le hicieron al 1205-E-01 la vez más reciente que se dañó?» → enrutada a *documental* (esperado *historial*), respuesta `SOLUCIÓN DE PROBLEMAS · modelo CV-2-300
- Síntoma: falla al `
- `PAR-16` «¿Está completa la hoja de datos del 1205-C-01?» → enrutada a *completitud* (esperado *completitud*), respuesta `None`
- `PAR-18` «¿Cuáles intercambiadores no tienen datasheet?» → enrutada a *documental* (esperado *completitud*), respuesta `MANUAL DE OPERACIÓN Y MANTENIMIENTO
Modelo AC-8 · Calderería`
- `PAR-19` «¿Qué compresores tienen la ficha incompleta?» → enrutada a *documental* (esperado *completitud*), respuesta `MANUAL DE OPERACIÓN Y MANTENIMIENTO
Modelo RC-2400 · Compres`
- `PAR-20` «¿El 1405-PCV-01 tiene hoja de datos?» → enrutada a *completitud* (esperado *completitud*), respuesta `None`

Esta brecha es la que debe cerrar la generación de Cypher con LLM (pendiente de llave).

## Aislamientos propuestos contra la lista manual

| Equipos críticos | Precisión por válvula | Exhaustividad por válvula | Equipos con lista idéntica |
|---|---|---|---|
| 21 | 100.0 % | 100.0 % | 21/21 |

## Normalización de tags en las órdenes de trabajo

202 órdenes, 32 con el tag mal escrito. Resueltas bien: 199 (de ellas 29 mal escritas) · al reporte de conflictos: 3 · resueltas a un tag equivocado: 0.

## Completitud de hojas de datos

Propiedades faltantes inyectadas: 7 · detectadas: 7 · falsos positivos: 0 · lista de equipos sin hoja idéntica a la etiqueta: sí.

## Pendiente

| Medición | Requiere |
|---|---|
| Generación de Cypher con LLM y redacción con LLM | ANTHROPIC_API_KEY |
| Carga y consultas sobre Neo4j 5 (`make neo4j`) | Demonio Docker |
| Extracción desde PDFs reales con Docling o visión | PDFs del fabricante y llave de API |
| Minutos para resolver un reporte de falla contra búsqueda manual | Cronometraje con usuarios |
| Verificación a mano de las 100 respuestas esperadas | Ingeniero de planta |
