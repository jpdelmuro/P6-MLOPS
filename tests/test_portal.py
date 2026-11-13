"""P6: portal -- consulta de eventos y alertas, vinculadas a su imagen (R4.2, R5.3)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from p6.alertas import Alerta, AlmacenAlertas
from p6.eventos import AlmacenEventos, Evento
from p6.modelo import Prediccion
from p6.portal.app import RAIZ, app


def _preparar_corrida(tmp_path, monkeypatch, run_id="run-1"):
    base = tmp_path / "escenarios"
    carpeta = base / run_id
    carpeta.mkdir(parents=True)

    # La ruta de la imagen debe quedar DENTRO de RAIZ para que /imagenes la acepte
    # (valida que la ruta no se salga del repositorio) -- se usa el scratch del propio
    # repo y se borra despues con monkeypatch de limpieza implicita de tmp_path.
    carpeta_imagenes = RAIZ / "evidencias" / "escenarios" / f"_test_{run_id}"
    carpeta_imagenes.mkdir(parents=True, exist_ok=True)
    imagen = carpeta_imagenes / "evt-1.jpg"
    imagen.write_bytes(b"contenido-de-prueba")

    almacen_eventos = AlmacenEventos(carpeta / f"eventos-{run_id}.db")
    almacen_eventos.registrar(
        Evento(
            event_id="evt-1",
            run_id=run_id,
            frame_id="normal_0000",
            timestamp_ms=1000.0,
            source_id="normal",
            task="classification",
            model_ref="torchvision.models.resnet18",
            status="ok",
            prediction=Prediccion(class_id=1, class_name="goldfish", score=0.30),
            confidence_zone="baja_confianza",
            config_ref="config-v1",
            image_ref=str(imagen),
        )
    )
    almacen_eventos.registrar(
        Evento(
            event_id="evt-2",
            run_id=run_id,
            frame_id="normal_0001",
            timestamp_ms=1500.0,
            source_id="normal",
            task="classification",
            model_ref="torchvision.models.resnet18",
            status="ok",
            prediction=Prediccion(class_id=2, class_name="tiger shark", score=0.95),
            confidence_zone="aceptada",
            config_ref="config-v1",
            image_ref=None,
        )
    )
    almacen_eventos.cerrar()

    almacen_alertas = AlmacenAlertas(carpeta / f"alertas-{run_id}.db")
    almacen_alertas.registrar(
        Alerta(
            alert_id="alert-1",
            rule_id="baja-confianza-v1",
            timestamp_ms=1000.0,
            severity="warning",
            event_ids=("evt-1",),
            config_ref="config-v1",
            reason="Se cumplio la condicion configurada de baja confianza.",
            suggested_action="Revisar captura",
        )
    )
    almacen_alertas.cerrar()

    monkeypatch.setenv("P6_EVIDENCIAS_DIR", str(base))
    return carpeta_imagenes, imagen


def test_inicio_lista_las_corridas_disponibles(tmp_path, monkeypatch):
    _preparar_corrida(tmp_path, monkeypatch)
    cliente = TestClient(app)
    respuesta = cliente.get("/")
    assert respuesta.status_code == 200
    assert "run-1" in respuesta.text


def test_eventos_sin_filtro_lista_todos(tmp_path, monkeypatch):
    carpeta_imagenes, _ = _preparar_corrida(tmp_path, monkeypatch)
    cliente = TestClient(app)
    respuesta = cliente.get("/eventos", params={"run_id": "run-1"})
    assert respuesta.status_code == 200
    assert "evt-1" in respuesta.text and "evt-2" in respuesta.text

    import shutil

    shutil.rmtree(carpeta_imagenes)


def test_eventos_filtra_por_zona(tmp_path, monkeypatch):
    carpeta_imagenes, _ = _preparar_corrida(tmp_path, monkeypatch)
    cliente = TestClient(app)
    respuesta = cliente.get("/eventos", params={"run_id": "run-1", "zona": "baja_confianza"})
    assert "evt-1" in respuesta.text and "evt-2" not in respuesta.text

    import shutil

    shutil.rmtree(carpeta_imagenes)


def test_alertas_muestra_regla_motivo_y_enlace_a_la_imagen(tmp_path, monkeypatch):
    carpeta_imagenes, imagen = _preparar_corrida(tmp_path, monkeypatch)
    cliente = TestClient(app)
    respuesta = cliente.get("/alertas", params={"run_id": "run-1"})
    assert respuesta.status_code == 200
    assert "baja-confianza-v1" in respuesta.text
    assert "Revisar captura" in respuesta.text
    assert str(imagen) in respuesta.text  # el enlace a /imagenes?ruta=... lleva la ruta real

    import shutil

    shutil.rmtree(carpeta_imagenes)


def test_imagenes_sirve_el_archivo_vinculado(tmp_path, monkeypatch):
    carpeta_imagenes, imagen = _preparar_corrida(tmp_path, monkeypatch)
    cliente = TestClient(app)
    respuesta = cliente.get("/imagenes", params={"ruta": str(imagen)})
    assert respuesta.status_code == 200
    assert respuesta.content == b"contenido-de-prueba"

    import shutil

    shutil.rmtree(carpeta_imagenes)


def test_imagenes_rechaza_ruta_fuera_del_repositorio(tmp_path, monkeypatch):
    _preparar_corrida(tmp_path, monkeypatch)
    cliente = TestClient(app)
    respuesta = cliente.get("/imagenes", params={"ruta": "/etc/passwd"})
    assert respuesta.status_code == 403


def test_imagenes_404_si_no_existe(tmp_path, monkeypatch):
    carpeta_imagenes, _ = _preparar_corrida(tmp_path, monkeypatch)
    cliente = TestClient(app)
    respuesta = cliente.get("/imagenes", params={"ruta": "evidencias/escenarios/no-existe/x.jpg"})
    assert respuesta.status_code == 404

    import shutil

    shutil.rmtree(carpeta_imagenes)


def test_sin_corridas_las_vistas_no_fallan(tmp_path, monkeypatch):
    monkeypatch.setenv("P6_EVIDENCIAS_DIR", str(tmp_path / "vacio"))
    cliente = TestClient(app)
    assert cliente.get("/").status_code == 200
    assert cliente.get("/eventos").status_code == 200
    assert cliente.get("/alertas").status_code == 200
    respuesta = cliente.get("/dashboard")
    assert respuesta.status_code == 200
    assert "No hay ninguna corrida disponible" in respuesta.text


def test_dashboard_muestra_zonas_histograma_y_alertas(tmp_path, monkeypatch):
    carpeta_imagenes, _ = _preparar_corrida(tmp_path, monkeypatch)
    cliente = TestClient(app)
    respuesta = cliente.get("/dashboard", params={"run_id": "run-1"})
    assert respuesta.status_code == 200
    assert ">2<" in respuesta.text  # total_eventos
    assert "baja-confianza-v1" in respuesta.text

    import shutil

    shutil.rmtree(carpeta_imagenes)


def test_dashboard_corrida_sin_eventos_no_falla(tmp_path, monkeypatch):
    base = tmp_path / "escenarios"
    (base / "run-vacio").mkdir(parents=True)
    monkeypatch.setenv("P6_EVIDENCIAS_DIR", str(base))
    cliente = TestClient(app)
    respuesta = cliente.get("/dashboard", params={"run_id": "run-vacio"})
    assert respuesta.status_code == 200
    assert "no hay eventos registrados" in respuesta.text.lower()


def test_dashboard_sin_mediciones_reporta_sin_datos_en_g1_g3(tmp_path, monkeypatch):
    carpeta_imagenes, _ = _preparar_corrida(tmp_path, monkeypatch)
    cliente = TestClient(app)
    respuesta = cliente.get("/dashboard", params={"run_id": "run-1"})
    assert respuesta.status_code == 200
    assert "sin datos" in respuesta.text.lower()

    import shutil

    shutil.rmtree(carpeta_imagenes)
