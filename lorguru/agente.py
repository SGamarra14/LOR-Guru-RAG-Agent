# -*- coding: utf-8 -*-
"""El agente: tools, system prompt y loop de tool use multi-proveedor.

Cambios de fase 2 respecto al notebook:

1. **LiteLLM en vez del SDK de anthropic.** Un solo formato de
   messages/tools (el de OpenAI, que LiteLLM usa como lingua franca) y la
   librería traduce a Claude/GPT/Gemini. La API key del usuario se pasa por
   llamada (`api_key=`), nunca se persiste ni se loguea (BYOK).

2. **Keywords portables vs. efectos lanzables.** El caso S4 de la fase 1
   falló porque el agente filtró por `Stun`, que existe en el glosario pero
   ninguna carta coleccionable lleva como keywordRef (las cartas *lanzan*
   Aturdir, no lo portan). Ahora se cruzan los keywordRefs reales del
   DataFrame contra el glosario y el system prompt lista explícitamente las
   keywords NO filtrables, indicando usar búsqueda semántica para ellas.

3. **Cartas citadas en la respuesta final.** El agente termina SIEMPRE con
   una línea `CARTAS: code1, code2, ...`. La evaluación (y la API) toman esas
   como su respuesta efectiva — no la última tool call, que penalizaba la
   exploración legítima (fase 1, análisis de S4). Se eligió una línea
   convencional + regex (y no un tool dedicado de "entrega") porque funciona
   idéntico en los tres proveedores, no añade una llamada extra, y los
   cardCode tienen un formato inconfundible (p. ej. 01IO012) que hace el
   parseo trivial y sin ambigüedad. Fallback documentado: si el modelo omite
   la línea, se buscan códigos en todo el texto; si tampoco, se usa la última
   tool call con resultados (el criterio viejo).
"""
import json
import re

import litellm

from .stores import Recursos, buscar_semantica, filtrar_cartas

# BYOK puro: si el usuario no manda api_key, el request debe fallar — nunca
# queremos que LiteLLM recoja en silencio una clave del entorno del servidor.
litellm.drop_params = True  # ignora params que un proveedor no soporte

MAX_CARTAS_TOOL = 25
PATRON_CARDCODE = re.compile(r"\b\d{2}[A-Z]{2}\d{3}\b")

# "verificado" = ESE MODELO corrió el set de 16 consultas de evaluación con
# resultado >= criterio (GUIA_FASE2.md §7). La verificación es POR MODELO,
# no por proveedor: solo claude-sonnet-5 tiene 16/16 — no se extiende a
# Opus/Haiku ni al resto por ser de la misma casa.
# ⚠️ openai/GPT: implementado con el mismo patrón pero SIN VERIFICAR — no se
# cuenta con API key para correr la evaluación.
# ⚠️ gemini: sin verificar el set completo POR CUOTA, no por calidad: el free
# tier (~20 requests/día/modelo) no cubre las ~40 llamadas del set. Parciales
# sobre gemini-2.5-flash-lite: 7 casos distintos pasados, cero fallos de
# calidad. Completar con: pytest -m agente -s -k gemini (con cuota).
# Identificadores de modelos confirmados contra la documentación de cada
# proveedor en 2026-07 — revisar al desplegar, cambian con frecuencia.
PROVEEDORES = {
    "anthropic": {
        "nombre": "Claude (Anthropic)",
        "modelo_default": "claude-sonnet-5",
        "verificado": True,
        "modelos": [
            {"id": "claude-sonnet-5", "nombre": "Claude Sonnet 5",
             "verificado": True,
             "nota": "Recomendado: 16/16 en el set de evaluación (fase 2)"},
            {"id": "claude-opus-4-8", "nombre": "Claude Opus 4.8",
             "verificado": False, "nota": ""},
            {"id": "claude-haiku-4-5", "nombre": "Claude Haiku 4.5",
             "verificado": False, "nota": ""},
        ],
    },
    "gemini": {
        "nombre": "Gemini (Google)",
        "modelo_default": "gemini-2.5-flash-lite",
        "verificado": False,
        "modelos": [
            {"id": "gemini-2.5-flash-lite", "nombre": "Gemini 2.5 Flash-Lite",
             "verificado": False,
             "nota": "Evaluación parcial (7 casos, sin fallos de calidad); "
                     "el free tier no cubre el set completo"},
            {"id": "gemini-3.5-flash", "nombre": "Gemini 3.5 Flash",
             "verificado": False, "nota": ""},
            {"id": "gemini-3.1-flash-lite", "nombre": "Gemini 3.1 Flash-Lite",
             "verificado": False, "nota": ""},
        ],
    },
    "openai": {
        "nombre": "GPT (OpenAI)",
        "modelo_default": "gpt-5.5",
        "verificado": False,
        "modelos": [
            {"id": "gpt-5.5", "nombre": "GPT-5.5",
             "verificado": False,
             "nota": "Sin verificar: no hay credenciales para correr el set"},
            {"id": "gpt-5.4-mini", "nombre": "GPT-5.4 mini",
             "verificado": False, "nota": ""},
        ],
    },
}


