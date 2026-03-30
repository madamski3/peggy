# AI Personal Assistant — Product Requirements Document

## 1. Vision & North Star

An AI-powered personal assistant that **reduces cognitive overhead** in daily life — managing time, tasks, information, and household logistics so the user can focus on what matters. The assistant should feel like a sharp, proactive chief of staff: it anticipates needs, takes initiative on routine matters, asks for input on important decisions, and gets smarter over time.

**Design Mantra:** *Do the thinking for me, but keep me in the loop.*

---

## 2. Core Design Principles

Derived from user priority ranking and stated preferences:

| # | Principle | Implication |
|---|-----------|-------------|
| 1 | **Bias toward action** | The assistant should default to *doing* things, not just suggesting. If it can resolve something without asking, it should — then report what it did. |
| 2 | **Compound intelligence** | Every interaction is a learning opportunity. The assistant should get measurably better at predicting preferences, estimating task duration, and prioritizing over time. |
| 3 | **Graduated autonomy** | Actions are classified by risk/reversibility. Low-stakes actions auto-execute. High-stakes actions require confirmation. The threshold should be tunable and should shift as the assistant earns trust. |
| 4 | **Voice-ready from day one** | All assistant outputs include a concise spoken-form summary alongside any structured data. No workflow should assume a visual interface. |

---

## 3. User Context Model

### 3.1 Users & Roles

- **Primary User (Mike):** Full access. All workflows, all data, all configuration.
- **Partner (referenced but not a user):** The assistant should know about her — name, preferences relevant to shared activities (meal planning, calendar coordination, etc.) — but she does not interact with the assistant directly.
- **Future consideration:** Multi-user access is out of scope for MVP but the data model should not preclude it (e.g., user_id on records).

### 3.2 Interaction Modes

| Mode | Priority | Notes |
|------|----------|-------|
| **Chat (web/mobile)** | MVP | Primary interface. Text-based. Rich UI for structured responses (calendars, lists, confirmations). |
| **Voice** | Post-MVP | Smart speaker and/or phone. Requires spoken-form output and intent parsing. Design for this now; build later. |

### 3.3 Notification & Delivery

| Channel | Use Case | Priority |
|---------|----------|----------|
| **Push notification** | Reminders, proactive nudges, confirmation requests | Primary |
| **SMS** | Fallback for time-sensitive reminders if push fails | Secondary |
| **In-app** | Non-urgent updates, daily summaries, plan proposals | Ambient |

---

## 4. Data Model

### 4.1 User Profile (Biography)

The user profile is a **living knowledge graph** about the user, structured as a collection of individual facts, each carrying its own provenance metadata. This fact-level provenance tracking allows the assistant to reason about the origin and reliability of every piece of information it holds.

The profile also includes **life aspirations** — broad, open-ended ambitions (e.g., "get healthier," "have kids," "build long-term wealth") that don't have clear completion criteria and are too large or abstract to be managed as todos. These are stored as biographical context so the assistant can account for them when relevant (e.g., suggesting healthier meal options, flagging a relevant article) without trying to manage them as todos.

#### Provenance Types
- **Seeded** — Provided by the user via the profile page UI (see Section 4.1.1). Seeded facts have confidence 1.0 and represent the user's self-reported information.
- **Explicit** — Stated during conversation (e.g., "Remember that I hate cilantro").
- **Inferred** — Derived from patterns in user behavior (e.g., "User prefers morning workouts based on 12/15 sessions being before 9am"). Inferred facts should have a confidence score and be confirmable.

#### Profile Fact Schema

Each fact in the profile is stored as an independent record with its own metadata:

```
ProfileFact
├── id
├── category (identity | household | preferences | career | aspirations | schedule | custom)
├── key (e.g., "dietary.likes", "partner.name", "waking_hours", "aspiration.health")
├── value (string or structured — e.g., "bananas", "7:00 AM – 11:00 PM", { name: "Mochi", species: "dog" })
├── provenance (seeded | explicit | inferred)
├── confidence (0.0–1.0 — always 1.0 for seeded/explicit, variable for inferred)
├── evidence (nullable — for inferred facts, describes the basis: "added oranges to grocery list 8 of last 10 weeks")
├── created_at
├── updated_at
├── last_confirmed_at (nullable — timestamp of last user confirmation)
└── superseded_by (nullable — id of the fact that replaced this one, for audit trail)
```

#### 4.1.1 Profile Page UI & Biography Ingestion

The user profile is managed through a **dedicated profile page** in the application — a permanent feature, not a one-time onboarding exercise. The profile page is the primary mechanism for seeding and editing biographical information.

