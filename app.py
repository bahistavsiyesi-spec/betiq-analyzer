from flask import Flask, render_template, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import os
import threading
from datetime import datetime
from backend.analyzer import run_selected_analysis
from backend.database import (
    init_db, get_today_matches, get_analyses_by_date,
    get_available_dates, save_pending_matches, get_pending_matches,
    clear_pending_matches, clear_old_pending_matches,
    save_coupon, get_coupons, update_coupon_results,
    get_value_bet_stats,
    save_summary, get_summary_by_date, get_summary_list
)

app = Flask(__name__, template_folder='frontend/templates', static_folder='frontend/static', static_url_path='/static')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
init_db()

def _get_month_filter(request):
    """?month=2026-04 parametresinden WHERE clause ve params döndürür"""
    month = request.args.get('month', '')
    if month and len(month) == 7:  # YYYY-MM formatı
        try:
            year, mon = month.split('-')
            from datetime import date
            import calendar
            last_day = calendar.monthrange(int(year), int(mon))[1]
            date_from = f"{year}-{mon}-01"
            date_to   = f"{year}-{mon}-{last_day:02d}"
            return "AND a.analysis_date BETWEEN %s AND %s", (date_from, date_to)
        except:
            pass
    return "", ()


def scheduled_result_check():
    try:
        from backend.results_checker import check_and_send_results
        check_and_send_results()
    except Exception as e:
        logger.error(f"Scheduled result check failed: {e}")

