# Personal Assistant

An AI-powered personal assistant with a chat interface, backed by Claude and integrated with Google Calendar and Gmail. It manages todos, tasks, lists, a user profile, and a people directory — all through natural language conversation. It can plan your day, set reminders with push notifications, read your email, and proactively reach out with morning briefings and deadline warnings.

The agent uses adaptive thinking (extended thinking with configurable effort), intent-based tool filtering, vector search over the knowledge base, and full message chain replay for multi-turn context fidelity.

## Architecture Overview

The app is a **React frontend** talking to a **FastAPI backend** through an nginx reverse proxy. The backend's core is an **agentic loop**: when a user sends a chat message, the backend assembles minimal context (datetime, timezone, user name), selects only the tools relevant to the detected intent, calls Claude with adaptive thinking, executes any tool calls Claude makes (creating todos, querying the calendar, searching the knowledge base via vector embeddings, etc.), and returns a structured response. Everything persists in **PostgreSQL** with **pgvector** for embedding-based search.

```
                    +-----------+
                    |  Browser  |
                    +-----+-----+
                          |
                    +-----v-----+
                    |   nginx   |  (reverse proxy, SPA fallback)
                    +-----+-----+
                          |
              +-----------+-----------+
              |  /api/*               |  /*
              v                       v
        +-----+------+        +------+------+
        |   FastAPI   |        |  React SPA  |
        |  (backend)  |        |  (frontend) |
        +-----+------+        +-------------+
              |
   +----------+----------+----------+----------+
   |          |          |          |          |
   v          v          v          v          v
+--+------+ +-+------+ ++------+ +-+------+ +-+------+
|PostgreSQL| |Google  | |Gmail  | | ntfy   | |OpenAI  |
|+pgvector | |Calendar| |(read  | |(push   | |Embed-  |
|(shared)  | |(OAuth) | | only) | | notifs)| |dings   |
+----------+ +--------+ +-------+ +--------+ +--------+
```

## How a Chat Message Flows

This is the central path through the codebase. Understanding this flow is understanding the app.

1. **User types a message** in the React chat UI (`ChatPage` -> `InputBar`).
2. **`useChat` hook** sends a POST to `/api/chat/` with the message and session ID.
3. **nginx** proxies `/api/*` to the FastAPI backend container.
4. **`routers/chat.py`** receives the request and calls `run_agent_loop()`.
5. **`orchestrator.py`** (the core loop):
   - **Context assembly** (`context.py`): Detects intents from keywords in the message (e.g., "plan my day" triggers `planning` intent). Resolves the user's timezone and name from profile facts. No data is pre-loaded — the agent fetches everything it needs via tool calls.
   - **Tool selection** (`registry.py`): Only tools whose category matches the detected intents are included in the LLM call. When no intents are detected, a curated set of general-purpose read-only tools is sent instead of the full registry.
   - **Prompt rendering** (`prompts/loader.py`): Injects the assembled context into a Jinja2 template (`system_v1.yaml`) to build the system prompt — behavioral instructions only, no data.
   - **Message building** (`context.py`): Replays the full message chain (including tool calls and results) from prior turns when available, falling back to spoken_summary for older interactions. Then appends the new user message.
   - **Tool-use loop** (up to 10 rounds): Calls Claude Sonnet 4.6 with adaptive thinking via `client.py`. If Claude returns `tool_use`, the orchestrator looks up the tool in `TOOL_REGISTRY`, checks its **action tier** (read-only / low-stakes / high-stakes), executes it, and feeds the result back to Claude for the next round. If a tool is **HIGH_STAKES**, the loop halts and returns a confirmation request to the frontend.
   - **Response parsing**: Extracts Claude's final JSON response (`spoken_summary`, `structured_payload`, `follow_up_suggestions`).
   - **Logging**: Persists the interaction (with full message chain) to the `interactions` table. Each LLM round is also logged to the `llm_calls` table with token counts and model metadata.
6. **Frontend** receives the `ChatResponse`, renders the `AssistantMessage` with the spoken summary, collapsible action list, optional confirmation card, and follow-up suggestion chips.

## Daily Planning Flow

This is the most complex workflow, involving multiple tool calls and a confirmation step.

