"""Replay a golden set of scenarios through the agent in dry-run mode.

Usage (from `/app` inside the backend container):

    python -m scripts.replay --scenarios evals/scenarios/planning.yaml
    python -m scripts.replay --scenarios evals/scenarios/planning.yaml \\
        --scenario-id plan_my_day_basic
    python -m scripts.replay --scenarios evals/scenarios/planning.yaml \\
        --output-dir evals/runs

Each scenario is a user_message plus optional expectations. The agent loop
runs with dry_run=True: READ_ONLY tools hit the real DB (so Claude sees
real context), LOW_STAKES tools return synthetic results, HIGH_STAKES
tools halt for confirmation as in production.

Results are written to `evals/runs/<timestamp>/<scenario_id>.json` plus
a `summary.json` at the run root. Exits non-zero if any assertion fails.
"""

import argparse
import asyncio
import hashlib
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select

from app.agent.orchestrator import run_agent_loop
from app.database import async_session_maker
from app.models.tables import LlmCall, PromptComponent
from app.observability.langfuse_client import get_langfuse
from app.prompts.composer import COMPONENTS_DIR

logger = logging.getLogger(__name__)


def _prompt_set_fingerprint() -> str:
    """Hash of every component file's current content on disk.

    A stable fingerprint of "the prompt state at run time" — lets you
    compare runs by prompt set without having to inspect every id.
    """
    hasher = hashlib.sha256()
    for path in sorted(COMPONENTS_DIR.glob("*.txt")):
        hasher.update(path.name.encode())
        hasher.update(b":")
        hasher.update(path.read_bytes())
        hasher.update(b"\n")
    return hasher.hexdigest()


async def _run_as_langfuse_experiment(
    dataset_name: str,
    scenarios_by_id: dict[str, dict[str, Any]],
    results_out: dict[str, dict[str, Any]],
    run_name: str,
) -> None:
    """Run scenarios via Langfuse's run_experiment so they link to dataset items.

    Stores each result into `results_out` keyed by scenario_id. Runs
    sequentially (max_concurrency=1) because the agent loop uses a single DB
    session per call.
    """
    lf = get_langfuse()
    if lf is None:
        logger.warning("--langfuse set but Langfuse not configured; running without linkage")
        return
    try:
        dataset = lf.get_dataset(name=dataset_name)
    except Exception as e:
        logger.warning("Langfuse dataset %s unavailable: %s", dataset_name, e)
        return

    async def task(*, item, **_kwargs):
        scenario_id = item.id
        scenario = scenarios_by_id.get(scenario_id)
        if scenario is None:
            return {"error": f"no scenario for item {scenario_id}"}
        result = await _run_scenario(scenario)
        results_out[scenario_id] = result
        return {
            "spoken_summary": result.get("spoken_summary"),
            "tools_called": result.get("tools_called"),
            "error": result.get("error"),
        }

    logger.info("Running Langfuse experiment %s on dataset %s", run_name, dataset_name)
    dataset.run_experiment(run_name=run_name, name=run_name, task=task, max_concurrency=1)
    lf.flush()


async def _run_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    """Run a single scenario and return a result dict."""
    scenario_id = scenario["id"]
    user_message = scenario["user_message"]
    session_id = uuid.uuid4()

    async with async_session_maker() as db:
        try:
            response = await run_agent_loop(
                user_message=user_message,
                session_id=session_id,
                db=db,
                channel="eval",
                dry_run=True,
            )
            error = None
            payload = response.model_dump(mode="json")
        except Exception as exc:
            logger.exception("Scenario %s crashed: %s", scenario_id, exc)
            error = f"{type(exc).__name__}: {exc}"
            payload = {}

        calls_rows = (
            await db.execute(
                select(LlmCall)
                .where(LlmCall.session_id == session_id)
                .order_by(LlmCall.round_number.asc())
            )
        ).scalars().all()
        llm_calls = [
            {
                "round": c.round_number,
                "prompt_component_ids": c.prompt_component_ids or [],
                "stop_reason": c.stop_reason,
                "input_tokens": c.input_tokens,
                "output_tokens": c.output_tokens,
                "cost_usd": float(c.estimated_cost_usd or 0),
            }
            for c in calls_rows
        ]
        main_calls = [c for c in calls_rows if c.round_number >= 1]
        main_component_ids = (main_calls[0].prompt_component_ids or []) if main_calls else []

        component_names: list[str] = []
        if main_component_ids:
            rows = (
                await db.execute(
                    select(PromptComponent.id, PromptComponent.name).where(
                        PromptComponent.id.in_(main_component_ids)
                    )
                )
            ).all()
            id_to_name = {row[0]: row[1] for row in rows}
            component_names = [id_to_name.get(cid, cid[:12]) for cid in main_component_ids]

    actions = payload.get("actions_taken") or []
    structured_payload = payload.get("structured_payload") or {}
    return {
        "scenario_id": scenario_id,
        "user_message": user_message,
        "session_id": str(session_id),
        "error": error,
        "main_component_ids": main_component_ids,
        "main_component_names": component_names,
        "llm_calls": llm_calls,
        "tools_called": [a["tool_name"] for a in actions],
        "spoken_summary": payload.get("spoken_summary"),
        "structured_payload": structured_payload or None,
        "payload_type": structured_payload.get("type") if structured_payload else None,
        "confirmation_required": payload.get("confirmation_required"),
        "follow_up_suggestions": payload.get("follow_up_suggestions") or [],
    }


