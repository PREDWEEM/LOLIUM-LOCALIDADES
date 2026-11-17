# -*- coding: utf-8 -*-
"""Clima diario de cualquier punto desde Open-Meteo, con la misma estrategia que la app de Azul.

- ERA5-Land (reanálisis, ~9 km): días ya consolidados (llega con unos 5 días de demora).
- ECMWF IFS (0,25°): los días recientes que el reanálisis todavía no cubre y el pronóstico de los próximos 7 días.

La lluvia faltante nunca se completa con cero: los días sin dato quedan vacíos y ``limpiar_clima`` del módulo común
los trata. La columna ``TIPO`` vale ``Pronostico`` en los días futuros, como en ``meteo_daily.csv`` de las apps.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import time

import pandas as pd
import requests

ZONA = "America/Argentina/Buenos_Aires"
URL_ARCHIVO = "https://archive-api.open-meteo.com/v1/archive"
URL_PRONOSTICO = "https://api.open-meteo.com/v1/forecast"
DIARIAS = "temperature_2m_max,temperature_2m_min,precipitation_sum"
DIAS_PRONOSTICO = 8  # hoy + 7 días
TIMEOUT = 60
REINTENTOS = 3  # ante «429 Too Many Requests» (límite por minuto de la API gratuita), con espera creciente


def _pedir(url: str, params: dict) -> pd.DataFrame:
    for intento in range(REINTENTOS + 1):
        r = requests.get(url, params=params, timeout=TIMEOUT)
        if r.status_code != 429 or intento == REINTENTOS:
            break
        espera = r.headers.get("Retry-After") if hasattr(r, "headers") else None
        time.sleep(min(float(espera), 60) if espera and str(espera).replace(".", "", 1).isdigit() else 5 * 2 ** intento)
    if r.status_code == 429:
        raise RuntimeError("Open-Meteo pidió esperar (demasiadas consultas en poco tiempo). Probá de nuevo en un minuto.")
    r.raise_for_status()
    d = r.json().get("daily") or {}
    if not d.get("time"):
        return pd.DataFrame(columns=["Fecha", "TMAX", "TMIN", "Prec"])
    return pd.DataFrame({"Fecha": pd.to_datetime(d["time"]), "TMAX": d.get("temperature_2m_max"),
                         "TMIN": d.get("temperature_2m_min"), "Prec": d.get("precipitation_sum")})


def reanalisis(lat: float, lon: float, inicio: date, fin: date, modelo: str = "era5_land") -> pd.DataFrame:
    """Serie diaria de reanálisis (por defecto ERA5-Land) entre ``inicio`` y ``fin``, sin los días incompletos del final."""
    df = _pedir(URL_ARCHIVO, dict(latitude=lat, longitude=lon, start_date=inicio.isoformat(), end_date=fin.isoformat(),
                                  daily=DIARIAS, timezone=ZONA, models=modelo))
    completo = df.dropna(subset=["TMAX", "TMIN", "Prec"])
    if completo.empty:
        return completo.assign(FUENTE=[], TIPO=[])
    return df[df["Fecha"] <= completo["Fecha"].max()].assign(FUENTE=modelo.upper(), TIPO="Reanalisis")


def ecmwf(lat: float, lon: float, dias_atras: int) -> pd.DataFrame:
    """ECMWF IFS: los últimos ``dias_atras`` días más hoy y 7 días de pronóstico."""
    df = _pedir(URL_PRONOSTICO, dict(latitude=lat, longitude=lon, daily=DIARIAS, timezone=ZONA, models="ecmwf_ifs025",
                                     past_days=max(0, min(int(dias_atras), 92)), forecast_days=DIAS_PRONOSTICO))
    return df.assign(FUENTE="ECMWF_IFS")


def campania(lat: float, lon: float, anio: int | None = None, hoy: date | None = None) -> pd.DataFrame:
    """Clima de la campaña (1/01 al 1/10) para el punto: reanálisis + ECMWF reciente + pronóstico.

    Para una campaña ya cerrada (``anio`` anterior al actual) devuelve solo reanálisis, sin pronóstico."""
    hoy = hoy or datetime.now(ZoneInfo(ZONA)).date()
    anio = anio or hoy.year
    ini, fin = date(anio, 1, 1), date(anio, 10, 1)
    if anio < hoy.year or hoy > fin:
        out = reanalisis(lat, lon, ini, min(fin, hoy - timedelta(days=1)))
        return out.assign(TIPO="Reanalisis")[["Fecha", "TMAX", "TMIN", "Prec", "FUENTE", "TIPO"]].reset_index(drop=True)
    rea = reanalisis(lat, lon, ini, hoy - timedelta(days=1)) if hoy > ini else pd.DataFrame()
    ultimo = rea["Fecha"].max().date() if not rea.empty else ini - timedelta(days=1)
    pro = ecmwf(lat, lon, (hoy - ultimo).days)
    pro = pro[(pro["Fecha"].dt.date > ultimo) & (pro["Fecha"].dt.date <= fin)]
    pro = pro.assign(TIPO=["Pronostico" if f.date() >= hoy else "Reciente" for f in pro["Fecha"]])
    out = pd.concat([rea, pro], ignore_index=True)
    return out[["Fecha", "TMAX", "TMIN", "Prec", "FUENTE", "TIPO"]].sort_values("Fecha").reset_index(drop=True)


def clima_feb_abr(lat: float, lon: float, anio: int, hoy: date | None = None) -> dict:
    """Clima de febrero a abril de una campaña (ERA5-Land; si todavía no está consolidado, lo que haya): temperatura media
    (°C), lluvia total (mm) y días con ≥ 20 mm en 5 días. Es una consulta liviana (unos 90 días)."""
    hoy = hoy or datetime.now(ZoneInfo(ZONA)).date()
    ini, fin = date(anio, 1, 27), min(date(anio, 4, 30), hoy - timedelta(days=1))  # 4 días antes del 1/02 para la suma de 5 días
    if fin < date(anio, 2, 1):
        return {}
    df = reanalisis(lat, lon, ini, fin)
    if df.empty:
        return {}
    pulsos = (df["Prec"].rolling(5).sum() >= 20)[df["Fecha"] >= pd.Timestamp(anio, 2, 1)]
    df = df[df["Fecha"] >= pd.Timestamp(anio, 2, 1)]
    return {"tmed_feb_abr": float(((df["TMAX"] + df["TMIN"]) / 2).mean()), "lluvia_feb_abr": float(df["Prec"].sum()),
            "dias_pulso_feb_abr": float(pulsos.sum()), "hasta": df["Fecha"].max().strftime("%d/%m")}


def climatologia(lat: float, lon: float, desde: int = 2011, hasta: int = 2025) -> dict:
    """Clima medio de febrero a abril (período del inicio y los grandes flujos) en ERA5-Land: temperatura media (°C),
    lluvia total (mm) y días con ≥ 20 mm en 5 días, promedio por año."""
    df = reanalisis(lat, lon, date(desde, 1, 1), date(hasta, 12, 31))
    df = df[df["Fecha"].dt.month.isin([2, 3, 4])].copy()
    if df.empty:
        return {}
    df["anio"] = df["Fecha"].dt.year
    tmed = ((df["TMAX"] + df["TMIN"]) / 2).groupby(df["anio"]).mean()
    lluvia = df.groupby("anio")["Prec"].sum()
    pulsos = df.groupby("anio")["Prec"].apply(lambda s: int((s.rolling(5).sum() >= 20).sum()))
    return {"tmed_feb_abr": float(tmed.mean()), "lluvia_feb_abr": float(lluvia.mean()),
            "dias_pulso_feb_abr": float(pulsos.mean()), "anios": int(len(tmed))}
