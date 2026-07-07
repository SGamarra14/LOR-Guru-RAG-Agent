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
| 2 — Módulos + tests + API FastAPI | [GUIA_FASE2.md](GUIA_FASE2.md) | [lorguru/](lorguru/) + [tests/](tests/) | ✅ (ver guía, sección de resultados) |
| 3 — UI (Next.js + Vercel AI SDK) | — | — | pendiente |

## Para correr la fase 2

```bash
pip install -r requirements.txt

# 1. Paso de BUILD (una vez; descarga datos con caché y construye el índice)
python -m lorguru.build_index

# 2. Servir la API (solo carga lo que dejó el build)
uvicorn lorguru.api:app --reload

# 3. Regresión capa A (sin gastar API externa)
pytest

# 4. Regresión capa B (agente real; gasta API — requiere claves en .env)
pytest -m agente -s
```

`.env` en la raíz (no se sube a git):

```
ANTHROPIC_API_KEY=sk-ant-...   # capa B con Claude (proveedor de referencia)
GEMINI_API_KEY=...             # capa B con Gemini
ORIGENES_CORS=http://localhost:3000
```

La API es **BYOK**: el endpoint `/agente` recibe `proveedor`
(`anthropic`/`gemini`/`openai`), `modelo` opcional y la `api_key` del usuario
en el body; la clave no se persiste ni se loguea. `GET /proveedores` indica
cuáles están verificados contra el set de evaluación (GPT está implementado
pero **sin verificar** — sin credenciales para correr el set).

Embeddings: `intfloat/multilingual-e5-large` local (elegido por A/B contra el
MiniLM de fase 1 — tabla en la guía). El modelo del agente es intercambiable;
el de embeddings no depende del proveedor.
