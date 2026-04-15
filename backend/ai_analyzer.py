import math
import os
import json
import logging
import requests
import time
from datetime import datetime

from backend.football_api import get_league_goal_averages

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.environ.get('GROQ_API_KEY', '')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

VALUE_THRESHOLD = 5.0


def detect_match_importance(league):
    league_lower = league.lower()
    if any(x in league_lower for x in ['champions league', 'sampiyonlar ligi', 'uefa', 'europa league', 'conference']):
        return 'Avrupa kupasi maci — eleme baskisi yuksek, iki takim da temkinli oynayabilir'
    if any(x in league_lower for x in ['cup', 'kupa', 'fa cup', 'copa', 'pokal']):
        return 'Kupa maci — tek maclik eleme, beklenmedik sonuclar olabilir'
    if any(x in league_lower for x in ['friendly', 'hazirlik']):
        return 'Hazirlik maci — motivasyon dusuk olabilir, sonuc guvenirligi az'
    return 'Lig maci — puan kaybi istemeyen iki takim'


def calculate_value_bets(result, csv_data, home_team, away_team):
    if not csv_data or not result:
        return []
    value_bets = []
    checks = [
        ('Over 2.5',   'over25_pct', 'odds_over25'),
        ('KG Var',     'btts_pct',   'odds_btts_yes'),
        ('İY 0.5 Üst', 'ht2g_pct',  'odds_ht_over05'),
        ('Over 1.5',   None,         'odds_over15'),
        ('Over 3.5',   None,         'odds_over35'),
    ]
    pred = result.get('prediction_1x2')
    pred_map = {
        '1': ('1X2 (Ev)', 'odds_home'),
        'X': ('1X2 (Beraberlik)', 'odds_draw'),
        '2': ('1X2 (Deplasman)', 'odds_away'),
    }
    if pred in pred_map:
        label, odds_key = pred_map[pred]
        odds = csv_data.get(odds_key)
        if odds:
            try:
                implied = round(1 / float(odds) * 100, 1)
                # PPG verisinden gerçek olasılık türet (conf_map sabitler yerine)
                our_pct = None
                try:
                    ch = float(csv_data.get('current_home_ppg') or csv_data.get('home_ppg') or 0)
                    ca = float(csv_data.get('current_away_ppg') or csv_data.get('away_ppg') or 0)
                    if ch > 0 or ca > 0:
                        total = (ch + ca) or 1.0
                        h_frac = ch / total
                        a_frac = ca / total
                        if pred == '1':
                            # Ev avantajı dahil: güçlü ev ekibinde ~70%, zayıfta ~40%
                            our_pct = round(max(35, min(80, 35 + h_frac * 50)))
                        elif pred == '2':
                            # Deplasman: güçlü rakipte ~70%, zayıfta ~30%
                            our_pct = round(max(25, min(75, 25 + a_frac * 50)))
                        elif pred == 'X':
                            # Beraberlik dengeli maçlarda daha yüksek
                            balance = 1.0 - abs(h_frac - 0.5) * 2
                            our_pct = round(max(20, min(40, 20 + balance * 20)))
                except (ValueError, TypeError):
                    pass
                # PPG verisi yoksa sabit harita (son çare)
                if our_pct is None:
                    conf_map = {'Çok Yüksek': 80, 'Yüksek': 70, 'Orta': 57, 'Düşük': 43}
                    our_pct = conf_map.get(result.get('confidence', 'Orta'), 57)
                diff = round(our_pct - implied, 1)
                if diff >= VALUE_THRESHOLD:
                    value_bets.append({'label': label, 'our_pct': our_pct, 'implied_pct': implied, 'diff': diff, 'odds': float(odds)})
            except (ValueError, TypeError, ZeroDivisionError) as e:
                logger.debug(f'Value bet 1x2 calc skipped: {e}')
    for label, our_key, odds_key in checks:
        if our_key is None: continue
        our_pct = result.get(our_key)
        odds = csv_data.get(odds_key)
        if our_pct is None or odds is None: continue
        try:
            implied = round(1 / float(odds) * 100, 1)
            diff = round(float(our_pct) - implied, 1)
            if diff >= VALUE_THRESHOLD:
                value_bets.append({'label': label, 'our_pct': round(float(our_pct)), 'implied_pct': implied, 'diff': diff, 'odds': float(odds)})
        except (ValueError, TypeError, ZeroDivisionError) as e:
            logger.debug(f'Value bet calc skipped for {label}: {e}')
            continue
    value_bets.sort(key=lambda x: x['diff'], reverse=True)
    return value_bets[:3]


def build_csv_section(home_team, away_team, csv_data):
    if not csv_data:
        return ''
    lines = ['\n── FootyStats CSV Verileri ──']
    hxg = csv_data.get('home_xg')
    axg = csv_data.get('away_xg')
    if hxg is not None or axg is not None:
        lines.append('Pre-Match xG (beklenen gol):')
        if hxg is not None: lines.append(f'  - {home_team}: {hxg} xG')
        if axg is not None: lines.append(f'  - {away_team}: {axg} xG')
        if hxg and axg:
            diff = round(float(hxg) - float(axg), 2)
            dominant = home_team if diff > 0 else away_team
            lines.append(f'  - xG farkı: {abs(diff)} ({dominant} üstün)')
    hppg = csv_data.get('home_ppg')
    appg = csv_data.get('away_ppg')
    if hppg is not None or appg is not None:
        lines.append('Puan/Maç Ortalaması (pre-match):')
        if hppg is not None: lines.append(f'  - {home_team}: {hppg} puan/maç')
        if appg is not None: lines.append(f'  - {away_team}: {appg} puan/maç')

    # ── YENİ: Güncel PPG (sezon içi form trendi) ──────────────────────────────
    curr_hppg = csv_data.get('current_home_ppg')
    curr_appg = csv_data.get('current_away_ppg')
    if curr_hppg is not None or curr_appg is not None:
        lines.append('Güncel Puan/Maç (sezon içi):')
        if curr_hppg is not None: lines.append(f'  - {home_team}: {curr_hppg} puan/maç (güncel)')
        if curr_appg is not None: lines.append(f'  - {away_team}: {curr_appg} puan/maç (güncel)')
        if curr_hppg and hppg:
            try:
                diff = round(float(curr_hppg) - float(hppg), 2)
                trend = 'form YUKSELIYOR' if diff > 0.2 else ('form DUSUYOR' if diff < -0.2 else 'form STABIL')
                lines.append(f'  - {home_team} trend: {trend} (fark: {diff:+.2f})')
            except (ValueError, TypeError) as e:
                logger.debug(f'PPG trend calc skipped for {home_team}: {e}')
        if curr_appg and appg:
            try:
                diff = round(float(curr_appg) - float(appg), 2)
                trend = 'form YUKSELIYOR' if diff > 0.2 else ('form DUSUYOR' if diff < -0.2 else 'form STABIL')
                lines.append(f'  - {away_team} trend: {trend} (fark: {diff:+.2f})')
            except (ValueError, TypeError) as e:
                logger.debug(f'PPG trend calc skipped for {away_team}: {e}')
    # ─────────────────────────────────────────────────────────────────────────

    gol_lines = []
    for key, label in [('avg_goals','Ort. gol/maç'),('over05_avg','Over 0.5 %'),('over15_avg','Over 1.5 %'),('over25_avg','Over 2.5 %'),('over35_avg','Over 3.5 %'),('over45_avg','Over 4.5 %')]:
        v = csv_data.get(key)
        if v is not None:
            suffix = '%' if 'avg' in key and key != 'avg_goals' else ''
            gol_lines.append(f'  - {label}: {v}{suffix}')
    if gol_lines:
        lines.append('Gol İstatistikleri (CSV):')
        lines.extend(gol_lines)
    btts = csv_data.get('btts_avg')
    btts1h = csv_data.get('btts_1h_avg')
    if btts is not None or btts1h is not None:
        lines.append('BTTS İstatistikleri (CSV):')
        if btts is not None:
            lines.append(f'  - KG VAR (maç geneli): %{btts}')
        if btts1h is not None: lines.append(f'  - KG VAR (ilk yarı): %{btts1h}')
    ht05 = csv_data.get('ht_over05_avg')
    ht15 = csv_data.get('ht_over15_avg')
    if ht05 is not None or ht15 is not None:
        lines.append('İlk Yarı İstatistikleri (CSV):')
        if ht05 is not None: lines.append(f'  - İlk yarı Over 0.5 (gol olan maç %): %{ht05}')
        if ht15 is not None: lines.append(f'  - İlk yarı Over 1.5 %: %{ht15}')

    # ── YENİ: 2. Yarı istatistikleri ─────────────────────────────────────────
    ht2_05 = csv_data.get('ht2_over05_avg')
    ht2_15 = csv_data.get('ht2_over15_avg')
    if ht2_05 is not None or ht2_15 is not None:
        lines.append('2. Yarı İstatistikleri (CSV):')
        if ht2_05 is not None: lines.append(f'  - 2. yarı gol olan maç %: %{ht2_05}')
        if ht2_15 is not None: lines.append(f'  - 2. yarı Over 1.5 %: %{ht2_15}')
    # ─────────────────────────────────────────────────────────────────────────

    corn_lines = []
    for key, label in [('avg_corners','Ort. korner/maç'),('avg_corners_85','Over 8.5 korner %'),('avg_corners_95','Over 9.5 korner %'),('avg_corners_105','Over 10.5 korner %')]:
        v = csv_data.get(key)
        if v is not None: corn_lines.append(f'  - {label}: {v}')
    if corn_lines:
        lines.append('Korner İstatistikleri (CSV):')
        lines.extend(corn_lines)
    shot_lines = []
    hs = csv_data.get('home_shots')
    hon = csv_data.get('home_shots_on')
    as_ = csv_data.get('away_shots')
    aon = csv_data.get('away_shots_on')
    for key, label in [
        ('home_shots',    f'{home_team} toplam şut/maç'),
        ('home_shots_on', f'{home_team} isabetli şut/maç'),
        ('away_shots',    f'{away_team} toplam şut/maç'),
        ('away_shots_on', f'{away_team} isabetli şut/maç'),
    ]:
        v = csv_data.get(key)
        if v is not None:
            shot_lines.append(f'  - {label}: {v}')
    if hs and hon:
        try:
            acc = round(float(hon) / float(hs) * 100, 1)
            shot_lines.append(f'  - {home_team} isabet oranı: %{acc}')
        except (ValueError, TypeError, ZeroDivisionError) as e:
            logger.debug(f'Shot accuracy calc skipped for {home_team}: {e}')
    if as_ and aon:
        try:
            acc = round(float(aon) / float(as_) * 100, 1)
            shot_lines.append(f'  - {away_team} isabet oranı: %{acc}')
        except (ValueError, TypeError, ZeroDivisionError) as e:
            logger.debug(f'Shot accuracy calc skipped for {away_team}: {e}')
    if shot_lines:
        lines.append('Şut İstatistikleri (CSV):')
        lines.extend(shot_lines)

    cards = csv_data.get('avg_cards')
    if cards is not None:
        lines.append(f'Ortalama Kart/Maç: {cards}')
    odds_lines = []
    for key, label in [
        ('odds_home', f'{home_team} kazanır (1)'), ('odds_draw', 'Beraberlik (X)'), ('odds_away', f'{away_team} kazanır (2)'),
        ('odds_over15','Over 1.5'), ('odds_over25','Over 2.5'), ('odds_over35','Over 3.5'), ('odds_over45','Over 4.5'), ('odds_under25','Under 2.5'),
        ('odds_btts_yes','KG VAR'), ('odds_btts_no','KG YOK'), ('odds_ht_over05','İY Over 0.5'), ('odds_ht_over15','İY Over 1.5'), ('odds_ht_over25','İY Over 2.5'),
        ('odds_dc_1x','Çifte Şans 1X'), ('odds_dc_12','Çifte Şans 12'), ('odds_dc_x2','Çifte Şans X2'),
        ('odds_dnb_1',f'Beraberlik Yok {home_team}'), ('odds_dnb_2',f'Beraberlik Yok {away_team}'),
        ('odds_corners_85','Korner Over 8.5'), ('odds_corners_95','Korner Over 9.5'), ('odds_corners_105','Korner Over 10.5'),
    ]:
        v = csv_data.get(key)
        if v is not None:
            try:
                imp = round(1 / float(v) * 100, 1)
                odds_lines.append(f'  - {label}: {v} (implied %{imp})')
            except:
                odds_lines.append(f'  - {label}: {v}')
    if odds_lines:
        lines.append('Bahis Oranları (CSV):')
        lines.extend(odds_lines)
    lines.append('── CSV Verisi Sonu ──')
    return '\n'.join(lines)


