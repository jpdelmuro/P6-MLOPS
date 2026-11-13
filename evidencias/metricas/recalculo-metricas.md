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

    print("G1", tiempo_inferencia_p50(mediciones))
    print("G2", antiguedad_ultimo_frame(timestamps, max(timestamps) + 1000))
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
| G1 tiempo_inferencia_p50 (ms) | 17.713 | 8.438 |
| G2 antiguedad_ultimo_frame (ms, con `ahora = ultimo_frame + 1000`) | 1000.0 | 1000.0 |
| G3 RAM promedio (MB) | 385.46 | 382.63 |
| G3 CPU promedio (%) | 119.63 | 153.72 |
| G3 muestras | 9 | 10 |
| G4 proporcion_baja_confianza | 0.333 (3/9) | 0.400 (4/10) |
| G5 cobertura_trazabilidad | 1.0 | 1.0 |
| G6 version_reportada_vs_esperada | coincide=True | coincide=True |
| G7 alertas_activas_en_ventana (toda la corrida) | 3 | 4 |

G1 y G3 varian entre corridas porque dependen del hardware/carga del proceso en
el momento de ejecutar (telemetria real, no un valor fijo); G2 es 1000 ms por
construccion de la muestra (`ahora = ultimo_frame + 1000`), no un artefacto.
G4 coincide exactamente con la proporcion de eventos en zona `baja_confianza`
reportada en `evidencias/escenarios/{normal,baja-confianza}/resumen-corrida-*.md`.
G7 coincide con el numero de alertas listadas en cada `alertas.jsonl`.

## Checklist M1-M5 por grupo

| Grupo | M1 Definicion | M2 Adquisicion | M3 Calculo | M4 Trazabilidad | M5 Verificacion |
|---|---|---|---|---|---|
| G1 | `metricas.py::CATALOGO_BASE` | `time.perf_counter` en `orquestador.py`, documentado en README | `tests/test_metricas.py` (mediana exacta) | `mediciones.jsonl` por corrida | recalculo arriba |
| G2 | idem | timestamps de `p6.fuente` | `tests/test_metricas.py` | `eventos.jsonl` | recalculo arriba |
| G3 | idem | `psutil.Process()` en `orquestador.py` | `tests/test_metricas.py` (promedios exactos) | `mediciones.jsonl` | recalculo arriba |
| G4 | idem | eventos persistidos | `tests/test_confianza.py` (misma formula que R3) | `eventos.jsonl` | recalculo arriba |
| G5 | idem | `AlmacenEventos` | `tests/test_metricas.py` (proporcion exacta) | `eventos.jsonl` | recalculo arriba |
| G6 | idem | `model_ref` del evento vs. `config/modelo.yaml` | `tests/test_metricas.py` | `eventos.jsonl` | recalculo arriba |
| G7 | idem | `AlmacenAlertas` | `tests/test_metricas.py` (rango inclusivo) | `alertas.jsonl` | recalculo arriba |

Los 7 grupos cubren los 5 checks (M1-M5). `R2 = 25 * (7*5)/(5*7) = 25` en
autoevaluacion, sujeto a la revision del evaluador.
