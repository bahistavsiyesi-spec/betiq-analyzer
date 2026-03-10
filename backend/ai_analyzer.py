import os
import json
import logging
import requests
from datetime import datetime
from backend.analyzer import extract_form, calc_goals_stats, calc_home_away_stats

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

def build_analysis_prompt(fixture, h2h_data, home_matches, away_matches):
    home_team = fixture['teams']['home']['name']
    away_team = fixture['teams']['away']['name']
    league = fixture['league']['name']
    match_time = fixture['fixture']['date']
    home_id = fixture['teams']['home']['id']
    away_id = fixture['teams']['away']['id']

    h2h_lines = []
    for m in h2h_data[-5:]:
        hg = m['goals']['home'] or 0
        ag = m['goals']['away'] or 0
        hn = m['teams']['home']['name']
        an = m['teams']['away']['name']
        dt = m['fixture']['date'][:10]
        h2h_lines.append(f"  {dt}: {hn} {hg}-{ag} {an}")
    h2h_text = '\n'.join(h2h_lines) if h2h_lines else "  H2H verisi yok"

    home_form = extract_form(home_matches, home_id)
    home_scored, home_conceded = calc_goals_stats(home_matches, home_id)
    home_home_stats, home_away_stats = calc_home_away_stats(home_matches, home_id)

    away_form = extract_form(away_matches, away_id)
    away_scored, away_conceded = calc_goals_stats(away_matches, away_id)
    away_home_stats, away_away_stats = calc_home_away_stats(away_matches, away_id)

    prompt = f"""Sen bir profesyonel futbol bahis analistsin. Aşağıdaki verileri analiz ederek tahmin yap.

## MAÇ BİLGİSİ
Maç: {home_team} vs {away_team}
Lig: {league}
Tarih: {match_time}

## SON 5 KARŞILAŞMA (H2H)
{h2h_text}

## {home_team} FORM (Son 10 maç)
- Form: {home_form}
- Ortalama gol atma: {home_scored}
- Ortalama gol yeme: {home_conceded}
- İç saha: {home_home_stats['W']}G {home_home_stats['D']}B {home_home_stats['L']}M
- Deplasman: {home_away_stats['W']}G {home_away_stats['D']}B {home_away_stats['L']}M

## {away_team} FORM (Son 10 maç)
- Form: {away_form}
- Ortalama gol atma: {away_scored}
- Ortalama gol yeme: {away_conceded}
- İç saha: {away_home_stats['W']}G {away_home_stats['D']}B {away_home_stats['L']}M
- Deplasman: {away_away_stats['W']}G {away_away_stats['D']}B {away_away_stats['L']}M

## GÖREV
Bu verilere dayanarak aşağıdaki JSON formatında bir analiz üret. SADECE JSON döndür, başka hiçbir şey yazma:

{{
  "prediction_1x2": "1 veya X veya 2",
  "over25_pct": <0-100 arası sayı>,
  "ht2g_pct": <0-100 arası sayı>,
  "btts_pct": <0-100 arası sayı>,
  "predicted_score": "örn: 2-1",
  "confidence": "Düşük veya Orta veya Yüksek veya Çok Yüksek",
  "reasoning": ["madde 1", "madde 2", "madde 3"],
  "h2h_summary": "H2H'dan 1 cümle özet",
  "home_form_analysis": "ev sahibi form özeti",
  "away_form_analysis": "deplasman takımı form özeti"
}}"""

    return prompt, home_form, away_form, home_scored, away_scored

