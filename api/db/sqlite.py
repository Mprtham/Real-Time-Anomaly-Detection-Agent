"""
SQLite store for persistent anomaly and RCA history.
"""

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path("sentinel.db")


class SQLiteStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._lock   = threading.Lock()
        self._init()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.db_path, check_same_thread=False)
        con.row_factory = sqlite3.Row
        return con

    def _init(self):
        with self._lock:
            con = self._connect()
            con.executescript("""
                CREATE TABLE IF NOT EXISTS anomalies (
                    anomaly_id    TEXT PRIMARY KEY,
                    anomaly_type  TEXT NOT NULL,
                    metric        TEXT,
                    metric_value  REAL,
                    baseline_mean REAL,
                    z_score       REAL,
                    severity      TEXT,
                    action        TEXT,
                    confidence    REAL,
                    detected_at   TEXT,
                    window_start  TEXT,
                    resolved      INTEGER DEFAULT 0,
                    created_at    TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS rca_reports (
                    anomaly_id   TEXT PRIMARY KEY REFERENCES anomalies(anomaly_id),
                    report_text  TEXT NOT NULL,
                    created_at   TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_anomalies_detected ON anomalies(detected_at DESC);
                CREATE INDEX IF NOT EXISTS idx_anomalies_type     ON anomalies(anomaly_type, detected_at DESC);
            """)
            con.commit()
            con.close()

    def save_anomaly(
        self,
        anomaly:    dict,
        rca_report: str,
        severity:   str,
        confidence: float,
        action:     str,
    ):
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            con = self._connect()
            con.execute("""
                INSERT OR REPLACE INTO anomalies
                    (anomaly_id, anomaly_type, metric, metric_value, baseline_mean,
                     z_score, severity, action, confidence, detected_at, window_start, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                anomaly.get("anomaly_id"),
                anomaly.get("anomaly_type"),
                anomaly.get("metric"),
                anomaly.get("metric_value"),
                anomaly.get("baseline_mean"),
                anomaly.get("z_score"),
                severity,
                action,
                confidence,
                anomaly.get("detected_at"),
                anomaly.get("window_start"),
                now,
            ])
            if rca_report:
                con.execute("""
                    INSERT OR REPLACE INTO rca_reports (anomaly_id, report_text, created_at)
                    VALUES (?, ?, ?)
                """, [anomaly.get("anomaly_id"), rca_report, now])
            con.commit()
            con.close()

    def list_anomalies(
        self,
        severity: str | None = None,
        limit:    int = 20,
        offset:   int = 0,
    ) -> list[dict]:
        where = "WHERE a.severity = ?" if severity else ""
        params = [severity] if severity else []
        params += [limit, offset]

        sql = f"""
            SELECT
                a.anomaly_id, a.anomaly_type, a.metric, a.metric_value,
                a.z_score, a.severity, a.action, a.confidence, a.detected_at,
                a.resolved,
                CASE WHEN r.anomaly_id IS NOT NULL THEN 1 ELSE 0 END AS has_rca
            FROM anomalies a
            LEFT JOIN rca_reports r ON r.anomaly_id = a.anomaly_id
            {where}
            ORDER BY a.detected_at DESC
            LIMIT ? OFFSET ?
        """
        with self._lock:
            con = self._connect()
            rows = con.execute(sql, params).fetchall()
            con.close()
        return [dict(r) for r in rows]

    def get_anomaly(self, anomaly_id: str) -> dict | None:
        with self._lock:
            con = self._connect()
            row = con.execute(
                "SELECT * FROM anomalies WHERE anomaly_id = ?", [anomaly_id]
            ).fetchone()
            con.close()
        return dict(row) if row else None

    def get_rca(self, anomaly_id: str) -> dict | None:
        with self._lock:
            con = self._connect()
            row = con.execute(
                "SELECT * FROM rca_reports WHERE anomaly_id = ?", [anomaly_id]
            ).fetchone()
            con.close()
        return dict(row) if row else None

    def resolve_anomaly(self, anomaly_id: str):
        with self._lock:
            con = self._connect()
            con.execute("UPDATE anomalies SET resolved = 1 WHERE anomaly_id = ?", [anomaly_id])
            con.commit()
            con.close()

    def count_recent_anomalies(self, anomaly_type: str, minutes: int = 30) -> int:
        sql = """
            SELECT COUNT(*) FROM anomalies
            WHERE anomaly_type = ?
              AND detected_at >= datetime('now', ? || ' minutes')
        """
        with self._lock:
            con = self._connect()
            count = con.execute(sql, [anomaly_type, f"-{minutes}"]).fetchone()[0]
            con.close()
        return count

    def get_stats(self) -> dict:
        with self._lock:
            con = self._connect()
            total      = con.execute("SELECT COUNT(*) FROM anomalies").fetchone()[0]
            last_hour  = con.execute(
                "SELECT COUNT(*) FROM anomalies WHERE detected_at >= datetime('now', '-1 hour')"
            ).fetchone()[0]
            with_rca   = con.execute("SELECT COUNT(*) FROM rca_reports").fetchone()[0]
            con.close()
        return {"total": total, "last_hour": last_hour, "with_rca": with_rca}
