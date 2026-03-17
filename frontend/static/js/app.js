// ===== CSV UPLOAD =====
function initCsvUpload() {
    const btn = document.getElementById('csvUploadBtn');
    const input = document.getElementById('csvUpload');
    if (!btn || !input) return;

    btn.addEventListener('click', () => input.click());
    input.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;

        const status = document.getElementById('csvStatus');
        status.textContent = '⏳ CSV okunuyor...';
        status.style.color = '#888';

        try {
            const text = await file.text();
            const lines = text.split('\n').filter(l => l.trim());
            if (lines.length < 2) {
                status.textContent = '❌ Geçersiz CSV';
                status.style.color = '#ef4444';
                return;
            }

            // Başlık satırını parse et
            const headers = parseCSVLine(lines[0]);
            const idx = {
                homeTeam:   findCol(headers, ['Home Team', 'home_team_name']),
                awayTeam:   findCol(headers, ['Away Team', 'away_team_name']),
                league:     findCol(headers, ['League', 'league']),
                country:    findCol(headers, ['Country', 'country']),
                date:       findCol(headers, ['date_GMT', 'timestamp']),
                status:     findCol(headers, ['Match Status', 'status']),
                // CSV istatistik sütunları
                homeXg:     findCol(headers, ['Home Team Pre-Match xG']),
                awayXg:     findCol(headers, ['Away Team Pre-Match xG']),
                bttsAvg:    findCol(headers, ['BTTS Average']),
                over25Avg:  findCol(headers, ['Over25 Average']),
                over15Avg:  findCol(headers, ['Over15 Average']),
                avgGoals:   findCol(headers, ['Average Goals']),
                avgCorners: findCol(headers, ['Average Corners']),
                oddsHome:   findCol(headers, ['Odds_Home_Win']),
                oddsDraw:   findCol(headers, ['Odds_Draw']),
                oddsAway:   findCol(headers, ['Odds_Away_Win']),
                oddsOver25: findCol(headers, ['Odds_Over25']),
                oddsBtts:   findCol(headers, ['Odds_BTTS_Yes']),
                homePpg:    findCol(headers, ['Home Team Points Per Game (Pre-Match)']),
                awayPpg:    findCol(headers, ['Away Team Points Per Game (Pre-Match)']),
            };

            if (idx.homeTeam === -1 || idx.awayTeam === -1) {
                status.textContent = '❌ Takım sütunları bulunamadı';
                status.style.color = '#ef4444';
                return;
            }

            let added = 0;
            const rows = lines.slice(1);

            for (const line of rows) {
                if (!line.trim()) continue;
                const cols = parseCSVLine(line);
                if (cols.length < 3) continue;

                const homeTeam = (cols[idx.homeTeam] || '').trim().replace(/^"|"$/g, '');
                const awayTeam = (cols[idx.awayTeam] || '').trim().replace(/^"|"$/g, '');
                if (!homeTeam || !awayTeam) continue;

                // Sadece oynanmamış maçlar
                if (idx.status !== -1) {
                    const matchStatus = (cols[idx.status] || '').toLowerCase();
                    if (matchStatus === 'complete') continue;
                }

                const league  = idx.league  !== -1 ? (cols[idx.league]  || '').trim().replace(/^"|"$/g, '') : 'Bilinmeyen';
                const country = idx.country !== -1 ? (cols[idx.country] || '').trim() : '';
                const leagueName = country && league ? `${country} - ${league}` : league;

                // Tarih parse
                let matchDate = null;
                if (idx.date !== -1 && cols[idx.date]) {
                    try {
                        const raw = cols[idx.date].trim().replace(/^"|"$/g, '');
                        matchDate = /^\d+$/.test(raw)
                            ? new Date(parseInt(raw) * 1000).toISOString()
                            : new Date(raw).toISOString();
                    } catch(e) {}
                }

                // ── CSV istatistik verilerini topla ──
                function safeFloat(colIdx) {
                    if (colIdx === -1 || !cols[colIdx]) return null;
                    const v = parseFloat(cols[colIdx].trim().replace(/^"|"$/g, ''));
                    return isNaN(v) ? null : v;
                }

                const csv_data = {
                    home_xg:       safeFloat(idx.homeXg),
                    away_xg:       safeFloat(idx.awayXg),
                    btts_avg:      safeFloat(idx.bttsAvg),
                    over25_avg:    safeFloat(idx.over25Avg),
                    over15_avg:    safeFloat(idx.over15Avg),
                    avg_goals:     safeFloat(idx.avgGoals),
                    avg_corners:   safeFloat(idx.avgCorners),
                    odds_home:     safeFloat(idx.oddsHome),
                    odds_draw:     safeFloat(idx.oddsDraw),
                    odds_away:     safeFloat(idx.oddsAway),
                    odds_over25:   safeFloat(idx.oddsOver25),
                    odds_btts_yes: safeFloat(idx.oddsBtts),
                    home_ppg:      safeFloat(idx.homePpg),
                    away_ppg:      safeFloat(idx.awayPpg),
                };

                // Zaten eklenmiş mi?
                const exists = manualMatches.some(x => x.home_team === homeTeam && x.away_team === awayTeam);
                if (!exists) {
                    manualMatches.push({
                        home_team: homeTeam,
                        away_team: awayTeam,
                        league:    leagueName,
                        date:      matchDate,
                        from_csv:  true,
                        csv_data,          // ← backend'e taşınan istatistikler
                    });
                    added++;
                }
            }

            renderManualList();
            updateSelectedCount();

            if (added > 0) {
                status.textContent = `✅ ${added} maç eklendi! Seçip analiz ettir.`;
                status.style.color = '#22c55e';
            } else {
                status.textContent = '⚠️ Eklenecek yeni maç bulunamadı.';
                status.style.color = '#f59e0b';
            }
        } catch(err) {
            status.textContent = '❌ Hata: ' + err.message;
            status.style.color = '#ef4444';
        }

        input.value = '';
    });
}
