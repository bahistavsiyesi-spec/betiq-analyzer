from flask import Flask, render_template, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import os
import threading
from backend.analyzer import run_daily_analysis
from backend.database import init_db, get_today_matches, get_recent_analyses
from backend.telegram_sender import send_daily_analysis

app = Flask(__name__, template_folder='frontend/templates', static_folder='frontend/static')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

init_db()

def run_analysis_and_notify():
    try:
        run_daily_analysis()
        matches = get_today_matches()
        send_daily_analysis(matches)
    except Exception as e:
        logger.error(f"Analysis thread error: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(run_analysis_and_notify, 'cron', hour=7, minute=0, id='daily_analysis')
scheduler.start()

@app.route('/')
def index():
    matches = get_today_matches()
    return render_template('index.html', matches=matches)

@app.route('/api/matches/today')
def api_today_matches():
    matches = get_today_matches()
    return jsonify(matches)

@app.route('/api/matches/history')
def api_history():
    analyses = get_recent_analyses(days=7)
    return jsonify(analyses)

@app.route('/api/analyze/run', methods=['POST'])
def api_run_analysis():
    try:
        # Arka planda çalıştır, timeout olmaz
        thread = threading.Thread(target=run_analysis_and_notify)
        thread.daemon = True
        thread.start()
        return jsonify({"status": "success", "message": "Analiz başlatıldı! 2-3 dakika sonra sonuçlar gelecek."})
    except Exception as e:
        logger.error(f"Analysis error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
