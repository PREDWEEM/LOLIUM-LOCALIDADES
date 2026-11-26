# PREDWEEM Lolium — otras localidades (web de prueba)

Una sola app de Streamlit con **selector de localidad** para usar la alerta de grandes flujos de *Lolium* en lugares sin
app propia. No modifica las 8 apps calibradas ni la web LOLIUM-WEB.

- **Alerta por localidad** (`alerta.py`): la misma alerta que las apps (paquete `lolium-comun`): qué hacer esta semana,
  tacómetro del inicio, grandes flujos, graminicida de barbecho, residual y flujos tardíos, con la **calibración
  regional** (`params/regional.json`) y el clima del punto.
  También abre un punto cualquiera con `?lat=…&lon=…&nombre=…` (lo usa el explorador de localidades de la web).
- **Nueva localidad** (`visor.py`): ubicar el punto en un mapa interactivo (se mueve arrastrando, zoom con la rueda y
  **doble clic** para elegir la localidad; `mapa.py` + `componentes/mapa_dblclick`, Leaflet 1.9.4 incluido) y ver la distancia al sitio calibrado más cercano, comparar su clima
  de enero a abril, típico 2011–2025 y de una campaña (por defecto la actual), con los 8 sitios (aviso de extrapolación), ver la alerta, validarla con conteos de una campaña (AUC
  y flujos detectados, como en el paper) y proponer la localidad con un PR sobre `localidades.json`.

## Clima

**Clima guardado.** El workflow `actualizar_clima.yml` corre todos los días a las 07:40 y 15:40 (hora argentina), y
también a mano desde *Actions → Actualizar el clima de las localidades → Run workflow*. Baja la campaña de cada
localidad de `localidades.json` y la guarda en `clima/<id>.csv`. Además, va sumando los días de pronóstico de cada
emisión en `clima/pronosticos/<id>_<año>.csv`, para validar al cierre con lo que la alerta mostró. La app lee primero ese
archivo si tiene menos de 30 h, o si la campaña ya cerró. Si no, o para un punto elegido en el mapa, baja el clima en
vivo. Así la página abre rápido y no choca con el límite de consultas de Open-Meteo.

Open-Meteo (en vivo: se baja al abrir la app y se guarda 3 horas), con la misma estrategia que la app
de Azul: **ERA5-Land** (reanálisis, ~9 km; si Open-Meteo no lo entrega completo, **ERA5**, y si los datos diarios
vienen vacíos, se arman desde los horarios) para los días consolidados, **ECMWF IFS** para los días recientes que el
reanálisis todavía no cubre y para el pronóstico de 7 días (`clima_openmeteo.py`). La lluvia faltante no se completa
con cero. Si Open-Meteo responde «429» (demasiadas consultas por minuto), se reintenta con espera creciente.

## Agregar una localidad

Con el visor, o a mano: una entrada en `localidades.json` con `id`, `nombre`, `lat`, `lon`, `parametros`
(`params/regional.json`), `confianza` (`regional` o `validada`), `campanias_locales` y `nota`. Para que el visor abra
el PR solo, cargar en los secretos:

```toml
[github]
token = "<token con permiso de contenido y pull requests sobre este repositorio>"
repo = "PREDWEEM/lolium-localidades"
```

Con el control de ingreso activo, el visor es solo para administradores (`[acceso]` → `administradores`).

## Despliegue

Streamlit Community Cloud → New app → este repositorio, rama `main`, archivo principal `app.py`. Los secretos de
ingreso (`[auth]`, `[acceso]`) son los mismos que en las apps.

## Curva acumulada

Con fecha de primeras plántulas (o un conteo con plantas), la curva de emergencia acumulada sigue el tiempo térmico desde esa fecha con la forma Weibull de LOLIUM-COMUN 1.13.0 (al ver las primeras plántulas ya nació el 15 %; 50 % a 294 °Cd; banda 10–90 %). Para sitios sin campañas propias es mejor que el calendario de Bordenave anclado que se usaba antes: en 38 campañas, error del acumulado 13,5 → 12,8 puntos (sitios de las apps 14,0 → 11,0; UBA 17,9 → 11,3; Red DIMA 15,2 → 17,3).

## Límites

Sin conteos locales, una localidad hereda la calibración regional (AUC 0,89–0,93 en los sitios de validación de la
región); fuera del rango de clima de los sitios calibrados es una extrapolación. Las localidades actuales (Tandil,
Coronel Suárez y Necochea) son de prueba.

## Pruebas

`python -m pytest -q tests` (clima y PR con Open-Meteo y GitHub simulados).

Copyright © 2026 Guillermo R. Chantre / PREDWEEM. Todos los derechos reservados.
