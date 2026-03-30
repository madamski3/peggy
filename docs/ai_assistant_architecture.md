# AI Personal Assistant — Architecture & Technical Design

## 1. Architecture Overview

The application follows a **tool-using agent** pattern: a central LLM orchestrator receives user input, gathers context, reasons about what to do, executes actions via tool calls, and returns a structured response. A separate scheduler handles proactive behaviors (nudges, morning planning) by triggering the same agent loop without user input.

### High-Level Component Map

```
┌──────────────────────────────────────────────────────────────────────┐
│                         HOME SERVER (Tailscale)                      │
│                                                                      │
│  ┌─────────────┐     ┌──────────────────────────────────────────┐   │
│  │  Frontend    │────▶│            Backend API (FastAPI)         │   │
│  │  (Chat UI)   │◀────│                                          │   │
│  │  React/Vite  │     │  ┌────────────────────────────────────┐  │   │
│  └─────────────┘     │  │        Agent Orchestrator           │  │   │
│                       │  │                                    │  │   │
│                       │  │  ┌──────────┐  ┌───────────────┐  │  │   │
│                       │  │  │ Context   │  │  Tool Router  │  │  │   │
│                       │  │  │ Assembler │  │               │  │  │   │
│                       │  │  └──────────┘  └───────┬───────┘  │  │   │
│                       │  │                        │          │  │   │
│                       │  └────────────────────────┼──────────┘  │   │
│                       │                           │              │   │
│                       │  ┌────────────────────────▼──────────┐  │   │
│                       │  │           Tool Layer               │  │   │
│                       │  │                                    │  │   │
│                       │  │  ┌──────────┐  ┌──────────────┐   │  │   │
│                       │  │  │ Internal  │  │  External    │   │  │   │
│                       │  │  │ Tools     │  │  Tools       │   │  │   │
│                       │  │  │          │  │              │   │  │   │
│                       │  │  │ • Tasks   │  │ • Calendar   │   │  │   │
│                       │  │  │ • Todos   │  │ • Gmail      │   │  │   │
│                       │  │  │ • Lists   │  │ • Weather    │   │  │   │
│                       │  │  │ • Profile │  │ • Plaid      │   │  │   │
│                       │  │  │ • People  │  │ • Push Notif │   │  │   │
│                       │  │  └──────────┘  └──────────────┘   │  │   │
│                       │  └───────────────────────────────────┘  │   │
│                       └──────────────────────────────────────────┘   │
│                                        │                             │
│  ┌──────────────┐     ┌───────────────▼──────────────────────────┐  │
│  │  Scheduler    │────▶│              Database                    │  │
│  │  (APScheduler)│     │              (PostgreSQL)                │  │
│  └──────────────┘     └──────────────────────────────────────────┘  │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
                    │                              │
                    ▼                              ▼
           ┌───────────────┐              ┌────────────────┐
           │ Anthropic API │              │ Google APIs     │
           │ (Claude)      │              │ Plaid, Weather  │
           └───────────────┘              │ Pushover/ntfy   │
                                          └────────────────┘
```

---

## 2. Tech Stack

### 2.1 Recommendations & Rationale

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Language** | Python | Your strongest backend language. Excellent ecosystem for LLM tooling, API clients, and all target integrations. |
| **LLM** | Claude (Anthropic API) | You're already familiar with the API. Native tool-use support is critical for this architecture — Claude can call tools, inspect results, and chain reasoning across multiple steps in a single turn. |
| **Backend framework** | FastAPI | Async-native, lightweight, great typing support. WebSocket support for streaming chat responses. Well-documented. |
| **Database** | PostgreSQL | See Section 2.2 for detailed rationale. |
| **Frontend** | React + Vite | Lightweight, fast iteration. A simple chat UI with structured response rendering (timelines, lists, confirmation cards). |
| **Scheduler** | APScheduler | Lightweight, in-process scheduler for proactive behaviors. No need for Airflow's overhead here — the jobs are simple triggers, not data pipelines. |
| **Push notifications** | ntfy or Pushover | Self-hostable (ntfy) or simple API (Pushover). Both support mobile push. ntfy aligns with the self-hosted philosophy. |
| **Containerization** | Docker Compose | Single `docker-compose.yml` to bring up the full stack: backend, frontend, database, scheduler. Clean separation, easy to manage on the home server. |

### 2.2 Database: Why PostgreSQL over SQLite or DuckDB

Given that you're already running DuckDB + Lightdash on the home server, the natural question is whether to reuse DuckDB here. The short answer is no — the access patterns are different.

**This application is OLTP, not OLAP.** The dominant operations are:
- Single-row inserts (new task, new list item, new profile fact)
- Single-row updates (mark task complete, update scheduling fields)
- Filtered reads with joins (get all pending tasks for todo X, get profile facts by category)
- Concurrent access from the backend API + scheduler

**PostgreSQL is the right fit because:**
- Full ACID transactions for concurrent read/write (scheduler + API hitting the DB simultaneously).
- JSONB columns for flexible structured data (profile fact values, task metadata, assistant response payloads) without needing a rigid schema for everything.
- Mature Python ecosystem (asyncpg for async access, SQLAlchemy or raw SQL).
- Rock-solid for indefinite data retention at this scale.
- Runs cleanly in Docker alongside the rest of the stack.

**SQLite was considered** and is viable for MVP (single-user, modest write volume), but it introduces friction around concurrent writes from the scheduler + API, and you'd eventually outgrow it once you want full-text search on conversation logs or complex queries on financial data. Starting with Postgres avoids a migration.

**DuckDB remains useful** for analytical queries — if you want to do deeper analysis on financial trends or task completion patterns, you could ETL snapshots from Postgres into your existing DuckDB/Lightdash stack. That's a clean separation of concerns: Postgres for the live application, DuckDB for offline analytics.

### 2.3 Prompt Management

System prompts are a critical part of the application — they define the assistant's personality, reasoning rules, tool-use behavior, and output format. They will require significant iteration, especially in the early stages. Rather than introducing a dedicated prompt management platform (e.g., Langsmith, Braintrust), which adds overhead without proportional benefit for a single-developer project, prompts are managed as **version-controlled template files**.

