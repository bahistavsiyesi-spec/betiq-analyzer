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

# ─── Puan durumu cache ────────────────────────────────────────────────────────
_standings_cache = {}

# ─── football-data.co.uk şut/korner cache (günde 1 kez) ─────────────────────
_shots_cache = {}

# ─── ClubElo → Düzgün isim tablosu ───────────────────────────────────────────
NAME_FIXES = {
    'Bueyueksehir': 'Başakşehir', 'Basaksehir': 'Başakşehir',
    'Besiktas': 'Beşiktaş', 'Fenerbahce': 'Fenerbahçe',
    'Kasimpasa': 'Kasımpaşa', 'Eyupspor': 'Eyüpspor',
    'Goztepe': 'Göztepe', 'Ankaragucu': 'Ankaragücü',
    'Keciorengucu': 'Keçiörengücü', 'Istanbulspor': 'İstanbulspor',
    'Koeln': 'Köln', 'Nuernberg': 'Nürnberg', 'Fuerth': 'Fürth',
    'Duesseldorf': 'Düsseldorf', 'Muenchen': 'München',
    'Moenchengladbach': 'Mönchengladbach', 'Muenster': 'Münster',
    'Saarbruecken': 'Saarbrücken', 'Osnabrueck': 'Osnabrück',
    'Cadiz': 'Cádiz', 'Almeria': 'Almería', 'Malaga': 'Málaga',
    'Leganes': 'Leganés', 'Cordoba': 'Córdoba',
    'Atletico': 'Atlético Madrid', 'Alaves': 'Alavés', 'Espanol': 'Espanyol',
    'Paris SG': 'Paris Saint-Germain', 'Saint-Etienne': 'Saint-Étienne',
    'Sporting': 'Sporting CP',
}

# ─── Lig kodu eşleştirmesi ────────────────────────────────────────────────────
LEAGUE_CODES = {
    'GER': 'BL1', 'ENG': 'PL', 'ESP': 'PD',
    'ITA': 'SA', 'FRA': 'FL1', 'POR': 'PPL', 'NED': 'DED',
}

# ─── football-data.co.uk lig CSV kodları ─────────────────────────────────────
FDCO_LEAGUES = {
    'ENG': ('2425', 'E0'),   # Premier League
    'GER': ('2425', 'D1'),   # Bundesliga
    'ESP': ('2425', 'SP1'),  # La Liga
    'ITA': ('2425', 'I1'),   # Serie A
    'FRA': ('2425', 'F1'),   # Ligue 1
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
    # Kulüp son eklerini temizle — uzundan kısaya sırala, ilk eşleşende dur
    for suffix in ('wanderers', 'united', 'city', 'town', 'afc', 'fc', 'sc', 'cf', 'ac', 'sv', 'bv', 'vfl', 'vfb', 'rb', 'tsv', 'fsv'):
        if name.endswith(suffix) and len(name) > len(suffix) + 2:
            name = name[:-len(suffix)]
            break
    return name


def teams_match(name_a, name_b):
    """
    İki takım isminin aynı takıma ait olup olmadığını kontrol et.
    Kısa isim (Wolves) ↔ uzun isim (Wolverhampton Wanderers FC) gibi durumları yakalar.
    """
    a = normalize_name(name_a)
    b = normalize_name(name_b)

    # Tam veya kısmi eşleşme
    if a in b or b in a:
        return True

    # İlk 5 karakter eşleşmesi
    if len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5]:
        return True

    return False


