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


def pct_bar(pct, length=10):
    pct = int(pct)
    filled = round(pct / 100 * length)
    empty = length - filled
    if pct >= 70:
        fill_char = '🟩'
    elif pct >= 40:
        fill_char = '🟨'
    else:
        fill_char = '🟥'
    return fill_char * filled + '⬜' * empty + f' <b>{pct}%</b>'


def format_match(match, index):
    conf_emoji = {
        'Çok Yüksek': '🔥', 'Yüksek': '✅', 'Orta': '⚠️', 'Düşük': '❌'
    }.get(match.get('confidence', 'Orta'), '⚠️')

    pred = match.get('prediction_1x2', '?')
    pred_text = {
        '1': f"🏠 {match.get('home_team', '?')} Kazanır",
        'X': '🤝 Beraberlik',
        '2': f"✈️ {match.get('away_team', '?')} Kazanır"
    }.get(pred, pred)

    match_time = match.get('match_time', '')
    try:
        dt = datetime.fromisoformat(match_time.replace('Z', '+00:00'))
        dt = dt.astimezone(TR_TZ)
        time_str = dt.strftime('%H:%M')
    except:
        time_str = '--:--'

    over25 = int(match.get('over25_pct', 0))
    ht2g  = int(match.get('ht2g_pct', 0))
    btts  = int(match.get('btts_pct', 0))

    # Tahmini skor
    pred_score    = match.get('predicted_score', '?-?')
    pred_ht_score = match.get('predicted_ht_score', '?-?')

    # Analiz yorumu (ilk 2 madde)
    try:
        reasoning = json.loads(match.get('reasoning', '[]'))
    except:
        reasoning = []
    reasoning_text = '\n'.join([f"  → {r}" for r in reasoning[:2]])

    # Value bets
    vb_text = ''
    try:
        vb_raw = match.get('value_bets')
        vb_list = json.loads(vb_raw) if isinstance(vb_raw, str) and vb_raw else (vb_raw or [])
        if vb_list:
            vb_lines = []
            for vb in vb_list[:3]:
                diff_color = '🟢' if vb['diff'] >= 15 else '🟡' if vb['diff'] >= 10 else '🔵'
                vb_lines.append(f"  {diff_color} <b>{vb['label']}</b> @ {vb['odds']} | Bizim: %{vb['our_pct']} | Bahisçi: %{vb['implied_pct']} | <b>+{vb['diff']}%</b>")
            vb_text = '\n💎 <b>Value Bet Fırsatları:</b>\n' + '\n'.join(vb_lines)
    except:
        pass

    # Korner istatistikleri
    corner_text = ''
    try:
        csv_data = match.get('csv_data')
        if isinstance(csv_data, str):
            csv_data = json.loads(csv_data)
        if csv_data:
            avg_c   = csv_data.get('avg_corners')
            over85  = csv_data.get('avg_corners_85')
            over95  = csv_data.get('avg_corners_95')
            over105 = csv_data.get('avg_corners_105')
            if avg_c is not None:
                c_parts = [f"Ort: {float(avg_c):.1f}"]
                if over85  is not None: c_parts.append(f"8.5Ü: %{int(float(over85)  if float(over85)  > 1 else float(over85)*100)}")
                if over95  is not None: c_parts.append(f"9.5Ü: %{int(float(over95)  if float(over95)  > 1 else float(over95)*100)}")
                if over105 is not None: c_parts.append(f"10.5Ü: %{int(float(over105) if float(over105) > 1 else float(over105)*100)}")
                corner_text = '\n🚩 <b>Korner:</b> ' + ' | '.join(c_parts)
    except:
        pass

    # Güven seviyesine göre 1X2 göster
    high_conf = match.get('confidence', '') in ('Yüksek', 'Çok Yüksek', 'Yuksek', 'Cok Yuksek')

    msg = f"""
<b>{'━' * 24}</b>
⚽ <b>{match.get('home_team')} — {match.get('away_team')}</b>
🏆 {match.get('league', '?')}  🕐 {time_str}
{conf_emoji} <b>{pred_text}</b>  <i>(Güven: {match.get('confidence', 'Orta')})</i>

🎯 <b>Tahmini Skor:</b> {pred_score}  |  <b>İY:</b> {pred_ht_score}

📊 <b>İstatistikler:</b>
2.5 Gol Üstü
{pct_bar(over25)}
İY 0.5 Üst
{pct_bar(ht2g)}
KG Var (BTTS)
{pct_bar(btts)}{corner_text}{vb_text}

🧠 <b>Analiz:</b>
{reasoning_text}"""

    return msg


def send_daily_analysis(matches):
    if not matches:
        send_message("⚠️ Bugün analiz edilecek maç bulunamadı.")
        return

    today = datetime.now(TR_TZ).strftime('%d %B %Y')
    high_conf = [m for m in matches if m.get('confidence') in ['Yüksek', 'Çok Yüksek']]
    avg_over25 = int(sum(m.get('over25_pct', 0) for m in matches) / len(matches))

    header = f"""⚡ <b>GOLLAZIM — Günlük Analiz</b>
📅 {today}
🔍 <b>{len(matches)} maç analiz edildi</b>
🔥 <b>{len(high_conf)} yüksek güvenli maç</b>
📊 <b>Ort. 2.5 Gol Üstü: %{avg_over25}</b>
<i>Bugünün maçları 👇</i>"""

    send_message(header)

    for i, match in enumerate(matches, 1):
        msg = format_match(match, i)
        send_message(msg)

    footer = f"""
<b>{'━' * 24}</b>
⚡ <b>GOLLAZIM Analiz Tamamlandı</b>
⚠️ <i>Bu analizler yatırım tavsiyesi değildir.</i>"""

    send_message(footer)
