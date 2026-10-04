"""Línea base: RAG vectorial plano sobre los mismos documentos.

Corpus: páginas de hojas de datos y manuales, una pieza por orden de trabajo (como saldría de
un export del CMMS), la lista de equipos por sistema y la lista de líneas (equivalente textual
del P&ID). Recuperación TF-IDF top-k. Sin LLM: la evaluación mide si el contexto recuperado
alcanza para responder (cota superior de un lector perfecto), lo que favorece a la línea base.
"""
from __future__ import annotations

from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .consulta import sin_tildes, tokens
from .datos import Datos


@dataclass(frozen=True)
class Fragmento:
    id: str
    texto: str


def corpus(d: Datos) -> list[Fragmento]:
    frags: list[Fragmento] = []
    for doc in d.documentos:
        for i, p in enumerate(doc["paginas"], 1):
            frags.append(Fragmento(f"{doc['id']}#p{i}", p))
    modos = d.catalogos["modos"]
    for ev in d.historial:
        frags.append(Fragmento(ev["id"], f"Orden {ev['id']} · {ev['fecha']} · {ev['descripcion']} · Modo de falla: "
                                         f"{modos[ev['modo']]} ({ev['modo']}) · Acción: {ev['accion']} · {ev['horas']} h"))
    topo = d.topologia
    for sis, s in topo["sistemas"].items():
        filas = [f"{t} – {e['descripcion']}" for t, e in topo["equipos"].items() if e["sistema"] == sis]
        frags.append(Fragmento(f"LISTA-{sis}", f"LISTA DE EQUIPOS · Sistema {s['nombre']} · Área {topo['areas'][s['area']]}\n" + "\n".join(filas)))
    cadena, n = [], 0
    for a, b in topo["conexiones"]:
        if cadena and cadena[-1] != a:
            n += 1
            frags.append(Fragmento(f"LINEA-{n:02d}", "LISTA DE LÍNEAS · " + " → ".join(cadena)))
            cadena = []
        if not cadena:
            cadena = [a]
        cadena.append(b)
    if cadena:
        frags.append(Fragmento(f"LINEA-{n + 1:02d}", "LISTA DE LÍNEAS · " + " → ".join(cadena)))
    return frags


class RagPlano:
    def __init__(self, d: Datos, k: int = 5):
        self.k = k
        self.frags = corpus(d)
        self.vec = TfidfVectorizer(preprocessor=sin_tildes, token_pattern=r"[\w\-]+")
        self.mat = self.vec.fit_transform([f.texto for f in self.frags])

    def recuperar(self, pregunta: str) -> list[Fragmento]:
        sims = cosine_similarity(self.vec.transform([pregunta]), self.mat)[0]
        return [self.frags[i] for i in sims.argsort()[::-1][: self.k]]

    def contexto_tokens(self, frags: list[Fragmento]) -> int:
        return tokens("\n\n".join(f.texto for f in frags))
