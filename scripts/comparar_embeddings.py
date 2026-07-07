# -*- coding: utf-8 -*-
"""A/B de modelos de embeddings sobre el set de evaluación de la fase 1.

Compara el MiniLM multilingüe (baseline de fase 1) contra
multilingual-e5-large (el candidato local; voyage-3 y text-embedding-3-large
quedan documentados como alternativas de pago — no hay credenciales para
probarlos). Dos baterías:

1. **Set estándar**: los 10 casos semánticos/híbridos de la evaluación, con
   las consultas ya afinadas al estilo del texto de carta. Mide que el
   candidato no EMPEORE lo que ya funciona.
2. **Sensibilidad al fraseo**: las formulaciones que FALLARON en fase 1
   (consultas abstractas, y el "Otorgo Barrera" que hundió al agente en S4/S3
   de capa B). Mide si el candidato cierra la brecha entre lenguaje de
   usuario y lenguaje de carta — la debilidad conocida del MiniLM.

Corre en memoria (numpy), sin tocar el índice persistido:
    python -m scripts.comparar_embeddings
"""
import re

import numpy as np
from sentence_transformers import SentenceTransformer

from lorguru.ingesta import cargar_cartas, cargar_glosario
from lorguru.stores import construir_texto_carta, filtrar_cartas

MODELOS = {
    "MiniLM (baseline)": {
        "nombre": "paraphrase-multilingual-MiniLM-L12-v2",
        "prefijo_doc": "", "prefijo_query": "",
    },
    "e5-large": {
        "nombre": "intfloat/multilingual-e5-large",
        # La familia E5 exige estos prefijos en documentos y consultas.
        "prefijo_doc": "passage: ", "prefijo_query": "query: ",
    },
}

TOP_K = 10


def _txt(fila) -> str:
    return f"{fila['descriptionRaw']} {fila['levelupDescriptionRaw']}"


# (id, consulta, filtro_metadata, criterio_por_carta, minimo)
SET_ESTANDAR = [
    ("S1", "robar cartas de la mano o del mazo del oponente enemigo", None,
     lambda f: "Nab" in f["keywordRefs"] or re.search(r"roba|hurtar", _txt(f), re.I), 3),
    ("S2", "Curo a tu nexo", None,
     lambda f: "Drain" in f["keywordRefs"] or re.search(r"\bcur|\bsana", _txt(f), re.I), 3),
    ("S3", "Doy Barrera a un aliado", None,
     lambda f: "Barrier" in f["keywordRefs"] or "Barrera" in _txt(f), 3),
    ("S4", "Lanzo Aturdir a un enemigo", None,
     lambda f: re.search(r"aturd", _txt(f), re.I), 3),
    ("S5", "Inflijo 2 de daño a TODAS las unidades", None,
     lambda f: re.search(r"daño a tod|a todos los enemigos", _txt(f), re.I), 3),
    ("S6", "revivir invocar de nuevo un aliado que murió esta partida", None,
     lambda f: re.search(r"reviv|que murió|que hayan muerto", _txt(f), re.I), 2),
    ("H1", "hacer daño al nexo enemigo", dict(tipo="Hechizo", costo_max=3),
     lambda f: re.search(r"nexo enemigo", _txt(f), re.I), 2),
    ("H2", "dar bonificación de ataque y vida a otros aliados",
     dict(region="Demacia", tipo="Unidad"),
     lambda f: re.search(r"\+\d+\|\+\d+", _txt(f)), 3),
    ("H3", "robar cartas o saquear al oponente",
     dict(region="Bilgewater", tipo="Unidad", costo_max=3),
     lambda f: "Nab" in f["keywordRefs"] or "Plunder" in f["keywordRefs"]
               or re.search(r"roba|hurt|pillaje", _txt(f), re.I), 2),
    ("H4", "convocar cartas celestiales", dict(region="Targon"),
     lambda f: re.search(r"celestial|convoc", _txt(f), re.I), 3),
]