def _check_assertions(scenario: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Apply binary assertions from the scenario's `expect` block."""
    if result.get("error"):
        return {"checks": {"crash": {"passed": False, "error": result["error"]}}, "passed": False}

    expect = scenario.get("expect") or {}
    checks: dict[str, Any] = {}

    if "components_any_of" in expect:
        want = set(expect["components_any_of"])
        got = set(result["main_component_names"])
        checks["components_any_of"] = {
            "expected_any_of": sorted(want),
            "got": sorted(got),
            "passed": bool(want & got),
        }

    if "tools_called_any_of" in expect:
        want = set(expect["tools_called_any_of"])
        got = set(result["tools_called"])
        checks["tools_called_any_of"] = {
            "expected_any_of": sorted(want),
            "got": sorted(got),
            "passed": bool(want & got),
        }

    if "payload_type" in expect:
        checks["payload_type"] = {
            "expected": expect["payload_type"],
            "got": result["payload_type"],
            "passed": result["payload_type"] == expect["payload_type"],
        }

    if "confirmation_required" in expect:
        expected = bool(expect["confirmation_required"])
        got = result["confirmation_required"] is not None
        checks["confirmation_required"] = {
            "expected": expected,
            "got": got,
            "passed": got == expected,
        }

    passed = all(c.get("passed", True) for c in checks.values())
    return {"checks": checks, "passed": passed}


async def _run(
    scenarios_path: Path,
    output_dir: Path,
    only_id: str | None,
    langfuse_enabled: bool = False,
) -> int:
    scenarios = yaml.safe_load(scenarios_path.read_text()) or []
    if only_id:
        scenarios = [s for s in scenarios if s.get("id") == only_id]
        if not scenarios:
            logger.error("No scenario matched id=%s", only_id)
            return 2

    fingerprint = _prompt_set_fingerprint()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    run_dir = output_dir / f"{timestamp}-{fingerprint[:12]}"
    run_dir.mkdir(parents=True, exist_ok=True)

    summary: dict[str, Any] = {
        "run_dir": str(run_dir),
        "started_at": timestamp,
        "prompt_set_fingerprint": fingerprint,
        "scenarios_file": str(scenarios_path),
        "scenarios": [],
    }

    scenarios_by_id = {s.get("id"): s for s in scenarios}
    scenario_results: dict[str, dict[str, Any]] = {}

    if langfuse_enabled:
        await _run_as_langfuse_experiment(
            scenarios_path.stem, scenarios_by_id, scenario_results,
            run_name=f"replay-{timestamp}-{fingerprint[:8]}",
        )

    overall_pass = True
    for scenario in scenarios:
        scenario_id = scenario.get("id", "unknown")
        if scenario_id in scenario_results:
            result = scenario_results[scenario_id]
        else:
            logger.info("Running scenario: %s", scenario_id)
            result = await _run_scenario(scenario)
        assertions = _check_assertions(scenario, result)
        result["assertions"] = assertions
        if not assertions["passed"]:
            overall_pass = False

        (run_dir / f"{scenario_id}.json").write_text(
            json.dumps(result, indent=2, default=str)
        )

        summary["scenarios"].append({
            "id": scenario_id,
            "passed": assertions["passed"],
            "tools_called": result["tools_called"],
            "payload_type": result["payload_type"],
            "confirmation_required": result["confirmation_required"] is not None,
            "error": result.get("error"),
        })

    summary["overall_passed"] = overall_pass
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2, default=str))

    logger.info("Run complete: %s (passed=%s)", run_dir, overall_pass)
    return 0 if overall_pass else 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", required=True, type=Path)
    parser.add_argument("--scenario-id", default=None)
    parser.add_argument("--output-dir", default=Path("evals/runs"), type=Path)
    parser.add_argument(
        "--langfuse",
        action="store_true",
        help="Link each scenario trace to its Langfuse dataset item.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    exit_code = asyncio.run(
        _run(args.scenarios, args.output_dir, args.scenario_id, args.langfuse)
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