**Approach:**
- Prompts live in a dedicated `prompts/` directory as YAML or Jinja2 templates.
- Each prompt template is parameterized — context variables (current datetime, profile facts, calendar snapshot) are injected at runtime by the context assembler.
- Prompt versions are tracked via git. Meaningful changes get descriptive commit messages.
- A config setting allows swapping the active prompt version without code changes (e.g., `SYSTEM_PROMPT_VERSION=v3` in `.env`).
- If structured evaluation is needed later (e.g., "did prompt v3 produce better daily plans than v2?"), a lightweight tool like Promptfoo can be added as a dev-time testing harness without becoming part of the runtime architecture.

### 2.4 Semantic Search: pgvector

For context assembly and conversation history search, keyword matching is brittle — a user asking "what did we talk about for the dinner party?" should find interactions about "planning the menu" even if those exact words don't appear. **pgvector** is a PostgreSQL extension that adds vector similarity search to the existing database, avoiding the need for a separate vector database.

**MVP scope:**
- Install the pgvector extension in the Postgres instance (zero new infrastructure).
- Add an `embedding` column (type `vector(1536)` or similar) to the `interactions` table.
- When interactions are logged, generate an embedding for the user message + assistant response summary using a lightweight embedding model (e.g., Anthropic's Voyage or OpenAI's `text-embedding-3-small`).
- The `search_conversations` tool uses vector similarity (`<=>` cosine distance operator) instead of or alongside full-text search.

**Future expansion:**
- Embeddings on profile facts for better semantic matching during context assembly.
- Embeddings on todo/task titles and descriptions for natural-language todo search ("what was that thing about the faucet?").
- The context assembler could use embeddings to select which profile facts are most relevant to a given query, rather than relying solely on category-based heuristics.

**Why pgvector over a dedicated vector DB (Pinecone, Weaviate, etc.):**
- No new infrastructure to deploy, manage, or pay for.
- The data volume is modest (thousands of interactions, not millions) — pgvector handles this scale comfortably.
- Keeps all data in one place, simplifying backups and queries that join vector search results with relational data.

---

## 3. Agent Architecture

### 3.1 The Agent Loop

The core of the application is an **agentic tool-use loop** powered by Claude's native tool calling. This is not a simple request-response pattern — the agent can reason across multiple tool calls in a single turn.

```
User Message (or Scheduler Trigger)
        │
        ▼
┌───────────────────┐
│  Context Assembly  │  ← Gather relevant state before calling the LLM
│                   │     • User profile (relevant facts)
│                   │     • Recent conversation history
│                   │     • Current datetime + timezone
│                   │     • Active tasks/todos summary (if relevant)
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│  LLM Call         │  ← System prompt + context + user message + tool definitions
│  (Claude API)     │
│                   │     Claude reasons about what to do and returns either:
│                   │     (a) A final text response, or
│                   │     (b) One or more tool_use calls
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│  Tool Execution   │  ← If tool calls were returned:
│                   │     1. Validate the call (action classification check)
│                   │     2. If confirmation required → pause, notify user
│                   │     3. If auto-execute → run the tool, return result
│                   │     4. Send tool results back to Claude for next step
└───────┬───────────┘
        │
        ▼ (loop back to LLM if more reasoning needed)
        │
        ▼
┌───────────────────┐
│  Response Builder  │  ← Format Claude's final output into the response contract:
│                   │     • spoken_summary
│                   │     • structured_payload
│                   │     • actions_taken
│                   │     • confirmation_required
│                   │     • follow_up_suggestions
└───────┬───────────┘
        │
        ▼
┌───────────────────┐
│  Logging          │  ← Persist to Interaction log
└───────────────────┘
```

### 3.2 System Prompt Design

The system prompt is the assistant's "personality and playbook." It needs to be carefully constructed and will include:

```
System Prompt Structure
├── Identity & Personality
│   └── Who you are, how you behave, design principles (bias toward action, etc.)
│
├── Current Context (injected per-request)
│   ├── Current datetime and timezone
│   ├── User profile summary (relevant facts, not the entire graph)
│   ├── Today's calendar snapshot (if relevant to the query)
│   └── Todo backlog summary + today's scheduled tasks (if relevant)
│
├── Tool Definitions
│   └── Full tool schemas for all available tools (see Section 3.3)
│
├── Action Classification Rules
│   └── Which actions auto-execute, which require confirmation
│   └── Calendar event tagging rules
│
└── Response Format Instructions
    └── Always produce spoken_summary + structured_payload
    └── Voice-friendly constraints
```

**Key design consideration:** The system prompt will be substantial. Context window management matters — we don't want to stuff the entire database into every prompt. The Context Assembly step should intelligently select what's relevant:
- For "plan my day" → inject full calendar + todo backlog (unscheduled, due soon) + today's scheduled tasks + weather
- For "add milk to grocery list" → inject just the active grocery list
- For "how much did we spend on dining?" → inject financial summary tools, not todo data

### 3.3 Tool Definitions

Tools are the agent's hands. Each tool is defined as a function schema that Claude can call. They map to internal data operations and external API calls.

#### Internal Tools (Database Operations)

