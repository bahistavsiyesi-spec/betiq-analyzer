import requests
import time
import os
import logging
import csv
import io
import re
from datetime import datetime, date

logger = logging.getLogger(__name__)

FOOTBALL_DATA_KEY = os.environ.get('FOOTBALL_DATA_KEY', '')
FOOTBALL_DATA_BASE = 'https://api.football-data.org/v4'
FOOTBALL_DATA_HEADERS = {
    'X-Auth-Token': FOOTBALL_DATA_KEY
}

COLLECT_API_KEY = os.environ.get('COLLECT_API_KEY', '')
COLLECT_API_BASE = 'https://api.collectapi.com/football'

# ─── Cache'ler ────────────────────────────────────────────────────────────────
_standings_cache = {}
_collectapi_standings_cache = {}
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

# ─── Lig kodu eşleştirmesi (football-data.org) ───────────────────────────────
LEAGUE_CODES = {
    'GER': 'BL1', 'ENG': 'PL', 'ESP': 'PD',
    'ITA': 'SA', 'FRA': 'FL1', 'POR': 'PPL', 'NED': 'DED', 'BRA': 'BSA',
    'CL': 'CL', 'EL': 'EL', 'EC': 'EC',
}

# ─── football-data.co.uk lig CSV kodları ─────────────────────────────────────
FDCO_LEAGUES = {
    'ENG': ('2425', 'E0'),
    'GER': ('2425', 'D1'),
    'ESP': ('2425', 'SP1'),
    'ITA': ('2425', 'I1'),
    'FRA': ('2425', 'F1'),
    'NED': ('2425', 'N1'),
}

# ─── CollectAPI lig key eşleştirmesi ─────────────────────────────────────────
COLLECT_API_LEAGUE_MAP = {
    'super lig': 'super-lig', 'süper lig': 'super-lig',
    'trendyol süper lig': 'super-lig', 'trendyol super lig': 'super-lig',
    'turkey': 'super-lig', 'türkiye': 'super-lig',
    'tff 1. lig': 'tff-1-lig', 'tff 1 lig': 'tff-1-lig',
    'trendyol 1. lig': 'tff-1-lig', '1. lig': 'tff-1-lig',
    'premier league': 'ingiltere-premier-ligi', 'england': 'ingiltere-premier-ligi',
    'championship': 'ingiltere-sampiyonluk-ligi', 'efl championship': 'ingiltere-sampiyonluk-ligi',
    'bundesliga': 'almanya-bundesliga', 'germany': 'almanya-bundesliga',
    '2. bundesliga': 'almanya-bundesliga-2-ligi',
    'la liga': 'ispanya-la-liga', 'laliga': 'ispanya-la-liga', 'spain': 'ispanya-la-liga',
    'serie a': 'italya-serie-a-ligi', 'italy': 'italya-serie-a-ligi',
    'ligue 1': 'fransa-ligue-1', 'france': 'fransa-ligue-1', 'ligue 2': 'fransa-ligue-2',
}

# ─── Gençlik/Rezerv takım suffix'leri ────────────────────────────────────────
YOUTH_SUFFIXES = (
    'u21', 'u18', 'u23', 'u19', 'u20', 'u17', 'u16', 'u15',
    'reserves', 'reserve', 'youth', ' ii', ' b', 'res.',
    'development', 'academy', 'cdp',
)

def is_youth_or_reserve(team_name):
    name_lower = team_name.lower()
    for suffix in YOUTH_SUFFIXES:
        if suffix in name_lower:
            return True
    return False


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
    for suffix in ('wanderers', 'united', 'city', 'town', 'afc', 'fc', 'sc', 'cf', 'ac', 'sv', 'bv', 'vfl', 'vfb', 'rb', 'tsv', 'fsv'):
        if name.endswith(suffix) and len(name) > len(suffix) + 2:
            name = name[:-len(suffix)]
            break
    return name


def teams_match(name_a, name_b):
    def _nv2(name):
        name = name.lower().strip()
        name = re.sub(r'\b(club|de|del|el|los|las|the)\b', ' ', name)
        name = re.sub(r'\s+', ' ', name).strip()
        for o, n in {'é': 'e', 'è': 'e', 'ñ': 'n', 'á': 'a', 'í': 'i', 'ó': 'o', 'ú': 'u',
                     'ö': 'o', 'ü': 'u', 'ä': 'a', 'ß': 'ss', '.': '', '-': '', "'": '',
                     'oe': 'o', 'ue': 'u', 'ae': 'a'}.items():
            name = name.replace(o, n)
        return name.replace(' ', '')
    a = normalize_name(name_a)
    b = normalize_name(name_b)
    if a in b or b in a:
        return True
    if len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5]:
        return True
    a2, b2 = _nv2(name_a), _nv2(name_b)
    if a2 and b2 and len(a2) >= 4 and len(b2) >= 4:
        if a2 in b2 or b2 in a2:
            return True
        if len(a2) >= 5 and len(b2) >= 5 and a2[:5] == b2[:5]:
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



