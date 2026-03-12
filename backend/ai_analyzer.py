import os
import json
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

ANALYSIS_MODE = os.environ.get('ANALYSIS_MODE', 'claude')

def detect_match_importance(league):
    league_lower = league.lower()
    if any(x in league_lower for x in ['champions league', 'şampiyonlar ligi', 'uefa', 'europa league', 'conference']):
        return 'Avrupa kupası maçı — eleme baskısı yüksek, iki takım da temkinli oynayabilir'
    if any(x in league_lower for x in ['cup', 'kupa', 'fa cup', 'copa', 'pokal']):
        return 'Kupa maçı — tek maçlık eleme, beklenmedik sonuçlar olabilir'
    if any(x in league_lower for x in ['friendly', 'hazırlık']):
        return 'Hazırlık maçı — motivasyon düşük olabilir, sonuç güvenilirliği az'
    return 'Lig maçı — puan kaybı istemeyen iki takım'

def build_prompt(home_team, away_team, league, match_time,
                 home_form, away_form, home_goals_avg, away_goals_avg,
                 home_conceded_avg, away_conceded_avg, h2h_summary,
                 home_home_avg=None, away_away_avg=None):

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
        home_venue = f"(evde ort. {home_home_avg} gol atar)" if home_home_avg is not None else ""
        away_venue = f"(deplasmanda ort. {away_away_avg} gol atar)" if away_away_avg is not None else ""
        stats_text = f"""
Gerçek İstatistikler (son 5 maç):
- {home_team}: {home_goals_avg} gol atar {home_venue} / {home_conceded_avg} gol yer (ortalama)
- {away_team}: {away_goals_avg} gol atar {away_venue} / {away_conceded_avg} gol yer (ortalama)
- {home_team} form: {home_form if home_form else 'Bilinmiyor'}
- {away_team} form: {away_form if away_form else 'Bilinmiyor'}"""

    match_importance = detect_match_importance(league)

    return f"""Asagidaki futbol macini analiz et ve SADECE JSON formatinda yanit ver:

Mac: {home_team} vs {away_team}
Lig: {league}
Tarih: {match_time}
Mac Tipi: {match_importance}
{stats_text}
{h2h_text}

Analiz yaparken su faktorleri goz onunde bulundur:
1. Ev sahibi avantaji: {home_team} kendi sahasinda oynadigi icin psikolojik ve fiziksel avantaja sahip
2. Mac onemi: {match_importance}
3. Motivasyon: Kendi bilginle {home_team} ve {away_team} takimlarinin mevcut sezondaki durumunu degerlendir
4. Yukaridaki GERCEK istatistikleri kullan, yoksa kendi bilginle tahmin et
5. Tum yanitlar TURKCE olacak

SADECE su JSON formatinda yanit ver, baska hicbir sey yazma:
{{
  "prediction_1x2": "1 veya X veya 2",
  "over25_pct": 55,
  "ht2g_pct": 30,
  "btts_pct": 45,
  "predicted_score": "2-1",
  "confidence": "Orta",
  "reasoning": [
    "{home_team} hakkinda degerlendirme",
    "{away_team} hakkinda degerlendirme",
    "Mac onemi ve H2H baglamı"
  ],
  "h2h_summary": "H2H ozeti"
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
                    'content': 'Sen profesyonel bir futbol bahis analistisin. Verilen gercek istatistikleri kullanarak analiz yap. Tum yanitlar TURKCE olacak. Her mac icin farkli ve gercekci tahminler uret.'
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
            'system': 'Sen profesyonel bir futbol bahis analistisin. Verilen gercek istatistikleri kullanarak analiz yap. Tum yanitlar TURKCE olacak. Her mac icin farkli ve gercekci tahminler uret.',
            'messages': [{'role': 'user', 'content': prompt}]
        },
        timeout=30
    )
    response.raise_for_status()
    return response.json()['content'][0]['text'].strip()

def call_gemini(prompt):
    response = requests.post(
        f'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}',
        headers={'Content-Type': 'application/json'},
        json={
            'contents': [
                {
                    'parts': [
                        {
                            'text': 'Sen profesyonel bir futbol bahis analistisin. Verilen gercek istatistikleri kullanarak analiz yap. Tum yanitlar TURKCE olacak. Her mac icin farkli ve gercekci tahminler uret. SADECE gecerli JSON dondur, baska hicbir sey yazma.\n\n' + prompt
                        }
                    ]
                }
            ],
            'generationConfig': {
                'maxOutputTokens': 1000,
                'temperature': 0.7,
                'responseMimeType': 'application/json'
            }
        },
        timeout=30
    )
    response.raise_for_status()
    return response.json()['candidates'][0]['content']['parts'][0]['text'].strip()

def parse_result(raw_text):
    raw_text = raw_text.strip()
    if '```json' in raw_text:
        raw_text = raw_text.split('```json')[1].split('```')[0].strip()
    elif '```' in raw_text:
        raw_text = raw_text.split('```')[1].split('```')[0].strip()
    # JSON bloğunu bul
    start = raw_text.find('{')
    end = raw_text.rfind('}')
    if start != -1 and end != -1:
        raw_text = raw_text[start:end+1]
    return json.loads(raw_text)

def merge_results(r1, r2):
    conf_order = ['Düşük', 'Orta', 'Yüksek', 'Çok Yüksek']
    pred = r1.get('prediction_1x2') if r1.get('prediction_1x2') == r2.get('prediction_1x2') else r1.get('prediction_1x2')
    over25 = round((float(r1.get('over25_pct', 50)) + float(r2.get('over25_pct', 50))) / 2)
    ht2g = round((float(r1.get('ht2g_pct', 30)) + float(r2.get('ht2g_pct', 30))) / 2)
    btts = round((float(r1.get('btts_pct', 40)) + float(r2.get('btts_pct', 40))) / 2)
    c1 = conf_order.index(r1.get('confidence', 'Orta')) if r1.get('confidence') in conf_order else 1
    c2 = conf_order.index(r2.get('confidence', 'Orta')) if r2.get('confidence') in conf_order else 1
    confidence = conf_order[min(c1, c2)]
    reasoning = r1.get('reasoning', r2.get('reasoning', []))
    return {
        'prediction_1x2': pred,
        'over25_pct': over25,
        'ht2g_pct': ht2g,
        'btts_pct': btts,
        'predicted_score': r1.get('predicted_score', '?-?'),
        'confidence': confidence,
        'reasoning': reasoning,
        'h2h_summary': r1.get('h2h_summary', '')
    }

def analyze_with_claude(fixture, h2h_data, home_matches, away_matches,
                        home_form='', away_form='',
                        home_goals_avg=0, away_goals_avg=0,
                        home_conceded_avg=0, away_conceded_avg=0,
                        h2h_summary=None):

    home_team = fixture['teams']['home']['name']
    away_team = fixture['teams']['away']['name']
    league = fixture['league']['name']
    match_time = fixture['fixture']['date']

    home_home_avg = None
    away_away_avg = None
    try:
        home_home_goals = [
            m['goals']['home'] for m in home_matches
            if home_team.lower().split()[0] in m['teams']['home']['name'].lower()
            and m['goals']['home'] is not None
        ]
        if home_home_goals:
            home_home_avg = round(sum(home_home_goals) / len(home_home_goals), 1)

        away_away_goals = [
            m['goals']['away'] for m in away_matches
            if away_team.lower().split()[0] in m['teams']['away']['name'].lower()
            and m['goals']['away'] is not None
        ]
        if away_away_goals:
            away_away_avg = round(sum(away_away_goals) / len(away_away_goals), 1)
    except:
        pass

    prompt = build_prompt(
        home_team, away_team, league, match_time,
        home_form, away_form,
        home_goals_avg, away_goals_avg,
        home_conceded_avg, away_conceded_avg,
        h2h_summary,
        home_home_avg, away_away_avg
    )

    result = None
    mode = ANALYSIS_MODE

    if mode == 'claude':
        if ANTHROPIC_API_KEY:
            try:
                raw = call_anthropic(prompt)
                result = parse_result(raw)
                logger.info(f"Claude OK: {home_team} vs {away_team}")
            except Exception as e:
                logger.error(f"Claude failed: {e}")
        if not result and GEMINI_API_KEY:
            try:
                raw = call_gemini(prompt)
                result = parse_result(raw)
                logger.info(f"Gemini (yedek) OK: {home_team} vs {away_team}")
            except Exception as e:
                logger.error(f"Gemini fallback failed: {e}")

    elif mode == 'gemini':
        if GEMINI_API_KEY:
            try:
                raw = call_gemini(prompt)
                result = parse_result(raw)
                logger.info(f"Gemini OK: {home_team} vs {away_team}")
            except Exception as e:
                logger.error(f"Gemini failed: {e}")
        if not result and ANTHROPIC_API_KEY:
            try:
                raw = call_anthropic(prompt)
                result = parse_result(raw)
                logger.info(f"Claude (yedek) OK: {home_team} vs {away_team}")
            except Exception as e:
                logger.error(f"Claude fallback failed: {e}")

    elif mode == 'both':
        r_claude = None
        r_gemini = None
        if ANTHROPIC_API_KEY:
            try:
                raw = call_anthropic(prompt)
                r_claude = parse_result(raw)
                logger.info(f"Claude OK: {home_team} vs {away_team}")
            except Exception as e:
                logger.error(f"Claude failed: {e}")
        if GEMINI_API_KEY:
            try:
                raw = call_gemini(prompt)
                r_gemini = parse_result(raw)
                logger.info(f"Gemini OK: {home_team} vs {away_team}")
            except Exception as e:
                logger.error(f"Gemini failed: {e}")
        if r_claude and r_gemini:
            result = merge_results(r_claude, r_gemini)
            logger.info(f"Claude+Gemini merged: {home_team} vs {away_team}")
        else:
            result = r_claude or r_gemini

    elif mode == 'groq':
        if GROQ_API_KEY:
            try:
                raw = call_groq(prompt)
                result = parse_result(raw)
                logger.info(f"Groq OK: {home_team} vs {away_team}")
            except Exception as e:
                logger.error(f"Groq failed: {e}")

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
