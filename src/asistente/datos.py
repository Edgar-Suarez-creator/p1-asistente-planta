"""Carga de los datos de planta-core (topología, catálogos, historial y documentos)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def carpeta_datos() -> Path:
    env = os.environ.get("PLANTA_CORE_DATOS")
    if env:
        return Path(env)
    for cand in (RAIZ.parent / "planta-core" / "datos", RAIZ / "vendor" / "planta-core" / "datos"):
        if (cand / "topologia.json").exists():
            return cand
    raise FileNotFoundError("No se encontró planta-core/datos. Ejecute `make setup` o defina PLANTA_CORE_DATOS.")


@dataclass(frozen=True)
class Datos:
    topologia: dict
    catalogos: dict
    historial: list[dict]
    documentos: list[dict]
    huecos: dict


@lru_cache(maxsize=1)
def cargar() -> Datos:
    d = carpeta_datos()
    leer = lambda n: json.loads((d / n).read_text(encoding="utf-8"))
    return Datos(leer("topologia.json"), leer("catalogos_iso14224.json"), leer("historial_fallas.json"),
                 leer("documentos.json"), leer("etiquetas_huecos.json"))
