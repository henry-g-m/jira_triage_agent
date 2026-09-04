import unittest

from app.models import Match
from app.triage import TicketTriageAgent


class TicketTriageAgentTests(unittest.TestCase):
    def test_recommend_prefers_project_with_strongest_match(self):
        agent = TicketTriageAgent()
        matches = [
            Match(project="Platform", issue_key="PLAT-101", issue_title="Login failures after MFA reset", issue_summary="Users are seeing 403 after MFA reset", similarity=0.12),
            Match(project="Support", issue_key="SUP-552", issue_title="Customer unable to access portal", issue_summary="User reports portal access issue", similarity=0.42),
            Match(project="Platform", issue_key="PLAT-202", issue_title="Production 403 with MFA", issue_summary="401/403 errors in production", similarity=0.18),
        ]

        recommendation = agent.recommend(matches)
        self.assertEqual(recommendation.project, "Platform")
        self.assertTrue(recommendation.guidance)

    def test_guidance_includes_reproduction_details_for_bug_patterns(self):
        agent = TicketTriageAgent()
        matches = [
            Match(project="Platform", issue_key="PLAT-300", issue_title="Production bug", issue_summary="Users hit exception after login attempt", similarity=0.05),
        ]

        recommendation = agent.recommend(matches)
        self.assertTrue(any("reproduction" in item.lower() for item in recommendation.guidance))


if __name__ == "__main__":
    unittest.main()
