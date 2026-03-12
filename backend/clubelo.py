import requests
import logging
import csv
import io
from datetime import datetime

logger = logging.getLogger(__name__)

CLUBELO_BASE = 'http://api.clubelo.com'

def get_team_elo(team_name):
    """Takımın güncel Elo puanını çek"""
    # ClubElo takım adı formatı: boşluk yok, her kelime büyük harf
    formatted = team_name.replace(' ', '').replace('-', '')
    try:
        resp = requests.get(f"{CLUBELO_BASE}/{formatted}", timeout=10)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        if not rows:
            return None
        # En son satır = güncel Elo
        latest = rows[-1]
        return {
            'team': latest.get('Club', team_name),
            'elo': round(float(latest.get('Elo', 0))),
            'rank': latest.get('Rank', '?'),
            'country': latest.get('Country', ''),
            'level': latest.get('Level', ''),
            'from': latest.get('From', ''),
            'to': latest.get('To', ''),
        }
    except Exception as e:
        logger.warning(f"ClubElo error for {team_name}: {e}")
        return None

def get_fixtures_elo():
    """Yaklaşan maçlar ve hesaplanmış olasılıklar"""
    try:
        resp = requests.get(f"{CLUBELO_BASE}/Fixtures", timeout=10)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        return rows
    except Exception as e:
        logger.warning(f"ClubElo fixtures error: {e}")
        return []

def find_match_in_fixtures(home_team, away_team, fixtures=None):
    """Fixtures listesinden bu maçı bul"""
    if fixtures is None:
        fixtures = get_fixtures_elo()
    
    home_lower = home_team.lower().replace(' ', '').replace('-', '')
    away_lower = away_team.lower().replace(' ', '').replace('-', '')

    for f in fixtures:
        fh = f.get('Home', '').lower().replace(' ', '').replace('-', '')
        fa = f.get('Away', '').lower().replace(' ', '').replace('-', '')
        if home_lower in fh or fh in home_lower:
            if away_lower in fa or fa in away_lower:
                try:
                    return {
                        'home_elo': round(float(f.get('Elo Home', 0))),
                        'away_elo': round(float(f.get('Elo Away', 0))),
                        'prob_home': round(float(f.get('ProbHome', 0)) * 100, 1),
                        'prob_draw': round(float(f.get('ProbDraw', 0)) * 100, 1),
                        'prob_away': round(float(f.get('ProbAway', 0)) * 100, 1),
                    }
                except Exception as e:
                    logger.warning(f"ClubElo parse error: {e}")
                    return None
    return None

def get_elo_for_match(home_team, away_team):
    """
    Bir maç için Elo verisi getir.
    Önce fixtures'da ara (olasılıklar hazır gelir),
    bulamazsa her takımı ayrı ayrı çek.
    """
    # Önce fixtures'dan dene
    fixtures = get_fixtures_elo()
    match_data = find_match_in_fixtures(home_team, away_team, fixtures)
    if match_data:
        logger.info(f"ClubElo fixtures found: {home_team} vs {away_team}")
        return match_data

    # Bulamazsa ayrı ayrı çek
    home_elo = get_team_elo(home_team)
    away_elo = get_team_elo(away_team)

    if not home_elo and not away_elo:
        return None

    result = {}
    if home_elo:
        result['home_elo'] = home_elo['elo']
        result['home_country'] = home_elo['country']
    if away_elo:
        result['away_elo'] = away_elo['elo']
        result['away_country'] = away_elo['country']

    # Elo farkından olasılık hesapla
    if home_elo and away_elo:
        dr = home_elo['elo'] - away_elo['elo']
        prob_home = round(1 / (10 ** (-dr / 400) + 1) * 100, 1)
        prob_away = round(1 / (10 ** (dr / 400) + 1) * 100, 1)
        prob_draw = round(100 - prob_home - prob_away, 1)
        result['prob_home'] = prob_home
        result['prob_draw'] = max(prob_draw, 0)
        result['prob_away'] = prob_away

    logger.info(f"ClubElo individual: {home_team} {result.get('home_elo','?')} vs {away_team} {result.get('away_elo','?')}")
    return result if result else None
