# LoR Guru — Fase 2: guía de construcción de la API

Esta guía te lleva a convertir el notebook de la fase 1 en un servicio real:
código modularizado, tests de regresión y una API FastAPI multi-proveedor
(BYOK). Como en la fase 1, **no hay código resuelto**: cada paso dice qué
construir y qué debe cumplir. El proyecto de referencia usa exactamente los
mismos nombres de archivos y funciones; si te estancas, consulta el archivo
homónimo.

**Estructura final del proyecto**

```
Lor Guru/
├── lorguru/                  # el paquete
│   ├── __init__.py           # versión
│   ├── ingesta.py            # descarga/caché + parseo (de la sección 2-3 del notebook)
│   ├── stores.py             # filtrar_cartas + Chroma + buscar_semantica + Recursos
│   ├── agente.py             # tools, system prompt, loop LiteLLM multi-proveedor
│   ├── evaluacion.py         # los 16 casos, reformulados contra la API
│   ├── build_index.py        # python -m lorguru.build_index (paso de build)
│   └── api.py                # FastAPI: endpoints, schemas, CORS, SSE
├── scripts/
│   └── comparar_embeddings.py  # el A/B de modelos (sección 4a)
├── tests/
│   ├── conftest.py           # TestClient de sesión
│   ├── test_capa_a.py        # 16 casos vía endpoints, sin API externa
│   └── test_capa_b.py        # 16 casos vía /agente, marker `agente`
├── pytest.ini
├── lor_guru_fase1.ipynb      # queda como documentación de la fase 1
└── data/ · chroma_db/ · .env · requirements.txt
```

**¿Por qué esta organización?** Un solo paquete (`lorguru`) con módulos por
*responsabilidad*, no por capa técnica: `ingesta` (de dónde salen los datos),
`stores` (cómo se consultan), `agente` (quién decide), `api` (cómo se expone),
`evaluacion` (cómo se mide). Cada módulo importa solo hacia "abajo"
(api → agente → stores → ingesta) y ninguno importa de `api` — eso permite
usar el agente sin la API (scripts, notebook) y testear cada capa sola.
`evaluacion` es un módulo del paquete (no vive en `tests/`) porque el set de
consultas es un *activo del proyecto* — lo usan los tests, el script de
comparación de embeddings, y en el futuro cualquier benchmark.

---

## 1. `ingesta.py` — de notebook a módulo

Copia del notebook: `descargar_bundle`, `descargar_datos`, `cargar_cartas`,
`cargar_glosario`, con dos cambios:

1. **Rutas ancladas al proyecto, no al cwd.** El notebook usaba `Path("data")`
   relativo — funciona porque Jupyter corre en la raíz. Uvicorn y pytest no
   garantizan eso. Define `RAIZ_PROYECTO = Path(__file__).resolve().parents[1]`
   y cuelga de ahí `RUTA_DATOS`, `RUTA_CARTAS`, `RUTA_GLOBALS`.
2. **URLs de imagen (sección 6c del prompt de fase).** Cada carta trae un
   campo `assets`: una lista donde el primer elemento tiene
   `gameAbsolutePath` (el arte del marco de juego) y `fullAbsolutePath` (la
   ilustración completa). Crea un helper `_url_imagen(assets, clave)` que
   devuelva la URL del primer asset (o `""` si no hay) y añade al DataFrame
   las columnas `imagen` e `imagen_full`. La fase 3 las mostrará.

Todo lo demás — la lista `SETS` con `set6cde`/`set7b`, el tag `latest`, el
caché por existencia de archivo, el filtro `collectible`, la deduplicación
por `cardCode` — se queda idéntico: está validado.

## 2. `stores.py` — los dos stores y el objeto `Recursos`

### La decisión revisitada: ¿DataFrame o SQLite?

**Se queda el DataFrame en memoria, cargado una vez al arrancar.** El
razonamiento (escríbelo en tu docstring del módulo):

- El dato es **solo-lectura en runtime**: cambia por parche de Riot (semanas),
  no por request. No hay escrituras que coordinar.
- ~1,650 filas ≈ pocos MB. Un `value_counts` o máscara booleana tarda
  microsegundos; SQLite no mejora nada medible.
- Las columnas-lista (`regionRefs`, `keywordRefs`) obligarían en SQL a tablas
  puente o JSON embebido — complejidad sin beneficio.
