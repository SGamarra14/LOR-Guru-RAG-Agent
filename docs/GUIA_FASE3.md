# LoR Guru — Fase 3: guía de construcción de la UI y el despliegue

La última fase: un frontend Next.js que consume la API de la fase 2, y el
despliegue de ambas partes. Como siempre: esta guía dice **qué construir y
qué debe cumplir**, sin código resuelto; el proyecto de referencia
(`webapp/`) usa exactamente los mismos nombres de archivos, componentes y
hooks. Para UI el modo "sin código" aplica igual que antes, con un matiz: los
patrones de React (estado, efectos, composición) se describen a nivel de
contrato — si en algún componente prefieres ver el código de una vez, la
referencia está a un archivo de distancia.

**Stack**: Next.js (App Router) + TypeScript + Tailwind v4 + shadcn/ui.
El Vercel AI SDK **no** se usa — la sección 2 explica por qué es una decisión
y no una omisión.

**Estructura de `webapp/src`**

```
src/
├── app/
│   ├── layout.tsx            # fuentes, metadata, fondo global
│   ├── globals.css           # el tema LoR (variables + utilidades marco-*)
│   └── page.tsx              # la página única: compone todo
├── lib/
│   ├── openapi.d.ts          # GENERADO — no editar a mano
│   ├── tipos.ts              # re-exporta tipos + eventos SSE + PasoProgreso
│   └── api.ts                # URL_API, obtenerProveedores, mensajeDeError, urlImagenSegura
├── hooks/
│   └── useAgenteStream.ts    # el consumidor del SSE por pasos
├── componentes/              # los del dominio (en español, como el backend)
│   ├── FormularioBusqueda.tsx
│   ├── SelectorProveedorModelo.tsx
│   ├── CampoApiKey.tsx
│   ├── ProgresoAgente.tsx
│   ├── GridCartas.tsx
│   ├── TarjetaCarta.tsx
│   └── PanelTransparencia.tsx
└── components/ui/            # primitivas estilo shadcn (ver nota abajo)
```

> **Nota sobre shadcn**: lo normal es generar `components/ui/*` con
> `npx shadcn init` + `npx shadcn add button input textarea select label
> badge alert`. En el entorno del proyecto de referencia el CLI se colgaba
> sin output, así que las 7 primitivas están **escritas a mano** con el
> mismo API y ubicación (para que un `shadcn add` futuro las reemplace sin
> tocar el resto): wrappers finos con Tailwind, un `cn` mínimo en
> `lib/utils.ts`, y solo una dependencia real — `@radix-ui/react-select` —
> porque los items del selector de modelos llevan una insignia dentro, cosa
> que un `<select>` nativo no puede renderizar. Si el CLI te funciona,
> úsalo; el resultado es intercambiable.

¿Por qué esta organización? `componentes/` (dominio, español) separado de
`components/ui/` (primitivas genéricas de shadcn, generadas): lo que es tuyo
se distingue de lo que es de la librería a simple vista, y actualizar shadcn
nunca toca tu código. Un solo `page.tsx` porque la app ES una página — meter
rutas sería estructura sin contenido.

---

## 1. Tipos compartidos (generados, no transcritos)

- Crea `scripts/exportar_openapi.py` en el **backend**: importa `app` de
  `lorguru.api`, llama `app.openapi()` y escribe el JSON en
  `webapp/openapi.json`. FastAPI genera el schema sin levantar el servidor.
- En `webapp/`: instala `openapi-typescript` (dev) y agrega el script npm
  `"tipos": "openapi-typescript openapi.json -o src/lib/openapi.d.ts"`.
- `src/lib/tipos.ts` **re-exporta** con nombres del dominio lo que la UI usa:
  `Carta` = `components["schemas"]["CartaOut"]`, `RespuestaAgente`,
  `Proveedor`, `Modelo`, `Llamada`, y `ProveedorId` (el `Literal` del campo
  `proveedor` de `AgenteRequest` — así el selector no puede mandar un
  proveedor que el backend no acepte).
