import logging
import time
from datetime import datetime
from typing import Any, Optional

from backend.database import delete_analyses_by_fixture_ids, log_run, save_analysis, get_custom_form
from backend.football_api import (
    get_h2h_footballdata,
    get_team_home_away_stats,
    get_team_last_matches,
    get_team_shot_stats,
    get_team_standing,
    get_todays_fixtures,
    teams_match,
    is_turkish_superlig_team,
    get_team_last_matches_apifootball,
    get_h2h_apifootball,
    LEAGUE_CODES,
)

logger = logging.getLogger(__name__)


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        text = str(value).strip().replace(',', '.')
        if not text:
            return None
        return round(float(text), 2)
    except (TypeError, ValueError):
        return None


def extract_form_from_fixtures(matches, team_name):
    form = []
    for m in matches[-5:]:
        try:
            home_name = m['teams']['home']['name']
            home_goals = m['goals']['home'] or 0
            away_goals = m['goals']['away'] or 0
            is_home = teams_match(team_name, home_name)
            if is_home:
                if home_goals > away_goals:
                    form.append('W')
                elif home_goals == away_goals:
                    form.append('D')
                else:
                    form.append('L')
            else:
                if away_goals > home_goals:
                    form.append('W')
                elif away_goals == home_goals:
                    form.append('D')
                else:
                    form.append('L')
        except Exception:
            continue
    return ''.join(form)


def extract_goals_avg(matches, team_name):
    scored, conceded = [], []
    for m in matches[-5:]:
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
        except Exception:
            continue
    avg_scored = round(sum(scored) / len(scored), 1) if scored else 0
    avg_conceded = round(sum(conceded) / len(conceded), 1) if conceded else 0
    return avg_scored, avg_conceded


def extract_goals_trend(matches, team_name):
    scored, conceded = [], []
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
        except Exception:
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
                if is_our_home:
                    home_wins += 1
                else:
                    away_wins += 1
            elif hg < ag:
                if is_our_home:
                    away_wins += 1
                else:
                    home_wins += 1
            else:
                draws += 1
        except Exception:
            continue
    total = len(h2h_matches)
    return {
        'home_wins': home_wins,
        'away_wins': away_wins,
        'draws': draws,
        'total': total,
        'avg_goals': round(total_goals / total, 1) if total else 0,
    }


def _get_country_code(fixture):
    league = fixture['league']['name'].lower()
    if any(x in league for x in ['germany', 'bundesliga', 'german']):
        return 'GER'
    if any(x in league for x in ['england', 'premier league', 'championship', 'league one', 'league two', 'fa cup', 'league cup']):
        return 'ENG'
    if any(x in league for x in ['spain', 'laliga', 'la liga', 'primera', 'copa del rey']):
        return 'ESP'
    if any(x in league for x in ['italy', 'serie a', 'serie b', 'coppa italia']):
        return 'ITA'
    if any(x in league for x in ['france', 'ligue 1', 'ligue 2', 'coupe de france']):
        return 'FRA'
    if any(x in league for x in ['portugal', 'primeira liga', 'liga nos']):
        return 'POR'
    if any(x in league for x in ['netherlands', 'eredivisie', 'dutch']):
        return 'NED'
    if any(x in league for x in ['brazil', 'brasileirao', 'serie a brasil', 'brasileiro', 'bsa']):
        return 'BRA'
    if any(x in league for x in ['champions league', 'sampiyonlar ligi', 'uefa champions']):
        return 'CL'
    if any(x in league for x in ['europa league', 'uefa europa']):
        return 'EL'
    if any(x in league for x in ['conference league', 'uefa conference']):
        return 'EC'
    return None


def _build_csv_odds_data(csv_data, home_name, away_name):
    if not csv_data:
        return None

    raw_home = csv_data.get('odds_home')
    raw_draw = csv_data.get('odds_draw')
    raw_away = csv_data.get('odds_away')

    home_odds = safe_float(raw_home)
    draw_odds = safe_float(raw_draw)
    away_odds = safe_float(raw_away)

    logger.info('RAW ODDS CSV: %s | %s | %s', raw_home, raw_draw, raw_away)
    logger.info('PARSED ODDS: %s | %s | %s', home_odds, draw_odds, away_odds)

    if home_odds is None or away_odds is None:
        return None

    odds_data = {
        'home_odds': home_odds,
        'draw_odds': draw_odds,
        'away_odds': away_odds,
        'bookmaker_count': 1,
        'source': 'CSV',
    }

    draw_log = f'{draw_odds:.2f}' if draw_odds is not None else 'None'
    logger.info('Odds (CSV): %s %.2f | Draw %s | %s %.2f', home_name, home_odds, draw_log, away_name, away_odds)
    return odds_data


