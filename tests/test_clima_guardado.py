# -*- coding: utf-8 -*-
from datetime import datetime

import pandas as pd

import actualizar_clima as A
import clima_openmeteo as clima


def _serie(anio=2027):
    f = pd.date_range(f"{anio}-01-01", f"{anio}-05-20")
    tipo = ["Reanalisis"] * (len(f) - 10) + ["Pronostico"] * 10
    return pd.DataFrame({"Fecha": f, "TMAX": 25.0, "TMIN": 10.0, "Prec": 0.0, "TIPO": tipo, "FUENTE": "x"})


def test_guardar_y_leer(tmp_path):
    loc = {"id": "tandil"}
    A.guardar(loc, _serie(), "2027-05-10T07:45:00-03:00", carpeta=tmp_path)
    assert (tmp_path / "tandil.csv").is_file()
    assert (tmp_path / "pronosticos" / "tandil_2027.csv").is_file()
    df, emit = clima.guardado(tmp_path / "tandil.csv", 2027, hoy=datetime(2027, 5, 10, 20))
    assert df is not None and len(df) == len(_serie()) and emit == "10/05 07:45"
    assert "FECHA_EMISION" not in df.columns


def test_viejo_o_de_otro_anio(tmp_path):
    A.guardar({"id": "x"}, _serie(), "2027-05-10T07:45:00-03:00", carpeta=tmp_path)
    assert clima.guardado(tmp_path / "x.csv", 2027, hoy=datetime(2027, 5, 12, 8))[0] is None
    assert clima.guardado(tmp_path / "x.csv", 2028, hoy=datetime(2027, 5, 10, 8))[0] is None
    assert clima.guardado(tmp_path / "no.csv", 2027)[0] is None


def test_pronosticos_se_acumulan(tmp_path):
    loc = {"id": "y"}
    A.guardar(loc, _serie(), "2027-05-10T07:45:00-03:00", carpeta=tmp_path)
    A.guardar(loc, _serie(), "2027-05-10T15:45:00-03:00", carpeta=tmp_path)  # mismo día: reemplaza
    A.guardar(loc, _serie(), "2027-05-11T07:45:00-03:00", carpeta=tmp_path)
    p = pd.read_csv(tmp_path / "pronosticos" / "y_2027.csv")
    assert p["FECHA_EMISION"].nunique() == 2 and len(p) == 20