- Los **eventos del SSE** no viajan en el schema OpenAPI (van dentro del
  stream), así que tipéalos a mano en `tipos.ts` (`EventoAgente`, unión
  discriminada por `tipo`) como espejo declarado de
  `lorguru/agente.py:eventos_agente` — con un comentario que diga de qué son
  espejo. Añade también `PasoProgreso`: el paso ya humanizado que pinta la UI
  (`{id, etiqueta, detalle?, estado: "en_curso"|"hecho"|"error"}`).

Flujo al cambiar el backend: `python -m scripts.exportar_openapi && cd webapp
&& npm run tipos`. Si un campo cambia, TypeScript truena en compilación — ese
es el punto.

## 2. La decisión de streaming: consumidor propio, sin `useChat`

**Decisión: opción (a), un hook propio (`useAgenteStream`) que consume
`/agente/stream` con `fetch` + `ReadableStream`.** El razonamiento completo,
porque es la pieza más importante de la fase:

- El protocolo de datos del AI SDK y su `useChat` están diseñados para
  **chats**: mensajes multi-turno cuyo contenido crece token a token. Lo que
  da nuestro backend es otra cosa: una secuencia corta de **pasos
  estructurados** (tool_use → tool_result → …) que culmina en **un** payload
  final con texto + cartas + metadatos. No hay historial de conversación, no
  hay tokens incrementales.
- El camino (b) — un route handler que traduzca nuestros eventos a
  data-parts del AI SDK — habría añadido un salto de red extra (navegador →
  Next → FastAPI), un formato intermedio que mantener, y al final `useChat`
  aportaría casi nada de lo suyo: ni gestión de historial ni streaming de
  texto aplican.
- El costo de (a) es bajo: ~40 líneas de parsing SSE sin dependencias.
- Detalle técnico que justifica `fetch` y no `EventSource`: `EventSource`
  solo hace **GET**, y nuestra `api_key` debe viajar en el **body de un
  POST** (nunca en query string).
- Qué se pierde: la reconexión automática de `EventSource` y el ecosistema
  del AI SDK si el día de mañana hubiera streaming token a token. Si la fase
  2 implementara eso, esta decisión se revisita — déjalo anotado.

**`useAgenteStream`** — el contrato:

- Estado expuesto: `fase` (`inactivo | buscando | listo | error`), `pasos:
  PasoProgreso[]`, `resultado: RespuestaAgente | null`, `error: string |
  null`, y las funciones `buscar(params)` y `cancelar()`.
- `buscar({consulta, proveedor, modelo, apiKey})`:
  1. Aborta cualquier búsqueda anterior (`AbortController` en un ref) y
     resetea el estado.
  2. `fetch` POST a `/agente/stream`. Si `!res.ok`, parsea el body como JSON
     de error de FastAPI y pásalo por `mensajeDeError` (sección 5).
  3. Lee `res.body.getReader()` + `TextDecoder` acumulando en un buffer;
     separa eventos por `\n\n`; de cada bloque toma la línea `data: ` y
     parsea el JSON como `EventoAgente`.
  4. Traduce eventos a pasos: `tool_use` abre un paso `en_curso` (etiqueta
     humanizada: "Filtrando cartas" / "Buscando por significado: …" +
     detalle con los argumentos); su `tool_result` cierra el último paso con
     `→ N cartas` (o error); `respuesta` guarda el resultado y pone `fase:
     "listo"`; `error` mapea con `mensajeDeError`.
- `cancelar()` aborta el fetch. Ojo: distingue `AbortError` (silencio) de un
  fallo real de red ("¿está corriendo el backend?").

## 3. Interfaz de búsqueda

