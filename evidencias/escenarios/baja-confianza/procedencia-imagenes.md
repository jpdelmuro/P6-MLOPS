# Procedencia de las imagenes de datos/stream/baja_confianza (R7.3)

## Origen

Las 10 imagenes de `datos/stream/baja_confianza/` son fotos reales reutilizadas del
Proyecto 3 (practica anterior de este mismo semestre, repositorio en
`Proyecto 3/data/raw/images/`): el dataset publico de Kaggle "Dogs vs. Cats"
(Asirra), fotos de aficionado de gatos y perros en refugios/hogares.

Reutilizar una fuente de imagenes de una practica previa esta explicitamente
contemplado por la guia de evaluacion del Proyecto 6 (que ya anticipa reutilizar,
por ejemplo, la camara del carrito del Proyecto 5, y pide no presumir que reutilizar
trabajo previo esta prohibido). Lo que exige declarar es la procedencia y la
aportacion propia (R7.3), que es justamente lo que documenta este archivo.

No se reutiliza nada mas que los pixeles originales: ninguna prediccion, score o
anotacion de la practica anterior se trae a este proyecto. Toda inferencia de la
tabla de abajo se corrio de cero en P6 con `p6.modelo.ClasificadorPreentrenado`
(`resnet18`, `ResNet18_Weights.IMAGENET1K_V1`, ver `config/modelo.yaml`).

## Criterio de seleccion

De las 600 fotos del dataset original se eligieron 10 (5 gatos + 5 perros) que son
visualmente dificiles de forma real, sin degradar ni manipular nada:

- `cat.5.jpg`: foto pequena/baja resolucion, interior con objetos encimados, gato
  parcialmente tapado por un brazo.
- `cat.150.jpg`: poca luz, fondo de jaulas de refugio, gato de espaldas/mirando abajo.
- `cat.175.jpg`: dos gatitos encimados en el mismo recorte (sujeto ambiguo).
- `cat.250.jpg`: primer plano extremo, borroso, sostenido con la mano, angulo raro.
- `cat.20.jpg`: ojos rojos de flash que distorsionan la cara, fondo reflectante de
  vidrio.
- `dog.5.jpg`: perro parcialmente ocluido por rejas de jaula metalica.
- `dog.75.jpg`: primer plano extremo sostenido con la mano, fondo con auto/casa.
- `dog.150.jpg`: dos personas ocluyendo al perro, angulo picado inusual.
- `dog.175.jpg`: angulo cenital inusual + marca de fecha superpuesta en la imagen.
- `dog.250.jpg`: dos perros encimados/ocluyendose entre si, fondo de lona.

## Comando usado (reproducible)

```
python3 -c "
import sys; sys.path.insert(0, 'src')
from p6.modelo import ClasificadorPreentrenado
from pathlib import Path
clasificador = ClasificadorPreentrenado()
for ruta in sorted(Path('datos/stream/baja_confianza').iterdir()):
    p = clasificador.clasificar(ruta)
    print(ruta.name, p.class_name, p.score)
"
```

## Observaciones (inferencia real, sin editar ni descartar ninguna)

| Foto | Clase predicha | Score | Zona (umbral_inferior=0.38 / umbral_superior=0.68) |
|---|---|---:|---|
| cat.5.jpg | Siamese cat | 0.601 | duda |
| cat.20.jpg | Siamese cat | 0.991 | aceptada |
| cat.150.jpg | Pekinese | 0.516 | duda |
| cat.175.jpg | Egyptian cat | 0.857 | aceptada |
| cat.250.jpg | Egyptian cat | 0.282 | baja_confianza |
| dog.5.jpg | bloodhound | 0.642 | duda |
| dog.75.jpg | Sussex spaniel | 0.112 | baja_confianza |
| dog.150.jpg | kelpie | 0.383 | duda |
| dog.175.jpg | Staffordshire bullterrier | 0.341 | baja_confianza |
| dog.250.jpg | Labrador retriever | 0.221 | baja_confianza |

4 en `baja_confianza`, 4 en `duda`, 2 en `aceptada`. Los umbrales usados son los
calibrados con la corrida de referencia real de `datos/stream/normal`
(ver `evidencias/metricas/calibracion-confianza.md`); no se recalibran con este
conjunto porque C2 es el escenario de prueba, no la referencia.

No se fabrica un estado de baja confianza: es el resultado real de un clasificador
de ImageNet (clases especificas de raza) sobre fotos de mascotas mestizas, ocluidas
o con mala iluminacion -- exactamente el tipo de condicion que C2 debe demostrar.
Las 4 imagenes en zona `baja_confianza` son evidencia suficiente para que la regla
`baja-confianza-v1` dispare sobre eventos reales (R6.2).
