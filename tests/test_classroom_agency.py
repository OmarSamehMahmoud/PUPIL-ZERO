import json
from fastapi.testclient import TestClient
from app import main
from app.classroom_agency import authored_hint, authored_objection_explanation, objection_context_payload, objection_guidance, validate_objection_explanation
from app.curriculum import get_lesson

def setup_pair(clients):
    teacher, student, other = clients
    assert teacher.post("/api/auth/register-teacher", json={"email":"agency-teacher@example.test","password":"TeacherPass123!","display_name":"Agency Teacher"}).status_code == 201
    room = teacher.post("/api/classes", json={"name":"Agency Class"}).json()
    for client,email,name in [(student,"agency-student@example.test","Agency Secret Learner"),(other,"agency-other@example.test","Other Learner")]:
        assert client.post("/api/classes/join", json={"join_code":room["join_code"],"display_name":name,"email":email,"password":"StudentPass123!"}).status_code == 201

def judged_debate(student):
    response=student.post("/api/student/debates",json={"lesson_id":"fractions"})
    assert response.status_code==201
    debate_id=response.json()["debate_id"]
    assert student.post(f"/api/student/debates/{debate_id}/judge",json={"winner":"milo","reason":"الحجة الأولى كانت واضحة بالنسبة لي."}).status_code==200
    return debate_id

def test_authored_hint_and_objection_helpers():
    lesson=get_lesson("fractions")
    hint=authored_hint(lesson,"",1)
    assert hint["kind"]=="authored_hint" and "فكّر" in hint["text"]
    debate={"arguments":[{"speaker":"zizo","text":"اعتراض من المناظرة"}]}
    system=objection_guidance(lesson,"noura","zizo")
    context=objection_context_payload(debate,"noura","zizo")
    assert "محتوى الدرس" in system and "اعتراض من المناظرة" not in system
    assert "اعتراض من المناظرة" in context
    assert validate_objection_explanation(json.dumps({"explanation":"خلينا نختبر الفكرة بمثال مختلف من الدرس."},ensure_ascii=False))
    assert "اعتراض ZIZO" in authored_objection_explanation(debate,"noura","zizo")

def test_debate_agency_persistence_and_account_scope(tmp_path,monkeypatch):
    monkeypatch.setattr(main,"DB_PATH",tmp_path/"agency.sqlite3")
    monkeypatch.setattr(main,"public_status",lambda:{"provider":"none","model":None,"configured":False,"mode":"demo_fallback"})
    with TestClient(main.app) as teacher,TestClient(main.app) as student,TestClient(main.app) as other:
        setup_pair((teacher,student,other))
        debate_id=judged_debate(student)
        hint=student.post(f"/api/student/debates/{debate_id}/hint",json={})
        assert hint.status_code==200 and hint.json()["hint"]["kind"]=="authored_hint"
        explanation=student.post(f"/api/student/debates/{debate_id}/explain-objection",json={"explainer":"noura","objector":"zizo"})
        assert explanation.status_code==200 and explanation.json()["explanation"]["mode"]=="authored_fallback"
        revision=student.post(f"/api/student/debates/{debate_id}/revise",json={"winner":"zizo","reason":"اعتراضه خلاني أراجع الفكرة."})
        assert revision.status_code==200 and len(revision.json()["challenge_state"]["revisions"])==2
        saved=student.get(f"/api/student/debates/{debate_id}").json()
        assert saved["judgment"]["winner"]=="zizo"
        assert len(saved["challenge_state"]["hints"])==1 and len(saved["challenge_state"]["explanations"])==1
        assert saved["challenge_state"]["revisions"][0]["winner"]=="milo"
        assert other.get(f"/api/student/debates/{debate_id}").status_code==404
        assert other.post(f"/api/student/debates/{debate_id}/hint",json={}).status_code==404

def test_agency_rejects_same_speaker_and_caps_hints(tmp_path,monkeypatch):
    monkeypatch.setattr(main,"DB_PATH",tmp_path/"agency-limits.sqlite3")
    monkeypatch.setattr(main,"public_status",lambda:{"provider":"none","model":None,"configured":False,"mode":"demo_fallback"})
    with TestClient(main.app) as teacher,TestClient(main.app) as student,TestClient(main.app) as other:
        setup_pair((teacher,student,other))
        debate_id=judged_debate(student)
        same=student.post(f"/api/student/debates/{debate_id}/explain-objection",json={"explainer":"milo","objector":"milo"})
        assert same.status_code==422
        for _ in range(5):
            assert student.post(f"/api/student/debates/{debate_id}/hint",json={}).status_code==200
        assert student.post(f"/api/student/debates/{debate_id}/hint",json={}).status_code==409
