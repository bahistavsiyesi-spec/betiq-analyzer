import requests
import os
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)

RAPIDAPI_KEY = os.environ.get('FOOTBALL_API_KEY', '')
RAPIDAPI_BASE = 'https://free-api-live-football-data.p.rapidapi.com'
RAPIDAPI_HEADERS = {
    'x-rapidapi-key': RAPIDAPI_KEY,
    'x-rapidapi-host': 'free-api-live-football-data.p.rapidapi.com'
}

FOOTBALL_DATA_KEY = os.environ.get('FOOTBALL_DATA_KEY', '')
FOOTBALL_DATA_BASE = 'https://api.football-data.org/v4'
FOOTBALL_DATA_HEADERS = {
    'X-Auth-Token': FOOTBALL_DATA_KEY
}

# Sadece bilinen büyük takımlar - API'ye gitmeden direkt ID
KNOWN_TEAM_IDS = {
    'galatasaray': 2290,
    'fenerbahce': 1007,
    'besiktas': 1009,
    'trabzonspor': 1012,
    'liverpool': 64,
    'manchester city': 65,
    'manchester united': 66,
    'chelsea': 61,
    'arsenal': 57,
    'tottenham': 73,
    'newcastle': 67,
    'aston villa': 58,
    'barcelona': 81,
    'real madrid': 86,
    'atletico madrid': 78,
    'sevilla': 559,
    'valencia': 94,
    'villarreal': 533,
    'athletic club': 77,
    'real sociedad': 92,
    'bayern munich': 5,
    'borussia dortmund': 4,
    'rb leipzig': 721,
    'bayer leverkusen': 3,
    'juventus': 109,
    'inter milan': 108,
    'ac milan': 98,
    'napoli': 113,
    'roma': 100,
    'lazio': 110,
    'atalanta': 102,
    'paris saint-germain': 524,
    'psg': 524,
    'marseille': 516,
    'lyon': 523,
    'monaco': 548,
    'ajax': 678,
    'porto': 503,
    'benfica': 1903,
    'sporting cp': 498,
    'celtic': 1007,
}

def _get_rapidapi(endpoint, params={}):
    if not RAPIDAPI_KEY:
        return None
    try:
        resp = requests.get(f"{RAPIDAPI_BASE}/{endpoint}", headers=RAPIDAPI_HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"RapidAPI request failed: {e}")
        return None

def _get_football_data(endpoint, params={}):
    if not FOOTBALL_DATA_KEY:
        return None
    try:
        resp = requests.get(f"{FOOTBALL_DATA_BASE}/{endpoint}", headers=FOOTBALL_DATA_HEADERS, params=params, timeout=15)
        if resp.status_code == 429:
            logger.warning("Football-Data rate limit hit, skipping")
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Football-Data request failed: {e}")
        return None

def get_todays_fixtures():
    today = datetime.now().strftime('%Y%m%d')
    today_str = datetime.now().strftime('%Y-%m-%d')
    result = _get_rapidapi('football-get-matches-by-date', {'date': today})
    if not result:
        return []
    try:
        matches = result.get('response', {}).get('matches', [])
        logger.info(f"Found {len(matches)} matches from API")
        fixtures = []
        for m in matches:
            match_time = m.get('status', {}).get('utcTime', '')
            if today_str not in match_time:
                continue
            if m.get('cancelled') or m.get('finished'):
                continue
            home_name = m.get('home', {}).get('name') or m.get('home', {}).get('longName', '?')
            away_name = m.get('away', {}).get('name') or m.get('away', {}).get('longName', '?')
            fixtures.append({
                'fixture': {'id': m.get('id', 0), 'date': match_time},
                'league': {'id': m.get('leagueId', 0), 'name': m.get('tournamentStage', 'Bilinmeyen Lig')},
                'teams': {
                    'home': {'id': m.get('home', {}).get('id', 0), 'name': home_name},
                    'away': {'id': m.get('away', {}).get('id', 0), 'name': away_name}
                },
                'goals': {'home': None, 'away': None}
            })
        logger.info(f"Filtered to {len(fixtures)} upcoming fixtures today")
        return fixtures
    except Exception as e:
        logger.error(f"Error parsing fixtures: {e}")
        return []

def search_team(team_name):
    """Sadece cache'den bul, API'ye gitme"""
    team_lower = team_name.lower().strip()
    for key, team_id in KNOWN_TEAM_IDS.items():
        if key in team_lower or team_lower in key:
            logger.info(f"Found cached ID for {team_name}: {team_id}")
            return team_id
    logger.info(f"No cached ID for {team_name}, skipping stats")
    return None

def get_team_last_matches(team_name, last=5):
    """Sadece bilinen takımlar için istatistik çek"""
    team_id = search_team(team_name)
    if not team_id:
        return []

    result = _get_football_data(f'teams/{team_id}/matches', {
        'status': 'FINISHED',
        'limit': last
    })

    if not result or not result.get('matches'):
        return []

    converted = []
    for m in result['matches'][-last:]:
        try:
            converted.append({
                'teams': {
                    'home': {'name': m['homeTeam']['name'], 'id': m['homeTeam']['id']},
                    'away': {'name': m['awayTeam']['name'], 'id': m['awayTeam']['id']}
                },
                'goals': {
                    'home': m['score']['fullTime']['home'],
                    'away': m['score']['fullTime']['away']
                }
            })
        except:
            continue

    logger.info(f"Got {len(converted)} matches for {team_name}")
    return converted

def get_h2h(team1_name, team2_name, last=5):
    """H2H - sadece bilinen takımlar için"""
    team1_id = search_team(team1_name)
    if not team1_id:
        return []

    result = _get_football_data(f'teams/{team1_id}/matches', {
        'status': 'FINISHED',
        'limit': 20
    })

    if not result or not result.get('matches'):
        return []

    h2h_matches = []
    team2_lower = team2_name.lower().split()[0]

    for m in result['matches']:
        try:
            home_name = m['homeTeam']['name'].lower()
            away_name = m['awayTeam']['name'].lower()
            if team2_lower in home_name or team2_lower in away_name:
                h2h_matches.append({
                    'teams': {
                        'home': {'name': m['homeTeam']['name'], 'id': m['homeTeam']['id']},
                        'away': {'name': m['awayTeam']['name'], 'id': m['awayTeam']['id']}
                    },
                    'goals': {
                        'home': m['score']['fullTime']['home'],
                        'away': m['score']['fullTime']['away']
                    }
                })
        except:
            continue

    return h2h_matches[:last]

def get_standings(league_code, season=2024):
    result = _get_football_data(f'competitions/{league_code}/standings', {'season': season})
    if not result:
        return []
    return result
