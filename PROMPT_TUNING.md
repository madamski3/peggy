# Prompt Tuning & Evaluation

This document is the reference for how prompts are versioned, observed, and tested in this project. It is intended for any human or agent who needs to iterate on the assistant's behavior without manually babysitting the UI.

The core idea: every prompt component is **content-addressable**, every LLM call records **which component versions it used**, and a **replay harness** runs a golden set of scenarios through the full agent loop in **dry-run mode** — so you can edit a `.txt`, run one command, and see exactly what changed.

---

## 1. Architecture

### 1.1 How the system prompt is composed

The assistant's system prompt is assembled at request time from granular component files in [backend/app/prompts/components/](backend/app/prompts/components/). Each file is a Jinja template rendered with the current context (datetime, timezone, user profile, strategy text, etc.).

Components are chosen by [_select_components](backend/app/prompts/composer.py#L91) based on:

- **Always-on** — `core_identity`, `current_context`, `tool_guidance`
- **Channel-based** — `proactive_notification` (proactive channel), `wiki_review` (wiki_review channel)
- **Planner-selected** — `daily_planning`, `schedule_overview` (chosen by the planner LLM round)
- **Context-derived** — `strategy` (if non-empty), and a response-format component (`response_format_default` or `response_format_planning`)

Composition order is fixed in [_COMPOSITION_ORDER](backend/app/prompts/composer.py#L35); sections are joined with blank lines.

The planner itself also runs an LLM call with its own prompt. That prompt is versioned the same way (see [planner.py](backend/app/agent/planner.py) — `PLANNER_PROMPT_ID` and `planner_component()`).

### 1.2 Content-addressable versioning

Every time a component is used in a call, [compose_prompt](backend/app/prompts/composer.py#L132) hashes its **raw pre-Jinja text** with SHA-256. Hashing the raw template (not the rendered output) keeps the id stable across requests where only context vars like `current_datetime` change — the id only shifts when the `.txt` itself is edited.

The result is an [ActiveComponent](backend/app/prompts/composer.py#L58) record per component, and a [ComposedPrompt](backend/app/prompts/composer.py#L72) wrapping the rendered text plus the ordered component list.

### 1.3 Where versions are stored

Two places in the database, populated automatically on every call:

**`prompt_components` table** — one row per unique `(id, name, type, prompt_text)` tuple. Content-addressed: the same text always produces the same id, so rows are insert-once. Schema:

| column        | type        | notes                                              |
|---------------|-------------|----------------------------------------------------|
| `id`          | TEXT PK     | hex SHA-256 of `prompt_text`                       |
| `name`        | TEXT        | e.g. `"core_identity"`, `"planner"`                |
| `type`        | TEXT        | `"component"` or `"planner"`                       |
| `prompt_text` | TEXT        | raw pre-Jinja template                             |
| `created_at`  | TIMESTAMPTZ | first-seen time                                    |

**`llm_calls.prompt_component_ids`** — JSONB array of component ids active on that call, in composition order. Non-null on every new call (planner calls carry exactly one id; main-loop calls carry one per active component).

Integrity is not enforced with a FK (Postgres can't FK into JSONB array elements). Instead, [compose_and_persist_prompt](backend/app/prompts/composer.py#L201) always upserts components before the `llm_calls` row is written — see [upsert_prompt_components](backend/app/prompts/composer.py#L176) for the `ON CONFLICT DO NOTHING` helper.

### 1.4 What happens on a live chat turn

1. Planner LLM runs — its prompt is upserted, its call is logged with `prompt_component_ids=[PLANNER_PROMPT_ID]`.
2. Main loop assembles the system prompt via `compose_and_persist_prompt` — every active component is upserted in one statement.
3. The main-loop `llm_calls` row is written with `prompt_component_ids=[...]` matching the ordered component list.
4. Subsequent tool-result rounds reuse the same component list (same cached system prompt).

This means: for any historical call, you can answer "what exact text did the model see?" by joining `llm_calls.prompt_component_ids` → `prompt_components.prompt_text`.

### 1.5 Replay harness

[backend/scripts/replay.py](backend/scripts/replay.py) runs a YAML-defined list of scenarios through the real agent loop with `dry_run=True`. In dry-run mode:

- **READ_ONLY** tools (list_todos, get_calendar_events, etc.) execute normally so Claude sees real context.
- **LOW_STAKES** tools (create_todo, set_reminder, etc.) return mocked success payloads via [_mock_tool_result](backend/app/agent/orchestrator.py) — no DB writes, no Google Calendar events, no notifications.
- **HIGH_STAKES** tools still halt for confirmation, so confirmation-flow scenarios remain testable.

Each run writes to `backend/evals/runs/<timestamp>-<fingerprint[:12]>/`:

- `<scenario_id>.json` per scenario — full response, llm_calls breakdown, component ids + names, tools called, assertion results
- `summary.json` — pass/fail roll-up across the run

The `fingerprint` is a SHA-256 over every `components/*.txt` file's current content — a short "prompt set identity" that lets you group runs by which prompt version produced them.

All replay interactions are logged with `channel="eval"` so they never mingle with real chat history when querying the `interactions` table.

---

## 2. Running an evaluation

All commands run from the repo root and execute inside the backend container.

### 2.1 Quick smoke test

```bash
docker compose exec -w /app backend python -m scripts.replay \
    --scenarios evals/scenarios/smoke.yaml
```

Exit code is `0` if every assertion passes, `1` if any fails, `2` if a filter matched nothing.

### 2.2 Running a specific scenario

```bash
docker compose exec -w /app backend python -m scripts.replay \
    --scenarios evals/scenarios/smoke.yaml \
    --scenario-id create_a_todo
```

### 2.3 Custom output directory

```bash
docker compose exec -w /app backend python -m scripts.replay \
    --scenarios evals/scenarios/smoke.yaml \
    --output-dir evals/runs/experimental
```

### 2.4 Reading results

```bash
# Summary of the latest run
ls -t backend/evals/runs/ | head -1 | xargs -I {} cat backend/evals/runs/{}/summary.json

# One scenario's full trace
cat backend/evals/runs/<timestamp>-<fingerprint>/<scenario_id>.json
```

Key fields on a per-scenario result:

- `main_component_names` — human-readable list of what the model saw on the main call
- `llm_calls[]` — per-round token cost, stop reason, and the component-id array for that round
- `tools_called[]` — tool names invoked in order
- `spoken_summary` — the final user-facing text
- `structured_payload` / `payload_type` — rendered UI payload, if any
- `confirmation_required` — set only when a HIGH_STAKES tool halted
- `assertions.checks` — per-assertion `{expected, got, passed}`

### 2.5 Comparing two prompt versions

Runs are named `<timestamp>-<fingerprint[:12]>`. Same fingerprint = same prompt set. To A/B a prompt change:

```bash
# Baseline
docker compose exec -w /app backend python -m scripts.replay \
    --scenarios evals/scenarios/smoke.yaml

# Edit a component — no restart needed (prompts dir is bind-mounted)
$EDITOR backend/app/prompts/components/core_identity.txt

# New run — different fingerprint
docker compose exec -w /app backend python -m scripts.replay \
    --scenarios evals/scenarios/smoke.yaml

# Diff
diff -r backend/evals/runs/<baseline> backend/evals/runs/<new>
```

Only `core_identity`'s id changes between the two runs — all other component ids remain stable.

### 2.6 Inspecting historical calls in the database

```sql
-- What components did recent calls use?
SELECT id, round_number, prompt_component_ids
FROM llm_calls
ORDER BY created_at DESC
LIMIT 10;

-- What did the model actually see?
SELECT name, type, LEFT(prompt_text, 120) AS preview, created_at
FROM prompt_components
ORDER BY created_at DESC;

-- All calls that used a specific component version
SELECT id, created_at
FROM llm_calls
WHERE prompt_component_ids @> '["<sha256-id-here>"]'::jsonb;
```

---

## 3. Creating or modifying tests

### 3.1 Scenario file structure

Scenario files live in [backend/evals/scenarios/](backend/evals/scenarios/) and are YAML lists of `{id, user_message, expect}` entries:

```yaml
- id: plan_my_day_basic
  user_message: "Plan my day"
  expect:
    components_any_of: ["daily_planning"]
    tools_called_any_of: ["get_calendar_events", "list_todos"]
    payload_type: "daily_plan"
    confirmation_required: false
```

**Naming convention**: group related scenarios in one file (`smoke.yaml`, `planning.yaml`, `confirmations.yaml`). Scenario ids must be unique within a file and filesystem-safe (they become JSON filenames).

### 3.2 Adding a new scenario

1. Open the relevant file in `backend/evals/scenarios/` (or create one).
2. Append an entry. Omit any `expect` key you don't want checked — assertions are opt-in.
3. Run it in isolation first:
   ```bash
   docker compose exec -w /app backend python -m scripts.replay \
       --scenarios evals/scenarios/<file>.yaml \
       --scenario-id <new_id>
   ```
4. Inspect the per-scenario JSON to confirm the behavior matches your intent, then lock it in with assertions.

### 3.3 Seeding scenarios from real conversations

If you have existing chat history that represents behavior you want to preserve, use [seed_golden.py](backend/scripts/seed_golden.py) to bootstrap a YAML file:

```bash
docker compose exec -w /app backend python -m scripts.seed_golden \
    --channel chat \
    --limit 30 \
    --output evals/scenarios/from_history.yaml
```

Each emitted scenario has:

- `id` — derived from the message prefix (or `interaction_<uuid>` if empty)
- `user_message` — verbatim from the interactions table
- Commented source metadata (`# source_interaction_id`, `# observed_tools`, `# observed_payload_type`) as hints
- An empty `expect: {}` block for you to fill in

The `--channel` filter and `--limit` control which rows are pulled; both are optional.

**Seeded files are gitignored.** The `from_*.yaml` pattern is excluded from git — seeded scenarios contain real user messages (often with personal details) and should stay local. Once you've curated a scenario into a stable test, copy it into a hand-crafted file (e.g. `planning.yaml`, `confirmations.yaml`) that *is* tracked.

### 3.4 Modifying an existing test

Edit the YAML entry in place. Re-run with `--scenario-id` to confirm the new assertions pass. Don't rename an id unless you're intentionally severing history — run-dir filenames are keyed on it.

### 3.5 Deleting a scenario

Just remove the YAML entry. Old run outputs remain in `evals/runs/` (which is gitignored).

---

## 4. The assertion panel

Assertions are the "expect" block per scenario. All are binary (pass/fail), all are opt-in (missing key = not checked), and all run against the final agent-loop result. No LLM-as-judge in this iteration.

### 4.1 Available assertions

| Key                    | Type             | Passes when                                                                     |
|------------------------|------------------|---------------------------------------------------------------------------------|
| `components_any_of`    | `list[str]`      | At least one of the named components was active on the main call                |
| `tools_called_any_of`  | `list[str]`      | At least one of the named tools was invoked during the loop                     |
| `payload_type`         | `str`            | `structured_payload.type` equals this exact value                               |
| `confirmation_required`| `bool`           | Whether the response halted for HIGH_STAKES confirmation matches this           |

All four are implemented in [_check_assertions](backend/scripts/replay.py#L131). If a scenario crashes (exception inside `run_agent_loop`), a synthetic `crash` check fails the scenario regardless of the `expect` block.

### 4.2 Adjusting assertion parameters

**Widen / narrow an `any_of` list** — add or remove entries:

```yaml
expect:
  tools_called_any_of: ["create_todo", "set_reminder", "create_list"]
```

**Require a specific payload** — exact string match:

```yaml
expect:
  payload_type: "daily_plan"
```

**Test a confirmation flow** — flip the boolean:

```yaml
expect:
  confirmation_required: true
```

**Drop an assertion** — delete the key entirely. Partial `expect` blocks are fine.

### 4.3 Adding a new assertion type

If you need a new check (e.g. `tools_called_in_order`, `spoken_summary_contains`, `min_components`), extend [_check_assertions](backend/scripts/replay.py#L131) with a new `if "<key>" in expect:` branch. Each branch should populate `checks["<key>"] = {"expected": ..., "got": ..., "passed": <bool>}` so the summary format stays uniform. Keep it binary for now — the harness is not designed for scored assertions.

### 4.4 Why assertions are intentionally minimal

The harness exists to surface regressions, not to grade completeness. An overly strict assertion locks in incidental behavior and makes every prompt change noisy; an overly loose one misses regressions. The binary, opt-in design pushes you to write assertions only for the behavior you actually care about — usually "did the right tool get called?" and "did we produce the right payload shape?".

---

## 5. Workflow: editing a prompt

Recommended loop for any non-trivial prompt change:

1. **Baseline** — run the full scenario set on `main`:
   ```bash
   docker compose exec -w /app backend python -m scripts.replay \
       --scenarios evals/scenarios/smoke.yaml
   ```
   Note the run dir.

2. **Edit** — modify `backend/app/prompts/components/<name>.txt`. The prompts directory is bind-mounted into the backend container (see [docker-compose.yml](docker-compose.yml)), and [compose_prompt](backend/app/prompts/composer.py#L132) re-reads files on every call — so edits are picked up on the next request with **no restart or rebuild needed**.

3. **Replay** — same command. The fingerprint will differ; the only component id that shifted is the one you edited.

4. **Compare** — inspect `summary.json` first, then drill into per-scenario JSONs for any `passed: false` check. `diff -r` between the two run dirs shows what changed end-to-end.

5. **Iterate or commit** — if behavior is right, commit the `.txt` edit. The SHA-256 is already persisted in `prompt_components` on the server that produced this run, so you have a durable reference to "what the text was at that moment" even if you later change it again.

### 5.1 When to add a new component vs. edit an existing one

- **Edit in place** when refining wording, tightening instructions, or fixing a specific regression. The hash changes; nothing else does.
- **Add a new component** when introducing a distinct mode (e.g. a new channel, a new specialized response format). Wire it into [_select_components](backend/app/prompts/composer.py#L91) and [_COMPOSITION_ORDER](backend/app/prompts/composer.py#L35).

### 5.2 Dry-run safety guarantees

Dry-run replay is safe to run in any environment with a real database:

- No rows created in `todos`, `lists`, `reminders`, `profile_facts`, `calendar_events`.
- No Google Calendar writes, no ntfy pushes, no `[via Assistant]` events.
- READ_ONLY calls still hit real data — scenarios reflect the state of the DB at replay time, which is usually what you want.
- One side-effect: a row is written to `interactions` with `channel="eval"` and to `llm_calls` (both tagged with component ids). Filter these out when analyzing real chat:
  ```sql
  SELECT * FROM interactions WHERE channel <> 'eval';
  ```

---

## 6. Files and entry points

| Path                                                                          | Purpose                                              |
|-------------------------------------------------------------------------------|------------------------------------------------------|
| [backend/app/prompts/components/](backend/app/prompts/components/)            | Prompt component `.txt` files — edit these           |
| [backend/app/prompts/composer.py](backend/app/prompts/composer.py)            | Composition, hashing, upsert logic                   |
| [backend/app/agent/planner.py](backend/app/agent/planner.py)                  | Planner prompt + `PLANNER_PROMPT_ID`                 |
| [backend/app/agent/orchestrator.py](backend/app/agent/orchestrator.py)        | `run_agent_loop`, `dry_run` flag, `_mock_tool_result`|
| [backend/scripts/replay.py](backend/scripts/replay.py)                        | Replay CLI                                           |
| [backend/scripts/seed_golden.py](backend/scripts/seed_golden.py)              | Seed YAML from interactions table                    |
| [backend/evals/scenarios/](backend/evals/scenarios/)                          | YAML scenario files (tracked in git)                 |
| `backend/evals/runs/`                                                         | Per-run output (gitignored)                          |
| [backend/migrations/versions/011_prompt_versioning.py](backend/migrations/versions/011_prompt_versioning.py) | Schema for `prompt_components` and the `llm_calls` column |

---

## 7. Out of scope (intentionally)

These are deferred until the current workflow is exercised enough to justify them:

- **External observability UI** (Langfuse, Arize, LangSmith) — current storage is sufficient for single-developer use.
- **LLM-as-judge scoring** — assertions are binary and deterministic on purpose.
- **A/B traffic splitting in production** — edits go out atomically via a backend restart.
- **Composition-logic versioning** — `_COMPOSITION_ORDER` and `_select_components` are tracked in git; component-level hashing alone won't detect a reorder. Revisit if composition logic starts churning.
- **Run-diff UI** — `diff -r` on two run directories is good enough for now.