# ─── Hollanda Takımları ───────────────────────────────────────────────────────
DUTCH_TEAM_NORMALIZED = {
    'ajax': 678, 'psv': 674, 'feyenoord': 675,
    'azalkmaar': 676, 'az': 676,
    'utrecht': 679, 'fcutrecht': 679,
    'vitesse': 677, 'twente': 680, 'fctwente': 680,
    'groningen': 682, 'fcgroningen': 682,
    'heerenveen': 683, 'scheerenveen': 683,
    'heracles': 684, 'heraclesalmelo': 684,
    'sparta': 685, 'spartarotterdam': 685,
    'nijmegen': 686, 'nijmegen': 686, 'necnijmegen': 686,
    'waalwijk': 1392, 'rkceagles': 1392,
    'volendam': 1383, 'fcvolendam': 1383,
    'almere': 6806, 'almerecity': 6806,
    'pec': 687, 'peczwolle': 687, 'zwolle': 687,
    'excelsior': 688, 'sbvexcelsior': 688,
    'cambuur': 689, 'sccambuur': 689,
    'denvhaag': 690, 'adovs': 690,
    'gokeen': 691, 'goahead': 691, 'goaheadeagles': 691,
    'emmen': 693, 'fcemmen': 693,
    'fortuna': 694, 'fortunasittard': 694,
    'nac': 340, 'nacbreda': 340,
}


# ─── Portekiz Takımları ───────────────────────────────────────────────────────
PORTUGUESE_TEAM_NORMALIZED = {
    'sporting': 498, 'sportingcp': 498, 'sportinglisbon': 498,
    'porto': 503, 'fcporto': 503,
    'benfica': 499, 'slbenfica': 499,
    'braga': 500, 'scbraga': 500,
    'guimaraes': 5455, 'vitoriaguimaraes': 5455,
    'estoril': 501, 'estorilpraia': 501,
    'famalicao': 5456, 'fcfamalicao': 5456,
    'vizela': 5457, 'fcvizela': 5457,
    'arouca': 5458, 'fcarouca': 5458,
    'portimonense': 502, 'portimoneense': 502,
    'maritimo': 5459, 'csmaritimo': 5459,
    'chaves': 5460, 'gdchaves': 5460,
    'boavista': 504, 'boavistafc': 504,
    'gilvicentfc': 5461, 'gilvicente': 5461,
    'paco': 5462, 'pacosdeferreira': 5462,
    'santaclara': 5463, 'cdsantaclara': 5463,
    'nacional': 5464, 'cdnacional': 5464,
    'casa': 5465, 'casapia': 5465,
    'moreirense': 5466, 'morerense': 5466,
}

# ─── Fransız Takımları ───────────────────────────────────────────────────────
FRENCH_TEAM_NORMALIZED = {
    'psg': 524, 'parissaintgermain': 524, 'parisstgermain': 524,
    'marseille': 516, 'olympiquedemarseille': 516, 'om': 516,
    'lyon': 523, 'olympiquelyon': 523, 'ol': 523,
    'monaco': 548, 'asmonaco': 548,
    'lille': 521, 'losc': 521, 'losclille': 521,
    'lens': 546, 'rclens': 546,
    'rennes': 529, 'staderennais': 529,
    'nice': 522, 'ogcnice': 522,
    'nantes': 543, 'fcnantes': 543,
    'reims': 547, 'stade': 547, 'stadedereims': 547,
    'strasbourg': 527, 'rcstrasbourg': 527,
    'montpellier': 525, 'mhsc': 525, 'montpellierhsc': 525,
    'brest': 3802, 'stade brest': 3802, 'stadebrest': 3802,
    'toulouse': 519, 'tfc': 519, 'toulouse fc': 519,
    'auxerre': 532, 'ajauxerre': 532,
    'angers': 515, 'scoangers': 515,
    'havre': 537, 'lehavre': 537, 'lehavreac': 537,
    'saintétienne': 518, 'saintetienne': 518, 'asse': 518,
    'metz': 544, 'fcmetz': 544,
    'lorient': 542, 'fclорient': 542,
    'clermont': 4063, 'clermontfoot': 4063,
    'troyes': 531, 'estr': 531, 'estroyesac': 531,
    'bordeaux': 514, 'fcgirondins': 514,
    'caen': 543, 'smcaen': 543,
    'guingamp': 541, 'enguingamp': 541,
    'grenoble': 538,
}

