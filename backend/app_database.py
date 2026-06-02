import json
import sqlite3
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
DB_FILE = DATA_DIR / "app.sqlite"


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS workflows (
                name TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at REAL NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_name TEXT NOT NULL,
                output TEXT NOT NULL,
                stats TEXT NOT NULL,
                logs TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection TEXT NOT NULL,
                title TEXT NOT NULL,
                source TEXT NOT NULL,
                chunk_count INTEGER NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )


def connect():
    return sqlite3.connect(DB_FILE)


def save_workflow(workflow, name="current"):
    init_db()
    with connect() as db:
        db.execute(
            """
            INSERT INTO workflows (name, payload, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (name, json.dumps(workflow), time.time()),
        )


def load_workflow(name="current"):
    init_db()
    with connect() as db:
        row = db.execute("SELECT payload FROM workflows WHERE name = ?", (name,)).fetchone()
    if not row:
        return None
    return json.loads(row[0])


def save_run(workflow, result, workflow_name="current"):
    init_db()
    with connect() as db:
        db.execute(
            """
            INSERT INTO runs (workflow_name, output, stats, logs, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                workflow_name,
                result.get("output", ""),
                json.dumps(result.get("stats", {})),
                json.dumps(result.get("logs", [])),
                time.time(),
            ),
        )


def save_document_metadata(collection, title, source, chunk_count):
    init_db()
    with connect() as db:
        db.execute(
            """
            INSERT INTO documents (collection, title, source, chunk_count, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (collection, title, source, chunk_count, time.time()),
        )


def list_document_collections():
    init_db()
    with connect() as db:
        rows = db.execute(
            """
            SELECT collection, COUNT(*) AS document_count, SUM(chunk_count) AS chunk_count, MAX(created_at) AS updated_at
            FROM documents
            GROUP BY collection
            ORDER BY updated_at DESC
            """
        ).fetchall()
        recent_documents = db.execute(
            """
            SELECT collection, title, source, chunk_count, created_at
            FROM documents
            ORDER BY created_at DESC
            LIMIT 10
            """
        ).fetchall()

    return {
        "collections": [
            {
                "name": row[0],
                "documents": row[1],
                "chunks": row[2] or 0,
                "updatedAt": row[3],
            }
            for row in rows
        ],
        "recentDocuments": [
            {
                "collection": row[0],
                "title": row[1],
                "source": row[2],
                "chunks": row[3],
                "createdAt": row[4],
            }
            for row in recent_documents
        ],
    }


def get_summary():
    init_db()
    with connect() as db:
        workflows = db.execute("SELECT COUNT(*) FROM workflows").fetchone()[0]
        runs = db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        documents = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        recent_runs = db.execute(
            """
            SELECT id, workflow_name, stats, created_at
            FROM runs
            ORDER BY created_at DESC
            LIMIT 5
            """
        ).fetchall()
    return {
        "path": str(DB_FILE),
        "workflows": workflows,
        "runs": runs,
        "documents": documents,
        "recentRuns": [
            {
                "id": row[0],
                "workflowName": row[1],
                "stats": json.loads(row[2]),
                "createdAt": row[3],
            }
            for row in recent_runs
        ],
    }
