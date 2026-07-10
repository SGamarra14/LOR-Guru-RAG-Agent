# LoR Guru — Fase 1: guía de construcción del notebook

Esta guía te lleva paso a paso a recrear, por tu cuenta, el notebook de prueba de
concepto de **búsqueda de cartas de Legends of Runeterra en lenguaje natural**.
No contiene código resuelto: cada paso te dice **qué construir y qué debe
cumplir**. Si te estancas en un paso, el notebook de referencia
[`lor_guru_fase1.ipynb`](lor_guru_fase1.ipynb) tiene la misma estructura y los
mismos nombres de funciones, sección por sección.

**Requisitos previos**

- Python 3.11+ con Jupyter.
- Instala: `pandas`, `requests`, `chromadb`, `sentence-transformers`,
  `anthropic`, `python-dotenv`, `matplotlib` (ver `requirements.txt`).
- Una API key de Anthropic en la variable de entorno `ANTHROPIC_API_KEY` (o en
  un archivo `.env` en la raíz del proyecto). Sin ella, todo funciona menos las
  secciones 8 y 10-B (el agente); diseña el notebook para que lo detecte y lo
  diga, en vez de reventar.

**Estructura del proyecto**

```
Lor Guru/
├── lor_guru_fase1.ipynb   # el notebook (todo vive aquí en fase 1)
├── data/
│   ├── cards/set*.json    # se descargan en la sección 2
│   └── globals-es_mx.json
├── chroma_db/             # lo crea Chroma en la sección 6
├── requirements.txt
└── .env                   # ANTHROPIC_API_KEY=... (no lo subas a git)
```

---

## 1. Introducción y objetivo (markdown)

Abre el notebook con una celda markdown que explique, para un lector que no ha
visto este proyecto:

- El problema: los buscadores de cartas existentes exigen filtros manuales o
  texto exacto; queremos "cartas baratas que curen mi nexo" en español.
- La lección del intento anterior: mezclar stats numéricos y texto de habilidad
  en un solo embedding degrada la búsqueda. Los modelos de embeddings capturan
  significado en lenguaje natural, no relaciones numéricas; un embedding jamás
  filtra bien "coste ≤ 3".
- La arquitectura de esta versión: **campos estructurados → filtros exactos;
  texto de habilidad → embeddings; un agente con tool use decide cuál usar (o
  ambos, filtrando primero)**.
- El criterio de éxito de la fase: el notebook corre completo y ≥80% del set de
  evaluación devuelve resultados relevantes.

---

## 2. Obtención de datos y armado del DataFrame

### La decisión de diseño: descarga propia con caché local

Tenías tres opciones y conviene que tu markdown las discuta:

1. **Asumir que los archivos ya existen localmente.** Es lo más simple, pero el
   notebook deja de ser reproducible: quien lo clone (o tú en otra máquina)
   tiene que adivinar de dónde sacar los datos. Para un portafolio eso es un
   punto en contra.
2. **Descargar siempre.** Reproducible, pero cada corrida golpea el CDN de Riot
   y tarda; además, si el CDN falla un día, el notebook no corre aunque ya
   tengas los datos de ayer.
3. **Descargar con caché local (la elegida).** Si el archivo ya existe en
   `data/`, se usa; si no, se descarga. Primera corrida: reproducible desde
   cero. Corridas siguientes: instantáneas y sin red. Un parámetro `forzar`
   permite refrescar cuando salga un parche nuevo.

Puntos duros del origen de datos (ya validados, úsalos tal cual):

- URL: `https://dd.b.pvp.net/latest/{set}-es_mx.zip` — el tag `latest` evita
  depender de un número de versión que caduca.
- La lista de sets **no** es `set1..set9`: incluye también `set6cde` y `set7b`.
- Dentro de cada zip, el JSON está en `es_mx/data/{set}-es_mx.json`.
- El bundle core: `https://dd.b.pvp.net/latest/core-es_mx.zip`, con el JSON en
  `es_mx/data/globals-es_mx.json`.

