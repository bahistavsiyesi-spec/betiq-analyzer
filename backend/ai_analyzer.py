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

ANALYSIS_MODE = os.environ.get('ANALYSIS_MODE', 'claude')

def detect_match_importance(league):
    league_lower = league.lower()
    if any(x in league_lower for x in ['champions league', 'sampiyonlar ligi', 'uefa', 'europa league', 'conference']):
        return 'Avrupa kupasi maci — eleme baskisi yuksek, iki takim da temkinli oynayabilir'
    if any(x in league_lower for x in ['cup', 'kupa', 'fa cup', 'copa', 'pokal']):
        return 'Kupa maci — tek maclik eleme, beklenmedik sonuclar olabilir'
    if any(x in league_lower for x in ['friendly', 'hazirlik']):
        return 'Hazirlik maci — motivasyon dusuk olabilir, sonuc guvenirligi az'
    return 'Lig maci — puan kaybi istemeyen iki takim'

def elo_trend_to_form(trend_label, trend_30d):
    if trend_label == 'Yükselen' or (trend_30d is not None and trend_30d >= 15):
        return 'WWDWW'
    elif trend_label == 'Düşen' or (trend_30d is not None and trend_30d <= -15):
        return 'LLDLL'
    else:
        return 'WDWDL'


def build_csv_section(home_team, away_team, csv_data):
    """
    CSV'den gelen verileri prompt'a eklemek için ayrı bir bölüm oluşturur.
    csv_data anahtarları (hepsi opsiyonel):
      home_xg, away_xg          — Pre-match xG
      btts_avg                  — BTTS Average (%)
      over25_avg                — Over 2.5 Average (%)
      over15_avg                — Over 1.5 Average (%)
      avg_goals                 — Maç başı ortalama gol
      avg_corners               — Maç başı ortalama korner
      odds_home                 — 1 oranı
      odds_draw                 — X oranı
      odds_away                 — 2 oranı
      odds_over25               — Over 2.5 oranı
      odds_btts_yes             — KG VAR oranı
      home_ppg                  — Ev sahibi puan/maç (pre-match)
      away_ppg                  — Deplasman puan/maç (pre-match)
    """
    if not csv_data:
        return ''

    lines = ['\n── FootyStats CSV Verileri ──']

    # Pre-match xG
    home_xg = csv_data.get('home_xg')
    away_xg = csv_data.get('away_xg')
    if home_xg is not None or away_xg is not None:
        lines.append('Pre-Match xG (beklenen gol):')
        if home_xg is not None:
            lines.append(f'  - {home_team}: {home_xg} xG')
        if away_xg is not None:
            lines.append(f'  - {away_team}: {away_xg} xG')
        if home_xg and away_xg:
            xg_diff = round(float(home_xg) - float(away_xg), 2)
            dominant = home_team if xg_diff > 0 else away_team
            lines.append(f'  - xG farkı: {abs(xg_diff)} ({dominant} üstün)')

    # Puan/maç ortalamaları
    home_ppg = csv_data.get('home_ppg')
    away_ppg = csv_data.get('away_ppg')
    if home_ppg is not None or away_ppg is not None:
        lines.append('Puan/Maç Ortalaması (pre-match):')
        if home_ppg is not None:
            lines.append(f'  - {home_team}: {home_ppg} puan/maç')
        if away_ppg is not None:
            lines.append(f'  - {away_team}: {away_ppg} puan/maç')

    # İstatistiksel averajlar
    stat_lines = []
    avg_goals = csv_data.get('avg_goals')
    over25_avg = csv_data.get('over25_avg')
    over15_avg = csv_data.get('over15_avg')
    btts_avg = csv_data.get('btts_avg')
    avg_corners = csv_data.get('avg_corners')

    if avg_goals is not None:
        stat_lines.append(f'  - Ortalama gol/maç: {avg_goals}')
    if over25_avg is not None:
        stat_lines.append(f'  - Over 2.5 oranı: %{over25_avg}')
    if over15_avg is not None:
        stat_lines.append(f'  - Over 1.5 oranı: %{over15_avg}')
    if btts_avg is not None:
        stat_lines.append(f'  - KG VAR (BTTS) oranı: %{btts_avg}')
    if avg_corners is not None:
        stat_lines.append(f'  - Ortalama korner/maç: {avg_corners}')

    if stat_lines:
        lines.append('Maç İstatistik Ortalamaları (CSV):')
        lines.extend(stat_lines)

    # Bahis oranları (CSV kaynaklı)
    odds_home = csv_data.get('odds_home')
    odds_draw = csv_data.get('odds_draw')
    odds_away = csv_data.get('odds_away')
    odds_over25 = csv_data.get('odds_over25')
    odds_btts = csv_data.get('odds_btts_yes')

    odds_lines = []
    if odds_home:
        try:
            imp = round(1 / float(odds_home) * 100, 1)
            odds_lines.append(f'  - {home_team} kazanır: {odds_home} (implied %{imp})')
        except:
            odds_lines.append(f'  - {home_team} kazanır: {odds_home}')
    if odds_draw:
        try:
            imp = round(1 / float(odds_draw) * 100, 1)
            odds_lines.append(f'  - Beraberlik: {odds_draw} (implied %{imp})')
        except:
            odds_lines.append(f'  - Beraberlik: {odds_draw}')
    if odds_away:
        try:
            imp = round(1 / float(odds_away) * 100, 1)
            odds_lines.append(f'  - {away_team} kazanır: {odds_away} (implied %{imp})')
        except:
            odds_lines.append(f'  - {away_team} kazanır: {odds_away}')
    if odds_over25:
        try:
            imp = round(1 / float(odds_over25) * 100, 1)
            odds_lines.append(f'  - Over 2.5: {odds_over25} (implied %{imp})')
        except:
            odds_lines.append(f'  - Over 2.5: {odds_over25}')
    if odds_btts:
        try:
            imp = round(1 / float(odds_btts) * 100, 1)
            odds_lines.append(f'  - KG VAR: {odds_btts} (implied %{imp})')
        except:
            odds_lines.append(f'  - KG VAR: {odds_btts}')

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
                 csv_data=None):           # ← YENİ parametre

    # Form yoksa Elo trendinden türet
    if not home_form and elo_data and elo_data.get('home_trend_label'):
        home_form = elo_trend_to_form(elo_data.get('home_trend_label'), elo_data.get('home_trend_30d'))
        home_form = home_form + ' (Guc trendi baz alinarak hesaplandi)'

    if not away_form and elo_data and elo_data.get('away_trend_label'):
        away_form = elo_trend_to_form(elo_data.get('away_trend_label'), elo_data.get('away_trend_30d'))
        away_form = away_form + ' (Guc trendi baz alinarak hesaplandi)'

    # H2H
    h2h_text = ''
    if h2h_summary:
        h2h_text = (
            '\nH2H (Son ' + str(h2h_summary['total']) + ' mac):\n' +
            '- ' + home_team + ' galibiyet: ' + str(h2h_summary['home_wins']) + '\n' +
            '- ' + away_team + ' galibiyet: ' + str(h2h_summary['away_wins']) + '\n' +
            '- Beraberlik: ' + str(h2h_summary['draws']) + '\n' +
            '- Mac basi ortalama gol: ' + str(h2h_summary['avg_goals'])
        )

    # İstatistikler
    stats_text = ''
    if home_goals_avg > 0 or away_goals_avg > 0:
        stats_text = '\nGenel Istatistikler (son maclar):\n'
        stats_text += '- ' + home_team + ': ort. ' + str(home_goals_avg) + ' gol atar / ' + str(home_conceded_avg) + ' gol yer\n'
        stats_text += '- ' + away_team + ': ort. ' + str(away_goals_avg) + ' gol atar / ' + str(away_conceded_avg) + ' gol yer\n'
        stats_text += '- ' + home_team + ' genel form: ' + (home_form if home_form else 'Bilinmiyor') + '\n'
        stats_text += '- ' + away_team + ' genel form: ' + (away_form if away_form else 'Bilinmiyor')
    else:
        stats_text = (
            '\nForm Bilgisi:\n' +
            '- ' + home_team + ' form: ' + (home_form if home_form else 'Bilinmiyor') + '\n' +
            '- ' + away_team + ' form: ' + (away_form if away_form else 'Bilinmiyor')
        )

    # Gol trendi
    trend_text = ''
    if home_goals_trend or away_goals_trend:
        trend_text = '\nGol Trendi (Son 5 Maç — eskiden yeniye):\n'
        if home_goals_trend:
            scored_str = ' | '.join(str(g) for g in home_goals_trend['scored'])
            conceded_str = ' | '.join(str(g) for g in home_goals_trend['conceded'])
            trend_text += (
                f'- {home_team} attığı goller: {scored_str} (ort. {home_goals_trend["scored_avg"]})\n'
                f'- {home_team} yediği goller: {conceded_str} (ort. {home_goals_trend["conceded_avg"]})\n'
            )
        if away_goals_trend:
            scored_str = ' | '.join(str(g) for g in away_goals_trend['scored'])
            conceded_str = ' | '.join(str(g) for g in away_goals_trend['conceded'])
            trend_text += (
                f'- {away_team} attığı goller: {scored_str} (ort. {away_goals_trend["scored_avg"]})\n'
                f'- {away_team} yediği goller: {conceded_str} (ort. {away_goals_trend["conceded_avg"]})\n'
            )
        trend_text += '- NOT: Son maçlardaki gol paterni, takımın mevcut hücum/savunma durumunu gösterir\n'

    # Ev/Deplasman ayrımlı istatistikler
    venue_text = ''
    has_venue = (home_home_avg is not None and home_home_avg > 0) or \
                (away_away_avg is not None and away_away_avg > 0)
    if has_venue:
        venue_text = '\nEv/Deplasman Istatistikleri:\n'
        if home_home_avg is not None:
            venue_text += '- ' + home_team + ' (EV): ort. ' + str(home_home_avg) + ' gol atar / ' + str(home_conceded_home_avg or 0) + ' gol yer'
            if home_home_form:
                venue_text += ' | ev formu: ' + home_home_form
            venue_text += '\n'
        if away_away_avg is not None:
            venue_text += '- ' + away_team + ' (DEPLASMAN): ort. ' + str(away_away_avg) + ' gol atar / ' + str(away_conceded_away_avg or 0) + ' gol yer'
            if away_away_form:
                venue_text += ' | deplasman formu: ' + away_away_form
            venue_text += '\n'
        venue_text += '- NOT: Ev sahibi istatistikleri bu mac icin daha relevantdir'

    # Puan durumu
    standing_text = ''
    if home_standing or away_standing:
        standing_text = '\nPuan Durumu:\n'
        if home_standing:
            standing_text += (
                '- ' + home_team + ': ' + str(home_standing['position']) + '. sira | ' +
                str(home_standing['points']) + ' puan | ' +
                str(home_standing['played']) + ' mac | ' +
                str(home_standing['won']) + 'G ' + str(home_standing['draw']) + 'B ' + str(home_standing['lost']) + 'M | ' +
                'Averaj: ' + str(home_standing['goal_diff']) + '\n'
            )
        if away_standing:
            standing_text += (
                '- ' + away_team + ': ' + str(away_standing['position']) + '. sira | ' +
                str(away_standing['points']) + ' puan | ' +
                str(away_standing['played']) + ' mac | ' +
                str(away_standing['won']) + 'G ' + str(away_standing['draw']) + 'B ' + str(away_standing['lost']) + 'M | ' +
                'Averaj: ' + str(away_standing['goal_diff']) + '\n'
            )
        if home_standing and away_standing:
            home_pos = home_standing['position']
            away_pos = away_standing['position']
            total = max(home_pos, away_pos)
            if home_pos <= 4:
                standing_text += '- ' + home_team + ' sampiyonluk/Avrupa yarisi motivasyonu YUKSEK\n'
            elif home_pos >= total - 2:
                standing_text += '- ' + home_team + ' kume dusme baskisi var, KRITIK mac\n'
            if away_pos <= 4:
                standing_text += '- ' + away_team + ' sampiyonluk/Avrupa yarisi motivasyonu YUKSEK\n'
            elif away_pos >= total - 2:
                standing_text += '- ' + away_team + ' kume dusme baskisi var, KRITIK mac\n'

    # Elo (CSV yoksa kullanılır)
    elo_text = ''
    if elo_data:
        home_elo = elo_data.get('home_elo')
        away_elo = elo_data.get('away_elo')
        prob_home = elo_data.get('prob_home')
        prob_draw = elo_data.get('prob_draw')
        prob_away = elo_data.get('prob_away')
        home_trend_label = elo_data.get('home_trend_label')
        away_trend_label = elo_data.get('away_trend_label')
        home_trend_30d = elo_data.get('home_trend_30d')
        away_trend_30d = elo_data.get('away_trend_30d')
        home_trend_90d = elo_data.get('home_trend_90d')
        away_trend_90d = elo_data.get('away_trend_90d')

        if home_elo and away_elo:
            elo_diff = home_elo - away_elo
            guclu = home_team if elo_diff > 0 else away_team
            elo_text = (
                '\nGuc ve Form Analizi (Matematiksel):\n' +
                '- ' + home_team + ' Guc Puani: ' + str(home_elo) + '\n' +
                '- ' + away_team + ' Guc Puani: ' + str(away_elo) + '\n' +
                '- Guc farki: ' + ('+' if elo_diff >= 0 else '') + str(elo_diff) + ' (' + guclu + ' daha guclu)\n'
            )
        elif home_elo:
            elo_text = '\nGuc ve Form Analizi:\n- ' + home_team + ' Guc Puani: ' + str(home_elo) + '\n'
        elif away_elo:
            elo_text = '\nGuc ve Form Analizi:\n- ' + away_team + ' Guc Puani: ' + str(away_elo) + '\n'

        if elo_text:
            if home_trend_label and home_trend_30d is not None:
                trend_sign = '+' if home_trend_30d >= 0 else ''
                h90_sign = '+' if (home_trend_90d or 0) >= 0 else ''
                elo_text += '- ' + home_team + ' form trendi: ' + home_trend_label + ' (son 30g: ' + trend_sign + str(home_trend_30d) + ', son 90g: ' + h90_sign + str(home_trend_90d or 0) + ')\n'
            if away_trend_label and away_trend_30d is not None:
                trend_sign = '+' if away_trend_30d >= 0 else ''
                a90_sign = '+' if (away_trend_90d or 0) >= 0 else ''
                elo_text += '- ' + away_team + ' form trendi: ' + away_trend_label + ' (son 30g: ' + trend_sign + str(away_trend_30d) + ', son 90g: ' + a90_sign + str(away_trend_90d or 0) + ')\n'
            if prob_home and prob_draw and prob_away:
                elo_text += (
                    '- Matematiksel 1X2 olasiliklari: ' + home_team + ' %' + str(prob_home) +
                    ' | Beraberlik %' + str(prob_draw) + ' | ' + away_team + ' %' + str(prob_away) + '\n' +
                    '- NOT: Bu olasiliklar matematiksel guc analizine gore hesaplanmistir'
                )

    # Bahis oranları (API kaynaklı — CSV yoksa)
    odds_text = ''
    if odds_data and not (csv_data and csv_data.get('odds_home')):
        home_odds = odds_data.get('home_odds')
        draw_odds = odds_data.get('draw_odds')
        away_odds = odds_data.get('away_odds')
        bm_count = odds_data.get('bookmaker_count', 0)
        if home_odds and away_odds:
            try:
                imp_home = round(1 / home_odds * 100, 1)
                imp_away = round(1 / away_odds * 100, 1)
                imp_draw = round(1 / draw_odds * 100, 1) if draw_odds else None
                odds_text = (
                    '\nBahis Piyasasi (' + str(bm_count) + ' bahisci ortalamasi):\n' +
                    '- ' + home_team + ' kazanir: ' + str(home_odds) + ' (' + str(imp_home) + '%)\n' +
                    ('- Beraberlik: ' + str(draw_odds) + ' (' + str(imp_draw) + '%)\n' if draw_odds else '') +
                    '- ' + away_team + ' kazanir: ' + str(away_odds) + ' (' + str(imp_away) + '%)\n'
                )
            except:
                pass

    # Şut / Korner istatistikleri (API kaynaklı)
    shot_text = ''
    if home_shot_stats or away_shot_stats:
        shot_text = '\nŞut ve Baskı İstatistikleri (Son 5 Maç):\n'
        if home_shot_stats:
            shot_text += (
                f'- {home_team}: ort. {home_shot_stats["shots_avg"]} şut | '
                f'{home_shot_stats["shots_on_target_avg"]} isabetli şut | '
                f'isabet oranı %{home_shot_stats["shot_accuracy"]} | '
                f'{home_shot_stats["corners_avg"]} korner | '
                f'yenilen şut: {home_shot_stats["shots_conceded_avg"]}\n'
            )
        if away_shot_stats:
            shot_text += (
                f'- {away_team}: ort. {away_shot_stats["shots_avg"]} şut | '
                f'{away_shot_stats["shots_on_target_avg"]} isabetli şut | '
                f'isabet oranı %{away_shot_stats["shot_accuracy"]} | '
                f'{away_shot_stats["corners_avg"]} korner | '
                f'yenilen şut: {away_shot_stats["shots_conceded_avg"]}\n'
            )
        shot_text += '- NOT: Yüksek şut ve korner sayısı baskı üstünlüğünü, yüksek isabetli şut oranı gol kalitesini gösterir\n'

    # İlk yarı istatistikleri
    ht_text = ''
    if home_ht_stats or away_ht_stats:
        ht_text = '\nİlk Yarı İstatistikleri (Gerçek Veri):\n'
        if home_ht_stats:
            n = home_ht_stats['matches_used']
            ht_text += (
                f'- {home_team}: ilk yarı ort. {home_ht_stats["ht_goals_avg"]} gol atar | '
                f'{home_ht_stats["ht_conceded_avg"]} gol yer | '
                f'son {n} maçın %{home_ht_stats["ht_over05_pct"]}\'inde ilk yarıda gol var | '
                f'%{home_ht_stats["ht_scored_pct"]}\'inde kendisi gol atar\n'
            )
        if away_ht_stats:
            n = away_ht_stats['matches_used']
            ht_text += (
                f'- {away_team}: ilk yarı ort. {away_ht_stats["ht_goals_avg"]} gol atar | '
                f'{away_ht_stats["ht_conceded_avg"]} gol yer | '
                f'son {n} maçın %{away_ht_stats["ht_over05_pct"]}\'inde ilk yarıda gol var | '
                f'%{away_ht_stats["ht_scored_pct"]}\'inde kendisi gol atar\n'
            )
        ht_text += (
            '- NOT: ht2g_pct tahminini bu gerçek ilk yarı verilerine dayandır. '
            'İki takımın ilk yarı gol ortalaması toplamı yüksekse ve '
            'maçlarının büyük çoğunluğunda ilk yarıda gol varsa ht2g_pct yüksek olmalı.\n'
        )

    # KG VAR istatistikleri
    btts_text = ''
    if home_btts_stats or away_btts_stats:
        btts_text = '\nKG VAR (BTTS) İstatistikleri (Gerçek Veri):\n'
        if home_btts_stats:
            n = home_btts_stats['matches_used']
            btts_text += (
                f'- {home_team}: son {n} maçın %{home_btts_stats["scored_pct"]}\'inde gol atar | '
                f'%{home_btts_stats["conceded_pct"]}\'inde gol yer\n'
            )
        if away_btts_stats:
            n = away_btts_stats['matches_used']
            btts_text += (
                f'- {away_team}: son {n} maçın %{away_btts_stats["scored_pct"]}\'inde gol atar | '
                f'%{away_btts_stats["conceded_pct"]}\'inde gol yer\n'
            )
        if btts_mathematical is not None:
            btts_text += (
                f'- Matematiksel KG VAR tahmini: '
                f'%{home_btts_stats["scored_pct"]} × %{away_btts_stats["scored_pct"]} / 100 = %{btts_mathematical}\n'
                f'- NOT: btts_pct için bu matematiksel değeri referans al, '
                f'ancak H2H ve motivasyon gibi faktörleri de göz önünde bulundur\n'
            )

    # ── CSV verileri bölümü ──
    csv_text = build_csv_section(home_team, away_team, csv_data)

    match_importance = detect_match_importance(league)

    # CSV varsa over25/btts için ek yönlendirme
    csv_hint = ''
    if csv_data:
        hints = []
        if csv_data.get('over25_avg'):
            hints.append(f'Over 2.5 için CSV ortalama %{csv_data["over25_avg"]} veriyor — bunu temel referans al')
        if csv_data.get('btts_avg'):
            hints.append(f'KG VAR için CSV ortalama %{csv_data["btts_avg"]} veriyor — bunu temel referans al')
        if csv_data.get('home_xg') and csv_data.get('away_xg'):
            hints.append(f'xG verileri tahmine en çok yansıtılacak istatistik — yüksek xG → yüksek gol ihtimali')
        if hints:
            csv_hint = '\nCSV Veri Önceliklendirmesi:\n' + '\n'.join(f'- {h}' for h in hints) + '\n'

    prompt = (
        'Asagidaki futbol macini analiz et ve SADECE JSON formatinda yanit ver:\n\n' +
        'Mac: ' + home_team + ' vs ' + away_team + '\n' +
        'Lig: ' + league + '\n' +
        'Tarih: ' + str(match_time) + '\n' +
        'Mac Tipi: ' + match_importance + '\n' +
        stats_text + '\n' +
        trend_text + '\n' +
        venue_text + '\n' +
        standing_text + '\n' +
        h2h_text + '\n' +
        elo_text + '\n' +
        odds_text + '\n' +
        shot_text + '\n' +
        ht_text + '\n' +
        btts_text + '\n' +
        csv_text + '\n' +       # ← CSV bölümü eklendi
        csv_hint + '\n' +       # ← CSV önceliklendirme ipuçları
        '\nAnaliz yaparken su faktorleri goz onunde bulundur:\n' +
        '1. Ev sahibi avantaji + ev/deplasman istatistikleri birlikte degerlendir\n' +
        '2. Puan durumu motivasyonu: kume dusme baskisi veya sampiyonluk yarisi performansi etkiler\n' +
        '3. CSV xG verisi varsa en güvenilir kaynak olarak kullan — gol beklentisini yansıtır\n' +
        '4. CSV Over25/BTTS ortalamaları varsa over25_pct ve btts_pct için temel referans al\n' +
        '5. Form trendi: Yukselende olan takim momentum avantajina sahiptir\n' +
        '6. Bahis oranları (CSV veya API): implied probability göz önünde bulundur\n' +
        '7. Şut ve korner istatistikleri varsa: yüksek şut = baskı üstünlüğü\n' +
        '8. ht2g_pct için MUTLAKA ilk yarı istatistiklerini kullan\n' +
        '9. btts_pct için matematiksel KG VAR değerini ve CSV BTTS%\'ini birlikte değerlendir\n' +
        '10. Gol trendi varsa son maçlardaki gol paterni over25_pct için referans al\n' +
        '11. Tum yanitlar TURKCE olacak\n' +
        '12. Analizinde kesinlikle "Elo" kelimesini kullanma, "Guc Puani" kullan\n\n' +
        'Alan aciklamalari:\n' +
        '- over25_pct: Mac genelinde 2.5 gol ustu olma ihtimali (0-100)\n' +
        '- ht2g_pct: Ilk yaride EN AZ 1 gol olma ihtimali (0-100) — ilk yarı istatistiklerine dayandır\n' +
        '- btts_pct: Her iki takimin da gol atma ihtimali (0-100) — CSV BTTS% ve matematiksel değeri referans al\n\n' +
        'SADECE su JSON formatinda yanit ver:\n' +
        '{\n' +
        '  "prediction_1x2": "1 veya X veya 2",\n' +
        '  "over25_pct": 55,\n' +
        '  "ht2g_pct": 40,\n' +
        '  "btts_pct": 45,\n' +
        '  "predicted_score": "2-1",\n' +
        '  "confidence": "Orta",\n' +
        '  "reasoning": [\n' +
        '    "' + home_team + ' hakkinda degerlendirme",\n' +
        '    "' + away_team + ' hakkinda degerlendirme",\n' +
        '    "Puan durumu ve motivasyon analizi"\n' +
        '  ],\n' +
        '  "h2h_summary": "H2H ozeti"\n' +
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
                {'role': 'system', 'content': 'Sen profesyonel bir futbol bahis analistisin. Tum yanitlar TURKCE olacak. Elo kelimesini kullanma, Guc Puani kullan.'},
                {'role': 'user', 'content': prompt}
            ],
            'max_tokens': 1000, 'temperature': 0.7
        },
        timeout=30
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
            'system': 'Sen profesyonel bir futbol bahis analistisin. Tum yanitlar TURKCE olacak. Elo kelimesini kullanma, Guc Puani kullan.',
            'messages': [{'role': 'user', 'content': prompt}]
        },
        timeout=30
    )
    response.raise_for_status()
    return response.json()['content'][0]['text'].strip()

