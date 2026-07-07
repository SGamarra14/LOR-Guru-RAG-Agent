# -*- coding: utf-8 -*-
"""Capa A: las 16 consultas de evaluación como peticiones directas a los
endpoints, con los parámetros mapeados a mano (el "resultado ideal").

No gasta API externa. Es la red de seguridad de la modularización: si algo
se rompió al extraer el código del notebook, truena aquí.
Criterio de fase: 16/16.
"""
import pytest

from lorguru.evaluacion import CONSULTAS_EVALUACION


@pytest.mark.parametrize(
    "caso", CONSULTAS_EVALUACION, ids=[c["id"] for c in CONSULTAS_EVALUACION])
def test_capa_a(cliente, caso):
    ruta, payload = caso["peticion"]
    respuesta = cliente.post(ruta, json=payload)
    assert respuesta.status_code == 200, respuesta.text
    cartas = respuesta.json()["cartas"]
    assert caso["verificar"](cartas), (
        f"{caso['id']} ({caso['tipo']}): criterio no cumplido con "
        f"{len(cartas)} cartas — {caso['consulta']}"
    )


def test_salud(cliente):
    datos = cliente.get("/salud").json()
    assert datos["ok"] and datos["cartas"] > 1500


def test_proveedores_marca_no_verificados(cliente):
    """openai/GPT debe anunciarse como NO verificado hasta correr el set."""
    proveedores = {p["id"]: p for p in cliente.get("/proveedores").json()}
    assert set(proveedores) == {"anthropic", "gemini", "openai"}
    assert proveedores["openai"]["verificado"] is False


def test_filtro_invalido_da_422(cliente):
    respuesta = cliente.post("/cartas/filtrar", json={"costo_max": "tres"})
    assert respuesta.status_code == 422


def test_agente_sin_api_key_da_422(cliente):
    respuesta = cliente.post("/agente", json={"consulta": "hola"})
    assert respuesta.status_code == 422  # api_key es requerida por schema
