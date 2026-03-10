from groq import Groq
import os
from flask import Flask, render_template, request, redirect, url_for, flash, Response, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime, timedelta
from sqlalchemy import func
import json

app = Flask(__name__)

# Use DATABASE_URL env var for PostgreSQL on Render, fallback to SQLite locally
database_url = os.environ.get("DATABASE_URL", "sqlite:///expenses.db")
# Render gives postgres:// but SQLAlchemy needs postgresql://
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-prod")

groq_api_key = os.environ.get("GROQ_API_KEY")
client = Groq(api_key=groq_api_key) if groq_api_key else None

db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# ──────────────────────── MODELS ────────────────────────

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    currency = db.Column(db.String(10), default="₹")

class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    description = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    is_recurring = db.Column(db.Boolean, default=False)
    recurrence = db.Column(db.String(20), nullable=True)  # monthly/weekly

class Budget(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    category = db.Column(db.String(50), nullable=False)
    limit_amount = db.Column(db.Float, nullable=False)
    month = db.Column(db.String(7), nullable=False)  # YYYY-MM

class Investment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    name = db.Column(db.String(120), nullable=False)
    type = db.Column(db.String(50), nullable=False)
    amount_invested = db.Column(db.Float, nullable=False)
    current_value = db.Column(db.Float, nullable=False)
    date = db.Column(db.Date, nullable=False, default=date.today)
    notes = db.Column(db.String(250), nullable=True)

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ──────────────────────── CONSTANTS ────────────────────────

EXPENSE_CATEGORIES = ['Food', 'Transport', 'Rent', 'Utilities', 'Health', 'Entertainment', 'Shopping', 'Education', 'Other']
INVESTMENT_TYPES = ['Mutual Fund', 'Stocks', 'Fixed Deposit', 'Health Insurance', 'Life Insurance', 'Gold', 'Real Estate', 'Crypto', 'PPF/NPS', 'Other']

# ──────────────────────── AUTH ────────────────────────

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username").strip()
        password = request.form.get("password")
        if User.query.filter_by(username=username).first():
            flash("Username already taken", "error")
            return redirect(url_for("register"))
        user = User(username=username, password=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        flash("Account created! Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username").strip()
        password = request.form.get("password")
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("index"))
        flash("Invalid username or password", "error")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))

# ──────────────────────── DASHBOARD ────────────────────────

@app.route("/")
@login_required
def index():
    start = request.args.get("start")
    end = request.args.get("end")
    category = request.args.get("category")

    query = Expense.query.filter_by(user_id=current_user.id)

    if start:
        query = query.filter(Expense.date >= datetime.strptime(start, "%Y-%m-%d").date())
    if end:
        query = query.filter(Expense.date <= datetime.strptime(end, "%Y-%m-%d").date())
    if category:
        query = query.filter(Expense.category == category)

    expenses = query.order_by(Expense.date.desc()).all()
    total = round(sum(e.amount for e in expenses), 2)

    # Charts data
    cat_rows = db.session.query(Expense.category, func.sum(Expense.amount))\
        .filter_by(user_id=current_user.id).group_by(Expense.category).all()
    cat_labels = [c for c, _ in cat_rows]
    cat_values = [float(v) for _, v in cat_rows]

    day_rows = db.session.query(Expense.date, func.sum(Expense.amount))\
        .filter_by(user_id=current_user.id).group_by(Expense.date).order_by(Expense.date).all()
    day_labels = [d.isoformat() for d, _ in day_rows]
    day_values = [float(v) for _, v in day_rows]

    # Budget alerts for current month
    current_month = date.today().strftime("%Y-%m")
    budgets = Budget.query.filter_by(user_id=current_user.id, month=current_month).all()
    budget_alerts = []
    for b in budgets:
        spent = db.session.query(func.sum(Expense.amount))\
            .filter_by(user_id=current_user.id, category=b.category)\
            .filter(func.strftime('%Y-%m', Expense.date) == current_month).scalar() or 0
        pct = round((spent / b.limit_amount) * 100, 1)
        budget_alerts.append({
            "category": b.category,
            "spent": round(spent, 2),
            "limit": b.limit_amount,
            "pct": pct,
            "over": spent > b.limit_amount
        })

    # Monthly totals for last 6 months
    monthly_data = []
    for i in range(5, -1, -1):
        d = date.today().replace(day=1) - timedelta(days=i * 28)
        m = d.strftime("%Y-%m")
        t = db.session.query(func.sum(Expense.amount))\
            .filter_by(user_id=current_user.id)\
            .filter(func.strftime('%Y-%m', Expense.date) == m).scalar() or 0
        monthly_data.append({"month": m, "total": round(float(t), 2)})

    return render_template("index.html",
        expenses=expenses, categories=EXPENSE_CATEGORIES, total=total,
        today=date.today().isoformat(), cat_labels=cat_labels, cat_values=cat_values,
        day_labels=day_labels, day_values=day_values, budget_alerts=budget_alerts,
        monthly_data=monthly_data, currency=current_user.currency)

