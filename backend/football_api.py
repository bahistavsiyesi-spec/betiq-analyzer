import requests
import os
import logging
import csv
import io
from datetime import datetime

logger = logging.getLogger(__name__)

FOOTBALL_DATA_KEY = os.environ.get('FOOTBALL_DATA_KEY', '')
FOOTBALL_DATA_BASE = 'https://api.football-data.org/v4'
FOOTBALL_DATA_HEADERS = {
    'X-Auth-Token': FOOTBALL_DATA_KEY
}

KNOWN_TEAM_IDS = {
    'galatasaray': 2290,
    'fenerbahce': 2290,
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
    'celtic': 732,
}

def _get_football_data(endpoint, params={}):
    if not FOOTBALL_DATA_KEY:
        return None
    try:
        resp = requests.get(FOOTBALL_DATA_BASE + '/' + endpoint, headers=FOOTBALL_DATA_HEADERS, params=params, timeout=15)
        if resp.status_code == 429:
            logger.warning('Football-Data rate limit hit, skipping')
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error('Football-Data request failed: ' + str(e))
        return None

def get_todays_fixtures():
    today_str = datetime.now().strftime('%Y-%m-%d')
    try:
        resp = requests.get('http://api.clubelo.com/Fixtures', timeout=10)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        fixtures = []
        for i, row in enumerate(rows):
            if row.get('Date', '') != today_str:
                continue
            home = row.get('Home', '').strip()
            away = row.get('Away', '').strip()
            country = row.get('Country', '').strip()
            if not home or not away:
                continue
            fixtures.append({
                'fixture': {
                    'id': i + 900000,
                    'date': None
                },
                'league': {
                    'id': 0,
                    'name': country if country else 'Bilinmeyen Lig'
                },
                'teams': {
                    'home': {'id': 0, 'name': home},
                    'away': {'id': 0, 'name': away}
                },
                'goals': {'home': None, 'away': None}
            })
        logger.info('ClubElo fixtures today: ' + str(len(fixtures)) + ' matches')
        return fixtures
    except Exception as e:
        logger.error('ClubElo fixtures fetch failed: ' + str(e))
        return []

def search_team(team_name):
    team_lower = team_name.lower().strip()
    for key, team_id in KNOWN_TEAM_IDS.items():
        if key in team_lower or team_lower in key:
            logger.info('Found cached ID for ' + team_name + ': ' + str(team_id))
            return team_id
    logger.info('No cached ID for ' + team_name + ', skipping stats')
    return None

def get_team_last_matches(team_name, last=5):
    team_id = search_team(team_name)
    if not team_id:
        return []

    result = _get_football_data('teams/' + str(team_id) + '/matches', {
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

    logger.info('Got ' + str(len(converted)) + ' matches for ' + team_name)
    return converted

def get_h2h(team1_name, team2_name, last=5):
    team1_id = search_team(team1_name)
    if not team1_id:
        return []

    result = _get_football_data('teams/' + str(team1_id) + '/matches', {
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
    result = _get_football_data('competitions/' + str(league_code) + '/standings', {'season': season})
    if not result:
        return []
    return result