# Las formulaciones que fallaron en fase 1 (y el criterio de qué debería
# recuperar cada una). Aquí NO se exige pasar/fallar: se cuentan aciertos@10.
SENSIBILIDAD_FRASEO = [
    ("Otorgo Barrera a un aliado (fraseo del agente, S3 capa B)",
     "Otorgo Barrera a un aliado",
     lambda f: "Barrier" in f["keywordRefs"] or "Barrera" in _txt(f)),
    ("abstracta: aturdir para que no ataque (fase 1)",
     "aturdir una unidad enemiga para que no pueda atacar ni bloquear",
     lambda f: re.search(r"aturd", _txt(f), re.I)),
    ("abstracta: curar sanar mi nexo (fase 1)",
     "curar sanar restaurar vida a mi nexo",
     lambda f: "Drain" in f["keywordRefs"] or re.search(r"\bcur|\bsana", _txt(f), re.I)),
    ("abstracta: daño a todas a la vez (fase 1)",
     "hacer daño a todas las unidades enemigas a la vez",
     lambda f: re.search(r"daño a tod|a todos los enemigos", _txt(f), re.I)),
    ("usuario casual: quitar el turno a un enemigo",
     "cartas para dejar a un enemigo sin poder hacer nada este turno",
     lambda f: re.search(r"aturd|helar", _txt(f), re.I)),
]


def evaluar_modelo(etiqueta, config, df, textos):
    print(f"\n===== {etiqueta} ({config['nombre']})")
    modelo = SentenceTransformer(config["nombre"])
    docs = modelo.encode([config["prefijo_doc"] + t for t in textos],
                         batch_size=32, show_progress_bar=True,
                         normalize_embeddings=True)

    def top_k(consulta, filtro):
        q = modelo.encode([config["prefijo_query"] + consulta],
                          normalize_embeddings=True)[0]
        indices = np.arange(len(df))
        if filtro:
            codigos = set(filtrar_cartas(df, **filtro)["cardCode"])
            indices = np.array([i for i in indices
                                if df.iloc[i]["cardCode"] in codigos])
            if len(indices) == 0:
                return df.head(0)
        similitudes = docs[indices] @ q
        orden = indices[np.argsort(-similitudes)[:TOP_K]]
        return df.iloc[orden]

    pasados = 0
    for id_, consulta, filtro, criterio, minimo in SET_ESTANDAR:
        resultado = top_k(consulta, filtro)
        hits = sum(bool(criterio(f)) for _, f in resultado.iterrows())
        ok = hits >= minimo
        pasados += ok
        print(f"  [{'PASA' if ok else 'FALLA'}] {id_}: {hits}/{TOP_K} aciertos "
              f"(mínimo {minimo})")
    print(f"  Set estándar: {pasados}/{len(SET_ESTANDAR)}")

    total_hits = 0
    for nombre, consulta, criterio in SENSIBILIDAD_FRASEO:
        resultado = top_k(consulta, None)
        hits = sum(bool(criterio(f)) for _, f in resultado.iterrows())
        total_hits += hits
        print(f"  [fraseo] {hits}/{TOP_K}: {nombre}")
    print(f"  Sensibilidad al fraseo (suma de aciertos@10): "
          f"{total_hits}/{len(SENSIBILIDAD_FRASEO) * TOP_K}")
    return pasados, total_hits


def main():
    df = cargar_cartas()
    glosario = cargar_glosario()
    textos = [construir_texto_carta(fila, glosario) for _, fila in df.iterrows()]
    print(f"{len(df)} cartas.")
    resumen = {}
    for etiqueta, config in MODELOS.items():
        resumen[etiqueta] = evaluar_modelo(etiqueta, config, df, textos)
    print("\n===== RESUMEN")
    for etiqueta, (estandar, fraseo) in resumen.items():
        print(f"  {etiqueta}: set estándar {estandar}/{len(SET_ESTANDAR)}, "
              f"fraseo {fraseo}/{len(SENSIBILIDAD_FRASEO) * TOP_K}")


if __name__ == "__main__":
    main()
