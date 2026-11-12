# Calibracion de umbrales de confianza (R3.1)

## Metodo

Corrida de referencia real: las 9 fotos de `datos/stream/normal/` (fotos de celular,
objetos cotidianos), clasificadas con `p6.modelo.ClasificadorPreentrenado`
(`resnet18`, `ResNet18_Weights.IMAGENET1K_V1`, ver `config/modelo.yaml`). Ningun score
fue ajustado ni descartado; se reportan los 9 tal cual salieron del modelo.

Comando usado:

```
python3 -c "
import sys; sys.path.insert(0, 'src')
from p6.modelo import ClasificadorPreentrenado
from pathlib import Path
clasificador = ClasificadorPreentrenado()
for ruta in sorted(Path('datos/stream/normal').iterdir()):
    p = clasificador.clasificar(ruta)
    print(ruta.name, p.class_name, p.score)
"
```

## Observaciones (M2/M5: reproducibles con el comando de arriba)

| Foto | Clase predicha | Score |
|---|---|---:|
| Screenshot_20261111_232942_Photos.jpg | lighter | 0.523 |
| Screenshot_20261111_232933_Photos.jpg | iPod | 0.587 |
| Screenshot_20261111_232914_Photos.jpg | notebook | 0.463 |
| Screenshot_20261111_232855_Photos.jpg | Persian cat | 0.995 |
| Screenshot_20261111_232842_Photos.jpg | Yorkshire terrier | 0.520 |
| Screenshot_20261111_232809_Photos.jpg | tricycle | 0.778 |
| Screenshot_20261111_232956_Photos.jpg | slot | 0.072 |
| Screenshot_20261111_233446_Photos.jpg | modem | 0.086 |
| Screenshot_20261111_234631_Photos.jpg | sports car | 0.296 |

Scores ordenados: `0.072, 0.086, 0.296, 0.463, 0.520, 0.523, 0.587, 0.778, 0.995`.

## Justificacion del umbral (R3.1)

0.60/0.80 (el ejemplo de la guia) dejaria 7 de las 9 fotos en `baja_confianza`, lo cual
no refleja una calibracion real: solo se tomo prestado el ejemplo sin observar nada.

En cambio, los dos saltos mas grandes entre scores consecutivos de esta distribucion
real son:

- `0.296 -> 0.463` (salto de 0.167)
- `0.587 -> 0.778` (salto de 0.191)

Se fijan los umbrales en el punto medio de cada salto:

- `umbral_inferior = 0.38` (punto medio de 0.296 y 0.463)
- `umbral_superior = 0.68` (punto medio de 0.587 y 0.778)

## Resultado de la calibracion

| Score | Zona (0.38 / 0.68) |
|---:|---|
| 0.072 | baja_confianza |
| 0.086 | baja_confianza |
| 0.296 | baja_confianza |
| 0.463 | duda |
| 0.520 | duda |
| 0.523 | duda |
| 0.587 | duda |
| 0.778 | aceptada |
| 0.995 | aceptada |

3 en `baja_confianza`, 4 en `duda`, 2 en `aceptada`. No se fabrico un estado saludable:
es la distribucion real de un clasificador preentrenado sobre fotos de celular, con
angulos y fondos que no son los de las imagenes de validacion de ImageNet.

Estos valores quedan en `config/confianza.yaml` (`umbral_inferior: 0.38`,
`umbral_superior: 0.68`) y se usan tal cual para las corridas de C1/C2.
