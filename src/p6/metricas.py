"""P6: metricas base G1-G7 (R2) -- una funcion por grupo aplicable, cada una calculada
desde observaciones primarias (eventos, alertas o mediciones tecnicas) para que se
puedan recalcular desde `evidencias/metricas/*.jsonl` (M5).

Los 7 grupos aplican en este proyecto: hay procesamiento de inferencias (G1), una
fuente de stream (G2), un proceso con uso de recursos medible (G3), salidas del modelo
(G4), eventos/imagenes (G5), una fuente local con modelo versionado (G6 -- aplica aunque
sea una sola fuente, segun la guia) y alertas (G7).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any

from p6.eventos import CAMPOS_EVENTO_OBLIGATORIOS


@dataclass(frozen=True)
class MetricaBase:
    grupo: str
    nombre: str
    definicion: str
    unidad: str


#: M1 (definicion) de cada metrica base elegida -- texto reusado en evidencias/indice.md
#: y en el README, para no mantenerlo duplicado en dos lugares.
CATALOGO_BASE: tuple[MetricaBase, ...] = (
    MetricaBase(
        "G1",
        "tiempo_inferencia_p50",
        "Percentil 50 (mediana) del tiempo de inferencia del modelo por ventana, medido "
        "con time.perf_counter alrededor de ClasificadorPreentrenado.inferir (nunca de "
        "cargar_y_preprocesar, que hace la lectura/decodificacion y el preprocesamiento "
        "por separado). Poblacion: un frame con inferencia exitosa en la ventana; los "
        "frames con fallo de lectura no producen medicion (no hubo inferencia).",
        "milisegundos",
    ),
    MetricaBase(
        "G2",
        "antiguedad_ultimo_frame",
        "Diferencia entre el reloj de la corrida y el timestamp del ultimo frame procesado. "
        "Poblacion: todos los frames de la fuente activa.",
        "milisegundos",
    ),
    MetricaBase(
        "G3",
        "uso_recursos_promedio",
        "Promedio de RAM (MB) y CPU (%) del proceso durante la ventana, muestreado con "
        "psutil.Process().cpu_percent(interval=None) en cada frame con inferencia exitosa "
        "(la primera lectura de cpu_percent se descarta antes del primer frame -- ver "
        "p6.orquestador.iniciar_medicion_recursos -- porque psutil la devuelve en 0.0 sin "
        "significado). El % de CPU puede superar 100 si el proceso usa mas de un nucleo; "
        "no es un error.",
        "MB y % de CPU (puede superar 100% con multiples nucleos)",
    ),
    MetricaBase(
        "G4",
        "proporcion_baja_confianza",
        "Imagenes con score < umbral_inferior / imagenes con inferencia valida y puntuacion "
        "elegible en la ventana (misma formula y calculo que R3, ver p6.confianza).",
        "proporcion [0, 1]",
    ),
    MetricaBase(
        "G5",
        "cobertura_trazabilidad",
        "Proporcion de eventos persistidos con todos los campos de identidad completos y "
        "coherentes con su estado (ok con prediction, error sin ella). Poblacion: eventos "
        "de la corrida.",
        "proporcion [0, 1]",
    ),
    MetricaBase(
        "G6",
        "version_reportada_vs_esperada",
        "Compara el model_ref reportado por los eventos de la corrida contra el configurado "
        "en config/modelo.yaml. Aplica con una sola fuente local, segun la guia.",
        "coincide / no coincide",
    ),
    MetricaBase(
        "G7",
        "alertas_activas_en_ventana",
        "Cantidad de alertas con timestamp dentro de una ventana [inicio_ms, fin_ms]. En este "
        "alcance las alertas no tienen ciclo de cierre explicito (no se exige); 'activa en la "
        "ventana' significa generada dentro de ella.",
        "conteo",
    ),
)


@dataclass(frozen=True)
class Medicion:
    """Una muestra tecnica por frame procesado -- separada de `Evento` porque es
    telemetria de ejecucion, no parte del contrato de negocio del evento."""

    frame_id: str
    timestamp_ms: float
    duracion_inferencia_ms: float
    cpu_percent: float
    ram_mb: float


# --- G1: tiempo de inferencia ------------------------------------------------


def tiempo_inferencia_p50(mediciones: list[Medicion]) -> float | None:
    duraciones = [m.duracion_inferencia_ms for m in mediciones]
    if not duraciones:
        return None
    return statistics.median(duraciones)


# --- G2: antiguedad del ultimo frame -----------------------------------------


def antiguedad_ultimo_frame(timestamps_ms: list[float], ahora_ms: float) -> float | None:
    if not timestamps_ms:
        return None
    return ahora_ms - max(timestamps_ms)


# --- G3: uso de recursos ------------------------------------------------------


@dataclass(frozen=True)
class UsoRecursos:
    ram_mb_promedio: float
    cpu_percent_promedio: float
    muestras: int


def uso_recursos_promedio(mediciones: list[Medicion]) -> UsoRecursos | None:
    if not mediciones:
        return None
    return UsoRecursos(
        ram_mb_promedio=statistics.fmean(m.ram_mb for m in mediciones),
        cpu_percent_promedio=statistics.fmean(m.cpu_percent for m in mediciones),
        muestras=len(mediciones),
    )


# --- G4: proporcion de baja confianza -----------------------------------------
#
# Reutiliza deliberadamente p6.confianza.tasa_baja_confianza: es la misma formula
# declarada en la guia y el mismo calculo que sostiene R3; aqui se reporta como
# metrica de monitoreo de G4 (un mismo artefacto respalda dos criterios distintos,
# lo cual la rubrica permite explicitamente).


# --- Extra M: distribucion de confianza (histograma) --------------------------
#
# Metrica adicional de G4, distinta de la metrica base (proporcion_baja_confianza):
# un histograma de puntuaciones, no un escalar. No confunde el histograma con
# probabilidad de acierto -- es la frecuencia de scores crudos, sin evaluacion de
# calidad predictiva.


@dataclass(frozen=True)
class DistribucionConfianza:
    bins: tuple[tuple[float, float], ...]
    conteos: tuple[int, ...]
    sin_puntuacion: int
    total: int


def distribucion_confianza(
    scores: list[float | None], n_bins: int = 5
) -> DistribucionConfianza | None:
    """Poblacion: todas las observaciones de la ventana/corrida. Exclusiones: los
    `None` (sin puntuacion, por ejemplo por fallo de inferencia) se cuentan aparte
    en `sin_puntuacion` y no entran en ningun bin -- nunca se tratan como score 0."""
    if not scores:
        return None
    ancho = 1 / n_bins
    bins = tuple((round(i * ancho, 4), round((i + 1) * ancho, 4)) for i in range(n_bins))
    conteos = [0] * n_bins
    sin_puntuacion = 0
    for s in scores:
        if s is None:
            sin_puntuacion += 1
            continue
        indice = min(int(s / ancho), n_bins - 1)  # score == 1.0 cae en el ultimo bin
        conteos[indice] += 1
    return DistribucionConfianza(
        bins=bins, conteos=tuple(conteos), sin_puntuacion=sin_puntuacion, total=len(scores)
    )


# --- G5: cobertura de trazabilidad --------------------------------------------


def _evento_dict_completo(evento: dict[str, Any]) -> bool:
    if any(not evento.get(campo) for campo in CAMPOS_EVENTO_OBLIGATORIOS):
        return False
    zona = evento["confidence_zone"]
    if evento["status"] == "ok":
        return evento.get("prediction") is not None and zona != "sin_puntuacion"
    return evento.get("prediction") is None and zona == "sin_puntuacion"


def cobertura_trazabilidad(eventos: list[dict[str, Any]]) -> float | None:
    if not eventos:
        return None
    completos = sum(1 for e in eventos if _evento_dict_completo(e))
    return completos / len(eventos)


# --- G6: version reportada vs esperada ----------------------------------------


@dataclass(frozen=True)
class VersionReportada:
    esperado: str
    reportados: tuple[str, ...]
    coincide: bool


def version_reportada_vs_esperada(
    eventos: list[dict[str, Any]], model_ref_esperado: str
) -> VersionReportada:
    reportados = tuple(sorted({e["model_ref"] for e in eventos})) if eventos else ()
    coincide = reportados == (model_ref_esperado,)
    return VersionReportada(esperado=model_ref_esperado, reportados=reportados, coincide=coincide)


# --- G7: alertas activas en ventana -------------------------------------------


def alertas_activas_en_ventana(
    alertas: list[dict[str, Any]], inicio_ms: float, fin_ms: float
) -> int:
    if inicio_ms > fin_ms:
        raise ValueError("inicio_ms no puede ser mayor que fin_ms")
    return sum(1 for a in alertas if inicio_ms <= a["timestamp_ms"] <= fin_ms)
