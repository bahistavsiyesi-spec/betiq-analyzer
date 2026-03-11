import sqlite3
import json
import os
from datetime import datetime, timedelta

DB_PATH = os.environ.get('DB_PATH', 'data/betting.db')

def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_date TEXT NOT NULL,
            fixture_id INTEGER,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            league TEXT,
            match_time TEXT,
            prediction_1x2 TEXT,
            over25_pct REAL,
            ht2g_pct REAL,
            btts_pct REAL,
            predicted_score TEXT,
            confidence TEXT,
            reasoning TEXT,
            h2h_summary TEXT,
            home_form TEXT,
            away_form TEXT,
            home_goals_avg REAL,
            away_goals_avg REAL,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS run_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_date TEXT,
            status TEXT,
            matches_found INTEGER,
            matches_analyzed INTEGER,
            error_message TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS match_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            analysis_id INTEGER NOT NULL,
            fixture_id INTEGER,
            home_score INTEGER NOT NULL,
            away_score INTEGER NOT NULL,
            actual_1x2 TEXT,
            pred_1x2_correct INTEGER DEFAULT 0,
            actual_over25 INTEGER DEFAULT 0,
            over25_correct INTEGER DEFAULT 0,
            actual_btts INTEGER DEFAULT 0,
            btts_correct INTEGER DEFAULT 0,
            score_correct INTEGER DEFAULT 0,
            total_goals INTEGER DEFAULT 0,
            source TEXT DEFAULT 'auto',
            telegram_sent INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT (datetime('now')),
            created_at TEXT DEFAULT (datetime('now')),
            FOREIGN KEY (analysis_id) REFERENCES analyses(id)
        );
    ''')
    conn.commit()
    conn.close()

def save_analysis(data: dict):
    conn = get_conn()
    conn.execute('''
        INSERT INTO analyses (
            analysis_date, fixture_id, home_team, away_team, league, match_time,
            prediction_1x2, over25_pct, ht2g_pct, btts_pct, predicted_score,
            confidence, reasoning, h2h_summary, home_form, away_form,
            home_goals_avg, away_goals_avg
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('analysis_date', datetime.now().strftime('%Y-%m-%d')),
        data.get('fixture_id'),
        data['home_team'], data['away_team'],
        data.get('league', ''), data.get('match_time', ''),
        data.get('prediction_1x2', ''), data.get('over25_pct', 0),
        data.get('ht2g_pct', 0), data.get('btts_pct', 0),
        data.get('predicted_score', ''), data.get('confidence', 'Orta'),
        data.get('reasoning', ''), data.get('h2h_summary', ''),
        data.get('home_form', ''), data.get('away_form', ''),
        data.get('home_goals_avg', 0), data.get('away_goals_avg', 0)
    ))
    conn.commit()
    conn.close()

def get_today_matches():
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_conn()
    rows = conn.execute(
        'SELECT * FROM analyses WHERE analysis_date = ? ORDER BY confidence DESC, over25_pct DESC',
        (today,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_recent_analyses(days=7):
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    conn = get_conn()
    rows = conn.execute(
        'SELECT * FROM analyses WHERE analysis_date >= ? ORDER BY analysis_date DESC, confidence DESC',
        (since,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_pending_result_checks():
    """Skoru henüz girilmemiş, maç saati geçmiş analizleri getir"""
    from datetime import timezone, timedelta
    tr_tz = timezone(timedelta(hours=3))
    now_tr = datetime.now(tr_tz).strftime('%Y-%m-%dT%H:%M')
    since = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    conn = get_conn()
    rows = conn.execute('''
        SELECT a.* FROM analyses a
        LEFT JOIN match_results r ON a.id = r.analysis_id
        WHERE r.id IS NULL
          AND a.analysis_date >= ?
          AND a.fixture_id IS NOT NULL
          AND a.fixture_id > 0
        ORDER BY a.match_time ASC
    ''', (since,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_match_result(analysis_id, fixture_id, home_score, away_score,
                      actual_1x2, pred_1x2_correct,
                      actual_over25, over25_correct,
                      actual_btts, btts_correct,
                      score_correct, total_goals, source='auto'):
    conn = get_conn()
    existing = conn.execute(
        'SELECT id FROM match_results WHERE analysis_id = ?', (analysis_id,)
    ).fetchone()
    if existing:
        conn.execute('''
            UPDATE match_results SET
                home_score=?, away_score=?, actual_1x2=?,
                pred_1x2_correct=?, actual_over25=?, over25_correct=?,
                actual_btts=?, btts_correct=?, score_correct=?,
                total_goals=?, source=?, updated_at=datetime('now')
            WHERE analysis_id=?
        ''', (home_score, away_score, actual_1x2,
              pred_1x2_correct, actual_over25, over25_correct,
              actual_btts, btts_correct, score_correct,
              total_goals, source, analysis_id))
    else:
        conn.execute('''
            INSERT INTO match_results (
                analysis_id, fixture_id, home_score, away_score,
                actual_1x2, pred_1x2_correct,
                actual_over25, over25_correct,
                actual_btts, btts_correct,
                score_correct, total_goals, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (analysis_id, fixture_id, home_score, away_score,
              actual_1x2, pred_1x2_correct,
              actual_over25, over25_correct,
              actual_btts, btts_correct,
              score_correct, total_goals, source))
    conn.commit()
    conn.close()

def mark_telegram_sent(analysis_id):
    conn = get_conn()
    conn.execute(
        'UPDATE match_results SET telegram_sent=1 WHERE analysis_id=?',
        (analysis_id,)
    )
    conn.commit()
    conn.close()

def log_run(run_date, status, matches_found=0, matches_analyzed=0, error=None):
    conn = get_conn()
    conn.execute(
        'INSERT INTO run_logs (run_date, status, matches_found, matches_analyzed, error_message) VALUES (?, ?, ?, ?, ?)',
        (run_date, status, matches_found, matches_analyzed, error)
    )
    conn.commit()
    conn.close()

def clear_today_analyses():
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_conn()
    conn.execute('DELETE FROM analyses WHERE analysis_date = ?', (today,))
    conn.commit()
    conn.close()