def build_prompt(home_team, away_team, league, match_time,
                 home_form, away_form, home_goals_avg, away_goals_avg,
                 home_conceded_avg, away_conceded_avg, h2h_summary,
                 home_home_avg=None, away_away_avg=None,
                 home_conceded_home_avg=None, away_conceded_away_avg=None,
                 home_home_form=None, away_away_form=None,
                 home_standing=None, away_standing=None,
                 elo_data=None, odds_data=None,
                 home_shot_stats=None, away_shot_stats=None,
                 home_ht_stats=None, away_ht_stats=None,
                 home_btts_stats=None, away_btts_stats=None,
                 btts_mathematical=None,
                 home_goals_trend=None, away_goals_trend=None,
                 csv_data=None, h2h_fd=None):

    h2h_text = ''
    if h2h_fd:
        # Gerçek H2H verisi varsa öncelikli kullan
        total = h2h_fd['total']
        hw = h2h_fd['home_wins']
        aw = h2h_fd['away_wins']
        dr = h2h_fd['draws']
        avg_g = h2h_fd['avg_goals']
        home_win_pct = round(hw / total * 100) if total else 0
        away_win_pct = round(aw / total * 100) if total else 0
        h2h_text = (
            f'\nH2H — Karşılıklı Maç Geçmişi (Son {total} maç, resmi kayıt):\n'
            f'- {home_team} galibiyet: {hw} (%{home_win_pct})\n'
            f'- {away_team} galibiyet: {aw} (%{away_win_pct})\n'
            f'- Beraberlik: {dr}\n'
            f'- Maç başı ortalama gol: {avg_g}\n'
        )
        # Taraf ve gol yorumu için ipuçları
        if hw > aw + 1:
            h2h_text += f'  → H2H: {home_team} tarihsel üstünlüğe sahip\n'
        elif aw > hw + 1:
            h2h_text += f'  → H2H: {away_team} tarihsel üstünlüğe sahip\n'
        else:
            h2h_text += f'  → H2H: Dengeli geçmiş\n'
        if avg_g >= 2.5:
            h2h_text += f'  → H2H gol ortalaması ({avg_g}) over 2.5\'i destekliyor\n'
        elif avg_g < 2.0:
            h2h_text += f'  → H2H gol ortalaması ({avg_g}) under 2.5\'i destekliyor\n'
    elif h2h_summary:
        h2h_text = (
            f'\nH2H (Son {h2h_summary["total"]} maç):\n'
            f'- {home_team} galibiyet: {h2h_summary["home_wins"]}\n'
            f'- {away_team} galibiyet: {h2h_summary["away_wins"]}\n'
            f'- Beraberlik: {h2h_summary["draws"]}\n'
            f'- Maç başı ort. gol: {h2h_summary["avg_goals"]}'
        )

    stats_text = ''
    if home_goals_avg > 0 or away_goals_avg > 0:
        stats_text = '\nGenel İstatistikler (son maçlar):\n'
        stats_text += f'- {home_team}: ort. {home_goals_avg} gol atar / {home_conceded_avg} gol yer\n'
        stats_text += f'- {away_team}: ort. {away_goals_avg} gol atar / {away_conceded_avg} gol yer\n'
        stats_text += f'- {home_team} form: {home_form if home_form else "Bilinmiyor"}\n'
        stats_text += f'- {away_team} form: {away_form if away_form else "Bilinmiyor"}'
    else:
        stats_text = (
            f'\nForm Bilgisi:\n'
            f'- {home_team} form: {home_form if home_form else "Bilinmiyor"}\n'
            f'- {away_team} form: {away_form if away_form else "Bilinmiyor"}'
        )

    trend_text = ''
    if home_goals_trend or away_goals_trend:
        trend_text = '\nGol Trendi (Son 5 Maç — eskiden yeniye):\n'
        if home_goals_trend:
            trend_text += f'- {home_team} attığı: {" | ".join(str(g) for g in home_goals_trend["scored"])} (ort. {home_goals_trend["scored_avg"]})\n'
            trend_text += f'- {home_team} yediği: {" | ".join(str(g) for g in home_goals_trend["conceded"])} (ort. {home_goals_trend["conceded_avg"]})\n'
        if away_goals_trend:
            trend_text += f'- {away_team} attığı: {" | ".join(str(g) for g in away_goals_trend["scored"])} (ort. {away_goals_trend["scored_avg"]})\n'
            trend_text += f'- {away_team} yediği: {" | ".join(str(g) for g in away_goals_trend["conceded"])} (ort. {away_goals_trend["conceded_avg"]})\n'

    shot_text = ''
    if home_shot_stats or away_shot_stats:
        shot_text = '\nŞut İstatistikleri (son 5 maç ortalaması):\n'
        if home_shot_stats:
            shot_text += (f'- {home_team}: {home_shot_stats["shots_avg"]} şut/maç, '
                          f'{home_shot_stats["shots_on_target_avg"]} isabetli, '
                          f'%{home_shot_stats["shot_accuracy"]} isabet oranı, '
                          f'{home_shot_stats["shots_conceded_avg"]} yenilen şut/maç\n')
        if away_shot_stats:
            shot_text += (f'- {away_team}: {away_shot_stats["shots_avg"]} şut/maç, '
                          f'{away_shot_stats["shots_on_target_avg"]} isabetli, '
                          f'%{away_shot_stats["shot_accuracy"]} isabet oranı, '
                          f'{away_shot_stats["shots_conceded_avg"]} yenilen şut/maç\n')
        if home_shot_stats and away_shot_stats:
            h_acc = home_shot_stats['shot_accuracy']
            a_acc = away_shot_stats['shot_accuracy']
            h_on = home_shot_stats['shots_on_target_avg']
            a_on = away_shot_stats['shots_on_target_avg']
            dominant = home_team if h_on > a_on else away_team
            shot_text += f'- İsabetli şut üstünlüğü: {dominant} ({max(h_on, a_on)} vs {min(h_on, a_on)}/maç)\n'

    venue_text = ''
    has_venue = (home_home_avg is not None and home_home_avg > 0) or (away_away_avg is not None and away_away_avg > 0)
    if has_venue:
        venue_text = '\nEv/Deplasman İstatistikleri:\n'
        if home_home_avg is not None:
            venue_text += f'- {home_team} (EV): ort. {home_home_avg} gol atar / {home_conceded_home_avg or 0} gol yer'
            if home_home_form: venue_text += f' | ev formu: {home_home_form}'
            venue_text += '\n'
        if away_away_avg is not None:
            venue_text += f'- {away_team} (DEPLASMAN): ort. {away_away_avg} gol atar / {away_conceded_away_avg or 0} gol yer'
            if away_away_form: venue_text += f' | deplasman formu: {away_away_form}'
            venue_text += '\n'

    standing_text = ''
    if home_standing or away_standing:
        standing_text = '\nPuan Durumu:\n'
        if home_standing:
            standing_text += (f'- {home_team}: {home_standing["position"]}. sıra | {home_standing["points"]} puan | '
                              f'{home_standing["played"]} maç | {home_standing["won"]}G {home_standing["draw"]}B {home_standing["lost"]}M\n')
            if home_standing.get('home_position') is not None:
                standing_text += (f'  Ev sırası: {home_standing["home_position"]}. | '
                                  f'{home_standing.get("home_won",0)}G {home_standing.get("home_draw",0)}B {home_standing.get("home_lost",0)}M\n')
        if away_standing:
            standing_text += (f'- {away_team}: {away_standing["position"]}. sıra | {away_standing["points"]} puan | '
                              f'{away_standing["played"]} maç | {away_standing["won"]}G {away_standing["draw"]}B {away_standing["lost"]}M\n')
            if away_standing.get('away_position') is not None:
                standing_text += (f'  Deplasman sırası: {away_standing["away_position"]}. | '
                                  f'{away_standing.get("away_won",0)}G {away_standing.get("away_draw",0)}B {away_standing.get("away_lost",0)}M\n')

    csv_text = build_csv_section(home_team, away_team, csv_data)

    # CSV hint
    csv_hint = ''
    if csv_data:
        hints = []
        if csv_data.get('home_shots_on') and csv_data.get('away_shots_on'):
            try:
                hs = float(csv_data.get('home_shots', 1) or 1)
                hon = float(csv_data['home_shots_on'])
                as_ = float(csv_data.get('away_shots', 1) or 1)
                aon = float(csv_data['away_shots_on'])
                h_acc = round(hon / hs * 100, 1)
                a_acc = round(aon / as_ * 100, 1)
                hints.append(f'İsabetli şut oranı: {home_team} %{h_acc} vs {away_team} %{a_acc} — gol beklentisini destekler')
            except (ValueError, TypeError, ZeroDivisionError) as e:
                logger.debug(f'Shot hint calc skipped: {e}')
        if csv_data.get('home_xg') and csv_data.get('away_xg'):
            hints.append('xG verileri en güvenilir tahmin kaynağı — yüksek xG → yüksek gol beklentisi')
        if csv_data.get('over25_avg'):
            hints.append(f'Over 2.5 için CSV ortalaması %{csv_data["over25_avg"]} — over25_pct için temel referans')
        if csv_data.get('btts_avg'):
            hints.append(f'KG VAR için CSV ortalaması %{csv_data["btts_avg"]} — btts_pct için temel referans')
        if csv_data.get('ht_over05_avg'):
            hints.append(f'İlk yarı gol için CSV ortalaması %{csv_data["ht_over05_avg"]} — ht2g_pct için temel referans')
        # ── YENİ: Güncel PPG ve 2. yarı ipuçları ─────────────────────────────
        if csv_data.get('current_home_ppg') and csv_data.get('home_ppg'):
            try:
                diff = float(csv_data['current_home_ppg']) - float(csv_data['home_ppg'])
                if abs(diff) > 0.2:
                    trend = 'form yukarı' if diff > 0 else 'form aşağı'
                    hints.append(f'{home_team} güncel PPG farkı {diff:+.2f} → {trend} — form momentumu dikkate al')
            except (ValueError, TypeError) as e:
                logger.debug(f'PPG hint skipped for {home_team}: {e}')
        if csv_data.get('current_away_ppg') and csv_data.get('away_ppg'):
            try:
                diff = float(csv_data['current_away_ppg']) - float(csv_data['away_ppg'])
                if abs(diff) > 0.2:
                    trend = 'form yukarı' if diff > 0 else 'form aşağı'
                    hints.append(f'{away_team} güncel PPG farkı {diff:+.2f} → {trend} — form momentumu dikkate al')
            except (ValueError, TypeError) as e:
                logger.debug(f'PPG hint skipped for {away_team}: {e}')
        if csv_data.get('ht2_over05_avg'):
            hints.append(f'2. yarı gol ihtimali %{csv_data["ht2_over05_avg"]} — maçın ikinci yarısı baskı göstergesi')
        # ─────────────────────────────────────────────────────────────────────
        # xG-BTTS fix uyarısı: her iki xG >= 1.0 ise btts min %50 olacak
        hxg_hint = csv_data.get('home_xg')
        axg_hint = csv_data.get('away_xg')
        btts_hint = csv_data.get('btts_avg')
        if hxg_hint and axg_hint and btts_hint:
            try:
                if float(hxg_hint) >= 1.0 and float(axg_hint) >= 1.0 and float(btts_hint) < 50:
                    hints.append(f'Her iki takım da yüksek gol tehlikesi yarattığından karşılıklı gol ihtimali en az %50 olarak değerlendiriliyor (ham veri %{btts_hint} olsa da)')
            except (ValueError, TypeError) as e:
                logger.debug(f'xG-BTTS hint skipped: {e}')
        if hints:
            csv_hint = '\nCSV Veri Önceliklendirmesi:\n' + '\n'.join(f'- {h}' for h in hints) + '\n'

    match_importance = detect_match_importance(league)

    has_xg = csv_data and csv_data.get('home_xg') and csv_data.get('away_xg')
    has_form = bool(home_form and away_form)
    has_venue_stats = has_venue
    has_standing = bool(home_standing or away_standing)

    over25_csv = csv_data.get('over25_avg') if csv_data else None
    btts_csv = csv_data.get('btts_avg') if csv_data else None
    ht_csv = csv_data.get('ht_over05_avg') if csv_data else None

    # ── H2H gol ortalaması — over25/btts için referans ───────────────────────
    h2h_avg_goals = None
    h2h_favors = None
    if h2h_fd and h2h_fd.get('total', 0) >= 3:
        h2h_avg_goals = h2h_fd['avg_goals']
        total = h2h_fd['total']
        hw = h2h_fd['home_wins']
        aw = h2h_fd['away_wins']
        if hw > aw + 1:
            h2h_favors = '1'
        elif aw > hw + 1:
            h2h_favors = '2'
        else:
            h2h_favors = 'X'
    # ─────────────────────────────────────────────────────────────────────────

    pct_rules = '\n── Yüzde Hesaplama Kuralları (ZORUNLU) ──\n'
    pct_rules += 'CSV verileri varsa aşağıdaki sapma sınırlarına KESINLIKLE uy:\n\n'

    if over25_csv is not None:
        pct_rules += f'over25_pct için:\n'
        pct_rules += f'  - Baz değer: CSV over25_avg = %{over25_csv}\n'
        pct_rules += f'  - İzin verilen aralık: %{max(0, float(over25_csv)-10)} ile %{min(100, float(over25_csv)+10)} arası\n'
        pct_rules += f'  - Form trendi her iki takımda da 3+ gol ortalaması → +10\'a kadar artır\n'
        pct_rules += f'  - Her iki takımda da 1\'den az gol ortalaması → -10\'a kadar düşür\n'
        pct_rules += f'  - Bu aralığın DIŞINA ÇIKMA\n\n'
    else:
        pct_rules += 'over25_pct: CSV yok — form trendi + gol ortalamalarına göre serbest hesapla\n\n'

    if btts_csv is not None:
        pct_rules += f'btts_pct için:\n'
        pct_rules += f'  - Baz değer: CSV btts_avg = %{btts_csv}\n'
        pct_rules += f'  - İzin verilen aralık: %{max(0, float(btts_csv)-8)} ile %{min(100, float(btts_csv)+8)} arası\n'
        pct_rules += f'  - Her iki takım son 5\'te gol attıysa → +8\'e kadar artır\n'
        pct_rules += f'  - Bir takım son 5\'te 2\'den az gol attıysa → -8\'e kadar düşür\n'
        pct_rules += f'  - Bu aralığın DIŞINA ÇIKMA\n\n'
    else:
        pct_rules += 'btts_pct: CSV yok — gol ortalamaları + form trendiyle serbest hesapla\n\n'

    if ht_csv is not None:
        pct_rules += f'ht2g_pct için:\n'
        pct_rules += f'  - Baz değer: CSV ht_over05_avg = %{ht_csv}\n'
        pct_rules += f'  - İzin verilen aralık: %{max(0, float(ht_csv)-5)} ile %{min(100, float(ht_csv)+5)} arası\n'
        pct_rules += f'  - Bu aralığın DIŞINA ÇIKMA — ilk yarı istatistiği en sabit veridir\n\n'
    else:
        pct_rules += 'ht2g_pct: CSV yok — form trendi + gol ortalamasıyla serbest hesapla\n\n'

    if h2h_avg_goals is not None:
        pct_rules += f'H2H Gol Ortalaması Düzeltmesi (resmi kayıt, {h2h_fd["total"]} maç):\n'
        pct_rules += f'  - H2H ort. gol: {h2h_avg_goals}\n'
        if h2h_avg_goals >= 3.0:
            pct_rules += f'  - Yüksek H2H golü → over25_pct ve btts_pct +5\'e kadar artır\n'
        elif h2h_avg_goals >= 2.5:
            pct_rules += f'  - H2H over 2.5 ortalaması → over25_pct baz değerini destekliyor\n'
        elif h2h_avg_goals < 1.8:
            pct_rules += f'  - Düşük H2H golü → over25_pct ve btts_pct -5\'e kadar düşür\n'
        else:
            pct_rules += f'  - H2H gol ortalaması nötr — diğer verilere göre karar ver\n'

    pct_rules += '── Yüzde Kuralları Sonu ──\n'

    shot_rules = ''
    if home_shot_stats or away_shot_stats:
        h_on = home_shot_stats.get('shots_on_target_avg', 0) if home_shot_stats else 0
        a_on = away_shot_stats.get('shots_on_target_avg', 0) if away_shot_stats else 0
        h_acc = home_shot_stats.get('shot_accuracy', 0) if home_shot_stats else 0
        a_acc = away_shot_stats.get('shot_accuracy', 0) if away_shot_stats else 0
        total_on = (h_on or 0) + (a_on or 0)

        shot_rules = '\n── Şut Bazlı Tahmin Kuralları (ZORUNLU) ──\n'
        shot_rules += f'Toplam isabetli şut/maç: {total_on} (ev {h_on} + dep {a_on})\n\n'

        shot_rules += 'over25_pct için şut düzeltmesi:\n'
        if total_on >= 10:
            shot_rules += f'  - Toplam isabetli şut {total_on} ≥ 10 → over25_pct minimum %55 olmalı\n'
        elif total_on <= 5:
            shot_rules += f'  - Toplam isabetli şut {total_on} ≤ 5 → over25_pct maximum %50 olmalı\n'
        else:
            shot_rules += f'  - Toplam isabetli şut {total_on} orta bölge → CSV baz değerine yakın kal\n'

        shot_rules += '\nbtts_pct için şut düzeltmesi:\n'
        if h_on >= 4.5 and a_on >= 4.5:
            shot_rules += f'  - Her iki takım da {h_on}/{a_on} isabetli şut üretiyor → btts_pct minimum %55 olmalı\n'
        elif h_on <= 2.5 or a_on <= 2.5:
            low_team = home_team if (h_on or 0) <= 2.5 else away_team
            shot_rules += f'  - {low_team} isabetli şutu düşük ({min(h_on or 0, a_on or 0)}/maç) → btts_pct maximum %45 olmalı\n'
        else:
            shot_rules += '  - Şut dengeli → CSV btts_avg baz değerine yakın kal\n'

        shot_rules += '\nİsabet oranı yorumu:\n'
        if h_acc >= 40:
            shot_rules += f'  - {home_team} isabet oranı %{h_acc} — yüksek → gol üretme kapasitesi güçlü\n'
        elif h_acc <= 25:
            shot_rules += f'  - {home_team} isabet oranı %{h_acc} — düşük → etkisiz hücum, over25 kır\n'
        if a_acc >= 40:
            shot_rules += f'  - {away_team} isabet oranı %{a_acc} — yüksek → gol üretme kapasitesi güçlü\n'
        elif a_acc <= 25:
            shot_rules += f'  - {away_team} isabet oranı %{a_acc} — düşük → etkisiz hücum, over25 kır\n'

        shot_rules += '── Şut Kuralları Sonu ──\n'

    hxg = csv_data.get('home_xg') if csv_data else None
    axg = csv_data.get('away_xg') if csv_data else None
    xg_diff = round(float(hxg) - float(axg), 2) if (hxg and axg) else None

    # ── Odds implied probability hesapla ────────────────────────────────────
    home_implied = None
    away_implied = None
    odds_favors = None
    if csv_data:
        try:
            h_odds = float(csv_data.get('odds_home') or 0)
            a_odds = float(csv_data.get('odds_away') or 0)
            if h_odds > 1 and a_odds > 1:
                home_implied = round(1 / h_odds * 100, 1)
                away_implied = round(1 / a_odds * 100, 1)
                imp_diff = home_implied - away_implied
                if imp_diff > 15:
                    odds_favors = '1'  # ev sahibi güçlü favori
                elif imp_diff < -15:
                    odds_favors = '2'  # deplasman güçlü favori
                elif imp_diff > 5:
                    odds_favors = '1_soft'  # ev sahibi hafif favori
                elif imp_diff < -5:
                    odds_favors = '2_soft'  # deplasman hafif favori
                else:
                    odds_favors = 'X'  # dengeli
        except (ValueError, TypeError, ZeroDivisionError) as e:
            logger.debug(f'Odds implied probability calc skipped: {e}')
    # ─────────────────────────────────────────────────────────────────────────

    # ── Güncel PPG farkı hesapla ──────────────────────────────────────────────
    ppg_favors = None
    if csv_data:
        try:
            ch = float(csv_data.get('current_home_ppg') or 0)
            ca = float(csv_data.get('current_away_ppg') or 0)
            if ch > 0 or ca > 0:
                ppg_diff = ch - ca
                if ppg_diff > 0.5:
                    ppg_favors = '1'
                elif ppg_diff < -0.5:
                    ppg_favors = '2'
                else:
                    ppg_favors = 'X'
        except (ValueError, TypeError) as e:
            logger.debug(f'PPG favors calc skipped: {e}')
    # ─────────────────────────────────────────────────────────────────────────

    # ── Ev/Deplasman sırası karşılaştırması ──────────────────────────────────
    venue_rank_favors = None
    try:
        h_home_pos = home_standing.get('home_position') if home_standing else None
        a_away_pos = away_standing.get('away_position') if away_standing else None
        if h_home_pos is not None and a_away_pos is not None:
            diff = a_away_pos - h_home_pos  # pozitif → ev sahibi daha üst sırada
            if diff >= 4:
                venue_rank_favors = '1'
            elif diff <= -4:
                venue_rank_favors = '2'
            else:
                venue_rank_favors = 'X'
    except (TypeError, ValueError) as e:
        logger.debug(f'Venue rank favors calc skipped: {e}')
    # ─────────────────────────────────────────────────────────────────────────

    prediction_rules = '\n── Taraf Tahmini Kuralları (ZORUNLU) ──\n'
    prediction_rules += 'KARAR HİYERARŞİSİ (öncelik sırası):\n'
    prediction_rules += '  1. Bahisçi oranı (piyasa konsensüsü) — en güvenilir gösterge\n'
    prediction_rules += '  2. Güncel PPG (sezon içi form trendi)\n'
    prediction_rules += '  3. Final Güven (bahisçi + PPG uyumu)\n\n'
    prediction_rules += '⚠️ xG verisi SADECE over/under ve BTTS tahmininde kullanılır, taraf kararını ETKİLEMEZ.\n\n'
    prediction_rules += 'prediction_1x2 ve güven seviyesi belirlenirken aşağıdaki kurallara KESINLIKLE uy:\n\n'

    # Odds analizi
    if home_implied and away_implied:
        prediction_rules += f'Bahisçi Oranı Analizi: {home_team} implied %{home_implied} | {away_team} implied %{away_implied}\n'
        imp_diff = home_implied - away_implied
        if abs(imp_diff) > 15:
            fav = home_team if imp_diff > 0 else away_team
            fav_val = "1" if imp_diff > 0 else "2"
            prediction_rules += f'  → Piyasa NET favori: {fav} ({fav_val}) — %{abs(imp_diff):.0f} fark\n'
            prediction_rules += f'  → Bu tarafı desteklemeyen veriler zayıf kalır\n\n'
        elif abs(imp_diff) > 5:
            fav = home_team if imp_diff > 0 else away_team
            fav_val = "1" if imp_diff > 0 else "2"
            prediction_rules += f'  → Piyasa hafif favori: {fav} ({fav_val}) — diğer verilerle teyit et\n\n'
        else:
            prediction_rules += f'  → Piyasa dengeli — form ve xG belirleyici\n\n'

    # PPG analizi
    if ppg_favors:
        ch = float(csv_data.get('current_home_ppg') or 0) if csv_data else 0
        ca = float(csv_data.get('current_away_ppg') or 0) if csv_data else 0
        prediction_rules += f'Güncel PPG: {home_team}={ch} | {away_team}={ca}\n'
        if ppg_favors == '1':
            prediction_rules += f'  → {home_team} güncel formda belirgin üstün\n\n'
        elif ppg_favors == '2':
            prediction_rules += f'  → {away_team} güncel formda belirgin üstün\n\n'
        else:
            prediction_rules += f'  → PPG dengeli\n\n'

    # Ev/deplasman sırası analizi
    if venue_rank_favors is not None:
        h_hp = home_standing.get('home_position') if home_standing else None
        a_ap = away_standing.get('away_position') if away_standing else None
        h_hw = home_standing.get('home_won', 0) if home_standing else 0
        h_hd = home_standing.get('home_draw', 0) if home_standing else 0
        h_hl = home_standing.get('home_lost', 0) if home_standing else 0
        a_aw = away_standing.get('away_won', 0) if away_standing else 0
        a_ad = away_standing.get('away_draw', 0) if away_standing else 0
        a_al = away_standing.get('away_lost', 0) if away_standing else 0
        prediction_rules += f'Ev/Deplasman Sırası:\n'
        if h_hp is not None:
            prediction_rules += f'  {home_team} evde {h_hp}. sıra ({h_hw}G {h_hd}B {h_hl}M)\n'
        if a_ap is not None:
            prediction_rules += f'  {away_team} deplasmanda {a_ap}. sıra ({a_aw}G {a_ad}B {a_al}M)\n'
        if venue_rank_favors == '1':
            prediction_rules += f'  → {home_team} bu sahada belirgin üstün (sıra farkı ≥4)\n\n'
        elif venue_rank_favors == '2':
            prediction_rules += f'  → {away_team} deplasmanda belirgin üstün (sıra farkı ≥4)\n\n'
        else:
            prediction_rules += f'  → Ev/dep performansları dengeli\n\n'

    # Kombinasyon kuralları
    prediction_rules += 'Kombinasyon karar kuralları (ZORUNLU):\n'
    if odds_favors and odds_favors != 'X' and ppg_favors and ppg_favors != 'X':
        odds_side = odds_favors.replace('_soft', '')
        if odds_side == ppg_favors:
            fav_name = home_team if odds_side == '1' else away_team
            prediction_rules += f'  ✓ BAHİSÇİ + PPG AYNI TARAF ({fav_name}) → {odds_side} seç, güven yüksek\n'
        else:
            fav_odds = home_team if odds_side == '1' else away_team
            fav_ppg = home_team if ppg_favors == '1' else away_team
            prediction_rules += f'  ⚠️ Çelişki: Bahisçi={fav_odds}, PPG={fav_ppg} — bahisçiye ağırlık ver\n'
    prediction_rules += '  - Bahisçi net favori (>%15 fark) → o tarafı seç, xG tek başına geçemez\n'
    prediction_rules += '  - Bahisçi + PPG aynı yönde → güvenle o tarafı seç\n'
    prediction_rules += '  - Bahisçi + PPG + ev/dep sırası üçü aynı yönde → çok güçlü gösterge\n'
    if h2h_favors and h2h_favors != 'X':
        h2h_fav_name = home_team if h2h_favors == '1' else away_team
        prediction_rules += f'  - H2H tarihsel üstünlük: {h2h_fav_name} — diğer göstergelerle örtüşüyorsa ağırlık ver\n'
    prediction_rules += '  - Sadece xG yüksek ama bahisçi karşı tarafta → bahisçiye uyu\n'
    prediction_rules += '  - Tüm göstergeler çelişkili → "X" ver\n\n'

    prediction_rules += 'Beraberlik (X) ne zaman verilmeli:\n'
    prediction_rules += '  - Bahisçi dengeli VE PPG benzer\n'
    prediction_rules += '  - Her iki takım da tutarsız form gösteriyorsa\n'
    prediction_rules += '  ❌ YANLIŞ: xG eşit diye otomatik X verme!\n\n'
    prediction_rules += '── Taraf Kuralları Sonu ──\n'

    confidence_rules = '''
── Güven Seviyesi Belirleme Kuralları (ZORUNLU) ──
TEMEL PRENSİP: Güven seviyesi KAZANMA ihtimalini gösterir — gol sayısını değil.
xG yüksek olan takım çok gol atabilir ama kaybedebilir. Bu yüzden güveni xG belirlemez.

KARAR FAKTÖRLERİ (öncelik sırası):
  1. Piyasa beklentisi (bahisçi oranları) — en güvenilir gösterge
  2. Güncel form (PPG — son dönem performansı)
  3. Ev/deplasman sırası (bu sahadaki performans)
  4. Puan durumu (genel sıra)

⚠️ "Çok Yüksek" artık KULLANILMIYOR. Maksimum güven seviyesi "Yüksek"tir.

KURAL 1 — "Yüksek":
  Bahisçi (1) + PPG (2) aynı tarafı gösteriyorsa — ev/dep sırası eksik veya farklı olsa bile
  (Bahisçi + PPG + ev/dep üçü aynı yönde → yine Yüksek)

KURAL 2 — "Orta":
  Sadece bahisçi net favori, PPG verisi yok
  VEYA göstergeler dengeli

KURAL 3 — "Düşük":
  Bahisçi ve PPG çelişiyor

KURAL 4 — Kupa/hazırlık maçlarında maksimum güven "Orta"dır

''' + f'''Mevcut veri durumu:
  - Piyasa analizi: {"VAR ✓" if home_implied else "YOK ✗"}
  - Güncel form (PPG): {"VAR ✓" if ppg_favors else "YOK ✗"}
  - Ev/dep sırası: {"VAR ✓" if venue_rank_favors is not None else "YOK ✗"}
  - H2H geçmiş (resmi): {"VAR ✓ (" + str(h2h_fd["total"]) + " maç)" if h2h_fd else "YOK ✗"}
  - Ev/dep istatistik: {"VAR ✓" if has_venue_stats else "YOK ✗"}
  - Puan durumu: {"VAR ✓" if has_standing else "YOK ✗"}
── Güven Kuralları Sonu ──
'''

    prompt = (
        'Aşağıdaki futbol maçını analiz et ve SADECE JSON formatında yanıt ver:\n\n'
        f'Maç: {home_team} vs {away_team}\n'
        f'Lig: {league}\n'
        f'Tarih: {match_time}\n'
        f'Maç Tipi: {match_importance}\n'
        + stats_text + '\n'
        + trend_text + '\n'
        + shot_text + '\n'
        + venue_text + '\n'
        + standing_text + '\n'
        + h2h_text + '\n'
        + csv_text + '\n'
        + csv_hint + '\n'
        + pct_rules + '\n'
        + shot_rules + '\n'
        + prediction_rules + '\n'
        + confidence_rules + '\n'
        + 'Genel analiz talimatları:\n'
        '1. CSV xG verisi varsa en güvenilir kaynak olarak kullan\n'
        '2. Yüzdeler için yukarıdaki sapma kurallarına kesinlikle uy\n'
        '3. Ev sahibi avantajı + ev/deplasman istatistiklerini birlikte değerlendir\n'
        '4. Puan durumu motivasyonu: küme düşme baskısı veya şampiyonluk yarışı\n'
        '5. H2H geçmişi varsa dikkate al\n'
        '6. Tüm yanıtlar TÜRKÇE olacak\n'
        '7. "Elo" kelimesini kullanma, "Güç Puanı" kullan\n'
        '11. Reasoning yazarken teknik terimler KULLANMA — kullanıcı dostu dil kullan:\n'
        '    - "xG", "CSV", "PPG", "implied", "btts_avg", "over25_avg" → KULLANMA\n'
        '    - xG yerine: "hücum gücü", "gol üretme kapasitesi", "tehlike yaratma potansiyeli"\n'
        '    - CSV ortalaması yerine: "bu fikstürün gol geçmişi", "maç istatistikleri", "geçmiş veriler"\n'
        '    - bahisçi oranı/implied yerine: "piyasa beklentisi", "oran analizi", "genel kanı"\n'
        '    - PPG/puan ortalaması yerine: "güncel form", "son dönem performansı"\n'
        '    - BTTS yerine: "her iki takımın gol bulması", "karşılıklı gol"\n'
        '    - over 2.5 yerine: "maçta 3 veya daha fazla gol", "golcü maç beklentisi"\n'
        '    Kulağa doğal ve anlaşılır gelsin — sanki bir analist yorumluyormuş gibi yaz\n'
        '8. predicted_ht_score ilk yarı tahmini, predicted_score maç sonu tahmini — ikisi tutarlı olmalı\n'
        '   Örnek: İY 1-0 tahmini yapıyorsan maç sonu 1-0, 2-0, 1-1, 2-1 olabilir — 0-1 olamaz\n'
        '9. Skor tahmini kuralları (ZORUNLU):\n'
        '   - btts_pct < %40 → en az bir takım 0 atmalı (1-0, 2-0, 0-1, 0-2 gibi)\n'
        '   - btts_pct > %65 → her iki takım da gol atmalı (1-1, 2-1, 1-2 gibi)\n'
        '   - over25_pct < %40 → toplam gol MAX 2 olmalı (1-0, 0-1, 1-1, 2-0, 0-2)\n'
        '   - over25_pct > %70 → toplam gol MIN 3 olmalı (2-1, 3-0, 1-2, 3-1 gibi)\n'
        '   - CSV over35_avg >= %55 ise predicted_score toplam golü MIN 4 olmalı (3-1, 2-2, 1-3, 4-0 gibi)\n'
        '   - CSV over45_avg >= %35 ise predicted_score toplam golü MIN 5 olmalı (3-2, 4-1, 2-3 gibi)\n'
        '   - CSV over25_avg yüksek ama over35_avg düşükse 2-1 / 1-2 / 3-0 bandında kal\n'
        '   - prediction_1x2=1 → ev sahibi skoru deplasmandan yüksek olmalı\n'
        '   - prediction_1x2=2 → deplasman skoru ev sahibinden yüksek olmalı\n'
        '   - prediction_1x2=X → skorlar eşit olmalı (1-1, 2-2, 0-0)\n'
        '   - Toplam gol MAX 5 olsun, uçuk skorlar verme (5-3, 6-1 gibi)\n'
        '10. İstatistik tutarlılık kuralları (ZORUNLU):\n'
        '   - btts_pct > %60 ise over25_pct MINIMUM %45 olmalı\n'
        '     (Her iki takım gol atıyorsa toplam gol az olamaz)\n'
        '   - btts_pct < %35 ise over25_pct MAXIMUM %55 olmalı\n'
        '     (Kimse gol atmıyorsa toplam gol çok olamaz)\n'
        '   - over25_pct > %70 ise ht2g_pct MINIMUM %60 olmalı\n'
        '     (Maç golsüz olmayacaksa ilk yarı da golsüz olmaz)\n'
        '   - over25_pct < %35 ise btts_pct MAXIMUM %45 olmalı\n'
        '     (Az gol olan maçta her iki takım gol atamaz)\n\n'
        'SADECE şu JSON formatında yanıt ver:\n'
        '{\n'
        '  "prediction_1x2": "1 veya X veya 2",\n'
        '  "over25_pct": 55,\n'
        '  "ht2g_pct": 40,\n'
        '  "btts_pct": 45,\n'
        '  "predicted_score": "2-1",\n'
        '  "predicted_ht_score": "1-0",\n'
        '  "confidence": "Orta",\n'
        '  "reasoning": [\n'
        f'    "{home_team} — form, xG ve güçlü/zayıf yönleri",\n'
        f'    "{away_team} — form, xG ve güçlü/zayıf yönleri",\n'
        '    "Maç geneli tahmin — over/under ve KG VAR/YOK gerekçesi",\n'
        '    "Korner yorumu — ort. korner ve over oranlarına göre beklenti",\n'
        '    "2. yarı gol yorumu — ikinci yarı gol beklentisi ve gerekçesi"\n'
        '  ],\n'
        '  "h2h_summary": "H2H özeti"\n'
        '}'
    )
    return prompt


