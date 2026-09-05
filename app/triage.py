from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from openai import AzureOpenAI, OpenAI

from app.models import Match, Recommendation


class TicketTriageAgent:
    def __init__(self, model_client: Any | None = None, llm_model: str = "gpt-4o-mini", use_llm: bool = True):
        self.model_client = model_client
        self.llm_model = llm_model
        self.use_llm = use_llm

    @classmethod
    def from_settings(cls, settings: Any) -> "TicketTriageAgent":
        model_client = None
        llm_api_key = settings.llm_api_key or settings.openai_api_key
        llm_base_url = settings.llm_base_url or settings.openai_base_url or "https://api.openai.com/v1"
        llm_uses_azure = "openai.azure.com" in llm_base_url.lower()

        try:
            if settings.llm_api_key and settings.llm_base_url:
                if llm_uses_azure:
                    model_client = AzureOpenAI(
                        api_key=llm_api_key,
                        api_version=settings.openai_api_version,
                        azure_endpoint=settings.llm_base_url.rstrip("/"),
                    )
                else:
                    model_client = OpenAI(
                        api_key=llm_api_key,
                        base_url=settings.llm_base_url.rstrip("/"),
                    )
            elif settings.openai_use_azure:
                model_client = AzureOpenAI(
                    api_key=llm_api_key,
                    api_version=settings.openai_api_version,
                    azure_endpoint=settings.openai_base_url.rstrip("/"),
                )
            else:
                model_client = OpenAI(
                    api_key=llm_api_key,
                    base_url=llm_base_url.rstrip("/"),
                )
        except Exception:
            model_client = None

        return cls(
            model_client=model_client,
            llm_model=settings.llm_model,
            use_llm=bool(settings.llm_model and llm_api_key),
        )

    def recommend(self, matches: list[Match], ticket_description: str | None = None) -> Recommendation:
        if not matches:
            raise ValueError("No matches were found for the provided ticket description.")

        if self.use_llm and self.model_client is not None and ticket_description:
            try:
                print("Using LLM for triage recommendation...")
                return self._recommend_with_llm(matches, ticket_description)
            except Exception:
                print("ERROR: LLM recommendation failed, falling back to heuristic-based recommendation.")

        return self._recommend_with_heuristics(matches)

    def _recommend_with_llm(self, matches: list[Match], ticket_description: str) -> Recommendation:
        print("Building recommendation based on semantic similarity and historical matches from Vector DB")
        prompt = self._build_llm_prompt(ticket_description, matches)
        print(f"LLM Prompt:\n{prompt}\n")
        response = self.model_client.chat.completions.create(
            model=self.llm_model,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a Jira triage assistant. Choose the single best-fit Jira project for a new ticket "
                        "using only the historical issue evidence provided. Return only valid JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        content = response.choices[0].message.content or "{}"
        parsed = self._safe_json_loads(content)
        if not parsed:
            raise ValueError("LLM did not return valid JSON for triage recommendation.")
        project = str(parsed.get("project") or "").strip()
        if not project:
            raise ValueError("LLM did not provide a valid project recommendation.")

        confidence = parsed.get("confidence")
        try:
            confidence_score = float(confidence) if confidence is not None else 0.7
        except (TypeError, ValueError):
            confidence_score = 0.7

        rationale = str(parsed.get("rationale") or f"The ticket aligns best with {project} based on historical issue patterns.")
        guidance = parsed.get("guidance") or [
            f"Recommended project: {project}",
            "Include reproduction steps, expected behavior, and user impact before submitting the ticket.",
        ]
        if isinstance(guidance, str):
            guidance = [guidance]

        return Recommendation(
            project=project,
            confidence=max(0.5, min(0.99, confidence_score)),
            rationale=rationale,
            matches=matches[:3],
            guidance=list(guidance),
        )

    def _recommend_with_heuristics(self, matches: list[Match]) -> Recommendation:
        project_scores: dict[str, float] = defaultdict(float)

        for match in matches:
            weighted_similarity = 1.0 / (1.0 + max(0.0, match.similarity))
            project_scores[match.project] += weighted_similarity

        ranked_projects = sorted(project_scores.items(), key=lambda item: item[1], reverse=True)
        selected_project, selected_score = ranked_projects[0]

        relevant_matches = [match for match in matches if match.project == selected_project][:3]
        rationale = (
            f"The ticket best aligns with {selected_project} based on {len(relevant_matches)} "
            f"historical matches and the strongest semantic similarity among retrieved Jira content."
        )

        guidance = self._build_guidance(selected_project, relevant_matches)
        confidence = min(0.99, max(0.5, selected_score / max(len(matches), 1)))

        return Recommendation(
            project=selected_project,
            confidence=confidence,
            rationale=rationale,
            matches=relevant_matches,
            guidance=guidance,
        )

    def _build_guidance(self, project: str, matches: list[Match]) -> list[str]:
        combined_text = "\n".join(
            [f"{match.issue_title}: {match.issue_summary}" for match in matches]
        ).lower()

        guidance: list[str] = [
            f"Recommended project: {project}",
            "Include a clear summary of the issue, user impact, and urgency.",
            "State the exact business or technical symptoms observed, including error messages or unexpected behavior.",
        ]

        if any(keyword in combined_text for keyword in ["bug", "error", "fail", "broken", "exception"]):
            guidance.append("Add reproduction steps, affected environment details, and any relevant logs or stack traces.")

        if any(keyword in combined_text for keyword in ["feature", "request", "enhancement", "improvement", "idea"]):
            guidance.append("Explain the business value, expected outcome, and acceptance criteria for the requested change.")

        if any(keyword in combined_text for keyword in ["incident", "outage", "urgent", "downtime", "severity"]):
            guidance.append("Include customer impact, timeline, affected systems, and any mitigation already in progress.")

        if any(keyword in combined_text for keyword in ["security", "vulnerability", "auth", "permission", "access"]):
            guidance.append("Document the exposure, affected identity or data, and any immediate containment actions.")

        guidance.append("Provide a concrete expected outcome so the team can triage the issue and assign the right owner quickly.")
        return guidance

    def _build_llm_prompt(self, ticket_description: str, matches: list[Match]) -> str:
        serialized_matches = []
        for index, match in enumerate(matches[:5], start=1):
            serialized_matches.append(
                {
                    "rank": index,
                    "project": match.project,
                    "issue_key": match.issue_key,
                    "issue_title": match.issue_title,
                    "summary": match.issue_summary,
                    "similarity": round(match.similarity, 4),
                }
            )

        return json.dumps(
            {
                "new_ticket": ticket_description,
                "historical_matches": serialized_matches,
                "instructions": [
                    "Pick the single best Jira project.",
                    "Use the historical matches to justify the choice in 1-2 sentences.",
                    "Return a confidence score between 0 and 1.",
                    "Provide a short actionable guidance list for the ticket submitter.",
                ],
            },
            indent=2,
        )

    def _safe_json_loads(self, content: str) -> dict[str, Any] | None:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].lstrip()
        try:
            payload = json.loads(text)
            if isinstance(payload, dict):
                return payload
        except Exception:
            return None
        return None
