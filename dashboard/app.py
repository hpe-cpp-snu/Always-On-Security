from flask import Flask, render_template, jsonify
import sqlite3

app = Flask(__name__)

DATABASE = "/data/events.db"


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


@app.route("/")
def index():
    conn = get_db_connection()

    try:
        events = conn.execute("""
            SELECT * FROM events ORDER BY id DESC LIMIT 20
        """).fetchall()

        total_events = conn.execute(
            "SELECT COUNT(*) as count FROM events"
        ).fetchone()["count"]

        # quarantine bucket (new engine) OR legacy risk_score >= 100
        high_risk = conn.execute("""
            SELECT COUNT(*) as count FROM events
            WHERE bucket = 'quarantine'
               OR (bucket IS NULL AND risk_score >= 100)
        """).fetchone()["count"]

        auto_count = conn.execute("""
            SELECT COUNT(*) as count FROM events WHERE bucket = 'auto'
        """).fetchone()["count"]

        human_count = conn.execute("""
            SELECT COUNT(*) as count FROM events WHERE bucket = 'human'
        """).fetchone()["count"]

        correlated_count = conn.execute("""
            SELECT COUNT(*) as count FROM events WHERE correlated = 1
        """).fetchone()["count"]

        try:
            node_status_records = conn.execute("""
                SELECT * FROM node_status ORDER BY node ASC
            """).fetchall()
        except sqlite3.OperationalError:
            node_status_records = []

    except sqlite3.OperationalError:
        events = []
        total_events = high_risk = auto_count = human_count = correlated_count = 0
        node_status_records = []

    conn.close()

    return render_template(
        "index.html",
        events=events,
        total_events=total_events,
        high_risk=high_risk,
        auto_count=auto_count,
        human_count=human_count,
        correlated_count=correlated_count,
        nodes=node_status_records,
    )

@app.route("/api/nodes")
def api_nodes():
    conn = get_db_connection()
    try:
        nodes = conn.execute("SELECT * FROM node_status ORDER BY node ASC").fetchall()
        result = [dict(row) for row in nodes]
    except sqlite3.OperationalError:
        result = []
    finally:
        conn.close()
    return jsonify(result)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
