from __future__ import annotations

from collections import defaultdict

from app.models import Match, Recommendation


class TicketTriageAgent:
    def recommend(self, matches: list[Match]) -> Recommendation:
        if not matches:
            raise ValueError("No matches were found for the provided ticket description.")

        project_scores: dict[str, float] = defaultdict(float)
        project_mentions: dict[str, list[str]] = defaultdict(list)

        for match in matches:
            weighted_similarity = 1.0 / (1.0 + max(0.0, match.similarity))
            project_scores[match.project] += weighted_similarity
            project_mentions[match.project].append(match.issue_title)

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
