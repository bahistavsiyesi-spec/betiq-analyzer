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

# ClubElo → Düzgün isim tablosu
NAME_FIXES = {
    # Türkiye
    'Bueyueksehir': 'Başakşehir',
    'Basaksehir': 'Başakşehir',
    'Besiktas': 'Beşiktaş',
    'Fenerbahce': 'Fenerbahçe',
    'Kasimpasa': 'Kasımpaşa',
    'Eyupspor': 'Eyüpspor',
    'Goztepe': 'Göztepe',
    'Ankaragucu': 'Ankaragücü',
    'Keciorengucu': 'Keçiörengücü',
    'Istanbulspor': 'İstanbulspor',
    # Almanya
    'Koeln': 'Köln',
    'Nuernberg': 'Nürnberg',
    'Fuerth': 'Fürth',
    'Duesseldorf': 'Düsseldorf',
    'Muenchen': 'München',
    'Moenchengladbach': 'Mönchengladbach',
    'Muenster': 'Münster',
    'Saarbruecken': 'Saarbrücken',
    'Osnabrueck': 'Osnabrück',
    # İspanya
    'Cadiz': 'Cádiz',
    'Almeria': 'Almería',
    'Malaga': 'Málaga',
    'Leganes': 'Leganés',
    'Cordoba': 'Córdoba',
    # Fransa
    'Paris SG': 'Paris Saint-Germain',
    'Saint-Etienne': 'Saint-Étienne',
    # Portekiz
    'Sporting': 'Sporting CP',
}

# ─── İngiliz Takımları → football-data.org ID ────────────────────────────────
# Sadece İngiliz takımları için football-data.org kullanılır, kota korunur
ENGLISH_TEAM_IDS = {
    # Premier League
    'arsenal': 57,
    'aston villa': 58,
    'bournemouth': 1044,
    'brentford': 402,
    'brighton': 397,
    'chelsea': 61,
    'crystal palace': 354,
    'everton': 62,
    'fulham': 63,
    'ipswich': 57,
    'leicester': 338,
    'liverpool': 64,
    'manchester city': 65,
    'manchester united': 66,
    'newcastle': 67,
    'nottingham forest': 351,
    'southampton': 340,
    'tottenham': 73,
    'west ham': 563,
    'wolverhampton': 76, 'wolves': 76,
    # Championship
    'sunderland': 356,
    'sheffield united': 356,
    'leeds': 341,
    'burnley': 328,
    'middlesbrough': 343,
    'coventry': 330,
    'watford': 346,
    'preston': 1076,
    'millwall': 1073,
    'blackburn': 59,
    'norwich': 68,
    'cardiff': 715,
    'bristol city': 387,
    'hull': 322,
    'swansea': 72,
    'stoke': 70,
    'sheffield wednesday': 345,
    'portsmouth': 1081,
    'derby': 333,
    'oxford': 1077,
    'luton': 1076,
    'plymouth': 1085,
    'qpr': 69,
}

# Normalize edilmiş İngiliz takım isimleri (ClubElo formatı)
ENGLISH_TEAM_NORMALIZED = {
    # Premier League - ClubElo'nun kullandığı isimler
    'arsenal': 57,
    'astonvilla': 58,
    'bournemouth': 1044,
    'brentford': 402,
    'brighton': 397,
    'chelsea': 61,
    'crystalpalace': 354,
    'everton': 62,
    'fulham': 63,
    'ipswich': 57,
    'leicester': 338,
    'liverpool': 64,
    'manchestercity': 65,
    'manchesterunited': 66,
    'newcastle': 67,
    'nottinghamforest': 351,
    'southampton': 340,
    'tottenham': 73,
    'westham': 563,
    'wolverhampton': 76, 'wolves': 76,
    # Championship
    'sunderland': 356,
    'sheffieldunited': 356,
    'leeds': 341,
    'burnley': 328,
    'middlesbrough': 343,
    'coventry': 330,
    'watford': 346,
    'blackburn': 59,
    'norwich': 68,
    'cardiff': 715,
    'bristolcity': 387,
    'hull': 322,
    'swansea': 72,
    'stoke': 70,
    'sheffieldwednesday': 345,
    'portsmouth': 1081,
    'derby': 333,
    'oxford': 1077,
    'luton': 1076,
    'plymouth': 1085,
    'qpr': 69,
}

