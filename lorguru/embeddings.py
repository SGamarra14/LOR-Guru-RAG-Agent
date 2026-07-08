# -*- coding: utf-8 -*-
"""Cliente de embeddings de Gemini (gemini-embedding-001) por REST directo.

Por qué REST y no LiteLLM/SDK: necesitamos control total de `taskType`
(RETRIEVAL_DOCUMENT vs RETRIEVAL_QUERY — el equivalente a los prefijos
"passage:"/"query:" de E5) y de `outputDimensionality`, y no queremos sumar
dependencias (requests ya está). LiteLLM se queda solo para el LLM del agente.

Migración (2026-07): reemplaza a intfloat/multilingual-e5-large local. Motivo:
sacar el modelo de ~2.5 GB del contenedor para poder hospedar barato — el
servidor deja de necesitar torch/sentence-transformers. Contrapartida: cada
consulta semántica hace ahora UNA llamada de red (barata: ~10-20 tokens).

Límites (free tier, gemini-embedding-001): ~100 requests/min POR PROYECTO, y
una sola entrada de texto por request. El build de las ~1,650 cartas rota dos
claves (GEMINI_API_KEY_1/_2) en dos hilos, cada uno paceado bajo 100/min:
- Si las claves son de PROYECTOS separados (recomendado), suman ~170/min.
- Si comparten proyecto, el backoff ante 429 las auto-throttlea a ~100/min:
  más lento, pero termina igual. No hay forma de detectar la diferencia desde
  aquí, así que el código es correcto en ambos casos.
"""
import threading
import time

import numpy as np
import requests

MODELO_EMBEDDINGS = "gemini-embedding-001"
# 768 es el tamaño recomendado por Google para retrieval (MRL): buena calidad,
# índice liviano. Con dimensiones < 3072 hay que normalizar a mano (lo hacemos).
DIMENSIONES = 768

_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODELO_EMBEDDINGS}:embedContent"

# Pace por clave: 100/min es el techo del free tier; 0.72s ≈ 83/min deja margen.
_INTERVALO_MIN_S = 0.72
_REINTENTOS_429 = 6


def _normalizar(vector: list[float]) -> list[float]:
    v = np.asarray(vector, dtype=np.float32)
    norma = np.linalg.norm(v)
    return (v / norma).tolist() if norma > 0 else v.tolist()


def _embed_una(texto: str, task_type: str, api_key: str) -> list[float]:
    """Una llamada a embedContent, con backoff ante 429. Nunca incluye la
    api_key en los mensajes de error."""
    cuerpo = {
        "model": f"models/{MODELO_EMBEDDINGS}",
        "content": {"parts": [{"text": texto}]},
        "taskType": task_type,
        "outputDimensionality": DIMENSIONES,
    }
    espera = 2.0
    for intento in range(_REINTENTOS_429):
        try:
            r = requests.post(_URL, params={"key": api_key}, json=cuerpo, timeout=30)
        except requests.RequestException as e:
            raise RuntimeError(f"Red al llamar embeddings Gemini: {type(e).__name__}")
        if r.status_code == 200:
            return _normalizar(r.json()["embedding"]["values"])
        if r.status_code == 429:
            time.sleep(espera)
            espera = min(espera * 2, 60)
            continue
        # 400/401/403/... → error accionable sin filtrar la clave
        detalle = ""
        try:
            detalle = r.json().get("error", {}).get("message", "")[:180]
        except Exception:
            detalle = r.text[:180]
        raise RuntimeError(f"Gemini embeddings HTTP {r.status_code}: {detalle}")
    raise RuntimeError("Gemini embeddings: agotados los reintentos por 429 "
                       "(¿cuota diaria del free tier agotada?)")


def embed_consulta(texto: str, api_key: str) -> list[float]:
    """Embebe UNA consulta de usuario (taskType RETRIEVAL_QUERY)."""
    if not api_key:
        raise RuntimeError(
            "Falta GEMINI_API_KEY para embeber la consulta. El modelo de "
            "embeddings es un costo del servidor (no BYOK): define la clave "
            "en el entorno del backend."
        )
    return _embed_una(texto, "RETRIEVAL_QUERY", api_key)


def _worker_documentos(indices, textos, api_key, salida, errores):
    """Embebe un subconjunto de textos con una clave, paceado bajo el RPM."""
    proximo = 0.0
    for i in indices:
        ahora = time.monotonic()
        if ahora < proximo:
            time.sleep(proximo - ahora)
        proximo = time.monotonic() + _INTERVALO_MIN_S
        try:
            salida[i] = _embed_una(textos[i], "RETRIEVAL_DOCUMENT", api_key)
        except Exception as e:  # noqa: BLE001
            errores.append(str(e))
            return


def embed_documentos(textos: list[str], claves: list[str], verbose: bool = True):
    """Embebe todos los textos (taskType RETRIEVAL_DOCUMENT), repartiendo el
    trabajo entre las claves dadas (una por hilo). Devuelve lista de vectores
    en el MISMO orden que `textos`.

    Reparte round-robin (clave i toma los índices i, i+n, i+2n…): si una clave
    va más lenta por 429, el desbalance es menor que partir en bloques.
    """
    claves = [k for k in claves if k]
    if not claves:
        raise RuntimeError("No hay claves de Gemini para construir el índice "
                           "(define GEMINI_API_KEY_1 y GEMINI_API_KEY_2).")

    salida: list = [None] * len(textos)
    errores: list = []
    hilos = []
    for offset, clave in enumerate(claves):
        indices = list(range(offset, len(textos), len(claves)))
        h = threading.Thread(
            target=_worker_documentos,
            args=(indices, textos, clave, salida, errores),
        )
        h.start()
        hilos.append(h)

    if verbose:
        total = len(textos)
        while any(h.is_alive() for h in hilos):
            hechos = sum(1 for v in salida if v is not None)
            print(f"  embeddings: {hechos}/{total}", end="\r", flush=True)
            time.sleep(2.0)
    for h in hilos:
        h.join()

    if errores:
        raise RuntimeError(f"Fallo al embeber documentos: {errores[0]}")
    if any(v is None for v in salida):
        raise RuntimeError("Quedaron textos sin embeber (revisa cuota/claves).")
    if verbose:
        print(f"  embeddings: {len(textos)}/{len(textos)} listos.")
    return salida