- El punto de corte real sería: escrituras concurrentes, varios workers que
  deban compartir estado mutable, o un dataset que no quepa en memoria.
  Ninguno aplica. (Con varios workers de uvicorn cada proceso carga su copia
  — 5 MB por worker es un no-problema.)

### Separación indexado / servido (sección 6d)

Divide lo que en el notebook era `construir_store_vectorial` en **dos
funciones con contratos distintos**:

- **`construir_indice(df, glosario, modelo_st, reconstruir=False)`** — solo
  la llama el paso de build. Igual que en el notebook (crear colección,
  embeber en lotes, metadata con cardCode/stats/regiones unidas por `"|"`)
  con una adición: guarda el **nombre del modelo de embeddings en la metadata
  de la colección** (`{"hnsw:space": "cosine", "modelo": MODELO_EMBEDDINGS}`),
  y solo reutiliza una colección existente si el conteo Y el modelo
  coinciden. Sin esto, cambiar de modelo dejaría un índice viejo sirviendo
  vectores incompatibles en silencio.
- **`cargar_indice(n_cartas_esperado)`** — lo único que toca el servidor.
  Obtiene la colección existente y **falla con `RuntimeError` e instrucciones
  concretas** ("corre `python -m lorguru.build_index`") en tres casos: no
  existe, el conteo no coincide con las cartas, o fue construida con otro
  modelo. El servidor jamás repara nada por su cuenta: arranques
  predecibles, y el error de operación dice exactamente qué comando correr.

### El resto del módulo

- `filtrar_cartas(df, ...)` — idéntica al notebook.
- `construir_texto_carta(fila, glosario)` — idéntica.
- Constantes `MODELO_EMBEDDINGS`, `PREFIJO_DOCUMENTO`, `PREFIJO_CONSULTA`.
  Los prefijos existen porque la familia E5 (candidata del A/B, sección 4a)
  exige `"passage: "` en documentos y `"query: "` en consultas; para MiniLM
  quedan `""`. Tenerlos como constantes hace el cambio de modelo un diff de
  tres líneas + rebuild.
- **`Recursos`** — un `dataclass` con `df`, `glosario`, `modelo_st`,
  `coleccion`: todo lo que hay que tener en memoria para servir. Evita
  variables globales sueltas y hace explícitas las dependencias de cada
  función.
- **`cargar_recursos()`** — carga los cuatro (verificando antes que existan
  los datos en disco, con el mismo patrón de error-con-instrucciones). Es lo
  único que llama el lifespan de la API y el conftest de los tests.
- `buscar_semantica(recursos, texto_consulta, top_k=10, filtro_metadata=None)`
  — igual que el notebook (el patrón híbrido intacto), pero recibiendo
  `recursos` explícitamente en vez de leer globales del notebook, y aplicando
  `PREFIJO_CONSULTA` al embeber.

## 3. `build_index.py` — el paso de build

Un `main()` con `argparse` y dos flags: `--forzar-datos` (re-descarga aunque
haya caché) y `--reconstruir` (regenera embeddings). Ejecutable como
`python -m lorguru.build_index`. Secuencia: `descargar_datos` →
`cargar_cartas` + `cargar_glosario` → `cargar_modelo_embeddings` →
`construir_indice`. Imprime el dispositivo (cuda/cpu) y termina diciendo que
la API ya puede arrancar.

Implicación de despliegue (déjala anotada): el host de la fase 3 necesita un
volumen persistente para `chroma_db/` — o el índice horneado en la imagen —
porque el proceso que sirve no sabe construirlo.

## 4. `agente.py` — multi-proveedor y los dos arreglos de fase 1

### 4.1 LiteLLM en vez del SDK de anthropic (sección 7)

- `litellm.completion(model=f"{proveedor}/{modelo}", messages=..., tools=...,
  api_key=..., max_tokens=8000)`. El formato de `messages` y `tools` es el de
  OpenAI (la *lingua franca* de LiteLLM); la librería traduce a
  Claude/GPT/Gemini.
- Convierte los esquemas de tools de fase 1 al formato OpenAI:
  `{"type": "function", "function": {"name", "description", "parameters"}}`.
  El contenido de `parameters` es el mismo JSON Schema de la fase 1
  (extráelo a un helper `_propiedades_filtro(df, glosario)` compartido por
  ambos tools). Crea `construir_tools(df, glosario)`.
