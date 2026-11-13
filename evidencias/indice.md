# Indice de evidencia (R7.2)

Criterio -> archivo/comando -> resultado. Todas las corridas referidas se
pueden reproducir con los comandos indicados (ver tambien README.md). El
commit de referencia de cada bloque de evidencia es el commit donde se agrego
(`git log --oneline -- <archivo>`); la revision evaluada es el `HEAD` de `main`
en el momento de la revision.

## R1 -- Integracion de fuente visual y modelo (15 pts)

| Criterio | Archivo / comando | Resultado |
|---|---|---|
| R1.1 | `config/fuente.yaml`, `src/p6/fuente.py` (`SecuenciaImagenes`) | Stream con `frecuencia_ms` declarada y documentada; `tests/test_fuente.py` cubre orden, `frame_id` unicos y timestamps. |
| R1.2 | `src/p6/modelo.py` (`ClasificadorPreentrenado`), corridas C1/C2 | Inferencia real sobre las 19 imagenes de ambos escenarios; resultados en `evidencias/escenarios/{normal,baja-confianza}/resumen-corrida-*.md` y `evidencias/escenarios/run-c1-normal|run-c2-baja/eventos.jsonl`. |
| R1.3 | `config/modelo.yaml` | Identidad: `torchvision.models.resnet18`, pesos `ResNet18_Weights.IMAGENET1K_V1`, 1000 clases ImageNet-1k, preprocesamiento oficial de los pesos, entorno CPU. |

## R2 -- Metricas por grupo aplicable (25 pts)

| Criterio | Archivo / comando | Resultado |
|---|---|---|
| R2 (catalogo, M1/M2) | `src/p6/metricas.py::CATALOGO_BASE`, tabla de "Fuente de datos" en README.md | Una metrica base por grupo G1-G7, definicion y fuente de adquisicion de cada una. |
| R2 (calculo, M3) | `tests/test_metricas.py` | 15 pruebas con datos sinteticos de entrada conocida -> resultado exacto esperado, ancla el calculo de cada metrica. |
| R2 (trazabilidad y verificacion, M4/M5) | `evidencias/metricas/recalculo-metricas.md` | Las 7 metricas recalculadas desde `eventos.jsonl`/`alertas.jsonl`/`mediciones.jsonl` de las corridas C1/C2 reales (comando reproducible incluido), con checklist M1-M5 completo por grupo. |
| R2 (distribucion de puntos) | Con `G=7` grupos aplicables, cada grupo vale `25/7 ≈ 3.57` pts. Los 7 grupos aplican (ver justificacion en `src/p6/metricas.py`, docstring del modulo). Los 5 checks (M1-M5) estan cubiertos en los 7 grupos: `R2 = 25 * (7*5)/(5*7) = 25` en autoevaluacion. |

## R3 -- Umbrales y monitoreo de confianza (15 pts)

| Criterio | Archivo / comando | Resultado |
|---|---|---|
| R3.1 | `config/confianza.yaml`, `evidencias/metricas/calibracion-confianza.md` | Umbrales `umbral_inferior=0.38 < umbral_superior=0.68`, calibrados con una corrida de referencia real (no el ejemplo 0.60/0.80 de la guia), con comando reproducible y justificacion de los saltos observados. |
| R3.2 | `src/p6/confianza.py` (`zona_de`), `tests/test_confianza.py` | Tres zonas (`aceptada`/`duda`/`baja_confianza`) mas `sin_puntuacion`; baja confianza se conserva en el evento (`confidence_zone`), nunca se descarta. |
| R3.3 | `src/p6/confianza.py` (`PoliticaConfianza.evaluar_ventana`), `config/confianza.yaml` (`tamano_ventana`, `minimo_muestras`, `margen_cambio_sostenido`, `ventanas_sostenidas`) | Referencia, ventana, minimo de muestras y regla de cambio sostenido configurados y probados por unidad (`tests/test_confianza.py`); evidencia insuficiente distinguida de normalidad (ventana con menos del minimo nunca se reporta como "normal"). No se demuestra con un tercer escenario -- la guia aclara que esa demostracion es un adicional, no un requisito base (ver README.md, "Limites conocidos"). |

## R4 -- Eventos e imagenes (15 pts)

