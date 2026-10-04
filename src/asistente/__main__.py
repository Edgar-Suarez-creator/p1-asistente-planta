"""Línea de comandos: python -m asistente "La bomba 1105p01 está botando glicol por el sello" [--json]

Imprime el borrador de solicitud de entrega. No aprueba ni emite: eso exige una persona
(demo en `make demo` o `Agente.aprobar` con nombre).
"""
from __future__ import annotations

import json
import sys

from .agente import Agente
from .grafo import GrafoPlanta


def main(argv: list[str]) -> int:
    args = [a for a in argv if a != "--json"]
    if not args:
        print('uso: python -m asistente "<reporte de falla>" [--json]', file=sys.stderr)
        return 2
    s = Agente(GrafoPlanta()).atender(" ".join(args))
    if "--json" in argv:
        print(json.dumps(s.dict(), ensure_ascii=False, indent=1))
        return 0
    if s.equipo is None:
        print(f"{s.estado} · " + " ".join(s.advertencias))
        return 1
    e, a = s.equipo, s.aislamientos
    filas = [
        ("síntoma", f"{s.sintoma['modo']} · {s.sintoma['nombre']}" if s.sintoma else "sin clasificar"),
        ("intervención", f"{s.intervencion_propuesta} ({s.fallas_similares['total']} antecedentes en la clase)"
         if s.fallas_similares else "por definir"),
        ("aislamientos", ", ".join(a["valvulas"]) + (f" · fuera de servicio: {', '.join(a['fuera_de_servicio'])}"
                                                      if a["fuera_de_servicio"] else "")),
        ("permisos", " · ".join(s.permisos_requeridos)),
        ("cuadrilla", s.cuadrilla),
        ("duración", f"{s.duracion_estimada_h} h (mediana de la clase)" if s.duracion_estimada_h else "por definir"),
        ("herramientas", " → ".join(c.split("(")[0] for c in s.llamadas)),
        ("citas", ", ".join(s.citas[:6]) + (" …" if len(s.citas) > 6 else "")),
    ]
    print(f"{s.estado} · {e['tag']} · {e['descripcion']}")
    for k, v in filas:
        print(f"  {k:<13}{v}")
    for adv in s.advertencias:
        print(f"  ! {adv}")
    print("  → no se emite sin aprobación humana registrada")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
