import requests
import logging
import csv
import io
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

CLUBELO_BASE = 'http://api.clubelo.com'

# Güzel isim → ClubElo API'nin beklediği ASCII isim
# NAME_FIXES ile düzelttiğimiz isimleri geri çeviriyoruz
CLUBELO_API_NAMES = {
    # Türkiye
    'Başakşehir': 'Bueyueksehir',
    'Beşiktaş': 'Besiktas',
    'Fenerbahçe': 'Fenerbahce',
    'Kasımpaşa': 'Kasimpasa',
    'Eyüpspor': 'Eyupspor',
    'Göztepe': 'Goztepe',
    'Ankaragücü': 'Ankaragucu',
    'Keçiörengücü': 'Keciorengucu',
    'İstanbulspor': 'Istanbulspor',
    # Almanya
    'Köln': 'Koeln',
    'Nürnberg': 'Nuernberg',
    'Fürth': 'Fuerth',
    'Düsseldorf': 'Duesseldorf',
    'Mönchengladbach': 'Moenchengladbach',
    'Münster': 'Muenster',
    'Saarbrücken': 'Saarbruecken',
    'Osnabrück': 'Osnabrueck',
    # İspanya
    'Atlético Madrid': 'Atletico',
    'Cádiz': 'Cadiz',
    'Almería': 'Almeria',
    'Málaga': 'Malaga',
    'Leganés': 'Leganes',
    'Córdoba': 'Cordoba',
    # Fransa
    'Paris Saint-Germain': 'ParisSG',
    'Saint-Étienne': 'SaintEtienne',
    # Portekiz
    'Sporting CP': 'Sporting',
}


def _to_clubelo_name(team_name):
    """Takım ismini ClubElo API formatına çevir."""
    # Önce özel isim tablosuna bak
    api_name = CLUBELO_API_NAMES.get(team_name, team_name)
    # Boşluk ve tire kaldır
    return api_name.replace(' ', '').replace('-', '')


def get_team_elo(team_name):
    formatted = _to_clubelo_name(team_name)
    try:
        resp = requests.get(CLUBELO_BASE + '/' + formatted, timeout=10)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        if not rows:
            return None
        latest = rows[-1]
        return {
            'team': latest.get('Club', team_name),
            'elo': round(float(latest.get('Elo', 0))),
            'country': latest.get('Country', ''),
        }
    except Exception as e:
        logger.warning('ClubElo error for ' + team_name + ': ' + str(e))
        return None


def get_team_elo_trend(team_name, days=90):
    """
    Son X günün Elo geçmişini çekip form trendi hesapla.
    Döndürür:
    - elo_current: güncel Elo
    - elo_30d_ago: 30 gün önceki Elo
    - elo_90d_ago: 90 gün önceki Elo
    - trend_30d: son 30 günlük değişim (+/-)
    - trend_90d: son 90 günlük değişim (+/-)
    - trend_label: 'Yükselen', 'Düşen', 'Stabil'
    """
    formatted = _to_clubelo_name(team_name)
    try:
        resp = requests.get(CLUBELO_BASE + '/' + formatted, timeout=10)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        if not rows:
            return None

        today = datetime.now().date()
        date_30d = today - timedelta(days=30)
        date_90d = today - timedelta(days=90)

        elo_current = None
        elo_30d = None
        elo_90d = None

        for row in rows:
            try:
                row_from = datetime.strptime(row.get('From', ''), '%Y-%m-%d').date()
                row_to_str = row.get('To', '')
                row_to = datetime.strptime(row_to_str, '%Y-%m-%d').date() if row_to_str else today
                elo_val = round(float(row.get('Elo', 0)))

                if row_from <= today <= row_to:
                    elo_current = elo_val
                if row_from <= date_30d <= row_to:
                    elo_30d = elo_val
                if row_from <= date_90d <= row_to:
                    elo_90d = elo_val
            except:
                continue

        if not elo_current:
            try:
                elo_current = round(float(rows[-1].get('Elo', 0)))
            except:
                return None

        if not elo_30d and len(rows) >= 2:
            try:
                elo_30d = round(float(rows[-2].get('Elo', 0)))
            except:
                elo_30d = elo_current

        if not elo_90d:
            elo_90d = elo_30d or elo_current

        trend_30d = elo_current - elo_30d if elo_30d else 0
        trend_90d = elo_current - elo_90d if elo_90d else 0

        if trend_30d >= 15:
            trend_label = 'Yükselen'
        elif trend_30d <= -15:
            trend_label = 'Düşen'
        else:
            trend_label = 'Stabil'

        logger.info(team_name + ' Elo trend: ' + str(elo_current) + ' (30g: ' + str(trend_30d) + ', 90g: ' + str(trend_90d) + ') => ' + trend_label)

        return {
            'elo_current': elo_current,
            'elo_30d_ago': elo_30d,
            'elo_90d_ago': elo_90d,
            'trend_30d': trend_30d,
            'trend_90d': trend_90d,
            'trend_label': trend_label,
        }
    except Exception as e:
        logger.warning('ClubElo trend error for ' + team_name + ': ' + str(e))
        return None


