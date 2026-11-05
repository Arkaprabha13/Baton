# Baton — File-by-File Implementation Plan
> **For OpenCode (Builder).** Follow this plan strictly. Do NOT skip files. Do NOT write code not described here. Run the specified unit test for every file before moving on.

---

## Conventions
- All Python files use `async/await` throughout.
- DB connections come **only** from `core/db.py` — never open a raw connection elsewhere.
- LLM calls go **only** through `core/llm.py` — never import model SDKs directly in agents or adapters.
- Every function must have a Google-style docstring.
- Tests live in `tests/` and mirror the source tree (e.g., `core/config.py` → `tests/test_core_config.py`).

---

## 1. `core/` — Foundation Layer

### `core/config.py`
**Purpose:** Single source of truth for all runtime settings. Loads from environment variables via `pydantic-settings`. Fails fast on missing secrets.

**Must contain:**
```
class Settings(BaseSettings):
    # Supabase
    supabase_url: str
    supabase_service_key: str
    db_dsn: str                     # postgresql+psycopg://...

    # LLM API Keys
    nvidia_api_key: str
    groq_api_key: str
    gemini_api_key: str

    # Rate limits (per-minute)
    nvidia_rpm: int = 10
    groq_rpm: int = 30
    gemini_rpm: int = 15

    # Services
    maps_scraper_url: str = "http://localhost:8080"
    gmail_mcp_url: str = "http://localhost:3100"

    # HITL
    hitl_approval_timeout_seconds: int = 3600

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

settings = Settings()
```

**Unit test (`tests/test_core_config.py`):**
- Monkeypatch all required env vars with dummy values.
- Assert `settings.nvidia_api_key` equals the monkeypatched value.
- Assert instantiation raises `ValidationError` when `supabase_url` is missing.

---

### `core/db.py`
**Purpose:** Provides a managed `psycopg_pool.AsyncConnectionPool` singleton, plus a `get_conn()` async context manager used by all DB-writing modules.

**Must contain:**
```python
async def init_pool() -> None
    """Initialise the global connection pool. Call once at startup."""

async def get_conn() -> AsyncGenerator[AsyncConnection, None]
    """Async context manager yielding a connection from the pool."""

async def close_pool() -> None
    """Drain and close the connection pool. Call at shutdown."""
```

**Unit test (`tests/test_core_db.py`):**
- Use `pytest-asyncio` with an in-memory SQLite or a Supabase test project DSN injected via env.
- Call `init_pool()`, acquire a connection with `get_conn()`, execute `SELECT 1`, assert result is `[(1,)]`.
- Call `close_pool()`, assert pool is closed (attempt `get_conn()` raises).

---

### `core/llm.py`
**Purpose:** LLM routing layer. Exposes a single `chat()` coroutine that picks the right provider based on `model` argument, logs token usage to `rate_limit_log`, and enforces per-minute rate limits.

**Must contain:**
```python
ModelProvider = Literal["nemotron", "groq", "gemini"]

async def chat(
    messages: list[dict],
    model: ModelProvider = "nemotron",
    *,
    temperature: float = 0.3,
    max_tokens: int = 2048,
    enable_thinking: bool = False,   # Nemotron only
) -> str:
    """Route to the correct LLM, log to rate_limit_log, return content string."""

async def embed(text: str) -> list[float]:
    """Embed text using Gemini text-embedding-004; returns vector(1536)."""

async def _log_usage(service: str, endpoint: str, tokens_in: int, tokens_out: int) -> None:
    """Write a row to rate_limit_log via core.db.get_conn()."""
```

**Provider routing table:**
| `model` | SDK | Base URL | Model ID |
|---|---|---|---|
| `nemotron` | `openai` | `https://integrate.api.nvidia.com/v1` | `nvidia/nemotron-3-super-120b-a12b` |
| `groq` | `groq` | (default) | `llama-3.3-70b-versatile` |
| `gemini` | `google-genai` | (default) | `gemini-2.0-flash` |

**Unit test (`tests/test_core_llm.py`):**
- Mock all three SDK clients.
- Call `chat(messages=[{"role":"user","content":"hi"}], model="nemotron")`.
- Assert the OpenAI client was called with `base_url="https://integrate.api.nvidia.com/v1"`.
- Call again with `model="groq"`, assert Groq client was called.
- Assert `_log_usage` was called once per `chat()` call.
- Call `embed("hello")`, assert the returned list has length 1536.

---

## 2. `adapters/` — External Integration Layer

