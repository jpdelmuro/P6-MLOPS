"""P6: fuente visual (R1.1) -- reproduce una carpeta de imagenes como stream, en orden
estable, a una frecuencia declarada en `config/fuente.yaml`.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from p6.config import ConfigFuente
from p6.reloj import Reloj

EXTENSIONES_VALIDAS = (".jpg", ".jpeg", ".png")


class FuenteError(ValueError):
    pass


@dataclass(frozen=True)
class Frame:
    frame_id: str
    ruta: Path
    indice: int
    timestamp_ms: float


class SecuenciaImagenes:
    """Stream sintetico: ordena las imagenes de `carpeta` por nombre de archivo y les
    asigna un timestamp `origen + indice * frecuencia_ms`. No depende del reloj de pared
    real en el momento de cada frame -- la secuencia queda exactamente reproducible por
    quien evalue, sin tener que esperar en tiempo real.

    `reloj` fija el origen con una sola llamada: debe ser el mismo reloj que usan el
    resto de los componentes de la corrida (ver `p6.orquestador`), nunca uno propio.
    """

    def __init__(
        self,
        carpeta: str | Path,
        frecuencia_ms: float,
        reloj: Reloj,
        source_id: str | None = None,
    ) -> None:
        ruta_carpeta = Path(carpeta)
        if not ruta_carpeta.is_dir():
            raise FuenteError(f"{carpeta}: no es una carpeta valida")
        self._rutas = sorted(
            p for p in ruta_carpeta.iterdir() if p.suffix.lower() in EXTENSIONES_VALIDAS
        )
        if not self._rutas:
            raise FuenteError(f"{carpeta}: no contiene imagenes {EXTENSIONES_VALIDAS}")
        self._frecuencia_ms = frecuencia_ms
        self._origen_ms = reloj()
        self._source_id = source_id or ruta_carpeta.name

    @property
    def source_id(self) -> str:
        return self._source_id

    def __len__(self) -> int:
        return len(self._rutas)

    def __iter__(self) -> Iterator[Frame]:
        for indice, ruta in enumerate(self._rutas):
            yield Frame(
                frame_id=f"{self._source_id}_{indice:04d}",
                ruta=ruta,
                indice=indice,
                timestamp_ms=self._origen_ms + indice * self._frecuencia_ms,
            )


def construir_fuente(
    cfg: ConfigFuente, reloj: Reloj, source_id: str | None = None
) -> SecuenciaImagenes:
    return SecuenciaImagenes(cfg.carpeta, cfg.frecuencia_ms, reloj, source_id=source_id)
