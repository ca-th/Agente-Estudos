from datetime import date
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from src.database import get_connection
from src.rag import (
    ask_tutor_with_rag,
    extract_text_from_pdf,
    generate_adaptive_quiz,
    index_document_chunks,
    parse_and_save_syllabus,
)
from src.schemas import QuestionRequest, StudyLogRequest

app = FastAPI(
    title="Agente de Estudos Universitários (RAG + n8n)",
    description="API de ingestão de planos de ensino, radar de prazos acadêmicos e tutoria com pgvector.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    """Verifica se a API está online."""
    return {"status": "ok"}


@app.post("/ingest-syllabus")
async def ingest_syllabus(file: UploadFile = File(...)):
    """
    Recebe o PDF de um Plano de Ensino (via Swagger ou n8n), extrai todas as datas
    importantes (provas, trabalhos, seminários, listas) e indexa a ementa no pgvector.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Envie um arquivo no formato PDF.")

    pdf_bytes = await file.read()
    pdf_text = extract_text_from_pdf(pdf_bytes)

    if not pdf_text.strip():
        raise HTTPException(status_code=400, detail="Não foi possível extrair texto deste PDF.")

    result = parse_and_save_syllabus(pdf_text, file.filename)
    return {
        "message": "Plano de ensino processado e datas cadastradas com sucesso.",
        "data": result,
    }


@app.post("/ingest-material")
async def ingest_material(
    subject_name: str = Form(...),
    file: UploadFile = File(...),
):
    """
    Recebe slides de aula ou listas de exercícios em PDF e indexa no pgvector
    vinculado à matéria informada.
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Envie um arquivo no formato PDF.")

    pdf_bytes = await file.read()
    pdf_text = extract_text_from_pdf(pdf_bytes)

    if not pdf_text.strip():
        raise HTTPException(status_code=400, detail="PDF vazio ou sem texto selecionável.")

    chunks_count = index_document_chunks(subject_name, pdf_text, file.filename)
    return {
        "message": "Material indexado com sucesso na base vetorial.",
        "subject": subject_name,
        "filename": file.filename,
        "chunks_indexed": chunks_count,
    }


@app.get("/upcoming-events")
def get_upcoming_events(days: int = 7):
    """
    Endpoint acionado diariamente pelo Cron do n8n.
    Lista provas, trabalhos e seminários nos próximos X dias e gera um mini-quiz
    adaptativo para eventos que ocorrerão em até 3 dias.
    """
    today = date.today()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    ae.id,
                    s.name AS subject_name,
                    ae.event_type,
                    ae.title,
                    ae.event_date,
                    ae.weight,
                    ae.topics
                FROM academic_events ae
                JOIN subjects s ON s.id = ae.subject_id
                WHERE ae.is_completed = FALSE
                  AND ae.event_date >= %s
                  AND ae.event_date <= %s + (%s || ' days')::INTERVAL
                ORDER BY ae.event_date ASC;
                """,
                (today, today, days),
            )
            events = cur.fetchall()

    if not events:
        return {
            "has_alerts": False,
            "telegram_message": f"Nenhuma prova, trabalho ou seminário agendado para os próximos {days} dias.",
            "events": [],
        }

    alerts = []
    message_lines = [f"Radar Acadêmico - Próximos {days} dias:\n"]

    for ev in events:
        days_left = (ev["event_date"] - today).days
        urgency = "AMANHÃ" if days_left == 1 else ("HOJE" if days_left == 0 else f"em {days_left} dias")

        quiz_preview = None
        if days_left <= 3 and ev["topics"]:
            quiz_preview = generate_adaptive_quiz(ev["subject_name"], ev["topics"])

        alerts.append({
            "id": str(ev["id"]),
            "subject": ev["subject_name"],
            "type": ev["event_type"],
            "title": ev["title"],
            "date": str(ev["event_date"]),
            "days_left": days_left,
            "weight": ev["weight"],
            "topics": ev["topics"],
            "adaptive_quiz": quiz_preview,
        })

        line = f"- [{ev['event_type'].upper()}] {ev['subject_name']}: {ev['title']} ({ev['event_date']} | {urgency})"
        if ev["weight"]:
            line += f" | Peso: {ev['weight']}"
        message_lines.append(line)

        if quiz_preview:
            message_lines.append(f"\nRevisão Ativa ({ev['subject_name']}):\n{quiz_preview}\n")

    return {
        "has_alerts": True,
        "count": len(alerts),
        "telegram_message": "\n".join(message_lines),
        "events": alerts,
    }


@app.post("/ask")
def ask_question(payload: QuestionRequest):
    """Responde dúvidas técnicas com base estrita nos PDFs da matéria (RAG)."""
    return ask_tutor_with_rag(payload.subject_name, payload.question)


@app.post("/study-log")
def save_study_log(payload: StudyLogRequest):
    """Salva o desempenho de uma revisão para calibrar os próximos quizzes adaptativos."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM subjects WHERE name ILIKE %s LIMIT 1;", (f"%{payload.subject_name}%",))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Matéria '{payload.subject_name}' não encontrada.")

            cur.execute(
                """
                INSERT INTO study_logs (subject_id, topic, score)
                VALUES (%s, %s, %s);
                """,
                (row["id"], payload.topic, payload.score),
            )
        conn.commit()

    return {"message": "Desempenho registrado com sucesso."}