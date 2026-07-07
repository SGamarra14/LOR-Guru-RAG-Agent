# -*- coding: utf-8 -*-
"""Fixtures compartidas: un TestClient de la API real, con lifespan.

El `with TestClient(app)` dispara el lifespan de FastAPI: los tests corren
contra la API completa (schemas, serialización, estado cargado), no contra
las funciones internas. Requiere el índice construido:
python -m lorguru.build_index
"""
import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from lorguru.api import app

load_dotenv()


@pytest.fixture(scope="session")
def cliente():
    with TestClient(app) as c:
        yield c
