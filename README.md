# PUPIL ZERO

**Prototype version: 1.9.0**

**Teach an AI. Discover what you really know.**

PUPIL ZERO is an Arabic-first, learning-by-teaching prototype. A learner explains a topic to an AI classmate, receives curious follow-up questions, and can review a formative evidence report. A teacher can inspect locally stored sessions through a simple dashboard.

## Current features

- FastAPI backend and SQLite session history.
- Local teacher accounts with scrypt password hashing, opaque random sessions stored as SHA-256 token digests, HttpOnly/SameSite cookies, login/logout, and a protected teacher dashboard/API.
- Classroom registry: teachers can create classes with join codes, students can create accounts and join with a code, and teachers can view their class roster.
- Class-linked student learning: joining a class signs the student in locally; the student can select an enrolled class, start a session linked to that class and its owning teacher, and view only their own account-linked learning journey.
- Teacher data scoping: teacher session lists, details, insights, priorities, class rosters, and intervention feedback are restricted to the signed-in teacher account. Legacy sessions without an owner are excluded from teacher dashboards.
- Teacher-created assignments scoped to owned classes, with title, instructions, lesson, optional due date, student task list, and per-student submitted/pending status.
- Student assignment inbox scoped to enrolled classes; students launch the assigned lesson from the task and the task is marked submitted after they contribute at least one response and finish the session.
- Student progress endpoint summarizing their own sessions, lessons visited, and longitudinal concept keyword signals; optional class filter is restricted to their memberships.
- Teacher class progress dashboard with per-student session counts, lessons visited, and evidence-signal summaries; individual progress is available only when the student belongs to a class owned by that teacher.
- Parent accounts can only be created from a teacher-issued, single-use guardian invitation tied to a specific student and class; invitations expire after seven days.
- Daily learning experience: students have a protected `/student` hub with their linked school timetable, assignment inbox, attendance history, and in-app notifications. Teachers can view their linked-school teaching timetable and mark attendance only for classes assigned to them. Parents can view attendance, timetable, and notifications only through an explicitly linked student/class. New assignments notify enrolled students; attendance updates notify the student and linked parent accounts. Notifications are local in-app records; no email, push, or background due-date reminders are sent.
- School learning operations: school administrators can define a weekly timetable for existing class/subject/teacher assignments (overlapping periods for the same class or teacher are rejected), record per-student attendance by date, log lesson delivery as completed/cancelled/missed, and generate date-range operational summaries. Records are scoped to the current school; attendance and lesson logs are not learning or mastery measures.
- School academic management: school administrators can define departments, grade levels, and subjects, attach a grade level to a school class, and assign a linked teacher to teach a subject in a class. These are school-scoped administrative records and do not transfer class ownership or imply student mastery.
- School workspaces: a school administrator can create a school account, invite a teacher by email with a single-use seven-day registration token, link an existing teacher account, and view school-scoped teacher/class/enrollment counts. Existing classes are included when an existing teacher is linked; future classes created by an invited/linked teacher are automatically included. Admins can unlink a teacher from the school without deleting the teacher account or their classes.
- Parent portal is restricted to the linked student/class pair and shows aggregate activity, lesson IDs, assignment submission status, and a downloadable PDF report. It does not expose chat transcripts.
- Arabic account portal at `/account`.
- Student daily hub at `/student` (student login required).
- Arabic RTL student experience, responsive layout, text chat, and optional browser speech input/output.
- Three selectable classmates: MILO, NOURA, and ZIZO. Each has a distinct prompt profile.
- Cross-session adaptive scenario selection: a new session can start with an authored scenario matching a concept flagged for review in the learner's previous sessions. The routing reason is returned by the session API; no difficulty or mastery claim is made.
- Persistent adaptive dialogue state per session: elicit, clarify, transfer, and reflect stages, with misconception review targets. These are conversation-routing signals, not mastery labels.
- Three original mathematics demonstrator lessons: fractions, decimals, and introductory ratios.
- Local Ollama integration and OpenAI-compatible chat endpoint support.
- Explicit demo fallback when no model is configured; if a configured model is unavailable, the app reports an error instead of pretending demo text is live AI.
- Teacher intervention planner: creates a four-step, 15-minute review suggestion from the selected lesson's authored concept explanation and existing scenarios. The teacher must review, adapt, and decide whether to use it; it is not automatically assigned.
- Teacher-account-scoped feedback loop for intervention plans: optional helpful / partly helpful / not helpful rating plus a short note, with aggregate counts only. Notes are not exposed by summary endpoints; fewer than three ratings are labelled a small sample. Feedback does not automatically change plans or judge student learning.
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
- `POST /api/classes/join` — create a student account, enroll it using a class join code, and sign the student in.
- `GET /api/student/classes` — list classes for the signed-in student.
- `POST /api/teacher/assignments` — publish an assignment to one class owned by the signed-in teacher. JSON: `{"class_id":"...","title":"Explain fractions","description":"Use an example","lesson_id":"fractions","due_at":"2026-11-20T18:00"}`.
- `GET /api/teacher/assignments` — list owned assignments and each class member’s submitted/pending status; optional owned `class_id` filter.
- `GET /api/student/assignments` — list assignments for the signed-in student’s enrolled classes; optional `class_id` filter.
- `GET /api/student/dashboard` — linked-school timetable, assignment inbox, attendance history, and recent notifications.
- `GET /api/teacher/operations` — teaching timetable and linked-school class assignments for the signed-in teacher.
- `POST /api/teacher/attendance` — mark attendance for a student in a class assigned to the signed-in teacher in a linked school.
- `GET /api/student/notifications` / `GET /api/teacher/notifications` — role-scoped in-app notification inboxes.
- `POST /api/notifications/{notification_id}/read` — mark one own notification as read.
- `GET /api/parent/students/{student_id}/school-summary?class_id=...` — attendance, timetable, and notifications for an explicitly linked student/class.
- `GET /api/student/progress` — the signed-in student's own learning progress; optional enrolled `class_id` filter.
- `GET /api/teacher/classes/{class_id}/progress` — roster-level progress summary for a class owned by the signed-in teacher.
- `GET /api/teacher/students/{student_id}/progress?class_id=...` — individual progress, only for a student enrolled in the specified class owned by the teacher.
- `POST /api/teacher/students/{student_id}/guardian-invite?class_id=...` — create a single-use, seven-day guardian invitation for a student in a class owned by the teacher.
- `POST /api/auth/register-parent` — create a parent account using a valid guardian invitation.
- `POST /api/auth/register-school-admin` — create a school workspace and its administrator account. JSON: `{"school_name":"North School","email":"admin@example.test","password":"at-least-10-characters","display_name":"School Admin"}`.
- `POST /api/school-admin/timetable` — create a weekly period from an existing teaching assignment; rejects teacher/class time conflicts.
- `GET /api/school-admin/classes/{class_id}/students` — list a school class roster for attendance entry.
- `POST /api/school-admin/attendance` — upsert one student attendance status (`present`, `absent`, `late`, `excused`) for a class/date.
- `POST /api/school-admin/lesson-records` — upsert lesson delivery status (`completed`, `cancelled`, `missed`) and optional topic/notes for a timetable period/date.
- `GET /api/school-admin/operations-report?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD` — aggregate attendance and lesson delivery counts for a date range.
- `POST /api/school-admin/departments` — create a department in the current school.
- `POST /api/school-admin/grade-levels?sort_order=0` — create a school grade/stage label and ordering.
- `POST /api/school-admin/subjects` — create a subject, optionally linked to a department.
- `POST /api/school-admin/class-grades` — assign a grade level to a class already linked to the school.
- `POST /api/school-admin/teaching-assignments` — assign a linked teacher to a subject in a school class; repeated assignment updates the teacher.
- `GET /api/school-admin/teacher-invites` — generate a single-use, seven-day teacher registration invitation for an email address.
- `POST /api/auth/register-invited-teacher` — create a teacher account using a valid school invitation; the email must match the invitation.
- `POST /api/school-admin/teachers` — link an existing teacher account by email and include that teacher's existing classes in the school overview.
- `DELETE /api/school-admin/teachers/{teacher_id}` — unlink a teacher and remove their classes from the school's overview; teacher account and class records remain intact.
- `GET /api/school-admin/overview` — list only the signed-in school's linked teachers, classes, and enrollment counts.
- School administrator dashboard: `/school-admin`.
- `GET /api/parent/students` — list only student/class links owned by the signed-in parent.
- `GET /api/parent/students/{student_id}/progress?class_id=...` — parent-facing aggregate report for an explicitly linked student/class.
- `GET /api/parent/students/{student_id}/report.pdf?class_id=...` — downloadable PDF report for that same link.