def get_fixtures_elo():
    try:
        resp = requests.get(CLUBELO_BASE + '/Fixtures', timeout=10)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        return rows
    except Exception as e:
        logger.warning('ClubElo fixtures error: ' + str(e))
        return []


def calc_probs_from_row(f):
    try:
        prob_home = 0.0
        prob_draw = 0.0
        prob_away = 0.0
        for k, v in f.items():
            try:
                val = float(v or 0)
            except:
                continue
            k = k.strip()
            if k == 'GD=0':
                prob_draw += val
            elif k.startswith('GD=') or k.startswith('GD>'):
                try:
                    num = float(k.replace('GD=', '').replace('GD>', ''))
                    if num > 0:
                        prob_home += val
                    elif num < 0:
                        prob_away += val
                except:
                    pass
            elif k.startswith('GD<'):
                try:
                    num = float(k.replace('GD<', ''))
                    if num < 0:
                        prob_away += val
                    elif num > 0:
                        prob_home += val
                except:
                    pass
        return round(prob_home * 100, 1), round(prob_draw * 100, 1), round(prob_away * 100, 1)
    except Exception as e:
        logger.warning('ClubElo prob calc error: ' + str(e))
        return None, None, None


def find_match_in_fixtures(home_team, away_team, fixtures=None):
    if fixtures is None:
        fixtures = get_fixtures_elo()

    home_lower = home_team.lower().replace(' ', '').replace('-', '')
    away_lower = away_team.lower().replace(' ', '').replace('-', '')

    # Ayrıca ClubElo API adıyla da dene
    home_api = _to_clubelo_name(home_team).lower()
    away_api = _to_clubelo_name(away_team).lower()

    for f in fixtures:
        fh = f.get('Home', '').lower().replace(' ', '').replace('-', '')
        fa = f.get('Away', '').lower().replace(' ', '').replace('-', '')
        home_match = (home_lower in fh or fh in home_lower or
                      home_api in fh or fh in home_api)
        away_match = (away_lower in fa or fa in away_lower or
                      away_api in fa or fa in away_api)
        if home_match and away_match:
            prob_home, prob_draw, prob_away = calc_probs_from_row(f)
            if prob_home is not None:
                logger.info('ClubElo probs: ' + home_team + ' %' + str(prob_home) + ' | Draw %' + str(prob_draw) + ' | ' + away_team + ' %' + str(prob_away))
                return {
                    'prob_home': prob_home,
                    'prob_draw': prob_draw,
                    'prob_away': prob_away,
                }
    return None


def get_elo_for_match(home_team, away_team):
    # Fixtures'dan olasılıkları al
    fixtures = get_fixtures_elo()
    match_data = find_match_in_fixtures(home_team, away_team, fixtures)

    # Takım Elo puanları ve form trendleri
    home_elo = get_team_elo(home_team)
    away_elo = get_team_elo(away_team)
    home_trend = get_team_elo_trend(home_team)
    away_trend = get_team_elo_trend(away_team)

    result = match_data or {}

    if home_elo:
        result['home_elo'] = home_elo['elo']
    if away_elo:
        result['away_elo'] = away_elo['elo']

    if home_trend:
        result['home_trend_30d'] = home_trend['trend_30d']
        result['home_trend_90d'] = home_trend['trend_90d']
        result['home_trend_label'] = home_trend['trend_label']
    if away_trend:
        result['away_trend_30d'] = away_trend['trend_30d']
        result['away_trend_90d'] = away_trend['trend_90d']
        result['away_trend_label'] = away_trend['trend_label']

    # Elo var ama olasılık yoksa hesapla
    if home_elo and away_elo and 'prob_home' not in result:
        dr = home_elo['elo'] - away_elo['elo']
        prob_home = round(1 / (10 ** (-dr / 400) + 1) * 100, 1)
        prob_away = round(1 / (10 ** (dr / 400) + 1) * 100, 1)
        prob_draw = round(max(100 - prob_home - prob_away, 0), 1)
        result['prob_home'] = prob_home
        result['prob_draw'] = prob_draw
        result['prob_away'] = prob_away

    if result:
        logger.info('ClubElo final: ' + home_team + ' elo=' + str(result.get('home_elo', '?')) + ' trend=' + str(result.get('home_trend_label', '?')) + ' vs ' + away_team + ' elo=' + str(result.get('away_elo', '?')) + ' trend=' + str(result.get('away_trend_label', '?')))
        return result

    return None
