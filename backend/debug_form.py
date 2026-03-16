"""
Bu scripti projenin kök dizininde çalıştır:
    python debug_form.py

Brentford ve Wolves için API'den gelen ham maçları gösterir.
Sofascore ile karşılaştırabilirsin.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.football_api import _get_football_data, ENGLISH_TEAM_NORMALIZED, teams_match

def debug_team(team_name, team_id):
    print(f"\n{'='*60}")
    print(f"TAKIM: {team_name} (ID: {team_id})")
    print('='*60)

    result = _get_football_data(f'teams/{team_id}/matches', {
        'status': 'FINISHED', 'limit': 10
    })

    if not result or not result.get('matches'):
        print("❌ Maç verisi gelmedi!")
        return

    matches = result['matches']
    print(f"API'den toplam {len(matches)} maç geldi\n")

    print("TÜM MAÇLAR (API sırası — index 0 = ilk gelen):")
    print(f"{'#':<4} {'Tarih':<12} {'Ev':<30} {'Dep':<30} {'Skor':<8} {'Sonuç'}")
    print('-'*95)

    for i, m in enumerate(matches):
        try:
            home = m['homeTeam']['name']
            away = m['awayTeam']['name']
            hg = m['score']['fullTime']['home']
            ag = m['score']['fullTime']['away']
            date = m.get('utcDate', '')[:10]

            is_home = teams_match(team_name, home)
            team_goals = hg if is_home else ag
            opp_goals = ag if is_home else hg

            if team_goals > opp_goals:
                result_str = 'W ✅'
            elif team_goals == opp_goals:
                result_str = 'D 🟡'
            else:
                result_str = 'L ❌'

            marker = " ← SON 5" if i >= len(matches) - 5 else ""
            print(f"{i:<4} {date:<12} {home:<30} {away:<30} {str(hg)+'-'+str(ag):<8} {result_str}{marker}")
        except Exception as e:
            print(f"{i:<4} PARSE HATASI: {e}")

    # Son 5 maçın form stringi
    last5 = matches[-5:]
    form = []
    for m in last5:
        try:
            home = m['homeTeam']['name']
            hg = m['score']['fullTime']['home']
            ag = m['score']['fullTime']['away']
            is_home = teams_match(team_name, home)
            tg = hg if is_home else ag
            og = ag if is_home else hg
            form.append('W' if tg > og else ('D' if tg == og else 'L'))
        except:
            continue

    print(f"\n📊 BİZİM SİSTEM FORMU (son 5): {''.join(form)}")
    print(f"📊 SOFASCORE FORMU karşılaştır yukarıdaki ekran görüntüsüyle")


if __name__ == '__main__':
    # Brentford: 402, Wolves: 76
    debug_team('Brentford', 402)
    debug_team('Wolverhampton', 76)