- El loop cambia de dialecto pero no de lógica: mientras
  `respuesta.choices[0].message.tool_calls` no sea vacío → añade el mensaje
  assistant (con sus `tool_calls` serializados), ejecuta cada tool call
  (ojo: `arguments` llega como *string* JSON — parséalo con tolerancia a
  error), y responde cada uno con un mensaje `{"role": "tool",
  "tool_call_id": ..., "content": json.dumps(salida)}`. Sin `tool_calls`,
  el `content` es la respuesta final.
- **Diccionario `PROVEEDORES`**: por cada proveedor (`anthropic`, `gemini`,
  `openai`), su `modelo_default` y un booleano `verificado` que significa
  "el set de 16 se corrió contra él con resultado ≥ criterio".
  **`openai` queda `verificado: False`** con un comentario explícito: está
  implementado con el mismo patrón pero sin API key para correr la
  evaluación — no lo presentes al nivel de los verificados.
- **BYOK estricto**: si no llega `api_key`, lanza `ValueError` — nunca dejes
  que LiteLLM recoja en silencio una clave del entorno del servidor. La clave
  no se imprime, no se loguea, no se guarda.

### 4.2 Keywords portables vs. efectos lanzables (sección 4b)

- `keywords_portables(df)`: la unión de todos los `keywordRefs` del
  DataFrame — las keywords que al menos una carta coleccionable **porta**.
- En `construir_system_prompt(glosario, df)`, parte el glosario de keywords
  en dos secciones usando ese set: las **PORTABLES** (utilizables en
  `filtrar_cartas`) y las **NO FILTRABLES** (existen como efectos que las
  cartas *causan* — `Stun`, `Frostbite`, etc. — pero ninguna carta las lleva;
  el prompt debe decir explícitamente que filtrar por ellas devuelve 0 y que
  el camino es `buscar_semantica` con fraseo de carta, con el ejemplo
  Aturdir → "Lanzo Aturdir a un enemigo").
- El resto del system prompt (lookups de regiones/rarezas/velocidades, guía
  de decisión de tools, la instrucción de frasear como texto de carta) viene
  tal cual de la fase 1 — no lo re-diseñes.

### 4.3 Cartas citadas en la respuesta final (sección 5)

El mecanismo elegido: **una línea final obligatoria `CARTAS: code1, code2...`**
en la respuesta del agente, parseada con regex. Por qué esta opción y no un
tool dedicado de "entrega":

- Funciona idéntico en los tres proveedores (un tool final obligatorio
  depende de `tool_choice` forzado, que se comporta distinto por proveedor).
- No añade una llamada extra al LLM (costo/latencia).
- Los `cardCode` tienen formato inconfundible (`\d{2}[A-Z]{2}\d{3}`, p. ej.
  `01IO012`): el parseo es trivial y sin falsos positivos razonables.
- Degrada bien: si el modelo omite la línea, buscas códigos en todo el
  texto; si tampoco hay, caes a "última tool call con resultados" (el
  criterio viejo). El campo `metodo_cartas` de la respuesta dice cuál de los
  tres caminos se usó — visibilidad para depurar.

Qué construir:

- En el system prompt: la instrucción del formato obligatorio (última línea
  `CARTAS: ...`, máximo 25, `CARTAS: ninguna` si no hay).
- `extraer_cartas_citadas(texto, codigos_validos)`: prioriza la línea
  `CARTAS:`; si no está, regex sobre todo el texto; filtra códigos
  inexistentes; dedup preservando orden.
- `_limpiar_respuesta(texto)`: quita la línea `CARTAS:` del texto que se
  muestra al usuario (es protocolo interno, no contenido).

### 4.4 El loop como generador (prepara la sección 6a)

Estructura el loop como **generador de eventos** (`eventos_agente(...)`) que
hace `yield` de dicts: `{"tipo": "inicio"}`, `{"tipo": "tool_use", ...}`,
`{"tipo": "tool_result", ...}` y al final `{"tipo": "respuesta", "texto",
"cartas", "metodo_cartas", "llamadas"}`. `consultar_agente(...)` pasa a ser
un consumidor trivial del generador que devuelve el último evento como dict.
Así el endpoint SSE y el síncrono comparten **el mismo loop** — cero
duplicación.

`carta_a_dict` gana un parámetro `completo`: `False` (compacto, para los
tool_result del LLM — tokens) y `True` (para la API: añade `regionRefs`,
`keywordRefs`, `rarityRef`, `velocidadRef`, `supertipo`, `descripcionSubida`,
`imagen`, `imagenFull`). Los campos `*Ref` en la respuesta de la API no son
decorativos: son los valores estables que usan los tests y usará el frontend.

