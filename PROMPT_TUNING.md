# Prompt Tuning & Evaluation

This document is the reference for how prompts are versioned, observed, and tested in this project. It is intended for any human or agent who needs to iterate on the assistant's behavior without manually babysitting the UI.

The core idea: every prompt component is **content-addressable**, every LLM call records **which component versions it used**, and a **replay harness** runs a golden set of scenarios through the full agent loop in **dry-run mode**. [Self-hosted Langfuse](http://100.94.165.38:3000) sits on top as a browsing/diffing surface — files remain the source of truth; Langfuse is a mirror for inspection and comparison.

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

Two stores, dual-written on every call:

**Postgres `prompt_components` table** — one row per unique `(id, name, type, prompt_text)` tuple. Content-addressed: same text → same id, insert-once. `llm_calls.prompt_component_ids` is a JSONB array of the component ids active on that call, in composition order. This is the durable system-of-record and what the replay harness inspects.

**Langfuse Prompt Management** — mirrored on upsert in [_mirror_components_to_langfuse](backend/app/prompts/composer.py#L203). Langfuse dedupes on `(name, prompt_text)` so steady-state calls are no-ops; when you edit a `.txt`, a new Langfuse prompt version appears automatically on the next request. This is the browsing surface — version history, side-by-side diffs, and the Playground for testing edits without a code path.

### 1.4 What happens on a live chat turn

1. Planner LLM runs — its prompt is upserted, its call is logged with `prompt_component_ids=[PLANNER_PROMPT_ID]`, and a `generation` span lands in Langfuse.
2. Main loop assembles the system prompt via `compose_and_persist_prompt` — every active component is upserted into Postgres and mirrored to Langfuse Prompt Management in one pass.
3. The main-loop `llm_calls` row is written with `prompt_component_ids=[...]` matching the ordered component list; a `generation` span is emitted per round with the same ids as metadata.
4. Each tool call emits a `tool:<name>` span tagged with its action tier.

For any historical call you can answer "what exact text did the model see?" by either joining `llm_calls.prompt_component_ids` → `prompt_components.prompt_text` in SQL, or opening the trace in Langfuse.

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

## 2. Langfuse: the browsing surface

Self-hosted Langfuse at [http://100.94.165.38:3000](http://100.94.165.38:3000). Compose and secrets live in `/home/mike/infra/langfuse/`; backend wiring is in [backend/app/observability/langfuse_client.py](backend/app/observability/langfuse_client.py). If the three `LANGFUSE_*` env vars are unset, every helper no-ops and the backend runs normally — failing Langfuse never takes down chat.

### 2.1 Traces

Every chat turn (and every replay scenario) emits one trace named `agent_loop` containing:

- One `generation` span for the planner (with `planner_prompt_id` metadata)
- One `generation` span per main-loop round (with `prompt_component_ids` + `effort` metadata)
- One `tool:<name>` span per tool invocation (with tier + dry_run metadata)

Traces are tagged with the channel (`chat`, `proactive`, `eval`, etc.); `session_id` is set so you can filter a full conversation in the UI. Use this view to answer "what did the model actually do on turn X?" without digging into the database.

### 2.2 Prompt Management

Every component version is mirrored to Langfuse on upsert (§1.3). The UI gives you:

- Full version history per component, side-by-side diff between any two versions
- Filter traces by a specific prompt version to see "what happened when we were running this text"
- A **Playground** that pulls a saved prompt and lets you tweak wording against sample inputs without touching files

Files stay the source of truth — editing a prompt in the Langfuse UI does not write back to disk. Use the Playground to sketch, then commit the change to the `.txt`.

### 2.3 Datasets and experiments

Scenario YAMLs become Langfuse datasets via [backend/scripts/import_datasets.py](backend/scripts/import_datasets.py). Run it after adding or editing scenarios:

```bash
docker compose exec -w /app backend python -m scripts.import_datasets
```

Each dataset is named after its file (`smoke.yaml` → dataset `smoke`). Dedupe is on `(dataset_name, scenario_id)` — rerunning is idempotent. `from_*.yaml` files are skipped (personal, gitignored).

`replay.py --langfuse` then runs the harness as a Langfuse *experiment*, linking each scenario's trace to its dataset item under a run named `replay-<timestamp>-<fingerprint>`. The dataset's "Runs" tab shows every experiment you've executed and lets you diff them pairwise (§5.3).

---

## 3. Running an evaluation

All commands run from the repo root and execute inside the backend container.

### 3.1 Quick smoke test

```bash
docker compose exec -w /app backend python -m scripts.replay \
    --scenarios evals/scenarios/smoke.yaml
```

Exit code is `0` if every assertion passes, `1` if any fails, `2` if a filter matched nothing.

### 3.2 Specific scenario

```bash
docker compose exec -w /app backend python -m scripts.replay \
    --scenarios evals/scenarios/smoke.yaml \
    --scenario-id create_a_todo
```

### 3.3 With Langfuse linkage

Add `--langfuse` to link each scenario's trace to its dataset item in Langfuse, making the run appear in the dataset's "Runs" tab for comparison against other versions:

```bash
docker compose exec -w /app backend python -m scripts.replay \
    --scenarios evals/scenarios/smoke.yaml --langfuse
```

Requires that the dataset has been imported (§2.3). If Langfuse is down, the replay still runs and writes JSON files — the linkage just silently skips.

### 3.4 Reading results

**Langfuse UI** is the primary surface for inspection: open the run's experiment page, click into a scenario to see the full trace (planner call, each main-loop round, every tool span, token counts, total cost). Filter by tag, session, prompt version, or scenario id.

**JSON on disk** is kept for CI and scripted use. Key fields per scenario:

- `main_component_names` — human-readable list of what the model saw on the main call
- `llm_calls[]` — per-round token cost, stop reason, component-id array
- `tools_called[]` — tool names invoked in order
- `spoken_summary`, `structured_payload`, `payload_type`
- `confirmation_required` — set only when a HIGH_STAKES tool halted
- `assertions.checks` — per-assertion `{expected, got, passed}`

```bash
# Summary of the latest run
ls -t backend/evals/runs/ | head -1 | xargs -I {} cat backend/evals/runs/{}/summary.json
```

---

## 4. Creating or modifying tests

### 4.1 Scenario file structure

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

**Naming convention**: group related scenarios in one file (`smoke.yaml`, `planning.yaml`, `confirmations.yaml`). Scenario ids must be unique within a file and filesystem-safe (they become JSON filenames and Langfuse dataset-item ids).

### 4.2 Adding a new scenario

1. Append an entry to the relevant file in `backend/evals/scenarios/`. Omit any `expect` key you don't want checked — assertions are opt-in.
2. Re-import to Langfuse so the new item appears in its dataset:
   ```bash
   docker compose exec -w /app backend python -m scripts.import_datasets
   ```
3. Run it in isolation first to verify behavior:
   ```bash
   docker compose exec -w /app backend python -m scripts.replay \
       --scenarios evals/scenarios/<file>.yaml \
       --scenario-id <new_id>
   ```
4. Inspect the trace in Langfuse (or the per-scenario JSON) to confirm the agent did what you intended, then lock in assertions.

### 4.3 Seeding scenarios from real conversations

[seed_golden.py](backend/scripts/seed_golden.py) bootstraps a YAML file from the `interactions` table:

```bash
docker compose exec -w /app backend python -m scripts.seed_golden \
    --channel chat --limit 30 \
    --output evals/scenarios/from_history.yaml
```

Each emitted scenario has:

- `id` — derived from the message prefix (or `interaction_<uuid>` if empty)
- `user_message` — verbatim from the interactions table
- Commented source metadata (`# source_interaction_id`, `# observed_tools`, `# observed_payload_type`) as hints
- An empty `expect: {}` block for you to fill in

**Seeded files are gitignored.** The `from_*.yaml` pattern contains real user messages (often personal details) and stays local. Once a scenario is stable, copy it into a hand-crafted file (e.g. `planning.yaml`) that *is* tracked. `import_datasets.py` also skips `from_*.yaml` for the same reason.

### 4.4 Modifying or deleting

Edit the YAML entry in place and re-run with `--scenario-id` to confirm assertions still pass; re-run `import_datasets` so Langfuse reflects the change. Don't rename an id unless you're intentionally severing history — run-dir filenames and Langfuse dataset items both key on it. To delete, just remove the YAML entry (run outputs remain in the gitignored `evals/runs/`; old Langfuse items persist but are orphaned).

---

## 5. Workflow: editing a prompt

Recommended loop for any non-trivial prompt change:

### 5.1 Sketch in the Playground (optional)

For pure wording tweaks, open the component in Langfuse's Prompt Management UI → Playground, paste a representative user message, and iterate until the output shape looks right. This skips the full agent loop — fast, but only exercises the single LLM call, not tool selection or response parsing.

### 5.2 Baseline → edit → replay

1. **Baseline** — run the scenario set on `main`:
   ```bash
   docker compose exec -w /app backend python -m scripts.replay \
       --scenarios evals/scenarios/smoke.yaml --langfuse
   ```
   Note the run name (printed on completion, also visible in the dataset's Runs tab).

2. **Edit** — modify `backend/app/prompts/components/<name>.txt`. The prompts directory is bind-mounted into the backend container and [compose_prompt](backend/app/prompts/composer.py#L132) re-reads files on every call — edits are picked up on the next request with **no restart or rebuild needed**.

3. **Replay** — same command. The fingerprint will differ; the only component id that shifted is the one you edited. A new Langfuse prompt version appears automatically, and the new experiment run links to the same dataset items as the baseline.

### 5.3 Compare

- **In Langfuse**: open the dataset, go to Runs, select the two runs — side-by-side diff of outputs per scenario, with token/cost delta and direct links into each trace. This is usually what you want.
- **On disk**: `diff -r` the two run directories for a machine-readable diff; useful in CI or when Langfuse isn't available.
- **Pass/fail first**: check `summary.json` (or the Runs tab) for any regression in binary assertions before drilling into diffs.

### 5.4 Commit

If the new behavior is right, commit the `.txt` edit. The SHA-256 is already persisted in `prompt_components` (and Langfuse) on the run that produced it, so you have a durable reference to "what the text was at that moment" even if you later change it again.

### 5.5 Edit vs. add a new component

- **Edit in place** when refining wording, tightening instructions, or fixing a regression. Only the edited component's id changes.
- **Add a new component** when introducing a distinct mode (new channel, new specialized response format). Wire it into [_select_components](backend/app/prompts/composer.py#L91) and [_COMPOSITION_ORDER](backend/app/prompts/composer.py#L35).

### 5.6 Dry-run safety guarantees

Dry-run replay is safe to run in any environment with a real database:

- No rows created in `todos`, `lists`, `reminders`, `profile_facts`, `calendar_events`.
- No Google Calendar writes, no ntfy pushes, no `[via Assistant]` events.
- READ_ONLY calls still hit real data — scenarios reflect the state of the DB at replay time, which is usually what you want.
- One side-effect: a row is written to `interactions` with `channel="eval"` and to `llm_calls` (both tagged with component ids). Filter these out when analyzing real chat.

---

## 6. The assertion panel

Assertions are the `expect` block per scenario. All are binary (pass/fail), opt-in (missing key = not checked), and run against the final agent-loop result. No LLM-as-judge in this iteration.

### 6.1 Available assertions

| Key                    | Type        | Passes when                                                          |
|------------------------|-------------|----------------------------------------------------------------------|
| `components_any_of`    | `list[str]` | At least one of the named components was active on the main call    |
| `tools_called_any_of`  | `list[str]` | At least one of the named tools was invoked during the loop         |
| `payload_type`         | `str`       | `structured_payload.type` equals this exact value                   |
| `confirmation_required`| `bool`      | Whether the response halted for HIGH_STAKES confirmation matches     |

All four are implemented in [_check_assertions](backend/scripts/replay.py#L172). If a scenario crashes (exception inside `run_agent_loop`), a synthetic `crash` check fails the scenario regardless of the `expect` block.

### 6.2 Adding a new assertion type

If you need a new check (e.g. `tools_called_in_order`, `spoken_summary_contains`, `min_components`), extend `_check_assertions` with a new `if "<key>" in expect:` branch. Each branch should populate `checks["<key>"] = {"expected": ..., "got": ..., "passed": <bool>}` so the summary format stays uniform. Keep it binary for now — the harness is not designed for scored assertions.

### 6.3 Why assertions are intentionally minimal

The harness surfaces regressions, not completeness. An overly strict assertion locks in incidental behavior and makes every prompt change noisy; an overly loose one misses regressions. The binary, opt-in design pushes you to assert only on behavior you actually care about — usually "did the right tool get called?" and "did we produce the right payload shape?".

---

## 7. Files and entry points

| Path                                                                          | Purpose                                              |
|-------------------------------------------------------------------------------|------------------------------------------------------|
| [backend/app/prompts/components/](backend/app/prompts/components/)            | Prompt component `.txt` files — edit these           |
| [backend/app/prompts/composer.py](backend/app/prompts/composer.py)            | Composition, hashing, Postgres + Langfuse upsert     |
| [backend/app/agent/planner.py](backend/app/agent/planner.py)                  | Planner prompt + `PLANNER_PROMPT_ID`                 |
| [backend/app/agent/orchestrator.py](backend/app/agent/orchestrator.py)        | `run_agent_loop`, trace/generation/tool spans, `dry_run` |
| [backend/app/observability/langfuse_client.py](backend/app/observability/langfuse_client.py) | Langfuse client + trace helpers (no-op fallback) |
| [backend/scripts/replay.py](backend/scripts/replay.py)                        | Replay CLI (`--langfuse` for experiment linkage)     |
| [backend/scripts/import_datasets.py](backend/scripts/import_datasets.py)      | Sync scenario YAMLs → Langfuse datasets              |
| [backend/scripts/seed_golden.py](backend/scripts/seed_golden.py)              | Seed YAML from `interactions` table                  |
| [backend/evals/scenarios/](backend/evals/scenarios/)                          | YAML scenario files (tracked in git)                 |
| `backend/evals/runs/`                                                         | Per-run JSON output (gitignored)                     |
| `/home/mike/infra/langfuse/`                                                  | Langfuse self-host compose + `.env`                  |

---

## 8. Out of scope (intentionally)

- **LLM-as-judge scoring** — assertions are binary and deterministic on purpose. Langfuse supports judge configs in its UI; revisit once the dataset baseline is established.
- **A/B traffic splitting in production** — Langfuse labels (`production` vs `staging`) exist, but wiring traffic-split logic into the agent is a separate task.
- **Composition-logic versioning** — `_COMPOSITION_ORDER` and `_select_components` are tracked in git; component-level hashing alone won't detect a reorder. Revisit if composition logic starts churning.
- **Dropping the Postgres `prompt_components` / `llm_calls` tables** — dual-writing for now; re-evaluate after ≥1 month of Langfuse-only inspection.