**Profile page design:**
- Organized into logical sections matching the profile categories (Identity, Household, Preferences, Career, Aspirations, Schedule).
- Each field uses an appropriate input type for its data: single-line text (name), date picker (birthday), dropdowns (timezone), multi-line text areas (interests, aspirations), structured sub-forms (pets, vehicles, people).
- All fields are editable at any time.

**Biography ingestion process:**
When the user saves changes to the profile page, a **biography ingestion** process runs to parse the edited fields into ProfileFacts:

1. **Diff detection:** Only fields that were actually modified are processed. Unchanged fields are skipped entirely.
2. **Fact generation:** Each modified field is parsed into one or more ProfileFacts with `provenance = "seeded"` and `confidence = 1.0`.
3. **Conflict resolution:** New seeded facts supersede any existing facts for the same category/key, regardless of the existing fact's provenance. The superseded fact is preserved with `superseded_by` pointing to the new fact (audit trail).
4. **Shared pipeline:** Biography ingestion uses the same fact-creation and conflict-resolution logic that handles explicit and inferred facts from conversations. It is a special case of the general fact-ingestion pipeline, not a separate system.

**Example flow:**
- User edits the "Interests" field on the profile page, adding "bouldering."
- The ingestion process detects the change, creates a new ProfileFact `{category: "preferences", key: "interests.bouldering", value: "bouldering", provenance: "seeded"}`.
- If a prior fact existed for an interest that was removed, it gets superseded.

#### Profile Categories & Example Facts

```
identity
├── name: "Mike"                                    [seeded, 1.0]
├── date_of_birth: "..."                            [seeded, 1.0]
├── location: "Camas, WA (Portland metro)"          [seeded, 1.0]
├── timezone: "America/Los_Angeles"                  [seeded, 1.0]
├── living_situation: "Lives with partner in house"  [seeded, 1.0]

household
├── partner.name: "..."                              [seeded, 1.0]
├── pet: { name: "Mochi", species: "dog", size: "small" }  [seeded, 1.0]
├── vehicles: [...]                                  [seeded, 1.0]

preferences
├── dietary.likes: "bananas"                         [seeded, 1.0]
├── dietary.likes: "oranges"                         [inferred, 0.80, "added to grocery list 8/10 weeks"]
├── dietary.dislikes: "cilantro"                     [explicit, 1.0]
├── communication.verbosity: "concise"               [inferred, 0.70, "edits verbose plans to shorter versions"]

schedule
├── waking_hours: "7:00 AM – 11:00 PM"              [seeded, 1.0]
├── preferred_work_hours: "9:00 AM – 5:00 PM"       [seeded, 1.0]
├── preferred_errand_time: "late morning"             [inferred, 0.75, "7/10 errands scheduled 10am–12pm"]

career
├── current_role: "Director of Analytics"            [seeded, 1.0]
├── work_arrangement: "remote"                       [seeded, 1.0]

aspirations
├── health: "Get healthier / improve fitness"        [seeded, 1.0]
├── family: "Have kids someday"                      [explicit, 1.0]
├── financial: "Build long-term wealth"              [seeded, 1.0]
```

#### Conflict Resolution