def call_groq(prompt):
    response = requests.post(
        'https://api.groq.com/openai/v1/chat/completions',
        headers={'Authorization': 'Bearer ' + GROQ_API_KEY, 'Content-Type': 'application/json'},
        json={
            'model': 'llama-3.3-70b-versatile',
            'messages': [
                {'role': 'system', 'content': 'Sen profesyonel bir futbol bahis analistisin. Tüm yanıtlar TÜRKÇE olacak. Elo kelimesini kullanma.'},
                {'role': 'user', 'content': prompt}
            ],
            'max_tokens': 1000, 'temperature': 0.7
        }, timeout=30
    )
    response.raise_for_status()
    return response.json()['choices'][0]['message']['content'].strip()


def call_anthropic(prompt):
    response = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={'x-api-key': ANTHROPIC_API_KEY, 'anthropic-version': '2023-06-01', 'content-type': 'application/json'},
        json={
            'model': 'claude-sonnet-4-6',
            'max_tokens': 4000,
            'system': 'Sen profesyonel bir futbol bahis analistisin. Tüm yanıtlar TÜRKÇE olacak. Elo kelimesini kullanma.',
            'messages': [{'role': 'user', 'content': prompt}]
        }, timeout=60
    )
    response.raise_for_status()
    return response.json()['content'][0]['text'].strip()