- `GET /api/health` — app and configured inference mode.
- `GET /api/lessons` — demonstrator lesson catalog.
- `POST /api/sessions` — create a session. Students must provide an enrolled `class_id`; the server derives the student and teacher ownership from the membership record. To complete a task, also provide its `assignment_id` and use the lesson selected by the teacher. Teacher-created local sessions remain teacher-owned; anonymous demo sessions remain unassigned.
- `POST /api/message` — send a student explanation. JSON: `{"session_id":"...","text":"..."}`.
- `POST /api/finish` — return transcript, formative evidence report, and current dialogue state.
- `GET /api/teacher/sessions` — recent sessions owned by the signed-in teacher; optional `class_id` narrows to one owned class.
- `GET /api/teacher/sessions/{session_id}` — transcript and report for one session.
- `GET /api/teacher/insights` — aggregate evidence and review signals by lesson; optional `lesson_id` and owned `class_id` filters. These are not mastery scores.
- `GET /api/teacher/priorities` — rank concepts flagged for teacher review;
- `GET /api/teacher/interventions?lesson_id=fractions&concept_id=unit_fraction` — create a teacher-reviewed suggestion from authored lesson content, including anonymous feedback counts.
- `POST /api/teacher/interventions/feedback` — save a teacher-account-scoped rating (`helpful`, `partly_helpful`, or `not_helpful`) and optional note (maximum 500 characters).
- `GET /api/teacher/interventions/feedback?lesson_id=fractions&concept_id=unit_fraction` — retrieve aggregate ratings only; individual notes are never returned. Fewer than three ratings are labelled a small sample.
- `GET /api/learner/journey/{learner_id}` — chronological evidence history for an anonymous learner UUID. The student browser stores this random key locally and reuses it across sessions; clearing browser storage loses the association for future sessions. This is not a verified student identity or a validated measure of retention.

