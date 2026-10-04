"""P1 · Asistente de planta sobre grafo de conocimiento."""
import sys
from pathlib import Path

try:
    import planta_core  # noqa: F401
except ImportError:  # sin `pip install -e ../planta-core`: se usa la copia hermana del repositorio
    _hermano = Path(__file__).resolve().parents[3] / "planta-core"
    if _hermano.exists():
        sys.path.insert(0, str(_hermano))
