# -*- coding: utf-8 -*-
"""El set de evaluación de la fase 1, reformulado contra la API.

Cambios respecto al notebook:

- La "ejecución directa" (capa A) ya no llama funciones de Python: es una
  petición HTTP (`peticion`) contra el endpoint correspondiente. Así la
  regresión valida la API completa (schemas, serialización, estado), no solo
  la lógica interna.
- Los criterios (`verificar`) operan sobre las cartas tal como las devuelve
  la API (dicts de carta_a_dict completo), no sobre filas de DataFrame.
- La capa B evalúa las cartas que el agente CITA en su respuesta final
  (campo `cartas` del endpoint /agente), no la última tool call — el arreglo
  al criterio identificado en la fase 1 (caso S4).
"""
import re


def texto_habilidad(carta: dict) -> str:
    return f"{carta['descripcion']} {carta.get('descripcionSubida', '')}"


def alguna(cartas: list, condicion, minimo: int = 1) -> bool:
    """True si al menos `minimo` cartas cumplen la condición."""
    if not cartas:
        return False
    return sum(bool(condicion(c)) for c in cartas) >= minimo


def todas(cartas: list, condicion) -> bool:
    """True si hay cartas y TODAS cumplen."""
    if not cartas:
        return False
    return all(bool(condicion(c)) for c in cartas)