def analyze_with_claude(fixture, h2h_data, home_matches, away_matches):
    if not ANTHROPIC_API_KEY:
        return mock_analysis(fixture, h2h_data, home_matches, away_matches)
    try:
        prompt, home_form, away_form, home_goals_avg, away_goals_avg = build_analysis_prompt(
            fixture, h2h_data, home_matches, away_matches
        )
        response = requests.post(
            'https://api.anthropic.com/v1/messages',
            headers={
                'x-api-key': ANTHROPIC_API_KEY,
                'anthropic-version': '2023-06-01',
                'content-type': 'application/json'
            },
            json={
                'model': 'claude-sonnet-4-20250514',
                'max_tokens': 1000,
                'messages': [{'role': 'user', 'content': prompt}]
            },
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        raw_text = data['content'][0]['text'].strip()
        if '```json' in raw_text:
            raw_text = raw_text.split('```json')[1].split('```')[0].strip()
        elif '```' in raw_text:
            raw_text = raw_text.split('```')[1].split('```')[0].strip()
        result = json.loads(raw_text)
        return {
            'analysis_date': datetime.now().strftime('%Y-%m-%d'),
            'fixture_id': fixture['fixture']['id'],
            'home_team': fixture['teams']['home']['name'],
            'away_team': fixture['teams']['away']['name'],
            'league': fixture['league']['name'],
            'match_time': fixture['fixture']['date'],
            'prediction_1x2': result.get('prediction_1x2', '?'),
            'over25_pct': float(result.get('over25_pct', 50)),
            'ht2g_pct': float(result.get('ht2g_pct', 30)),
            'btts_pct': float(result.get('btts_pct', 40)),
            'predicted_score': result.get('predicted_score', '?-?'),
            'confidence': result.get('confidence', 'Orta'),
            'reasoning': json.dumps(result.get('reasoning', []), ensure_ascii=False),
            'h2h_summary': result.get('h2h_summary', ''),
            'home_form': home_form,
            'away_form': away_form,
            'home_goals_avg': home_goals_avg,
            'away_goals_avg': away_goals_avg,
        }
    except Exception as e:
        logger.error(f"Claude analysis failed: {e}")
        return mock_analysis(fixture, h2h_data, home_matches, away_matches)

def mock_analysis(fixture, h2h_data, home_matches, away_matches):
    home_id = fixture['teams']['home']['id']
    away_id = fixture['teams']['away']['id']
    home_form = extract_form(home_matches, home_id) if home_matches else 'N/A'
    away_form = extract_form(away_matches, away_id) if away_matches else 'N/A'
    home_scored, home_conceded = calc_goals_stats(home_matches, home_id) if home_matches else (1.2, 1.1)
    away_scored, away_conceded = calc_goals_stats(away_matches, away_id) if away_matches else (1.0, 1.3)
    total_goals_avg = home_scored + away_scored
    over25 = min(85, max(35, int(total_goals_avg * 25)))
    btts = min(75, max(30, int((home_scored * away_scored) * 20)))
    home_wins = home_form.count('W')
    away_wins = away_form.count('W')
    if home_wins > away_wins + 1:
        pred = '1'
        score = '2-1'
    elif away_wins > home_wins + 1:
        pred = '2'
        score = '1-2'
    else:
        pred = 'X'
        score = '1-1'
    return {
        'analysis_date': datetime.now().strftime('%Y-%m-%d'),
        'fixture_id': fixture['fixture']['id'],
        'home_team': fixture['teams']['home']['name'],
        'away_team': fixture['teams']['away']['name'],
        'league': fixture['league']['name'],
        'match_time': fixture['fixture']['date'],
        'prediction_1x2': pred,
        'over25_pct': over25,
        'ht2g_pct': int(over25 * 0.45),
        'btts_pct': btts,
        'predicted_score': score,
        'confidence': 'Orta',
        'reasoning': json.dumps([
            f"{fixture['teams']['home']['name']} son formu: {home_form}",
            f"Maç başına ortalama toplam gol: {round(total_goals_avg, 1)}",
            "İstatistiksel model tahmini"
        ], ensure_ascii=False),
        'h2h_summary': f"Son {len(h2h_data)} H2H maçı incelendi",
        'home_form': home_form,
        'away_form': away_form,
        'home_goals_avg': home_scored,
        'away_goals_avg': away_scored,
    }
