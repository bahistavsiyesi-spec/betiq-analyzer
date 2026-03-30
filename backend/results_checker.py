import logging
import requests
import os
import json
from datetime import datetime, timedelta, timezone
from backend.database import get_pending_result_checks, save_match_result, mark_telegram_sent

logger = logging.getLogger(__name__)

RAPIDAPI_KEY = os.environ.get('FOOTBALL_API_KEY', '')
RAPIDAPI_BASE = 'https://free-api-live-football-data.p.rapidapi.com'
RAPIDAPI_HEADERS = {
    'x-rapidapi-key': RAPIDAPI_KEY,
    'x-rapidapi-host': 'free-api-live-football-data.p.rapidapi.com'
}

FOOTBALL_DATA_KEY = os.environ.get('FOOTBALL_DATA_KEY', '')
FOOTBALL_DATA_BASE = 'https://api.football-data.org/v4'
FOOTBALL_DATA_HEADERS = {'X-Auth-Token': FOOTBALL_DATA_KEY}

TR_TZ = timezone(timedelta(hours=3))


def get_fixture_result_rapidapi(fixture_id):
    if not RAPIDAPI_KEY:
        return None
    try:
        resp = requests.get(
            f"{RAPIDAPI_BASE}/football-get-match-details",
            headers=RAPIDAPI_HEADERS,
            params={'matchId': fixture_id},
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        match = data.get('response', {}).get('match', {})
        if not match:
            return None
        finished = match.get('status', {}).get('finished', False)
        if not finished:
            return None
        home_score = match.get('home', {}).get('score')
        away_score = match.get('away', {}).get('score')
        if home_score is None or away_score is None:
            return None
        return {'home_score': int(home_score), 'away_score': int(away_score)}
    except Exception as e:
        logger.error(f"RapidAPI error for fixture {fixture_id}: {e}")
        return None


def get_fixture_result_footballdata(home_team, away_team, match_date):
    if not FOOTBALL_DATA_KEY:
        return None
    try:
        dt = datetime.fromisoformat(match_date.replace('Z', '+00:00'))
        date_from = dt.strftime('%Y-%m-%d')
        date_to = dt.strftime('%Y-%m-%d')

        resp = requests.get(
            f"{FOOTBALL_DATA_BASE}/matches",
            headers=FOOTBALL_DATA_HEADERS,
            params={'dateFrom': date_from, 'dateTo': date_to},
            timeout=15
        )
        if resp.status_code == 429:
            logger.warning("Football-data rate limit hit")
            return None
        resp.raise_for_status()
        matches = resp.json().get('matches', [])

        home_lower = home_team.lower().split()[0]
        away_lower = away_team.lower().split()[0]

        for m in matches:
            mh = m.get('homeTeam', {}).get('name', '').lower()
            ma = m.get('awayTeam', {}).get('name', '').lower()
            if home_lower in mh and away_lower in ma:
                status = m.get('status', '')
                if status != 'FINISHED':
                    return None
                score = m.get('score', {}).get('fullTime', {})
                hs = score.get('home')
                as_ = score.get('away')
                if hs is None or as_ is None:
                    return None
                logger.info(f"Football-data result: {home_team} {hs}-{as_} {away_team}")
                return {'home_score': int(hs), 'away_score': int(as_)}
    except Exception as e:
        logger.error(f"Football-data error: {e}")
    return None


def get_fixture_result(fixture_id, home_team='', away_team='', match_time=''):
    result = get_fixture_result_rapidapi(fixture_id)
    if result:
        logger.info(f"Result from RapidAPI: {home_team} vs {away_team}")
        return result

    if home_team and away_team and match_time:
        result = get_fixture_result_footballdata(home_team, away_team, match_time)
        if result:
            logger.info(f"Result from football-data: {home_team} vs {away_team}")
            return result

    return None


def calculate_value_bet_results(analysis, outcomes):
    value_bets_raw = analysis.get('value_bets')
    if not value_bets_raw:
        return None
    try:
        value_bets = json.loads(value_bets_raw)
    except:
        return None
    if not value_bets:
        return None

    results = []
    for vb in value_bets:
        label = vb.get('label', '')
        correct = None

        if label == 'Over 2.5':
            correct = bool(outcomes.get('actual_over25'))
        elif label == 'Under 2.5':
            correct = not bool(outcomes.get('actual_over25'))
        elif label == 'KG Var':
            correct = bool(outcomes.get('actual_btts'))
        elif label == 'KG Yok':
            correct = not bool(outcomes.get('actual_btts'))
        elif label == 'İY 0.5 Üst':
            correct = bool(outcomes.get('ht_correct'))
        elif label in ('1X2 (Ev)', '1X2 (Deplasman)', '1X2 (Beraberlik)'):
            correct = bool(outcomes.get('pred_1x2_correct'))
        elif label == 'Over 1.5':
            correct = (outcomes.get('total_goals', 0) or 0) > 1
        elif label == 'Over 3.5':
            correct = (outcomes.get('total_goals', 0) or 0) > 3

        results.append({
            'label': label,
            'correct': correct,
            'odds': vb.get('odds'),
            'diff': vb.get('diff'),
            'our_pct': vb.get('our_pct'),
            'implied_pct': vb.get('implied_pct'),
        })

    return results if results else None


def calculate_outcomes(analysis, home_score, away_score, ht_home_score=None, ht_away_score=None):
    total_goals = home_score + away_score

    if home_score > away_score:
        actual_1x2 = '1'
    elif home_score == away_score:
        actual_1x2 = 'X'
    else:
        actual_1x2 = '2'
    pred_1x2_correct = (analysis.get('prediction_1x2') == actual_1x2)

    over25_pct = int(analysis.get('over25_pct', 0))
    actual_over25 = total_goals > 2.5
    # Sadece eşik üstü tahminler sayılır, eşik altı False olarak kaydedilir
    if over25_pct >= 65:
        over25_correct = actual_over25       # Üst tahmin ettik, üst geldiyse True
    else:
        over25_correct = False               # Eşik altı → istatistiğe katma

    btts_pct = int(analysis.get('btts_pct', 0))
    actual_btts = home_score > 0 and away_score > 0
    # Sadece eşik üstü tahminler sayılır
    if btts_pct >= 65:
        btts_correct = actual_btts           # KG Var tahmin ettik, var geldiyse True
    else:
        btts_correct = False                 # Eşik altı → istatistiğe katma

    predicted = analysis.get('predicted_score', '?-?')
    try:
        ph, pa = predicted.split('-')
        score_correct = (int(ph) == home_score and int(pa) == away_score)
    except:
        score_correct = False

    ht_correct = False
    if ht_home_score is not None and ht_away_score is not None:
        ht_pct = int(analysis.get('ht2g_pct', 0))
        actual_ht_goal = (ht_home_score + ht_away_score) >= 1
        if ht_pct >= 65:
            ht_correct = actual_ht_goal      # İY 0.5 Üst tahmin ettik
        else:
            ht_correct = False               # Eşik altı → istatistiğe katma

    return {
        'actual_1x2': actual_1x2,
        'pred_1x2_correct': pred_1x2_correct,
        'actual_over25': actual_over25,
        'over25_correct': over25_correct,
        'actual_btts': actual_btts,
        'btts_correct': btts_correct,
        'score_correct': score_correct,
        'ht_correct': ht_correct,
        'total_goals': total_goals,
    }


def send_result_to_telegram(analysis, home_score, away_score, outcomes, ht_home_score=None, ht_away_score=None):
    from backend.telegram_sender import send_message

    match_time = analysis.get('match_time', '')
    try:
        dt = datetime.fromisoformat(match_time.replace('Z', '+00:00'))
        dt = dt.astimezone(TR_TZ)
        time_str = dt.strftime('%H:%M')
    except:
        time_str = '--:--'

    def tick(correct):
        return '✅' if correct else '❌'

    pred = analysis.get('prediction_1x2', '?')
    pred_text = {
        '1': f"1 ({analysis.get('home_team','?')})",
        'X': 'X (Beraberlik)',
        '2': f"2 ({analysis.get('away_team','?')})"
    }.get(pred, pred)

    over25_pct = int(analysis.get('over25_pct', 0))
    btts_pct = int(analysis.get('btts_pct', 0))

    over25_label = f"2.5 Üst (%{over25_pct})" if over25_pct >= 65 else f"2.5 Alt (%{100 - over25_pct})"
    over25_result = f"{'Üstü ✓' if outcomes['actual_over25'] else 'Altı ✗'}"

    btts_label = f"KG Var (%{btts_pct})" if btts_pct >= 65 else f"KG Yok (%{100 - btts_pct})"
    btts_result = f"{'Var ✓' if outcomes['actual_btts'] else 'Yok ✗'}"

    ht_line = ''
    if ht_home_score is not None and ht_away_score is not None:
        ht_pct = int(analysis.get('ht2g_pct', 0))
        ht_label = f"İY 0.5 Üst (%{ht_pct})" if ht_pct >= 65 else f"İY 0.5 Alt (%{100 - ht_pct})"
        ht_result = f"İY {ht_home_score}-{ht_away_score} ({'Var ✓' if (ht_home_score + ht_away_score) >= 1 else 'Yok ✗'})"
        ht_line = f"\n{tick(outcomes['ht_correct'])} {ht_label} → <b>{ht_result}</b>"

    msg = f"""
<b>{'─' * 28}</b>
⚽ <b>SONUÇ: {analysis.get('home_team')} vs {analysis.get('away_team')}</b>
🏆 {analysis.get('league', '')}  🕐 {time_str}

📊 <b>Gerçek Skor: {home_score}-{away_score}</b>
🎯 Tahmini Skor: {analysis.get('predicted_score','?-?')} {tick(outcomes['score_correct'])}

<b>Tahmin Sonuçları:</b>
{tick(outcomes['pred_1x2_correct'])} 1X2: {pred_text} → <b>{outcomes['actual_1x2']}</b>
{tick(outcomes['over25_correct'])} {over25_label} → <b>{over25_result}</b>
{tick(outcomes['btts_correct'])} {btts_label} → <b>{btts_result}</b>{ht_line}"""

    send_message(msg)


def check_and_send_results():
    pending = get_pending_result_checks()
    if not pending:
        logger.info("No pending result checks")
        return

    now_tr = datetime.now(TR_TZ)
    updated = 0

    for analysis in pending:
        try:
            match_time = analysis.get('match_time', '')
            try:
                dt = datetime.fromisoformat(match_time.replace('Z', '+00:00'))
                dt = dt.astimezone(TR_TZ)
                if (now_tr - dt).total_seconds() < 7200:
                    logger.info(f"Match not finished yet: {analysis['home_team']} vs {analysis['away_team']}")
                    continue
            except:
                pass

            result = get_fixture_result(
                fixture_id=analysis['fixture_id'],
                home_team=analysis.get('home_team', ''),
                away_team=analysis.get('away_team', ''),
                match_time=match_time
            )

            if not result:
                logger.info(f"No result yet: {analysis['home_team']} vs {analysis['away_team']}")
                continue

            outcomes = calculate_outcomes(analysis, result['home_score'], result['away_score'])
            outcomes['pred_1x2_correct'] = int(outcomes['pred_1x2_correct'])
            outcomes['actual_over25'] = int(outcomes['actual_over25'])
            outcomes['over25_correct'] = int(outcomes['over25_correct'])
            outcomes['actual_btts'] = int(outcomes['actual_btts'])
            outcomes['btts_correct'] = int(outcomes['btts_correct'])
            outcomes['score_correct'] = int(outcomes['score_correct'])
            outcomes['ht_correct'] = int(outcomes['ht_correct'])

            vb_results = calculate_value_bet_results(analysis, outcomes)

            save_match_result(
                analysis_id=analysis['id'],
                fixture_id=analysis['fixture_id'],
                home_score=result['home_score'],
                away_score=result['away_score'],
                source='auto',
                value_bet_results=vb_results,
                **outcomes
            )
            send_result_to_telegram(analysis, result['home_score'], result['away_score'], outcomes)
            mark_telegram_sent(analysis['id'])
            updated += 1
            logger.info(f"Result sent: {analysis['home_team']} vs {analysis['away_team']} {result['home_score']}-{result['away_score']}")

        except Exception as e:
            logger.error(f"Error checking result for {analysis.get('home_team')}: {e}")
            continue

    logger.info(f"Result check done: {updated} results sent")
    return updated