# ──────────────────────── EXPENSE CRUD ────────────────────────

@app.route("/add", methods=["POST"])
@login_required
def add():
    e = Expense(
        description=request.form.get("description"),
        amount=float(request.form.get("amount")),
        category=request.form.get("category"),
        date=datetime.strptime(request.form.get("date"), "%Y-%m-%d").date(),
        user_id=current_user.id,
        is_recurring=bool(request.form.get("is_recurring")),
        recurrence=request.form.get("recurrence") or None
    )
    db.session.add(e)
    db.session.commit()
    flash("Expense added successfully", "success")
    return redirect(url_for("index"))

@app.route("/delete/<int:expense_id>", methods=["POST"])
@login_required
def delete(expense_id):
    e = Expense.query.get_or_404(expense_id)
    if e.user_id != current_user.id:
        flash("Unauthorized", "error")
        return redirect(url_for("index"))
    db.session.delete(e)
    db.session.commit()
    flash("Expense deleted", "success")
    return redirect(url_for("index"))

@app.route("/edit/<int:expense_id>", methods=["GET", "POST"])
@login_required
def edit(expense_id):
    expense = Expense.query.get_or_404(expense_id)
    if expense.user_id != current_user.id:
        flash("Unauthorized", "error")
        return redirect(url_for("index"))
    if request.method == "POST":
        expense.description = request.form.get("description")
        expense.amount = float(request.form.get("amount"))
        expense.category = request.form.get("category")
        expense.date = datetime.strptime(request.form.get("date"), "%Y-%m-%d").date()
        db.session.commit()
        flash("Expense updated", "success")
        return redirect(url_for("index"))
    return render_template("edit.html", expense=expense, categories=EXPENSE_CATEGORIES, currency=current_user.currency)

# ──────────────────────── BUDGET ────────────────────────

@app.route("/budget", methods=["GET", "POST"])
@login_required
def budget():
    current_month = date.today().strftime("%Y-%m")
    if request.method == "POST":
        category = request.form.get("category")
        limit = float(request.form.get("limit_amount"))
        existing = Budget.query.filter_by(user_id=current_user.id, category=category, month=current_month).first()
        if existing:
            existing.limit_amount = limit
        else:
            db.session.add(Budget(user_id=current_user.id, category=category, limit_amount=limit, month=current_month))
        db.session.commit()
        flash("Budget set!", "success")
        return redirect(url_for("budget"))

    budgets = Budget.query.filter_by(user_id=current_user.id, month=current_month).all()
    budget_data = []
    for b in budgets:
        spent = db.session.query(func.sum(Expense.amount))\
            .filter_by(user_id=current_user.id, category=b.category)\
            .filter(func.strftime('%Y-%m', Expense.date) == current_month).scalar() or 0
        budget_data.append({
            "id": b.id, "category": b.category,
            "limit": b.limit_amount, "spent": round(float(spent), 2),
            "remaining": round(b.limit_amount - float(spent), 2),
            "pct": min(round((float(spent) / b.limit_amount) * 100, 1), 100),
            "over": float(spent) > b.limit_amount
        })
    return render_template("budget.html", budgets=budget_data, categories=EXPENSE_CATEGORIES, currency=current_user.currency, current_month=current_month)

@app.route("/budget/delete/<int:budget_id>", methods=["POST"])
@login_required
def delete_budget(budget_id):
    b = Budget.query.get_or_404(budget_id)
    if b.user_id != current_user.id:
        flash("Unauthorized", "error")
    else:
        db.session.delete(b)
        db.session.commit()
        flash("Budget removed", "success")
    return redirect(url_for("budget"))

# ──────────────────────── INVESTMENTS ────────────────────────