| Criterio | Archivo / comando | Resultado |
|---|---|---|
| R4.1 | `src/p6/eventos.py` (`Evento`, `CAMPOS_EVENTO_OBLIGATORIOS`) | Evento completo: identidad, timestamp, fuente, modelo, estado, prediccion, zona de confianza, `config_ref`. `tests/test_eventos.py` verifica cobertura de campos. |
| R4.2 | `src/p6/portal/app.py` (`/eventos`), `tests/test_portal.py` | Eventos consultables y filtrables por corrida/zona en el portal, leidos directo de la base SQLite de la corrida. |
| R4.3 | `src/p6/capturas.py` (`PoliticaCapturas`) | Captura siempre en baja confianza o alerta, mas muestreo periodico en operacion normal; nunca sobreescribe ni borra. Evidencia real: `evidencias/escenarios/run-c1-normal/imagenes/`, `evidencias/escenarios/run-c2-baja/imagenes/`. |

## R5 -- Alertas (15 pts)

| Criterio | Archivo / comando | Resultado |
|---|---|---|
| R5.1 | `config/alertas.yaml`, `src/p6/alertas.py` (`MotorAlertas`) | Dos reglas explicitas (`baja-confianza-v1`, `cambio-sostenido-v1`) con condicion, severidad y accion sugerida declaradas. |
| R5.2 | `evidencias/escenarios/run-c1-normal/alertas.jsonl`, `evidencias/escenarios/run-c2-baja/alertas.jsonl` | Alertas generadas desde eventos reales de las corridas C1/C2, cada una vinculada a su `event_id`, `config_ref` y motivo. |
| R5.3 | `src/p6/portal/app.py` (`/alertas`), `tests/test_portal.py` | Alertas visibles en el portal con momento, motivo, severidad, accion sugerida y enlace a la imagen del evento vinculado. |

## R6 -- Demostracion obligatoria (10 pts)

| Criterio | Archivo / comando | Resultado |
|---|---|---|
| R6.1 (C1) | `python3 scripts/ejecutar_corrida.py --stream datos/stream/normal --run-id run-c1-normal` | `evidencias/escenarios/normal/resumen-corrida-c1.md`: 9 eventos coherentes, metricas calculables, 3 alertas reales (no fabricadas). |
| R6.2 (C2) | `python3 scripts/ejecutar_corrida.py --stream datos/stream/baja_confianza --run-id run-c2-baja` | `evidencias/escenarios/baja-confianza/resumen-corrida-c2.md`: 4 de 10 eventos en `baja_confianza` (inferencia real sobre fotos genuinamente dificiles), 4 capturas vinculadas, 4 alertas `baja-confianza-v1` acreditadas por su propia condicion declarada. |

## R7 -- Repositorio Git y reproducibilidad (5 pts)

| Criterio | Archivo / comando | Resultado |
|---|---|---|
| R7.1 | `README.md` | Instalacion, dependencias (`requirements.txt`), configuracion (`config/*.yaml`) y comandos para correr cada escenario y el portal. |
| R7.2 | Este archivo (`evidencias/indice.md`) + `evidencias/escenarios/` + `evidencias/metricas/calibracion-confianza.md` | Evidencia organizada por criterio, con comando exacto para reproducir o recalcular cada muestra. |
| R7.3 | README.md ("Autoria y procedencia"), `evidencias/escenarios/baja-confianza/procedencia-imagenes.md` | Autoria individual, componentes reutilizados (imagenes de baja confianza, Proyecto 3) y procedencia del modelo (preentrenado, sin entrenamiento propio) declarados explicitamente. |

## Extras reclamados (sin limite, se suman al puntaje base)

Ver `evidencias/extras/inventario.md` para el detalle completo (ID, tipo, nivel
solicitado, evidencia) de cada uno:

| ID | Tipo | Elemento | Nivel solicitado |
|---|---|---|---|
| M-01 | Metrica adicional | Distribucion de confianza (histograma) | 5 |
| F-01 | Funcionalidad opcional | Dashboard del portal | 10 |
| S-01 | Escenario adicional | Interrupcion y reconexion real de la fuente | 8 |

## Verificacion tecnica

`ruff check .`, `ruff format --check .` y `pytest -q` (123 pruebas) en verde;
CI (`.github/workflows/ci.yml`) corre lo mismo en cada push/PR a `main`.
