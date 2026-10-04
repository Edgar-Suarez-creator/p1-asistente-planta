"""Banco de 100 preguntas en cuatro familias, con respuesta esperada calculada desde los datos
crudos de planta-core (no desde el grafo ni desde el motor), y aislamientos desde la lista manual.

Declaración: las respuestas esperadas son derivadas de los datos sintéticos y de una lista
escrita a mano; la verificación a mano pregunta por pregunta por un ingeniero de planta está
PENDIENTE. Así se reporta en RESULTS.md.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

AQUI = Path(__file__).resolve().parent
SEMILLA_BANCO = 7


def _mal_escrito(tag: str, rng: random.Random) -> str:
    area, tipo, num = tag.split("-")
    return rng.choice([f"{area}{tipo}{num}", f"{area}-{tipo.lower()}-{int(num)}", f"{area} {tipo} {num}", f"{area}_{tipo}_{num}"])


def generar(datos) -> list[dict]:
    rng = random.Random(SEMILLA_BANCO)
    topo, cat, hist, huecos = datos.topologia, datos.catalogos, datos.historial, datos.huecos
    equipos = topo["equipos"]
    clase_de = lambda t: cat["clases"][equipos[t]["tipo"]]["nombre"]
    con_hoja = {d["tag"]: d for d in datos.documentos if d["tipo"] == "hoja_de_datos"}
    manual = json.loads((AQUI / "aislamientos_manual.json").read_text(encoding="utf-8"))
    manual.pop("_origen")
    escribir = lambda t: _mal_escrito(t, rng) if rng.random() < 0.3 else t
    qs: list[dict] = []

    def add(familia, intencion, pregunta, esperado, tipo, **extra):
        qs.append({"id": f"{familia[:3].upper()}-{sum(q['familia'] == familia for q in qs) + 1:02d}", "familia": familia,
                   "intencion": intencion, "pregunta": pregunta, "esperado": esperado, "tipo_respuesta": tipo, **extra})

    # ---------------- Identificación (25)
    tags = sorted(equipos)
    for t in rng.sample(tags, 7):
        add("identificacion", "descripcion", f"¿Qué equipo es el {escribir(t)}?", equipos[t]["descripcion"], "texto", tag=t)
    for t in rng.sample(tags, 6):
        add("identificacion", "sistema", f"¿En qué sistema está el {escribir(t)}?", topo["sistemas"][equipos[t]["sistema"]]["nombre"], "texto", tag=t)
    for t in rng.sample(tags, 6):
        area = topo["sistemas"][equipos[t]["sistema"]]["area"]
        add("identificacion", "area", f"¿A qué área pertenece el {escribir(t)}?", topo["areas"][area], "texto", tag=t)
    for t in rng.sample(sorted(con_hoja), 6):
        fab = next(l.split(": ", 1)[1] for l in con_hoja[t]["paginas"][0].splitlines() if l.startswith("Fabricante"))
        add("identificacion", "fabricante", f"¿Quién es el fabricante del {escribir(t)}?", fab, "texto", tag=t)

    # ---------------- Topología (25)
    for t, v in manual.items():
        add("topologia", "aislamiento", f"¿Qué válvulas de bloqueo aíslan el {escribir(t)}?", v["valvulas"], "lista", tag=t)
    for t in ("1105-V-04", "1205-E-01", "1305-E-01", "1105-P-01"):
        add("topologia", "envolvente", f"¿Qué otros equipos quedan fuera de servicio al cerrar las válvulas que aíslan el {t}?",
            manual[t]["fuera_de_servicio"], "lista", tag=t)

    # ---------------- Historial (25)
    por_tag: dict[str, list[dict]] = {}
    for e in hist:
        por_tag.setdefault(e["tag"], []).append(e)
    criticos = sorted(t for t in equipos if equipos[t]["critico"])
    for t in rng.sample(criticos, 9):
        ult = max(por_tag[t], key=lambda e: (e["fecha"], e["id"]))
        add("historial", "ultima_accion", f"¿Qué se hizo la última vez que falló el {escribir(t)}?", ult["accion"], "texto", tag=t)
    for t in rng.sample(criticos, 8):
        modo = rng.choice(sorted({e["modo"] for e in por_tag[t]}))
        n = sum(e["modo"] == modo for e in por_tag[t])
        add("historial", "conteo_modo", f"¿Cuántas veces ha fallado el {escribir(t)} por {cat['modos'][modo].lower()} ({modo})?", n, "numero",
            tag=t, modo=modo)
    for t in rng.sample(criticos, 8):
        anio = rng.choice(["2022", "2023", "2024", "2025"])
        n = sum(e["fecha"].startswith(anio) for e in por_tag[t])
        add("historial", "conteo_anio", f"¿Cuántas fallas tuvo el {escribir(t)} en {anio}?", n, "numero", tag=t, anio=anio)

    # ---------------- Completitud (25)
    falt = huecos["propiedades_faltantes"]
    completos = [t for t in sorted(con_hoja) if t not in falt]
    elegidos = sorted(falt) + huecos["sin_hoja"] + rng.sample(completos, 13 - len(falt) - len(huecos["sin_hoja"]))
    for t in elegidos:
        esperado = "SIN_HOJA" if t in huecos["sin_hoja"] else falt.get(t, [])
        add("completitud", "faltantes_tag", f"¿Qué propiedades obligatorias le faltan al {escribir(t)}?", esperado,
            "texto" if esperado == "SIN_HOJA" else "lista", tag=t)
    clases = sorted({clase_de(t) for t in equipos})
    for c in rng.sample(clases, 6):
        sel = sorted(t for t in huecos["sin_hoja"] if clase_de(t) == c)
        add("completitud", "sin_hoja_clase", f"¿Qué equipos de la clase {c} no tienen hoja de datos?", sel, "lista", clase=c)
    for c in rng.sample(clases, 6):
        sel = sorted(t for t in falt if clase_de(t) == c)
        add("completitud", "faltantes_clase", f"¿Qué equipos de la clase {c} tienen propiedades obligatorias faltantes?", sel, "lista", clase=c)

    assert len(qs) == 100, len(qs)
    return qs


# Paráfrasis escritas a mano FUERA del sublenguaje de las plantillas, para medir cuánto se
# cae el enrutador por reglas con redacción libre. (familia, intención, pregunta, tag, extra)
PARAFRASIS = [
    ("identificacion", "descripcion", "Dame la descripción del 1205-C-01", "1205-C-01", {}),
    ("identificacion", "descripcion", "¿Para qué sirve el 1105-V-03?", "1105-V-03", {}),
    ("identificacion", "sistema", "¿A qué sistema pertenece la 1405-P-03?", "1405-P-03", {}),
    ("identificacion", "area", "¿Dónde queda el 1305-K-01, en qué unidad?", "1305-K-01", {}),
    ("identificacion", "fabricante", "¿Qué marca es la bomba 1105-P-02?", "1105-P-02", {}),
    ("topologia", "aislamiento", "¿Qué tengo que cerrar para intervenir la 1405-P-02?", "1405-P-02", {}),
    ("topologia", "aislamiento", "Lista de bloqueos para trabajar en el 1205-C-02", "1205-C-02", {}),
    ("topologia", "aislamiento", "¿Con qué válvulas se bloquea el 1105-E-01?", "1105-E-01", {}),
    ("topologia", "envolvente", "Si aíslo el 1305-E-01, ¿qué más se para?", "1305-E-01", {}),
    ("topologia", "aislamiento", "Válvulas a cerrar para sacar de servicio el 1105-V-02", "1105-V-02", {}),
    ("historial", "conteo_total", "¿Cuántas averías ha tenido el 1205-C-01?", "1205-C-01", {}),
    ("historial", "ultima_accion", "¿Cuál fue la última intervención del 1105-P-01?", "1105-P-01", {}),
    ("historial", "conteo_anio", "¿Cuántas órdenes correctivas tuvo el 1405-P-01 durante 2024?", "1405-P-01", {"anio": "2024"}),
    ("historial", "conteo_total", "Número de fallas registradas del 1305-V-02", "1305-V-02", {}),
    ("historial", "ultima_accion", "¿Qué le hicieron al 1205-E-01 la vez más reciente que se dañó?", "1205-E-01", {}),
    ("completitud", "faltantes_tag", "¿Está completa la hoja de datos del 1205-C-01?", "1205-C-01", {}),
    ("completitud", "faltantes_tag", "¿Qué datos le faltan a la ficha del 1305-V-02?", "1305-V-02", {}),
    ("completitud", "sin_hoja_clase", "¿Cuáles intercambiadores no tienen datasheet?", None, {"clase": "Intercambiador de calor"}),
    ("completitud", "faltantes_clase", "¿Qué compresores tienen la ficha incompleta?", None, {"clase": "Compresor"}),
    ("completitud", "faltantes_tag", "¿El 1405-PCV-01 tiene hoja de datos?", "1405-PCV-01", {}),
]


def parafrasis(datos) -> list[dict]:
    topo, cat, hist, huecos = datos.topologia, datos.catalogos, datos.historial, datos.huecos
    equipos = topo["equipos"]
    manual = json.loads((AQUI / "aislamientos_manual.json").read_text(encoding="utf-8"))
    hojas = {d["tag"]: d for d in datos.documentos if d["tipo"] == "hoja_de_datos"}
    clase_de = lambda t: cat["clases"][equipos[t]["tipo"]]["nombre"]
    out = []
    for n, (fam, intencion, pregunta, tag, extra) in enumerate(PARAFRASIS, 1):
        h = [e for e in hist if e["tag"] == tag]
        tipo = "texto"
        if intencion == "descripcion":
            esp = equipos[tag]["descripcion"]
        elif intencion == "sistema":
            esp = topo["sistemas"][equipos[tag]["sistema"]]["nombre"]
        elif intencion == "area":
            esp = topo["areas"][topo["sistemas"][equipos[tag]["sistema"]]["area"]]
        elif intencion == "fabricante":
            esp = next(l.split(": ", 1)[1] for l in hojas[tag]["paginas"][0].splitlines() if l.startswith("Fabricante"))
        elif intencion in ("aislamiento", "envolvente"):
            esp, tipo = manual[tag]["valvulas" if intencion == "aislamiento" else "fuera_de_servicio"], "lista"
        elif intencion == "conteo_total":
            esp, tipo = len(h), "numero"
        elif intencion == "conteo_anio":
            esp, tipo = sum(e["fecha"].startswith(extra["anio"]) for e in h), "numero"
        elif intencion == "ultima_accion":
            esp = max(h, key=lambda e: (e["fecha"], e["id"]))["accion"]
        elif intencion == "faltantes_tag":
            if tag in huecos["sin_hoja"]:
                esp = "SIN_HOJA"
            else:
                esp, tipo = huecos["propiedades_faltantes"].get(tag, []), "lista"
        elif intencion == "sin_hoja_clase":
            esp, tipo = sorted(t for t in huecos["sin_hoja"] if clase_de(t) == extra["clase"]), "lista"
        else:
            esp, tipo = sorted(t for t in huecos["propiedades_faltantes"] if clase_de(t) == extra["clase"]), "lista"
        out.append({"id": f"PAR-{n:02d}", "familia": fam, "intencion": intencion, "pregunta": pregunta, "esperado": esp,
                    "tipo_respuesta": tipo, "tag": tag, **extra})
    return out
