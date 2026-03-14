import requests
import os
import logging
import csv
import io
from datetime import datetime, date

logger = logging.getLogger(__name__)

FOOTBALL_DATA_KEY = os.environ.get('FOOTBALL_DATA_KEY', '')
FOOTBALL_DATA_BASE = 'https://api.football-data.org/v4'
FOOTBALL_DATA_HEADERS = {
    'X-Auth-Token': FOOTBALL_DATA_KEY
}

# ─── Puan durumu cache (günde 1 kez çekilir) ─────────────────────────────────
_standings_cache = {}  # {league_code: {'date': date, 'data': [...]}}

# ─── ClubElo → Düzgün isim tablosu ───────────────────────────────────────────
NAME_FIXES = {
    # Türkiye
    'Bueyueksehir': 'Başakşehir', 'Basaksehir': 'Başakşehir',
    'Besiktas': 'Beşiktaş', 'Fenerbahce': 'Fenerbahçe',
    'Kasimpasa': 'Kasımpaşa', 'Eyupspor': 'Eyüpspor',
    'Goztepe': 'Göztepe', 'Ankaragucu': 'Ankaragücü',
    'Keciorengucu': 'Keçiörengücü', 'Istanbulspor': 'İstanbulspor',
    # Almanya
    'Koeln': 'Köln', 'Nuernberg': 'Nürnberg', 'Fuerth': 'Fürth',
    'Duesseldorf': 'Düsseldorf', 'Muenchen': 'München',
    'Moenchengladbach': 'Mönchengladbach', 'Muenster': 'Münster',
    'Saarbruecken': 'Saarbrücken', 'Osnabrueck': 'Osnabrück',
    # İspanya
    'Cadiz': 'Cádiz', 'Almeria': 'Almería', 'Malaga': 'Málaga',
    'Leganes': 'Leganés', 'Cordoba': 'Córdoba',
    'Atletico': 'Atlético Madrid', 'Alaves': 'Alavés', 'Espanol': 'Espanyol',
    # Fransa
    'Paris SG': 'Paris Saint-Germain', 'Saint-Etienne': 'Saint-Étienne',
    # Portekiz
    'Sporting': 'Sporting CP',
}

# ─── Lig kodu eşleştirmesi (puan durumu için) ─────────────────────────────────
LEAGUE_CODES = {
    'GER': 'BL1',   # Bundesliga
    'ENG': 'PL',    # Premier League
    'ESP': 'PD',    # La Liga
    'ITA': 'SA',    # Serie A
    'FRA': 'FL1',   # Ligue 1
    'POR': 'PPL',   # Primeira Liga
    'NED': 'DED',   # Eredivisie
}

