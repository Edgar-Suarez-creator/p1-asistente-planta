"""Extracción de propiedades de hojas de datos hacia un esquema validado.

Ruta por defecto: reglas sobre el texto paginado (las hojas sintéticas son texto). Cada
propiedad extraída guarda documento y página de origen; sin cita no se guarda.
Ruta con Docling o con un modelo con visión sobre PDFs reales: pendiente (requiere los PDFs
del fabricante y, para la visión, una llave de API).
"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

_LINEA = re.compile(r"^(?P<k>[A-Za-zÁÉÍÓÚáéíóúñ ]+):\s*(?P<v>.+?)\s*$")


class Propiedad(BaseModel):
    nombre: str
    valor: str | float
    unidad: str | None = None
    documento: str
    pagina: int = Field(ge=1)


class FichaExtraida(BaseModel):
    tag: str
    propiedades: dict[str, Propiedad]
    faltantes: list[str]


def _clave(texto: str) -> str:
    t = texto.strip().lower().replace(" ", "_")
    return t.translate(str.maketrans("áéíóú", "aeiou"))


def extraer(doc: dict, obligatorias: list[str], unidades: dict[str, str | None]) -> FichaExtraida:
    props: dict[str, Propiedad] = {}
    for i, pagina in enumerate(doc["paginas"], 1):
        for linea in pagina.splitlines():
            m = _LINEA.match(linea)
            if not m:
                continue
            k = _clave(m["k"])
            if k not in obligatorias:
                continue
            crudo, unidad = m["v"], unidades.get(k)
            valor: str | float = crudo
            if unidad and crudo.endswith(unidad):
                num = crudo[: -len(unidad)].strip()
                try:
                    valor = float(num)
                except ValueError:
                    valor = num
            props[k] = Propiedad(nombre=k, valor=valor, unidad=unidad, documento=doc["id"], pagina=i)
    return FichaExtraida(tag=doc["tag"], propiedades=props, faltantes=[p for p in obligatorias if p not in props])
