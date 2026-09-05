from __future__ import annotations

import argparse
import json
from typing import Sequence

from app.config import Settings
from app.retrieval import JiraVectorRetriever
from app.triage import TicketTriageAgent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Recommend the best Jira project from a ticket description.")
    parser.add_argument("description", help="Free-text ticket description to triage.")
    parser.add_argument("--top-k", type=int, default=None, help="Number of similar historical matches to retrieve.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = Settings.from_env()
    retriever = JiraVectorRetriever(settings)
    triage_agent = TicketTriageAgent.from_settings(settings)

    matches = retriever.search(args.description, top_k=args.top_k)
    recommendation = triage_agent.recommend(matches, ticket_description=args.description)

    payload = {
        "project": recommendation.project,
        "confidence": round(recommendation.confidence, 4),
        "rationale": recommendation.rationale,
        "matches": [
            {
                "project": match.project,
                "issue_key": match.issue_key,
                "issue_title": match.issue_title,
                "issue_summary": match.issue_summary,
                "similarity": round(match.similarity, 4),
            }
            for match in recommendation.matches
        ],
        "guidance": recommendation.guidance,
    }

    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
