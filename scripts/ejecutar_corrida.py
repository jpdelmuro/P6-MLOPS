#!/usr/bin/env python3
"""CLI de P6: ejecuta una corrida completa (fuente -> modelo -> confianza -> eventos ->
alertas) sobre una carpeta de imagenes. Usado para C1 (normal) y C2 (baja confianza),
y para cualquier corrida manual durante el desarrollo.

Uso:
    python scripts/ejecutar_corrida.py --stream datos/stream/normal --run-id run-c1-normal
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
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
    parser.add_argument("--evidencias", default=str(RAIZ / "evidencias" / "escenarios"))
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
    resultado = ejecutar_corrida(
        run_id=args.run_id,
        cfg_fuente=cfg_fuente,
        cfg_modelo=cfg_modelo,
        cfg_confianza=cfg_confianza,
        cfg_alertas=cfg_alertas,
        reloj=reloj_monotonico(),
        carpeta_evidencias=carpeta_evidencias,
        clasificador=ClasificadorPreentrenado(),
    )

    eventos_jsonl = resultado.almacen_eventos.exportar_jsonl(carpeta_evidencias / "eventos.jsonl")
    alertas_jsonl = resultado.almacen_alertas.exportar_jsonl(carpeta_evidencias / "alertas.jsonl")
    resultado.almacen_eventos.cerrar()
    resultado.almacen_alertas.cerrar()

    print(f"run_id={resultado.run_id} total_frames={resultado.total_frames}")
    print(f"eventos  -> {eventos_jsonl}")
    print(f"alertas  -> {alertas_jsonl}")
    print(f"imagenes -> {carpeta_evidencias / 'imagenes'}")


if __name__ == "__main__":
    main()