1. User says "plan my day" (or similar).
2. Agent detects `planning` intent, loads today's calendar, tasks, and todo backlog into context.
3. Agent calls tools in parallel: `get_calendar_events`, `get_tasks`, `get_todos`, `find_free_time`.
4. Agent reasons about schedule and proposes a plan with specific time slots for each todo.
5. Agent stores the plan payload (with todo IDs and time slots) in `structured_payload` and returns it with a confirmation prompt.
6. User clicks "Lock it in" — frontend sends the confirmation back.
7. **Deterministic execution** (`orchestrator._execute_confirmed_action`): Instead of re-running the LLM, the orchestrator looks up the cached `execute_daily_plan` tool call from session history and executes it directly. This avoids non-deterministic re-planning.
8. `execute_daily_plan` (`services/planning.py`) atomically creates tasks for each todo and optionally creates Google Calendar events.

## Reminder Flow

1. User says "remind me to call the vet at 3pm".
2. Agent calls `set_reminder` tool (LOW_STAKES, auto-executes).
3. Tool creates a todo + task + `scheduled_notifications` row with `send_at` set to 3pm.
4. APScheduler's notification poller (runs every 30s) picks up the notification when `send_at` passes.
5. Sends a push notification to the user's phone via ntfy.

## Proactive Behaviors

The backend runs three scheduled jobs via APScheduler (cron triggers):

- **Morning briefing** (daily, configurable time): Invokes the full agent loop with a synthetic message asking for a day summary. The LLM checks calendar, tasks, deadlines, and emails, then the response is sent as a push notification.
- **Deadline warnings** (daily at 10am): Scans for backlog todos with deadlines within 3 days that have no tasks scheduled. If found, the agent generates a nudge sent via push.
- **Key date alerts** (daily at 9am): Checks People records for upcoming birthdays/anniversaries within 7 days. Sends a simple notification (no LLM call needed).

## How the Profile/People Pages Work

These are separate from the chat flow -- they're direct CRUD pages.

1. **Profile page** (`ProfilePage.tsx`): Loads the current profile via `GET /api/profile/`, renders section-specific form components (Identity, Household, Preferences, etc.). On save, POSTs all fields to `POST /api/profile/`.
2. **Backend profile save** (`routers/profile.py` -> `services/profile.py` -> `services/ingestion.py`): The **ingestion pipeline** diffs field values against `SeedFieldVersions` (a version history table), generates `ProfileFact` records using `field_mappings.py`, and handles conflict resolution by superseding old facts. This is how form data becomes the structured facts that the agent reads during chat. After ingestion, embeddings are generated for each fact via `services/embeddings.py` (OpenAI `text-embedding-3-small`) and stored alongside the fact for vector search.
3. **People pages** (`PeoplePage.tsx`, `PersonDetailForm.tsx`): Standard CRUD for contacts. Creating/updating a person also triggers the ingestion pipeline to generate profile facts about that person, with embeddings computed for vector search.

The agent accesses all knowledge through a single `search_profile` tool that performs vector similarity search (pgvector) over profile facts and people records, returning the most relevant results for any query about the user's life, contacts, or preferences.

## Project Structure

### Backend (`backend/`)

