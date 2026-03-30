# Personal Assistant

An AI-powered personal assistant with a chat interface, backed by Claude and integrated with Google Calendar and Gmail. It manages todos, tasks, lists, a user profile, and a people directory — all through natural language conversation. It can plan your day, set reminders with push notifications, read your email, and proactively reach out with morning briefings and deadline warnings.

## Architecture Overview

The app is a **React frontend** talking to a **FastAPI backend** through an nginx reverse proxy. The backend's core is an **agentic loop**: when a user sends a chat message, the backend assembles context, calls Claude with tool definitions, executes any tool calls Claude makes (creating todos, querying the calendar, etc.), and returns a structured response. Everything persists in **PostgreSQL**.

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
   +----------+----------+----------+
   |          |          |          |
   v          v          v          v
+--+------+ +-+------+ ++------+ +-+------+
|PostgreSQL| |Google  | |Gmail  | | ntfy   |
|(shared)  | |Calendar| |(read  | |(push   |
|          | |(OAuth) | | only) | | notifs)|
+----------+ +--------+ +-------+ +--------+
```

## How a Chat Message Flows

This is the central path through the codebase. Understanding this flow is understanding the app.

1. **User types a message** in the React chat UI (`ChatPage` -> `InputBar`).
2. **`useChat` hook** sends a POST to `/api/chat/` with the message and session ID.
3. **nginx** proxies `/api/*` to the FastAPI backend container.
4. **`routers/chat.py`** receives the request and calls `run_agent_loop()`.
5. **`orchestrator.py`** (the core loop):
   - **Context assembly** (`context.py`): Detects intents from keywords in the message (e.g., "plan my day" triggers `planning` intent). Loads the user's profile facts, and conditionally loads today's tasks, calendar events, todo backlog, and lists based on detected intents.
   - **Prompt rendering** (`prompts/loader.py`): Injects the assembled context into a Jinja2 template (`system_v1.yaml`) to build the system prompt.
   - **Message building** (`context.py`): Prepends recent conversation history from the session, then appends the new user message.
   - **Tool-use loop** (up to 10 rounds): Calls Claude via `client.py`. If Claude returns `tool_use`, the orchestrator looks up the tool in `TOOL_REGISTRY`, checks its **action tier** (read-only / low-stakes / high-stakes), executes it, and feeds the result back to Claude for the next round. If a tool is **HIGH_STAKES**, the loop halts and returns a confirmation request to the frontend.
   - **Response parsing**: Extracts Claude's final JSON response (`spoken_summary`, `structured_payload`, `follow_up_suggestions`).
   - **Logging**: Persists the interaction to the `interactions` table.
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
2. **Backend profile save** (`routers/profile.py` -> `services/profile.py` -> `services/ingestion.py`): The **ingestion pipeline** diffs field values against `SeedFieldVersions` (a version history table), generates `ProfileFact` records using `field_mappings.py`, and handles conflict resolution by superseding old facts. This is how form data becomes the structured facts that the agent reads during chat.
3. **People pages** (`PeoplePage.tsx`, `PersonDetailForm.tsx`): Standard CRUD for contacts. Creating/updating a person also triggers the ingestion pipeline to generate profile facts about that person.

## Project Structure

### Backend (`backend/`)

```
app/
  main.py                    # FastAPI app, CORS, router registration, APScheduler startup
  config.py                  # Settings from env vars (API keys, OAuth, ntfy, job schedules)
  database.py                # SQLAlchemy async engine, session factory, session maker for jobs

  models/
    tables.py                # All SQLAlchemy ORM models (13 tables)

  routers/                   # HTTP endpoints
    chat.py                  #   POST /api/chat/ -- the agent endpoint
    profile.py               #   GET/POST /api/profile/ -- profile CRUD
    people.py                #   CRUD /api/people/ -- contacts directory
    auth.py                  #   Google OAuth2 flow (Calendar + Gmail scopes)
    todos.py                 #   GET /api/todos/ -- todo list for UI
    tasks.py                 #   GET /api/tasks/ -- task list for UI
    health.py                #   GET /api/health

  agent/                     # The AI agent subsystem
    orchestrator.py          #   The core loop: context -> LLM -> tools -> response
    context.py               #   Intent detection + context assembly for the system prompt
    client.py                #   Anthropic API client wrapper

    tools/                   # Tool definitions (one file per domain)
      registry.py            #   Global tool registry, action tier classification
      todo_tools.py          #   Todo CRUD tools (including create_todo_with_task)
      task_tools.py          #   Task scheduling tools
      list_tools.py          #   List/item management tools
      calendar_tools.py      #   Google Calendar tools
      gmail_tools.py         #   Gmail read-only tools (list, detail, search)
      planning_tools.py      #   execute_daily_plan (HIGH_STAKES)
      reminder_tools.py      #   set_reminder (LOW_STAKES, creates todo + task + notification)
      profile_tools.py       #   Profile fact + people lookup tools
      conversation_tools.py  #   Conversation search tools

  services/                  # Business logic layer (called by tools AND routers)
    todos.py                 #   Todo CRUD, completion cascading, create_todo_with_task
    tasks.py                 #   Task CRUD, batch creation, auto-complete parent todo
    lists.py                 #   List + ListItem CRUD
    planning.py              #   Daily plan execution (atomic task + calendar event creation)
    google_calendar.py       #   Google Calendar API wrapper (async, OAuth token management)
    gmail.py                 #   Gmail API wrapper (read-only, shares OAuth with Calendar)
    notifications.py         #   Notification scheduling, ntfy delivery, APScheduler poll loop
    proactive.py             #   Agent invocation helper for scheduler-triggered jobs
    scheduled_jobs.py        #   Cron job definitions (morning briefing, deadline warnings, key dates)
    profile.py               #   Profile retrieval and save
    people.py                #   People CRUD
    conversations.py         #   Interaction logging and search
    ingestion.py             #   Form-data-to-ProfileFact pipeline
    field_mappings.py        #   Maps form field keys to fact category/key patterns
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
  App.tsx                    # Top-level routes: /, /profile, /people, /todos, /tasks

  hooks/
    useChat.ts               # Chat state management, message sending, confirmation flow

  utils/
    api.ts                   # Generic fetch wrapper for /api/*
    id.ts                    # UUID v4 generator (works over plain HTTP)

  types/
    chat.ts                  # ChatMessage, ChatRequest, ChatResponse, etc.
    profile.ts               # ProfileData, Pet, Vehicle, Role
    people.ts                # Person
    todos.ts                 # Todo, Task interfaces

  components/
    layout/
      NavBar.tsx             # Top nav: Chat | Profile | People | Todos | Tasks

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
      TodosPage.tsx          # Table view with status/priority filters

    tasks/
      TasksPage.tsx          # Table view with status filters and schedule times
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
- **Intent-aware context loading**: Rather than always loading everything into the system prompt, the context assembler detects what the message is about and only loads relevant data. This keeps the prompt focused and token-efficient.
- **ProfileFacts as the knowledge model**: All user knowledge (from the profile form, people directory, and agent conversations) is stored as versioned `ProfileFact` rows with a `superseded_by` chain. This gives the agent a unified, queryable knowledge base with full edit history.
- **Ingestion pipeline**: When profile/people forms are saved, changes flow through a diff-detection + fact-generation pipeline rather than direct DB updates. This ensures the agent's knowledge base stays in sync with form edits.
- **Session-based conversations**: Each chat session has a UUID. Conversation history is loaded from the `interactions` table and prepended to messages for multi-turn context. `structured_payload` (e.g., a daily plan with todo IDs) is included in history so follow-up turns can reference it.
- **Two-tier proactive notifications**: Simple notifications (birthday alerts) go directly to ntfy with no LLM call. Agent invocations (morning briefings, deadline nudges) run the full agent loop with a synthetic message so the LLM can use tools and produce contextual content.
- **Shared Google OAuth**: Calendar and Gmail share a single OAuth credential row. Adding a new Google scope just requires updating the `SCOPES` list and re-authorizing once.

## Data Model

The 13 tables in `models/tables.py`:

| Table | Purpose |
|-------|---------|
| `profile_facts` | User knowledge store (versioned, with supersession chain) |
| `seed_field_versions` | Tracks form field edit history for diff detection |
| `people` | Contacts directory (with key_dates for birthday/anniversary alerts) |
| `todos` | Backlog items (title, priority, deadline, tags, hierarchy) |
| `tasks` | Scheduled work blocks linked to todos |
| `lists` | Named lists (grocery, packing, custom) |
| `list_items` | Items within lists |
| `interactions` | Conversation log (user message, intent, response, channel, actions) |
| `financial_accounts` | (Placeholder) Bank/investment accounts |
| `transactions` | (Placeholder) Financial transactions |
| `net_worth_snapshots` | (Placeholder) Point-in-time net worth |
| `credentials` | OAuth tokens (Google Calendar + Gmail) |
| `scheduled_notifications` | Push notification queue (linked to tasks, polled by APScheduler) |
