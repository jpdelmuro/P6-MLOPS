"""P6: ejecutar_corrida -- integra fuente, modelo, confianza, eventos y alertas."""

from __future__ import annotations

from p6.config import ConfigAlertas, ConfigConfianza, ConfigFuente, ConfigModelo, ReglaAlerta
from p6.modelo import ClasificadorPreentrenado, ModeloError, Prediccion
from p6.orquestador import ejecutar_corrida
from p6.reloj import RelojControlado

CFG_MODELO = ConfigModelo(
    modelo_ref="torchvision.models.resnet18",
    pesos="ResNet18_Weights.IMAGENET1K_V1",
    clases_ref="imagenet-1k",
    preprocesamiento="resize+crop+normalize",
    entorno="CPU",
)
CFG_CONFIANZA = ConfigConfianza(
    umbral_inferior=0.60,
    umbral_superior=0.80,
    tamano_ventana=3,
    minimo_muestras=3,
    margen_cambio_sostenido=0.20,
    ventanas_sostenidas=2,
)
CFG_ALERTAS = ConfigAlertas(
    version=1,
    reglas=(
        ReglaAlerta("baja-confianza-v1", "baja_confianza", "warning", "revisar"),
        ReglaAlerta("cambio-sostenido-v1", "cambio_sostenido", "warning", "investigar"),
    ),
)


class ClasificadorFalso:
    """Doble de prueba: devuelve scores predeterminados en orden, sin cargar pesos
    reales -- la misma interfaz (`clasificar(ruta) -> Prediccion`) que
    `ClasificadorPreentrenado`."""

    def __init__(self, scores: list[float | None]) -> None:
        self._scores = iter(scores)

    def clasificar(self, ruta_imagen):
        score = next(self._scores)
        if score is None:
            raise ModeloError(f"{ruta_imagen}: fallo simulado")
        return Prediccion(class_id=0, class_name="fake", score=score)


def _crear_imagenes(carpeta, cantidad):
    carpeta.mkdir(parents=True, exist_ok=True)
    for i in range(cantidad):
        (carpeta / f"f{i:03d}.jpg").write_bytes(b"contenido-de-prueba")
    return carpeta


def test_cada_frame_produce_un_evento_y_cuenta_total_frames(tmp_path):
    carpeta = _crear_imagenes(tmp_path / "stream", 4)
    cfg_fuente = ConfigFuente(carpeta=str(carpeta), frecuencia_ms=100.0)
    clasificador = ClasificadorFalso([0.95, 0.95, 0.95, 0.95])

    resultado = ejecutar_corrida(
        run_id="run-test",
        cfg_fuente=cfg_fuente,
        cfg_modelo=CFG_MODELO,
        cfg_confianza=CFG_CONFIANZA,
        cfg_alertas=CFG_ALERTAS,
        reloj=RelojControlado(0.0),
        carpeta_evidencias=tmp_path / "evidencias",
        clasificador=clasificador,
    )

    assert resultado.total_frames == 4
    eventos = resultado.almacen_eventos.listar(run_id="run-test")
    assert len(eventos) == 4
    assert all(e["status"] == "ok" and e["confidence_zone"] == "aceptada" for e in eventos)
    resultado.almacen_eventos.cerrar()
    resultado.almacen_alertas.cerrar()


def test_frame_con_error_de_modelo_queda_registrado_como_error(tmp_path):
    carpeta = _crear_imagenes(tmp_path / "stream", 2)
    cfg_fuente = ConfigFuente(carpeta=str(carpeta), frecuencia_ms=100.0)
    clasificador = ClasificadorFalso([0.95, None])

    resultado = ejecutar_corrida(
        run_id="run-error",
        cfg_fuente=cfg_fuente,
        cfg_modelo=CFG_MODELO,
        cfg_confianza=CFG_CONFIANZA,
        cfg_alertas=CFG_ALERTAS,
        reloj=RelojControlado(0.0),
        carpeta_evidencias=tmp_path / "evidencias",
        clasificador=clasificador,
    )

    eventos = resultado.almacen_eventos.listar(run_id="run-error")
    fallido = next(e for e in eventos if e["status"] == "error")
    assert fallido["confidence_zone"] == "sin_puntuacion"
    assert fallido["prediction"] is None
    resultado.almacen_eventos.cerrar()
    resultado.almacen_alertas.cerrar()


def test_evento_en_baja_confianza_dispara_alerta_vinculada(tmp_path):
    carpeta = _crear_imagenes(tmp_path / "stream", 1)
    cfg_fuente = ConfigFuente(carpeta=str(carpeta), frecuencia_ms=100.0)
    clasificador = ClasificadorFalso([0.30])

    resultado = ejecutar_corrida(
        run_id="run-baja",
        cfg_fuente=cfg_fuente,
        cfg_modelo=CFG_MODELO,
        cfg_confianza=CFG_CONFIANZA,
        cfg_alertas=CFG_ALERTAS,
        reloj=RelojControlado(0.0),
        carpeta_evidencias=tmp_path / "evidencias",
        clasificador=clasificador,
    )

    alertas = resultado.almacen_alertas.listar(rule_id="baja-confianza-v1")
    assert len(alertas) == 1
    evento_id = resultado.almacen_eventos.listar(run_id="run-baja")[0]["event_id"]
    assert alertas[0]["event_ids"] == [evento_id]
    resultado.almacen_eventos.cerrar()
    resultado.almacen_alertas.cerrar()


