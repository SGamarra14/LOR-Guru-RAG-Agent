# LoR Guru

**Busca cartas de _Legends of Runeterra_ describiéndolas en español natural.**
Un agente LLM decide —según tu consulta— si aplicar filtros exactos, búsqueda
semántica, o ambos, y te explica por qué eligió esas cartas.

### ▶ Pruébalo en vivo: **https://lor-guru-rag-agent.vercel.app/**

> Es **BYOK** (_bring your own key_): pones tu propia API key de Claude, Gemini
> o GPT en el navegador —no se guarda en ningún lado— y puedes **ver en vivo el
> flujo que sigue el agente**: qué herramienta llamó, con qué argumentos y cómo
> curó los resultados.

<img width="1285" height="857" alt="https-lor-guru-rag-agent vercel apsp-" src="https://github.com/user-attachments/assets/265d1735-5e30-4be0-aae7-af22945bc398" />

---

## Cómo funciona (RAG con tool use)

La idea central es **no mezclar** lo estructurado con lo semántico —el error
clásico al vectorizar todo junto—. En su lugar, el sistema tiene dos "almacenes"
y un agente que decide cuál usar:

1. **Filtros exactos** (pandas) para lo que es preciso: costo, ataque, vida,
   región, tipo, rareza, keywords.
2. **Búsqueda semántica** (embeddings + Chroma) solo sobre el _texto de las
   habilidades_ — nunca sobre los stats numéricos, que diluirían la señal.
3. Un **agente LLM con tool use** recibe tu español, lo traduce a las llamadas
   correctas y orquesta las dos herramientas:
   - `filtrar_cartas(...)` → el almacén estructurado.
   - `buscar_semantica(...)` → el vectorial, con un `filtro_metadata` opcional
     para el **patrón híbrido**: filtrar primero y buscar semánticamente solo
     dentro de ese subconjunto.
4. El agente **cura** los resultados (descarta el ruido del retrieval leyendo la
   descripción de cada carta) y responde con la explicación + las cartas.

El backend transmite el progreso paso a paso (SSE), por eso la UI muestra el
razonamiento del agente en tiempo real en vez de un spinner.

## Stack tecnológico

| Capa | Tecnología |
|---|---|
| **Frontend** | Next.js 16 · React 19 · TypeScript · Tailwind v4 · tipos generados desde OpenAPI |
| **Backend** | FastAPI · Pydantic · Server-Sent Events (streaming por pasos) |
| **Agente** | LiteLLM (multi-proveedor BYOK: Claude / Gemini / GPT) · tool use |
| **Datos** | Data Dragon de LoR (es_mx) · pandas |
| **Búsqueda vectorial** | Chroma (persistente) |
| **Embeddings** | API de Gemini `gemini-embedding-001` |
| **Tests** | pytest — set de evaluación de 16 consultas en dos capas |
| **Despliegue** | Frontend en **Vercel** · Backend en **Railway** (Docker) |

## Notebook de pruebas iniciales

El proyecto empezó como una **prueba de concepto en un Jupyter notebook**, donde
se validó el enfoque de principio a fin antes de escribir la API: ingesta de
datos, los dos almacenes, el agente y un set de evaluación de 16 consultas.
Está en [`docs/lor_guru_fase1.ipynb`](docs/lor_guru_fase1.ipynb) con sus salidas
guardadas, y es **reproducible localmente**.

## Correr localmente

```bash
pip install -r requirements.txt
cp .env.example .env                   # rellena tus claves

python -m lorguru.build_index          # descarga datos + construye el índice
uvicorn lorguru.api:app --reload       # API en :8000

cd webapp && npm install && npm run dev # UI en :3000
```

Detalle completo (arquitectura, decisiones de diseño, despliegue) en las guías
de cada fase dentro de [`docs/`](docs/).

---

Proyecto de portafolio. No afiliado a Riot Games. Los datos e imágenes de cartas
provienen del [Data Dragon](https://developer.riotgames.com/docs/lor) público de
_Legends of Runeterra_.
