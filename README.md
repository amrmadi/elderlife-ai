# ElderLife AI

AI-powered safety platform for older adults living alone: check-ins, fall/activity events, risk scoring with explanations ("Why?"), smart alerts and a care plan.
Demo data is synthetic. Only events and scores are stored, never video. The care plan shows recorded reminders only; it does not diagnose or change doses.

## Run the backend (Python 3.10+)
    cd backend
    python -m venv .venv
    .venv\Scripts\activate.bat      (Windows CMD)   |   source .venv/bin/activate   (Mac/Linux)
    pip install -r requirements.txt
    python -m uvicorn app.main:app --reload
API docs: http://localhost:8000/docs

## Run the frontend (Node 18+), in a second terminal
    cd frontend
    npm install
    npm run dev
Open http://localhost:5173 and click "Load sample data".

## Where the AI team plugs in
- backend/app/risk.py: replace assess() with the real model (contract in its docstring).
- POST /events: send {elderly_id, kind: "fall"|"activity"|"ok", value}.

## Roadmap
Auth and roles, notifications (Telegram/Email), PostgreSQL, Docker.