# ─── Brezilya Takımları ───────────────────────────────────────────────────────
BRAZILIAN_TEAM_NORMALIZED = {
    'flamengo': 71, 'crflamengo': 71,
    'palmeiras': 72, 'sepalmerias': 72,
    'atleticomineiro': 1062, 'atletico': 1062,
    'fluminense': 73, 'fluminensefc': 73,
    'corinthians': 74, 'sportcorinthians': 74,
    'internacional': 75, 'scinteracional': 75,
    'gremio': 76, 'gremiofc': 76,
    'saopaulofc': 77, 'saopaulo': 77,
    'botafogo': 1836, 'botafogorj': 1836,
    'vasco': 1062, 'vascodagama': 1062,
    'cruzeiro': 1063, 'cruzeiroec': 1063,
    'bahia': 1064, 'ecbahia': 1064,
    'fortaleza': 1065, 'fortalezaec': 1065,
    'atleticoparanaense': 1066, 'athleticoparanaense': 1066, 'athletico': 1066,
    'ceara': 1067, 'cearasc': 1067,
    'sport': 1068, 'sportrecife': 1068,
    'santos': 1069, 'santosfc': 1069,
    'americamineiro': 1070, 'americafutebol': 1070,
    'juventude': 1071, 'ecjuventude': 1071,
    'goias': 1072, 'goiasec': 1072,
    'coritiba': 1073, 'coritibafbc': 1073,
    'avai': 1074, 'avaifc': 1074,
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

def is_dutch_team(team_name):
    return _find_team_id(team_name, DUTCH_TEAM_NORMALIZED) is not None

def is_portuguese_team(team_name):
    return _find_team_id(team_name, PORTUGUESE_TEAM_NORMALIZED) is not None

def is_french_team(team_name):
    return _find_team_id(team_name, FRENCH_TEAM_NORMALIZED) is not None

def is_brazilian_team(team_name):
    return _find_team_id(team_name, BRAZILIAN_TEAM_NORMALIZED) is not None


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
                team_matches.append({'shots': shots, 'shots_on': shots_on, 'corners': corners, 'shots_conceded': shots_conceded})
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
    return {'shots_avg': shots_avg, 'shots_on_target_avg': shots_on_avg, 'corners_avg': corners_avg, 'shots_conceded_avg': shots_conceded_avg, 'shot_accuracy': accuracy, 'matches_used': n}


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
        result = _get_football_data('teams/' + str(team_id) + '/matches', {'status': 'FINISHED', 'limit': last})
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
                    'goals': {'home': m['score']['fullTime']['home'], 'away': m['score']['fullTime']['away']}
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
        result = _get_football_data('teams/' + str(team_id) + '/matches', {'status': 'FINISHED', 'limit': 20})
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
                        'goals': {'home': m['score']['fullTime']['home'], 'away': m['score']['fullTime']['away']}
                    })
            except:
                continue
        return h2h[:last]
    except Exception as e:
        logger.warning('Football-Data H2H failed: ' + str(e))
        return []


# ─── Gerçek H2H (football-data.org /matches/{id}/head2head) ──────────────────

def get_footballdata_match_id(home_team, away_team, league_code):
    """Bugünkü maçlar arasından football-data.org maç ID'sini döndür."""
    if not FOOTBALL_DATA_KEY or not league_code:
        return None
    try:
        today_str = date.today().isoformat()
        result = _get_football_data(
            'competitions/' + league_code + '/matches',
            {'dateFrom': today_str, 'dateTo': today_str}
        )
        if not result or not result.get('matches'):
            return None
        home_norm = normalize_name(home_team)
        away_norm = normalize_name(away_team)
        for m in result['matches']:
            mh = normalize_name(m.get('homeTeam', {}).get('name', ''))
            ma = normalize_name(m.get('awayTeam', {}).get('name', ''))
            if (home_norm in mh or mh in home_norm) and (away_norm in ma or ma in away_norm):
                match_id = m.get('id')
                logger.info(f'Football-data match ID found: {home_team} vs {away_team} -> {match_id}')
                return match_id
        logger.info(f'Football-data match ID not found for {home_team} vs {away_team} in {league_code}')
        return None
    except Exception as e:
        logger.warning(f'get_footballdata_match_id failed ({home_team} vs {away_team}): {e}')
        return None


