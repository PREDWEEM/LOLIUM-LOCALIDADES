from datetime import date

import pandas as pd

import clima_openmeteo as C


class _Resp:
    def __init__(self, d):
        self.d = d

    def raise_for_status(self):
        pass

    def json(self):
        return {"daily": self.d}


def _serie(ini, n, nulos_final=0):
    f = pd.date_range(ini, periods=n).strftime("%Y-%m-%d").tolist()
    v = [20.0] * (n - nulos_final) + [None] * nulos_final
    return {"time": f, "temperature_2m_max": v, "temperature_2m_min": [x and 8.0 for x in v], "precipitation_sum": [x and 1.0 for x in v]}


def test_campania_combina_reanalisis_y_ecmwf(monkeypatch):
    hoy = date(2026, 3, 20)

    def falso(url, params, timeout):
        if "archive" in url:
            return _Resp(_serie("2026-01-01", 78, nulos_final=5))  # hasta 19/03, los últimos 5 días incompletos
        return _Resp(_serie(pd.Timestamp(hoy) - pd.Timedelta(days=params["past_days"]), params["past_days"] + 8))

    monkeypatch.setattr(C.requests, "get", falso)
    df = C.campania(-37.3, -59.1, 2026, hoy=hoy)
    assert df["Fecha"].min() == pd.Timestamp("2026-01-01") and df["Fecha"].is_unique
    assert df["Fecha"].diff().dropna().dt.days.eq(1).all()
    assert set(df["TIPO"]) == {"Reanalisis", "Reciente", "Pronostico"}
    assert (df.loc[df["TIPO"] == "Pronostico", "Fecha"] >= pd.Timestamp(hoy)).all()
    assert df.loc[df["FUENTE"] == "ERA5_LAND", "Fecha"].max() == pd.Timestamp("2026-03-14")


def test_campania_cerrada_solo_reanalisis(monkeypatch):
    monkeypatch.setattr(C.requests, "get", lambda url, params, timeout: _Resp(_serie("2025-01-01", 274)))
    df = C.campania(-37.3, -59.1, 2025, hoy=date(2026, 3, 1))
    assert set(df["TIPO"]) == {"Reanalisis"}
