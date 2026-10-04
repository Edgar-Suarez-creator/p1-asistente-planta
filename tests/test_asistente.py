import pytest

from asistente.agente import Agente
from asistente.aislamientos import calcular_aislamiento
from asistente.consulta import MotorConsultas, clasificar
from asistente.grafo import GrafoPlanta
from asistente.normalizacion import ResolutorTags


@pytest.fixture(scope="module")
def g():
    return GrafoPlanta()


def test_esquema_del_grafo(g):
    r = g.resumen()
    for label in ("Area", "Sistema", "Equipo", "Componente", "Documento", "Falla", "Intervencion", "ModoFalla"):
        assert r["por_label"].get(label, 0) > 0, label
    for rel in ("PERTENECE_A", "CONECTA_A", "AISLA", "DOCUMENTA", "PRESENTO_FALLA"):
        assert r["por_relacion"].get(rel, 0) > 0, rel


def test_aislamiento_hasta_primera_valvula(g):
    a = calcular_aislamiento(g.proceso(), "1105-P-01")
    assert a.valvulas == ["1105-HV-09", "1105-HV-10"]
    a = calcular_aislamiento(g.proceso(), "1205-E-01")
    assert "1205-PCV-01" in a.fuera_de_servicio  # la PCV no es aislamiento positivo
    a = calcular_aislamiento(g.proceso(), "1305-C-01")
    assert a.ramas_abiertas == ["LIM-ATM-1305-A"]


def test_resolutor_conflicto_no_adivina(g):
    r = ResolutorTags(list(g.d.topologia["equipos"]))
    assert r.resolver("BBA 1105p01").tag == "1105-P-01"
    assert r.resolver("1105-P-0").tag is None  # ambiguo entre P-01 y P-02


def test_propiedades_con_cita(g):
    for ficha in g.fichas.values():
        for p in ficha.propiedades.values():
            assert p.documento.startswith("DS-") and p.pagina >= 1


def test_enrutador():
    assert clasificar("¿Qué válvulas de bloqueo aíslan el 1105-V-01?") == "topologia"
    assert clasificar("¿Cuántas veces ha fallado el 1105-P-01 por vibración (VIB)?") == "historial"
    assert clasificar("¿Qué propiedades obligatorias le faltan al 1205-C-01?") == "completitud"
    assert clasificar("¿Cada cuántos días recomienda el fabricante el análisis de vibraciones?") == "documental"


def test_motor_responde_con_cypher_y_cita(g):
    m = MotorConsultas(g)
    r = m.responder("¿Qué válvulas de bloqueo aíslan el 1405_P_03?")
    assert r.tag == "1405-P-03" and r.valor == ["1405-HV-05", "1405-HV-06"]
    assert "AISLA" in r.cypher and r.citas


def test_agente_borrador_y_aprobacion(g, tmp_path):
    ag = Agente(g, tmp_path / "aprobaciones.jsonl")
    s = ag.atender("La bomba 1105p01 está botando glicol por el sello")
    assert s.estado == "BORRADOR" and s.equipo["tag"] == "1105-P-01" and s.sintoma["modo"] == "ELP"
    assert s.aislamientos["valvulas"] == ["1105-HV-09", "1105-HV-10"]
    assert "Aislamiento eléctrico del motor (LOTO)" in s.permisos_requeridos
    with pytest.raises(PermissionError):
        Agente.emitir(s)
    with pytest.raises(ValueError):
        ag.aprobar(s, "  ")
    ag.aprobar(s, "Ing. de turno")
    assert Agente.emitir(s)["emitida"]
    assert (tmp_path / "aprobaciones.jsonl").read_text(encoding="utf-8").count("Ing. de turno") == 1


def test_linea_de_comandos(capsys):
    from asistente.__main__ import main

    assert main(["La bomba 1105p01 está botando glicol por el sello"]) == 0
    salida = capsys.readouterr().out
    assert salida.startswith("BORRADOR · 1105-P-01") and "1105-HV-09, 1105-HV-10" in salida
    assert main(["Hay una bomba que vibra mucho en glicol"]) == 1


def test_agente_sin_tag_no_inventa(g):
    s = Agente(g).atender("Hay una bomba que vibra mucho en glicol")
    assert s.estado == "NO_RESUELTA" and s.equipo is None
