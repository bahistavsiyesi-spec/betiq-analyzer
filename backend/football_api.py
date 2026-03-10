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
        logger.info(f"API response keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
        return data
    except Exception as e:
        logger.error(f"API request failed: {e}")
        return None

def get_todays_fixtures():
    today = datetime.now().strftime('%Y%m%d')
    result = _get('football-get-matches-by-date', {'date': today})
    if not result:
        return []
    try:
        logger.info(f"Full response sample: {str(result)[:500]}")
        # Farklı formatlara göre dene
        matches = []
        if isinstance(result, dict):
            for key in ['matches', 'data', 'response', 'fixtures', 'events']:
                if key in result:
                    matches = result[key]
                    logger.info(f"Found matches under key: {key}, count: {len(matches)}")
                    break
        elif isinstance(result, list):
            matches = result

        if not matches:
            logger.warning(f"No matches found in response: {list(result.keys()) if isinstance(result, dict) else type(result)}")
            return []

        fixtures = []
        for m in matches[:20]:
            logger.info(f"Match sample: {str(m)[:200]}")
            # Farklı alan isimlerine göre dene
            home_name = (
                m.get('homeTeam', {}).get('name') or
                m.get('home_team', {}).get('name') or
                m.get('home', {}).get('name') or
                m.get('localTeam', {}).get('name') or
                m.get('team_home') or
                '?'
            )
            away_name = (
                m.get('awayTeam', {}).get('name') or
                m.get('away_team', {}).get('name') or
                m.get('away', {}).get('name') or
                m.get('visitorTeam', {}).get('name') or
                m.get('team_away') or
                '?'
            )
            league_name = (
                m.get('competition', {}).get('name') or
                m.get('league', {}).get('name') or
                m.get('tournament', {}).get('name') or
                m.get('league_name') or
                'Bilinmeyen Lig'
            )
            match_time = (
                m.get('date') or
                m.get('time') or
                m.get('datetime') or
                m.get('kickoff') or
                ''
            )
            fixtures.append({
                'fixture': {
                    'id': m.get('id', 0),
                    'date': match_time
                },
                'league': {
                    'id': 0,
                    'name': league_name
                },
                'teams': {
                    'home': {
                        'id': m.get('homeTeam', {}).get('id', 0) or m.get('home_team', {}).get('id', 0) or 0,
                        'name': home_name
                    },
                    'away': {
                        'id': m.get('awayTeam', {}).get('id', 0) or m.get('away_team', {}).get('id', 0) or 0,
                        'name': away_name
                    }
                },
                'goals': {'home': None, 'away': None}
            })
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
