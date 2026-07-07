# -*- coding: utf-8 -*-
"""Exporta el schema OpenAPI de la API a webapp/openapi.json.

Los tipos de TypeScript del frontend se GENERAN desde este schema
(openapi-typescript), no se transcriben a mano — así no se desincronizan de
los schemas de Pydantic. Correr tras cualquier cambio en lorguru/api.py:

    python -m scripts.exportar_openapi
    cd webapp && npm run tipos
"""
import json
from pathlib import Path

from lorguru.api import app

destino = Path(__file__).resolve().parents[1] / "webapp" / "openapi.json"
destino.parent.mkdir(parents=True, exist_ok=True)
with open(destino, "w", encoding="utf-8") as f:
    json.dump(app.openapi(), f, ensure_ascii=False, indent=1)
print(f"Schema exportado: {destino}")
