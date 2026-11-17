# PREDWEEM Lolium — otras localidades (web de prueba)

Una sola app de Streamlit con **selector de localidad** para usar la alerta de grandes flujos de *Lolium* en lugares sin
app propia. No modifica las 8 apps calibradas ni la web LOLIUM-WEB.

- **Alerta por localidad** (`alerta.py`): la misma alerta que las apps (paquete `lolium-comun`): qué hacer esta semana,
  tacómetro del inicio, grandes flujos, graminicida de barbecho, residual y flujos tardíos, con la **calibración
  regional** (`params/regional.json`) y el clima del punto.
- **Nueva localidad** (`visor.py`): ubicar el punto en un mapa interactivo (se mueve arrastrando, zoom con la rueda y
  **doble clic** para elegir la localidad; `mapa.py` + `componentes/mapa_dblclick`, Leaflet 1.9.4 incluido) y ver la distancia al sitio calibrado más cercano, comparar su clima
  de febrero a abril de una campaña (por defecto la actual) con los 8 sitios (aviso de extrapolación), ver la alerta, validarla con conteos de una campaña (AUC
  y flujos detectados, como en el paper) y proponer la localidad con un PR sobre `localidades.json`.

## Clima

Open-Meteo, sin workflow por localidad (se baja al abrir la app y se guarda 3 horas), con la misma estrategia que la app
de Azul: **ERA5-Land** (reanálisis, ~9 km) para los días consolidados, **ECMWF IFS** para los días recientes que el
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

## Límites

Sin conteos locales, una localidad hereda la calibración regional (AUC 0,89–0,93 en los sitios de validación de la
región); fuera del rango de clima de los sitios calibrados es una extrapolación. Las localidades actuales (Tandil,
Coronel Suárez y Necochea) son de prueba.

## Pruebas

`python -m pytest -q tests` (clima y PR con Open-Meteo y GitHub simulados).

Copyright © 2026 Guillermo R. Chantre / PREDWEEM. Todos los derechos reservados.
