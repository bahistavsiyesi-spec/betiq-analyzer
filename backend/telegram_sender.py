import os
import json
import logging
import requests
from datetime import datetime, timezone, timedelta
logger = logging.getLogger(__name__)
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')
TR_TZ = timezone(timedelta(hours=3))

def send_message(text, parse_mode='HTML'):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not set")
        return False
    try:
        resp = requests.post(
            f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage',
            json={
                'chat_id': TELEGRAM_CHAT_ID,
                'text': text,
                'parse_mode': parse_mode
            },
            timeout=10
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False

def format_match(match, index):
    conf_emoji = {
        'Çok Yüksek': '🔥',
        'Yüksek': '✅',
        'Orta': '⚠️',
        'Düşük': '❌'
    }.get(match.get('confidence', 'Orta'), '⚠️')
    pred = match.get('prediction_1x2', '?')
    pred_text = {
        '1': f"1 ({match.get('home_team', '?')})",
        'X': 'X (Beraberlik)',
        '2': f"2 ({match.get('away_team', '?')})"
    }.get(pred, pred)
    try:
        reasoning = json.loads(match.get('reasoning', '[]'))
    except:
        reasoning = []
    reasoning_text = '\n'.join([f"  → {r}" for r in reasoning[:3]])
    match_time = match.get('match_time', '')
    try:
        dt = datetime.fromisoformat(match_time.replace('Z', '+00:00'))
        dt = dt.astimezone(TR_TZ)
        time_str = dt.strftime('%H:%M')
    except:
        time_str = match_time[11:16] if len(match_time) > 15 else '--:--'
    return f"""
<b>{'─' * 28}</b>
<b>#{index} {match.get('home_team')} vs {match.get('away_team')}</b>
🏆 {match.get('league', 'Bilinmeyen Lig')}  🕐 {time_str}
📊 <b>Tahmin:</b> {pred_text}
🎯 <b>Skor:</b> {match.get('predicted_score', '?-?')}
{conf_emoji} <b>Güven:</b> {match.get('confidence', 'Orta')}
📈 2.5 Gol Üstü: <b>{int(match.get('over25_pct', 0))}%</b>
⚽ İY 0.5 Üst: <b>{int(match.get('ht2g_pct', 0))}%</b>
🔁 KG Var: <b>{int(match.get('btts_pct', 0))}%</b>
🧠 <b>Analiz:</b>
{reasoning_text}"""

def send_daily_analysis(matches):
    if not matches:
        send_message("⚠️ Bugün analiz edilecek maç bulunamadı.")
        return
    today = datetime.now(TR_TZ).strftime('%d %B %Y')
    high_conf = [m for m in matches if m.get('confidence') in ['Yüksek', 'Çok Yüksek']]
    avg_over25 = int(sum(m.get('over25_pct', 0) for m in matches) / len(matches))
    header = f"""⚡ <b>BetIQ — Günlük Analiz</b>
📅 {today}
🔍 <b>{len(matches)} maç analiz edildi</b>
🔥 <b>{len(high_conf)} yüksek güvenli maç</b>
📊 <b>Ort. 2.5 Gol Üstü: %{avg_over25}</b>
<i>Aşağıda bugünün en güçlü maçları 👇</i>"""
    send_message(header)
    for i, match in enumerate(matches, 1):
        msg = format_match(match, i)
        send_message(msg)
    footer = f"""
<b>{'─' * 28}</b>
⚡ <b>BetIQ Analiz Tamamlandı</b>
⚠️ <i>Bu analizler yatırım tavsiyesi değildir. Sorumlu oynayın.</i>"""
    send_message(footer)
