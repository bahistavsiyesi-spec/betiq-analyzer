import logging
import json
import time
import requests
import os
from datetime import datetime
from backend.football_api import (
    get_todays_fixtures, get_h2h, get_team_last_matches, search_team
)
from backend.database import save_analysis, delete_analyses_by_fixture_ids, log_run

logger = logging.getLogger(__name__)

ODDS_API_KEY = os.environ.get('ODDS_API_KEY', '')

def get_odds_for_match(home_team, away_team):
    if not ODDS_API_KEY:
        return None
    try:
        resp = requests.get(
            'https://api.the-odds-api.com/v4/sports/soccer/odds',
            params={
                'apiKey': ODDS_API_KEY,
                'regions': 'eu,uk',
                'markets': 'h2h',
                'oddsFormat': 'decimal',
            },
            timeout=10
        )
        if resp.status_code != 200:
            logger.warning('Odds API error: ' + str(resp.status_code))
            return None

        data = resp.json()
        home_lower = home_team.lower().replace(' ', '')
        away_lower = away_team.lower().replace(' ', '')

        for game in data:
            gh = game.get('home_team', '').lower().replace(' ', '')
            ga = game.get('away_team', '').lower().replace(' ', '')
            if (home_lower in gh or gh in home_lower) and (away_lower in ga or ga in away_lower):
                bookmakers = game.get('bookmakers', [])
                if not bookmakers:
                    continue
                all_home = []
                all_draw = []
                all_away = []
                for bm in bookmakers:
                    for market in bm.get('markets', []):
                        if market.get('key') != 'h2h':
                            continue
                        for outcome in market.get('outcomes', []):
                            name = outcome.get('name', '').lower().replace(' ', '')
                            price = outcome.get('price', 0)
                            if name in gh or gh in name:
                                all_home.append(price)
                            elif name in ga or ga in name:
                                all_away.append(price)
                            else:
                                all_draw.append(price)

                if all_home and all_away:
                    avg_home = round(sum(all_home) / len(all_home), 2)
                    avg_draw = round(sum(all_draw) / len(all_draw), 2) if all_draw else None
                    avg_away = round(sum(all_away) / len(all_away), 2)
                    logger.info('Odds: ' + home_team + ' ' + str(avg_home) + ' | Draw ' + str(avg_draw) + ' | ' + away_team + ' ' + str(avg_away))
                    return {
                        'home_odds': avg_home,
                        'draw_odds': avg_draw,
                        'away_odds': avg_away,
                        'bookmaker_count': len(bookmakers)
                    }
        logger.info('Odds: no match found for ' + home_team + ' vs ' + away_team)
        return None
    except Exception as e:
        logger.warning('Odds API failed: ' + str(e))
        return None

def extract_form_from_fixtures(matches, team_name):
    form = []
    for m in matches[-5:]:
        try:
            home_name = m['teams']['home']['name']
            home_goals = m['goals']['home'] or 0
            away_goals = m['goals']['away'] or 0
            is_home = team_name.lower() in home_name.lower()
            if is_home:
                if home_goals > away_goals: form.append('W')
                elif home_goals == away_goals: form.append('D')
                else: form.append('L')
            else:
                if away_goals > home_goals: form.append('W')
                elif away_goals == home_goals: form.append('D')
                else: form.append('L')
        except:
            continue
    return ''.join(form)

def extract_goals_avg(matches, team_name):
    scored = []
    conceded = []
    for m in matches:
        try:
            home_name = m['teams']['home']['name']
            home_goals = m['goals']['home'] or 0
            away_goals = m['goals']['away'] or 0
            is_home = team_name.lower() in home_name.lower()
            if is_home:
                scored.append(home_goals)
                conceded.append(away_goals)
            else:
                scored.append(away_goals)
                conceded.append(home_goals)
        except:
            continue
    avg_scored = round(sum(scored)/len(scored), 1) if scored else 0
    avg_conceded = round(sum(conceded)/len(conceded), 1) if conceded else 0
    return avg_scored, avg_conceded

def extract_h2h_summary(h2h_matches, home_team, away_team):
    if not h2h_matches:
        return None
    home_wins = 0
    away_wins = 0
    draws = 0
    total_goals = 0
    for m in h2h_matches:
        try:
            match_home = m['teams']['home']['name']
            hg = m['goals']['home'] or 0
            ag = m['goals']['away'] or 0
            total_goals += hg + ag
            is_our_home = home_team.lower().split()[0] in match_home.lower()
            if hg > ag:
                if is_our_home: home_wins += 1
                else: away_wins += 1
            elif hg < ag:
                if is_our_home: away_wins += 1
                else: home_wins += 1
            else:
                draws += 1
        except:
            continue
    total = len(h2h_matches)
    avg_goals = round(total_goals / total, 1) if total else 0
    return {
        'home_wins': home_wins,
        'away_wins': away_wins,
        'draws': draws,
        'total': total,
        'avg_goals': avg_goals
    }

