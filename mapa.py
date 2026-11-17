# -*- coding: utf-8 -*-
"""Mapa interactivo (Leaflet) para el visor: se mueve arrastrando, zoom con la rueda y doble clic para elegir el punto.

Componente propio de Streamlit sin dependencias de Python extra: ``componentes/mapa_dblclick/index.html`` (Leaflet 1.9.4
incluido en la carpeta; teselas de OpenStreetMap). Devuelve ``{"lat", "lon", "n"}`` del último doble clic (``n`` cuenta
los dobles clics, para distinguir uno nuevo de una nueva ejecución de la página) o ``None``.
"""
from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

_componente = components.declare_component(
    "mapa_dblclick", path=str(Path(__file__).resolve().parent / "componentes" / "mapa_dblclick"))


def mapa_dblclick(puntos: list[dict], centro: tuple[float, float], zoom: int = 6, seleccion: tuple[float, float] | None = None,
                  altura: int = 420, key: str | None = None) -> dict | None:
    """``puntos``: lista de ``{"lat", "lon", "nombre", "color", "etiqueta"}`` (``etiqueta`` = nombre siempre visible)."""
    return _componente(puntos=puntos, centro=list(centro), zoom=zoom, seleccion=list(seleccion) if seleccion else None,
                       altura=altura, key=key, default=None)
