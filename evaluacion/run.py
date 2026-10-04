"""Evaluación reproducible: `python -m evaluacion.run` (o `make eval`).

Compara el GraphRAG (grafo + herramientas) contra el RAG vectorial plano sobre los mismos
documentos, en las 100 preguntas del banco. Escribe evaluacion/preguntas.jsonl,
evaluacion/runs/<fecha>-deterministico.json y evaluacion/RESULTS.md. Sin LLM ni red.
"""
from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, median

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "src"))
sys.path.insert(0, str(AQUI.parent))

from asistente.consulta import MotorConsultas, clasificar, sin_tildes  # noqa: E402
from asistente.grafo import GrafoPlanta  # noqa: E402
from asistente.herramientas import Herramientas  # noqa: E402
from asistente.normalizacion import ResolutorTags  # noqa: E402
from asistente.rag_plano import RagPlano  # noqa: E402
from evaluacion import banco  # noqa: E402

FAMILIAS = ["identificacion", "topologia", "historial", "completitud"]
NOMBRE = {"identificacion": "Identificación", "topologia": "Topología", "historial": "Historial", "completitud": "Completitud"}


def correcto(q: dict, valor) -> bool:
    esp = q["esperado"]
    if q["tipo_respuesta"] == "lista":
        return isinstance(valor, list) and sorted(valor) == sorted(esp)
    if q["tipo_respuesta"] == "numero":
        return valor == esp
    return isinstance(valor, str) and sin_tildes(valor).strip() == sin_tildes(esp).strip()


def evidencia(q: dict, rag: RagPlano, d) -> set[str]:
    """Fragmentos que un lector perfecto necesitaría ver para responder (cota superior del RAG plano)."""
    frags = rag.frags
    t = q.get("tag")
    hist = [e for e in d.historial if e["tag"] == t] if t else []
    i = q["intencion"]
    if i in ("descripcion", "sistema", "area"):
        return {f.id for f in frags if f.id.startswith("LISTA-") and t in f.texto}
    if i == "fabricante":
        return {f"DS-{t}#p1"}
    if i in ("aislamiento", "envolvente"):
        manual = json.loads((AQUI / "aislamientos_manual.json").read_text(encoding="utf-8"))[t]
        nodos = {t, *manual["valvulas"], *manual["fuera_de_servicio"]}
        return {f.id for f in frags if f.id.startswith("LINEA-") and any(n in f.texto for n in nodos)}
    if i == "ultima_accion":
        return {e["id"] for e in hist}
    if i == "conteo_total":
        return {e["id"] for e in hist}
    if i == "conteo_modo":
        return {e["id"] for e in hist if e["modo"] == q["modo"]}
    if i == "conteo_anio":
        return {e["id"] for e in hist if e["fecha"].startswith(q["anio"])}
    if i == "faltantes_tag":
        return set() if q["esperado"] == "SIN_HOJA" else {f"DS-{t}#p1", f"DS-{t}#p2"}
    if i in ("sin_hoja_clase", "faltantes_clase"):
        miembros = [x for x, e in d.topologia["equipos"].items() if d.catalogos["clases"][e["tipo"]]["nombre"] == q["clase"]]
        ev = {f.id for f in frags if f.id.startswith("LISTA-") and any(m in f.texto for m in miembros)}
        if i == "sin_hoja_clase":
            return set()  # demostrar ausencia de un documento no es posible desde fragmentos recuperados
        return ev | {f"DS-{m}#p{p}" for m in miembros if any(x.id == f"DS-{m}#p1" for x in frags) for p in (1, 2)}
    raise ValueError(i)


def pct(x: float) -> str:
    return f"{100 * x:.1f} %"


def main() -> None:
    t0 = time.perf_counter()
    g = GrafoPlanta()
    d = g.d
    motor, rag = MotorConsultas(g), RagPlano(d, k=5)
    preguntas = banco.generar(d)
    (AQUI / "preguntas.jsonl").write_text("\n".join(json.dumps(q, ensure_ascii=False) for q in preguntas) + "\n", encoding="utf-8")

    filas = [evaluar(q, motor, rag, d) for q in preguntas]
    par = [evaluar(q, motor, rag, d) for q in banco.parafrasis(d)]
    _main_resto(t0, g, d, filas, par)


def evaluar(q: dict, motor: MotorConsultas, rag: RagPlano, d) -> dict:
    if True:
        a = time.perf_counter()
        r = motor.responder(q["pregunta"])
        ms_g = (time.perf_counter() - a) * 1000
        a = time.perf_counter()
        frags = rag.recuperar(q["pregunta"])
        ms_r = (time.perf_counter() - a) * 1000
        ev = evidencia(q, rag, d)
        ids = {f.id for f in frags}
        return {
            "id": q["id"], "familia": q["familia"], "intencion": q["intencion"], "pregunta": q["pregunta"],
            "enrutado": clasificar(q["pregunta"]),
            "grafo": {"valor": r.valor, "ok": correcto(q, r.valor), "tokens": r.tokens_contexto, "ms": round(ms_g, 2), "cypher": r.cypher},
            "rag": {"ok": bool(ev) and ev <= ids, "evidencia": sorted(ev), "recuperado": sorted(ids),
                    "tokens": rag.contexto_tokens(frags), "ms": round(ms_r, 2)},
        }


