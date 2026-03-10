import requests
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

API_KEY = os.environ.get('FOOTBALL_API_KEY', '')
BASE_URL = 'https://free-api-live-football-data.p.rapidapi.com'

HEADERS = {
    'x-rapidapi-key': API_KEY,
    'x-rapidapi-host': 'free-api-live-football-data.p.rapidapi.com'
}

def _get(endpoint, params={}):
    if not API_KEY:
        logger.warning("No API key set")
        return None
    try:
        resp = requests.get(f"{BASE_URL}/{endpoint}", headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get('response', data)
    except Exception as e:
        logger.error(f"API request failed: {e}")
        return None

def get_todays_fixtures():
    today = datetime.now().strftime('%Y%m%d')
    result = _get('football-get-matches-by-date', {'date': today})
    if not result:
        return []
    try:
        matches = result.get('matches', [])
        fixtures = []
        for m in matches:
            fixtures.append({
                'fixture': {
                    'id': m.get('id', 0),
                    'date': m.get('date', '') or m.get('time', '')
                },
                'league': {
                    'id': 0,
                    'name': m.get('competition', {}).get('name', 'Bilinmeyen Lig')
                },
                'teams': {
                    'home': {
                        'id': m.get('homeTeam', {}).get('id', 0),
                        'name': m.get('homeTeam', {}).get('name', '?')
                    },
                    'away': {
                        'id': m.get('awayTeam', {}).get('id', 0),
                        'name': m.get('awayTeam', {}).get('name', '?')
                    }
                },
                'goals': {'home': None, 'away': None}
            })
        return fixtures[:20]
    except Exception as e:
        logger.error(f"Error parsing fixtures: {e}")
        return []

def get_h2h(team1_id, team2_id, last=5):
    return []

def get_team_last_matches(team_id, last=10):
    return []

def get_standings(league_id, season=2024):
    return []
