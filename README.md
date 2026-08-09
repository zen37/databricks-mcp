# Weather-Prediction MCP Server + Agent Bricks Agent

A **Model Context Protocol (MCP) server** that exposes weather-forecast tools,
wired to a **Databricks Agent Bricks agent** that answers natural-language
weather questions and makes simple predictions ("Will it rain in Chicago
tomorrow?", "Should I bring a jacket to Austin this weekend?").

Built on the same split as
[`databricks-lakebase-app-day-3`](../databricks-lakebase-app-day-3/README.md):
a `mcp_server/` app that serves MCP tool calls to the agent, and an optional
`dashboard/` app for a human-facing view - each deployed as its own Databricks
App from its own folder.

> **Why Open-Meteo?** [Open-Meteo](https://open-meteo.com/) is a free, global
> weather API that needs **no API key and no signup** (~10k calls/day,
> non-commercial). Students get real forecast data with zero credentials and no
> secret to manage - the weather analogue of Day 3's "instant paper account".

## Architecture

```
Agent Bricks agent  --(MCP tool calls)-->  mcp_server/weather_mcp_server.py  --(HTTPS)-->  Open-Meteo API
                                                        |                                   (geocoding + forecast,
                                                        | (all HTTP/parsing in               no key required)
                                                        v  weather_broker.py)
                                            dashboard/app.py  --(same broker, read-only)----> Open-Meteo API
```

- `mcp_server/` and `dashboard/` are **two separate Databricks Apps**. One
  serves MCP tool calls to the agent; the other serves a human-facing weather
  dashboard. Both hit the same free Open-Meteo API through their own copy of
  `weather_broker.py`.
- `weather_broker.py` is the **adapter/broker** (the weather equivalent of Day
  3's `alpaca_broker.py`): it is the only place that makes HTTP calls and
  parses JSON, returning clean dicts. **There are no raw `requests` calls
  inside the `@mcp.tool` functions.**
- `weather_mcp_server.py` wraps the broker with [FastMCP](https://gofastmcp.com/)
  `@mcp.tool` decorators and serves them over **streamable HTTP** - the
  transport Databricks' MCP client/gateway expects when you
  [host your own MCP server as a Databricks App](https://docs.databricks.com/aws/en/agents/mcp-tools/custom-mcp).
- The two **prediction tools** (`predict_umbrella_needed`,
  `get_travel_recommendation`) do more than echo the API: they apply explicit,
  tunable thresholds and return both a judgment and the `reasoning` behind it.

## Files

- `mcp_server/weather_mcp_server.py` - FastMCP server exposing the weather tools
- `mcp_server/weather_broker.py` - Open-Meteo adapter (geocoding + forecast, all HTTP/parsing)
- `mcp_server/app.yaml` / `mcp_server/requirements.txt` - Databricks App config for the MCP server
- `dashboard/app.py` - Flask dashboard (read-only view of current conditions + forecast)
- `dashboard/templates/index.html` - Dashboard UI
- `dashboard/weather_broker.py` - copy of the same adapter (each Databricks App deploys from its own folder)
- `dashboard/app.yaml` / `dashboard/requirements.txt` - Databricks App config for the dashboard
- `agent_system_prompt.md` - System prompt to paste into the Agent Bricks agent
- `.env.example` - Local dev env var template (no secrets - Open-Meteo is keyless)

## MCP tools

| Tool | Signature | Returns |
|------|-----------|---------|
| **Current conditions** | `get_current_weather(location)` | Temp, feels-like, conditions, humidity, wind, precipitation |
| **Forecast** | `get_forecast(location, days=3)` | Per-day high/low, precip probability + total, max wind (1-16 days) |
| **Umbrella prediction** | `predict_umbrella_needed(location, date="today")` | Boolean verdict + `reasoning` (precip prob >= 40% or >= 0.1 in) |
| **Travel/packing rec** | `get_travel_recommendation(location, date="today")` | Jacket/umbrella/wind/severe advice + `reasoning` |
| **Compare cities** (stretch) | `compare_weather(locations, date="today")` | Ranks locations, picks the nicest with `reasoning` |
| **End-user identity** | `get_current_user()` | The calling user (from `X-Forwarded-User` on Databricks Apps) |

`location` accepts a city name (`"Chicago"`), city + region (`"Austin, TX"`), a
postal code (`"60601"`), or raw coordinates (`"41.88,-87.63"`). `date` accepts
`"today"`, `"tomorrow"`, or an ISO `YYYY-MM-DD` within the next 16 days. Every
tool returns `status: "success"` or a clean `status: "error"` with a
human-readable message - never a stack trace.

## Weather API + auth

- **API:** Open-Meteo (`api.open-meteo.com` for forecasts,
  `geocoding-api.open-meteo.com` for resolving place names).
- **Auth:** none. No API key, no signup, so **no Databricks secret is
  required** for this lab.
- **If you swap in a keyed provider** (e.g. WeatherAPI.com): store the key as a
  Databricks secret and read it with the `_secret()` /
  `WorkspaceClient().secrets.get_secret()` pattern - see the note at the top of
  `mcp_server/weather_broker.py`. Never hardcode or commit a key.

## Setup

### 1. Local dev

```bash
cp .env.example .env   # optional - defaults work as-is; Open-Meteo needs no key
```

Run the MCP server:

```bash
cd mcp_server && pip install -r requirements.txt && python weather_mcp_server.py   # serves MCP on :8000
```

In a second terminal, run the dashboard:

```bash
cd dashboard && pip install -r requirements.txt && python app.py                    # serves UI on :8001
```

Open `http://localhost:8001`, type a city, and confirm you see current
conditions, a 5-day forecast, and an umbrella verdict. Use an
[MCP Inspector](https://docs.databricks.com/aws/en/agents/mcp-tools/connect-clients)
against `http://localhost:8000/mcp` to sanity-check the tools before deploying.

> `get_current_user()` uses the Databricks SDK; running it locally needs a
> Databricks CLI profile (`databricks auth login`). The weather tools need no
> auth at all.

### 2. Deploy both apps to Databricks Apps

Following Day 3's Git-folder + Apps-UI flow (no CLI required), deploy **two**
apps pointed at two subfolders of the same Git folder:

1. Create a Git folder for this repo (once).
2. **MCP server app:** Compute > Apps > Create app > Custom, name it e.g.
   `weather-mcp`, point its source at this repo's `mcp_server/` subfolder (so it
   picks up `mcp_server/app.yaml`). Deploy it and copy its base app URL (shown
   under **App status**, e.g. `https://mcp-server-xxxx.aws.databricksapps.com`) -
   you'll register that URL **with `/mcp` appended** as an external MCP server in
   step 3.
3. **Dashboard app:** repeat, naming it e.g. `weather-dashboard`, pointing at
   `dashboard/`. Deploy it and open its URL to confirm the dashboard loads.

### 3. Register the MCP server as an external MCP

Follow
[Connect agents to external MCPs and tools](https://docs.databricks.com/aws/en/agents/mcp-tools/connect-external):

1. In your workspace, go to **AI Gateway** > **MCPs** > **Add MCP**.
2. Set the **Server URL** to the `weather-mcp` app's base URL **with `/mcp`
   appended** - e.g. `https://mcp-server-xxxx.aws.databricksapps.com/mcp`. The
   FastMCP server serves the streamable-HTTP transport at the `/mcp` path, not at
   the app root, so the bare app URL will fail to load tools.
3. Choose an **Authentication** method (Bearer token with a Databricks PAT is the
   simplest; OAuth U2M per-user forwards the end user's identity to
   `get_current_user()`).
4. Name it (e.g. `weather-prediction`) and click **Create & load tools** -
   Databricks will introspect the server and list the 6 tools.

### 4. Build the Agent Bricks agent

1. **Agents** > **Agent Bricks** > **Create agent** > **Custom LLM**.
2. Under **Tools**, add the `weather-prediction` MCP server (all tools).
3. Paste the system prompt from [`agent_system_prompt.md`](agent_system_prompt.md).
4. Evaluate/iterate on sample prompts, then deploy and chat.

## Demonstration

Ask the deployed agent (or the MCP Inspector) questions like:

1. *"What's the weather in Chicago right now?"* -> `get_current_weather("Chicago")`
2. *"Will it rain in Chicago tomorrow - do I need an umbrella?"* -> `predict_umbrella_needed("Chicago", "tomorrow")`
3. *"Should I bring a jacket to Austin this weekend?"* -> `get_travel_recommendation("Austin", "<Saturday ISO date>")`
4. *"Is it nicer in Denver or Phoenix this weekend?"* -> `compare_weather(["Denver", "Phoenix"], "<ISO date>")`

Paste or screenshot the agent's tool calls + final answers for your submission.

## Notes

- `mcp_server/` and `dashboard/` intentionally duplicate `weather_broker.py`
  rather than sharing a package, because each Databricks App deploys
  independently from its own folder with its own `app.yaml`/`requirements.txt`.
  If you edit the broker, copy it to both folders (or publish it as a wheel and
  add it to both `requirements.txt` files instead).
- Thresholds for the prediction tools (`UMBRELLA_PROB_THRESHOLD`,
  `JACKET_TEMP_THRESHOLD`, etc.) are env vars set in each `app.yaml`, so you can
  tune the agent's judgment without changing code.

----
 # Links

 https://github.com/zen37/databricks-mcp

 https://weather-dashboard-7474651165193831.aws.databricksapps.com

 https://mcp-server-7474651165193831.aws.databricksapps.com

 ## Screenshots

 <img width="867" height="860" alt="image" src="https://github.com/user-attachments/assets/070d64d8-8d72-47ff-8793-5431dc3bde17" />

 <img width="957" height="885" alt="image" src="https://github.com/user-attachments/assets/dcc1dcb5-b6ec-41c6-aa8a-3c1547358a08" />

 <img width="1005" height="915" alt="image" src="https://github.com/user-attachments/assets/08849b80-e1ef-4619-886f-bd2ed0ecedda" />

 <img width="887" height="920" alt="image" src="https://github.com/user-attachments/assets/57fb406e-355b-4960-a3d6-00d4c512863c" />




 
