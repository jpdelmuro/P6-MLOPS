"""P6: portal minimo (R4.2, R5.3) -- consulta de eventos y alertas. Lee directamente de
las bases SQLite que produce cada corrida (`p6.orquestador`); nada mockeado.

Variable de entorno `P6_EVIDENCIAS_DIR` apunta a la carpeta base que contiene una
subcarpeta por `run_id` (por defecto `evidencias/escenarios`, la misma que usa
`scripts/ejecutar_corrida.py`).
"""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from p6.alertas import AlmacenAlertas
from p6.eventos import AlmacenEventos
from p6.fuente import EXTENSIONES_VALIDAS
from p6.metricas import (
    Medicion,
    antiguedad_ultimo_frame,
    distribucion_confianza,
    tiempo_inferencia_p50,
    uso_recursos_promedio,
)

RAIZ = Path(__file__).resolve().parents[3]
ZONAS = ("aceptada", "duda", "baja_confianza", "sin_puntuacion")

app = FastAPI(title="P6 - Centro de monitoreo")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _base_evidencias() -> Path:
    # Se lee en cada llamada (no en import) para que las pruebas puedan apuntar a un
    # tmp_path propio con la variable de entorno, sin reiniciar el proceso.
    return Path(os.environ.get("P6_EVIDENCIAS_DIR", str(RAIZ / "evidencias" / "escenarios")))


def listar_corridas() -> list[str]:
    """Solo carpetas que son corridas de verdad (tienen `eventos-<run_id>.db`) -- la
    carpeta de evidencias tambien contiene subcarpetas de documentacion
    (`normal/`, `baja-confianza/`) que no lo son y antes aparecian vacias aqui."""
    base = _base_evidencias()
    if not base.is_dir():
        return []
    return sorted(
        p.name for p in base.iterdir() if p.is_dir() and (p / f"eventos-{p.name}.db").exists()
    )


def _rutas_db(run_id: str) -> tuple[Path, Path]:
    carpeta = _base_evidencias() / run_id
    return carpeta / f"eventos-{run_id}.db", carpeta / f"alertas-{run_id}.db"


def _run_id_por_defecto() -> str | None:
    corridas = listar_corridas()
    return corridas[-1] if corridas else None


@app.get("/", response_class=HTMLResponse)
def inicio(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "inicio.html",
        {"titulo": "P6 - Centro de monitoreo", "corridas": listar_corridas()},
    )


@app.get("/eventos", response_class=HTMLResponse)
def ver_eventos(
    request: Request, run_id: str | None = None, zona: str | None = None
) -> HTMLResponse:
    run_id = run_id or _run_id_por_defecto()
    eventos: list[dict] = []
    ruta_eventos, _ = _rutas_db(run_id) if run_id else (None, None)
    if ruta_eventos is not None and ruta_eventos.exists():
        almacen = AlmacenEventos(ruta_eventos)
        eventos = almacen.listar(run_id=run_id, zona=zona or None)
        almacen.cerrar()
    return templates.TemplateResponse(
        request,
        "eventos.html",
        {
            "titulo": "Eventos",
            "eventos": eventos,
            "run_id": run_id,
            "zona": zona or "",
            "zonas": ZONAS,
            "corridas": listar_corridas(),
        },
    )


@app.get("/alertas", response_class=HTMLResponse)
def ver_alertas(request: Request, run_id: str | None = None) -> HTMLResponse:
    run_id = run_id or _run_id_por_defecto()
    alertas: list[dict] = []
    eventos_por_id: dict[str, dict] = {}
    if run_id:
        ruta_eventos, ruta_alertas = _rutas_db(run_id)
        if ruta_alertas.exists():
            almacen_alertas = AlmacenAlertas(ruta_alertas)
            alertas = almacen_alertas.listar()
            almacen_alertas.cerrar()
        if ruta_eventos.exists() and alertas:
            almacen_eventos = AlmacenEventos(ruta_eventos)
            for alerta in alertas:
                for event_id in alerta["event_ids"]:
                    evento = almacen_eventos.obtener(event_id)
                    if evento:
                        eventos_por_id[event_id] = evento
            almacen_eventos.cerrar()
    return templates.TemplateResponse(
        request,
        "alertas.html",
        {
            "titulo": "Alertas",
            "alertas": alertas,
            "eventos_por_id": eventos_por_id,
            "run_id": run_id,
            "corridas": listar_corridas(),
        },
    )


