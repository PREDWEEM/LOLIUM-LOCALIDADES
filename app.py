# -*- coding: utf-8 -*-
"""PREDWEEM Lolium — otras localidades (web de prueba).

Una sola app con selector de localidad: la alerta de grandes flujos del paquete ``lolium-comun`` con el clima de cada
punto bajado de Open-Meteo (ERA5-Land + ECMWF IFS). Las localidades están en ``localidades.json`` y se agregan con la
página «Nueva localidad» (visor), que abre un PR sobre ese archivo.
"""
import streamlit as st

from acceso_predweem import requerir_acceso
from lolium_comun.pagina import FONDO_CSS

st.set_page_config(page_title="PREDWEEM Lolium — localidades", layout="wide", page_icon="🌾")
st.markdown(FONDO_CSS, unsafe_allow_html=True)
requerir_acceso("Otras localidades")

navegacion = st.navigation([
    st.Page("alerta.py", title="Alerta por localidad", icon="🔔", default=True),
    st.Page("visor.py", title="Nueva localidad", icon="🗺️"),
])
navegacion.run()
