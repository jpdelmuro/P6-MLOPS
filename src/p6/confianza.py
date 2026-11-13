"""P6: politica de confianza (R3) -- dos umbrales, tres zonas, referencia y una regla
de cambio sostenido.

Modulo con estado minimo (solo cuenta ventanas sostenidas), sin reloj ni persistencia:
`PoliticaConfianza` recibe un score y devuelve su zona; `evaluar_ventana` acumula
observaciones y decide si corresponde alertar por cambio sostenido. Quien arma el
evento/alerta final (ver `p6.eventos`/`p6.alertas`) agrega identidad y tiempos.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from p6.config import ConfigConfianza

Zona = Literal["aceptada", "duda", "baja_confianza", "sin_puntuacion"]


def zona_de(score: float | None, cfg: ConfigConfianza) -> Zona:
    """Interpretacion obligatoria de la politica: inferior <= s < superior es duda;
    s < inferior es baja confianza; s >= superior es aceptada (sin afirmar acierto).
    Sin puntuacion (inferencia fallida) es un estado aparte, nunca "aceptada" ni
    "baja_confianza" por omision."""
    if score is None or not math.isfinite(score):
        return "sin_puntuacion"
    if score >= cfg.umbral_superior:
        return "aceptada"
    if score >= cfg.umbral_inferior:
        return "duda"
    return "baja_confianza"


@dataclass(frozen=True)
class ResultadoVentana:
    tamano: int
    tasa_baja_confianza: float | None  # None si no hay suficientes muestras elegibles
    evidencia_suficiente: bool
    cambio_sostenido: bool
    razon: str


def tasa_baja_confianza(scores: list[float], cfg: ConfigConfianza) -> float | None:
    """`tasa_baja_confianza = imagenes con s < umbral_inferior / imagenes con
    inferencia valida y puntuacion elegible en la ventana` (formula declarada en la
    guia). `scores` ya debe venir filtrado a solo inferencias validas y puntuadas."""
    if len(scores) < cfg.minimo_muestras:
        return None
    bajos = sum(1 for s in scores if s < cfg.umbral_inferior)
    return bajos / len(scores)


def cargar_referencia(ruta: str | Path) -> float | None:
    """R3.3: "conserva una referencia" -- la referencia de `PoliticaConfianza` vive
    solo en memoria durante una corrida; esto le da continuidad real entre corridas
    (ej. C1 establece la referencia, C2 la hereda en vez de fijar la suya propia).
    Devuelve None si el archivo no existe todavia (primera corrida de la serie)."""
    ruta = Path(ruta)
    if not ruta.exists():
        return None
    datos = json.loads(ruta.read_text())
    return datos["referencia"]


def guardar_referencia(ruta: str | Path, referencia: float) -> None:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps({"referencia": referencia}))


class PoliticaConfianza:
    """Mantiene la referencia (tasa de baja confianza de la primera ventana valida, o
    la heredada de una corrida anterior via `referencia_inicial`) y cuenta ventanas
    consecutivas por encima de `referencia + margen_cambio_sostenido` para decidir un
    cambio sostenido -- misma histeresis por conteo que `p5.politica.cuadros_liberar`,
    aplicada aqui a ventanas en vez de cuadros."""

    def __init__(self, cfg: ConfigConfianza, referencia_inicial: float | None = None) -> None:
        self.cfg = cfg
        self._referencia: float | None = referencia_inicial
        self._ventanas_por_encima = 0

    @property
    def referencia(self) -> float | None:
        return self._referencia

    def evaluar_ventana(self, scores: list[float]) -> ResultadoVentana:
        tasa = tasa_baja_confianza(scores, self.cfg)
        if tasa is None:
            self._ventanas_por_encima = 0
            return ResultadoVentana(
                tamano=len(scores),
                tasa_baja_confianza=None,
                evidencia_suficiente=False,
                cambio_sostenido=False,
                razon="evidencia_insuficiente",
            )

        if self._referencia is None:
            self._referencia = tasa
            return ResultadoVentana(
                tamano=len(scores),
                tasa_baja_confianza=tasa,
                evidencia_suficiente=True,
                cambio_sostenido=False,
                razon="referencia_fijada",
            )

        if tasa > self._referencia + self.cfg.margen_cambio_sostenido:
            self._ventanas_por_encima += 1
        else:
            self._ventanas_por_encima = 0

        sostenido = self._ventanas_por_encima >= self.cfg.ventanas_sostenidas
        return ResultadoVentana(
            tamano=len(scores),
            tasa_baja_confianza=tasa,
            evidencia_suficiente=True,
            cambio_sostenido=sostenido,
            razon="cambio_sostenido" if sostenido else "dentro_de_referencia",
        )
