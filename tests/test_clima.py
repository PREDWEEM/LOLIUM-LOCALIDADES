from datetime import date

import pandas as pd

import clima_openmeteo as C


class _Resp:
    status_code, headers = 200, {}

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


def test_feb_abr_una_campania(monkeypatch):
    pedidos = []

    def falso(url, params, timeout):
        pedidos.append(params)
        return _Resp(_serie(params["start_date"], 94))

    monkeypatch.setattr(C.requests, "get", falso)
    r = C.clima_feb_abr(-33.9, -60.6, 2026, hoy=date(2026, 11, 17))
    assert len(pedidos) == 1 and pedidos[0]["start_date"] == "2026-01-27" and pedidos[0]["end_date"] == "2026-04-30"
    assert r["tmed_feb_abr"] == 14.0 and r["lluvia_feb_abr"] == 89.0 and r["dias_pulso_feb_abr"] == 0


def test_reintenta_ante_429(monkeypatch):
    estados = iter([429, 429, 200])

    class R429(_Resp):
        def __init__(self, d, code):
            super().__init__(d)
            self.status_code, self.headers = code, {"Retry-After": "1"}

    monkeypatch.setattr(C.time, "sleep", lambda s: None)
    monkeypatch.setattr(C.requests, "get", lambda url, params, timeout: R429(_serie("2026-01-01", 3), next(estados)))
    assert len(C._pedir(C.URL_ARCHIVO, {})) == 3


def test_429_persistente_da_mensaje_claro(monkeypatch):
    class R(_Resp):
        status_code, headers = 429, {}

    monkeypatch.setattr(C.time, "sleep", lambda s: None)
    monkeypatch.setattr(C.requests, "get", lambda url, params, timeout: R({}))
    import pytest
    with pytest.raises(RuntimeError, match="Open-Meteo pidió esperar"):
        C._pedir(C.URL_ARCHIVO, {})


def test_respaldo_era5_si_era5_land_viene_vacio(monkeypatch):
    def falso(url, params, timeout):
        n = (pd.Timestamp(params["end_date"]) - pd.Timestamp(params["start_date"])).days + 1
        if params["models"] == "era5_land":
            return _Resp(_serie(params["start_date"], n, nulos_final=n))  # todo vacío, diario y horario
        return _Resp(_serie(params["start_date"], n))

    monkeypatch.setattr(C.requests, "get", falso)
    df = C.campania(-33.9, -60.6, 2026, hoy=date(2026, 11, 17))
    assert len(df) == 274 and set(df["FUENTE"]) == {"ERA5"} and df["TMAX"].notna().all()


def test_agrega_horario_si_diario_vacio(monkeypatch):
    class RH(_Resp):
        def json(self):
            return {"hourly": self.d}

    def falso(url, params, timeout):
        if "daily" in params:
            return _Resp(_serie(params["start_date"], 3, nulos_final=3))
        horas = pd.date_range(params["start_date"], periods=72, freq="h")
        return RH({"time": horas.strftime("%Y-%m-%dT%H:%M").tolist(), "temperature_2m": [10 + h.hour / 2 for h in horas],
                   "precipitation": [0.5] * 72})

    monkeypatch.setattr(C.requests, "get", falso)
    df = C.reanalisis(-33.9, -60.6, date(2026, 1, 1), date(2026, 1, 3))
    assert len(df) == 3 and df["TMAX"].iloc[0] == 21.5 and df["TMIN"].iloc[0] == 10 and df["Prec"].iloc[0] == 12.0
    assert df["FUENTE"].iloc[0] == "ERA5_LAND"
