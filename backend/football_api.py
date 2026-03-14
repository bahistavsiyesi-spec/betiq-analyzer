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

# OpenLigaDB - Alman ligleri (ücretsiz, limitsiz)
OPENLIGA_BASE = 'https://api.openligadb.de'
OPENLIGA_LEAGUES = {
    'bl1': {'name': 'Bundesliga', 'season': '2024'},
    'bl2': {'name': '2. Bundesliga', 'season': '2024'},
    'bl3': {'name': '3. Liga', 'season': '2024'},
}

# Alman lig takımları → OpenLigaDB ID eşleştirmesi
OPENLIGA_TEAM_IDS = {
    # Bundesliga
    'fc bayern': 40, 'bayern munich': 40, 'bayern münchen': 40, 'bayernmunich': 40,
    'borussia dortmund': 7, 'dortmund': 7,
    'bayer leverkusen': 9, 'leverkusen': 9,
    'rb leipzig': 54, 'leipzig': 54,
    'eintracht frankfurt': 91, 'frankfurt': 91,
    'vfb stuttgart': 16, 'stuttgart': 16,
    'sc freiburg': 112, 'freiburg': 112,
    'tsg hoffenheim': 3, 'hoffenheim': 3,
    'werder bremen': 86, 'bremen': 86,
    'vfl wolfsburg': 24, 'wolfsburg': 24,
    'borussia mönchengladbach': 87, 'gladbach': 87, 'monchengladbach': 87,
    'fc augsburg': 167, 'augsburg': 167,
    'union berlin': 80, '1. fc union berlin': 80,
    'vfl bochum': 44, 'bochum': 44,
    'fsv mainz': 6, 'mainz': 6,
    'fc st. pauli': 65, 'st pauli': 65, 'st. pauli': 65,
    'holstein kiel': 14, 'kiel': 14,
    # 2. Bundesliga
    'hamburger sv': 100, 'hamburg': 100, 'hsv': 100,
    'hannover 96': 55, 'hannover': 55,
    'karlsruher sc': 8, 'karlsruhe': 8,
    'fc schalke': 5, 'schalke': 5,
    'sv darmstadt': 127, 'darmstadt': 127,
    '1. fc köln': 27, 'köln': 27, 'koln': 27, 'cologne': 27,
    'hertha bsc': 28, 'hertha': 28,
    'fortuna düsseldorf': 74, 'düsseldorf': 74, 'dusseldorf': 74,
    'fc nürnberg': 4, 'nürnberg': 4, 'nurnberg': 4,
    'greuther fürth': 79, 'fürth': 79, 'furth': 79,
    'vfl osnabrück': 120, 'osnabrück': 120,
    'eintracht braunschweig': 97, 'braunschweig': 97,
    'ssv ulm': 158, 'ulm': 158,
    'preußen münster': 21, 'münster': 21,
}

