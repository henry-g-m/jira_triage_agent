import unittest

from app.models import Match
from app.triage import TicketTriageAgent


class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeChat:
    def __init__(self, payload):
        self.payload = payload

    class Completions:
        def __init__(self, payload):
            self.payload = payload

        def create(self, **kwargs):
            return type(
                "FakeResponse",
                (),
                {"choices": [FakeChoice(self.payload)]},
            )()

    @property
    def completions(self):
        return FakeChat.Completions(self.payload)


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

    def test_llm_recommendation_uses_model_output_when_available(self):
        fake_llm = type(
            "FakeLLM",
            (),
            {
                "chat": type(
                    "FakeChat",
                    (),
                    {
                        "completions": type(
                            "FakeCompletions",
                            (),
                            {
                                "create": lambda self, **kwargs: type(
                                    "FakeResponse",
                                    (),
                                    {
                                        "choices": [
                                            FakeChoice(
                                                '{"project":"CAM","confidence":0.87,"rationale":"This is a catalog issue.","guidance":["Include reproduction steps.","State the expected result."]}'
                                            )
                                        ]
                                    },
                                )()
                            },
                        )()
                    },
                )
            },
        )()
        agent = TicketTriageAgent(model_client=fake_llm, llm_model="gpt-4o-mini", use_llm=True)
        matches = [
            Match(project="CAM", issue_key="CAM-1", issue_title="Catalog quantity issue", issue_summary="Quantity stays at 0 when entering a number", similarity=0.72),
            Match(project="SUPPORT", issue_key="SUP-2", issue_title="General portal issue", issue_summary="Portal has user issue", similarity=0.41),
        ]

        recommendation = agent.recommend(matches, ticket_description="Cannot add quantity to a catalog item.")
        self.assertEqual(recommendation.project, "CAM")
        self.assertTrue(recommendation.guidance)

    def test_query_expander_returns_rewritten_query(self):
        class FakeQueryLlm:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kwargs):
                        return type(
                            "FakeResponse",
                            (),
                            {"choices": [FakeChoice("catalog quantity field manually set to zero issue")]},
                        )()

        from app.retrieval import QueryExpander
        from app.config import Settings

        settings = Settings(
            openai_api_key="test-key",
            openai_base_url="https://api.openai.com/v1",
            llm_api_key="llm-key",
            llm_base_url="https://example.com/v1",
            llm_model="kimi-k3",
            jira_cosmos_endpoint="https://example.test",
            jira_cosmos_username="user",
            jira_cosmos_api_key="cosmos-key",
            jira_cosmos_database="jira_db",
            jira_cosmos_collections=("jira_coll_ccrt",),
        )

        expander = QueryExpander.__new__(QueryExpander)
        expander.settings = settings
        expander.model_name = "kimi-k3"
        expander.client = FakeQueryLlm()

        expanded = expander.expand("User cannot add quantity to a catalog item.")
        self.assertIn("catalog", expanded.lower())
        self.assertIn("quantity", expanded.lower())

    def test_from_settings_prefers_llm_override_over_azure_embedding_base(self):
        from app.config import Settings

        settings = Settings(
            openai_api_key="azure-key",
            openai_base_url="https://prosqa2usc.openai.azure.com",
            openai_model="text-embedding-3-large",
            llm_api_key="nim-key",
            llm_base_url="https://integrate.api.nvidia.com/v1",
            llm_model="moonshotai/kimi-k3",
            jira_cosmos_endpoint="https://example.test",
            jira_cosmos_username="user",
            jira_cosmos_api_key="cosmos-key",
            jira_cosmos_database="jira_db",
            jira_cosmos_collections=("jira_coll_ccrt",),
        )

        agent = TicketTriageAgent.from_settings(settings)
        self.assertIsNotNone(agent.model_client)
        self.assertTrue(agent.use_llm)
        self.assertEqual(agent.llm_model, "moonshotai/kimi-k3")


if __name__ == "__main__":
    unittest.main()
