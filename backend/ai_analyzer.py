import os
import json
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

def build_prompt(home_team, away_team, league, match_time,
                 home_form, away_form, home_goals_avg, away_goals_avg,
                 home_conceded_avg, away_conceded_avg, h2h_summary):
    
    h2h_text = ''
    if h2h_summary:
        h2h_text = f"""
H2H (Son {h2h_summary['total']} maç):
- {home_team} galibiyet: {h2h_summary['home_wins']}
- {away_team} galibiyet: {h2h_summary['away_wins']}
- Beraberlik: {h2h_summary['draws']}
- Maç başı ortalama gol: {h2h_summary['avg_goals']}"""

    stats_text = ''
    if home_goals_avg > 0 or away_goals_avg > 0:
        stats_text = f"""
Gerçek İstatistikler (son 5 maç):
- {home_team}: {home_goals_avg} gol atar / {home_conceded_avg} gol yer (ortalama)
- {away_team}: {away_goals_avg} gol atar / {away_conceded_avg} gol yer (ortalama)
- {home_team} form: {home_form if home_form else 'Bilinmiyor'}
- {away_team} form: {away_form if away_form else 'Bilinmiyor'}"""

    return f"""Aşağıdaki futbol maçını analiz et ve SADECE JSON formatında yanıt ver:

Maç: {home_team} vs {away_team}
Lig: {league}
Tarih: {match_time}
{stats_text}
{h2h_text}

Yukarıdaki GERÇEK istatistikleri kullanarak analiz yap. İstatistik yoksa kendi bilginle tahmin et.
Tüm yanıtlar TÜRKÇE olacak.

SADECE şu JSON formatında yanıt ver, başka hiçbir şey yazma:
{{
  "prediction_1x2": "1 veya X veya 2",
  "over25_pct": <gerçekçi sayı 0-100>,
  "ht2g_pct": <gerçekçi sayı 0-100>,
  "btts_pct": <gerçekçi sayı 0-100>,
  "predicted_score": "örn: 2-1",
  "confidence": "Düşük veya Orta veya Yüksek veya Çok Yüksek",
  "reasoning": [
    "{home_team} hakkında istatistiğe dayalı Türkçe bilgi",
    "{away_team} hakkında istatistiğe dayalı Türkçe bilgi",
    "H2H veya genel bağlam Türkçe"
  ],
  "h2h_summary": "H2H özeti Türkçe"
}}"""

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
                    'content': 'Sen profesyonel bir futbol bahis analistisin. Verilen gerçek istatistikleri kullanarak analiz yap. Tüm yanıtlar TÜRKÇE olacak. Her maç için farklı ve gerçekçi tahminler üret.'
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

def call_gemini(prompt):
    # Geçici olarak devre dışı - rate limit sorunu
    raise Exception("Gemini devre dışı")

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

def parse_result(raw_text):
    if '```json' in raw_text:
        raw_text = raw_text.split('```json')[1].split('```')[0].strip()
    elif '```' in raw_text:
        raw_text = raw_text.split('```')[1].split('```')[0].strip()
    return json.loads(raw_text)

def analyze_with_claude(fixture, h2h_data, home_matches, away_matches,
                        home_form='', away_form='',
                        home_goals_avg=0, away_goals_avg=0,
                        home_conceded_avg=0, away_conceded_avg=0,
                        h2h_summary=None):
    
    home_team = fixture['teams']['home']['name']
    away_team = fixture['teams']['away']['name']
    league = fixture['league']['name']
    match_time = fixture['fixture']['date']

    prompt = build_prompt(
        home_team, away_team, league, match_time,
        home_form, away_form,
        home_goals_avg, away_goals_avg,
        home_conceded_avg, away_conceded_avg,
        h2h_summary
    )

    raw_text = None
    result = None

    if GROQ_API_KEY:
        try:
            raw_text = call_groq(prompt)
            result = parse_result(raw_text)
            logger.info(f"Groq OK: {home_team} vs {away_team}")
        except Exception as e:
            logger.error(f"Groq failed: {e}")

    if not result and ANTHROPIC_API_KEY:
        try:
            raw_text = call_anthropic(prompt)
            result = parse_result(raw_text)
        except Exception as e:
            logger.error(f"Anthropic failed: {e}")

    if not result:
        return mock_analysis(fixture, home_form, away_form, home_goals_avg, away_goals_avg)

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
        'home_form': home_form,
        'away_form': away_form,
        'home_goals_avg': home_goals_avg,
        'away_goals_avg': away_goals_avg,
    }

def mock_analysis(fixture, home_form='', away_form='', home_goals_avg=0, away_goals_avg=0):
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
        'home_form': home_form,
        'away_form': away_form,
        'home_goals_avg': home_goals_avg,
        'away_goals_avg': away_goals_avg,
    }
