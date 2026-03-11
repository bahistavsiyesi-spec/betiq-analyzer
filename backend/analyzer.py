import logging
import json
import time
from datetime import datetime
from backend.football_api import (
    get_todays_fixtures, get_h2h, get_team_last_matches, search_team
)
from backend.database import save_analysis, clear_today_analyses, log_run

logger = logging.getLogger(__name__)

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
    
    home_name = fixture['teams']['home']['name']
    away_name = fixture['teams']['away']['name']
    
    logger.info(f"Analyzing: {home_name} vs {away_name}")
    
    home_matches = get_team_last_matches(home_name, last=5)
    away_matches = get_team_last_matches(away_name, last=5)
    h2h = get_h2h(home_name, away_name, last=5)
    
    home_form = extract_form_from_fixtures(home_matches, home_name)
    away_form = extract_form_from_fixtures(away_matches, away_name)
    home_goals_avg, home_conceded_avg = extract_goals_avg(home_matches, home_name)
    away_goals_avg, away_conceded_avg = extract_goals_avg(away_matches, away_name)
    h2h_summary = extract_h2h_summary(h2h, home_name, away_name)
    
    logger.info(f"Stats: {home_name} form={home_form} avg={home_goals_avg}, {away_name} form={away_form} avg={away_goals_avg}")
    
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
        h2h_summary=h2h_summary
    )

def run_selected_analysis(fixture_ids=[], manual_matches=[]):
    today = datetime.now().strftime('%Y-%m-%d')
    logger.info(f"Starting selected analysis: {len(fixture_ids)} fixtures, {len(manual_matches)} manual")
    
    try:
        clear_today_analyses()
        analyzed = 0
        all_analyses = []

        if fixture_ids:
            all_fixtures = get_todays_fixtures()
            selected = [f for f in all_fixtures if f['fixture']['id'] in fixture_ids]
            for fixture in selected:
                try:
                    analysis = analyze_fixture(fixture)
                    if analysis:
                        save_analysis(analysis)
                        all_analyses.append(analysis)
                        analyzed += 1
                    time.sleep(1)
                except Exception as e:
                    logger.error(f"Error analyzing fixture: {e}")
                    continue

        for m in manual_matches:
            try:
                manual_fixture = {
                    'fixture': {'id': int(time.time()), 'date': m.get('date', datetime.now().isoformat())},
                    'league': {'id': 0, 'name': m.get('league', 'Manuel Maç')},
                    'teams': {
                        'home': {'id': 0, 'name': m.get('home_team', '?')},
                        'away': {'id': 0, 'name': m.get('away_team', '?')}
                    },
                    'goals': {'home': None, 'away': None}
                }
                analysis = analyze_fixture(manual_fixture)
                if analysis:
                    save_analysis(analysis)
                    all_analyses.append(analysis)
                    analyzed += 1
                time.sleep(1)
            except Exception as e:
                logger.error(f"Error analyzing manual match: {e}")
                continue

        # Tüm maçlar bittikten sonra Telegram'a gönder
        if all_analyses:
            from backend.telegram_sender import send_daily_analysis
            send_daily_analysis(all_analyses)

        log_run(today, 'success', len(fixture_ids) + len(manual_matches), analyzed)
        logger.info(f"Done. Analyzed {analyzed} matches.")

    except Exception as e:
        logger.error(f"Selected analysis failed: {e}")
        log_run(today, 'error', 0, 0, str(e))
        raise

def run_daily_analysis():
    today = datetime.now().strftime('%Y-%m-%d')
    fixtures = get_todays_fixtures()
    fixture_ids = [f['fixture']['id'] for f in fixtures[:10]]
    run_selected_analysis(fixture_ids=fixture_ids)
