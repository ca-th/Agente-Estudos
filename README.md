# Radar Estudos IFB

Assistente acadêmico automatizado baseado em Retrieval-Augmented Generation (RAG) e orquestração de fluxos, desenvolvido para extrair datas de planos de ensino em PDF, enviar alertas proativos de prazos e responder dúvidas sobre o conteúdo das disciplinas via Telegram e interface web.

---

## Visão Geral e Arquitetura

O sistema integra um backend em Python com busca vetorial, fluxos de automação no n8n e duas interfaces de interação (Bot no Telegram e painel web):

```text
[ Telegram Bot ] <---> [ n8n (Cloudflare Tunnel HTTPS) ]
                              |
                              v
[ Interface Web ] ---> [ FastAPI Backend ] ---> [ PostgreSQL / pgvector (Neon) ]
                              |
                              v
                   [ LLM & Embeddings API ]
```

### Principais Funcionalidades

* **Ingestão Automática de Planos de Ensino (PDF):** Extrai textos, datas de avaliações/entregas e pesos das atividades, armazenando os metadados relacionais e os chunks vetoriais no PostgreSQL (`pgvector`).
* **Tutor RAG por Disciplina:** Responde perguntas específicas sobre ementas, critérios de avaliação e conteúdos indexados utilizando busca por similaridade semântica filtrada por matéria.
* **Radar Diário Proativo:** Fluxo agendado no n8n que consulta os prazos dos próximos 15 dias e dispara notificações no Telegram acompanhadas de perguntas de revisão ativa.
* **Painel Web Local:** Interface construída em HTML5, CSS3 e JavaScript puro para upload via drag-and-drop, visualização de cronograma e chat direto com a API.

---

## Stack Tecnológica

* **Backend:** Python 3.11+, FastAPI, Uvicorn, PyPDF / pdfplumber
* **Banco de Dados & Busca Vetorial:** PostgreSQL (Neon) com extensão `pgvector`
* **Orquestração & Automação:** n8n (self-hosted), Cloudflare Tunnel (`cloudflared`)
* **Mensageria:** Telegram Bot API
* **Frontend:** HTML5, CSS3, JavaScript (Vanilla ES6+)

---

## Estrutura do Repositório

```text
Agente-Estudos/
├── src/
│   ├── backend/          # API FastAPI, lógica de chunking, embeddings e consultas RAG
│   └── frontend/         # Interface web (index.html, style.css)
├── n8n/                  # Workflows exportados em JSON (Radar Diário e Tutor/Ingestão)
├── docs/                 # Capturas de tela do projeto em funcionamento
├── .env.example          # Modelo das variáveis de ambiente necessárias
├── .gitignore            # Arquivos ignorados (venv, .env, cache)
├── requirements.txt      # Dependências Python do projeto
└── README.md
```

---

## Como Executar Localmente

### 1. Pré-requisitos

* Python 3.11 ou superior
* Node.js (para execução local do n8n via `npx`)
* Conta no [Neon](https://neon.tech/) (PostgreSQL com `pgvector` habilitado)
* Token de um bot criado via `@BotFather` no Telegram

### 2. Configuração do Backend (FastAPI)

Clone o repositório e configure o ambiente virtual:

```bash
git clone https://github.com/ca-th/Agente-Estudos.git
cd Agente-Estudos

python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

Crie um arquivo `.env` na raiz com base no `.env.example`:

```env
DATABASE_URL=postgresql://usuario:senha@host.neon.tech/neondb?sslmode=require
GEMINI_API_KEY=sua_chave_api
TELEGRAM_BOT_TOKEN=seu_token_do_botfather
TELEGRAM_CHAT_ID=seu_chat_id
```

Inicie o servidor FastAPI:

```bash
uvicorn src.backend.main:app --reload
```

A documentação interativa da API ficará disponível em `[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)`.

### 3. Executando o Frontend Web

Em outro terminal, sirva os arquivos estáticos da interface:

```bash
python -m http.server 5500 --directory src/frontend
```

Acesse `[http://127.0.0.1:5500](http://127.0.0.1:5500)` no navegador.

### 4. Configuração do n8n e Túnel HTTPS

Como a API do Telegram exige HTTPS para registro de webhooks, exponha a porta local do n8n (`5678`) com o Cloudflare Tunnel:

```bash
npx cloudflared tunnel --url http://localhost:5678
```

Copie a URL `https://*.trycloudflare.com` gerada e inicie o n8n apontando a variável `WEBHOOK_URL`:

```powershell
$env:WEBHOOK_URL="https://sua-url-gerada.trycloudflare.com"; npx n8n
```

Acesse `http://localhost:5678`, importe os arquivos da pasta `/n8n`, configure suas credenciais do Telegram e publique os dois fluxos.

---

## Endpoints Principais da API

| Método | Rota | Descrição |
| :--- | :--- | :--- |
| `POST` | `/ingest-syllabus` | Recebe um arquivo PDF (`multipart/form-data`), extrai datas/eventos e indexa os embeddings no banco. |
| `POST` | `/ask` | Recebe `{"subject_name": "IHC", "question": "..."}` e retorna a resposta gerada via RAG. |
| `GET` | `/events` | Lista os prazos e avaliações cadastrados para os próximos dias. |

---

## Capturas de Tela

![Painel Web Radar Estudos IFB](docs/screenshot-web.png)

![Interação no Telegram Bot](docs/screenshot-telegram.png)

---

## Autoria

Desenvolvido por **Catharina Napoleão** — Estudante de Ciência da Computação (IFB) e Tecnóloga em Análise e Desenvolvimento de Sistemas.