def get_h2h_footballdata(home_team, away_team, league_code, last=5):
    """football-data.org /matches/{id}/head2head endpoint'inden H2H özeti döndür."""
    if not FOOTBALL_DATA_KEY or not league_code:
        return None
    try:
        match_id = get_footballdata_match_id(home_team, away_team, league_code)
        if not match_id:
            return None
        result = _get_football_data(f'matches/{match_id}/head2head', {'limit': last})
        if not result:
            return None
        matches = result.get('matches', [])
        if not matches:
            return None

        home_wins = 0
        away_wins = 0
        draws = 0
        total_goals = 0
        valid = 0
        home_norm = normalize_name(home_team)

        for m in matches:
            try:
                hs = m['score']['fullTime']['home']
                as_ = m['score']['fullTime']['away']
                if hs is None or as_ is None:
                    continue
                mh_norm = normalize_name(m.get('homeTeam', {}).get('name', ''))
                home_is_home = home_norm in mh_norm or mh_norm in home_norm
                if home_is_home:
                    if hs > as_:
                        home_wins += 1
                    elif hs < as_:
                        away_wins += 1
                    else:
                        draws += 1
                else:
                    if as_ > hs:
                        home_wins += 1
                    elif as_ < hs:
                        away_wins += 1
                    else:
                        draws += 1
                total_goals += hs + as_
                valid += 1
            except (KeyError, TypeError):
                continue

        if valid == 0:
            return None

        avg_goals = round(total_goals / valid, 1)
        summary = {
            'total': valid,
            'home_wins': home_wins,
            'away_wins': away_wins,
            'draws': draws,
            'total_goals': total_goals,
            'avg_goals': avg_goals,
        }
        logger.info(
            f'H2H {home_team} vs {away_team}: {valid} maç | '
            f'Ev {home_wins}G Dep {away_wins}G {draws}B | Ort {avg_goals} gol'
        )
        return summary
    except Exception as e:
        logger.warning(f'get_h2h_footballdata failed ({home_team} vs {away_team}): {e}')
        return None


# ─── Puan Durumu (football-data.org) ─────────────────────────────────────────

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
        total_table = {}
        home_table = {}
        away_table = {}
        for standing in result.get('standings', []):
            stype = standing.get('type')
            for team in standing.get('table', []):
                tname = team.get('team', {}).get('name', '')
                entry = {
                    'position': team.get('position'),
                    'team': tname,
                    'played': team.get('playedGames', 0),
                    'points': team.get('points', 0),
                    'won': team.get('won', 0),
                    'draw': team.get('draw', 0),
                    'lost': team.get('lost', 0),
                    'goals_for': team.get('goalsFor', 0),
                    'goals_against': team.get('goalsAgainst', 0),
                    'goal_diff': team.get('goalDifference', 0),
                }
                if stype == 'TOTAL':
                    total_table[tname] = entry
                elif stype == 'HOME':
                    home_table[tname] = entry
                elif stype == 'AWAY':
                    away_table[tname] = entry

        standings = []
        for tname, entry in total_table.items():
            row = dict(entry)
            if tname in home_table:
                h = home_table[tname]
                row['home_position'] = h['position']
                row['home_won'] = h['won']
                row['home_draw'] = h['draw']
                row['home_lost'] = h['lost']
                row['home_points'] = h['points']
            if tname in away_table:
                a = away_table[tname]
                row['away_position'] = a['position']
                row['away_won'] = a['won']
                row['away_draw'] = a['draw']
                row['away_lost'] = a['lost']
                row['away_points'] = a['points']
            standings.append(row)

        _standings_cache[league_code] = {'date': today, 'data': standings}
        logger.info('Standings cached for ' + league_code + ': ' + str(len(standings)) + ' teams (TOTAL+HOME+AWAY)')
        return standings
    except Exception as e:
        logger.warning('Standings parse failed: ' + str(e))
        return None


# ─── Puan Durumu (CollectAPI) ─────────────────────────────────────────────────

def _get_collectapi_league_key(league_name):
    league_lower = league_name.lower().strip()
    logger.info(f'CollectAPI league key aranıyor: "{league_lower}"')
    for key, collect_key in COLLECT_API_LEAGUE_MAP.items():
        if key in league_lower or league_lower in key:
            logger.info(f'CollectAPI league key bulundu: {collect_key}')
            return collect_key
    logger.info(f'CollectAPI league key bulunamadi: "{league_lower}"')
    return None


