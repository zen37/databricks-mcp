"""
Weather-prediction MCP server.

Exposes weather-forecast tools over MCP (Model Context Protocol) so a
Databricks Agent Bricks agent can call them like any other tool:

    - get_current_weather(location)
    - get_forecast(location, days)
    - predict_umbrella_needed(location, date)      # derived judgment + reasoning
    - get_travel_recommendation(location, date)    # derived judgment + reasoning
    - compare_weather(locations)                   # multi-city comparison
    - get_current_user()                           # end-user identity (Databricks App)

These tools are backed by the free Open-Meteo API (see weather_broker.py),
which needs no API key or signup, so this server can be deployed as a
Databricks App with no secrets to configure.

Design (mirrors Day 3's alpaca_mcp_server.py):
  * The ``@mcp.tool`` functions stay thin - all HTTP calls and JSON parsing
    live in weather_broker.py. No raw ``requests`` here.
  * The two prediction tools do MORE than echo the API: they apply explicit
    thresholds and return both a judgment and the ``reasoning`` behind it.

Deploy this as its own Databricks App (same app.yaml + FastMCP entrypoint
pattern documented at
https://docs.databricks.com/aws/en/agents/mcp-tools/custom-mcp) and register
its URL as an external MCP server for your Agent Bricks agent.

Run locally:
    python weather_mcp_server.py        # serves MCP on :8000
"""

import logging
import os
from contextvars import ContextVar

from fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

import weather_broker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("weather-mcp-server")

# Thresholds for the derived recommendations, tunable via env so the agent's
# judgment can be adjusted without code changes.
UMBRELLA_PROB_THRESHOLD = float(os.environ.get("UMBRELLA_PROB_THRESHOLD", "40"))  # %
UMBRELLA_PRECIP_THRESHOLD = float(os.environ.get("UMBRELLA_PRECIP_THRESHOLD", "0.1"))  # inch
JACKET_TEMP_THRESHOLD = float(os.environ.get("JACKET_TEMP_THRESHOLD", "50"))  # °
WINDY_THRESHOLD = float(os.environ.get("WINDY_THRESHOLD", "25"))  # wind unit

# Context variable to store request headers for accessing end-user identity.
_request_context: ContextVar[dict] = ContextVar("request_context", default={})


