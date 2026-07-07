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
from dataclasses import dataclass
from pathlib import Path

import chromadb
import pandas as pd
from sentence_transformers import SentenceTransformer

from .ingesta import RAIZ_PROYECTO, RUTA_CARTAS, RUTA_GLOBALS, cargar_cartas, cargar_glosario

# --- Modelo de embeddings -----------------------------------------------
# Elegido por el A/B de fase 2 (scripts/comparar_embeddings.py; tabla en
# GUIA_FASE2.md sección 8): e5-large iguala el set estándar del MiniLM
# (10/10) y lo cuadruplica en sensibilidad al fraseo (28/50 vs 7/50) —
# incluida la formulación "Otorgo Barrera" que falló en la capa B de fase 1.
# La familia E5 EXIGE estos prefijos en documentos y consultas.
MODELO_EMBEDDINGS = "intfloat/multilingual-e5-large"
PREFIJO_DOCUMENTO = "passage: "
PREFIJO_CONSULTA = "query: "

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


def cargar_modelo_embeddings() -> SentenceTransformer:
    return SentenceTransformer(MODELO_EMBEDDINGS)


def construir_indice(df, glosario, modelo_st, reconstruir: bool = False):
    """Construye (o completa) la colección Chroma. SOLO para el paso de build
    (`python -m lorguru.build_index`) — el servidor nunca llama esto."""
    cliente = chromadb.PersistentClient(path=RUTA_CHROMA)
    if reconstruir:
        try:
            cliente.delete_collection(NOMBRE_COLECCION)
        except Exception:
            pass
    coleccion = cliente.get_or_create_collection(
        NOMBRE_COLECCION,
        metadata={"hnsw:space": "cosine", "modelo": MODELO_EMBEDDINGS},
    )
    modelo_indice = (coleccion.metadata or {}).get("modelo", "")
    if coleccion.count() == len(df) and modelo_indice == MODELO_EMBEDDINGS:
        print(f"Índice ya construido ({coleccion.count()} vectores).")
        return coleccion

    if coleccion.count() > 0:  # a medias, desactualizado o de otro modelo
        cliente.delete_collection(NOMBRE_COLECCION)
        coleccion = cliente.get_or_create_collection(
            NOMBRE_COLECCION,
            metadata={"hnsw:space": "cosine", "modelo": MODELO_EMBEDDINGS},
        )

    textos = [construir_texto_carta(fila, glosario) for _, fila in df.iterrows()]
    print(f"Generando embeddings de {len(textos)} cartas con {MODELO_EMBEDDINGS}...")
    embeddings = modelo_st.encode(
        [PREFIJO_DOCUMENTO + t for t in textos],
        batch_size=64, show_progress_bar=True, normalize_embeddings=True,
    )
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
            embeddings=embeddings[i:i + TAMANO_LOTE].tolist(),
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
    if modelo_indice != MODELO_EMBEDDINGS:
        raise RuntimeError(
            f"El índice fue construido con '{modelo_indice}' pero el código usa "
            f"'{MODELO_EMBEDDINGS}'. Reconstrúyelo: "
            "python -m lorguru.build_index --reconstruir"
        )
    return coleccion


# --- Recursos compartidos -------------------------------------------------

@dataclass
class Recursos:
    """Todo lo que la API necesita cargado en memoria para servir."""
    df: pd.DataFrame
    glosario: dict
    modelo_st: SentenceTransformer
    coleccion: object


def cargar_recursos() -> Recursos:
    """Carga datos, glosario, modelo de embeddings e índice YA construido.

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
    modelo_st = cargar_modelo_embeddings()
    coleccion = cargar_indice(n_cartas_esperado=len(df))
    return Recursos(df=df, glosario=glosario, modelo_st=modelo_st,
                    coleccion=coleccion)


def buscar_semantica(recursos: Recursos, texto_consulta: str, top_k: int = 10,
                     filtro_metadata: dict = None) -> pd.DataFrame:
    """Búsqueda semántica, opcionalmente restringida por filtros exactos.

    Patrón híbrido validado en fase 1: filtrar exacto primero en el DataFrame
    y restringir Chroma al subconjunto vía where={"cardCode": {"$in": ...}}.
    """
    where = None
    if filtro_metadata:
        subconjunto = filtrar_cartas(recursos.df, **filtro_metadata)
        if subconjunto.empty:
            return subconjunto.assign(distancia=pd.Series(dtype=float))
        where = {"cardCode": {"$in": subconjunto["cardCode"].tolist()}}

    vector = recursos.modelo_st.encode(
        [PREFIJO_CONSULTA + texto_consulta], normalize_embeddings=True)
    resultado = recursos.coleccion.query(
        query_embeddings=vector.tolist(), n_results=top_k, where=where
    )
    codigos = resultado["ids"][0]
    if not codigos:
        return recursos.df.head(0).assign(distancia=pd.Series(dtype=float))
    salida = recursos.df.set_index("cardCode").loc[codigos].reset_index()
    salida["distancia"] = resultado["distances"][0]
    return salida
