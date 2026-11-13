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
    reales -- la misma interfaz dividida (`cargar_y_preprocesar`/`inferir`/`model_ref`)
    que `ClasificadorPreentrenado`. El fallo simulado ocurre en `cargar_y_preprocesar`,
    igual que un fallo real de lectura de imagen. `model_ref` es independiente de
    cualquier `ConfigModelo` -- a proposito, para poder probar que G6 detecta una
    discrepancia real entre lo declarado y lo que el clasificador reporta de si mismo."""

    def __init__(self, scores: list[float | None], model_ref: str = "fake-model@v0") -> None:
        self._scores = iter(scores)
        self._siguiente_score: float | None = None
        self.model_ref = model_ref

    def cargar_y_preprocesar(self, ruta_imagen):
        self._siguiente_score = next(self._scores)
        if self._siguiente_score is None:
            raise ModeloError(f"{ruta_imagen}: fallo simulado")
        return ruta_imagen  # "tensor" falso: basta con pasarlo a inferir

    def inferir(self, entrada):
        return Prediccion(class_id=0, class_name="fake", score=self._siguiente_score)


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


def test_resultados_ventana_quedan_en_el_resultado_incluida_evidencia_insuficiente(tmp_path):
    # tamano_ventana=3, minimo_muestras=3: 4 frames -> 1 ventana completa (evidencia
    # suficiente) + 1 cola de 1 frame (evidencia insuficiente). Ambas deben quedar
    # registradas en resultados_ventana, no solo la que alcanza a generar alerta.
    carpeta = _crear_imagenes(tmp_path / "stream", 4)
    cfg_fuente = ConfigFuente(carpeta=str(carpeta), frecuencia_ms=100.0)
    clasificador = ClasificadorFalso([0.95, 0.95, 0.95, 0.95])

    resultado = ejecutar_corrida(
        run_id="run-ventanas",
        cfg_fuente=cfg_fuente,
        cfg_modelo=CFG_MODELO,
        cfg_confianza=CFG_CONFIANZA,
        cfg_alertas=CFG_ALERTAS,
        reloj=RelojControlado(0.0),
        carpeta_evidencias=tmp_path / "evidencias",
        clasificador=clasificador,
    )
    assert len(resultado.resultados_ventana) == 2
    assert resultado.resultados_ventana[0]["evidencia_suficiente"] is True
    assert resultado.resultados_ventana[1]["evidencia_suficiente"] is False
    assert resultado.resultados_ventana[1]["razon"] == "evidencia_insuficiente"
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


def test_config_ref_se_calcula_de_la_configuracion_real_si_no_se_da(tmp_path):
    carpeta = _crear_imagenes(tmp_path / "stream", 1)
    cfg_fuente = ConfigFuente(carpeta=str(carpeta), frecuencia_ms=100.0)

    resultado = ejecutar_corrida(
        run_id="run-cref",
        cfg_fuente=cfg_fuente,
        cfg_modelo=CFG_MODELO,
        cfg_confianza=CFG_CONFIANZA,
        cfg_alertas=CFG_ALERTAS,
        reloj=RelojControlado(0.0),
        carpeta_evidencias=tmp_path / "evidencias",
        clasificador=ClasificadorFalso([0.95]),
    )
    evento = resultado.almacen_eventos.listar(run_id="run-cref")[0]
    assert evento["config_ref"] != "config-v1"
    assert evento["config_ref"].startswith("config-")
    resultado.almacen_eventos.cerrar()
    resultado.almacen_alertas.cerrar()


def test_config_ref_cambia_si_cambia_la_configuracion(tmp_path):
    from dataclasses import replace

    carpeta = _crear_imagenes(tmp_path / "stream", 1)
    cfg_fuente = ConfigFuente(carpeta=str(carpeta), frecuencia_ms=100.0)
    otra_confianza = replace(CFG_CONFIANZA, umbral_inferior=0.1)

    r1 = ejecutar_corrida(
        run_id="run-a",
        cfg_fuente=cfg_fuente,
        cfg_modelo=CFG_MODELO,
        cfg_confianza=CFG_CONFIANZA,
        cfg_alertas=CFG_ALERTAS,
        reloj=RelojControlado(0.0),
        carpeta_evidencias=tmp_path / "evidencias-a",
        clasificador=ClasificadorFalso([0.95]),
    )
    r2 = ejecutar_corrida(
        run_id="run-b",
        cfg_fuente=cfg_fuente,
        cfg_modelo=CFG_MODELO,
        cfg_confianza=otra_confianza,
        cfg_alertas=CFG_ALERTAS,
        reloj=RelojControlado(0.0),
        carpeta_evidencias=tmp_path / "evidencias-b",
        clasificador=ClasificadorFalso([0.95]),
    )
    ref_a = r1.almacen_eventos.listar(run_id="run-a")[0]["config_ref"]
    ref_b = r2.almacen_eventos.listar(run_id="run-b")[0]["config_ref"]
    assert ref_a != ref_b
    for r in (r1, r2):
        r.almacen_eventos.cerrar()
        r.almacen_alertas.cerrar()


def test_referencia_persiste_entre_corridas_via_ruta_referencia(tmp_path):
    # C1: 5 scores altos (tamano_ventana=3, 1 ventana completa + cola insuficiente)
    # -> referencia = 0.0. C2: 2 ventanas completas, ambas con tasa=2/3 > 0.0+0.20.
    # Si C2 heredara la referencia de C1 (0.0), ambas ventanas cuentan "por encima" y
    # la 2a (ventanas_sostenidas=2) dispara cambio-sostenido-v1. Si C2 fijara su PROPIA
    # referencia (bug corregido), la 1a ventana solo la fijaria y nunca dispararia.
    carpeta_c1 = _crear_imagenes(tmp_path / "c1", 5)
    carpeta_c2 = _crear_imagenes(tmp_path / "c2", 6)
    cfg_fuente_c1 = ConfigFuente(carpeta=str(carpeta_c1), frecuencia_ms=100.0)
    cfg_fuente_c2 = ConfigFuente(carpeta=str(carpeta_c2), frecuencia_ms=100.0)
    ruta_referencia = tmp_path / "referencia.json"

    ejecutar_corrida(
        run_id="c1",
        cfg_fuente=cfg_fuente_c1,
        cfg_modelo=CFG_MODELO,
        cfg_confianza=CFG_CONFIANZA,
        cfg_alertas=CFG_ALERTAS,
        reloj=RelojControlado(0.0),
        carpeta_evidencias=tmp_path / "evidencias-c1",
        clasificador=ClasificadorFalso([0.95, 0.95, 0.95, 0.95, 0.95]),
        ruta_referencia=ruta_referencia,
    )
    assert ruta_referencia.exists()

    resultado_c2 = ejecutar_corrida(
        run_id="c2",
        cfg_fuente=cfg_fuente_c2,
        cfg_modelo=CFG_MODELO,
        cfg_confianza=CFG_CONFIANZA,
        cfg_alertas=CFG_ALERTAS,
        reloj=RelojControlado(0.0),
        carpeta_evidencias=tmp_path / "evidencias-c2",
        clasificador=ClasificadorFalso([0.5, 0.5, 0.9] * 2),  # 2 ventanas, tasa=2/3 c/u
        ruta_referencia=ruta_referencia,
    )
    alertas_sostenido = resultado_c2.almacen_alertas.listar(rule_id="cambio-sostenido-v1")
    assert len(alertas_sostenido) == 1  # solo se dispara si C2 hereda la referencia 0.0 de C1
    resultado_c2.almacen_eventos.cerrar()
    resultado_c2.almacen_alertas.cerrar()


def test_model_ref_del_evento_viene_del_clasificador_no_de_la_config(tmp_path):
    # G6 compara lo declarado en config/modelo.yaml contra lo que el evento reporta.
    # Si el evento solo repitiera cfg_modelo, G6 nunca podria detectar una
    # discrepancia real -- este doble declara un model_ref DISTINTO al de CFG_MODELO
    # a proposito, y el evento debe reflejar el del clasificador, no el de la config.
    from p6.metricas import version_reportada_vs_esperada

    carpeta = _crear_imagenes(tmp_path / "stream", 1)
    cfg_fuente = ConfigFuente(carpeta=str(carpeta), frecuencia_ms=100.0)
    clasificador = ClasificadorFalso([0.95], model_ref="otro-modelo@v9")

    resultado = ejecutar_corrida(
        run_id="run-g6",
        cfg_fuente=cfg_fuente,
        cfg_modelo=CFG_MODELO,  # declara "torchvision.models.resnet18@..."
        cfg_confianza=CFG_CONFIANZA,
        cfg_alertas=CFG_ALERTAS,
        reloj=RelojControlado(0.0),
        carpeta_evidencias=tmp_path / "evidencias",
        clasificador=clasificador,
    )
    eventos = resultado.almacen_eventos.listar(run_id="run-g6")
    assert eventos[0]["model_ref"] == "otro-modelo@v9"  # del clasificador, no de CFG_MODELO

    esperado = f"{CFG_MODELO.modelo_ref}@{CFG_MODELO.pesos}"
    g6 = version_reportada_vs_esperada(eventos, esperado)
    assert g6.coincide is False  # G6 SI detecta la discrepancia real
    resultado.almacen_eventos.cerrar()
    resultado.almacen_alertas.cerrar()


def test_tiempo_real_espera_la_frecuencia_declarada_entre_frames(tmp_path):
    import time

    # frecuencia_ms chica para que la prueba sea rapida mientras sigue siendo real:
    # 3 frames * 0.05s = 0.15s minimo de reloj de pared, no de timestamp sintetico.
    carpeta = _crear_imagenes(tmp_path / "stream", 3)
    cfg_fuente = ConfigFuente(carpeta=str(carpeta), frecuencia_ms=50.0)
    clasificador = ClasificadorFalso([0.95, 0.95, 0.95])

    inicio = time.perf_counter()
    resultado = ejecutar_corrida(
        run_id="run-tiempo-real",
        cfg_fuente=cfg_fuente,
        cfg_modelo=CFG_MODELO,
        cfg_confianza=CFG_CONFIANZA,
        cfg_alertas=CFG_ALERTAS,
        reloj=RelojControlado(0.0),
        carpeta_evidencias=tmp_path / "evidencias",
        clasificador=clasificador,
        tiempo_real=True,
    )
    duracion_real_s = time.perf_counter() - inicio

    assert duracion_real_s >= 0.15  # de verdad espero, no solo etiqueto timestamps
    assert resultado.total_frames == 3
    resultado.almacen_eventos.cerrar()
    resultado.almacen_alertas.cerrar()


def test_sin_tiempo_real_la_corrida_es_instantanea(tmp_path):
    import time

    carpeta = _crear_imagenes(tmp_path / "stream", 3)
    cfg_fuente = ConfigFuente(carpeta=str(carpeta), frecuencia_ms=50.0)
    clasificador = ClasificadorFalso([0.95, 0.95, 0.95])

    inicio = time.perf_counter()
    resultado = ejecutar_corrida(
        run_id="run-sin-tiempo-real",
        cfg_fuente=cfg_fuente,
        cfg_modelo=CFG_MODELO,
        cfg_confianza=CFG_CONFIANZA,
        cfg_alertas=CFG_ALERTAS,
        reloj=RelojControlado(0.0),
        carpeta_evidencias=tmp_path / "evidencias",
        clasificador=clasificador,
        # tiempo_real=False (por defecto): nunca espera, para que siga siendo
        # reproducible sin tiempo real por defecto.
    )
    assert time.perf_counter() - inicio < 0.15
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