def call_gemini(prompt):
    time.sleep(3)
    response = requests.post(
        'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=' + GEMINI_API_KEY,
        headers={'Content-Type': 'application/json'},
        json={
            'contents': [{'parts': [{'text': 'Sen profesyonel bir futbol bahis analistisin. TÜRKÇE yaz. SADECE JSON döndür.\n\n' + prompt}]}],
            'generationConfig': {'maxOutputTokens': 1000, 'temperature': 0.7, 'responseMimeType': 'application/json'}
        }, timeout=30
    )
    response.raise_for_status()
    return response.json()['candidates'][0]['content']['parts'][0]['text'].strip()


def parse_result(raw_text):
    raw_text = raw_text.strip()
    if '```json' in raw_text:
        raw_text = raw_text.split('```json')[1].split('```')[0].strip()
    elif '```' in raw_text:
        raw_text = raw_text.split('```')[1].split('```')[0].strip()
    start = raw_text.find('{')
    end = raw_text.rfind('}')
    if start != -1 and end != -1:
        raw_text = raw_text[start:end+1]
    return json.loads(raw_text)


def merge_results(r1, r2):
    conf_order = ['Düşük', 'Orta', 'Yüksek', 'Çok Yüksek']
    pred = r1.get('prediction_1x2') if r1.get('prediction_1x2') == r2.get('prediction_1x2') else r1.get('prediction_1x2')
    over25 = round((float(r1.get('over25_pct', 50)) + float(r2.get('over25_pct', 50))) / 2)
    ht2g = round((float(r1.get('ht2g_pct', 40)) + float(r2.get('ht2g_pct', 40))) / 2)
    btts = round((float(r1.get('btts_pct', 40)) + float(r2.get('btts_pct', 40))) / 2)
    c1 = conf_order.index(r1.get('confidence', 'Orta')) if r1.get('confidence') in conf_order else 1
    c2 = conf_order.index(r2.get('confidence', 'Orta')) if r2.get('confidence') in conf_order else 1
    return {
        'prediction_1x2': pred, 'over25_pct': over25, 'ht2g_pct': ht2g, 'btts_pct': btts,
        'predicted_score': r1.get('predicted_score', '?-?'), 'confidence': conf_order[min(c1, c2)],
        'reasoning': r1.get('reasoning', r2.get('reasoning', [])),
        'h2h_summary': r1.get('h2h_summary', '')
    }