### Qué construir

Define constantes de módulo: `RUTA_DATOS` (`data/`), `RUTA_CARTAS`
(`data/cards/`), `RUTA_GLOBALS` (`data/globals-es_mx.json`), `URL_BASE` y la
lista `SETS`.

**`descargar_bundle(nombre_bundle, ruta_interna, ruta_destino, forzar=False)`**
— descarga un zip del CDN y extrae un único JSON.

- Si `ruta_destino` existe y no se fuerza: no descarga (imprime que usó caché)
  y devuelve `True`.
- Descarga con `requests.get(url, timeout=...)`; maneja tanto excepciones de
  red como códigos HTTP ≠ 200 imprimiendo el problema y devolviendo `False`
  (un set que no existe no debe tumbar el notebook).
- Abre el zip en memoria (`zipfile.ZipFile` + `io.BytesIO`), verifica que
  `ruta_interna` esté en el zip, extrae esos bytes y escríbelos en
  `ruta_destino` (creando carpetas padre si hace falta).

**`descargar_datos(forzar=False)`** — recorre `SETS` llamando a
`descargar_bundle` para cada uno y luego descarga el bundle `core`.

**`cargar_cartas(carpeta)`** — lee todos los `.json` de `carpeta` y los combina
en un solo `DataFrame`, una fila por carta. Debe cumplir:

- Filtra `collectible == True` (excluye tokens y variantes internas).
- Se queda solo con las columnas que el proyecto usa: `cardCode`, `name`,
  `cost`, `attack`, `health`, `type`, `supertype`, `subtypes`, `regions`,
  `regionRefs`, `rarity`, `rarityRef`, `keywords`, `keywordRefs`, `spellSpeed`,
  `spellSpeedRef`, `descriptionRaw`, `levelupDescriptionRaw`, `set`.
- Elimina duplicados por `cardCode` y resetea el índice.

> ⚠️ **Antes de escribir el parser, abre un `.json` descargado y confirma el
> esquema.** Dos sorpresas respecto a la documentación que circula por ahí:
> las cartas traen `regions`/`regionRefs` y `subtypes` como **listas** (hay
> cartas multi-región), no campos singulares; y `rarity` viene en mayúsculas
> ("COMÚN") mientras el glosario dice "Común" — otra razón para usar siempre
> los campos `*Ref` en la lógica. Los valores de `type` están localizados
> ("Unidad", "Hechizo", "Hito", "Equipo") y **no tienen** campo `typeRef`.

Termina la sección ejecutando `descargar_datos()` y `cargar_cartas(RUTA_CARTAS)`
hacia una variable `df_cartas`, y valida con asserts: ~1647 cartas
coleccionables y `cardCode` único.

---

## 3. Lookups Ref ↔ nombre y glosario de keywords

El bundle core es la fuente de verdad para traducir entre los valores `*Ref`
(estables, en inglés) y los nombres oficiales en español. Es mejor que derivar
los mapeos de las cartas por dos razones: trae las **descripciones** de cada
keyword (una carta solo dice `keywordRefs: ["Challenger"]`, no qué significa), y
trae traducciones que no adivinarías ("Ionia" → "Jonia", "Runeterra" →
"Runaterra").

**`cargar_glosario(ruta_globals)`** — lee el JSON y devuelve un `dict` con:

- Por cada categoría — `regiones` (`regions`), `rarezas` (`rarities`),
  `keywords` (`keywords`), `sets` (`sets`), `velocidades` (`spellSpeeds`) —
  dos diccionarios: `glosario["<categoria>"]` con `ref → nombre_es` y
  `glosario["<categoria>_inv"]` con el inverso.
- `glosario["descripciones_keywords"]`: `ref → {"nombre": ..., "descripcion": ...}`.
- Excluye entradas cuyo `name` sea `"Missing Translation"` (existen).