# ─── Alman Takımları ──────────────────────────────────────────────────────────
GERMAN_TEAM_NORMALIZED = {
    'bayern': 5, 'fcbayern': 5, 'bayernmunich': 5, 'bayernmunchen': 5,
    'dortmund': 4, 'borussiadortmund': 4,
    'leverkusen': 3, 'bayerleverkusen': 3,
    'leipzig': 721, 'rbleipzig': 721,
    'frankfurt': 19, 'eintrachtfrankfurt': 19,
    'stuttgart': 10, 'vfbstuttgart': 10,
    'freiburg': 17, 'scfreiburg': 17,
    'hoffenheim': 2, 'tsghoffenheim': 2,
    'bremen': 12, 'werderbremen': 12,
    'wolfsburg': 11, 'vflwolfsburg': 11,
    'gladbach': 18, 'borussiamonchengladbach': 18, 'monchengladbach': 18,
    'augsburg': 16, 'fcaugsburg': 16,
    'unionberlin': 28, 'union': 28,
    'bochum': 20, 'vflbochum': 20,
    'mainz': 15, 'fsvmainz': 15,
    'stpauli': 20, 'fcstpauli': 20,
    'kiel': 44, 'holsteinkiel': 44,
    'heidenheim': 44, 'fcheidenheim': 44,
    'hamburg': 7, 'hsv': 7,
    'hannover': 30, 'hannover96': 30,
    'karlsruhe': 24, 'karlsruhersc': 24,
    'schalke': 6, 'fcschalke': 6,
    'darmstadt': 36, 'svdarmstadt': 36,
    'koln': 1, 'koeln': 1, 'fckoln': 1, 'cologne': 1,
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

# ─── İngiliz Takımları ────────────────────────────────────────────────────────
ENGLISH_TEAM_NORMALIZED = {
    'arsenal': 57, 'astonvilla': 58, 'bournemouth': 1044,
    'brentford': 402, 'brighton': 397, 'chelsea': 61,
    'crystalpalace': 354, 'everton': 62, 'fulham': 63,
    'ipswich': 349, 'leicester': 338, 'liverpool': 64,
    'manchestercity': 65, 'mancity': 65,
    'manchesterunited': 66, 'manunited': 66, 'manutd': 66,
    'newcastle': 67, 'newcastleunited': 67,
    'nottinghamforest': 351, 'nottmforest': 351, 'forest': 351,
    'southampton': 340, 'tottenham': 73, 'spurs': 73,
    'westham': 563, 'wolverhampton': 76, 'wolves': 76,
    'burnley': 328, 'leedsunited': 341, 'leeds': 341,
    'sunderland': 71,
    'birmingham': 332, 'blackburn': 59, 'bristolcity': 387,
    'charlton': 348, 'coventry': 1076, 'derby': 342,
    'hull': 322, 'middlesbrough': 343, 'millwall': 384,
    'norwich': 68, 'oxford': 1082, 'portsmouth': 325,
    'preston': 1081, 'qpr': 69, 'sheffieldunited': 356,
    'sheffieldwednesday': 345, 'stoke': 70, 'swansea': 72,
    'watford': 346, 'westbrom': 74, 'wrexham': 404,
    'luton': 1076, 'plymouth': 1085,
}

# ─── İspanyol Takımları ───────────────────────────────────────────────────────
SPANISH_TEAM_NORMALIZED = {
    'athleticclub': 77, 'athleticbilbao': 77, 'athletic': 77,
    'osasuna': 79, 'atleticomadrid': 78, 'atletico': 78,
    'alaves': 263, 'elche': 285, 'barcelona': 81,
    'getafe': 82, 'girona': 298, 'levante': 88,
    'celtavigo': 558, 'celta': 558,
    'espanyol': 80, 'mallorca': 89,
    'rayovallecano': 88, 'rayo': 88,
    'realbetis': 90, 'betis': 90,
    'realmadrid': 86, 'realoviedo': 1048,
    'realsociedad': 92, 'sevilla': 559,
    'valencia': 94, 'villarreal': 95,
    'laspalmas': 275, 'leganes': 745, 'valladolid': 250,
    'sportinggijon': 287, 'zaragoza': 303, 'huesca': 302,
}

# ─── İtalyan Takımları ────────────────────────────────────────────────────────
ITALIAN_TEAM_NORMALIZED = {
    'acmilan': 98, 'milan': 98,
    'acpisa': 487, 'pisa': 487,
    'acffiorentina': 99, 'fiorentina': 99,
    'asroma': 100, 'roma': 100,
    'atalanta': 102, 'bologna': 103,
    'cagliari': 104, 'como': 7397,
    'inter': 108, 'intermilan': 108, 'fcinternazionale': 108,
    'juventus': 109, 'juve': 109,
    'lazio': 110, 'napoli': 113,
    'parma': 112, 'torino': 586,
    'cremonese': 457, 'lecce': 5890,
    'sassuolo': 471, 'udinese': 115,
    'verona': 450, 'genoa': 107,
    'monza': 5911, 'venezia': 454,
    'empoli': 445, 'sampdoria': 574,
    'palermo': 576, 'brescia': 580, 'spezia': 3964,
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

def is_italian_team(team_name):
    return _find_team_id(team_name, ITALIAN_TEAM_NORMALIZED) is not None


# ─── football-data.co.uk Şut/Korner İstatistikleri ───────────────────────────

def _fetch_fdco_csv(country_code):
    today = date.today()
    if country_code in _shots_cache:
        cached = _shots_cache[country_code]
        if cached['date'] == today:
            return cached['data']

    league_info = FDCO_LEAGUES.get(country_code)
    if not league_info:
        return []

    season, league_code = league_info
    url = f'https://www.football-data.co.uk/mmz4281/{season}/{league_code}.csv'

    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = [r for r in reader if r.get('HomeTeam') and r.get('AwayTeam')]
        _shots_cache[country_code] = {'date': today, 'data': rows}
        logger.info(f'FDCO: {len(rows)} matches loaded for {country_code}')
        return rows
    except Exception as e:
        logger.warning(f'FDCO fetch failed for {country_code}: {e}')
        return []


def get_team_shot_stats(team_name, country_code, last=5):
    rows = _fetch_fdco_csv(country_code)
    if not rows:
        return None

    team_norm = normalize_name(team_name)
    team_matches = []

    for row in rows:
        home_norm = normalize_name(row.get('HomeTeam', ''))
        away_norm = normalize_name(row.get('AwayTeam', ''))

        is_home = team_norm in home_norm or home_norm in team_norm
        is_away = team_norm in away_norm or away_norm in team_norm

        if not is_home and not is_away:
            continue

        try:
            if is_home:
                shots = int(row.get('HS', 0) or 0)
                shots_on = int(row.get('HST', 0) or 0)
                corners = int(row.get('HC', 0) or 0)
                shots_conceded = int(row.get('AS', 0) or 0)
            else:
                shots = int(row.get('AS', 0) or 0)
                shots_on = int(row.get('AST', 0) or 0)
                corners = int(row.get('AC', 0) or 0)
                shots_conceded = int(row.get('HS', 0) or 0)

            if shots > 0:
                team_matches.append({
                    'shots': shots,
                    'shots_on': shots_on,
                    'corners': corners,
                    'shots_conceded': shots_conceded,
                })
        except:
            continue

    if not team_matches:
        return None

    recent = team_matches[-last:]
    n = len(recent)

    shots_avg = round(sum(m['shots'] for m in recent) / n, 1)
    shots_on_avg = round(sum(m['shots_on'] for m in recent) / n, 1)
    corners_avg = round(sum(m['corners'] for m in recent) / n, 1)
    shots_conceded_avg = round(sum(m['shots_conceded'] for m in recent) / n, 1)
    accuracy = round(shots_on_avg / shots_avg * 100, 1) if shots_avg > 0 else 0

    logger.info(f'FDCO shots {team_name}: {shots_avg} şut, {shots_on_avg} isabet, {corners_avg} korner (son {n} maç)')

    return {
        'shots_avg': shots_avg,
        'shots_on_target_avg': shots_on_avg,
        'corners_avg': corners_avg,
        'shots_conceded_avg': shots_conceded_avg,
        'shot_accuracy': accuracy,
        'matches_used': n,
    }


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


def _footballdata_last_matches(team_id, team_name, last=10):
    try:
        result = _get_football_data('teams/' + str(team_id) + '/matches', {
            'status': 'FINISHED', 'limit': last
        })
        if not result or not result.get('matches'):
            return []

        # FIX: Maçları tarihe göre eskiden yeniye sırala, sonra son N tanesini al
        # football-data.org bazen ters sırada dönüyor, bu Sofascore uyumsuzluğuna yol açıyordu
        sorted_matches = sorted(result['matches'], key=lambda x: x.get('utcDate', ''))
        last_matches = sorted_matches[-last:]

        converted = []
        for m in last_matches:
            try:
                ht = m.get('score', {}).get('halfTime', {})
                ht_home = ht.get('home')
                ht_away = ht.get('away')
                home = m['homeTeam']['name']
                away = m['awayTeam']['name']
                hg = m['score']['fullTime']['home']
                ag = m['score']['fullTime']['away']
                date_str = m.get('utcDate', '')[:10]
                is_home = teams_match(team_name, home)

                if is_home:
                    result_str = 'W' if hg > ag else ('D' if hg == ag else 'L')
                else:
                    result_str = 'W' if ag > hg else ('D' if ag == hg else 'L')

                # DEBUG: Her maçı logla
                logger.info(f'MATCH {team_name} | {date_str} | {home} {hg}-{ag} {away} | is_home={is_home} | {result_str}')

                converted.append({
                    'teams': {
                        'home': {'name': home, 'id': m['homeTeam']['id']},
                        'away': {'name': away, 'id': m['awayTeam']['id']}
                    },
                    'goals': {
                        'home': hg,
                        'away': ag,
                        'ht_home': ht_home,
                        'ht_away': ht_away,
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
        for m in result['matches']:
            try:
                home_name = m['homeTeam']['name']
                away_name = m['awayTeam']['name']
                if teams_match(team2_name, home_name) or teams_match(team2_name, away_name):
                    ht = m.get('score', {}).get('halfTime', {})
                    h2h.append({
                        'teams': {
                            'home': {'name': home_name, 'id': m['homeTeam']['id']},
                            'away': {'name': away_name, 'id': m['awayTeam']['id']}
                        },
                        'goals': {
                            'home': m['score']['fullTime']['home'],
                            'away': m['score']['fullTime']['away'],
                            'ht_home': ht.get('home'),
                            'ht_away': ht.get('away'),
                        }
                    })
            except:
                continue
        return h2h[:last]
    except Exception as e:
        logger.warning('Football-Data H2H failed: ' + str(e))
        return []


# ─── Puan Durumu ─────────────────────────────────────────────────────────────

def get_standings_cached(league_code):
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
    league_code = LEAGUE_CODES.get(country_code)
    if not league_code:
        return None
    standings = get_standings_cached(league_code)
    if not standings:
        return None
    # teams_match kullanarak daha esnek eşleştirme
    for s in standings:
        if teams_match(team_name, s['team']):
            return s
    return None


# ─── Ev/Deplasman Ayrımlı İstatistik ─────────────────────────────────────────

def get_team_home_away_stats(team_name, matches):
    if not matches:
        return None

    home_results = []
    away_results = []

    for m in matches:
        try:
            match_home_name = m['teams']['home']['name']
            hg = m['goals']['home']
            ag = m['goals']['away']
            if hg is None or ag is None:
                continue

            is_home = teams_match(team_name, match_home_name)

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
    if is_italian_team(team_name):
        team_id = _find_team_id(team_name, ITALIAN_TEAM_NORMALIZED)
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
    if is_italian_team(team1_name) or is_italian_team(team2_name):
        team_id = _find_team_id(team1_name, ITALIAN_TEAM_NORMALIZED) or \
                  _find_team_id(team2_name, ITALIAN_TEAM_NORMALIZED)
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