def _get_collectapi_standings(league_key):
    if not COLLECT_API_KEY:
        return None
    today = date.today()
    if league_key in _collectapi_standings_cache:
        cached = _collectapi_standings_cache[league_key]
        if cached['date'] == today:
            return cached['data']
    try:
        resp = requests.get(
            f'{COLLECT_API_BASE}/league',
            headers={'authorization': f'apikey {COLLECT_API_KEY}', 'content-type': 'application/json'},
            params={'league': league_key},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list):
            raw_list = data
        elif isinstance(data, dict):
            if not data.get('success'):
                logger.warning(f'CollectAPI standings failed for {league_key}: {data}')
                return None
            raw_list = data.get('result', [])
        else:
            return None
        standings = []
        for item in raw_list:
            standings.append({
                'position': item.get('rank'),
                'team': item.get('team', ''),
                'played': item.get('play', 0),
                'points': item.get('point', 0),
                'won': item.get('win', 0),
                'draw': item.get('draw', 0),
                'lost': item.get('lose', 0),
                'goals_for': item.get('goalfor', 0),
                'goals_against': item.get('goalagainst', 0),
                'goal_diff': item.get('goaldistance', 0),
            })
        _collectapi_standings_cache[league_key] = {'date': today, 'data': standings}
        logger.info(f'CollectAPI standings cached for {league_key}: {len(standings)} teams')
        return standings
    except Exception as e:
        logger.warning(f'CollectAPI standings error for {league_key}: {e}')
        return None


def _find_team_in_standings(team_name, standings):
    if not standings:
        return None
    team_norm = normalize_name(team_name)
    for s in standings:
        s_norm = normalize_name(s['team'])
        if team_norm in s_norm or s_norm in team_norm:
            return s
    return None


def get_team_standing(team_name, country_code, league_name=None):
    logger.info(f'get_team_standing: {team_name} | country_code={country_code} | league_name={league_name}')
    league_code = LEAGUE_CODES.get(country_code)
    if league_code:
        standings = get_standings_cached(league_code)
        if standings:
            clean_name = team_name
            for suffix in [' U21', ' U18', ' U23', ' U19', ' B', ' II', ' Reserves', ' Youth']:
                if clean_name.endswith(suffix):
                    clean_name = clean_name[:-len(suffix)].strip()
                    break
            result = _find_team_in_standings(clean_name, standings) or \
                     _find_team_in_standings(team_name, standings)
            if result:
                home_str = ''
                away_str = ''
                if result.get('home_position') is not None:
                    home_str = f' | HOME {result["home_position"]}. sira {result.get("home_won",0)}G {result.get("home_draw",0)}B {result.get("home_lost",0)}M'
                if result.get('away_position') is not None:
                    away_str = f' | AWAY {result["away_position"]}. sira {result.get("away_won",0)}G {result.get("away_draw",0)}B {result.get("away_lost",0)}M'
                logger.info(
                    f'Standing {team_name}: TOTAL {result["position"]}. sira {result["points"]}p'
                    + home_str + away_str + ' (football-data.org)'
                )
                return result
    if not COLLECT_API_KEY:
        return None
    search_league = league_name or ''
    collect_key = _get_collectapi_league_key(search_league)
    if not collect_key and country_code:
        collect_key = {'TUR': 'super-lig'}.get(country_code)
    if not collect_key:
        return None
    standings = _get_collectapi_standings(collect_key)
    result = _find_team_in_standings(team_name, standings)
    if result:
        logger.info(f'Standing {team_name}: TOTAL {result["position"]}. sira {result["points"]}p (CollectAPI)')
    return result


# ─── Ev/Deplasman Ayrımlı İstatistik ─────────────────────────────────────────

def get_team_home_away_stats(team_name, matches):
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
                home_results.append({'scored': hg, 'conceded': ag, 'result': 'W' if hg > ag else ('D' if hg == ag else 'L')})
            else:
                away_results.append({'scored': ag, 'conceded': hg, 'result': 'W' if ag > hg else ('D' if ag == hg else 'L')})
        except:
            continue
    result = {}
    if home_results:
        result['home_form'] = ''.join([r['result'] for r in home_results[-5:]])
        result['home_goals_avg'] = round(sum(r['scored'] for r in home_results) / len(home_results), 1)
        result['home_conceded_avg'] = round(sum(r['conceded'] for r in home_results) / len(home_results), 1)
    else:
        result['home_form'] = ''; result['home_goals_avg'] = 0; result['home_conceded_avg'] = 0
    if away_results:
        result['away_form'] = ''.join([r['result'] for r in away_results[-5:]])
        result['away_goals_avg'] = round(sum(r['scored'] for r in away_results) / len(away_results), 1)
        result['away_conceded_avg'] = round(sum(r['conceded'] for r in away_results) / len(away_results), 1)
    else:
        result['away_form'] = ''; result['away_goals_avg'] = 0; result['away_conceded_avg'] = 0
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
                'teams': {'home': {'id': 0, 'name': home}, 'away': {'id': 0, 'name': away}},
                'goals': {'home': None, 'away': None}
            })
        logger.info('ClubElo fixtures today: ' + str(len(fixtures)) + ' matches')
        return fixtures
    except Exception as e:
        logger.error('ClubElo fixtures fetch failed: ' + str(e))
        return []


