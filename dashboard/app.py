from flask import Flask, render_template, jsonify
import sqlite3
import docker
from datetime import datetime, timezone
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

        try:
            wazuh_logs = conn.execute("""
                SELECT * FROM wazuh_alerts ORDER BY id DESC LIMIT 10
            """).fetchall()
        except sqlite3.OperationalError:
            wazuh_logs = []

    except sqlite3.OperationalError:
        events = []
        total_events = high_risk = auto_count = human_count = correlated_count = 0
        node_status_records = []
        wazuh_logs = []

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
        wazuh_logs=wazuh_logs,
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

@app.route("/api/reset", methods=["POST"])
def reset_demo():
    conn = get_db_connection()
    try:
        conn.execute("DELETE FROM events")
        conn.execute("DELETE FROM node_scores")
        conn.execute("DELETE FROM node_status")
        conn.execute("DELETE FROM wazuh_alerts")
        conn.commit()
    except sqlite3.OperationalError as e:
        return jsonify({"error": f"Database wipe failed: {e}"}), 500
    finally:
        conn.close()

    try:
        client = docker.from_env()
        containers_to_restart = ["risk-engine", "controller", "wazuh", "node1", "node2", "node3", "node4"]
        for c_name in containers_to_restart:
            try:
                c = client.containers.get(c_name)
                c.restart()
            except docker.errors.NotFound:
                pass
    except Exception as e:
        return jsonify({"error": f"Docker restart failed: {e}"}), 500

    return jsonify({"success": True})

@app.route("/api/nodes/<node_name>/restart", methods=["POST"])
def restart_node(node_name):
    conn = get_db_connection()
    try:
        # Wipe the node's cumulative score so it doesn't instantly quarantine again
        conn.execute(
            "UPDATE node_scores SET cumulative_score = 0.0 WHERE node = ?",
            (node_name,)
        )
        
        # Overwrite the node status to idle
        ts = datetime.now(timezone.utc).isoformat()
        conn.execute("""
            INSERT INTO node_status (node, status, risk_score, last_updated)
            VALUES (?, 'idle', 0.0, ?)
            ON CONFLICT(node) DO UPDATE SET
                status = 'idle',
                risk_score = 0.0,
                last_updated = ?
        """, (node_name, ts, ts))
        conn.commit()
    except sqlite3.OperationalError as e:
        return jsonify({"error": f"Database error: {e}"}), 500
    finally:
        conn.close()

    # Restart the actual container via Docker API
    try:
        client = docker.from_env()
        container = client.containers.get(node_name)
        container.start()
    except Exception as e:
        return jsonify({"error": f"Docker error: {e}"}), 500

    return jsonify({"success": True, "node": node_name})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
