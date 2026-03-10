from flask import Flask, render_template, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import os
import threading
from backend.football_api import get_todays_fixtures
from backend.analyzer import run_selected_analysis
from backend.database import init_db, get_today_matches
from backend.telegram_sender import send_daily_analysis

app = Flask(__name__, template_folder='frontend/templates', static_folder='frontend/static')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init_db()

scheduler = BackgroundScheduler()
scheduler.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/fixtures/today')
def api_today_fixtures():
    """Bugünün maçlarını analiz yapılmadan getir"""
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
    """Analiz edilmiş maçları getir"""
    matches = get_today_matches()
    return jsonify(matches)

@app.route('/api/analyze/selected', methods=['POST'])
def api_analyze_selected():
    """Seçilen maçları analiz et"""
    data = request.get_json()
    selected_ids = data.get('fixture_ids', [])
    manual_matches = data.get('manual_matches', [])

    if not selected_ids and not manual_matches:
        return jsonify({"status": "error", "message": "Hiç maç seçilmedi!"}), 400

    def run_analysis():
        try:
            run_selected_analysis(selected_ids, manual_matches)
            matches = get_today_matches()
            send_daily_analysis(matches)
        except Exception as e:
            logger.error(f"Analysis error: {e}")

    thread = threading.Thread(target=run_analysis)
    thread.daemon = True
    thread.start()

    total = len(selected_ids) + len(manual_matches)
    return jsonify({
        "status": "success",
        "message": f"{total} maç analiz ediliyor...",
        "total": total
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
