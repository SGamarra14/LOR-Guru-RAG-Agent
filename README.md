# LoR Guru

Búsqueda de cartas de *Legends of Runeterra* en lenguaje natural (español):
filtros exactos para lo estructurado, embeddings para el texto de habilidades,
y un agente LLM con tool use que decide cuál usar.

Cada fase tiene dos entregables espejo: una **guía** para recrearla desde cero
(especificación sin código resuelto, con las decisiones de diseño explicadas)
y el **proyecto de referencia** funcionando, con los mismos nombres.

| Fase | Guía | Referencia | Estado |
|---|---|---|---|
| 1 — Notebook de prueba de concepto | [GUIA.md](GUIA.md) | [lor_guru_fase1.ipynb](lor_guru_fase1.ipynb) | ✅ Capa A 16/16, Capa B 14/16 |
| 2 — Módulos + tests + API FastAPI | [GUIA_FASE2.md](GUIA_FASE2.md) | [lorguru/](lorguru/) + [tests/](tests/) | ✅ Capa A 16/16, Capa B Claude 16/16 |
| 3 — UI (Next.js) + despliegue | [GUIA_FASE3.md](GUIA_FASE3.md) | [webapp/](webapp/) + [Dockerfile](Dockerfile) | ✅ (deploy real pendiente de cuentas) |

## Para correr (fase 2 + 3)

```bash
pip install -r requirements.txt

# 1. Paso de BUILD (una vez; descarga datos con caché y construye el índice
#    embebiendo las cartas con la API de Gemini — rota GEMINI_API_KEY_1/_2)
python -m lorguru.build_index

# 2. Servir la API (solo carga lo que dejó el build)
uvicorn lorguru.api:app --reload           # :8000

# 3. Frontend
cd webapp && npm install && npm run dev     # :3000

# 4. Regresión capa A (endpoints; hace embeddings de consulta vía API)
pytest
# 5. Regresión capa B (agente real; gasta la API del proveedor)
pytest -m agente -s
```

`.env` en la raíz (no se sube a git):

```
ANTHROPIC_API_KEY=sk-ant-...   # capa B con Claude (proveedor de referencia)
GEMINI_API_KEY=...             # embeddings del servidor + capa B con Gemini
GEMINI_API_KEY_1=...           # build del índice (rotación, ver abajo)
GEMINI_API_KEY_2=...
ORIGENES_CORS=http://localhost:3000
```

**Embeddings: API de Gemini (`gemini-embedding-001`, 768 dims).** Se migró
desde el modelo local `multilingual-e5-large` de la fase 2 para poder
hospedar barato — el servidor ya no carga un modelo de ~2.5 GB. Detalles y
el porqué: [GUIA_FASE2.md](GUIA_FASE2.md) §8 (nota de migración). El **build**
del índice rota `GEMINI_API_KEY_1` y `GEMINI_API_KEY_2` para respetar el RPM
del free tier (ideal: dos proyectos de Google Cloud separados → cuotas
independientes); el **servidor** usa `GEMINI_API_KEY` para embeber cada
consulta. Esa clave de embeddings es un costo del servidor, aparte del modelo
del agente.

La API del agente es **BYOK**: `/agente` recibe `proveedor`
(`anthropic`/`gemini`/`openai`), `modelo` opcional y la `api_key` del usuario
en el body; la clave no se persiste ni se loguea. `GET /proveedores` marca la
verificación **por modelo** (solo `claude-sonnet-5` corrió el set completo).
