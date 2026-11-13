"""P6: MotorAlertas y AlmacenAlertas (R5) -- reglas evaluadas sobre datos reales."""

from __future__ import annotations

import json

from p6.alertas import Alerta, AlmacenAlertas, MotorAlertas
from p6.confianza import ResultadoVentana
from p6.config import ConfigAlertas, ReglaAlerta

CFG_ALERTAS = ConfigAlertas(
    version=1,
    reglas=(
        ReglaAlerta(
            id="baja-confianza-v1",
            tipo="baja_confianza",
            severidad="warning",
            accion_sugerida="revisar captura",
        ),
        ReglaAlerta(
            id="cambio-sostenido-v1",
            tipo="cambio_sostenido",
            severidad="warning",
            accion_sugerida="investigar cambio",
        ),
        ReglaAlerta(
            id="fuente-interrumpida-v1",
            tipo="fuente_interrumpida",
            severidad="critical",
            accion_sugerida="revisar conectividad",
        ),
        ReglaAlerta(
            id="fuente-reconectada-v1",
            tipo="fuente_reconectada",
            severidad="info",
            accion_sugerida="confirmar continuidad",
        ),
    ),
)


def test_evaluar_evento_en_baja_confianza_genera_alerta_vinculada():
    motor = MotorAlertas(CFG_ALERTAS, config_ref="config-v1")
    alerta = motor.evaluar_evento("evt-1", zona="baja_confianza", timestamp_ms=1000.0)
    assert alerta is not None
    assert alerta.rule_id == "baja-confianza-v1"
    assert alerta.event_ids == ("evt-1",)
    assert alerta.severity == "warning"
    assert alerta.config_ref == "config-v1"


def test_evaluar_evento_en_zona_aceptada_no_genera_alerta():
    motor = MotorAlertas(CFG_ALERTAS, config_ref="config-v1")
    assert motor.evaluar_evento("evt-1", zona="aceptada", timestamp_ms=1000.0) is None


def test_evaluar_evento_en_zona_duda_no_genera_alerta():
    motor = MotorAlertas(CFG_ALERTAS, config_ref="config-v1")
    assert motor.evaluar_evento("evt-1", zona="duda", timestamp_ms=1000.0) is None


def test_sin_regla_de_baja_confianza_configurada_no_genera_alerta():
    cfg_sin_regla = ConfigAlertas(version=1, reglas=(CFG_ALERTAS.reglas[1],))
    motor = MotorAlertas(cfg_sin_regla, config_ref="config-v1")
    assert motor.evaluar_evento("evt-1", zona="baja_confianza", timestamp_ms=1000.0) is None


def test_evaluar_ventana_con_cambio_sostenido_genera_alerta_vinculada():
    motor = MotorAlertas(CFG_ALERTAS, config_ref="config-v1")
    resultado = ResultadoVentana(
        tamano=5,
        tasa_baja_confianza=0.4,
        evidencia_suficiente=True,
        cambio_sostenido=True,
        razon="cambio_sostenido",
    )
    alerta = motor.evaluar_ventana(resultado, ["evt-1", "evt-2"], timestamp_ms=2000.0)
    assert alerta is not None
    assert alerta.rule_id == "cambio-sostenido-v1"
    assert alerta.event_ids == ("evt-1", "evt-2")
    assert "0.40" in alerta.reason


def test_generar_alerta_fuente_interrumpida():
    motor = MotorAlertas(CFG_ALERTAS, config_ref="config-v1")
    alerta = motor.generar_alerta_fuente(
        "fuente_interrumpida", timestamp_ms=3000.0, reason="carpeta inaccesible tras frame 4"
    )
    assert alerta is not None
    assert alerta.rule_id == "fuente-interrumpida-v1"
    assert alerta.severity == "critical"
    assert alerta.reason == "carpeta inaccesible tras frame 4"


