# PUPIL ZERO

**Teach an AI. Discover what you really know.**

PUPIL ZERO is an Arabic-first, learning-by-teaching experience for Egyptian school students. A learner explains a topic to an AI classmate; the classmate asks follow-up questions, and the session produces a transparent, teacher-reviewable evidence report.

## Current build

- FastAPI + SQLite session storage.
- Arabic RTL student interface with text chat and optional browser speech input/output. The interface has no required remote font or CDN dependency.
- Three character profiles in the local AI prompt (MILO, NOURA, ZIZO); MILO is currently selected by the starter screen.
- Live model integration through a local Ollama server or an OpenAI-compatible endpoint.
- Deterministic fallback mode when no model is configured. The interface labels this as a demo; it is not represented as live AI.
- Initial fractions lesson is original demonstrator content. Exact grade/term alignment with the current Egyptian Ministry curriculum is not yet verified.

## Run with local Ollama (recommended for offline use)

1. Install and start Ollama on the same computer.
2. Download a model supported by your machine. Example:

   ```bash
   ollama pull qwen3.5:4b-q4_K_M
   ```

   Use a model already available in your Ollama library if you prefer.
3. Create and activate a Python environment:

   ```bash
   python -m venv .venv
   # Windows PowerShell:
   .venv\\Scripts\\Activate.ps1
   # macOS/Linux:
   source .venv/bin/activate
   ```
4. Install dependencies and create the environment file:

   ```bash
   pip install -r requirements.txt
   # Windows:
   copy .env.example .env
   # macOS/Linux:
   cp .env.example .env
   ```
5. Open `.env` and set the exact model tag shown by `ollama list`:

   ```dotenv
   PUPIL_LLM_PROVIDER=ollama
   PUPIL_LLM_BASE_URL=http://127.0.0.1:11434
   PUPIL_LLM_MODEL=qwen3.5:4b-q4_K_M
   ```
6. Start the app:

   ```bash
   uvicorn app.main:app --reload
   ```

7. Open http://127.0.0.1:8000. The header should show **إعداد الذكاء الاصطناعي المحلي** when the provider and model are configured.

If you do not configure a model, PUPIL ZERO runs in clearly labelled demo fallback mode. If a configured model is unreachable, the chat reports an error instead of silently pretending that a canned response came from AI.

## OpenAI-compatible local servers

Set `PUPIL_LLM_PROVIDER=openai-compatible`, `PUPIL_LLM_BASE_URL` to the server base URL (without `/v1/chat/completions`), and `PUPIL_LLM_MODEL` to its model identifier. Set `PUPIL_LLM_API_KEY` only if the server requires one.

## Run automated tests

Install the development test dependency and run the suite:

```bash
pip install -r requirements-dev.txt
pytest -q
```

## API

- `GET /api/health` — health and active AI/demo mode.
- `GET /api/lessons` — available starter lessons.
- `POST /api/sessions` — create a session.
- `POST /api/message` — send a learner explanation and receive the classmate's response.
- `POST /api/finish` — return transcript and formative evidence report.

## Curriculum sources and rights

The Ministry of Education's official electronic textbook portal is the source to verify grade, subject, term, and topic mapping:
https://studentbooks.moe.gov.eg/

The Ministry's published materials state that intellectual property rights in developed curricula belong to the Egyptian state represented by the Ministry. Do not bulk-copy, redistribute, or embed textbook PDFs/content in this repository without confirming permission and applicable terms. This project uses original summaries, objectives, and examples; it does not claim official Ministry endorsement.

## Safety, privacy, and limitations

- Obtain appropriate parent/guardian and school consent before use with minors.
- Avoid collecting student names, precise location, face/video, or raw voice recordings by default.
- Text chat with local Ollama stays on the configured local endpoint. Do not configure a remote endpoint if local-only processing is required.
- Browser speech recognition support varies and may use a browser vendor's cloud service. Voice input is therefore not guaranteed to be offline; text mode is available.
- The report uses explainable keyword signals, not a validated educational measurement or grade. Teacher review is required.
- AI responses can be wrong. This is a prototype, not a replacement for a teacher or formal assessment.

## Development status

This is an actively evolving MVP. Automated tests are included but must be run in the target environment before treating a build as verified. The current lesson catalog is intentionally small; curriculum expansion should follow source verification and original-content authoring.

## License

No license is granted for Ministry textbook materials. Source-code licensing will be selected separately before public distribution.
