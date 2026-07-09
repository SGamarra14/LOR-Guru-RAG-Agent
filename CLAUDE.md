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
- **Embeddings**: **API de Gemini `gemini-embedding-001` (768 dims)** desde la
  migración de 2026-07 (`lorguru/embeddings.py`; nota en GUIA_FASE2.md §8).
  Antes era `intfloat/multilingual-e5-large` local — se migró para hospedar
  barato (el servidor ya no carga un modelo de ~2.5 GB). `taskType`
  RETRIEVAL_DOCUMENT/QUERY hace el papel de los viejos prefijos passage/query;
  se normaliza a L2. Solo texto de habilidades + descripciones de keywords —
  nunca stats. El A/B histórico (e5 vs MiniLM) en `scripts/comparar_embeddings.py`
  sigue siendo la doc de la decisión de fase 2, pero ya NO refleja el modelo
  en uso.
- **Claves de Gemini para embeddings**: el **build** rota `GEMINI_API_KEY_1` y
  `GEMINI_API_KEY_2` (2 hilos, paceados bajo 100/min con backoff 429 — ideal:
  proyectos separados). El **servidor** usa `GEMINI_API_KEY` para embeber cada
  consulta (costo del servidor, NO BYOK). Esto es aparte del LLM del agente.
- **Indexado separado del servido**: `python -m lorguru.build_index`
  construye (necesita las claves de Gemini); la API solo carga y FALLA si el
  índice no existe. No cambiar.
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

`.env`: `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` (embeddings del servidor + capa B
Gemini), `GEMINI_API_KEY_1`/`_2` (build del índice), `ORIGENES_CORS`.

## Fase 3: plan y avance

Objetivo: frontend Next.js (+ Tailwind/shadcn) en `webapp/` que consuma la
API, y despliegue (Vercel + host con el índice ya construido copiado en la
imagen Docker; sin torch tras la migración a embeddings de Gemini).
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
- [x] Primitivas `components/ui/*` escritas A MANO (el CLI de shadcn se
      colgaba sin output): button, input, textarea, label, badge, alert +
      select sobre @radix-ui/react-select; `lib/utils.ts` con `cn` mínimo.
      Mismo API/ubicación que shadcn — un `shadcn add` futuro las reemplaza.
- [x] Tema LoR en `globals.css`: paleta azul noche (#0a1120) / dorado
      (#c8a24b) / cian (#2dd4d4), radios angulosos, `fondo-grimorio` (grano
      feTurbulence), `marco-panel`/`marco-carta` con esquinas doradas y glow
      cian al hover. `npm run build` en verde.
- [x] Verificación local end-to-end: backend con `python -m uvicorn
      lorguru.api:app --port 8000` (OJO: el launcher del preview no logró
      arrancar la API; uvicorn directo sí) + `npm run dev`. Verificado en
      navegador: carga de proveedores con insignia "Recomendado · verificado
      16/16", flujo de error real (clave inválida → paso "Agente iniciado" →
      Alert con mensaje de 401), y flujo de éxito con stream simulado sobre
      cartas reales (progreso por pasos con argumentos, grid con imágenes
      del Data Dragon reescritas a https, panel de transparencia). La
      búsqueda real con clave desde el navegador queda para el usuario (la
      clave no debe pasar por logs de herramientas).
- [x] Dockerfile backend (índice horneado, torch CPU) + requirements-api.txt
      + .dockerignore; instrucciones de deploy en GUIA_FASE3.md §6
- [x] GUIA_FASE3.md (completa, con la nota de primitivas a mano)

- [x] Pulido UX (post-cierre, pedido por Sebas): fondo aurora animado sutil
      (pseudo-elemento fijo, misma paleta, respeta prefers-reduced-motion);
      acordeón "Configuración del Agente" (details/summary controlado, se
      colapsa al lanzar la búsqueda, resumen en el summary); insignia del
      modelo verificado reducida a "Recomendado" y sin nota bajo el select;
      placeholder de API key con recomendación de revocar la clave tras su
      uso; respuesta del agente renderizada como Markdown (react-markdown +
      estilos `.prosa`); galería limpia (TarjetaCarta sin pie de metadata,
      marco abrazando solo la imagen). Verificado en navegador.

⚠️ Trampa del entorno descubierta: la caché persistente de Turbopack (Next
16, `webapp/.next`) puede servir `globals.css` VIEJO aunque el archivo cambie
y hasta tras reiniciar el dev server ("Compiled" engañoso). Si un cambio de
CSS no aparece: borrar `webapp/.next` y reiniciar.

Pendiente que requiere cuentas del usuario (no automatizable desde aquí):
deploy real a Vercel (root dir `webapp/`, var `NEXT_PUBLIC_API_URL`) y al
host del backend (imagen del Dockerfile; var `ORIGENES_CORS` con el dominio
de Vercel). Pasos exactos en GUIA_FASE3.md §6.