**Extensión previa del backend (autorizada por el prompt de fase):**
`GET /proveedores` ahora devuelve, por proveedor, `nombre` legible,
`modelo_default` y `modelos: [{id, nombre, verificado, nota}]`. La
verificación es **por modelo**: solo `claude-sonnet-5` (16/16 en el set) es
`verificado: true`; los demás modelos de Claude, todos los de Gemini y GPT
van con `false` y una `nota` que explica su situación (parcial por cuota,
sin credenciales…). Los IDs de modelos se confirmaron contra la
documentación vigente de cada proveedor (2026-07) — deja el comentario de
revisarlos al desplegar, cambian seguido. Ajusta el test de capa A que
valida `/proveedores` para que afirme exactamente esto (ningún modelo salvo
sonnet-5 puede venir verificado).

**`SelectorProveedorModelo`** — dos `Select` de shadcn encadenados:

- El de proveedor lista `proveedores` (del endpoint, cargados una vez en
  `page.tsx`); al cambiarlo, el modelo se resetea al `modelo_default` del
  nuevo proveedor.
- El de modelo lista `modelos` del proveedor actual; el verificado lleva un
  `Badge` con solo la palabra "Recomendado" (la evidencia detallada — 16/16,
  notas de evaluación — vive en la guía y en la API, no satura la UI). No
  muestres la `nota` bajo el select: mantén el selector limpio.

**`CampoApiKey`** — la clave se trata como el secreto que es:

- `Input type="password"` (con botón Ver/Ocultar), `autoComplete="off"`.
- Placeholder que educa sobre higiene de claves: "Ingresa tu API Key (Se
  recomienda desechar/revocar la API tras su uso. No se guarda en el
  servidor)."
- Vive en el estado de React; **no** se persiste por defecto.
- Persistirla es **opt-in visible**: un checkbox "Recordar esta clave en este
  navegador (localStorage)" con la advertencia de no usarlo en equipos
  compartidos. Marcado → se guarda bajo una clave por proveedor; desmarcado →
  se borra. Al cambiar de proveedor se recupera solo si el usuario había
  optado por recordarla.
- Nada de logs, analítica ni query strings. Solo el body del POST.

**`FormularioBusqueda`** — compone textarea de consulta (Enter envía,
Shift+Enter salto de línea), chips de consultas de ejemplo (las del set de
evaluación son buenos candidatos), la configuración y el botón (deshabilitado
sin consulta o sin clave; en curso muestra "Consultando…" y aparece un botón
Cancelar).

- **Acordeón "Configuración del Agente"**: agrupa el selector
  proveedor→modelo y el campo de API key en un `<details>/<summary>`
  controlado (estado React + `onToggle`). Arranca **abierto** (hay que
  configurar la clave) y se **colapsa solo al lanzar la primera búsqueda** —
  despeja la pantalla una vez configurado, sin esconder nada antes de tiempo.
  El `summary` muestra un resumen del estado cuando está cerrado
  ("Claude (Anthropic) · Claude Sonnet 5 · clave lista/falta la clave") y un
  chevron que rota con `group-open:`.

## 4. Resultados

- **`TarjetaCarta`**: SOLO la imagen (`carta.imagen`), con `loading="lazy"` y
  `alt` descriptivo — sin pie de metadata. El arte de la carta ya muestra
  nombre, coste, región y stats: repetirlos en texto es carga cognitiva
  redundante; el marco (borde dorado + esquinas + glow cian al hover) abraza
  únicamente los bordes de la imagen, dejando una galería visual limpia. Dos
  detalles del dato real: las URLs del Data Dragon vienen con `http://` —
  crea `urlImagenSegura` en `lib/api.ts` que las reescriba a `https://` (si
  no, contenido mixto bloqueado en producción) — y alguna imagen puede
  faltar: maneja `onError` mostrando un fallback textual con nombre +
  descripción (el único caso donde el texto sí hace falta, porque no hay
  arte que lo supla).
- **`GridCartas`**: grid responsivo (2 → 5 columnas), key por `cardCode`.
- **`PanelTransparencia`** (colapsable, cerrado por defecto): el "por qué"
  de los resultados — la explicación de `metodo_cartas` en lenguaje llano
  (citadas / nombres / última llamada / ninguna) y la lista numerada de
  `llamadas` con tool + argumentos + total. Es la conexión con la idea
  original del proyecto: mostrar cómo decidió el agente, no solo qué devolvió.
