"""Las cuatro herramientas deterministas del agente. El agente no calcula: las llama y redacta."""
from __future__ import annotations

from collections import Counter
from statistics import median

from .aislamientos import calcular_aislamiento
from .grafo import GrafoPlanta


class Herramientas:
    def __init__(self, grafo: GrafoPlanta):
        self.g = grafo

    def buscar_equipo(self, tag: str) -> dict | None:
        if tag not in self.g.g or self.g.g.nodes[tag].get("label") != "Equipo":
            return None
        a = self.g.g.nodes[tag]
        sistema = self.g.salientes(tag, "PERTENECE_A")[0]
        area = self.g.salientes(sistema, "PERTENECE_A")[0]
        ficha = self.g.fichas.get(tag)
        return {
            "tag": tag, "descripcion": a["descripcion"], "clase": a["clase"], "codigo_iso": a.get("codigo_iso"),
            "critico": a["critico"], "modelo": a.get("modelo"),
            "sistema": self.g.g.nodes[sistema]["nombre"], "area": self.g.g.nodes[area]["nombre"],
            "propiedades": {k: {"valor": p.valor, "unidad": p.unidad, "cita": f"{p.documento} p.{p.pagina}"}
                            for k, p in (ficha.propiedades.items() if ficha else [])},
            "hoja_de_datos": ficha is not None,
            "faltantes": ficha.faltantes if ficha else None,
            "documentos": sorted(d.split(":", 1)[1] for d in self.g.entrantes(tag, "DOCUMENTA")),
        }

    def historial(self, tag: str) -> list[dict]:
        return [{"orden": f["id"], "fecha": f["fecha"], "modo": f["modo"], "descripcion": f["descripcion"],
                 "accion": f["intervencion"]["accion"], "horas": f["intervencion"]["horas"]} for f in self.g.fallas_de(tag)]

    def fallas_similares(self, clase: str, modo: str, excluir: str | None = None, limite: int = 5) -> dict:
        casos = []
        for tag, a in self.g.equipos().items():
            if a["clase"] != clase or tag == excluir:
                continue
            for f in self.g.fallas_de(tag):
                if f["modo"] == modo:
                    casos.append({"tag": tag, "orden": f["id"], "fecha": f["fecha"], "accion": f["intervencion"]["accion"],
                                  "horas": f["intervencion"]["horas"]})
        casos.sort(key=lambda c: c["fecha"], reverse=True)
        acciones = Counter(c["accion"] for c in casos)
        return {"clase": clase, "modo": modo, "total": len(casos), "casos": casos[:limite],
                "accion_mas_frecuente": acciones.most_common(1)[0][0] if acciones else None,
                "horas_mediana": median(c["horas"] for c in casos) if casos else None}

    def aislamientos(self, tag: str) -> dict:
        r = calcular_aislamiento(self.g.proceso(), tag)
        return {"equipo": tag, "valvulas": r.valvulas, "fuera_de_servicio": [t for t in r.fuera_de_servicio if t != tag],
                "ramas_abiertas": r.ramas_abiertas}