def analyze_fixture(fixture, csv_data=None, ai_provider='claude'):
    from backend.ai_analyzer import analyze_with_claude

    home_name = fixture['teams']['home']['name']
    away_name = fixture['teams']['away']['name']

    if not home_name or not away_name or home_name == '?' or away_name == '?':
        logger.error('Skipping match with missing team names: ' + str(home_name) + ' vs ' + str(away_name))
        return None

    home_name = str(home_name).strip()
    away_name = str(away_name).strip()
    league_name = fixture['league']['name']
    country_code = _get_country_code(fixture)
    logger.info('Analyzing: ' + home_name + ' vs ' + away_name)

    home_matches = get_team_last_matches(home_name, last=10)
    away_matches = get_team_last_matches(away_name, last=10)
    h2h = []

    # API-Football genel fallback — football-data.org'dan veri gelmeyen tüm takımlar için
    from backend.football_api import _find_league_id
    _fb_league_id = _find_league_id(league_name)
    if not _fb_league_id and (is_turkish_superlig_team(home_name) or is_turkish_superlig_team(away_name)):
        _fb_league_id = 203
    if not _fb_league_id:
        if not csv_data:
            logger.warning(f'League ID bulunamadı, CSV yok, atlanıyor: {league_name}')
            return None
        logger.info(f'League ID bulunamadı ama CSV var, devam ediliyor: {league_name}')

    if not home_matches:
        home_matches = get_team_last_matches_apifootball(home_name, league_id=_fb_league_id) or []
        if home_matches:
            logger.info(f'API-Football matches fallback: {home_name} -> {len(home_matches)} mac')
    if not away_matches:
        away_matches = get_team_last_matches_apifootball(away_name, league_id=_fb_league_id) or []
        if away_matches:
            logger.info(f'API-Football matches fallback: {away_name} -> {len(away_matches)} mac')
    if not h2h:
        h2h = get_h2h_apifootball(home_name, away_name, league_id=_fb_league_id) or []
        if h2h:
            logger.info(f'API-Football H2H fallback: {home_name} vs {away_name} -> {len(h2h)} mac')

    # Gerçek H2H (football-data.org /head2head endpoint'i) — karşılaştırma için
    h2h_fd = None
    try:
        fd_league_code = LEAGUE_CODES.get(country_code) if country_code else None
        if fd_league_code:
            h2h_fd = get_h2h_footballdata(home_name, away_name, fd_league_code)
            if h2h_fd:
                logger.info(
                    f'H2H (football-data) {home_name} vs {away_name}: '
                    f'{h2h_fd["total"]} maç | Ev {h2h_fd["home_wins"]}G '
                    f'Dep {h2h_fd["away_wins"]}G {h2h_fd["draws"]}B | '
                    f'Ort {h2h_fd["avg_goals"]} gol'
                )
            else:
                logger.info(f'H2H (football-data): veri bulunamadi ({home_name} vs {away_name})')
    except Exception as e:
        logger.warning(f'H2H footballdata call failed: {e}')

    h2h_raw = h2h_fd.get('matches', []) if h2h_fd else []

    home_form = extract_form_from_fixtures(home_matches or [], home_name)
    away_form = extract_form_from_fixtures(away_matches or [], away_name)

    if not home_form or not away_form:
        try:
            custom_form_row = get_custom_form(league_name or '')
            if custom_form_row and custom_form_row.get('data'):
                form_data = custom_form_row['data']
                if not home_form:
                    for key, val in form_data.items():
                        from backend.football_api import teams_match as _tm
                        if _tm(home_name, key):
                            home_form = val
                            logger.info(f'Custom form fallback: {home_name} -> {home_form}')
                            break
                if not away_form:
                    for key, val in form_data.items():
                        from backend.football_api import teams_match as _tm
                        if _tm(away_name, key):
                            away_form = val
                            logger.info(f'Custom form fallback: {away_name} -> {away_form}')
                            break
        except Exception as _e:
            logger.debug(f'Custom form lookup failed: {_e}')
    home_goals_avg, home_conceded_avg = extract_goals_avg(home_matches, home_name)
    away_goals_avg, away_conceded_avg = extract_goals_avg(away_matches, away_name)
    h2h_summary = extract_h2h_summary(h2h, home_name, away_name)

    home_goals_trend = extract_goals_trend(home_matches, home_name)
    away_goals_trend = extract_goals_trend(away_matches, away_name)

    if home_goals_trend:
        logger.info(f'Trend {home_name}: atti={home_goals_trend["scored"]} yedi={home_goals_trend["conceded"]}')
    if away_goals_trend:
        logger.info(f'Trend {away_name}: atti={away_goals_trend["scored"]} yedi={away_goals_trend["conceded"]}')

    home_venue_stats = get_team_home_away_stats(home_name, home_matches)
    away_venue_stats = get_team_home_away_stats(away_name, away_matches)

    home_standing = None
    away_standing = None

    is_youth_match = any(
        x in home_name.lower() or x in away_name.lower()
        for x in ['u21', 'u18', 'u23', 'u19', 'reserves', 'youth', ' ii']
    )

    if is_youth_match:
        logger.info(f'Youth match — standings skipped: {home_name} vs {away_name}')
    else:
        try:
            # league_name ile hem football-data.org hem CollectAPI fallback çalışır
            home_standing = get_team_standing(home_name, country_code, league_name=league_name)
            away_standing = get_team_standing(away_name, country_code, league_name=league_name)
            for team_name_log, st in [(home_name, home_standing), (away_name, away_standing)]:
                if not st:
                    continue
                home_str = ''
                away_str = ''
                if st.get('home_position') is not None:
                    home_str = f' | HOME {st["home_position"]}. sira {st.get("home_won",0)}G {st.get("home_draw",0)}B {st.get("home_lost",0)}M'
                if st.get('away_position') is not None:
                    away_str = f' | AWAY {st["away_position"]}. sira {st.get("away_won",0)}G {st.get("away_draw",0)}B {st.get("away_lost",0)}M'
                logger.info(f'Standing {team_name_log}: TOTAL {st["position"]}. sira {st["points"]}p{home_str}{away_str}')
        except Exception as e:
            logger.warning('Standings failed: ' + str(e))

    home_shot_stats = None
    away_shot_stats = None
    shot_supported = ('ENG', 'GER', 'ESP', 'ITA', 'FRA', 'NED')
    if country_code and country_code in shot_supported and not is_youth_match:
        try:
            home_shot_stats = get_team_shot_stats(home_name, country_code, last=5)
            away_shot_stats = get_team_shot_stats(away_name, country_code, last=5)
            if home_shot_stats:
                logger.info(
                    f'Shot stats {home_name}: {home_shot_stats["shots_avg"]} şut, '
                    f'{home_shot_stats["shots_on_target_avg"]} isabetli, '
                    f'%{home_shot_stats["shot_accuracy"]} isabet'
                )
            if away_shot_stats:
                logger.info(
                    f'Shot stats {away_name}: {away_shot_stats["shots_avg"]} şut, '
                    f'{away_shot_stats["shots_on_target_avg"]} isabetli, '
                    f'%{away_shot_stats["shot_accuracy"]} isabet'
                )
        except Exception as e:
            logger.warning(f'Shot stats failed: {e}')

    odds_data = _build_csv_odds_data(csv_data, home_name, away_name)

    logger.info(f'Stats: {home_name} form={home_form} avg={home_goals_avg} matches={len(home_matches)}, {away_name} form={away_form} avg={away_goals_avg} matches={len(away_matches)}')

    if csv_data:
        logger.info(
            f'CSV data: xG={csv_data.get("home_xg")}/{csv_data.get("away_xg")} '
            f'BTTS%={csv_data.get("btts_avg")} Over25%={csv_data.get("over25_avg")} '
            f'IY05%={csv_data.get("ht_over05_avg")} AvgGoals={csv_data.get("avg_goals")} '
            f'CurrPPG={csv_data.get("current_home_ppg")}/{csv_data.get("current_away_ppg")} '
            f'HT2={csv_data.get("ht2_over05_avg")}'
        )

    return analyze_with_claude(
        fixture=fixture,
        h2h_data=h2h_raw or h2h,
        home_matches=home_matches,
        away_matches=away_matches,
        home_form=home_form,
        away_form=away_form,
        home_goals_avg=home_goals_avg,
        away_goals_avg=away_goals_avg,
        home_conceded_avg=home_conceded_avg,
        away_conceded_avg=away_conceded_avg,
        h2h_summary=h2h_summary,
        h2h_fd=h2h_fd,
        elo_data=None,
        odds_data=odds_data,
        home_standing=home_standing,
        away_standing=away_standing,
        home_venue_stats=home_venue_stats,
        away_venue_stats=away_venue_stats,
        home_shot_stats=home_shot_stats,
        away_shot_stats=away_shot_stats,
        home_ht_stats=None,
        away_ht_stats=None,
        home_btts_stats=None,
        away_btts_stats=None,
        btts_mathematical=None,
        home_goals_trend=home_goals_trend,
        away_goals_trend=away_goals_trend,
        csv_data=csv_data,
        league_code=country_code,
        ai_provider=ai_provider,
    )


