import psycopg2
import psycopg2.extras
import os
import json
from datetime import datetime, timedelta

DATABASE_URL = os.environ.get('DATABASE_URL', '')

def get_conn():
    return psycopg2.connect(DATABASE_URL)

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
            predicted_ht_score TEXT,
            confidence TEXT,
            reasoning TEXT,
            h2h_summary TEXT,
            home_form TEXT,
            away_form TEXT,
            home_goals_avg REAL,
            away_goals_avg REAL,
            home_goals_trend TEXT,
            away_goals_trend TEXT,
            value_bets TEXT,
            csv_data TEXT,
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
            value_bet_results TEXT,
            updated_at TEXT DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS'),
            created_at TEXT DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS'),
            FOREIGN KEY (analysis_id) REFERENCES analyses(id)
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS pending_matches (
            id SERIAL PRIMARY KEY,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            league TEXT,
            match_date TEXT,
            csv_data TEXT,
            added_date TEXT NOT NULL,
            created_at TEXT DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS coupons (
            id SERIAL PRIMARY KEY,
            coupon_date TEXT NOT NULL,
            items TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            won INTEGER DEFAULT 0,
            total_items INTEGER DEFAULT 0,
            correct_items INTEGER DEFAULT 0,
            created_at TEXT DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
        )
    ''')
    # ── İY Gol Takip tablosu ─────────────────────────────────────────────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS iy_gol_tracker (
            id SERIAL PRIMARY KEY,
            match_date TEXT NOT NULL,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            league TEXT,
            match_time TEXT,
            iy_pct REAL,
            iy2_pct REAL,
            iy_result INTEGER,
            iy2_result INTEGER,
            iy_score TEXT,
            ft_score TEXT,
            created_at TEXT DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
        )
    ''')
    for sql in [
        'ALTER TABLE iy_gol_tracker ADD COLUMN IF NOT EXISTS iy_score TEXT',
        'ALTER TABLE iy_gol_tracker ADD COLUMN IF NOT EXISTS ft_score TEXT',
    ]:
        try:
            cur.execute(sql)
            conn.commit()
        except:
            conn.rollback()
    # ── YENİ: Günlük özet tablosu ────────────────────────────────────────────
    cur.execute('''
        CREATE TABLE IF NOT EXISTS daily_summaries (
            id SERIAL PRIMARY KEY,
            summary_date TEXT NOT NULL UNIQUE,
            ai_provider TEXT DEFAULT 'claude',
            content TEXT NOT NULL,
            created_at TEXT DEFAULT to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
        )
    ''')
    # ─────────────────────────────────────────────────────────────────────────
    for sql in [
        'ALTER TABLE match_results ADD COLUMN IF NOT EXISTS ht_home_score INTEGER',
        'ALTER TABLE match_results ADD COLUMN IF NOT EXISTS ht_away_score INTEGER',
        'ALTER TABLE match_results ADD COLUMN IF NOT EXISTS ht_correct INTEGER DEFAULT 0',
        'ALTER TABLE analyses ADD COLUMN IF NOT EXISTS home_goals_trend TEXT',
        'ALTER TABLE analyses ADD COLUMN IF NOT EXISTS away_goals_trend TEXT',
        'ALTER TABLE analyses ADD COLUMN IF NOT EXISTS value_bets TEXT',
        'ALTER TABLE analyses ADD COLUMN IF NOT EXISTS csv_data TEXT',
        'ALTER TABLE match_results ADD COLUMN IF NOT EXISTS value_bet_results TEXT',
        'ALTER TABLE analyses ADD COLUMN IF NOT EXISTS predicted_ht_score TEXT',
        'ALTER TABLE coupons ADD COLUMN IF NOT EXISTS coupon_type TEXT DEFAULT \'dengeli\'',
    ]:
        try:
            cur.execute(sql)
            conn.commit()
        except:
            conn.rollback()
    conn.commit()
    cur.close()
    conn.close()


# ── Günlük Özet ──────────────────────────────────────────────────────────────

