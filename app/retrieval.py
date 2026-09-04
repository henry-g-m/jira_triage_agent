from __future__ import annotations

from typing import Any

import requests
from openai import AzureOpenAI, OpenAI

from app.config import Settings
from app.models import Match


class JiraVectorRetriever:
    def __init__(self, settings: Settings):
        self.settings = settings
        if settings.openai_use_azure:
            self.openai = AzureOpenAI(
                api_key=settings.openai_api_key,
                api_version=settings.openai_api_version,
                azure_endpoint=settings.openai_base_url,
            )
        else:
            base_url = settings.openai_base_url.strip() if settings.openai_base_url else "https://api.openai.com/v1"
            self.openai = OpenAI(
                api_key=settings.openai_api_key,
                base_url=base_url,
            )
        self.session = requests.Session()
        self.session.headers.update(
            {
                "X-Username": settings.jira_cosmos_username,
                "X-API-Key": settings.jira_cosmos_api_key,
                "Content-Type": "application/json",
            }
        )

    def embed_text(self, text: str) -> list[float]:
        response = self.openai.embeddings.create(
            model=self.settings.openai_model,
            input=text,
        )
        return response.data[0].embedding

    def _query_collection(self, collection_name: str, embedding: list[float], top_k: int) -> list[dict[str, Any]]:
        payload = {
            "databaseName": self.settings.jira_cosmos_database,
            "collectionName": collection_name,
            "query": {
                "queryText": (
                    "SELECT TOP @topK c.id, c.ProjectKey, c.Summary, c.Description, c.Comments, "
                    "c.Vector, VectorDistance(c.Vector, @embedding) AS similarity "
                    "FROM c ORDER BY VectorDistance(c.Vector, @embedding)"
                ),
                "parameters": {"@topK": top_k, "@embedding": embedding},
            },
        }

        response = self.session.post(self.settings.jira_cosmos_endpoint, json=payload, timeout=30)
        response.raise_for_status()
        body = response.json()
        if isinstance(body, list):
            return body
        if isinstance(body, dict) and isinstance(body.get("value"), list):
            return body["value"]
        if isinstance(body, dict) and "items" in body:
            return body["items"]
        return []

    def search(self, ticket_description: str, top_k: int | None = None) -> list[Match]:
        embedding = self.embed_text(ticket_description)
        limit = top_k or self.settings.cosmos_top_k
        matches: list[Match] = []

        for collection_name in self.settings.jira_cosmos_collections:
            try:
                items = self._query_collection(collection_name, embedding, limit)
            except requests.HTTPError:
                continue

            for item in items:
                issue_key = str(item.get("id") or item.get("IssueKey") or "N/A")
                project = str(item.get("ProjectKey") or item.get("project") or collection_name)
                issue_title = str(item.get("Summary") or item.get("issue_title") or "Untitled issue")
                issue_summary = str(item.get("Description") or item.get("issue_summary") or "")
                comments = item.get("Comments") or item.get("comments") or ""
                if isinstance(comments, list):
                    comments = "\n".join(
                        comment.get("Comment", "") if isinstance(comment, dict) else str(comment)
                        for comment in comments
                    )
                similarity = item.get("similarity", 0.0)
                if not isinstance(similarity, (int, float)):
                    similarity = 0.0
                matches.append(
                    Match(
                        project=project,
                        issue_key=issue_key,
                        issue_title=issue_title,
                        issue_summary=issue_summary,
                        body=issue_summary,
                        comments=str(comments),
                        similarity=float(similarity),
                        metadata={"collection_name": collection_name, **item},
                    )
                )

        matches.sort(key=lambda match: match.similarity, reverse=True)
        return matches[:limit]
