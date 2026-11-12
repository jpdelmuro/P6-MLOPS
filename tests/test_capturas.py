"""P6: PoliticaCapturas -- captura selectiva vinculada a eventos (R4.3)."""

from __future__ import annotations

import pytest

from p6.capturas import PoliticaCapturas


def test_alerta_siempre_se_captura(tmp_path):
    politica = PoliticaCapturas(tmp_path, cada_n_normal=10)
    captura, razon = politica.debe_capturar(zona="aceptada", alerta_disparada=True)
    assert captura is True and razon == "alerta"


def test_baja_confianza_siempre_se_captura(tmp_path):
    politica = PoliticaCapturas(tmp_path, cada_n_normal=10)
    captura, razon = politica.debe_capturar(zona="baja_confianza", alerta_disparada=False)
    assert captura is True and razon == "baja_confianza"


def test_zona_aceptada_solo_se_captura_cada_n(tmp_path):
    politica = PoliticaCapturas(tmp_path, cada_n_normal=3)
    resultados = [
        politica.debe_capturar(zona="aceptada", alerta_disparada=False)[0] for _ in range(6)
    ]
    assert resultados == [False, False, True, False, False, True]


def test_cada_n_normal_invalido_lanza_value_error(tmp_path):
    with pytest.raises(ValueError):
        PoliticaCapturas(tmp_path, cada_n_normal=0)


def test_capturar_copia_el_archivo_sin_borrar_el_original(tmp_path):
    origen = tmp_path / "origen"
    origen.mkdir()
    imagen = origen / "frame.jpg"
    imagen.write_bytes(b"contenido-de-prueba")

    destino = tmp_path / "capturas"
    politica = PoliticaCapturas(destino)
    referencia = politica.capturar("evt-001", imagen)

    assert imagen.exists()  # el original nunca se borra ni se mueve
    from pathlib import Path

    assert Path(referencia).exists()
    assert Path(referencia).read_bytes() == b"contenido-de-prueba"
    assert Path(referencia).name == "evt-001.jpg"


def test_capturar_dos_veces_el_mismo_event_id_no_sobreescribe(tmp_path):
    origen = tmp_path / "origen"
    origen.mkdir()
    imagen = origen / "frame.jpg"
    imagen.write_bytes(b"version-1")

    politica = PoliticaCapturas(tmp_path / "capturas")
    referencia = politica.capturar("evt-001", imagen)

    imagen.write_bytes(b"version-2")  # si se repitiera la captura, no debe pisar la anterior
    politica.capturar("evt-001", imagen)

    from pathlib import Path

    assert Path(referencia).read_bytes() == b"version-1"