## 5. `evaluacion.py` — el set contra la API

Reformula los 16 casos de fase 1 con dos cambios:

- `ejecucion_directa` (lambda de Python) se convierte en **`peticion`**: una
  tupla `(ruta, payload)` — p. ej. F1 → `("/cartas/filtrar", {"region":
  "Noxus", "tipo": "Unidad", "costo_max": 2})`. La capa A pasa a validar la
  API completa (schemas, serialización, estado), no solo la lógica interna.
- `verificar` opera sobre las cartas **como las devuelve la API** (dicts con
  `coste`, `regionRefs`, `keywordRefs`...), no sobre filas de DataFrame.
  Adapta `texto_habilidad`, `todas` y `alguna` a listas de dicts.

Las consultas y criterios en sí no cambian — están validados.

## 6. `api.py` — FastAPI

### Estado y arranque

- **Lifespan** (`@asynccontextmanager`): llama `cargar_recursos()` una vez y
  guarda el resultado. Si el índice no está construido, el arranque **falla**
  con el RuntimeError de instrucciones — decisión deliberada (sección 6d):
  mejor un deploy que truena con "corre build_index" que un servidor que
  reconstruye índices cuando nadie lo mira.
- **CORS**: `CORSMiddleware` con `allow_origins` desde la variable de entorno
  `ORIGENES_CORS` (lista separada por comas), default
  `http://localhost:3000` (el dev server de Next.js). En producción pondrás
  ahí el dominio de Vercel.

### Schemas (Pydantic)

- `FiltroParams`: espejo exacto de los parámetros de `filtrar_cartas`, todos
  opcionales, con `ge=0` en los numéricos.
- `BusquedaRequest`: `texto_consulta` (requerido), `top_k` (default 10,
  acotado 1–100), `filtro_metadata: Optional[FiltroParams]` — el híbrido.
- `AgenteRequest`: `consulta`, `proveedor` (un `Literal` de los tres),
  `modelo` opcional, `api_key` requerida, `max_turnos` acotado.
- `CartaOut` (el shape de `carta_a_dict(completo=True)` + `distancia`
  opcional), `CartasResponse {total, cartas}`, `AgenteResponse {respuesta,
  cartas, llamadas, metodo_cartas}`, `ProveedorOut`.

### Endpoints

| Método/ruta | Qué hace |
|---|---|
| `GET /salud` | ok, versión, nº de cartas, modelo de embeddings |
| `GET /proveedores` | los tres proveedores con su `verificado` — para que la UI marque GPT como no verificado |
| `POST /cartas/filtrar` | `FiltroParams` → `filtrar_cartas` |
| `POST /cartas/buscar` | `BusquedaRequest` → `buscar_semantica` (híbrido si trae filtro) |
| `POST /agente` | `AgenteRequest` → `consultar_agente` (síncrono) |
| `POST /agente/stream` | lo mismo, como SSE por pasos |

`POST` (y no `GET` con query params) también para filtrar/buscar: los
payloads tienen listas y objetos anidados, y así la `api_key` del agente
jamás puede acabar en un access log de query strings.

### Errores

Crea `_error_agente(e)` que mapee las excepciones de LiteLLM a HTTP
accionable: `AuthenticationError` → 401 "el proveedor rechazó la api_key",
`RateLimitError` → 429, `BadRequestError`/`NotFoundError` → 400, `ValueError`
propio → 400, resto → 502. Para los 400 del proveedor, **extrae el mensaje
humano** del body del error (`_mensaje_proveedor`, regex sobre el campo
`"message"`, recortado) y pásalo en el detail: ahí caen tanto "modelo
inválido" como cosas de cuenta tipo "credit balance too low" — en BYOK ese
mensaje es del usuario y es lo único accionable para él (lección aprendida:
la primera versión decía "¿modelo inválido?" para un crédito agotado).
**Nunca** incluyas la api_key en un mensaje de error. Los errores de
validación (tipos mal, campos faltantes) los da Pydantic solo, como 422.

### La decisión de streaming (sección 6a)

**Se implementa SSE por pasos desde ya; el streaming token a token queda
como pendiente explícito de la fase 3.** Razonamiento:

- Lo que más valor da a la UI es ver el *progreso del agente* (qué tool
  llamó, cuántas cartas encontró) mientras piensa — eso son los eventos del
  generador, y sale casi gratis (`StreamingResponse` +
  `f"data: {json}\n\n"`).
