# FinTrack — Personal Finance Tracker

A full-featured expense tracker built with Flask, SQLite, and Groq AI.

## Features

- **Expense Tracking** — Add, edit, delete, filter, and export expenses
- **Budget Goals** — Set monthly category limits with visual progress bars and alerts
- **Investments** — Track mutual funds, stocks, insurance, FDs, gold, and more
- **Monthly Reports** — Month-over-month comparisons and budget vs actual
- **AI Chatbot** — Powered by Groq (llama-3.1-8b) with smart expense queries
- **Recurring Expenses** — Mark expenses as weekly/monthly recurring
- **CSV Export** — Download all your data

---

## Local Setup

```bash
# 1. Clone / copy the project
cd fintrack

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set environment variables
export GROQ_API_KEY=your_groq_api_key_here
export SECRET_KEY=any-random-secret-string

# 5. Run
python app.py
# Visit http://localhost:4848
```

---

## Deploy to Render (Free)

### Option A: Using render.yaml (recommended)
1. Push this project to a GitHub repository
2. Go to [render.com](https://render.com) → New → Blueprint
3. Connect your GitHub repo — Render auto-detects `render.yaml`
4. Add your `GROQ_API_KEY` in the Render dashboard under Environment
5. Deploy!

### Option B: Manual setup
1. Go to render.com → New → Web Service
2. Connect GitHub repo
3. Settings:
   - **Runtime**: Python
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
4. Add environment variables:
   - `SECRET_KEY` → any random string (e.g. use `openssl rand -hex 32`)
   - `GROQ_API_KEY` → your Groq API key
5. Add a **Disk** (for SQLite persistence):
   - Name: `sqlite-data`
   - Mount Path: `/opt/render/project/src/instance`
   - Size: 1 GB

> **Note**: The `instance/` folder is where SQLite stores `expenses.db`. Without a persistent disk on Render, data resets on each deploy.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `SECRET_KEY` | Yes | Flask session secret (any random string) |
| `GROQ_API_KEY` | Recommended | Powers the AI chatbot |

---

## Project Structure

```
fintrack/
├── app.py                  # Main Flask application
├── requirements.txt        # Python dependencies
├── Procfile               # Gunicorn start command
├── render.yaml            # Render deployment config
├── runtime.txt            # Python version
└── templates/
    ├── base.html          # Shared layout + sidebar + chatbot
    ├── login.html
    ├── register.html
    ├── index.html         # Dashboard
    ├── budget.html        # Budget goals
    ├── investments.html   # Investment tracker
    ├── report.html        # Monthly report
    ├── edit.html          # Edit expense
    └── edit_investment.html
```