## Curriculum status and rights

The lesson content in this repository is original demonstrator content, not copied textbook pages. Exact grade, term, and topic mapping for the current Egyptian curriculum is **not verified**. The official electronic textbook portal is https://studentbooks.moe.gov.eg/; check the current edition and applicable reuse permissions before claiming curriculum alignment or importing source material. The project does not claim Ministry endorsement.

## Safety, privacy, and limitations

- This is a locally tested classroom- and school-scoping foundation, not a production-ready multi-school deployment. Existing legacy sessions remain unassigned and are deliberately excluded from teacher dashboards. Do not use it to store real student records or expose it to a school network/public internet yet.
- Students can sign in after class enrollment, select an enrolled class, and create class-linked sessions. Assignment editing/deletion, student account recovery, due-date enforcement, validated educational measurement, and deployment-grade controls remain pending. The initial school workspace is a single-admin/single-school prototype. Teacher invitations are email-bound tokens but email delivery is not built in; administrators must securely share the generated link. Unlinking removes school-level visibility but does not disable the teacher's standalone account or delete class/student records. Staff role hierarchy, audit history, invitation revocation, and full ownership-transfer workflows remain pending. The first PDF export uses English-safe labels and ASCII fallback for names until an Arabic shaping font is bundled.
- Account registration is open in this local prototype. Before deployment, add administrator-controlled teacher invitations, rate limiting, password reset/recovery, secure HTTPS cookie configuration, CSRF protection appropriate to the deployment, audit logging, and a reviewed data-retention/deletion workflow.
- Before any real pilot with minors, obtain school and parent/guardian approvals, define retention/deletion rules, and implement authentication and access controls.
- Avoid collecting names, phone numbers, precise location, face/video, or raw voice recordings. The journey feature uses a random browser-local UUID rather than a name or account; it is a pseudonymous identifier, so protect the local database and browser profile.
- Local Ollama inference sends text to the configured local Ollama endpoint. Do not configure a remote endpoint if local-only processing is required.
- Browser speech recognition may use a browser vendor's cloud service and is not guaranteed offline. Text chat remains available.
- The report is a simple keyword-matching signal, not a validated measure of learning and not a school grade. Teacher review is required.
- AI output may be wrong. This prototype is not a replacement for a teacher or formal assessment.

## License

No license is granted for Ministry textbook materials. A source-code license should be selected before public distribution.