# Alman lig takımları → OpenLigaDB ID eşleştirmesi
OPENLIGA_TEAM_IDS = {
    # Bundesliga (Level 1)
    'fc bayern': 40, 'bayern munich': 40, 'bayern': 40,
    'borussia dortmund': 7, 'dortmund': 7,
    'bayer leverkusen': 9, 'leverkusen': 9,
    'rb leipzig': 54, 'leipzig': 54,
    'eintracht frankfurt': 91, 'frankfurt': 91,
    'vfb stuttgart': 16, 'stuttgart': 16,
    'sc freiburg': 112, 'freiburg': 112,
    'tsg hoffenheim': 3, 'hoffenheim': 3,
    'werder bremen': 86, 'bremen': 86,
    'vfl wolfsburg': 24, 'wolfsburg': 24,
    'borussia monchengladbach': 87, 'gladbach': 87,
    'fc augsburg': 167, 'augsburg': 167,
    'union berlin': 80,
    'vfl bochum': 44, 'bochum': 44,
    'fsv mainz': 6, 'mainz': 6,
    'fc st pauli': 65, 'st pauli': 65,
    'holstein kiel': 14, 'kiel': 14,
    'heidenheim': 150,
    # 2. Bundesliga (Level 2)
    'hamburger sv': 100, 'hamburg': 100, 'hsv': 100,
    'hannover 96': 55, 'hannover': 55,
    'karlsruher sc': 8, 'karlsruhe': 8,
    'fc schalke': 5, 'schalke': 5,
    'sv darmstadt': 127, 'darmstadt': 127,
    'fc koln': 65, 'koln': 65, 'cologne': 65,
    'hertha bsc': 28, 'hertha': 28,
    'fortuna dusseldorf': 74, 'dusseldorf': 74,
    'fc nurnberg': 4, 'nurnberg': 4,
    'greuther furth': 79, 'furth': 79,
    'vfl osnabruck': 120, 'osnabruck': 120,
    'eintracht braunschweig': 97, 'braunschweig': 97,
    'ssv ulm': 158, 'ulm': 158,
    'preussen munster': 21, 'munster': 21,
    'paderborn': 131,
    'elversberg': 166,
    'magdeburg': 43,
    'bielefeld': 71,
    'dresden': 68,
    'lautern': 62, 'kaiserslautern': 62,
}


def normalize_name(name):
    """Tüm özel karakterleri kaldır, küçük harfe çevir."""
    name = name.lower().strip()
    replacements = {
        'ö': 'o', 'oe': 'o',
        'ü': 'u', 'ue': 'u',
        'ä': 'a', 'ae': 'a',
        'ß': 'ss',
        'é': 'e', 'è': 'e',
        'ñ': 'n',
        '.': '', '-': '', "'": '', ' ': '',
    }
    for old, new in replacements.items():
        name = name.replace(old, new)
    return name


