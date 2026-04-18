"""Import eval scenario YAML files into Langfuse datasets.

Each `evals/scenarios/<name>.yaml` becomes a Langfuse dataset named `<name>`.
Each scenario entry becomes a dataset item keyed on `scenario_id` (stored in
`metadata.scenario_id`), with `input=user_message` and `expected_output=expect`.

Langfuse dedupes items on (dataset_name, id), so rerunning this is idempotent
as long as scenario ids are stable. Files prefixed with `from_` are skipped —
those are personal / gitignored.

Usage:
    python -m scripts.import_datasets
    python -m scripts.import_datasets --scenarios-dir evals/scenarios
"""

import argparse
import logging
import sys
from pathlib import Path

import yaml

from app.observability.langfuse_client import get_langfuse

logger = logging.getLogger(__name__)

DEFAULT_SCENARIOS_DIR = Path("evals/scenarios")


def _import_file(lf, path: Path) -> int:
    dataset_name = path.stem
    scenarios = yaml.safe_load(path.read_text()) or []

    try:
        lf.create_dataset(name=dataset_name, description=f"Imported from {path.name}")
    except Exception as e:
        logger.debug("create_dataset(%s) skipped: %s", dataset_name, e)

    count = 0
    for scenario in scenarios:
        scenario_id = scenario.get("id")
        if not scenario_id:
            logger.warning("Skipping scenario without id in %s", path)
            continue
        try:
            lf.create_dataset_item(
                dataset_name=dataset_name,
                id=scenario_id,
                input={"user_message": scenario.get("user_message", "")},
                expected_output=scenario.get("expect") or {},
                metadata={"scenario_id": scenario_id, "source_file": path.name},
            )
            count += 1
        except Exception as e:
            logger.warning("create_dataset_item(%s/%s) failed: %s", dataset_name, scenario_id, e)

    logger.info("Imported %d items into dataset %s", count, dataset_name)
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios-dir", type=Path, default=DEFAULT_SCENARIOS_DIR)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    lf = get_langfuse()
    if lf is None:
        logger.error("Langfuse not configured — set LANGFUSE_HOST/PUBLIC_KEY/SECRET_KEY")
        sys.exit(1)

    total = 0
    for path in sorted(args.scenarios_dir.glob("*.yaml")):
        if path.stem.startswith("from_"):
            logger.info("Skipping personal file %s", path.name)
            continue
        total += _import_file(lf, path)

    lf.flush()
    logger.info("Import complete: %d total items", total)


if __name__ == "__main__":
    main()
