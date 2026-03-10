import requests
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# RapidAPI - bugünkü maçlar için
RAPIDAPI_KEY = os.environ.get('FOOTBALL_API_KEY', '')
RAPIDAPI_BASE = 'https://free-api-live-football-data.p.rapidapi.com'
RAPIDAPI_HEADERS = {
    'x-rapidapi-key': RAPIDAPI_KEY,
    'x-rapidapi-host': 'free-api-live-football-data.p.rapidapi.com'
}

# API-Football - istatistikler için
API_FOOTBALL_KEY = os.environ.get('API_FOOTBALL_KEY', '')
API_FOOTBALL_BASE = 'https://v3.football.api-sports.io'
API_FOOTBALL_HEADERS = {
    'x-apisports-key': API_FOOTBALL_KEY
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

def _get_api_football(endpoint, params={}):
    if not API_FOOTBALL_KEY:
        return None
    try:
        resp = requests.get(f"{API_FOOTBALL_BASE}/{endpoint}", headers=API_FOOTBALL_HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        # Kalan istek sayısını logla
        remaining = resp.headers.get('x-ratelimit-requests-remaining', '?')
        logger.info(f"API-Football remaining requests: {remaining}")
        return data
    except Exception as e:
        logger.error(f"API-Football request failed: {e}")
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
            cancelled = m.get('cancelled', False)
            finished = m.get('finished', False)
            if cancelled or finished:
                continue

            home_name = m.get('home', {}).get('name') or m.get('home', {}).get('longName', '?')
            away_name = m.get('away', {}).get('name') or m.get('away', {}).get('longName', '?')
            league_name = m.get('tournamentStage', 'Bilinmeyen Lig')

            fixtures.append({
                'fixture': {
                    'id': m.get('id', 0),
                    'date': match_time
                },
                'league': {
                    'id': m.get('leagueId', 0),
                    'name': league_name
                },
                'teams': {
                    'home': {
                        'id': m.get('home', {}).get('id', 0),
                        'name': home_name
                    },
                    'away': {
                        'id': m.get('away', {}).get('id', 0),
                        'name': away_name
                    }
                },
                'goals': {'home': None, 'away': None}
            })
        logger.info(f"Filtered to {len(fixtures)} upcoming fixtures today")
        return fixtures
    except Exception as e:
        logger.error(f"Error parsing fixtures: {e}")
        return []

def search_team(team_name):
    """Takım adından API-Football team ID bul"""
    result = _get_api_football('teams', {'search': team_name})
    if not result or not result.get('response'):
        return None
    teams = result['response']
    if teams:
        return teams[0]['team']['id']
    return None

def get_team_statistics(team_id, league_id=None, season=2024):
    """Takım istatistiklerini getir"""
    if not team_id:
        return None
    
    # Önce büyük liglerde ara
    leagues_to_try = [league_id] if league_id else [39, 140, 135, 78, 61, 2, 203, 197]
    
    for league in leagues_to_try:
        if not league:
            continue
        result = _get_api_football('teams/statistics', {
            'team': team_id,
            'league': league,
            'season': season
        })
        if result and result.get('response') and result['response'].get('fixtures'):
            return result['response']
    return None

def get_h2h(team1_name, team2_name, last=5):
    """İki takım arasındaki H2H maçları"""
    team1_id = search_team(team1_name)
    team2_id = search_team(team2_name)
    
    if not team1_id or not team2_id:
        logger.warning(f"Could not find team IDs for H2H: {team1_name} vs {team2_name}")
        return []
    
    result = _get_api_football('fixtures/headtohead', {
        'h2h': f"{team1_id}-{team2_id}",
        'last': last
    })
    
    if not result or not result.get('response'):
        return []
    
    return result['response']

def get_team_last_matches(team_name, last=5):
    """Takımın son maçları"""
    team_id = search_team(team_name)
    if not team_id:
        return []
    
    result = _get_api_football('fixtures', {
        'team': team_id,
        'last': last,
        'status': 'FT'
    })
    
    if not result or not result.get('response'):
        return []
    
    return result['response']

def get_standings(league_id, season=2024):
    result = _get_api_football('standings', {
        'league': league_id,
        'season': season
    })
    if not result or not result.get('response'):
        return []
    return result['response']
