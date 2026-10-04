"""Grafo de conocimiento de la planta.

Nodos: Area, Sistema, Equipo, Componente, Documento, Falla, Intervencion y catálogos ISO 14224
(NivelISO, ModoFalla, Mecanismo, Causa). Cabezales y límites de batería son nodos Linea.
Relaciones: PERTENECE_A, CONECTA_A, AISLA, DOCUMENTA, PRESENTO_FALLA, MIDE, TIENE_MODO,
TIENE_MECANISMO, TIENE_CAUSA, AFECTA, ATENDIDA_POR.

Backend por defecto: networkx en memoria (sin servicios). `exportar_cypher` escribe el mismo
grafo como sentencias Cypher para cargarlo en Neo4j 5 (docker compose up neo4j).
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import networkx as nx
from planta_core.ontologia.clases import PROPIEDADES

from .aislamientos import calcular_aislamiento
from .datos import Datos, cargar
from .extraccion import FichaExtraida, extraer
from .normalizacion import ResolutorTags


class GrafoPlanta:
    def __init__(self, datos: Datos | None = None):
        self.d = datos or cargar()
        self.g = nx.MultiDiGraph()
        self.fichas: dict[str, FichaExtraida] = {}
        self.conflictos: list[dict] = []
        self._construir()

    # ------------------------------------------------------------------ construcción
    def _nodo(self, nid: str, label: str, **props) -> str:
        self.g.add_node(nid, label=label, **props)
        return nid

    def _rel(self, a: str, tipo: str, b: str, **props) -> None:
        self.g.add_edge(a, b, key=tipo, tipo=tipo, **props)

    def _construir(self) -> None:
        topo, cat = self.d.topologia, self.d.catalogos
        for nivel, nombre in cat["niveles"]:
            self._nodo(f"NivelISO:{nivel}", "NivelISO", nivel=nivel, nombre=nombre)
        for cod, nombre in cat["modos"].items():
            self._nodo(f"ModoFalla:{cod}", "ModoFalla", codigo=cod, nombre=nombre)
        for cod, nombre in cat["mecanismos"].items():
            self._nodo(f"Mecanismo:{cod}", "Mecanismo", codigo=cod, nombre=nombre)
        for cod, nombre in cat["causas"].items():
            self._nodo(f"Causa:{cod}", "Causa", codigo=cod, nombre=nombre)

        for area, nombre in topo["areas"].items():
            self._rel(self._nodo(f"Area:{area}", "Area", codigo=area, nombre=nombre), "NIVEL", "NivelISO:4")
        for sis, s in topo["sistemas"].items():
            self._nodo(f"Sistema:{sis}", "Sistema", codigo=sis, nombre=s["nombre"])
            self._rel(f"Sistema:{sis}", "PERTENECE_A", f"Area:{s['area']}")

        clases = cat["clases"]
        for tag, e in topo["equipos"].items():
            clase = clases[e["tipo"]]
            self._nodo(tag, "Equipo", tag=tag, tipo=e["tipo"], clase=clase["nombre"], codigo_iso=clase["codigo"],
                       descripcion=e["descripcion"], critico=e["critico"], modelo=e["modelo"])
            self._rel(tag, "PERTENECE_A", f"Sistema:{e['sistema']}")
            for sub, items in cat["subunidades"].get(e["tipo"], {}).items():
                for item in items:
                    cid = f"Componente:{tag}/{item}"
                    self._nodo(cid, "Componente", nombre=item, subunidad=sub)
                    self._rel(cid, "PERTENECE_A", tag)
        for v in topo["valvulas_bloqueo"]:
            self._nodo(v, "Equipo", tag=v, tipo="HV", clase="Válvula manual de bloqueo", descripcion="Válvula de bloqueo", critico=False)
        for a, b in topo["conexiones"]:
            for n in (a, b):
                if n not in self.g:
                    self._nodo(n, "Linea", nombre=n, tipo=n[:3])
            self._rel(a, "CONECTA_A", b)
        for pt, eq in topo["instrumentos"].items():
            self._rel(pt, "MIDE", eq)

        # Documentos y extracción de propiedades con cita
        oblig = cat["propiedades_obligatorias"]
        for doc in self.d.documentos:
            did = f"Documento:{doc['id']}"
            self._nodo(did, "Documento", id=doc["id"], tipo=doc["tipo"], paginas=len(doc["paginas"]))
            if doc["tipo"] == "hoja_de_datos":
                tipo = topo["equipos"][doc["tag"]]["tipo"]
                self._rel(did, "DOCUMENTA", doc["tag"])
                self.fichas[doc["tag"]] = extraer(doc, oblig[tipo], dict(PROPIEDADES[tipo]))
            else:
                for tag, e in topo["equipos"].items():
                    if e["modelo"] == doc["modelo"]:
                        self._rel(did, "DOCUMENTA", tag)

        # Historial: resolución de tags y carga de fallas
        resol = ResolutorTags(list(topo["equipos"]))
        for ev in self.d.historial:
            r = resol.resolver(ev["tag_escrito"])
            if r.tag is None:
                self.conflictos.append({"orden": ev["id"], "texto": ev["tag_escrito"], "candidatos": list(r.candidatos),
                                        "puntaje": round(r.puntaje, 3)})
                continue
            fid = f"Falla:{ev['id']}"
            self._nodo(fid, "Falla", id=ev["id"], fecha=ev["fecha"], descripcion=ev["descripcion"], tag_escrito=ev["tag_escrito"],
                       resolucion=r.metodo)
            self._rel(r.tag, "PRESENTO_FALLA", fid)
            self._rel(fid, "TIENE_MODO", f"ModoFalla:{ev['modo']}")
            self._rel(fid, "TIENE_MECANISMO", f"Mecanismo:{ev['mecanismo']}")
            self._rel(fid, "TIENE_CAUSA", f"Causa:{ev['causa']}")
            comp = f"Componente:{r.tag}/{ev['componente']}"
            if comp in self.g:
                self._rel(fid, "AFECTA", comp)
            iid = f"Intervencion:{ev['id']}"
            self._nodo(iid, "Intervencion", accion=ev["accion"], horas=ev["horas"], cuadrilla=ev["cuadrilla"], fecha=ev["fecha"])
            self._rel(fid, "ATENDIDA_POR", iid)

        # Aislamientos materializados como relación AISLA
        for tag, e in topo["equipos"].items():
            if e["tipo"] == "PT":
                continue
            for v in calcular_aislamiento(self.proceso(), tag).valvulas:
                self._rel(v, "AISLA", tag)

    # ------------------------------------------------------------------ vistas
    def proceso(self) -> nx.Graph:
        """Vista no dirigida sólo con las conexiones de proceso."""
        if not hasattr(self, "_proceso"):
            g = nx.Graph()
            for a, b, k in self.g.edges(keys=True):
                if k == "CONECTA_A":
                    g.add_edge(a, b)
            for n in g.nodes:
                g.nodes[n]["tipo"] = self.g.nodes[n].get("tipo")
            self._proceso = g
        return self._proceso

    def salientes(self, nid: str, tipo: str) -> list[str]:
        return [b for _a, b, k in self.g.out_edges(nid, keys=True) if k == tipo]

    def entrantes(self, nid: str, tipo: str) -> list[str]:
        return [a for a, _b, k in self.g.in_edges(nid, keys=True) if k == tipo]

    def equipos(self) -> dict[str, dict]:
        return {n: a for n, a in self.g.nodes(data=True) if a.get("label") == "Equipo" and a.get("tipo") != "HV"}

    def fallas_de(self, tag: str) -> list[dict]:
        out = []
        for fid in self.salientes(tag, "PRESENTO_FALLA"):
            f = dict(self.g.nodes[fid])
            f["modo"] = self.salientes(fid, "TIENE_MODO")[0].split(":", 1)[1]
            f["intervencion"] = dict(self.g.nodes[self.salientes(fid, "ATENDIDA_POR")[0]])
            out.append(f)
        return sorted(out, key=lambda f: f["fecha"])

    def resumen(self) -> dict:
        por_label: dict[str, int] = defaultdict(int)
        for _n, a in self.g.nodes(data=True):
            por_label[a["label"]] += 1
        por_rel: dict[str, int] = defaultdict(int)
        for *_ab, k in self.g.edges(keys=True):
            por_rel[k] += 1
        return {"nodos": self.g.number_of_nodes(), "relaciones": self.g.number_of_edges(),
                "por_label": dict(por_label), "por_relacion": dict(por_rel), "conflictos_tag": len(self.conflictos)}

    # ------------------------------------------------------------------ Neo4j
    def exportar_cypher(self, ruta: Path) -> None:
        lineas = ["CREATE CONSTRAINT nodo_id IF NOT EXISTS FOR (n:Nodo) REQUIRE n.id IS UNIQUE;"]
        for n, a in self.g.nodes(data=True):
            props = {k: v for k, v in a.items() if k != "label" and v is not None}
            props["id"] = n
            lineas.append(f"CREATE (:Nodo:{a['label']} {_cypher_map(props)});")
        for a, b, k in self.g.edges(keys=True):
            lineas.append(f"MATCH (x:Nodo {{id: {json.dumps(a, ensure_ascii=False)}}}), (y:Nodo {{id: {json.dumps(b, ensure_ascii=False)}}}) "
                          f"CREATE (x)-[:{k}]->(y);")
        ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")


def _cypher_map(props: dict) -> str:
    partes = [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in props.items()]
    return "{" + ", ".join(partes) + "}"