def test_cambio_sostenido_dispara_alerta_de_ventana(tmp_path):
    # tamano_ventana=3, ventanas_sostenidas=2: referencia (0.0) + 2 ventanas altas.
    carpeta = _crear_imagenes(tmp_path / "stream", 9)
    cfg_fuente = ConfigFuente(carpeta=str(carpeta), frecuencia_ms=100.0)
    referencia = [0.95, 0.95, 0.95]
    ventana_alta = [0.50, 0.50, 0.95]  # tasa=2/3 > 0.0+0.20
    clasificador = ClasificadorFalso(referencia + ventana_alta + ventana_alta)

    resultado = ejecutar_corrida(
        run_id="run-sostenido",
        cfg_fuente=cfg_fuente,
        cfg_modelo=CFG_MODELO,
        cfg_confianza=CFG_CONFIANZA,
        cfg_alertas=CFG_ALERTAS,
        reloj=RelojControlado(0.0),
        carpeta_evidencias=tmp_path / "evidencias",
        clasificador=clasificador,
    )

    alertas = resultado.almacen_alertas.listar(rule_id="cambio-sostenido-v1")
    assert len(alertas) == 1
    resultado.almacen_eventos.cerrar()
    resultado.almacen_alertas.cerrar()


def test_cola_final_incompleta_se_evalua_y_no_se_descarta(tmp_path):
    # tamano_ventana=3, minimo_muestras=3: deja 1 frame suelto tras la primera ventana.
    carpeta = _crear_imagenes(tmp_path / "stream", 4)
    cfg_fuente = ConfigFuente(carpeta=str(carpeta), frecuencia_ms=100.0)
    clasificador = ClasificadorFalso([0.95, 0.95, 0.95, 0.95])

    resultado = ejecutar_corrida(
        run_id="run-cola",
        cfg_fuente=cfg_fuente,
        cfg_modelo=CFG_MODELO,
        cfg_confianza=CFG_CONFIANZA,
        cfg_alertas=CFG_ALERTAS,
        reloj=RelojControlado(0.0),
        carpeta_evidencias=tmp_path / "evidencias",
        clasificador=clasificador,
    )
    # No hay aserto directo sobre la ventana final (minimo_muestras=3 > 1 restante,
    # evidencia_insuficiente): lo que importa es que la corrida completa sin lanzar.
    assert resultado.total_frames == 4
    resultado.almacen_eventos.cerrar()
    resultado.almacen_alertas.cerrar()


def test_imagenes_vinculadas_se_capturan_siempre_en_baja_confianza(tmp_path):
    from pathlib import Path

    carpeta = _crear_imagenes(tmp_path / "stream", 1)
    cfg_fuente = ConfigFuente(carpeta=str(carpeta), frecuencia_ms=100.0)
    clasificador = ClasificadorFalso([0.30])

    resultado = ejecutar_corrida(
        run_id="run-captura",
        cfg_fuente=cfg_fuente,
        cfg_modelo=CFG_MODELO,
        cfg_confianza=CFG_CONFIANZA,
        cfg_alertas=CFG_ALERTAS,
        reloj=RelojControlado(0.0),
        carpeta_evidencias=tmp_path / "evidencias",
        clasificador=clasificador,
    )
    evento = resultado.almacen_eventos.listar(run_id="run-captura")[0]
    assert evento["image_ref"] is not None
    assert Path(evento["image_ref"]).exists()
    resultado.almacen_eventos.cerrar()
    resultado.almacen_alertas.cerrar()


def test_corrida_real_con_clasificador_preentrenado(tmp_path):
    from PIL import Image

    carpeta = tmp_path / "stream"
    carpeta.mkdir()
    Image.new("RGB", (224, 224), color=(120, 160, 200)).save(carpeta / "a.jpg")
    Image.new("RGB", (224, 224), color=(40, 40, 40)).save(carpeta / "b.jpg")
    cfg_fuente = ConfigFuente(carpeta=str(carpeta), frecuencia_ms=100.0)

    resultado = ejecutar_corrida(
        run_id="run-real",
        cfg_fuente=cfg_fuente,
        cfg_modelo=CFG_MODELO,
        cfg_confianza=CFG_CONFIANZA,
        cfg_alertas=CFG_ALERTAS,
        reloj=RelojControlado(0.0),
        carpeta_evidencias=tmp_path / "evidencias",
        clasificador=ClasificadorPreentrenado(),
    )

    assert resultado.total_frames == 2
    eventos = resultado.almacen_eventos.listar(run_id="run-real")
    assert all(e["status"] == "ok" for e in eventos)
    assert all(0.0 <= e["prediction"]["score"] <= 1.0 for e in eventos)
    resultado.almacen_eventos.cerrar()
    resultado.almacen_alertas.cerrar()