mcp = FastMCP("weather-prediction")


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Capture the HTTP headers Databricks injects with end-user identity."""

    async def dispatch(self, request: Request, call_next):
        headers = {
            "x-forwarded-user": request.headers.get("x-forwarded-user"),
            "x-forwarded-email": request.headers.get("x-forwarded-email"),
        }
        _request_context.set(headers)
        return await call_next(request)


# ---------------------------------------------------------------------------
# Core data tools (thin wrappers over weather_broker)
# ---------------------------------------------------------------------------


@mcp.tool
def get_current_weather(location: str) -> dict:
    """
    Get current weather conditions for a location.

    Args:
        location: A city name ("Chicago"), city + region ("Austin, TX"), a
            postal code ("60601"), or raw coordinates ("41.88,-87.63").

    Returns:
        On success, a dict with status="success" and the resolved location,
        an ISO ``as_of`` timestamp, ``temperature`` and ``feels_like``, textual
        ``conditions``, ``humidity``, ``wind_speed``/``wind_direction``,
        ``precipitation``, and a ``units`` sub-dict. On failure, a dict with
        status="error" and a human-readable ``message`` (never a stack trace).
    """
    try:
        data = weather_broker.get_current_weather(location)
        return {"status": "success", **data}
    except Exception as e:
        logger.exception("get_current_weather failed for %r", location)
        return {"status": "error", "message": str(e)}


@mcp.tool
def get_forecast(location: str, days: int = 3) -> dict:
    """
    Get a multi-day daily forecast for a location.

    Args:
        location: City name, "City, Region", postal code, or "lat,lon".
        days: Number of days to forecast, 1-16 (default 3). Values outside the
            range are clamped.

    Returns:
        On success, a dict with status="success", the resolved location, a
        ``units`` sub-dict, and a ``days`` list; each day has ``date``,
        ``conditions``, ``temp_high``/``temp_low``, ``precip_probability`` (%),
        ``precip_sum``, and ``wind_max``. On failure, status="error" with a
        human-readable ``message``.
    """
    try:
        data = weather_broker.get_forecast(location, days)
        return {"status": "success", **data}
    except Exception as e:
        logger.exception("get_forecast failed for %r", location)
        return {"status": "error", "message": str(e)}


# ---------------------------------------------------------------------------
# Prediction / recommendation tools (apply thresholds AND explain reasoning)
# ---------------------------------------------------------------------------


@mcp.tool
def predict_umbrella_needed(location: str, date: str = "today") -> dict:
    """
    Decide whether someone should bring an umbrella, with the reasoning shown.

    This does more than echo the API: it applies explicit thresholds to the
    forecast - umbrella recommended if precipitation probability >= 40% OR
    expected precipitation >= 0.1 in - and returns both the yes/no judgment and
    the numbers behind it.

    Args:
        location: City name, "City, Region", postal code, or "lat,lon".
        date: "today", "tomorrow", or an ISO date "YYYY-MM-DD" within 16 days.

    Returns:
        On success, a dict with status="success", location, date, conditions,
        ``precip_probability``, ``precip_sum``, a boolean ``umbrella_needed``,
        a short ``recommendation``, and a ``reasoning`` string explaining the
        decision against the thresholds. On failure, status="error" with a
        human-readable ``message``.
    """
    try:
        result = weather_broker.get_daily_for_date(location, date)
        day = result["day"]
        units = result["units"]
        prob = day.get("precip_probability")
        amount = day.get("precip_sum")
        precip_unit = units.get("precipitation") or "in"

        prob_hit = prob is not None and prob >= UMBRELLA_PROB_THRESHOLD
        amount_hit = amount is not None and amount >= UMBRELLA_PRECIP_THRESHOLD
        needed = bool(prob_hit or amount_hit)

        prob_txt = f"{prob}%" if prob is not None else "unknown"
        amount_txt = f"{amount} {precip_unit}" if amount is not None else "unknown"
        if needed:
            drivers = []
            if prob_hit:
                drivers.append(
                    f"chance of precipitation is {prob_txt} "
                    f"(>= {UMBRELLA_PROB_THRESHOLD:.0f}% threshold)"
                )
            if amount_hit:
                drivers.append(
                    f"expected precipitation is {amount_txt} "
                    f"(>= {UMBRELLA_PRECIP_THRESHOLD} {precip_unit} threshold)"
                )
            reasoning = (
                f"Bring an umbrella: {' and '.join(drivers)}. "
                f"Conditions: {day.get('conditions')}."
            )
            recommendation = "Bring an umbrella."
        else:
            reasoning = (
                f"No umbrella needed: chance of precipitation is {prob_txt} "
                f"(< {UMBRELLA_PROB_THRESHOLD:.0f}%) and expected precipitation is "
                f"{amount_txt} (< {UMBRELLA_PRECIP_THRESHOLD} {precip_unit}). "
                f"Conditions: {day.get('conditions')}."
            )
            recommendation = "No umbrella needed."

        return {
            "status": "success",
            "location": result["location"],
            "date": result["date"],
            "conditions": day.get("conditions"),
            "precip_probability": prob,
            "precip_sum": amount,
            "umbrella_needed": needed,
            "recommendation": recommendation,
            "reasoning": reasoning,
        }
    except Exception as e:
        logger.exception("predict_umbrella_needed failed for %r", location)
        return {"status": "error", "message": str(e)}


@mcp.tool
def get_travel_recommendation(location: str, date: str = "today") -> dict:
    """
    Give a plain-language "what should I plan for?" recommendation for a day,
    with the reasoning shown.

    Combines several forecast signals into a short packing/planning tip:
      * jacket if the low (or feels-like low) is below 50 deg,
      * umbrella if precipitation probability >= 40% or precip >= 0.1 in,
      * a caution flag for severe conditions (heavy rain/snow, storms, hail),
      * a windy note if max wind exceeds the windy threshold.

    Args:
        location: City name, "City, Region", postal code, or "lat,lon".
        date: "today", "tomorrow", or an ISO date "YYYY-MM-DD" within 16 days.

    Returns:
        On success, a dict with status="success", location, date, conditions,
        temp_high/temp_low, a boolean ``severe``, a list of ``advice`` tips, a
        one-line ``recommendation``, and a ``reasoning`` string. On failure,
        status="error" with a human-readable ``message``.
    """
    try:
        result = weather_broker.get_daily_for_date(location, date)
        day = result["day"]
        units = result["units"]
        temp_unit = units.get("temperature") or "°"
        wind_unit = units.get("wind_speed") or ""
        precip_unit = units.get("precipitation") or "in"

        high = day.get("temp_high")
        low = day.get("temp_low")
        feels_low = day.get("feels_like_low")
        prob = day.get("precip_probability")
        amount = day.get("precip_sum")
        wind = day.get("wind_max")
        severe = bool(day.get("severe"))

        advice = []
        reasons = []

        cold_ref = feels_low if feels_low is not None else low
        if cold_ref is not None and cold_ref < JACKET_TEMP_THRESHOLD:
            advice.append("Bring a jacket")
            reasons.append(
                f"low around {cold_ref}{temp_unit} "
                f"(< {JACKET_TEMP_THRESHOLD:.0f}{temp_unit})"
            )

        if (prob is not None and prob >= UMBRELLA_PROB_THRESHOLD) or (
            amount is not None and amount >= UMBRELLA_PRECIP_THRESHOLD
        ):
            advice.append("Bring an umbrella / rain gear")
            reasons.append(
                f"{prob}% chance of precipitation, {amount} {precip_unit} expected"
                if prob is not None
                else f"{amount} {precip_unit} precipitation expected"
            )

        if wind is not None and wind >= WINDY_THRESHOLD:
            advice.append("Expect it to be windy")
            reasons.append(f"winds up to {wind} {wind_unit}")

        if severe:
            advice.append(f"Take caution - severe weather ({day.get('conditions')})")
            reasons.append(f"forecast is {day.get('conditions')}")

        if not advice:
            advice.append("Looks like a pleasant day - no special prep needed")
            reasons.append(
                f"mild ({low}-{high}{temp_unit}), low precipitation, calm winds"
            )

        recommendation = "; ".join(advice)
        reasoning = (
            f"For {result['location']} on {result['date']} "
            f"({day.get('conditions')}, {low}-{high}{temp_unit}): "
            + "; ".join(reasons)
            + "."
        )

        return {
            "status": "success",
            "location": result["location"],
            "date": result["date"],
            "conditions": day.get("conditions"),
            "temp_high": high,
            "temp_low": low,
            "severe": severe,
            "advice": advice,
            "recommendation": recommendation,
            "reasoning": reasoning,
        }
    except Exception as e:
        logger.exception("get_travel_recommendation failed for %r", location)
        return {"status": "error", "message": str(e)}


@mcp.tool
def compare_weather(locations: list[str], date: str = "today") -> dict:
    """
    Compare the forecast across several locations for a given day and pick the
    one with the most pleasant conditions.

    Scores each location (warmer within a comfortable band, drier, and calmer
    is better) and returns the ranking plus a ``best`` pick with reasoning.
    Locations that can't be resolved are reported in ``errors`` rather than
    failing the whole call.

    Args:
        locations: A list of location strings (city names, "City, Region",
            postal codes, or "lat,lon"). At least one is required.
        date: "today", "tomorrow", or an ISO date "YYYY-MM-DD" within 16 days.

    Returns:
        On success, a dict with status="success", the ``date``, a ``results``
        list (each with location, conditions, temp_high/low, precip_probability,
        wind_max), any per-location ``errors``, and a ``best`` recommendation
        with ``reasoning``. On failure, status="error" with a ``message``.
    """
    try:
        if not locations:
            return {"status": "error", "message": "locations must be a non-empty list"}

        results = []
        errors = []
        for loc in locations:
            try:
                r = weather_broker.get_daily_for_date(loc, date)
                day = r["day"]
                results.append(
                    {
                        "location": r["location"],
                        "date": r["date"],
                        "conditions": day.get("conditions"),
                        "temp_high": day.get("temp_high"),
                        "temp_low": day.get("temp_low"),
                        "precip_probability": day.get("precip_probability"),
                        "wind_max": day.get("wind_max"),
                        "severe": bool(day.get("severe")),
                    }
                )
            except Exception as le:
                errors.append({"location": loc, "message": str(le)})

        if not results:
            return {
                "status": "error",
                "message": "Could not resolve any of the requested locations.",
                "errors": errors,
            }

        def comfort_score(r: dict) -> float:
            # Higher is better. Penalize deviation from ~72 deg, precip chance,
            # wind, and severe weather.
            high = r.get("temp_high")
            temp_pen = abs((high if high is not None else 72) - 72)
            precip_pen = (r.get("precip_probability") or 0) * 0.5
            wind_pen = (r.get("wind_max") or 0) * 0.3
            severe_pen = 100 if r.get("severe") else 0
            return -(temp_pen + precip_pen + wind_pen + severe_pen)

        best = max(results, key=comfort_score)
        reasoning = (
            f"{best['location']} looks best on {best['date']}: "
            f"{best['conditions']}, high {best['temp_high']}, "
            f"{best.get('precip_probability')}% chance of precipitation, "
            f"winds up to {best.get('wind_max')}."
        )

        return {
            "status": "success",
            "date": results[0]["date"],
            "results": results,
            "errors": errors,
            "best": {"location": best["location"], "reasoning": reasoning},
        }
    except Exception as e:
        logger.exception("compare_weather failed")
        return {"status": "error", "message": str(e)}


@mcp.tool
def get_current_user() -> dict:
    """
    Get information about the currently authenticated end user calling the MCP
    server.

    When running as a Databricks App, this returns the actual end user making
    the request (from the X-Forwarded-User header), not the service principal
    running the app.

    Returns:
        A dict with user_name (email from the X-Forwarded-User header),
        forwarded_email, and source ("request_header" or "service_principal").
    """
    try:
        headers = _request_context.get()
        forwarded_user = headers.get("x-forwarded-user")
        forwarded_email = headers.get("x-forwarded-email")
        if forwarded_user:
            return {
                "status": "success",
                "user_name": forwarded_user,
                "forwarded_email": forwarded_email,
                "source": "request_header",
            }

        from databricks.sdk import WorkspaceClient

        w = WorkspaceClient()
        user = w.current_user.me()
        return {
            "status": "success",
            "user_name": user.user_name,
            "display_name": user.display_name,
            "active": user.active,
            "source": "service_principal",
        }
    except Exception as e:
        logger.exception("Failed to get current user")
        return {"status": "error", "message": f"Failed to get current user: {str(e)}"}


if __name__ == "__main__":
    # Capture request headers for end-user identity before serving.
    if hasattr(mcp, "app") and mcp.app is not None:
        mcp.app.add_middleware(RequestContextMiddleware)

    # Databricks Apps route external HTTP traffic to this port via app.yaml;
    # streamable-http is the transport Databricks' MCP client/gateway expects
    # (see the "Host your own MCP" doc linked in the module docstring above).
    port = int(os.getenv("DATABRICKS_APP_PORT", os.getenv("PORT", 8000)))
    mcp.run(transport="http", host="0.0.0.0", port=port)