- El token a token del texto final exige `litellm.completion(stream=True)`
  con reconstrucción de tool_calls parciales multi-proveedor — complejidad
  real que conviene abordar cuando el consumidor (Vercel AI SDK) esté
  enfrente para probarla de verdad.
- El evento de error también viaja por el stream (`{"tipo": "error", ...}`)
  para que el cliente no se quede colgado.

## 7. Tests (`tests/` + `pytest.ini`)

- `conftest.py`: fixture `cliente` de scope sesión — `with TestClient(app)`
  (el `with` dispara el lifespan: los tests corren contra la API real con
  recursos cargados). Carga `.env`.
- `test_capa_a.py`: un test parametrizado sobre `CONSULTAS_EVALUACION`
  (ids = F1..H4): POST a `caso["peticion"]`, status 200, y
  `caso["verificar"](cartas)`. Añade tests de contorno: `/salud`,
  `/proveedores` marca openai como no verificado, filtro con tipo inválido →
  422, agente sin api_key → 422.
- `test_capa_b.py`: tras el marker `@pytest.mark.agente`. Parametrizado por
  proveedor (`anthropic`/`gemini`, cada uno con su variable de entorno; skip
  si falta). Corre las 16 consultas por `/agente` y **asserta el total ≥ 14**
  (no caso por caso: el criterio de fase tolera 2 fallos de exploración).
  Imprime la tabla PASA/FALLA con `metodo_cartas` y tools usados.
- **Ritmo para tiers gratuitos** (lección aprendida al correrlo): el free
  tier de Gemini permite ~10 requests/minuto y el agente hace 2-3 por
  consulta — la primera corrida murió en cascada de 429 a partir del caso 4,
  midiendo la cuota y no al agente. Parametriza una **pausa entre casos** por
  proveedor (0s para Claude, ~10s para Gemini) y un helper
  `_post_con_reintentos` que ante un 429 espere (~25s) y reintente unas
  veces antes de dar el caso por fallido. Complementa en `agente.py` con
  `num_retries=2` en `litellm.completion` para los 429/5xx transitorios
  dentro del loop.
- `pytest.ini`: registra el marker y pon `addopts = -m "not agente"` — el
  default no gasta API; la capa B se corre a propósito con
  `pytest -m agente -s`.

## 8. El A/B de embeddings (`scripts/comparar_embeddings.py`, sección 4a)

- Candidato elegido: **`intfloat/multilingual-e5-large`** (local, gratis,
  ~2.2 GB). `voyage-3` y `text-embedding-3-large` quedan documentados como
  alternativas de pago — sin credenciales para probarlas, no se comparan a
  ciegas.
- El script corre **en memoria** (encode de las 1,647 cartas + numpy para
  coseno), sin tocar el índice persistido — comparar no debe requerir
  reconstruir nada.
- Dos baterías:
  1. **Set estándar**: los 10 casos semánticos/híbridos con los criterios de
     la evaluación (que el candidato no empeore lo que ya pasa).
  2. **Sensibilidad al fraseo**: las formulaciones que *fallaron* en fase 1 —
     las consultas abstractas originales y el "Otorgo Barrera a un aliado"
     que hundió la capa B en S3 — contando aciertos@10. Esta batería es la
     que responde la pregunta real: ¿el modelo grande cierra la brecha entre
     lenguaje de usuario y lenguaje de carta?
- Ojo E5: exige prefijos `"passage: "`/`"query: "` — sin ellos rinde mal y la
  comparación sería inválida.
- Documenta la tabla completa de resultados en esta guía (no solo el
  veredicto) y decide: si e5 iguala el set estándar y gana claramente en
  fraseo, se cambia `MODELO_EMBEDDINGS` (+ prefijos) en `stores.py` y se
  reconstruye el índice; si no, se queda MiniLM y el A/B queda documentado.

### Resultados del A/B (proyecto de referencia)

Corrida real, aciertos@10 por caso (criterio de PASA idéntico a la
evaluación):

