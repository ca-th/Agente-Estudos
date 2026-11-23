import io
import os
from typing import List
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pypdf import PdfReader

from src.database import get_connection
from src.schemas import SyllabusExtractionSchema

load_dotenv()

# Inicializa o cliente oficial do Google GenAI (lê GEMINI_API_KEY do .env)
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

CHAT_MODEL = "gemini-2.5-flash"
EMBEDDING_MODEL = "gemini-embedding-001"


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extrai todo o texto de um arquivo PDF em memória."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages_text = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if text.strip():
            pages_text.append(f"--- Página {i + 1} ---\n{text.strip()}")
    return "\n\n".join(pages_text)


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 150) -> List[str]:
    """Divide um texto longo em pedaços menores com sobreposição para não cortar ideias no meio."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks


def get_embedding(text: str) -> List[float]:
    """Gera o vetor numérico (768 dimensões) de um texto usando a API de Embeddings do Gemini."""
    response = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(output_dimensionality=768),
    )
    return response.embeddings[0].values


def parse_and_save_syllabus(pdf_text: str, filename: str) -> dict:
    """
    Lê o texto de um Plano de Ensino, extrai a matéria e todas as datas importantes
    via Structured Outputs e salva no Neon (subjects + academic_events + study_chunks).
    """
    prompt = f"""
    Analise o Plano de Ensino universitário abaixo.
    Extraia o nome oficial da disciplina, o professor, o semestre e TODAS as datas importantes
    do cronograma (provas, entregas de trabalhos, seminários, listas de exercícios e apresentações).
    Converta todas as datas para o formato exato AAAA-MM-DD (considere o ano atual 2026 se não estiver explícito).

    Texto do Plano de Ensino:
    {pdf_text[:25000]}
    """

    response = client.models.generate_content(
        model=CHAT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=SyllabusExtractionSchema,
            temperature=0.1,
        ),
    )

    extracted = SyllabusExtractionSchema.model_validate_json(response.text)

    with get_connection() as conn:
        with conn.cursor() as cur:
            # 1. Insere ou atualiza a matéria na tabela subjects
            cur.execute(
                """
                INSERT INTO subjects (name, professor, semester)
                VALUES (%s, %s, %s)
                ON CONFLICT (name) DO UPDATE
                SET professor = COALESCE(EXCLUDED.professor, subjects.professor),
                    semester = EXCLUDED.semester
                RETURNING id;
                """,
                (extracted.subject_name, extracted.professor, extracted.semester),
            )
            subject_id = cur.fetchone()["id"]

            # 2. Insere cada data importante na tabela academic_events
            for ev in extracted.events:
                cur.execute(
                    """
                    INSERT INTO academic_events (subject_id, event_type, title, event_date, weight, topics)
                    VALUES (%s, %s, %s, %s, %s, %s);
                    """,
                    (subject_id, ev.event_type, ev.title, ev.event_date, ev.weight, ev.topics),
                )

        conn.commit()

    # 3. Indexa o próprio Plano de Ensino no RAG para consultas futuras sobre ementa/bibliografia
    chunks_saved = index_document_chunks(extracted.subject_name, pdf_text, filename)

    return {
        "subject": extracted.subject_name,
        "professor": extracted.professor,
        "events_count": len(extracted.events),
        "events": [ev.model_dump() for ev in extracted.events],
        "rag_chunks_indexed": chunks_saved,
    }


def index_document_chunks(subject_name: str, text: str, filename: str) -> int:
    """Gera embeddings dos trechos de um material (plano de ensino ou slides) e salva no pgvector."""
    chunks = chunk_text(text)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO subjects (name)
                VALUES (%s)
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id;
                """,
                (subject_name,),
            )
            subject_id = cur.fetchone()["id"]

            for chunk in chunks:
                vector = get_embedding(chunk)
                cur.execute(
                    """
                    INSERT INTO study_chunks (subject_id, source_filename, content, embedding)
                    VALUES (%s, %s, %s, %s::vector);
                    """,
                    (subject_id, filename, chunk, str(vector)),
                )
        conn.commit()

    return len(chunks)


def ask_tutor_with_rag(subject_name: str, question: str, top_k: int = 4) -> dict:
    """Busca os trechos mais relevantes no pgvector e responde com base estrita no material da matéria."""
    query_vector = get_embedding(question)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sc.content, sc.source_filename
                FROM study_chunks sc
                JOIN subjects s ON s.id = sc.subject_id
                WHERE s.name ILIKE %s
                ORDER BY sc.embedding <=> %s::vector
                LIMIT %s;
                """,
                (f"%{subject_name}%", str(query_vector), top_k),
            )
            rows = cur.fetchall()

    if not rows:
        return {
            "answer": f"Não encontrei materiais indexados para a matéria '{subject_name}'. Envie o Plano de Ensino ou os slides primeiro.",
            "sources": [],
        }

    context_blocks = [f"[Fonte: {r['source_filename']}]\n{r['content']}" for r in rows]
    context_text = "\n\n---\n\n".join(context_blocks)
    sources = list({r["source_filename"] for r in rows})

    prompt = f"""
    Você é um tutor universitário técnico e direto. Responda à dúvida do aluno usando EXCLUSIVAMENTE
    os trechos do material da disciplina fornecidos abaixo. Se a resposta não estiver no material, diga isso claramente.

    Material da disciplina ({subject_name}):
    {context_text}

    Pergunta do aluno:
    {question}
    """

    response = client.models.generate_content(
        model=CHAT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.2),
    )

    return {
        "subject": subject_name,
        "answer": response.text,
        "sources": sources,
    }


def generate_adaptive_quiz(subject_name: str, event_topics: str) -> str:
    """
    Gera 3 questões rápidas de Active Recall focando nos tópicos da próxima avaliação
    e nos assuntos em que o aluno teve menor pontuação no histórico (study_logs).
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sl.topic, AVG(sl.score) as avg_score
                FROM study_logs sl
                JOIN subjects s ON s.id = sl.subject_id
                WHERE s.name ILIKE %s
                GROUP BY sl.topic
                ORDER BY avg_score ASC
                LIMIT 3;
                """,
                (f"%{subject_name}%",),
            )
            weak_topics = cur.fetchall()

    weak_summary = (
        ", ".join([f"{w['topic']} (média {round(w['avg_score'])}%)" for w in weak_topics])
        if weak_topics
        else "Nenhum histórico anterior (focar nos tópicos principais da avaliação)."
    )

    query_text = f"{event_topics} {weak_summary}"
    rag_data = ask_tutor_with_rag(
        subject_name=subject_name,
        question=(
            f"Com base neste material, crie 3 perguntas curtas e diretas de revisão ativa (sem dar a resposta ainda) "
            f"cobrindo: {event_topics}. Priorize estas lacunas do aluno: {weak_summary}."
        ),
        top_k=5,
    )
    return rag_data["answer"]