```
app/
  main.py                    # FastAPI app, CORS, router registration, APScheduler startup
  config.py                  # Settings from env vars (API keys, OAuth, ntfy, embeddings, job schedules)
  database.py                # SQLAlchemy async engine, session factory, session maker for jobs

  models/
    tables.py                # All SQLAlchemy ORM models (14 tables)

  routers/                   # HTTP endpoints
    chat.py                  #   POST /api/chat/ -- the agent endpoint
    profile.py               #   GET/POST /api/profile/ -- profile CRUD
    people.py                #   CRUD /api/people/ -- contacts directory
    auth.py                  #   Google OAuth2 flow (Calendar + Gmail scopes)
    todos.py                 #   GET /api/todos/ -- todo list for UI
    planning.py              #   GET/POST /api/planning/ -- daily plans for UI
    health.py                #   GET /api/health

  agent/                     # The AI agent subsystem
    orchestrator.py          #   The core loop: context -> LLM -> tools -> response
    context.py               #   Intent detection + minimal context assembly (no data pre-loading)
    client.py                #   Anthropic API client wrapper (adaptive thinking support)

    tools/                   # Tool definitions (one file per domain, each tagged with a category)
      registry.py            #   Global tool registry, action tier classification, intent-based filtering
      todo_tools.py          #   Todo CRUD + scheduling tools (create, complete, reschedule, cancel, batch)
      list_tools.py          #   List/item management tools
      calendar_tools.py      #   Google Calendar tools
      gmail_tools.py         #   Gmail read-only tools (list, detail, search)
      planning_tools.py      #   execute_daily_plan (HIGH_STAKES)
      reminder_tools.py      #   set_reminder (LOW_STAKES, creates todo + notification)
      profile_tools.py       #   Profile fact + people lookup tools (vector search via search_profile)
      conversation_tools.py  #   Conversation search tools

  services/                  # Business logic layer (called by tools AND routers)
    todos.py                 #   Todo CRUD, scheduling, calendar sync, parent status cascading
    lists.py                 #   List + ListItem CRUD
    planning.py              #   Daily plan execution (creates child todos with calendar events)
    google_calendar.py       #   Google Calendar API wrapper (async, OAuth token management)
    gmail.py                 #   Gmail API wrapper (read-only, shares OAuth with Calendar)
    notifications.py         #   Notification scheduling, ntfy delivery, APScheduler poll loop
    proactive.py             #   Agent invocation helper for scheduler-triggered jobs
    scheduled_jobs.py        #   Cron job definitions (morning briefing, deadline warnings, key dates)
    profile.py               #   Profile retrieval and save
    people.py                #   People CRUD
    conversations.py         #   Interaction logging, search, and LLM call tracking
    ingestion.py             #   Form-data-to-ProfileFact pipeline
    field_mappings.py        #   Maps form field keys to fact category/key patterns
    embeddings.py            #   OpenAI embedding generation + text serializers for vector search
    timezone.py              #   Centralized timezone resolution and datetime utilities
    daily_plans.py           #   Daily plan CRUD for the planning page
    serialization.py         #   SQLAlchemy model -> JSON-safe dict

  prompts/
    loader.py                #   YAML + Jinja2 prompt template loader
    system_v1.yaml           #   The system prompt template

  schemas/                   # Pydantic request/response models
    agent.py                 #   ChatRequest, ChatResponse, ActionTaken, ConfirmationRequired
    profile.py               #   ProfileSaveRequest, ProfileFactResponse
    people.py                #   PersonCreate, PersonUpdate, PersonResponse
    common.py                #   SuccessResponse, ErrorResponse
```

### Frontend (`frontend/`)

```
src/
  main.tsx                   # React entry point (BrowserRouter)
  App.tsx                    # Top-level routes: /, /profile, /people, /todos, /planning

  hooks/
    useChat.ts               # Chat state management, message sending, confirmation flow

  utils/
    api.ts                   # Generic fetch wrapper for /api/*
    id.ts                    # UUID v4 generator (works over plain HTTP)

  types/
    chat.ts                  # ChatMessage, ChatRequest, ChatResponse, etc.
    profile.ts               # ProfileData, Pet, Vehicle, Role
    people.ts                # Person
    todos.ts                 # Todo, ReviewTodo interfaces
    payloads.ts              # DailyPlan, DailySchedule structured payload types

  components/
    layout/
      NavBar.tsx             # Top nav: Chat | Profile | People | Todos | Planning

    chat/
      ChatPage.tsx           # Page shell: MessageList + InputBar
      MessageList.tsx        # Message rendering, welcome state, loading/error
      InputBar.tsx           # Textarea with Enter-to-send
      AssistantMessage.tsx   # Spoken summary + collapsible actions + confirmation + chips
      UserMessage.tsx        # Blue bubble
      ConfirmationCard.tsx   # Approve/Reject for high-stakes actions
      FollowUpChips.tsx      # Clickable suggestion pills

    profile/
      ProfilePage.tsx        # Loads/saves profile, renders section components
      Section.tsx            # Collapsible card wrapper + shared CSS classes
      TagInput.tsx           # Tag pill input (Enter/comma to add, Backspace to remove)
      IdentitySection.tsx    # Name, DOB, location, timezone, living situation
      HouseholdSection.tsx   # Partner, pets, vehicles
      PreferencesSection.tsx # Dietary likes/dislikes, communication style
      CareerSection.tsx      # Roles, professional skills
      HobbiesSection.tsx     # Hobbies, interests
      AspirationsSection.tsx # Aspirations
      ScheduleSection.tsx    # Waking hours, work hours, errand time

    people/
      PeoplePage.tsx         # List all people, filter by relationship type
      PersonList.tsx         # Card grid linking to detail forms
      PersonDetailForm.tsx   # Create/edit/delete a person

    todos/
      TodosPage.tsx          # Table view with status/priority/schedule filters

    planning/
      PlanningPage.tsx       # Daily plan view and management

    payloads/
      PayloadRenderer.tsx    # Routes structured_payload to type-specific components
      DailyPlanView.tsx      # Renders daily plan payload with time slots and confirmation
      DailyScheduleView.tsx  # Renders schedule overview payload
```

