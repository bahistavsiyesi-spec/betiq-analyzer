from flask import Flask, render_template, jsonify, request
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import os
import threading
from backend.football_api import get_todays_fixtures
from backend.analyzer import run_selected_analysis
from backend.database import init_db, get_today_matches, get_analyses_by_date, get_available_dates

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
        logger.info("Gece sıfırlama tamamlandı. Yeni gün başladı.")
    except Exception as e:
        logger.error(f"Midnight reset failed: {e}")

scheduler = BackgroundScheduler()
scheduler.add_job(scheduled_result_check, 'interval', minutes=30, id='result_check')
scheduler.add_job(midnight_reset, 'cron', hour=0, minute=1, id='midnight_reset')
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

@app.route('/api/telegram/send', methods=['POST'])
def api_telegram_send():
    try:
        from backend.telegram_sender import send_daily_analysis
        matches = get_today_matches()
        if not matches:
            return jsonify({"status": "error", "message": "Gönderilecek analiz yok"}), 400
        send_daily_analysis(matches)
        return jsonify({"status": "success", "message": f"{len(matches)} maç Telegram'a gönderildi!"})
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
    return jsonify({"status": "success", "message": "Sonuçlar kontrol ediliyor..."})

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
        from backend.results_checker import send_result_to_telegram, calculate_outcomes

        analysis = get_analysis_by_id(analysis_id)
        if not analysis:
            return jsonify({"status": "error", "message": "Analiz bulunamadı"}), 404

        ht_hs = int(ht_home_score) if ht_home_score is not None and ht_home_score != '' else None
        ht_as = int(ht_away_score) if ht_away_score is not None and ht_away_score != '' else None

        outcomes = calculate_outcomes(analysis, home_score, away_score, ht_hs, ht_as)

        outcomes['pred_1x2_correct'] = int(outcomes['pred_1x2_correct'])
        outcomes['actual_over25'] = int(outcomes['actual_over25'])
        outcomes['over25_correct'] = int(outcomes['over25_correct'])
        outcomes['actual_btts'] = int(outcomes['actual_btts'])
        outcomes['btts_correct'] = int(outcomes['btts_correct'])
        outcomes['score_correct'] = int(outcomes['score_correct'])
        outcomes['ht_correct'] = int(outcomes['ht_correct'])

        save_match_result(
            analysis_id=analysis_id,
            fixture_id=analysis.get('fixture_id'),
            home_score=home_score,
            away_score=away_score,
            ht_home_score=ht_hs,
            ht_away_score=ht_as,
            source='manual',
            **outcomes
        )

        send_result_to_telegram(analysis, home_score, away_score, outcomes, ht_hs, ht_as)
        mark_telegram_sent(analysis_id)

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

            pct_1x2 = round(c1x2 / total_results * 100)
            pct_over25 = round(c_over25 / total_results * 100)
            pct_btts = round(c_btts / total_results * 100)

            with_ht = [m for m in with_results if m.get('ht_home_score') is not None]
            ht_line = f"\n⚽ İY 0.5 Üst: <b>{c_ht}/{len(with_ht)}</b>" if with_ht else ''

            details = ''
            for m in with_results:
                pred = m.get('prediction_1x2', '?')
                tick_1x2 = '✅' if m.get('pred_1x2_correct') else '❌'
                tick_over = '✅' if m.get('over25_correct') else '❌'
                tick_btts = '✅' if m.get('btts_correct') else '❌'
                tick_score = '✅' if m.get('score_correct') else '❌'
                tick_ht = ''
                if m.get('ht_home_score') is not None:
                    tick_ht = f"  {'✅' if m.get('ht_correct') else '❌'} İY {m['ht_home_score']}-{m['ht_away_score']}"
                details += f"\n⚽ <b>{m['home_team']} {m['home_score']}-{m['away_score']} {m['away_team']}</b>\n"
                details += f"   {tick_1x2} 1X2: {pred}  {tick_over} 2.5 Gol  {tick_btts} KG Var  {tick_score} Skor{tick_ht}\n"

            msg = f"""
<b>{'─' * 28}</b>
📊 <b>GÜNLÜK RAPOR — {date_str}</b>
<b>{'─' * 28}</b>

📋 Toplam Analiz: <b>{total}</b>
✅ Sonuç Girilmiş: <b>{total_results}</b>

<b>Başarı Oranları:</b>
🎯 1X2: <b>{c1x2}/{total_results} (%{pct_1x2})</b>
⚽ 2.5 Gol Üstü: <b>{c_over25}/{total_results} (%{pct_over25})</b>
🔁 KG Var: <b>{c_btts}/{total_results} (%{pct_btts})</b>
🏆 Skor Doğru: <b>{c_score}/{total_results}</b>{ht_line}
{details}
<b>{'─' * 28}</b>"""
        else:
            msg = f"""
<b>{'─' * 28}</b>
📊 <b>GÜNLÜK RAPOR — {date_str}</b>
<b>{'─' * 28}</b>

📋 Toplam Analiz: <b>{total}</b>
⏳ Henüz sonuç girilmemiş maçlar var.
<b>{'─' * 28}</b>"""

        send_message(msg)
        return jsonify({"status": "success"})

    except Exception as e:
        logger.error(f"Daily report error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/parse/image', methods=['POST'])
def api_parse_image():
    try:
        import anthropic
        from datetime import datetime

        data = request.get_json()
        image_data = data.get('image')
        media_type = data.get('media_type', 'image/jpeg')

        if not image_data:
            return jsonify({"status": "error", "message": "Görsel eksik"}), 400

        client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))
        today = datetime.now().strftime('%Y-%m-%d')

        message = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data,
                            },
                        },
                        {
                            "type": "text",
                            "text": f"""Bu görseldeki maç programını analiz et. Bugünün tarihi: {today}.

Görseldeki TÜM maçları JSON formatında döndür. Her maç için:
- home_team: ev sahibi takım adı (tam ve resmi isim, kısaltma kullanma)
- away_team: deplasman takımı adı (tam ve resmi isim, kısaltma kullanma)
- league: lig adı (görünüyorsa, yoksa "Bilinmeyen Lig")
- time: maç saati HH:MM formatında (görünüyorsa, yoksa null)

Önemli: Takım isimlerini tam yaz. Örnek: "Man City" değil "Manchester City", "Atl. Madrid" değil "Atletico Madrid".

Sadece JSON array döndür, başka hiçbir şey yazma. Örnek:
[{{"home_team": "Fenerbahçe", "away_team": "Galatasaray", "league": "Süper Lig", "time": "20:00"}}]

Eğer görsel bir maç programı değilse boş array [] döndür."""
                        }
                    ],
                }
            ],
        )

        import json
        raw = message.content[0].text.strip()
        raw = raw.replace('```json', '').replace('```', '').strip()
        parsed = json.loads(raw)

        matches = []
        for m in parsed:
            match_date = datetime.now()
            if m.get('time'):
                try:
                    h, mi = m['time'].split(':')
                    match_date = match_date.replace(hour=int(h), minute=int(mi), second=0)
                except:
                    pass
            matches.append({
                'home_team': m.get('home_team', ''),
                'away_team': m.get('away_team', ''),
                'league': m.get('league', 'Bilinmeyen Lig'),
                'date': match_date.isoformat()
            })

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
        logger.error(f"Delete error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/matches/clear', methods=['DELETE'])
def api_clear_matches():
    try:
        from backend.database import delete_today_analyses
        delete_today_analyses()
        return jsonify({"status": "success"})
    except Exception as e:
        logger.error(f"Clear error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# ─── Debug Endpointler ────────────────────────────────────────────────────────

@app.route('/api/debug/openliga/<league>')
def debug_openliga(league):
    try:
        import requests as req
        resp = req.get(f'https://api.openligadb.de/getavailableteams/{league}/2024', timeout=10)
        resp.raise_for_status()
        teams = resp.json()
        result = [{'id': t.get('teamId'), 'name': t.get('teamName'), 'short': t.get('shortName', '')} for t in teams]
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/debug/footballdata/<league_code>')
def debug_footballdata(league_code):
    try:
        import requests as req
        resp = req.get(
            f'https://api.football-data.org/v4/competitions/{league_code}/teams',
            headers={'X-Auth-Token': os.environ.get('FOOTBALL_DATA_KEY', '')},
            timeout=10
        )
        resp.raise_for_status()
        teams = resp.json().get('teams', [])
        result = [{'id': t.get('id'), 'name': t.get('name'), 'short': t.get('shortName', '')} for t in teams]
        return jsonify(sorted(result, key=lambda x: x['name']))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
