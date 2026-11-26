# -*- coding: utf-8 -*-
"""Página «Nueva localidad» (visor): ubicar el punto, revisar el clima, ver la alerta, validar con conteos y proponerla."""
import importlib
import json
import os
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

import clima_openmeteo as clima
import localidades as L
from mapa import mapa_dblclick
from acceso_predweem import mostrar_sesion

BASE = Path(__file__).resolve().parent
CLIMA_DESDE, CLIMA_HASTA = 2011, 2025  # campañas del clima típico

# solo administradores cuando el control de ingreso está activo
def _secreto(nombre: str) -> dict:
    try:
        return dict(st.secrets.get(nombre, {}))
    except Exception:  # noqa: BLE001  (sin archivo de secretos)
        return {}


_acc = _secreto("acceso")
if _acc.get("activo"):
    _admins = {str(x).strip().lower() for x in _acc.get("administradores", [])}
    if str(getattr(st, "user", {}).get("email", "")).strip().lower() not in _admins:
        st.title("🗺️ Nueva localidad")
        st.info("Esta página es solo para administradores.")
        st.stop()


@st.cache_data(ttl=24 * 3600, show_spinner=False)
def _clima_ene_abr(lat: float, lon: float, anio: int) -> dict:
    return clima.clima_ene_abr(lat, lon, anio)


@st.cache_data(ttl=30 * 24 * 3600, show_spinner=False, persist="disk")
def _climatologia(lat: float, lon: float) -> dict:
    # 15 campañas de reanálisis por punto: tarda la primera vez y después queda guardado (no cambia)
    return clima.climatologia(lat, lon, CLIMA_DESDE, CLIMA_HASTA)


@st.cache_data(ttl=3 * 3600, show_spinner=False)
def _campania(lat: float, lon: float, anio: int) -> pd.DataFrame:
    return clima.campania(lat, lon, anio)


st.title("🗺️ Nueva localidad")
st.caption("Ubicá el punto, revisá si su clima se parece al de los sitios calibrados, mirá cómo se vería la alerta y, si hay "
           "conteos, validala. Al final, el visor propone la localidad con un PR sobre `localidades.json`.")
datos = L.cargar()
sitios = datos["sitios_calibrados"]

# ---------------------------------------------------------------------------------------------- 1. ubicar
st.subheader("1. Ubicar la localidad")
st.session_state.setdefault("v_lat", -37.98)
st.session_state.setdefault("v_lon", -61.35)
clic = mapa_dblclick(
    puntos=[{"lat": s["lat"], "lon": s["lon"], "nombre": s["nombre"], "color": "#6b7280", "etiqueta": True} for s in sitios]
    + [{"lat": x["lat"], "lon": x["lon"], "nombre": x["nombre"], "color": "#1d4ed8", "etiqueta": True} for x in datos["localidades"]],
    centro=(-36.8, -60.5), zoom=6, seleccion=(st.session_state["v_lat"], st.session_state["v_lon"]), key="v_mapa")
if clic and clic.get("n") != st.session_state.get("v_clic_n"):
    # doble clic nuevo en el mapa: pasa a ser el punto elegido (antes de crear los campos de latitud y longitud)
    st.session_state["v_clic_n"] = clic.get("n")
    st.session_state["v_lat"] = min(max(float(clic["lat"]), -55.0), -21.0)
    st.session_state["v_lon"] = min(max(float(clic["lon"]), -74.0), -53.0)
c1, c2, c3 = st.columns([2, 1, 1])
nombre = c1.text_input("Nombre", key="v_nombre", placeholder="p. ej. Coronel Pringles")
lat = c2.number_input("Latitud", min_value=-55.0, max_value=-21.0, step=0.01, format="%.4f", key="v_lat")
lon = c3.number_input("Longitud", min_value=-74.0, max_value=-53.0, step=0.01, format="%.4f", key="v_lon")
cercano, dist = L.sitio_mas_cercano(lat, lon, sitios)
st.caption(f"Rojo: el punto elegido (doble clic en el mapa, o latitud y longitud a mano) · gris: las 8 apps calibradas · "
           f"azul: localidades de prueba. Sitio calibrado más cercano: "
           f"**{cercano['nombre']}**, a {dist:.0f} km.")
if dist > 150:
    st.warning(f"El punto está a más de 150 km del sitio calibrado más cercano ({cercano['nombre']}): la alerta sería una "
               "extrapolación de la calibración regional.")

