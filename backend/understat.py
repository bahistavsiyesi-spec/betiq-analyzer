import requests
from bs4 import BeautifulSoup
import json
import re
import logging
from datetime import date

logger = logging.getLogger(__name__)

# ─── Cache (günlük) ───────────────────────────────────────────────────────────
_xg_cache = {}

# ─── Takım ismi → Understat URL ismi ─────────────────────────────────────────
UNDERSTAT_NAMES = {
    # İngiltere
    'Arsenal': 'Arsenal',
    'Aston Villa': 'Aston_Villa',
    'Bournemouth': 'Bournemouth',
    'Brentford': 'Brentford',
    'Brighton': 'Brighton',
    'Chelsea': 'Chelsea',
    'Crystal Palace': 'Crystal_Palace',
    'Everton': 'Everton',
    'Fulham': 'Fulham',
    'Ipswich': 'Ipswich',
    'Leicester': 'Leicester',
    'Liverpool': 'Liverpool',
    'Manchester City': 'Manchester_City',
    'Man City': 'Manchester_City',
    'Manchester United': 'Manchester_United',
    'Man United': 'Manchester_United',
    'Newcastle': 'Newcastle_United',
    'Newcastle United': 'Newcastle_United',
    'Nottingham Forest': 'Nottingham_Forest',
    'Forest': 'Nottingham_Forest',
    'Southampton': 'Southampton',
    'Tottenham': 'Tottenham',
    'West Ham': 'West_Ham',
    'Wolverhampton': 'Wolverhampton_Wanderers',
    'Wolves': 'Wolverhampton_Wanderers',
    # Almanya
    'Bayern': 'Bayern_Munich',
    'Dortmund': 'Borussia_Dortmund',
    'Leverkusen': 'Bayer_Leverkusen',
    'Leipzig': 'RasenBallsport_Leipzig',
    'RB Leipzig': 'RasenBallsport_Leipzig',
    'Frankfurt': 'Eintracht_Frankfurt',
    'Stuttgart': 'VfB_Stuttgart',
    'Freiburg': 'SC_Freiburg',
    'Hoffenheim': 'Hoffenheim',
    'Bremen': 'Werder_Bremen',
    'Wolfsburg': 'Wolfsburg',
    'Gladbach': 'Borussia_Monchengladbach',
    'Augsburg': 'Augsburg',
    'Union Berlin': 'Union_Berlin',
    'Mainz': 'Mainz_05',
    'Bochum': 'Bochum',
    # İspanya
    'Barcelona': 'Barcelona',
    'Real Madrid': 'Real_Madrid',
    'Atletico': 'Atletico_Madrid',
    'Atlético Madrid': 'Atletico_Madrid',
    'Athletic Club': 'Athletic_Club',
    'Real Sociedad': 'Real_Sociedad',
    'Villarreal': 'Villarreal',
    'Real Betis': 'Real_Betis',
    'Valencia': 'Valencia',
    'Girona': 'Girona',
    'Sevilla': 'Sevilla',
    'Osasuna': 'Osasuna',
    'Getafe': 'Getafe',
    'Celta': 'Celta_Vigo',
    'Celta Vigo': 'Celta_Vigo',
    'Rayo': 'Rayo_Vallecano',
    'Rayo Vallecano': 'Rayo_Vallecano',
    'Mallorca': 'Mallorca',
    'Espanyol': 'Espanyol',
    # İtalya
    'AC Milan': 'AC_Milan',
    'Milan': 'AC_Milan',
    'Inter': 'Internazionale',
    'Juventus': 'Juventus',
    'Napoli': 'Napoli',
    'Atalanta': 'Atalanta',
    'Roma': 'Roma',
    'AS Roma': 'Roma',
    'Lazio': 'Lazio',
    'Fiorentina': 'Fiorentina',
    'Bologna': 'Bologna',
    'Torino': 'Torino',
    'Udinese': 'Udinese',
    'Genoa': 'Genoa',
    'Cagliari': 'Cagliari',
    'Lecce': 'Lecce',
    'Verona': 'Hellas_Verona',
    # Fransa
    'Paris Saint-Germain': 'Paris_Saint_Germain',
    'Lyon': 'Lyon',
    'Marseille': 'Marseille',
    'Monaco': 'Monaco',
    'Lille': 'Lille',
    'Nice': 'Nice',
    'Lens': 'Lens',
    'Rennes': 'Rennes',
    'Strasbourg': 'Strasbourg',
    'Nantes': 'Nantes',
}

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}


