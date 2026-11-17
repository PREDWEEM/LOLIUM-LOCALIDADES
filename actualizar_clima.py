# -*- coding: utf-8 -*-
"""Guarda el clima de la campaña de cada localidad de ``localidades.json`` (lo corre el workflow dos veces por día).

- ``clima/<id>.csv``: la serie de la campaña en curso (registrado + reciente + pronóstico), la que lee la app.
- ``clima/pronosticos/<id>_<año>.csv``: cada emisión agrega los días de pronóstico que se vieron ese día, para poder
  validar la alerta al cierre de la campaña con lo que efectivamente se mostró.

Las localidades se bajan de a una, con una pausa, para no pasar el límite por minuto de Open-Meteo. Si una falla, se
conserva su archivo anterior y se sigue con las demás; el script termina con error solo si fallan todas.
"""
from __future__ import annotations

import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

import clima_openmeteo as clima
import localidades as L

CARPETA = L.BASE / "clima"
PAUSA_S = 3


def guardar(loc: dict, df: pd.DataFrame, emision: str, carpeta: Path = CARPETA) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    out = df.assign(FECHA_EMISION=emision)
    out.assign(Fecha=out["Fecha"].dt.strftime("%Y-%m-%d")).to_csv(carpeta / f"{loc['id']}.csv", index=False)
    pron = out[out["TIPO"] == "Pronostico"]
    if pron.empty:
        return
    anio = int(pron["Fecha"].dt.year.iloc[0])
    arch = carpeta / "pronosticos" / f"{loc['id']}_{anio}.csv"
    arch.parent.mkdir(parents=True, exist_ok=True)
    pron = pron.assign(Fecha=pron["Fecha"].dt.strftime("%Y-%m-%d"))
    if arch.is_file():
        previo = pd.read_csv(arch)
        pron = pd.concat([previo[previo["FECHA_EMISION"].astype(str).str[:10] != emision[:10]], pron], ignore_index=True)
    pron.to_csv(arch, index=False)


def main() -> int:
    emision = datetime.now(ZoneInfo(clima.ZONA)).isoformat(timespec="seconds")
    locs = L.cargar()["localidades"]
    fallas = []
    for i, loc in enumerate(locs):
        if i:
            time.sleep(PAUSA_S)
        try:
            df = clima.campania(loc["lat"], loc["lon"])
            if df.empty:
                raise RuntimeError("Open-Meteo no devolvió datos")
            guardar(loc, df, emision)
            print(f"{loc['nombre']}: {len(df)} días, {df['Fecha'].min():%d/%m}–{df['Fecha'].max():%d/%m}, "
                  f"fuentes {', '.join(sorted(df['FUENTE'].astype(str).unique()))}")
        except Exception as e:  # noqa: BLE001
            fallas.append(loc["nombre"])
            print(f"ADVERTENCIA {loc['nombre']}: {e} (se conserva el archivo anterior)")
    if fallas and len(fallas) == len(locs):
        print("Fallaron todas las localidades.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
