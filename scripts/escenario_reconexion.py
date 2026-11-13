#!/usr/bin/env python3
"""Extra S: demuestra una interrupcion y reconexion REALES de la fuente, con
inferencia real sobre cada frame -- nada de la interrupcion se narra ni se fabrica:
la carpeta de origen se renombra de verdad a mitad de la corrida (provocando un
`FuenteError` real) y se restaura de verdad antes de reconectar.

Uso:
    python scripts/escenario_reconexion.py

Deja evidencia en evidencias/extras/escenario-reconexion/: eventos.jsonl,
alertas.jsonl y un resumen con los timestamps reales de interrupcion/reconexion.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from p6.alertas import AlmacenAlertas, MotorAlertas
from p6.confianza import zona_de
from p6.config import cargar_alertas, cargar_confianza, cargar_fuente, cargar_modelo
from p6.eventos import AlmacenEventos, Evento
from p6.fuente import FuenteError
from p6.modelo import ClasificadorPreentrenado, ModeloError
from p6.reconexion import FuenteConReconexion
from p6.reloj import reloj_monotonico

RAIZ = Path(__file__).resolve().parents[1]
RUN_ID = "run-s-reconexion"


def main() -> None:
    cfg_fuente = cargar_fuente(RAIZ / "config" / "fuente.yaml")
    cfg_modelo = cargar_modelo(RAIZ / "config" / "modelo.yaml")
    cfg_confianza = cargar_confianza(RAIZ / "config" / "confianza.yaml")
    cfg_alertas = cargar_alertas(RAIZ / "config" / "alertas.yaml")

    carpeta_evidencias = RAIZ / "evidencias" / "escenarios" / RUN_ID
    carpeta_evidencias.mkdir(parents=True, exist_ok=True)

    # Carpeta de trabajo propia (fuera del repo) para poder renombrarla de verdad sin
    # tocar datos/stream/normal, que si esta versionado.
    scratch = Path("/tmp/p6-escenario-reconexion")
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    origenes = sorted(Path(cfg_fuente.carpeta).iterdir())
    for ruta in origenes:
        shutil.copy(ruta, scratch / ruta.name)
    carpeta_caida = scratch.parent / "p6-escenario-reconexion-caida"

    reloj = reloj_monotonico()
    fuente = FuenteConReconexion(scratch, cfg_fuente.frecuencia_ms, reloj, source_id="reconexion")
    total_frames = len(fuente)
    interrumpir_tras = total_frames // 2

    clasificador = ClasificadorPreentrenado()
    almacen_eventos = AlmacenEventos(carpeta_evidencias / f"eventos-{RUN_ID}.db")
    almacen_alertas = AlmacenAlertas(carpeta_evidencias / f"alertas-{RUN_ID}.db")
    motor_alertas = MotorAlertas(cfg_alertas, config_ref="config-v1")
    model_ref = f"{cfg_modelo.modelo_ref}@{cfg_modelo.pesos}"

    bitacora: list[dict] = []
    procesados = 0
    reconexiones = 0

    while True:
        try:
            for frame in fuente:
                event_id = f"evt-{RUN_ID}-{frame.frame_id}"
                try:
                    prediccion = clasificador.clasificar(frame.ruta)
                    status = "ok"
                except ModeloError:
                    prediccion = None
                    status = "error"
                zona = zona_de(prediccion.score if prediccion else None, cfg_confianza)
                almacen_eventos.registrar(
                    Evento(
                        event_id=event_id,
                        run_id=RUN_ID,
                        frame_id=frame.frame_id,
                        timestamp_ms=frame.timestamp_ms,
                        source_id=fuente.source_id,
                        task="classification",
                        model_ref=model_ref,
                        status=status,
                        prediction=prediccion,
                        confidence_zone=zona if status == "ok" else "sin_puntuacion",
                        config_ref="config-v1",
                        image_ref=None,
                    )
                )
                procesados += 1
                print(f"frame {frame.frame_id}: {status} ({zona if status == 'ok' else 'error'})")

                if procesados == interrumpir_tras and reconexiones == 0:
                    t_interrupcion = reloj()
                    print(f"-- interrupcion real: renombrando {scratch} -> {carpeta_caida} --")
                    scratch.rename(carpeta_caida)
                    bitacora.append(
                        {"evento": "interrupcion_fisica", "timestamp_ms": t_interrupcion}
                    )
            break  # recorrio toda la fuente sin errores -> termina
        except FuenteError as err:
            t_detectada = reloj()
            print(f"-- FuenteError real detectado: {err} --")
            alerta_caida = motor_alertas.generar_alerta_fuente(
                "fuente_interrumpida",
                timestamp_ms=t_detectada,
                reason=str(err),
            )
            if alerta_caida is not None:
                almacen_alertas.registrar(alerta_caida)
            bitacora.append(
                {
                    "evento": "fuenteerror_detectado",
                    "timestamp_ms": t_detectada,
                    "frames_antes_de_la_caida": fuente.siguiente_indice,
                }
            )

            time.sleep(0.3)  # separa los timestamps de la bitacora; no afecta el stream sintetico
            print(f"-- restaurando acceso real: {carpeta_caida} -> {scratch} --")
            carpeta_caida.rename(scratch)

            if not fuente.reconectar():
                raise RuntimeError("no se pudo reconectar: la carpeta sigue inaccesible") from err

            t_reconexion = reloj()
            reconexiones += 1
            alerta_reconexion = motor_alertas.generar_alerta_fuente(
                "fuente_reconectada",
                timestamp_ms=t_reconexion,
                reason=f"fuente disponible de nuevo; reanuda en indice {fuente.siguiente_indice}",
            )
            if alerta_reconexion is not None:
                almacen_alertas.registrar(alerta_reconexion)
            bitacora.append(
                {
                    "evento": "reconexion_exitosa",
                    "timestamp_ms": t_reconexion,
                    "reanuda_en_indice": fuente.siguiente_indice,
                }
            )

    eventos_jsonl = almacen_eventos.exportar_jsonl(carpeta_evidencias / "eventos.jsonl")
    alertas_jsonl = almacen_alertas.exportar_jsonl(carpeta_evidencias / "alertas.jsonl")
    almacen_eventos.cerrar()
    almacen_alertas.cerrar()
    shutil.rmtree(scratch, ignore_errors=True)

    resumen = {
        "run_id": RUN_ID,
        "total_frames": total_frames,
        "frames_procesados": procesados,
        "reconexiones": reconexiones,
        "bitacora": bitacora,
    }
    ruta_resumen = carpeta_evidencias / "bitacora-reconexion.json"
    ruta_resumen.write_text(json.dumps(resumen, indent=2, ensure_ascii=False))

    print(f"\nrun_id={RUN_ID} total_frames={total_frames} procesados={procesados}")
    print(f"eventos  -> {eventos_jsonl}")
    print(f"alertas  -> {alertas_jsonl}")
    print(f"bitacora -> {ruta_resumen}")


if __name__ == "__main__":
    main()