```
TODO TOOLS (Planning Layer)
├── get_todos(filters: {status?, priority?, deadline_before?, tags?, has_scheduled_tasks?})
│   → Returns filtered todo list with task summaries
│   → has_scheduled_tasks filter is useful for finding unscheduled backlog items
├── create_todo(title, description?, priority?, deadline?, target_date?,
│                  preferred_window?, estimated_duration_minutes?, energy_level?,
│                  tags?, location?, parent_todo_id?)
│   → Creates a todo in the backlog (status: backlog)
├── update_todo(todo_id, fields_to_update)
│   → Updates todo fields (priority, deadline, tags, etc.)
├── complete_todo(todo_id)
│   → Marks todo complete (verifies all tasks are done or cancels remaining)
├── get_todo_detail(todo_id)
│   → Returns todo with all tasks, progress, notes
└── create_todo_with_task(title, description?, priority?, scheduled_start,
│                           scheduled_end, estimated_duration_minutes?)
    → Shortcut for reminders and simple items: creates a Todo + single Task
      simultaneously. Todo goes straight to "active" status.

TASK TOOLS (Execution Layer)
├── get_tasks(filters: {status?, todo_id?, scheduled_date?, date_range?})
│   → Returns filtered task list (typically: "what's scheduled for today?")
├── create_task(todo_id, title, description?, scheduled_start, scheduled_end,
│              estimated_duration_minutes?, position?)
│   → Creates a task linked to a todo, optionally creates calendar event
├── create_tasks_batch(todo_id, tasks[])
│   → Creates multiple tasks for a todo at once (used during decomposition)
│   → Each task: {title, scheduled_start, scheduled_end, estimated_duration_minutes}
├── update_task(task_id, fields_to_update)
│   → Updates task fields (reschedule, etc.)
├── complete_task(task_id, actual_duration_minutes?, completion_notes?)
│   → Marks task complete, records actual duration for learning
│   → If all tasks for the parent todo are done, marks todo complete too
├── defer_task(task_id, new_scheduled_start?, new_scheduled_end?)
│   → Reschedules a task, increments deferred_count
└── cancel_task(task_id)
    → Cancels a task (soft delete)

LIST TOOLS
├── get_lists(filters: {type?, status?})
│   → Returns all lists or filtered subset
├── get_list_items(list_id, filters: {status?})
│   → Returns items on a specific list
├── create_list(name, type, description?)
│   → Creates a new list
├── add_list_item(list_id, name, notes?)
│   → Adds an item to a list
├── complete_list_item(item_id)
│   → Marks a list item as done
├── bulk_complete_list_items(list_id, exceptions[]?)
│   → Marks all items done, optionally excluding some

PROFILE TOOLS
├── get_profile_facts(filters: {category?, key_pattern?})
│   → Returns matching profile facts with provenance
├── add_profile_fact(category, key, value, provenance, evidence?, confidence?)
│   → Adds a new fact (checks for conflicts first)
├── update_profile_fact(fact_id, new_value, provenance?)
│   → Updates an existing fact (preserves audit trail)
└── get_people(filters: {relationship?, name?})
    → Returns people records

CONVERSATION TOOLS
├── search_conversations(query, date_range?)
│   → Full-text search over conversation history
└── get_recent_conversations(n?)
    → Returns last N interactions for context
```

#### External Tools (API Integrations)

```
CALENDAR TOOLS
├── get_calendar_events(date_start, date_end)
│   → Returns events in the date range
├── create_calendar_event(title, start, end, description?, color?)
│   → Creates an event with assistant metadata tag
│   → Auto-applies assistant color + created_by marker
├── update_calendar_event(event_id, fields_to_update)
│   → Updates an event; checks if assistant-created for action tier
├── delete_calendar_event(event_id)
│   → Deletes an event; checks if assistant-created for action tier
└── find_free_time(date, min_duration_minutes?)
    → Returns available time blocks for a given day

GMAIL TOOLS
├── get_recent_emails(n?, labels?, after_date?)
│   → Returns recent emails (subject, sender, snippet, date)
├── get_email_detail(email_id)
│   → Returns full email body
└── search_emails(query)
    → Searches email by Gmail query syntax

WEATHER TOOLS
├── get_weather_forecast(date?)
│   → Returns hourly forecast for the given day (defaults to today)
│   → Includes temperature, precipitation probability, wind, conditions
└── get_current_weather()
    → Returns current conditions

FINANCIAL TOOLS
├── get_account_balances()
│   → Returns current balances for all linked accounts
├── get_transactions(date_start, date_end, category?, account_id?)
│   → Returns filtered transactions
├── get_spending_summary(period: "this_month" | "last_month" | date_range)
│   → Returns categorized spending totals with comparisons to prior periods
└── get_net_worth_snapshot(date?)
    → Returns net worth with breakdown, plus trend data

NOTIFICATION TOOLS
├── send_push_notification(title, body, priority?)
│   → Sends a push notification via ntfy/Pushover
└── schedule_notification(title, body, send_at)
    → Schedules a future notification (for reminders)
```

### 3.4 Action Classification Middleware

Between the LLM returning a tool call and the tool actually executing, there's a **classification middleware layer** that enforces the action tiers from the requirements doc.

```python
# Pseudocode for the action classification middleware

def classify_action(tool_name: str, tool_args: dict) -> ActionTier:
    """Determine the action tier for a given tool call."""

    # Read-only tools: always auto-execute
    READ_ONLY = {
        "get_tasks", "get_todos", "get_todo_detail",
        "get_lists", "get_list_items",
        "get_profile_facts", "get_people", "get_calendar_events",
        "find_free_time", "get_recent_emails", "get_email_detail",
        "search_emails", "get_weather_forecast", "get_current_weather",
        "get_account_balances", "get_transactions", "get_spending_summary",
        "get_net_worth_snapshot", "search_conversations",
        "get_recent_conversations",
    }

    # Low-stakes writes: auto-execute, notify user
    LOW_STAKES = {
        "create_todo",              # adding to backlog is low-stakes
        "update_todo",              # editing backlog metadata
        "complete_task",               # marking scheduled work done
        "complete_todo",            # completing a todo
        "create_todo_with_task",    # reminders / simple items
        "add_list_item", "complete_list_item", "bulk_complete_list_items",
        "create_list", "add_profile_fact", "update_profile_fact",
        "send_push_notification", "schedule_notification",
    }

    # High-stakes writes: always require confirmation
    HIGH_STAKES = {
        "create_tasks_batch",          # decomposing a todo into scheduled tasks
    }

    if tool_name in READ_ONLY:
        return ActionTier.READ_ONLY

    if tool_name in LOW_STAKES:
        return ActionTier.LOW_STAKES

    if tool_name in HIGH_STAKES:
        return ActionTier.HIGH_STAKES

    # Calendar writes: tier depends on whether assistant created the event
    if tool_name in ("update_calendar_event", "delete_calendar_event"):
        event = get_calendar_event(tool_args["event_id"])
        if event.created_by_assistant:
            return ActionTier.LOW_STAKES
        else:
            return ActionTier.HIGH_STAKES

    # create_calendar_event: low-stakes individually, but see batch handling (3.5)
    if tool_name == "create_calendar_event":
        return ActionTier.LOW_STAKES

    # Individual task creation: low-stakes if standalone,
    # but typically tasks are created via create_tasks_batch (high-stakes)
    if tool_name == "create_task":
        return ActionTier.LOW_STAKES

    # Default to medium
    return ActionTier.MEDIUM


def execute_with_classification(tool_name, tool_args, agent_context):
    """Middleware that checks classification before executing."""
    tier = classify_action(tool_name, tool_args)

    if tier == ActionTier.READ_ONLY:
        return execute_tool(tool_name, tool_args)

    if tier == ActionTier.LOW_STAKES:
        result = execute_tool(tool_name, tool_args)
        log_action(tool_name, tool_args, result)  # audit trail
        return result

    if tier in (ActionTier.MEDIUM, ActionTier.HIGH_STAKES):
        # Don't execute — return a confirmation request to the agent
        return ConfirmationRequired(
            tier=tier,
            tool_name=tool_name,
            tool_args=tool_args,
            description=describe_action(tool_name, tool_args),
        )
```

