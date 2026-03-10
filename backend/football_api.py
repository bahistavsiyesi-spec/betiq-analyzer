import requests
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

API_KEY = os.environ.get('FOOTBALL_API_KEY', '')
BASE_URL = 'https://v3.football.api-sports.io'

HEADERS = {
    'x-apisports-key': API_KEY
}

PRIORITY_LEAGUES = [
    39,   # Premier League
    140,  # La Liga
    135,  # Serie A
    78,   # Bundesliga
    61,   # Ligue 1
    2,    # Champions League
    3,    # Europa League
    203,  # Süper Lig
    94,   # Primeira Liga
    88,   # Eredivisie
]

def _get(endpoint, params={}):
    if not API_KEY:
        logger.warning("No API key set")
        return None
    try:
        resp = requests.get(f"{BASE_URL}/{endpoint}", headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        if data.get('errors'):
            logger.error(f"API error: {data['errors']}")
            return None
        return data.get('response', [])
    except Exception as e:
        logger.error(f"API request failed: {e}")
        return None

def get_todays_fixtures():
    today = datetime.now().strftime('%Y-%m-%d')
    fixtures = _get('fixtures', {'date': today, 'timezone': 'Europe/Istanbul'})
    if not fixtures:
        return []
    priority = [f for f in fixtures if f['league']['id'] in PRIORITY_LEAGUES]
    other = [f for f in fixtures if f['league']['id'] not in PRIORITY_LEAGUES]
    return priority + other

def get_h2h(team1_id, team2_id, last=5):
    results = _get('fixtures/headtohead', {
        'h2h': f"{team1_id}-{team2_id}",
        'last': last,
        'status': 'FT'
    })
    return results or []

def get_team_last_matches(team_id, last=10):
    results = _get('fixtures', {
        'team': team_id,
        'last': last,
        'status': 'FT'
    })
    return results or []

def get_standings(league_id, season=None):
    if not season:
        season = datetime.now().year
    results = _get('standings', {'league': league_id, 'season': season})
    return results or []
