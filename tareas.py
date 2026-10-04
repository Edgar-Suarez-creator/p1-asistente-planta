"""Equivalente de `make` para Windows sin make: python tareas.py setup|eval|demo|test|cypher"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
CORE = RAIZ.parent / "planta-core"
PY = sys.executable

TAREAS = {
    "setup": [[PY, "-m", "pip", "install", "-e", str(CORE)], [PY, "-m", "pip", "install", "-e", ".[dev]"],
              [PY, "-m", "planta_core.generar"]],
    "eval": [[PY, "-m", "evaluacion.run"]],
    "demo": [[PY, "-m", "app.servidor", "--exportar"], [PY, "-m", "app.servidor"]],
    "test": [[PY, "-m", "pytest", "-q"]],
    "cypher": [[PY, "-c", "import sys; sys.path.insert(0,'src'); from pathlib import Path; from asistente.grafo import GrafoPlanta; "
                "GrafoPlanta().exportar_cypher(Path('neo4j/planta.cypher')); print('neo4j/planta.cypher')"]],
}

if __name__ == "__main__":
    nombre = sys.argv[1] if len(sys.argv) > 1 else ""
    if nombre not in TAREAS:
        sys.exit(f"uso: python tareas.py {{{'|'.join(TAREAS)}}}")
    for cmd in TAREAS[nombre]:
        cwd = CORE if cmd[-1] == "planta_core.generar" else RAIZ
        subprocess.run(cmd, cwd=cwd, check=True)