# ─── Ana Fonksiyonlar ─────────────────────────────────────────────────────────

def get_team_last_matches(team_name, last=10):
    if is_youth_or_reserve(team_name):
        logger.info(f'Youth/reserve team skipped for stats: {team_name}')
        return []
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
    if is_dutch_team(team_name):
        team_id = _find_team_id(team_name, DUTCH_TEAM_NORMALIZED)
        if team_id:
            return _footballdata_last_matches(team_id, team_name, last)
        return []
    if is_portuguese_team(team_name):
        team_id = _find_team_id(team_name, PORTUGUESE_TEAM_NORMALIZED)
        if team_id:
            return _footballdata_last_matches(team_id, team_name, last)
        return []
    if is_french_team(team_name):
        team_id = _find_team_id(team_name, FRENCH_TEAM_NORMALIZED)
        if team_id:
            return _footballdata_last_matches(team_id, team_name, last)
        return []
    if is_brazilian_team(team_name):
        team_id = _find_team_id(team_name, BRAZILIAN_TEAM_NORMALIZED)
        if team_id:
            return _footballdata_last_matches(team_id, team_name, last)
        return []
    logger.info('No stats source for ' + team_name + ', using ClubElo only')
    return []


def get_h2h(team1_name, team2_name, last=5):
    if is_youth_or_reserve(team1_name) or is_youth_or_reserve(team2_name):
        logger.info(f'Youth/reserve team H2H skipped: {team1_name} vs {team2_name}')
        return []
    if is_german_team(team1_name) or is_german_team(team2_name):
        team_id = _find_team_id(team1_name, GERMAN_TEAM_NORMALIZED) or _find_team_id(team2_name, GERMAN_TEAM_NORMALIZED)
        if team_id:
            return _footballdata_h2h(team_id, team1_name, team2_name, last)
        return []
    if is_english_team(team1_name) or is_english_team(team2_name):
        team_id = _find_team_id(team1_name, ENGLISH_TEAM_NORMALIZED) or _find_team_id(team2_name, ENGLISH_TEAM_NORMALIZED)
        if team_id:
            return _footballdata_h2h(team_id, team1_name, team2_name, last)
        return []
    if is_spanish_team(team1_name) or is_spanish_team(team2_name):
        team_id = _find_team_id(team1_name, SPANISH_TEAM_NORMALIZED) or _find_team_id(team2_name, SPANISH_TEAM_NORMALIZED)
        if team_id:
            return _footballdata_h2h(team_id, team1_name, team2_name, last)
        return []
    if is_italian_team(team1_name) or is_italian_team(team2_name):
        team_id = _find_team_id(team1_name, ITALIAN_TEAM_NORMALIZED) or _find_team_id(team2_name, ITALIAN_TEAM_NORMALIZED)
        if team_id:
            return _footballdata_h2h(team_id, team1_name, team2_name, last)
        return []
    if is_dutch_team(team1_name) or is_dutch_team(team2_name):
        team_id = _find_team_id(team1_name, DUTCH_TEAM_NORMALIZED) or _find_team_id(team2_name, DUTCH_TEAM_NORMALIZED)
        if team_id:
            return _footballdata_h2h(team_id, team1_name, team2_name, last)
        return []
    if is_portuguese_team(team1_name) or is_portuguese_team(team2_name):
        team_id = _find_team_id(team1_name, PORTUGUESE_TEAM_NORMALIZED) or _find_team_id(team2_name, PORTUGUESE_TEAM_NORMALIZED)
        if team_id:
            return _footballdata_h2h(team_id, team1_name, team2_name, last)
        return []
    if is_french_team(team1_name) or is_french_team(team2_name):
        team_id = _find_team_id(team1_name, FRENCH_TEAM_NORMALIZED) or _find_team_id(team2_name, FRENCH_TEAM_NORMALIZED)
        if team_id:
            return _footballdata_h2h(team_id, team1_name, team2_name, last)
        return []
    if is_brazilian_team(team1_name) or is_brazilian_team(team2_name):
        team_id = _find_team_id(team1_name, BRAZILIAN_TEAM_NORMALIZED) or _find_team_id(team2_name, BRAZILIAN_TEAM_NORMALIZED)
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


# ─── API-Football ─────────────────────────────────────────────────────────────
API_FOOTBALL_KEY = os.environ.get('API_FOOTBALL_KEY', '')
API_FOOTBALL_BASE = 'https://v3.football.api-sports.io'
API_FOOTBALL_HEADERS = {'x-apisports-key': API_FOOTBALL_KEY}

