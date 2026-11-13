"""P6: eventos de inferencia (R4.1, R4.2) -- identidad completa, persistencia en SQLite
y exportacion a JSONL para evidencia recalculable (M5).
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from p6.modelo import Prediccion

#: Reutilizado por `p6.metricas` para la cobertura de trazabilidad (G5) sobre eventos
#: recalculados desde JSONL (dicts), no solo sobre instancias de `Evento` en memoria.
CAMPOS_EVENTO_OBLIGATORIOS = (
    "event_id",
    "run_id",
    "frame_id",
    "timestamp_ms",
    "fecha_utc",
    "source_id",
    "task",
    "model_ref",
    "status",
    "confidence_zone",
    "config_ref",
)


def _ahora_utc_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class Evento:
    event_id: str
    run_id: str
    frame_id: str
    timestamp_ms: float  # posicion sintetica en el stream (R1.1), no un reloj de pared
    source_id: str
    task: str
    model_ref: str
    status: str  # "ok" | "error"
    prediction: Prediccion | None
    confidence_zone: str  # "aceptada" | "duda" | "baja_confianza" | "sin_puntuacion"
    config_ref: str
    image_ref: str | None = None
    #: Fecha/hora real (UTC, ISO-8601) en que se proceso el frame -- R4.1 pide "fecha",
    #: que `timestamp_ms` (sintetico, relativo al origen de la corrida) no provee.
    fecha_utc: str = field(default_factory=_ahora_utc_iso)

    def a_dict(self) -> dict[str, Any]:
        return asdict(self)


def evento_completo(evento: Evento) -> bool:
    """R4.1/G5: todos los campos de identidad presentes, y la prediccion coherente con
    el estado (ok -> hay prediction; error -> no la hay, zona sin_puntuacion)."""
    datos = evento.a_dict()
    if any(not datos.get(campo) for campo in CAMPOS_EVENTO_OBLIGATORIOS):
        return False
    if evento.status == "ok":
        return evento.prediction is not None and evento.confidence_zone != "sin_puntuacion"
    return evento.prediction is None and evento.confidence_zone == "sin_puntuacion"


class AlmacenEventos:
    """Persistencia SQLite de eventos, consultable por el portal (R4.2) y exportable a
    JSONL para recalculo (M5). Nunca borra ni expira registros."""

    def __init__(self, ruta_db: str | Path) -> None:
        Path(ruta_db).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(ruta_db)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS eventos (
                event_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                timestamp_ms REAL NOT NULL,
                confidence_zone TEXT NOT NULL,
                status TEXT NOT NULL,
                datos TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def registrar(self, evento: Evento) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO eventos "
            "(event_id, run_id, timestamp_ms, confidence_zone, status, datos) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                evento.event_id,
                evento.run_id,
                evento.timestamp_ms,
                evento.confidence_zone,
                evento.status,
                json.dumps(evento.a_dict(), ensure_ascii=False),
            ),
        )
        self._conn.commit()

    def obtener(self, event_id: str) -> dict[str, Any] | None:
        fila = self._conn.execute(
            "SELECT datos FROM eventos WHERE event_id = ?", (event_id,)
        ).fetchone()
        return json.loads(fila[0]) if fila else None

    def listar(self, run_id: str | None = None, zona: str | None = None) -> list[dict[str, Any]]:
        consulta = "SELECT datos FROM eventos WHERE 1=1"
        parametros: list[Any] = []
        if run_id is not None:
            consulta += " AND run_id = ?"
            parametros.append(run_id)
        if zona is not None:
            consulta += " AND confidence_zone = ?"
            parametros.append(zona)
        consulta += " ORDER BY timestamp_ms ASC"
        filas = self._conn.execute(consulta, parametros).fetchall()
        return [json.loads(f[0]) for f in filas]

    def exportar_jsonl(self, ruta: str | Path, run_id: str | None = None) -> Path:
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with ruta.open("w", encoding="utf-8") as archivo:
            for evento in self.listar(run_id=run_id):
                archivo.write(json.dumps(evento, ensure_ascii=False) + "\n")
        return ruta

    def cerrar(self) -> None:
        self._conn.close()
