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
        if rows:
            logger.info('ClubElo fixtures columns: ' + str(list(rows[0].keys())))
        return rows
    except Exception as e:
        logger.warning('ClubElo fixtures error: ' + str(e))
        return []


def find_match_in_fixtures(home_team, away_team, fixtures=None):
    if fixtures is None:
        fixtures = get_fixtures_elo()

    home_lower = home_team.lower().replace(' ', '').replace('-', '')
    away_lower = away_team.lower().replace(' ', '').replace('-', '')

    for f in fixtures:
        fh = f.get('Home', '').lower().replace(' ', '').replace('-', '')
        fa = f.get('Away', '').lower().replace(' ', '').replace('-', '')
        if (home_lower in fh or fh in home_lower) and (away_lower in fa or fa in away_lower):
            logger.info('ClubElo raw row: ' + str(dict(f)))
            try:
                keys = list(f.keys())
                home_elo_val = 0
                away_elo_val = 0
                prob_home_val = 0
                prob_draw_val = 0
                prob_away_val = 0
                for k in keys:
                    kl = k.lower().replace(' ', '')
                    if kl == 'elohome':
                        home_elo_val = float(f[k] or 0)
                    if kl == 'eloaway':
                        away_elo_val = float(f[k] or 0)
                    if kl == 'probhome':
                        prob_home_val = float(f[k] or 0)
                    if kl == 'probdraw':
                        prob_draw_val = float(f[k] or 0)
                    if kl == 'probaway':
                        prob_away_val = float(f[k] or 0)
                return {
                    'home_elo': round(home_elo_val),
                    'away_elo': round(away_elo_val),
                    'prob_home': round(prob_home_val * 100, 1),
                    'prob_draw': round(prob_draw_val * 100, 1),
                    'prob_away': round(prob_away_val * 100, 1),
                }
            except Exception as e:
                logger.warning('ClubElo parse error: ' + str(e))
                return None
    return None


def get_elo_for_match(home_team, away_team):
    fixtures = get_fixtures_elo()
    match_data = find_match_in_fixtures(home_team, away_team, fixtures)
    if match_data:
        logger.info('ClubElo fixtures found: ' + home_team + ' vs ' + away_team)
        return match_data

    home_elo = get_team_elo(home_team)
    away_elo = get_team_elo(away_team)

    if not home_elo and not away_elo:
        return None

    result = {}
    if home_elo:
        result['home_elo'] = home_elo['elo']
    if away_elo:
        result['away_elo'] = away_elo['elo']

    if home_elo and away_elo:
        dr = home_elo['elo'] - away_elo['elo']
        prob_home = round(1 / (10 ** (-dr / 400) + 1) * 100, 1)
        prob_away = round(1 / (10 ** (dr / 400) + 1) * 100, 1)
        prob_draw = round(max(100 - prob_home - prob_away, 0), 1)
        result['prob_home'] = prob_home
        result['prob_draw'] = prob_draw
        result['prob_away'] = prob_away

    logger.info('ClubElo individual: ' + home_team + ' ' + str(result.get('home_elo', '?')) + ' vs ' + away_team + ' ' + str(result.get('away_elo', '?')))
    return result if result else None
