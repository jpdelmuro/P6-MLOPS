"""P6: captura selectiva de imagenes (R4.3) -- se guarda por baja confianza, por alerta,
o como muestra periodica de operacion normal (no se exige guardar cada frame). Las
capturas se copian (nunca se mueve ni se borra el original) y nunca se sobreescriben ni
expiran.
"""

from __future__ import annotations

import shutil
from pathlib import Path


class PoliticaCapturas:
    """`cada_n_normal` guarda 1 de cada N frames en zona aceptada/duda/sin_puntuacion,
    como muestra de operacion normal -- documentado aqui, no en el config, porque no
    depende de la politica de confianza sino de cuanta evidencia de "va bien" se quiere
    conservar."""

    def __init__(self, carpeta_destino: str | Path, cada_n_normal: int = 10) -> None:
        if cada_n_normal < 1:
            raise ValueError("cada_n_normal debe ser al menos 1")
        self._carpeta = Path(carpeta_destino)
        self._carpeta.mkdir(parents=True, exist_ok=True)
        self._cada_n_normal = cada_n_normal
        self._contador_muestra = 0

    def debe_capturar(self, zona: str, alerta_disparada: bool) -> tuple[bool, str]:
        if alerta_disparada:
            return True, "alerta"
        if zona == "baja_confianza":
            return True, "baja_confianza"
        self._contador_muestra += 1
        if self._contador_muestra % self._cada_n_normal == 0:
            return True, "muestra_normal"
        return False, "no_capturada"

    def capturar(self, event_id: str, ruta_origen: str | Path) -> str:
        """Copia la imagen con un nombre vinculado a `event_id`, nunca mueve ni borra el
        original. Devuelve una referencia relativa resoluble para `Evento.image_ref`."""
        ruta_origen = Path(ruta_origen)
        destino = self._carpeta / f"{event_id}{ruta_origen.suffix.lower()}"
        if not destino.exists():
            shutil.copy2(ruta_origen, destino)
        return str(destino)
