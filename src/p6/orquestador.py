"""P6: orquestador -- une fuente, modelo, politica de confianza, eventos, capturas y
alertas en una sola corrida, con un unico reloj compartido (mismo principio que el
`Watchdog` del Proyecto 5: un solo origen de tiempo por corrida, nunca dos relojes
independientes).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import psutil

from p6.alertas import AlmacenAlertas, MotorAlertas
from p6.capturas import PoliticaCapturas
from p6.confianza import PoliticaConfianza, zona_de
from p6.config import ConfigAlertas, ConfigConfianza, ConfigFuente, ConfigModelo
from p6.eventos import AlmacenEventos, Evento
from p6.fuente import construir_fuente
from p6.metricas import Medicion
from p6.modelo import ModeloError, Prediccion
from p6.reloj import Reloj


class Clasificador(Protocol):
    def clasificar(self, ruta_imagen: Path) -> Prediccion: ...


@dataclass(frozen=True)
class ResultadoCorrida:
    run_id: str
    total_frames: int
    almacen_eventos: AlmacenEventos
    almacen_alertas: AlmacenAlertas
    mediciones: tuple[Medicion, ...]


def ejecutar_corrida(
    run_id: str,
    cfg_fuente: ConfigFuente,
    cfg_modelo: ConfigModelo,
    cfg_confianza: ConfigConfianza,
    cfg_alertas: ConfigAlertas,
    reloj: Reloj,
    carpeta_evidencias: str | Path,
    clasificador: Clasificador,
    source_id: str | None = None,
    config_ref: str = "config-v1",
) -> ResultadoCorrida:
    """Recorre toda la fuente una vez: por cada frame, clasifica, ubica la zona de
    confianza, decide la captura, registra el evento y evalua alertas (por evento y por
    ventana). `clasificador` se inyecta siempre explicitamente -- nunca se construye
    aqui un modelo por defecto, para que una corrida de prueba pueda usar un doble sin
    cargar los pesos reales."""
    carpeta_evidencias = Path(carpeta_evidencias)
    fuente = construir_fuente(cfg_fuente, reloj, source_id=source_id)
    politica = PoliticaConfianza(cfg_confianza)
    motor_alertas = MotorAlertas(cfg_alertas, config_ref=config_ref)

    almacen_eventos = AlmacenEventos(carpeta_evidencias / f"eventos-{run_id}.db")
    almacen_alertas = AlmacenAlertas(carpeta_evidencias / f"alertas-{run_id}.db")
    capturas = PoliticaCapturas(carpeta_evidencias / "imagenes")

    proceso = psutil.Process()
    model_ref = f"{cfg_modelo.modelo_ref}@{cfg_modelo.pesos}"

    mediciones: list[Medicion] = []
    scores_ventana: list[float] = []
    event_ids_ventana: list[str] = []
    ultimo_timestamp_ms = reloj()
    total = 0

    for frame in fuente:
        total += 1
        event_id = f"evt-{run_id}-{frame.frame_id}"
        ultimo_timestamp_ms = frame.timestamp_ms

        inicio = time.perf_counter()
        try:
            prediccion: Prediccion | None = clasificador.clasificar(frame.ruta)
            status = "ok"
        except ModeloError:
            prediccion = None
            status = "error"
        duracion_ms = (time.perf_counter() - inicio) * 1000

        mediciones.append(
            Medicion(
                frame_id=frame.frame_id,
                timestamp_ms=frame.timestamp_ms,
                duracion_inferencia_ms=duracion_ms,
                cpu_percent=proceso.cpu_percent(interval=None),
                ram_mb=proceso.memory_info().rss / (1024 * 1024),
            )
        )

        score = prediccion.score if prediccion is not None else None
        zona = zona_de(score, cfg_confianza) if status == "ok" else "sin_puntuacion"

        alerta_evento = motor_alertas.evaluar_evento(event_id, zona, frame.timestamp_ms)
        captura, _razon = capturas.debe_capturar(zona, alerta_disparada=alerta_evento is not None)
        image_ref = capturas.capturar(event_id, frame.ruta) if captura else None

        almacen_eventos.registrar(
            Evento(
                event_id=event_id,
                run_id=run_id,
                frame_id=frame.frame_id,
                timestamp_ms=frame.timestamp_ms,
                source_id=fuente.source_id,
                task="classification",
                model_ref=model_ref,
                status=status,
                prediction=prediccion,
                confidence_zone=zona,
                config_ref=config_ref,
                image_ref=image_ref,
            )
        )
        if alerta_evento is not None:
            almacen_alertas.registrar(alerta_evento)

        if status == "ok" and score is not None:
            scores_ventana.append(score)
            event_ids_ventana.append(event_id)
            if len(scores_ventana) >= cfg_confianza.tamano_ventana:
                _evaluar_y_registrar_ventana(
                    politica,
                    motor_alertas,
                    almacen_alertas,
                    scores_ventana,
                    event_ids_ventana,
                    frame.timestamp_ms,
                )
                scores_ventana, event_ids_ventana = [], []

    if scores_ventana:  # cola final: nunca se descarta en silencio, aunque no llene la ventana
        _evaluar_y_registrar_ventana(
            politica,
            motor_alertas,
            almacen_alertas,
            scores_ventana,
            event_ids_ventana,
            ultimo_timestamp_ms,
        )

    return ResultadoCorrida(
        run_id=run_id,
        total_frames=total,
        almacen_eventos=almacen_eventos,
        almacen_alertas=almacen_alertas,
        mediciones=tuple(mediciones),
    )


def _evaluar_y_registrar_ventana(
    politica: PoliticaConfianza,
    motor_alertas: MotorAlertas,
    almacen_alertas: AlmacenAlertas,
    scores_ventana: list[float],
    event_ids_ventana: list[str],
    timestamp_ms: float,
) -> None:
    resultado = politica.evaluar_ventana(scores_ventana)
    alerta = motor_alertas.evaluar_ventana(resultado, event_ids_ventana, timestamp_ms)
    if alerta is not None:
        almacen_alertas.registrar(alerta)