When a new fact conflicts with an existing one:
1. If the new fact is **seeded or explicit** and the existing fact is **inferred** → replace the inferred fact (user's word wins).
2. If both are **explicit** and contradictory → ask the user ("I had you down as preferring mornings for exercise — has that changed?").
3. If the new fact is **inferred** and the existing is **seeded/explicit** → do not replace; flag for periodic confirmation if confidence is high enough.
4. When a fact is replaced, the old fact is marked with `superseded_by` for audit trail, not deleted.

### 4.2 People

People the user knows, referenced across workflows (calendar events, gift reminders, meal planning for guests, etc.).

```
Person
├── name
├── relationship (partner, friend, family, coworker, etc.)
├── description (free-text, user-provided)
├── contact_info (phone, email — optional)
├── key_dates
│   ├── birthday
│   ├── anniversary
│   └── custom (e.g., "day we met")
├── preferences (dietary, gift ideas, etc.)
├── notes (free-text)
├── created_at
└── updated_at
```

#### 4.2.1 People Management UI

People are managed through a dedicated **People page** in the application — a permanent feature that allows the user to add, edit, and remove people. The design mirrors the Profile page pattern:

- A list view shows all people, filterable by relationship type.
- Clicking a person opens their detail form with structured sections (relationship, description, contact info, key dates, preferences, notes).
- Each field uses an appropriate input type: single-line text (name), dropdown (relationship type), date pickers (birthday, anniversary), multi-line text areas (description, notes).
- Edits trigger the same diff → version → ingest pipeline as the Profile page (see Section 4.1.2). Only modified fields are processed, and new facts supersede conflicting existing ones.

### 4.1.2 Seed Field Edit History

Both the Profile page and the People page track a **field-level edit history** for all seeded data. Every time a field is saved, the full value of that field at that point in time is recorded. This serves three purposes:

1. **Reference:** The user can review what they previously wrote in any field (e.g., "what did I have listed as my hobbies before I updated them?").
2. **Diff detection:** The biography ingestion pipeline compares the new field value against the most recent version to determine whether the field was actually changed. Unchanged fields are skipped entirely.
3. **Audit trail:** Combined with the ProfileFact `superseded_by` chain, this provides a complete history of how the assistant's knowledge about the user evolved.

```
SeedFieldVersion
├── id
├── entity_type ("profile" | "person")
├── entity_id (nullable — null for profile, person_id for people)
├── field_key (e.g., "hobbies", "living_situation", "dietary.likes")
├── value (the full field content at this point in time)
├── edited_at
```

The current value of any field is the most recent `SeedFieldVersion` entry for that entity + field_key. When the user saves edits:
1. For each field in the form, compare the submitted value against the latest `SeedFieldVersion` for that field.
2. If unchanged → skip entirely (no new version, no fact ingestion).
3. If changed → create a new `SeedFieldVersion` record, then run biography ingestion for that field only.
4. The ingestion pipeline generates or supersedes ProfileFacts based on the new field value.

### 4.3 Todos (Planning Layer)

A Todo represents **anything the user needs to accomplish** — from "pick up the dry cleaning" to "file taxes by April 15" to "plan the wedding." Every commitment, obligation, chore, reminder, or goal with a completion state enters the system as a Todo. Todos are the planning layer: they capture *what* needs to get done, *when*, and *how important* it is.

Broad life aspirations that lack clear completion criteria (e.g., "get healthier," "have kids") are **not** todos — they belong in the user profile as biographical aspirations (see 4.1). Todos are things you can finish.

Todos can be nested: a large todo like "Plan the wedding" can contain sub-todos ("Book the venue," "Plan the honeymoon"), each of which decomposes into tasks.

**Todos exist in the backlog until the agent (or user) decides to schedule work.** At that point, the todo is decomposed into one or more Tasks — the execution layer.

```
Todo
├── id
├── title
├── description (nullable)
├── status (backlog | planning | active | completed | on_hold | abandoned)
├── priority (critical | high | medium | low)
│
├── scheduling
│   ├── deadline (nullable — hard deadline if one exists)
│   ├── target_date (nullable — soft target, distinct from hard deadline)
│   ├── preferred_window (nullable — e.g., "morning", "after work", "weekend")
│   ├── estimated_duration_minutes (nullable — total effort estimate)
│   └── energy_level (nullable — low | medium | high — what this effort demands)
│
├── hierarchy
│   ├── parent_todo_id (nullable — for sub-todos)
│   └── child_todo_ids[] (nullable — sub-todos under this one)
│
├── tasks[] (ordered list of task_ids — the decomposed, scheduled work)
│
├── progress
│   ├── progress_notes[] (timestamped journal entries, manual or auto-generated)
│   └── computed_progress (derived: % of tasks completed)
│
├── tags[] (flexible categorization — e.g., "household", "career", "health", "errand")
├── location (nullable — "grocery store", "home office", "downtown")
├── dependencies[] (todo_ids that must complete first)
├── notes (free-text, evolving)
├── created_at
├── updated_at
└── created_by (user | assistant)
```

**Lifecycle:**
1. **Captured → Backlog:** User says "I need to do X." A Todo is created with relevant metadata (priority, deadline, etc.). No calendar impact yet.
2. **Planned → Active:** The agent (during daily planning or on request) decomposes the Todo into Tasks with specific time slots. Todo status moves to `active`.
3. **Executed → Completed:** All Tasks are completed. Todo status moves to `completed`.

**Example range of todos:**
- Trivial: "Pick up the dry cleaning" → 1 todo, 1 task (scheduled for tomorrow at 2pm, 20 min).
- Reminder: "Remind me to call the vet at 3pm" → 1 todo + 1 task created simultaneously (since the time is explicit). The task triggers a push notification.
- Medium: "Get the house ready for guests by Friday" → 1 todo, decomposed into 4–5 tasks (clean bathroom, clean kitchen, prep guest room, grocery shop for dinner).
- Large: "File 2025 taxes by April 15" → 1 todo, decomposed into 5–6 tasks (gather W-2s, collect deductions, schedule CPA, review return, file, pay if owed), back-scheduled from deadline.
- Multi-level: "Plan the wedding" → 1 parent todo with sub-todos for venue, catering, guest list, etc., each with their own tasks.

### 4.4 Tasks (Execution Layer)

A Task represents a **specific, scheduled block of work** — a concrete action placed on the calendar at a particular time. Every Task belongs to a Todo (`todo_id` is non-nullable). Tasks are lean and execution-focused: they answer "what am I doing, when, and for how long?"

Tasks are created when the agent decomposes a Todo and schedules the work. They are the bridge between the todo backlog and the calendar.

```
Task
├── id
├── todo_id (non-nullable — every task belongs to a todo)
├── title
├── description (nullable)
│
├── scheduling
│   ├── scheduled_start (the calendar start time)
│   ├── scheduled_end (the calendar end time)
│   ├── estimated_duration_minutes
│   ├── actual_duration_minutes (nullable — for learning/calibration)
│   └── calendar_event_id (nullable — Google Calendar event ID, set when placed on calendar)
│
├── status (scheduled | in_progress | completed | deferred | cancelled)
│
├── completion
│   ├── completed_at (nullable)
│   ├── deferred_count (how many times rescheduled — useful signal)
│   └── completion_notes (nullable)
│
├── position (integer — ordering within the todo's task list)
├── created_at
├── updated_at
└── created_by (user | assistant)
```

**Key behaviors:**
- When a Task is **deferred**, its `deferred_count` increments. This is a signal to the agent that the user is avoiding or struggling with this work — the agent can use this when re-prioritizing.
- When a Task is **completed**, the agent checks whether all Tasks in the parent Todo are done. If so, the Todo is automatically marked `completed`.
- **Duration tracking:** `estimated_duration_minutes` comes from the Todo (or the agent's estimate). `actual_duration_minutes` is recorded at completion. Over time, the delta between these feeds the agent's duration estimation model.
- **Calendar sync:** When a Task is created with a `scheduled_start` and `scheduled_end`, the agent also creates a corresponding Google Calendar event (tagged as assistant-created per Section 7.3). The `calendar_event_id` links the two. Moving a Task on the calendar updates the Task record, and vice versa.

### 4.5 Lists & List Items

A generic list system that supports multiple list types — groceries, trip planning, reading lists, wish lists, etc. Each list has its own items with flexible metadata.

```
List
├── id
├── name (e.g., "Grocery List", "Portland Trip Ideas", "Books to Read")
├── type (grocery | travel | reading | shopping | custom)
├── description (nullable)
├── status (active | archived)
├── tags[] (flexible categorization)
├── created_at
└── updated_at

ListItem
├── id
├── list_id
├── name
├── status (pending | done)
├── notes (nullable — free-text for any context: "the brand Sarah recommended", "chapter 3 was great")
├── position (integer — for user-defined ordering within the list)
├── added_by (user | assistant)
├── added_at
└── completed_at (nullable)
```

**List type behaviors:**
- **Grocery:** When the user says "what do I need from the store?", the assistant returns the active grocery list. When the user says "I got everything," bulk-mark items as done (or "everything except the parmesan" for partial completion). Completed items remain on the list with `status = done` until the user explicitly removes them or adds them again.
- **Travel:** "Things to do on our Portland trip" — items can be reordered by priority, marked done as they're accomplished.
- **Reading:** "Books I want to read" — items can be marked done when finished, notes can capture thoughts.
- **Custom:** Any user-defined list with the same core mechanics.

### 4.6 Conversation & Interaction Log

Every interaction is stored for preference learning, context continuity, and audit trail.

```
Interaction
├── id
├── timestamp
├── channel (chat | voice | system)
├── user_message (raw input)
├── parsed_intent (what the assistant understood)
├── assistant_response
│   ├── spoken_summary (short, voice-friendly)
│   └── structured_payload (rich data for UI)
├── actions_taken[] (what the assistant did as a result)
├── feedback (nullable — thumbs up/down, correction)
└── session_id (groups a multi-turn conversation)
```

### 4.7 Financial Snapshot

Sourced from Plaid. The assistant doesn't manage financial data directly — it reads from a synced data store.

```
FinancialAccount
├── id
├── institution_name
├── account_type (checking | savings | credit | investment | loan)
├── account_name
├── current_balance
├── available_balance (nullable)
├── last_synced_at

Transaction
├── id
├── account_id
├── date
├── amount
├── merchant_name
├── category (Plaid-provided + user overrides)
├── is_recurring (boolean)
├── notes (nullable)

NetWorthSnapshot
├── date
├── total_assets
├── total_liabilities
├── net_worth
├── breakdown_by_account[]
```

---

## 5. Workflow Definitions

### 5.1 Organization / Time Management

#### 5.1.1 Plan My Day

**Trigger:** User asks ("plan my day"), or assistant proactively nudges in the morning.

**Inputs:**
- Today's calendar events (from Google Calendar)
- Today's existing Tasks (already scheduled for today)
- Todo backlog (todos with upcoming deadlines or high priority that don't yet have Tasks scheduled)
- Recent emails (from Gmail — appointment confirmations, bills due, action items)
- User preferences (morning person? meeting-heavy day? energy patterns?)
- Weather forecast (hourly — to inform scheduling of outdoor tasks like runs, errands)

**Logic:**
1. Pull calendar events — these are fixed anchors.
2. Pull already-scheduled Tasks for today — these are also anchors.
3. Identify available time blocks between events and existing Tasks.
4. Scan the Todo backlog for work that should be scheduled today:
   a. Todos with deadlines approaching that need Tasks created.
   b. High-priority todos with no scheduled Tasks yet.
5. For each eligible Todo, create proposed Tasks with estimated durations.
6. Rank proposed Tasks by: todo priority, deadline urgency, estimated energy match to time-of-day, location batching.
7. Slot proposed Tasks into available blocks, respecting estimated duration and energy alignment.
8. Generate a proposed daily plan.

**Output:**
- Spoken summary: "You've got 3 meetings today. I've slotted in time to work on your tax prep this morning and grocery shopping after your 2pm call. Want me to lock this in?"
- Structured plan: timeline view with events + proposed task blocks.

**Action classification:** HIGH-STAKES (modifies calendar) → present plan, wait for confirmation.

**Learning opportunities:**
- Track which proposed plans get accepted vs. modified.
- Track actual task completion vs. estimates.
- Over time, improve duration estimates and time-of-day preferences.

#### 5.1.2 Remind Me

**Trigger:** User says "remind me to [X] at [time/context]."

**Inputs:**
- What to remember
- When to trigger (absolute time or relative time, e.g., "in 2 hours," "at 3pm," "tomorrow morning")

**Logic:**
1. Parse the reminder target and trigger condition.
2. Create a Todo (e.g., "Call the vet", priority: medium) **and** a Task simultaneously, since the user provided an explicit time. The Task is scheduled at the specified time.
3. Schedule a push notification (or SMS fallback) for the specified time, linked to the Task.

**Output:**
- Spoken confirmation: "Got it — I'll remind you to call the vet at 3pm."

**Action classification:** LOW-STAKES → auto-execute, confirm creation.

#### 5.1.3 Reschedule a Task

**Trigger:** User says "push that back an hour" / "move grocery shopping to tomorrow."

**Logic:**
1. Identify the referenced Task (may require disambiguation — "which task do you mean?").
2. Update the Task's scheduling fields (scheduled_start, scheduled_end).
3. Move the corresponding calendar event.
4. Re-evaluate the daily plan if other Tasks are affected (e.g., cascading time conflicts).

**Action classification:** LOW-STAKES if rescheduling a single Task (the calendar event is assistant-created). MEDIUM if it cascades to other scheduled Tasks → summarize downstream changes.

#### 5.1.4 Recommend What to Do

**Trigger:** User asks "what should I do right now?" or "I have a free hour."

**Inputs:**
- Current time and remaining calendar
- Already-scheduled Tasks for the rest of the day
- Todo backlog (unscheduled todos that could fill the gap)
- User's current energy level (could ask, or infer from time of day)
- Context (at home? out running errands?)

**Logic:**
1. Identify the available time window.
2. Look at already-scheduled Tasks first — anything that could be pulled forward?
3. Scan the todo backlog for todos that fit the window (by estimated duration, energy level, location).
4. Rank by todo priority, deadline, and energy match.
5. Present top 1–3 options with reasoning.

**Output:**
- "You've got an hour before your 3pm meeting. I'd suggest knocking out the expense report (30 min, due tomorrow) and then prepping dinner ingredients. Or if you're feeling low-energy, catch up on that article you bookmarked."

**Action classification:** INFORMATIONAL → no action needed, just a recommendation.

### 5.2 Chores & Household

#### 5.2.1 Manage Todo Backlog

**Trigger:** User adds, edits, completes, or reviews things they need to do.

**Capabilities:**
- Add to backlog: "I need to fix the leaky faucet" → create a Todo in the backlog, infer priority and tags.
- Complete: "I finished the laundry" → if there's a scheduled Task, mark it complete. If all Tasks for the Todo are done, mark the Todo complete.
- Review backlog: "What's on my plate this week?" → show Todos filtered by deadline/priority, with their Task status (scheduled vs. not yet planned).
- Decompose and schedule: "I need to plan a dinner party for Saturday" → create a Todo, decompose into Tasks, propose a schedule with calendar blocks, wait for confirmation.

**Action classification:** Adding a Todo to the backlog → LOW-STAKES, auto-execute. Decomposing and scheduling Tasks onto the calendar → HIGH-STAKES, confirm.

#### 5.2.2 Manage Lists

**Trigger:** User adds items to a list, asks what's on a list, or marks items done.

**Capabilities:**
- **Grocery list:** "Add milk and eggs to the grocery list" → create ListItems on the grocery List. "What do I need from the store?" → return pending items. "I got everything" / "I got everything except the parmesan" → bulk mark done. Smart additions: if user says "I want to make carbonara this week," the assistant infers required ingredients.
- **Other lists:** "Add 'Multnomah Falls' to our Portland trip list" → create ListItem. "What books am I reading?" → return the reading list. "I finished Project Hail Mary" → mark done, optionally capture notes.
- **Create new lists:** "Start a list for things we need for the nursery" → create a new List.

**Action classification:** LOW-STAKES → auto-execute all (adding items, marking done, creating lists).

### 5.3 Information Retrieval

#### 5.3.1 Review Spending

**Trigger:** "How much did we spend this month?" / "What's our dining out budget looking like?"

**Inputs:** Transaction data from Plaid integration.

**Output:**
- Spoken summary: "You've spent $3,200 so far this month. Dining out is at $480, which is above your typical $350."
- Structured view: category breakdown, trend vs. prior months, anomaly callouts.

**Action classification:** INFORMATIONAL → read-only.

#### 5.3.2 Check Net Worth

**Trigger:** "What's our net worth?" / "How are we doing financially?"

**Inputs:** Account balances from Plaid, historical snapshots.

**Output:**
- Current net worth with breakdown by account type.
- Month-over-month and year-over-year trend.
- Notable changes ("Your brokerage is up $4K since last month").

**Action classification:** INFORMATIONAL → read-only.

#### 5.3.3 Check the News

**Trigger:** "What's going on in the world?" / "Any news about [topic]?"

**Inputs:** News API, user topic preferences (from profile).

**Output:**
- Curated summary, prioritized by user interests.
- Should avoid overwhelming — 3–5 top stories with one-line summaries, expandable.

**Action classification:** INFORMATIONAL → read-only.

### 5.4 Preference Learning

#### 5.4.1 Learn New Info About Me

**Trigger:**
- **Explicit:** "Remember that I'm allergic to shellfish."
- **Conversational:** During a recipe discussion: "Oh, I don't eat pork." → infer and store with provenance = `explicit`.
- **Behavioral:** After 10 morning workouts and 2 evening ones, the assistant infers "user prefers morning exercise" with confidence 0.85.

**Logic:**
1. Classify the new information (which profile section does it belong to?).
2. Check for conflicts with existing profile data.
3. If conflict: ask the user ("I had you down as preferring mornings for exercise — has that changed?").
4. If new: store with appropriate provenance and confidence.
5. If inferred: periodically surface inferences for confirmation ("I've noticed you tend to defer tasks on Fridays — want me to schedule less on Fridays?").

**Action classification:** LOW-STAKES for storing explicit statements. MEDIUM for acting on inferences → confirm before changing behavior.

---

## 6. Action Classification Framework

Every action the assistant can take is classified into a tier that determines whether it auto-executes or requires confirmation.

| Tier | Confirmation | Examples |
|------|-------------|----------|
| **Read-only** | None | Check calendar, look up weather, review spending, check net worth, view todo backlog |
| **Low-stakes write** | Auto-execute, notify | Add a todo to backlog, add a list item, log a preference, mark a task complete, set a reminder (creates todo + task simultaneously), modify/move a calendar event created by the assistant |
| **Medium-stakes write** | Summarize & confirm | Reschedule multiple tasks, act on an inferred preference |
| **High-stakes write** | Present plan & wait for approval | Plan the day (decompose todos → create tasks → calendar events), decompose and schedule a multi-step todo, any bulk calendar operation, modify a calendar event NOT created by the assistant |

**Note on calendar events:** Events created by the assistant are tagged with a metadata marker (see Section 7.3) and treated as low-stakes to modify, since the assistant created them and can recreate them. Events that originated from other sources (user-created, shared calendar invites, etc.) are treated as high-stakes. This distinction applies to the calendar modification itself — if the calendar change is part of a larger high-stakes action (e.g., replanning the whole day), the overall action tier governs.

### Graduation Mechanism

Over time, the assistant should be able to "graduate" action types from higher tiers to lower tiers based on user trust signals:
- If the user accepts 10 consecutive daily plans with minimal edits, the assistant could propose: "I've been getting your daily plans pretty close — want me to just lock them in and send you a summary instead of asking?"
- This graduation should be **explicitly offered**, not silently changed.

---

## 7. External Integrations

### 7.1 Integration Map

| System | Access | MVP? | Purpose |
|--------|--------|------|---------|
| **Google Calendar** | Read + Write (OAuth) | Yes | Anchor for daily planning, event awareness, task scheduling |
| **Gmail** | Read (OAuth) | Yes | Surface actionable items (bills due, appointment confirmations, shipping notifications, new information about the user's life) |
| **Plaid** | Read (API) | Yes | Account balances, transactions for spending/net worth. User will curate data into structured formats accessible via tool call. |
| **News API** | Read | Phase 2 | Curated news summaries |
| **Weather API** | Read | Yes | Context for daily planning and on-demand queries. Must provide **hourly (or more granular) forecast data** to support activity-level planning (e.g., scheduling a run during a dry window). |
| **Push notification service** (e.g., Firebase, ntfy, Pushover) | Write | Yes | Reminder delivery, proactive nudges |
| **SMS gateway** (e.g., Twilio) | Write | Phase 2 | Fallback for push notifications |

### 7.2 Data Sync Strategy

- **Calendar:** Real-time sync via Google Calendar API webhooks. The assistant should always have a current view.
- **Gmail:** Periodic polling (every 15–30 min) or Gmail push notifications for new mail. Read-only — the assistant never sends email.
- **Plaid:** Daily batch sync of transactions. On-demand balance refresh when user asks. User curates data into structured tool-callable formats.
- **Weather:** Fetched on-demand whenever needed — at morning planning time, when the user asks, or when the assistant is scheduling outdoor activities. Hourly granularity cached for the current day; refresh as needed.
- **News:** On-demand fetch when requested, with optional morning briefing.

### 7.3 Calendar Event Tagging

All calendar events created by the assistant must be clearly identifiable:

- **Metadata marker:** Each event created by the assistant includes a custom extended property (e.g., `extendedProperties.private.created_by = "assistant"`) that flags it as assistant-created.
- **Visual distinction:** Assistant-created events use a consistent, non-default calendar color (not Google Calendar's default blue). This should be configurable but ship with a sensible default (e.g., sage green or lavender).
- **Purpose:** This tagging enables the action classification framework to distinguish low-stakes modifications (assistant's own events) from high-stakes ones (user or third-party events). It also gives the user at-a-glance visibility into what the assistant has scheduled.

---

## 8. Proactive Behaviors

The assistant doesn't just wait to be asked. It should initiate context-appropriate nudges.

| Trigger | Proactive Action | Channel |
|---------|-----------------|---------|
| Morning (configurable time) | "Good morning — here's what your day looks like. Want me to plan your open time?" | Push notification |
| Upcoming deadline (configurable horizon) | "Your taxes are due in 10 days. You haven't started the prep tasks yet — want me to schedule time?" | Push notification |
| Calendar gap detected + pending todos | "You've got 2 free hours this afternoon and 3 todos in the backlog. Want a suggestion?" | In-app (low urgency) |
| Key date approaching (birthday, anniversary) | "Sarah's birthday is next week. Want me to add gift shopping to your todos?" | Push notification |
| Spending anomaly | "Heads up — dining out spending this month is 40% above your average." | In-app |
| Inferred preference to confirm | "I've noticed you usually skip tasks after 8pm. Want me to avoid scheduling things in the evening?" | In-app |

### Nudge Etiquette
- The assistant should respect the user's **waking hours** as defined in their profile (see Section 4.1, schedule facts). No proactive notifications outside waking hours. If this proves insufficient, strict DND windows will be implemented later.
- If the user ignores or dismisses a nudge, back off on that type (learning signal).
- Every proactive nudge type should be individually toggleable.

---

## 9. Response Contract

Every assistant response, regardless of workflow, should conform to a dual-format output contract to support the future voice interface.

```
AssistantResponse
├── spoken_summary (string)
│   └── Max ~2 sentences. Conversational. No jargon.
│       Suitable for text-to-speech.
│       Example: "You've got a busy morning with 2 meetings.
│                I've blocked time for your tax prep at 2pm."
│
├── structured_payload (object, nullable)
│   └── Rich data for the UI to render (timeline, list, chart, etc.)
│       Type varies by workflow.
│
├── actions_taken[] (array)
│   └── What the assistant did (for audit trail and undo support).
│       Example: [{ type: "calendar_event_created", details: {...} }]
│
├── confirmation_required (boolean)
│   └── If true, the UI should present accept/reject/modify controls.
│
└── follow_up_suggestions[] (array, nullable)
    └── Contextual next actions.
        Example: ["Add a todo", "See full weekly view", "Skip planning today"]
```

---

## 10. MVP Scope & Phasing

### Phase 1 — MVP (Core Loop)

**Goal:** A working chat assistant that can manage todos/tasks/lists, plan your day, set reminders, and surface relevant information from email — all integrated with Google Calendar.

- Chat interface (web)
- Profile page UI with biography ingestion pipeline (see 4.1.1)
- Todo backlog management (add, edit, review, complete)
- Todo → Task decomposition and scheduling (user confirms the plan)
- Generic list management (grocery list + any custom lists)
- Daily planning workflow (scan backlog → decompose → schedule tasks → calendar)
- Reminders (creates todo + task simultaneously, push notification via Pushover or ntfy)
- Google Calendar read/write with event tagging (see 7.3)
- Gmail read integration (surface actionable items, new info)
- Weather API with hourly granularity (for daily planning + on-demand)
- Plaid integration (spending review, net worth)
- Action confirmation framework (low/medium/high stakes)
- Conversation logging
- Response contract (spoken_summary + structured_payload from day one)

### Phase 2 — Intelligence & Expansion

- Preference inference engine (behavioral pattern detection)
- Duration estimation learning (track estimate vs. actual)
- Proactive nudge system
- News briefing
- Trust graduation for action tiers
- SMS fallback for notifications

### Phase 3 — Voice & Advanced

- Voice interface (smart speaker / phone)
- Advanced scheduling (energy-level matching, context-aware recommendations)

---

## 11. Deployment & Infrastructure

The application will be deployed to a **home server** accessible only via SSH from within a **Tailscale network**. This significantly reduces the attack surface compared to a public-facing deployment.

### Security Model

- **Network access:** Tailscale mesh VPN only. No public-facing endpoints. SSH access for administration.
- **Authentication:** Single-user application; authentication is handled at the network layer (Tailscale) rather than application layer for MVP. Application-level auth can be added later if multi-user access is needed.
- **OAuth tokens:** Google Calendar and Gmail OAuth tokens, Plaid access tokens, and any other API credentials should be stored securely (e.g., environment variables, secrets manager, or encrypted config — not in plaintext config files or source code).
- **Data at rest:** Given the single-user, locked-down deployment model, full database encryption is not required for MVP. The home server's disk encryption (if enabled) provides baseline protection.

### Data Retention

- **All granular data is retained indefinitely.** Conversation logs, financial snapshots, completed tasks, profile fact history (including superseded facts), and interaction logs are never automatically purged.
- **Rationale:** Single-user system with locked-down access. The data has compounding value for preference learning, trend analysis, and personal history. Storage costs on a home server are negligible.
- **Future consideration:** If storage becomes a concern, implement archival tiers (hot/warm/cold) rather than deletion.

### Tool-Callable Data

Where external data sources benefit from cleaner or more structured inputs, the user will curate the data into formats that the assistant can access via tool calls. This is particularly relevant for:
- **Financial data (Plaid):** Raw Plaid transaction data can be noisy. The user may curate categorized summaries, account groupings, or budget targets into structured files or database tables that the assistant queries via tool call.
- **Any domain where pre-processing improves LLM reasoning quality** over raw API responses.

---

## 12. Future Considerations

The following items are explicitly out of scope for now but are recorded for future reference:

1. **Undo support:** If the assistant auto-executes a low-stakes action, can the user say "undo that"? This implies action reversibility metadata.
2. **Shared calendar awareness:** Factor partner's calendar events into planning.
3. **Recipe integration:** Connect grocery list workflow to a recipe database or meal planning system.
4. **Todo review cadence:** Prompt periodic progress reviews on active todos.
5. **Multi-user access:** Allow partner to interact with the assistant directly.
6. **Context-aware reminders:** Geofencing or location-based triggers (currently out of scope; user provides explicit times instead).
