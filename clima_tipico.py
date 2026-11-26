# -*- coding: utf-8 -*-
"""Guarda el clima típico de enero a abril de los 8 sitios calibrados en ``clima/tipico_sitios.json``.

Lo leen la página «Nueva localidad» de la app y el explorador de la web, para comparar un punto nuevo con los sitios sin
volver a bajar 15 campañas de cada uno (Open-Meteo cuenta los pedidos largos como muchas consultas). Lo corre el
workflow ``clima_tipico.yml`` a mano o cuando cambian los sitios o este cálculo; solo recalcula los sitios que faltan o
cambiaron de lugar.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import clima_openmeteo as clima
import localidades as L

DESDE, HASTA = 2011, 2025
ARCHIVO = L.BASE / "clima" / "tipico_sitios.json"


def main() -> int:
    previo = json.loads(ARCHIVO.read_text(encoding="utf-8")) if ARCHIVO.is_file() else {}
    vale = previo.get("desde") == DESDE and previo.get("hasta") == HASTA
    sitios = {}
    for s in L.cargar()["sitios_calibrados"]:
        viejo = previo.get("sitios", {}).get(s["nombre"]) if vale else None
        if viejo and viejo.get("lat") == s["lat"] and viejo.get("lon") == s["lon"] and viejo.get("anios", 0) >= HASTA - DESDE:
            sitios[s["nombre"]] = viejo
            continue
        print(f"{s['nombre']}: bajando {DESDE}–{HASTA}…", flush=True)
        r = clima.climatologia(s["lat"], s["lon"], DESDE, HASTA)
        if r:
            sitios[s["nombre"]] = {"lat": s["lat"], "lon": s["lon"], **r}
        elif viejo:
            sitios[s["nombre"]] = viejo
    if not sitios:
        print("No se pudo calcular ningún sitio.", file=sys.stderr)
        return 1
    ARCHIVO.parent.mkdir(parents=True, exist_ok=True)
    ARCHIVO.write_text(json.dumps({
        "descripcion": "Clima típico de enero a abril (ERA5-Land, Open-Meteo): temperatura media (°C), lluvia (mm) y días "
                       "con >= 20 mm en 5 días; promedio de las campañas desde-hasta completas.",
        "desde": DESDE, "hasta": HASTA,
        "calculado": datetime.now(ZoneInfo("America/Argentina/Buenos_Aires")).strftime("%Y-%m-%d %H:%M"),
        "sitios": sitios}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"Guardado {ARCHIVO} ({len(sitios)} sitios).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