@app.route("/investments", methods=["GET", "POST"])
@login_required
def investments():
    if request.method == "POST":
        inv = Investment(
            user_id=current_user.id,
            name=request.form.get("name"),
            type=request.form.get("type"),
            amount_invested=float(request.form.get("amount_invested")),
            current_value=float(request.form.get("current_value")),
            date=datetime.strptime(request.form.get("date"), "%Y-%m-%d").date(),
            notes=request.form.get("notes") or None
        )
        db.session.add(inv)
        db.session.commit()
        flash("Investment added!", "success")
        return redirect(url_for("investments"))

    invs = Investment.query.filter_by(user_id=current_user.id).order_by(Investment.date.desc()).all()
    total_invested = sum(i.amount_invested for i in invs)
    total_current = sum(i.current_value for i in invs)
    total_gain = total_current - total_invested
    gain_pct = round((total_gain / total_invested * 100), 2) if total_invested > 0 else 0

    # By type breakdown
    type_data = {}
    for inv in invs:
        if inv.type not in type_data:
            type_data[inv.type] = {"invested": 0, "current": 0}
        type_data[inv.type]["invested"] += inv.amount_invested
        type_data[inv.type]["current"] += inv.current_value

    return render_template("investments.html",
        investments=invs, investment_types=INVESTMENT_TYPES,
        total_invested=round(total_invested, 2), total_current=round(total_current, 2),
        total_gain=round(total_gain, 2), gain_pct=gain_pct,
        type_labels=list(type_data.keys()),
        type_values=[round(v["current"], 2) for v in type_data.values()],
        currency=current_user.currency, today=date.today().isoformat())

@app.route("/investments/delete/<int:inv_id>", methods=["POST"])
@login_required
def delete_investment(inv_id):
    inv = Investment.query.get_or_404(inv_id)
    if inv.user_id != current_user.id:
        flash("Unauthorized", "error")
    else:
        db.session.delete(inv)
        db.session.commit()
        flash("Investment removed", "success")
    return redirect(url_for("investments"))

@app.route("/investments/edit/<int:inv_id>", methods=["GET", "POST"])
@login_required
def edit_investment(inv_id):
    inv = Investment.query.get_or_404(inv_id)
    if inv.user_id != current_user.id:
        flash("Unauthorized", "error")
        return redirect(url_for("investments"))
    if request.method == "POST":
        inv.name = request.form.get("name")
        inv.type = request.form.get("type")
        inv.amount_invested = float(request.form.get("amount_invested"))
        inv.current_value = float(request.form.get("current_value"))
        inv.date = datetime.strptime(request.form.get("date"), "%Y-%m-%d").date()
        inv.notes = request.form.get("notes") or None
        db.session.commit()
        flash("Investment updated!", "success")
        return redirect(url_for("investments"))
    return render_template("edit_investment.html", inv=inv, investment_types=INVESTMENT_TYPES, currency=current_user.currency)

# ──────────────────────── MONTHLY REPORT ────────────────────────

@app.route("/report")
@login_required
def report():
    month_str = request.args.get("month", date.today().strftime("%Y-%m"))
    expenses = Expense.query.filter_by(user_id=current_user.id)\
        .filter(func.strftime('%Y-%m', Expense.date) == month_str).all()

    total = round(sum(e.amount for e in expenses), 2)
    by_cat = {}
    for e in expenses:
        by_cat[e.category] = by_cat.get(e.category, 0) + e.amount

    by_cat = {k: round(v, 2) for k, v in sorted(by_cat.items(), key=lambda x: -x[1])}

    # Compare with last month
    prev = (datetime.strptime(month_str + "-01", "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m")
    prev_total = db.session.query(func.sum(Expense.amount))\
        .filter_by(user_id=current_user.id)\
        .filter(func.strftime('%Y-%m', Expense.date) == prev).scalar() or 0
    change_pct = round(((total - float(prev_total)) / float(prev_total)) * 100, 1) if prev_total else 0

    budgets = Budget.query.filter_by(user_id=current_user.id, month=month_str).all()
    budget_comparison = []
    for b in budgets:
        spent = by_cat.get(b.category, 0)
        budget_comparison.append({
            "category": b.category, "budget": b.limit_amount,
            "spent": spent, "over": spent > b.limit_amount
        })

    # Available months
    months_raw = db.session.query(func.strftime('%Y-%m', Expense.date))\
        .filter_by(user_id=current_user.id).distinct().all()
    available_months = sorted([m[0] for m in months_raw], reverse=True)

    return render_template("report.html",
        month=month_str, expenses=expenses, total=total, by_cat=by_cat,
        prev_total=round(float(prev_total), 2), change_pct=change_pct,
        budget_comparison=budget_comparison, available_months=available_months,
        currency=current_user.currency)

# ──────────────────────── EXPORT ────────────────────────

@app.route("/export.csv")
@login_required
def export_csv():
    expenses = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date).all()
    lines = ["date,description,category,amount,recurring"]
    for e in expenses:
        lines.append(f"{e.date},{e.description},{e.category},{e.amount},{e.is_recurring}")
    return Response("\n".join(lines), headers={
        "Content-Type": "text/csv",
        "Content-Disposition": "attachment; filename=expenses.csv"
    })

