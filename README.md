# 🐰 ReadRabbit

A personal article discovery app that helps you go down rabbit holes on topics you care about. Replace mindless social media scrolling with intentional long-form reading.

## Quick Start

### Backend (Python + FastAPI)

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Backend runs at: http://localhost:8000

### Frontend (React + Vite + Tailwind)

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at: http://localhost:5173

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/articles/random?count=4` | GET | Get random articles |
| `/api/articles/{id}/dismiss` | POST | Don't show article again |
| `/api/articles/reset` | POST | Reset shown articles |

## Project Structure

```
readrabbit/
├── backend/
│   ├── main.py              # FastAPI app with mock data
│   └── requirements.txt
└── frontend/
    ├── src/
    │   ├── components/
    │   │   └── ArticleCard.jsx
    │   ├── App.jsx
    │   ├── main.jsx
    │   └── index.css
    ├── index.html
    ├── package.json
    ├── vite.config.js
    ├── tailwind.config.js
    └── postcss.config.js
```

## Next Steps

- [ ] Connect to Notion API (replace mock data)
- [ ] Add PostgreSQL database for user data
- [ ] Implement auth (Clerk)
- [ ] Add save/bookmark feature
- [ ] Add AI features (auto-tagging, embeddings, RAG)

## Tech Stack

- **Frontend**: React, Vite, Tailwind CSS
- **Backend**: Python, FastAPI
- **Database**: PostgreSQL (coming soon)
- **AI**: OpenAI embeddings, pgvector (planned)
