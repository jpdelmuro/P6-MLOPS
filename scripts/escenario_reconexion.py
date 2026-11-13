#!/usr/bin/env python3
"""Extra S: demuestra una interrupcion y reconexion REALES de la fuente, con
inferencia real sobre cada frame -- nada de la interrupcion se narra ni se fabrica:
la carpeta de origen se renombra de verdad a mitad de la corrida (provocando un
`FuenteError` real) y se restaura de verdad antes de reconectar.

Cada frame pasa por `p6.orquestador.procesar_frame` -- el mismo camino que usa
`ejecutar_corrida` para C1/C2 -- para que los frames en baja_confianza disparen su
alerta y su captura igual que en cualquier otra corrida (nunca un camino aparte que se
salte la regla que el resto del sistema sí aplica).

Uso:
    python scripts/escenario_reconexion.py

Deja evidencia en evidencias/escenarios/run-s-reconexion/: eventos.jsonl,
alertas.jsonl y una bitacora con los timestamps reales de interrupcion/reconexion.
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from p6.alertas import AlmacenAlertas, MotorAlertas
from p6.capturas import PoliticaCapturas
from p6.config import cargar_alertas, cargar_confianza, cargar_fuente, cargar_modelo
from p6.eventos import AlmacenEventos
from p6.fuente import FuenteError
from p6.modelo import ClasificadorPreentrenado
from p6.orquestador import calcular_config_ref, iniciar_medicion_recursos, procesar_frame
from p6.reconexion import FuenteConReconexion
from p6.reloj import reloj_monotonico

RAIZ = Path(__file__).resolve().parents[1]
RUN_ID = "run-s-reconexion"


def main() -> None:
    cfg_fuente = cargar_fuente(RAIZ / "config" / "fuente.yaml")
    cfg_modelo = cargar_modelo(RAIZ / "config" / "modelo.yaml")
    cfg_confianza = cargar_confianza(RAIZ / "config" / "confianza.yaml")
    cfg_alertas = cargar_alertas(RAIZ / "config" / "alertas.yaml")
    config_ref = calcular_config_ref(cfg_confianza, cfg_alertas, cfg_modelo)

    carpeta_evidencias = Path("evidencias") / "escenarios" / RUN_ID
    carpeta_evidencias.mkdir(parents=True, exist_ok=True)

    # Carpeta de trabajo propia, fuera del repo, para poder renombrarla de verdad sin
    # tocar datos/stream/normal (que si esta versionado). tempfile evita una ruta fija
    # y colisiones si se corre mas de una vez en paralelo.
    scratch = Path(tempfile.mkdtemp(prefix="p6-escenario-reconexion-"))
    for ruta in sorted(Path(cfg_fuente.carpeta).iterdir()):
        shutil.copy(ruta, scratch / ruta.name)
    carpeta_caida = scratch.parent / f"{scratch.name}-caida"

    reloj = reloj_monotonico()
    fuente = FuenteConReconexion(scratch, cfg_fuente.frecuencia_ms, reloj, source_id="reconexion")
    total_frames = len(fuente)
    interrumpir_tras = total_frames // 2

    clasificador = ClasificadorPreentrenado()
    almacen_eventos = AlmacenEventos(carpeta_evidencias / f"eventos-{RUN_ID}.db")
    almacen_alertas = AlmacenAlertas(carpeta_evidencias / f"alertas-{RUN_ID}.db")
    motor_alertas = MotorAlertas(cfg_alertas, config_ref=config_ref)
    capturas = PoliticaCapturas(carpeta_evidencias / "imagenes")
    proceso = iniciar_medicion_recursos()
    model_ref = f"{cfg_modelo.modelo_ref}@{cfg_modelo.pesos}"

    bitacora: list[dict] = []
    procesados = 0
    reconexiones = 0

    while True:
        try:
            for frame in fuente:
                resultado = procesar_frame(
                    frame,
                    run_id=RUN_ID,
                    source_id=fuente.source_id,
                    model_ref=model_ref,
                    config_ref=config_ref,
                    clasificador=clasificador,
                    cfg_confianza=cfg_confianza,
                    motor_alertas=motor_alertas,
                    capturas=capturas,
                    proceso=proceso,
                )
                almacen_eventos.registrar(resultado.evento)
                if resultado.alerta is not None:
                    almacen_alertas.registrar(resultado.alerta)
                procesados += 1
                print(
                    f"frame {frame.frame_id}: {resultado.evento.status} "
                    f"({resultado.evento.confidence_zone})"
                    + (" -- ALERTA" if resultado.alerta is not None else "")
                )

                if procesados == interrumpir_tras and reconexiones == 0:
                    t_interrupcion = frame.timestamp_ms
                    print(f"-- interrupcion real: renombrando {scratch} -> {carpeta_caida} --")
                    scratch.rename(carpeta_caida)
                    bitacora.append(
                        {"evento": "interrupcion_fisica", "timestamp_ms": t_interrupcion}
                    )
            break  # recorrio toda la fuente sin errores -> termina
        except FuenteError as err:
            # El timestamp y el event_id vinculado vienen del propio calendario
            # sintetico del stream (no de un reloj de pared distinto): el ultimo frame
            # realmente entregado antes de la caida.
            ultimo = fuente.ultimo_frame_entregado
            t_detectada = ultimo.timestamp_ms if ultimo is not None else 0.0
            evento_previo = f"evt-{RUN_ID}-{ultimo.frame_id}" if ultimo is not None else None
            print(f"-- FuenteError real detectado: {err} --")
            alerta_caida = motor_alertas.generar_alerta_fuente(
                "fuente_interrumpida",
                timestamp_ms=t_detectada,
                reason=str(err),
                event_ids=(evento_previo,) if evento_previo else (),
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

            print(f"-- restaurando acceso real: {carpeta_caida} -> {scratch} --")
            carpeta_caida.rename(scratch)

            if not fuente.reconectar():
                raise RuntimeError("no se pudo reconectar: la carpeta sigue inaccesible") from err

            # Igual que arriba: el timestamp y el event_id vinculado son los del
            # proximo frame real del stream, no un reloj de pared aparte.
            proximo = fuente.proximo_frame
            t_reconexion = proximo.timestamp_ms if proximo is not None else t_detectada
            evento_siguiente = f"evt-{RUN_ID}-{proximo.frame_id}" if proximo is not None else None
            reconexiones += 1
            alerta_reconexion = motor_alertas.generar_alerta_fuente(
                "fuente_reconectada",
                timestamp_ms=t_reconexion,
                reason=f"fuente disponible de nuevo; reanuda en indice {fuente.siguiente_indice}",
                event_ids=(evento_siguiente,) if evento_siguiente else (),
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
