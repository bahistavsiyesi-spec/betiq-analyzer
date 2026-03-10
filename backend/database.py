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
