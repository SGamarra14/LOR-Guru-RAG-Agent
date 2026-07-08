# -*- coding: utf-8 -*-
"""Regresión del parseo de la línea CARTAS: del agente (no gasta API).

Bug histórico: con listas largas el modelo envuelve los códigos en varias
líneas; la regex sin DOTALL solo leía la primera → el grid mostraba una sola
carta aunque la respuesta citara muchas.
"""
from lorguru.agente import cartas_por_nombre, extraer_cartas_citadas

VALIDOS = {"01NX050", "02NX003", "05NX014", "06NX027", "01SI025", "03SI008"}


def test_cartas_en_una_linea():
    txt = "Recomiendo estas.\nCARTAS: 01NX050, 02NX003, 05NX014, 06NX027"
    assert extraer_cartas_citadas(txt, VALIDOS) == \
        ["01NX050", "02NX003", "05NX014", "06NX027"]


def test_cartas_envueltas_en_varias_lineas():
    """El caso que fallaba: la lista envuelta debe recuperarse completa."""
    txt = ("CARTAS: 01NX050,\n02NX003, 05NX014, 06NX027,\n"
           "01SI025, 03SI008")
    assert extraer_cartas_citadas(txt, VALIDOS) == \
        ["01NX050", "02NX003", "05NX014", "06NX027", "01SI025", "03SI008"]


def test_envuelto_tras_el_primer_codigo():
    """El peor caso reportado: envuelve tras el primer código -> antes daba 1."""
    txt = "CARTAS: 01NX050,\n02NX003, 05NX014"
    assert extraer_cartas_citadas(txt, VALIDOS) == ["01NX050", "02NX003", "05NX014"]


def test_descarta_codigos_inexistentes_y_duplicados():
    txt = "CARTAS: 01NX050, 99ZZ999, 01NX050, 02NX003"
    assert extraer_cartas_citadas(txt, VALIDOS) == ["01NX050", "02NX003"]


def test_sin_linea_cartas_busca_en_todo_el_texto():
    txt = "Te sirve 01NX050 y también 02NX003."
    assert extraer_cartas_citadas(txt, VALIDOS) == ["01NX050", "02NX003"]


def test_fallback_por_nombre():
    recuperadas = {"01NX050": "Loto Mortal", "02NX003": "Fervor Noxiano",
                   "05NX014": "Carta Que No Mencionó"}
    txt = "Te recomiendo Loto Mortal y Fervor Noxiano para el mazo."
    assert cartas_por_nombre(txt, recuperadas) == ["01NX050", "02NX003"]
