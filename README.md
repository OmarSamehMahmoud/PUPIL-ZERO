# PUPIL ZERO

**Teach an AI. Discover what you really know.**

PUPIL ZERO is a voice-first, curriculum-grounded learning-by-teaching experience for Egyptian school students. Learners explain concepts to an AI classmate; the system asks misconception-driven questions and produces an evidence-linked learning report.

## MVP scope

- Egyptian preparatory-school mathematics (initial demonstrator).
- Arabic-first voice interaction using browser speech APIs where available.
- One AI classmate persona with configurable misconception profiles.
- Deterministic, curriculum-grounded assessment baseline; optional LLM integration is planned but not required to run the starter.
- Teacher-facing session summary.
- No special hardware.

## Project status

Early MVP scaffold. The first release prioritizes a reliable local demo and transparent assessment evidence. It is not an official Ministry of Education product, does not claim Ministry endorsement, and is not a replacement for teachers or formal assessment.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## Curriculum sources and rights

Use the Ministry of Education's official electronic textbook portal as a discovery/source reference:
https://studentbooks.moe.gov.eg/

The Ministry's published materials state that intellectual property rights in the developed curricula belong to the Egyptian state represented by the Ministry. Do not bulk-copy, redistribute, or embed textbook PDFs/content in this repository without confirming permission and applicable terms. This project initially uses original summaries, learning objectives, and original examples aligned to publicly visible syllabus topics. Each curriculum record should retain source URL, academic year, grade, subject, term, and verification date.

## Safety and privacy

- Obtain appropriate parent/guardian and school consent before use with minors.
- Avoid collecting student full names, precise location, face/video, or raw voice recordings by default.
- Browser speech recognition support varies by browser and may use vendor cloud services; disclose this clearly. Text mode is always available.
- AI feedback is formative and must be reviewable by a teacher.
- Never use the score as a psychological diagnosis or a high-stakes grade.

## Planned architecture

FastAPI + SQLite for the first local prototype; browser-native speech recognition/synthesis; a replaceable persona/assessment service; later integrations can add a self-hosted speech stack and an LLM provider behind explicit configuration.

## License

No license is granted for Ministry textbook materials. Source-code licensing will be selected separately before public distribution.
