import psycopg2
import psycopg2.extras
import os
from datetime import datetime, timedelta

DATABASE_URL = os.environ.get('DATABASE_URL', '')

def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS analyses (
            id SERIAL PRIMARY KEY,
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
            home_goals_trend TEXT,
            away_goals_trend TEXT,
            created_at TEXT DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS run_logs (
            id SERIAL PRIMARY KEY,
            run_date TEXT,
            status TEXT,
            matches_found INTEGER,
            matches_analyzed INTEGER,
            error_message TEXT,
            created_at TEXT DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS match_results (
            id SERIAL PRIMARY KEY,
            analysis_id INTEGER NOT NULL,
            fixture_id INTEGER,
            home_score INTEGER NOT NULL,
            away_score INTEGER NOT NULL,
            ht_home_score INTEGER,
            ht_away_score INTEGER,
            actual_1x2 TEXT,
            pred_1x2_correct INTEGER DEFAULT 0,
            actual_over25 INTEGER DEFAULT 0,
            over25_correct INTEGER DEFAULT 0,
            actual_btts INTEGER DEFAULT 0,
            btts_correct INTEGER DEFAULT 0,
            score_correct INTEGER DEFAULT 0,
            ht_correct INTEGER DEFAULT 0,
            total_goals INTEGER DEFAULT 0,
            source TEXT DEFAULT 'auto',
            telegram_sent INTEGER DEFAULT 0,
            updated_at TEXT DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS'),
            created_at TEXT DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS'),
            FOREIGN KEY (analysis_id) REFERENCES analyses(id)
        )
    ''')

    # Mevcut tabloya kolon ekle (zaten varsa hata vermez)
    try:
        cur.execute('ALTER TABLE match_results ADD COLUMN IF NOT EXISTS ht_home_score INTEGER')
        cur.execute('ALTER TABLE match_results ADD COLUMN IF NOT EXISTS ht_away_score INTEGER')
        cur.execute('ALTER TABLE match_results ADD COLUMN IF NOT EXISTS ht_correct INTEGER DEFAULT 0')
        conn.commit()
    except:
        conn.rollback()

    # Trend sütunları (mevcut DB'ye ekle)
    try:
        cur.execute('ALTER TABLE analyses ADD COLUMN IF NOT EXISTS home_goals_trend TEXT')
        cur.execute('ALTER TABLE analyses ADD COLUMN IF NOT EXISTS away_goals_trend TEXT')
        conn.commit()
    except:
        conn.rollback()

    conn.commit()
    cur.close()
    conn.close()

def save_analysis(data: dict):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO analyses (
            analysis_date, fixture_id, home_team, away_team, league, match_time,
            prediction_1x2, over25_pct, ht2g_pct, btts_pct, predicted_score,
            confidence, reasoning, h2h_summary, home_form, away_form,
            home_goals_avg, away_goals_avg, home_goals_trend, away_goals_trend
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        data.get('home_goals_avg', 0), data.get('away_goals_avg', 0),
        data.get('home_goals_trend'), data.get('away_goals_trend'),
    ))
    conn.commit()
    cur.close()
    conn.close()

def get_today_matches():
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        'SELECT * FROM analyses WHERE analysis_date = %s ORDER BY confidence DESC, over25_pct DESC',
        (today,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]

def get_recent_analyses(days=7):
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        'SELECT * FROM analyses WHERE analysis_date >= %s ORDER BY analysis_date DESC, confidence DESC',
        (since,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]

def get_analyses_by_date(date_str):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        'SELECT * FROM analyses WHERE analysis_date = %s ORDER BY confidence DESC, over25_pct DESC',
        (date_str,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]

def get_analyses_by_date_with_results(date_str):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('''
        SELECT 
            a.*,
            r.home_score,
            r.away_score,
            r.ht_home_score,
            r.ht_away_score,
            r.actual_1x2,
            r.pred_1x2_correct,
            r.actual_over25,
            r.over25_correct,
            r.actual_btts,
            r.btts_correct,
            r.score_correct,
            r.ht_correct,
            r.total_goals
        FROM analyses a
        LEFT JOIN match_results r ON a.id = r.analysis_id
        WHERE a.analysis_date = %s
        ORDER BY a.confidence DESC, a.over25_pct DESC
    ''', (date_str,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]

def get_analysis_by_id(analysis_id):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SELECT * FROM analyses WHERE id = %s', (analysis_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None

def get_available_dates():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        'SELECT DISTINCT analysis_date FROM analyses ORDER BY analysis_date DESC LIMIT 30'
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [r[0] for r in rows]

def get_pending_result_checks():
    since = (datetime.now() - timedelta(days=2)).strftime('%Y-%m-%d')
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('''
        SELECT a.* FROM analyses a
        LEFT JOIN match_results r ON a.id = r.analysis_id
        WHERE r.id IS NULL
          AND a.analysis_date >= %s
          AND a.fixture_id IS NOT NULL
          AND a.fixture_id > 0
        ORDER BY a.match_time ASC
    ''', (since,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]

def save_match_result(analysis_id, fixture_id, home_score, away_score,
                      actual_1x2, pred_1x2_correct,
                      actual_over25, over25_correct,
                      actual_btts, btts_correct,
                      score_correct, total_goals, source='auto',
                      ht_home_score=None, ht_away_score=None, ht_correct=0):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT id FROM match_results WHERE analysis_id = %s', (analysis_id,))
    existing = cur.fetchone()
    if existing:
        cur.execute('''
            UPDATE match_results SET
                home_score=%s, away_score=%s,
                ht_home_score=%s, ht_away_score=%s,
                actual_1x2=%s, pred_1x2_correct=%s,
                actual_over25=%s, over25_correct=%s,
                actual_btts=%s, btts_correct=%s,
                score_correct=%s, ht_correct=%s,
                total_goals=%s, source=%s
            WHERE analysis_id=%s
        ''', (home_score, away_score,
              ht_home_score, ht_away_score,
              actual_1x2, pred_1x2_correct,
              actual_over25, over25_correct,
              actual_btts, btts_correct,
              score_correct, ht_correct,
              total_goals, source, analysis_id))
    else:
        cur.execute('''
            INSERT INTO match_results (
                analysis_id, fixture_id, home_score, away_score,
                ht_home_score, ht_away_score,
                actual_1x2, pred_1x2_correct,
                actual_over25, over25_correct,
                actual_btts, btts_correct,
                score_correct, ht_correct,
                total_goals, source
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (analysis_id, fixture_id, home_score, away_score,
              ht_home_score, ht_away_score,
              actual_1x2, pred_1x2_correct,
              actual_over25, over25_correct,
              actual_btts, btts_correct,
              score_correct, ht_correct,
              total_goals, source))
    conn.commit()
    cur.close()
    conn.close()

def mark_telegram_sent(analysis_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        'UPDATE match_results SET telegram_sent=1 WHERE analysis_id=%s',
        (analysis_id,)
    )
    conn.commit()
    cur.close()
    conn.close()

def log_run(run_date, status, matches_found=0, matches_analyzed=0, error=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        'INSERT INTO run_logs (run_date, status, matches_found, matches_analyzed, error_message) VALUES (%s, %s, %s, %s, %s)',
        (run_date, status, matches_found, matches_analyzed, error)
    )
    conn.commit()
    cur.close()
    conn.close()

def clear_today_analyses():
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('DELETE FROM analyses WHERE analysis_date = %s', (today,))
    conn.commit()
    cur.close()
    conn.close()

def delete_analyses_by_fixture_ids(fixture_ids: list):
    if not fixture_ids:
        return
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''
        DELETE FROM match_results WHERE analysis_id IN (
            SELECT id FROM analyses WHERE fixture_id = ANY(%s)
        )
    ''', (fixture_ids,))
    cur.execute('DELETE FROM analyses WHERE fixture_id = ANY(%s)', (fixture_ids,))
    conn.commit()
    cur.close()
    conn.close()

def delete_analysis(analysis_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('DELETE FROM match_results WHERE analysis_id = %s', (analysis_id,))
    cur.execute('DELETE FROM analyses WHERE id = %s', (analysis_id,))
    conn.commit()
    cur.close()
    conn.close()

def delete_today_analyses():
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''
        DELETE FROM match_results WHERE analysis_id IN (
            SELECT id FROM analyses WHERE analysis_date = %s
        )
    ''', (today,))
    cur.execute('DELETE FROM analyses WHERE analysis_date = %s', (today,))
    conn.commit()
    cur.close()
    conn.close()