API_FOOTBALL_LEAGUE_MAP = {
    'super lig': 203, 'turkey': 203,
    '1. lig': 204, 'tff first league': 204, 'tff 1. lig': 204,
    'pro league': 144, 'belgian pro league': 144, 'first division a': 144, 'belgium': 144,
    'challenger pro league': 145, 'first division b': 145,
    'premiership': 179, 'scottish premiership': 179, 'scotland': 179,
    'scottish championship': 180, 'scottish league one': 181,
    'austrian bundesliga': 218, 'austria': 218,
    'a-league': 188, 'a league': 188, 'australia': 188,
    'a-league women': 190, 'a league women': 190,
    'national league': 43,
    'league one': 41, 'efl league one': 41,
    'league two': 42, 'efl league two': 42,
    'championship': 40, 'efl championship': 40,
    'premier league': 39,
    'superliga': 119, 'danish superliga': 119,
    'eliteserien': 103,
    'allsvenskan': 113,
    'swiss super league': 207,
    'ekstraklasa': 106,
    'greek super league': 233,
    'champions league': 2, 'uefa champions league': 2, 'sampiyonlar ligi': 2,
    'europa league': 3, 'uefa europa league': 3,
    'conference league': 848, 'uefa conference league': 848,
    'eredivisie': 88, 'netherlands': 88, 'dutch': 88, 'holland': 88,
    'eerste divisie': 89,
    'primeira liga': 94, 'portugal': 94, 'liga nos': 94, 'liga bwin': 94,
    'brasileirao': 71, 'serie a brasil': 71, 'brazil': 71, 'bsa': 71, 'brasileiro': 71,
    'la liga': 140, 'laliga': 140, 'spain': 140,
    'serie a': 135, 'italy': 135,
    'bundesliga': 78, 'germany': 78,
    'ligue 1': 61, 'france': 61,
}

_apifootball_standings_cache = {}


def _get_api_football(endpoint, params={}):
    if not API_FOOTBALL_KEY:
        return None
    try:
        time.sleep(1)
        resp = requests.get(
            API_FOOTBALL_BASE + '/' + endpoint,
            headers=API_FOOTBALL_HEADERS,
            params=params,
            timeout=15
        )
        if resp.status_code == 429:
            logger.warning('API-Football rate limit hit')
            time.sleep(3)
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error('API-Football request failed: ' + str(e))
        return None


def _find_league_id(league_name):
    league_lower = league_name.lower()
    for key, lid in API_FOOTBALL_LEAGUE_MAP.items():
        if key in league_lower or league_lower in key:
            return lid
    return None


def _find_team_in_apifootball_standings(team_name, standings):
    if not standings:
        return None
    team_norm = normalize_name(team_name)
    for s in standings:
        s_norm = normalize_name(s['team'])
        if team_norm in s_norm or s_norm in team_norm:
            logger.info('API-Football standing: ' + s['team'] + ' -> ' + str(s['position']) + '. sira, ' + str(s['points']) + ' puan')
            return s
    return None


def get_team_standing_apifootball(team_name, league_name, season=2024):
    if not API_FOOTBALL_KEY:
        return None
    league_id = _find_league_id(league_name)
    if not league_id:
        logger.info('API-Football: league ID not found for ' + league_name)
        return None
    cache_key = str(league_id) + '_' + str(season)
    today = date.today()
    if cache_key in _apifootball_standings_cache:
        cached = _apifootball_standings_cache[cache_key]
        if cached['date'] == today:
            return _find_team_in_apifootball_standings(team_name, cached['data'])
    result = _get_api_football('standings', {'league': league_id, 'season': 2025})
    if not result or not result.get('response'):
        logger.warning('API-Football standings empty for league ' + str(league_id))
        return None
    try:
        standings = []
        for entry in result['response']:
            for group in entry.get('league', {}).get('standings', []):
                for team in group:
                    standings.append({
                        'position': team.get('rank'),
                        'team': team.get('team', {}).get('name', ''),
                        'played': team.get('all', {}).get('played', 0),
                        'points': team.get('points', 0),
                        'won': team.get('all', {}).get('win', 0),
                        'draw': team.get('all', {}).get('draw', 0),
                        'lost': team.get('all', {}).get('lose', 0),
                        'goals_for': team.get('all', {}).get('goals', {}).get('for', 0),
                        'goals_against': team.get('all', {}).get('goals', {}).get('against', 0),
                        'goal_diff': team.get('goalsDiff', 0),
                    })
        _apifootball_standings_cache[cache_key] = {'date': today, 'data': standings}
        logger.info('API-Football standings cached: league ' + str(league_id) + ', ' + str(len(standings)) + ' teams')
        return _find_team_in_apifootball_standings(team_name, standings)
    except Exception as e:
        logger.warning('API-Football standings parse failed: ' + str(e))
        return None


