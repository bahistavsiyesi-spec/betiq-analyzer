import logging
import json
import time
from datetime import datetime
from backend.football_api import (
    get_todays_fixtures, get_h2h, get_team_last_matches
)
from backend.database import save_analysis, clear_today_analyses, log_run

logger = logging.getLogger(__name__)

def extract_form(matches, team_id):
    form = []
    for m in matches[-5:]:
        home_id = m['teams']['home']['id']
        home_goals = m['goals']['home'] or 0
        away_goals = m['goals']['away'] or 0
        if home_id == team_id:
            if home_goals > away_goals: form.append('W')
            elif home_goals == away_goals: form.append('D')
            else: form.append('L')
        else:
            if away_goals > home_goals: form.append('W')
            elif away_goals == home_goals: form.append('D')
            else: form.append('L')
    return ''.join(form[-5:])

def calc_goals_stats(matches, team_id):
    scored, conceded = [], []
    for m in matches:
        home_id = m['teams']['home']['id']
        hg = m['goals']['home'] or 0
        ag = m['goals']['away'] or 0
        if home_id == team_id:
            scored.append(hg)
            conceded.append(ag)
        else:
            scored.append(ag)
            conceded.append(hg)
    avg_scored = round(sum(scored)/len(scored), 2) if scored else 0
    avg_conceded = round(sum(conceded)/len(conceded), 2) if conceded else 0
    return avg_scored, avg_conceded

def calc_home_away_stats(matches, team_id):
    home_stats = {'W': 0, 'D': 0, 'L': 0}
    away_stats = {'W': 0, 'D': 0, 'L': 0}
    for m in matches:
        home_id = m['teams']['home']['id']
        hg = m['goals']['home'] or 0
        ag = m['goals']['away'] or 0
        if home_id == team_id:
            if hg > ag: home_stats['W'] += 1
            elif hg == ag: home_stats['D'] += 1
            else: home_stats['L'] += 1
        else:
            if ag > hg: away_stats['W'] += 1
            elif ag == hg: away_stats['D'] += 1
            else: away_stats['L'] += 1
    return home_stats, away_stats

def score_match(fixture, h2h_data, home_matches, away_matches):
    score = 0
    home_team = fixture['teams']['home']
    away_team = fixture['teams']['away']
    if len(h2h_data) >= 3: score += 20
    if len(home_matches) >= 7: score += 15
    if len(away_matches) >= 7: score += 15
    home_form = extract_form(home_matches, home_team['id'])
    away_form = extract_form(away_matches, away_team['id'])
    if home_form.count('W') >= 3: score += 10
    if away_form.count('L') >= 3: score += 10
    if home_matches:
        hgs, hgc = calc_goals_stats(home_matches, home_team['id'])
        ags, agc = calc_goals_stats(away_matches, away_team['id'])
        if hgs + ags > 2.5: score += 10
    league_id = fixture['league']['id']
    top_leagues = [39, 140, 135, 78, 61, 2, 3]
    if league_id in top_leagues: score += 15
    return score

def run_daily_analysis():
    from backend.ai_analyzer import analyze_with_claude
    today = datetime.now().strftime('%Y-%m-%d')
    logger.info(f"Starting daily analysis for {today}")
    try:
        clear_today_analyses()
        fixtures = get_todays_fixtures()
        logger.info(f"Found {len(fixtures)} fixtures today")
        if not fixtures:
            log_run(today, 'no_matches', 0, 0)
            return
        scored_fixtures = []
        for fixture in fixtures:
            try:
                home_id = fixture['teams']['home']['id']
                away_id = fixture['teams']['away']['id']
                h2h = get_h2h(home_id, away_id, last=5)
                home_matches = get_team_last_matches(home_id, last=10)
                away_matches = get_team_last_matches(away_id, last=10)
                priority_score = score_match(fixture, h2h, home_matches, away_matches)
                scored_fixtures.append({
                    'fixture': fixture,
                    'h2h': h2h,
                    'home_matches': home_matches,
                    'away_matches': away_matches,
                    'priority_score': priority_score
                })
            except Exception as e:
                logger.warning(f"Error scoring fixture: {e}")
                continue
        scored_fixtures.sort(key=lambda x: x['priority_score'], reverse=True)
        top_10 = scored_fixtures[:10]
        logger.info(f"Analyzing top {len(top_10)} matches")
        analyzed = 0
        for item in top_10:
            try:
                analysis = analyze_with_claude(
                    item['fixture'], item['h2h'],
                    item['home_matches'], item['away_matches']
                )
                if analysis:
                    save_analysis(analysis)
                    analyzed += 1
                time.sleep(8)
            except Exception as e:
                logger.error(f"Error analyzing match: {e}")
                continue
        log_run(today, 'success', len(fixtures), analyzed)
        logger.info(f"Done. Analyzed {analyzed} matches.")
    except Exception as e:
        logger.error(f"Daily analysis failed: {e}")
        log_run(today, 'error', 0, 0, str(e))
        raise