def _cargar_mediciones(run_id: str) -> list[Medicion]:
    ruta = _base_evidencias() / run_id / "mediciones.jsonl"
    if not ruta.exists():
        return []
    with ruta.open() as archivo:
        return [Medicion(**json.loads(linea)) for linea in archivo if linea.strip()]


def _g2_antiguedad_ms(eventos: list[dict]) -> float | None:
    """G2 con tiempo real, no el timestamp sintetico del stream (R4.1/G2): usa
    `fecha_utc` (hora de pared real en que se proceso cada evento) contra el reloj de
    pared actual -- una "antiguedad" genuina, no un valor fijo por construccion."""
    fechas = [e["fecha_utc"] for e in eventos if e.get("fecha_utc")]
    if not fechas:
        return None
    timestamps_epoch_ms = [datetime.fromisoformat(f).timestamp() * 1000 for f in fechas]
    ahora_ms = datetime.now(UTC).timestamp() * 1000
    return antiguedad_ultimo_frame(timestamps_epoch_ms, ahora_ms)


@app.get("/dashboard", response_class=HTMLResponse)
def ver_dashboard(request: Request, run_id: str | None = None) -> HTMLResponse:
    """Extra F: vista agregada de una corrida -- conteo por zona, tiempo de inferencia
    (G1), uso de recursos (G3), distribucion de confianza (extra M) y alertas por regla.
    Parametrizada por `run_id`; maneja de forma explicita la corrida sin datos y la
    ausencia de `mediciones.jsonl` (no todas las corridas antiguas lo tienen)."""
    run_id = run_id or _run_id_por_defecto()
    contexto: dict = {
        "titulo": "Dashboard",
        "run_id": run_id,
        "corridas": listar_corridas(),
        "hay_datos": False,
    }
    if run_id is None:
        return templates.TemplateResponse(request, "dashboard.html", contexto)

    ruta_eventos, ruta_alertas = _rutas_db(run_id)
    if not ruta_eventos.exists():
        return templates.TemplateResponse(request, "dashboard.html", contexto)

    almacen_eventos = AlmacenEventos(ruta_eventos)
    eventos = almacen_eventos.listar(run_id=run_id)
    almacen_eventos.cerrar()
    if not eventos:
        return templates.TemplateResponse(request, "dashboard.html", contexto)

    alertas: list[dict] = []
    if ruta_alertas.exists():
        almacen_alertas = AlmacenAlertas(ruta_alertas)
        alertas = almacen_alertas.listar()
        almacen_alertas.cerrar()

    conteo_zonas = Counter(e["confidence_zone"] for e in eventos)
    scores = [e["prediction"]["score"] if e.get("prediction") else None for e in eventos]
    histograma = distribucion_confianza(scores)
    conteo_alertas = Counter(a["rule_id"] for a in alertas)

    mediciones = _cargar_mediciones(run_id)
    g1_p50 = tiempo_inferencia_p50(mediciones) if mediciones else None
    g3_uso = uso_recursos_promedio(mediciones) if mediciones else None
    g2_antiguedad = _g2_antiguedad_ms(eventos)

    contexto.update(
        {
            "hay_datos": True,
            "total_eventos": len(eventos),
            "conteo_zonas": dict(conteo_zonas),
            "histograma": histograma,
            "g1_p50": g1_p50,
            "g2_antiguedad": g2_antiguedad,
            "g3_uso": g3_uso,
            "total_alertas": len(alertas),
            "conteo_alertas": dict(conteo_alertas),
        }
    )
    return templates.TemplateResponse(request, "dashboard.html", contexto)


@app.get("/imagenes")
def ver_imagen(ruta: str) -> FileResponse:
    """Sirve una captura vinculada a un evento/alerta -- valida que quede dentro del
    repositorio (nunca una ruta arbitraria del sistema de archivos) y que sea una
    imagen de verdad (nunca un archivo de codigo o config del propio repo, aunque la
    ruta este dentro de RAIZ -- ej. README.md)."""
    archivo = Path(ruta)
    if not archivo.is_absolute():
        archivo = RAIZ / archivo
    try:
        archivo.resolve().relative_to(RAIZ.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="ruta fuera del repositorio") from exc
    if archivo.suffix.lower() not in EXTENSIONES_VALIDAS:
        raise HTTPException(status_code=403, detail="solo se sirven imagenes")
    if not archivo.exists():
        raise HTTPException(status_code=404, detail="imagen no encontrada")
    return FileResponse(archivo)