def _safe_float(v):
    try:
        if v is None or v == '':
            return None
        return float(v)
    except:
        return None


def _shot_pressure_score(home_shot_stats, away_shot_stats):
    """
    Şut istatistiklerinden 0-3 arası baskı skoru üretir.
    Yüksek → golcü maç beklentisi, düşük → az gollü maç.
    Döndürür: (pressure_score, dominant_side)
      pressure_score: 0=düşük, 1=orta-düşük, 2=orta-yüksek, 3=yüksek
      dominant_side: '1' | '2' | 'X'
    """
    if not home_shot_stats and not away_shot_stats:
        return None, 'X'

    h_on = _safe_float(home_shot_stats.get('shots_on_target_avg') if home_shot_stats else None) or 0
    a_on = _safe_float(away_shot_stats.get('shots_on_target_avg') if away_shot_stats else None) or 0
    h_acc = _safe_float(home_shot_stats.get('shot_accuracy') if home_shot_stats else None) or 0
    a_acc = _safe_float(away_shot_stats.get('shot_accuracy') if away_shot_stats else None) or 0
    h_conc = _safe_float(home_shot_stats.get('shots_conceded_avg') if home_shot_stats else None) or 0
    a_conc = _safe_float(away_shot_stats.get('shots_conceded_avg') if away_shot_stats else None) or 0

    total_on = h_on + a_on
    avg_acc = (h_acc + a_acc) / 2 if (h_acc and a_acc) else max(h_acc, a_acc)

    # Baskı skoru: toplam isabetli şut + isabet oranı ağırlıklı
    if total_on >= 10 and avg_acc >= 38:
        pressure = 3   # çok yüksek
    elif total_on >= 8 or avg_acc >= 35:
        pressure = 2   # orta-yüksek
    elif total_on >= 5 or avg_acc >= 28:
        pressure = 1   # orta-düşük
    else:
        pressure = 0   # düşük

    # Dominant taraf: isabetli şut + karşı tarafa yenilen şut kombine
    h_attack = h_on + (a_conc * 0.3)
    a_attack = a_on + (h_conc * 0.3)
    diff = h_attack - a_attack
    if abs(diff) < 0.8:
        dominant = 'X'
    elif diff > 0:
        dominant = '1'
    else:
        dominant = '2'

    return pressure, dominant


def _pick_score_by_csv_rules(pred_1x2, btts_pct, over25_pct, over35_avg=None, over45_avg=None,
                              home_shot_stats=None, away_shot_stats=None):
    """
    CSV 3.5/4.5 üst yüzdelerine göre daha gerçekçi skor üretir.
    Şut istatistikleri varsa tempo filtresi uygular.
    Öncelik sırası: 4.5 üst > 3.5 üst > şut baskısı > 2.5 üst > düşük gol.
    pred_1x2 == 'X' için her zaman eşit skor döndürür.
    """
    o35 = _safe_float(over35_avg)
    o45 = _safe_float(over45_avg)
    btts = _safe_float(btts_pct) or 0
    o25 = _safe_float(over25_pct) or 0

    # Şut baskı skoru
    pressure, shot_dominant = _shot_pressure_score(home_shot_stats, away_shot_stats)

    # Şut baskısına göre over25 soft-adjust (CSV clamp'ten önce gelmiyor, fallback'i etkiliyor)
    if pressure is not None:
        if pressure == 0 and o25 > 55:
            o25 = 55   # düşük baskılı maçta over25 fazla iyimser — kır
        elif pressure == 3 and o25 < 50:
            o25 = 50   # yüksek baskılı maçta over25 fazla kötümser — yükselt

    # 4.5 ÜST → 5+ gol
    if o45 is not None and o45 >= 35:
        if pred_1x2 == '1':
            return '3-2' if btts >= 60 else '4-1'
        if pred_1x2 == '2':
            return '2-3' if btts >= 60 else '1-4'
        return '3-2'

    # 3.5 ÜST → 4+ gol
    if o35 is not None and o35 >= 55:
        if pred_1x2 == '1':
            return '3-1' if btts >= 50 else '4-0'
        if pred_1x2 == '2':
            return '1-3' if btts >= 50 else '0-4'
        return '2-2'

    if pressure == 3 and (o35 is None or o35 < 55):
        if pred_1x2 == '1':
            return '2-1' if btts >= 50 else '3-0'
        if pred_1x2 == '2':
            return '1-2' if btts >= 50 else '0-3'
        return '1-1'

    # 3.5 orta bölge (45-54 arası) → 3 gol bandı
    if o35 is not None and 45 <= o35 < 55:
        if pred_1x2 == '1':
            return '2-1' if btts >= 55 else '3-0'
        if pred_1x2 == '2':
            return '1-2' if btts >= 55 else '0-3'
        return '2-2' if btts >= 55 else '1-1'

    # KRİTİK FIX → 3.5 düşükse 4 gollü skor YASAK
    if o35 is not None and o35 < 45:
        if pred_1x2 == '1':
            return '2-1' if btts >= 50 else '2-0'
        if pred_1x2 == '2':
            return '1-2' if btts >= 50 else '0-2'
        return '1-1'

    if o25 >= 70:
        if pred_1x2 == '1':
            return '2-1' if btts >= 55 else '3-0'
        if pred_1x2 == '2':
            return '1-2' if btts >= 55 else '0-3'
        # 'X' + over25≥70%: eşitlik skoru en az 4 gol → her zaman 2-2
        return '2-2'

    # 2.5 ALT eğilimli maç
    if o25 <= 35:
        if pred_1x2 == '1':
            return '1-0'
        if pred_1x2 == '2':
            return '0-1'
        return '0-0'

    # Orta bölge fallback
    if pred_1x2 == '1':
        return '2-0' if btts < 45 else '2-1'
    if pred_1x2 == '2':
        return '0-2' if btts < 45 else '1-2'
    return '1-1'


def _parse_score(score_text):
    try:
        if not score_text or '-' not in str(score_text):
            return None
        left, right = str(score_text).strip().split('-', 1)
        return int(left.strip()), int(right.strip())
    except:
        return None


def _is_score_valid(score_text, pred_1x2, btts_pct, over25_pct, over35_avg=None, over45_avg=None):
    parsed = _parse_score(score_text)
    if not parsed:
        return False

    home, away = parsed
    total = home + away
    btts = _safe_float(btts_pct) or 0
    o25 = _safe_float(over25_pct) or 0
    o35 = _safe_float(over35_avg)
    o45 = _safe_float(over45_avg)

    if pred_1x2 == '1' and home <= away:
        return False
    if pred_1x2 == '2' and away <= home:
        return False
    if pred_1x2 == 'X' and home != away:
        return False

    if btts < 40 and home > 0 and away > 0:
        return False
    if btts > 65 and (home == 0 or away == 0):
        return False

    if o25 < 40 and total > 2:
        return False
    if o25 > 70 and total < 3:
        return False

    if o35 is not None and o35 < 45 and total >= 4:
        return False
    if o35 is not None and o35 >= 55 and total < 4:
        return False
    if o45 is not None and o45 >= 35 and total < 5:
        return False

    if total > 5:
        return False

    return True


def _is_ht_ft_consistent(ht_score_text, ft_score_text):
    ht = _parse_score(ht_score_text)
    ft = _parse_score(ft_score_text)
    if not ht or not ft:
        return False
    ht_home, ht_away = ht
    ft_home, ft_away = ft
    if ht_home > ft_home or ht_away > ft_away:
        return False
    return True


def _repair_ht_from_ft(ft_score_text, ht2g_pct=None):
    ft = _parse_score(ft_score_text)
    if not ft:
        return '?-?'

    home, away = ft
    total = home + away
    ht2g = _safe_float(ht2g_pct) or 0

    if total == 0:
        return '0-0'
    if total == 1:
        return '1-0' if home > away else '0-1'
    if total == 2:
        if home == away:
            return '1-1' if ht2g >= 60 else '0-0'
        if home > away:
            return '1-0'
        return '0-1'
    if total == 3:
        if home > away:
            return '1-0' if ht2g < 65 else '1-1'
        if away > home:
            return '0-1' if ht2g < 65 else '1-1'
        return '1-1'
    if total >= 4:
        if home == away:
            return '1-1'
        if home > away:
            return '2-0' if away == 0 else '2-1'
        return '0-2' if home == 0 else '1-2'

    return '1-0'