def _get_understat_name(team_name):
    if team_name in UNDERSTAT_NAMES:
        return UNDERSTAT_NAMES[team_name]
    lower = team_name.lower()
    for key, val in UNDERSTAT_NAMES.items():
        if key.lower() in lower or lower in key.lower():
            return val
    return None


def _fetch_team_xg_data(understat_name, season='2024'):
    today = date.today()
    cache_key = f'{understat_name}_{season}'

    if cache_key in _xg_cache:
        cached = _xg_cache[cache_key]
        if cached['date'] == today:
            return cached['data']

    url = f'https://understat.com/team/{understat_name}/{season}'

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, 'html.parser')
        scripts = soup.find_all('script')

        # Script içeriklerini logla — debug için
        script_vars = []
        for script in scripts:
            if script.string:
                # Tüm JSON.parse çağrılarını bul
                vars_found = re.findall(r'(\w+)\s*=\s*JSON\.parse\(', script.string)
                script_vars.extend(vars_found)

        logger.info(f'Understat script vars for {understat_name}: {script_vars}')

        for script in scripts:
            if not script.string:
                continue

            # Pattern 1: datesData = JSON.parse('...')
            match = re.search(r"datesData\s*=\s*JSON\.parse\('(.+?)'\)", script.string)
            if match:
                raw = match.group(1)
                raw = raw.encode('utf-8').decode('unicode_escape')
                data = json.loads(raw)
                _xg_cache[cache_key] = {'date': today, 'data': data}
                logger.info(f'Understat: {len(data)} matches loaded for {understat_name} (pattern1)')
                return data

            # Pattern 2: JSON.parse ile çift tırnak
            match = re.search(r'datesData\s*=\s*JSON\.parse\("(.+?)"\)', script.string)
            if match:
                raw = match.group(1)
                data = json.loads(raw)
                _xg_cache[cache_key] = {'date': today, 'data': data}
                logger.info(f'Understat: {len(data)} matches loaded for {understat_name} (pattern2)')
                return data

            # Pattern 3: Doğrudan atama (JSON.parse olmadan)
            match = re.search(r'datesData\s*=\s*(\[.+?\]);', script.string, re.DOTALL)
            if match:
                data = json.loads(match.group(1))
                _xg_cache[cache_key] = {'date': today, 'data': data}
                logger.info(f'Understat: {len(data)} matches loaded for {understat_name} (pattern3)')
                return data

        logger.warning(f'Understat: no matching pattern for {understat_name}. Available vars: {script_vars}')
        return None

    except Exception as e:
        logger.warning(f'Understat fetch failed for {understat_name}: {e}')
        return None


def get_team_xg_stats(team_name, last=5, season='2024'):
    """
    Takımın son N maçının xG istatistiklerini döndür.
    """
    understat_name = _get_understat_name(team_name)
    if not understat_name:
        logger.info(f'Understat: no mapping for {team_name}')
        return None

    data = _fetch_team_xg_data(understat_name, season)
    if not data:
        return None

    played = [m for m in data if m.get('isResult')]
    if not played:
        return None

    recent = played[-last:]
    n = len(recent)

    xg_list = []
    xga_list = []
    goals_list = []

    for m in recent:
        try:
            xg_list.append(float(m.get('xG', 0) or 0))
            xga_list.append(float(m.get('xGA', 0) or 0))
            goals_list.append(int(m.get('scored', 0) or 0))
        except:
            continue

    if not xg_list:
        return None

    xg_avg = round(sum(xg_list) / n, 2)
    xga_avg = round(sum(xga_list) / n, 2)
    xg_diff = round(xg_avg - xga_avg, 2)
    goals_avg = round(sum(goals_list) / n, 2)
    xg_overperform = round(goals_avg - xg_avg, 2)

    logger.info(f'Understat xG {team_name}: xG={xg_avg}, xGA={xga_avg}, diff={xg_diff} (son {n} maç)')

    return {
        'xg_avg': xg_avg,
        'xga_avg': xga_avg,
        'xg_diff': xg_diff,
        'xg_overperform': xg_overperform,
        'matches_used': n,
    }
