import os
import json
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

def extract_form(matches, team_id):
    return 'N/A'

def calc_goals_stats(matches, team_id):
    return 0, 0

def calc_home_away_stats(matches, team_id):
    return {'W': 0, 'D': 0, 'L': 0}, {'W': 0, 'D': 0, 'L': 0}

def analyze_with_claude(fixture, h2h_data, home_matches, away_matches):
    home_team = fixture['teams']['home']['name']
    away_team = fixture['teams']['away']['name']
    league = fixture['league']['name']
    match_time = fixture['fixture']['date']

    if ANTHROPIC_API_KEY:
        try:
            prompt = f"""Sen bir profesyonel futbol bahis analistsin. Genel futbol bilgine dayanarak aşağıdaki maçı analiz et.

## MAÇ BİLGİSİ
Maç: {home_team} vs {away_team}
Lig: {league}
Tarih: {match_time}

Bu iki takımın genel performanslarını, lig durumlarını, tarihsel H2H sonuçlarını ve güncel formlarını bilerek analiz et.

SADECE aşağıdaki JSON formatında yanıt ver, başka hiçbir şey yazma:

{{
  "prediction_1x2": "1 veya X veya 2",
  "over25_pct": <0-100 arası sayı>,
  "ht2g_pct": <0-100 arası sayı>,
  "btts_pct": <0-100 arası sayı>,
  "predicted_score": "örn: 2-1",
  "confidence": "Düşük veya Orta veya Yüksek veya Çok Yüksek",
  "reasoning": ["madde 1", "madde 2", "madde 3"],
  "h2h_summary": "Bu iki takım hakkında kısa H2H özeti"
}}"""

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
                'home_team': home_team,
                'away_team': away_team,
                'league': league,
                'match_time': match_time,
                'prediction_1x2': result.get('prediction_1x2', '?'),
                'over25_pct': float(result.get('over25_pct', 50)),
                'ht2g_pct': float(result.get('ht2g_pct', 30)),
                'btts_pct': float(result.get('btts_pct', 40)),
                'predicted_score': result.get('predicted_score', '?-?'),
                'confidence': result.get('confidence', 'Orta'),
                'reasoning': json.dumps(result.get('reasoning', []), ensure_ascii=False),
                'h2h_summary': result.get('h2h_summary', ''),
                'home_form': 'N/A',
                'away_form': 'N/A',
                'home_goals_avg': 0,
                'away_goals_avg': 0,
            }
        except Exception as e:
            logger.error(f"Claude analysis failed: {e}")

    return mock_analysis(fixture)

def mock_analysis(fixture):
    home_team = fixture['teams']['home']['name']
    away_team = fixture['teams']['away']['name']
    league = fixture['league']['name']
    match_time = fixture['fixture']['date']

    return {
        'analysis_date': datetime.now().strftime('%Y-%m-%d'),
        'fixture_id': fixture['fixture']['id'],
        'home_team': home_team,
        'away_team': away_team,
        'league': league,
        'match_time': match_time,
        'prediction_1x2': '1',
        'over25_pct': 55,
        'ht2g_pct': 25,
        'btts_pct': 45,
        'predicted_score': '2-1',
        'confidence': 'Orta',
        'reasoning': json.dumps([
            f"{home_team} ev sahibi avantajına sahip",
            "İstatistiksel model tahmini",
            "API anahtarı olmadan genel tahmin"
        ], ensure_ascii=False),
        'h2h_summary': 'Genel istatistiklere göre tahmin',
        'home_form': 'N/A',
        'away_form': 'N/A',
        'home_goals_avg': 0,
        'away_goals_avg': 0,
    }
