# C2 - Baja confianza (R6.2)

## Comando ejecutado

```
python3 scripts/ejecutar_corrida.py --stream datos/stream/baja_confianza --run-id run-c2-baja
```

Config usada: la misma que C1 (`config/fuente.yaml`, `config/modelo.yaml`,
`config/confianza.yaml`, `config/alertas.yaml`) -- misma identidad de modelo y
umbrales, solo cambia la fuente de imagenes. `run_id = run-c2-baja`,
`total_frames = 10`.

Procedencia de las 10 imagenes: ver
`evidencias/escenarios/baja-confianza/procedencia-imagenes.md` (fotos reales
dificiles reutilizadas de Proyecto 3, R7.3).

Salida cruda: `evidencias/escenarios/run-c2-baja/{eventos.jsonl, alertas.jsonl,
eventos-run-c2-baja.db, alertas-run-c2-baja.db, imagenes/}`.

## Resultado (10 eventos, inferencia real, nada fabricado)

| frame_id | clase predicha | score | zona | captura |
|---|---|---:|---|---|
| baja_confianza_0000 | Pekinese | 0.516 | duda | no |
| baja_confianza_0001 | Egyptian cat | 0.857 | aceptada | no |
| baja_confianza_0002 | Siamese cat | 0.991 | aceptada | no |
| baja_confianza_0003 | Egyptian cat | 0.282 | **baja_confianza** | si |
| baja_confianza_0004 | Siamese cat | 0.601 | duda | no |
| baja_confianza_0005 | kelpie | 0.383 | duda | no |
| baja_confianza_0006 | Staffordshire bullterrier | 0.341 | **baja_confianza** | si |
| baja_confianza_0007 | Labrador retriever | 0.221 | **baja_confianza** | si |
| baja_confianza_0008 | bloodhound | 0.642 | duda | no |
| baja_confianza_0009 | Sussex spaniel | 0.112 | **baja_confianza** | si |

4 eventos cayeron en zona `baja_confianza` con los umbrales calibrados en C1
(`umbral_inferior=0.38`, `umbral_superior=0.68`). Son el resultado real del
clasificador sobre fotos dificiles (oclusion, poca luz, primer plano extremo,
multiples sujetos) -- condicion degradada genuina, no simulada.

## Alertas generadas (R6.2: acreditable por su propia condicion declarada)

4 alertas `baja-confianza-v1`, una por cada evento en zona `baja_confianza`
(`baja_confianza_0003`, `_0006`, `_0007`, `_0009`), cada una con su `event_id`
vinculado. Visibles en `/alertas?run_id=run-c2-baja`.

## Capturas vinculadas (R4.3)

`evidencias/escenarios/run-c2-baja/imagenes/` contiene las 4 imagenes
correspondientes a los eventos en `baja_confianza` (politica: siempre captura en
baja confianza o alerta). Cada `image_ref` del evento resuelve a un archivo
existente y es consultable desde el portal (`/imagenes?ruta=...`).
