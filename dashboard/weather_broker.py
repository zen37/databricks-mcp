"""
Open-Meteo weather engine backing the weather-prediction MCP server.

This is the adapter/broker module (the weather equivalent of Day 3's
``alpaca_broker.py`` / ``massive_broker.py``): it is the *only* place that
talks HTTP to the weather API and parses raw JSON into clean Python dicts.
The MCP tools in ``weather_mcp_server.py`` stay thin and just call the
functions here - there are no raw ``requests`` calls inside the ``@mcp.tool``
functions.

Backing API: Open-Meteo (https://open-meteo.com/) - a free, global weather
API that requires **no API key and no signup** (non-commercial use, ~10k
calls/day). Because there is no credential, this module needs no Databricks
secret. If you swap in a keyed provider (e.g. WeatherAPI.com) later, add a
``_secret()`` helper here exactly like ``alpaca_broker.py`` does and read the
key from a Databricks secret scope - never hardcode it.

Two Open-Meteo endpoints are used:
  * Geocoding  - resolve a human location ("Chicago", "Austin, TX", a zip,
                 or "lat,lon") to latitude/longitude.
  * Forecast   - current conditions and daily forecast for those coords.

Every function raises ``RuntimeError`` (or ``ValueError`` for bad input) with
a clean, human-readable message on failure, so the MCP tools can surface a
tidy error to the agent instead of a stack trace.
"""

import os
from datetime import date, datetime, timedelta

import requests

# Endpoints and unit defaults are env-overridable so the same code runs
# locally and as a Databricks App (values injected via app.yaml).
_GEOCODE_URL = os.environ.get(
    "GEOCODING_API_BASE", "https://geocoding-api.open-meteo.com/v1/search"
)
_FORECAST_URL = os.environ.get(
    "WEATHER_API_BASE", "https://api.open-meteo.com/v1/forecast"
)
_TEMP_UNIT = os.environ.get("WEATHER_TEMP_UNIT", "fahrenheit")  # or "celsius"
_WIND_UNIT = os.environ.get("WEATHER_WIND_UNIT", "mph")  # or "kmh", "ms", "kn"
_PRECIP_UNIT = os.environ.get("WEATHER_PRECIP_UNIT", "inch")  # or "mm"
_TIMEOUT = int(os.environ.get("WEATHER_HTTP_TIMEOUT", "10"))

# Open-Meteo's daily forecast supports up to 16 days.
MAX_FORECAST_DAYS = 16

# WMO weather interpretation codes -> human-readable text.
# https://open-meteo.com/en/docs (WMO Weather interpretation codes, WW)
_WMO_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}

# WMO codes that indicate hazardous / severe conditions the recommendation
# tools should warn about.
SEVERE_WMO_CODES = {65, 67, 75, 82, 86, 95, 96, 99}


def _describe_code(code) -> str:
    """Translate a WMO weather code into human-readable text."""
    try:
        return _WMO_CODES.get(int(code), f"Unknown conditions (code {code})")
    except (TypeError, ValueError):
        return "Unknown conditions"


def is_severe_code(code) -> bool:
    """True if the WMO code denotes heavy rain/snow, storms, or hail."""
    try:
        return int(code) in SEVERE_WMO_CODES
    except (TypeError, ValueError):
        return False


_COMPASS = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def _compass(degrees) -> str | None:
    """Convert a wind direction in degrees to a 16-point compass label."""
    if degrees is None:
        return None
    try:
        return _COMPASS[int((float(degrees) % 360) / 22.5 + 0.5) % 16]
    except (TypeError, ValueError):
        return None


def _http_get(url: str, params: dict) -> dict:
    """GET ``url`` with query ``params`` and return parsed JSON, or raise cleanly."""
    try:
        resp = requests.get(url, params=params, timeout=_TIMEOUT)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"Weather API request failed: {e}")


def _try_parse_latlon(location: str):
    """If ``location`` looks like 'lat,lon', return (lat, lon) floats, else None."""
    if "," not in location:
        return None
    parts = [p.strip() for p in location.split(",")]
    if len(parts) != 2:
        return None
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    if -90 <= lat <= 90 and -180 <= lon <= 180:
        return lat, lon
    return None