# ---------------------------------------------------------------------------------------------- 2. clima
st.subheader("2. Clima comparado con los sitios calibrados")
hoy = date.today()
anio = st.selectbox("Campaña", [hoy.year, hoy.year - 1, hoy.year - 2], key="v_anio",
                    help="Se usa para comparar el clima (paso 2) y para la vista previa de la alerta (paso 3).")
st.caption(f"ERA5-Land (Open-Meteo), enero a abril: el período del inicio de la emergencia y de los grandes flujos. Se compara el "
           f"clima típico ({CLIMA_DESDE}–{CLIMA_HASTA}), que describe el lugar, y el de {anio}, que describe ese año.")
if st.button("Revisar el clima", key="v_clima"):
    with st.spinner(f"Bajando enero a abril de {anio} y el clima típico {CLIMA_DESDE}–{CLIMA_HASTA} para el punto y los 8 sitios "
                    "(la primera vez puede tardar un minuto)…"):
        try:
            todos = [(f"➡️ {nombre or 'Punto nuevo'}", lat, lon)] + [(s_["nombre"], s_["lat"], s_["lon"]) for s_ in sitios]
            st.session_state["v_clim"] = {
                "punto": (lat, lon, int(anio)),
                "filas": [(n, _climatologia(la, lo), _clima_ene_abr(la, lo, int(anio))) for n, la, lo in todos]}
        except Exception as e:  # noqa: BLE001
            st.error(f"No se pudo bajar el clima: {e}")
cl = st.session_state.get("v_clim")
if cl and cl["punto"] == (lat, lon, int(anio)):
    nuevo_tip, nuevo_anio = cl["filas"][0][1], cl["filas"][0][2]
    ref_tip = [t for _, t, _ in cl["filas"][1:] if t]
    ref_anio = [a for _, _, a in cl["filas"][1:] if a]
    VARS = (("tmed", "temp. media (°C)", "temperatura"), ("lluvia", "lluvia (mm)", "lluvia"),
            ("dias_pulso", "días de pulso", "pulsos de lluvia"))
    tabla = pd.DataFrame([{"Lugar": n,
                           **{f"Típico: {et}": t.get(k) for k, et, _ in VARS},
                           **{f"{anio}: {et}": a.get(k) for k, et, _ in VARS}} for n, t, a in cl["filas"]])
    st.dataframe(tabla.round(1), hide_index=True, width="stretch")
    st.caption(f"Enero a abril. Típico: promedio de las campañas {CLIMA_DESDE}–{CLIMA_HASTA}. Días de pulso: días en que la lluvia "
               "de los 5 días previos suma 20 mm o más.")
    hasta = nuevo_anio.get("hasta") if nuevo_anio else None
    if hasta and hasta != "30/04":
        st.caption(f"{anio}: datos hasta el {hasta} (campaña en curso).")
    if not nuevo_tip:
        st.warning("Open-Meteo no devolvió el clima típico de este punto. Probá de nuevo en unos minutos.")
    else:
        fuera = [nom for k, _, nom in VARS if L.fuera_de_rango(nuevo_tip[k], [r[k] for r in ref_tip])]
        if fuera:
            st.warning(f"Clima típico de enero a abril fuera del rango de los sitios calibrados en: {', '.join(fuera)}. "
                       "La alerta en este lugar sería una extrapolación de la calibración.")
        else:
            st.success("El clima típico de enero a abril está dentro del rango de los sitios calibrados.")
    if not nuevo_anio:
        st.info(f"Todavía no hay datos de enero a abril de {anio} para este punto.")
    else:
        fuera = [nom for k, _, nom in VARS if L.fuera_de_rango(nuevo_anio[k], [r[k] for r in ref_anio])]
        if fuera:
            st.caption(f"En {anio}, fuera del rango de los sitios calibrados ese mismo año en: {', '.join(fuera)}.")
        else:
            st.caption(f"En {anio}, dentro del rango de los sitios calibrados ese mismo año.")

# ---------------------------------------------------------------------------------------------- 3. vista previa
st.subheader("3. Vista previa de la alerta")
st.caption(f"Campaña {anio} (la elegida en el paso 2).")
os.environ["LOLIUM_ALERTA_PARAMS"] = str(BASE / L.PARAMS_REGIONAL)
from lolium_comun import alerta_lolmu as _al  # noqa: E402
from lolium_comun import visualizacion_alerta_lolmu as _vis  # noqa: E402

