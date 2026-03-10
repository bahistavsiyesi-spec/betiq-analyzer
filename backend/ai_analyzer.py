import os
import json
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')

def extract_form(matches, team_id):
    return 'N/A'

def calc_goals_stats(matches, team_id):
    return 0, 0

def calc_home_away_stats(matches, team_id):
    return {'W': 0, 'D': 0, 'L': 0}, {'W': 0, 'D': 0, 'L': 0}

def call_groq(prompt):
    response = requests.post(
        'https://api.groq.com/openai/v1/chat/completions',
        headers={
            'Authorization': f'Bearer {GROQ_API_KEY}',
            'Content-Type': 'application/json'
        },
        json={
            'model': 'llama-3.3-70b-versatile',
            'messages': [
                {
                    'role': 'system',
                    'content': 'You are an expert football statistician and betting analyst. You must provide UNIQUE and SPECIFIC analysis for each match based on the actual teams involved. Never use generic or identical statistics for different matches. Base your analysis on your knowledge of each team\'s actual performance, style, and history.'
                },
                {'role': 'user', 'content': prompt}
            ],
            'max_tokens': 1000,
            'temperature': 0.7
        },
        timeout=30
    )
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content'].strip()

def analyze_with_claude(fixture, h2h_data, home_matches, away_matches):
    home_team = fixture['teams']['home']['name']
    away_team = fixture['teams']['away']['name']
    league = fixture['league']['name']
    match_time = fixture['fixture']['date']

    prompt = f"""Analyze this specific football match: {home_team} vs {away_team} in {league}.

You must provide REALISTIC and SPECIFIC statistics based on what you know about {home_team} and {away_team}.

Consider:
- {home_team}'s actual playing style, recent form, and scoring patterns
- {away_team}'s actual playing style, defensive record, and away performance  
- Historical results between these specific teams
- The importance and context of this {league} match

Do NOT use generic 55%/25%/45% values. Use your actual knowledge of these teams.

For example:
- A Champions League match between top teams should have higher over2.5 probability
- A lower league match between defensive teams should have lower probabilities
- Home advantage matters differently for different teams

Respond ONLY with valid JSON, no other text:

{{
  "prediction_1x2": "1 or X or 2",
  "over25_pct": <realistic number based on these specific teams>,
  "ht2g_pct": <realistic number based on these specific teams>,
  "btts_pct": <realistic number based on these specific teams>,
  "predicted_score": "specific score prediction",
  "confidence": "Düşük or Orta or Yüksek or Çok Yüksek",
  "reasoning": [
    "specific fact about {home_team}",
    "specific fact about {away_team}",
    "specific H2H or context fact"
  ],
  "h2h_summary": "specific H2H history between {home_team} and {away_team}"
}}"""

    raw_text = None
    try:
        if GROQ_API_KEY:
            raw_text = call_groq(prompt)
        elif ANTHROPIC_API_KEY:
            raw_text = call_anthropic(prompt)
        else:
            return mock_analysis(fixture)

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
        logger.error(f"AI analysis failed: {e}, raw: {raw_text}")
        return mock_analysis(fixture)

def call_anthropic(prompt):
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
    return response.json()['content'][0]['text'].strip()

def mock_analysis(fixture):
    home_team = fixture['teams']['home']['name']
    away_team = fixture['teams']['away']['name']
    return {
        'analysis_date': datetime.now().strftime('%Y-%m-%d'),
        'fixture_id': fixture['fixture']['id'],
        'home_team': home_team,
        'away_team': away_team,
        'league': fixture['league']['name'],
        'match_time': fixture['fixture']['date'],
        'prediction_1x2': '1',
        'over25_pct': 55,
        'ht2g_pct': 25,
        'btts_pct': 45,
        'predicted_score': '2-1',
        'confidence': 'Orta',
        'reasoning': json.dumps([
            f"{home_team} ev sahibi avantajına sahip",
            "İstatistiksel model tahmini",
            "Genel form değerlendirmesi"
        ], ensure_ascii=False),
        'h2h_summary': 'Genel istatistiklere göre tahmin',
        'home_form': 'N/A',
        'away_form': 'N/A',
        'home_goals_avg': 0,
        'away_goals_avg': 0,
    }
