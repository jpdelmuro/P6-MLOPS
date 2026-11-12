"""P6: portal minimo (R4.2, R5.3) -- consulta de eventos y alertas. Lee directamente de
las bases SQLite que produce cada corrida (`p6.orquestador`); nada mockeado.

Variable de entorno `P6_EVIDENCIAS_DIR` apunta a la carpeta base que contiene una
subcarpeta por `run_id` (por defecto `evidencias/escenarios`, la misma que usa
`scripts/ejecutar_corrida.py`).
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from p6.alertas import AlmacenAlertas
from p6.eventos import AlmacenEventos

RAIZ = Path(__file__).resolve().parents[3]
ZONAS = ("aceptada", "duda", "baja_confianza", "sin_puntuacion")

app = FastAPI(title="P6 - Centro de monitoreo")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _base_evidencias() -> Path:
    # Se lee en cada llamada (no en import) para que las pruebas puedan apuntar a un
    # tmp_path propio con la variable de entorno, sin reiniciar el proceso.
    return Path(os.environ.get("P6_EVIDENCIAS_DIR", str(RAIZ / "evidencias" / "escenarios")))


def listar_corridas() -> list[str]:
    base = _base_evidencias()
    if not base.is_dir():
        return []
    return sorted(p.name for p in base.iterdir() if p.is_dir())


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


@app.get("/imagenes")
def ver_imagen(ruta: str) -> FileResponse:
    """Sirve una captura vinculada a un evento/alerta -- valida que quede dentro del
    repositorio, nunca una ruta arbitraria del sistema de archivos."""
    archivo = Path(ruta)
    if not archivo.is_absolute():
        archivo = RAIZ / archivo
    try:
        archivo.resolve().relative_to(RAIZ.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="ruta fuera del repositorio") from exc
    if not archivo.exists():
        raise HTTPException(status_code=404, detail="imagen no encontrada")
    return FileResponse(archivo)
