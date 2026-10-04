"""Demo local sin credenciales: `python -m app.servidor` (o `make demo`) → http://127.0.0.1:8001

Sirve app/index.html y dos rutas JSON:
  POST /api/reporte   {"reporte": "..."}            → borrador de solicitud + vecindario del grafo
  POST /api/aprobar   {"reporte": "...", "aprobador": "..."} → aprobación registrada en app/aprobaciones.jsonl
`python -m app.servidor --exportar` escribe app/demo.json para la versión estática (GitHub Pages).
"""
from __future__ import annotations

import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent / "src"))

import networkx as nx  # noqa: E402

from asistente.agente import Agente  # noqa: E402
from asistente.grafo import GrafoPlanta  # noqa: E402

EJEMPLOS = [
    "La bomba 1105p01 está botando glicol por el sello",
    "El compresor 1205-C-02 se dispara solo, parece el sensor de vibración",
    "Alto diferencial en el aeroenfriador 1205 E 01, posible taponamiento",
    "La torre secadora 1305-V-02 tiene una fuga por una boquilla",
    "La bomba jockey 1405_P_03 hace ruido al arrancar",
    "Hay una bomba que vibra mucho en glicol",
]

GRAFO = GrafoPlanta()
AGENTE = Agente(GRAFO, AQUI / "aprobaciones.jsonl")


def vecindario(tag: str, ais: dict) -> dict:
    p = GRAFO.proceso()
    nodos = set(nx.single_source_shortest_path_length(p, tag, cutoff=3))
    sub = p.subgraph(nodos)
    pos = nx.kamada_kawai_layout(sub) if len(sub) > 2 else {n: (i, 0) for i, n in enumerate(sub)}
    xs = [x for x, _ in pos.values()] or [0]
    ys = [y for _, y in pos.values()] or [0]
    nx_ = lambda v, lo, hi: 40 + 520 * (v - lo) / ((hi - lo) or 1)
    rol = lambda n: ("equipo" if n == tag else "valvula_aisla" if n in ais["valvulas"] else
                     "fuera_servicio" if n in ais["fuera_de_servicio"] else "limite" if n.startswith("LIM-") else
                     "cabezal" if n.startswith("HDR-") else "otro")
    return {"nodos": [{"id": n, "x": round(nx_(pos[n][0], min(xs), max(xs)), 1), "y": round(30 + 300 * (pos[n][1] - min(ys)) / ((max(ys) - min(ys)) or 1), 1),
                       "tipo": p.nodes[n].get("tipo"), "rol": rol(n)} for n in sub],
            "aristas": [[a, b] for a, b in sub.edges]}


def atender(reporte: str) -> dict:
    s = AGENTE.atender(reporte)
    out = s.dict()
    out["grafo"] = vecindario(s.equipo["tag"], s.aislamientos) if s.equipo else None
    return out


class Manejador(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(AQUI), **k)

    def _json(self, code: int, obj) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length", 0))
        if n > 10_000:
            return self._json(413, {"error": "solicitud demasiado grande"})
        try:
            datos = json.loads(self.rfile.read(n) or b"{}")
            reporte = str(datos.get("reporte", ""))[:500]
            if self.path == "/api/reporte":
                return self._json(200, atender(reporte))
            if self.path == "/api/aprobar":
                s = AGENTE.atender(reporte)
                AGENTE.aprobar(s, str(datos.get("aprobador", ""))[:80])
                return self._json(200, {"estado": s.estado, "aprobacion": s.aprobacion, "emision": Agente.emitir(s)})
        except (ValueError, PermissionError) as e:
            return self._json(400, {"error": str(e)})
        self._json(404, {"error": "ruta no encontrada"})


def main(argv: list[str]) -> None:
    if "--exportar" in argv:
        (AQUI / "demo.json").write_text(json.dumps({"ejemplos": [{"reporte": r, **atender(r)} for r in EJEMPLOS]},
                                                   ensure_ascii=False, indent=1), encoding="utf-8")
        print("app/demo.json escrito")
        return
    srv = ThreadingHTTPServer(("127.0.0.1", 8001), Manejador)
    print("Demo en http://127.0.0.1:8001  (Ctrl+C para salir)")
    srv.serve_forever()


if __name__ == "__main__":
    main(sys.argv[1:])
