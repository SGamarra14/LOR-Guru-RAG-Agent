# -*- coding: utf-8 -*-
"""Capa B: las 16 consultas contra el endpoint /agente con el proveedor real.

Gasta la API del proveedor — por eso está tras el marker `agente`:

    pytest -m agente -s

Se evalúan las cartas que el agente CITA en su respuesta final (el criterio
corregido de la fase 2), con el mismo `verificar` de la capa A. El criterio
de fase permite exploración imperfecta: se exige el TOTAL (>=14/16 para
Claude, el proveedor de referencia), no cada caso individual.
"""
import os
import time

import pytest

from lorguru.evaluacion import CONSULTAS_EVALUACION

UMBRAL = 14  # criterio de fase: capa B >= 14/16

# (proveedor, variable de entorno, pausa entre casos en segundos).
# La pausa existe por los tiers gratuitos con rate limit por minuto (Gemini
# free: ~10 requests/min, y el agente hace 2-3 por consulta): sin ritmo, la
# evaluación truena por 429 y mide la cuota, no al agente.
PROVEEDORES_EVAL = [
    ("anthropic", "ANTHROPIC_API_KEY", 0),
    ("gemini", "GEMINI_API_KEY", 10),
]

REINTENTOS_429 = 5
ESPERA_429 = 25  # segundos entre reintentos cuando el proveedor devuelve 429


def _post_con_reintentos(cliente, payload):
    for intento in range(REINTENTOS_429):
        r = cliente.post("/agente", json=payload)
        if r.status_code != 429:
            return r
        print(f"  [429] rate limit del proveedor; reintento "
              f"{intento + 1}/{REINTENTOS_429} en {ESPERA_429}s")
        time.sleep(ESPERA_429)
    return r


@pytest.mark.agente
@pytest.mark.parametrize("proveedor,variable,pausa", PROVEEDORES_EVAL,
                         ids=[p for p, _, _ in PROVEEDORES_EVAL])
def test_capa_b(cliente, proveedor, variable, pausa):
    api_key = os.environ.get(variable)
    if not api_key:
        pytest.skip(f"Sin {variable} en el entorno: no se evalúa {proveedor}.")

    resultados = []
    for caso in CONSULTAS_EVALUACION:
        if pausa:
            time.sleep(pausa)
        r = _post_con_reintentos(cliente, {
            "consulta": caso["consulta"],
            "proveedor": proveedor,
            "api_key": api_key,
        })
        if r.status_code != 200:
            resultados.append((caso["id"], False, f"HTTP {r.status_code}", ""))
            continue
        datos = r.json()
        ok = bool(caso["verificar"](datos["cartas"]))
        tools = " + ".join(l["tool"] for l in datos["llamadas"])
        resultados.append((caso["id"], ok, datos["metodo_cartas"], tools))
        print(f"[{'PASA' if ok else 'FALLA'}] {caso['id']} "
              f"({datos['metodo_cartas']}, {len(datos['cartas'])} cartas, "
              f"{tools}): {caso['consulta']}")

    aciertos = sum(1 for _, ok, _, _ in resultados if ok)
    tabla = "\n".join(f"  {i} {'PASA' if ok else 'FALLA':5} metodo={m} tools={t}"
                      for i, ok, m, t in resultados)
    print(f"\n{proveedor}: {aciertos}/16")
    assert aciertos >= UMBRAL, (
        f"{proveedor}: {aciertos}/16, por debajo del umbral {UMBRAL}.\n{tabla}"
    )