def predict_score_poisson(home_matches, away_matches, home_name, away_name, h2h_data=None, h2h_fd=None, csv_data=None, league_code=None, return_debug=False):
    """
    Poisson dağılımı kullanarak en olasılıklı skoru tahmin eder.

    Mantık:
    - Son 5 maçtan ev/deplasman ayrımlı ortalama hesapla
    - Beklenen gol = (takım hücum ort + rakip savunma zafiyeti) / 2
    - 0-5 gol arası tüm kombinasyonlar için P(h)*P(a) hesapla
    - H2H varsa %20 ağırlıkla karıştır

    Returns: "X-Y" string
    """
    league_avgs = get_league_goal_averages(league_code) if league_code else None
    LEAGUE_HOME_AVG = league_avgs['home'] if league_avgs else 1.55
    LEAGUE_AWAY_AVG = league_avgs['away'] if league_avgs else 1.15

    def _name_matches_home(team_name, match_home_name):
        """Takım adının maçın ev sahibiyle eşleşip eşleşmediğini kontrol et."""
        t = team_name.lower()
        h = match_home_name.lower()
        first_word = t.split()[0] if t.split() else t
        return first_word in h or h.startswith(first_word) or t in h or h in t

    def _extract_venue_goals(matches, team_name, is_home_venue):
        """Son 5 maçtan sadece belirtilen venue'daki maçları filtrele."""
        scored, conceded = [], []
        for m in (matches or [])[-5:]:
            try:
                match_home = m['teams']['home']['name']
                hg = m['goals']['home']
                ag = m['goals']['away']
                if hg is None or ag is None:
                    continue
                team_is_home = _name_matches_home(team_name, match_home)
                if is_home_venue and team_is_home:
                    scored.append(int(hg))
                    conceded.append(int(ag))
                elif not is_home_venue and not team_is_home:
                    scored.append(int(ag))
                    conceded.append(int(hg))
            except Exception:
                continue
        return scored, conceded

    def _extract_all_goals(matches, team_name):
        """Son 5 maçtan tüm maçların genel ortalama değerleri."""
        scored, conceded = [], []
        for m in (matches or [])[-5:]:
            try:
                match_home = m['teams']['home']['name']
                hg = m['goals']['home']
                ag = m['goals']['away']
                if hg is None or ag is None:
                    continue
                is_home = _name_matches_home(team_name, match_home)
                scored.append(int(hg) if is_home else int(ag))
                conceded.append(int(ag) if is_home else int(hg))
            except Exception:
                continue
        return scored, conceded

    def _avg(lst):
        return sum(lst) / len(lst) if lst else None

    # ── 1. Ev sahibi hücum/savunma ortalamaları ───────────────────────────────
    h_scored_home, h_conceded_home = _extract_venue_goals(home_matches, home_name, True)
    h_scored_all, h_conceded_all = _extract_all_goals(home_matches, home_name)

    if _avg(h_scored_home) is not None:
        h_attack = _avg(h_scored_home)
        h_defense = _avg(h_conceded_home) or LEAGUE_AWAY_AVG
        home_data_source = 'venue'
    elif _avg(h_scored_all) is not None:
        logger.warning(f'[SKOR TAHMİN] {home_name} - home/away verisi yok, genel ortalama kullanıldı')
        h_attack = _avg(h_scored_all)
        h_defense = _avg(h_conceded_all) or LEAGUE_AWAY_AVG
        home_data_source = 'general'
    else:
        logger.warning(f'[SKOR TAHMİN] {home_name} - son maç verisi yok, ortalama kullanıldı')
        h_attack = LEAGUE_HOME_AVG
        h_defense = LEAGUE_AWAY_AVG
        home_data_source = 'league_avg'

    # ── 2. Deplasman hücum/savunma ortalamaları ───────────────────────────────
    a_scored_away, a_conceded_away = _extract_venue_goals(away_matches, away_name, False)
    a_scored_all, a_conceded_all = _extract_all_goals(away_matches, away_name)

    if _avg(a_scored_away) is not None:
        a_attack = _avg(a_scored_away)
        a_defense = _avg(a_conceded_away) or LEAGUE_HOME_AVG
        away_data_source = 'venue'
    elif _avg(a_scored_all) is not None:
        logger.warning(f'[SKOR TAHMİN] {away_name} - home/away verisi yok, genel ortalama kullanıldı')
        a_attack = _avg(a_scored_all)
        a_defense = _avg(a_conceded_all) or LEAGUE_HOME_AVG
        away_data_source = 'general'
    else:
        logger.warning(f'[SKOR TAHMİN] {away_name} - son maç verisi yok, ortalama kullanıldı')
        a_attack = LEAGUE_AWAY_AVG
        a_defense = LEAGUE_HOME_AVG
        away_data_source = 'league_avg'

    # ── 3. Beklenen gol = (takım hücum ort + rakip savunma zafiyeti) / 2 ─────
    home_xg = (h_attack + a_defense) / 2
    away_xg = (a_attack + h_defense) / 2

    # ── 4. H2H karıştırma (%20 ağırlık) ──────────────────────────────────────
    h2h_used = False
    if h2h_data:
        h2h_home_goals, h2h_away_goals = [], []
        for m in (h2h_data or [])[-5:]:
            try:
                hg = m.get('goals', {}).get('home') or m.get('score', {}).get('fullTime', {}).get('home')
                ag = m.get('goals', {}).get('away') or m.get('score', {}).get('fullTime', {}).get('away')
                match_home = m.get('teams', {}).get('home', {}).get('name') or m.get('homeTeam', {}).get('name', '')
                if hg is None or ag is None:
                    continue
                is_our_home = _name_matches_home(home_name, match_home)
                if is_our_home:
                    h2h_home_goals.append(int(hg))
                    h2h_away_goals.append(int(ag))
                else:
                    h2h_home_goals.append(int(ag))
                    h2h_away_goals.append(int(hg))
            except Exception:
                continue

        if h2h_home_goals and h2h_away_goals:
            h2h_home_xg = sum(h2h_home_goals) / len(h2h_home_goals)
            h2h_away_xg = sum(h2h_away_goals) / len(h2h_away_goals)
            home_xg = home_xg * 0.8 + h2h_home_xg * 0.2
            away_xg = away_xg * 0.8 + h2h_away_xg * 0.2
            h2h_used = True
        else:
            logger.warning('[SKOR TAHMİN] H2H raw maç listesi boş, h2h_fd fallback deneniyor')

    # h2h_data boşsa h2h_fd summary'den avg_goals ile xG ölçekle (%20 ağırlık)
    if not h2h_used and h2h_fd and h2h_fd.get('total', 0) >= 3:
        h2h_avg = h2h_fd['avg_goals']
        current_total = home_xg + away_xg
        if current_total > 0:
            # Toplam gol ortalamasını h2h verisiyle blend et, ev/dep oranını koru
            blended_total = current_total * 0.8 + h2h_avg * 0.2
            scale = blended_total / current_total
            home_xg *= scale
            away_xg *= scale
            h2h_used = True
            logger.info(f'[SKOR TAHMİN] h2h_fd fallback: avg_goals={h2h_avg} ({h2h_fd["total"]} maç) → xG scale={scale:.3f}')
    elif not h2h_used:
        logger.warning('[SKOR TAHMİN] H2H bulunamadı, ağırlık atlandı')

    # ── 5. CSV blend: season-long avg_goals / over25_avg (%45 ağırlık) ───────
    # Form datası son 5 maçtır (küçük örnek). CSV tüm sezon verisidir ve
    # xG toplamını doğrulamak için daha güvenilirdir.
    csv_total_target = None
    if csv_data:
        csv_avg_g = _safe_float(csv_data.get('avg_goals'))
        csv_o25   = _safe_float(csv_data.get('over25_avg'))
        if csv_avg_g is not None and csv_avg_g > 0:
            csv_total_target = csv_avg_g
        elif csv_o25 is not None and csv_o25 > 0:
            # over25% → Poisson lambda matematiksel ters fonksiyon
            def over25_to_lambda(over25_pct):
                import math
                from scipy.optimize import brentq
                p = over25_pct / 100.0
                def f(lam):
                    p0 = math.exp(-lam)
                    p1 = lam * math.exp(-lam)
                    p2 = (lam**2 / 2) * math.exp(-lam)
                    return (1 - p0 - p1 - p2) - p
                try:
                    return brentq(f, 0.01, 10.0)
                except Exception:
                    return max(1.5, over25_pct / 24.5 + 0.5)
            csv_total_target = over25_to_lambda(csv_o25)

    if csv_total_target is not None:
        current_total = home_xg + away_xg
        if current_total > 0:
            blended_total = current_total * 0.55 + csv_total_target * 0.45
            scale = blended_total / current_total
            home_xg *= scale
            away_xg *= scale
            logger.info(
                f'[SKOR TAHMİN] CSV blend: target={csv_total_target:.2f} → '
                f'total {current_total:.2f}→{home_xg+away_xg:.2f} (scale={scale:.3f})'
            )

    # ── 6. Poisson dağılımı ile 0-5 arası tüm kombinasyonları hesapla ────────
    def poisson_prob(lam, k):
        if lam <= 0:
            return 1.0 if k == 0 else 0.0
        return math.exp(-lam) * (lam ** k) / math.factorial(k)

    best_prob = -1.0
    best_home_goals = 1
    best_away_goals = 0

    for h in range(6):
        for a in range(6):
            prob = poisson_prob(home_xg, h) * poisson_prob(away_xg, a)
            if prob > best_prob:
                best_prob = prob
                best_home_goals = h
                best_away_goals = a

    logger.info(
        f'[SKOR TAHMİN] Poisson: {home_name} xG={home_xg:.2f} | '
        f'{away_name} xG={away_xg:.2f} → {best_home_goals}-{best_away_goals} '
        f'(p={best_prob:.4f})'
    )
    score_str = f'{best_home_goals}-{best_away_goals}'
    if not return_debug:
        return score_str
    return {
        'score': score_str,
        'home_match_count': len(home_matches) if home_matches else 0,
        'away_match_count': len(away_matches) if away_matches else 0,
        'home_avg': round(h_attack, 2),
        'away_avg': round(a_attack, 2),
        'home_data_source': home_data_source,
        'away_data_source': away_data_source,
        'h2h_used': h2h_used,
        'csv_target': round(csv_total_target, 2) if csv_total_target else None,
        'home_xg': round(home_xg, 2),
        'away_xg': round(away_xg, 2),
        'best_prob': round(best_prob, 4),
    }