### `adapters/scraper.py`
**Purpose:** Wraps the Maps Scraper Docker REST API (`vendor/maps-scraper`). Submits a scrape job, polls until complete, downloads and parses the result CSV into a list of raw lead dicts.

**Must contain:**
```python
async def submit_job(query: str, location: str, max_results: int = 100) -> str:
    """POST /api/v1/jobs; return job_id."""

async def poll_job(job_id: str, timeout_s: float = 300.0, interval_s: float = 5.0) -> str:
    """Poll GET /api/v1/jobs/{job_id} until status == 'done'; return download URL."""

async def download_results(download_url: str) -> list[dict]:
    """GET download_url, parse CSV rows, return list of dicts."""

async def scrape(query: str, location: str, max_results: int = 100) -> list[dict]:
    """Compose submit_job → poll_job → download_results pipeline."""
```

**Unit test (`tests/test_adapters_scraper.py`):**
- Use `respx` or `aioresponses` to mock HTTP calls.
- Mock `POST /api/v1/jobs` returning `{"job_id": "abc123"}`.
- Mock `GET /api/v1/jobs/abc123` returning `{"status": "done", "download_url": "/dl/abc123.csv"}`.
- Mock the download returning a CSV string with 2 rows.
- Call `scrape("coffee shops", "NYC")` and assert the result is a list of 2 dicts.

---

### `adapters/email.py`
**Purpose:** Thin async wrapper around the Gmail MCP server SSE endpoint (`vendor/gmail-mcp`). Uses `langchain-mcp-adapters` to call `send_email` and `search_emails` tools.

**Must contain:**
```python
async def send_email(to: str, subject: str, body: str) -> dict:
    """Call the MCP send_email tool; return the tool response dict."""

async def search_emails(query: str, max_results: int = 20) -> list[dict]:
    """Call the MCP search_emails tool; return list of email dicts."""

async def _get_mcp_client() -> MultiServerMCPClient:
    """Return a cached MultiServerMCPClient connected to gmail_mcp_url/sse."""
```

**Unit test (`tests/test_adapters_email.py`):**
- Mock `MultiServerMCPClient` and its `ainvoke` method.
- Call `send_email("a@b.com", "Hi", "Body")`, assert `ainvoke` was called with tool name `"send_email"`.
- Call `search_emails("from:boss@corp.com")`, assert result is a list.

---

## 3. `agents/` — LangGraph Multi-Agent Layer

> All agents are LangGraph nodes. The shared state type is defined in `agents/state.py`.

### `agents/state.py`
**Purpose:** Define `BatonState` TypedDict used across all LangGraph nodes.

**Must contain:**
```python
class BatonState(TypedDict):
    lead_id: str
    raw_data: dict
    cleaned_data: dict
    enriched_data: dict
    score: float
    stage: str
    messages: list[dict]        # conversation history
    quotation_id: str | None
    approval_status: str | None  # pending | approved | rejected
    errors: list[str]
```

**Unit test (`tests/test_agents_state.py`):**
- Instantiate a `BatonState` dict with all required keys.
- Assert `isinstance(state, dict)` is `True`.

---

### `agents/supervisor.py`
**Purpose:** Orchestrates routing between agent nodes based on `state["stage"]`. Decides next node or ends the graph.

**Must contain:**
```python
def route(state: BatonState) -> str:
    """Return the name of the next node ('cleaner'|'enricher'|'qualifier'|'negotiator'|'reporter'|END)."""

async def supervisor_node(state: BatonState) -> BatonState:
    """LangGraph node: logs the routing decision, may call core.llm.chat() for edge-case reasoning."""
```

**Unit test (`tests/test_agents_supervisor.py`):**
- Build a state with `stage="raw"`. Assert `route(state) == "cleaner"`.
- Build a state with `stage="qualified"`. Assert `route(state) == "negotiator"`.
- Build a state with `stage="converted"`. Assert `route(state) == END`.

---

### `agents/cleaner.py`
**Purpose:** Deduplicates and normalises raw scraped lead data. Writes cleaned lead to DB (upsert on `dedupe_key`). Transitions stage `raw → cleaned`.

**Must contain:**
```python
async def cleaner_node(state: BatonState) -> BatonState:
    """Normalise raw_data, compute dedupe_key, upsert leads table, return updated state."""

def normalise(raw: dict) -> dict:
    """Pure function: lowercase emails, strip whitespace, map field aliases."""

def compute_dedupe_key(normalised: dict) -> str:
    """Return SHA-256 hex of (email|phone|business_name+address)."""
```

