# Recalculo de metricas G1-G7 desde evidencia persistida (M5)

Las 7 metricas base se recalculan aqui directamente desde los archivos que cada
corrida deja en el repositorio (`eventos.jsonl`, `alertas.jsonl`,
`mediciones.jsonl` -- agregado en `scripts/ejecutar_corrida.py` junto con los
otros dos exports), sin depender de las bases SQLite (que no se versionan, ver
`.gitignore`). Esto prueba M4 (trazabilidad: el resultado se vincula con
observaciones primarias) y M5 (verificacion: hay un comando reproducible que
recalcula una muestra).

## Comando usado (reproducible)

```python
import sys, json
from datetime import UTC, datetime

sys.path.insert(0, "src")
from p6.metricas import (
    tiempo_inferencia_p50,
    antiguedad_ultimo_frame,
    uso_recursos_promedio,
    Medicion,
    cobertura_trazabilidad,
    version_reportada_vs_esperada,
    alertas_activas_en_ventana,
)
from p6.confianza import tasa_baja_confianza
from p6.config import cargar_confianza

for run in ["run-c1-normal", "run-c2-baja"]:
    base = f"evidencias/escenarios/{run}"
    eventos = [json.loads(l) for l in open(f"{base}/eventos.jsonl")]
    alertas = [json.loads(l) for l in open(f"{base}/alertas.jsonl")]
    mediciones = [Medicion(**json.loads(l)) for l in open(f"{base}/mediciones.jsonl")]

    timestamps = [e["timestamp_ms"] for e in eventos]
    scores = [e["prediction"]["score"] if e.get("prediction") else None for e in eventos]
    cfg_confianza = cargar_confianza("config/confianza.yaml")

    # G2 usa fecha_utc (hora de pared real), no el timestamp sintetico del stream --
    # igual que p6.portal.app._g2_antiguedad_ms.
    fechas_epoch_ms = [datetime.fromisoformat(e["fecha_utc"]).timestamp() * 1000 for e in eventos]
    ahora_ms = datetime.now(UTC).timestamp() * 1000

    print("G1", tiempo_inferencia_p50(mediciones))
    print("G2", antiguedad_ultimo_frame(fechas_epoch_ms, ahora_ms))
    print("G3", uso_recursos_promedio(mediciones))
    print("G4", tasa_baja_confianza(scores, cfg_confianza))
    print("G5", cobertura_trazabilidad(eventos))
    print(
        "G6",
        version_reportada_vs_esperada(
            eventos, "torchvision.models.resnet18@ResNet18_Weights.IMAGENET1K_V1"
        ),
    )
    print("G7", alertas_activas_en_ventana(alertas, 0, max(timestamps) + 1))
```

## Resultado (recalculado, no copiado a mano)

| Metrica | run-c1-normal | run-c2-baja |
|---|---:|---:|
| G1 tiempo_inferencia_p50 (ms) -- solo `ClasificadorPreentrenado.inferir` | 6.607 | 7.058 |
| G2 antiguedad_ultimo_frame (ms, fecha_utc real vs. ahora) | varia con el momento de la consulta (ver dashboard) |
| G3 RAM promedio (MB) | 385.38 | 382.83 |
| G3 CPU promedio (%) -- puede superar 100 (multinucleo) | 134.86 | 173.02 |
| G3 muestras | 9 | 10 |
| G4 proporcion_baja_confianza | 0.333 (3/9) | 0.400 (4/10) |
| G5 cobertura_trazabilidad | 1.0 | 1.0 |
| G6 version_reportada_vs_esperada | coincide=True | coincide=True |
| G7 alertas_activas_en_ventana (toda la corrida) | 3 | 4 |

G1 y G3 varian entre corridas porque dependen del hardware/carga del proceso en
el momento de ejecutar (telemetria real, no un valor fijo); G1 cronometra solo
`inferir` (nunca `cargar_y_preprocesar`, que hace la lectura/decodificacion de
la imagen por separado -- ver `src/p6/modelo.py`). G2 no tiene un valor fijo
reproducible en este documento porque depende de "ahora" en el momento de la
consulta; es observable en vivo en `/dashboard?run_id=<corrida>` (extra F-01).
G4 coincide exactamente con la proporcion de eventos en zona `baja_confianza`
reportada en `evidencias/escenarios/{normal,baja-confianza}/resumen-corrida-*.md`.
G7 coincide con el numero de alertas listadas en cada `alertas.jsonl`.

## Checklist M1-M5 por grupo

| Grupo | M1 Definicion | M2 Adquisicion | M3 Calculo | M4 Trazabilidad | M5 Verificacion |
|---|---|---|---|---|---|
| G1 | `metricas.py::CATALOGO_BASE` | `time.perf_counter` alrededor de `ClasificadorPreentrenado.inferir`, en `orquestador.procesar_frame` | `tests/test_metricas.py` (mediana exacta) | `mediciones.jsonl` por corrida | recalculo arriba |
| G2 | idem | `fecha_utc` real (UTC, ISO-8601) de cada evento, registrada en `orquestador.procesar_frame` | `tests/test_metricas.py` | `eventos.jsonl` (`fecha_utc`) | recalculo arriba / `/dashboard` |
| G3 | idem | `psutil.Process()` en `orquestador.py`, primera lectura de CPU descartada (`iniciar_medicion_recursos`) | `tests/test_metricas.py` (promedios exactos) | `mediciones.jsonl` | recalculo arriba |
| G4 | idem | eventos persistidos | `tests/test_confianza.py` (misma formula que R3) | `eventos.jsonl` | recalculo arriba |
| G5 | idem | `AlmacenEventos` | `tests/test_metricas.py` (proporcion exacta) | `eventos.jsonl` | recalculo arriba |
| G6 | idem | `model_ref` del evento vs. `config/modelo.yaml` | `tests/test_metricas.py` | `eventos.jsonl` | recalculo arriba |
| G7 | idem | `AlmacenAlertas` | `tests/test_metricas.py` (rango inclusivo) | `alertas.jsonl` | recalculo arriba |

Los 7 grupos cubren los 5 checks (M1-M5). `R2 = 25 * (7*5)/(5*7) = 25` en
autoevaluacion, sujeto a la revision del evaluador.

## `config_ref`: huella real de la configuracion, no un texto fijo

Desde `p6.orquestador.calcular_config_ref`, `config_ref` es un hash (sha256,
10 caracteres) de `confianza.yaml` + `alertas.yaml` + `modelo.yaml` realmente
usados -- cambia si cambia cualquier umbral, ventana o regla (probado en
`tests/test_orquestador.py::test_config_ref_cambia_si_cambia_la_configuracion`).
Las corridas C1/C2 actuales comparten `config_ref = config-20bfa852c3` porque
usan exactamente la misma configuracion.
