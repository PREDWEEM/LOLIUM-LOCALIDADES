import json

import localidades as L


def test_lista_valida():
    d = L.cargar()
    ids = [x["id"] for x in d["localidades"]]
    assert len(ids) == len(set(ids)) and len(d["sitios_calibrados"]) == 8
    for x in d["localidades"]:
        assert (L.BASE / x["parametros"]).is_file()
        json.loads((L.BASE / x["parametros"]).read_text(encoding="utf-8"))


def test_utilidades():
    assert L.identificador("Coronel Suárez") == "coronel-suarez"
    s, d = L.sitio_mas_cercano(-37.32, -59.13, L.cargar()["sitios_calibrados"])
    assert s["nombre"] == "Azul" and 50 < d < 120
    assert L.fuera_de_rango(30, [15, 16, 18]) and not L.fuera_de_rango(17, [15, 16, 18])


def test_proponer_pr_arma_la_rama_y_el_pr(monkeypatch):
    import base64
    llamadas = []
    actual = {"_descripcion": "x", "sitios_calibrados": [], "localidades": [{"id": "tandil"}]}

    class R:
        def __init__(self, d):
            self.d = d

        def raise_for_status(self):
            pass

        def json(self):
            return self.d

    def falso(metodo, url, headers, timeout, **kw):
        llamadas.append((metodo, url.split("/repos/o/r")[1], kw.get("json")))
        if url.endswith("/contents/localidades.json") and metodo == "GET":
            return R({"sha": "s1", "content": base64.b64encode(json.dumps(actual).encode()).decode()})
        if "/git/ref/heads/" in url:
            return R({"object": {"sha": "abc"}})
        if url.endswith("/pulls"):
            return R({"html_url": "https://github.com/o/r/pull/1"})
        return R({})

    monkeypatch.setattr(L.requests, "request", falso)
    url = L.proponer_pr({"id": "pringles", "nombre": "Pringles", "lat": -38.0, "lon": -61.3, "confianza": "regional"}, "t", "o/r")
    assert url.endswith("/pull/1")
    put = [c for c in llamadas if c[0] == "PUT"][0]
    nuevo = json.loads(base64.b64decode(put[2]["content"]))
    assert [x["id"] for x in nuevo["localidades"]] == ["tandil", "pringles"] and put[2]["branch"] == "localidad-pringles"
