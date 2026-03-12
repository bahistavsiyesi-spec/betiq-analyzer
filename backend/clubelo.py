import requests
import logging
import csv
import io
from datetime import datetime

logger = logging.getLogger(__name__)

CLUBELO_BASE = 'http://api.clubelo.com'

def get_team_elo(team_name):
    formatted = team_name.replace(' ', '').replace('-', '')
    try:
        resp = requests.get(f"{CLUBELO_BASE}/{formatted}", timeout=10)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        if not rows:
            return None
        latest = rows[-1]
        return {
            'team': latest.get('Club', team_name),
            'elo': round(float(latest.get('Elo', 0))),
            'rank': latest.get('Rank', '?'),
            'country': latest.get('Country', ''),
            'level': latest.get('Level', ''),
            'from': latest.get('From', ''),
            'to': latest.get('To', ''),
        }
    except Exception as e:
        logger.warning(f"ClubElo error for {team_name}: {e}")
        return None

def get_fixtures_elo():
    try:
        resp = requests.get(f"{CLUBELO_BASE}/Fixtures", timeout=10)
        resp.raise_for_status()
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        if rows:
            logger.info(f"ClubElo fixtures columns: {list(rows[0].keys())}")
        return rows
    except Exception as e:
        logger.warning(f"ClubElo fixtures error: {e}")
        return []

def find_match_in_fixtures(home_team, away_team, fixtures=None):
    if fixtures is None:
        fixtures = get_fixtures_elo()

    home_lower = home_team.lower().replace(' ', '').replace('-', '')
    away_lower = away_team.lower().replace(' ', '').replace('-', '')

    for f in fixtures:
        fh = f.get('Home', '').lower().replace(' ', '').replace('-', '')
        fa = f.get('Away', '').lower().replace(' ', '').replace('-', '')
        if home_lower in fh or fh in home_lower:
            if away_lower in fa or fa in away_lower:
                logger.info(f"ClubElo raw row: {dict(f)}")
                try:
                    home_elo = float(f.get('EloHome') or f.get('Elo Home') or f.get('elo_home') or 0)
                    away_elo = float(f.get('EloAway') or f.get('Elo Away') or f.get('elo_away') or 0)
                    prob_home = float(f.get('ProbHome') or f.get('Prob Home') or f.get('prob_home') or 0)
                    prob_draw = float(f.get('ProbDraw') or f.get('Prob Draw') or f.get('prob_draw') or 0)
                    prob_away = float(f.get('ProbAway') or f.get('Prob Away') or f.get('prob_away') or 0)
                    return {
                        'home_elo': round(home_elo),
                        'away_elo': round(away_elo),
                        'prob_home': round(prob_home * 100, 1),
                        'prob_draw': round(prob_draw * 100, 1),
                        'prob_away': round(prob_away * 100, 1),
                    }
                except Exception as e:
                    logger.warning(f"ClubElo parse error: {e}")
                    return None
    return None

def get_elo_for_match(home_team, away_team):
    fixtures = get_fixtures_elo()
    match_data = find_match_in_fixtures(home_team, away_team, fixtures)
    if match_data:
        logger.info(f"ClubElo fixtures found: {home_team} vs {away_team}")
        return match_data

    home_elo = get_team_elo(home_team)
    away_elo = get_team_elo(away_team)

    if not home_elo and not away_elo:
        return None

    result = {}
    if home_elo:
        result['home_elo'] = home_elo['elo']
        result['home_country'] = home_elo['country']
    if away_elo:
        result['away_elo'] = away_elo['elo']
        result['away_country'] = away_elo['country']

    if home_elo and away_elo:
        dr = home_elo['elo'] - away_elo['elo']
        prob_home = round(1 / (10 ** (-dr / 400) + 1) * 100, 1)
        prob_away = round(1 / (10 ** (dr / 400) + 1) * 100, 1)
        prob_draw = round(max(100 - prob_home - prob_away, 0), 1)
        result['prob_home'] = prob_home
        result['prob_draw'] = prob_draw
        result['prob_away'] = prob_away

    logger.info(f"ClubElo individual: {home_team} {result.get('home_elo','?')} vs {away_team} {result.get('away_elo','?')}")
    return result if result else None
```

Şimdi bir analiz yaptır, Render logunda şunu göreceksin:
```
ClubElo fixtures columns: ['Home', 'Away', 'EloHome', ...]
ClubElo raw row: {'Home': 'Samsunspor', 'Away': 'Rayo', ...}
