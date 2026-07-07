# LoR Guru — estado del proyecto

Búsqueda de cartas de Legends of Runeterra en lenguaje natural (español).
Proyecto de portafolio en 3 fases. **Regla de trabajo**: cada fase produce
una guía markdown SIN código resuelto (para que Sebas la construya) + un
proyecto de referencia con nombres idénticos. Este archivo se actualiza y
comitea al completar cada sección de la fase en curso — si retomas en una
sesión nueva, empieza leyendo esto.

## Estado por fase

- **Fase 1 — Notebook PoC**: ✅ terminada. `GUIA.md` + `lor_guru_fase1.ipynb`.
  Capa A 16/16, capa B 14/16.
- **Fase 2 — API FastAPI**: ✅ terminada. `GUIA_FASE2.md` + `lorguru/` +
  `tests/`. Capa A 16/16 (vía endpoints), capa B Claude **16/16**. Gemini
  incompleto por cuota del free tier (7 casos confirmados, cero fallos de
  calidad) — `verificado: False`. GPT implementado, sin credenciales para
  verificar.
- **Fase 3 — UI + despliegue**: 🚧 EN CURSO. Ver "Fase 3: avance" abajo.

## Arquitectura (decisiones ya tomadas — no re-litigar)

- **Stores separados**: DataFrame pandas en memoria para filtros exactos
  (`lorguru/stores.py:filtrar_cartas`); Chroma persistente para semántica.
  Híbrido = filtrar primero, restringir Chroma con `$in` sobre cardCode.
- **Embeddings**: `intfloat/multilingual-e5-large` (A/B en
  `scripts/comparar_embeddings.py`; tabla en GUIA_FASE2.md §8). Exige
  prefijos `"passage: "` / `"query: "`. Solo texto de habilidades +
  descripciones de keywords — nunca stats numéricos.
- **Indexado separado del servido**: `python -m lorguru.build_index`
  construye; la API solo carga y FALLA si el índice no existe. No cambiar.
- **Agente BYOK multi-proveedor** vía LiteLLM `==1.91.0` (jamás 1.82.7/1.82.8
  — comprometidas con malware). La api_key del usuario viaja en el body, no
  se persiste ni loguea.
- **Cartas del agente**: línea final `CARTAS: code1, code2...` parseada con
  regex (fallback: regex en todo el texto → última tool call). Campo
  `metodo_cartas` lo reporta.
- **Evaluación**: 16 consultas en `lorguru/evaluacion.py`. Capa A =
  endpoints directos (`pytest`, no gasta API). Capa B = agente real
  (`pytest -m agente -s`). Umbral capa B: ≥14/16.
- El free tier de Gemini (~20 req/día/modelo) no aguanta el set completo
  (~40 llamadas) — por eso el default es `gemini-2.5-flash-lite` y quedó sin
  verificar. Para completar: `pytest -m agente -s -k gemini` con cuota.

## Cómo correr

```bash
pip install -r requirements.txt
python -m lorguru.build_index     # una vez (descarga datos + construye índice)
uvicorn lorguru.api:app --reload  # API en :8000
pytest                            # capa A (gratis)
pytest -m agente -s               # capa B (gasta API; claves en .env)
```

`.env`: `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `ORIGENES_CORS`.

## Fase 3: plan y avance

Objetivo: frontend Next.js (+ Tailwind/shadcn) en `webapp/` que consuma la
API, y despliegue (Vercel + host con índice horneado en imagen Docker).
Entregables: `GUIA_FASE3.md` + `webapp/` de referencia.

Decisiones de fase 3 (tomadas al arrancar, justificación en GUIA_FASE3.md):

- **Streaming**: consumidor SSE propio (`useAgenteStream` con fetch +
  ReadableStream), NO adaptador a `useChat` del AI SDK — los eventos son
  pasos estructurados con un payload final único, no un chat de tokens.
- **API key en el cliente**: en memoria (estado React) por defecto; persistir
  es opt-in visible del usuario.
- **Tema**: azul oscuro casi negro + acentos dorado/bronce + cian para
  foco/hover; Cinzel (display) + sans limpia (cuerpo). Lenguaje visual de
  LoR sin assets de Riot.

Checklist de avance:

- [x] Repo git inicializado, .gitignore, CLAUDE.md (esta sección)
- [x] Backend: `GET /proveedores` extendido con `modelos[]` por proveedor
      (cada modelo con su `verificado`; solo claude-sonnet-5 = true).
      Capa A: 20 passed. IDs de modelos confirmados contra docs 2026-07.
- [x] `webapp/` scaffold (Next.js 16.2 + TS + Tailwind v4, `--src-dir`)
- [x] Tipos generados desde OpenAPI (`scripts/exportar_openapi.py` +
      `npm run tipos` → `src/lib/openapi.d.ts`)
- [x] `useAgenteStream` (fetch + ReadableStream; decisión documentada en
      GUIA_FASE3.md §2) y componentes del dominio: FormularioBusqueda,
      SelectorProveedorModelo, CampoApiKey (secreto, persistencia opt-in),
      ProgresoAgente, GridCartas, TarjetaCarta, PanelTransparencia;
      `page.tsx` y `layout.tsx` (Cinzel + Nunito Sans, lang=es)
- [ ] **BLOQUEADO/EN CURSO**: primitivas `components/ui/*` — el CLI de
      shadcn (`npx shadcn init/add`) se cuelga sin output en este entorno.
      Plan B decidido: escribir a mano las 7 primitivas que usa la UI
      (button, input, textarea, label, badge, alert, select — select con
      @radix-ui/react-select para poder meter el badge en los items) con el
      mismo API y layout de archivos que shadcn.
- [ ] Tema LoR en `globals.css` (paleta azul noche/dorado/cian, utilidades
      `fondo-grimorio`, `marco-panel`, `marco-carta` — spec en GUIA_FASE3 §7)
- [ ] Verificación local end-to-end (uvicorn + next dev) — hay preview tools
- [x] Dockerfile backend (índice horneado, torch CPU) + requirements-api.txt
      + .dockerignore; instrucciones de deploy en GUIA_FASE3.md §6
- [x] GUIA_FASE3.md (completa; §7 describe el tema aún no aplicado)

Siguiente paso concreto: (1) escribir `webapp/src/components/ui/{button,
input,textarea,label,badge,alert,select}.tsx` a mano + `lib/utils.ts` (cn) +
`npm i @radix-ui/react-select`; (2) tema en `globals.css`; (3) `npm run
build` hasta verde; (4) verificación local con backend real.
