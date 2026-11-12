"""P6: reloj inyectable -- mismo principio que `p5.control`/`p5.watchdog`: un solo
origen monotonico por corrida, nunca el reloj de pared, compartido explicitamente entre
todos los componentes de una corrida (fuente, eventos, metricas, orquestador).
"""

from __future__ import annotations

import time
from collections.abc import Callable

Reloj = Callable[[], float]


def reloj_monotonico() -> Reloj:
    """Milisegundos monotonicos desde que se llama -- un solo origen por corrida.
    Quien construye la corrida llama esto una sola vez y pasa esa misma instancia a
    todos los componentes (o usa `RelojControlado` en pruebas)."""
    inicio = time.monotonic()
    return lambda: (time.monotonic() - inicio) * 1000


class RelojControlado:
    """Reloj de pruebas: tiempo manual en milisegundos, nunca el de pared."""

    def __init__(self, inicio: float = 0.0) -> None:
        self._ahora = inicio

    def __call__(self) -> float:
        return self._ahora

    def avanzar(self, ms: float) -> None:
        if ms < 0:
            raise ValueError(f"no se puede retroceder el reloj ({ms} ms)")
        self._ahora += ms