CONSULTAS_EVALUACION = [
    # ---------- filtro puro ----------
    dict(
        id="F1", tipo="filtro",
        consulta="Muéstrame las unidades de Noxus que cuesten 2 o menos",
        peticion=("/cartas/filtrar",
                  {"region": "Noxus", "tipo": "Unidad", "costo_max": 2}),
        verificar=lambda cs: todas(cs, lambda c: "Noxus" in c["regionRefs"]
                                   and c["coste"] <= 2 and c["tipo"] == "Unidad"),
    ),
    dict(
        id="F2", tipo="filtro",
        consulta="¿Qué campeones tiene Jonia?",
        peticion=("/cartas/filtrar", {"region": "Ionia", "rareza": "Champion"}),
        verificar=lambda cs: todas(cs, lambda c: "Ionia" in c["regionRefs"]
                                   and c["rarityRef"] == "Champion"),
    ),
    dict(
        id="F3", tipo="filtro",
        consulta="Hechizos de Ráfaga de Piltóver y Zaun",
        peticion=("/cartas/filtrar",
                  {"region": "PiltoverZaun", "tipo": "Hechizo",
                   "velocidad": "Burst"}),
        verificar=lambda cs: todas(cs, lambda c: "PiltoverZaun" in c["regionRefs"]
                                   and c["velocidadRef"] == "Burst"),
    ),
    dict(
        id="F4", tipo="filtro",
        consulta="Unidades con Desafío que cuesten máximo 4",
        peticion=("/cartas/filtrar",
                  {"tipo": "Unidad", "keywords": ["Challenger"], "costo_max": 4}),
        verificar=lambda cs: todas(cs, lambda c: "Challenger" in c["keywordRefs"]
                                   and c["coste"] <= 4),
    ),
    dict(
        id="F5", tipo="filtro",
        consulta="Cartas del Fréljord con 8 o más de vida",
        peticion=("/cartas/filtrar", {"region": "Freljord", "vida_min": 8}),
        verificar=lambda cs: todas(cs, lambda c: "Freljord" in c["regionRefs"]
                                   and c["vida"] >= 8),
    ),
    dict(
        id="F6", tipo="filtro",
        consulta="Unidades Temibles de las Islas de la Sombra",
        peticion=("/cartas/filtrar",
                  {"region": "ShadowIsles", "tipo": "Unidad",
                   "keywords": ["Fearsome"]}),
        verificar=lambda cs: todas(cs, lambda c: "Fearsome" in c["keywordRefs"]
                                   and "ShadowIsles" in c["regionRefs"]),
    ),
    # ---------- semántica pura ----------
    # Los textos imitan el estilo del texto de las cartas (hallazgo fase 1).
    dict(
        id="S1", tipo="semantica",
        consulta="Cartas que roben cartas de la mano o del mazo del oponente",
        peticion=("/cartas/buscar",
                  {"texto_consulta":
                   "robar cartas de la mano o del mazo del oponente enemigo"}),
        verificar=lambda cs: alguna(cs, lambda c: "Nab" in c["keywordRefs"]
                                    or re.search(r"roba|hurtar",
                                                 texto_habilidad(c), re.I),
                                    minimo=3),
    ),
    dict(
        id="S2", tipo="semantica",
        consulta="Cartas que curen mi nexo",
        peticion=("/cartas/buscar", {"texto_consulta": "Curo a tu nexo"}),
        verificar=lambda cs: alguna(cs, lambda c: "Drain" in c["keywordRefs"]
                                    or re.search(r"\bcur|\bsana",
                                                 texto_habilidad(c), re.I),
                                    minimo=3),
    ),
    dict(
        id="S3", tipo="semantica",
        consulta="Cartas que den Barrera a un aliado",
        peticion=("/cartas/buscar", {"texto_consulta": "Doy Barrera a un aliado"}),
        verificar=lambda cs: alguna(cs, lambda c: "Barrier" in c["keywordRefs"]
                                    or "Barrera" in texto_habilidad(c), minimo=3),
    ),
    dict(
        id="S4", tipo="semantica",
        consulta="Efectos que aturdan unidades enemigas",
        peticion=("/cartas/buscar",
                  {"texto_consulta": "Lanzo Aturdir a un enemigo"}),
        verificar=lambda cs: alguna(cs, lambda c: re.search(
            r"aturd", texto_habilidad(c), re.I), minimo=3),
    ),
    dict(
        id="S5", tipo="semantica",
        consulta="Cartas que hagan daño a todas las unidades enemigas",
        peticion=("/cartas/buscar",
                  {"texto_consulta": "Inflijo 2 de daño a TODAS las unidades"}),
        verificar=lambda cs: alguna(cs, lambda c: re.search(
            r"daño a tod|a todos los enemigos", texto_habilidad(c), re.I),
            minimo=3),
    ),
    dict(
        id="S6", tipo="semantica",
        consulta="Cartas que revivan aliados que ya murieron",
        peticion=("/cartas/buscar",
                  {"texto_consulta":
                   "revivir invocar de nuevo un aliado que murió esta partida"}),
        verificar=lambda cs: alguna(cs, lambda c: re.search(
            r"reviv|que murió|que hayan muerto", texto_habilidad(c), re.I),
            minimo=2),
    ),
    # ---------- híbridas ----------
    dict(
        id="H1", tipo="hibrida",
        consulta="Hechizos de coste 3 o menos que hagan daño al nexo enemigo",
        peticion=("/cartas/buscar",
                  {"texto_consulta": "hacer daño al nexo enemigo",
                   "filtro_metadata": {"tipo": "Hechizo", "costo_max": 3}}),
        verificar=lambda cs: todas(cs, lambda c: c["tipo"] == "Hechizo"
                                   and c["coste"] <= 3)
                             and alguna(cs, lambda c: re.search(
                                 r"nexo enemigo", texto_habilidad(c), re.I),
                                 minimo=2),
    ),
    dict(
        id="H2", tipo="hibrida",
        consulta="Unidades de Demacia que den bonificaciones de stats a otros aliados",
        peticion=("/cartas/buscar",
                  {"texto_consulta":
                   "dar bonificación de ataque y vida a otros aliados",
                   "filtro_metadata": {"region": "Demacia", "tipo": "Unidad"}}),
        verificar=lambda cs: todas(cs, lambda c: "Demacia" in c["regionRefs"])
                             and alguna(cs, lambda c: re.search(
                                 r"\+\d+\|\+\d+", texto_habilidad(c)), minimo=3),
    ),
    dict(
        id="H3", tipo="hibrida",
        consulta="Unidades baratas de Aguasturbias que roben o saqueen al oponente",
        peticion=("/cartas/buscar",
                  {"texto_consulta": "robar cartas o saquear al oponente",
                   "filtro_metadata": {"region": "Bilgewater", "tipo": "Unidad",
                                       "costo_max": 3}}),
        verificar=lambda cs: todas(cs, lambda c: "Bilgewater" in c["regionRefs"]
                                   and c["coste"] <= 3)
                             and alguna(cs, lambda c: "Nab" in c["keywordRefs"]
                                        or "Plunder" in c["keywordRefs"]
                                        or re.search(r"roba|hurt|pillaje",
                                                     texto_habilidad(c), re.I),
                                        minimo=2),
    ),
    dict(
        id="H4", tipo="hibrida",
        consulta="Cartas de Targón que convoquen celestiales",
        peticion=("/cartas/buscar",
                  {"texto_consulta": "convocar cartas celestiales",
                   "filtro_metadata": {"region": "Targon"}}),
        verificar=lambda cs: todas(cs, lambda c: "Targon" in c["regionRefs"])
                             and alguna(cs, lambda c: re.search(
                                 r"celestial|convoc", texto_habilidad(c), re.I),
                                 minimo=3),
    ),
]
