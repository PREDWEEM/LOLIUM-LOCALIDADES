# -*- coding: utf-8 -*-
"""Página «Alerta por localidad»: elegir la localidad y ver su alerta."""
import importlib
import os
from pathlib import Path

import pandas as pd
import streamlit as st

import clima_openmeteo as clima
import localidades as L
from acceso_predweem import mostrar_sesion
from lolium_comun import pagina

BASE = Path(__file__).resolve().parent


@st.cache_data(ttl=3 * 3600, show_spinner="Bajando el clima de Open-Meteo…")
def _clima(lat: float, lon: float, anio: int) -> pd.DataFrame:
    return clima.campania(lat, lon, anio)


datos = L.cargar()
locs = datos["localidades"]
por_id = {x["id"]: x for x in locs}
inicial = st.query_params.get("loc")
idx = next((i for i, x in enumerate(locs) if x["id"] == inicial), 0)
st.sidebar.markdown("## 📍 Localidad")
loc = st.sidebar.selectbox("Localidad", locs, index=idx, format_func=lambda x: x["nombre"], label_visibility="collapsed")
st.query_params["loc"] = loc["id"]

pagina.encabezado(f"🌾 PREDWEEM LOLIUM — {loc['nombre'].upper()} · prueba", "PREDWEEM Lolium — localidades")
st.caption(f"Web de prueba: alerta para localidades sin app propia · {L.CONFIANZA.get(loc.get('confianza'), '')} · "
           f"lat {loc['lat']:.4f}, lon {loc['lon']:.4f} · clima ERA5-Land + ECMWF IFS (Open-Meteo).")
parametros = pagina.barra_lateral(BASE, loc["nombre"])
with st.sidebar.expander("Mapa de localidades"):
    pts = pd.DataFrame([{"lat": x["lat"], "lon": x["lon"], "color": "#dc2626" if x["id"] == loc["id"] else "#1d4ed8"} for x in locs]
                       + [{"lat": s["lat"], "lon": s["lon"], "color": "#9ca3af"} for s in datos["sitios_calibrados"]])
    st.map(pts, color="color", size=3500, zoom=5)
    st.caption("Rojo: localidad elegida · azul: otras localidades de prueba · gris: las 8 apps calibradas.")

anio = pd.Timestamp.now(tz="America/Argentina/Buenos_Aires").year
try:
    meteo = _clima(loc["lat"], loc["lon"], anio)
except Exception as e:  # noqa: BLE001
    meteo = None
    st.error(f"No se pudo bajar el clima de Open-Meteo: {e}")

resultados = None
if meteo is not None and not meteo.empty:
    os.environ["LOLIUM_ALERTA_PARAMS"] = str(BASE / loc.get("parametros", L.PARAMS_REGIONAL))
    try:
        from lolium_comun import alerta_lolmu as _al
        from lolium_comun import visualizacion_alerta_lolmu as _vis

        importlib.reload(_al)
        importlib.reload(_vis)
        resultados = _vis.mostrar_alerta_lolmu(
            meteo, **parametros,
            tope_hasta_ultimo_cero=True, curva_desde_ultimo_cero=True, curva_desde_primeras=True,
            localidad=loc["nombre"], nota_sitio=L.nota_markdown(loc))
    except Exception as e:  # noqa: BLE001
        st.warning(f"No se pudo calcular la alerta: {e}")

pagina.descarga_excel(resultados, loc["id"], f"descarga_excel_{loc['id']}")
mostrar_sesion()