### 3.5 Batch Action Handling

The "plan my day" workflow is the primary case where multiple write operations need to be evaluated as a group. The flow is:

1. Claude calls `get_calendar_events("2026-03-25")` → read-only, auto-execute
2. Claude calls `get_todos(status="backlog", deadline_before="2026-04-01")` → read-only, auto-execute
3. Claude calls `find_free_time("2026-03-25")` → read-only, auto-execute
4. Claude calls `get_weather_forecast("2026-03-25")` → read-only, auto-execute
5. Claude proposes a plan (which todos to work on, when) → **this is the confirmation point**
6. After user approval, Claude calls `create_tasks_batch(todo_id, tasks[])` for each todo → high-stakes, but already confirmed

The key insight with the new model is that **`create_tasks_batch` is inherently high-stakes** — it creates multiple scheduled Tasks and calendar events at once. This makes batch detection simpler than before: the tool itself is the signal, not the number of calls.

**The system prompt reinforces this:**

> "When planning a user's day or decomposing a todo into scheduled tasks, first gather all the information you need (calendar, todo backlog, weather), then present the proposed plan to the user and wait for confirmation before creating any tasks or calendar events. Use `create_tasks_batch` only after the user approves the plan."

This makes the LLM's own reasoning the primary control mechanism, with the middleware's high-stakes classification of `create_tasks_batch` as the safety net.

---

## 4. Context Assembly

### 4.1 The Problem

The LLM's context window is finite and has cost implications. We can't dump the entire database into every request. But the agent needs enough context to reason well.

### 4.2 Strategy: Intent-Aware Context Loading

The context assembler runs before the LLM call and selects what to inject based on a quick classification of the user's message.

```
Context Assembly Pipeline
│
├── ALWAYS included:
│   ├── System prompt (identity, personality, rules)
│   ├── Current datetime + timezone
│   ├── User's core profile facts (name, location, waking hours, schedule prefs)
│   └── Last 3-5 conversation turns (for continuity)
│
├── CONDITIONALLY included based on intent signal:
│   │
│   ├── Planning/scheduling signals ("plan my day", "what should I do", "schedule"):
│   │   ├── Today's calendar events
│   │   ├── Today's scheduled Tasks (already on the calendar)
│   │   ├── Todo backlog (unscheduled todos with upcoming deadlines or high priority)
│   │   └── Today's hourly weather forecast
│   │
│   ├── Todo/backlog signals ("add a task", "todo", "my taxes", "I need to"):
│   │   ├── Todo backlog summary (titles, priorities, deadlines)
│   │   └── Related todo detail + tasks if a specific todo is referenced
│   │
│   ├── List signals ("grocery", "shopping list", "what do I need"):
│   │   └── The referenced list + items
│   │
│   ├── Financial signals ("spending", "net worth", "budget"):
│   │   └── Recent financial summary (injected or tool-accessible)
│   │
│   ├── Email signals ("any emails", "did I get", "bills"):
│   │   └── Recent unread/important email summaries
│   │
│   └── General/ambiguous:
│       └── Rely on tools — let the LLM decide what to fetch
│
└── NEVER included (always via tool call):
    ├── Full conversation history (use search_conversations tool)
    ├── Full financial transaction data (use get_transactions tool)
    └── Full email bodies (use get_email_detail tool)
```

**Implementation:** The intent classifier can be simple for MVP — keyword matching or a lightweight regex-based router. It doesn't need to be perfect because the LLM can always fall back to calling tools for missing context. The goal is to front-load the most likely needed context to reduce round-trips.

### 4.3 Conversation History Management

Conversation context within a session uses a **sliding window** approach:

- **Full context:** Last 10 turns (user + assistant messages) within the current session.
- **Summary context:** For longer sessions, older turns are summarized and the summary replaces the full messages.
- **Cross-session:** The agent does not automatically load prior sessions. It can use `search_conversations` or `get_recent_conversations` tools if the user references something from a past interaction.

---

## 5. Scheduler & Proactive Behaviors

### 5.1 Scheduler Architecture

APScheduler runs in-process alongside the FastAPI backend (or as a separate lightweight service in the same Docker Compose stack). It triggers proactive behaviors on defined schedules.

