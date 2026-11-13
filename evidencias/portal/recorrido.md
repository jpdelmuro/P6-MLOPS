# Recorrido del portal (R4.2, R5.3)

Recorrido reproducible -- cada paso es un comando o una URL real, no una
narracion. Requiere tener al menos una corrida (ver README, "Correr los
escenarios"); este recorrido asume que ya corriste C1 y C2.

## 1. Levantar el portal

```bash
PYTHONPATH=src P6_EVIDENCIAS_DIR=evidencias/escenarios uvicorn p6.portal.app:app --reload
```

## 2. Inicio -- `GET /`

Lista solo las corridas reales (las que tienen `eventos-<run_id>.db`, nunca
las carpetas de documentacion `normal/`/`baja-confianza/`), cada una con
enlaces directos a sus eventos, alertas y dashboard.

![Inicio](capturas/01-inicio.png)

## 3. Eventos -- `GET /eventos?run_id=run-c2-baja`

Tabla de los 10 eventos de C2, cada fila con `event_id`, `frame_id`,
`timestamp_ms`, `status`, zona de confianza (coloreada), clase predicha, score
e imagen (si se capturo). Filtrar por zona:
`GET /eventos?run_id=run-c2-baja&zona=baja_confianza` reduce la tabla a los 4
eventos en esa zona.

![Eventos filtrados por zona baja_confianza](capturas/02-eventos-baja-confianza.png)

## 4. Alertas -- `GET /alertas?run_id=run-c2-baja`

Tabla de las 4 alertas `baja-confianza-v1` de C2, cada una con `rule_id`,
`timestamp_ms`, `severity`, `reason`, `accion sugerida`, y un enlace
`event_id -> /imagenes?ruta=...` a la captura real que origino la alerta.

![Alertas](capturas/03-alertas.png)

## 5. Imagen vinculada -- `GET /imagenes?ruta=evidencias/escenarios/run-c2-baja/imagenes/evt-run-c2-baja-baja_confianza_0003.jpg`

Clic en cualquier `event_id` de la tabla de alertas sirve el archivo real
(`FileResponse`), validado contra la raiz del repositorio (una ruta fuera del
repo responde 403; una ruta inexistente, 404 -- ver
`tests/test_portal.py::test_imagenes_rechaza_ruta_fuera_del_repositorio` y
`test_imagenes_404_si_no_existe`).

![Imagen vinculada servida por /imagenes](capturas/05-imagen-vinculada.png)

`GET /imagenes?ruta=../../../etc/passwd` (una ruta fuera del repositorio)
responde 403, no el archivo:

![403 ante una ruta fuera del repositorio](capturas/06-imagenes-403.png)

## 6. Dashboard (extra F-01) -- `GET /dashboard?run_id=run-c2-baja`

Vista agregada: conteo de eventos por zona, G1 (tiempo de inferencia p50), G2
(antiguedad real del ultimo frame), G3 (uso de recursos), el histograma de
confianza (extra M-01) y alertas por regla. Cambiar la corrida con el
selector reconsulta todo en vivo.

![Dashboard](capturas/04-dashboard.png)

## Estados verificados (no solo el camino feliz)

- `GET /` sin ninguna corrida: `evidencias/escenarios/` vacio -> mensaje
  explicito, no un error 500
  (`tests/test_portal.py::test_sin_corridas_las_vistas_no_fallan`).
- `GET /dashboard?run_id=<corrida-sin-eventos>`: mensaje explicito, no falla
  (`test_dashboard_corrida_sin_eventos_no_falla`).
- `GET /dashboard?run_id=<corrida-sin-mediciones.jsonl>`: G1/G3 muestran
  "sin datos" en vez de un error
  (`test_dashboard_sin_mediciones_reporta_sin_datos_en_g1_g3`).

Las 14 pruebas de `tests/test_portal.py` cubren cada ruta descrita arriba con
`fastapi.testclient.TestClient` sobre datos reales (nunca mockeados): son la
evidencia "observado/reproducido" de este recorrido, ejecutable con
`pytest tests/test_portal.py -q`.
