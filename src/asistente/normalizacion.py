"""Resolución de tags duplicados o mal escritos.

Dos etapas: (1) reglas de normalización de planta_core.tags; (2) si el resultado no existe en
el registro, comparación por similitud de n-gramas de caracteres contra los tags registrados.
La etapa 2 usa TF-IDF de caracteres como sustituto local de embeddings (sin descarga de
modelos); el resultado sólo se acepta si supera el umbral y no hay empate, si no va al
reporte de conflictos para revisión humana.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from planta_core.tags import normalizar
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

UMBRAL = 0.80
_CANDIDATO = re.compile(r"\b\d{3,4}[\s\-_]*[A-Za-z]{1,3}[\s\-_]*[0-9Oo]{0,2}\b")


@dataclass(frozen=True)
class Resolucion:
    texto: str
    tag: str | None
    metodo: str  # "regla" | "similitud" | "conflicto"
    puntaje: float
    candidatos: tuple[str, ...] = ()


class ResolutorTags:
    def __init__(self, registro: list[str]):
        self.registro = sorted(registro)
        self._set = set(registro)
        self._vec = TfidfVectorizer(analyzer="char", ngram_range=(2, 3), lowercase=True)
        self._m = self._vec.fit_transform([t.replace("-", "") for t in self.registro])

    def resolver(self, texto: str) -> Resolucion:
        cand = normalizar(texto)
        if cand in self._set:
            return Resolucion(texto, cand, "regla", 1.0)
        m = _CANDIDATO.search(texto)
        if not m:
            return Resolucion(texto, None, "conflicto", 0.0)
        q = re.sub(r"[\s\-_]", "", m.group(0)).upper()
        sims = cosine_similarity(self._vec.transform([q]), self._m)[0]
        orden = sims.argsort()[::-1]
        best, second = sims[orden[0]], sims[orden[1]]
        tops = tuple(self.registro[i] for i in orden[:3])
        if best >= UMBRAL and best - second > 0.05:
            return Resolucion(texto, self.registro[orden[0]], "similitud", float(best), tops)
        return Resolucion(texto, None, "conflicto", float(best), tops)