| Batería | Caso | MiniLM | e5-large |
|---|---|---|---|
| Estándar | S1 robar cartas | 8/10 | 7/10 |
| Estándar | S2 curar nexo | 5/10 | **10/10** |
| Estándar | S3 dar Barrera | 4/10 | **10/10** |
| Estándar | S4 aturdir | 4/10 | **10/10** |
| Estándar | S5 daño en área | 3/10 | 4/10 |
| Estándar | S6 revivir | 4/10 | 5/10 |
| Estándar | H1 daño al nexo (hechizos ≤3) | 2/10 | **7/10** |
| Estándar | H2 buffs en Demacia | 3/10 | **8/10** |
| Estándar | H3 robo en Aguasturbias | 7/10 | 7/10 |
| Estándar | H4 celestiales Targón | 6/10 | **9/10** |
| | **Set estándar (PASA)** | 10/10 | 10/10 |
| Fraseo | "Otorgo Barrera" (falló en capa B) | 2/10 | **8/10** |
| Fraseo | abstracta: aturdir sin atacar | 1/10 | **6/10** |
| Fraseo | abstracta: curar sanar nexo | 1/10 | **10/10** |
| Fraseo | abstracta: daño a todas a la vez | 2/10 | 4/10 |
| Fraseo | casual: "dejar sin turno a un enemigo" | 1/10 | 0/10 |
| | **Fraseo (suma aciertos@10)** | 7/50 | **28/50** |

**Veredicto: se cambia a e5-large.** Iguala el set estándar en PASA/FALLA
pero con márgenes mucho más holgados (S2/S3/S4 al 10/10), y cuadruplica la
robustez al fraseo — incluyendo la formulación exacta que hundió S3 en la
capa B de la fase 1. Costos del cambio: 2.2 GB vs 470 MB de modelo, 1024 vs
384 dimensiones (índice más pesado), encode algo más lento (irrelevante en
GPU a esta escala). La consulta "casual" (0/10) muestra que ningún embedding
sustituye al agente reformulando: la instrucción de frasear como carta sigue
vigente.

## 9. Orden de trabajo sugerido

1. `ingesta.py` y `stores.py` (sin agente) + `build_index.py` → corre el
   build.
2. `evaluacion.py` + `api.py` solo con `/salud`, `/cartas/filtrar`,
   `/cartas/buscar` → `test_capa_a.py` en verde (además de validar la
   modularización, F1–H4 deben dar exactamente lo mismo que en el notebook).
3. `agente.py` con LiteLLM + `/agente` → prueba manual con tu clave de
   Claude.
4. `test_capa_b.py` → `pytest -m agente -s` con Claude; luego Gemini.
5. El A/B de embeddings; si cambia el modelo: editar constantes, rebuild,
   y re-correr capa A y B (documenta el antes/después).
6. `/agente/stream`, CORS, `/proveedores`.

## Criterio de éxito

`pytest` (capa A, contra los endpoints): **16/16**. `pytest -m agente -s`
con Claude: **≥14/16**. Documentados los números de Gemini y el antes/después
de cualquier cambio de modelo de embeddings o de criterio de capa B.

### Resultados de la corrida de referencia

| Métrica | Fase 1 (notebook) | Fase 2 (API) |
|---|---|---|
| Capa A | 16/16 | **16/16** (vía endpoints) |
| Capa B — Claude | 14/16 | **16/16** |
| Capa B — Gemini | — | incompleta: bloqueada por cuota del free tier (ver nota) |

**Nota Gemini.** El free tier actual de la API de Gemini (~20 requests/día
por modelo) no alcanza para las ~40 llamadas LLM del set: tres corridas
(contra `gemini-2.5-flash` y `gemini-2.5-flash-lite`) se agotaron a mitad.
Evidencia parcial acumulada: **7 casos distintos pasados (F1–F6, S2) y cero
fallos de calidad** — el 100% de los fallos fueron 429 de cuota. Aplicando la
regla de esta fase (no dar por soportado sin el set completo), `gemini` queda
`verificado: False` en `/proveedores` hasta correr
`pytest -m agente -s -k gemini` con cuota disponible (reset diario, o clave
de pago). Los reintentos ante 429 sirven para límites por minuto, pero contra
una cuota *diaria* son contraproducentes (cada reintento consume cuota) —
por eso el helper reintenta pocas veces y se rinde.

El salto de la capa B con Claude (14 → 16) viene de las dos mejoras de esta
fase actuando juntas: **e5-large** absorbe la variación de fraseo que hundió
S3 ("Otorgo" vs "Doy" Barrera), y el criterio de **cartas citadas** deja de
castigar la exploración que hundió S4 (el agente exploró cinco formulaciones
y la evaluación vieja calificaba una llamada intermedia). S4 además ya no
intenta `filtrar_cartas(keywords=["Stun"])`: el system prompt le dice que
`Stun` no es portable y va directo a semántica.
