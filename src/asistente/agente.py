"""Agente del reporte de falla → borrador de solicitud de entrega a operaciones.

Flujo: identificar el equipo (tag) → clasificar el síntoma en un modo ISO 14224 → llamar las
cuatro herramientas → llenar la plantilla de campos fijos. El agente no calcula: todo valor
sale de una herramienta y lleva su cita. Nada se emite sin aprobación humana registrada.

Redacción por defecto: plantilla determinista. Redacción con LLM: pendiente (ANTHROPIC_API_KEY);
cuando exista, el LLM sólo redacta sobre las salidas de las herramientas, no las sustituye.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .consulta import sin_tildes
from .grafo import GrafoPlanta
from .herramientas import Herramientas
from .normalizacion import ResolutorTags

# Palabras del reporte → modo ISO 14224. Orden: la primera coincidencia gana.
SINTOMAS = [
    ("se dispara", "UST"), ("disparo", "UST"), ("no arranca", "FTS"), ("no abre", "FTO"), ("no cierra", "FTC"), ("fuga interna", "INL"),
    ("aceite", "ELU"), ("fuga", "ELP"), ("bota", "ELP"), ("gotea", "ELP"), ("goteo", "ELP"),
    ("vibra", "VIB"), ("ruido", "NOI"), ("golpeteo", "NOI"), ("temperatura", "OHE"), ("caliente", "OHE"),
    ("tapon", "PLU"), ("diferencial", "PLU"), ("bajo caudal", "LOO"), ("no entrega", "LOO"), ("baja presion", "LOO"),
    ("lectura", "AIR"), ("senal", "ERO"), ("corrosion", "STD"),
]
CUADRILLA = {"P": "mecánica + eléctrica (desenergizar motor)", "C": "mecánica + eléctrica (desenergizar motor)",
             "K": "mecánica + eléctrica", "V": "mecánica", "E": "mecánica", "PCV": "instrumentación", "PT": "instrumentación"}
FLUIDO = {"1105": "gas y glicol", "1205": "gas", "1305": "aire comprimido", "1405": "agua contra incendio"}


@dataclass
class Solicitud:
    estado: str  # BORRADOR | APROBADA | NO_RESUELTA
    reporte: str
    equipo: dict | None = None
    sintoma: dict | None = None
    intervencion_propuesta: str | None = None
    aislamientos: dict | None = None
    permisos_requeridos: list[str] = field(default_factory=list)
    cuadrilla: str | None = None
    duracion_estimada_h: float | None = None
    historial: list[dict] = field(default_factory=list)
    fallas_similares: dict | None = None
    citas: list[str] = field(default_factory=list)
    advertencias: list[str] = field(default_factory=list)
    llamadas: list[str] = field(default_factory=list)
    aprobacion: dict | None = None

    def dict(self) -> dict:
        return asdict(self)


class Agente:
    def __init__(self, grafo: GrafoPlanta, registro_aprobaciones: Path | None = None):
        self.g = grafo
        self.h = Herramientas(grafo)
        self.resolutor = ResolutorTags(list(grafo.d.topologia["equipos"]))
        self.registro = registro_aprobaciones

    def _candidatos_por_descripcion(self, reporte: str, n: int = 3) -> list[str]:
        eqs = self.g.equipos()
        tags = sorted(eqs)
        vec = TfidfVectorizer(preprocessor=sin_tildes)
        m = vec.fit_transform([f"{eqs[t]['descripcion']} {eqs[t]['clase']}" for t in tags])
        sims = cosine_similarity(vec.transform([reporte]), m)[0]
        return [tags[i] for i in sims.argsort()[::-1][:n] if sims[i] > 0.2]

    def _modo(self, reporte: str) -> str | None:
        p = sin_tildes(reporte)
        return next((m for clave, m in SINTOMAS if clave in p), None)

    def atender(self, reporte: str) -> Solicitud:
        s = Solicitud("BORRADOR", reporte)
        r = self.resolutor.resolver(reporte)
        if r.tag is None:
            s.estado = "NO_RESUELTA"
            cands = list(r.candidatos) or self._candidatos_por_descripcion(reporte)
            s.advertencias.append("No se identificó el tag del equipo. Candidatos: " + (", ".join(cands) or "ninguno")
                                  + ". Pida al reportante el tag de la placa; el sistema no elige por él.")
            return s
        if r.metodo == "similitud":
            s.advertencias.append(f"Tag inferido por similitud ({r.puntaje:.2f}) desde «{r.texto}»: confirmar en campo.")
        tag = r.tag
        eq = self.h.buscar_equipo(tag)
        s.llamadas.append(f"buscar_equipo({tag!r})")
        s.equipo = {k: eq[k] for k in ("tag", "descripcion", "clase", "sistema", "area", "critico")}
        s.historial = self.h.historial(tag)[-5:]
        s.llamadas.append(f"historial({tag!r})")
        s.citas += [h["orden"] for h in s.historial] + eq["documentos"]

        modo = self._modo(reporte)
        if modo is None:
            s.advertencias.append("Síntoma no clasificado en un modo ISO 14224: el planeador debe asignarlo.")
        else:
            s.sintoma = {"modo": modo, "nombre": self.g.d.catalogos["modos"][modo]}
            sim = self.h.fallas_similares(eq["clase"], modo, excluir=None)
            s.llamadas.append(f"fallas_similares({eq['clase']!r}, {modo!r})")
            s.fallas_similares = sim
            s.intervencion_propuesta = sim["accion_mas_frecuente"]
            s.duracion_estimada_h = round(sim["horas_mediana"], 1) if sim["horas_mediana"] is not None else None
            s.citas += [c["orden"] for c in sim["casos"]]
            if sim["total"] == 0:
                s.advertencias.append("Sin antecedentes de ese modo en la clase: la intervención y la duración quedan por definir.")

        ais = self.h.aislamientos(tag)
        s.llamadas.append(f"aislamientos({tag!r})")
        s.aislamientos = ais
        if ais["ramas_abiertas"]:
            s.advertencias.append("Ramas sin válvula de bloqueo hasta el límite de batería: " + ", ".join(ais["ramas_abiertas"])
                                  + ". Definir aislamiento adicional (brida ciega o desconexión).")
        tipo = self.g.g.nodes[tag]["tipo"]
        s.cuadrilla = CUADRILLA[tipo]
        s.permisos_requeridos = self._permisos(tag, tipo, modo, ais)
        return s

    @staticmethod
    def _permisos(tag: str, tipo: str, modo: str | None, ais: dict) -> list[str]:
        p = ["Permiso de trabajo en frío", f"Aislamiento de proceso ({len(ais['valvulas'])} válvulas, bloqueo y etiquetado)"]
        if tipo in ("P", "C", "K"):
            p.append("Aislamiento eléctrico del motor (LOTO)")
        if tipo == "V" and modo in ("PLU", "STD", "OTH"):
            p.append("Entrada a espacio confinado")
        if tag[:4] in ("1105", "1205"):
            p.append(f"Drenaje, despresurización y prueba de atmósfera ({FLUIDO[tag[:4]]})")
        if tag[:4] == "1405":
            p.append("Notificación de sistema contra incendio fuera de servicio y vigilancia compensatoria")
        return p

    def aprobar(self, s: Solicitud, aprobador: str) -> Solicitud:
        if s.estado != "BORRADOR":
            raise ValueError(f"sólo se aprueba un BORRADOR (estado actual: {s.estado})")
        if not aprobador.strip():
            raise ValueError("la aprobación exige el nombre de quien aprueba")
        s.estado = "APROBADA"
        s.aprobacion = {"aprobador": aprobador.strip(), "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        if self.registro:
            self.registro.parent.mkdir(parents=True, exist_ok=True)
            with self.registro.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"tag": s.equipo["tag"], **s.aprobacion, "reporte": s.reporte}, ensure_ascii=False) + "\n")
        return s

    @staticmethod
    def emitir(s: Solicitud) -> dict:
        if s.estado != "APROBADA" or not s.aprobacion:
            raise PermissionError("No se emite una solicitud sin aprobación humana registrada.")
        return {"emitida": True, "tag": s.equipo["tag"], "aprobacion": s.aprobacion}
