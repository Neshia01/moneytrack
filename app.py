import sqlite3
from pathlib import Path
from datetime import date, datetime

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    abort,
)


# ==========================================
# APPLICATION CONFIGURATION
# ==========================================

app = Flask(__name__)

app.config["SECRET_KEY"] = "moneytrack-development-key"

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "database" / "moneytrack.db"

DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)


# ==========================================
# DATABASE
# ==========================================

def get_db():
    """Create and return a SQLite database connection."""
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")

    return connection


def init_db():
    """Create database tables if they do not exist."""
    connection = get_db()

    try:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                type TEXT NOT NULL
                    CHECK (type IN ('income', 'expense')),
                date TEXT NOT NULL,
                description TEXT
            );

            CREATE TABLE IF NOT EXISTS budgets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                amount REAL NOT NULL,
                month TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS debts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person_name TEXT NOT NULL,
                amount REAL NOT NULL,
                remaining_amount REAL NOT NULL,
                type TEXT NOT NULL,
                transaction_date TEXT NOT NULL,
                due_date TEXT,
                description TEXT,
                status TEXT DEFAULT 'active',
                settled_date TEXT
            );

            CREATE TABLE IF NOT EXISTS debt_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                debt_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                payment_date TEXT NOT NULL,
                FOREIGN KEY (debt_id)
                    REFERENCES debts(id)
            );
        """)

        connection.commit()

    finally:
        connection.close()


# ==========================================
# HELPER FUNCTIONS
# ==========================================

def format_currency(value):
    """Format a number into Indonesian Rupiah."""
    return f"Rp {value:,.0f}".replace(",", ".")


def validate_transaction(form_data):
    """Validate transaction data from a submitted form."""

    title = form_data.get("title", "").strip()
    category = form_data.get("category", "").strip()
    transaction_type = form_data.get("type", "").strip()
    transaction_date = form_data.get("date", "").strip()
    description = form_data.get("description", "").strip()

    try:
        amount = float(form_data.get("amount", 0))
    except (ValueError, TypeError):
        return None, "Jumlah transaksi harus berupa angka."

    if not title:
        return None, "Nama transaksi wajib diisi."

    if amount <= 0:
        return None, "Jumlah transaksi harus lebih dari nol."

    if transaction_type not in ("income", "expense"):
        return None, "Jenis transaksi tidak valid."

    if not category:
        return None, "Kategori transaksi wajib dipilih."

    try:
        datetime.strptime(transaction_date, "%Y-%m-%d")
    except ValueError:
        return None, "Tanggal transaksi tidak valid."

    transaction = {
        "title": title,
        "amount": amount,
        "category": category,
        "type": transaction_type,
        "date": transaction_date,
        "description": description,
    }

    return transaction, None


# ==========================================
# DASHBOARD
# ==========================================

@app.route("/")
def dashboard():

    connection = get_db()

    try:
        income = connection.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE type = 'income'
        """).fetchone()[0]

        expense = connection.execute("""
            SELECT COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE type = 'expense'
        """).fetchone()[0]

        balance = income - expense

        recent = connection.execute("""
            SELECT *
            FROM transactions
            ORDER BY date DESC, id DESC
            LIMIT 5
        """).fetchall()

        monthly_rows = connection.execute("""
            SELECT
                strftime('%Y-%m', date) AS month,
                SUM(
                    CASE
                        WHEN type = 'income' THEN amount
                        ELSE 0
                    END
                ) AS income,
                SUM(
                    CASE
                        WHEN type = 'expense' THEN amount
                        ELSE 0
                    END
                ) AS expense
            FROM transactions
            GROUP BY strftime('%Y-%m', date)
            ORDER BY month ASC
        """).fetchall()

        monthly = [
            dict(row) for row in monthly_rows
        ]

        category_rows = connection.execute("""
            SELECT
                category,
                SUM(amount) AS total
            FROM transactions
            WHERE type = 'expense'
            GROUP BY category
            ORDER BY total DESC
        """).fetchall()

        categories = [
            dict(row) for row in category_rows
        ]

    finally:
        connection.close()

    return render_template(
        "dashboard.html",
        income=income,
        expense=expense,
        balance=balance,
        recent=recent,
        monthly=monthly,
        categories=categories,
        format_currency=format_currency,
    )


# ==========================================
# TRANSACTION HISTORY
# ==========================================

@app.route("/transactions")
def transactions():

    connection = get_db()

    try:
        transaction_list = connection.execute("""
            SELECT *
            FROM transactions
            ORDER BY date DESC, id DESC
        """).fetchall()

    finally:
        connection.close()

    return render_template(
        "transactions.html",
        transactions=transaction_list,
        format_currency=format_currency,
    )


# ==========================================
# ADD TRANSACTION
# ==========================================

@app.route("/transaction/add", methods=["GET", "POST"])
def add_transaction():

    if request.method == "POST":

        transaction, error = validate_transaction(request.form)

        if error:
            flash(error, "error")
            return redirect(url_for("add_transaction"))

        connection = get_db()

        try:
            connection.execute("""
                INSERT INTO transactions (
                    title,
                    amount,
                    category,
                    type,
                    date,
                    description
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                transaction["title"],
                transaction["amount"],
                transaction["category"],
                transaction["type"],
                transaction["date"],
                transaction["description"],
            ))

            connection.commit()

        finally:
            connection.close()

        flash("Transaksi berhasil ditambahkan!", "success")

        return redirect(url_for("transactions"))

    return render_template(
        "add_transaction.html",
        today=date.today().isoformat(),
        transaction=None,
    )


# ==========================================
# EDIT TRANSACTION
# ==========================================

@app.route("/transaction/edit/<int:id>", methods=["GET", "POST"])
def edit_transaction(id):

    connection = get_db()

    try:
        transaction = connection.execute("""
            SELECT *
            FROM transactions
            WHERE id = ?
        """, (id,)).fetchone()

        if transaction is None:
            abort(404)

        if request.method == "POST":

            updated_data, error = validate_transaction(request.form)

            if error:
                flash(error, "error")

                return redirect(
                    url_for("edit_transaction", id=id)
                )

            connection.execute("""
                UPDATE transactions
                SET
                    title = ?,
                    amount = ?,
                    category = ?,
                    type = ?,
                    date = ?,
                    description = ?
                WHERE id = ?
            """, (
                updated_data["title"],
                updated_data["amount"],
                updated_data["category"],
                updated_data["type"],
                updated_data["date"],
                updated_data["description"],
                id,
            ))

            connection.commit()

            flash("Transaksi berhasil diperbarui!", "success")

            return redirect(url_for("transactions"))

    finally:
        connection.close()

    return render_template(
        "add_transaction.html",
        transaction=transaction,
        today=date.today().isoformat(),
    )


# ==========================================
# DELETE TRANSACTION
# ==========================================

@app.route("/transaction/delete/<int:id>", methods=["POST"])
def delete_transaction(id):

    connection = get_db()

    try:
        result = connection.execute("""
            DELETE FROM transactions
            WHERE id = ?
        """, (id,))

        connection.commit()

        if result.rowcount == 0:
            flash("Transaksi tidak ditemukan.", "error")
        else:
            flash("Transaksi berhasil dihapus!", "success")

    finally:
        connection.close()

    return redirect(url_for("transactions"))


# ==========================================
# ERROR HANDLING
# ==========================================

@app.errorhandler(404)
def page_not_found(error):
    return "Halaman tidak ditemukan.", 404


# ==========================================
# APPLICATION ENTRY POINT
# ==========================================

if __name__ == "__main__":
    init_db()
    app.run(debug=True)