def save_summary(date_str, content, ai_provider='claude'):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO daily_summaries (summary_date, content, ai_provider)
        VALUES (%s, %s, %s)
        ON CONFLICT (summary_date) DO UPDATE
        SET content = EXCLUDED.content,
            ai_provider = EXCLUDED.ai_provider,
            created_at = to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
    ''', (date_str, content, ai_provider))
    conn.commit()
    cur.close()
    conn.close()


def get_summary_by_date(date_str):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SELECT * FROM daily_summaries WHERE summary_date = %s', (date_str,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def get_summary_list(limit=30):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        'SELECT summary_date, ai_provider, created_at FROM daily_summaries ORDER BY summary_date DESC LIMIT %s',
        (limit,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]

# ─────────────────────────────────────────────────────────────────────────────


def save_pending_matches(matches: list):
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_conn()
    cur = conn.cursor()
    for m in matches:
        cur.execute('''
            INSERT INTO pending_matches (home_team, away_team, league, match_date, csv_data, added_date)
            VALUES (%s, %s, %s, %s, %s, %s)
        ''', (
            m['home_team'], m['away_team'],
            m.get('league', ''), m.get('date', ''),
            json.dumps(m.get('csv_data'), ensure_ascii=False) if m.get('csv_data') else None,
            today
        ))
    conn.commit()
    cur.close()
    conn.close()


def get_pending_matches():
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SELECT * FROM pending_matches WHERE added_date = %s ORDER BY id ASC', (today,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    result = []
    for r in rows:
        row = dict(r)
        if row.get('csv_data'):
            try:
                row['csv_data'] = json.loads(row['csv_data'])
            except:
                row['csv_data'] = None
        result.append(row)
    return result


def clear_pending_matches():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('DELETE FROM pending_matches')
    conn.commit()
    cur.close()
    conn.close()


def clear_old_pending_matches():
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('DELETE FROM pending_matches WHERE added_date < %s', (today,))
    conn.commit()
    cur.close()
    conn.close()


def save_coupon(items: list, coupon_type: str = 'dengeli'):
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT id FROM coupons WHERE coupon_date = %s AND coupon_type = %s', (today, coupon_type))
    existing = cur.fetchone()
    if existing:
        cur.execute('''
            UPDATE coupons SET items=%s, status='pending', won=0, total_items=%s, correct_items=0
            WHERE coupon_date=%s AND coupon_type=%s
        ''', (json.dumps(items, ensure_ascii=False), len(items), today, coupon_type))
    else:
        cur.execute('''
            INSERT INTO coupons (coupon_date, coupon_type, items, status, total_items)
            VALUES (%s, %s, %s, 'pending', %s)
        ''', (today, coupon_type, json.dumps(items, ensure_ascii=False), len(items)))
    conn.commit()
    cur.close()
    conn.close()


def get_coupons(limit=30):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SELECT * FROM coupons ORDER BY coupon_date DESC LIMIT %s', (limit,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    result = []
    for r in rows:
        row = dict(r)
        try:
            row['items'] = json.loads(row['items'])
        except:
            row['items'] = []
        result.append(row)
    return result


def get_coupon_by_date(date_str, coupon_type=None):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if coupon_type:
        cur.execute('SELECT * FROM coupons WHERE coupon_date = %s AND coupon_type = %s', (date_str, coupon_type))
    else:
        cur.execute('SELECT * FROM coupons WHERE coupon_date = %s ORDER BY id DESC', (date_str,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    result = dict(row)
    try:
        result['items'] = json.loads(result['items'])
    except:
        result['items'] = []
    return result


def _update_single_coupon(coupon, cur):
    """Tek bir kuponun sonuçlarını güncelle — tüm tipler için ortak mantık."""
    items = coupon['items']
    if not items:
        return
    correct = 0
    updated_items = []
    for item in items:
        analysis_id = item.get('analysis_id')
        pred_type = item.get('prediction_type')
        item_result = None
        if analysis_id:
            cur.execute('''
                SELECT r.*, a.prediction_1x2
                FROM match_results r
                JOIN analyses a ON a.id = r.analysis_id
                WHERE r.analysis_id = %s
            ''', (analysis_id,))
            row = cur.fetchone()
            if row:
                row = dict(row)
                if pred_type == '1X2':
                    item_result = bool(row.get('pred_1x2_correct'))
                elif pred_type in ('2.5 Ust', '2.5 Üst'):
                    item_result = bool(row.get('over25_correct'))
                elif pred_type in ('2.5 Alt',):
                    item_result = not bool(row.get('actual_over25'))
                elif pred_type == 'KG Var':
                    item_result = bool(row.get('btts_correct'))
                elif pred_type == 'KG Yok':
                    item_result = not bool(row.get('actual_btts'))
                elif pred_type in ('IY 0.5 Ust', 'İY 0.5 Üst'):
                    item_result = bool(row.get('ht_correct'))
                elif pred_type == 'Over 1.5':
                    item_result = (row.get('total_goals') or 0) > 1
                elif pred_type == 'Over 3.5':
                    item_result = (row.get('total_goals') or 0) > 3
                elif pred_type == '2.5 Ust + KG Var':
                    item_result = bool(row.get('actual_over25')) and bool(row.get('actual_btts'))
                elif pred_type == 'COMBO_O25_BTTS':
                    item_result = bool(row.get('over25_correct')) and bool(row.get('btts_correct'))
                elif pred_type == 'COMBO_1X2_O15':
                    item_result = bool(row.get('pred_1x2_correct')) and (row.get('total_goals') or 0) > 1
                elif pred_type == 'COMBO_1X2_BTTS':
                    item_result = bool(row.get('pred_1x2_correct')) and bool(row.get('btts_correct'))
        item['result'] = item_result
        if item_result is True:
            correct += 1
        updated_items.append(item)
    total = len(updated_items)
    all_resolved = all(i.get('result') is not None for i in updated_items)
    all_correct = (correct == total) and all_resolved
    status = 'completed' if all_resolved else 'pending'
    won = 1 if all_correct else 0
    cur.execute('''
        UPDATE coupons SET items=%s, correct_items=%s, won=%s, status=%s
        WHERE id=%s
    ''', (json.dumps(updated_items, ensure_ascii=False), correct, won, status, coupon['id']))


def update_coupon_results(date_str):
    """O güne ait tüm kupon tiplerini güncelle (güvenli, dengeli, riskli)."""
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SELECT * FROM coupons WHERE coupon_date = %s', (date_str,))
    coupons = cur.fetchall()
    for row in coupons:
        coupon = dict(row)
        try:
            coupon['items'] = json.loads(coupon['items']) if isinstance(coupon['items'], str) else coupon['items']
        except:
            coupon['items'] = []
        _update_single_coupon(coupon, cur)
    conn.commit()
    cur.close()
    conn.close()


def get_value_bet_stats():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SELECT value_bet_results FROM match_results WHERE value_bet_results IS NOT NULL')
    rows = cur.fetchall()
    cur.close()
    conn.close()
    stats = {}
    for row in rows:
        try:
            bets = json.loads(row['value_bet_results'])
            for b in bets:
                label = b.get('label', 'Diger')
                correct = b.get('correct')
                if correct is None:
                    continue
                if label not in stats:
                    stats[label] = {'total': 0, 'correct': 0, 'total_diff': 0}
                stats[label]['total'] += 1
                if correct:
                    stats[label]['correct'] += 1
                stats[label]['total_diff'] += b.get('diff', 0)
        except:
            continue
    result = []
    for label, s in stats.items():
        t = s['total']
        c = s['correct']
        result.append({
            'label': label, 'total': t, 'correct': c,
            'pct': round(c / t * 100) if t else 0,
            'avg_diff': round(s['total_diff'] / t, 1) if t else 0,
        })
    result.sort(key=lambda x: x['total'], reverse=True)
    return result


def save_analysis(data: dict):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO analyses (
            analysis_date, fixture_id, home_team, away_team, league, match_time,
            prediction_1x2, over25_pct, ht2g_pct, btts_pct, predicted_score,
            predicted_ht_score, confidence, reasoning, h2h_summary, home_form, away_form,
            home_goals_avg, away_goals_avg, home_goals_trend, away_goals_trend,
            value_bets, csv_data
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    ''', (
        data.get('analysis_date', datetime.now().strftime('%Y-%m-%d')),
        data.get('fixture_id'),
        data['home_team'], data['away_team'],
        data.get('league', ''), data.get('match_time', ''),
        data.get('prediction_1x2', ''), data.get('over25_pct', 0),
        data.get('ht2g_pct', 0), data.get('btts_pct', 0),
        data.get('predicted_score', ''),
        data.get('predicted_ht_score', ''),
        data.get('confidence', 'Orta'),
        data.get('reasoning', ''), data.get('h2h_summary', ''),
        data.get('home_form', ''), data.get('away_form', ''),
        data.get('home_goals_avg', 0), data.get('away_goals_avg', 0),
        data.get('home_goals_trend'), data.get('away_goals_trend'),
        data.get('value_bets'),
        json.dumps(data.get('csv_data'), ensure_ascii=False) if data.get('csv_data') is not None else None,
    ))
    conn.commit()
    cur.close()
    conn.close()