def analyze_with_claude(fixture, h2h_data, home_matches, away_matches,
                        home_form='', away_form='',
                        home_goals_avg=0, away_goals_avg=0,
                        home_conceded_avg=0, away_conceded_avg=0,
                        h2h_summary=None, h2h_fd=None, elo_data=None, odds_data=None,
                        home_standing=None, away_standing=None,
                        home_venue_stats=None, away_venue_stats=None,
                        home_shot_stats=None, away_shot_stats=None,
                        home_ht_stats=None, away_ht_stats=None,
                        home_btts_stats=None, away_btts_stats=None,
                        btts_mathematical=None,
                        home_goals_trend=None, away_goals_trend=None,
                        csv_data=None, league_code=None,
                        ai_provider='claude'):

    home_team = fixture['teams']['home']['name']
    away_team = fixture['teams']['away']['name']
    league = fixture['league']['name']
    match_time = fixture['fixture']['date']

    home_home_avg = None
    home_conceded_home_avg = None
    home_home_form = None
    away_away_avg = None
    away_conceded_away_avg = None
    away_away_form = None

    if home_venue_stats:
        home_home_avg = home_venue_stats.get('home_goals_avg')
        home_conceded_home_avg = home_venue_stats.get('home_conceded_avg')
        home_home_form = home_venue_stats.get('home_form')
    if away_venue_stats:
        away_away_avg = away_venue_stats.get('away_goals_avg')
        away_conceded_away_avg = away_venue_stats.get('away_conceded_avg')
        away_away_form = away_venue_stats.get('away_form')

    if not home_home_avg:
        try:
            home_keyword = home_team.lower().split()[0] if home_team.split() else home_team.lower()
            home_home_goals = [
                m['goals']['home'] for m in home_matches
                if home_keyword in m['teams']['home']['name'].lower()
                and m['goals']['home'] is not None
            ]
            if home_home_goals:
                home_home_avg = round(sum(home_home_goals)/len(home_home_goals), 1)
        except (KeyError, TypeError, ZeroDivisionError) as e:
            logger.debug(f'Home venue avg calc skipped for {home_team}: {e}')

    if not away_away_avg:
        try:
            away_keyword = away_team.lower().split()[0] if away_team.split() else away_team.lower()
            away_away_goals = [
                m['goals']['away'] for m in away_matches
                if away_keyword in m['teams']['away']['name'].lower()
                and m['goals']['away'] is not None
            ]
            if away_away_goals:
                away_away_avg = round(sum(away_away_goals)/len(away_away_goals), 1)
        except (KeyError, TypeError, ZeroDivisionError) as e:
            logger.debug(f'Away venue avg calc skipped for {away_team}: {e}')

    prompt = build_prompt(
        home_team, away_team, league, match_time,
        home_form, away_form,
        home_goals_avg, away_goals_avg,
        home_conceded_avg, away_conceded_avg,
        h2h_summary,
        home_home_avg, away_away_avg,
        home_conceded_home_avg, away_conceded_away_avg,
        home_home_form, away_away_form,
        home_standing, away_standing,
        elo_data, odds_data,
        home_shot_stats=home_shot_stats,
        away_shot_stats=away_shot_stats,
        home_ht_stats=home_ht_stats,
        away_ht_stats=away_ht_stats,
        home_btts_stats=home_btts_stats,
        away_btts_stats=away_btts_stats,
        btts_mathematical=btts_mathematical,
        home_goals_trend=home_goals_trend,
        away_goals_trend=away_goals_trend,
        csv_data=csv_data,
        h2h_fd=h2h_fd,
    )

    result = None

    if ai_provider == 'grok':
        if GROQ_API_KEY:
            try:
                raw = call_groq(prompt)
                result = parse_result(raw)
                logger.info(f'Grok OK: {home_team} vs {away_team}')
            except Exception as e:
                logger.error(f'Grok failed: {e}')
        if not result and ANTHROPIC_API_KEY:
            try:
                raw = call_anthropic(prompt)
                result = parse_result(raw)
                logger.info(f'Claude (Grok yedek) OK: {home_team} vs {away_team}')
            except Exception as e:
                logger.error(f'Claude fallback failed: {e}')

    elif ai_provider == 'gemini':
        if GEMINI_API_KEY:
            try:
                raw = call_gemini(prompt)
                result = parse_result(raw)
                logger.info(f'Gemini OK: {home_team} vs {away_team}')
            except Exception as e:
                logger.error(f'Gemini failed: {e}')
        if not result and ANTHROPIC_API_KEY:
            try:
                raw = call_anthropic(prompt)
                result = parse_result(raw)
                logger.info(f'Claude (Gemini yedek) OK: {home_team} vs {away_team}')
            except Exception as e:
                logger.error(f'Claude fallback failed: {e}')

    else:
        if ANTHROPIC_API_KEY:
            try:
                raw = call_anthropic(prompt)
                result = parse_result(raw)
                logger.info(f'Claude OK: {home_team} vs {away_team}')
            except Exception as e:
                logger.error(f'Claude failed: {e}')
        if not result and GEMINI_API_KEY:
            try:
                raw = call_gemini(prompt)
                result = parse_result(raw)
                logger.info(f'Gemini (Claude yedek) OK: {home_team} vs {away_team}')
            except Exception as e:
                logger.error(f'Gemini fallback failed: {e}')

    if not result:
        return mock_analysis(fixture, home_form, away_form, home_goals_avg, away_goals_avg)

    value_bets = calculate_value_bets(result, csv_data, home_team, away_team)
    if value_bets:
        logger.info(f'Value bets {home_team} vs {away_team}: {[v["label"] + " +" + str(v["diff"]) + "%" for v in value_bets]}')

    confidence = result.get('confidence', 'Orta')

    # Güven seviyesini bahisçi+PPG uyumuna göre kontrol et (xG tabanlı değil)
    # odds_favors ve ppg_favors build_prompt içinde hesaplandı ama burada yeniden hesaplayalım
    _conf_odds_favors = None
    _conf_ppg_favors = None
    _odds_diff_abs = None
    if csv_data:
        try:
            h_o = float(csv_data.get('odds_home') or 0)
            a_o = float(csv_data.get('odds_away') or 0)
            if h_o > 1 and a_o > 1:
                h_imp = round(1/h_o*100, 1)
                a_imp = round(1/a_o*100, 1)
                d = h_imp - a_imp
                _odds_diff_abs = abs(d)
                if d > 15: _conf_odds_favors = '1'
                elif d < -15: _conf_odds_favors = '2'
                elif d > 5: _conf_odds_favors = '1_soft'
                elif d < -5: _conf_odds_favors = '2_soft'
                else: _conf_odds_favors = 'X'
        except (ValueError, TypeError, ZeroDivisionError) as e:
            logger.debug(f'Confidence odds favors calc skipped: {e}')
        try:
            ch = float(csv_data.get('current_home_ppg') or 0)
            ca = float(csv_data.get('current_away_ppg') or 0)
            if ch > 0 or ca > 0:
                pd = ch - ca
                if pd > 0.5: _conf_ppg_favors = '1'
                elif pd < -0.5: _conf_ppg_favors = '2'
                else: _conf_ppg_favors = 'X'
        except (ValueError, TypeError) as e:
            logger.debug(f'Confidence PPG favors calc skipped: {e}')

    # ── Ev/dep sırası yeniden hesapla (post-process için) ────────────────────
    _conf_venue_rank_favors = None
    try:
        h_hp = home_standing.get('home_position') if home_standing else None
        a_ap = away_standing.get('away_position') if away_standing else None
        if h_hp is not None and a_ap is not None:
            diff = a_ap - h_hp
            if diff >= 4:
                _conf_venue_rank_favors = '1'
            elif diff <= -4:
                _conf_venue_rank_favors = '2'
            else:
                _conf_venue_rank_favors = 'X'
    except (TypeError, ValueError):
        pass

    # Çok Yüksek artık yok — AI bunu verse de Yüksek'e indir
    if confidence == 'Çok Yüksek':
        confidence = 'Yüksek'

    # Kupa/hazırlık maçlarında max Orta
    match_type = detect_match_importance(league)
    if 'Kupa' in match_type or 'Hazirlik' in match_type:
        if confidence == 'Yüksek':
            confidence = 'Orta'
            logger.info(f'Confidence capped to Orta (cup/friendly): {home_team} vs {away_team}')
    else:
        odds_side = _conf_odds_favors.replace('_soft', '') if _conf_odds_favors else None

        # Sinyal yön uyumu yardımcıları
        _side_ok   = odds_side and odds_side not in ('X', None)
        _ppg_ok    = _conf_ppg_favors and _conf_ppg_favors not in ('X', None)
        _venue_ok  = _conf_venue_rank_favors and _conf_venue_rank_favors not in ('X', None)

        ppg_aligned   = _side_ok and _ppg_ok   and _conf_ppg_favors        == odds_side
        venue_aligned = _side_ok and _venue_ok  and _conf_venue_rank_favors == odds_side
        venue_data_exists = _conf_venue_rank_favors is not None  # None = veri yok, 'X' = veri var ama dengeli

        # Odds gücü eşikleri
        strong_odds = _odds_diff_abs is not None and _odds_diff_abs >= 30
        medium_odds = _odds_diff_abs is not None and 15 <= _odds_diff_abs < 30

        # Çelişki: odds ve PPG farklı tarafa işaret ediyor (X/None değil)
        conflict = (
            _side_ok and _ppg_ok
            and _conf_ppg_favors != odds_side
        )

        # ── Yüksek: odds %30+ VE PPG aynı yön VE sıralama aynı yön ────────────
        high = strong_odds and ppg_aligned and venue_aligned

        # ── Orta: üç alt koşuldan biri ──────────────────────────────────────────
        # 1. Odds %15-30 VE PPG + sıralama aynı yönde
        # 2. Odds %30+ ama sıralama verisi yok (None), PPG aynı yönde
        # 3. Odds %30 altında ama odds + PPG aynı yönde (sıralama ne olursa)
        medium = (
            (medium_odds and ppg_aligned and venue_aligned)
            or (strong_odds and ppg_aligned and not venue_data_exists)
            or (not strong_odds and _side_ok and ppg_aligned)
        )

        if high:
            confidence = 'Yüksek'
        elif conflict:
            confidence = 'Düşük'
        elif medium:
            confidence = 'Orta'
        else:
            confidence = 'Orta'

        logger.info(
            f'Confidence inputs: odds_diff={_odds_diff_abs} odds={_conf_odds_favors} '
            f'ppg={_conf_ppg_favors} venue_rank={_conf_venue_rank_favors}'
        )

        logger.info(
            f'Confidence final: {confidence} | odds={_conf_odds_favors} ppg={_conf_ppg_favors} '
            f'venue_rank={_conf_venue_rank_favors} | {home_team} vs {away_team}'
        )

    over25_pct = float(result.get('over25_pct', 50))
    btts_pct = float(result.get('btts_pct', 40))
    ht2g_pct = float(result.get('ht2g_pct', 40))

    if csv_data:
        def clamp(val, base, margin):
            if base is None: return val
            return max(float(base) - margin, min(float(base) + margin, val))

        over25_base = csv_data.get('over25_avg')
        btts_base = csv_data.get('btts_avg')
        ht_base = csv_data.get('ht_over05_avg')

        if over25_base is not None:
            clamped = clamp(over25_pct, over25_base, 10)
            if clamped != over25_pct:
                logger.info(f'over25_pct clamped {over25_pct}→{clamped} (base={over25_base})')
                over25_pct = clamped

        if btts_base is not None:
            clamped = clamp(btts_pct, btts_base, 8)
            if clamped != btts_pct:
                logger.info(f'btts_pct clamped {btts_pct}→{clamped} (base={btts_base})')
                btts_pct = clamped

        if ht_base is not None:
            clamped = clamp(ht2g_pct, ht_base, 5)
            if clamped != ht2g_pct:
                logger.info(f'ht2g_pct clamped {ht2g_pct}→{clamped} (base={ht_base})')
                ht2g_pct = clamped

    # ── Şut bazlı yüzde düzeltmesi ───────────────────────────────────────────
    pressure, shot_dominant = _shot_pressure_score(home_shot_stats, away_shot_stats)
    if pressure is not None:
        if pressure == 0:
            if over25_pct > 58:
                adj = min(6, over25_pct - 52)
                logger.info(f'Shot pressure=0: over25_pct {over25_pct}→{over25_pct - adj} (düşük baskı)')
                over25_pct -= adj
        elif pressure == 3:
            if over25_pct < 52:
                adj = min(6, 58 - over25_pct)
                logger.info(f'Shot pressure=3: over25_pct {over25_pct}→{over25_pct + adj} (yüksek baskı)')
                over25_pct += adj

        h_on = _safe_float(home_shot_stats.get('shots_on_target_avg') if home_shot_stats else None) or 0
        a_on = _safe_float(away_shot_stats.get('shots_on_target_avg') if away_shot_stats else None) or 0
        if h_on >= 4.5 and a_on >= 4.5 and btts_pct < 60:
            adj = min(5, 65 - btts_pct)
            logger.info(f'Shot both-teams-high SOT: btts_pct {btts_pct}→{btts_pct + adj}')
            btts_pct += adj
        elif h_on <= 2.5 and a_on <= 2.5 and btts_pct > 45:
            adj = min(5, btts_pct - 40)
            logger.info(f'Shot both-teams-low SOT: btts_pct {btts_pct}→{btts_pct - adj}')
            btts_pct -= adj
    # ─────────────────────────────────────────────────────────────────────────

    # ── xG-BTTS tutarlılık kontrolü ──────────────────────────────────────────
    if csv_data:
        hxg_val = _safe_float(csv_data.get('home_xg'))
        axg_val = _safe_float(csv_data.get('away_xg'))
        btts_base_val = _safe_float(csv_data.get('btts_avg'))
        if hxg_val is not None and axg_val is not None:
            if hxg_val >= 1.0 and axg_val >= 1.0:
                # Her iki takım da gol beklentisi yüksek — BTTS min %50 olmalı
                # Ama CSV btts_avg zaten >= 50 ise dokunma
                if (btts_base_val is None or btts_base_val < 50) and btts_pct < 50:
                    logger.info(f'xG-BTTS fix: her iki xG>=1.0 ({hxg_val}/{axg_val}), btts_pct {btts_pct}→50')
                    btts_pct = 50
    # ─────────────────────────────────────────────────────────────────────────

    # Tutarlılık garantisi — clamp sonrası çelişkileri düzelt
    if btts_pct > 60 and over25_pct < 45:
        logger.info(f'Consistency fix: btts={btts_pct}>60 but over25={over25_pct}<45 → over25 set to 45')
        over25_pct = 45
    if btts_pct < 35 and over25_pct > 55:
        logger.info(f'Consistency fix: btts={btts_pct}<35 but over25={over25_pct}>55 → over25 set to 55')
        over25_pct = 55
    if over25_pct > 70 and ht2g_pct < 60:
        logger.info(f'Consistency fix: over25={over25_pct}>70 but ht2g={ht2g_pct}<60 → ht2g set to 60')
        ht2g_pct = 60
    if over25_pct < 35 and btts_pct > 45:
        logger.info(f'Consistency fix: over25={over25_pct}<35 but btts={btts_pct}>45 → btts set to 45')
        btts_pct = 45

    ai_predicted_score = result.get('predicted_score', '?-?')
    ai_predicted_ht_score = result.get('predicted_ht_score', '?-?')

    _pred_1x2   = result.get('prediction_1x2', '?')
    _over35_avg = csv_data.get('over35_avg') if csv_data else None
    _over45_avg = csv_data.get('over45_avg') if csv_data else None

    try:
        poisson_score = predict_score_poisson(
            home_matches, away_matches, home_team, away_team,
            h2h_data=h2h_data, h2h_fd=h2h_fd, csv_data=csv_data,
            league_code=league_code,
        )
    except Exception as e:
        logger.warning(f'[SKOR TAHMİN] Poisson hesabı başarısız: {e}')
        poisson_score = None

    csv_fallback_score = _pick_score_by_csv_rules(
        _pred_1x2, btts_pct, over25_pct, _over35_avg, _over45_avg,
        home_shot_stats=home_shot_stats, away_shot_stats=away_shot_stats,
    )

    # Poisson skoru önce doğrula; geçersizse CSV fallback kullan
    if poisson_score and _is_score_valid(poisson_score, _pred_1x2, btts_pct, over25_pct, _over35_avg, _over45_avg):
        fallback_score = poisson_score
    else:
        if poisson_score:
            logger.info(f'[SKOR TAHMİN] Poisson skoru ({poisson_score}) geçersiz, csv_fallback kullanılıyor: {csv_fallback_score}')
        fallback_score = csv_fallback_score

    final_score = ai_predicted_score
    if not _is_score_valid(final_score, _pred_1x2, btts_pct, over25_pct, _over35_avg, _over45_avg):
        logger.info(f'AI predicted_score invalid, Poisson fallback used: {ai_predicted_score} -> {fallback_score}')
        final_score = fallback_score

    final_ht_score = ai_predicted_ht_score
    if not _is_ht_ft_consistent(final_ht_score, final_score):
        repaired_ht = _repair_ht_from_ft(final_score, ht2g_pct)
        logger.info(f'AI predicted_ht_score inconsistent, repaired: {ai_predicted_ht_score} -> {repaired_ht}')
        final_ht_score = repaired_ht

    return {
        'analysis_date': datetime.now().strftime('%Y-%m-%d'),
        'fixture_id': fixture['fixture']['id'],
        'home_team': home_team, 'away_team': away_team,
        'league': league, 'match_time': match_time,
        'prediction_1x2': result.get('prediction_1x2', '?'),
        'over25_pct': round(over25_pct),
        'ht2g_pct': round(ht2g_pct),
        'btts_pct': round(btts_pct),
        'predicted_score': final_score,
        'predicted_ht_score': final_ht_score,
        'confidence': confidence,
        'reasoning': json.dumps(result.get('reasoning', []), ensure_ascii=False),
        'h2h_summary': result.get('h2h_summary', ''),
        'home_form': home_form, 'away_form': away_form,
        'home_goals_avg': home_goals_avg, 'away_goals_avg': away_goals_avg,
        'home_goals_trend': json.dumps(home_goals_trend, ensure_ascii=False) if home_goals_trend else None,
        'away_goals_trend': json.dumps(away_goals_trend, ensure_ascii=False) if away_goals_trend else None,
        'value_bets': json.dumps(value_bets, ensure_ascii=False) if value_bets else None,
        'csv_data': csv_data,
    }


