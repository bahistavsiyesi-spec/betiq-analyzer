import os
import json
import logging
import requests
from datetime import datetime

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

def extract_form(matches, team_id):
    return 'N/A'

def calc_goals_stats(matches, team_id):
    return 0, 0

def calc_home_away_stats(matches, team_id):
    return {'W': 0, 'D': 0, 'L': 0}, {'W': 0, 'D': 0, 'L': 0}

def build_prompt(home_team, away_team, league, match_time):
    return f"""Aşağıdaki maçı analiz et ve SADECE JSON formatında yanıt ver, başka hiçbir şey yazma:

Maç: {home_team} - {away_team}
Lig: {league}
Tarih: {match_time}

Bu maç için gerçekçi istatistikler üret. {home_team} ve {away_team} hakkında bildiklerini kullan.
Şampiyonlar Ligi veya büyük lig maçıysa gol oranlarını yüksek tut.
Alt lig veya bilinmeyen takımsa daha düşük ve temkinli tahmin yap.
Tüm reasoning alanları TÜRKÇE olacak.

SADECE şu JSON formatında yanıt ver:
{{
  "prediction_1x2": "1 veya X veya 2",
  "over25_pct": <bu maça özel gerçekçi sayı 0-100>,
  "ht2g_pct": <bu maça özel gerçekçi sayı 0-100>,
  "btts_pct": <bu maça özel gerçekçi sayı 0-100>,
  "predicted_score": "tahmin edilen skor örn: 2-1",
  "confidence": "Düşük veya Orta veya Yüksek veya Çok Yüksek",
  "reasoning": [
    "{home_team} hakkında spesifik Türkçe bilgi",
    "{away_team} hakkında spesifik Türkçe bilgi",
    "Bu maça özel Türkçe H2H veya bağlam bilgisi"
  ],
  "h2h_summary": "{home_team} ile {away_team} arasındaki tarihsel H2H özeti Türkçe"
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
                    'content': 'Sen profesyonel bir futbol bahis analistisin. Her maç için GERÇEKÇI ve BİRBİRİNDEN FARKLI istatistikler üretmelisin. Tüm yanıtlar TÜRKÇE olacak. Hiçbir zaman iki farklı maç için aynı yüzdeleri kullanma.'
                },
                {'role': 'user', 'content': prompt}
            ],
            'max_tokens': 1000,
            'temperature': 0.8
        },
        timeout=30
    )
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content'].strip()

def call_gemini(prompt):
    response = requests.post(
        f'https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}',
        headers={'Content-Type': 'application/json'},
        json={
            'contents': [{'parts': [{'text': prompt}]}],
            'generationConfig': {
                'temperature': 0.8,
                'maxOutputTokens': 1000,
            }
        },
        timeout=30
    )
    response.raise_for_status()
    return response.json()['candidates'][0]['content']['parts'][0]['text'].strip()

def parse_result(raw_text):
    if '```json' in raw_text:
        raw_text = raw_text.split('```json')[1].split('```')[0].strip()
    elif '```' in raw_text:
        raw_text = raw_text.split('```')[1].split('```')[0].strip()
    return json.loads(raw_text)

def merge_results(r1, r2):
    """İki AI sonucunu birleştir"""
    # Yüzdelerin ortalaması
    over25 = (float(r1.get('over25_pct', 50)) + float(r2.get('over25_pct', 50))) / 2
    ht2g = (float(r1.get('ht2g_pct', 30)) + float(r2.get('ht2g_pct', 30))) / 2
    btts = (float(r1.get('btts_pct', 40)) + float(r2.get('btts_pct', 40))) / 2

    # Tahmin oylama
    pred1 = r1.get('prediction_1x2', '1')
    pred2 = r2.get('prediction_1x2', '1')

    if pred1 == pred2:
        final_pred = pred1
        # Skor ortalaması
        try:
            s1 = r1.get('predicted_score', '1-1').split('-')
            s2 = r2.get('predicted_score', '1-1').split('-')
            home_avg = round((int(s1[0]) + int(s2[0])) / 2)
            away_avg = round((int(s1[1]) + int(s2[1])) / 2)
            final_score = f"{home_avg}-{away_avg}"
        except:
            final_score = r1.get('predicted_score', '1-1')

        # Güven seviyeleri
        conf_map = {'Düşük': 1, 'Orta': 2, 'Yüksek': 3, 'Çok Yüksek': 4}
        conf_reverse = {1: 'Düşük', 2: 'Orta', 3: 'Yüksek', 4: 'Çok Yüksek'}
        c1 = conf_map.get(r1.get('confidence', 'Orta'), 2)
        c2 = conf_map.get(r2.get('confidence', 'Orta'), 2)
        final_conf = conf_reverse.get(round((c1 + c2) / 2), 'Orta')
    else:
        # İki AI çelişiyor → güven düşük
        final_pred = pred1  # Groq'u önceliklendir
        final_score = '?-?'
        final_conf = 'Düşük'

    # Her iki AI'dan reasoning al
    r1_reasoning = r1.get('reasoning', [])
    r2_reasoning = r2.get('reasoning', [])
    combined_reasoning = []
    if r1_reasoning:
        combined_reasoning.append(f"🤖 Groq: {r1_reasoning[0]}")
    if r2_reasoning:
        combined_reasoning.append(f"🧠 Gemini: {r2_reasoning[0]}")
    if r1_reasoning and len(r1_reasoning) > 1:
        combined_reasoning.append(r1_reasoning[1])

    return {
        'prediction_1x2': final_pred,
        'over25_pct': round(over25, 1),
        'ht2g_pct': round(ht2g, 1),
        'btts_pct': round(btts, 1),
        'predicted_score': final_score,
        'confidence': final_conf,
        'reasoning': combined_reasoning,
        'h2h_summary': r1.get('h2h_summary', '') or r2.get('h2h_summary', ''),
        'ai_agreement': pred1 == pred2
    }

def analyze_with_claude(fixture, h2h_data, home_matches, away_matches):
    home_team = fixture['teams']['home']['name']
    away_team = fixture['teams']['away']['name']
    league = fixture['league']['name']
    match_time = fixture['fixture']['date']

    prompt = build_prompt(home_team, away_team, league, match_time)

    groq_result = None
    gemini_result = None

    # Groq analizi
    if GROQ_API_KEY:
        try:
            raw = call_groq(prompt)
            groq_result = parse_result(raw)
            logger.info(f"Groq OK: {home_team} vs {away_team}")
        except Exception as e:
            logger.error(f"Groq failed: {e}")

    # Gemini analizi
    if GEMINI_API_KEY:
        try:
            raw = call_gemini(prompt)
            gemini_result = parse_result(raw)
            logger.info(f"Gemini OK: {home_team} vs {away_team}")
        except Exception as e:
            logger.error(f"Gemini failed: {e}")

    # Sonuçları birleştir
    if groq_result and gemini_result:
        result = merge_results(groq_result, gemini_result)
        logger.info(f"Dual AI merge: agreement={result['ai_agreement']}")
    elif groq_result:
        result = groq_result
        result['reasoning'] = [f"🤖 Groq: {r}" for r in result.get('reasoning', [])]
    elif gemini_result:
        result = gemini_result
        result['reasoning'] = [f"🧠 Gemini: {r}" for r in result.get('reasoning', [])]
    else:
        return mock_analysis(fixture)

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
