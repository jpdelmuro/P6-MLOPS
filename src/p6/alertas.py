"""P6: alertas (R5) -- reglas explicitas evaluadas sobre observaciones reales (un
evento en zona baja_confianza, o una ventana de `PoliticaConfianza` con cambio
sostenido). El motor nunca fabrica una condicion: sin evidencia, no hay alerta.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from p6.confianza import ResultadoVentana
from p6.config import ConfigAlertas


@dataclass(frozen=True)
class Alerta:
    alert_id: str
    rule_id: str
    timestamp_ms: float
    severity: str
    event_ids: tuple[str, ...]
    config_ref: str
    reason: str
    suggested_action: str

    def a_dict(self) -> dict[str, Any]:
        datos = asdict(self)
        datos["event_ids"] = list(datos["event_ids"])
        return datos


class MotorAlertas:
    """Evalua las reglas declaradas en `config/alertas.yaml` sobre datos reales.
    `baja_confianza` depende de un evento individual; `cambio_sostenido` depende del
    `ResultadoVentana` de `PoliticaConfianza.evaluar_ventana`. Cada alerta queda
    vinculada a los `event_ids` que la originaron (R5.2)."""

    def __init__(self, cfg: ConfigAlertas, config_ref: str) -> None:
        self._cfg = cfg
        self._config_ref = config_ref
        self._contador = 0

    def _siguiente_id(self, prefijo: str) -> str:
        self._contador += 1
        return f"alert-{prefijo}-{self._contador:04d}"

    def evaluar_evento(self, event_id: str, zona: str, timestamp_ms: float) -> Alerta | None:
        regla = self._cfg.regla("baja_confianza")
        if regla is None or zona != "baja_confianza":
            return None
        return Alerta(
            alert_id=self._siguiente_id("bc"),
            rule_id=regla.id,
            timestamp_ms=timestamp_ms,
            severity=regla.severidad,
            event_ids=(event_id,),
            config_ref=self._config_ref,
            reason="Se cumplio la condicion configurada de baja confianza.",
            suggested_action=regla.accion_sugerida,
        )

    def generar_alerta_fuente(
        self,
        tipo: str,
        timestamp_ms: float,
        reason: str,
        event_ids: tuple[str, ...] = (),
    ) -> Alerta | None:
        """Genera una alerta para una condicion de la fuente (interrupcion/reconexion,
        extra S) -- no depende de un evento individual ni de una ventana de confianza,
        a diferencia de las otras dos reglas, pero usa la misma regla declarada en
        config/alertas.yaml (severidad, accion_sugerida) y el mismo almacen."""
        regla = self._cfg.regla(tipo)
        if regla is None:
            return None
        return Alerta(
            alert_id=self._siguiente_id(tipo.replace("fuente_", "")[:2]),
            rule_id=regla.id,
            timestamp_ms=timestamp_ms,
            severity=regla.severidad,
            event_ids=event_ids,
            config_ref=self._config_ref,
            reason=reason,
            suggested_action=regla.accion_sugerida,
        )

    def evaluar_ventana(
        self, resultado: ResultadoVentana, event_ids: list[str], timestamp_ms: float
    ) -> Alerta | None:
        regla = self._cfg.regla("cambio_sostenido")
        if regla is None or not resultado.cambio_sostenido:
            return None
        return Alerta(
            alert_id=self._siguiente_id("cs"),
            rule_id=regla.id,
            timestamp_ms=timestamp_ms,
            severity=regla.severidad,
            event_ids=tuple(event_ids),
            config_ref=self._config_ref,
            reason=(
                f"Tasa de baja confianza ({resultado.tasa_baja_confianza:.2f}) sostenida por "
                "encima de la referencia durante las ventanas configuradas."
            ),
            suggested_action=regla.accion_sugerida,
        )


class AlmacenAlertas:
    """Persistencia SQLite de alertas, consultable por el portal (R5.3) y exportable a
    JSONL para recalculo. Nunca borra ni expira registros."""

    def __init__(self, ruta_db: str | Path) -> None:
        Path(ruta_db).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(ruta_db)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alertas (
                alert_id TEXT PRIMARY KEY,
                rule_id TEXT NOT NULL,
                timestamp_ms REAL NOT NULL,
                datos TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def registrar(self, alerta: Alerta) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO alertas (alert_id, rule_id, timestamp_ms, datos) "
            "VALUES (?, ?, ?, ?)",
            (
                alerta.alert_id,
                alerta.rule_id,
                alerta.timestamp_ms,
                json.dumps(alerta.a_dict(), ensure_ascii=False),
            ),
        )
        self._conn.commit()

    def obtener(self, alert_id: str) -> dict[str, Any] | None:
        fila = self._conn.execute(
            "SELECT datos FROM alertas WHERE alert_id = ?", (alert_id,)
        ).fetchone()
        return json.loads(fila[0]) if fila else None

    def listar(self, rule_id: str | None = None) -> list[dict[str, Any]]:
        consulta = "SELECT datos FROM alertas WHERE 1=1"
        parametros: list[Any] = []
        if rule_id is not None:
            consulta += " AND rule_id = ?"
            parametros.append(rule_id)
        consulta += " ORDER BY timestamp_ms ASC"
        filas = self._conn.execute(consulta, parametros).fetchall()
        return [json.loads(f[0]) for f in filas]

    def exportar_jsonl(self, ruta: str | Path) -> Path:
        ruta = Path(ruta)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with ruta.open("w", encoding="utf-8") as archivo:
            for alerta in self.listar():
                archivo.write(json.dumps(alerta, ensure_ascii=False) + "\n")
        return ruta

    def cerrar(self) -> None:
        self._conn.close()