# ClubElo → OpenLigaDB isim eşleştirmesi (ClubElo bazen farklı isim kullanır)
CLUBELO_TO_OPENLIGA = {
    'Bayern Munich': 'fc bayern',
    'Dortmund': 'borussia dortmund',
    'Leverkusen': 'bayer leverkusen',
    'Leipzig': 'rb leipzig',
    'Frankfurt': 'eintracht frankfurt',
    'Stuttgart': 'vfb stuttgart',
    'Freiburg': 'sc freiburg',
    'Hoffenheim': 'tsg hoffenheim',
    'Bremen': 'werder bremen',
    'Wolfsburg': 'vfl wolfsburg',
    'Gladbach': 'borussia mönchengladbach',
    'Augsburg': 'fc augsburg',
    'Union Berlin': 'union berlin',
    'Bochum': 'vfl bochum',
    'Mainz': 'fsv mainz',
    'St. Pauli': 'fc st. pauli',
    'Kiel': 'holstein kiel',
    'Hamburg': 'hamburger sv',
    'Hannover': 'hannover 96',
    'Karlsruhe': 'karlsruher sc',
    'Schalke': 'fc schalke',
    'Darmstadt': 'sv darmstadt',
    'Koln': 'fc köln', 'Köln': 'fc köln',
    'Hertha': 'hertha bsc',
    'Düsseldorf': 'fortuna düsseldorf', 'Dusseldorf': 'fortuna düsseldorf',
    'Nürnberg': 'fc nürnberg', 'Nurnberg': 'fc nürnberg',
    'Fürth': 'greuther fürth', 'Furth': 'greuther fürth',
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


# ─── OpenLigaDB Fonksiyonları ─────────────────────────────────────────────────

def _find_openliga_team_id(team_name):
    """Takım adından OpenLigaDB ID'sini bul."""
    # Önce ClubElo→OpenLigaDB eşleştirme tablosuna bak
    mapped = CLUBELO_TO_OPENLIGA.get(team_name)
    if mapped:
        team_name_lookup = mapped
    else:
        team_name_lookup = team_name.lower().strip()

    for key, team_id in OPENLIGA_TEAM_IDS.items():
        if key in team_name_lookup or team_name_lookup in key:
            logger.info('OpenLigaDB ID found for ' + team_name + ': ' + str(team_id))
            return team_id

    logger.info('No OpenLigaDB ID for ' + team_name)
    return None


def _get_openliga_season_matches(league_short, season):
    """OpenLigaDB'den tüm sezon maçlarını çek (cache'lenmiş gibi tek seferde)."""
    try:
        url = OPENLIGA_BASE + '/getmatchdata/' + league_short + '/' + season
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning('OpenLigaDB fetch failed for ' + league_short + ': ' + str(e))
        return []


def get_openliga_team_last_matches(team_name, last=5):
    """Alman ligi takımı için son maçları OpenLigaDB'den çek."""
    team_id = _find_openliga_team_id(team_name)
    if not team_id:
        return []

    results = []
    for league_short, info in OPENLIGA_LEAGUES.items():
        if results:
            break
        matches = _get_openliga_season_matches(league_short, info['season'])
        team_matches = []
        for m in matches:
            try:
                t1_id = m.get('team1', {}).get('teamId')
                t2_id = m.get('team2', {}).get('teamId')
                if team_id not in (t1_id, t2_id):
                    continue
                # Sadece biten maçlar
                results_list = m.get('matchResults', [])
                final = next((r for r in results_list if r.get('resultTypeID') == 2), None)
                if not final:
                    continue
                team_matches.append({
                    'teams': {
                        'home': {'name': m['team1']['teamName'], 'id': t1_id},
                        'away': {'name': m['team2']['teamName'], 'id': t2_id}
                    },
                    'goals': {
                        'home': final['pointsTeam1'],
                        'away': final['pointsTeam2']
                    }
                })
            except Exception:
                continue
        if team_matches:
            results = team_matches[-last:]
            logger.info('OpenLigaDB: ' + str(len(results)) + ' matches for ' + team_name)

    return results


def get_openliga_h2h(team1_name, team2_name, last=5):
    """İki Alman ligi takımı arasındaki H2H maçlarını OpenLigaDB'den çek."""
    team1_id = _find_openliga_team_id(team1_name)
    team2_id = _find_openliga_team_id(team2_name)
    if not team1_id or not team2_id:
        return []

    h2h = []
    for league_short, info in OPENLIGA_LEAGUES.items():
        matches = _get_openliga_season_matches(league_short, info['season'])
        for m in matches:
            try:
                t1_id = m.get('team1', {}).get('teamId')
                t2_id = m.get('team2', {}).get('teamId')
                if set([t1_id, t2_id]) != set([team1_id, team2_id]):
                    continue
                results_list = m.get('matchResults', [])
                final = next((r for r in results_list if r.get('resultTypeID') == 2), None)
                if not final:
                    continue
                h2h.append({
                    'teams': {
                        'home': {'name': m['team1']['teamName'], 'id': t1_id},
                        'away': {'name': m['team2']['teamName'], 'id': t2_id}
                    },
                    'goals': {
                        'home': final['pointsTeam1'],
                        'away': final['pointsTeam2']
                    }
                })
            except Exception:
                continue

    return h2h[-last:]


def is_german_team(team_name):
    """Takımın Alman ligi takımı olup olmadığını kontrol et."""
    mapped = CLUBELO_TO_OPENLIGA.get(team_name)
    lookup = (mapped or team_name).lower().strip()
    for key in OPENLIGA_TEAM_IDS:
        if key in lookup or lookup in key:
            return True
    return False


# ─── Football-Data API Fonksiyonları ─────────────────────────────────────────

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
    """
    Önce Alman ligi mi diye kontrol et → OpenLigaDB'den çek.
    Değilse Football-Data'dan çekmeyi dene.
    """
    # Alman ligi kontrolü
    if is_german_team(team_name):
        matches = get_openliga_team_last_matches(team_name, last)
        if matches:
            return matches

    # Football-Data fallback
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
    """
    Önce Alman ligi mi diye kontrol et → OpenLigaDB'den çek.
    Değilse Football-Data'dan çekmeyi dene.
    """
    # Alman ligi kontrolü
    if is_german_team(team1_name) or is_german_team(team2_name):
        h2h = get_openliga_h2h(team1_name, team2_name, last)
        if h2h:
            return h2h

    # Football-Data fallback
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
