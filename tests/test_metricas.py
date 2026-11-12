"""P6: metricas base G1-G7 -- cada calculo anclado con un resultado exacto esperado (M3)."""

from __future__ import annotations

import pytest

from p6.metricas import (
    CATALOGO_BASE,
    Medicion,
    alertas_activas_en_ventana,
    antiguedad_ultimo_frame,
    cobertura_trazabilidad,
    tiempo_inferencia_p50,
    uso_recursos_promedio,
    version_reportada_vs_esperada,
)


def _medicion(frame_id="f0", timestamp_ms=0.0, duracion_ms=10.0, cpu=5.0, ram=100.0):
    return Medicion(
        frame_id=frame_id,
        timestamp_ms=timestamp_ms,
        duracion_inferencia_ms=duracion_ms,
        cpu_percent=cpu,
        ram_mb=ram,
    )


def test_catalogo_base_tiene_una_entrada_por_grupo():
    grupos = [m.grupo for m in CATALOGO_BASE]
    assert grupos == ["G1", "G2", "G3", "G4", "G5", "G6", "G7"]
    assert len(set(grupos)) == 7


# --- G1 -----------------------------------------------------------------------


def test_tiempo_inferencia_p50_sin_mediciones_es_none():
    assert tiempo_inferencia_p50([]) is None


def test_tiempo_inferencia_p50_calcula_la_mediana_exacta():
    mediciones = [_medicion(duracion_ms=d) for d in (10.0, 20.0, 30.0, 40.0, 50.0)]
    assert tiempo_inferencia_p50(mediciones) == 30.0


# --- G2 -----------------------------------------------------------------------


def test_antiguedad_ultimo_frame_sin_frames_es_none():
    assert antiguedad_ultimo_frame([], ahora_ms=1000.0) is None


def test_antiguedad_ultimo_frame_usa_el_mas_reciente():
    timestamps = [1000.0, 1500.0, 1800.0]
    assert antiguedad_ultimo_frame(timestamps, ahora_ms=2000.0) == 200.0


# --- G3 -----------------------------------------------------------------------


def test_uso_recursos_promedio_sin_mediciones_es_none():
    assert uso_recursos_promedio([]) is None


def test_uso_recursos_promedio_calcula_promedios_exactos():
    mediciones = [
        _medicion(cpu=10.0, ram=100.0),
        _medicion(cpu=20.0, ram=200.0),
    ]
    resultado = uso_recursos_promedio(mediciones)
    assert resultado.cpu_percent_promedio == 15.0
    assert resultado.ram_mb_promedio == 150.0
    assert resultado.muestras == 2


# --- G5 -----------------------------------------------------------------------


_SIN_PROVEER = object()


def _evento_dict(status="ok", prediction=_SIN_PROVEER, zona="aceptada", **overrides):
    base = {
        "event_id": "evt-1",
        "run_id": "run-1",
        "frame_id": "f0",
        "timestamp_ms": 1000.0,
        "source_id": "normal",
        "task": "classification",
        "model_ref": "torchvision.models.resnet18",
        "status": status,
        "prediction": {"class_id": 1, "score": 0.9} if prediction is _SIN_PROVEER else prediction,
        "confidence_zone": zona,
        "config_ref": "config-v1",
        "image_ref": None,
    }
    if status == "error":
        base["prediction"] = None
        base["confidence_zone"] = "sin_puntuacion"
    base.update(overrides)
    return base


def test_cobertura_trazabilidad_sin_eventos_es_none():
    assert cobertura_trazabilidad([]) is None


def test_cobertura_trazabilidad_proporcion_exacta():
    eventos = [
        _evento_dict(),  # completo
        _evento_dict(status="error"),  # completo (coherente con error)
        _evento_dict(prediction=None),  # incompleto: ok sin prediction
    ]
    assert cobertura_trazabilidad(eventos) == pytest.approx(2 / 3)


def test_cobertura_trazabilidad_detecta_campo_de_identidad_vacio():
    eventos = [_evento_dict(run_id="")]
    assert cobertura_trazabilidad(eventos) == 0.0


# --- G6 -----------------------------------------------------------------------


def test_version_reportada_coincide_con_la_esperada():
    eventos = [_evento_dict(model_ref="torchvision.models.resnet18") for _ in range(3)]
    resultado = version_reportada_vs_esperada(eventos, "torchvision.models.resnet18")
    assert resultado.coincide is True
    assert resultado.reportados == ("torchvision.models.resnet18",)


def test_version_reportada_detecta_discrepancia():
    eventos = [
        _evento_dict(model_ref="torchvision.models.resnet18"),
        _evento_dict(model_ref="torchvision.models.mobilenet_v3"),
    ]
    resultado = version_reportada_vs_esperada(eventos, "torchvision.models.resnet18")
    assert resultado.coincide is False
    assert resultado.reportados == (
        "torchvision.models.mobilenet_v3",
        "torchvision.models.resnet18",
    )


def test_version_reportada_sin_eventos_no_coincide():
    resultado = version_reportada_vs_esperada([], "torchvision.models.resnet18")
    assert resultado.coincide is False  # ausencia de evidencia no es "coincide"


# --- G7 -----------------------------------------------------------------------


def test_alertas_activas_en_ventana_filtra_por_rango_inclusivo():
    alertas = [{"timestamp_ms": 100.0}, {"timestamp_ms": 500.0}, {"timestamp_ms": 900.0}]
    assert alertas_activas_en_ventana(alertas, 100.0, 500.0) == 2


def test_alertas_activas_en_ventana_invalida_lanza_value_error():
    with pytest.raises(ValueError):
        alertas_activas_en_ventana([], inicio_ms=500.0, fin_ms=100.0)
