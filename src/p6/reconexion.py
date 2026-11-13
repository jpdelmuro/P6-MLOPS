"""P6: interrupcion y reconexion de la fuente (extra S) -- envuelve `SecuenciaImagenes`
para demostrar una perdida real de acceso a la carpeta de origen (carpeta renombrada o
removida) y una recuperacion real, sin reemitir ni saltar frames.

No simula nada de red: la "fuente" de este proyecto es siempre una carpeta local, asi
que "interrupcion" significa que esa carpeta deja de ser accesible (renombrada, movida,
permisos revocados) y "reconexion" significa que vuelve a serlo.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from p6.fuente import Frame, FuenteError, SecuenciaImagenes
from p6.reloj import Reloj


class FuenteConReconexion:
    """Calcula el orden y los timestamps de los frames una sola vez (como
    `SecuenciaImagenes`, para que la secuencia siga siendo reproducible), pero valida
    que la carpeta de origen siga accesible antes de entregar cada frame. Si deja de
    estarlo, levanta `FuenteError` sin avanzar el cursor interno: una llamada posterior
    a `__iter__` (tras `reconectar()`) continua exactamente donde se quedo, sin repetir
    ni saltar frames."""

    def __init__(
        self,
        carpeta: str | Path,
        frecuencia_ms: float,
        reloj: Reloj,
        source_id: str | None = None,
    ) -> None:
        secuencia = SecuenciaImagenes(carpeta, frecuencia_ms, reloj, source_id=source_id)
        self._frames: tuple[Frame, ...] = tuple(secuencia)
        self._source_id = secuencia.source_id
        self._carpeta = Path(carpeta)
        self._siguiente_indice = 0

    @property
    def source_id(self) -> str:
        return self._source_id

    @property
    def siguiente_indice(self) -> int:
        """Cuantos frames ya se entregaron -- util para registrar el punto exacto de
        interrupcion en la evidencia del escenario."""
        return self._siguiente_indice

    def __len__(self) -> int:
        return len(self._frames)

    def esta_disponible(self) -> bool:
        return self._carpeta.is_dir()

    def reconectar(self) -> bool:
        """Revalida el acceso a la carpeta de origen. Devuelve True si ya esta
        disponible de nuevo (no vuelve a leer ni reordenar los archivos: el orden y los
        timestamps de los frames restantes son los mismos que se calcularon al
        construir la fuente, para que la corrida siga siendo reproducible)."""
        return self.esta_disponible()

    def __iter__(self) -> Iterator[Frame]:
        while self._siguiente_indice < len(self._frames):
            if not self.esta_disponible():
                raise FuenteError(f"{self._carpeta}: conexion perdida (fuente inaccesible)")
            frame = self._frames[self._siguiente_indice]
            yield frame
            self._siguiente_indice += 1