# --- Formato de cartas ----------------------------------------------------

def carta_a_dict(fila, glosario, completo: bool = False) -> dict:
    """Versión serializable de una carta.

    completo=False: formato compacto para los tool_result del LLM (tokens).
    completo=True: formato para la API — añade los campos *Ref* (estables,
    para clientes/tests) y las URLs de imagen (fase 3).
    """
    base = {
        "cardCode": fila["cardCode"],
        "nombre": fila["name"],
        "regiones": list(fila["regions"]),
        "coste": int(fila["cost"]),
        "ataque": int(fila["attack"]),
        "vida": int(fila["health"]),
        "tipo": fila["type"],
        "rareza": glosario["rarezas"].get(fila["rarityRef"], fila["rarityRef"]),
        "keywords": list(fila["keywords"]),
        "descripcion": fila["descriptionRaw"],
    }
    if completo:
        base.update({
            "supertipo": fila["supertype"],
            "regionRefs": list(fila["regionRefs"]),
            "keywordRefs": list(fila["keywordRefs"]),
            "rarityRef": fila["rarityRef"],
            "velocidadRef": fila["spellSpeedRef"],
            "descripcionSubida": fila["levelupDescriptionRaw"],
            "imagen": fila["imagen"],
            "imagenFull": fila["imagen_full"],
        })
    return base


# --- Tools (formato OpenAI, la lingua franca de LiteLLM) ------------------

def _propiedades_filtro(df, glosario) -> dict:
    return {
        "region": {
            "type": "string",
            "description": "Ref de región EN INGLÉS según el lookup del system "
                           "prompt (p. ej. 'Noxus', 'Ionia', 'PiltoverZaun').",
        },
        "costo_min": {"type": "integer", "description": "Coste de maná mínimo (inclusive)."},
        "costo_max": {"type": "integer", "description": "Coste de maná máximo (inclusive)."},
        "ataque_min": {"type": "integer", "description": "Ataque mínimo (inclusive)."},
        "ataque_max": {"type": "integer", "description": "Ataque máximo (inclusive)."},
        "vida_min": {"type": "integer", "description": "Vida mínima (inclusive)."},
        "vida_max": {"type": "integer", "description": "Vida máxima (inclusive)."},
        "tipo": {
            "type": "string",
            "enum": sorted(df["type"].unique().tolist()),
            "description": "Tipo de carta (valores localizados del dato).",
        },
        "supertipo": {
            "type": "string",
            "enum": sorted(t for t in df["supertype"].unique() if t),
            "description": "Supertipo ('Campeón'). Equivale a rareza='Champion'.",
        },
        "keywords": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Refs de keywords EN INGLÉS (p. ej. ['Challenger']). "
                           "Solo keywords PORTABLES (ver system prompt). La "
                           "carta debe tener TODAS las indicadas.",
        },
        "rareza": {
            "type": "string",
            "enum": sorted(glosario["rarezas"].keys()),
            "description": "Ref de rareza en inglés.",
        },
        "velocidad": {
            "type": "string",
            "enum": sorted(glosario["velocidades"].keys()),
            "description": "Velocidad de hechizo (ref en inglés).",
        },
    }