Detalles a cuidar:

- `regions` incluye "regiones" de un solo campeón (Kayn, Bardo, Rey Poro, el
  Dragón Ancestral...) por la mecánica de Origen. **Inclúyelas**: aparecen como
  `regionRef` en cartas reales.
- El ref de Targón en `regions` es `Targon` (ojo: en la lista de `keywords` del
  mismo archivo aparece un `MtTargon` que es otra cosa — el ícono de región en
  los textos de carta).

Valida con asserts: `glosario["regiones"]["Ionia"] == "Jonia"` y
`glosario["regiones"]["Runeterra"] == "Runaterra"`.

---

## 4. Exploración rápida

Unas pocas celdas para conocer el dataset y de paso generar evidencia de que la
ingesta funcionó:

- Total de cartas y conteo por `type` (deberías ver ~970 Unidad, ~566 Hechizo,
  ~81 Hito, ~30 Equipo) y por `supertype`.
- Distribución por región: como `regionRefs` es lista, usa
  `df.explode("regionRefs")` antes del `value_counts`, y traduce los refs a
  español con el glosario para mostrar.
- Histograma de `cost` (matplotlib) — la típica curva de maná.
- Cuántas cartas tienen `descriptionRaw` vacío. **Este número importa**: son
  cartas "vanilla" o cuyo texto es solo sus keywords, y justifica una decisión
  de la sección 6.

---

## 5. Store estructurado

Para ~1,600 filas, un DataFrame de pandas en memoria **es** el store
estructurado; SQLite sería razonable si quisieras practicar SQL o si el volumen
creciera órdenes de magnitud, pero añade una capa de serialización sin ganancia
aquí (y las columnas-lista como `keywordRefs` obligarían a tablas puente o
JSON embebido). En fase 2, si hay API, se revisita.

**`filtrar_cartas(df, region=None, costo_min=None, costo_max=None,
ataque_min=None, ataque_max=None, vida_min=None, vida_max=None, tipo=None,
supertipo=None, keywords=None, rareza=None, velocidad=None)`** — devuelve el
subconjunto del DataFrame que cumple **todos** los filtros presentes:

- Construye una máscara booleana que empieza en todo-`True` y se va
  restringiendo con cada parámetro no-`None` (`&=`).
- `region`, `rareza`, `velocidad` y `keywords` se comparan contra los campos
  `*Ref` (valores en inglés: `"Noxus"`, `"Champion"`, `"Burst"`,
  `["Challenger"]`). `region` debe buscar **pertenencia en la lista**
  `regionRefs`, no igualdad.
- `keywords` es una lista y exige que la carta tenga **todas** las indicadas.
- `tipo`/`supertipo` se comparan (sin distinguir mayúsculas) contra los valores
  localizados del dato: `"Unidad"`, `"Hechizo"`, `"Hito"`, `"Equipo"`;
  `"Campeón"`.
- Devuelve ordenado por `cost` y con índice reseteado.

Pruébala: campeones de Freljord con coste ≤ 3 debe incluir a Braum.

---

## 6. Store vectorial (embeddings solo de texto)

### Decisiones de diseño (explícalas en markdown)

**¿Por qué Chroma y no FAISS/pgvector/Qdrant?** FAISS es solo un índice de
vectores: rapidísimo, pero no persiste metadata ni ofrece filtrado por
metadata — tendrías que construir tú el mapeo id→carta y el filtrado híbrido.
pgvector/Qdrant/Weaviate son excelentes pero implican un servidor aparte, que
en una fase de validación es fricción pura. Chroma embebido corre dentro del
proceso, persiste a disco (`PersistentClient`) y —clave para este proyecto—
permite combinar `where=` sobre metadata con la búsqueda vectorial **en una
sola llamada**, que es exactamente el patrón híbrido que queremos validar.

