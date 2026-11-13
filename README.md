# P6-MLOPS -- Centro de monitoreo de computer vision

Proyecto individual. Convierte un stream de imagenes en inferencias, eventos y
alertas investigables, con un portal minimo para consultarlos.

## Autoria y procedencia (R7.3)

- **Autor:** Juan Pablo Del Muro, individual. Todo el codigo (`src/p6/`,
  `scripts/`, `tests/`) es aportacion propia de este proyecto.
- **Modelo:** preentrenado publico, sin entrenamiento propio -- `torchvision`
  `resnet18` con pesos `ResNet18_Weights.IMAGENET1K_V1` (1000 clases de
  ImageNet-1k). Ver `config/modelo.yaml`.
- **Imagenes de `datos/stream/normal/`:** 9 fotos propias, tomadas con celular
  para este proyecto.
- **Imagenes de `datos/stream/baja_confianza/`:** 10 fotos reales reutilizadas
  del Proyecto 3 (practica anterior del mismo semestre), del dataset publico de
  Kaggle "Dogs vs. Cats". Reutilizar una fuente de imagenes de una practica
  previa esta contemplado por la guia de evaluacion del Proyecto 6. Procedencia,
  criterio de seleccion y disclosure completo en
  `evidencias/escenarios/baja-confianza/procedencia-imagenes.md`. Ninguna
  prediccion ni score de esa practica se reutiliza: toda inferencia de este
  repositorio se corre de cero con el modelo de P6.

## Arquitectura

```
datos/stream/<carpeta>/          (carpeta de imagenes)
        |
        v
  p6.fuente.SecuenciaImagenes    frame_id + timestamp sintetico (frecuencia_ms)
        |
        v
  p6.modelo.ClasificadorPreentrenado   inferencia real (resnet18 / ImageNet-1k)
        |
        v
  p6.confianza.PoliticaConfianza       score -> zona (aceptada / duda / baja_confianza)
        |
        +--> p6.eventos.AlmacenEventos   (SQLite, evento completo por frame)
        +--> p6.capturas.PoliticaCapturas (guarda imagen si baja confianza / alerta / muestreo)
        |
        v
  p6.alertas.MotorAlertas + AlmacenAlertas   reglas de config/alertas.yaml
        |
        v
  p6.portal (FastAPI)   /eventos  /alertas  /imagenes?ruta=...
```

`p6.orquestador.ejecutar_corrida` conecta todo el flujo con un `Reloj` unico por
corrida (`p6.reloj`). `scripts/ejecutar_corrida.py` es el CLI que se usa para
correr un escenario completo.

## Instalacion

Requiere Python 3.12 (PyTorch no soporta Python 3.14 al momento de este
proyecto).

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Correr los escenarios

```bash
# C1 -- operacion normal
python3 scripts/ejecutar_corrida.py --stream datos/stream/normal --run-id run-c1-normal

# C2 -- baja confianza
python3 scripts/ejecutar_corrida.py --stream datos/stream/baja_confianza --run-id run-c2-baja
```

Cada corrida escribe en `evidencias/escenarios/<run-id>/`:
- `eventos-<run-id>.db` / `alertas-<run-id>.db` (SQLite, regenerables -- no
  versionadas, ver `.gitignore`)
- `eventos.jsonl` / `alertas.jsonl` (exportados, si versionados -- evidencia
  persistente)
- `imagenes/` (capturas vinculadas a eventos de baja confianza o con alerta)

Resultado y evidencia de cada escenario ya corrido:
`evidencias/escenarios/normal/resumen-corrida-c1.md` y
`evidencias/escenarios/baja-confianza/resumen-corrida-c2.md`.

## Portal

El portal lee directamente las bases SQLite que produce cada corrida -- hay que
correr al menos una corrida antes de levantarlo (las `.db` no estan en el repo).

```bash
PYTHONPATH=src P6_EVIDENCIAS_DIR=evidencias/escenarios uvicorn p6.portal.app:app --reload
```

Abre `http://127.0.0.1:8000/` -- lista las corridas disponibles, `/eventos`
(filtrable por corrida y zona) y `/alertas` (con regla, motivo, severidad,
accion sugerida y enlace a la imagen vinculada).

## Configuracion (`config/`)

- `fuente.yaml`: carpeta del stream y frecuencia declarada entre cuadros.
- `modelo.yaml`: identidad del modelo, pesos, clases, preprocesamiento, entorno.
- `confianza.yaml`: umbrales (calibrados con datos reales, ver
  `evidencias/metricas/calibracion-confianza.md`), tamano de ventana, minimo de
  muestras y regla de cambio sostenido.
- `alertas.yaml`: identidad, severidad y accion sugerida de cada regla
  (`baja-confianza-v1`, `cambio-sostenido-v1`).

## Metricas (R2) -- una por grupo G1-G7

| Grupo | Metrica base | Fuente de datos |
|---|---|---|
| G1 | `tiempo_inferencia_p50` | `time.perf_counter` alrededor de `modelo.clasificar` |
| G2 | `antiguedad_ultimo_frame` | timestamps de `p6.fuente` |
| G3 | `uso_recursos_promedio` (RAM/CPU) | `psutil.Process()` |
| G4 | `proporcion_baja_confianza` | eventos persistidos (misma formula que R3) |
| G5 | `cobertura_trazabilidad` | campos completos en `AlmacenEventos` |
| G6 | `version_reportada_vs_esperada` | `model_ref` del evento vs. `config/modelo.yaml` |
| G7 | `alertas_activas_en_ventana` | `AlmacenAlertas` |

Definiciones completas (M1) en `src/p6/metricas.py::CATALOGO_BASE`.

## Pruebas y calidad

```bash
ruff check .
ruff format --check .
pytest -q
```

110 pruebas, todas en verde; CI (`.github/workflows/ci.yml`) corre lo mismo en
cada push/PR a `main`.

## Limites conocidos

- La `referencia` de `PoliticaConfianza` (linea base para "cambio sostenido") se
  reinicia en cada corrida -- no persiste entre C1 y C2. La regla
  `cambio-sostenido-v1` esta configurada y probada por unidad, pero no se
  demuestra con un tercer escenario: la guia aclara que esa demostracion es un
  adicional, no un requisito de R3.3. El escenario obligatorio de C2 (alerta de
  baja confianza por evento individual) no depende de esta referencia y
  funciona de forma independiente.
- No se evalua calidad predictiva (accuracy, F1, IoU, etc.) -- fuera de alcance
  segun la guia del proyecto.
