# -*- coding: utf-8 -*-
"""Lista de localidades de la web de prueba y herramientas del visor para agregar nuevas."""
from __future__ import annotations

import base64
import json
import math
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import requests

BASE = Path(__file__).resolve().parent
ARCHIVO = BASE / "localidades.json"
PARAMS_REGIONAL = "params/regional.json"
CONFIANZA = {
    "regional": "Calibración regional, sin validar con conteos locales",
    "validada": "Validada con conteos locales",
}


def cargar() -> dict:
    return json.loads(ARCHIVO.read_text(encoding="utf-8"))


def distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def sitio_mas_cercano(lat: float, lon: float, sitios: list[dict]) -> tuple[dict, float]:
    d = [(s, distancia_km(lat, lon, s["lat"], s["lon"])) for s in sitios]
    return min(d, key=lambda x: x[1])


def identificador(nombre: str) -> str:
    t = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-") or "localidad"


def nota_markdown(loc: dict) -> str:
    conf = CONFIANZA.get(loc.get("confianza", "regional"), loc.get("confianza", ""))
    n = int(loc.get("campanias_locales", 0) or 0)
    return (f"**{loc['nombre']} · {conf}{f' ({n} campañas)' if n else ''}.** {loc.get('nota', '')} "
            f"Coordenadas: {loc['lat']:.4f}, {loc['lon']:.4f}.")


# ---------------------------------------------------------------------------------------------------- chequeo de clima
def fuera_de_rango(valor: float, referencias: list[float], margen: float = 0.10) -> bool:
    """True si ``valor`` cae fuera del rango de los sitios calibrados ampliado en ``margen`` (fracción del rango)."""
    ref = [x for x in referencias if x is not None and np.isfinite(x)]
    if not ref:
        return False
    lo, hi = min(ref), max(ref)
    m = (hi - lo) * margen
    return not (lo - m <= valor <= hi + m)


# ------------------------------------------------------------------------------------------- validación con conteos
def leer_conteos(archivo) -> pd.DataFrame:
    """CSV o Excel con columnas de fecha y plantas/m² (acumuladas o por intervalo, se usan por intervalo)."""
    nombre = getattr(archivo, "name", str(archivo)).lower()
    df = pd.read_excel(archivo) if nombre.endswith((".xlsx", ".xls")) else pd.read_csv(archivo, sep=None, engine="python")
    df = df.iloc[:, :2].copy()
    df.columns = ["Fecha", "PLM2"]
    df["Fecha"] = pd.to_datetime(df["Fecha"], errors="coerce", dayfirst=True)
    df["PLM2"] = pd.to_numeric(df["PLM2"], errors="coerce")
    return df.dropna().sort_values("Fecha").reset_index(drop=True)


def _auc(y, s) -> float | None:
    y, s = np.asarray(y, bool), np.asarray(s, float)
    pos, neg = s[y], s[~y]
    if len(pos) == 0 or len(neg) == 0:
        return None
    return float(np.mean([(p > n) + 0.5 * (p == n) for p in pos for n in neg]))


def validar(al, modelo, meteo: pd.DataFrame, conteos: pd.DataFrame, umbral: float = 0.05) -> dict:
    """Valida la alerta con conteos de una campaña, como en el paper: la alerta se emite al comienzo de cada intervalo
    entre conteos con lo que se sabe ese día; gran flujo = ≥ 5 % de la campaña por 7 días en el intervalo."""
    c = conteos.copy()
    total = c["PLM2"].sum()
    if total <= 0 or len(c) < 3:
        return {"error": "Hacen falta al menos 3 conteos con plántulas."}
    c["frac"] = c["PLM2"] / total
    primeras = c.loc[c["PLM2"] > 0, "Fecha"].min()
    filas = []
    for i in range(1, len(c)):
        ini, fin = c.loc[i - 1, "Fecha"], c.loc[i, "Fecha"]
        dias = max((fin - ini).days, 1)
        flush = c.loc[i, "frac"] * 7 / dias >= umbral
        fila = {"Desde": ini, "Hasta": fin, "Emergencia (%)": 100 * c.loc[i, "frac"], "Gran flujo": bool(flush)}
        for nom, kw in (("Solo clima", {}), ("+ primeras plántulas", {"primeras": primeras}),
                        ("+ conteos", {"primeras": primeras, "conteos": c.loc[: i - 1, ["Fecha", "PLM2"]]})):
            pr = kw.get("primeras")
            r = al.evaluar(meteo, ini, pr if pr is not None and pr <= ini else None, kw.get("conteos"), modelo,
                           tope_hasta_ultimo_cero=True)
            fila[nom] = 100 * r["probabilidad"]
        filas.append(fila)
    t = pd.DataFrame(filas)
    y = t["Gran flujo"].to_numpy()
    res = {"tabla": t, "intervalos": len(t), "flushes": int(y.sum())}
    for nom in ("Solo clima", "+ primeras plántulas", "+ conteos"):
        res[nom] = {"auc": _auc(y, t[nom]), "detectados": int((t.loc[y, nom] >= 100 * al.ALERTA).sum())}
    return res


# --------------------------------------------------------------------------------------------- PR a GitHub
def proponer_pr(entrada: dict, token: str, repo: str, base: str = "main") -> str:
    """Agrega ``entrada`` a ``localidades.json`` en una rama nueva de ``repo`` (dueño/nombre) y abre un PR. Devuelve su URL."""
    api = f"https://api.github.com/repos/{repo}"
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}

    def _r(metodo, url, **kw):
        r = requests.request(metodo, url, headers=h, timeout=30, **kw)
        r.raise_for_status()
        return r.json()

    actual = _r("GET", f"{api}/contents/localidades.json", params={"ref": base})
    datos = json.loads(base64.b64decode(actual["content"]).decode("utf-8"))
    ids = {x["id"] for x in datos["localidades"]}
    if entrada["id"] in ids:
        raise ValueError(f"Ya existe una localidad con id «{entrada['id']}».")
    datos["localidades"].append(entrada)
    sha_base = _r("GET", f"{api}/git/ref/heads/{base}")["object"]["sha"]
    rama = f"localidad-{entrada['id']}"
    _r("POST", f"{api}/git/refs", json={"ref": f"refs/heads/{rama}", "sha": sha_base})
    contenido = json.dumps(datos, ensure_ascii=False, indent=2) + "\n"
    _r("PUT", f"{api}/contents/localidades.json", json={
        "message": f"Nueva localidad: {entrada['nombre']}", "branch": rama, "sha": actual["sha"],
        "content": base64.b64encode(contenido.encode("utf-8")).decode()})
    pr = _r("POST", f"{api}/pulls", json={
        "title": f"Nueva localidad: {entrada['nombre']}", "head": rama, "base": base,
        "body": (f"Agrega **{entrada['nombre']}** ({entrada['lat']:.4f}, {entrada['lon']:.4f}) a la web de prueba, con "
                 f"«{CONFIANZA.get(entrada['confianza'], entrada['confianza'])}».\n\nPropuesto desde el visor «Nueva localidad».")})
    return pr["html_url"]