### Infrastructure

```
docker-compose.yml           # Three services: backend, frontend, ntfy (push notifications)
backend/Dockerfile           # Python 3.12, uvicorn
frontend/Dockerfile          # Node build -> nginx static serving
frontend/nginx.conf          # /api/* -> backend:8000, /* -> SPA fallback
```

## Key Design Decisions

- **Tool tiers** (read-only / low-stakes / high-stakes): The agent auto-executes read-only and low-stakes tools. High-stakes tools (batch task creation, calendar deletion) pause the loop and return a confirmation card to the user. This is the "graduated autonomy" principle.
- **Deterministic confirmation execution**: When a user approves a HIGH_STAKES action, the orchestrator replays the cached tool call from session history instead of re-running the LLM. This avoids non-deterministic behavior where the LLM might produce a different plan on the second pass.
- **Intent-based tool filtering**: Rather than sending all 35+ tool schemas on every call, the registry filters tools by category based on detected intents. Unmatched intents get a curated set of general-purpose read-only tools. This keeps the prompt focused and token-efficient.
- **Behavioral-only system prompt**: The system prompt contains only behavioral instructions and current datetime — no pre-loaded data. The agent fetches all data it needs (tasks, calendar, todos, profile, emails) via tool calls, which lets it decide what's relevant.
- **ProfileFacts as the knowledge model**: All user knowledge (from the profile form, people directory, and agent conversations) is stored as versioned `ProfileFact` rows with a `superseded_by` chain and vector embeddings. This gives the agent a unified, semantically searchable knowledge base with full edit history. People records also have embeddings for vector search.
- **Ingestion pipeline**: When profile/people forms are saved, changes flow through a diff-detection + fact-generation pipeline rather than direct DB updates. This ensures the agent's knowledge base stays in sync with form edits.
- **Full message chain replay**: Each chat session has a UUID. When replaying conversation history, the full message chain (user messages, tool calls, tool results, and assistant responses) is stored and replayed verbatim, preserving the exact LLM context from prior turns. Older interactions without a stored chain fall back to spoken_summary.
- **LLM call logging**: Every round of the tool-use loop is logged to the `llm_calls` table with token counts, model ID, stop reason, and the number of tool calls. This enables cost tracking and debugging.
- **Adaptive thinking**: The LLM is called with extended thinking enabled (`adaptive` mode, `medium` effort), allowing Claude to reason through complex multi-step tool orchestration before responding.
- **Centralized timezone handling**: All timezone resolution goes through `services/timezone.py`, which reads the user's timezone from profile facts and falls back to a configured default. This eliminated a class of UTC-based scheduling bugs.
- **Structured payload rendering**: The frontend renders `structured_payload` objects (daily plans, schedule overviews) using type-specific components via `PayloadRenderer`, providing rich visual representations of agent outputs beyond plain text.
- **Two-tier proactive notifications**: Simple notifications (birthday alerts) go directly to ntfy with no LLM call. Agent invocations (morning briefings, deadline nudges) run the full agent loop with a synthetic message so the LLM can use tools and produce contextual content.
- **Shared Google OAuth**: Calendar and Gmail share a single OAuth credential row. Adding a new Google scope just requires updating the `SCOPES` list and re-authorizing once.

## Data Model

The 14 tables in `models/tables.py`:

| Table | Purpose |
|-------|---------|
| `profile_facts` | User knowledge store (versioned, with supersession chain + vector embeddings) |
| `seed_field_versions` | Tracks form field edit history for diff detection |
| `people` | Contacts directory (with key_dates for birthday/anniversary alerts + vector embeddings) |
| `todos` | Unified productivity items (backlog or scheduled, with optional calendar sync and parent/child hierarchy) |
| `daily_plans` | Saved daily plans from the planning page |
| `lists` | Named lists (grocery, packing, custom) |
| `list_items` | Items within lists |
| `interactions` | Conversation log (user message, intent, response, channel, actions, message_chain) |
| `llm_calls` | Per-round LLM call metadata (tokens, model, stop reason, tool call count) |
| `financial_accounts` | (Placeholder) Bank/investment accounts |
| `transactions` | (Placeholder) Financial transactions |
| `net_worth_snapshots` | (Placeholder) Point-in-time net worth |
| `credentials` | OAuth tokens (Google Calendar + Gmail) |
| `scheduled_notifications` | Push notification queue (linked to tasks, polled by APScheduler) |
