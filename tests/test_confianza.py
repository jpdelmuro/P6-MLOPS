"""P6: zonas de confianza, tasa de baja confianza y regla de cambio sostenido (R3)."""

from __future__ import annotations

import pytest

from p6.confianza import PoliticaConfianza, tasa_baja_confianza, zona_de
from p6.config import ConfigConfianza

CFG = ConfigConfianza(
    umbral_inferior=0.60,
    umbral_superior=0.80,
    tamano_ventana=10,
    minimo_muestras=5,
    margen_cambio_sostenido=0.20,
    ventanas_sostenidas=3,
)


@pytest.mark.parametrize(
    ("score", "zona_esperada"),
    [
        (0.95, "aceptada"),
        (0.80, "aceptada"),  # igualdad con el superior: aceptada
        (0.79, "duda"),
        (0.60, "duda"),  # igualdad con el inferior: duda
        (0.59, "baja_confianza"),
        (0.0, "baja_confianza"),
        (None, "sin_puntuacion"),
        (float("nan"), "sin_puntuacion"),
    ],
)
def test_zona_de_respeta_los_bordes_exactos(score, zona_esperada):
    assert zona_de(score, CFG) == zona_esperada


def test_tasa_baja_confianza_none_si_faltan_muestras():
    assert tasa_baja_confianza([0.5, 0.5], CFG) is None  # minimo_muestras=5


def test_tasa_baja_confianza_calcula_la_proporcion_exacta():
    scores = [0.5, 0.5, 0.9, 0.9, 0.9]  # 2 de 5 bajo 0.60
    assert tasa_baja_confianza(scores, CFG) == pytest.approx(0.4)


def test_primera_ventana_valida_fija_la_referencia():
    politica = PoliticaConfianza(CFG)
    resultado = politica.evaluar_ventana([0.9, 0.9, 0.9, 0.9, 0.9])  # tasa=0.0
    assert resultado.evidencia_suficiente is True
    assert resultado.razon == "referencia_fijada"
    assert resultado.cambio_sostenido is False
    assert politica.referencia == pytest.approx(0.0)


def test_ventana_insuficiente_nunca_es_normal_ni_cambio_sostenido():
    politica = PoliticaConfianza(CFG)
    politica.evaluar_ventana([0.9, 0.9, 0.9, 0.9, 0.9])  # referencia = 0.0
    resultado = politica.evaluar_ventana([0.5, 0.5])  # insuficiente
    assert resultado.evidencia_suficiente is False
    assert resultado.cambio_sostenido is False
    assert resultado.razon == "evidencia_insuficiente"
    assert resultado.tasa_baja_confianza is None


def test_cambio_sostenido_dispara_solo_tras_las_ventanas_persistentes_configuradas():
    politica = PoliticaConfianza(CFG)
    politica.evaluar_ventana([0.9, 0.9, 0.9, 0.9, 0.9])  # referencia = 0.0

    # tasa=0.4 > referencia(0.0) + margen(0.20): por encima, pero solo 1 ventana.
    ventana_alta = [0.5, 0.5, 0.9, 0.9, 0.9]
    r1 = politica.evaluar_ventana(ventana_alta)
    r2 = politica.evaluar_ventana(ventana_alta)
    assert r1.cambio_sostenido is False
    assert r2.cambio_sostenido is False

    r3 = politica.evaluar_ventana(ventana_alta)  # 3ra consecutiva -> ventanas_sostenidas=3
    assert r3.cambio_sostenido is True
    assert r3.razon == "cambio_sostenido"


def test_una_ventana_dentro_de_referencia_reinicia_el_conteo_sostenido():
    politica = PoliticaConfianza(CFG)
    politica.evaluar_ventana([0.9, 0.9, 0.9, 0.9, 0.9])  # referencia = 0.0
    ventana_alta = [0.5, 0.5, 0.9, 0.9, 0.9]
    ventana_normal = [0.9, 0.9, 0.9, 0.9, 0.9]

    politica.evaluar_ventana(ventana_alta)
    politica.evaluar_ventana(ventana_alta)
    r = politica.evaluar_ventana(ventana_normal)  # rompe la racha antes de sostenerse
    assert r.cambio_sostenido is False

    r1 = politica.evaluar_ventana(ventana_alta)
    r2 = politica.evaluar_ventana(ventana_alta)
    assert r1.cambio_sostenido is False and r2.cambio_sostenido is False  # solo 2, no 3


def test_ventana_insuficiente_tambien_reinicia_el_conteo_sostenido():
    politica = PoliticaConfianza(CFG)
    politica.evaluar_ventana([0.9, 0.9, 0.9, 0.9, 0.9])  # referencia = 0.0
    ventana_alta = [0.5, 0.5, 0.9, 0.9, 0.9]

    politica.evaluar_ventana(ventana_alta)
    politica.evaluar_ventana(ventana_alta)
    politica.evaluar_ventana([0.5, 0.5])  # insuficiente: rompe la racha
    r1 = politica.evaluar_ventana(ventana_alta)
    r2 = politica.evaluar_ventana(ventana_alta)
    assert r1.cambio_sostenido is False and r2.cambio_sostenido is False
