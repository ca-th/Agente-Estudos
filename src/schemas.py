from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class AcademicEventSchema(BaseModel):
    """Representa uma data importante extraída do Plano de Ensino."""
    event_type: Literal["prova", "trabalho", "seminario", "lista", "outro"] = Field(
        description="Categoria do evento acadêmico: 'prova', 'trabalho', 'seminario', 'lista' ou 'outro'."
    )
    title: str = Field(
        description="Título claro do evento (ex: 'Prova 1 - Árvores Balanceadas' ou 'Entrega do Projeto Final')."
    )
    event_date: str = Field(
        description="Data do evento no formato exato AAAA-MM-DD (ex: '2026-11-28')."
    )
    weight: Optional[str] = Field(
        default=None,
        description="Peso ou pontuação na média final, se mencionado no documento (ex: '30%', '2,5 pontos')."
    )
    topics: Optional[str] = Field(
        default=None,
        description="Lista resumida dos conteúdos ou capítulos cobrados nessa data."
    )


class SyllabusExtractionSchema(BaseModel):
    """Estrutura completa extraída de um Plano de Ensino universitário."""
    subject_name: str = Field(
        description="Nome oficial da disciplina (ex: 'Engenharia de Software', 'Compiladores')."
    )
    professor: Optional[str] = Field(
        default=None,
        description="Nome do docente responsável pela disciplina, se constar no plano."
    )
    semester: str = Field(
        default="2026/2",
        description="Semestre letivo identificado no plano (ex: '2026/2')."
    )
    events: List[AcademicEventSchema] = Field(
        default_factory=list,
        description="Todas as datas de provas, entregas de trabalhos, seminários e listas encontradas no cronograma."
    )


class QuestionRequest(BaseModel):
    """Modelo de entrada para o endpoint /ask (usado pelo n8n)."""
    subject_name: str
    question: str


class StudyLogRequest(BaseModel):
    """Modelo de entrada para registrar o desempenho do aluno numa revisão."""
    subject_name: str
    topic: str
    score: int = Field(ge=0, le=100, description="Nota de 0 a 100 obtida na revisão.")