**¿Por qué `paraphrase-multilingual-MiniLM-L12-v2`?** El corpus está en
español, así que un modelo solo-inglés (los `all-MiniLM-*` típicos) queda
descartado. Este modelo multilingüe (50+ idiomas, 384 dimensiones) corre local
y gratis, lo que permite iterar sin pensar en costos. Alternativas de más
calidad para fase 2: `voyage-3` o `text-embedding-3-large` (mejor recall,
pero son APIs de pago y meten latencia de red en cada re-indexado), o
`multilingual-e5-large` (local, mejor calidad, ~4× más pesado). Para validar
la arquitectura, el MiniLM basta; si la evaluación muestra recall pobre en la
capa semántica, subir de modelo es un cambio de una línea.

**¿Qué texto se embebe?** Solo lenguaje natural, nunca números de stats:
nombre, tipo (la palabra "Hechizo" aporta semántica), `descriptionRaw`,
`levelupDescriptionRaw` y — decisión importante — **las descripciones
oficiales de sus keywords** tomadas del glosario. La razón: viste en la
sección 4 que muchas cartas tienen `descriptionRaw` vacío porque su texto es
solo keywords (Braum: `Desafío, Regeneración` y descripción vacía). Sin este
enriquecimiento, esas cartas serían invisibles para "unidades que pueden
elegir a quién bloquean". Es texto en lenguaje natural, así que no
contamina el embedding como lo harían los stats.

### Qué construir

Constantes: `MODELO_EMBEDDINGS`, `RUTA_CHROMA` (`"chroma_db"`),
`NOMBRE_COLECCION` (`"cartas_lor"`).

**`construir_texto_carta(fila, glosario)`** — devuelve el string a embeber:
`"{nombre}. {tipo}."` + descripción (si no está vacía) + `"Subida de nivel:
..."` (si aplica) + `"{keyword}: {descripción oficial}"` por cada
`keywordRef` presente en el glosario.

Carga el modelo en una variable `modelo_st` (`SentenceTransformer(...)`; si
tienes GPU la usa sola — imprime `modelo_st.device` para confirmar).

**`construir_store_vectorial(df, glosario, reconstruir=False)`** — crea o
reutiliza la colección:

- `chromadb.PersistentClient(path=RUTA_CHROMA)` +
  `get_or_create_collection(..., metadata={"hnsw:space": "cosine"})` (la
  distancia por defecto de Chroma es L2; con embeddings normalizados quieres
  coseno).
- **Caché**: si `coleccion.count() == len(df)`, reutilízala y no recalcules
  nada (los embeddings de 1,600 cartas tardan; en CPU, varios minutos). Si el
  conteo no cuadra o `reconstruir=True`, bórrala y reconstruye.
- Genera los textos con `construir_texto_carta`, los embeddings con
  `modelo_st.encode(..., normalize_embeddings=True)` y añade a la colección en
  lotes (~500) con: `ids` = `cardCode`, `embeddings`, `documents` = los textos,
  y `metadatas` = dict por carta con `cardCode`, `cost`, `attack`, `health`,
  `type`, `rarityRef` y `regiones` (la lista `regionRefs` unida con `"|"` —
  la metadata de Chroma no acepta listas).

**`buscar_semantica(texto_consulta, top_k=10, filtro_metadata=None)`** — la
búsqueda híbrida:

- Si `filtro_metadata` viene (un dict con los **mismos parámetros** de
  `filtrar_cartas`): primero filtra exacto en el DataFrame, y si el resultado
  no está vacío arma `where = {"cardCode": {"$in": [códigos...]}}` para
  restringir Chroma a ese subconjunto. Si el filtro no deja nada, devuelve
  vacío sin consultar Chroma.