**Unit test (`tests/test_agents_cleaner.py`):**
- Call `normalise({"Email": " Test@Example.COM ", "Name": "  Acme  "})`.
- Assert `result["email"] == "test@example.com"` and `result["name"] == "Acme"`.
- Call `compute_dedupe_key(normalised)`, assert it's a 64-character hex string.
- Mock `get_conn()`, call `cleaner_node(state)`, assert state `stage == "cleaned"`.

---

### `agents/enricher.py`
**Purpose:** Augments cleaned leads with LinkedIn data or other enrichment sources. Writes to `lead_enrichment`. Transitions stage `cleaned → enriched`.

**Must contain:**
```python
async def enricher_node(state: BatonState) -> BatonState:
    """Call enrichment APIs, persist to lead_enrichment, return updated state."""

async def fetch_linkedin_data(name: str, company: str) -> dict:
    """Use Nemotron (long context) to summarise publicly available LinkedIn signals via web search context."""

async def persist_enrichment(lead_id: str, enrichment_type: str, payload: dict) -> None:
    """INSERT into lead_enrichment via get_conn()."""
```

**Unit test (`tests/test_agents_enricher.py`):**
- Mock `core.llm.chat()` to return a JSON string of enrichment data.
- Mock `get_conn()`.
- Call `enricher_node(state)`, assert state `stage == "enriched"` and `enriched_data` is non-empty.

---

### `agents/qualifier.py`
**Purpose:** Scores the lead 0–100 using Groq (fast). Writes score back to `leads.score`. Transitions `enriched → qualified` (score ≥ 60) or `enriched → lost` (score < 60).

**Must contain:**
```python
QUALIFICATION_THRESHOLD: float = 60.0

async def qualifier_node(state: BatonState) -> BatonState:
    """Score lead, persist score, set stage, return updated state."""

async def score_lead(enriched_data: dict) -> float:
    """Call core.llm.chat(model='groq') with scoring rubric; parse float from response."""

SCORING_PROMPT: str  # Module-level constant holding the scoring rubric
```

**Unit test (`tests/test_agents_qualifier.py`):**
- Mock `core.llm.chat()` to return `"72.5"`.
- Call `qualifier_node(state)`, assert `state["score"] == 72.5` and `state["stage"] == "qualified"`.
- Mock `core.llm.chat()` to return `"45.0"`.
- Assert `state["stage"] == "lost"`.

---

### `agents/negotiation.py`
**Purpose:** Runs the negotiation dialogue loop. Sends outreach email (via `adapters.email`), monitors replies, generates counter-proposals using Nemotron, creates quotations in DB. Flags for HITL approval when deal value exceeds threshold.

**Must contain:**
```python
HITL_VALUE_THRESHOLD: float = 5000.0   # USD

async def negotiation_node(state: BatonState) -> BatonState:
    """Drive the negotiation loop; return updated state with quotation_id."""

async def send_initial_outreach(lead_id: str, contact_email: str) -> str:
    """Generate personalised email via Nemotron, send via adapters.email, return gmail message_id."""

async def generate_proposal(state: BatonState) -> dict:
    """Return a quotation line_items dict using Nemotron reasoning."""

async def create_quotation(lead_id: str, line_items: dict) -> str:
    """INSERT into quotations, return quotation_id."""

async def request_hitl_approval(quotation_id: str) -> None:
    """INSERT into approvals with status='pending'; the HITL dashboard picks this up."""
```

**Unit test (`tests/test_agents_negotiation.py`):**
- Mock `adapters.email.send_email`, mock `core.llm.chat()`, mock `get_conn()`.
- Call `negotiation_node(state)`.
- Assert `state["quotation_id"]` is a non-empty string.
- Build a state whose proposal total exceeds `HITL_VALUE_THRESHOLD`.
- Assert `approvals` table insert was called (mock assertion on `get_conn()`).

---

### `agents/reporter.py`
**Purpose:** Generates a final conversion summary (Gemini Flash, long context). Writes to `conversion_events`. Ends the graph.

**Must contain:**
```python
async def reporter_node(state: BatonState) -> BatonState:
    """Summarise the full conversation, persist conversion_event, return final state."""

async def generate_summary(state: BatonState) -> str:
    """Call core.llm.chat(model='gemini') with full message history; return markdown summary."""

async def persist_conversion(lead_id: str, quotation_id: str, value: float) -> None:
    """INSERT into conversion_events via get_conn()."""
```

