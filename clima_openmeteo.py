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


def _get(url: str, params: dict) -> dict:
    for intento in range(REINTENTOS + 1):
        r = requests.get(url, params=params, timeout=TIMEOUT)
        if r.status_code != 429 or intento == REINTENTOS:
            break
        espera = r.headers.get("Retry-After") if hasattr(r, "headers") else None
        time.sleep(min(float(espera), 60) if espera and str(espera).replace(".", "", 1).isdigit() else 5 * 2 ** intento)
    if r.status_code == 429:
        raise RuntimeError("Open-Meteo pidió esperar (demasiadas consultas en poco tiempo). Probá de nuevo en un minuto.")
    r.raise_for_status()
    return r.json()


def _pedir(url: str, params: dict) -> pd.DataFrame:
    """Serie diaria (``daily``); devuelve las columnas Fecha, TMAX, TMIN, Prec (con huecos si la API no tiene el dato)."""
    d = _get(url, params).get("daily") or {}
    if not d.get("time"):
        return pd.DataFrame(columns=["Fecha", "TMAX", "TMIN", "Prec"])
    return pd.DataFrame({"Fecha": pd.to_datetime(d["time"]), "TMAX": pd.to_numeric(pd.Series(d.get("temperature_2m_max")), errors="coerce"),
                         "TMIN": pd.to_numeric(pd.Series(d.get("temperature_2m_min")), errors="coerce"),
                         "Prec": pd.to_numeric(pd.Series(d.get("precipitation_sum")), errors="coerce")})


def _pedir_horario(url: str, params: dict) -> pd.DataFrame:
    """Serie horaria agregada a diaria (hora local): máxima, mínima y suma; un día cuenta solo con sus 24 horas."""
    h = _get(url, params).get("hourly") or {}
    if not h.get("time"):
        return pd.DataFrame(columns=["Fecha", "TMAX", "TMIN", "Prec"])
    df = pd.DataFrame({"Hora": pd.to_datetime(h["time"]), "T": pd.to_numeric(pd.Series(h.get("temperature_2m")), errors="coerce"),
                       "P": pd.to_numeric(pd.Series(h.get("precipitation")), errors="coerce")})
    df["Fecha"] = df["Hora"].dt.normalize()
    g = df.groupby("Fecha")
    out = pd.DataFrame({"TMAX": g["T"].max(), "TMIN": g["T"].min(), "Prec": g["P"].sum(min_count=1),
                        "n": g["T"].count().combine(g["P"].count(), min)}).reset_index()
    out.loc[out["n"] < 24, ["TMAX", "TMIN", "Prec"]] = float("nan")
    return out.drop(columns="n")


def _completos(df: pd.DataFrame) -> pd.DataFrame:
    return df.dropna(subset=["TMAX", "TMIN", "Prec"])


def reanalisis(lat: float, lon: float, inicio: date, fin: date, modelos: tuple[str, ...] = ("era5_land", "era5")) -> pd.DataFrame:
    """Serie diaria de reanálisis entre ``inicio`` y ``fin``, sin los días incompletos del final.

    Igual que la app de Azul: prueba ERA5-Land y, si Open-Meteo no lo entrega completo (pasa seguido con los datos
    diarios), ERA5; para cada uno, si los datos diarios vienen vacíos, los arma desde los horarios. Se queda con la
    primera fuente que cubre el período salvo los últimos días (demora del reanálisis), o con la más completa."""
    n = (fin - inicio).days + 1
    base = dict(latitude=lat, longitude=lon, start_date=inicio.isoformat(), end_date=fin.isoformat(), timezone=ZONA,
                cell_selection="land")
    mejor, n_mejor = None, -1
    for modelo in modelos:
        for horario in (False, True):
            try:
                df = (_pedir_horario(URL_ARCHIVO, {**base, "models": modelo, "hourly": "temperature_2m,precipitation"}) if horario
                      else _pedir(URL_ARCHIVO, {**base, "models": modelo, "daily": DIARIAS}))
            except RuntimeError:
                raise
            except Exception:  # noqa: BLE001  (modelo no disponible para ese punto o período: probar el siguiente)
                continue
            c = _completos(df)
            if len(c) > n_mejor:
                mejor, n_mejor = (df, modelo), len(c)
            if len(c) >= max(1, n - 12):  # cubre todo salvo la demora del reanálisis
                break
        if n_mejor >= max(1, n - 12):
            break
    if mejor is None or n_mejor <= 0:
        return pd.DataFrame(columns=["Fecha", "TMAX", "TMIN", "Prec", "FUENTE", "TIPO"])
    df, modelo = mejor
    ult = _completos(df)["Fecha"].max()
    return df[df["Fecha"] <= ult].assign(FUENTE=modelo.upper(), TIPO="Reanalisis").reset_index(drop=True)


def ecmwf(lat: float, lon: float, dias_atras: int) -> pd.DataFrame:
    """ECMWF IFS: los últimos ``dias_atras`` días más hoy y 7 días de pronóstico."""
    df = _pedir(URL_PRONOSTICO, dict(latitude=lat, longitude=lon, daily=DIARIAS, timezone=ZONA, models="ecmwf_ifs025", cell_selection="land",
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