def analyze_fixture(fixture):
    from backend.ai_analyzer import analyze_with_claude
    from backend.clubelo import get_elo_for_match

    home_name = fixture['teams']['home']['name']
    away_name = fixture['teams']['away']['name']

    if not home_name or not away_name or home_name == '?' or away_name == '?':
        logger.error('Skipping match with missing team names: ' + str(home_name) + ' vs ' + str(away_name))
        return None

    home_name = str(home_name).strip()
    away_name = str(away_name).strip()

    logger.info('Analyzing: ' + home_name + ' vs ' + away_name)

    home_matches = get_team_last_matches(home_name, last=5)
    away_matches = get_team_last_matches(away_name, last=5)
    h2h = get_h2h(home_name, away_name, last=5)

    home_form = extract_form_from_fixtures(home_matches, home_name)
    away_form = extract_form_from_fixtures(away_matches, away_name)
    home_goals_avg, home_conceded_avg = extract_goals_avg(home_matches, home_name)
    away_goals_avg, away_conceded_avg = extract_goals_avg(away_matches, away_name)
    h2h_summary = extract_h2h_summary(h2h, home_name, away_name)

    # ClubElo verisi
    elo_data = None
    try:
        elo_data = get_elo_for_match(home_name, away_name)
        if elo_data:
            logger.info('ClubElo: ' + home_name + ' ' + str(elo_data.get('home_elo', '?')) + ' vs ' + away_name + ' ' + str(elo_data.get('away_elo', '?')))
        else:
            logger.info('ClubElo: no data for ' + home_name + ' vs ' + away_name)
    except Exception as e:
        logger.warning('ClubElo failed: ' + str(e))

    # Bahis oranları
    odds_data = None
    try:
        odds_data = get_odds_for_match(home_name, away_name)
    except Exception as e:
        logger.warning('Odds failed: ' + str(e))

    logger.info('Stats: ' + home_name + ' form=' + home_form + ' avg=' + str(home_goals_avg) + ', ' + away_name + ' form=' + away_form + ' avg=' + str(away_goals_avg))

    return analyze_with_claude(
        fixture=fixture,
        h2h_data=h2h,
        home_matches=home_matches,
        away_matches=away_matches,
        home_form=home_form,
        away_form=away_form,
        home_goals_avg=home_goals_avg,
        away_goals_avg=away_goals_avg,
        home_conceded_avg=home_conceded_avg,
        away_conceded_avg=away_conceded_avg,
        h2h_summary=h2h_summary,
        elo_data=elo_data,
        odds_data=odds_data
    )

def run_selected_analysis(fixture_ids=[], manual_matches=[]):
    today = datetime.now().strftime('%Y-%m-%d')
    logger.info('Starting selected analysis: ' + str(len(fixture_ids)) + ' fixtures, ' + str(len(manual_matches)) + ' manual')

    try:
        # Sadece yeniden analiz edilecek fixture ID'lerini sil, diğer maçlara dokunma
        if fixture_ids:
            delete_analyses_by_fixture_ids(fixture_ids)

        analyzed = 0

        if fixture_ids:
            all_fixtures = get_todays_fixtures()
            selected = [f for f in all_fixtures if f['fixture']['id'] in fixture_ids]
            for fixture in selected:
                try:
                    analysis = analyze_fixture(fixture)
                    if analysis:
                        save_analysis(analysis)
                        analyzed += 1
                    time.sleep(1)
                except Exception as e:
                    logger.error('Error analyzing fixture: ' + str(e))
                    continue

        for m in manual_matches:
            try:
                home_team = str(m.get('home_team', '') or '').strip()
                away_team = str(m.get('away_team', '') or '').strip()

                if not home_team or not away_team:
                    logger.error('Skipping manual match with missing teams: ' + str(m))
                    continue

                # Manuel maçlar için fixture_id yok, doğrudan ekle (silme yapma)
                manual_fixture = {
                    'fixture': {'id': 0, 'date': m.get('date', datetime.now().isoformat())},
                    'league': {'id': 0, 'name': m.get('league', 'Manuel Mac')},
                    'teams': {
                        'home': {'id': 0, 'name': home_team},
                        'away': {'id': 0, 'name': away_team}
                    },
                    'goals': {'home': None, 'away': None}
                }
                analysis = analyze_fixture(manual_fixture)
                if analysis:
                    save_analysis(analysis)
                    analyzed += 1
                time.sleep(1)
            except Exception as e:
                logger.error('Error analyzing manual match: ' + str(e))
                continue

        log_run(today, 'success', len(fixture_ids) + len(manual_matches), analyzed)
        logger.info('Done. Analyzed ' + str(analyzed) + ' matches.')

    except Exception as e:
        logger.error('Selected analysis failed: ' + str(e))
        log_run(today, 'error', 0, 0, str(e))
        raise

def run_daily_analysis():
    today = datetime.now().strftime('%Y-%m-%d')
    fixtures = get_todays_fixtures()
    fixture_ids = [f['fixture']['id'] for f in fixtures[:10]]
    run_selected_analysis(fixture_ids=fixture_ids)
