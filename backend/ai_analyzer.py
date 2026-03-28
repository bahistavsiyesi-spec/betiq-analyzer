import os
import json
import logging
import requests
import time
from datetime import datetime

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
                conf_map = {'Çok Yüksek': 85, 'Yüksek': 75, 'Orta': 60, 'Düşük': 45}
                our_pct = conf_map.get(result.get('confidence', 'Orta'), 60)
                diff = round(our_pct - implied, 1)
                if diff >= VALUE_THRESHOLD:
                    value_bets.append({'label': label, 'our_pct': our_pct, 'implied_pct': implied, 'diff': diff, 'odds': float(odds)})
            except: pass
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
        except: continue
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
            except: pass
        if curr_appg and appg:
            try:
                diff = round(float(curr_appg) - float(appg), 2)
                trend = 'form YUKSELIYOR' if diff > 0.2 else ('form DUSUYOR' if diff < -0.2 else 'form STABIL')
                lines.append(f'  - {away_team} trend: {trend} (fark: {diff:+.2f})')
            except: pass
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
        if btts is not None: lines.append(f'  - KG VAR (maç geneli): %{btts}')
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
        except: pass
    if as_ and aon:
        try:
            acc = round(float(aon) / float(as_) * 100, 1)
            shot_lines.append(f'  - {away_team} isabet oranı: %{acc}')
        except: pass
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
                 csv_data=None):

    h2h_text = ''
    if h2h_summary:
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
        if away_standing:
            standing_text += (f'- {away_team}: {away_standing["position"]}. sıra | {away_standing["points"]} puan | '
                              f'{away_standing["played"]} maç | {away_standing["won"]}G {away_standing["draw"]}B {away_standing["lost"]}M\n')

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
            except: pass
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
            except: pass
        if csv_data.get('current_away_ppg') and csv_data.get('away_ppg'):
            try:
                diff = float(csv_data['current_away_ppg']) - float(csv_data['away_ppg'])
                if abs(diff) > 0.2:
                    trend = 'form yukarı' if diff > 0 else 'form aşağı'
                    hints.append(f'{away_team} güncel PPG farkı {diff:+.2f} → {trend} — form momentumu dikkate al')
            except: pass
        if csv_data.get('ht2_over05_avg'):
            hints.append(f'2. yarı gol ihtimali %{csv_data["ht2_over05_avg"]} — maçın ikinci yarısı baskı göstergesi')
        # ─────────────────────────────────────────────────────────────────────
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
        except: pass
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
        except: pass
    # ─────────────────────────────────────────────────────────────────────────

    prediction_rules = '\n── Taraf Tahmini Kuralları (ZORUNLU) ──\n'
    prediction_rules += 'KARAR HİYERARŞİSİ (öncelik sırası):\n'
    prediction_rules += '  1. Bahisçi oranı (piyasa konsensüsü) — en güvenilir gösterge\n'
    prediction_rules += '  2. Güncel PPG (sezon içi form trendi)\n'
    prediction_rules += '  3. xG farkı (tehlike göstergesi, KAZANMA değil GOL beklentisi)\n'
    prediction_rules += '  4. Ev sahibi avantajı\n'
    prediction_rules += '  5. H2H geçmişi\n\n'
    prediction_rules += '⚠️ xG yüksek = çok gol atabilir, ama KAZANIR anlamına gelmez!\n'
    prediction_rules += '⚠️ Bahisçi + PPG aynı tarafı gösteriyorsa, xG tek başına bunu geçemez.\n\n'
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

    if xg_diff is not None:
        prediction_rules += f'xG Durumu: {home_team}={hxg} xG, {away_team}={axg} xG, fark={abs(xg_diff)} ({home_team if xg_diff > 0 else away_team} daha tehlikeli)\n'
        prediction_rules += f'  ⚠️ xG = GOL BEKLENTİSİ, KAZANMA ihtimali değil!\n\n'
        prediction_rules += 'xG tek başına tahmin kuralı:\n'
        prediction_rules += f'  - xG farkı > 0.8 VE bahisçi + PPG destekliyorsa → güçlü favori\n'
        prediction_rules += f'  - xG farkı > 0.8 AMA bahisçi karşı tarafı gösteriyorsa → bahisçiye uyu\n'
        prediction_rules += f'  - xG farkı 0.4-0.8 → hafif gösterge, bahisçi + PPG belirler\n'
        prediction_rules += f'  - xG farkı < 0.4 → göz ardı et, diğer faktörler belirler\n\n'
    else:
        prediction_rules += 'xG verisi yok — bahisçi + PPG + ev/dep istatistik belirler\n\n'

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
    prediction_rules += '  - Sadece xG yüksek ama bahisçi karşı tarafta → bahisçiye uyu\n'
    prediction_rules += '  - Tüm göstergeler çelişkili → "X" ver\n\n'

    prediction_rules += 'Beraberlik (X) ne zaman verilmeli:\n'
    prediction_rules += '  - Bahisçi dengeli VE xG farkı < 0.4 VE PPG benzer\n'
    prediction_rules += '  - Her iki takım da tutarsız form gösteriyorsa\n'
    prediction_rules += '  ❌ YANLIŞ: xG eşit diye otomatik X verme!\n\n'
    prediction_rules += '── Taraf Kuralları Sonu ──\n'

    confidence_rules = '''
── Güven Seviyesi Belirleme Kuralları (ZORUNLU) ──
VERİ KAYNAĞI ÖNCELİĞİ: 1.CSV xG  2.Form trendi  3.Ev/dep istatistik  4.Puan durumu

KURAL 1 — CSV xG YOKSA maksimum güven "Orta"dır
KURAL 2 — CSV xG VARSA:
  "Çok Yüksek": xG + form + ev/dep + puan → HEPSİ aynı tarafı gösteriyor
  "Yüksek"    : xG var + 3 kaynaktan en az 2'si aynı yönde
  "Orta"      : xG var ama kaynaklar çelişkili
  "Düşük"     : veriler tamamen çelişkili
KURAL 3 — Kupa/hazırlık maçlarında maksimum güven "Orta"dır

Mevcut veri durumu:
''' + f'''  - CSV xG: {"VAR ✓" if has_xg else "YOK ✗ → max güven Orta"}
  - Form trendi: {"VAR ✓" if has_form else "YOK ✗"}
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
            'model': 'claude-sonnet-4-20250514',
            'max_tokens': 1000,
            'system': 'Sen profesyonel bir futbol bahis analistisin. Tüm yanıtlar TÜRKÇE olacak. Elo kelimesini kullanma.',
            'messages': [{'role': 'user', 'content': prompt}]
        }, timeout=30
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
        return '2-2' if btts >= 55 else '1-1'

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


def analyze_with_claude(fixture, h2h_data, home_matches, away_matches,
                        home_form='', away_form='',
                        home_goals_avg=0, away_goals_avg=0,
                        home_conceded_avg=0, away_conceded_avg=0,
                        h2h_summary=None, elo_data=None, odds_data=None,
                        home_standing=None, away_standing=None,
                        home_venue_stats=None, away_venue_stats=None,
                        home_shot_stats=None, away_shot_stats=None,
                        home_ht_stats=None, away_ht_stats=None,
                        home_btts_stats=None, away_btts_stats=None,
                        btts_mathematical=None,
                        home_goals_trend=None, away_goals_trend=None,
                        csv_data=None,
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
            home_home_goals = [
                m['goals']['home'] for m in home_matches
                if home_team.lower().split()[0] in m['teams']['home']['name'].lower()
                and m['goals']['home'] is not None
            ]
            if home_home_goals:
                home_home_avg = round(sum(home_home_goals)/len(home_home_goals), 1)
        except: pass

    if not away_away_avg:
        try:
            away_away_goals = [
                m['goals']['away'] for m in away_matches
                if away_team.lower().split()[0] in m['teams']['away']['name'].lower()
                and m['goals']['away'] is not None
            ]
            if away_away_goals:
                away_away_avg = round(sum(away_away_goals)/len(away_away_goals), 1)
        except: pass

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
    has_xg = csv_data and csv_data.get('home_xg') and csv_data.get('away_xg')

    if not has_xg and confidence in ('Yüksek', 'Çok Yüksek'):
        confidence = 'Orta'
        logger.info(f'Confidence capped to Orta (no CSV xG): {home_team} vs {away_team}')

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
    fallback_score = _pick_score_by_csv_rules(
        result.get('prediction_1x2', '?'),
        btts_pct,
        over25_pct,
        csv_data.get('over35_avg') if csv_data else None,
        csv_data.get('over45_avg') if csv_data else None,
        home_shot_stats=home_shot_stats,
        away_shot_stats=away_shot_stats,
    )

    final_score = ai_predicted_score
    if not _is_score_valid(
        final_score,
        result.get('prediction_1x2', '?'),
        btts_pct,
        over25_pct,
        csv_data.get('over35_avg') if csv_data else None,
        csv_data.get('over45_avg') if csv_data else None,
    ):
        logger.info(f'AI predicted_score invalid, fallback used: {ai_predicted_score} -> {fallback_score}')
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
