# PUPIL ZERO

**Teach an AI. Discover what you really know.**

PUPIL ZERO is an Arabic-first, learning-by-teaching prototype. A learner explains a topic to an AI classmate, receives curious follow-up questions, and can review a formative evidence report. A teacher can inspect locally stored sessions through a simple dashboard.

## Current features

- FastAPI backend and SQLite session history.
- Arabic RTL student experience, responsive layout, text chat, and optional browser speech input/output.
- Three selectable classmates: MILO, NOURA, and ZIZO. Each has a distinct prompt profile.
- Three original mathematics demonstrator lessons: fractions, decimals, and introductory ratios.
- Local Ollama integration and OpenAI-compatible chat endpoint support.
- Explicit demo fallback when no model is configured; if a configured model is unavailable, the app reports an error instead of pretending demo text is live AI.
- Teacher dashboard at `/teacher` with session list, transcript detail, and conservative keyword-evidence signals.

## Run locally with Ollama

1. Install Ollama and start it on the same computer.
2. Pull a model supported by your hardware. Example:

   ```bash
   ollama pull qwen3.5:4b-q4_K_M
   ```

3. From the repository folder, create and activate a virtual environment:

   ```bash
   python -m venv .venv
   # Windows PowerShell:
   .venv\\Scripts\\Activate.ps1
   # macOS/Linux:
   source .venv/bin/activate
   ```

4. Install requirements and create the environment file:

   ```bash
   pip install -r requirements.txt
   # Windows:
   copy .env.example .env
   # macOS/Linux:
   cp .env.example .env
   ```

5. Edit `.env` and use the exact model tag shown by `ollama list`:

   ```dotenv
   PUPIL_LLM_PROVIDER=ollama
   PUPIL_LLM_BASE_URL=http://127.0.0.1:11434
   PUPIL_LLM_MODEL=qwen3.5:4b-q4_K_M
   PUPIL_LLM_API_KEY=
   ```

6. Start the application:

   ```bash
   uvicorn app.main:app --reload
   ```

7. Open:
   - Student experience: http://127.0.0.1:8000
   - Teacher dashboard: http://127.0.0.1:8000/teacher
   - API health: http://127.0.0.1:8000/api/health
   - Interactive API docs: http://127.0.0.1:8000/docs

Without a configured provider/model, the app uses a clearly labelled deterministic demo mode. A configured but unreachable model produces an error; it does not silently switch to demo mode.

## OpenAI-compatible local inference

Set `PUPIL_LLM_PROVIDER=openai-compatible`, `PUPIL_LLM_BASE_URL` to the server base URL (without `/v1/chat/completions`), and `PUPIL_LLM_MODEL` to its model identifier. Set `PUPIL_LLM_API_KEY` only when required by that endpoint.

## Tests

Install development dependencies and run:

```bash
pip install -r requirements-dev.txt
pytest -q
```

Tests are committed but have not been executed in the maintainer's environment as part of this update. Run them locally before relying on the build.

## API

- `GET /api/health` — app and configured inference mode.
- `GET /api/lessons` — demonstrator lesson catalog.
- `POST /api/sessions` — create a session. JSON: `{"lesson_id":"fractions","persona":"milo"}`.
- `POST /api/message` — send a student explanation. JSON: `{"session_id":"...","text":"..."}`.
- `POST /api/finish` — return transcript and formative evidence report.
- `GET /api/teacher/sessions` — recent local sessions.
- `GET /api/teacher/sessions/{session_id}` — transcript and report for one session.

## Curriculum status and rights

The lesson content in this repository is original demonstrator content, not copied textbook pages. Exact grade, term, and topic mapping for the current Egyptian curriculum is **not verified**. The official electronic textbook portal is https://studentbooks.moe.gov.eg/; check the current edition and applicable reuse permissions before claiming curriculum alignment or importing source material. The project does not claim Ministry endorsement.

## Safety, privacy, and limitations

- The teacher dashboard currently has no authentication or role-based access. Keep the service bound to localhost; do not expose it to a school network or the public internet in this state.
- Before any real pilot with minors, obtain school and parent/guardian approvals, define retention/deletion rules, and implement authentication and access controls.
- Avoid collecting names, phone numbers, precise location, face/video, or raw voice recordings.
- Local Ollama inference sends text to the configured local Ollama endpoint. Do not configure a remote endpoint if local-only processing is required.
- Browser speech recognition may use a browser vendor's cloud service and is not guaranteed offline. Text chat remains available.
- The report is a simple keyword-matching signal, not a validated measure of learning and not a school grade. Teacher review is required.
- AI output may be wrong. This prototype is not a replacement for a teacher or formal assessment.

## License

No license is granted for Ministry textbook materials. A source-code license should be selected before public distribution.
