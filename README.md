# LoR Guru

**Busca cartas de _Legends of Runeterra_ describiéndolas en español natural.**
En vez de filtros manuales o un buscador de texto exacto, un agente LLM decide
—según tu consulta— si usar filtros estructurados, búsqueda semántica, o ambos.

> _"hechizos baratos que hagan daño al nexo enemigo"_, _"unidades de Jonia con
> Evasión para un mazo agresivo"_, _"cartas que revivan aliados que ya
> murieron"_ → el agente encuentra las cartas y explica por qué.

Proyecto de portafolio construido en **tres fases**, cada una con una **guía**
(especificación sin código, para reconstruirla desde cero) y su **proyecto de
referencia** funcionando.

## Stack

| Capa | Tecnología |
|---|---|
| Frontend | Next.js 16 · TypeScript · Tailwind v4 · tema propio estilo LoR |
| Backend | FastAPI · Pydantic · SSE (streaming por pasos) |
| Agente | LiteLLM (multi-proveedor BYOK) · tool use |
| Datos | Data Dragon (es_mx) · pandas · Chroma |
| Embeddings | API de Gemini `gemini-embedding-001` |
| Tests | pytest — set de evaluación de 16 consultas en dos capas |

## Fases

| Fase | Guía | Referencia |
|---|---|---|
| 1 — Notebook de prueba de concepto | [docs/GUIA_FASE1.md](docs/GUIA_FASE1.md) | [docs/lor_guru_fase1.ipynb](docs/lor_guru_fase1.ipynb) |
| 2 — Módulos + tests + API FastAPI | [docs/GUIA_FASE2.md](docs/GUIA_FASE2.md) | [lorguru/](lorguru/) · [tests/](tests/) |
| 3 — UI (Next.js) + despliegue | [docs/GUIA_FASE3.md](docs/GUIA_FASE3.md) | [webapp/](webapp/) · [Dockerfile](Dockerfile) |

## Estructura

```
lorguru/          Paquete del backend
  ingesta.py        Descarga con caché + parseo del Data Dragon
  stores.py         Filtro exacto (pandas) + búsqueda semántica (Chroma)
  embeddings.py     Cliente de la API de embeddings de Gemini
  agente.py         Tools, system prompt y loop de tool use (LiteLLM, BYOK)
  evaluacion.py     Las 16 consultas del set de evaluación
  build_index.py    Paso de build del índice (python -m lorguru.build_index)
  api.py            FastAPI: endpoints, schemas, CORS, SSE
webapp/           Frontend Next.js (consume la API)
tests/            Regresión: capa A (endpoints) y capa B (agente real)
scripts/          Utilidades (export OpenAPI, A/B de embeddings)
docs/             Guías de las tres fases + notebook de la fase 1
Dockerfile        Imagen del backend (índice ya construido, sin torch)
```

`data/` (cartas descargadas) y `chroma_db/` (índice) se generan con el build y
**no** están en el repo — se reconstruyen con un comando.

## Correr en local

```bash
pip install -r requirements.txt
cp .env.example .env          # y rellena tus claves (ver abajo)

python -m lorguru.build_index         # una vez: descarga datos + construye índice
uvicorn lorguru.api:app --reload      # API en :8000

cd webapp && npm install && npm run dev   # UI en :3000
```

Pruebas:

```bash
pytest                # capa A: los endpoints contra el set de evaluación
pytest -m agente -s   # capa B: el agente real (gasta la API; claves en .env)
```

## Variables de entorno

Todas van en `.env` (local) o en el panel del host (producción) — **nunca en
el código ni en el repo**. Ver [`.env.example`](.env.example):

| Variable | Para qué | Dónde |
|---|---|---|
| `GEMINI_API_KEY` | Embeddings de cada consulta (costo del servidor) | Backend, runtime |
| `GEMINI_API_KEY_1`/`_2` | Build del índice (rotadas por rate limit) | Solo al construir |
| `ORIGENES_CORS` | Orígenes permitidos (dominio de Vercel en prod) | Backend, runtime |
| `ANTHROPIC_API_KEY` | Solo para `pytest -m agente` | Local, opcional |
| `NEXT_PUBLIC_API_URL` | URL pública del backend | Vercel (frontend) |

## Modelo de seguridad (BYOK)

- **El agente es _bring your own key_**: cada usuario pone su propia clave de
  Claude/Gemini/GPT en el navegador. Viaja en el body del request, se usa para
  esa llamada y **no se persiste, no se loguea, no toca disco ni query string**.
  El proyecto no tiene una clave de LLM propia que exponer.
- **Las claves del servidor** (embeddings) viven solo como variables de entorno
  del host; nunca se envían al navegador ni se incluyen en la imagen.
- `NEXT_PUBLIC_API_URL` es público a propósito (es una URL, no un secreto).

Proyecto de portafolio. No afiliado a Riot Games. Los datos e imágenes de
cartas provienen del [Data Dragon](https://developer.riotgames.com/docs/lor)
público de _Legends of Runeterra_.