def geocode(location: str) -> dict:
    """
    Resolve a human location to coordinates.

    Accepts a city name ("Chicago"), a city+region ("Austin, TX"), a postal
    code ("60601"), or raw "lat,lon" ("41.88,-87.63"). Returns a dict with
    ``name``, ``label`` (a friendly "City, Region, Country" string),
    ``latitude``, ``longitude``, and ``timezone``.

    Raises ValueError for empty input and RuntimeError if the location can't
    be resolved.
    """
    location = (location or "").strip()
    if not location:
        raise ValueError("location is required")

    coords = _try_parse_latlon(location)
    if coords:
        lat, lon = coords
        label = f"{lat:.4f}, {lon:.4f}"
        return {
            "name": label,
            "label": label,
            "latitude": lat,
            "longitude": lon,
            "timezone": "auto",
        }

    data = _http_get(
        _GEOCODE_URL,
        {"name": location, "count": 1, "language": "en", "format": "json"},
    )
    results = data.get("results") or []
    if not results:
        raise RuntimeError(
            f"Could not resolve location {location!r}. Try a city name, "
            f"'City, Region', a postal code, or 'lat,lon'."
        )
    r = results[0]
    label_parts = [r.get("name"), r.get("admin1"), r.get("country")]
    label = ", ".join(p for p in label_parts if p)
    return {
        "name": r.get("name"),
        "label": label,
        "latitude": r["latitude"],
        "longitude": r["longitude"],
        "timezone": r.get("timezone", "auto"),
    }


def get_current_weather(location: str) -> dict:
    """
    Fetch current conditions for ``location`` from Open-Meteo.

    Returns a dict with the resolved location label, coordinates, an ISO
    ``as_of`` timestamp, temperature, feels-like, textual conditions, the raw
    WMO ``weather_code``, humidity, wind (speed/direction/gusts), precipitation,
    a day/night flag, and a ``units`` sub-dict.
    """
    place = geocode(location)
    data = _http_get(
        _FORECAST_URL,
        {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "is_day,precipitation,weather_code,wind_speed_10m,"
                "wind_direction_10m,wind_gusts_10m"
            ),
            "temperature_unit": _TEMP_UNIT,
            "wind_speed_unit": _WIND_UNIT,
            "precipitation_unit": _PRECIP_UNIT,
            "timezone": "auto",
        },
    )
    cur = data.get("current") or {}
    units = data.get("current_units") or {}
    code = cur.get("weather_code")
    return {
        "location": place["label"],
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "as_of": cur.get("time"),
        "temperature": cur.get("temperature_2m"),
        "feels_like": cur.get("apparent_temperature"),
        "conditions": _describe_code(code),
        "weather_code": code,
        "humidity": cur.get("relative_humidity_2m"),
        "precipitation": cur.get("precipitation"),
        "wind_speed": cur.get("wind_speed_10m"),
        "wind_gusts": cur.get("wind_gusts_10m"),
        "wind_direction_deg": cur.get("wind_direction_10m"),
        "wind_direction": _compass(cur.get("wind_direction_10m")),
        "is_day": bool(cur.get("is_day")),
        "units": {
            "temperature": units.get("temperature_2m"),
            "wind_speed": units.get("wind_speed_10m"),
            "precipitation": units.get("precipitation"),
            "humidity": units.get("relative_humidity_2m"),
        },
    }


def _fetch_daily(place: dict, days: int) -> dict:
    """Fetch the raw daily-forecast payload for an already-resolved place."""
    return _http_get(
        _FORECAST_URL,
        {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "apparent_temperature_max,apparent_temperature_min,"
                "precipitation_probability_max,precipitation_sum,"
                "wind_speed_10m_max,sunrise,sunset"
            ),
            "temperature_unit": _TEMP_UNIT,
            "wind_speed_unit": _WIND_UNIT,
            "precipitation_unit": _PRECIP_UNIT,
            "forecast_days": days,
            "timezone": "auto",
        },
    )


