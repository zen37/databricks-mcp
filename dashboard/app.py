"""
Weather dashboard: a small Flask app to WATCH the same weather data the
weather-prediction MCP server (weather_mcp_server.py) serves to the Agent
Bricks agent. This app never predicts anything itself - it just reads current
conditions, the daily forecast, and the umbrella recommendation for a location
straight from Open-Meteo via weather_broker.py, so a human can sanity-check
what the agent is seeing.

Deploy this as its OWN Databricks App (separate from weather_mcp_server.py) -
one app serves MCP tool calls, the other serves the human-facing UI. Both read
the same free Open-Meteo API through their own copy of weather_broker.py.

Run locally:
    python app.py        # serves UI on :8001
"""

import os

from flask import Flask, jsonify, render_template, request

import weather_broker

app = Flask(__name__)

DEFAULT_LOCATION = os.environ.get("DEFAULT_LOCATION", "Chicago")

# Recommendation thresholds - kept in sync with the MCP server so the
# dashboard's umbrella verdict matches what the agent's tool would return.
UMBRELLA_PROB_THRESHOLD = float(os.environ.get("UMBRELLA_PROB_THRESHOLD", "40"))
UMBRELLA_PRECIP_THRESHOLD = float(os.environ.get("UMBRELLA_PRECIP_THRESHOLD", "0.1"))


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.errorhandler(Exception)
def handle_exception(err):
    """Ensure all unhandled errors return JSON (not an HTML error page)."""
    status_code = getattr(err, "code", 500)
    if not isinstance(status_code, int):
        status_code = 500
    return jsonify({"error": str(err)}), status_code


@app.route("/")
def index():
    """Dashboard UI showing current conditions + forecast for a location."""
    return render_template("index.html", default_location=DEFAULT_LOCATION)


@app.route("/api/current")
def api_current():
    """Current conditions for a location."""
    location = request.args.get("location", DEFAULT_LOCATION)
    return jsonify(weather_broker.get_current_weather(location))


@app.route("/api/forecast")
def api_forecast():
    """Multi-day daily forecast for a location."""
    location = request.args.get("location", DEFAULT_LOCATION)
    days = int(request.args.get("days", 5))
    return jsonify(weather_broker.get_forecast(location, days))


@app.route("/api/umbrella")
def api_umbrella():
    """The same umbrella recommendation the MCP predict tool returns."""
    location = request.args.get("location", DEFAULT_LOCATION)
    date = request.args.get("date", "today")
    result = weather_broker.get_daily_for_date(location, date)
    day = result["day"]
    prob = day.get("precip_probability")
    amount = day.get("precip_sum")
    needed = bool(
        (prob is not None and prob >= UMBRELLA_PROB_THRESHOLD)
        or (amount is not None and amount >= UMBRELLA_PRECIP_THRESHOLD)
    )
    return jsonify(
        {
            "location": result["location"],
            "date": result["date"],
            "conditions": day.get("conditions"),
            "precip_probability": prob,
            "precip_sum": amount,
            "umbrella_needed": needed,
        }
    )


if __name__ == "__main__":
    host = os.getenv("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_RUN_PORT", 8001))
    app.run(debug=True, host=host, port=port)