def mock_analysis(fixture, home_form='', away_form='', home_goals_avg=0, away_goals_avg=0):
    home_team = fixture['teams']['home']['name']
    away_team = fixture['teams']['away']['name']
    return {
        'analysis_date': datetime.now().strftime('%Y-%m-%d'),
        'fixture_id': fixture['fixture']['id'],
        'home_team': home_team, 'away_team': away_team,
        'league': fixture['league']['name'], 'match_time': fixture['fixture']['date'],
        'prediction_1x2': '1', 'over25_pct': 55, 'ht2g_pct': 40, 'btts_pct': 45,
        'predicted_score': _pick_score_by_csv_rules('1', 45, 55, None, None), 'predicted_ht_score': '1-0', 'confidence': 'Orta',
        'reasoning': json.dumps([home_team + ' ev sahibi avantajına sahip', 'İstatistiksel model tahmini'], ensure_ascii=False),
        'h2h_summary': 'Genel istatistiklere göre tahmin',
        'home_form': home_form, 'away_form': away_form,
        'home_goals_avg': home_goals_avg, 'away_goals_avg': away_goals_avg,
        'home_goals_trend': None, 'away_goals_trend': None,
        'value_bets': None,
    }


# ─── Günlük Özet Fonksiyonları ────────────────────────────────────────────────

def build_summary_prompt(matches):
    """Günlük özet için AI prompt'u oluştur"""
    today = datetime.now().strftime('%d.%m.%Y')
    total = len(matches)

    lines = [
        f"Bugün ({today}) toplam {total} maç analiz edildi.",
        "Aşağıdaki verilere dayanarak Türkçe, madde madde bir günlük özet yaz.",
        "Teknik terimler kullanma, analist gibi sade ve anlaşılır yaz.",
        "",
        "── MAÇ VERİLERİ ──",
    ]

    for m in matches:
        csv = m.get('csv_data') or {}
        if isinstance(csv, str):
            try:
                csv = json.loads(csv)
            except:
                csv = {}

        lines.append(f"\n{m['home_team']} vs {m['away_team']} ({m.get('league', '')})")
        lines.append(f"  Tahmin: {m.get('prediction_1x2','?')} | Güven: {m.get('confidence','?')}")
        lines.append(f"  2.5 Üst: %{m.get('over25_pct',0)} | KG Var: %{m.get('btts_pct',0)} | İY 0.5: %{m.get('ht2g_pct',0)}")

        avg_corners = csv.get('avg_corners')
        if avg_corners:
            over85 = csv.get('avg_corners_85', '—')
            over95 = csv.get('avg_corners_95', '—')
            lines.append(f"  Korner ort: {avg_corners} | 8.5 üst: %{over85} | 9.5 üst: %{over95}")

        ht2_05 = csv.get('ht2_over05_avg')
        ht2_15 = csv.get('ht2_over15_avg')
        if ht2_05 or ht2_15:
            lines.append(f"  2Y 0.5 üst: %{ht2_05 or '—'} | 2Y 1.5 üst: %{ht2_15 or '—'}")

    lines.append("\n── TALİMATLAR ──")
    lines.append("Aşağıdaki başlıklar altında madde madde özet yaz:")
    lines.append("1. En güvenilir maçlar - Taraf (1X2) tahmini Yüksek veya Çok Yüksek güven seviyesinde olanlar")
    lines.append("2. En golcü beklenen maçlar (%75 ve üzeri 2.5 üst yüzdesi olanlar)")
    lines.append("3. Karşılıklı gol beklentisi yüksek maçlar (%70 ve üzeri KG Var yüzdesi olanlar)")
    lines.append("4. Korner açısından hareketli maçlar (ortalama korner 10+ olanlar)")
    lines.append("5. İlk yarı gol beklentisi yüksek maçlar (İY 0.5 üst %65 ve üzeri olanlar)")
    lines.append("6. Genel risk değerlendirmesi ve günün kısa özeti")
    lines.append("")
    lines.append("Eğer bir kategoride öne çıkan maç yoksa 'Bu kategoride belirgin bir maç yok' de.")
    lines.append("Yanıtın sadece madde madde metin olsun, JSON değil.")

    return "\n".join(lines)


def generate_daily_summary(matches, ai_provider='claude'):
    """Bugünün maçları için AI özeti üret"""
    if not matches:
        return None

    prompt = build_summary_prompt(matches)
    raw = None

    if ai_provider == 'grok':
        if GROQ_API_KEY:
            try:
                raw = call_groq(prompt)
                logger.info('Grok summary OK')
            except Exception as e:
                logger.error(f'Grok summary failed: {e}')
        if not raw and ANTHROPIC_API_KEY:
            try:
                raw = call_anthropic(prompt)
                logger.info('Claude summary (Grok fallback) OK')
            except Exception as e:
                logger.error(f'Claude summary fallback failed: {e}')

    elif ai_provider == 'gemini':
        if GEMINI_API_KEY:
            try:
                response = requests.post(
                    'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=' + GEMINI_API_KEY,
                    headers={'Content-Type': 'application/json'},
                    json={
                        'contents': [{'parts': [{'text': 'Sen profesyonel bir futbol bahis analistisin. TÜRKÇE yaz.\n\n' + prompt}]}],
                        'generationConfig': {'maxOutputTokens': 3000, 'temperature': 0.7}
                    }, timeout=30
                )
                response.raise_for_status()
                raw = response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                logger.info('Gemini summary OK')
            except Exception as e:
                logger.error(f'Gemini summary failed: {e}')
        if not raw and ANTHROPIC_API_KEY:
            try:
                raw = call_anthropic(prompt)
                logger.info('Claude summary (Gemini fallback) OK')
            except Exception as e:
                logger.error(f'Claude summary fallback failed: {e}')

    else:  # claude (varsayılan)
        if ANTHROPIC_API_KEY:
            try:
                raw = call_anthropic(prompt)
                logger.info('Claude summary OK')
            except Exception as e:
                logger.error(f'Claude summary failed: {e}')
        if not raw and GEMINI_API_KEY:
            try:
                response = requests.post(
                    'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=' + GEMINI_API_KEY,
                    headers={'Content-Type': 'application/json'},
                    json={
                        'contents': [{'parts': [{'text': 'Sen profesyonel bir futbol bahis analistisin. TÜRKÇE yaz.\n\n' + prompt}]}],
                        'generationConfig': {'maxOutputTokens': 3000, 'temperature': 0.7}
                    }, timeout=30
                )
                response.raise_for_status()
                raw = response.json()['candidates'][0]['content']['parts'][0]['text'].strip()
                logger.info('Gemini summary (Claude fallback) OK')
            except Exception as e:
                logger.error(f'Gemini summary fallback failed: {e}')

    return raw
