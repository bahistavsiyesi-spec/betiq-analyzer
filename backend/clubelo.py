import requests
import logging
import csv
import io

logger = logging.getLogger(__name__)

CLUBELO_BASE = 'http://api.clubelo.com'


def get_team_elo(team_name):
    formatted = team_name.replace(' ', '').replace('-', '')
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

    for f in fixtures:
        fh = f.get('Home', '').lower().replace(' ', '').replace('-', '')
        fa = f.get('Away', '').lower().replace(' ', '').replace('-', '')
        if (home_lower in fh or fh in home_lower) and (away_lower in fa or fa in away_lower):
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
    # Önce fixtures'dan olasılıkları al
    fixtures = get_fixtures_elo()
    match_data = find_match_in_fixtures(home_team, away_team, fixtures)

    # Takım Elo puanlarını ayrı çek
    home_elo = get_team_elo(home_team)
    away_elo = get_team_elo(away_team)

    result = match_data or {}

    if home_elo:
        result['home_elo'] = home_elo['elo']
    if away_elo:
        result['away_elo'] = away_elo['elo']

    # Elo puanları var ama olasılık yoksa hesapla
    if home_elo and away_elo and 'prob_home' not in result:
        dr = home_elo['elo'] - away_elo['elo']
        prob_home = round(1 / (10 ** (-dr / 400) + 1) * 100, 1)
        prob_away = round(1 / (10 ** (dr / 400) + 1) * 100, 1)
        prob_draw = round(max(100 - prob_home - prob_away, 0), 1)
        result['prob_home'] = prob_home
        result['prob_draw'] = prob_draw
        result['prob_away'] = prob_away

    if result:
        logger.info('ClubElo final: ' + home_team + ' elo=' + str(result.get('home_elo', '?')) + ' vs ' + away_team + ' elo=' + str(result.get('away_elo', '?')))
        return result

    return None