def run_selected_analysis(fixture_ids=None, manual_matches=None, ai_provider='claude'):
    fixture_ids = fixture_ids or []
    manual_matches = manual_matches or []

    today = datetime.now().strftime('%Y-%m-%d')
    logger.info(f'Starting selected analysis: {len(fixture_ids)} fixtures, {len(manual_matches)} manual, AI: {ai_provider}')

    try:
        if fixture_ids:
            delete_analyses_by_fixture_ids(fixture_ids)

        analyzed = 0

        if fixture_ids:
            all_fixtures = get_todays_fixtures()
            selected = [f for f in all_fixtures if f['fixture']['id'] in fixture_ids]
            for fixture in selected:
                try:
                    analysis = analyze_fixture(fixture, ai_provider=ai_provider)
                    if analysis:
                        save_analysis(analysis)
                        analyzed += 1
                    time.sleep(1)
                except Exception as e:
                    logger.error('Error analyzing fixture: ' + str(e))

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
                        'away': {'id': 0, 'name': away_team},
                    },
                    'goals': {'home': None, 'away': None},
                }

                csv_data = m.get('csv_data') or None
                analysis = analyze_fixture(manual_fixture, csv_data=csv_data, ai_provider=ai_provider)
                if analysis:
                    save_analysis(analysis)
                    analyzed += 1
                time.sleep(1)
            except Exception as e:
                logger.error('Error analyzing manual match: ' + str(e))

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