```
Scheduled Jobs
│
├── Morning Briefing
│   ├── Schedule: Daily at [user's preferred morning time, from profile]
│   ├── Action: Invoke the agent loop with a synthetic "system" message:
│   │   "Generate a morning briefing for the user. Check today's calendar,
│   │    pending tasks, upcoming deadlines, and weather. Summarize and
│   │    offer to plan the day."
│   └── Delivery: Push notification with summary + "Open to plan" deep link
│
├── Reminder Delivery
│   ├── Schedule: Per-task, based on due_time
│   ├── Action: Send push notification with reminder text
│   └── Note: These are simple notifications, not full agent invocations
│
├── Deadline Warning
│   ├── Schedule: Daily scan (e.g., 10am)
│   ├── Action: Query todos with deadlines in the next N days
│   │   that are still in backlog (no tasks scheduled yet).
│   │   If found, invoke agent to generate a nudge.
│   └── Delivery: Push notification
│
├── Key Date Alerts
│   ├── Schedule: Daily scan (e.g., 9am)
│   ├── Action: Check People records for upcoming birthdays/anniversaries
│   │   within a configurable horizon (e.g., 7 days)
│   └── Delivery: Push notification
│
├── Plaid Sync
│   ├── Schedule: Daily (e.g., 2am)
│   ├── Action: Pull latest transactions and balances from Plaid API,
│   │   update local financial tables, compute net worth snapshot
│   └── Delivery: None (background sync); anomaly detection can trigger a nudge
│
└── Gmail Poll (if not using push)
    ├── Schedule: Every 15 minutes
    ├── Action: Check for new emails since last poll
    └── Processing: Flag actionable emails for the agent's awareness
```

### 5.2 Proactive Agent Invocations vs. Simple Notifications

Not every scheduled job needs the full LLM. There are two tiers:

- **Simple notifications:** Reminder delivery, key date alerts. These are pre-formatted messages that go directly to the push notification service. No LLM call needed.
- **Agent invocations:** Morning briefing, deadline warnings, recommendation nudges. These trigger the full agent loop with a system-generated message, and the LLM produces the notification content.

This distinction matters for cost (LLM API calls) and latency. Simple notifications are instant and free; agent invocations take a few seconds and cost API tokens.

---

## 6. Data Layer

### 6.1 Database Schema Sketch

This is a starting point — the exact column types and constraints will be refined during implementation.

```sql
-- Profile facts (knowledge graph)
CREATE TABLE profile_facts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category TEXT NOT NULL,        -- identity, household, preferences, etc.
    key TEXT NOT NULL,              -- e.g., "dietary.likes", "partner.name"
    value JSONB NOT NULL,          -- flexible: string, object, array
    provenance TEXT NOT NULL,       -- seeded, explicit, inferred
    confidence FLOAT DEFAULT 1.0,
    evidence TEXT,                  -- for inferred facts
    superseded_by UUID REFERENCES profile_facts(id),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    last_confirmed_at TIMESTAMPTZ
);

-- People
CREATE TABLE people (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    relationship TEXT,
    description TEXT,
    contact_info JSONB,            -- {phone, email}
    key_dates JSONB,               -- {birthday, anniversary, custom[]}
    preferences JSONB,             -- {dietary, gift_ideas, etc.}
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Seed field edit history (tracks every version of every seeded field)
CREATE TABLE seed_field_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL,       -- 'profile' or 'person'
    entity_id UUID,                  -- null for profile, references people(id) for person
    field_key TEXT NOT NULL,          -- e.g., "hobbies", "living_situation", "dietary.likes"
    value TEXT NOT NULL,              -- full field content at this point in time
    edited_at TIMESTAMPTZ DEFAULT now()
);

-- Todos (Planning Layer — everything the user needs to accomplish)
CREATE TABLE todos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'backlog',   -- backlog, planning, active, completed, on_hold, abandoned
    priority TEXT DEFAULT 'medium',  -- critical, high, medium, low

    -- Scheduling (planning-level metadata)
    deadline TIMESTAMPTZ,            -- hard deadline
    target_date TIMESTAMPTZ,         -- soft target
    preferred_window TEXT,           -- morning, afternoon, evening, weekend
    estimated_duration_minutes INT,  -- total effort estimate
    energy_level TEXT,               -- low, medium, high
    location TEXT,                   -- grocery store, home office, downtown

    -- Hierarchy
    parent_todo_id UUID REFERENCES todos(id),

    -- Context
    tags TEXT[],
    dependencies UUID[],             -- todo IDs that must complete first
    notes TEXT,

    created_by TEXT DEFAULT 'user',  -- user, assistant
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Tasks (Execution Layer — scheduled blocks of work, always belong to a todo)
CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    todo_id UUID NOT NULL REFERENCES todos(id),
    title TEXT NOT NULL,
    description TEXT,

    -- Scheduling (execution-level: when exactly is this happening?)
    scheduled_start TIMESTAMPTZ,
    scheduled_end TIMESTAMPTZ,
    estimated_duration_minutes INT,
    actual_duration_minutes INT,     -- for learning/calibration
    calendar_event_id TEXT,          -- Google Calendar event ID, set when placed on calendar

    -- Status
    status TEXT DEFAULT 'scheduled', -- scheduled, in_progress, completed, deferred, cancelled

    -- Completion
    completed_at TIMESTAMPTZ,
    deferred_count INT DEFAULT 0,    -- how many times rescheduled
    completion_notes TEXT,

    -- Ordering within todo
    position INT,

    created_by TEXT DEFAULT 'assistant', -- typically created by the agent during scheduling
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Lists
CREATE TABLE lists (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    type TEXT DEFAULT 'custom',     -- grocery, travel, reading, shopping, custom
    description TEXT,
    status TEXT DEFAULT 'active',   -- active, archived
    tags TEXT[],
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE list_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    list_id UUID NOT NULL REFERENCES lists(id),
    name TEXT NOT NULL,
    status TEXT DEFAULT 'pending',  -- pending, done
    notes TEXT,
    position INT,
    added_by TEXT DEFAULT 'user',   -- user, assistant
    added_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ
);

-- Conversation log
CREATE TABLE interactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID,
    channel TEXT DEFAULT 'chat',    -- chat, voice, system
    user_message TEXT,
    parsed_intent TEXT,
    assistant_response JSONB,       -- {spoken_summary, structured_payload}
    actions_taken JSONB,            -- [{type, details}]
    feedback TEXT,                   -- thumbs_up, thumbs_down, correction text
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Financial data (synced from Plaid)
CREATE TABLE financial_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plaid_account_id TEXT UNIQUE,
    institution_name TEXT,
    account_type TEXT,              -- checking, savings, credit, investment, loan
    account_name TEXT,
    current_balance NUMERIC,
    available_balance NUMERIC,
    last_synced_at TIMESTAMPTZ
);

CREATE TABLE transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id UUID REFERENCES financial_accounts(id),
    plaid_transaction_id TEXT UNIQUE,
    date DATE NOT NULL,
    amount NUMERIC NOT NULL,
    merchant_name TEXT,
    category TEXT,                   -- Plaid-provided
    category_override TEXT,          -- user correction
    is_recurring BOOLEAN DEFAULT FALSE,
    notes TEXT,
    synced_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE net_worth_snapshots (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    date DATE NOT NULL UNIQUE,
    total_assets NUMERIC,
    total_liabilities NUMERIC,
    net_worth NUMERIC,
    breakdown JSONB,                 -- [{account_id, account_name, balance}]
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Scheduled notifications (for reminders)
CREATE TABLE scheduled_notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID REFERENCES tasks(id),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    send_at TIMESTAMPTZ NOT NULL,
    sent BOOLEAN DEFAULT FALSE,
    sent_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

### 6.2 Indexing Strategy

Key indexes for the most common query patterns:

```sql
-- Todos: backlog queries are the most common read pattern
CREATE INDEX idx_todos_status ON todos(status) WHERE status NOT IN ('completed', 'abandoned');
CREATE INDEX idx_todos_deadline ON todos(deadline) WHERE status IN ('backlog', 'planning', 'active');
CREATE INDEX idx_todos_priority ON todos(priority, status) WHERE status IN ('backlog', 'planning', 'active');
CREATE INDEX idx_todos_parent ON todos(parent_todo_id) WHERE parent_todo_id IS NOT NULL;