# ClubElo → OpenLigaDB ID direkt eşleştirme
CLUBELO_DIRECT_MAP = {
    # Bundesliga
    'bayern': 40,
    'dortmund': 7,
    'leverkusen': 9,
    'leipzig': 54,
    'frankfurt': 91,
    'stuttgart': 16,
    'freiburg': 112,
    'hoffenheim': 3,
    'bremen': 86,
    'wolfsburg': 24,
    'gladbach': 87,
    'augsburg': 167,
    'unionberlin': 80,
    'bochum': 44,
    'mainz': 6,
    'stpauli': 65,
    'kiel': 14,
    'heidenheim': 150,
    # 2. Bundesliga
    'hamburg': 100,
    'hannover': 55,
    'karlsruhe': 8,
    'schalke': 5,
    'darmstadt': 127,
    'koln': 65,
    'koeln': 65,
    'hertha': 28,
    'dusseldorf': 74,
    'nurnberg': 4,
    'furth': 79,
    'braunschweig': 97,
    'ulm': 158,
    'munster': 21,
    'paderborn': 131,
    'elversberg': 166,
    'magdeburg': 43,
    'bielefeld': 71,
    'dresden': 68,
    'lautern': 62,
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


# ─── İngiliz Takım Fonksiyonları ──────────────────────────────────────────────

def _find_english_team_id(team_name):
    """Takım adından football-data.org ID'sini bul."""
    normalized = normalize_name(team_name)

    # 1. Normalize edilmiş direkt eşleştirme
    if normalized in ENGLISH_TEAM_NORMALIZED:
        team_id = ENGLISH_TEAM_NORMALIZED[normalized]
        logger.info('Football-Data ID found for ' + team_name + ': ' + str(team_id))
        return team_id

    # 2. Kısmi eşleştirme
    for key, team_id in ENGLISH_TEAM_NORMALIZED.items():
        if key in normalized or normalized in key:
            logger.info('Football-Data ID found for ' + team_name + ': ' + str(team_id))
            return team_id

    # 3. Ham isim tablosunda ara
    team_lower = team_name.lower().strip()
    for key, team_id in ENGLISH_TEAM_IDS.items():
        if key in team_lower or team_lower in key:
            logger.info('Football-Data ID found for ' + team_name + ': ' + str(team_id))
            return team_id

    logger.info('No Football-Data ID for ' + team_name)
    return None


def is_english_team(team_name):
    """Takımın İngiliz ligi takımı olup olmadığını kontrol et."""
    return _find_english_team_id(team_name) is not None


def get_footballdata_team_last_matches(team_name, last=5):
    """İngiliz ligi takımı için son maçları football-data.org'dan çek."""
    if not FOOTBALL_DATA_KEY:
        return []

    team_id = _find_english_team_id(team_name)
    if not team_id:
        return []

    try:
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

        logger.info('Football-Data: ' + str(len(converted)) + ' matches for ' + team_name)
        return converted
    except Exception as e:
        logger.warning('Football-Data team matches failed for ' + team_name + ': ' + str(e))
        return []


def get_footballdata_h2h(team1_name, team2_name, last=5):
    """İki İngiliz ligi takımı arasındaki H2H maçlarını football-data.org'dan çek."""
    if not FOOTBALL_DATA_KEY:
        return []

    team1_id = _find_english_team_id(team1_name)
    if not team1_id:
        return []

    try:
        result = _get_football_data('teams/' + str(team1_id) + '/matches', {
            'status': 'FINISHED',
            'limit': 20
        })
        if not result or not result.get('matches'):
            return []

        h2h = []
        team2_lower = normalize_name(team2_name)
        for m in result['matches']:
            try:
                home_norm = normalize_name(m['homeTeam']['name'])
                away_norm = normalize_name(m['awayTeam']['name'])
                if team2_lower in home_norm or home_norm in team2_lower or \
                   team2_lower in away_norm or away_norm in team2_lower:
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


# ─── OpenLigaDB Fonksiyonları ─────────────────────────────────────────────────

def _find_openliga_team_id(team_name):
    """Takım adından OpenLigaDB ID'sini bul. Normalize ederek eşleştirir."""
    normalized = normalize_name(team_name)

    if normalized in CLUBELO_DIRECT_MAP:
        team_id = CLUBELO_DIRECT_MAP[normalized]
        logger.info('OpenLigaDB ID found for ' + team_name + ': ' + str(team_id))
        return team_id

    for key, team_id in CLUBELO_DIRECT_MAP.items():
        if key in normalized or normalized in key:
            logger.info('OpenLigaDB ID found for ' + team_name + ': ' + str(team_id))
            return team_id

    for key, team_id in OPENLIGA_TEAM_IDS.items():
        key_norm = normalize_name(key)
        if key_norm in normalized or normalized in key_norm:
            logger.info('OpenLigaDB ID found for ' + team_name + ': ' + str(team_id))
            return team_id

    logger.info('No OpenLigaDB ID for ' + team_name)
    return None


def _get_openliga_season_matches(league_short, season):
    """OpenLigaDB'den tüm sezon maçlarını çek."""
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
    normalized = normalize_name(team_name)
    if normalized in CLUBELO_DIRECT_MAP:
        return True
    for key in CLUBELO_DIRECT_MAP:
        if key in normalized or normalized in key:
            return True
    for key in OPENLIGA_TEAM_IDS:
        if normalize_name(key) in normalized or normalized in normalize_name(key):
            return True
    return False


# ─── Football-Data API ───────────────────────────────────────────────────────

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

            # ClubElo ASCII isimlerini düzelt
            home = NAME_FIXES.get(home, home)
            away = NAME_FIXES.get(away, away)

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
    Öncelik sırası:
    1. Alman ligi → OpenLigaDB (ücretsiz, limitsiz)
    2. İngiliz ligi → football-data.org (kotadan tasarruflu)
    3. Diğer → football-data.org KNOWN_TEAM_IDS ile
    """
    # 1. Alman ligi
    if is_german_team(team_name):
        matches = get_openliga_team_last_matches(team_name, last)
        if matches:
            return matches

    # 2. İngiliz ligi
    if is_english_team(team_name):
        matches = get_footballdata_team_last_matches(team_name, last)
        if matches:
            return matches
        return []  # İngiliz takımı ama veri gelmedi, diğer API'ye geçme

    # 3. Diğer ligler - KNOWN_TEAM_IDS ile
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
    Öncelik sırası:
    1. Alman ligi → OpenLigaDB
    2. İngiliz ligi → football-data.org
    3. Diğer → football-data.org KNOWN_TEAM_IDS ile
    """
    # 1. Alman ligi
    if is_german_team(team1_name) or is_german_team(team2_name):
        h2h = get_openliga_h2h(team1_name, team2_name, last)
        if h2h:
            return h2h

    # 2. İngiliz ligi
    if is_english_team(team1_name) or is_english_team(team2_name):
        h2h = get_footballdata_h2h(team1_name, team2_name, last)
        if h2h:
            return h2h
        return []

    # 3. Diğer ligler
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