def call_gemini(prompt):
    time.sleep(3)
    response = requests.post(
        'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key=' + GEMINI_API_KEY,
        headers={'Content-Type': 'application/json'},
        json={
            'contents': [{'parts': [{'text': 'Sen profesyonel bir futbol bahis analistisin. TURKCE yaz. Elo kelimesini kullanma. SADECE JSON dondur.\n\n' + prompt}]}],
            'generationConfig': {'maxOutputTokens': 1000, 'temperature': 0.7, 'responseMimeType': 'application/json'}
        },
        timeout=30
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
    conf_order = ['Dusuk', 'Orta', 'Yuksek', 'Cok Yuksek']
    pred = r1.get('prediction_1x2') if r1.get('prediction_1x2') == r2.get('prediction_1x2') else r1.get('prediction_1x2')
    over25 = round((float(r1.get('over25_pct', 50)) + float(r2.get('over25_pct', 50))) / 2)
    ht2g = round((float(r1.get('ht2g_pct', 40)) + float(r2.get('ht2g_pct', 40))) / 2)
    btts = round((float(r1.get('btts_pct', 40)) + float(r2.get('btts_pct', 40))) / 2)
    c1 = conf_order.index(r1.get('confidence', 'Orta')) if r1.get('confidence') in conf_order else 1
    c2 = conf_order.index(r2.get('confidence', 'Orta')) if r2.get('confidence') in conf_order else 1
    confidence = conf_order[min(c1, c2)]
    return {
        'prediction_1x2': pred, 'over25_pct': over25, 'ht2g_pct': ht2g, 'btts_pct': btts,
        'predicted_score': r1.get('predicted_score', '?-?'), 'confidence': confidence,
        'reasoning': r1.get('reasoning', r2.get('reasoning', [])),
        'h2h_summary': r1.get('h2h_summary', '')
    }

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
                        csv_data=None):              # ← YENİ parametre

    home_team = fixture['teams']['home']['name']
    away_team = fixture['teams']['away']['name']
    league = fixture['league']['name']
    match_time = fixture['fixture']['date']

    # Ev/deplasman ayrımlı istatistikler
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
                home_home_avg = round(sum(home_home_goals) / len(home_home_goals), 1)
        except:
            pass

    if not away_away_avg:
        try:
            away_away_goals = [
                m['goals']['away'] for m in away_matches
                if away_team.lower().split()[0] in m['teams']['away']['name'].lower()
                and m['goals']['away'] is not None
            ]
            if away_away_goals:
                away_away_avg = round(sum(away_away_goals) / len(away_away_goals), 1)
        except:
            pass

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
        csv_data=csv_data,         # ← prompt'a taşındı
    )

    result = None
    mode = ANALYSIS_MODE

    if mode == 'claude':
        if ANTHROPIC_API_KEY:
            try:
                raw = call_anthropic(prompt)
                result = parse_result(raw)
                logger.info('Claude OK: ' + home_team + ' vs ' + away_team)
            except Exception as e:
                logger.error('Claude failed: ' + str(e))
        if not result and GEMINI_API_KEY:
            try:
                raw = call_gemini(prompt)
                result = parse_result(raw)
                logger.info('Gemini (yedek) OK: ' + home_team + ' vs ' + away_team)
            except Exception as e:
                logger.error('Gemini fallback failed: ' + str(e))

    elif mode == 'gemini':
        if GEMINI_API_KEY:
            try:
                raw = call_gemini(prompt)
                result = parse_result(raw)
                logger.info('Gemini OK: ' + home_team + ' vs ' + away_team)
            except Exception as e:
                logger.error('Gemini failed: ' + str(e))
        if not result and ANTHROPIC_API_KEY:
            try:
                raw = call_anthropic(prompt)
                result = parse_result(raw)
                logger.info('Claude (yedek) OK: ' + home_team + ' vs ' + away_team)
            except Exception as e:
                logger.error('Claude fallback failed: ' + str(e))

    elif mode == 'both':
        r_claude = None
        r_gemini = None
        if ANTHROPIC_API_KEY:
            try:
                raw = call_anthropic(prompt)
                r_claude = parse_result(raw)
                logger.info('Claude OK: ' + home_team + ' vs ' + away_team)
            except Exception as e:
                logger.error('Claude failed: ' + str(e))
        if GEMINI_API_KEY:
            try:
                raw = call_gemini(prompt)
                r_gemini = parse_result(raw)
                logger.info('Gemini OK: ' + home_team + ' vs ' + away_team)
            except Exception as e:
                logger.error('Gemini failed: ' + str(e))
        if r_claude and r_gemini:
            result = merge_results(r_claude, r_gemini)
        else:
            result = r_claude or r_gemini

    elif mode == 'groq':
        if GROQ_API_KEY:
            try:
                raw = call_groq(prompt)
                result = parse_result(raw)
                logger.info('Groq OK: ' + home_team + ' vs ' + away_team)
            except Exception as e:
                logger.error('Groq failed: ' + str(e))

    if not result:
        return mock_analysis(fixture, home_form, away_form, home_goals_avg, away_goals_avg)

    return {
        'analysis_date': datetime.now().strftime('%Y-%m-%d'),
        'fixture_id': fixture['fixture']['id'],
        'home_team': home_team, 'away_team': away_team,
        'league': league, 'match_time': match_time,
        'prediction_1x2': result.get('prediction_1x2', '?'),
        'over25_pct': float(result.get('over25_pct', 50)),
        'ht2g_pct': float(result.get('ht2g_pct', 40)),
        'btts_pct': float(result.get('btts_pct', 40)),
        'predicted_score': result.get('predicted_score', '?-?'),
        'confidence': result.get('confidence', 'Orta'),
        'reasoning': json.dumps(result.get('reasoning', []), ensure_ascii=False),
        'h2h_summary': result.get('h2h_summary', ''),
        'home_form': home_form, 'away_form': away_form,
        'home_goals_avg': home_goals_avg, 'away_goals_avg': away_goals_avg,
        'home_goals_trend': json.dumps(home_goals_trend, ensure_ascii=False) if home_goals_trend else None,
        'away_goals_trend': json.dumps(away_goals_trend, ensure_ascii=False) if away_goals_trend else None,
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
        'predicted_score': '2-1', 'confidence': 'Orta',
        'reasoning': json.dumps([
            home_team + ' ev sahibi avantajina sahip',
            'Istatistiksel model tahmini', 'Genel form degerlendirmesi'
        ], ensure_ascii=False),
        'h2h_summary': 'Genel istatistiklere gore tahmin',
        'home_form': home_form, 'away_form': away_form,
        'home_goals_avg': home_goals_avg, 'away_goals_avg': away_goals_avg,
        'home_goals_trend': None, 'away_goals_trend': None,
    }
