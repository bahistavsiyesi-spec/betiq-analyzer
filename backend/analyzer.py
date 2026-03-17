import logging
import json
import time
import requests
import os
from datetime import datetime
from backend.football_api import (
    get_todays_fixtures, get_h2h, get_team_last_matches,
    get_team_home_away_stats, get_team_standing, get_team_shot_stats,
    teams_match
)
from backend.database import save_analysis, delete_analyses_by_fixture_ids, log_run

logger = logging.getLogger(__name__)

# Odds API ve ClubElo artık CSV'den geldiği için devre dışı
# ODDS_API_KEY = os.environ.get('ODDS_API_KEY', '')


def extract_form_from_fixtures(matches, team_name):
    form = []
    for m in matches[-5:]:
        try:
            home_name = m['teams']['home']['name']
            home_goals = m['goals']['home'] or 0
            away_goals = m['goals']['away'] or 0
            is_home = teams_match(team_name, home_name)
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
    scored, conceded = [], []
    for m in matches:
        try:
            home_name = m['teams']['home']['name']
            home_goals = m['goals']['home'] or 0
            away_goals = m['goals']['away'] or 0
            is_home = teams_match(team_name, home_name)
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


def extract_goals_trend(matches, team_name):
    """Son 5 maçtan gol attı/yedi trendini çıkarır."""
    scored = []
    conceded = []
    for m in matches[-5:]:
        try:
            home_name = m['teams']['home']['name']
            hg = m['goals']['home']
            ag = m['goals']['away']
            if hg is None or ag is None:
                continue
            is_home = teams_match(team_name, home_name)
            if is_home:
                scored.append(int(hg))
                conceded.append(int(ag))
            else:
                scored.append(int(ag))
                conceded.append(int(hg))
        except:
            continue

    if not scored:
        return None

    return {
        'scored': scored,
        'conceded': conceded,
        'scored_avg': round(sum(scored) / len(scored), 1),
        'conceded_avg': round(sum(conceded) / len(conceded), 1),
        'matches_used': len(scored),
    }


def extract_btts_stats(matches, team_name):
    scored_count = 0
    conceded_count = 0
    total = 0

    for m in matches:
        try:
            home_name = m['teams']['home']['name']
            hg = m['goals']['home']
            ag = m['goals']['away']
            if hg is None or ag is None:
                continue

            is_home = teams_match(team_name, home_name)
            team_goals = hg if is_home else ag
            opp_goals = ag if is_home else hg

            if team_goals > 0:
                scored_count += 1
            if opp_goals > 0:
                conceded_count += 1
            total += 1
        except:
            continue

    if total == 0:
        return None

    scored_pct = round(scored_count / total * 100)
    conceded_pct = round(conceded_count / total * 100)
    btts_estimate = round(scored_pct * conceded_pct / 100)

    logger.info(f'BTTS stats {team_name}: %{scored_pct} gol atar, %{conceded_pct} gol yer (son {total} maç)')

    return {
        'scored_pct': scored_pct,
        'conceded_pct': conceded_pct,
        'btts_estimate': btts_estimate,
        'matches_used': total,
    }


def extract_ht_stats(matches, team_name):
    ht_scored = []
    ht_conceded = []

    for m in matches:
        try:
            goals = m.get('goals', {})
            ht_home = goals.get('ht_home')
            ht_away = goals.get('ht_away')

            if ht_home is None or ht_away is None:
                continue

            home_name = m['teams']['home']['name']
            is_home = teams_match(team_name, home_name)

            if is_home:
                ht_scored.append(ht_home)
                ht_conceded.append(ht_away)
            else:
                ht_scored.append(ht_away)
                ht_conceded.append(ht_home)
        except:
            continue

    if not ht_scored:
        return None

    n = len(ht_scored)
    ht_goals_avg = round(sum(ht_scored) / n, 2)
    ht_conceded_avg = round(sum(ht_conceded) / n, 2)
    ht_over05_count = sum(1 for s, c in zip(ht_scored, ht_conceded) if s + c >= 1)
    ht_over05_pct = round(ht_over05_count / n * 100)
    ht_scored_count = sum(1 for s in ht_scored if s >= 1)
    ht_scored_pct = round(ht_scored_count / n * 100)

    logger.info(f'HT stats {team_name}: {ht_goals_avg} gol atar, {ht_conceded_avg} yer, '
                f'%{ht_over05_pct} maçta ilk yarı gol var (son {n} maç)')

    return {
        'ht_goals_avg': ht_goals_avg,
        'ht_conceded_avg': ht_conceded_avg,
        'ht_over05_pct': ht_over05_pct,
        'ht_scored_pct': ht_scored_pct,
        'matches_used': n,
    }