- ¿Por qué pasar por `filtrar_cartas` en vez de traducir los filtros a
  operadores `where` de Chroma? Porque los campos-lista (región, keywords) no
  se pueden filtrar bien en metadata plana, y porque así hay **una sola
  implementación** de la lógica de filtrado — el store estructurado — y el
  vectorial solo la consume. Un solo lugar donde arreglar bugs.
- Embebe la consulta (también normalizada), llama `coleccion.query(...,
  n_results=top_k, where=where)` y devuelve un DataFrame: las filas de
  `df_cartas` correspondientes a los ids devueltos (en el orden de Chroma) más
  una columna `distancia`.

Prueba a mano un par de consultas ("robar cartas al enemigo", "curar mi nexo")
y mira los resultados antes de seguir: es tu primera señal de si la capa
semántica funciona.

---

## 7. Tools del agente

El agente es un modelo de Claude que recibe la consulta del usuario y decide
qué herramienta llamar. Aquí defines el "contrato" de esas herramientas.

**Esquemas de tools** (`TOOLS`, lista de dicts con `name`, `description`,
`input_schema` en JSON Schema):

1. `filtrar_cartas` — parámetros opcionales espejo de la función de la
   sección 5: `region` (string, ref), `costo_min`, `costo_max`, `ataque_min`,
   `ataque_max`, `vida_min`, `vida_max` (enteros), `tipo`, `supertipo`
   (strings localizados), `keywords` (array de refs), `rareza`, `velocidad`
   (strings ref). En cada `description` del esquema deja claro **qué valores
   son válidos** (p. ej. `tipo` con `enum` de los 4 valores; en `region` y
   `keywords`, que deben ser refs en inglés según el glosario del system
   prompt).
2. `buscar_semantica` — `texto_consulta` (string, requerido), `top_k`
   (entero, default 10) y `filtro_metadata` (objeto opcional con las mismas
   propiedades que los parámetros de `filtrar_cartas`). La descripción debe
   explicar el patrón: si la petición mezcla condición numérica/categórica +
   descripción de efecto, usar `filtro_metadata` para acotar y el texto para
   la parte semántica.

**`carta_a_dict(fila)`** — reduce una fila a un dict compacto y serializable
para devolvérselo al modelo: `cardCode`, `nombre`, `regiones` (en español),
`coste`, `ataque`, `vida`, `tipo`, `rareza`, `keywords` (en español),
`descripcion`. No mandes las 19 columnas: los tokens cuestan.

**`ejecutar_tool(nombre, entrada)`** — el despachador: recibe el nombre del
tool y el dict de argumentos que produjo el modelo, llama a la función real y
devuelve un dict `{"total": n, "cartas": [...]}` (limita a ~25 cartas para no
inflar el contexto; informa el total real). Envuélvelo en `try/except` y
devuelve `{"error": "..."}` en caso de fallo — el modelo sabe corregirse si le
explicas el error.

**`construir_system_prompt(glosario, df)`** — genera el system prompt. Debe
incluir:

- El rol: asistente de búsqueda de cartas de LoR en español; decide entre
  filtros exactos, búsqueda semántica o ambas; responde con las cartas
  encontradas.
- **Los lookups completos** nombre-español → ref: regiones, rarezas,
  velocidades. Son pequeños y le permiten mapear "Jonia" → `Ionia` sin
  adivinar.
