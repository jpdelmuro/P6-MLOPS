"""P6: FuenteConReconexion (extra S) -- interrupcion real de la fuente y reconexion sin
reemitir ni saltar frames."""

from __future__ import annotations

import pytest

from p6.fuente import FuenteError
from p6.reconexion import FuenteConReconexion
from p6.reloj import RelojControlado


def _crear_imagenes(carpeta, nombres):
    for nombre in nombres:
        (carpeta / nombre).write_bytes(b"contenido-de-prueba")
    return carpeta


def test_entrega_todos_los_frames_sin_interrupcion(tmp_path):
    _crear_imagenes(tmp_path, ["a.jpg", "b.jpg", "c.jpg"])
    fuente = FuenteConReconexion(tmp_path, 500.0, RelojControlado(0.0), source_id="s")
    frames = list(fuente)
    assert [f.frame_id for f in frames] == ["s_0000", "s_0001", "s_0002"]
    assert fuente.siguiente_indice == 3


def test_interrupcion_real_levanta_fuenteerror_sin_perder_el_cursor(tmp_path):
    carpeta = tmp_path / "stream"
    carpeta.mkdir()
    _crear_imagenes(carpeta, ["a.jpg", "b.jpg", "c.jpg", "d.jpg"])
    fuente = FuenteConReconexion(carpeta, 500.0, RelojControlado(0.0), source_id="s")

    vistos = []
    with pytest.raises(FuenteError):
        for i, frame in enumerate(fuente):
            vistos.append(frame.frame_id)
            if i == 1:  # tras el segundo frame, la carpeta deja de estar disponible de verdad
                carpeta.rename(tmp_path / "stream-caida")

    assert vistos == ["s_0000", "s_0001"]
    assert fuente.siguiente_indice == 2  # el cursor no avanzo sobre el frame que fallo


def test_reconectar_y_reanudar_entrega_el_resto_sin_duplicar_ni_saltar(tmp_path):
    carpeta = tmp_path / "stream"
    carpeta.mkdir()
    _crear_imagenes(carpeta, ["a.jpg", "b.jpg", "c.jpg", "d.jpg"])
    fuente = FuenteConReconexion(carpeta, 500.0, RelojControlado(0.0), source_id="s")

    vistos = []
    with pytest.raises(FuenteError):
        for i, frame in enumerate(fuente):
            vistos.append(frame.frame_id)
            if i == 1:
                carpeta.rename(tmp_path / "stream-caida")

    assert fuente.reconectar() is False  # todavia caida

    (tmp_path / "stream-caida").rename(carpeta)  # se restaura el acceso real
    assert fuente.reconectar() is True

    restantes = [f.frame_id for f in fuente]  # nueva llamada a __iter__, mismo cursor interno
    assert restantes == ["s_0002", "s_0003"]  # continua, no repite s_0000/s_0001
    assert vistos + restantes == ["s_0000", "s_0001", "s_0002", "s_0003"]


def test_timestamps_de_los_frames_restantes_no_cambian_tras_reconectar(tmp_path):
    # La secuencia se calcula una sola vez al construir -- reconectar no reordena ni
    # reasigna timestamps, para que la corrida siga siendo reproducible.
    carpeta = tmp_path / "stream"
    carpeta.mkdir()
    _crear_imagenes(carpeta, ["a.jpg", "b.jpg", "c.jpg"])
    fuente = FuenteConReconexion(carpeta, 500.0, RelojControlado(1000.0), source_id="s")

    with pytest.raises(FuenteError):
        for i, _frame in enumerate(fuente):
            if i == 0:
                carpeta.rename(tmp_path / "caida")
    (tmp_path / "caida").rename(carpeta)
    assert fuente.reconectar() is True

    restantes = list(fuente)
    assert [f.timestamp_ms for f in restantes] == [1500.0, 2000.0]


def test_proximo_frame_y_ultimo_frame_entregado(tmp_path):
    carpeta = tmp_path / "stream"
    carpeta.mkdir()
    _crear_imagenes(carpeta, ["a.jpg", "b.jpg", "c.jpg"])
    fuente = FuenteConReconexion(carpeta, 500.0, RelojControlado(0.0), source_id="s")

    assert fuente.ultimo_frame_entregado is None  # nada entregado todavia
    assert fuente.proximo_frame.frame_id == "s_0000"

    iterador = iter(fuente)
    next(iterador)
    assert fuente.ultimo_frame_entregado.frame_id == "s_0000"
    assert fuente.proximo_frame.frame_id == "s_0001"

    next(iterador)
    next(iterador)
    assert fuente.ultimo_frame_entregado.frame_id == "s_0002"
    assert fuente.proximo_frame is None  # ya se agoto
