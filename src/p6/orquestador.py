"""P6: orquestador -- une fuente, modelo, politica de confianza, eventos, capturas y
alertas en una sola corrida, con un unico reloj compartido (mismo principio que el
`Watchdog` del Proyecto 5: un solo origen de tiempo por corrida, nunca dos relojes
independientes).

`procesar_frame` concentra la logica por-frame (clasificar, zona, captura, evento,
alerta por evento) para que `ejecutar_corrida` y cualquier corrida que envuelva su
propia fuente (ver `scripts/escenario_reconexion.py`, extra S) usen exactamente el
mismo camino -- un escenario adicional nunca debe saltarse la alerta o la captura que
el resto del sistema sí aplica.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol

import psutil

from p6.alertas import Alerta, AlmacenAlertas, MotorAlertas
from p6.capturas import PoliticaCapturas
from p6.confianza import PoliticaConfianza, cargar_referencia, guardar_referencia, zona_de
from p6.config import ConfigAlertas, ConfigConfianza, ConfigFuente, ConfigModelo
from p6.eventos import AlmacenEventos, Evento
from p6.fuente import Frame, construir_fuente
from p6.metricas import Medicion
from p6.modelo import ModeloError, Prediccion
from p6.reloj import Reloj


class Clasificador(Protocol):
    def cargar_y_preprocesar(self, ruta_imagen: Path): ...  # devuelve un tensor de torch
    def inferir(self, entrada) -> Prediccion: ...
    @property
    def model_ref(self) -> str: ...  # identidad real de lo que esta instancia cargo (G6)


def calcular_config_ref(
    cfg_confianza: ConfigConfianza, cfg_alertas: ConfigAlertas, cfg_modelo: ConfigModelo
) -> str:
    """Huella de la configuracion real usada por la corrida (R4.1 pide "la
    configuracion usada", no un texto fijo que no refleje umbrales ni ventana).
    Cambia si cambia cualquier umbral, ventana o regla -- identidad resoluble, no
    decorativa."""
    payload = json.dumps(
        {
            "confianza": asdict(cfg_confianza),
            "alertas": asdict(cfg_alertas),
            "modelo": asdict(cfg_modelo),
        },
        sort_keys=True,
    )
    return "config-" + hashlib.sha256(payload.encode()).hexdigest()[:10]


def iniciar_medicion_recursos() -> psutil.Process:
    """`Process.cpu_percent(interval=None)` devuelve 0.0, sin significado, en su
    primera llamada (no hay intervalo previo que medir) -- esa primera lectura se
    descarta aqui, antes de procesar ningun frame, para que G3 no promedie un 0.0
    artificial. Llamadas posteriores sí miden el intervalo real transcurrido."""
    proceso = psutil.Process()
    proceso.cpu_percent(interval=None)
    return proceso


@dataclass(frozen=True)
class ResultadoFrame:
    evento: Evento
    medicion: Medicion | None  # None si la imagen no se pudo leer: no hubo inferencia
    alerta: Alerta | None


def procesar_frame(
    frame: Frame,
    *,
    run_id: str,
    source_id: str,
    model_ref: str,
    config_ref: str,
    clasificador: Clasificador,
    cfg_confianza: ConfigConfianza,
    motor_alertas: MotorAlertas,
    capturas: PoliticaCapturas,
    proceso: psutil.Process,
) -> ResultadoFrame:
    """Un frame -> un evento + (si hubo inferencia) una medicion + (si corresponde)
    una alerta por evento. El tiempo medido para G1 es solo `clasificador.inferir`
    (nunca la lectura/decodificacion de la imagen, que `cargar_y_preprocesar` hace por
    separado)."""
    event_id = f"evt-{run_id}-{frame.frame_id}"

    try:
        entrada = clasificador.cargar_y_preprocesar(frame.ruta)
        status = "ok"
    except ModeloError:
        entrada = None
        status = "error"

    prediccion: Prediccion | None = None
    medicion: Medicion | None = None
    if status == "ok":
        inicio = time.perf_counter()
        prediccion = clasificador.inferir(entrada)
        duracion_inferencia_ms = (time.perf_counter() - inicio) * 1000
        medicion = Medicion(
            frame_id=frame.frame_id,
            timestamp_ms=frame.timestamp_ms,
            duracion_inferencia_ms=duracion_inferencia_ms,
            cpu_percent=proceso.cpu_percent(interval=None),
            ram_mb=proceso.memory_info().rss / (1024 * 1024),
        )

    score = prediccion.score if prediccion is not None else None
    zona = zona_de(score, cfg_confianza) if status == "ok" else "sin_puntuacion"

    alerta_evento = motor_alertas.evaluar_evento(
        event_id,
        zona,
        frame.timestamp_ms,
        score=score,
        umbral_inferior=cfg_confianza.umbral_inferior,
    )
    captura, _razon = capturas.debe_capturar(zona, alerta_disparada=alerta_evento is not None)
    image_ref = capturas.capturar(event_id, frame.ruta) if captura else None

    evento = Evento(
        event_id=event_id,
        run_id=run_id,
        frame_id=frame.frame_id,
        timestamp_ms=frame.timestamp_ms,
        source_id=source_id,
        task="classification",
        model_ref=model_ref,
        status=status,
        prediction=prediccion,
        confidence_zone=zona,
        config_ref=config_ref,
        image_ref=image_ref,
    )
    return ResultadoFrame(evento=evento, medicion=medicion, alerta=alerta_evento)


@dataclass(frozen=True)
class ResultadoCorrida:
    run_id: str
    total_frames: int
    almacen_eventos: AlmacenEventos
    almacen_alertas: AlmacenAlertas
    mediciones: tuple[Medicion, ...]
    #: Un dict por ventana evaluada (timestamp_ms + los campos de ResultadoVentana),
    #: incluidas las que dieron "evidencia_insuficiente" y nunca generaron alerta --
    #: para que ese estado sea observable en la evidencia persistida, no solo en
    #: pruebas unitarias (R3.3).
    resultados_ventana: tuple[dict, ...]


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
    config_ref: str | None = None,
    ruta_referencia: str | Path | None = None,
    tiempo_real: bool = False,
) -> ResultadoCorrida:
    """Recorre toda la fuente una vez usando `procesar_frame` por cada frame, y evalua
    la regla de cambio sostenido por ventana. `clasificador` se inyecta siempre
    explicitamente -- nunca se construye aqui un modelo por defecto, para que una
    corrida de prueba pueda usar un doble sin cargar los pesos reales.

    `config_ref`: si se omite, se calcula de `cfg_confianza`/`cfg_alertas`/`cfg_modelo`
    reales (ver `calcular_config_ref`) en vez de usar un texto fijo.

    `ruta_referencia` (R3.3): si se da, la referencia de `PoliticaConfianza` se carga
    de ese archivo al iniciar (si existe de una corrida anterior) y se guarda ahi al
    terminar -- asi una serie de corridas (ej. C1 -> C2) comparte una referencia real
    en vez de que cada una fije la suya propia.

    `tiempo_real` (R1.1): por defecto la corrida es instantanea (los timestamps son
    sinteticos, para que sea reproducible sin esperar). Con `tiempo_real=True`, ademas
    espera `cfg_fuente.frecuencia_ms` de reloj de pared real entre frames -- la
    frecuencia declarada deja de ser solo una etiqueta y pasa a ser el ritmo real de
    entrega, a costa de que la corrida tarde literalmente eso en completarse."""
    carpeta_evidencias = Path(carpeta_evidencias)
    config_ref = config_ref or calcular_config_ref(cfg_confianza, cfg_alertas, cfg_modelo)
    fuente = construir_fuente(cfg_fuente, reloj, source_id=source_id)
    referencia_inicial = cargar_referencia(ruta_referencia) if ruta_referencia else None
    politica = PoliticaConfianza(cfg_confianza, referencia_inicial=referencia_inicial)
    motor_alertas = MotorAlertas(cfg_alertas, config_ref=config_ref)

    almacen_eventos = AlmacenEventos(carpeta_evidencias / f"eventos-{run_id}.db")
    almacen_alertas = AlmacenAlertas(carpeta_evidencias / f"alertas-{run_id}.db")
    capturas = PoliticaCapturas(carpeta_evidencias / "imagenes")

    proceso = iniciar_medicion_recursos()
    # G6 compara esto (lo que el clasificador reporta de si mismo) contra lo declarado
    # en cfg_modelo -- si algun dia divergen, la metrica debe poder verlo (ver
    # version_reportada_vs_esperada en p6.metricas y Clasificador.model_ref).
    model_ref = clasificador.model_ref

    mediciones: list[Medicion] = []
    resultados_ventana: list[dict] = []
    scores_ventana: list[float] = []
    event_ids_ventana: list[str] = []
    ultimo_timestamp_ms = reloj()
    total = 0

    for frame in fuente:
        total += 1
        ultimo_timestamp_ms = frame.timestamp_ms

        if tiempo_real:
            time.sleep(cfg_fuente.frecuencia_ms / 1000)

        resultado_frame = procesar_frame(
            frame,
            run_id=run_id,
            source_id=fuente.source_id,
            model_ref=model_ref,
            config_ref=config_ref,
            clasificador=clasificador,
            cfg_confianza=cfg_confianza,
            motor_alertas=motor_alertas,
            capturas=capturas,
            proceso=proceso,
        )
        almacen_eventos.registrar(resultado_frame.evento)
        if resultado_frame.medicion is not None:
            mediciones.append(resultado_frame.medicion)
        if resultado_frame.alerta is not None:
            almacen_alertas.registrar(resultado_frame.alerta)

        evento = resultado_frame.evento
        if evento.status == "ok" and evento.prediction is not None:
            scores_ventana.append(evento.prediction.score)
            event_ids_ventana.append(evento.event_id)
            if len(scores_ventana) >= cfg_confianza.tamano_ventana:
                resultados_ventana.append(
                    _evaluar_y_registrar_ventana(
                        politica,
                        motor_alertas,
                        almacen_alertas,
                        scores_ventana,
                        event_ids_ventana,
                        frame.timestamp_ms,
                    )
                )
                scores_ventana, event_ids_ventana = [], []

    if scores_ventana:  # cola final: nunca se descarta en silencio, aunque no llene la ventana
        resultados_ventana.append(
            _evaluar_y_registrar_ventana(
                politica,
                motor_alertas,
                almacen_alertas,
                scores_ventana,
                event_ids_ventana,
                ultimo_timestamp_ms,
            )
        )

    if ruta_referencia is not None and politica.referencia is not None:
        guardar_referencia(ruta_referencia, politica.referencia)

    return ResultadoCorrida(
        run_id=run_id,
        total_frames=total,
        almacen_eventos=almacen_eventos,
        almacen_alertas=almacen_alertas,
        mediciones=tuple(mediciones),
        resultados_ventana=tuple(resultados_ventana),
    )


def _evaluar_y_registrar_ventana(
    politica: PoliticaConfianza,
    motor_alertas: MotorAlertas,
    almacen_alertas: AlmacenAlertas,
    scores_ventana: list[float],
    event_ids_ventana: list[str],
    timestamp_ms: float,
) -> dict:
    resultado = politica.evaluar_ventana(scores_ventana)
    alerta = motor_alertas.evaluar_ventana(resultado, event_ids_ventana, timestamp_ms)
    if alerta is not None:
        almacen_alertas.registrar(alerta)
    return {"timestamp_ms": timestamp_ms, **asdict(resultado)}
