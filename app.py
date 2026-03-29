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
    get_value_bet_stats
)

app = Flask(__name__, template_folder='frontend/templates', static_folder='frontend/static', static_url_path='/static')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
init_db()

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
        cur.execute('''
            SELECT COUNT(*) as total, SUM(r.score_correct) as cscore,
                -- Sadece Yüksek/Çok Yüksek güvenli maçlar için 1X2
                COUNT(CASE WHEN a.confidence IN ('Yuksek','Cok Yuksek') THEN 1 END) as total_1x2,
                SUM(CASE WHEN a.confidence IN ('Yuksek','Cok Yuksek') THEN r.pred_1x2_correct ELSE 0 END) as c1x2,
                -- Sadece eşik üzeri (%65+) tahminleri say
                COUNT(CASE WHEN a.over25_pct >= 65 THEN 1 END) as total_over25,
                SUM(CASE WHEN a.over25_pct >= 65 THEN r.over25_correct ELSE 0 END) as cover25,
                COUNT(CASE WHEN a.btts_pct >= 65 THEN 1 END) as total_btts,
                SUM(CASE WHEN a.btts_pct >= 65 THEN r.btts_correct ELSE 0 END) as cbtts,
                COUNT(CASE WHEN a.ht2g_pct >= 65 AND r.ht_home_score IS NOT NULL THEN 1 END) as total_ht,
                SUM(CASE WHEN a.ht2g_pct >= 65 AND r.ht_home_score IS NOT NULL THEN r.ht_correct ELSE 0 END) as cht
            FROM match_results r
            JOIN analyses a ON a.id = r.analysis_id
        ''')
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
        cur.execute('''
            SELECT a.analysis_date, COUNT(*) as total,
                SUM(r.pred_1x2_correct) as c1x2,
                SUM(r.over25_correct) as cover25,
                SUM(r.btts_correct) as cbtts
            FROM analyses a JOIN match_results r ON a.id = r.analysis_id
            GROUP BY a.analysis_date ORDER BY a.analysis_date DESC LIMIT 30
        ''')
        rows = [dict(r) for r in cur.fetchall()]
        rows.reverse()
        daily = []
        for r in rows:
            t = r['total'] or 0
            daily.append({
                'date': r['analysis_date'], 'total': t,
                'pct_1x2': round((r['c1x2'] or 0)/t*100) if t else 0,
                'pct_over25': round((r['cover25'] or 0)/t*100) if t else 0,
                'pct_btts': round((r['cbtts'] or 0)/t*100) if t else 0,
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
        cur.execute('''
            SELECT COUNT(*) as total, SUM(r.score_correct) as cscore,
                COUNT(CASE WHEN a.confidence IN ('Yuksek','Cok Yuksek') THEN 1 END) as total_1x2,
                SUM(CASE WHEN a.confidence IN ('Yuksek','Cok Yuksek') THEN r.pred_1x2_correct ELSE 0 END) as c1x2,
                COUNT(CASE WHEN a.over25_pct >= 65 THEN 1 END) as total_over25,
                SUM(CASE WHEN a.over25_pct >= 65 THEN r.over25_correct ELSE 0 END) as cover25,
                COUNT(CASE WHEN a.btts_pct >= 65 THEN 1 END) as total_btts,
                SUM(CASE WHEN a.btts_pct >= 65 THEN r.btts_correct ELSE 0 END) as cbtts,
                COUNT(CASE WHEN a.ht2g_pct >= 65 AND r.ht_home_score IS NOT NULL THEN 1 END) as total_ht,
                SUM(CASE WHEN a.ht2g_pct >= 65 AND r.ht_home_score IS NOT NULL THEN r.ht_correct ELSE 0 END) as cht
            FROM match_results r
            JOIN analyses a ON a.id = r.analysis_id
        ''')
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
        cur.execute('''
            SELECT a.league, COUNT(*) as total,
                SUM(r.pred_1x2_correct) as c1x2,
                SUM(r.over25_correct) as cover25,
                SUM(r.btts_correct) as cbtts,
                COUNT(CASE WHEN r.ht_home_score IS NOT NULL THEN 1 END) as total_ht,
                SUM(r.ht_correct) as cht
            FROM analyses a JOIN match_results r ON a.id = r.analysis_id
            GROUP BY a.league HAVING COUNT(*) >= 3 ORDER BY COUNT(*) DESC
        ''')
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
        cur.execute('''
            SELECT a.confidence, COUNT(*) as total,
                SUM(r.pred_1x2_correct) as c1x2,
                SUM(r.over25_correct) as cover25,
                SUM(r.btts_correct) as cbtts
            FROM analyses a JOIN match_results r ON a.id = r.analysis_id
            GROUP BY a.confidence ORDER BY COUNT(*) DESC
        ''')
        rows = [dict(r) for r in cur.fetchall()]

        # Türkçe/ASCII varyantlarını normalize et
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

        # Normalize edip birleştir
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
        cur.execute('''
            SELECT a.analysis_date, COUNT(*) as total, SUM(r.pred_1x2_correct) as c1x2
            FROM analyses a JOIN match_results r ON a.id = r.analysis_id
            GROUP BY a.analysis_date HAVING COUNT(*) >= 2
            ORDER BY (SUM(r.pred_1x2_correct)::float / COUNT(*)) DESC
        ''')
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

@app.route('/api/stats/calibration')
def api_stats_calibration():
    try:
        import psycopg2, psycopg2.extras
        conn = psycopg2.connect(os.environ.get('DATABASE_URL', ''))
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Her tahmin tipi için yüzde gruplarına göre gerçek başarı oranı
        buckets = [
            (65, 70, '65-70'),
            (70, 80, '70-80'),
            (80, 90, '80-90'),
            (90, 101, '90+'),
        ]

        result = {'over25': [], 'btts': [], 'ht2g': []}

        for low, high, label in buckets:
            # Over 2.5 kalibrasyonu
            cur.execute('''
                SELECT COUNT(*) as total, SUM(r.over25_correct) as correct
                FROM analyses a
                JOIN match_results r ON a.id = r.analysis_id
                WHERE a.over25_pct >= %s AND a.over25_pct < %s
            ''', (low, high))
            row = dict(cur.fetchone())
            total = row['total'] or 0
            correct = row['correct'] or 0
            result['over25'].append({
                'bucket': label,
                'predicted': round((low + min(high, 100)) / 2),
                'total': total,
                'correct': correct,
                'actual_pct': round(correct / total * 100) if total > 0 else None
            })

            # BTTS kalibrasyonu
            cur.execute('''
                SELECT COUNT(*) as total, SUM(r.btts_correct) as correct
                FROM analyses a
                JOIN match_results r ON a.id = r.analysis_id
                WHERE a.btts_pct >= %s AND a.btts_pct < %s
            ''', (low, high))
            row = dict(cur.fetchone())
            total = row['total'] or 0
            correct = row['correct'] or 0
            result['btts'].append({
                'bucket': label,
                'predicted': round((low + min(high, 100)) / 2),
                'total': total,
                'correct': correct,
                'actual_pct': round(correct / total * 100) if total > 0 else None
            })

            # IY 0.5 Üst kalibrasyonu
            cur.execute('''
                SELECT COUNT(CASE WHEN r.ht_home_score IS NOT NULL THEN 1 END) as total,
                       SUM(CASE WHEN r.ht_home_score IS NOT NULL THEN r.ht_correct ELSE 0 END) as correct
                FROM analyses a
                JOIN match_results r ON a.id = r.analysis_id
                WHERE a.ht2g_pct >= %s AND a.ht2g_pct < %s
            ''', (low, high))
            row = dict(cur.fetchone())
            total = row['total'] or 0
            correct = row['correct'] or 0
            result['ht2g'].append({
                'bucket': label,
                'predicted': round((low + min(high, 100)) / 2),
                'total': total,
                'correct': correct,
                'actual_pct': round(correct / total * 100) if total > 0 else None
            })

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
        vb_results = calculate_value_bet_results(analysis, outcomes)
        save_match_result(analysis_id=analysis_id, fixture_id=analysis.get('fixture_id'),
                          home_score=home_score, away_score=away_score,
                          ht_home_score=ht_hs, ht_away_score=ht_as, source='manual',
                          value_bet_results=vb_results, **outcomes)
        send_result_to_telegram(analysis, home_score, away_score, outcomes, ht_hs, ht_as)
        mark_telegram_sent(analysis_id)
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

        min_count = int(request.args.get('min', 3))
        max_count = int(request.args.get('max', 5))
        min_count = max(2, min(min_count, 8))
        max_count = max(min_count, min(max_count, 8))

        MIN_PCT = 70

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

        # ── Yüksek güven + value bet olan maçları önce kupona ekle ──────────────
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
                # En iyi value bet'i al
                best_vb = max(vb_list, key=lambda v: v.get('diff', 0))
                label = best_vb.get('label', '')
                # Label'dan tip ve tahmin belirle
                if '1X2 (Ev)' in label:
                    vb_type = '1X2'
                    vb_label = f"{m['home_team']} Kazanir"
                elif '1X2 (Deplasman)' in label:
                    vb_type = '1X2'
                    vb_label = f"{m['away_team']} Kazanir"
                elif '1X2 (Beraberlik)' in label:
                    vb_type = '1X2'
                    vb_label = 'Beraberlik'
                elif 'Over 2.5' in label:
                    vb_type = '2.5 Ust'
                    vb_label = '2.5 Gol Ustu'
                elif 'KG Var' in label:
                    vb_type = 'KG Var'
                    vb_label = 'KG Var'
                elif 'İY 0.5 Üst' in label or 'IY 0.5' in label:
                    vb_type = 'IY 0.5 Ust'
                    vb_label = 'IY 0.5 Ustu'
                else:
                    continue
                conf = m.get('confidence', 'Orta')
                conf_score = 4 if conf in ('Cok Yuksek', 'Çok Yüksek') else 3
                priority_items.append({
                    'type': vb_type,
                    'label': vb_label,
                    'pct': best_vb.get('our_pct', 75),
                    'conf_score': conf_score + 1,  # öncelik için +1
                    'match': m,
                    'odds': best_vb.get('odds'),
                    'is_priority': True,
                })
            except Exception:
                continue
        # ─────────────────────────────────────────────────────────────────────

        all_candidates.sort(key=lambda x: (x['conf_score'], TYPE_PRIORITY.get(x['type'], 0), x['pct']), reverse=True)

        coupon = []
        type_counts = {}
        used_combos = set()
        used_match_ids = set()

        # Önce priority item'ları ekle
        for c in priority_items:
            if len(coupon) >= max_count:
                break
            match_id = c['match'].get('id')
            if match_id in used_match_ids:
                continue
            t = c['type']
            if type_counts.get(t, 0) >= MAX_PER_TYPE:
                continue
            type_counts[t] = type_counts.get(t, 0) + 1
            used_match_ids.add(match_id)
            m = c['match']
            coupon.append({
                'home_team': m['home_team'],
                'away_team': m['away_team'],
                'league': m.get('league', ''),
                'match_time': m.get('match_time', ''),
                'prediction_type': c['type'],
                'prediction_label': c['label'],
                'pct': round(c['pct']),
                'confidence': m.get('confidence', 'Orta'),
                'analysis_id': m.get('id'),
                'odds': round(float(c['odds']), 2) if c.get('odds') else None,
            })
            logger.info(f"Kupon priority: {m['home_team']} vs {m['away_team']} → {c['type']} (value bet)")

        for c in all_candidates:
            if len(coupon) >= max_count:
                break
            t = c['type']
            match_id = c['match'].get('id')
            combo = f"{match_id}_{t}"

            if match_id in used_match_ids:
                continue
            if combo in used_combos:
                continue
            if type_counts.get(t, 0) >= MAX_PER_TYPE:
                continue
            type_counts[t] = type_counts.get(t, 0) + 1
            used_combos.add(combo)
            used_match_ids.add(match_id)
            m = c['match']

            odds_map = {
                'IY 0.5 Ust': 'odds_ht_over05',
                '2.5 Ust':    'odds_over25',
                '2.5 Alt':    'odds_under25',
                'KG Var':     'odds_btts_yes',
                'KG Yok':     'odds_btts_no',
                '1X2':        None,
            }
            odds_val = None
            try:
                import json as _json
                import re as _re

                def _normalize_csv_keys(data):
                    normalized = {}
                    if not isinstance(data, dict):
                        return normalized
                    for k, v in data.items():
                        key = str(k).strip().lower()
                        key = key.replace('%', 'pct')
                        key = key.replace('.', '')
                        key = key.replace('-', '_').replace(' ', '_')
                        key = _re.sub(r'_+', '_', key)
                        normalized[key] = v
                    return normalized

                def _extract_odds_from_csv(data, odds_key):
                    normalized = _normalize_csv_keys(data)
                    odds_aliases = {
                        'odds_ht_over05': [
                            'odds_ht_over05', 'odds_ht_over_05', 'odds_ht_over_0_5',
                            'odds_1h_over05', 'odds_1h_over_05', 'odds_1h_over_0_5',
                            'odds_1st_half_over05', 'odds_1st_half_over_05', 'odds_1st_half_over_0_5',
                            '1st_half_over05', 'first_half_over05'
                        ],
                        'odds_over25': ['odds_over25', 'odds_over_25', 'odds_over_2_5', 'over25', 'over_25'],
                        'odds_under25': ['odds_under25', 'odds_under_25', 'odds_under_2_5', 'under25', 'under_25'],
                        'odds_btts_yes': ['odds_btts_yes', 'odds_btts_yes_', 'btts_yes', 'odds_bttsyes'],
                        'odds_btts_no': ['odds_btts_no', 'odds_btts_no_', 'btts_no', 'odds_bttsno'],
                    }
                    for key in odds_aliases.get(odds_key, [odds_key]):
                        val = normalized.get(key)
                        if val not in (None, '', 0, '0'):
                            return val
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
                        if odds_val:
                            break

                if not odds_val:
                    odds_key = odds_map.get(t)
                    analysis_csv = m.get('csv_data')
                    if isinstance(analysis_csv, str) and analysis_csv:
                        try:
                            analysis_csv = _json.loads(analysis_csv)
                        except Exception:
                            analysis_csv = None
                    if odds_key and analysis_csv:
                        odds_val = _extract_odds_from_csv(analysis_csv, odds_key)

                if not odds_val:
                    odds_key = odds_map.get(t)
                    if odds_key:
                        pending = get_pending_matches()
                        best_pm = None
                        for pm in pending:
                            if _same_team(pm.get('home_team'), m.get('home_team')) and _same_team(pm.get('away_team'), m.get('away_team')):
                                best_pm = pm
                                break
                        if best_pm and best_pm.get('csv_data'):
                            pm_csv = best_pm['csv_data']
                            if isinstance(pm_csv, str):
                                pm_csv = _json.loads(pm_csv)
                            odds_val = _extract_odds_from_csv(pm_csv, odds_key)
            except Exception:
                pass

            coupon.append({
                'home_team': m['home_team'],
                'away_team': m['away_team'],
                'league': m.get('league', ''),
                'match_time': m.get('match_time', ''),
                'prediction_type': c['type'],
                'prediction_label': c['label'],
                'pct': round(c['pct']),
                'confidence': m.get('confidence', 'Orta'),
                'analysis_id': m.get('id'),
                'odds': round(float(odds_val), 2) if odds_val else None,
            })

        if len(coupon) < min_count:
            return jsonify({
                "status": "error",
                "message": f"Yeterli tahmin bulunamadi (min {min_count}, bulunan {len(coupon)})"
            }), 404

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
        if not items:
            return jsonify({"status": "error", "message": "Kupon bos"}), 400
        save_coupon(items)
        logger.info(f"Kupon kaydedildi: {len(items)} mac")
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

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
