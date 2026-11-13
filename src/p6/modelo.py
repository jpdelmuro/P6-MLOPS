"""P6: identidad y ejecucion del modelo (R1.2, R1.3).

Clasificador preentrenado de torchvision (ImageNet-1k), sin entrenamiento ni ajuste
propio -- identidad, pesos, clases, preprocesamiento y entorno quedan fijos y
documentados en `config/modelo.yaml`. Este modulo solo ejecuta inferencia real.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import torch
from PIL import Image, UnidentifiedImageError
from torchvision.models import ResNet18_Weights, resnet18


class ModeloError(RuntimeError):
    """La imagen no se pudo leer o decodificar -- nunca una inferencia fallida real."""


@dataclass(frozen=True)
class Prediccion:
    class_id: int
    class_name: str
    score: float


class ClasificadorPreentrenado:
    """Envuelve `torchvision.models.resnet18` con `ResNet18_Weights.IMAGENET1K_V1`
    (ver `config/modelo.yaml`). Una instancia por corrida: cargar el modelo es costoso,
    se reutiliza para todos los frames."""

    def __init__(self) -> None:
        pesos = ResNet18_Weights.IMAGENET1K_V1
        self._modelo = resnet18(weights=pesos)
        self._modelo.eval()
        self._transformar = pesos.transforms()
        self._clases = tuple(pesos.meta["categories"])
        self._model_ref = f"torchvision.models.resnet18@{pesos}"

    @property
    def clases(self) -> tuple[str, ...]:
        return self._clases

    @property
    def model_ref(self) -> str:
        """Identidad real del modelo que esta instancia realmente cargo (G6) --
        construida desde los pesos efectivamente instanciados aqui arriba, nunca desde
        `config/modelo.yaml`. Si la config declarara otro modelo pero este codigo
        siguiera cargando resnet18, `model_ref` seguiria diciendo la verdad y G6 podria
        detectar la discrepancia entre lo declarado y lo realmente cargado."""
        return self._model_ref

    def cargar_y_preprocesar(self, ruta_imagen: str | Path) -> torch.Tensor:
        """Lectura/decodificacion + preprocesamiento -- deliberadamente separado de
        `inferir` para que quien mida tiempos (ver `p6.orquestador`) pueda cronometrar
        solo la inferencia del modelo, tal como declara G1 en `p6.metricas`."""
        try:
            imagen = Image.open(ruta_imagen).convert("RGB")
        except (OSError, UnidentifiedImageError) as exc:
            raise ModeloError(f"{ruta_imagen}: no se pudo leer la imagen ({exc})") from exc
        return self._transformar(imagen).unsqueeze(0)

    def inferir(self, entrada: torch.Tensor) -> Prediccion:
        """Solo el paso del modelo (forward + softmax + argmax) sobre un tensor ya
        preprocesado -- esto es lo que G1 (tiempo de inferencia) debe cronometrar."""
        with torch.inference_mode():
            logits = self._modelo(entrada)
            probabilidades = torch.nn.functional.softmax(logits, dim=1)[0]
        class_id = int(torch.argmax(probabilidades))
        score = float(probabilidades[class_id])
        return Prediccion(class_id=class_id, class_name=self._clases[class_id], score=score)

    def clasificar(self, ruta_imagen: str | Path) -> Prediccion:
        """Conveniencia: carga + preprocesa + infiere en un solo paso. Quien necesite
        medir solo la inferencia (orquestador, metricas G1) debe llamar
        `cargar_y_preprocesar` e `inferir` por separado en vez de este metodo."""
        return self.inferir(self.cargar_y_preprocesar(ruta_imagen))
