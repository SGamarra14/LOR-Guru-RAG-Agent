# -*- coding: utf-8 -*-
"""Paso de BUILD del pipeline: descarga datos (con caché) y construye el
índice vectorial embebiendo las cartas con la API de Gemini. Se corre
explícitamente — al desplegar, o cuando cambian los datos (parche nuevo) o el
modelo/dimensiones de embeddings — nunca desde el servidor:

    python -m lorguru.build_index                # usa la caché de datos
    python -m lorguru.build_index --forzar-datos # re-descarga los sets
    python -m lorguru.build_index --reconstruir  # regenera los embeddings

Claves: usa GEMINI_API_KEY_1 y GEMINI_API_KEY_2 (rotadas para respetar el RPM
del free tier; ver lorguru/embeddings.py). Si no están, cae a GEMINI_API_KEY.
El proceso que sirve (uvicorn lorguru.api:app) solo CARGA el chroma_db/ que
este paso deja en disco; si falta, falla rápido con instrucciones.
"""
import argparse
import os

from dotenv import load_dotenv

from .ingesta import RUTA_CARTAS, cargar_cartas, cargar_glosario, descargar_datos
from .stores import TAG_INDICE, construir_indice


def _claves_build() -> list[str]:
    """Claves para el build: GEMINI_API_KEY_1/_2, o GEMINI_API_KEY como fallback."""
    claves = [os.environ.get("GEMINI_API_KEY_1"), os.environ.get("GEMINI_API_KEY_2")]
    claves = [k for k in claves if k]
    if not claves:
        base = os.environ.get("GEMINI_API_KEY")
        if base:
            print("Aviso: no hay GEMINI_API_KEY_1/_2; uso GEMINI_API_KEY (más lento).")
            claves = [base]
    return claves


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Construye el índice vectorial de LoR Guru (embeddings Gemini).")
    parser.add_argument("--forzar-datos", action="store_true",
                        help="Re-descarga sets y glosario aunque estén en caché.")
    parser.add_argument("--reconstruir", action="store_true",
                        help="Borra y regenera la colección de embeddings.")
    args = parser.parse_args()

    load_dotenv()
    claves = _claves_build()
    if not claves:
        raise SystemExit(
            "Faltan claves de Gemini. Define GEMINI_API_KEY_1 y GEMINI_API_KEY_2 "
            "(o al menos GEMINI_API_KEY) en el .env o el entorno."
        )

    descargar_datos(forzar=args.forzar_datos)
    df = cargar_cartas(RUTA_CARTAS)
    glosario = cargar_glosario()
    print(f"{len(df)} cartas coleccionables. Embeddings: {TAG_INDICE} "
          f"con {len(claves)} clave(s).")

    construir_indice(df, glosario, claves, reconstruir=args.reconstruir)
    print("Build terminado. La API ya puede arrancar: uvicorn lorguru.api:app")


if __name__ == "__main__":
    main()
