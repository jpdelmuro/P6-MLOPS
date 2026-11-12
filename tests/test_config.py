"""P6: validacion de config/*.yaml (fuente, modelo, confianza, alertas)."""

from __future__ import annotations

import copy

import pytest

from p6.config import (
    ConfigError,
    cargar_alertas,
    cargar_confianza,
    cargar_fuente,
    cargar_modelo,
    validar_alertas,
    validar_confianza,
    validar_fuente,
    validar_modelo,
)

FUENTE_OK = {"carpeta": "datos/stream/normal", "frecuencia_ms": 500}
MODELO_OK = {
    "modelo_ref": "torchvision.models.resnet18",
    "pesos": "ResNet18_Weights.IMAGENET1K_V1",
    "clases_ref": "imagenet-1k",
    "preprocesamiento": "resize+crop+normalize",
    "entorno": "CPU",
}
CONFIANZA_OK = {
    "umbral_inferior": 0.60,
    "umbral_superior": 0.80,
    "tamano_ventana": 10,
    "minimo_muestras": 5,
    "margen_cambio_sostenido": 0.20,
    "ventanas_sostenidas": 3,
}
ALERTAS_OK = {
    "version": 1,
    "reglas": [
        {
            "id": "baja-confianza-v1",
            "tipo": "baja_confianza",
            "severidad": "warning",
            "accion_sugerida": "revisar",
        },
        {
            "id": "cambio-sostenido-v1",
            "tipo": "cambio_sostenido",
            "severidad": "warning",
            "accion_sugerida": "investigar",
        },
    ],
}


def test_fuente_valida_se_acepta():
    cfg = validar_fuente(FUENTE_OK)
    assert cfg.carpeta == "datos/stream/normal"
    assert cfg.frecuencia_ms == 500.0


@pytest.mark.parametrize(
    "mutacion",
    [
        lambda d: d.update(frecuencia_ms=0),
        lambda d: d.update(frecuencia_ms=-10),
        lambda d: d.update(frecuencia_ms=float("nan")),
        lambda d: d.update(carpeta=""),
        lambda d: d.pop("carpeta"),
        lambda d: d.update(clave_extra=1),
    ],
)
def test_fuente_invalida_se_rechaza(mutacion):
    data = copy.deepcopy(FUENTE_OK)
    mutacion(data)
    with pytest.raises(ConfigError):
        validar_fuente(data)


def test_modelo_valido_se_acepta():
    cfg = validar_modelo(MODELO_OK)
    assert cfg.modelo_ref == "torchvision.models.resnet18"


@pytest.mark.parametrize("campo", list(MODELO_OK))
def test_modelo_rechaza_campo_vacio(campo):
    data = copy.deepcopy(MODELO_OK)
    data[campo] = ""
    with pytest.raises(ConfigError):
        validar_modelo(data)


def test_confianza_valida_se_acepta():
    cfg = validar_confianza(CONFIANZA_OK)
    assert cfg.umbral_inferior < cfg.umbral_superior


@pytest.mark.parametrize(
    "mutacion",
    [
        lambda d: d.update(umbral_inferior=0.80, umbral_superior=0.60),
        lambda d: d.update(umbral_inferior=0.80, umbral_superior=0.80),
        lambda d: d.update(umbral_superior=1.5),
        lambda d: d.update(umbral_inferior=-0.1),
        lambda d: d.update(tamano_ventana=0),
        lambda d: d.update(minimo_muestras=20),  # > tamano_ventana
        lambda d: d.update(margen_cambio_sostenido=-0.1),
        lambda d: d.update(ventanas_sostenidas=0),
    ],
)
def test_confianza_invalida_se_rechaza(mutacion):
    data = copy.deepcopy(CONFIANZA_OK)
    mutacion(data)
    with pytest.raises(ConfigError):
        validar_confianza(data)


def test_confianza_acepta_igualdad_en_los_bordes():
    # 0 <= inferior < superior <= 1, los bordes 0 y 1 son validos por si solos.
    data = copy.deepcopy(CONFIANZA_OK)
    data["umbral_inferior"] = 0.0
    data["umbral_superior"] = 1.0
    validar_confianza(data)  # no lanza


def test_alertas_validas_se_aceptan():
    cfg = validar_alertas(ALERTAS_OK)
    assert len(cfg.reglas) == 2
    assert cfg.regla("baja_confianza").id == "baja-confianza-v1"
    assert cfg.regla("cambio_sostenido").id == "cambio-sostenido-v1"


def test_alertas_rechaza_tipo_desconocido():
    data = copy.deepcopy(ALERTAS_OK)
    data["reglas"][0]["tipo"] = "fantasia"
    with pytest.raises(ConfigError):
        validar_alertas(data)


def test_alertas_rechaza_id_duplicado():
    data = copy.deepcopy(ALERTAS_OK)
    data["reglas"][1]["id"] = data["reglas"][0]["id"]
    with pytest.raises(ConfigError):
        validar_alertas(data)


def test_alertas_rechaza_lista_vacia():
    data = copy.deepcopy(ALERTAS_OK)
    data["reglas"] = []
    with pytest.raises(ConfigError):
        validar_alertas(data)


def test_cargar_los_cuatro_yaml_reales_del_repo():
    # Asegura que config/*.yaml del repo siguen siendo validos conforme evoluciona config.py.
    cargar_fuente("config/fuente.yaml")
    cargar_modelo("config/modelo.yaml")
    cargar_confianza("config/confianza.yaml")
    cargar_alertas("config/alertas.yaml")