def _daily_rows(data: dict) -> list[dict]:
    """Zip Open-Meteo's parallel daily arrays into a list of per-day dicts."""
    daily = data.get("daily") or {}
    dates = daily.get("time") or []
    rows = []
    for i, day in enumerate(dates):
        code = _at(daily.get("weather_code"), i)
        rows.append(
            {
                "date": day,
                "conditions": _describe_code(code),
                "weather_code": code,
                "severe": is_severe_code(code),
                "temp_high": _at(daily.get("temperature_2m_max"), i),
                "temp_low": _at(daily.get("temperature_2m_min"), i),
                "feels_like_high": _at(daily.get("apparent_temperature_max"), i),
                "feels_like_low": _at(daily.get("apparent_temperature_min"), i),
                "precip_probability": _at(daily.get("precipitation_probability_max"), i),
                "precip_sum": _at(daily.get("precipitation_sum"), i),
                "wind_max": _at(daily.get("wind_speed_10m_max"), i),
                "sunrise": _at(daily.get("sunrise"), i),
                "sunset": _at(daily.get("sunset"), i),
            }
        )
    return rows


def _at(seq, i):
    """Safe list index: return seq[i] or None if missing."""
    if seq is None or i >= len(seq):
        return None
    return seq[i]


def _daily_units(data: dict) -> dict:
    units = data.get("daily_units") or {}
    return {
        "temperature": units.get("temperature_2m_max"),
        "wind_speed": units.get("wind_speed_10m_max"),
        "precipitation": units.get("precipitation_sum"),
        "precip_probability": units.get("precipitation_probability_max"),
    }


def get_forecast(location: str, days: int = 3) -> dict:
    """
    Fetch a multi-day daily forecast for ``location``.

    ``days`` is clamped to 1..16 (Open-Meteo's daily limit). Returns a dict
    with the resolved location, a ``units`` sub-dict, and a ``days`` list where
    each entry has date, conditions, high/low temp, precipitation probability
    and total, and max wind.
    """
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 3
    days = max(1, min(days, MAX_FORECAST_DAYS))

    place = geocode(location)
    data = _fetch_daily(place, days)
    return {
        "location": place["label"],
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "units": _daily_units(data),
        "days": _daily_rows(data),
    }


def _resolve_date(target: str) -> date:
    """Parse a target date: '', 'today', 'tomorrow', or an ISO 'YYYY-MM-DD'."""
    target = (target or "").strip().lower()
    if target in ("", "today"):
        return date.today()
    if target == "tomorrow":
        return date.today() + timedelta(days=1)
    try:
        return datetime.strptime(target, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(
            f"Could not parse date {target!r}. Use 'today', 'tomorrow', or "
            f"'YYYY-MM-DD'."
        )


def get_daily_for_date(location: str, target_date: str = "today") -> dict:
    """
    Fetch the single-day forecast for ``location`` on ``target_date``.

    ``target_date`` accepts 'today', 'tomorrow', or an ISO 'YYYY-MM-DD' date
    within the next 16 days. Returns a dict with the resolved location, the
    ``units`` sub-dict, and a ``day`` sub-dict (same shape as one entry of
    ``get_forecast``'s ``days`` list). This is the data-fetch helper the
    prediction/recommendation MCP tools build their reasoning on top of.

    Raises ValueError for an out-of-range date and RuntimeError if the
    forecast has no matching day.
    """
    want = _resolve_date(target_date)
    offset = (want - date.today()).days
    if offset < 0:
        raise ValueError(
            f"{want.isoformat()} is in the past; this tool only forecasts today "
            f"and the next {MAX_FORECAST_DAYS - 1} days."
        )
    if offset >= MAX_FORECAST_DAYS:
        raise ValueError(
            f"{want.isoformat()} is more than {MAX_FORECAST_DAYS} days out; "
            f"Open-Meteo only forecasts {MAX_FORECAST_DAYS} days ahead."
        )

    place = geocode(location)
    data = _fetch_daily(place, offset + 1)
    want_iso = want.isoformat()
    match = next((r for r in _daily_rows(data) if r["date"] == want_iso), None)
    if match is None:
        raise RuntimeError(f"No forecast available for {want_iso} at {place['label']}.")
    return {
        "location": place["label"],
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "date": want_iso,
        "units": _daily_units(data),
        "day": match,
    }