- La **respuesta del agente** se muestra prominente y se renderiza como
  **Markdown** (`react-markdown`): los modelos responden con negritas,
  cursivas y listas — mostrarla como string plano deja `**` y `*` visibles.
  Estilízala con una clase propia (`.prosa` en `globals.css`): negritas en
  dorado, cursivas en cian, viñetas `◆` doradas, encabezados con la fuente
  display. El panel de transparencia va debajo y el grid después.

## 5. Manejo de errores

`mensajeDeError(status, detalle)` en `lib/api.ts` — el backend ya extrajo
mensajes humanos; el frontend les da contexto, no los tapa:

- **401** → "el proveedor rechazó tu API key…".
- **429** → el mensaje específico de cuota, mencionando el caso real: los
  tiers gratuitos (Gemini free ≈ 20 solicitudes/día/modelo) se agotan y hay
  que esperar el reinicio diario o usar clave de pago. Adjunta el `detalle`
  si viene.
- **400** → usa el `detail` del backend tal cual (ahí llega "credit balance
  is too low", "modelo inválido"…). Nunca lo sustituyas por un genérico.
- **422** → validación; **502** → transitorio del proveedor; default →
  `detalle` o "error inesperado (N)".

Los errores llegan por dos vías y ambas pasan por la misma función: HTTP
no-ok del fetch inicial, y el evento `{"tipo": "error"}` dentro del stream.
En la UI: `Alert` destructivo con título + mensaje. El fallo de conexión
inicial (API caída) tiene su propio mensaje.

## 6. Despliegue

**Backend — imagen Docker con el índice YA construido copiado dentro.**

> Este patrón cambió con la migración a embeddings de Gemini (ver
> GUIA_FASE2.md §8, nota de migración). Antes se horneaba el índice en el
> build (`RUN python -m lorguru.build_index`) porque el modelo e5 era local y
> gratis. Ahora construir el índice necesita **claves de API de Gemini**, y
> un build de Docker no debe llevar secretos — así que se construye
> localmente y se copia el resultado.

- `requirements-api.txt`: el subconjunto mínimo para servir. Tras la
  migración **ya no incluye torch ni sentence-transformers** — el servidor no
  carga ningún modelo; embebe la consulta por REST a Gemini (`requests`). La
  imagen pasa de ~3 GB a cientos de MB.
- **Antes de `docker build`**, en tu máquina: `python -m lorguru.build_index`
  (usa tus `GEMINI_API_KEY_1/_2`, deja `data/` y `chroma_db/` listos).
- `Dockerfile` (en la raíz): `python:3.12-slim`; instala
  `requirements-api.txt`; copia `lorguru/` **y los artefactos ya construidos
  `data/` + `chroma_db/`** (solo vectores y metadata — no hay secretos ahí).
  El contenedor arranca con `uvicorn` y solo carga; si el índice faltara,
  falla al arrancar (por diseño, desde fase 2).
- `.dockerignore`: excluye todo lo de dev y **siempre `.env`**, pero ahora
  **permite** `data/` y `chroma_db/` (son la entrada del servidor).
- ¿Por qué copiar y no hornear ni usar volumen? Copiar el índice pre-hecho
  mantiene los despliegues atómicos (imagen = índice) sin meter claves en el
  build ni configurar discos persistentes. La alternativa con volumen (job de
  `build_index` como release step, con las claves de Gemini como env del job)
  queda para cuando quieras re-indexar sin reconstruir la imagen —
  documentada, no implementada.
- **Runtime**: el servidor necesita `GEMINI_API_KEY` (para embeber cada
  consulta — costo del servidor, no BYOK) y `ORIGENES_CORS` con el dominio
  exacto de Vercel. Se pasan como variables de entorno del host, nunca en la
  imagen.
- Host: Railway/Render/Fly sirven de sobra; sin el modelo local el costo de
  RAM se desploma — un plan pequeño (512 MB–1 GB) alcanza, e incluso los
  tiers gratuitos con scale-to-zero se vuelven viables (el cold start ya no
  recarga 2.5 GB de modelo).

**Frontend — Vercel:**

- Proyecto apuntando a `webapp/` (root directory). Variable
  `NEXT_PUBLIC_API_URL` = URL pública del backend. En dev, `.env.local` con
  `http://localhost:8000`.
- Tras el primer deploy: copia el dominio real de Vercel a `ORIGENES_CORS`
  del backend y redespliega el backend (o reinicia con la variable nueva).

**Checklist de humo post-deploy**: `GET /salud` responde; la página carga
proveedores; una búsqueda con clave válida muestra progreso y cartas; una
clave inválida muestra el mensaje de 401; sin `ORIGENES_CORS` correcto verás
errores CORS en la consola del navegador — esa es la señal de qué falta.

## 7. Dirección visual (el tema)

Lenguaje visual de los menús de LoR sin assets de Riot. Con Tailwind v4 +
shadcn es trabajo de **variables**, casi todo en `globals.css`:

- **Paleta** (variables de shadcn, modo único oscuro):
  - Fondo: azul noche casi negro `#0a1120` (`--background`), paneles un paso
    más claros `#101a2d` (`--card`).
  - **Primario dorado/bronce** `#c8a24b` (`--primary`) para títulos, bordes
    activos e insignias.
  - **Acento cian** `#2dd4d4` (`--accent`) para foco, hover y el paso "en
    curso" del progreso.
  - Texto: blanco hueso `#e8e4d8` (`--foreground`); secundario gris azulado.
- **Tipografía** con `next/font/google`: `Cinzel` (display, variable
  `--font-display`) para h1/h2/nombres de carta vía una utilidad
  `font-display`; `Nunito Sans` (variable `--font-cuerpo`) como sans de
  cuerpo. Nada de tipografías de Riot.
- **Fondos y marcos** — dos utilidades CSS propias:
  - `fondo-grimorio` (en el `body`): gradientes radiales oscuros +
    **ruido sutil** con un SVG inline de `feTurbulence` como data-URI, para
    que el fondo no sea plano. Encima, una **aurora animada**: un
    pseudo-elemento `::before` fijo (`position: fixed; z-index: -1`) con 3-4
    manchas `radial-gradient` en la MISMA paleta (azules noche + un susurro
    de cian y dorado), `filter: blur(~50px)` y un `@keyframes` que las
    traslada/escala muy lento (~45s, solo `transform` — barato para la GPU).
    Debe ser sutil: no compite con la lectura ni con los paneles. Respeta
    `prefers-reduced-motion` desactivando la animación.
  - `marco-panel` y `marco-carta`: borde 1px dorado translúcido, esquinas
    poco redondeadas (`--radius` bajo: las UIs de Riot son angulosas),
    **esquinas marcadas** con pseudo-elementos (dos trazos dorados en las
    esquinas opuestas) y glow cian al hover en las cartas — evocan el marco
    de una carta sin replicar el diseño exacto.
- En `layout.tsx`: `lang="es"`, metadata real, y las dos fuentes aplicadas.
- Footer con el descargo: proyecto de portafolio, no afiliado a Riot; datos
  e imágenes del Data Dragon público.

## 8. Mantén `CLAUDE.md` vivo

Al completar cada sección de esta guía: actualiza el checklist de la sección
"Fase 3" de `CLAUDE.md` (raíz del repo) y comitea. Si una sesión se corta a
media sección, el commit de `CLAUDE.md` debe decir el siguiente paso
concreto. Es el mecanismo de handoff entre sesiones — trátalo como parte del
entregable, no como burocracia.

## Criterio de éxito

Desde una URL pública: búsqueda en lenguaje natural, eligiendo proveedor y
modelo (con `claude-sonnet-5` marcado como verificado), progreso del agente
visible paso a paso, resultados con imagen, panel de transparencia, y
mensajes de error claros para clave inválida (401) y cuota agotada (429) —
con el backend sirviendo desde un índice horneado, sin reconstruirlo al
arrancar.
