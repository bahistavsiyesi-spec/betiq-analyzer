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
        return resp.json()
    except Exception as e:
        logger.error(f"API request failed: {e}")
        return None

def get_todays_fixtures():
    today = datetime.now().strftime('%Y%m%d')
    today_str = datetime.now().strftime('%Y-%m-%d')
    result = _get('football-get-matches-by-date', {'date': today})
    if not result:
        return []
    try:
        matches = result.get('response', {}).get('matches', [])
        logger.info(f"Found {len(matches)} matches from API")
        fixtures = []
        for m in matches:
            # Sadece bugünün maçlarını al
            match_time = m.get('status', {}).get('utcTime', '')
            if today_str not in match_time:
                continue
            # Sadece oynanmamış maçları al
            started = m.get('started', False)
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

def get_h2h(team1_id, team2_id, last=5):
    return []

def get_team_last_matches(team_id, last=10):
    return []

def get_standings(league_id, season=2024):
    return []
