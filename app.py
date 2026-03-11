from flask import Flask, render_template, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import os
import threading
from backend.football_api import get_todays_fixtures
from backend.analyzer import run_selected_analysis
from backend.database import init_db, get_today_matches, get_analyses_by_date, get_available_dates

app = Flask(__name__, template_folder='frontend/templates', static_folder='frontend/static')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
init_db()

def scheduled_result_check():
    try:
        from backend.results_checker import check_and_send_results
        check_and_send_results()
    except Exception as e:
        logger.error(f"Scheduled result check failed: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(scheduled_result_check, 'interval', minutes=30, id='result_check')
scheduler.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/gecmis')
def gecmis():
    return render_template('gecmis.html')

@app.route('/api/fixtures/today')
def api_today_fixtures():
    fixtures = get_todays_fixtures()
    result = []
    for f in fixtures:
        result.append({
            'id': f['fixture']['id'],
            'date': f['fixture']['date'],
            'league': f['league']['name'],
            'home_team': f['teams']['home']['name'],
            'away_team': f['teams']['away']['name'],
        })
    return jsonify(result)

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

@app.route('/api/analyze/selected', methods=['POST'])
def api_analyze_selected():
    data = request.get_json()
    selected_ids = data.get('fixture_ids', [])
    manual_matches = data.get('manual_matches', [])
    if not selected_ids and not manual_matches:
        return jsonify({"status": "error", "message": "Hiç maç seçilmedi!"}), 400

    def run_analysis():
        try:
            run_selected_analysis(selected_ids, manual_matches)
        except Exception as e:
            logger.error(f"Analysis error: {e}")

    thread = threading.Thread(target=run_analysis)
    thread.daemon = False
    thread.start()
    total = len(selected_ids) + len(manual_matches)
    return jsonify({
        "status": "success",
        "message": f"{total} maç analiz ediliyor...",
        "total": total
    })

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
    return jsonify({"status": "success", "message": "Sonuçlar kontrol ediliyor..."})

@app.route('/api/results/manual', methods=['POST'])
def api_manual_result():
    try:
        data = request.get_json()
        analysis_id = data.get('analysis_id')
        home_score = data.get('home_score')
        away_score = data.get('away_score')

        if analysis_id is None or home_score is None or away_score is None:
            return jsonify({"status": "error", "message": "Eksik veri"}), 400

        from backend.database import get_analysis_by_id, save_match_result, mark_telegram_sent
        from backend.results_checker import send_result_to_telegram, calculate_outcomes

        analysis = get_analysis_by_id(analysis_id)
        if not analysis:
            return jsonify({"status": "error", "message": "Analiz bulunamadı"}), 404

        outcomes = calculate_outcomes(analysis, home_score, away_score)

        # Boolean → integer dönüşümü
        outcomes['pred_1x2_correct'] = int(outcomes['pred_1x2_correct'])
        outcomes['actual_over25'] = int(outcomes['actual_over25'])
        outcomes['over25_correct'] = int(outcomes['over25_correct'])
        outcomes['actual_btts'] = int(outcomes['actual_btts'])
        outcomes['btts_correct'] = int(outcomes['btts_correct'])
        outcomes['score_correct'] = int(outcomes['score_correct'])

        save_match_result(
            analysis_id=analysis_id,
            fixture_id=analysis.get('fixture_id'),
            home_score=home_score,
            away_score=away_score,
            source='manual',
            **outcomes
        )

        send_result_to_telegram(analysis, home_score, away_score, outcomes)
        mark_telegram_sent(analysis_id)

        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Manual result error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
