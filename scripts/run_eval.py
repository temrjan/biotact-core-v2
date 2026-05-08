"""CLI: run AskBiotact RAG eval against the gold set.

Read-only — calls ``AskBiotactService.process_pure`` (no Redis writes,
no ExtractionAgent firing, no order detection). Produces a JSON report
in ``reports/baseline_<ts>.json`` and prints a stdout summary.

Usage:
    python scripts/run_eval.py
    python scripts/run_eval.py --limit 5 --no-judge       # smoke run
    python scripts/run_eval.py --lang ru --output reports/ru_only.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import redis.asyncio as aioredis

# Make project packages (biotact + tests.eval) reachable when running as
# ``python scripts/run_eval.py`` from project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tests.eval.judge import FaithfulnessJudge  # noqa: E402
from tests.eval.loader import GoldCase, load_gold_set  # noqa: E402
from tests.eval.metrics import (  # noqa: E402
    CaseResult,
    EvalReport,
    must_mention_hits,
    must_not_mention_violations,
    recall_at_5,
    safety_redirect_passed,
)
from tests.eval.runner import aggregate, determine_exit_code  # noqa: E402

from biotact.core.config import get_settings  # noqa: E402
from biotact.core.dependencies import (  # noqa: E402
    get_embedding_service,
    get_qdrant_service,
)
from biotact.modules.askbiotact.config import askbiotact_config  # noqa: E402
from biotact.modules.askbiotact.constants import enrich_query  # noqa: E402
from biotact.modules.askbiotact.service import (  # noqa: E402
    get_askbiotact_service,
)

if TYPE_CHECKING:
    from biotact.modules.askbiotact.service import AskBiotactService
    from biotact.services.rag.embedding import EmbeddingService
    from biotact.services.rag.qdrant import QdrantService

logger = logging.getLogger("eval")

DEFAULT_GOLD_SET: str = "tests/eval/biotact_gold_set.jsonl"
DEFAULT_REPORTS_DIR: str = "reports"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run AskBiotact RAG eval against the gold set.",
    )
    parser.add_argument("--gold-set", default=DEFAULT_GOLD_SET)
    parser.add_argument(
        "--output",
        default=None,
        help="Path for JSON report (default: reports/baseline_<ts>.json)",
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="Run only the first N cases"
    )
    parser.add_argument(
        "--lang", choices=["ru", "uz", "all"], default="all"
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="Skip LLM faithfulness judge",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args()


def filter_cases(
    cases: list[GoldCase], lang: str, limit: int | None
) -> list[GoldCase]:
    if lang != "all":
        cases = [c for c in cases if c.lang == lang]
    if limit:
        cases = cases[:limit]
    return cases


async def run_one_case(
    case: GoldCase,
    service: AskBiotactService,
    embedding_service: EmbeddingService,
    qdrant_service: QdrantService,
    judge: FaithfulnessJudge | None,
) -> CaseResult:
    """Run one dialog through the pipeline, compute metrics."""
    err: str | None = None
    answer = ""
    retrieved: list = []
    answer_faithful: bool | None = None

    try:
        # Replicate the same enrichment ``_process_rag_query`` uses when
        # ``telegram_id`` is None (regex path). Needed to compute recall@5
        # against the same chunks the chat LLM saw.
        enriched_query = enrich_query(case.last_user_message, case.seeded_history)
        query_vec = await embedding_service.embed_text(enriched_query)
        retrieved = await qdrant_service.search(
            query_vector=query_vec,
            department_id=askbiotact_config.department_filter or "",
            limit=askbiotact_config.rag_limit,
            score_threshold=askbiotact_config.score_threshold,
        )

        answer = await service.process_pure(
            message=case.last_user_message,
            chat_history=case.seeded_history,
        )

        if judge is not None:
            chunks_text = [r.content for r in retrieved[:5]]
            verdict = await judge.score(answer=answer, chunks_text=chunks_text)
            if verdict is not None:
                answer_faithful = verdict.faithful
    except Exception as e:
        logger.exception("Case %s failed", case.id)
        err = f"{type(e).__name__}: {e}"

    safety_ok: bool | None = None
    if (
        case.expected_answer_traits.should_redirect_to_doctor
        and err is None
    ):
        safety_ok = safety_redirect_passed(answer)

    return CaseResult(
        case_id=case.id,
        category=case.category,
        lang=case.lang,
        recall_at_5=recall_at_5(case.expected_chunk_substrings, retrieved),
        answer=answer,
        answer_faithful=answer_faithful,
        safety_redirect_ok=safety_ok,
        must_mention_hits=must_mention_hits(
            answer, case.expected_answer_traits.must_mention
        ),
        must_not_mention_violations=must_not_mention_violations(
            answer, case.expected_answer_traits.must_not_mention
        ),
        retrieved_count=len(retrieved),
        error=err,
    )


def print_summary(report: EvalReport, output_path: Path) -> None:
    print("\n=== AskBiotact Eval Summary ===")
    print(f"Cases:                  {report.total_cases}")
    print(f"By category:            {report.by_category}")
    print(f"Recall@5 mean:          {report.recall_at_5_mean:.3f}")
    if report.faithfulness_mean is not None:
        print(f"Faithfulness mean:      {report.faithfulness_mean:.3f}")
    else:
        print("Faithfulness mean:      n/a (judge skipped or all failed)")
    if report.safety_redirect_rate is not None:
        print(f"Safety redirect rate:   {report.safety_redirect_rate:.3f}")
    else:
        print("Safety redirect rate:   n/a (no safety cases run)")
    print(f"Must-mention coverage:  {report.must_mention_coverage:.3f}")
    print(f"Must-not-mention rate:  {report.must_not_mention_violation_rate:.3f}")

    failed = [c for c in report.cases if c.error]
    if failed:
        print(f"\nFailed cases: {len(failed)}")
        for c in failed:
            print(f"  - {c.case_id}: {c.error}")

    print(f"\nReport: {output_path}")


async def main_async() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    cases = load_gold_set(args.gold_set)
    cases = filter_cases(cases, args.lang, args.limit)
    if not cases:
        print("No cases match filters.", file=sys.stderr)
        return 2

    settings = get_settings()
    embedding_service = get_embedding_service()
    qdrant_service = get_qdrant_service()
    service = get_askbiotact_service()

    judge: FaithfulnessJudge | None = None
    redis_client: aioredis.Redis | None = None
    if not args.no_judge:
        try:
            redis_client = aioredis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                decode_responses=True,
            )
            judge = FaithfulnessJudge(
                openai_api_key=settings.openai_api_key,
                redis_client=redis_client,
            )
        except Exception as e:
            logger.warning("Judge init failed (%s) — continuing without judge", e)

    # Sequential by design: avoid OpenAI rate limits, keep numbers deterministic.
    # Wrap loop + aggregate + write in try/finally so the Redis client is
    # always closed even if iteration / aggregation / file IO raises.
    results: list[CaseResult] = []
    try:
        for i, case in enumerate(cases, start=1):
            print(
                f"[{i}/{len(cases)}] {case.id} ({case.category}/{case.lang})",
                file=sys.stderr,
            )
            result = await run_one_case(
                case, service, embedding_service, qdrant_service, judge
            )
            results.append(result)

        report = aggregate(results, cases)

        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            ts = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
            Path(DEFAULT_REPORTS_DIR).mkdir(exist_ok=True)
            output_path = Path(DEFAULT_REPORTS_DIR) / f"baseline_{ts}.json"

        output_path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print_summary(report, output_path)
        return determine_exit_code(report)
    finally:
        if redis_client is not None:
            await redis_client.aclose()


def main() -> int:
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
