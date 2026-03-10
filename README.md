# FinTrack — Personal Finance Tracker

A full-featured expense tracker built with Flask, SQLite, and Groq AI.

## Features

- **Expense Tracking** — Add, edit, delete, filter, and export expenses
- **Budget Goals** — Set monthly category limits with visual progress bars and alerts
- **Investments** — Track mutual funds, stocks, insurance
- **Monthly Reports** — Month-over-month comparisons and budget vs actual
- **AI Chatbot** — Powered by Groq (llama-3.1-8b) with smart expense queries
- **Recurring Expenses** — Mark expenses as weekly/monthly recurring
- **CSV Export** — Download all your data


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