def _main_resto(t0, g, d, filas, par) -> None:
    # Aislamientos contra la lista manual (precisión y exhaustividad por válvula)
    manual = json.loads((AQUI / "aislamientos_manual.json").read_text(encoding="utf-8"))
    manual.pop("_origen")
    h = Herramientas(g)
    tp = fp = fn = exactos = 0
    detalle_ais = {}
    for t, m in manual.items():
        pred, ref = set(h.aislamientos(t)["valvulas"]), set(m["valvulas"])
        tp, fp, fn = tp + len(pred & ref), fp + len(pred - ref), fn + len(ref - pred)
        exactos += pred == ref
        detalle_ais[t] = {"predicho": sorted(pred), "manual": sorted(ref)}
    ais = {"equipos": len(manual), "precision": tp / (tp + fp), "exhaustividad": tp / (tp + fn), "exactos": exactos}

    # Normalización de tags en las órdenes
    resol = ResolutorTags(list(d.topologia["equipos"]))
    norm = defaultdict(int)
    for e in d.historial:
        r = resol.resolver(e["tag_escrito"])
        mal_escrito = e["tag_escrito"] != e["tag"]
        norm["mal_escritos"] += mal_escrito
        if r.tag is None:
            norm["conflicto"] += 1
        elif r.tag == e["tag"]:
            norm["correcto" + ("_mal_escrito" if mal_escrito else "")] += 1
        else:
            norm["incorrecto"] += 1
    norm["total"] = len(d.historial)

    # Detección de huecos de completitud contra la etiqueta del generador
    falt_ref = {(t, p) for t, ps in d.huecos["propiedades_faltantes"].items() for p in ps}
    falt_pred = {(t, p) for t, f in g.fichas.items() for p in f.faltantes}
    sin_hoja_ok = sorted(t for t in g.equipos() if t not in g.fichas) == sorted(d.huecos["sin_hoja"])

    res = {"familias": {}, "global": {}}
    for fam in FAMILIAS + ["global"]:
        sel = [f for f in filas if fam == "global" or f["familia"] == fam]
        res["familias" if fam != "global" else "global"][fam] = {
            "n": len(sel),
            "grafo_exactitud": mean(f["grafo"]["ok"] for f in sel),
            "rag_exactitud_cota": mean(f["rag"]["ok"] for f in sel),
            "grafo_tokens_mediana": median(f["grafo"]["tokens"] for f in sel),
            "rag_tokens_mediana": median(f["rag"]["tokens"] for f in sel),
            "enrutamiento": mean(f["enrutado"] == f["familia"] for f in sel),
        }
    run = {"fecha": date.today().isoformat(), "etiqueta": "deterministico-sin-llm", "semilla_planta": 14224,
           "semilla_banco": banco.SEMILLA_BANCO, "grafo": g.resumen(), "resultados": res, "aislamientos": ais,
           "aislamientos_detalle": detalle_ais, "normalizacion": dict(norm), "conflictos": g.conflictos,
           "completitud": {"faltantes_ref": len(falt_ref), "faltantes_detectados": len(falt_ref & falt_pred),
                           "falsos_positivos": len(falt_pred - falt_ref), "sin_hoja_exacto": sin_hoja_ok},
           "parafrasis": {"n": len(par), "grafo_exactitud": mean(f["grafo"]["ok"] for f in par),
                          "rag_exactitud_cota": mean(f["rag"]["ok"] for f in par),
                          "enrutamiento": mean(f["enrutado"] == f["familia"] for f in par)},
           "segundos": round(time.perf_counter() - t0, 2), "preguntas": filas, "preguntas_parafrasis": par}
    runs = AQUI / "runs"
    runs.mkdir(exist_ok=True)
    nombre_run = f"{run['fecha']}-deterministico.json"
    (runs / nombre_run).write_text(json.dumps(run, ensure_ascii=False, indent=1), encoding="utf-8")
    (AQUI / "RESULTS.md").write_text(informe(run, nombre_run), encoding="utf-8")
    gl = res["global"]["global"]
    print(f"run: evaluacion/runs/{nombre_run}")
    print(f"GraphRAG {pct(gl['grafo_exactitud'])} · RAG plano (cota) {pct(gl['rag_exactitud_cota'])} · "
          f"tokens mediana {gl['grafo_tokens_mediana']} vs {gl['rag_tokens_mediana']} · aislamientos P {pct(ais['precision'])} "
          f"R {pct(ais['exhaustividad'])} · {run['segundos']} s")


