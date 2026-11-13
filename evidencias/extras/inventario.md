# Inventario de adicionales reclamados

Tres elementos distintos, cada uno con ID unico, tipo, nivel solicitado y
evidencia propia. Ninguno reemplaza ni renombra un requisito base: R2, R3.3,
R4.3 y R6 ya estan acreditados sin depender de estos extras (ver
`evidencias/indice.md`).

## M-01 -- Distribucion de confianza (histograma)

- **Tipo:** M (metrica adicional).
- **Nivel solicitado:** 5 ("Calculo derivado o por ventana -- tasa, proporcion
  o distribucion -- con poblacion, exclusiones y ausencia de datos tratadas y
  recalculo comprobable").
- **Distincion de la metrica base:** la base de G4 es `proporcion_baja_confianza`
  (un escalar). Este extra es `distribucion_confianza` (un histograma de 5
  bins) -- informacion distinta, no una reparametrizacion del mismo calculo.
- **Evidencia:**
  - Implementacion: `src/p6/metricas.py::distribucion_confianza`.
  - Poblacion/exclusiones: toda observacion de la ventana; los `None` (sin
    puntuacion) se cuentan aparte en `sin_puntuacion`, nunca como score 0.
  - Calculo anclado: `tests/test_metricas.py` (3 pruebas: vacio, bins exactos,
    exclusion de `sin_puntuacion`).
  - Recalculo comprobable con datos reales: visible en vivo en
    `/dashboard?run_id=run-c2-baja` (ver extra F-01) -- bins
    `[0,.2)=1 [.2,.4)=4 [.4,.6)=1 [.6,.8)=2 [.8,1]=2`, que coinciden exactamente
    con los 10 scores de `evidencias/escenarios/run-c2-baja/eventos.jsonl`.

## F-01 -- Dashboard del portal

- **Tipo:** F (funcionalidad opcional).
- **Nivel solicitado:** 10 ("Flujo compuesto con interaccion o consulta
  parametrizada, persistencia pertinente y verificacion de resultados y
  estados vacios/erroneos").
- **Evidencia:**
  - Implementacion: `src/p6/portal/app.py::ver_dashboard`,
    `src/p6/portal/templates/dashboard.html`.
  - Parametrizado por `run_id` (selector, igual que `/eventos` y `/alertas`).
  - Persistencia real: lee `AlmacenEventos`/`AlmacenAlertas` (SQLite) y
    `mediciones.jsonl` de la corrida -- nada mockeado.
  - Contenido: conteo de eventos por zona, G1 (tiempo de inferencia p50), G3
    (uso de recursos), el histograma de M-01 y alertas agrupadas por regla.
  - Estados vacios/erroneos verificados por prueba, no solo por inspeccion:
    `tests/test_portal.py::test_sin_corridas_las_vistas_no_fallan`,
    `test_dashboard_corrida_sin_eventos_no_falla`,
    `test_dashboard_sin_mediciones_reporta_sin_datos_en_g1_g3`.
  - Observado con datos reales: `run-c2-baja` renderiza 200 con
    `tiempo de inferencia p50 = 8.44 ms` y `RAM/CPU = 382.6 MB / 153.7%`,
    identico al recalculo de `evidencias/metricas/recalculo-metricas.md`.
  - No cobra doble por el histograma: M-01 es la aportacion de la metrica
    (calculo, poblacion, exclusiones); F-01 es la aportacion de mostrarla
    integrada a un flujo de consulta parametrizado junto con otras metricas.

## S-01 -- Interrupcion y reconexion real de la fuente

- **Tipo:** S (escenario adicional).
- **Nivel solicitado:** 8 ("Una secuencia temporal adicional con transicion y
  recuperacion o persistencia, con registros vinculados y expectativas
  verificadas").
- **Distincion de C1/C2:** condicion distinta de los dos escenarios base (la
  fuente, no el modelo, es lo que falla), con su propia entrada, resultado
  esperado y evidencia trazable.
- **Como se demuestra (sin fabricar nada):**
  - `src/p6/reconexion.py::FuenteConReconexion` valida de verdad que la
    carpeta de origen siga siendo un directorio antes de entregar cada frame;
    si no lo es, levanta `FuenteError` real -- no un valor simulado.
  - `scripts/escenario_reconexion.py` copia las imagenes de
    `datos/stream/normal` a una carpeta de trabajo fuera del repositorio
    (`/tmp/p6-escenario-reconexion`), corre la mitad de los frames, **renombra
    de verdad** esa carpeta (`os.rename`) para provocar la perdida de acceso,
    captura el `FuenteError` real, registra una alerta `fuente-interrumpida-v1`
    (regla nueva en `config/alertas.yaml`), **restaura de verdad** la carpeta,
    reconecta (`fuente.reconectar()`), registra `fuente-reconectada-v1` y
    reanuda sin reprocesar ni saltar frames.
  - Pruebas unitarias de la mecanica de reconexion (cursor, sin duplicar/saltar
    frames, timestamps estables tras reconectar):
    `tests/test_reconexion.py` (5 pruebas). Pruebas de las dos alertas nuevas:
    `tests/test_alertas.py::test_generar_alerta_fuente_*` (3 pruebas).
  - Evidencia observada de una corrida real (`run_id=run-s-reconexion`):
    `evidencias/escenarios/run-s-reconexion/{eventos.jsonl, alertas.jsonl,
    bitacora-reconexion.json}`.
    - 9/9 frames procesados, `frame_id` `reconexion_0000..0008` sin huecos ni
      duplicados (la interrupcion ocurrio justo despues del frame 3).
    - `alertas.jsonl`: `fuente-interrumpida-v1` (severidad `critical`,
      `timestamp_ms=173.52`) seguida de `fuente-reconectada-v1` (severidad
      `info`, `timestamp_ms=479.24`, `reason` indica que reanuda en el indice
      4) -- el hueco entre ambas (~306 ms) es el tiempo real que la carpeta
      estuvo renombrada.
    - `bitacora-reconexion.json` deja el timestamp exacto de la interrupcion
      fisica, de la deteccion del `FuenteError` y de la reconexion exitosa.
  - Reproducible: `python3 scripts/escenario_reconexion.py` (usa una carpeta
    de scratch temporal, nunca toca `datos/stream/`).
