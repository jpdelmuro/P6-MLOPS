"""P6: Evento, evento_completo y AlmacenEventos (R4.1, R4.2)."""

from __future__ import annotations

import json

from p6.eventos import AlmacenEventos, Evento, evento_completo
from p6.modelo import Prediccion


def _evento_ok(
    event_id="evt-001",
    run_id="run-001",
    frame_id="normal_0000",
    zona="aceptada",
    timestamp_ms=1000.0,
):
    return Evento(
        event_id=event_id,
        run_id=run_id,
        frame_id=frame_id,
        timestamp_ms=timestamp_ms,
        source_id="normal",
        task="classification",
        model_ref="torchvision.models.resnet18",
        status="ok",
        prediction=Prediccion(class_id=1, class_name="goldfish", score=0.91),
        confidence_zone=zona,
        config_ref="config-v1",
        image_ref=None,
    )


def _evento_error(event_id="evt-err", run_id="run-001", frame_id="normal_0001"):
    return Evento(
        event_id=event_id,
        run_id=run_id,
        frame_id=frame_id,
        timestamp_ms=1500.0,
        source_id="normal",
        task="classification",
        model_ref="torchvision.models.resnet18",
        status="error",
        prediction=None,
        confidence_zone="sin_puntuacion",
        config_ref="config-v1",
        image_ref=None,
    )


def test_evento_ok_completo_es_verdadero():
    assert evento_completo(_evento_ok()) is True


def test_evento_error_completo_es_verdadero_si_es_coherente():
    assert evento_completo(_evento_error()) is True


def test_evento_ok_sin_prediction_es_incompleto():
    evento = _evento_ok()
    roto = Evento(**{**evento.a_dict(), "prediction": None})
    assert evento_completo(roto) is False


def test_evento_con_campo_de_identidad_vacio_es_incompleto():
    evento = _evento_ok()
    roto = Evento(**{**evento.a_dict(), "run_id": ""})
    assert evento_completo(roto) is False


def test_registrar_y_obtener_por_event_id(tmp_path):
    almacen = AlmacenEventos(tmp_path / "eventos.db")
    evento = _evento_ok()
    almacen.registrar(evento)

    recuperado = almacen.obtener(evento.event_id)
    assert recuperado is not None
    assert recuperado["event_id"] == evento.event_id
    assert recuperado["prediction"]["score"] == 0.91
    almacen.cerrar()


def test_obtener_event_id_inexistente_devuelve_none(tmp_path):
    almacen = AlmacenEventos(tmp_path / "eventos.db")
    assert almacen.obtener("no-existe") is None
    almacen.cerrar()


def test_listar_filtra_por_run_id_y_zona_y_ordena_por_tiempo(tmp_path):
    almacen = AlmacenEventos(tmp_path / "eventos.db")
    e1 = _evento_ok(event_id="evt-1", run_id="run-a", zona="baja_confianza", timestamp_ms=1000.0)
    e2 = _evento_ok(event_id="evt-2", run_id="run-a", zona="aceptada", timestamp_ms=2000.0)
    e3 = _evento_ok(event_id="evt-3", run_id="run-b", zona="aceptada", timestamp_ms=3000.0)
    for e in (e2, e1, e3):  # orden de insercion deliberadamente distinto al esperado
        almacen.registrar(e)

    de_run_a = almacen.listar(run_id="run-a")
    assert [e["event_id"] for e in de_run_a] == ["evt-1", "evt-2"]

    baja_confianza = almacen.listar(zona="baja_confianza")
    assert [e["event_id"] for e in baja_confianza] == ["evt-1"]
    almacen.cerrar()


def test_exportar_jsonl_produce_una_linea_json_por_evento(tmp_path):
    almacen = AlmacenEventos(tmp_path / "eventos.db")
    almacen.registrar(_evento_ok(event_id="evt-1"))
    almacen.registrar(_evento_error(event_id="evt-2"))

    ruta = almacen.exportar_jsonl(tmp_path / "export" / "eventos.jsonl")
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 2
    ids = {json.loads(linea)["event_id"] for linea in lineas}
    assert ids == {"evt-1", "evt-2"}
    almacen.cerrar()


def test_registrar_el_mismo_event_id_dos_veces_no_duplica(tmp_path):
    almacen = AlmacenEventos(tmp_path / "eventos.db")
    almacen.registrar(_evento_ok(event_id="evt-1"))
    almacen.registrar(_evento_ok(event_id="evt-1"))
    assert len(almacen.listar()) == 1
    almacen.cerrar()