def construir_tools(df, glosario) -> list:
    props = _propiedades_filtro(df, glosario)
    return [
        {
            "type": "function",
            "function": {
                "name": "filtrar_cartas",
                "description": (
                    "Filtra cartas por condiciones EXACTAS: región, rangos de "
                    "coste/ataque/vida, tipo, keywords portables, rareza y "
                    "velocidad de hechizo. Úsalo cuando la consulta se expresa "
                    "completa con estas condiciones. Devuelve ordenado por coste."
                ),
                "parameters": {"type": "object", "properties": props},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "buscar_semantica",
                "description": (
                    "Búsqueda semántica sobre el TEXTO de las habilidades (en "
                    "español). Úsalo cuando el usuario describe un efecto o "
                    "mecánica que no es un campo exacto. Si la consulta además "
                    "trae condiciones exactas, pásalas en filtro_metadata: la "
                    "búsqueda se hará SOLO dentro de ese subconjunto (híbrido)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "texto_consulta": {
                            "type": "string",
                            "description": "Descripción en español del efecto "
                                           "buscado, imitando el estilo del "
                                           "texto de las cartas.",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Cuántas cartas devolver (default 10).",
                        },
                        "filtro_metadata": {
                            "type": "object",
                            "properties": props,
                            "description": "Filtros exactos para acotar ANTES "
                                           "de buscar.",
                        },
                    },
                    "required": ["texto_consulta"],
                },
            },
        },
    ]


def ejecutar_tool(recursos: Recursos, nombre: str, entrada: dict) -> dict:
    """Despachador. Los errores vuelven como {"error": ...} para que el modelo
    pueda corregirse."""
    try:
        if nombre == "filtrar_cartas":
            cartas = filtrar_cartas(recursos.df, **entrada)
        elif nombre == "buscar_semantica":
            cartas = buscar_semantica(recursos, **entrada)
        else:
            return {"error": f"Tool desconocido: {nombre}"}
        return {
            "total": len(cartas),
            "cartas": [carta_a_dict(f, recursos.glosario)
                       for _, f in cartas.head(MAX_CARTAS_TOOL).iterrows()],
        }
    except TypeError as e:
        return {"error": f"Argumentos inválidos: {e}"}
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


# --- System prompt --------------------------------------------------------

def keywords_portables(df) -> set:
    """Refs de keywords que al menos una carta coleccionable PORTA."""
    portables = set()
    for refs in df["keywordRefs"]:
        portables.update(refs)
    return portables


def construir_system_prompt(glosario, df) -> str:
    regiones = "\n".join(
        f"- {nombre} -> {ref}"
        for ref, nombre in sorted(glosario["regiones"].items(), key=lambda x: x[1])
    )
    rarezas = "\n".join(
        f"- {nombre} -> {ref}" for ref, nombre in glosario["rarezas"].items()
    )
    velocidades = "\n".join(
        f"- {nombre} -> {ref}" for ref, nombre in glosario["velocidades"].items()
    )
    portables = keywords_portables(df)
    kw_filtrables, kw_no_filtrables = [], []
    for ref, d in sorted(glosario["descripciones_keywords"].items(),
                         key=lambda x: x[1]["nombre"]):
        if not d["descripcion"]:
            continue
        linea = f"- {d['nombre']} ({ref}): {d['descripcion']}"
        (kw_filtrables if ref in portables else kw_no_filtrables).append(linea)
    tipos = ", ".join(sorted(df["type"].unique()))
    supertipos = ", ".join(sorted(t for t in df["supertype"].unique() if t))

    return f"""Eres un asistente de búsqueda de cartas de Legends of Runeterra (LoR). \
Recibes consultas en español y las resuelves llamando a tus herramientas; al final \
respondes en español listando las cartas encontradas (nombre, coste, región y por qué \
son relevantes).

Cómo decidir qué herramienta usar:
- Condiciones exactas (región, coste, ataque, vida, tipo, rareza, keyword portable, \
velocidad) -> filtrar_cartas.
- El usuario describe un EFECTO o mecánica con sus palabras -> buscar_semantica.
- Mezcla de ambas -> buscar_semantica con filtro_metadata (filtra exacto primero, \
busca semánticamente dentro del subconjunto).
- Si el usuario describe el efecto de una keyword PORTABLE sin nombrarla, \
identifícala con el glosario y usa filtrar_cartas con esa keyword (más preciso que \
la búsqueda semántica). Ej.: "que curen mi nexo al hacer daño" -> Drain.
- Si un tool devuelve 0 resultados, relaja el filtro o reformula el texto antes de \
rendirte, y explica al usuario qué ajustaste.
- Al usar buscar_semantica, redacta texto_consulta imitando el ESTILO DEL TEXTO DE LAS \
CARTAS, en primera persona: "Curo a tu nexo", "Lanzo Aturdir a un enemigo", "Inflijo \
daño a TODAS las unidades". Recupera mucho mejor que describir el efecto en abstracto.

CURACIÓN (MUY IMPORTANTE): buscar_semantica devuelve las cartas MÁS PARECIDAS por \
significado, pero el parecido NO garantiza que cumplan la consulta — la cola de \
resultados suele traer ruido. Tu trabajo es filtrar ese ruido: LEE la `descripcion` de \
CADA carta devuelta y quédate SOLO con las que de verdad cumplen lo que pidió el \
usuario. Descarta sin piedad las que solo se parecen de lejos. Una respuesta de 4 \
cartas correctas es mejor que una de 12 donde la mitad no aplica. Si una carta buena no \
apareció en los resultados, sube top_k o reformula la búsqueda en vez de conformarte.

FORMATO OBLIGATORIO DEL FINAL DE TU RESPUESTA (no lo omitas nunca): la última línea debe \
ser exactamente
CARTAS: code1, code2, ...
con los cardCode EXACTAMENTE de las cartas que pasaron tu curación (las que citas en tu \
respuesta), máximo {MAX_CARTAS_TOOL}, en orden de relevancia. NO incluyas aquí cartas \
que descartaste por no cumplir. Si ninguna cumple, termina con "CARTAS: ninguna". No \
agregues nada después de esa línea.

Los parámetros region, keywords, rareza y velocidad usan los valores Ref EN INGLÉS de \
estos lookups (el usuario hablará en español):

Regiones (nombre español -> ref):
{regiones}

Rarezas:
{rarezas}

Velocidades de hechizo:
{velocidades}

Tipos de carta (valores exactos, localizados): {tipos}
Supertipos: {supertipos}

Keywords PORTABLES — al menos una carta las lleva; puedes usarlas en filtrar_cartas. \
Nombre español (ref): qué hace:
{chr(10).join(kw_filtrables)}

Keywords NO FILTRABLES — existen como efectos que las cartas CAUSAN (los lanzan a \
otras), pero NINGUNA carta coleccionable las porta como keyword. NUNCA las uses en \
filtrar_cartas (devolverá 0): para encontrarlas usa buscar_semantica con el estilo del \
texto de carta (p. ej. Aturdir -> "Lanzo Aturdir a un enemigo"):
{chr(10).join(kw_no_filtrables)}"""


