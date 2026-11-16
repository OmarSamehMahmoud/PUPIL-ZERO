# PUPIL ZERO

**Prototype version: 1.0.0**

**Teach an AI. Discover what you really know.**

PUPIL ZERO is an Arabic-first, learning-by-teaching prototype. A learner explains a topic to an AI classmate, receives curious follow-up questions, and can review a formative evidence report. A teacher can inspect locally stored sessions through a simple dashboard.

## Current features

- FastAPI backend and SQLite session history.
- Local teacher accounts with scrypt password hashing, opaque random sessions stored as SHA-256 token digests, HttpOnly/SameSite cookies, login/logout, and a protected teacher dashboard/API.
- Classroom registry: teachers can create classes with join codes, students can create accounts and join with a code, and teachers can view their class roster.
- Arabic account portal at `/account`.
- Arabic RTL student experience, responsive layout, text chat, and optional browser speech input/output.
- Three selectable classmates: MILO, NOURA, and ZIZO. Each has a distinct prompt profile.
- Cross-session adaptive scenario selection: a new session can start with an authored scenario matching a concept flagged for review in the learner's previous sessions. The routing reason is returned by the session API; no difficulty or mastery claim is made.
- Persistent adaptive dialogue state per session: elicit, clarify, transfer, and reflect stages, with misconception review targets. These are conversation-routing signals, not mastery labels.
- Three original mathematics demonstrator lessons: fractions, decimals, and introductory ratios.
- Local Ollama integration and OpenAI-compatible chat endpoint support.
- Explicit demo fallback when no model is configured; if a configured model is unavailable, the app reports an error instead of pretending demo text is live AI.
- Teacher intervention planner: creates a four-step, 15-minute review suggestion from the selected lesson's authored concept explanation and existing scenarios. The teacher must review, adapt, and decide whether to use it; it is not automatically assigned.
- Anonymous teacher feedback loop for intervention plans: optional helpful / partly helpful / not helpful rating plus a short note, with aggregate counts only. Notes are not exposed by summary endpoints; fewer than three ratings are labelled a small sample. Feedback does not automatically change plans or judge student learning.
- Teacher dashboard at `/teacher` with session list, transcript detail, conservative keyword-evidence signals, lesson-level class insight aggregation, evidence-grounded review-priority suggestions with small-sample warnings, and an anonymous learner journey that compares per-session evidence over time.

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
   - Account portal: http://127.0.0.1:8000/account
   - Teacher dashboard (requires teacher login): http://127.0.0.1:8000/teacher
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

Tests are committed and a GitHub Actions workflow runs them on pushes and pull requests. Check GitHub for the latest workflow result; do not assume it passed until a completed run is visible.

## API

- `POST /api/auth/register-teacher` — create a local teacher account (password minimum 10 characters).
- `POST /api/auth/login` / `POST /api/auth/logout` — sign in/out using an HttpOnly local session cookie.
- `GET /api/auth/me` — current account profile.
- `POST /api/classes` — create a class as the authenticated teacher; returns an eight-character join code.
- `GET /api/classes` — list the authenticated teacher's classes.
- `GET /api/classes/{class_id}/members` — list members of a class owned by the authenticated teacher.
- `POST /api/classes/join` — create a student account and enroll it using a class join code.

- `GET /api/health` — app and configured inference mode.
- `GET /api/lessons` — demonstrator lesson catalog.
- `POST /api/sessions` — create a session. JSON: `{"lesson_id":"fractions","persona":"milo"}`.
- `POST /api/message` — send a student explanation. JSON: `{"session_id":"...","text":"..."}`.
- `POST /api/finish` — return transcript, formative evidence report, and current dialogue state.
- `GET /api/teacher/sessions` — recent local sessions.
- `GET /api/teacher/sessions/{session_id}` — transcript and report for one session.
- `GET /api/teacher/insights` — aggregate evidence and review signals by lesson; optional `lesson_id` filter. These are not mastery scores.
- `GET /api/teacher/priorities` — rank concepts flagged for teacher review;
- `GET /api/teacher/interventions?lesson_id=fractions&concept_id=unit_fraction` — create a teacher-reviewed suggestion from authored lesson content, including anonymous feedback counts.
- `POST /api/teacher/interventions/feedback` — save a teacher rating (`helpful`, `partly_helpful`, or `not_helpful`) and optional note (maximum 500 characters).
- `GET /api/teacher/interventions/feedback?lesson_id=fractions&concept_id=unit_fraction` — retrieve aggregate ratings only; individual notes are never returned. Fewer than three ratings are labelled a small sample.
- `GET /api/learner/journey/{learner_id}` — chronological evidence history for an anonymous learner UUID. The student browser stores this random key locally and reuses it across sessions; clearing browser storage loses the association for future sessions. This is not a verified student identity or a validated measure of retention.

## Curriculum status and rights

The lesson content in this repository is original demonstrator content, not copied textbook pages. Exact grade, term, and topic mapping for the current Egyptian curriculum is **not verified**. The official electronic textbook portal is https://studentbooks.moe.gov.eg/; check the current edition and applicable reuse permissions before claiming curriculum alignment or importing source material. The project does not claim Ministry endorsement.

## Safety, privacy, and limitations

- This is an authentication and class-management foundation, not a production-ready multi-school deployment. Existing learning sessions and aggregate reports have not yet been fully linked to class memberships and teacher ownership; do not use it to store real student records or expose it to a school network/public internet yet.
- Student class enrollment is implemented, but a complete student sign-in/classroom learning portal and class-scoped learning history are still pending.
- Account registration is open in this local prototype. Before deployment, add administrator-controlled teacher invitations, rate limiting, password reset/recovery, secure HTTPS cookie configuration, CSRF protection appropriate to the deployment, audit logging, and a reviewed data-retention/deletion workflow.
- Before any real pilot with minors, obtain school and parent/guardian approvals, define retention/deletion rules, and implement authentication and access controls.
- Avoid collecting names, phone numbers, precise location, face/video, or raw voice recordings. The journey feature uses a random browser-local UUID rather than a name or account; it is a pseudonymous identifier, so protect the local database and browser profile.
- Local Ollama inference sends text to the configured local Ollama endpoint. Do not configure a remote endpoint if local-only processing is required.
- Browser speech recognition may use a browser vendor's cloud service and is not guaranteed offline. Text chat remains available.
- The report is a simple keyword-matching signal, not a validated measure of learning and not a school grade. Teacher review is required.
- AI output may be wrong. This prototype is not a replacement for a teacher or formal assessment.

## License

No license is granted for Ministry textbook materials. A source-code license should be selected before public distribution.
