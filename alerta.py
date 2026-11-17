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


@st.cache_data(ttl=3600, show_spinner=False)
def _clima_guardado(ruta: str, modificado: float, anio: int):  # noqa: ARG001  (``modificado`` invalida el caché)
    return clima.guardado(ruta, anio)


@st.cache_data(ttl=3 * 3600, show_spinner="Bajando el clima de Open-Meteo…")
def _clima(lat: float, lon: float, anio: int) -> pd.DataFrame:
    return clima.campania(lat, lon, anio)


datos = L.cargar()
locs = list(datos["localidades"])
# punto elegido en el explorador de la web (?lat=…&lon=…&nombre=…): se agrega al selector con la calibración regional
_q = st.query_params
punto = None
try:
    if "lat" in _q and "lon" in _q:
        _lat, _lon = float(_q["lat"]), float(_q["lon"])
        if -55 <= _lat <= -21 and -74 <= _lon <= -53:
            punto = {"id": "punto", "nombre": (_q.get("nombre") or "Punto elegido")[:60], "lat": round(_lat, 4),
                     "lon": round(_lon, 4), "parametros": L.PARAMS_REGIONAL, "confianza": "regional", "campanias_locales": 0,
                     "nota": "Punto elegido en el explorador de localidades de la web: alerta con la calibración regional, sin "
                             "conteos locales. Clima ERA5-Land/ERA5 + ECMWF IFS (Open-Meteo)."}
            locs.insert(0, punto)
except (TypeError, ValueError):
    punto = None
inicial = "punto" if punto else _q.get("loc")
idx = next((i for i, x in enumerate(locs) if x["id"] == inicial), 0)
st.sidebar.markdown("## 📍 Localidad")
loc = st.sidebar.selectbox("Localidad", locs, index=idx, format_func=lambda x: x["nombre"], label_visibility="collapsed")
if loc["id"] != "punto":
    for _k in ("lat", "lon", "nombre"):
        if _k in st.query_params:
            del st.query_params[_k]
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
# primero el clima guardado por el workflow (dos veces por día); si falta o está viejo, se baja en vivo
_arch = BASE / "clima" / f"{loc['id']}.csv"
meteo, _emitido = _clima_guardado(str(_arch), _arch.stat().st_mtime if _arch.is_file() else 0, anio)
try:
    if meteo is None:
        meteo = _clima(loc["lat"], loc["lon"], anio)
        st.caption("Clima bajado en vivo de Open-Meteo.")
    else:
        st.caption(f"Clima actualizado el {_emitido} (se actualiza dos veces por día).")
except Exception as e:  # noqa: BLE001
    meteo = None
    st.error(f"No se pudo bajar el clima de Open-Meteo: {e}")

resultados = None
if meteo is not None and meteo.empty:
    st.warning(f"Open-Meteo no devolvió datos de clima para {loc['nombre']} en {anio} (ni ERA5-Land ni ERA5). Probá de nuevo "
               "en unos minutos.")
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