# --- Cartas citadas -------------------------------------------------------

def extraer_cartas_citadas(texto: str, codigos_validos: set) -> list:
    """Extrae los cardCode citados en la respuesta final del agente.

    Prioriza la línea 'CARTAS: ...' (el formato obligatorio del system
    prompt); si no está, busca códigos en todo el texto. Devuelve solo
    códigos que existen, sin duplicados y en orden de aparición.
    """
    fuente = texto or ""
    coincidencia = re.search(r"CARTAS:\s*(.+)", fuente, re.IGNORECASE)
    if coincidencia:
        fuente = coincidencia.group(1)
    vistos, codigos = set(), []
    for codigo in PATRON_CARDCODE.findall(fuente):
        if codigo in codigos_validos and codigo not in vistos:
            vistos.add(codigo)
            codigos.append(codigo)
    return codigos


def _limpiar_respuesta(texto: str) -> str:
    """Quita la línea CARTAS: ... del texto que se muestra al usuario."""
    return re.sub(r"\n?CARTAS:.*$", "", texto or "",
                  flags=re.IGNORECASE | re.DOTALL).strip()


def cartas_por_nombre(texto: str, recuperadas: dict) -> list:
    """Fallback de curación: de las cartas que los tools recuperaron, quédate
    con aquellas cuyo NOMBRE aparece en la respuesta del agente.

    Los modelos citan cartas por nombre en la prosa aunque olviden la línea
    CARTAS: — esto recupera SU selección (curada) en vez de volcar los hits
    crudos del retrieval. `recuperadas` es {cardCode: nombre} en orden de
    aparición. El guard de longitud evita falsos positivos con nombres muy
    cortos.
    """
    t = (texto or "").lower()
    codigos = []
    for codigo, nombre in recuperadas.items():
        n = (nombre or "").lower().strip()
        if len(n) >= 4 and n in t:
            codigos.append(codigo)
    return codigos


# --- Loop del agente ------------------------------------------------------