def normalize_name(name):
    name = name.lower().strip()
    replacements = {
        'ö': 'o', 'oe': 'o', 'ü': 'u', 'ue': 'u',
        'ä': 'a', 'ae': 'a', 'ß': 'ss',
        'é': 'e', 'è': 'e', 'ñ': 'n',
        'á': 'a', 'í': 'i', 'ó': 'o', 'ú': 'u',
        '.': '', '-': '', "'": '', ' ': '',
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    return name


# ─── Alman Takımları → football-data.org ID ──────────────────────────────────
GERMAN_TEAM_NORMALIZED = {
    'bayern': 5, 'fcbayern': 5, 'bayernmunich': 5, 'bayernmunchen': 5,
    'dortmund': 4, 'borussiadortmund': 4,
    'leverkusen': 3, 'bayerleverkusen': 3,
    'leipzig': 721, 'rbleipzig': 721,
    'frankfurt': 19, 'eintrachtfrankfurt': 19,
    'stuttgart': 10, 'vfbstuttgart': 10,
    'freiburg': 17, 'scfreiburg': 17,
    'hoffenheim': 715, 'tsghoffenheim': 715,
    'bremen': 86, 'werderbremen': 86,
    'wolfsburg': 11, 'vflwolfsburg': 11,
    'gladbach': 18, 'borussiamonchengladbach': 18, 'monchengladbach': 18,
    'augsburg': 16, 'fcaugsburg': 16,
    'unionberlin': 28483, 'union': 28483,
    'bochum': 26, 'vflbochum': 26,
    'mainz': 15, 'fsvmainz': 15,
    'stpauli': 29, 'fcstpauli': 29,
    'kiel': 2087, 'holsteinkiel': 2087,
    'heidenheim': 3669, 'fcheidenheim': 3669,
    'hamburg': 62, 'hsv': 62,
    'hannover': 30, 'hannover96': 30,
    'karlsruhe': 24, 'karlsruhersc': 24,
    'schalke': 6, 'fcschalke': 6,
    'darmstadt': 36, 'svdarmstadt': 36,
    'koln': 25, 'koeln': 25, 'fckoln': 25, 'cologne': 25,
    'hertha': 27, 'herthabsc': 27,
    'dusseldorf': 45, 'fortunadusseldorf': 45,
    'nurnberg': 7, 'fcnurnberg': 7,
    'furth': 70, 'greuther': 70,
    'braunschweig': 96,
    'ulm': 3663, 'ssvulm': 3663,
    'munster': 6890, 'preussenmunster': 6890,
    'paderborn': 38, 'scpaderborn': 38,
    'elversberg': 15970,
    'magdeburg': 71, 'fcmagdeburg': 71,
    'regensburg': 46, 'jahnregensburg': 46,
    'lautern': 23, 'kaiserslautern': 23,
}

# ─── İngiliz Takımları → football-data.org ID ────────────────────────────────
ENGLISH_TEAM_NORMALIZED = {
    'arsenal': 57, 'astonvilla': 58, 'bournemouth': 1044,
    'brentford': 402, 'brighton': 397, 'chelsea': 61,
    'crystalpalace': 354, 'everton': 62, 'fulham': 63,
    'ipswich': 57, 'leicester': 338, 'liverpool': 64,
    'manchestercity': 65, 'mancity': 65,
    'manchesterunited': 66, 'manunited': 66, 'manutd': 66,
    'newcastle': 67, 'newcastleunited': 67,
    'nottinghamforest': 351, 'nottmforest': 351, 'forest': 351,
    'southampton': 340, 'tottenham': 73, 'spurs': 73,
    'westham': 563, 'wolverhampton': 76, 'wolves': 76,
    'sunderland': 356, 'sheffieldunited': 356, 'leeds': 341,
    'burnley': 328, 'middlesbrough': 343, 'coventry': 330,
    'watford': 346, 'blackburn': 59, 'norwich': 68,
    'cardiff': 715, 'bristolcity': 387, 'hull': 322,
    'swansea': 72, 'stoke': 70, 'sheffieldwednesday': 345,
    'portsmouth': 1081, 'derby': 333, 'oxford': 1077,
    'luton': 1076, 'plymouth': 1085, 'qpr': 69,
}

# ─── İspanyol Takımları → football-data.org ID ───────────────────────────────
SPANISH_TEAM_NORMALIZED = {
    'barcelona': 81, 'realmadrid': 86,
    'atleticomadrid': 78, 'atletico': 78,
    'athleticbilbao': 77, 'athleticclub': 77, 'athletic': 77,
    'realsociedad': 92, 'villarreal': 533,
    'realbetis': 90, 'betis': 90, 'valencia': 94,
    'girona': 298, 'celtavigo': 558, 'celta': 558,
    'sevilla': 559, 'osasuna': 727, 'getafe': 264,
    'rayovallecano': 876, 'rayo': 876, 'mallorca': 89,
    'alaves': 263, 'espanyol': 80, 'laspalmas': 275,
    'leganes': 745, 'valladolid': 250, 'realoviedo': 285,
    'elche': 284, 'sportinggijon': 287, 'zaragoza': 303, 'huesca': 302,
}


def _find_team_id(team_name, table):
    normalized = normalize_name(team_name)
    if normalized in table:
        return table[normalized]
    for key, tid in table.items():
        if key in normalized or normalized in key:
            return tid
    return None

def is_german_team(team_name):
    return _find_team_id(team_name, GERMAN_TEAM_NORMALIZED) is not None

def is_english_team(team_name):
    return _find_team_id(team_name, ENGLISH_TEAM_NORMALIZED) is not None

def is_spanish_team(team_name):
    return _find_team_id(team_name, SPANISH_TEAM_NORMALIZED) is not None


# ─── football-data.org API ────────────────────────────────────────────────────

def _get_football_data(endpoint, params={}):
    if not FOOTBALL_DATA_KEY:
        return None
    try:
        resp = requests.get(FOOTBALL_DATA_BASE + '/' + endpoint,
                            headers=FOOTBALL_DATA_HEADERS, params=params, timeout=15)
        if resp.status_code == 429:
            logger.warning('Football-Data rate limit hit, skipping')
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error('Football-Data request failed: ' + str(e))
        return None


def _footballdata_last_matches(team_id, team_name, last=5):
    try:
        result = _get_football_data('teams/' + str(team_id) + '/matches', {
            'status': 'FINISHED', 'limit': last
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
        logger.info('Football-Data: ' + str(len(converted)) + ' matches for ' + team_name)
        return converted
    except Exception as e:
        logger.warning('Football-Data matches failed for ' + team_name + ': ' + str(e))
        return []


def _footballdata_h2h(team_id, team1_name, team2_name, last=5):
    try:
        result = _get_football_data('teams/' + str(team_id) + '/matches', {
            'status': 'FINISHED', 'limit': 20
        })
        if not result or not result.get('matches'):
            return []
        h2h = []
        team2_norm = normalize_name(team2_name)
        for m in result['matches']:
            try:
                home_norm = normalize_name(m['homeTeam']['name'])
                away_norm = normalize_name(m['awayTeam']['name'])
                if team2_norm in home_norm or home_norm in team2_norm or \
                   team2_norm in away_norm or away_norm in team2_norm:
                    h2h.append({
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
        return h2h[:last]
    except Exception as e:
        logger.warning('Football-Data H2H failed: ' + str(e))
        return []


# ─── Puan Durumu (Günde 1 kez, cache'li) ─────────────────────────────────────

def get_standings_cached(league_code):
    """Puan durumunu çek, gün içinde cache'den döndür."""
    today = date.today()
    if league_code in _standings_cache:
        cached = _standings_cache[league_code]
        if cached['date'] == today:
            return cached['data']

    result = _get_football_data('competitions/' + league_code + '/standings')
    if not result:
        return None

    try:
        standings = []
        for standing in result.get('standings', []):
            if standing.get('type') == 'TOTAL':
                for team in standing.get('table', []):
                    standings.append({
                        'position': team.get('position'),
                        'team': team.get('team', {}).get('name', ''),
                        'played': team.get('playedGames', 0),
                        'points': team.get('points', 0),
                        'won': team.get('won', 0),
                        'draw': team.get('draw', 0),
                        'lost': team.get('lost', 0),
                        'goals_for': team.get('goalsFor', 0),
                        'goals_against': team.get('goalsAgainst', 0),
                        'goal_diff': team.get('goalDifference', 0),
                    })
                break

        _standings_cache[league_code] = {'date': today, 'data': standings}
        logger.info('Standings cached for ' + league_code + ': ' + str(len(standings)) + ' teams')
        return standings
    except Exception as e:
        logger.warning('Standings parse failed: ' + str(e))
        return None


def get_team_standing(team_name, country_code):
    """Takımın puan durumundaki yerini bul."""
    league_code = LEAGUE_CODES.get(country_code)
    if not league_code:
        return None

    standings = get_standings_cached(league_code)
    if not standings:
        return None

    team_norm = normalize_name(team_name)
    for s in standings:
        s_norm = normalize_name(s['team'])
        if team_norm in s_norm or s_norm in team_norm:
            return s

    return None


# ─── Ev/Deplasman Ayrımlı İstatistik ─────────────────────────────────────────

def get_team_home_away_stats(team_name, matches):
    """
    Maç listesinden ev/deplasman ayrımlı form ve gol ortalaması hesapla.
    Döndürür: {
        'home_form': 'WWD', 'home_goals_avg': 2.1, 'home_conceded_avg': 0.8,
        'away_form': 'LDW', 'away_goals_avg': 1.2, 'away_conceded_avg': 1.5
    }
    """
    if not matches:
        return None

    team_norm = normalize_name(team_name)
    home_results = []
    away_results = []

    for m in matches:
        try:
            home_name_norm = normalize_name(m['teams']['home']['name'])
            hg = m['goals']['home']
            ag = m['goals']['away']
            if hg is None or ag is None:
                continue

            is_home = team_norm in home_name_norm or home_name_norm in team_norm

            if is_home:
                home_results.append({'scored': hg, 'conceded': ag,
                                     'result': 'W' if hg > ag else ('D' if hg == ag else 'L')})
            else:
                away_results.append({'scored': ag, 'conceded': hg,
                                     'result': 'W' if ag > hg else ('D' if ag == hg else 'L')})
        except:
            continue

    result = {}

    if home_results:
        result['home_form'] = ''.join([r['result'] for r in home_results[-5:]])
        result['home_goals_avg'] = round(sum(r['scored'] for r in home_results) / len(home_results), 1)
        result['home_conceded_avg'] = round(sum(r['conceded'] for r in home_results) / len(home_results), 1)
    else:
        result['home_form'] = ''
        result['home_goals_avg'] = 0
        result['home_conceded_avg'] = 0

    if away_results:
        result['away_form'] = ''.join([r['result'] for r in away_results[-5:]])
        result['away_goals_avg'] = round(sum(r['scored'] for r in away_results) / len(away_results), 1)
        result['away_conceded_avg'] = round(sum(r['conceded'] for r in away_results) / len(away_results), 1)
    else:
        result['away_form'] = ''
        result['away_goals_avg'] = 0
        result['away_conceded_avg'] = 0

    return result


# ─── ClubElo Fixtures ─────────────────────────────────────────────────────────

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
            home = NAME_FIXES.get(home, home)
            away = NAME_FIXES.get(away, away)
            fixtures.append({
                'fixture': {'id': i + 900000, 'date': None},
                'league': {'id': 0, 'name': country if country else 'Bilinmeyen Lig'},
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


# ─── Ana Fonksiyonlar ─────────────────────────────────────────────────────────

def get_team_last_matches(team_name, last=10):
    """
    Son maçları çek (ev/deplasman ayrımı için daha fazla maç — 10)
    1. Alman → football-data.org
    2. İngiliz → football-data.org
    3. İspanyol → football-data.org
    4. Diğer → boş
    """
    if is_german_team(team_name):
        team_id = _find_team_id(team_name, GERMAN_TEAM_NORMALIZED)
        if team_id:
            return _footballdata_last_matches(team_id, team_name, last)
        return []

    if is_english_team(team_name):
        team_id = _find_team_id(team_name, ENGLISH_TEAM_NORMALIZED)
        if team_id:
            return _footballdata_last_matches(team_id, team_name, last)
        return []

    if is_spanish_team(team_name):
        team_id = _find_team_id(team_name, SPANISH_TEAM_NORMALIZED)
        if team_id:
            return _footballdata_last_matches(team_id, team_name, last)
        return []

    logger.info('No stats source for ' + team_name + ', using ClubElo only')
    return []


def get_h2h(team1_name, team2_name, last=5):
    if is_german_team(team1_name) or is_german_team(team2_name):
        team_id = _find_team_id(team1_name, GERMAN_TEAM_NORMALIZED) or \
                  _find_team_id(team2_name, GERMAN_TEAM_NORMALIZED)
        if team_id:
            return _footballdata_h2h(team_id, team1_name, team2_name, last)
        return []

    if is_english_team(team1_name) or is_english_team(team2_name):
        team_id = _find_team_id(team1_name, ENGLISH_TEAM_NORMALIZED) or \
                  _find_team_id(team2_name, ENGLISH_TEAM_NORMALIZED)
        if team_id:
            return _footballdata_h2h(team_id, team1_name, team2_name, last)
        return []

    if is_spanish_team(team1_name) or is_spanish_team(team2_name):
        team_id = _find_team_id(team1_name, SPANISH_TEAM_NORMALIZED) or \
                  _find_team_id(team2_name, SPANISH_TEAM_NORMALIZED)
        if team_id:
            return _footballdata_h2h(team_id, team1_name, team2_name, last)
        return []

    return []


def search_team(team_name):
    return None


def get_standings(league_code, season=2024):
    result = _get_football_data('competitions/' + str(league_code) + '/standings', {'season': season})
    if not result:
        return []
    return result
