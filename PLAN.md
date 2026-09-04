# Jira Triage Agent Plan

## Findings
- The workspace is currently a minimal Python project scaffold with no existing application source files.
- The vector index already exists and was populated using OpenAI text-embedding-3-large, so the project should reuse the existing index rather than re-index historical Jira data.
- The user requirement is specifically for a Python application that:
  - embeds a new user ticket description,
  - retrieves similar historical Jira project / issue / comment context,
  - recommends the most appropriate Jira project,
  - and provides tailored guidance on what details the ticket should contain.
- The target interface has been defined as a CLI tool.
- We retried the live Cosmos connection using the provided endpoint and credentials. The host resolves successfully and the port is reachable, but the API rejects the initial request payload because the service uses a wrapped request model with required fields that were not fully known.
- The response indicates that the API expects a message-wrapped request schema and enforces validation for `Query`, `DatabaseName`, and `CollectionName`. This means the exact collection name and request serialization remain the missing pieces for a successful live query.

## Decisions
1. Use a Python CLI as the primary app interface.
   - Keep the workflow simple and operationally friendly for triage and intake use.
   - Design the entrypoint to accept a free-text ticket description and produce a recommendation + guidance output.

2. Reuse the existing vector database and embeddings model.
   - Avoid rebuilding the index.
   - Treat the existing collection as the source of truth for semantic retrieval.
   - Use the same embedding model family (OpenAI embeddings) for the newly submitted ticket text.

3. Recommend the project using semantic retrieval, not static rules only.
   - Search the historical Jira corpus for the nearest matches to the incoming ticket.
   - Aggregate the highest-signal matched projects/issues and rank by similarity and supporting evidence.
   - Use retrieved issue metadata and comments to explain project choice.

4. Generate guidance from historical ticket patterns.
   - For the recommended project, infer the likely ticket type from similar issues.
   - Map that to the information usually required for that track, such as impact, reproduction, environment, acceptance criteria, stakeholders, logs, timelines, or blockers.
   - Present this as advice the submitter can use to improve ticket quality before creation.

5. Keep implementation modular and lightweight.
   - Separate concerns into: configuration, retrieval, recommendation, guidance, and CLI layers.
   - Use environment variables for all secrets and runtime settings.

## Proposed architecture
- app/
  - cli.py
  - config.py
  - models.py
  - retrieval.py
  - triage.py
  - guidance.py
- requirements.txt
- .env.example
- README.md

## Implementation plan
1. Define the CLI contract and required arguments.
   - Input: ticket description (and optional project hints if needed later)
   - Output: recommended Jira project, confidence, similar historical matches, and ticket-quality guidance

2. Confirm runtime configuration contract.
   - OpenAI API key / endpoint configuration
   - Vector database connection settings
   - Collection/index names and any metadata field names

3. Build the retrieval layer.
   - Embed the user’s ticket text with the same model used in the existing vector database.
   - Run similarity search in the historical Jira index.
   - Return top matches with project, issue, and comment context.

4. Build the recommendation engine.
   - Group matches by Jira project.
   - Score by semantic similarity, recency, and frequency of matching issue patterns.
   - Choose the best candidate project and include a rationale.

5. Build the guidance engine.
   - Identify the likely ticket type from the matched issues.
   - Generate a checklist or guidance tailored to the selected project and issue pattern.
   - Include missing-information prompts the user should address.

6. Validate with sample tickets.
   - Test with representative Jira issue descriptions spanning bug reports, feature requests, incidents, and support requests.
   - Verify that the recommended project and guidance are aligned with historical evidence.

## Risks and mitigations
- Risk: vector index schema is not fully known.
  - Mitigation: inspect the existing index metadata and document the schema before implementing query logic.
- Risk: guidance may be too generic.
  - Mitigation: anchor guidance to the retrieved historical tickets and project patterns.
- Risk: improper project recommendations from weak matches.
  - Mitigation: apply ranking thresholds and show the top supporting evidence to the user.

## Next steps
- Inspect the existing vector database schema and metadata contract.
- Implement the CLI structure and config handling.
- Build the retrieval and scoring flow.
- Add project recommendation and guidance generation.
- Run a focused end-to-end validation with real sample descriptions.