def extract_h2h_summary(h2h_matches, home_team, away_team):
    if not h2h_matches:
        return None
    home_wins, away_wins, draws, total_goals = 0, 0, 0, 0
    for m in h2h_matches:
        try:
            match_home = m['teams']['home']['name']
            hg = m['goals']['home'] or 0
            ag = m['goals']['away'] or 0
            total_goals += hg + ag
            is_our_home = teams_match(home_team, match_home)
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
    return {
        'home_wins': home_wins, 'away_wins': away_wins,
        'draws': draws, 'total': total,
        'avg_goals': round(total_goals / total, 1) if total else 0
    }


def _get_country_code(fixture):
    league = fixture['league']['name']
    country_map = {
        'GER': 'GER', 'ENG': 'ENG', 'ESP': 'ESP',
        'ITA': 'ITA', 'FRA': 'FRA', 'POR': 'POR', 'NED': 'NED',
    }
    return country_map.get(league, None)


def analyze_fixture(fixture, csv_data=None):
    """
    fixture: standart fixture dict
    csv_data: CSV'den gelen ek veriler (xG, BTTS%, Over25%, oranlar, vb.)
              Örnek:
              {
                'home_xg': 1.45,
                'away_xg': 0.92,
                'btts_avg': 52,
                'over25_avg': 61,
                'over15_avg': 78,
                'avg_goals': 2.4,
                'avg_corners': 10.2,
                'odds_home': 1.85,
                'odds_draw': 3.40,
                'odds_away': 4.20,
                'odds_over25': 1.72,
                'odds_btts_yes': 1.80,
                'home_ppg': 1.8,
                'away_ppg': 1.1,
              }
    """
    from backend.ai_analyzer import analyze_with_claude

    home_name = fixture['teams']['home']['name']
    away_name = fixture['teams']['away']['name']

    if not home_name or not away_name or home_name == '?' or away_name == '?':
        logger.error('Skipping match with missing team names: ' + str(home_name) + ' vs ' + str(away_name))
        return None

    home_name = str(home_name).strip()
    away_name = str(away_name).strip()
    logger.info('Analyzing: ' + home_name + ' vs ' + away_name)

    # football-data.org: form, H2H, gol trendi için hâlâ kullanılıyor
    home_matches = get_team_last_matches(home_name, last=10)
    away_matches = get_team_last_matches(away_name, last=10)
    h2h = get_h2h(home_name, away_name, last=5)

    home_form = extract_form_from_fixtures(home_matches if home_matches else [], home_name)
    away_form = extract_form_from_fixtures(away_matches if away_matches else [], away_name)
    home_goals_avg, home_conceded_avg = extract_goals_avg(home_matches, home_name)
    away_goals_avg, away_conceded_avg = extract_goals_avg(away_matches, away_name)
    h2h_summary = extract_h2h_summary(h2h, home_name, away_name)

    home_goals_trend = extract_goals_trend(home_matches, home_name)
    away_goals_trend = extract_goals_trend(away_matches, away_name)

    if home_goals_trend:
        logger.info(f'Trend {home_name}: attı={home_goals_trend["scored"]} yedi={home_goals_trend["conceded"]}')
    if away_goals_trend:
        logger.info(f'Trend {away_name}: attı={away_goals_trend["scored"]} yedi={away_goals_trend["conceded"]}')

    home_venue_stats = get_team_home_away_stats(home_name, home_matches)
    away_venue_stats = get_team_home_away_stats(away_name, away_matches)

    home_ht_stats = extract_ht_stats(home_matches, home_name)
    away_ht_stats = extract_ht_stats(away_matches, away_name)

    home_btts_stats = extract_btts_stats(home_matches, home_name)
    away_btts_stats = extract_btts_stats(away_matches, away_name)

    if home_btts_stats and away_btts_stats:
        btts_mathematical = round(home_btts_stats['scored_pct'] * away_btts_stats['scored_pct'] / 100)
    else:
        btts_mathematical = None

    # Puan durumu — country_code varsa çek
    home_standing = None
    away_standing = None
    country_code = _get_country_code(fixture)
    if country_code:
        try:
            home_standing = get_team_standing(home_name, country_code)
            away_standing = get_team_standing(away_name, country_code)
        except Exception as e:
            logger.warning('Standings failed: ' + str(e))

    # ── CSV veri varsa oranlar/xG CSV'den gelir, API'den çekilmez ──
    odds_data = None
    if csv_data:
        # CSV'den gelen oranları odds_data formatına dönüştür
        if csv_data.get('odds_home') and csv_data.get('odds_away'):
            odds_data = {
                'home_odds': csv_data['odds_home'],
                'draw_odds': csv_data.get('odds_draw'),
                'away_odds': csv_data['odds_away'],
                'bookmaker_count': 1,  # CSV kaynağı
                'source': 'CSV',
            }
            logger.info(f'Odds (CSV): {home_name} {odds_data["home_odds"]} | '
                        f'Draw {odds_data["draw_odds"]} | {away_name} {odds_data["away_odds"]}')

    # Shot stats — CSV varsa korner CSV'den gelir, API çağrısı yapma
    home_shot_stats = None
    away_shot_stats = None
    if csv_data and csv_data.get('avg_corners'):
        # CSV'de takım bazlı korner ayrımı yok; maç geneli avg_corners var
        # Bunu prompt'a csv_data üzerinden ayrıca göndereceğiz
        pass
    elif country_code:
        try:
            home_shot_stats = get_team_shot_stats(home_name, country_code, last=5)
            away_shot_stats = get_team_shot_stats(away_name, country_code, last=5)
        except Exception as e:
            logger.warning(f'Shot stats failed: {e}')

    # ClubElo — CSV varsa kullanma
    elo_data = None
    if not csv_data:
        try:
            from backend.clubelo import get_elo_for_match
            elo_data = get_elo_for_match(home_name, away_name)
            if elo_data:
                logger.info('ClubElo: ' + home_name + ' ' + str(elo_data.get('home_elo', '?')) +
                            ' vs ' + away_name + ' ' + str(elo_data.get('away_elo', '?')))
        except Exception as e:
            logger.warning('ClubElo failed: ' + str(e))

    logger.info('Stats: ' + home_name + ' form=' + home_form + ' avg=' + str(home_goals_avg) +
                ', ' + away_name + ' form=' + away_form + ' avg=' + str(away_goals_avg))
    if csv_data:
        logger.info(f'CSV data: xG={csv_data.get("home_xg")}/{csv_data.get("away_xg")} '
                    f'BTTS%={csv_data.get("btts_avg")} Over25%={csv_data.get("over25_avg")} '
                    f'AvgGoals={csv_data.get("avg_goals")}')

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
        odds_data=odds_data,
        home_standing=home_standing,
        away_standing=away_standing,
        home_venue_stats=home_venue_stats,
        away_venue_stats=away_venue_stats,
        home_shot_stats=home_shot_stats,
        away_shot_stats=away_shot_stats,
        home_ht_stats=home_ht_stats,
        away_ht_stats=away_ht_stats,
        home_btts_stats=home_btts_stats,
        away_btts_stats=away_btts_stats,
        btts_mathematical=btts_mathematical,
        home_goals_trend=home_goals_trend,
        away_goals_trend=away_goals_trend,
        csv_data=csv_data,       # ← YENİ: CSV verileri direkt geçiyor
    )


def run_selected_analysis(fixture_ids=[], manual_matches=[]):
    today = datetime.now().strftime('%Y-%m-%d')
    logger.info('Starting selected analysis: ' + str(len(fixture_ids)) + ' fixtures, ' + str(len(manual_matches)) + ' manual')

    try:
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

                manual_fixture = {
                    'fixture': {'id': 0, 'date': m.get('date', datetime.now().isoformat())},
                    'league': {'id': 0, 'name': m.get('league', 'Manuel Mac')},
                    'teams': {
                        'home': {'id': 0, 'name': home_team},
                        'away': {'id': 0, 'name': away_team}
                    },
                    'goals': {'home': None, 'away': None}
                }

                # CSV'den gelen ek veriler — app.js'de parse edilip manual_matches içine ekleniyor
                csv_data = m.get('csv_data') or None

                analysis = analyze_fixture(manual_fixture, csv_data=csv_data)
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
    fixtures = get_todays_fixtures()
    fixture_ids = [f['fixture']['id'] for f in fixtures[:10]]
    run_selected_analysis(fixture_ids=fixture_ids)