-- Tasks: scheduled work queries (what's on the calendar today/this week?)
CREATE INDEX idx_tasks_scheduled ON tasks(scheduled_start) WHERE status NOT IN ('completed', 'cancelled');
CREATE INDEX idx_tasks_status ON tasks(status) WHERE status != 'cancelled';
CREATE INDEX idx_tasks_todo ON tasks(todo_id);
CREATE INDEX idx_tasks_calendar ON tasks(calendar_event_id) WHERE calendar_event_id IS NOT NULL;

-- Profile facts: category + key lookups
CREATE INDEX idx_profile_category ON profile_facts(category);
CREATE INDEX idx_profile_key ON profile_facts(key);
CREATE INDEX idx_profile_active ON profile_facts(category, key) WHERE superseded_by IS NULL;

-- Seed field versions: latest version lookup per field
CREATE INDEX idx_seed_versions ON seed_field_versions(entity_type, entity_id, field_key, edited_at DESC);

-- Interactions: session-based retrieval + full-text search
CREATE INDEX idx_interactions_session ON interactions(session_id, created_at);
CREATE INDEX idx_interactions_created ON interactions(created_at DESC);

-- Transactions: date-range queries with category filtering
CREATE INDEX idx_transactions_date ON transactions(date DESC);
CREATE INDEX idx_transactions_category ON transactions(category, date);

-- Scheduled notifications: due for sending
CREATE INDEX idx_notifications_pending ON scheduled_notifications(send_at) WHERE sent = FALSE;

-- List items: list membership + status
CREATE INDEX idx_list_items_list ON list_items(list_id, status);
```

---

## 7. Frontend Architecture

### 7.1 Overview

The MVP frontend is a **chat interface** with support for structured response rendering. It's not just a text box — it needs to render timelines, lists, confirmation cards, and other structured payloads alongside conversational text.

### 7.2 Tech Stack

| Component | Choice | Notes |
|-----------|--------|-------|
| Framework | React 18+ | Component-based, large ecosystem |
| Build tool | Vite | Fast dev server, simple config |
| Styling | Tailwind CSS | Utility-first, fast iteration |
| State management | React Context + useReducer | Sufficient for a chat app; no Redux needed |
| Chat transport | WebSocket (via FastAPI) | Streaming responses, real-time updates |
| HTTP client | fetch (native) | For non-streaming API calls |

### 7.3 Key UI Components

```
App
├── ChatApp (primary view)
│   ├── MessageList
│   │   ├── UserMessage (simple text bubble)
│   │   └── AssistantMessage
│   │       ├── SpokenSummary (always present — the conversational text)
│   │       └── StructuredPayload (conditionally rendered based on type)
│   │           ├── DailyPlanView (timeline of events + proposed tasks)
│   │           ├── TodoBacklogView (filtered, sortable todo list with status)
│   │           ├── ListItemsView (grocery list, reading list, etc.)
│   │           ├── FinancialSummaryView (spending breakdown, net worth)
│   │           ├── WeatherView (hourly forecast, conditions)
│   │           └── ConfirmationCard (accept / reject / modify controls)
│   │
│   ├── InputBar
│   │   ├── TextInput (auto-expanding textarea)
│   │   └── SendButton
│   │
│   ├── FollowUpSuggestions (clickable chips below the latest message)
│   │
│   └── Sidebar (optional, Phase 2)
│       ├── Todo backlog (priorities, upcoming deadlines)
│       ├── Today's scheduled tasks
│       └── Quick actions
│
├── ProfilePage (accessible via navigation, not embedded in chat)
│   ├── IdentitySection (name, birthday, location, timezone, living situation)
│   ├── HouseholdSection (partner, pets, vehicles)
│   ├── PreferencesSection (dietary, schedule, communication)
│   ├── CareerSection (role, work arrangement, skills)
│   ├── AspirationsSection (life goals, free-text)
│   ├── ScheduleSection (waking hours, preferred work hours, errand preferences)
│   └── SaveButton → triggers biography ingestion on modified fields only
│
└── PeoplePage (accessible via navigation)
    ├── PersonList (filterable by relationship type)
    ├── AddPersonButton
    └── PersonDetailForm (opens on click or add)
        ├── BasicInfo (name, relationship type)
        ├── DescriptionSection (free-text)
        ├── ContactSection (phone, email)
        ├── KeyDatesSection (birthday, anniversary, custom dates)
        ├── PreferencesSection (dietary, gift ideas, etc.)
        ├── NotesSection (free-text)
        └── SaveButton → triggers biography ingestion on modified fields only
```

Both ProfilePage and PeoplePage share the same field-level edit history mechanism (see `seed_field_versions` table in Section 6.1). Edits are tracked per field, and only modified fields trigger fact ingestion.

### 7.4 Confirmation Flow

When the agent returns `confirmation_required: true`, the UI renders a `ConfirmationCard`:

```
┌─────────────────────────────────────────────────┐
│  📅 Daily Plan — March 25, 2026                  │
│                                                   │
│  Here's what I'd suggest for tomorrow:            │
│                                                   │
│  9:00 AM  ☀️ Morning run (weather: 55°, dry)      │
│  10:30 AM 📋 Tax prep — gather W-2s (45 min)     │
│  12:00 PM 🍽️ Lunch                                │
│  1:00 PM  📞 Team standup (existing event)        │
│  2:00 PM  📋 Grocery shopping (30 min)            │
│  3:00 PM  📋 Read Chapter 8 (60 min)             │
│                                                   │
│  ┌──────────┐ ┌──────────┐ ┌────────────────┐   │
│  │ ✅ Accept │ │ ✏️ Modify │ │ ❌ Skip today  │   │
│  └──────────┘ └──────────┘ └────────────────┘   │
└─────────────────────────────────────────────────┘
```

Clicking "Accept" sends a confirmation message to the agent, which then creates the Tasks and corresponding calendar events via `create_tasks_batch`. "Modify" opens an inline editor. "Skip" dismisses the plan — the Todos stay in the backlog for another day.

---

## 8. Deployment

### 8.1 Docker Compose Stack

```yaml
# docker-compose.yml (conceptual)
services:
  db:
    image: postgres:16
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: assistant
      POSTGRES_USER: assistant
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    restart: unless-stopped

  backend:
    build: ./backend
    depends_on:
      - db
    environment:
      DATABASE_URL: postgresql+asyncpg://assistant:${DB_PASSWORD}@db/assistant
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      GOOGLE_CREDENTIALS: ${GOOGLE_CREDENTIALS}
      PLAID_CLIENT_ID: ${PLAID_CLIENT_ID}
      PLAID_SECRET: ${PLAID_SECRET}
      NTFY_TOPIC: ${NTFY_TOPIC}
    ports:
      - "8000:8000"
    restart: unless-stopped

  frontend:
    build: ./frontend
    depends_on:
      - backend
    ports:
      - "3000:3000"
    restart: unless-stopped

  ntfy:  # optional: self-hosted push notification server
    image: binwiederhier/ntfy
    volumes:
      - ntfy-cache:/var/cache/ntfy
    ports:
      - "8080:80"
    restart: unless-stopped

volumes:
  pgdata:
  ntfy-cache:
```

### 8.2 Access Model

- All services bind to localhost or the Tailscale interface only.
- Frontend accessible at `https://assistant.tailnet-name.ts.net:3000` (or via Tailscale Serve/Funnel for HTTPS).
- No public-facing endpoints.
- API keys and secrets stored in `.env` file (gitignored) or Docker secrets.

### 8.3 Backup Strategy

- **Database:** Daily pg_dump to a local backup directory. Consider shipping to a second location (NAS, cloud bucket) for disaster recovery.
- **Configuration:** All config in version control (minus secrets).
- **Retention:** Indefinite, per requirements. Monitor disk usage over time.

---

## 9. Project Structure

```
assistant/
├── docker-compose.yml
├── .env                        # secrets (gitignored)
├── .env.example                # template for secrets
│
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml          # dependencies (or requirements.txt)
│   │
│   ├── app/
│   │   ├── main.py             # FastAPI app, WebSocket endpoint
│   │   ├── config.py           # Settings loaded from env
│   │   │
│   │   ├── agent/
│   │   │   ├── orchestrator.py # The main agent loop
│   │   │   ├── context.py      # Context assembly logic
│   │   │   ├── classifier.py   # Action classification middleware
│   │   │   └── response.py     # Response contract builder
│   │   │
│   │   ├── prompts/            # Version-controlled prompt templates
│   │   │   ├── system.yaml     # Main system prompt (active version)
│   │   │   ├── system_v1.yaml  # Historical versions for comparison
│   │   │   └── loader.py       # Prompt loading + context injection
│   │   │
│   │   ├── tools/
│   │   │   ├── base.py         # Base tool interface
│   │   │   ├── tasks.py        # Task CRUD tools
│   │   │   ├── todos.py        # Todo tools
│   │   │   ├── lists.py        # List tools
│   │   │   ├── profile.py      # Profile fact tools + biography ingestion pipeline
│   │   │   ├── people.py       # People CRUD + ingestion (shares pipeline with profile)
│   │   │   ├── calendar.py     # Google Calendar tools
│   │   │   ├── gmail.py        # Gmail tools
│   │   │   ├── weather.py      # Weather API tools
│   │   │   ├── finance.py      # Plaid / financial tools
│   │   │   └── notifications.py # Push notification tools
│   │   │
│   │   ├── models/
│   │   │   ├── database.py     # SQLAlchemy models / async engine
│   │   │   └── schemas.py      # Pydantic schemas for API + tool I/O
│   │   │
│   │   ├── integrations/
│   │   │   ├── anthropic.py    # Claude API client wrapper
│   │   │   ├── google.py       # Google Calendar + Gmail OAuth + API
│   │   │   ├── plaid.py        # Plaid API client
│   │   │   ├── weather.py      # Weather API client
│   │   │   └── ntfy.py         # ntfy push notification client
│   │   │
│   │   ├── scheduler/
│   │   │   ├── jobs.py         # Job definitions (morning briefing, etc.)
│   │   │   └── engine.py       # APScheduler setup and lifecycle
│   │   │
│   │   └── db/
│   │       └── migrations/     # Alembic migrations
│   │
│   └── tests/
│       ├── test_agent.py
│       ├── test_tools.py
│       └── test_classifier.py
│
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── chat/
│   │   │   │   ├── ChatWindow.tsx
│   │   │   │   ├── MessageList.tsx
│   │   │   │   ├── UserMessage.tsx
│   │   │   │   ├── AssistantMessage.tsx
│   │   │   │   ├── ConfirmationCard.tsx
│   │   │   │   ├── InputBar.tsx
│   │   │   │   └── FollowUpSuggestions.tsx
│   │   │   ├── payloads/
│   │   │   │   ├── DailyPlanView.tsx
│   │   │   │   ├── TodoBacklogView.tsx
│   │   │   │   ├── ListItemsView.tsx
│   │   │   │   ├── FinancialSummaryView.tsx
│   │   │   │   └── WeatherView.tsx
│   │   │   └── profile/
│   │   │       ├── ProfilePage.tsx       # Main profile page layout
│   │   │       ├── IdentitySection.tsx   # Name, birthday, location, timezone
│   │   │       ├── HouseholdSection.tsx  # Partner, pets, vehicles
│   │   │       ├── PreferencesSection.tsx # Dietary, schedule, communication
│   │   │       ├── CareerSection.tsx     # Role, work arrangement
│   │   │       └── AspirationsSection.tsx # Life goals, free-text
│   │   │   └── people/
│   │   │       ├── PeoplePage.tsx        # People list + add button
│   │   │       ├── PersonList.tsx        # Filterable list of people
│   │   │       └── PersonDetailForm.tsx  # Per-person edit form
│   │   ├── hooks/
│   │   │   ├── useChat.ts      # WebSocket connection + message state
│   │   │   └── useConfirmation.ts
│   │   ├── types/
│   │   │   └── index.ts        # TypeScript types matching response contract
│   │   └── utils/
│   │       └── api.ts          # HTTP helpers for non-streaming calls
│   └── public/
│
└── docs/
    ├── requirements.md          # Product requirements document
    ├── architecture.md          # This document
    └── setup.md                 # Local dev setup guide
```

---

## 10. Implementation Sequence

A suggested order for building this out, designed so each step produces something testable and incrementally useful.

### Step 1: Foundation (Backend Shell + Database + Profile + People)
- Set up the project structure and Docker Compose (Postgres with pgvector + backend)
- Define SQLAlchemy models and Pydantic schemas for all data objects (Todos, Tasks, Lists, ProfileFacts, People, SeedFieldVersions, etc.)
- Run Alembic migrations to create the schema
- Build the biography ingestion pipeline (backend): field-level diff detection via SeedFieldVersions → fact generation → conflict resolution → ProfileFact upsert
- Build the Profile Page UI (frontend) with structured form sections
- Build the People Page UI (frontend) with list view + detail forms, sharing the same ingestion pipeline
- Wire save → version → ingest for both Profile and People; verify ProfileFacts are created and versioned correctly
- Set up the prompts directory with the initial system prompt template

### Step 2: Agent Core (Tool-Use Loop)
- Implement the Anthropic API client wrapper
- Define tool schemas for internal tools (todos, tasks, lists, profile)
- Build the agent orchestrator: system prompt → LLM call → tool execution → response
- Build the response contract builder (spoken_summary + structured_payload)
- Test via command line or simple HTTP endpoint (no frontend yet)
- Key test: "I need to pick up the dry cleaning" → Todo created in backlog

### Step 3: Chat Interface (Frontend MVP)
- Scaffold React + Vite frontend
- Build the chat UI: message list, input bar, user/assistant message rendering
- Implement WebSocket connection for streaming
- Render spoken_summary as conversational text
- Test the full loop: type a message → agent processes → response rendered

### Step 4: Calendar Integration
- Implement Google Calendar OAuth flow
- Build calendar tools (get events, create event, update, delete, find free time)
- Implement calendar event tagging (assistant-created marker + color)
- Wire into the agent tool layer
- Test: "What's on my calendar today?" → shows events
- Test: Create a Todo + Task with calendar event for a simple reminder

### Step 5: Action Classification + Confirmation + Daily Planning
- Implement the classification middleware
- Build the ConfirmationCard frontend component
- Wire up the accept/reject/modify flow
- Implement the daily planning workflow (scan backlog → propose tasks → confirm → create_tasks_batch)
- Test: "Plan my day" → agent reads backlog + calendar → proposes plan → accept → Tasks + calendar events created
- This is the milestone where the core Todo→Task→Calendar loop works end-to-end

### Step 6: Gmail Integration
- Implement Gmail OAuth (shares Google OAuth with Calendar)
- Build Gmail tools (recent emails, email detail, search)
- Wire into agent + context assembly
- Test: "Any important emails today?" → summarized email highlights

### Step 7: Notifications + Reminders
- Set up ntfy (self-hosted) or Pushover
- Build notification tools (send, schedule)
- Implement the scheduled_notifications table + delivery job
- Test: "Remind me to call the vet at 3pm" → Todo + Task created simultaneously → push notification at 3pm

### Step 8: Weather + Financial
- Integrate weather API (hourly forecast)
- Integrate Plaid (account sync, transactions, net worth)
- Build financial tools and schedule daily Plaid sync
- Wire weather into daily planning (agent can now factor in rain, temperature for outdoor scheduling)
- Test: "What's the weather this afternoon?" → hourly forecast
- Test: "How much did we spend on dining this month?" → categorized breakdown

### Step 9: Scheduler + Proactive Behaviors
- Set up APScheduler with job definitions
- Implement morning briefing job (agent invocation)
- Implement deadline warning scanner (todos in backlog with approaching deadlines)
- Implement key date alerts (birthdays, anniversaries from People records)
- Test: Receive morning push notification with daily summary

### Step 10: Structured Response Rendering
- Build frontend components for structured payloads (DailyPlanView, TodoBacklogView, etc.)
- Implement follow-up suggestion chips
- Polish the chat UI for a daily-driver experience
