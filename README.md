# Jira Triage Agent

A Python CLI app that embeds a new Jira ticket description, queries the live Jira collections, finds the closest historical issue context, recommends the most likely Jira project, and provides tailored guidance to improve ticket quality.

## Features
- Uses the OpenAI embedding model to convert the incoming issue text into a vector.
- Queries the live Jira Cosmos endpoint with the request shape required by the provided API.
- Searches across the available Jira collections (`jira_coll_*`) to find the best semantic matches.
- Recommends the best Jira project based on similarity and historical evidence.
- Generates issue-quality guidance tailored to the likely ticket type.
- Exposes a command-line interface for support and triage teams.

## Setup
1. Create a virtual environment and install dependencies:

   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt

2. Create a local settings file named `config.txt` (or copy the example) and fill in the required values:

   copy config.txt.example config.txt

3. Set the following variables in `config.txt`:
   - `OPENAI_API_KEY`
   - `OPENAI_BASE_URL` (optional custom OpenAI-compatible endpoint)
   - `JIRA_COSMOS_ENDPOINT`
   - `JIRA_COSMOS_USERNAME`
   - `JIRA_COSMOS_API_KEY`
   - `JIRA_COSMOS_DATABASE`
   - `JIRA_COSMOS_COLLECTIONS`
   - optionally `OPENAI_MODEL`, `JIRA_VECTOR_FIELD`, `COSMOS_TOP_K`

   Values can also still be supplied through a `.env` file, but the app will prefer a `config.txt` file if present.

## Usage
Run the CLI with a ticket description:

   .\.venv\Scripts\python.exe -m app -- "Customers are unable to log in after MFA reset and receive a 403 error in production."

The app returns a JSON payload with the recommended project, confidence, matching historical issues, and ticket-quality guidance.

## Notes
This implementation was built against the live API contract used by the Jira collections:
- databaseName and collectionName are required in the outer payload
- the inner query object uses `queryText` and `parameters`
- the historical documents include `ProjectKey`, `Summary`, `Description`, `Comments`, and a `Vector` field for similarity search
