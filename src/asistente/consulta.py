"""Recuperación híbrida: enrutador + consulta estructurada al grafo o búsqueda en manuales.

Preguntas estructurales (identificación, topología, historial, completitud) → plantilla de
consulta Cypher ejecutada sobre el grafo. Preguntas documentales → búsqueda por similitud sobre
las páginas de manuales. El enrutador y la generación de la consulta son reglas en código; la
ruta con un LLM que genere Cypher libre queda pendiente (requiere ANTHROPIC_API_KEY) y se
compara contra estas plantillas cuando exista la llave.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .grafo import GrafoPlanta
from .herramientas import Herramientas
from .normalizacion import ResolutorTags


def sin_tildes(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def tokens(obj) -> int:
    """Tokens aproximados (caracteres / 4) del contexto entregado al redactor."""
    return max(1, len(obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)) // 4)


@dataclass
class Respuesta:
    pregunta: str
    familia: str
    intencion: str
    valor: object
    cypher: str = ""
    tag: str | None = None
    citas: list[str] = field(default_factory=list)
    tokens_contexto: int = 0

    def dict(self) -> dict:
        return asdict(self)


REGLAS_FAMILIA = [
    ("documental", ("manual", "cada cuantos dias", "recomienda el fabricante", "procedimiento")),
    ("completitud", ("hoja de datos", "propiedades obligatorias", "faltan")),
    ("topologia", ("aisla", "fuera de servicio", "valvulas de bloqueo")),
    ("historial", ("cuantas veces", "cuantas fallas", "ultima vez", "historial")),
    ("identificacion", ("que equipo es", "sistema", "area", "fabricante", "modelo")),
]


def clasificar(pregunta: str) -> str:
    p = sin_tildes(pregunta)
    for familia, claves in REGLAS_FAMILIA:
        if any(c in p for c in claves):
            return familia
    return "documental"


class MotorConsultas:
    def __init__(self, grafo: GrafoPlanta):
        self.g = grafo
        self.h = Herramientas(grafo)
        self.resolutor = ResolutorTags(list(grafo.d.topologia["equipos"]))
        self.clases = sorted({a["clase"] for a in grafo.equipos().values()}, key=len, reverse=True)
        self.modos = grafo.d.catalogos["modos"]
        self._paginas = [(d["id"], i, p) for d in grafo.d.documentos if d["tipo"] == "manual" for i, p in enumerate(d["paginas"], 1)]
        self._vec = TfidfVectorizer(preprocessor=sin_tildes)
        self._mat = self._vec.fit_transform([p for *_x, p in self._paginas])

    # ---------------------------------------------------------------- análisis
    def _tag(self, pregunta: str) -> str | None:
        return self.resolutor.resolver(pregunta).tag

    def _clase(self, pregunta: str) -> str | None:
        p = sin_tildes(pregunta)
        return next((c for c in self.clases if sin_tildes(c) in p), None)

    def _modo(self, pregunta: str) -> str | None:
        m = re.search(r"\(([A-Z]{3})\)", pregunta)
        if m and m.group(1) in self.modos:
            return m.group(1)
        p = sin_tildes(pregunta)
        return next((c for c, n in sorted(self.modos.items(), key=lambda x: -len(x[1])) if sin_tildes(n) in p), None)

    # ---------------------------------------------------------------- respuesta
    def responder(self, pregunta: str) -> Respuesta:
        familia = clasificar(pregunta)
        p = sin_tildes(pregunta)
        tag = self._tag(pregunta)
        r = getattr(self, f"_{familia}")(pregunta, p, tag)
        r.tokens_contexto = tokens({"valor": r.valor, "citas": r.citas})
        return r

    def _identificacion(self, q: str, p: str, tag: str | None) -> Respuesta:
        if not tag or not (ficha := self.h.buscar_equipo(tag)):
            return Respuesta(q, "identificacion", "sin_tag", None)
        base = "MATCH (e:Equipo {tag: $tag})"
        if "fabricante" in p:
            prop = ficha["propiedades"].get("fabricante")
            return Respuesta(q, "identificacion", "fabricante", prop["valor"] if prop else None,
                             f"{base}<-[:DOCUMENTA]-(d:Documento {{tipo:'hoja_de_datos'}}) RETURN d.fabricante", tag,
                             [prop["cita"]] if prop else [])
        if "sistema" in p:
            return Respuesta(q, "identificacion", "sistema", ficha["sistema"],
                             f"{base}-[:PERTENECE_A]->(s:Sistema) RETURN s.nombre", tag, [f"grafo:{tag}"])
        if "area" in p:
            return Respuesta(q, "identificacion", "area", ficha["area"],
                             f"{base}-[:PERTENECE_A]->(:Sistema)-[:PERTENECE_A]->(a:Area) RETURN a.nombre", tag, [f"grafo:{tag}"])
        return Respuesta(q, "identificacion", "descripcion", ficha["descripcion"], f"{base} RETURN e.descripcion, e.clase",
                         tag, [f"grafo:{tag}"])

    def _topologia(self, q: str, p: str, tag: str | None) -> Respuesta:
        if not tag:
            return Respuesta(q, "topologia", "sin_tag", None)
        a = self.h.aislamientos(tag)
        if "fuera de servicio" in p:
            return Respuesta(q, "topologia", "envolvente", a["fuera_de_servicio"],
                             "MATCH (v)-[:AISLA]->(e:Equipo {tag: $tag}) WITH collect(v) AS vs "
                             "MATCH p=(e)-[:CONECTA_A*]-(x:Equipo) WHERE NONE(n IN nodes(p)[1..] WHERE n IN vs) RETURN DISTINCT x.tag",
                             tag, [f"grafo:{tag}"])
        valvulas = sorted(self.g.entrantes(tag, "AISLA"))
        return Respuesta(q, "topologia", "aislamiento", valvulas,
                         "MATCH (v:Equipo {tipo:'HV'})-[:AISLA]->(e:Equipo {tag: $tag}) RETURN v.tag", tag, [f"grafo:{tag}"])

    def _historial(self, q: str, p: str, tag: str | None) -> Respuesta:
        if not tag:
            return Respuesta(q, "historial", "sin_tag", None)
        hist = self.h.historial(tag)
        base = "MATCH (e:Equipo {tag: $tag})-[:PRESENTO_FALLA]->(f:Falla)"
        if "ultima vez" in p:
            ult = hist[-1] if hist else None
            return Respuesta(q, "historial", "ultima_accion", ult["accion"] if ult else None,
                             f"{base}-[:ATENDIDA_POR]->(i) RETURN i.accion ORDER BY f.fecha DESC LIMIT 1", tag,
                             [ult["orden"]] if ult else [])
        modo = self._modo(q)
        if modo:
            sel = [h for h in hist if h["modo"] == modo]
            return Respuesta(q, "historial", "conteo_modo", len(sel),
                             f"{base}-[:TIENE_MODO]->(:ModoFalla {{codigo: '{modo}'}}) RETURN count(f)", tag, [h["orden"] for h in sel])
        anio = re.search(r"\b(20\d\d)\b", q)
        if anio:
            sel = [h for h in hist if h["fecha"].startswith(anio.group(1))]
            return Respuesta(q, "historial", "conteo_anio", len(sel),
                             f"{base} WHERE f.fecha STARTS WITH '{anio.group(1)}' RETURN count(f)", tag, [h["orden"] for h in sel])
        return Respuesta(q, "historial", "conteo_total", len(hist), f"{base} RETURN count(f)", tag, [h["orden"] for h in hist])

    def _completitud(self, q: str, p: str, tag: str | None) -> Respuesta:
        clase = self._clase(q)
        if tag and "le faltan" in p:
            ficha = self.h.buscar_equipo(tag)
            valor = "SIN_HOJA" if not ficha["hoja_de_datos"] else ficha["faltantes"]
            return Respuesta(q, "completitud", "faltantes_tag", valor,
                             "MATCH (e:Equipo {tag: $tag}) OPTIONAL MATCH (d:Documento {tipo:'hoja_de_datos'})-[:DOCUMENTA]->(e) "
                             "RETURN d IS NULL AS sin_hoja, [p IN $obligatorias WHERE e[p] IS NULL] AS faltantes", tag, [f"grafo:{tag}"])
        if not clase:
            return Respuesta(q, "completitud", "sin_clase", None)
        miembros = sorted(t for t, a in self.g.equipos().items() if a["clase"] == clase)
        if "no tienen hoja" in p:
            sel = [t for t in miembros if t not in self.g.fichas]
            return Respuesta(q, "completitud", "sin_hoja_clase", sel,
                             f"MATCH (e:Equipo {{clase: '{clase}'}}) WHERE NOT (:Documento {{tipo:'hoja_de_datos'}})-[:DOCUMENTA]->(e) RETURN e.tag",
                             None, [f"grafo:clase:{clase}"])
        sel = [t for t in miembros if t in self.g.fichas and self.g.fichas[t].faltantes]
        return Respuesta(q, "completitud", "faltantes_clase", sel,
                         f"MATCH (e:Equipo {{clase: '{clase}'}}) WHERE any(p IN $obligatorias WHERE e[p] IS NULL) RETURN e.tag",
                         None, [f"grafo:clase:{clase}"])

    def _documental(self, q: str, p: str, tag: str | None) -> Respuesta:
        sims = cosine_similarity(self._vec.transform([q]), self._mat)[0]
        i = int(sims.argmax())
        doc, pag, texto = self._paginas[i]
        return Respuesta(q, "documental", "busqueda_manual", texto, "", tag, [f"{doc} p.{pag}"])
