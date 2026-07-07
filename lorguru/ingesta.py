# -*- coding: utf-8 -*-
"""Obtención de datos: descarga con caché del Data Dragon (es_mx) y parseo.

Idéntico en lógica a la sección 2-3 del notebook de fase 1, con una adición
para la fase 3: las URLs de imagen de cada carta (campo `assets` del JSON).
"""
import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import requests

# Las rutas se anclan a la raíz del proyecto (el padre del paquete), para que
# funcionen sin importar desde dónde se invoque uvicorn/pytest.
RAIZ_PROYECTO = Path(__file__).resolve().parents[1]
RUTA_DATOS = RAIZ_PROYECTO / "data"
RUTA_CARTAS = RUTA_DATOS / "cards"
RUTA_GLOBALS = RUTA_DATOS / "globals-es_mx.json"

URL_BASE = "https://dd.b.pvp.net/latest/{}-es_mx.zip"

# La lista de sets no sigue un patrón numérico puro: existen set6cde y set7b.
SETS = [
    "set1", "set2", "set3", "set4", "set5", "set6",
    "set6cde", "set7", "set7b", "set8", "set9",
]


def descargar_bundle(nombre_bundle: str, ruta_interna: str, ruta_destino: Path,
                     forzar: bool = False) -> bool:
    """Descarga un bundle .zip del Data Dragon y extrae un solo JSON.

    Si el archivo destino ya existe (caché local) no descarga nada,
    salvo que forzar=True. Devuelve True si el archivo quedó disponible.
    """
    if ruta_destino.exists() and not forzar:
        print(f"  [caché] {ruta_destino.name} ya existe, no se descarga")
        return True

    url = URL_BASE.format(nombre_bundle)
    try:
        respuesta = requests.get(url, timeout=60)
    except requests.RequestException as e:
        print(f"  [error] {nombre_bundle}: {e}")
        return False

    if respuesta.status_code != 200:
        print(f"  [no disponible] {nombre_bundle} (HTTP {respuesta.status_code})")
        return False

    with zipfile.ZipFile(io.BytesIO(respuesta.content)) as z:
        if ruta_interna not in z.namelist():
            print(f"  [error] {nombre_bundle}: no contiene {ruta_interna}")
            return False
        datos = z.read(ruta_interna)

    ruta_destino.parent.mkdir(parents=True, exist_ok=True)
    ruta_destino.write_bytes(datos)
    print(f"  [descargado] {ruta_destino.name} ({len(datos) / 1024:.0f} KB)")
    return True


def descargar_datos(forzar: bool = False) -> None:
    """Descarga (con caché) todos los sets de cartas y el bundle core."""
    print("Sets de cartas:")
    for s in SETS:
        descargar_bundle(s, f"es_mx/data/{s}-es_mx.json",
                         RUTA_CARTAS / f"{s}.json", forzar)
    print("Bundle core (glosario):")
    descargar_bundle("core", "es_mx/data/globals-es_mx.json", RUTA_GLOBALS, forzar)


def _url_imagen(assets: list, clave: str) -> str:
    """Extrae la URL de imagen del primer asset de la carta ('' si no hay)."""
    if isinstance(assets, list) and assets:
        return assets[0].get(clave, "") or ""
    return ""


def cargar_cartas(carpeta: Path = RUTA_CARTAS) -> pd.DataFrame:
    """Lee todos los .json de `carpeta` y los combina en un DataFrame.

    Una fila por carta coleccionable (collectible=True). Además de las
    columnas del notebook, añade `imagen` (arte del juego) e `imagen_full`
    (ilustración completa) desde el campo `assets` — la fase 3 las muestra.
    """
    columnas = [
        "cardCode", "name", "cost", "attack", "health",
        "type", "supertype", "subtypes",
        "regions", "regionRefs", "rarity", "rarityRef",
        "keywords", "keywordRefs", "spellSpeed", "spellSpeedRef",
        "descriptionRaw", "levelupDescriptionRaw", "set",
    ]
    registros = []
    for archivo in sorted(carpeta.glob("*.json")):
        with open(archivo, encoding="utf-8") as f:
            registros.extend(json.load(f))
    df = pd.DataFrame(registros)
    df = df[df["collectible"]].copy()
    df["imagen"] = df["assets"].apply(_url_imagen, args=("gameAbsolutePath",))
    df["imagen_full"] = df["assets"].apply(_url_imagen, args=("fullAbsolutePath",))
    df = df[columnas + ["imagen", "imagen_full"]]
    df = df.drop_duplicates(subset="cardCode").reset_index(drop=True)
    return df


def cargar_glosario(ruta_globals: Path = RUTA_GLOBALS) -> dict:
    """Construye los lookups Ref <-> nombre en español desde globals-es_mx.json.

    Devuelve un dict con, por cada categoría (regiones, rarezas, keywords,
    sets, velocidades):
      - "<categoria>":      {ref: nombre_es}
      - "<categoria>_inv":  {nombre_es: ref}
    más "descripciones_keywords": {ref: {"nombre": ..., "descripcion": ...}}.
    """
    with open(ruta_globals, encoding="utf-8") as f:
        globales = json.load(f)

    categorias = {
        "regiones": "regions",
        "rarezas": "rarities",
        "keywords": "keywords",
        "sets": "sets",
        "velocidades": "spellSpeeds",
    }
    glosario = {}
    for nombre_cat, clave_json in categorias.items():
        ref_a_nombre = {
            e["nameRef"]: e["name"]
            for e in globales[clave_json]
            if e.get("name") and e["name"] != "Missing Translation"
        }
        glosario[nombre_cat] = ref_a_nombre
        glosario[nombre_cat + "_inv"] = {v: k for k, v in ref_a_nombre.items()}

    glosario["descripciones_keywords"] = {
        e["nameRef"]: {"nombre": e["name"], "descripcion": e.get("description", "")}
        for e in globales["keywords"]
        if e.get("name") and e["name"] != "Missing Translation"
    }
    return glosario
