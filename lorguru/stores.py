# -*- coding: utf-8 -*-
"""Los dos stores: estructurado (DataFrame) y vectorial (Chroma).

Decisión de fase 2 (revisitada): el store estructurado SIGUE siendo un
DataFrame de pandas en memoria, cargado una sola vez al arrancar la API.
Razones: es de solo-lectura (los datos cambian por parche, no por request),
son ~1,650 filas (~5 MB), y las columnas-lista (regionRefs, keywordRefs)
obligarían en SQLite a tablas puente o JSON embebido sin ganar nada a esta
escala. El punto de corte real sería necesitar escrituras concurrentes o
varios procesos compartiendo estado — ninguno aplica aquí.

Separación indexado/servido (fase 2): `construir_indice` solo se usa desde
`python -m lorguru.build_index` (paso de build explícito). El proceso que
sirve la API llama a `cargar_recursos`, que CARGA el índice ya construido y
falla rápido —con instrucciones— si no existe. El servidor nunca decide si
reconstruir.
"""
import os
from dataclasses import dataclass

import chromadb
import pandas as pd

from . import embeddings
from .ingesta import RAIZ_PROYECTO, RUTA_CARTAS, RUTA_GLOBALS, cargar_cartas, cargar_glosario

# --- Modelo de embeddings -----------------------------------------------
# Historia: fase 1 MiniLM → fase 2 e5-large local (A/B en
# scripts/comparar_embeddings.py, tabla en GUIA_FASE2.md §8) → migración
# 2026-07 a la API de Gemini (gemini-embedding-001) para poder hospedar
# barato: el servidor ya no carga un modelo de ~2.5 GB. El "task type"
# RETRIEVAL_DOCUMENT/QUERY cumple el papel que tenían los prefijos de E5.
# El tag guardado en la colección incluye las dimensiones: si cambian,
# cargar_indice exige reconstruir.
MODELO_EMBEDDINGS = embeddings.MODELO_EMBEDDINGS
TAG_INDICE = f"{MODELO_EMBEDDINGS}@{embeddings.DIMENSIONES}"

RUTA_CHROMA = str(RAIZ_PROYECTO / "chroma_db")
NOMBRE_COLECCION = "cartas_lor"


# --- Store estructurado ---------------------------------------------------

def filtrar_cartas(df, region=None, costo_min=None, costo_max=None,
                   ataque_min=None, ataque_max=None, vida_min=None, vida_max=None,
                   tipo=None, supertipo=None, keywords=None, rareza=None,
                   velocidad=None):
    """Filtros exactos sobre el DataFrame de cartas.

    region/rareza/velocidad/keywords usan valores *Ref* (inglés, estables);
    tipo/supertipo los valores localizados del dato. keywords exige que la
    carta tenga TODAS las indicadas. Devuelve ordenado por coste.
    """
    mascara = pd.Series(True, index=df.index)
    if region is not None:
        mascara &= df["regionRefs"].apply(lambda refs: region in refs)
    if costo_min is not None:
        mascara &= df["cost"] >= costo_min
    if costo_max is not None:
        mascara &= df["cost"] <= costo_max
    if ataque_min is not None:
        mascara &= df["attack"] >= ataque_min
    if ataque_max is not None:
        mascara &= df["attack"] <= ataque_max
    if vida_min is not None:
        mascara &= df["health"] >= vida_min
    if vida_max is not None:
        mascara &= df["health"] <= vida_max
    if tipo is not None:
        mascara &= df["type"].str.lower() == tipo.lower()
    if supertipo is not None:
        mascara &= df["supertype"].str.lower() == supertipo.lower()
    if rareza is not None:
        mascara &= df["rarityRef"].str.lower() == rareza.lower()
    if velocidad is not None:
        mascara &= df["spellSpeedRef"].str.lower() == velocidad.lower()
    if keywords:
        mascara &= df["keywordRefs"].apply(
            lambda refs: all(k in refs for k in keywords)
        )
    return df[mascara].sort_values("cost").reset_index(drop=True)


# --- Store vectorial ------------------------------------------------------

def construir_texto_carta(fila, glosario) -> str:
    """Texto en lenguaje natural que representa a la carta para el embedding.

    Solo lenguaje natural (nombre, tipo, descripciones, descripciones
    oficiales de sus keywords) — nunca números de stats: esos viven en la
    metadata y se filtran exacto.
    """
    partes = [f"{fila['name']}. {fila['type']}."]
    if fila["descriptionRaw"]:
        partes.append(fila["descriptionRaw"])
    if fila["levelupDescriptionRaw"]:
        partes.append("Subida de nivel: " + fila["levelupDescriptionRaw"])
    descripciones = glosario["descripciones_keywords"]
    for ref in fila["keywordRefs"]:
        if ref in descripciones:
            kw = descripciones[ref]
            partes.append(f"{kw['nombre']}: {kw['descripcion']}")
    return " ".join(partes)


