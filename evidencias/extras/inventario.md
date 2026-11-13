# Inventario de adicionales reclamados

Cuatro elementos distintos, cada uno con ID unico, tipo, nivel solicitado y
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

## M-02 -- Distribucion de predicciones por clase

- **Tipo:** M (metrica adicional).
- **Nivel solicitado:** 5 ("Calculo derivado o por ventana -- tasa, proporcion
  o distribucion -- con poblacion, exclusiones y ausencia de datos tratadas y
  recalculo comprobable").
- **Distincion de la metrica base y de M-01:** la base de G4 es
  `proporcion_baja_confianza` (cuantos scores caen bajo el umbral); M-01 es
  `distribucion_confianza` (histograma de los SCORES). Este extra,
  `distribucion_predicciones_por_clase`, mide algo distinto de ambas: QUE
  clases salio prediciendo el modelo, no que tan seguro estuvo. Las tres son
  calculos independientes sobre los mismos eventos, cada una con su propia
  poblacion/exclusiones -- el catalogo de G4 de la guia lista "Predicciones
  por clase" y "Distribucion de confianza" como indicadores separados.
- **Evidencia:**
  - Implementacion: `src/p6/metricas.py::distribucion_predicciones_por_clase`.
  - Poblacion/exclusiones: todos los eventos de la corrida; los eventos con
    `status == "error"` (sin `prediction`, fallo de lectura de imagen) se
    cuentan aparte en `sin_puntuacion`, nunca como una clase mas.
  - Calculo anclado: `tests/test_metricas.py` (3 pruebas: vacio, conteo exacto,
    exclusion de eventos sin prediccion).
  - Recalculo comprobable con datos reales: visible en vivo en
    `/dashboard?run_id=run-c2-baja` -- `Egyptian cat=2, Siamese cat=2,
    Pekinese=1, kelpie=1, Staffordshire bullterrier=1, Labrador retriever=1,
    bloodhound=1, Sussex spaniel=1`, `sin_puntuacion=0 de 10`, que coincide
    exactamente con las 10 predicciones de
    `evidencias/escenarios/run-c2-baja/eventos.jsonl`.

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
  - Contenido: conteo de eventos por zona, G1/G2/G3, el histograma de M-01,
    la distribucion de clases de M-02 y alertas agrupadas por regla.
  - Estados vacios/erroneos verificados por prueba, no solo por inspeccion:
    `tests/test_portal.py::test_sin_corridas_las_vistas_no_fallan`,
    `test_dashboard_corrida_sin_eventos_no_falla`,
    `test_dashboard_sin_mediciones_reporta_sin_datos_en_g1_g3`.
  - Observado con datos reales: `GET /dashboard?run_id=run-c2-baja` renderiza
    200 con G1/G3 identicos, al momento de cada corrida, al recalculo de
    `evidencias/metricas/recalculo-metricas.md` (son telemetria real: cambian
    de una corrida a otra, por eso no se fija aqui un valor puntual).
  - No cobra doble por lo que muestra: M-01 y M-02 son la aportacion de cada
    metrica (calculo, poblacion, exclusiones); F-01 es la aportacion de
    mostrarlas integradas a un flujo de consulta parametrizado junto con las
    demas metricas.

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
    `datos/stream/normal` a una carpeta de trabajo temporal propia
    (`tempfile.mkdtemp`, fuera del repositorio -- sin ruta fija), corre la
    mitad de los frames, **renombra de verdad** esa carpeta (`Path.rename`)
    para provocar la perdida de acceso, captura el `FuenteError` real,
    restaura de verdad la carpeta, reconecta (`fuente.reconectar()`) y
    reanuda sin reprocesar ni saltar frames.
  - **Cada frame pasa por `p6.orquestador.procesar_frame`** -- el mismo
    camino que usa `ejecutar_corrida` para C1/C2 -- asi los frames en
    `baja_confianza` disparan su alerta `baja-confianza-v1` y su captura
    igual que en cualquier otra corrida; el escenario nunca se salta una
    regla que el resto del sistema si aplica.
  - Las alertas de fuente (`fuente-interrumpida-v1`/`fuente-reconectada-v1`)
    quedan **vinculadas a `event_ids` reales** (el ultimo frame entregado
    antes de la caida, y el primer frame tras reconectar --
    `FuenteConReconexion.ultimo_frame_entregado`/`.proximo_frame`) y usan el
    **mismo calendario sintetico que el resto de los eventos**
    (`frame.timestamp_ms`), no un reloj de pared aparte.
  - Pruebas unitarias de la mecanica de reconexion (cursor, sin duplicar/saltar
    frames, timestamps estables tras reconectar, `proximo_frame`/
    `ultimo_frame_entregado`): `tests/test_reconexion.py` (6 pruebas). Pruebas
    de las dos alertas de fuente: `tests/test_alertas.py::test_generar_alerta_fuente_*`
    (3 pruebas).
  - Evidencia observada de una corrida real (`run_id=run-s-reconexion`):
    `evidencias/escenarios/run-s-reconexion/{eventos.jsonl, alertas.jsonl,
    bitacora-reconexion.json, imagenes/}`.
    - 9/9 frames procesados, `frame_id` `reconexion_0000..0008` sin huecos ni
      duplicados (la interrupcion ocurrio justo despues del frame 3).
    - `alertas.jsonl`: `fuente-interrumpida-v1` vinculada a
      `evt-run-s-reconexion-reconexion_0003` (ultimo frame antes de la caida,
      `timestamp_ms=1500.05`, igual al `timestamp_ms` de ese evento), seguida
      de `fuente-reconectada-v1` vinculada a
      `evt-run-s-reconexion-reconexion_0004` (primer frame tras reconectar,
      `timestamp_ms=2000.05`) -- y 3 alertas `baja-confianza-v1` reales para
      los frames 6-8, cada una con su propia captura en `imagenes/`.
    - `bitacora-reconexion.json` deja el timestamp exacto (del propio
      calendario del stream) de la interrupcion fisica, de la deteccion del
      `FuenteError` y de la reconexion exitosa.
  - Reproducible: `python3 scripts/escenario_reconexion.py` (usa una carpeta
    de scratch temporal nueva en cada corrida, nunca toca `datos/stream/`).
