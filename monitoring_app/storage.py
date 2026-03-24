from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from monitoring_app.config import (
    DB_PATH,
    DEFAULT_FULL_NAME,
    DEFAULT_PASSWORD,
    DEFAULT_USERNAME,
    EXPORTS_DIR,
)
from monitoring_app.models import CaseRecord, SearchOptions, SearchResult


def utc_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def hash_password(password: str, salt: Optional[str] = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 390000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored_hash: str) -> bool:
    salt, expected = stored_hash.split("$", 1)
    candidate = hash_password(password, salt).split("$", 1)[1]
    return secrets.compare_digest(candidate, expected)


class DatabaseManager:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    full_name TEXT NOT NULL,
                    role TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS searches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    google_dork TEXT,
                    sources_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    total_results INTEGER NOT NULL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS cases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    case_key TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    primary_category TEXT NOT NULL,
                    risk_score INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    summary TEXT,
                    confidence REAL NOT NULL DEFAULT 0,
                    canonical_text TEXT,
                    canonical_url TEXT,
                    evidence_count INTEGER NOT NULL DEFAULT 0,
                    source_mix_json TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_search_id INTEGER
                );

                CREATE TABLE IF NOT EXISTS results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    search_id INTEGER NOT NULL,
                    case_id INTEGER,
                    source_type TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    url TEXT,
                    domain TEXT,
                    snippet TEXT,
                    content_text TEXT,
                    transcript TEXT,
                    ocr_text TEXT,
                    media_urls_json TEXT,
                    published_at TEXT,
                    author TEXT,
                    classification TEXT,
                    classification_confidence REAL,
                    risk_score INTEGER,
                    relevance_score REAL,
                    duplicate_of INTEGER,
                    raw_json TEXT,
                    matched_signals_json TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(search_id) REFERENCES searches(id),
                    FOREIGN KEY(case_id) REFERENCES cases(id)
                );

                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    report_name TEXT NOT NULL,
                    format TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    filters_json TEXT,
                    created_at TEXT NOT NULL
                );
                """
            )
            self._seed_default_user(conn)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _seed_default_user(self, conn: sqlite3.Connection) -> None:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (DEFAULT_USERNAME,)).fetchone()
        if existing:
            return
        conn.execute(
            """
            INSERT INTO users (username, password_hash, full_name, role, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (DEFAULT_USERNAME, hash_password(DEFAULT_PASSWORD), DEFAULT_FULL_NAME, "admin", utc_now()),
        )
        conn.commit()

    def authenticate_user(self, username: str, password: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, username, password_hash, full_name, role FROM users WHERE username = ?",
                (username.strip(),),
            ).fetchone()
        if not row or not verify_password(password, row["password_hash"]):
            return None
        return {
            "id": row["id"],
            "username": row["username"],
            "full_name": row["full_name"],
            "role": row["role"],
        }

    def create_search(self, query: str, options: SearchOptions, total_results: int) -> int:
        payload = json.dumps(
            {
                "sources": options.enabled_sources,
                "official_domains": options.official_domains,
                "direct_urls": options.direct_urls,
                "fetch_full_text": options.fetch_full_text,
                "enable_ocr": options.enable_ocr,
                "enable_video_transcript": options.enable_video_transcript,
                "search_images": options.search_images,
                "max_results_per_source": options.max_results_per_source,
            },
            ensure_ascii=False,
        )
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO searches (query, google_dork, sources_json, created_at, total_results)
                VALUES (?, ?, ?, ?, ?)
                """,
                (query, options.google_dork, payload, utc_now(), total_results),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def list_case_anchors(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, title, primary_category, canonical_text, canonical_url,
                       risk_score, confidence, evidence_count, source_mix_json
                FROM cases
                ORDER BY updated_at DESC
                """
            ).fetchall()
        anchors: List[Dict[str, Any]] = []
        for row in rows:
            anchors.append(
                {
                    "id": row["id"],
                    "title": row["title"],
                    "primary_category": row["primary_category"],
                    "canonical_text": row["canonical_text"] or "",
                    "canonical_url": row["canonical_url"] or "",
                    "risk_score": row["risk_score"],
                    "confidence": row["confidence"],
                    "evidence_count": row["evidence_count"],
                    "source_mix": json.loads(row["source_mix_json"] or "{}"),
                }
            )
        return anchors

    def save_case_bundle(self, search_id: int, case: CaseRecord) -> int:
        now = utc_now()
        with self._connect() as conn:
            if case.case_id:
                current = conn.execute(
                    """
                    SELECT evidence_count, source_mix_json, risk_score, confidence
                    FROM cases
                    WHERE id = ?
                    """,
                    (case.case_id,),
                ).fetchone()
                current_mix = json.loads(current["source_mix_json"] or "{}") if current else {}
                for key, value in case.source_mix.items():
                    current_mix[key] = current_mix.get(key, 0) + value
                evidence_count = (current["evidence_count"] if current else 0) + len(case.results)
                risk_score = max(int(current["risk_score"]) if current else 0, case.risk_score)
                confidence = max(float(current["confidence"]) if current else 0.0, case.confidence)
                conn.execute(
                    """
                    UPDATE cases
                    SET title = ?, primary_category = ?, risk_score = ?, summary = ?, confidence = ?,
                        canonical_text = ?, canonical_url = ?, evidence_count = ?, source_mix_json = ?,
                        updated_at = ?, last_search_id = ?
                    WHERE id = ?
                    """,
                    (
                        case.title,
                        case.primary_category,
                        risk_score,
                        case.summary,
                        confidence,
                        case.canonical_text,
                        case.canonical_url,
                        evidence_count,
                        json.dumps(current_mix, ensure_ascii=False),
                        now,
                        search_id,
                        case.case_id,
                    ),
                )
                case_id = int(case.case_id)
            else:
                case_key = hashlib.sha1(f"{case.canonical_text}|{case.canonical_url}".encode("utf-8")).hexdigest()
                cursor = conn.execute(
                    """
                    INSERT INTO cases (
                        case_key, title, primary_category, risk_score, summary, confidence,
                        canonical_text, canonical_url, evidence_count, source_mix_json,
                        created_at, updated_at, last_search_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        case_key,
                        case.title,
                        case.primary_category,
                        case.risk_score,
                        case.summary,
                        case.confidence,
                        case.canonical_text,
                        case.canonical_url,
                        len(case.results),
                        json.dumps(case.source_mix, ensure_ascii=False),
                        now,
                        now,
                        search_id,
                    ),
                )
                case_id = int(cursor.lastrowid)

            for result in case.results:
                conn.execute(
                    """
                    INSERT INTO results (
                        search_id, case_id, source_type, source_name, title, url, domain, snippet,
                        content_text, transcript, ocr_text, media_urls_json, published_at, author,
                        classification, classification_confidence, risk_score, relevance_score,
                        duplicate_of, raw_json, matched_signals_json, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        search_id,
                        case_id,
                        result.source_type,
                        result.source_name,
                        result.title,
                        result.url,
                        result.domain,
                        result.snippet,
                        result.content_text,
                        result.transcript,
                        result.ocr_text,
                        json.dumps(result.media_urls, ensure_ascii=False),
                        result.published_at,
                        result.author,
                        result.classification,
                        result.classification_confidence,
                        result.risk_score,
                        result.relevance_score,
                        result.duplicate_of,
                        json.dumps(result.raw_payload, ensure_ascii=False),
                        json.dumps(result.matched_signals, ensure_ascii=False),
                        now,
                    ),
                )
            conn.commit()
        return case_id

    def list_cases(self, limit: int = 100) -> pd.DataFrame:
        with self._connect() as conn:
            return pd.read_sql_query(
                """
                SELECT id, title, primary_category, risk_score, status, summary, confidence,
                       evidence_count, created_at, updated_at
                FROM cases
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                conn,
                params=(limit,),
            )

    def get_case(self, case_id: int) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["source_mix"] = json.loads(data.get("source_mix_json") or "{}")
        return data

    def get_case_results(self, case_id: int) -> pd.DataFrame:
        with self._connect() as conn:
            return pd.read_sql_query(
                """
                SELECT id, source_type, source_name, title, url, domain, snippet, content_text,
                       transcript, ocr_text, published_at, author, classification,
                       classification_confidence, risk_score, relevance_score, created_at
                FROM results
                WHERE case_id = ?
                ORDER BY risk_score DESC, created_at DESC
                """,
                conn,
                params=(case_id,),
            )

    def dashboard_snapshot(self) -> Dict[str, Any]:
        with self._connect() as conn:
            metrics = conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM cases) AS total_cases,
                    (SELECT COUNT(*) FROM results) AS total_results,
                    (SELECT COUNT(*) FROM cases WHERE risk_score >= 80) AS high_risk_cases,
                    (SELECT COUNT(*) FROM results WHERE classification = 'استغاثة') AS distress_results
                """
            ).fetchone()
            categories = pd.read_sql_query(
                """
                SELECT primary_category AS category, COUNT(*) AS total
                FROM cases
                GROUP BY primary_category
                ORDER BY total DESC
                """,
                conn,
            )
            sources = pd.read_sql_query(
                """
                SELECT source_type, COUNT(*) AS total
                FROM results
                GROUP BY source_type
                ORDER BY total DESC
                """,
                conn,
            )
            latest_cases = pd.read_sql_query(
                """
                SELECT id, title, primary_category, risk_score, evidence_count, updated_at
                FROM cases
                ORDER BY updated_at DESC
                LIMIT 8
                """,
                conn,
            )
        return {
            "metrics": dict(metrics) if metrics else {},
            "categories": categories,
            "sources": sources,
            "latest_cases": latest_cases,
        }

    def export_rows(self, category: str = "", minimum_risk: int = 0) -> pd.DataFrame:
        query = """
            SELECT
                c.id AS case_id,
                c.title AS case_title,
                c.primary_category,
                c.risk_score AS case_risk_score,
                c.summary AS case_summary,
                c.evidence_count,
                r.id AS result_id,
                r.source_type,
                r.source_name,
                r.title,
                r.url,
                r.domain,
                r.snippet,
                r.classification,
                r.classification_confidence,
                r.risk_score,
                r.relevance_score,
                r.published_at,
                r.author,
                r.created_at
            FROM cases c
            LEFT JOIN results r ON c.id = r.case_id
            WHERE c.risk_score >= ?
        """
        params: List[Any] = [minimum_risk]
        if category:
            query += " AND c.primary_category = ?"
            params.append(category)
        query += " ORDER BY c.risk_score DESC, c.updated_at DESC"
        with self._connect() as conn:
            return pd.read_sql_query(query, conn, params=params)

    def assistant_documents(self) -> pd.DataFrame:
        with self._connect() as conn:
            return pd.read_sql_query(
                """
                SELECT
                    c.id AS case_id,
                    c.title AS case_title,
                    c.primary_category,
                    c.risk_score AS case_risk_score,
                    c.summary AS case_summary,
                    c.confidence AS case_confidence,
                    r.id AS result_id,
                    r.title AS result_title,
                    r.url,
                    r.snippet,
                    r.content_text,
                    r.transcript,
                    r.ocr_text,
                    r.source_type,
                    r.classification
                FROM cases c
                LEFT JOIN results r ON c.id = r.case_id
                ORDER BY c.updated_at DESC, r.risk_score DESC
                """,
                conn,
            )

    def record_report(self, report_name: str, format_name: str, file_path: str, filters: Dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO reports (report_name, format, file_path, filters_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (report_name, format_name, file_path, json.dumps(filters, ensure_ascii=False), utc_now()),
            )
            conn.commit()

    def list_reports(self, limit: int = 20) -> pd.DataFrame:
        with self._connect() as conn:
            return pd.read_sql_query(
                """
                SELECT report_name, format, file_path, created_at
                FROM reports
                ORDER BY created_at DESC
                LIMIT ?
                """,
                conn,
                params=(limit,),
            )
