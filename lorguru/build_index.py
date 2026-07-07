# -*- coding: utf-8 -*-
"""Paso de BUILD del pipeline: descarga datos (con caché) y construye el
índice vectorial. Se corre explícitamente — al desplegar, o cuando cambian
los datos (parche nuevo) o el modelo de embeddings — nunca desde el servidor:

    python -m lorguru.build_index                # usa la caché de datos
    python -m lorguru.build_index --forzar-datos # re-descarga los sets
    python -m lorguru.build_index --reconstruir  # regenera los embeddings

El proceso que sirve (uvicorn lorguru.api:app) solo CARGA lo que este paso
deja en disco (data/ y chroma_db/); si falta, falla rápido con instrucciones.
"""
import argparse

from .ingesta import RUTA_CARTAS, cargar_cartas, cargar_glosario, descargar_datos
from .stores import MODELO_EMBEDDINGS, cargar_modelo_embeddings, construir_indice


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Construye el índice vectorial de LoR Guru.")
    parser.add_argument("--forzar-datos", action="store_true",
                        help="Re-descarga sets y glosario aunque estén en caché.")
    parser.add_argument("--reconstruir", action="store_true",
                        help="Borra y regenera la colección de embeddings.")
    args = parser.parse_args()

    descargar_datos(forzar=args.forzar_datos)
    df = cargar_cartas(RUTA_CARTAS)
    glosario = cargar_glosario()
    print(f"{len(df)} cartas coleccionables. "
          f"Modelo de embeddings: {MODELO_EMBEDDINGS}")

    modelo_st = cargar_modelo_embeddings()
    print(f"Dispositivo: {modelo_st.device}")
    construir_indice(df, glosario, modelo_st, reconstruir=args.reconstruir)
    print("Build terminado. La API ya puede arrancar: "
          "uvicorn lorguru.api:app")


if __name__ == "__main__":
    main()