- **El glosario de keywords con sus descripciones** (`Desafío (Challenger):
  Puede elegir la unidad enemiga que va a bloquear.` ...). Esto cubre el caso
  donde el usuario describe el efecto sin nombrarlo ("cartas que curen mi
  nexo" → Drenar/Drain).
- Los valores exactos de `tipo`/`supertipo` **calculados del DataFrame**
  (`df["type"].unique()`), no escritos a mano.
- Guía de decisión: filtros para condiciones numéricas/categóricas; semántica
  para descripciones de efectos; híbrido con `filtro_metadata` cuando hay
  ambas. Y que si un tool devuelve 0 resultados, relaje el filtro o
  reformule antes de rendirse.

---

## 8. Loop del agente con tool use

**Modelo elegido: `claude-sonnet-5`** (~$3/M tokens de entrada, $15/M de
salida). Para orquestar 2 tools no hace falta el tope de gama; Haiku 4.5
($1/$5) es la alternativa aún más barata si el presupuesto aprieta, y Opus
($5/$25) sería exagerado aquí. El costo real por consulta es de fracciones de
centavo: el grueso del prompt (glosario + tools) ronda 2-3K tokens.

Configura el cliente: carga `.env` con `python-dotenv`, crea
`anthropic.Anthropic()` y guarda un booleano `HAY_API_KEY` para que las celdas
de agente se salten limpiamente si no hay clave.

**`consultar_agente(consulta, max_turnos=6, verbose=True)`** — el loop manual
de tool use:

1. Inicializa `messages` con el turno de usuario.
2. En un bucle (máximo `max_turnos`): llama a
   `client.messages.create(model=..., max_tokens=..., system=SYSTEM_PROMPT,
   tools=TOOLS, messages=messages)`.
3. Si `response.stop_reason != "tool_use"`: terminó — extrae el texto final y
   sal del bucle.
4. Si pidió tools: añade `{"role": "assistant", "content": response.content}`
   a `messages`, ejecuta **cada** bloque `tool_use` con `ejecutar_tool`, y
   añade un único mensaje `user` con todos los bloques `tool_result`
   (cada uno con su `tool_use_id` y el resultado serializado con
   `json.dumps`).
5. Acumula en un set los `cardCode` de todas las cartas devueltas por los
   tools: la evaluación automática se hace sobre **lo que los tools
   devolvieron**, no sobre el texto libre del modelo.
6. Devuelve un dict con `respuesta` (texto final), `cartas` (DataFrame con
   los códigos acumulados) y `llamadas` (lista de qué tools se llamaron y con
   qué argumentos — oro para depurar).

Con `verbose=True` imprime cada llamada a tool y sus argumentos: en la
evaluación querrás ver *cómo* razonó, no solo si acertó.

Prueba con 2-3 consultas sueltas antes de la evaluación formal.

---

## 9. Set de evaluación

Define `CONSULTAS_EVALUACION`: una lista de ~16 casos, cada uno un dict con:

- `id` (`F1..F6`, `S1..S6`, `H1..H4`), `tipo` (`filtro` / `semantica` /
  `hibrida`), `consulta` (la frase en español que recibiría el agente).
- `ejecucion_directa`: una lambda que llama al tool correcto **con los
  parámetros ya mapeados a mano** (p. ej. F1 →
  `filtrar_cartas(df, region="Noxus", tipo="Unidad", costo_max=2)`).
- `verificar`: una lambda que recibe un DataFrame de cartas y devuelve
  `True`/`False` **mecánicamente** (nada de juzgar a ojo).

Para las verificaciones crea tres helpers: `texto_habilidad(fila)` (concatena
`descriptionRaw` y `levelupDescriptionRaw`), `todas(cartas, condicion)` (no
vacío y todas cumplen — para filtros) y `alguna(cartas, condicion, minimo=1)`
(al menos N cumplen — para semántica, donde exigir 100% de precisión en el
top-10 sería irreal; pide 2-3 coincidencias). Las condiciones semánticas se
verifican con regex sobre `texto_habilidad` (usa `re.IGNORECASE`: hay textos
como "daño a TODAS las unidades") o por presencia de la keyword esperada
(p. ej. "curen mi nexo" → keyword `Drain` o regex de "curar/sanar").

> 💡 Un hallazgo que te vas a encontrar al afinar los casos semánticos: las
> consultas abstractas ("aturdir a un enemigo para que no pueda atacar ni
> bloquear") recuperan mal con este modelo de embeddings; frasea el
> `texto_consulta` de `ejecucion_directa` **imitando el estilo del texto de
> las cartas, en primera persona** ("Lanzo Aturdir a un enemigo", "Curo a tu
> nexo"). Y dale la misma instrucción al agente en el system prompt de la
> sección 7. El notebook de referencia documenta este hallazgo en su sección
> 10.

Cubre: 6 casos de filtro puro (región+coste, campeón por región, velocidad de
hechizo, keyword+coste, umbral de vida, keyword+región), 6 de semántica pura
(robar cartas, curar nexo, dar Barrera, aturdir, daño en área, revivir) y 4
híbridos (hechizos baratos de daño al nexo, buffs en Demacia, robo barato en
Aguasturbias, celestiales en Targón).

**El diseño en dos capas es deliberado:**

- **Capa A (directa)** ejecuta `ejecucion_directa` + `verificar`. Valida los
  stores y los criterios **sin gastar API ni depender de la clave**. Si un
  caso falla aquí, el problema es de datos/embeddings/criterio, no del agente.
- **Capa B (agente)** ejecuta `consultar_agente(consulta)` y aplica el mismo
  `verificar` a las cartas que devolvieron los tools del agente. Si A pasa y B
  falla, el problema es el mapeo del agente (system prompt, esquemas).

Esa separación te dice exactamente dónde iterar.

---

## 10. Corrida de la evaluación y análisis

- **`correr_evaluacion_directa()`**: recorre los casos, ejecuta capa A, imprime
  PASA/FALLA con el número de cartas, y para los casos semánticos muestra el
  top de resultados (para inspección cualitativa). Devuelve un DataFrame de
  resultados con la tasa de éxito.
- **`correr_evaluacion_agente()`**: igual pero con `consultar_agente`; guarda
  también qué tools llamó en cada caso. Protégela con `HAY_API_KEY`.
- Cierra con una tabla comparativa (id, tipo, capa A, capa B, tools usados) y
  una celda markdown de **análisis de fallos**: para cada caso fallido, hipótesis
  de por qué (¿el embedding no captó el matiz? ¿el agente eligió mal el tool?
  ¿el criterio de verificación es demasiado estricto?) y qué cambiarías.

Criterio de éxito de la fase: ≥80% en capa B (o en capa A si aún no tienes
API key). Documenta cualquier fallo sistemático antes de pasar a fase 2.

---

## 11. Conclusiones y próximos pasos (markdown)

Resume honestamente:

- Qué validó la fase: la separación filtros/embeddings funciona; el patrón
  híbrido (filtrar → buscar en el subconjunto) es expresable en una sola
  llamada; el agente mapea español → refs con el glosario en el prompt.
- Qué quedó débil (según tu análisis de la sección 10) y su hipótesis.
- Fase 2: extraer el código del notebook a módulos, envolver en FastAPI
  (endpoints de filtro, semántica y agente), considerar subir el modelo de
  embeddings si el recall semántico quedó corto, tests automatizados con el
  set de evaluación como base de regresión.
- Fase 3: UI, despliegue y actualización automática cuando salga parche
  (el tag `latest` + `descargar_datos(forzar=True)` ya lo dejan casi listo).

---

## 12. Consulta libre — pruébalo tú

Cierra el notebook con una mini-sección interactiva para jugar con el agente
sin tocar el resto:

- Una celda con una sola variable `MI_CONSULTA` (un string editable con la
  consulta en español).
- Una celda que, si `HAY_API_KEY`, llama a `consultar_agente(MI_CONSULTA)` e
  imprime la respuesta final (con `verbose=True` verás además qué tools llamó
  y con qué argumentos — la parte más ilustrativa).
- Una celda que muestra `resultado["cartas"]` como tabla (`display(...)` con
  las columnas de nombre, regiones, coste, ataque, vida, tipo, keywords y
  descripción).

Separar la variable de la ejecución permite re-correr solo estas celdas en
cada prueba.