_apifootball_team_id_cache = {}
_apifootball_fixtures_cache = {}

TURKISH_SUPER_LIG_ID = 203
TURKISH_SUPER_LIG_SEASON = 2025


def _get_apifootball_team_id(team_name, league_id=203, season=2025):
    cache_key = normalize_name(team_name)
    if cache_key in _apifootball_team_id_cache:
        return _apifootball_team_id_cache[cache_key]
    result = _get_api_football('teams', {'name': team_name, 'league': league_id, 'season': season})
    if result and result.get('response'):
        for entry in result['response']:
            team_id = entry.get('team', {}).get('id')
            name = entry.get('team', {}).get('name', '')
            if team_id:
                _apifootball_team_id_cache[cache_key] = team_id
                logger.info('API-Football team ID: ' + name + ' -> ' + str(team_id))
                return team_id
    short_name = team_name.split()[0]
    if short_name != team_name:
        result2 = _get_api_football('teams', {'name': short_name, 'league': league_id, 'season': season})
        if result2 and result2.get('response'):
            for entry in result2['response']:
                team_id = entry.get('team', {}).get('id')
                name = entry.get('team', {}).get('name', '')
                if team_id:
                    _apifootball_team_id_cache[cache_key] = team_id
                    logger.info('API-Football team ID (fuzzy): ' + name + ' -> ' + str(team_id))
                    return team_id
    _apifootball_team_id_cache[cache_key] = None
    logger.info('API-Football team ID not found: ' + team_name)
    return None


def _convert_apifootball_fixture(fixture, team_name):
    try:
        home_name = fixture['teams']['home']['name']
        away_name = fixture['teams']['away']['name']
        home_goals = fixture['goals']['home']
        away_goals = fixture['goals']['away']
        if home_goals is None or away_goals is None:
            return None
        return {
            'teams': {
                'home': {'name': home_name, 'id': fixture['teams']['home']['id']},
                'away': {'name': away_name, 'id': fixture['teams']['away']['id']},
            },
            'goals': {'home': int(home_goals), 'away': int(away_goals)}
        }
    except Exception:
        return None


def get_team_last_matches_apifootball(team_name, league_id=203, season=2025, last=10):
    if not API_FOOTBALL_KEY:
        return []
    team_id = _get_apifootball_team_id(team_name, league_id, season)
    if not team_id:
        return []
    result = _get_api_football('fixtures', {
        'team': team_id, 'league': league_id, 'season': season, 'last': last, 'status': 'FT'
    })
    if not result or not result.get('response'):
        return []
    matches = []
    for fix in result['response']:
        converted = _convert_apifootball_fixture(fix, team_name)
        if converted:
            matches.append(converted)
    logger.info('API-Football last matches: ' + team_name + ' -> ' + str(len(matches)) + ' mac')
    return matches


def get_h2h_apifootball(team1_name, team2_name, league_id=203, season=2025, last=5):
    if not API_FOOTBALL_KEY:
        return []
    team1_id = _get_apifootball_team_id(team1_name, league_id, season)
    team2_id = _get_apifootball_team_id(team2_name, league_id, season)
    if not team1_id or not team2_id:
        return []
    result = _get_api_football('fixtures/headtohead', {'h2h': str(team1_id) + '-' + str(team2_id), 'last': last})
    if not result or not result.get('response'):
        return []
    matches = []
    for fix in result['response']:
        converted = _convert_apifootball_fixture(fix, team1_name)
        if converted:
            matches.append(converted)
    logger.info('API-Football H2H: ' + team1_name + ' vs ' + team2_name + ' -> ' + str(len(matches)) + ' mac')
    return matches


def is_turkish_superlig_team(team_name):
    turkish_teams = [
        'galatasaray', 'fenerbahce', 'fenerbahçe', 'besiktas', 'beşiktaş',
        'trabzonspor', 'basaksehir', 'başakşehir', 'sivasspor', 'konyaspor',
        'alanyaspor', 'antalyaspor', 'kayserispor', 'rizespor', 'gaziantep',
        'hatayspor', 'kasimpasa', 'kasımpaşa', 'eyupspor', 'eyüpspor',
        'goztepe', 'göztepe', 'bodrumspor', 'samsunspor', 'ankaragucu', 'ankaragücü',
        'keciorengucu', 'keçiörengücü', 'adana demirspor', 'istanbulspor',
        'umraniyespor', 'ümraniyespor', 'giresunspor',
    ]
    name_lower = team_name.lower()
    for t in turkish_teams:
        if t in name_lower or name_lower in t:
            return True
    return False
