# C1 - Operacion normal (R6.1)

## Comando ejecutado

```
python3 scripts/ejecutar_corrida.py --stream datos/stream/normal --run-id run-c1-normal
```

Config usada: `config/fuente.yaml`, `config/modelo.yaml`, `config/confianza.yaml`
(umbrales calibrados, ver `evidencias/metricas/calibracion-confianza.md`),
`config/alertas.yaml`. `run_id = run-c1-normal`, `total_frames = 9`.

Salida cruda: `evidencias/escenarios/run-c1-normal/{eventos.jsonl, alertas.jsonl,
eventos-run-c1-normal.db, alertas-run-c1-normal.db, imagenes/}`.

## Resultado (9 eventos, inferencia real, nada fabricado)

| frame_id | clase predicha | score | zona |
|---|---|---:|---|
| normal_0000 | tricycle | 0.778 | aceptada |
| normal_0001 | Yorkshire terrier | 0.520 | duda |
| normal_0002 | Persian cat | 0.995 | aceptada |
| normal_0003 | notebook | 0.463 | duda |
| normal_0004 | iPod | 0.587 | duda |
| normal_0005 | lighter | 0.523 | duda |
| normal_0006 | slot | 0.072 | baja_confianza |
| normal_0007 | modem | 0.086 | baja_confianza |
| normal_0008 | sports car | 0.296 | baja_confianza |

2 `aceptada`, 4 `duda`, 3 `baja_confianza`. No se exige mayoria en `aceptada` para
que C1 sea valido (la rubrica no pide fabricar un estado saludable); lo que C1
demuestra es que la corrida completa -- fuente, modelo, zonas, eventos, capturas,
alertas -- funciona de extremo a extremo sobre operacion real sin condiciones
degradadas a proposito.

## Alertas generadas

3 alertas `baja-confianza-v1` (una por cada evento en zona `baja_confianza`:
`normal_0006`, `normal_0007`, `normal_0008`), cada una vinculada a su propio
`event_id` y visible en el portal (`/alertas?run_id=run-c1-normal`).

## Capturas

`evidencias/escenarios/run-c1-normal/imagenes/` contiene 3 imagenes (una por cada
evento en `baja_confianza`, segun la politica de `p6.capturas.PoliticaCapturas`:
siempre captura en baja confianza o alerta). Con solo 9 frames no se alcanzo el
umbral de muestreo periodico (`cada_n_normal=10`) para capturar tambien una
muestra de operacion "normal", lo cual es coherente con la politica declarada, no
un error.