# ──────────────────────── CHATBOT ────────────────────────

@app.route("/chat", methods=["POST"])
@login_required
def chat():
    message = request.json.get("message", "").lower()
    currency = current_user.currency
    current_month = date.today().strftime("%Y-%m")

    def q_total(cat=None, month=None):
        q = db.session.query(func.sum(Expense.amount)).filter_by(user_id=current_user.id)
        if cat:
            q = q.filter(Expense.category == cat)
        if month:
            q = q.filter(func.strftime('%Y-%m', Expense.date) == month)
        return round(q.scalar() or 0, 2)

    # Smart keyword matching
    if "total" in message and "invest" not in message:
        total = q_total()
        return jsonify({"reply": f"Your total expenses so far: {currency}{total}"})

    elif "today" in message:
        t = db.session.query(func.sum(Expense.amount)).filter_by(user_id=current_user.id)\
            .filter(Expense.date == date.today()).scalar() or 0
        return jsonify({"reply": f"You spent {currency}{round(t,2)} today."})

    elif "this month" in message or ("month" in message and "last" not in message):
        t = q_total(month=current_month)
        return jsonify({"reply": f"You've spent {currency}{t} this month ({current_month})."})

    elif "last month" in message:
        prev = (datetime.strptime(current_month + "-01", "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m")
        t = q_total(month=prev)
        return jsonify({"reply": f"You spent {currency}{t} last month ({prev})."})

    elif "highest" in message or "biggest" in message:
        exp = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.amount.desc()).first()
        if exp:
            return jsonify({"reply": f"Your biggest expense was {currency}{exp.amount} on '{exp.description}' ({exp.date})."})
        return jsonify({"reply": "No expenses found."})

    elif "budget" in message:
        budgets = Budget.query.filter_by(user_id=current_user.id, month=current_month).all()
        if not budgets:
            return jsonify({"reply": "You haven't set any budgets for this month. Visit the Budget page to set them!"})
        lines = [f"Budget status for {current_month}:"]
        for b in budgets:
            spent = q_total(cat=b.category, month=current_month)
            status = "⚠️ OVER" if spent > b.limit_amount else "✅ OK"
            lines.append(f"{b.category}: spent {currency}{spent} / limit {currency}{b.limit_amount} {status}")
        return jsonify({"reply": "\n".join(lines)})

    elif "invest" in message:
        invs = Investment.query.filter_by(user_id=current_user.id).all()
        if not invs:
            return jsonify({"reply": "No investments tracked yet. Add them in the Investments section!"})
        total_inv = sum(i.amount_invested for i in invs)
        total_cur = sum(i.current_value for i in invs)
        gain = total_cur - total_inv
        sign = "+" if gain >= 0 else ""
        return jsonify({"reply": f"Investments summary:\nTotal invested: {currency}{round(total_inv,2)}\nCurrent value: {currency}{round(total_cur,2)}\nGain/Loss: {sign}{currency}{round(gain,2)}"})

    elif any(cat.lower() in message for cat in EXPENSE_CATEGORIES):
        for cat in EXPENSE_CATEGORIES:
            if cat.lower() in message:
                t = q_total(cat=cat)
                return jsonify({"reply": f"You've spent {currency}{t} on {cat} in total."})

    # Fallback to Groq AI
    if not client:
        return jsonify({"reply": "AI assistant not configured. Please set GROQ_API_KEY environment variable."})

    # Build context
    recent = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.date.desc()).limit(10).all()
    context = "\n".join([f"- {e.date}: {e.category} - {e.description} ({currency}{e.amount})" for e in recent])
    budgets = Budget.query.filter_by(user_id=current_user.id, month=current_month).all()
    budget_ctx = "\n".join([f"- {b.category}: limit {currency}{b.limit_amount}" for b in budgets]) or "None set"

    prompt = f"""You are a helpful financial assistant for a personal expense tracker app.
The user's currency is {currency}.

Recent expenses (last 10):
{context}

Budget limits for {current_month}:
{budget_ctx}

User question: {message}

Answer briefly, practically, and helpfully. If you can give specific advice based on the data, do so. Keep it under 3 sentences."""

    try:
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}]
        )
        return jsonify({"reply": response.choices[0].message.content})
    except Exception as e:
        return jsonify({"reply": f"AI error: {str(e)}"})

if __name__ == "__main__":
    app.run(debug=True, port=4848)
