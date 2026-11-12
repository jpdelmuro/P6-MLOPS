"""P6: SecuenciaImagenes -- orden estable, frame_id unicos, frecuencia declarada."""

from __future__ import annotations

import pytest

from p6.config import ConfigFuente
from p6.fuente import FuenteError, SecuenciaImagenes, construir_fuente
from p6.reloj import RelojControlado


def _crear_imagenes(tmp_path, nombres):
    for nombre in nombres:
        (tmp_path / nombre).write_bytes(b"contenido-de-prueba")
    return tmp_path


def test_orden_estable_por_nombre_de_archivo(tmp_path):
    # Se crean fuera de orden alfabetico a proposito.
    _crear_imagenes(tmp_path, ["c.jpg", "a.jpg", "b.png"])
    secuencia = SecuenciaImagenes(tmp_path, 500.0, RelojControlado(0.0))
    rutas = [f.ruta.name for f in secuencia]
    assert rutas == ["a.jpg", "b.png", "c.jpg"]


def test_frame_id_unicos_y_con_source_id(tmp_path):
    _crear_imagenes(tmp_path, ["a.jpg", "b.jpg"])
    secuencia = SecuenciaImagenes(tmp_path, 500.0, RelojControlado(0.0), source_id="normal")
    frames = list(secuencia)
    assert [f.frame_id for f in frames] == ["normal_0000", "normal_0001"]
    assert len({f.frame_id for f in frames}) == len(frames)


def test_source_id_por_defecto_es_el_nombre_de_la_carpeta(tmp_path):
    carpeta = tmp_path / "baja_confianza"
    carpeta.mkdir()
    _crear_imagenes(carpeta, ["a.jpg"])
    secuencia = SecuenciaImagenes(carpeta, 500.0, RelojControlado(0.0))
    assert secuencia.source_id == "baja_confianza"


def test_frecuencia_declarada_se_respeta_con_reloj_controlado(tmp_path):
    _crear_imagenes(tmp_path, ["a.jpg", "b.jpg", "c.jpg"])
    reloj = RelojControlado(1000.0)
    secuencia = SecuenciaImagenes(tmp_path, 500.0, reloj)
    # El reloj no avanza entre frames: el timestamp es sintetico (origen + indice*frecuencia),
    # no depende de que pase tiempo real.
    marcas = [f.timestamp_ms for f in secuencia]
    assert marcas == [1000.0, 1500.0, 2000.0]


def test_ignora_archivos_que_no_son_imagen(tmp_path):
    _crear_imagenes(tmp_path, ["a.jpg", "notas.txt"])
    secuencia = SecuenciaImagenes(tmp_path, 500.0, RelojControlado(0.0))
    assert len(secuencia) == 1


def test_carpeta_inexistente_lanza_fuente_error(tmp_path):
    with pytest.raises(FuenteError):
        SecuenciaImagenes(tmp_path / "no-existe", 500.0, RelojControlado(0.0))


def test_carpeta_vacia_lanza_fuente_error(tmp_path):
    with pytest.raises(FuenteError):
        SecuenciaImagenes(tmp_path, 500.0, RelojControlado(0.0))


def test_construir_fuente_desde_config(tmp_path):
    _crear_imagenes(tmp_path, ["a.jpg"])
    cfg = ConfigFuente(carpeta=str(tmp_path), frecuencia_ms=250.0)
    secuencia = construir_fuente(cfg, RelojControlado(0.0))
    assert len(secuencia) == 1