def _decode_csv_data_in_rows(rows):
    result = []
    for r in rows:
        row = dict(r)
        if row.get('csv_data'):
            try:
                row['csv_data'] = json.loads(row['csv_data']) if isinstance(row['csv_data'], str) else row['csv_data']
            except:
                row['csv_data'] = None
        result.append(row)
    return result


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
    return _decode_csv_data_in_rows(rows)


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
    return _decode_csv_data_in_rows(rows)


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
    return _decode_csv_data_in_rows(rows)


def get_analyses_by_date_with_results(date_str):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('''
        SELECT
            a.*,
            r.home_score, r.away_score,
            r.ht_home_score, r.ht_away_score,
            r.actual_1x2, r.pred_1x2_correct,
            r.actual_over25, r.over25_correct,
            r.actual_btts, r.btts_correct,
            r.score_correct, r.ht_correct, r.total_goals,
            r.value_bet_results
        FROM analyses a
        LEFT JOIN match_results r ON a.id = r.analysis_id
        WHERE a.analysis_date = %s
        ORDER BY a.confidence DESC, a.over25_pct DESC
    ''', (date_str,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return _decode_csv_data_in_rows(rows)


def get_analysis_by_id(analysis_id):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('SELECT * FROM analyses WHERE id = %s', (analysis_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    result = dict(row)
    if result.get('csv_data'):
        try:
            result['csv_data'] = json.loads(result['csv_data']) if isinstance(result['csv_data'], str) else result['csv_data']
        except:
            result['csv_data'] = None
    return result


def get_available_dates():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT DISTINCT analysis_date FROM analyses ORDER BY analysis_date DESC LIMIT 30')
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
                      ht_home_score=None, ht_away_score=None, ht_correct=0,
                      value_bet_results=None):
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
                total_goals=%s, source=%s,
                value_bet_results=%s
            WHERE analysis_id=%s
        ''', (home_score, away_score, ht_home_score, ht_away_score,
              actual_1x2, pred_1x2_correct, actual_over25, over25_correct,
              actual_btts, btts_correct, score_correct, ht_correct,
              total_goals, source,
              json.dumps(value_bet_results, ensure_ascii=False) if value_bet_results else None,
              analysis_id))
    else:
        cur.execute('''
            INSERT INTO match_results (
                analysis_id, fixture_id, home_score, away_score,
                ht_home_score, ht_away_score,
                actual_1x2, pred_1x2_correct,
                actual_over25, over25_correct,
                actual_btts, btts_correct,
                score_correct, ht_correct,
                total_goals, source, value_bet_results
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (analysis_id, fixture_id, home_score, away_score,
              ht_home_score, ht_away_score,
              actual_1x2, pred_1x2_correct,
              actual_over25, over25_correct,
              actual_btts, btts_correct,
              score_correct, ht_correct,
              total_goals, source,
              json.dumps(value_bet_results, ensure_ascii=False) if value_bet_results else None))
    conn.commit()
    cur.close()
    conn.close()


def mark_telegram_sent(analysis_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('UPDATE match_results SET telegram_sent=1 WHERE analysis_id=%s', (analysis_id,))
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


def clear_today_analyses():
    delete_today_analyses()


# ── İY Gol Tracker ───────────────────────────────────────────────────────────

def save_iy_match(date, home, away, league, time, iy_pct, iy2_pct):
    conn = get_conn()
    cur = conn.cursor()
    # Aynı gün aynı maç varsa güncelle, yoksa ekle
    cur.execute(
        'SELECT id FROM iy_gol_tracker WHERE match_date=%s AND home_team=%s AND away_team=%s',
        (date, home, away)
    )
    existing = cur.fetchone()
    if existing:
        cur.execute('''
            UPDATE iy_gol_tracker SET league=%s, match_time=%s, iy_pct=%s, iy2_pct=%s
            WHERE id=%s
        ''', (league, time, iy_pct, iy2_pct, existing[0]))
        row_id = existing[0]
    else:
        cur.execute('''
            INSERT INTO iy_gol_tracker (match_date, home_team, away_team, league, match_time, iy_pct, iy2_pct)
            VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        ''', (date, home, away, league, time, iy_pct, iy2_pct))
        row_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return row_id


def get_iy_matches_by_date(date):
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        'SELECT * FROM iy_gol_tracker WHERE match_date=%s ORDER BY match_time ASC, id ASC',
        (date,)
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def update_iy_result(row_id, iy_result, iy2_result, iy_score=None, ft_score=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        'UPDATE iy_gol_tracker SET iy_result=%s, iy2_result=%s, iy_score=%s, ft_score=%s WHERE id=%s',
        (iy_result, iy2_result, iy_score, ft_score, row_id)
    )
    conn.commit()
    cur.close()
    conn.close()


def get_iy_stats():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute('''
        SELECT
            COUNT(CASE WHEN iy_result IS NOT NULL THEN 1 END) as total_resolved,
            SUM(CASE WHEN iy_result = 1 THEN 1 ELSE 0 END) as iy_correct,
            SUM(CASE WHEN iy_result = 0 AND iy2_result = 1 THEN 1 ELSE 0 END) as saved,
            SUM(CASE WHEN iy_result = 0 AND iy2_result = 0 THEN 1 ELSE 0 END) as none
        FROM iy_gol_tracker
        WHERE iy_result IS NOT NULL
    ''')
    row = dict(cur.fetchone())
    cur.close()
    conn.close()
    total = row['total_resolved'] or 0
    iy_correct = row['iy_correct'] or 0
    saved = row['saved'] or 0
    none_ = row['none'] or 0
    return {
        'total_resolved': total,
        'iy_correct': iy_correct,
        'iy_pct': round(iy_correct / total * 100) if total else 0,
        'saved': saved,
        'saved_pct': round(saved / total * 100) if total else 0,
        'none': none_,
        'none_pct': round(none_ / total * 100) if total else 0,
    }
