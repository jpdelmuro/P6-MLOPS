"""P6: ClasificadorPreentrenado -- contrato de la inferencia real (R1.2)."""

from __future__ import annotations

import pytest
from PIL import Image

from p6.modelo import ClasificadorPreentrenado, ModeloError, Prediccion


@pytest.fixture(scope="module")
def clasificador():
    # Cargar los pesos preentrenados es costoso: una sola instancia para todo el modulo.
    return ClasificadorPreentrenado()


@pytest.fixture
def imagen_de_prueba(tmp_path):
    ruta = tmp_path / "prueba.jpg"
    Image.new("RGB", (224, 224), color=(120, 160, 200)).save(ruta)
    return ruta


def test_clasificar_devuelve_prediccion_dentro_del_catalogo(clasificador, imagen_de_prueba):
    prediccion = clasificador.clasificar(imagen_de_prueba)
    assert isinstance(prediccion, Prediccion)
    assert 0.0 <= prediccion.score <= 1.0
    assert prediccion.class_name == clasificador.clases[prediccion.class_id]
    assert prediccion.class_id in range(len(clasificador.clases))


def test_hay_mil_clases_de_imagenet(clasificador):
    assert len(clasificador.clases) == 1000


def test_imagen_corrupta_lanza_modelo_error(clasificador, tmp_path):
    ruta = tmp_path / "corrupta.jpg"
    ruta.write_bytes(b"esto no es una imagen valida")
    with pytest.raises(ModeloError):
        clasificador.clasificar(ruta)


def test_imagen_inexistente_lanza_modelo_error(clasificador, tmp_path):
    with pytest.raises(ModeloError):
        clasificador.clasificar(tmp_path / "no-existe.jpg")