def test_generar_alerta_fuente_reconectada_vinculada_a_eventos():
    motor = MotorAlertas(CFG_ALERTAS, config_ref="config-v1")
    alerta = motor.generar_alerta_fuente(
        "fuente_reconectada",
        timestamp_ms=4000.0,
        reason="reanudada en frame 5",
        event_ids=("evt-5", "evt-6"),
    )
    assert alerta is not None
    assert alerta.rule_id == "fuente-reconectada-v1"
    assert alerta.severity == "info"
    assert alerta.event_ids == ("evt-5", "evt-6")


def test_generar_alerta_fuente_sin_regla_configurada_es_none():
    cfg_sin_reglas_de_fuente = ConfigAlertas(version=1, reglas=CFG_ALERTAS.reglas[:2])
    motor = MotorAlertas(cfg_sin_reglas_de_fuente, config_ref="config-v1")
    assert motor.generar_alerta_fuente("fuente_interrumpida", 1000.0, "x") is None


def test_evaluar_ventana_sin_cambio_sostenido_no_genera_alerta():
    motor = MotorAlertas(CFG_ALERTAS, config_ref="config-v1")
    resultado = ResultadoVentana(
        tamano=5,
        tasa_baja_confianza=0.1,
        evidencia_suficiente=True,
        cambio_sostenido=False,
        razon="dentro_de_referencia",
    )
    assert motor.evaluar_ventana(resultado, ["evt-1"], timestamp_ms=2000.0) is None


def test_ids_de_alerta_son_unicos_por_instancia_del_motor():
    motor = MotorAlertas(CFG_ALERTAS, config_ref="config-v1")
    a1 = motor.evaluar_evento("evt-1", zona="baja_confianza", timestamp_ms=1000.0)
    a2 = motor.evaluar_evento("evt-2", zona="baja_confianza", timestamp_ms=1500.0)
    assert a1.alert_id != a2.alert_id


def _alerta(alert_id="alert-1", rule_id="baja-confianza-v1", timestamp_ms=1000.0):
    return Alerta(
        alert_id=alert_id,
        rule_id=rule_id,
        timestamp_ms=timestamp_ms,
        severity="warning",
        event_ids=("evt-1",),
        config_ref="config-v1",
        reason="prueba",
        suggested_action="revisar",
    )


def test_registrar_y_obtener_por_alert_id(tmp_path):
    almacen = AlmacenAlertas(tmp_path / "alertas.db")
    almacen.registrar(_alerta())
    recuperada = almacen.obtener("alert-1")
    assert recuperada is not None
    assert recuperada["event_ids"] == ["evt-1"]
    almacen.cerrar()


def test_listar_filtra_por_rule_id_y_ordena_por_tiempo(tmp_path):
    almacen = AlmacenAlertas(tmp_path / "alertas.db")
    almacen.registrar(_alerta(alert_id="a2", rule_id="cambio-sostenido-v1", timestamp_ms=2000.0))
    almacen.registrar(_alerta(alert_id="a1", rule_id="baja-confianza-v1", timestamp_ms=1000.0))

    solo_baja_confianza = almacen.listar(rule_id="baja-confianza-v1")
    assert [a["alert_id"] for a in solo_baja_confianza] == ["a1"]

    todas = almacen.listar()
    assert [a["alert_id"] for a in todas] == ["a1", "a2"]
    almacen.cerrar()


def test_exportar_jsonl_produce_una_linea_por_alerta(tmp_path):
    almacen = AlmacenAlertas(tmp_path / "alertas.db")
    almacen.registrar(_alerta(alert_id="a1"))
    almacen.registrar(_alerta(alert_id="a2", timestamp_ms=1500.0))

    ruta = almacen.exportar_jsonl(tmp_path / "export" / "alertas.jsonl")
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    assert len(lineas) == 2
    ids = {json.loads(linea)["alert_id"] for linea in lineas}
    assert ids == {"a1", "a2"}
    almacen.cerrar()
