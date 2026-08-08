# Weather-Prediction MCP Server + Agent
**Date:** 2026-08-08
**Based on:** Day 3 (`databricks-lakebase-app-day-3`) - Agent Bricks + Alpaca Markets paper-trading MCP server

---

## TL;DR
Build your own **MCP server** that exposes weather-forecast tools. Wire a **Databricks Agent Bricks agent** to use it for answering weather questions and making simple predictions/recommendations. Deploy both as **Databricks Apps**, following the same split as Day 3's `mcp_server/` + `dashboard/`.

---

## What You're Building
1. **MCP Server** (`FastMCP`, like `mcp_server/alpaca_mcp_server.py`)
   - Exposes weather tools backed by a **free weather API** (no paid tier or credit card required).
2. **Broker/Adapter Module** (like `alpaca_broker.py`)
   - Calls the weather API and returns clean dictionaries.
   - Keep `@mcp.tool` functions thin; push HTTP/parsing logic into this module.
3. **Databricks Agent Bricks Agent**
   - Uses your MCP server as an external tool to answer natural-language weather questions (e.g., *"Will it rain in Chicago tomorrow?"*, *"Should I bring a jacket to Austin this weekend?"*).
4. **(Optional Stretch) Dashboard App**
   - Like `dashboard/`, showing recent agent queries/predictions (extra credit).

---

## Suggested Free Weather APIs
   API | Signup | API Key | Rate Limit | Notes |
 |-----|--------|---------|------------|-------|
 | [Open-Meteo](https://open-meteo.com/) | ❌ No | ❌ No | ~10,000 calls/day | Non-commercial, global coverage. **Recommended for simplicity.** |
 | [National Weather Service API](https://www.weather.gov/documentation/services-web-api) | ❌ No | ❌ No | Unlimited | US-only, NOAA data. Great for alerts/forecasts. |
 | [WeatherAPI.com](https://www.weatherapi.com/) | ✅ Yes | ✅ Yes | 100,000 calls/month | Current + forecast + historical in one call. |

**Recommendation:** Start with **Open-Meteo** (zero credentials). If you need US-specific alerts, layer in the **NWS API** later.

---

## Required MCP Tools (Minimum 3)
Design your own tool names/signatures, but your MCP server **must** expose at least these capabilities (modeled after `get_quote`/`get_positions`/`get_account_summary` in `mcp_server/alpaca_mcp_server.py`):

1. **Current Conditions**
   - Example: `get_current_weather(location)`
   - Returns: Temperature, conditions, humidity, wind for a given location (city name, zip, or lat/lon).
2. **Forecast**
   - Example: `get_forecast(location, days)`
   - Returns: Multi-day forecast (temp high/low, precipitation chance, conditions).
3. **Simple Prediction/Recommendation**
   - Example: `predict_umbrella_needed(location, date)` or `get_travel_recommendation(location, date)`
   - Returns: Derived judgment (e.g., *"Bring an umbrella if precipitation chance > 40%"*).
   - **Key:** Show reasoning, not just raw API data.

**Stretch Tools (Optional):**
- Severe weather alerts
- Historical weather lookup
- Compare weather across multiple cities

---

## Requirements Checklist
- [ ] MCP server built with **FastMCP** (or MCP-compliant framework), exposing tools via `@mcp.tool` decorators.
- [ ] Follow the **streamable-HTTP pattern** from `mcp_server/alpaca_mcp_server.py`.
- [ ] Separate **adapter module** (like `alpaca_broker.py`) for HTTP calls/parsing.
- [ ] **No raw requests** inside `@mcp.tool` functions.
- [ ] If API requires a key:
  - Store it as a **Databricks secret** (never hardcode or commit to repo).
  - Use `_secret()` / `WorkspaceClient().secrets.get_secret()` pattern (see `mcp_server/alpaca_broker.py`).
- [ ] `requirements.txt` and `app.yaml` for your MCP server app (see `mcp_server/` for the pattern).
- [ ] Deployed as its own **Databricks App**.
- [ ] Databricks Agent Bricks agent **registered** against your MCP server as an external tool.
- [ ] Clear **system prompt** for your agent:
  - What it should do.
  - Which tools to call in what order.
  - Guardrails (e.g., *"Only answer for resolvable locations; if API fails, say so"*).
- [ ] Short `README.md` for your submission:
  - Architecture diagram (optional but encouraged).
  - List of tools.
  - Setup steps.
  - Weather API + auth method used.
- [ ] **Demonstration:**
  - Paste or screenshot **3+ natural-language questions** and the agent's tool-calling + final answers.

---

## What "Good" Looks Like
✅ **Tool Functions:**
- Clear **docstrings** (Args/Returns), matching the style in `mcp_server/alpaca_mcp_server.py`.
- **Error handling:** Bad location/API outage returns a clean error (not a stack trace). Agent reacts sensibly (e.g., asks user to clarify).

✅ **Prediction Tool:**
- Does **more than echo** the raw API (applies thresholds/logic and explains it in the docstring).

✅ **Security:**
- **No secrets** committed to Git.
- **No hardcoded API keys**.

✅ **Agent Behavior:**
- System prompt is **specific enough** to prevent hallucinating weather data.

---
## Submission
Push your **MCP server + agent config** (system prompt, tool list) to your own repo/branch and share:
- Repo link.
- Databricks App URLs (or screenshots if workspace access is restricted).
- Include your `README.md`.