**Unit test (`tests/test_agents_reporter.py`):**
- Mock `core.llm.chat()` to return `"# Summary\nDeal closed."`.
- Mock `get_conn()`.
- Call `reporter_node(state)` with `stage="converted"`.
- Assert `state["stage"] == "converted"` and `generate_summary` was called with `model="gemini"`.

---

## 4. `tools/` — Operational Infrastructure

### `tools/hitl_dashboard.py`
**Purpose:** Minimal FastAPI app exposing the Human-in-the-Loop approval dashboard. Reads pending approvals from DB, allows approve/reject via POST endpoint.

**Must contain:**
```python
app = FastAPI(title="Baton HITL Dashboard")

@app.get("/approvals")
async def list_pending_approvals() -> list[dict]:
    """Return all approvals WHERE status = 'pending'."""

@app.post("/approvals/{approval_id}/approve")
async def approve(approval_id: str, approved_by: str) -> dict:
    """UPDATE approvals SET status='approved', approved_by=..., resolved_at=NOW()."""

@app.post("/approvals/{approval_id}/reject")
async def reject(approval_id: str, approved_by: str, notes: str = "") -> dict:
    """UPDATE approvals SET status='rejected', notes=..., resolved_at=NOW()."""
```

**Unit test (`tests/test_tools_hitl.py`):**
- Use `httpx.AsyncClient` with `app` transport.
- Mock `get_conn()` to return 1 pending approval row.
- `GET /approvals` → assert response is a list with 1 item.
- `POST /approvals/{id}/approve?approved_by=admin` → assert response `status == "approved"`.

---

### `tools/scheduler.py`
**Purpose:** APScheduler-based job runner. Schedules the Maps Scraper pipeline to run on a cron. Publishes new leads into the LangGraph pipeline.

**Must contain:**
```python
scheduler = AsyncIOScheduler()

async def run_scrape_pipeline(query: str, location: str) -> None:
    """Call adapters.scraper.scrape(), persist raw leads, enqueue into LangGraph."""

def add_scrape_job(query: str, location: str, cron_expr: str = "0 6 * * 1-5") -> str:
    """Add a cron job to the scheduler; return job_id."""

async def start_scheduler() -> None:
    """Start APScheduler. Called at app startup."""

async def stop_scheduler() -> None:
    """Shutdown APScheduler gracefully."""
```

**Unit test (`tests/test_tools_scheduler.py`):**
- Call `add_scrape_job("coffee shops", "NYC", "0 6 * * 1-5")`.
- Assert the returned job_id is non-empty.
- Assert `scheduler.get_job(job_id)` is not None.
- Assert the job's trigger is a `CronTrigger`.

---

## Dependency Map

```
core/config.py
    └─► core/db.py
    └─► core/llm.py
            └─► adapters/scraper.py
            └─► adapters/email.py
                    └─► agents/state.py
                            └─► agents/cleaner.py
                            └─► agents/enricher.py
                            └─► agents/qualifier.py
                            └─► agents/negotiation.py
                            └─► agents/reporter.py
                                    └─► agents/supervisor.py  (graph assembly)
                                            └─► tools/scheduler.py
                                            └─► tools/hitl_dashboard.py
```

---

## Build Order for OpenCode

| Order | File | Blocking Dependency |
|---|---|---|
| 1 | `core/config.py` | None |
| 2 | `core/db.py` | `core/config.py` |
| 3 | `core/llm.py` | `core/config.py`, `core/db.py` |
| 4 | `adapters/scraper.py` | `core/config.py` |
| 5 | `adapters/email.py` | `core/config.py` |
| 6 | `agents/state.py` | None |
| 7 | `agents/cleaner.py` | `agents/state.py`, `core/db.py` |
| 8 | `agents/enricher.py` | `agents/state.py`, `core/llm.py`, `core/db.py` |
| 9 | `agents/qualifier.py` | `agents/state.py`, `core/llm.py`, `core/db.py` |
| 10 | `agents/negotiation.py` | `agents/state.py`, `core/llm.py`, `adapters/email.py`, `core/db.py` |
| 11 | `agents/reporter.py` | `agents/state.py`, `core/llm.py`, `core/db.py` |
| 12 | `agents/supervisor.py` | All agent nodes |
| 13 | `tools/hitl_dashboard.py` | `core/db.py` |
| 14 | `tools/scheduler.py` | `adapters/scraper.py`, `agents/supervisor.py` |

---

> **Stop after each file. Run the specified test. Only proceed when the test passes.**
