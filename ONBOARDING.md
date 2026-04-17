# Onboarding Guide

This document explains how the personal assistant codebase works. It is written for a developer who is new to the project and needs to understand the architecture, core concepts, and key workflows before contributing.

The codebase is a **tool-using AI agent** deployed as a web application. Users interact with it through a chat interface, and behind the scenes it can take real actions — create todos, check calendars, send reminders — not just generate text.

---

## Table of Contents

1. [High-Level Architecture](#1-high-level-architecture)
2. [The Agent Loop](#2-the-agent-loop)
3. [Tools and the Safety Model](#3-tools-and-the-safety-model)
4. [The Planner and Dynamic Prompts](#4-the-planner-and-dynamic-prompts)
5. [Data Model and Services](#5-data-model-and-services)
6. [Frontend and Chat UX](#6-frontend-and-chat-ux)
7. [Background Jobs and Proactive Behaviors](#7-background-jobs-and-proactive-behaviors)
8. [External Integrations](#8-external-integrations)
9. [Authentication and Multi-Tenancy](#9-authentication-and-multi-tenancy)

---

## 1. High-Level Architecture

### The three containers

Everything runs in Docker Compose with three services:

```
┌─────────────────┐     ┌─────────────────┐     ┌────────────┐
│    frontend      │────>│    backend       │────>│  postgres   │
│  (React + nginx) │     │   (FastAPI)      │     │  (shared)   │
│  :3002           │     │   :8000          │     │  :5432      │
└─────────────────┘     └─────────────────┘     └────────────┘
                              │
                        ┌─────┴──────┐
                        │    ntfy     │
                        │   (push)    │
                        │   :8090     │
                        └────────────┘
```

- **Frontend** — React SPA served by nginx. The nginx config reverse-proxies `/api/*` requests to the backend. The backend has no host port — it is only reachable through the frontend container.
- **Backend** — FastAPI (Python 3.12, async). Hosts the API endpoints, the agent loop, scheduled jobs, and all business logic.
- **ntfy** — Lightweight push notification server. The backend posts to it when reminders fire or proactive alerts trigger.

PostgreSQL is the shared instance from the infra stack (not in this compose file), connected via the `server-network` Docker network.

### The request lifecycle

When a user sends a message in the chat:

```
Browser -> nginx -> POST /api/chat/ -> FastAPI router -> Agent Orchestrator
                                                              |
                                                    1. Plan    (Haiku -- what strategy?)
                                                    2. Select  (which tools are relevant?)
                                                    3. Compose (build system prompt)
                                                    4. Loop    (Claude + tool calls, up to 10 rounds)
                                                    5. Parse   (extract structured response)
                                                    6. Log     (persist interaction + costs)
                                                              |
                                                    ChatResponse (JSON)
                                                              |
Browser <--- nginx <--- FastAPI <-────────────────────────────┘
```

This is **not** a simple "send message, get text back" system. The orchestrator runs an **agentic loop** — Claude can call tools, see the results, call more tools, and iterate up to 10 rounds before producing a final response. A single user message might trigger 3-4 LLM calls internally.

### What makes it "agentic"

1. **Tool use** — Claude can call tools across multiple domains (todos, calendar, email, reminders, etc.) that perform real actions against real data.
2. **Multi-turn reasoning** — If Claude needs to check the calendar before scheduling a todo, it does that autonomously within a single request.
3. **Safety gates** — Destructive or batch operations require explicit user confirmation before executing. The system classifies every tool call into a risk tier.

### Project structure

```
backend/
  app/
    agent/          <- The brain: orchestrator, planner, LLM client, tools
    services/       <- Business logic: CRUD operations, calendar sync, notifications
    routers/        <- HTTP endpoints (thin -- delegate to agent or services)
    models/         <- SQLAlchemy ORM
    prompts/        <- Dynamic system prompt components (Jinja2 templates)
    schemas/        <- Pydantic request/response models

frontend/
  src/
    components/     <- React components (chat, profile, people, todos, planning)
    hooks/          <- useChat (the main state hook)
    types/          <- TypeScript interfaces matching backend schemas
    utils/          <- API client wrapper
```

The backend's `agent/` directory is where the most important logic lives.

---

## 2. The Agent Loop

This is the heart of the system. Everything else exists to support what happens in `backend/app/agent/orchestrator.py`.

### Entry point

Every chat message hits a single function:

```python
async def run_agent_loop(user_message, session_id, db, confirmation_id, channel)
```

There are two paths through it:

1. **Normal path** — user sends a message, the full loop runs.
2. **Confirmation path** — user approved a high-stakes action, the system skips the LLM entirely and executes the cached tool call directly.

### The five phases (normal path)

**Phase 1: Context Assembly** (orchestrator lines ~90-118)

Before Claude sees anything, the system prepares three things:

1. **`assemble_context()`** — Resolves the user's timezone, name, and current datetime from profile facts. These become the template variables for the system prompt.
2. **`run_planner()`** — A separate, cheap LLM call (Haiku) that reads the user's message and recent conversation history, then decides:
   - **strategy**: a guidance note injected into the system prompt
   - **effort**: how hard Claude should think ("low" / "medium" / "high")
   - **components**: which optional prompt sections to activate
3. **`select_tools()`** — Uses vector similarity (OpenAI embeddings) to pick the ~12 most relevant tools out of the full registry. Keeps Claude's context focused.

Then `compose_prompt()` assembles the system prompt from modular Jinja2 templates based on what the planner selected.

**Phase 2: Message Building** (orchestrator ~line 117)

`build_conversation_messages()` loads the last 3 turns from the session and replays them. It replays the **full message chain** — not just "user said X, assistant said Y", but the entire sequence including tool calls and tool results. Claude sees exactly what happened in prior turns.

**Phase 3: The Tool-Use Loop** (orchestrator lines ~128-219)

This is the agentic core. It is a `for` loop, max 10 iterations:

```
Round 1: Claude sees message + tools -> calls get_calendar_events
         Result appended to messages
Round 2: Claude sees calendar data -> calls create_todo
         Result appended to messages
Round 3: Claude sees todo created -> produces final text response
         stop_reason == "end_turn" -> break
```

Each round:
1. Call Claude with the full message history + system prompt + tool schemas.
2. Check `stop_reason`:
   - `"end_turn"` — Claude is done, extract final text, break.
   - `"tool_use"` — Claude wants to call tools, process them.
   - `"refusal"` — Claude declined, break with error.
3. For each tool call, check the **action tier**:
   - **HIGH_STAKES** — halt immediately, return a `ConfirmationRequired` response, save state.
   - **READ_ONLY / LOW_STAKES** — execute the handler, append result to messages.
4. Append the assistant's response + tool results as new messages for the next round.

Messages grow with each round. Round 2 sees everything from round 1. Claude builds up context as it works.

**Phase 4: Response Parsing** (orchestrator lines ~228-232)

Claude is instructed (via the system prompt) to output a JSON object:

```json
{
  "spoken_summary": "I've scheduled your dentist appointment for Thursday at 2pm.",
  "structured_payload": { "type": "daily_schedule", "items": [...] },
  "follow_up_suggestions": ["Show me Thursday's full schedule", "Set a reminder"]
}
```

`_build_response()` tries to parse this JSON. If parsing fails, the raw text becomes `spoken_summary` as a fallback.

**Phase 5: Log and Commit** (orchestrator lines ~234-240)

Every interaction is persisted:
- User message, parsed intent, full `ChatResponse`, and actions taken go to the `interactions` table.
- The **message chain** (all messages from this turn) is stored for future replay.
- Each LLM API call was already logged during the loop (tokens, cost, model) to the `llm_calls` table.

### The confirmation shortcut

When a HIGH_STAKES action needs approval, the tool name and args are cached in the interaction's `confirmation_required` field. When the user clicks "Approve":

1. The frontend re-sends the original message with `confirmation_id`.
2. The orchestrator skips the entire LLM — goes straight to `_execute_confirmed_action()`.
3. Looks up the cached tool call from session history.
4. Executes it directly and returns the result.

This is **deterministic** — no risk of Claude changing its mind on the re-run.

---

## 3. Tools and the Safety Model

Tools are how the assistant takes real actions. They are defined in `backend/app/agent/tools/`, with a central registry in `registry.py`.

### The anatomy of a tool

Every tool has these parts, registered at import time via `register_tool()`:

| Field | Purpose |
|-------|---------|
| `name` | Identifier Claude uses when calling it (e.g. `"create_todo"`) |
| `description` | Shown to Claude in the tool schema |
| `input_schema` | JSON Schema defining the parameters Claude must provide |
| `tier` | Safety classification: `READ_ONLY`, `LOW_STAKES`, or `HIGH_STAKES` |
| `handler` | The async function that does the work |
| `embedding_text` | Rich text for vector search — includes example user phrasings |
| `category` | Domain grouping (todo, calendar, profile, etc.) |

The handler always follows the same signature: `async def handler(db: AsyncSession, **kwargs) -> dict`. It receives the DB session plus whatever parameters Claude provided, and returns a dict.

Tool modules are organized by domain: `todo_tools.py`, `calendar_tools.py`, `reminder_tools.py`, `planning_tools.py`, `profile_tools.py`, `list_tools.py`, `gmail_tools.py`, `conversation_tools.py`.

### Tool selection: semantic search

The system uses **vector similarity**, not hardcoded rules, to decide which tools Claude sees:

1. At startup, every tool's `embedding_text` is embedded via OpenAI's `text-embedding-3-small` (in `tool_selector.py`).
2. At query time, the user's message (plus last 2 turns for context) is embedded.
3. Cosine similarity ranks all tools. The top 12 scoring above 0.40 are included.
4. A set of **general tools** (`get_todos`, `get_calendar_events`, `search_profile`, etc.) is always included as a floor so Claude can always read basic data.

This is why `embedding_text` matters — it's hand-crafted with example phrasings like *"Remind me to call mom at 3pm"* so the vector search matches natural language well.

### The three-tier safety model

Every tool is classified at registration time:

- **READ_ONLY** — Queries with zero side effects (e.g. `get_todos`, `get_calendar_events`). Auto-executed silently. Not logged as an "action taken."
- **LOW_STAKES** — Single creates/updates that are easily reversible (e.g. `create_todo`, `set_reminder`). Auto-executed, logged in `actions_taken`.
- **HIGH_STAKES** — Batch operations or destructive actions (e.g. `create_sub_todos`, `execute_daily_plan`, `delete_calendar_event`). The loop **halts immediately**, the tool call is cached, and a `ConfirmationRequired` response is returned to the frontend.

Unknown tools (not in the registry) default to HIGH_STAKES as a safety measure.

### The handler pattern

Handlers are thin wrappers that delegate to the service layer:

```python
async def handle_create_todo(db: AsyncSession, **kwargs: Any) -> dict:
    return await todo_service.create_todo(db, **kwargs)
```

Business logic never lives in the tool layer — it lives in `app/services/`. This keeps the tool layer focused on parameter translation and the service layer focused on actual operations.

---

## 4. The Planner and Dynamic Prompts

The system doesn't send the same prompt to Claude every time. A lightweight planner runs first to decide *how* to handle each request, then the system prompt is assembled dynamically from modular components.

### The planner (`agent/planner.py`)

A cheap, fast pre-flight call using Haiku that outputs:

- **`strategy`** — 2-5 sentences of approach guidance, injected into the system prompt.
- **`effort`** — Controls Claude's extended thinking: `"low"`, `"medium"`, or `"high"`.
- **`components`** — Which optional prompt sections to activate (e.g. `"daily_planning"`, `"schedule_overview"`).

If the planner fails, the system falls back gracefully — empty strategy, medium effort, no extra components.

### Prompt composition (`prompts/composer.py`)

The composer selects and orders prompt components, then renders each with Jinja2:

**Always included:**
- `core_identity.txt` — Role definition and behavioral principles.
- `current_context.txt` — Datetime, timezone (template variables).
- `tool_guidance.txt` — Instructions for how to use tools, data trust rules.

**Conditional:**
- `proactive_notification.txt` — Added when `channel="proactive"` (scheduled jobs).
- `daily_planning.txt` — Added when the planner selects it. Includes step-by-step planning instructions.
- `schedule_overview.txt` — Added when the planner selects it.
- `strategy.txt` — Added when the planner produces a non-empty strategy.

**Response format (one of):**
- `response_format_planning.txt` — Auto-selected when `daily_planning` is active. Includes the daily plan payload schema.
- `response_format_default.txt` — Used otherwise.

`_COMPOSITION_ORDER` ensures sections appear in a consistent sequence regardless of which are active.

### Behavioral-only prompts

No data is pre-loaded into the system prompt — no calendar events, no todos, no profile facts. The prompt tells Claude *how to behave* and *what tools are available*, then Claude fetches what it needs via tool calls. This keeps the system prompt small and cacheable, and means Claude only fetches data it actually needs.

### Prompt caching

The LLM client (`agent/client.py`) uses Anthropic's prompt caching with three breakpoints:
1. End of system prompt (stable across the entire agent loop).
2. End of tool definitions (stable across the loop).
3. End of the last message (grows each round — cache-hits on previous rounds).

This significantly reduces input token costs on multi-round tool-use conversations.

---

## 5. Data Model and Services

The models define the database schema (`models/tables.py`) and the services (`services/`) contain all business logic. The service layer mediates all database access — routers and tool handlers never query the database directly.

### Table groups

**Knowledge Base** — ProfileFact (versioned user facts with embeddings), Person (contacts with key dates and embeddings), SeedFieldVersion (form field edit history).

**Productivity** — Todo (the central productivity object, supports hierarchy and calendar sync), List/ListItem (simple named lists), DailyPlan (proposed/approved day plans).

**Infrastructure** — Interaction (conversation log with full message chain), LlmCall (per-API-call token/cost tracking), Credential (OAuth tokens), ScheduledNotification (push notification queue).

### The Todo model

This is the most important data model. A todo has a lifecycle: `backlog -> scheduled -> completed/cancelled`. It is both a task list item and a calendar block — when `scheduled_start`/`scheduled_end` are set, it automatically creates a Google Calendar event. Todos support hierarchy via `parent_todo_id`.

### Key service behaviors

**Calendar sync** (`services/todos.py: _sync_calendar`): Any time a todo's scheduled times change, this runs automatically. Times added with no event creates one; times changed updates it; times cleared deletes it. The calendar is always in sync.

**Status cascading** (`services/todos.py: update_todo` + `_maybe_update_parent_status`): Setting a todo's status to "completed" via `update_todo` cascades in both directions. Completing a parent auto-completes unfinished children. If all siblings of a parent are completed/cancelled, the parent auto-completes. The upward cascade walks the parent chain, so it works at any depth.

**LLM observability** (`services/conversations.py: log_llm_call`): Every API call to Claude is recorded with token usage (input, output, thinking, cache read, cache creation), estimated cost in USD, and the full raw API response (thinking text redacted for size).

### Data flow example

```
User: "Remind me to call the dentist at 3pm"

1. Orchestrator calls Claude with tools
2. Claude calls set_reminder(title="Call the dentist", remind_at="...")
3. Tool handler -> services/todos.create_todo()       -> Todo row (status=scheduled)
4.              -> _sync_calendar()                    -> Google Calendar event
5.              -> services/notifications.schedule_notification() -> Notification row
6. Result flows back to Claude -> final response
7. Orchestrator -> services/conversations.log_interaction()  -> Interaction row

... later, at 3pm ...
8. APScheduler poller -> finds due notification -> sends via ntfy -> phone
```

---

## 6. Frontend and Chat UX

The frontend is a React 19 SPA built with Vite, styled with Tailwind CSS, using react-router-dom for routing.

### Routing

- `/` — ChatPage (main chat interface)
- `/profile` — ProfilePage (user profile form)
- `/people`, `/people/new`, `/people/:id` — Contacts management
- `/todos` — Todo list
- `/planning` — Daily planning workflow

### State management

There is no global state library. The chat state lives in a single custom hook — `useChat()` (`hooks/useChat.ts`). It manages `messages`, `sessionId`, `isLoading`, and `error`, and exposes four actions: `sendMessage`, `confirmAction`, `rejectAction`, `startNewChat`.

Every other page uses local `useState` with direct `apiFetch` calls.

### The message flow

1. User types a message and hits Enter.
2. `useChat.sendMessage()` appends a `ChatMessage{role: "user"}` immediately (instant UI update).
3. Sets `isLoading = true` (disables input, shows loading dots).
4. POST `/api/chat/` with `{message, session_id}`.
5. On response, appends `ChatMessage{role: "assistant", response: ChatResponse}`.
6. Sets `isLoading = false`.

There is **no streaming** — the frontend waits for the complete response. The agentic loop involves multiple tool calls that can't be meaningfully streamed, and the response format is structured JSON that must be complete before the frontend can render it.

### The ChatResponse contract

The backend always returns:

```typescript
{
  spoken_summary: string;          // Always present -- the text bubble content
  structured_payload?: object;     // Optional rich data for special rendering
  actions_taken: ActionTaken[];    // What tools the agent executed
  confirmation_required?: object;  // Present when HIGH_STAKES action needs approval
  follow_up_suggestions: string[]; // Clickable chips for quick follow-ups
  session_id: string;              // Conversation continuity token
}
```

### AssistantMessage rendering

An `AssistantMessage` conditionally renders up to five elements from a single `ChatResponse`:

1. **spoken_summary** — Always shown as a text bubble.
2. **structured_payload** — Rich data card, dispatched by `type` field via `PayloadRenderer`.
3. **actions_taken** — Collapsible list of tool executions.
4. **confirmation_required** — Amber card with Approve/Reject buttons for HIGH_STAKES actions.
5. **follow_up_suggestions** — Clickable chips (only on the latest message).

### The structured payload system

Claude includes a `structured_payload` JSON object in its response when rich rendering is appropriate. The `type` field is dictated by the system prompt (e.g., `response_format_planning.txt` defines the `"daily_plan"` schema). The backend passes it through untouched, and the frontend's `PayloadRenderer` dispatches by type:

- `"daily_plan"` -> `DailyPlanView` (timeline of existing events + proposed tasks)
- `"daily_schedule"` -> `DailyScheduleView` (read-only event list)
- Unknown type -> raw JSON dump (development fallback)

This is extensible: adding a new payload type means adding a TypeScript interface, a React component, and a case in the switch.

### The confirmation flow (frontend side)

1. Backend returns `confirmation_required` with `{confirmation_id, tool_name, tool_args, description}`.
2. `ConfirmationCard` renders with Approve/Reject buttons.
3. Approve -> `confirmAction(confirmation_id)` -> POST with `{message, confirmation_id, session_id}` -> backend executes cached tool directly.
4. Reject -> `rejectAction()` -> sends "Never mind, cancel that." as a regular message.

---

## 7. Background Jobs and Proactive Behaviors

The system can act on its own, without a user message. APScheduler manages background jobs, initialized in FastAPI's lifespan context (`main.py`).

### Scheduled jobs

| Job | Trigger | What it does |
|-----|---------|--------------|
| `notification_poller` | Every 30s | Checks `scheduled_notifications` for due rows, sends via ntfy |
| `morning_briefing` | Daily cron | Runs the full agent loop to generate a daily plan proposal |
| `deadline_warning` | Daily cron | Checks for backlog todos with approaching deadlines, asks Claude to write a nudge |
| `key_date_alerts` | Daily cron | Checks Person records for upcoming birthdays/anniversaries |

All cron jobs use the user's local timezone (resolved from the database at startup). Each can be individually enabled/disabled via environment variables.

### Two categories of proactive behavior

**LLM-powered jobs** (morning briefing, deadline warnings): These run the full agent loop via `invoke_agent_proactively()` in `services/proactive.py`. This adapter creates its own DB session (since scheduled jobs run outside FastAPI's request lifecycle) and passes `channel="proactive"`, which causes the prompt composer to include the `proactive_notification.txt` component.

The morning briefing invokes the agent with a planning prompt. If Claude returns a `daily_plan` structured payload, it is saved as a `DailyPlan` proposal. A push notification with a deep link to `/planning` is sent so the user can review and approve.

**Simple jobs** (key date alerts, notification poller): These do not involve the LLM. Key date alerts scan Person records and format notifications directly. The notification poller is the delivery mechanism for the `set_reminder` tool — it queries for unsent notifications that are due and sends them.

### Notification delivery (ntfy)

All push notifications go through `send_ntfy()` — a simple HTTP POST to the ntfy container. The `Click` header can include a deep link URL, so tapping a notification opens the relevant page.

---

## 8. External Integrations

### Google Calendar (`services/google_calendar.py`)

**OAuth**: Standard OAuth 2.0 flow in `routers/auth.py`. A single token (stored in the `credentials` table) is shared between Calendar and Gmail. The Google SDK auto-refreshes expired access tokens; after each API call, tokens are re-saved in case a refresh occurred.

**Async pattern**: The Google API client is synchronous. Every operation is wrapped in `asyncio.to_thread()` so it doesn't block the event loop. A fresh service object is built per call.

**Assistant-created events**: Events created by the assistant get a blueberry color ID and `"[via Assistant]"` in the description. When reading events back, `_normalize_event()` checks for these markers and sets `is_assistant_created: true`.

**Free time finder**: `find_free_time()` uses Google's FreeBusy API to get busy periods and computes the gaps. The daily planner uses this to figure out where to slot tasks.

### Gmail (`services/gmail.py`)

Read-only — list, search, and read emails. No send/draft capability. Shares OAuth credentials with Calendar. Same `asyncio.to_thread()` wrapper pattern.

Long emails are truncated to 3000 characters to avoid blowing up the LLM context window.

### OpenAI Embeddings (`services/embeddings.py`)

Uses `text-embedding-3-small` for 1536-dimensional vectors, serving three purposes:

1. **Tool selection** — Matching user messages to relevant tools at query time.
2. **Profile search** — Semantic search over ProfileFact records.
3. **People search** — Semantic search over Person records.

`fact_to_text()` converts structured data into natural language before embedding (e.g., a person record becomes `"person: Sarah; relationship: sister; birthday: 1990-05-15"`). This produces better vector matches than embedding raw JSON.

---

## 9. Authentication and Multi-Tenancy

### Current state

The app is **single-user** with no user authentication. There is no login, no session cookie, no JWT, no auth middleware. The Tailscale network boundary is the auth boundary — anyone who can reach the frontend has full access.

Google OAuth exists only for the app to act on the user's behalf against Google APIs, not for user identity.

### What would need to change for multi-tenant

**No auth middleware**: Every route's only dependency is `Depends(get_db)`. Multi-tenant would require a user model, login system, and a `Depends(get_current_user)` injected into every route.

**All data tables are unscoped**: No table has a `user_id` column. Every query (e.g., `select(Todo)`) would need a `.where(Todo.user_id == user_id)` filter. This is the largest surface area change.

**Credential storage has no user scoping**: The `credentials` table stores one row per service name globally. Multi-tenant would need a `user_id` FK.

**Context assembly assumes one user**: `assemble_context()` loads all active profile facts with no user filter.

**Scheduled jobs assume one user**: APScheduler registers jobs globally with a single timezone. Multi-tenant would need per-user job scheduling.

The architecture is clean enough that most of this is mechanical — the service layer mediates all DB access, so the refactor is primarily adding a `user_id` parameter and `.where()` clause to each service function.