def construir_indice(df, glosario, claves, reconstruir: bool = False):
    """Construye (o completa) la colección Chroma. SOLO para el paso de build
    (`python -m lorguru.build_index`) — el servidor nunca llama esto.

    `claves`: lista de API keys de Gemini (GEMINI_API_KEY_1/_2) que se rotan
    para respetar el RPM del free tier (ver lorguru/embeddings.py)."""
    cliente = chromadb.PersistentClient(path=RUTA_CHROMA)
    if reconstruir:
        try:
            cliente.delete_collection(NOMBRE_COLECCION)
        except Exception:
            pass
    coleccion = cliente.get_or_create_collection(
        NOMBRE_COLECCION,
        metadata={"hnsw:space": "cosine", "modelo": TAG_INDICE},
    )
    modelo_indice = (coleccion.metadata or {}).get("modelo", "")
    if coleccion.count() == len(df) and modelo_indice == TAG_INDICE:
        print(f"Índice ya construido ({coleccion.count()} vectores).")
        return coleccion

    if coleccion.count() > 0:  # a medias, desactualizado o de otro modelo
        cliente.delete_collection(NOMBRE_COLECCION)
        coleccion = cliente.get_or_create_collection(
            NOMBRE_COLECCION,
            metadata={"hnsw:space": "cosine", "modelo": TAG_INDICE},
        )

    textos = [construir_texto_carta(fila, glosario) for _, fila in df.iterrows()]
    print(f"Generando embeddings de {len(textos)} cartas con {TAG_INDICE}...")
    vectores = embeddings.embed_documentos(textos, claves)
    metadatas = [
        {
            "cardCode": fila["cardCode"],
            "cost": int(fila["cost"]),
            "attack": int(fila["attack"]),
            "health": int(fila["health"]),
            "type": fila["type"],
            "rarityRef": fila["rarityRef"],
            "regiones": "|".join(fila["regionRefs"]),
        }
        for _, fila in df.iterrows()
    ]
    TAMANO_LOTE = 500
    for i in range(0, len(df), TAMANO_LOTE):
        coleccion.add(
            ids=df["cardCode"].iloc[i:i + TAMANO_LOTE].tolist(),
            embeddings=vectores[i:i + TAMANO_LOTE],
            documents=textos[i:i + TAMANO_LOTE],
            metadatas=metadatas[i:i + TAMANO_LOTE],
        )
    print(f"Índice construido: {coleccion.count()} vectores.")
    return coleccion


def cargar_indice(n_cartas_esperado: int):
    """Carga el índice ya construido. Falla rápido y con instrucciones si no
    existe, está incompleto, o fue construido con otro modelo de embeddings."""
    cliente = chromadb.PersistentClient(path=RUTA_CHROMA)
    try:
        coleccion = cliente.get_collection(NOMBRE_COLECCION)
    except Exception:
        raise RuntimeError(
            f"No existe el índice vectorial '{NOMBRE_COLECCION}' en {RUTA_CHROMA}. "
            "Constrúyelo primero: python -m lorguru.build_index"
        )
    if coleccion.count() != n_cartas_esperado:
        raise RuntimeError(
            f"El índice tiene {coleccion.count()} vectores pero hay "
            f"{n_cartas_esperado} cartas. Reconstrúyelo: "
            "python -m lorguru.build_index --reconstruir"
        )
    modelo_indice = (coleccion.metadata or {}).get("modelo", "")
    if modelo_indice != TAG_INDICE:
        raise RuntimeError(
            f"El índice fue construido con '{modelo_indice}' pero el código usa "
            f"'{TAG_INDICE}'. Reconstrúyelo: "
            "python -m lorguru.build_index --reconstruir"
        )
    return coleccion


# --- Recursos compartidos -------------------------------------------------

@dataclass
class Recursos:
    """Todo lo que la API necesita en memoria para servir. Ya no carga un
    modelo pesado: solo la clave con la que embeber las consultas (costo del
    servidor, no BYOK — el LLM del agente sí es BYOK)."""
    df: pd.DataFrame
    glosario: dict
    clave_embeddings: str
    coleccion: object


def cargar_recursos() -> Recursos:
    """Carga datos, glosario e índice YA construido, y toma del entorno la
    clave de embeddings del servidor (GEMINI_API_KEY).

    Es lo único que llama el proceso que sirve (lifespan de FastAPI, tests).
    No descarga datos ni construye índices: si falta algo, RuntimeError con
    el comando a correr.
    """
    if not RUTA_GLOBALS.exists() or not any(RUTA_CARTAS.glob("*.json")):
        raise RuntimeError(
            f"No hay datos en {RUTA_CARTAS.parent}. "
            "Descárgalos y construye el índice: python -m lorguru.build_index"
        )
    df = cargar_cartas()
    glosario = cargar_glosario()
    coleccion = cargar_indice(n_cartas_esperado=len(df))
    # No falla si no está: /cartas/filtrar no la usa. buscar_semantica sí, y
    # dará un error claro en ese momento si falta.
    clave = os.environ.get("GEMINI_API_KEY", "")
    return Recursos(df=df, glosario=glosario, clave_embeddings=clave,
                    coleccion=coleccion)


def buscar_semantica(recursos: Recursos, texto_consulta: str, top_k: int = 10,
                     filtro_metadata: dict = None) -> pd.DataFrame:
    """Búsqueda semántica, opcionalmente restringida por filtros exactos.

    Patrón híbrido validado en fase 1: filtrar exacto primero en el DataFrame
    y restringir Chroma al subconjunto vía where={"cardCode": {"$in": ...}}.
    La consulta se embebe con la API de Gemini (taskType RETRIEVAL_QUERY).
    """
    where = None
    if filtro_metadata:
        subconjunto = filtrar_cartas(recursos.df, **filtro_metadata)
        if subconjunto.empty:
            return subconjunto.assign(distancia=pd.Series(dtype=float))
        where = {"cardCode": {"$in": subconjunto["cardCode"].tolist()}}

    vector = embeddings.embed_consulta(texto_consulta, recursos.clave_embeddings)
    resultado = recursos.coleccion.query(
        query_embeddings=[vector], n_results=top_k, where=where
    )
    codigos = resultado["ids"][0]
    if not codigos:
        return recursos.df.head(0).assign(distancia=pd.Series(dtype=float))
    salida = recursos.df.set_index("cardCode").loc[codigos].reset_index()
    salida["distancia"] = resultado["distances"][0]
    return salida
