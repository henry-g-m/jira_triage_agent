# Jira Triage Agent Plan

## Findings
- The project is now implemented as a Python CLI that reuses the existing vectorized Jira corpus instead of re-indexing historical issues.
- The retrieval layer is working with the live Cosmos API contract and the embedding model remains on OpenAI (`text-embedding-3-large`).
- The LLM recommendation path was failing because the runtime incorrectly treated the Azure embeddings endpoint as the LLM provider even when a separate NVIDIA/Kimi LLM override was configured.
- The app must prefer the explicit LLM override (`LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`) over the embedding endpoint when building the recommendation client.
- The current implementation still keeps the retrieval flow primary and uses the LLM as a secondary recommendation/query-expansion layer with heuristic fallback when needed.

## Decisions
1. Use a Python CLI as the primary app interface.
   - Keep the workflow simple and operationally friendly for triage and intake use.
   - Design the entrypoint to accept a free-text ticket description and produce a recommendation + guidance output.

2. Reuse the existing vector database and embeddings model.
   - Avoid rebuilding the index.
   - Treat the existing collection as the source of truth for semantic retrieval.
   - Use the same embedding model family (OpenAI embeddings) for the newly submitted ticket text.

3. Prefer explicit LLM runtime overrides over generic Azure/OpenAI defaults.
   - When `LLM_API_KEY` and `LLM_BASE_URL` are present, build the recommendation client against that provider.
   - This is required for NVIDIA NIM and Kimi endpoints that are OpenAI-compatible but not Azure-hosted.

4. Recommend the project using semantic retrieval and LLM synthesis, not static rules only.
   - Search the historical Jira corpus for the nearest matches to the incoming ticket.
   - Use the LLM to synthesize the project choice and guidance from those evidence-based matches.
   - Keep the heuristic result as a fallback only when the LLM is unavailable or returns invalid output.

5. Keep implementation modular and lightweight.
   - Separate concerns into: configuration, retrieval, recommendation, guidance, and CLI layers.
   - Use environment variables and local config files for secrets and runtime settings.

## Current implementation status
- CLI, config, retrieval, and triage modules are in place.
- The project is validated via focused unit tests for recommendation logic and query expansion.
- The outstanding issue was provider selection for the LLM recommendation client: the app was incorrectly preferring Azure detection from the embeddings endpoint instead of the explicit LLM override.

## Next steps
- Keep the OpenAI embedding model for vectors.
- Keep the LLM recommendation model on the configured override provider (Kimi/NVIDIA/OpenAI-compatible) when present.
- Validate the real LLM/endpoint response format from the actual runtime before relying on JSON mode in production.
- Continue end-to-end testing with representative sample tickets against the live Jira corpus.
