# Build Your Own Weather MCP Server

**Grade:** B
**Status:** Pass (automatic by LLM)

---

## Feedback

### Hard Blockers
- **None detected.** No hardcoded secrets, MCP server code is present with 6 tools, and it is not a reuse of the Day 3 Alpaca server.

---

## Grading Table


Grading Table


| **Category**                          | **Score** | **Maximum** | **Feedback** |
|---------------------------------------|-----------|-------------|--------------|
| **MCP Server Correctness** (30 pts)   |           |             |              |
| - At least 3 distinct tools exposed via `@mcp.tool` | 10/10 | 10 | `weather_mcp_server.py` defines 6 tools (`get_current_weather`, `get_forecast`, `predict_umbrella_needed`, `get_travel_recommendation`, `compare_weather`, `get_current_user`). |
| - Tools have clear docstrings with Args/Returns | 5/5 | 5 | Each tool in `weather_mcp_server.py` includes Args/Returns sections in detailed docstrings. |
| - HTTP/parsing logic in a separate adapter module | 5/5 | 5 | All HTTP and JSON parsing are in `weather_broker.py`; `@mcp.tool` functions call broker helpers only. |
| - Server runs over streamable HTTP for Databricks Apps | 5/5 | 5 | `weather_mcp_server.py` runs FastMCP with `transport="http"`, and README instructs using `/mcp` path for Databricks Apps. |
| - Reasonable error handling (clean error dicts) | 5/5 | 5 | `@mcp.tool` functions wrap calls in `try/except` and return `{"status":"error","message":...}`; broker raises `RuntimeError/ValueError` with clean messages. |
| **Prediction/Recommendation Logic** (15 pts) | | | |
| - At least one tool applies derived logic (thresholds/rules) | 10/10 | 10 | `predict_umbrella_needed` applies probability/amount thresholds; `get_travel_recommendation` combines temp, precip, wind, and severe flags; `compare_weather` computes a comfort score. |
| - Logic/thresholds explained in docstring or README | 5/5 | 5 | Docstrings call out thresholds; README tool table documents umbrella and travel thresholds. |
| **Secrets & Security** (15 pts) | | | |
| - No hardcoded API keys or secrets in committed code | 10/10 | 10 | Open-Meteo is keyless; no keys found in code or configs. |
| - If API requires a key, it's fetched from a secret store | 5/5 | 5 | Not applicable here; README explicitly instructs the Databricks secrets pattern if swapping to a keyed provider and warns against hardcoding. |
| **Agent Configuration** (20 pts) | | | |
| - Agent registered against student's own MCP server as an external tool | 0/5 | 5 | README describes how and includes app URLs, but no verifiable evidence of the agent actually being registered (no exported agent config or viewable screenshot/transcript). |
| - System prompt clearly instructs tool usage order and scope | 5/5 | 5 | `agent_system_prompt.md` maps question types to tools and enforces "always call a tool," date handling, and explanation expectations. |
| - System prompt includes at least one explicit guardrail | 5/5 | 5 | Multiple guardrails (don't invent data; handle ambiguous locations; enforce 16-day window; concise/practical answers). |
| - Agent behavior matches the system prompt in transcripts | 0/5 | 5 | Only image links are provided; without accessible transcripts or textual logs, behavior can't be verified. |
| **Documentation & Deployment Readiness** (10 pts) | | | |
| - README explains architecture, tool list, and which weather API + auth | 5/5 | 5 | Clear architecture diagram, file list, tool definitions, Open-Meteo choice, and auth rationale. |
| - `requirements.txt`/`app.yaml` present and plausible for Databricks App | 5/5 | 5 | Both MCP server and dashboard include `app.yaml` and `requirements.txt` with appropriate deps (`fastmcp`, `flask`, `requests`, `databricks-sdk`). |
| **Demonstration** (10 pts) | | | |
| - 3+ natural-language questions shown with tool calls and final answers | 0/5 | 5 | Only image links are provided; without viewable transcripts or pasted logs, this cannot be verified. |
| - Answers consistent with tool outputs (no obvious hallucination) | 0/5 | 5 | Cannot assess without accessible transcripts/logs. |

**Total Score:** 80/100

---

## Most Important Improvements

1. **Provide verifiable demonstration evidence:**
   - Paste at least 3 text transcripts (tool call inputs/outputs plus final answers) or include the raw MCP Inspector logs in the README so grading can confirm behavior.

2. **Show proof of Agent Bricks registration against your MCP server:**
   - Add a screenshot with visible MCP name and server URL, or export the agent/tool config details in text.

3. **Include at least one transcript showing guardrails in action:**
   - Example: Ambiguous "Springfield" and an out-of-range date to validate error handling and prompt adherence.

4. **Optionally add a brief smoke test script:**
   - Or `curl` examples that exercise each tool and demonstrate clean error messages for bad inputs.

---

## Evidence Limitations

- **Screenshots:** Could not open or verify the screenshots from the GitHub "user-attachments" links.
  **Remedy:** Paste text transcripts of agent chats (including tool calls and returned JSON), or provide accessible image links plus a brief textual summary for each screenshot showing the question, tools invoked, and the final answer.

- **Agent Registration Verification:**
  **Remedy:** Include either:
  - A screenshot of the Agent Bricks "Tools" panel showing your external MCP and its tools, **or**
  - A short note with the MCP name/URL as registered and a log line from the agent showing a call to, e.g., `predict_umbrella_needed`.

---

## Unsupported Files

The following files were not recognized (unsupported formats):
- `.orig_head`, `.config`, `.head`, `.description`, `.index`, `.packed-refs`, `.commit_editmsg`, `.fetch_head`, `.pyc`, `.sample`, `.pack`, `.idx`, `.rev`, and other Git/internal files.

> **Note:** For grading, supported formats are:
> - Documents: `.pdf`, `.txt`, `.md`, `.rtf`
> - Images: `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`
> - Submission: `.zip` or a single image.

---
*Submit as a `.zip` or a single image.*

---
