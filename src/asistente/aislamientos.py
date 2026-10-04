"""Cálculo de aislamientos recorriendo la topología.

Desde el equipo se recorre la red de proceso aguas arriba y aguas abajo (vista no dirigida)
hasta la primera válvula manual de bloqueo (HV) de cada rama. Las válvulas de control (PCV)
no son aislamiento positivo y se atraviesan. Un límite de batería sin válvula se reporta como
rama abierta: requiere aislamiento adicional que el sistema no puede proponer.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

import networkx as nx


@dataclass
class Aislamiento:
    equipo: str
    valvulas: list[str] = field(default_factory=list)
    fuera_de_servicio: list[str] = field(default_factory=list)  # equipos dentro de la envolvente
    ramas_abiertas: list[str] = field(default_factory=list)  # límites alcanzados sin válvula


def calcular_aislamiento(proceso: nx.Graph, equipo: str) -> Aislamiento:
    res = Aislamiento(equipo)
    if equipo not in proceso:
        return res
    vistos, cola = {equipo}, deque([equipo])
    envolvente = {equipo}
    while cola:
        n = cola.popleft()
        for vecino in proceso.neighbors(n):
            if vecino in vistos:
                continue
            vistos.add(vecino)
            tipo = proceso.nodes[vecino].get("tipo")
            if tipo == "HV":
                res.valvulas.append(vecino)
            elif tipo == "LIM":
                res.ramas_abiertas.append(vecino)
            else:
                if tipo != "HDR":
                    envolvente.add(vecino)
                cola.append(vecino)
    res.valvulas.sort()
    res.ramas_abiertas.sort()
    res.fuera_de_servicio = sorted(envolvente)
    return res