importlib.reload(_al)
importlib.reload(_vis)
if st.toggle("Mostrar la alerta con la calibración regional", key="v_prev"):
    try:
        met = _campania(lat, lon, int(anio))
        if met.empty:
            st.warning(f"Open-Meteo no devolvió datos de clima para este punto en {anio} (ni ERA5-Land ni ERA5). Probá de nuevo "
                       "en unos minutos o con otra campaña.")
        else:
            _vis.mostrar_alerta_lolmu(met, tope_hasta_ultimo_cero=True, curva_desde_ultimo_cero=True, curva_tiempo_termico=True,
                                      localidad=nombre or "Punto nuevo",
                                      nota_sitio="**Vista previa del visor:** calibración regional, sin conteos locales.")
    except Exception as e:  # noqa: BLE001
        st.error(f"No se pudo calcular la vista previa: {e}")

# ---------------------------------------------------------------------------------------------- 4. conteos
st.subheader("4. Validar con conteos (opcional)")
st.caption("Un archivo CSV o Excel con dos columnas: fecha y plantas/m² emergidas en cada intervalo, de una campaña. "
           "Incluí los conteos en cero previos al inicio.")
arch = st.file_uploader("Conteos de una campaña", type=["csv", "xlsx", "xls"], key="v_conteos")
validacion = None
if arch is not None:
    try:
        cont = L.leer_conteos(arch)
        anio_c = int(cont["Fecha"].dt.year.mode()[0])
        met_c = _campania(lat, lon, anio_c)
        validacion = L.validar(_al, _al.AlertaLolmu(), met_c, cont)
        if "error" in validacion:
            st.warning(validacion["error"])
            validacion = None
        else:
            st.markdown(f"Campaña **{anio_c}**: {validacion['intervalos']} intervalos, {validacion['flushes']} con gran flujo (≥ 5 % por semana).")
            cols = st.columns(3)
            for col, nom in zip(cols, ("Solo clima", "+ primeras plántulas", "+ conteos")):
                v = validacion[nom]
                col.metric(nom, "—" if v["auc"] is None else f"AUC {v['auc']:.2f}".replace(".", ","),
                           f"{v['detectados']}/{validacion['flushes']} flujos en Alerta", delta_color="off")
            with st.expander("Detalle por intervalo"):
                st.dataframe(validacion["tabla"].round(1), hide_index=True, width="stretch")
            st.caption("Referencia en los sitios de validación del paper: AUC 0,89–0,93. Con una sola campaña la validación es indicativa.")
    except Exception as e:  # noqa: BLE001
        st.error(f"No se pudieron leer o validar los conteos: {e}")

# ---------------------------------------------------------------------------------------------- 5. proponer
st.subheader("5. Proponer la localidad")
ids = {x["id"] for x in datos["localidades"]}
lid = L.identificador(nombre) if nombre else ""
nota = st.text_area("Nota que verá el usuario", value=("Alerta con la calibración regional, sin conteos locales. "
                                                       "Clima ERA5-Land + ECMWF IFS (Open-Meteo)."), key="v_nota")
validada = validacion is not None and st.checkbox("Marcar como validada con estos conteos", key="v_validada")
entrada = {"id": lid, "nombre": nombre.strip(), "lat": round(float(lat), 4), "lon": round(float(lon), 4),
           "parametros": L.PARAMS_REGIONAL, "confianza": "validada" if validada else "regional",
           "campanias_locales": 1 if validacion is not None else 0, "nota": nota.strip(),
           "sitio_calibrado_cercano": cercano["nombre"], "distancia_km": round(dist)}
st.code(json.dumps(entrada, ensure_ascii=False, indent=2), language="json")
problemas = ([] if nombre.strip() else ["falta el nombre"]) + ([f"ya existe «{lid}»"] if lid in ids else [])
if problemas:
    st.info("Para proponerla: " + "; ".join(problemas) + ".")
else:
    gh = _secreto("github")
    if gh.get("token") and gh.get("repo"):
        if st.button("📤 Proponer con un PR", type="primary", key="v_pr"):
            try:
                url = L.proponer_pr(entrada, gh["token"], gh["repo"], gh.get("rama", "main"))
                st.success(f"PR abierto: {url}. Al unirlo, la localidad aparece en el selector.")
            except Exception as e:  # noqa: BLE001
                st.error(f"No se pudo abrir el PR: {e}")
    else:
        st.download_button("📥 Descargar la entrada (JSON)", json.dumps(entrada, ensure_ascii=False, indent=2),
                           file_name=f"localidad_{lid}.json", mime="application/json", key="v_json")
        st.caption("Para abrir el PR desde acá, cargar en los secretos `[github]` con `token` (permiso de contenido y PR sobre "
                   "este repositorio) y `repo` (p. ej. \"PREDWEEM/LOLIUM-LOCALIDADES\"). Sin eso, agregá la entrada a "
                   "`localidades.json` a mano.")
mostrar_sesion()
