"""P6: configuracion YAML validada para fuente, modelo, confianza y alertas.

Mismo principio que `p5.contrato`/`p5.politica`: una configuracion invalida lanza
`ConfigError` con la lista completa de problemas, nunca se completa con un valor
por defecto silencioso.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class ConfigError(ValueError):
    def __init__(self, archivo: str, errores: list[str]) -> None:
        super().__init__(f"{archivo}: configuracion invalida: " + "; ".join(errores))
        self.archivo = archivo
        self.errores = errores


def _leer_yaml(ruta: str | Path) -> Any:
    try:
        return yaml.safe_load(Path(ruta).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(str(ruta), [f"no se pudo leer ({exc})"]) from exc


def _numero_positivo(valor: Any) -> bool:
    es_numero = isinstance(valor, int | float) and not isinstance(valor, bool)
    return es_numero and math.isfinite(valor) and valor > 0


def _entero_positivo(valor: Any) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool) and valor > 0


def _texto_no_vacio(valor: Any) -> bool:
    return isinstance(valor, str) and valor.strip() != ""


def _claves_invalidas(data: dict, claves_validas: tuple[str, ...]) -> list[str]:
    errores = [f"clave desconocida: {k}" for k in data if k not in claves_validas]
    errores += [f"falta: {k}" for k in claves_validas if k not in data]
    return errores


# --- fuente.yaml -----------------------------------------------------------


@dataclass(frozen=True)
class ConfigFuente:
    carpeta: str
    frecuencia_ms: float


_CLAVES_FUENTE = ("carpeta", "frecuencia_ms")


def validar_fuente(data: Any, archivo: str = "fuente.yaml") -> ConfigFuente:
    if not isinstance(data, dict):
        raise ConfigError(archivo, ["(raiz): se espera un mapa"])
    errores = _claves_invalidas(data, _CLAVES_FUENTE)
    if errores:
        raise ConfigError(archivo, errores)
    if not _texto_no_vacio(data["carpeta"]):
        errores.append("carpeta: se espera una ruta no vacia")
    if not _numero_positivo(data["frecuencia_ms"]):
        errores.append("frecuencia_ms: se espera un numero positivo finito")
    if errores:
        raise ConfigError(archivo, errores)
    return ConfigFuente(carpeta=data["carpeta"], frecuencia_ms=float(data["frecuencia_ms"]))


def cargar_fuente(ruta: str | Path) -> ConfigFuente:
    return validar_fuente(_leer_yaml(ruta), str(ruta))


# --- modelo.yaml -------------------------------------------------------------


@dataclass(frozen=True)
class ConfigModelo:
    modelo_ref: str
    pesos: str
    clases_ref: str
    preprocesamiento: str
    entorno: str


_CLAVES_MODELO = ("modelo_ref", "pesos", "clases_ref", "preprocesamiento", "entorno")


def validar_modelo(data: Any, archivo: str = "modelo.yaml") -> ConfigModelo:
    if not isinstance(data, dict):
        raise ConfigError(archivo, ["(raiz): se espera un mapa"])
    errores = _claves_invalidas(data, _CLAVES_MODELO)
    if errores:
        raise ConfigError(archivo, errores)
    errores += [
        f"{k}: se espera texto no vacio" for k in _CLAVES_MODELO if not _texto_no_vacio(data[k])
    ]
    if errores:
        raise ConfigError(archivo, errores)
    return ConfigModelo(**{k: data[k] for k in _CLAVES_MODELO})


def cargar_modelo(ruta: str | Path) -> ConfigModelo:
    return validar_modelo(_leer_yaml(ruta), str(ruta))


# --- confianza.yaml ----------------------------------------------------------


@dataclass(frozen=True)
class ConfigConfianza:
    umbral_inferior: float
    umbral_superior: float
    tamano_ventana: int
    minimo_muestras: int
    margen_cambio_sostenido: float
    ventanas_sostenidas: int


_CLAVES_CONFIANZA = (
    "umbral_inferior",
    "umbral_superior",
    "tamano_ventana",
    "minimo_muestras",
    "margen_cambio_sostenido",
    "ventanas_sostenidas",
)


def validar_confianza(data: Any, archivo: str = "confianza.yaml") -> ConfigConfianza:
    if not isinstance(data, dict):
        raise ConfigError(archivo, ["(raiz): se espera un mapa"])
    errores = _claves_invalidas(data, _CLAVES_CONFIANZA)
    if errores:
        raise ConfigError(archivo, errores)

    inferior, superior = data["umbral_inferior"], data["umbral_superior"]
    for nombre, valor in (("umbral_inferior", inferior), ("umbral_superior", superior)):
        es_numero = isinstance(valor, int | float) and not isinstance(valor, bool)
        if not (es_numero and math.isfinite(valor) and 0 <= valor <= 1):
            errores.append(f"{nombre}: se espera un numero en [0, 1]")
    if not errores and inferior >= superior:
        errores.append("umbral_inferior debe ser menor que umbral_superior")

    if not _entero_positivo(data["tamano_ventana"]):
        errores.append("tamano_ventana: se espera un entero positivo")
    if not _entero_positivo(data["minimo_muestras"]):
        errores.append("minimo_muestras: se espera un entero positivo")
    if (
        _entero_positivo(data["tamano_ventana"])
        and _entero_positivo(data["minimo_muestras"])
        and data["minimo_muestras"] > data["tamano_ventana"]
    ):
        errores.append("minimo_muestras no puede ser mayor que tamano_ventana")
    if not _numero_positivo(data["margen_cambio_sostenido"]):
        errores.append("margen_cambio_sostenido: se espera un numero positivo finito")
    if not _entero_positivo(data["ventanas_sostenidas"]):
        errores.append("ventanas_sostenidas: se espera un entero positivo")

    if errores:
        raise ConfigError(archivo, errores)
    return ConfigConfianza(
        umbral_inferior=float(inferior),
        umbral_superior=float(superior),
        tamano_ventana=data["tamano_ventana"],
        minimo_muestras=data["minimo_muestras"],
        margen_cambio_sostenido=float(data["margen_cambio_sostenido"]),
        ventanas_sostenidas=data["ventanas_sostenidas"],
    )


def cargar_confianza(ruta: str | Path) -> ConfigConfianza:
    return validar_confianza(_leer_yaml(ruta), str(ruta))


# --- alertas.yaml ------------------------------------------------------------

_TIPOS_REGLA = ("baja_confianza", "cambio_sostenido")
_CLAVES_REGLA = ("id", "tipo", "severidad", "accion_sugerida")


@dataclass(frozen=True)
class ReglaAlerta:
    id: str
    tipo: str
    severidad: str
    accion_sugerida: str


@dataclass(frozen=True)
class ConfigAlertas:
    version: int
    reglas: tuple[ReglaAlerta, ...]

    def regla(self, tipo: str) -> ReglaAlerta | None:
        return next((r for r in self.reglas if r.tipo == tipo), None)


def validar_alertas(data: Any, archivo: str = "alertas.yaml") -> ConfigAlertas:
    if not isinstance(data, dict):
        raise ConfigError(archivo, ["(raiz): se espera un mapa"])
    errores = _claves_invalidas(data, ("version", "reglas"))
    if errores:
        raise ConfigError(archivo, errores)
    if data["version"] != 1:
        errores.append(f"version: se espera 1, llego {data['version']!r}")

    reglas_data = data["reglas"]
    if not isinstance(reglas_data, list) or not reglas_data:
        raise ConfigError(archivo, [*errores, "reglas: se espera una lista no vacia"])

    reglas: list[ReglaAlerta] = []
    ids_vistos: set[str] = set()
    for i, r in enumerate(reglas_data):
        prefijo = f"reglas[{i}]"
        if not isinstance(r, dict):
            errores.append(f"{prefijo}: se espera un mapa")
            continue
        errores += [f"{prefijo}.{e}" for e in _claves_invalidas(r, _CLAVES_REGLA)]
        if any(e.startswith(prefijo) for e in errores):
            continue
        if not _texto_no_vacio(r["id"]):
            errores.append(f"{prefijo}.id: se espera texto no vacio")
        elif r["id"] in ids_vistos:
            errores.append(f"{prefijo}.id: duplicado ({r['id']!r})")
        else:
            ids_vistos.add(r["id"])
        if r["tipo"] not in _TIPOS_REGLA:
            errores.append(f"{prefijo}.tipo: se espera uno de {_TIPOS_REGLA}, llego {r['tipo']!r}")
        if not _texto_no_vacio(r["severidad"]):
            errores.append(f"{prefijo}.severidad: se espera texto no vacio")
        if not _texto_no_vacio(r["accion_sugerida"]):
            errores.append(f"{prefijo}.accion_sugerida: se espera texto no vacio")
        if not errores:
            reglas.append(ReglaAlerta(**{k: r[k] for k in _CLAVES_REGLA}))

    if errores:
        raise ConfigError(archivo, errores)
    return ConfigAlertas(version=data["version"], reglas=tuple(reglas))


def cargar_alertas(ruta: str | Path) -> ConfigAlertas:
    return validar_alertas(_leer_yaml(ruta), str(ruta))
