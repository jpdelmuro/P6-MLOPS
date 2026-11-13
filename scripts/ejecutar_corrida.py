#!/usr/bin/env python3
"""CLI de P6: ejecuta una corrida completa (fuente -> modelo -> confianza -> eventos ->
alertas) sobre una carpeta de imagenes. Usado para C1 (normal) y C2 (baja confianza),
y para cualquier corrida manual durante el desarrollo.

Uso:
    python scripts/ejecutar_corrida.py --stream datos/stream/normal --run-id run-c1-normal
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from p6.config import cargar_alertas, cargar_confianza, cargar_fuente, cargar_modelo
from p6.modelo import ClasificadorPreentrenado
from p6.orquestador import ejecutar_corrida
from p6.reloj import reloj_monotonico

RAIZ = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stream", required=True, help="Carpeta de imagenes a reproducir")
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--frecuencia-ms", type=float, default=None, help="Sobrescribe config/fuente.yaml"
    )
    parser.add_argument(
        "--evidencias",
        default="evidencias/escenarios",
        help="Relativa al directorio actual (se asume cwd = raiz del repo, igual que --stream)",
    )
    parser.add_argument(
        "--referencia",
        default="evidencias/escenarios/referencia.json",
        help="Archivo donde persiste la referencia de confianza entre corridas (R3.3) "
        "-- una serie (ej. C1 -> C2) comparte este archivo. Vacio ('') para no persistir.",
    )
    parser.add_argument(
        "--tiempo-real",
        action="store_true",
        help="Espera frecuencia_ms real entre frames (R1.1) en vez de solo etiquetar "
        "timestamps sinteticos; la corrida tarda literalmente eso en completarse.",
    )
    args = parser.parse_args()

    cfg_fuente = cargar_fuente(RAIZ / "config" / "fuente.yaml")
    cfg_fuente = replace(
        cfg_fuente,
        carpeta=args.stream,
        frecuencia_ms=args.frecuencia_ms or cfg_fuente.frecuencia_ms,
    )
    cfg_modelo = cargar_modelo(RAIZ / "config" / "modelo.yaml")
    cfg_confianza = cargar_confianza(RAIZ / "config" / "confianza.yaml")
    cfg_alertas = cargar_alertas(RAIZ / "config" / "alertas.yaml")

    carpeta_evidencias = Path(args.evidencias) / args.run_id
    ruta_referencia = Path(args.referencia) if args.referencia else None
    resultado = ejecutar_corrida(
        run_id=args.run_id,
        cfg_fuente=cfg_fuente,
        cfg_modelo=cfg_modelo,
        cfg_confianza=cfg_confianza,
        cfg_alertas=cfg_alertas,
        reloj=reloj_monotonico(),
        carpeta_evidencias=carpeta_evidencias,
        clasificador=ClasificadorPreentrenado(),
        ruta_referencia=ruta_referencia,
        tiempo_real=args.tiempo_real,
    )

    eventos_jsonl = resultado.almacen_eventos.exportar_jsonl(carpeta_evidencias / "eventos.jsonl")
    alertas_jsonl = resultado.almacen_alertas.exportar_jsonl(carpeta_evidencias / "alertas.jsonl")
    resultado.almacen_eventos.cerrar()
    resultado.almacen_alertas.cerrar()

    mediciones_jsonl = carpeta_evidencias / "mediciones.jsonl"
    with mediciones_jsonl.open("w") as f:
        for medicion in resultado.mediciones:
            f.write(json.dumps(asdict(medicion)) + "\n")

    ventanas_jsonl = carpeta_evidencias / "ventanas.jsonl"
    with ventanas_jsonl.open("w") as f:
        for resultado_ventana in resultado.resultados_ventana:
            f.write(json.dumps(resultado_ventana) + "\n")

    print(f"run_id={resultado.run_id} total_frames={resultado.total_frames}")
    print(f"eventos    -> {eventos_jsonl}")
    print(f"alertas    -> {alertas_jsonl}")
    print(f"mediciones -> {mediciones_jsonl}")
    print(f"ventanas   -> {ventanas_jsonl}")
    print(f"imagenes   -> {carpeta_evidencias / 'imagenes'}")
    if ruta_referencia is not None:
        print(f"referencia -> {ruta_referencia} (compartida entre corridas)")


if __name__ == "__main__":
    main()