def midnight_reset():
    try:
        clear_old_pending_matches()
        logger.info("Gece sifirlama: eski pending maclar silindi.")
    except Exception as e:
        logger.error(f"Midnight reset failed: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(scheduled_result_check, 'interval', hours=6, id='result_check')
scheduler.add_job(midnight_reset, 'cron', hour=0, minute=1, id='midnight_reset')
scheduler.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/gecmis')
def gecmis():
    return render_template('gecmis.html')

@app.route('/istatistik')
def istatistik():
    return render_template('istatistik.html')

@app.route('/kuponlar')
def kuponlar():
    return render_template('kuponlar.html')

@app.route('/debug')
def debug():
    return render_template('debug.html')


# Fixtures
@app.route('/api/fixtures/today')
def api_today_fixtures():
    pending = get_pending_matches()
    result = []
    for p in pending:
        result.append({
            'id': p['id'],
            'date': p.get('match_date', ''),
            'league': p.get('league', ''),
            'home_team': p['home_team'],
            'away_team': p['away_team'],
            'csv_data': p.get('csv_data'),
        })
    return jsonify(result)


# CSV Upload
@app.route('/api/csv/upload', methods=['POST'])
def api_csv_upload():
    try:
        data = request.get_json()
        matches = data.get('matches', [])
        if not matches:
            return jsonify({"status": "error", "message": "Mac listesi bos"}), 400
        clear_pending_matches()
        save_pending_matches(matches)
        logger.info(f"CSV upload: {len(matches)} mac kaydedildi")
        return jsonify({"status": "success", "message": f"{len(matches)} mac yuklendi!", "total": len(matches)})
    except Exception as e:
        logger.error(f"CSV upload error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/matches/today')
def api_today_matches():
    matches = get_today_matches()
    return jsonify(matches)

@app.route('/api/matches/date/<date_str>')
def api_matches_by_date(date_str):
    try:
        from backend.database import get_analyses_by_date_with_results
        matches = get_analyses_by_date_with_results(date_str)
        return jsonify(matches)
    except Exception as e:
        logger.error(f"Error fetching matches by date: {e}")
        return jsonify([])

@app.route('/api/dates')
def api_available_dates():
    dates = get_available_dates()
    return jsonify(dates)


# Istatistik
@app.route('/api/stats/overview')
def api_stats_overview():
    try:
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(os.environ.get('DATABASE_URL', ''))
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        month_clause, month_params = _get_month_filter(request)
        cur.execute(f'''
            SELECT COUNT(*) as total, SUM(r.score_correct) as cscore,
                COUNT(CASE WHEN a.confidence IN ('Yuksek','Cok Yuksek','Yüksek','Çok Yüksek') THEN 1 END) as total_1x2,
                SUM(CASE WHEN a.confidence IN ('Yuksek','Cok Yuksek','Yüksek','Çok Yüksek') THEN r.pred_1x2_correct ELSE 0 END) as c1x2,
                COUNT(CASE WHEN a.over25_pct >= 65 THEN 1 END) as total_over25,
                SUM(CASE WHEN a.over25_pct >= 65 THEN r.over25_correct ELSE 0 END) as cover25,
                COUNT(CASE WHEN a.btts_pct >= 65 THEN 1 END) as total_btts,
                SUM(CASE WHEN a.btts_pct >= 65 THEN r.btts_correct ELSE 0 END) as cbtts,
                COUNT(CASE WHEN a.ht2g_pct >= 65 AND r.ht_home_score IS NOT NULL THEN 1 END) as total_ht,
                SUM(CASE WHEN a.ht2g_pct >= 65 AND r.ht_home_score IS NOT NULL THEN r.ht_correct ELSE 0 END) as cht
            FROM match_results r
            JOIN analyses a ON a.id = r.analysis_id
            WHERE 1=1 {{month_clause}}
        '''.format(month_clause=month_clause), month_params)
        row = dict(cur.fetchone())
        total = row['total'] or 0
        total_1x2 = row['total_1x2'] or 0
        total_over25 = row['total_over25'] or 0
        total_btts = row['total_btts'] or 0
        total_ht = row['total_ht'] or 0
        result = {
            'total': total,
            '1x2': {'correct': row['c1x2'] or 0, 'total': total_1x2, 'pct': round((row['c1x2'] or 0)/total_1x2*100) if total_1x2 else 0},
            'over25': {'correct': row['cover25'] or 0, 'total': total_over25, 'pct': round((row['cover25'] or 0)/total_over25*100) if total_over25 else 0},
            'btts': {'correct': row['cbtts'] or 0, 'total': total_btts, 'pct': round((row['cbtts'] or 0)/total_btts*100) if total_btts else 0},
            'score': {'correct': row['cscore'] or 0, 'pct': round((row['cscore'] or 0)/total*100) if total else 0},
            'ht': {'correct': row['cht'] or 0, 'total': total_ht,
                   'pct': round((row['cht'] or 0)/total_ht*100) if total_ht else 0},
        }
        cur.close(); conn.close()
        return jsonify(result)
    except Exception as e:
        logger.error(f"Stats overview error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats/daily')
def api_stats_daily():
    try:
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(os.environ.get('DATABASE_URL', ''))
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        month_clause, month_params = _get_month_filter(request)
        cur.execute(f'''
            SELECT a.analysis_date, COUNT(*) as total,
                SUM(r.pred_1x2_correct) as c1x2,
                SUM(CASE WHEN a.over25_pct >= 65 THEN r.over25_correct ELSE 0 END) as cover25,
                COUNT(CASE WHEN a.over25_pct >= 65 THEN 1 END) as total_over25,
                SUM(CASE WHEN a.btts_pct >= 65 THEN r.btts_correct ELSE 0 END) as cbtts,
                COUNT(CASE WHEN a.btts_pct >= 65 THEN 1 END) as total_btts,
                SUM(CASE WHEN a.ht2g_pct >= 65 AND r.ht_home_score IS NOT NULL THEN r.ht_correct ELSE 0 END) as cht,
                COUNT(CASE WHEN a.ht2g_pct >= 65 AND r.ht_home_score IS NOT NULL THEN 1 END) as total_ht
            FROM analyses a JOIN match_results r ON a.id = r.analysis_id
            WHERE 1=1 {{month_clause}}
            GROUP BY a.analysis_date ORDER BY a.analysis_date DESC LIMIT 31
        '''.format(month_clause=month_clause), month_params)
        rows = [dict(r) for r in cur.fetchall()]
        rows.reverse()
        daily = []
        for r in rows:
            t = r['total'] or 0
            total_over25 = r['total_over25'] or 0
            total_btts = r['total_btts'] or 0
            total_ht = r['total_ht'] or 0
            daily.append({
                'date': r['analysis_date'], 'total': t,
                'pct_1x2': round((r['c1x2'] or 0)/t*100) if t else 0,
                'pct_over25': round((r['cover25'] or 0)/total_over25*100) if total_over25 else 0,
                'pct_btts': round((r['cbtts'] or 0)/total_btts*100) if total_btts else 0,
                'pct_ht': round((r['cht'] or 0)/total_ht*100) if total_ht else 0,
            })
        cur.close(); conn.close()
        return jsonify(daily)
    except Exception as e:
        logger.error(f"Stats daily error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats/by-category')
def api_stats_by_category():
    try:
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(os.environ.get('DATABASE_URL', ''))
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        month_clause, month_params = _get_month_filter(request)
        cur.execute(f'''
            SELECT COUNT(*) as total, SUM(r.score_correct) as cscore,
                COUNT(CASE WHEN a.confidence IN ('Yuksek','Coc Yuksek','Yüksek','Çok Yüksek') THEN 1 END) as total_1x2,
                SUM(CASE WHEN a.confidence IN ('Yuksek','Cok Yuksek','Yüksek','Çok Yüksek') THEN r.pred_1x2_correct ELSE 0 END) as c1x2,
                COUNT(CASE WHEN a.over25_pct >= 65 THEN 1 END) as total_over25,
                SUM(CASE WHEN a.over25_pct >= 65 THEN r.over25_correct ELSE 0 END) as cover25,
                COUNT(CASE WHEN a.btts_pct >= 65 THEN 1 END) as total_btts,
                SUM(CASE WHEN a.btts_pct >= 65 THEN r.btts_correct ELSE 0 END) as cbtts,
                COUNT(CASE WHEN a.ht2g_pct >= 65 AND r.ht_home_score IS NOT NULL THEN 1 END) as total_ht,
                SUM(CASE WHEN a.ht2g_pct >= 65 AND r.ht_home_score IS NOT NULL THEN r.ht_correct ELSE 0 END) as cht
            FROM match_results r
            JOIN analyses a ON a.id = r.analysis_id
            WHERE 1=1 {{month_clause}}
        '''.format(month_clause=month_clause), month_params)
        row = dict(cur.fetchone())
        total = row['total'] or 0
        total_1x2 = row['total_1x2'] or 0
        total_over25 = row['total_over25'] or 0
        total_btts = row['total_btts'] or 0
        total_ht = row['total_ht'] or 0
        categories = [
            {'name': '1X2 (Y/ÇY)', 'correct': row['c1x2'] or 0, 'total': total_1x2, 'pct': round((row['c1x2'] or 0)/total_1x2*100) if total_1x2 else 0},
            {'name': '2.5 Ust (%65+)', 'correct': row['cover25'] or 0, 'total': total_over25, 'pct': round((row['cover25'] or 0)/total_over25*100) if total_over25 else 0},
            {'name': 'KG Var (%65+)', 'correct': row['cbtts'] or 0, 'total': total_btts, 'pct': round((row['cbtts'] or 0)/total_btts*100) if total_btts else 0},
            {'name': 'Skor', 'correct': row['cscore'] or 0, 'total': total, 'pct': round((row['cscore'] or 0)/total*100) if total else 0},
            {'name': 'IY 0.5 Ust (%65+)', 'correct': row['cht'] or 0, 'total': total_ht, 'pct': round((row['cht'] or 0)/total_ht*100) if total_ht else 0},
        ]
        cur.close(); conn.close()
        return jsonify(categories)
    except Exception as e:
        logger.error(f"Stats by category error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats/by-league')
def api_stats_by_league():
    try:
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(os.environ.get('DATABASE_URL', ''))
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        month_clause, month_params = _get_month_filter(request)
        cur.execute(f'''
            SELECT a.league, COUNT(*) as total,
                SUM(r.pred_1x2_correct) as c1x2,
                SUM(r.over25_correct) as cover25,
                SUM(r.btts_correct) as cbtts,
                COUNT(CASE WHEN r.ht_home_score IS NOT NULL THEN 1 END) as total_ht,
                SUM(r.ht_correct) as cht
            FROM analyses a JOIN match_results r ON a.id = r.analysis_id
            WHERE 1=1 {{month_clause}}
            GROUP BY a.league HAVING COUNT(*) >= 3 ORDER BY COUNT(*) DESC
        '''.format(month_clause=month_clause), month_params)
        rows = [dict(r) for r in cur.fetchall()]
        leagues = []
        for r in rows:
            t = r['total'] or 0
            total_ht = r['total_ht'] or 0
            leagues.append({
                'league': r['league'], 'total': t,
                'pct_1x2': round((r['c1x2'] or 0)/t*100) if t else 0,
                'pct_over25': round((r['cover25'] or 0)/t*100) if t else 0,
                'pct_btts': round((r['cbtts'] or 0)/t*100) if t else 0,
                'pct_ht': round((r['cht'] or 0)/total_ht*100) if total_ht else 0,
                'total_ht': total_ht,
            })
        cur.close(); conn.close()
        return jsonify(leagues)
    except Exception as e:
        logger.error(f"Stats by league error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats/by-confidence')
def api_stats_by_confidence():
    try:
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(os.environ.get('DATABASE_URL', ''))
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        month_clause, month_params = _get_month_filter(request)
        cur.execute(f'''
            SELECT a.confidence, COUNT(*) as total,
                SUM(r.pred_1x2_correct) as c1x2,
                SUM(r.over25_correct) as cover25,
                SUM(r.btts_correct) as cbtts
            FROM analyses a JOIN match_results r ON a.id = r.analysis_id
            WHERE 1=1 {{month_clause}}
            GROUP BY a.confidence ORDER BY COUNT(*) DESC
        '''.format(month_clause=month_clause), month_params)
        rows = [dict(r) for r in cur.fetchall()]

        def normalize_conf(c):
            c = (c or '').strip()
            mapping = {
                'Çok Yüksek': 'Çok Yüksek', 'Cok Yuksek': 'Çok Yüksek',
                'Çok yüksek': 'Çok Yüksek', 'cok yuksek': 'Çok Yüksek',
                'Yüksek': 'Yüksek', 'Yuksek': 'Yüksek',
                'yüksek': 'Yüksek', 'yuksek': 'Yüksek',
                'Orta': 'Orta', 'orta': 'Orta',
                'Düşük': 'Düşük', 'Dusuk': 'Düşük',
                'düşük': 'Düşük', 'dusuk': 'Düşük',
            }
            return mapping.get(c, c)

        merged = {}
        for r in rows:
            key = normalize_conf(r['confidence'])
            if key not in merged:
                merged[key] = {'confidence': key, 'total': 0, 'c1x2': 0, 'cover25': 0, 'cbtts': 0}
            merged[key]['total']   += r['total'] or 0
            merged[key]['c1x2']    += r['c1x2'] or 0
            merged[key]['cover25'] += r['cover25'] or 0
            merged[key]['cbtts']   += r['cbtts'] or 0

        order = ['Çok Yüksek', 'Yüksek', 'Orta', 'Düşük']
        result = []
        for key in order:
            if key not in merged:
                continue
            m = merged[key]
            t = m['total'] or 0
            result.append({
                'confidence': m['confidence'], 'total': t,
                'pct_1x2': round(m['c1x2']/t*100) if t else 0,
                'pct_over25': round(m['cover25']/t*100) if t else 0,
                'pct_btts': round(m['cbtts']/t*100) if t else 0,
            })
        cur.close(); conn.close()
        return jsonify(result)
    except Exception as e:
        logger.error(f"Stats by confidence error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats/best-worst-days')
def api_stats_best_worst_days():
    try:
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(os.environ.get('DATABASE_URL', ''))
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        month_clause, month_params = _get_month_filter(request)
        cur.execute(f'''
            SELECT a.analysis_date, COUNT(*) as total, SUM(r.pred_1x2_correct) as c1x2
            FROM analyses a JOIN match_results r ON a.id = r.analysis_id
            WHERE 1=1 {{month_clause}}
            GROUP BY a.analysis_date HAVING COUNT(*) >= 2
            ORDER BY (SUM(r.pred_1x2_correct)::float / COUNT(*)) DESC
        '''.format(month_clause=month_clause), month_params)
        rows = [dict(r) for r in cur.fetchall()]
        all_days = [{'date': r['analysis_date'], 'total': r['total'] or 0, 'correct': r['c1x2'] or 0,
                     'pct': round((r['c1x2'] or 0)/(r['total'] or 1)*100)} for r in rows]
        cur.close(); conn.close()
        return jsonify({'best': all_days[:3], 'worst': list(reversed(all_days))[:3]})
    except Exception as e:
        logger.error(f"Stats best/worst error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats/value-bets')
def api_stats_value_bets():
    try:
        data = get_value_bet_stats()
        return jsonify(data)
    except Exception as e:
        logger.error(f"Stats value bets error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/stats/ht-recovery')
def api_stats_ht_recovery():
    try:
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(os.environ.get('DATABASE_URL', ''))
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        month_clause, month_params = _get_month_filter(request)
        cur.execute('''
            SELECT
                COUNT(*) FILTER (WHERE r.ht_correct = 0 AND a.ht2g_pct >= 65 AND r.ht_home_score IS NOT NULL) as total_missed,
                COUNT(*) FILTER (WHERE r.ht_correct = 0 AND a.ht2g_pct >= 65 AND r.ht_home_score IS NOT NULL
                    AND (r.home_score - r.ht_home_score + r.away_score - r.ht_away_score) > 1) as recovered,
                COUNT(*) FILTER (WHERE a.ht2g_pct >= 65 AND r.ht_home_score IS NOT NULL) as total_ht_eligible,
                COUNT(*) FILTER (WHERE a.ht2g_pct >= 65 AND r.ht_home_score IS NOT NULL AND r.ht_correct = 1) as ht_correct_count
            FROM match_results r
            JOIN analyses a ON a.id = r.analysis_id
            WHERE r.ht_home_score IS NOT NULL AND r.home_score IS NOT NULL
        ''' + ((' ' + month_clause) if month_clause else ''), month_params)
        row = dict(cur.fetchone())
        total_missed = row['total_missed'] or 0
        recovered = row['recovered'] or 0
        total_ht = row['total_ht_eligible'] or 0
        ht_correct = row['ht_correct_count'] or 0

        cur.execute('''
            SELECT a.home_team, a.away_team, a.league, a.analysis_date,
                   r.ht_home_score, r.ht_away_score, r.home_score, r.away_score,
                   a.ht2g_pct,
                   (r.home_score - r.ht_home_score + r.away_score - r.ht_away_score) as ht2_goals
            FROM match_results r
            JOIN analyses a ON a.id = r.analysis_id
            WHERE r.ht_correct = 0 AND a.ht2g_pct >= 65
              AND r.ht_home_score IS NOT NULL AND r.home_score IS NOT NULL
        ''' + ((' ' + month_clause) if month_clause else '') + '''
            ORDER BY a.analysis_date DESC LIMIT 10
        ''', month_params)

        recent = []
        for r in cur.fetchall():
            r = dict(r)
            ht2_goals = int(r.get('ht2_goals') or 0)
            recent.append({
                'home_team': r['home_team'], 'away_team': r['away_team'],
                'league': r['league'], 'date': str(r['analysis_date']),
                'ht_score': f"{r['ht_home_score']}-{r['ht_away_score']}",
                'ft_score': f"{r['home_score']}-{r['away_score']}",
                'ht2g_pct': r['ht2g_pct'], 'ht2_goals': ht2_goals,
                'recovered': ht2_goals > 1,
            })
        cur.close(); conn.close()
        return jsonify({
            'total_ht_eligible': total_ht, 'ht_correct': ht_correct,
            'total_missed': total_missed, 'recovered': recovered,
            'recovery_rate': round(recovered / total_missed * 100) if total_missed else 0,
            'recent_missed': recent,
        })
    except Exception as e:
        logger.error(f"Stats ht-recovery error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats/combo-bets')
def api_stats_combo_bets():
    try:
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(os.environ.get('DATABASE_URL', ''))
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        month_clause, month_params = _get_month_filter(request)
        cur.execute(f'''
            SELECT
                COUNT(CASE WHEN a.over25_pct >= 65 AND a.btts_pct >= 65 THEN 1 END) as total_o25_btts,
                SUM(CASE WHEN a.over25_pct >= 65 AND a.btts_pct >= 65 THEN
                    CASE WHEN r.over25_correct = 1 AND r.btts_correct = 1 THEN 1 ELSE 0 END
                END) as correct_o25_btts,
                COUNT(CASE WHEN a.over25_pct >= 65 AND a.ht2g_pct >= 65 AND r.ht_home_score IS NOT NULL THEN 1 END) as total_o25_ht,
                SUM(CASE WHEN a.over25_pct >= 65 AND a.ht2g_pct >= 65 AND r.ht_home_score IS NOT NULL THEN
                    CASE WHEN r.over25_correct = 1 AND r.ht_correct = 1 THEN 1 ELSE 0 END
                END) as correct_o25_ht,
                COUNT(CASE WHEN a.btts_pct >= 65 AND a.ht2g_pct >= 65 AND r.ht_home_score IS NOT NULL THEN 1 END) as total_btts_ht,
                SUM(CASE WHEN a.btts_pct >= 65 AND a.ht2g_pct >= 65 AND r.ht_home_score IS NOT NULL THEN
                    CASE WHEN r.btts_correct = 1 AND r.ht_correct = 1 THEN 1 ELSE 0 END
                END) as correct_btts_ht,
                COUNT(CASE WHEN a.over25_pct >= 65 AND a.btts_pct >= 65 AND a.ht2g_pct >= 65 AND r.ht_home_score IS NOT NULL THEN 1 END) as total_all3,
                SUM(CASE WHEN a.over25_pct >= 65 AND a.btts_pct >= 65 AND a.ht2g_pct >= 65 AND r.ht_home_score IS NOT NULL THEN
                    CASE WHEN r.over25_correct = 1 AND r.btts_correct = 1 AND r.ht_correct = 1 THEN 1 ELSE 0 END
                END) as correct_all3
            FROM match_results r
            JOIN analyses a ON a.id = r.analysis_id
            WHERE 1=1 {{month_clause}}
        '''.format(month_clause=month_clause), month_params)
        row = dict(cur.fetchone())
        cur.close(); conn.close()

        def combo(total_key, correct_key, label):
            t = row[total_key] or 0
            c = row[correct_key] or 0
            return {'label': label, 'total': t, 'correct': c, 'pct': round(c/t*100) if t else 0}

        result = [
            combo('total_o25_btts', 'correct_o25_btts', '2.5 Üst + KG Var'),
            combo('total_o25_ht',   'correct_o25_ht',   '2.5 Üst + İY 0.5 Üst'),
            combo('total_btts_ht',  'correct_btts_ht',  'KG Var + İY 0.5 Üst'),
            combo('total_all3',     'correct_all3',     '2.5 Üst + KG Var + İY 0.5 Üst'),
        ]
        return jsonify(result)
    except Exception as e:
        logger.error(f"Stats combo bets error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats/calibration')
def api_stats_calibration():
    try:
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(os.environ.get('DATABASE_URL', ''))
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        buckets = [
            (65, 70, '65-70'),
            (70, 80, '70-80'),
            (80, 90, '80-90'),
            (90, 101, '90+'),
        ]

        result = {'over25': [], 'btts': [], 'ht2g': []}

        for low, high, label in buckets:
            cur.execute('''
                SELECT COUNT(*) as total, SUM(r.over25_correct) as correct
                FROM analyses a JOIN match_results r ON a.id = r.analysis_id
                WHERE a.over25_pct >= %s AND a.over25_pct < %s
            ''', (low, high))
            row = dict(cur.fetchone())
            total = row['total'] or 0
            correct = row['correct'] or 0
            result['over25'].append({'bucket': label, 'predicted': round((low + min(high, 100)) / 2),
                'total': total, 'correct': correct, 'actual_pct': round(correct / total * 100) if total > 0 else None})

            cur.execute('''
                SELECT COUNT(*) as total, SUM(r.btts_correct) as correct
                FROM analyses a JOIN match_results r ON a.id = r.analysis_id
                WHERE a.btts_pct >= %s AND a.btts_pct < %s
            ''', (low, high))
            row = dict(cur.fetchone())
            total = row['total'] or 0
            correct = row['correct'] or 0
            result['btts'].append({'bucket': label, 'predicted': round((low + min(high, 100)) / 2),
                'total': total, 'correct': correct, 'actual_pct': round(correct / total * 100) if total > 0 else None})

            cur.execute('''
                SELECT COUNT(CASE WHEN r.ht_home_score IS NOT NULL THEN 1 END) as total,
                       SUM(CASE WHEN r.ht_home_score IS NOT NULL THEN r.ht_correct ELSE 0 END) as correct
                FROM analyses a JOIN match_results r ON a.id = r.analysis_id
                WHERE a.ht2g_pct >= %s AND a.ht2g_pct < %s
            ''', (low, high))
            row = dict(cur.fetchone())
            total = row['total'] or 0
            correct = row['correct'] or 0
            result['ht2g'].append({'bucket': label, 'predicted': round((low + min(high, 100)) / 2),
                'total': total, 'correct': correct, 'actual_pct': round(correct / total * 100) if total > 0 else None})

        cur.close()
        conn.close()
        return jsonify(result)
    except Exception as e:
        logger.error(f"Stats calibration error: {e}")
        return jsonify({"error": str(e)}), 500


# Analiz
@app.route('/api/analyze/selected', methods=['POST'])
def api_analyze_selected():
    data = request.get_json()
    selected_ids = data.get('fixture_ids', [])
    manual_matches = data.get('manual_matches', [])
    ai_provider = data.get('ai_provider', 'claude')

    if selected_ids:
        pending = get_pending_matches()
        pending_map = {p['id']: p for p in pending}
        for fid in selected_ids:
            if fid in pending_map:
                p = pending_map[fid]
                manual_matches.append({
                    'home_team': p['home_team'],
                    'away_team': p['away_team'],
                    'league': p['league'],
                    'date': p.get('match_date', ''),
                    'csv_data': p.get('csv_data'),
                })

    if not manual_matches:
        return jsonify({"status": "error", "message": "Hic mac secilmedi!"}), 400

    def run_analysis():
        try:
            run_selected_analysis([], manual_matches, ai_provider=ai_provider)
        except Exception as e:
            logger.error(f"Analysis error: {e}")

    thread = threading.Thread(target=run_analysis)
    thread.daemon = False
    thread.start()
    total = len(manual_matches)
    return jsonify({"status": "success", "message": f"{total} mac analiz ediliyor...", "total": total})


# Diger Endpointler

@app.route('/api/telegram/send-card', methods=['POST'])
def api_telegram_send_card():
    try:
        import base64, requests as req
        data = request.get_json()
        image_data = data.get('image')  # base64 PNG
        caption = data.get('caption', '')
        if not image_data:
            return jsonify({"status": "error", "message": "Gorsel eksik"}), 400
        token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
        if not token or not chat_id:
            return jsonify({"status": "error", "message": "Telegram ayarlari eksik"}), 400
        img_bytes = base64.b64decode(image_data)
        resp = req.post(
            f'https://api.telegram.org/bot{token}/sendPhoto',
            data={'chat_id': chat_id, 'caption': caption, 'parse_mode': 'HTML'},
            files={'photo': ('card.png', img_bytes, 'image/png')},
            timeout=30
        )
        resp.raise_for_status()
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Telegram send card error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/telegram/send', methods=['POST'])
def api_telegram_send():
    try:
        from backend.telegram_sender import send_daily_analysis
        matches = get_today_matches()
        if not matches:
            return jsonify({"status": "error", "message": "Gonderilecek analiz yok"}), 400
        send_daily_analysis(matches)
        return jsonify({"status": "success", "message": f"{len(matches)} mac Telegram'a gonderildi!"})
    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/results/check', methods=['POST'])
def api_check_results():
    def check():
        try:
            from backend.results_checker import check_and_send_results
            check_and_send_results()
        except Exception as e:
            logger.error(f"Manual result check failed: {e}")
    thread = threading.Thread(target=check)
    thread.daemon = False
    thread.start()
    return jsonify({"status": "success", "message": "Sonuclar kontrol ediliyor..."})

@app.route('/api/results/manual', methods=['POST'])
def api_manual_result():
    try:
        data = request.get_json()
        analysis_id = data.get('analysis_id')
        home_score = data.get('home_score')
        away_score = data.get('away_score')
        ht_home_score = data.get('ht_home_score')
        ht_away_score = data.get('ht_away_score')
        if analysis_id is None or home_score is None or away_score is None:
            return jsonify({"status": "error", "message": "Eksik veri"}), 400
        from backend.database import get_analysis_by_id, save_match_result, mark_telegram_sent
        from backend.results_checker import send_result_to_telegram, calculate_outcomes, calculate_value_bet_results
        analysis = get_analysis_by_id(analysis_id)
        if not analysis:
            return jsonify({"status": "error", "message": "Analiz bulunamadi"}), 404
        ht_hs = int(ht_home_score) if ht_home_score not in (None, '') else None
        ht_as = int(ht_away_score) if ht_away_score not in (None, '') else None
        outcomes = calculate_outcomes(analysis, home_score, away_score, ht_hs, ht_as)
        for k in ['pred_1x2_correct','actual_over25','over25_correct','actual_btts','btts_correct','score_correct','ht_correct']:
            outcomes[k] = int(outcomes[k])
        # ht2_over15_correct DB'ye kaydedilmiyor, outcomes'dan çıkar
        outcomes.pop('ht2_over15_correct', None)
        vb_results = calculate_value_bet_results(analysis, outcomes)
        save_match_result(analysis_id=analysis_id, fixture_id=analysis.get('fixture_id'),
                          home_score=home_score, away_score=away_score,
                          ht_home_score=ht_hs, ht_away_score=ht_as, source='manual',
                          value_bet_results=vb_results, **outcomes)
        send_telegram = data.get('send_telegram', False)
        if send_telegram:
            # Telegram'ı arka planda gönder — kullanıcı beklemeden yanıt dönsün
            def _send_tg():
                try:
                    send_result_to_telegram(analysis, home_score, away_score, outcomes, ht_hs, ht_as)
                    mark_telegram_sent(analysis_id)
                except Exception as e:
                    logger.error(f"Telegram send error (background): {e}")
            t = threading.Thread(target=_send_tg)
            t.daemon = True
            t.start()
        try:
            analysis_date = analysis.get('analysis_date', datetime.now().strftime('%Y-%m-%d'))
            update_coupon_results(analysis_date)
            today = datetime.now().strftime('%Y-%m-%d')
            if analysis_date != today:
                update_coupon_results(today)
        except Exception as e:
            logger.warning(f"Coupon update after result: {e}")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Manual result error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/report/daily', methods=['POST'])
def api_daily_report():
    try:
        data = request.get_json()
        date_str = data.get('date')
        if not date_str:
            return jsonify({"status": "error", "message": "Tarih eksik"}), 400
        from backend.database import get_analyses_by_date_with_results
        from backend.telegram_sender import send_message
        matches = get_analyses_by_date_with_results(date_str)
        if not matches:
            return jsonify({"status": "error", "message": "Bu tarihte analiz yok"}), 404
        with_results = [m for m in matches if m.get('home_score') is not None]
        total = len(matches)
        total_results = len(with_results)
        if total_results > 0:
            c1x2 = sum(1 for m in with_results if m.get('pred_1x2_correct'))
            c_over25 = sum(1 for m in with_results if m.get('over25_correct'))
            c_btts = sum(1 for m in with_results if m.get('btts_correct'))
            c_score = sum(1 for m in with_results if m.get('score_correct'))
            c_ht = sum(1 for m in with_results if m.get('ht_correct'))
            pct_1x2 = round(c1x2/total_results*100)
            pct_over25 = round(c_over25/total_results*100)
            pct_btts = round(c_btts/total_results*100)
            with_ht = [m for m in with_results if m.get('ht_home_score') is not None]
            ht_line = f"\nIY 0.5 Ust: {c_ht}/{len(with_ht)}" if with_ht else ''
            details = ''
            for m in with_results:
                pred = m.get('prediction_1x2','?')
                tick_1x2 = 'OK' if m.get('pred_1x2_correct') else 'X'
                tick_over = 'OK' if m.get('over25_correct') else 'X'
                tick_btts = 'OK' if m.get('btts_correct') else 'X'
                tick_score = 'OK' if m.get('score_correct') else 'X'
                tick_ht = ''
                if m.get('ht_home_score') is not None:
                    tick_ht = f"  {'OK' if m.get('ht_correct') else 'X'} IY {m['ht_home_score']}-{m['ht_away_score']}"
                details += f"\n{m['home_team']} {m['home_score']}-{m['away_score']} {m['away_team']}\n"
                details += f"   {tick_1x2} 1X2: {pred}  {tick_over} 2.5 Gol  {tick_btts} KG Var  {tick_score} Skor{tick_ht}\n"
            msg = f"GUNLUK RAPOR - {date_str}\nToplam: {total} | Sonuclu: {total_results}\n1X2: {c1x2}/{total_results} (%{pct_1x2})\n2.5 Ust: {c_over25}/{total_results} (%{pct_over25})\nKG Var: {c_btts}/{total_results} (%{pct_btts})\nSkor: {c_score}/{total_results}{ht_line}\n{details}"
        else:
            msg = f"GUNLUK RAPOR - {date_str}\nToplam: {total}\nHenuz sonuc girilmemis."
        send_message(msg)
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Daily report error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# Kupon
@app.route('/api/coupon/today')
def api_coupon_today():
    try:
        matches = get_today_matches()
        if not matches:
            return jsonify({"status": "error", "message": "Analiz bulunamadi"}), 404

        coupon_type = request.args.get('type', 'dengeli')  # guvenli | dengeli | riskli

        # Tipe göre parametreler
        if coupon_type == 'guvenli':
            min_count = int(request.args.get('min', 3))
            max_count = int(request.args.get('max', 4))
            MIN_PCT = 75          # Daha yüksek eşik
            REQUIRED_CONF = ('Yüksek', 'Çok Yüksek', 'Yuksek', 'Cok Yuksek')
        elif coupon_type == 'riskli':
            min_count = int(request.args.get('min', 4))
            max_count = int(request.args.get('max', 6))
            MIN_PCT = 60          # Daha düşük eşik
            REQUIRED_CONF = None  # Tüm güven seviyeleri
        else:  # dengeli (varsayılan)
            min_count = int(request.args.get('min', 3))
            max_count = int(request.args.get('max', 5))
            MIN_PCT = 70
            REQUIRED_CONF = None

        min_count = max(2, min(min_count, 8))
        max_count = max(min_count, min(max_count, 8))

        logger.info(f"Kupon tipi: {coupon_type} | MIN_PCT={MIN_PCT} | min={min_count} max={max_count}")

        TYPE_PRIORITY = {
            'IY 0.5 Ust': 6, '2.5 Ust': 5, 'KG Var': 4,
            '1X2': 3, '2.5 Alt': 2, 'KG Yok': 1,
        }
        MAX_PER_TYPE = 2

        all_candidates = []
        for m in matches:
            confidence = m.get('confidence', '')
            over25_pct = float(m.get('over25_pct') or 0)
            btts_pct = float(m.get('btts_pct') or 0)
            ht2g_pct = float(m.get('ht2g_pct') or 0)

            high_conf = confidence in ('Yuksek', 'Cok Yuksek', 'Y\u00fcksek', '\u00c7ok Y\u00fcksek')
            # Güvenli modda sadece yüksek güvenli maçlar
            if REQUIRED_CONF and confidence not in REQUIRED_CONF:
                continue
            if confidence in ('Cok Yuksek', '\u00c7ok Y\u00fcksek'):
                conf_score = 4
            elif confidence in ('Yuksek', 'Y\u00fcksek'):
                conf_score = 3
            elif confidence == 'Orta':
                conf_score = 2
            else:
                conf_score = 1

            pred = m.get('prediction_1x2', '?')
            pred_text = {
                '1': f"{m['home_team']} Kazanir",
                'X': 'Beraberlik',
                '2': f"{m['away_team']} Kazanir"
            }.get(pred, pred)

            if ht2g_pct >= MIN_PCT:
                all_candidates.append({'type': 'IY 0.5 Ust', 'label': 'IY 0.5 Ustu', 'pct': ht2g_pct, 'conf_score': conf_score, 'match': m})
            if over25_pct >= MIN_PCT:
                all_candidates.append({'type': '2.5 Ust', 'label': '2.5 Gol Ustu', 'pct': over25_pct, 'conf_score': conf_score, 'match': m})
            elif (100 - over25_pct) >= MIN_PCT:
                all_candidates.append({'type': '2.5 Alt', 'label': '2.5 Gol Alti', 'pct': 100-over25_pct, 'conf_score': conf_score, 'match': m})
            if btts_pct >= MIN_PCT:
                all_candidates.append({'type': 'KG Var', 'label': 'KG Var', 'pct': btts_pct, 'conf_score': conf_score, 'match': m})
            elif (100 - btts_pct) >= MIN_PCT:
                all_candidates.append({'type': 'KG Yok', 'label': 'KG Yok', 'pct': 100-btts_pct, 'conf_score': conf_score, 'match': m})

            if high_conf:
                all_candidates.append({'type': '1X2', 'label': pred_text, 'pct': conf_score*20, 'conf_score': conf_score, 'match': m})

        if not all_candidates:
            return jsonify({"status": "error", "message": "Kriterlere uyan tahmin bulunamadi"}), 404

        priority_items = []
        import json as _json_vb
        high_conf_matches = [
            m for m in matches
            if m.get('confidence', '') in ('Yuksek', 'Cok Yuksek', 'Yüksek', 'Çok Yüksek')
        ]
        for m in high_conf_matches:
            try:
                vb_raw = m.get('value_bets')
                vb_list = _json_vb.loads(vb_raw) if isinstance(vb_raw, str) and vb_raw else (vb_raw or [])
                if not vb_list:
                    continue
                best_vb = max(vb_list, key=lambda v: v.get('diff', 0))
                label = best_vb.get('label', '')
                if '1X2 (Ev)' in label:
                    vb_type = '1X2'; vb_label = f"{m['home_team']} Kazanir"
                elif '1X2 (Deplasman)' in label:
                    vb_type = '1X2'; vb_label = f"{m['away_team']} Kazanir"
                elif '1X2 (Beraberlik)' in label:
                    vb_type = '1X2'; vb_label = 'Beraberlik'
                elif 'Over 2.5' in label:
                    if float(m.get('over25_pct') or 0) < 65: continue
                    vb_type = '2.5 Ust'; vb_label = '2.5 Gol Ustu'
                elif 'KG Var' in label:
                    if float(m.get('btts_pct') or 0) < 65: continue
                    vb_type = 'KG Var'; vb_label = 'KG Var'
                elif 'İY 0.5 Üst' in label or 'IY 0.5' in label:
                    if float(m.get('ht2g_pct') or 0) < 65: continue
                    vb_type = 'IY 0.5 Ust'; vb_label = 'IY 0.5 Ustu'
                else:
                    continue
                conf = m.get('confidence', 'Orta')
                conf_score = 4 if conf in ('Cok Yuksek', 'Çok Yüksek') else 3
                priority_items.append({
                    'type': vb_type, 'label': vb_label,
                    'pct': best_vb.get('our_pct', 75),
                    'conf_score': conf_score + 1, 'match': m,
                    'odds': best_vb.get('odds'), 'is_priority': True,
                })
            except Exception:
                continue

        # ─── KOMBİNE KURALLAR ───────────────────────────────────────────
        # Her maç için kombine tahminler oluştur — tekli tahminlerden önce değerlendirilir
        combo_items = []
        for m in matches:
            confidence  = m.get('confidence', '')
            over25_pct  = float(m.get('over25_pct') or 0)
            btts_pct    = float(m.get('btts_pct') or 0)
            pred        = m.get('prediction_1x2', '?')
            very_high   = confidence in ('Cok Yuksek', 'Çok Yüksek')
            high_or_vhigh = confidence in ('Yuksek', 'Cok Yuksek', 'Yüksek', 'Çok Yüksek')
            pred_label  = {
                '1': 'Ev Kazanir',
                '2': 'Dep Kazanir',
                'X': 'Beraberlik'
            }.get(pred, pred)

            # Kural 1: 2.5 Üst + KG Var — ikisi de %75+
            if over25_pct >= 75 and btts_pct >= 75:
                combo_items.append({
                    'type': 'COMBO_O25_BTTS',
                    'label': '2.5 Ust + KG Var',
                    'pct': round((over25_pct + btts_pct) / 2),
                    'conf_score': 5,
                    'match': m,
                    'is_combo': True,
                    'odds_keys': ['odds_over25', 'odds_btts_yes'],
                })

            # Kural 2: Taraf Kazanır + 1.5 Üst — Yüksek/ÇY + over25 %70+
            if high_or_vhigh and over25_pct >= 70 and pred in ('1', '2'):
                over15_label = f"{pred_label} + 1.5 Ust"
                combo_items.append({
                    'type': 'COMBO_1X2_O15',
                    'label': over15_label,
                    'pct': round((over25_pct + (5 if very_high else 3)) ),  # güven bonusu
                    'conf_score': 6 if very_high else 5,
                    'match': m,
                    'is_combo': True,
                    'odds_keys': ['odds_over15'],
                })

            # Kural 3: Taraf Kazanır + KG Var — ÇY güven + btts %75+
            if very_high and btts_pct >= 75 and pred in ('1', '2'):
                combo_items.append({
                    'type': 'COMBO_1X2_BTTS',
                    'label': f"{pred_label} + KG Var",
                    'pct': round((btts_pct + 5)),
                    'conf_score': 6,
                    'match': m,
                    'is_combo': True,
                    'odds_keys': ['odds_btts_yes'],
                })

        # Kombine öncelikleri en yüksek, sonra tekli
        combo_items.sort(key=lambda x: (x['conf_score'], x['pct']), reverse=True)
        all_candidates.sort(key=lambda x: (x['conf_score'], TYPE_PRIORITY.get(x['type'], 0), x['pct']), reverse=True)

        coupon = []
        type_counts = {}
        used_combos = set()
        used_match_ids = set()

        # Önce kombine kuralları değerlendir
        for c in combo_items:
            if len(coupon) >= max_count: break
            match_id = c['match'].get('id')
            if match_id in used_match_ids: continue
            combo_key = f"{match_id}_{c['type']}"
            if combo_key in used_combos: continue
            used_combos.add(combo_key)
            used_match_ids.add(match_id)
            m = c['match']
            # Kombine için oran bul — odds_keys'teki oranları çarp
            combo_odds = None
            try:
                import json as _jc, re as _rc
                def _norm_keys(d):
                    r = {}
                    for k, v in (d or {}).items():
                        nk = _rc.sub(r'_+', '_', str(k).strip().lower().replace('%','pct').replace('.','').replace('-','_').replace(' ','_'))
                        r[nk] = v
                    return r
                csv_d = m.get('csv_data')
                if isinstance(csv_d, str): csv_d = _jc.loads(csv_d)
                nd = _norm_keys(csv_d or {})
                odds_vals = []
                for ok in c.get('odds_keys', []):
                    v = nd.get(ok)
                    if v and float(v) > 1: odds_vals.append(float(v))
                if len(odds_vals) == len(c.get('odds_keys', [])) and odds_vals:
                    combo_odds = round(1.0, 2)
                    for ov in odds_vals: combo_odds = round(combo_odds * ov, 2)
            except: pass
            coupon.append({
                'home_team': m['home_team'], 'away_team': m['away_team'],
                'league': m.get('league', ''), 'match_time': m.get('match_time', ''),
                'prediction_type': c['type'], 'prediction_label': c['label'],
                'pct': c['pct'], 'confidence': m.get('confidence', 'Orta'),
                'analysis_id': m.get('id'),
                'odds': combo_odds,
                'is_combo': True,
            })
            logger.info(f"Kupon kombine: {m['home_team']} vs {m['away_team']} → {c['label']}")

        for c in priority_items:
            if len(coupon) >= max_count: break
            match_id = c['match'].get('id')
            if match_id in used_match_ids: continue
            t = c['type']
            if type_counts.get(t, 0) >= MAX_PER_TYPE: continue
            type_counts[t] = type_counts.get(t, 0) + 1
            used_match_ids.add(match_id)
            m = c['match']
            coupon.append({
                'home_team': m['home_team'], 'away_team': m['away_team'],
                'league': m.get('league', ''), 'match_time': m.get('match_time', ''),
                'prediction_type': c['type'], 'prediction_label': c['label'],
                'pct': round(c['pct']), 'confidence': m.get('confidence', 'Orta'),
                'analysis_id': m.get('id'),
                'odds': round(float(c['odds']), 2) if c.get('odds') else None,
            })
            logger.info(f"Kupon priority: {m['home_team']} vs {m['away_team']} → {c['type']} (value bet)")

        for c in all_candidates:
            if len(coupon) >= max_count: break
            t = c['type']
            match_id = c['match'].get('id')
            combo = f"{match_id}_{t}"
            if match_id in used_match_ids: continue
            if combo in used_combos: continue
            if type_counts.get(t, 0) >= MAX_PER_TYPE: continue
            type_counts[t] = type_counts.get(t, 0) + 1
            used_combos.add(combo)
            used_match_ids.add(match_id)
            m = c['match']

            odds_map = {
                'IY 0.5 Ust': 'odds_ht_over05', '2.5 Ust': 'odds_over25',
                '2.5 Alt': 'odds_under25', 'KG Var': 'odds_btts_yes',
                'KG Yok': 'odds_btts_no', '1X2': None,
            }
            odds_val = None
            try:
                import json as _json
                import re as _re

                def _normalize_csv_keys(data):
                    normalized = {}
                    if not isinstance(data, dict): return normalized
                    for k, v in data.items():
                        key = str(k).strip().lower()
                        key = key.replace('%', 'pct').replace('.', '')
                        key = key.replace('-', '_').replace(' ', '_')
                        key = _re.sub(r'_+', '_', key)
                        normalized[key] = v
                    return normalized

                def _extract_odds_from_csv(data, odds_key):
                    normalized = _normalize_csv_keys(data)
                    odds_aliases = {
                        'odds_ht_over05': ['odds_ht_over05','odds_ht_over_05','odds_ht_over_0_5','odds_1h_over05','odds_1h_over_05','odds_1h_over_0_5','odds_1st_half_over05','odds_1st_half_over_05','odds_1st_half_over_0_5','1st_half_over05','first_half_over05'],
                        'odds_over25': ['odds_over25','odds_over_25','odds_over_2_5','over25','over_25'],
                        'odds_under25': ['odds_under25','odds_under_25','odds_under_2_5','under25','under_25'],
                        'odds_btts_yes': ['odds_btts_yes','odds_btts_yes_','btts_yes','odds_bttsyes'],
                        'odds_btts_no': ['odds_btts_no','odds_btts_no_','btts_no','odds_bttsno'],
                    }
                    for key in odds_aliases.get(odds_key, [odds_key]):
                        val = normalized.get(key)
                        if val not in (None, '', 0, '0'): return val
                    return None

                def _same_team(a, b):
                    def norm(s):
                        s = str(s or '').strip().lower()
                        s = s.replace('&', 'and')
                        s = _re.sub(r'[^a-z0-9]+', ' ', s)
                        s = _re.sub(r'\b(fc|cf|afc|sc|ac|club|women|woman|wfc|w)\b', ' ', s)
                        s = _re.sub(r'\s+', ' ', s).strip()
                        return s
                    na, nb = norm(a), norm(b)
                    return na == nb or na in nb or nb in na

                vb_raw = m.get('value_bets')
                vb_list = _json.loads(vb_raw) if isinstance(vb_raw, str) and vb_raw else (vb_raw or [])
                for vb in vb_list:
                    label = str(vb.get('label', ''))
                    if label.replace('Over 2.5', '2.5 Ust').replace('KG Var', 'KG Var') in t or t in label:
                        odds_val = vb.get('odds')
                        if odds_val: break

                if not odds_val:
                    odds_key = odds_map.get(t)
                    analysis_csv = m.get('csv_data')
                    if isinstance(analysis_csv, str) and analysis_csv:
                        try: analysis_csv = _json.loads(analysis_csv)
                        except Exception: analysis_csv = None
                    if odds_key and analysis_csv:
                        odds_val = _extract_odds_from_csv(analysis_csv, odds_key)

                if not odds_val:
                    odds_key = odds_map.get(t)
                    if odds_key:
                        pending = get_pending_matches()
                        best_pm = None
                        for pm in pending:
                            if _same_team(pm.get('home_team'), m.get('home_team')) and _same_team(pm.get('away_team'), m.get('away_team')):
                                best_pm = pm; break
                        if best_pm and best_pm.get('csv_data'):
                            pm_csv = best_pm['csv_data']
                            if isinstance(pm_csv, str): pm_csv = _json.loads(pm_csv)
                            odds_val = _extract_odds_from_csv(pm_csv, odds_key)
            except Exception:
                pass

            coupon.append({
                'home_team': m['home_team'], 'away_team': m['away_team'],
                'league': m.get('league', ''), 'match_time': m.get('match_time', ''),
                'prediction_type': c['type'], 'prediction_label': c['label'],
                'pct': round(c['pct']), 'confidence': m.get('confidence', 'Orta'),
                'analysis_id': m.get('id'),
                'odds': round(float(odds_val), 2) if odds_val else None,
            })

        if len(coupon) < min_count:
            return jsonify({"status": "error", "message": f"Yeterli tahmin bulunamadi (min {min_count}, bulunan {len(coupon)})"}), 404

        logger.info(f"Kupon: {len(coupon)} tahmin, turler: {type_counts}")
        return jsonify({"status": "success", "coupon": coupon})
    except Exception as e:
        logger.error(f"Coupon error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/coupon/save', methods=['POST'])
def api_coupon_save():
    try:
        data = request.get_json()
        items = data.get('items', [])
        coupon_type = data.get('coupon_type', 'dengeli')
        if not items:
            return jsonify({"status": "error", "message": "Kupon bos"}), 400
        save_coupon(items, coupon_type=coupon_type)
        logger.info(f"Kupon kaydedildi: {len(items)} mac ({coupon_type})")
        return jsonify({"status": "success", "message": "Kupon kaydedildi!"})
    except Exception as e:
        logger.error(f"Coupon save error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/coupon/list')
def api_coupon_list():
    try:
        coupons = get_coupons(30)
        return jsonify(coupons)
    except Exception as e:
        logger.error(f"Coupon list error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/coupon/delete/<int:coupon_id>', methods=['DELETE'])
def api_coupon_delete(coupon_id):
    try:
        import psycopg2
        conn = psycopg2.connect(os.environ.get('DATABASE_URL', ''))
        cur = conn.cursor()
        cur.execute('DELETE FROM coupons WHERE id = %s', (coupon_id,))
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Coupon delete error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/coupon/update/<date_str>', methods=['POST'])
def api_coupon_update(date_str):
    try:
        update_coupon_results(date_str)
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Coupon update error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# Parse Image
@app.route('/api/parse/image', methods=['POST'])
def api_parse_image():
    try:
        import anthropic, json
        data = request.get_json()
        image_data = data.get('image')
        media_type = data.get('media_type', 'image/jpeg')
        if not image_data:
            return jsonify({"status": "error", "message": "Gorsel eksik"}), 400
        client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
        today = datetime.now().strftime('%Y-%m-%d')
        message = client.messages.create(
            model="claude-opus-4-5", max_tokens=1024,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                {"type": "text", "text": f"Bu gorseldeki mac programini analiz et. Bugun: {today}.\nTUM maclari JSON array olarak dondur:\n[{{\"home_team\": \"...\", \"away_team\": \"...\", \"league\": \"...\", \"time\": \"HH:MM\"}}]\nSadece JSON dondur."}
            ]}]
        )
        raw = message.content[0].text.strip().replace('```json','').replace('```','').strip()
        parsed = json.loads(raw)
        matches = []
        for m in parsed:
            match_date = datetime.now()
            if m.get('time'):
                try:
                    h, mi = m['time'].split(':')
                    match_date = match_date.replace(hour=int(h), minute=int(mi), second=0)
                except: pass
            matches.append({'home_team': m.get('home_team',''), 'away_team': m.get('away_team',''),
                            'league': m.get('league','Bilinmeyen Lig'), 'date': match_date.isoformat()})
        return jsonify({"status": "success", "matches": matches})
    except Exception as e:
        logger.error(f"Image parse error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/matches/delete/<int:analysis_id>', methods=['DELETE'])
def api_delete_match(analysis_id):
    try:
        from backend.database import delete_analysis
        delete_analysis(analysis_id)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/matches/clear', methods=['DELETE'])
def api_clear_matches():
    try:
        from backend.database import delete_today_analyses
        delete_today_analyses()
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# Admin
@app.route('/api/admin/clear-before/<date_str>', methods=['DELETE'])
def api_clear_before_date(date_str):
    try:
        import psycopg2
        conn = psycopg2.connect(os.environ.get('DATABASE_URL', ''))
        cur = conn.cursor()
        cur.execute('''
            DELETE FROM match_results WHERE analysis_id IN (
                SELECT id FROM analyses WHERE analysis_date < %s
            )
        ''', (date_str,))
        deleted_results = cur.rowcount
        cur.execute('DELETE FROM analyses WHERE analysis_date < %s', (date_str,))
        deleted_analyses = cur.rowcount
        conn.commit()
        cur.close(); conn.close()
        return jsonify({"status": "success", "message": f"{date_str} oncesi {deleted_analyses} analiz ve {deleted_results} sonuc silindi"})
    except Exception as e:
        logger.error(f"Admin clear error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


# Debug
@app.route('/api/debug/footballdata/<league_code>')
def debug_footballdata(league_code):
    try:
        import requests as req
        resp = req.get(f'https://api.football-data.org/v4/competitions/{league_code}/teams',
            headers={'X-Auth-Token': os.environ.get('FOOTBALL_DATA_KEY','')}, timeout=10)
        resp.raise_for_status()
        teams = resp.json().get('teams', [])
        return jsonify(sorted([{'id': t.get('id'), 'name': t.get('name')} for t in teams], key=lambda x: x['name']))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/debug/analysis-data/<int:analysis_id>')
def api_debug_analysis_data(analysis_id):
    try:
        from backend.database import get_analysis_by_id
        from backend.football_api import (
            get_team_last_matches, get_h2h, get_team_shot_stats,
            get_team_standing, is_youth_or_reserve,
        )
        from backend.analyzer import (
            extract_form_from_fixtures, extract_goals_avg,
            extract_h2h_summary, _get_country_code,
        )
        from backend.ai_analyzer import _safe_float, calculate_value_bets, _is_score_valid, _is_ht_ft_consistent
        import json as _json

        analysis = get_analysis_by_id(analysis_id)
        if not analysis:
            return jsonify({'error': 'Analiz bulunamadı'}), 404

        home_team = analysis['home_team']
        away_team = analysis['away_team']
        league    = analysis.get('league', '')
        csv_data  = analysis.get('csv_data') or {}

        fixture = {
            'fixture': {'id': analysis.get('fixture_id', 0), 'date': analysis.get('match_time', '')},
            'league':  {'id': 0, 'name': league},
            'teams':   {'home': {'id': 0, 'name': home_team}, 'away': {'id': 0, 'name': away_team}},
            'goals':   {'home': None, 'away': None},
        }
        country_code = _get_country_code(fixture)
        is_youth = is_youth_or_reserve(home_team) or is_youth_or_reserve(away_team)

        csv_status = 'ok' if csv_data else 'error'
        if csv_data:
            filled = sum(1 for v in csv_data.values() if v is not None)
            if filled < 5:
                csv_status = 'warn'

        home_matches = get_team_last_matches(home_team, last=10) if not is_youth else []
        away_matches = get_team_last_matches(away_team, last=10) if not is_youth else []

        def match_info(matches, team_name):
            if not matches:
                return {'count': 0}
            form = extract_form_from_fixtures(matches, team_name)
            gavg, cavg = extract_goals_avg(matches, team_name)
            return {'count': len(matches), 'form': form, 'goals_avg': gavg, 'conceded_avg': cavg}

        last_matches = {
            'home': match_info(home_matches, home_team),
            'away': match_info(away_matches, away_team),
        }

        shot_supported_codes = ('ENG', 'GER', 'ESP', 'ITA', 'FRA')
        shots_supported = country_code and country_code in shot_supported_codes and not is_youth

        if shots_supported:
            home_shots = get_team_shot_stats(home_team, country_code, last=5)
            away_shots = get_team_shot_stats(away_team, country_code, last=5)
            shot_stats = {
                'supported': True,
                'home': {
                    'available': bool(home_shots),
                    'shots_avg': home_shots.get('shots_avg') if home_shots else None,
                    'shots_on_avg': home_shots.get('shots_on_target_avg') if home_shots else None,
                    'accuracy': home_shots.get('shot_accuracy') if home_shots else None,
                    'reason': None if home_shots else 'Takım bulunamadı',
                },
                'away': {
                    'available': bool(away_shots),
                    'shots_avg': away_shots.get('shots_avg') if away_shots else None,
                    'shots_on_avg': away_shots.get('shots_on_target_avg') if away_shots else None,
                    'accuracy': away_shots.get('shot_accuracy') if away_shots else None,
                    'reason': None if away_shots else 'Takım bulunamadı',
                },
            }
        else:
            reason = 'Gençlik/Rezerv takım' if is_youth else f'Lig desteklenmiyor ({country_code or "bilinmiyor"})'
            shot_stats = {'supported': False, 'reason': reason}

        home_standing = get_team_standing(home_team, country_code, league_name=league) if not is_youth else None
        away_standing = get_team_standing(away_team, country_code, league_name=league) if not is_youth else None

        standings = {
            'home': {
                'available': bool(home_standing),
                'position': home_standing.get('position') if home_standing else None,
                'points':   home_standing.get('points')   if home_standing else None,
                'played':   home_standing.get('played')   if home_standing else None,
                'reason': None if home_standing else ('Gençlik/Rezerv' if is_youth else 'Lig desteklenmiyor'),
            },
            'away': {
                'available': bool(away_standing),
                'position': away_standing.get('position') if away_standing else None,
                'points':   away_standing.get('points')   if away_standing else None,
                'played':   away_standing.get('played')   if away_standing else None,
                'reason': None if away_standing else ('Gençlik/Rezerv' if is_youth else 'Lig desteklenmiyor'),
            },
        }

        h2h_raw = get_h2h(home_team, away_team, last=5) if not is_youth else []
        h2h_summary = extract_h2h_summary(h2h_raw, home_team, away_team)
        h2h = {
            'count':     h2h_summary.get('total', 0)     if h2h_summary else 0,
            'avg_goals': h2h_summary.get('avg_goals')    if h2h_summary else None,
            'home_wins': h2h_summary.get('home_wins')    if h2h_summary else None,
            'away_wins': h2h_summary.get('away_wins')    if h2h_summary else None,
            'draws':     h2h_summary.get('draws')        if h2h_summary else None,
        }

        def clamp_info(csv_key, margin, analysis_val):
            csv_base = _safe_float(csv_data.get(csv_key)) if csv_data else None
            final_val = round(_safe_float(analysis_val) or 0)
            if csv_base is None:
                return {'csv_base': None, 'margin': margin, 'ai_value': final_val, 'final_value': final_val, 'was_clamped': False}
            low = max(0, csv_base - margin)
            high = min(100, csv_base + margin)
            was_clamped = not (low <= final_val <= high)
            return {'csv_base': round(csv_base), 'margin': margin, 'ai_value': final_val, 'final_value': final_val, 'was_clamped': was_clamped}

        clamp = {
            'over25_pct': clamp_info('over25_avg', 10, analysis.get('over25_pct', 50)),
            'btts_pct':   clamp_info('btts_avg',    8, analysis.get('btts_pct', 40)),
            'ht2g_pct':   clamp_info('ht_over05_avg', 5, analysis.get('ht2g_pct', 40)),
        }

        odds_side = odds_detail = ppg_side = ppg_detail = xg_side = xg_detail = None

        if csv_data:
            try:
                h_o = float(csv_data.get('odds_home') or 0)
                a_o = float(csv_data.get('odds_away') or 0)
                if h_o > 1 and a_o > 1:
                    h_imp = round(1/h_o*100, 1)
                    a_imp = round(1/a_o*100, 1)
                    d = h_imp - a_imp
                    if d > 15:    odds_side, odds_detail = '1', f'{home_team} net favori (%{h_imp} vs %{a_imp})'
                    elif d < -15: odds_side, odds_detail = '2', f'{away_team} net favori (%{a_imp} vs %{h_imp})'
                    elif d > 5:   odds_side, odds_detail = '1 (hafif)', f'Fark: {abs(d):.0f}%'
                    elif d < -5:  odds_side, odds_detail = '2 (hafif)', f'Fark: {abs(d):.0f}%'
                    else:         odds_side, odds_detail = 'X (dengeli)', f'Fark: {abs(d):.0f}%'
            except: pass

            try:
                ch = float(csv_data.get('current_home_ppg') or 0)
                ca = float(csv_data.get('current_away_ppg') or 0)
                if ch > 0 or ca > 0:
                    d = ch - ca
                    if d > 0.5:    ppg_side, ppg_detail = '1', f'{home_team}: {ch} · {away_team}: {ca}'
                    elif d < -0.5: ppg_side, ppg_detail = '2', f'{away_team}: {ca} · {home_team}: {ch}'
                    else:          ppg_side, ppg_detail = 'X (dengeli)', f'Fark: {abs(d):.2f}'
            except: pass

            try:
                hxg = float(csv_data.get('home_xg') or 0)
                axg = float(csv_data.get('away_xg') or 0)
                if hxg > 0 or axg > 0:
                    d = hxg - axg
                    if abs(d) >= 0.8:
                        xg_side = home_team if d > 0 else away_team
                        xg_detail = f'Fark: {abs(d):.2f} xG ({home_team}: {hxg} · {away_team}: {axg})'
                    elif abs(d) >= 0.4:
                        xg_side = f'Hafif: {home_team if d>0 else away_team}'
                        xg_detail = f'Fark: {abs(d):.2f} xG'
                    else:
                        xg_side = 'Dengeli'
                        xg_detail = f'{home_team}: {hxg} · {away_team}: {axg}'
            except: pass

        pred = analysis.get('prediction_1x2', '?')
        conf = analysis.get('confidence', 'Orta')

        decision = {
            'odds_side':   odds_side  or '— (CSV oran yok)',
            'odds_detail': odds_detail,
            'ppg_side':    ppg_side   or '— (CSV PPG yok)',
            'ppg_detail':  ppg_detail,
            'xg_side':     xg_side    or '— (CSV xG yok)',
            'xg_detail':   xg_detail,
            'ai_pred':     pred,
            'confidence':  conf,
            'final_conf':  conf,
            'conf_reason': 'Bahisçi + PPG uyumu kontrol edildi',
        }

        pred_score    = analysis.get('predicted_score', '?-?')
        pred_ht_score = analysis.get('predicted_ht_score', '?-?')
        over25_pct = analysis.get('over25_pct', 50)
        btts_pct   = analysis.get('btts_pct', 40)
        over35_avg = _safe_float(csv_data.get('over35_avg')) if csv_data else None
        over45_avg = _safe_float(csv_data.get('over45_avg')) if csv_data else None

        ai_valid      = _is_score_valid(pred_score, pred, btts_pct, over25_pct, over35_avg, over45_avg)
        ht_consistent = _is_ht_ft_consistent(pred_ht_score, pred_score)

        score_info = {
            'ai_score':       pred_score,
            'ai_valid':       ai_valid,
            'final_score':    pred_score,
            'ai_ht_score':    pred_ht_score,
            'ht_consistent':  ht_consistent,
            'final_ht_score': pred_ht_score,
            'pred_1x2':       pred,
            'confidence':     conf,
        }

        try:
            vb_raw = analysis.get('value_bets')
            value_bets = _json.loads(vb_raw) if isinstance(vb_raw, str) and vb_raw else (vb_raw or [])
        except:
            value_bets = []

        score_pts = 0
        flags = []
        if csv_data and csv_data.get('over25_avg'):  score_pts += 2
        else: flags.append('CSV eksik')
        if last_matches['home']['count'] >= 5: score_pts += 2
        else: flags.append('Son maç az')
        if shots_supported and shot_stats.get('home', {}).get('available'): score_pts += 1
        if home_standing:  score_pts += 1
        if h2h['count'] >= 3: score_pts += 1
        if csv_data and csv_data.get('odds_home'): score_pts += 1
        if csv_data and csv_data.get('home_xg'):   score_pts += 1
        if len(value_bets) > 0: score_pts += 1

        quality = 'Mükemmel' if score_pts >= 8 else 'İyi' if score_pts >= 6 else 'Orta' if score_pts >= 4 else 'Zayıf'
        overall = {'score': score_pts, 'quality': quality, 'flags': flags}

        return jsonify({
            'csv':          {**{'status': csv_status}, **(csv_data or {})},
            'last_matches': last_matches,
            'shot_stats':   shot_stats,
            'standings':    standings,
            'h2h':          h2h,
            'clamp':        clamp,
            'decision':     decision,
            'score':        score_info,
            'value_bets':   value_bets,
            'overall':      overall,
        })

    except Exception as e:
        logger.error(f"Debug analysis data error: {e}")
        import traceback
        return jsonify({'error': str(e), 'trace': traceback.format_exc()}), 500



@app.route('/gunun-ozeti')
def gunun_ozeti():
    return render_template('gunun_ozeti.html')


@app.route('/api/summary/generate', methods=['POST'])
def api_summary_generate():
    try:
        from backend.ai_analyzer import generate_daily_summary
        data = request.get_json() or {}
        ai_provider = data.get('ai_provider', 'claude')
        matches = get_today_matches()
        if not matches:
            return jsonify({"status": "error", "message": "Bugün analiz edilmiş maç yok"}), 404
        content = generate_daily_summary(matches, ai_provider=ai_provider)
        if not content:
            return jsonify({"status": "error", "message": "Özet üretilemedi"}), 500
        today = datetime.now().strftime('%Y-%m-%d')
        save_summary(today, content, ai_provider=ai_provider)
        summary = get_summary_by_date(today)
        logger.info(f"Daily summary generated: {today} ({ai_provider})")
        return jsonify({
            "status": "success",
            "content": content,
            "ai_provider": ai_provider,
            "created_at": summary.get('created_at', '') if summary else '',
        })
    except Exception as e:
        logger.error(f"Summary generate error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/summary/date/<date_str>')
def api_summary_by_date(date_str):
    try:
        summary = get_summary_by_date(date_str)
        if not summary:
            return jsonify({}), 200
        return jsonify(summary)
    except Exception as e:
        logger.error(f"Summary by date error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/summary/list')
def api_summary_list():
    try:
        summaries = get_summary_list(30)
        return jsonify(summaries)
    except Exception as e:
        logger.error(f"Summary list error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/summary/telegram', methods=['POST'])
def api_summary_telegram():
    try:
        from backend.telegram_sender import send_message
        data = request.get_json() or {}
        content = data.get('content', '')
        if not content:
            return jsonify({"status": "error", "message": "İçerik boş"}), 400
        today = datetime.now().strftime('%d.%m.%Y')
        msg = f"📋 GÜNÜN ÖZETİ — {today}\n\n{content}"
        send_message(msg)
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Summary telegram error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