def eventos_agente(recursos: Recursos, consulta: str, api_key: str,
                   proveedor: str = "anthropic", modelo: str = None,
                   max_turnos: int = 6):
    """Generador de eventos del loop de tool use (la base del streaming SSE).

    Emite dicts: {"tipo": "inicio"|"tool_use"|"tool_result"|"respuesta"}.
    El último evento ("respuesta") incluye el texto final y las cartas.
    """
    if proveedor not in PROVEEDORES:
        raise ValueError(f"Proveedor no soportado: {proveedor}. "
                         f"Opciones: {', '.join(PROVEEDORES)}")
    if not api_key:
        raise ValueError("Falta api_key: este servicio es BYOK, cada request "
                         "debe traer la clave del proveedor elegido.")

    modelo = modelo or PROVEEDORES[proveedor]["modelo_default"]
    modelo_litellm = f"{proveedor}/{modelo}"
    system = construir_system_prompt(recursos.glosario, recursos.df)
    tools = construir_tools(recursos.df, recursos.glosario)
    mensajes = [{"role": "system", "content": system},
                {"role": "user", "content": consulta}]
    llamadas = []
    codigos_ultima = []
    recuperadas = {}  # {cardCode: nombre} de TODAS las llamadas, para el fallback por nombre
    texto_final = ""

    yield {"tipo": "inicio", "proveedor": proveedor, "modelo": modelo}

    for _ in range(max_turnos):
        respuesta = litellm.completion(
            model=modelo_litellm,
            messages=mensajes,
            tools=tools,
            api_key=api_key,
            max_tokens=8000,
            num_retries=2,  # backoff automático ante 429/5xx transitorios
        )
        mensaje = respuesta.choices[0].message

        if not mensaje.tool_calls:
            texto_final = mensaje.content or ""
            break

        mensajes.append({
            "role": "assistant",
            "content": mensaje.content or "",
            "tool_calls": [tc.model_dump() for tc in mensaje.tool_calls],
        })
        for tc in mensaje.tool_calls:
            try:
                entrada = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                entrada = {}
            yield {"tipo": "tool_use", "tool": tc.function.name,
                   "entrada": entrada}
            salida = ejecutar_tool(recursos, tc.function.name, entrada)
            llamadas.append({"tool": tc.function.name, "entrada": entrada,
                             "total": salida.get("total", 0)})
            if salida.get("cartas"):
                codigos_ultima = [c["cardCode"] for c in salida["cartas"]]
                for c in salida["cartas"]:
                    recuperadas.setdefault(c["cardCode"], c["nombre"])
            yield {"tipo": "tool_result", "tool": tc.function.name,
                   "total": salida.get("total", 0),
                   "error": salida.get("error")}
            mensajes.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(salida, ensure_ascii=False),
            })

    # Selección de las cartas finales, de más a menos curada:
    # 1) citadas: la línea CARTAS: (o cardCodes en el texto) — la curación
    #    explícita del agente.
    # 2) nombres: si no citó códigos, las cartas recuperadas cuyo NOMBRE
    #    mencionó en la prosa — sigue siendo SU selección, no el retrieval crudo.
    # 3) ultima_llamada: red de seguridad — la última llamada con resultados
    #    (correcto para filtros puros donde todo el resultado es válido).
    codigos_validos = set(recursos.df["cardCode"])
    citadas = extraer_cartas_citadas(texto_final, codigos_validos)
    por_nombre = cartas_por_nombre(texto_final, recuperadas)
    if citadas:
        metodo = "citadas"
        codigos = citadas
    elif por_nombre:
        metodo = "nombres"
        codigos = por_nombre
    elif codigos_ultima:
        metodo = "ultima_llamada"
        codigos = codigos_ultima
    else:
        metodo = "ninguna"
        codigos = []

    indice = recursos.df.set_index("cardCode")
    cartas = [carta_a_dict(indice.loc[c].to_dict() | {"cardCode": c},
                           recursos.glosario, completo=True)
              for c in codigos]
    yield {"tipo": "respuesta",
           "texto": _limpiar_respuesta(texto_final),
           "cartas": cartas,
           "metodo_cartas": metodo,
           "llamadas": llamadas}


def consultar_agente(recursos: Recursos, consulta: str, api_key: str,
                     proveedor: str = "anthropic", modelo: str = None,
                     max_turnos: int = 6, verbose: bool = False) -> dict:
    """Versión síncrona: consume el generador y devuelve el evento final."""
    final = None
    for evento in eventos_agente(recursos, consulta, api_key,
                                 proveedor, modelo, max_turnos):
        if verbose and evento["tipo"] == "tool_use":
            print(f"  -> {evento['tool']}("
                  f"{json.dumps(evento['entrada'], ensure_ascii=False)})")
        if evento["tipo"] == "respuesta":
            final = evento
    return {"respuesta": final["texto"], "cartas": final["cartas"],
            "llamadas": final["llamadas"],
            "metodo_cartas": final["metodo_cartas"]}