def informe(run: dict, nombre_run: str) -> str:
    r, a, n, c = run["resultados"], run["aislamientos"], run["normalizacion"], run["completitud"]
    L = [f"# Resultados · P1 Asistente de planta", "",
         f"Corrida `{run['etiqueta']}` del {run['fecha']} · artefacto `evaluacion/runs/{nombre_run}` · "
         f"regenerar con `make eval` (o `python -m evaluacion.run`).", "",
         "Datos **sintéticos** de planta-core (semilla 14224). Sin LLM: consulta por plantillas Cypher y redacción por plantilla.", "",
         f"Grafo: {run['grafo']['nodos']} nodos · {run['grafo']['relaciones']} relaciones.", "",
         "## Exactitud sobre las 100 preguntas", "",
         "| Familia | n | GraphRAG | RAG plano (cota superior) | Tokens mediana GraphRAG | Tokens mediana RAG | Enrutamiento |",
         "|---|---|---|---|---|---|---|"]
    for fam in FAMILIAS:
        x = r["familias"][fam]
        L.append(f"| {NOMBRE[fam]} | {x['n']} | {pct(x['grafo_exactitud'])} | {pct(x['rag_exactitud_cota'])} | "
                 f"{x['grafo_tokens_mediana']} | {x['rag_tokens_mediana']} | {pct(x['enrutamiento'])} |")
    g = r["global"]["global"]
    L += [f"| **Total** | {g['n']} | **{pct(g['grafo_exactitud'])}** | {pct(g['rag_exactitud_cota'])} | "
          f"{g['grafo_tokens_mediana']} | {g['rag_tokens_mediana']} | {pct(g['enrutamiento'])} |", "",
          "**Cómo leer la columna del RAG plano.** No hay LLM en esta corrida, así que no se mide la respuesta del RAG sino si "
          "los 5 fragmentos recuperados contienen toda la evidencia que necesitaría un lector perfecto. Es una cota superior: "
          "un RAG real con LLM no puede superarla. Las preguntas de ausencia (equipos sin hoja de datos) cuentan como fallo "
          "del RAG porque la ausencia no se demuestra con fragmentos recuperados.", "",
          "**Cómo leer la columna del GraphRAG.** Respuesta exacta: lista igual, número igual o texto igual. Las respuestas "
          "esperadas se calcularon desde los datos crudos de planta-core y, para topología, desde una lista escrita a mano; "
          "la verificación pregunta por pregunta por un ingeniero de planta está pendiente.", "",
          "## Robustez: 20 paráfrasis fuera de las plantillas", "",
          "El banco de 100 está redactado dentro del sublenguaje que reconoce el enrutador por reglas; por eso el 100 % mide "
          "recuperación estructural y ausencia de errores, no comprensión de lenguaje libre. Las 20 paráfrasis "
          "(`evaluacion/banco.py: PARAFRASIS`) están escritas a mano fuera de esas plantillas:", "",
          "| n | GraphRAG | RAG plano (cota superior) | Enrutamiento correcto |", "|---|---|---|---|",
          f"| {run['parafrasis']['n']} | {pct(run['parafrasis']['grafo_exactitud'])} | {pct(run['parafrasis']['rag_exactitud_cota'])} | "
          f"{pct(run['parafrasis']['enrutamiento'])} |", "",
          "Fallos del GraphRAG en paráfrasis:", ""]
    L += [f"- `{f['id']}` «{f['pregunta']}» → enrutada a *{f['enrutado']}* (esperado *{f['familia']}*), respuesta `{str(f['grafo']['valor'])[:60]}`"
          for f in run["preguntas_parafrasis"] if not f["grafo"]["ok"]] or ["- ninguno"]
    L += ["", "Esta brecha es la que debe cerrar la generación de Cypher con LLM (pendiente de llave).", "",
          "## Aislamientos propuestos contra la lista manual", "",
          "| Equipos críticos | Precisión por válvula | Exhaustividad por válvula | Equipos con lista idéntica |", "|---|---|---|---|",
          f"| {a['equipos']} | {pct(a['precision'])} | {pct(a['exhaustividad'])} | {a['exactos']}/{a['equipos']} |", "",
          "## Normalización de tags en las órdenes de trabajo", "",
          f"{n['total']} órdenes, {n['mal_escritos']} con el tag mal escrito. Resueltas bien: {n.get('correcto', 0) + n.get('correcto_mal_escrito', 0)} "
          f"(de ellas {n.get('correcto_mal_escrito', 0)} mal escritas) · al reporte de conflictos: {n.get('conflicto', 0)} · "
          f"resueltas a un tag equivocado: {n.get('incorrecto', 0)}.", "",
          "## Completitud de hojas de datos", "",
          f"Propiedades faltantes inyectadas: {c['faltantes_ref']} · detectadas: {c['faltantes_detectados']} · falsos positivos: "
          f"{c['falsos_positivos']} · lista de equipos sin hoja idéntica a la etiqueta: {'sí' if c['sin_hoja_exacto'] else 'no'}.", "",
          "## Pendiente", "",
          "| Medición | Requiere |", "|---|---|",
          "| Generación de Cypher con LLM y redacción con LLM | ANTHROPIC_API_KEY |",
          "| Carga y consultas sobre Neo4j 5 (`make neo4j`) | Demonio Docker |",
          "| Extracción desde PDFs reales con Docling o visión | PDFs del fabricante y llave de API |",
          "| Minutos para resolver un reporte de falla contra búsqueda manual | Cronometraje con usuarios |",
          "| Verificación a mano de las 100 respuestas esperadas | Ingeniero de planta |", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
