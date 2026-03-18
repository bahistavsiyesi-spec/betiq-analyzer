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
            if (lines.length < 2) { status.textContent = '❌ Geçersiz CSV'; status.style.color = '#ef4444'; return; }

            const headers = parseCSVLine(lines[0]);
            const idx = {
                homeTeam:       findCol(headers, ['Home Team', 'home_team_name']),
                awayTeam:       findCol(headers, ['Away Team', 'away_team_name']),
                league:         findCol(headers, ['League', 'league']),
                country:        findCol(headers, ['Country', 'country']),
                date:           findCol(headers, ['date_GMT', 'timestamp']),
                status:         findCol(headers, ['Match Status', 'status']),
                homeXg:         findCol(headers, ['Home Team Pre-Match xG']),
                awayXg:         findCol(headers, ['Away Team Pre-Match xG']),
                homePpg:        findCol(headers, ['Home Team Points Per Game (Pre-Match)']),
                awayPpg:        findCol(headers, ['Away Team Points Per Game (Pre-Match)']),
                avgGoals:       findCol(headers, ['Average Goals']),
                over05Avg:      findCol(headers, ['Over05 Average']),
                over15Avg:      findCol(headers, ['Over15 Average']),
                over25Avg:      findCol(headers, ['Over25 Average']),
                over35Avg:      findCol(headers, ['Over35 Average']),
                over45Avg:      findCol(headers, ['Over45 Average']),
                bttsAvg:        findCol(headers, ['BTTS Average']),
                btts1hAvg:      findCol(headers, ['1H BTTS Average']),
                ht05Avg:        findCol(headers, ['Over05 FHG HT Average']),
                ht15Avg:        findCol(headers, ['Over15 FHG HT Average']),
                avgCorners:     findCol(headers, ['Average Corners']),
                avgCorners85:   findCol(headers, ['Average Over 8.5 Corners']),
                avgCorners95:   findCol(headers, ['Average Over 9.5 Corners']),
                avgCorners105:  findCol(headers, ['Average Over 10.5 Corners']),
                avgCards:       findCol(headers, ['Average Cards']),
                oddsHome:       findCol(headers, ['Odds_Home_Win']),
                oddsDraw:       findCol(headers, ['Odds_Draw']),
                oddsAway:       findCol(headers, ['Odds_Away_Win']),
                oddsOver15:     findCol(headers, ['Odds_Over15']),
                oddsOver25:     findCol(headers, ['Odds_Over25']),
                oddsOver35:     findCol(headers, ['Odds_Over35']),
                oddsOver45:     findCol(headers, ['Odds_Over45']),
                oddsUnder25:    findCol(headers, ['Odds_Under25']),
                oddsBtts:       findCol(headers, ['Odds_BTTS_Yes']),
                oddsBttsNo:     findCol(headers, ['Odds_BTTS_No']),
                oddsHt05:       findCol(headers, ['Odds_1st_Half_Over05']),
                oddsHt15:       findCol(headers, ['Odds_1st_Half_Over15']),
                oddsHt25:       findCol(headers, ['Odds_1st_Half_Over25']),
                oddsDc1x:       findCol(headers, ['Odds_DoubleChance_1x']),
                oddsDc12:       findCol(headers, ['Odds_DoubleChance_12']),
                oddsDcX2:       findCol(headers, ['Odds_DoubleChance_x2']),
                oddsDnb1:       findCol(headers, ['Odds_DrawNoBet_1']),
                oddsDnb2:       findCol(headers, ['Odds_DrawNoBet_2']),
                oddsCorn85:     findCol(headers, ['Odds_Corners_Over85']),
                oddsCorn95:     findCol(headers, ['Odds_Corners_Over95']),
                oddsCorn105:    findCol(headers, ['Odds_Corners_Over105']),
            };

            if (idx.homeTeam === -1 || idx.awayTeam === -1) {
                status.textContent = '❌ Takım sütunları bulunamadı'; status.style.color = '#ef4444'; return;
            }

            let added = 0;
            for (const line of lines.slice(1)) {
                if (!line.trim()) continue;
                const cols = parseCSVLine(line);
                if (cols.length < 3) continue;
                const homeTeam = (cols[idx.homeTeam] || '').trim().replace(/^"|"$/g, '');
                const awayTeam = (cols[idx.awayTeam] || '').trim().replace(/^"|"$/g, '');
                if (!homeTeam || !awayTeam) continue;
                if (idx.status !== -1) {
                    const ms = (cols[idx.status] || '').toLowerCase();
                    if (ms === 'complete') continue;
                }
                const league  = idx.league  !== -1 ? (cols[idx.league]  || '').trim().replace(/^"|"$/g, '') : 'Bilinmeyen';
                const country = idx.country !== -1 ? (cols[idx.country] || '').trim() : '';
                const leagueName = country && league ? `${country} - ${league}` : league;
                let matchDate = null;
                if (idx.date !== -1 && cols[idx.date]) {
                    try {
                        const raw = cols[idx.date].trim().replace(/^"|"$/g, '');
                        matchDate = /^\d+$/.test(raw) ? new Date(parseInt(raw)*1000).toISOString() : new Date(raw).toISOString();
                    } catch(e) {}
                }
                function sf(ci) {
                    if (ci === -1 || !cols[ci]) return null;
                    const v = parseFloat(cols[ci].trim().replace(/^"|"$/g, ''));
                    return isNaN(v) ? null : v;
                }
                const csv_data = {
                    home_xg: sf(idx.homeXg), away_xg: sf(idx.awayXg),
                    home_ppg: sf(idx.homePpg), away_ppg: sf(idx.awayPpg),
                    avg_goals: sf(idx.avgGoals),
                    over05_avg: sf(idx.over05Avg), over15_avg: sf(idx.over15Avg),
                    over25_avg: sf(idx.over25Avg), over35_avg: sf(idx.over35Avg), over45_avg: sf(idx.over45Avg),
                    btts_avg: sf(idx.bttsAvg), btts_1h_avg: sf(idx.btts1hAvg),
                    ht_over05_avg: sf(idx.ht05Avg), ht_over15_avg: sf(idx.ht15Avg),
                    avg_corners: sf(idx.avgCorners),
                    avg_corners_85: sf(idx.avgCorners85), avg_corners_95: sf(idx.avgCorners95), avg_corners_105: sf(idx.avgCorners105),
                    avg_cards: sf(idx.avgCards),
                    odds_home: sf(idx.oddsHome), odds_draw: sf(idx.oddsDraw), odds_away: sf(idx.oddsAway),
                    odds_over15: sf(idx.oddsOver15), odds_over25: sf(idx.oddsOver25),
                    odds_over35: sf(idx.oddsOver35), odds_over45: sf(idx.oddsOver45), odds_under25: sf(idx.oddsUnder25),
                    odds_btts_yes: sf(idx.oddsBtts), odds_btts_no: sf(idx.oddsBttsNo),
                    odds_ht_over05: sf(idx.oddsHt05), odds_ht_over15: sf(idx.oddsHt15), odds_ht_over25: sf(idx.oddsHt25),
                    odds_dc_1x: sf(idx.oddsDc1x), odds_dc_12: sf(idx.oddsDc12), odds_dc_x2: sf(idx.oddsDcX2),
                    odds_dnb_1: sf(idx.oddsDnb1), odds_dnb_2: sf(idx.oddsDnb2),
                    odds_corners_85: sf(idx.oddsCorn85), odds_corners_95: sf(idx.oddsCorn95), odds_corners_105: sf(idx.oddsCorn105),
                };
                if (!manualMatches.some(x => x.home_team === homeTeam && x.away_team === awayTeam)) {
                    manualMatches.push({ home_team: homeTeam, away_team: awayTeam, league: leagueName, date: matchDate, from_csv: true, csv_data });
                    added++;
                }
            }
            renderManualList(); updateSelectedCount();
            status.textContent = added > 0 ? `✅ ${added} maç eklendi! Seçip analiz ettir.` : '⚠️ Eklenecek yeni maç bulunamadı.';
            status.style.color = added > 0 ? '#22c55e' : '#f59e0b';
        } catch(err) {
            status.textContent = '❌ Hata: ' + err.message; status.style.color = '#ef4444';
        }
        input.value = '';
    });
}

function parseCSVLine(line) {
    const result = []; let current = '', inQuotes = false;
    for (let i = 0; i < line.length; i++) {
        const ch = line[i];
        if (ch === '"') inQuotes = !inQuotes;
        else if (ch === ',' && !inQuotes) { result.push(current); current = ''; }
        else current += ch;
    }
    result.push(current); return result;
}

function findCol(headers, names) {
    for (const name of names) {
        const idx = headers.findIndex(h => h.trim().replace(/^"|"$/g, '').toLowerCase() === name.toLowerCase());
        if (idx !== -1) return idx;
    }
    return -1;
}

const API_BASE = '';
let selectedFixtures = {};
let manualMatches = [];
let couponCanvas = null;

const TEAM_IDS = {
    'Bayern': 5, 'Dortmund': 4, 'Leverkusen': 3, 'Leipzig': 721,
    'Frankfurt': 19, 'Stuttgart': 10, 'Freiburg': 17, 'Hoffenheim': 2,
    'Bremen': 12, 'Wolfsburg': 11, 'Gladbach': 18, 'Augsburg': 16,
    'Union Berlin': 28, 'Bochum': 20, 'Mainz': 15, 'St. Pauli': 20,
    'Kiel': 44, 'Heidenheim': 44, 'Hamburg': 7, 'Hannover': 30,
    'Karlsruhe': 24, 'Schalke': 6, 'Darmstadt': 36, 'Köln': 1,
    'Hertha': 27, 'Düsseldorf': 45, 'Nürnberg': 7,
    'Arsenal': 57, 'Aston Villa': 58, 'Bournemouth': 1044,
    'Brentford': 402, 'Brighton': 397, 'Chelsea': 61,
    'Crystal Palace': 354, 'Everton': 62, 'Fulham': 63,
    'Ipswich': 349, 'Leicester': 338, 'Liverpool': 64,
    'Manchester City': 65, 'Man City': 65,
    'Manchester United': 66, 'Man United': 66, 'Man Utd': 66,
    'Newcastle': 67, 'Newcastle United': 67,
    'Nottingham Forest': 351, "Nott'm Forest": 351,
    'Southampton': 340, 'Tottenham': 73, 'Spurs': 73,
    'West Ham': 563, 'Wolverhampton': 76, 'Wolves': 76,
    'Burnley': 328, 'Leeds': 341, 'Sunderland': 71, 'Coventry': 1076, 'Middlesbrough': 343,
    'Barcelona': 81, 'Real Madrid': 86, 'Atlético Madrid': 78, 'Atletico': 78,
    'Athletic Club': 77, 'Athletic Bilbao': 77, 'Real Sociedad': 92, 'Villarreal': 95,
    'Real Betis': 90, 'Betis': 90, 'Valencia': 94, 'Girona': 298,
    'Celta Vigo': 558, 'Celta': 558, 'Sevilla': 559, 'Osasuna': 79,
    'Getafe': 82, 'Rayo Vallecano': 88, 'Rayo': 88, 'Mallorca': 89,
    'Alavés': 263, 'Alaves': 263, 'Espanyol': 80,
    'Las Palmas': 275, 'Leganés': 745, 'Leganes': 745, 'Valladolid': 250,
    'AC Milan': 98, 'Milan': 98, 'Inter': 108, 'Inter Milan': 108,
    'Juventus': 109, 'Napoli': 113, 'Atalanta': 102,
    'Roma': 100, 'AS Roma': 100, 'Lazio': 110, 'Fiorentina': 99, 'Bologna': 103,
    'Torino': 586, 'Udinese': 115, 'Genoa': 107,
    'Cagliari': 104, 'Lecce': 5890, 'Verona': 450,
    'Parma': 112, 'Como': 7397, 'Monza': 5911,
    'PSG': 524, 'Paris Saint-Germain': 524, 'Marseille': 516,
    'Lyon': 523, 'Monaco': 548, 'Lille': 521, 'Nice': 522,
    'Lens': 546, 'Rennes': 529, 'Nantes': 543,
};

function getTeamLogoUrl(teamName) {
    if (TEAM_IDS[teamName]) return `https://crests.football-data.org/${TEAM_IDS[teamName]}.png`;
    const lower = teamName.toLowerCase();
    for (const [key, id] of Object.entries(TEAM_IDS)) {
        if (key.toLowerCase().includes(lower) || lower.includes(key.toLowerCase()))
            return `https://crests.football-data.org/${id}.png`;
    }
    return null;
}

function teamLogoHtml(teamName) {
    const url = getTeamLogoUrl(teamName);
    if (!url) return '';
    return `<img src="${url}" alt="${teamName}" style="width:24px;height:24px;object-fit:contain;border-radius:4px;margin-bottom:4px;" onerror="this.style.display='none'">`;
}

function getWinnerLabel(prediction, homeTeam, awayTeam) {
    if (prediction === '1') return { label: homeTeam + ' Kazanır', icon: '🏆' };
    if (prediction === '2') return { label: awayTeam + ' Kazanır', icon: '🏆' };
    if (prediction === 'X') return { label: 'Beraberlik', icon: '🤝' };
    return { label: 'Belirsiz', icon: '❓' };
}

function pctClass(pct) { const v = parseFloat(pct)||0; return v>=70?'pct-high':v>=40?'pct-medium':'pct-low'; }
function barClass(pct) { const v = parseFloat(pct)||0; return v>=70?'bar-high':v>=40?'bar-medium':'bar-low'; }
function cardConfidenceClass(c) {
    return {'Çok Yüksek':'card-confidence-very-high','Yüksek':'card-confidence-high','Orta':'card-confidence-medium','Düşük':'card-confidence-low'}[c]||'card-confidence-medium';
}

async function downloadCard(matchId, homeTeam, awayTeam) {
    const card = document.getElementById(`matchcard-${matchId}`); if (!card) return;
    const btn = document.getElementById(`dlbtn-${matchId}`);
    if (btn) { btn.textContent = '⏳'; btn.disabled = true; }
    try {
        const canvas = await html2canvas(card, { scale: 2, backgroundColor: null, useCORS: true, logging: false });
        const link = document.createElement('a');
        link.download = `${homeTeam}_vs_${awayTeam}.png`.replace(/\s+/g, '_');
        link.href = canvas.toDataURL('image/png'); link.click();
    } catch(e) { alert('İndirme hatası: ' + e.message); }
    if (btn) { btn.textContent = '📸'; btn.disabled = false; }
}

function buildTrendHtml(match) {
    let homeTrend = null, awayTrend = null;
    try { homeTrend = match.home_goals_trend ? JSON.parse(match.home_goals_trend) : null; } catch(e) {}
    try { awayTrend = match.away_goals_trend ? JSON.parse(match.away_goals_trend) : null; } catch(e) {}
    if (!homeTrend && !awayTrend) return '';
    function goalDot(goals, type) {
        return goals.map(g => {
            let color = type==='scored' ? (g===0?'#ef4444':g>=3?'#22c55e':'#f59e0b') : (g===0?'#22c55e':g>=3?'#ef4444':'#f59e0b');
            return `<span style="display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:50%;background:${color}22;border:1px solid ${color};color:${color};font-size:11px;font-weight:700;">${g===0?'○':g}</span>`;
        }).join('');
    }
    function trendRow(label, goals, type) {
        const avg = goals.length?(goals.reduce((a,b)=>a+b,0)/goals.length).toFixed(1):'0';
        return `<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
            <span style="font-size:11px;color:#666;width:90px;flex-shrink:0;">${label}</span>
            <div style="display:flex;gap:4px;">${goalDot(goals,type)}</div>
            <span style="font-size:11px;color:#555;margin-left:4px;">ort. ${avg}</span>
        </div>`;
    }
    let html = `<div style="margin-top:14px;padding:12px 14px;background:#0d0d1a;border-radius:10px;border:1px solid #1e1e3a;">
        <div style="font-size:11px;color:#7c3aed;font-weight:700;letter-spacing:0.5px;margin-bottom:10px;">📈 GOL TRENDİ (Son 5 Maç)</div>`;
    if (homeTrend) html += `<div style="margin-bottom:8px;"><div style="font-size:11px;color:#aaa;font-weight:600;margin-bottom:4px;">${match.home_team}</div>${trendRow('⚽ Attığı',homeTrend.scored,'scored')}${trendRow('🥅 Yediği',homeTrend.conceded,'conceded')}</div>`;
    if (awayTrend) html += `<div style="margin-top:${homeTrend?'8px':'0'};padding-top:${homeTrend?'8px':'0'};${homeTrend?'border-top:1px solid #1e1e3a;':''}"><div style="font-size:11px;color:#aaa;font-weight:600;margin-bottom:4px;">${match.away_team}</div>${trendRow('⚽ Attığı',awayTrend.scored,'scored')}${trendRow('🥅 Yediği',awayTrend.conceded,'conceded')}</div>`;
    html += `<div style="font-size:10px;color:#333;margin-top:6px;">← Eski &nbsp;&nbsp;&nbsp; Yeni →</div></div>`;
    return html;
}

async function generateCoupon() {
    const btn = document.getElementById('couponBtn');
    btn.disabled = true; btn.textContent = '⏳ Oluşturuluyor...';
    try {
        const resp = await fetch('/api/coupon/today');
        const data = await resp.json();
        if (data.status !== 'success') { alert(data.message||'Kupon oluşturulamadı.'); btn.disabled=false; btn.textContent='🎫 Kupon Oluştur'; return; }
        drawCouponCanvas(data.coupon);
    } catch(e) { alert('Hata: '+e.message); btn.disabled=false; btn.textContent='🎫 Kupon Oluştur'; }
}

function drawCouponCanvas(coupon) {
    const today = new Date().toLocaleDateString('tr-TR',{day:'2-digit',month:'2-digit',year:'numeric'});
    const width=480,headerH=110,rowH=68,footerH=70;
    const contentH=headerH+coupon.length*rowH+footerH;
    const height=Math.max(width*1.25,contentH);
    const extraPad=Math.max(0,height-contentH);
    const canvas=document.createElement('canvas');
    canvas.width=width*2; canvas.height=height*2;
    const ctx=canvas.getContext('2d'); ctx.scale(2,2);
    const bg=ctx.createLinearGradient(0,0,0,height);
    bg.addColorStop(0,'#0d0d1a'); bg.addColorStop(1,'#160a28');
    ctx.fillStyle=bg; ctx.fillRect(0,0,width,height);
    ctx.strokeStyle='#2a1a4e'; ctx.lineWidth=1; ctx.strokeRect(0.5,0.5,width-1,height-1);
    const logo=new Image(); logo.crossOrigin='anonymous'; logo.src='/static/img/logo.png';
    const drawContent=()=>{
        if(logo.naturalWidth) ctx.drawImage(logo,20,20,56,56);
        ctx.fillStyle='#555'; ctx.font='500 11px Syne,sans-serif'; ctx.textAlign='right'; ctx.fillText(today,width-20,32);
        ctx.fillStyle='#7c3aed'; ctx.font='800 16px Syne,sans-serif'; ctx.fillText('GÜNÜN KUPONU',width-20,54);
        ctx.strokeStyle='#1e1e3a'; ctx.lineWidth=1;
        ctx.beginPath(); ctx.moveTo(20,headerH-6); ctx.lineTo(width-20,headerH-6); ctx.stroke();
        coupon.forEach((item,i)=>{
            const y=headerH+i*rowH;
            if(i%2===0){ctx.fillStyle='rgba(124,58,237,0.04)';ctx.fillRect(0,y,width,rowH);}
            ctx.font='700 12px Syne,sans-serif'; ctx.fillStyle='#fff'; ctx.textAlign='left';
            let mt=`${item.home_team} vs ${item.away_team}`;
            while(ctx.measureText(mt).width>230&&mt.length>10) mt=mt.slice(0,-4)+'...';
            ctx.fillText(mt,20,y+26);
            ctx.fillStyle='#444'; ctx.font='500 10px Syne,sans-serif'; ctx.fillText(item.league,20,y+44);
            const bc=getBadgeColor(item.prediction_type);
            const bW=118,bH=44,bX=width-bW-20,bY=y+(rowH-bH)/2;
            ctx.fillStyle=bc.bg; roundRect(ctx,bX,bY,bW,bH,10); ctx.fill();
            ctx.strokeStyle=bc.border; ctx.lineWidth=1.5; roundRect(ctx,bX,bY,bW,bH,10); ctx.stroke();
            ctx.fillStyle=bc.text; ctx.font='700 13px Syne,sans-serif'; ctx.textAlign='center';
            ctx.fillText(item.prediction_label,bX+bW/2,bY+bH/2+5);
        });
        const fy=headerH+coupon.length*rowH+extraPad/2;
        ctx.fillStyle='#2a2a3a'; ctx.font='400 9px Syne,sans-serif'; ctx.textAlign='center';
        ctx.fillText('Bu tahminler yapay zeka analizi ile oluşturulmuştur. Sorumluluk kabul edilmez.',width/2,fy+32);
        couponCanvas=canvas; showCouponPreview(canvas,today);
        const b=document.getElementById('couponBtn'); if(b){b.disabled=false;b.textContent='🎫 Kupon Oluştur';}
    };
    logo.onload=drawContent; logo.onerror=drawContent;
}

function showCouponPreview(canvas,today) {
    document.getElementById('couponModal')?.remove();
    const modal=document.createElement('div'); modal.id='couponModal';
    modal.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:9999;display:flex;align-items:center;justify-content:center;padding:20px;';
    const imgSrc=canvas.toDataURL('image/png');
    modal.innerHTML=`<div style="background:#0d0d1a;border:1px solid #2a1a4e;border-radius:16px;padding:20px;max-width:520px;width:100%;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
            <span style="color:#fff;font-weight:700;font-size:14px;">🎫 Kupon Önizleme</span>
            <button onclick="document.getElementById('couponModal').remove()" style="background:transparent;border:none;color:#666;font-size:20px;cursor:pointer;">✕</button>
        </div>
        <div style="display:flex;justify-content:center;margin-bottom:16px;max-height:70vh;overflow-y:auto;">
            <img src="${imgSrc}" style="max-width:100%;border-radius:10px;border:1px solid #2a1a4e;">
        </div>
        <div style="display:flex;gap:10px;justify-content:flex-end;">
            <button onclick="document.getElementById('couponModal').remove()" style="padding:10px 20px;border-radius:10px;border:1px solid #333;background:transparent;color:#aaa;font-size:13px;cursor:pointer;font-family:inherit;">İptal</button>
            <button onclick="downloadCoupon('${today}')" style="padding:10px 20px;border-radius:10px;border:none;background:#7c3aed;color:#fff;font-size:13px;font-weight:700;cursor:pointer;font-family:inherit;">⬇️ PNG İndir</button>
        </div>
    </div>`;
    modal.addEventListener('click',(e)=>{if(e.target===modal)modal.remove();});
    document.body.appendChild(modal);
}

function downloadCoupon(today) {
    if(!couponCanvas) return;
    const link=document.createElement('a');
    link.download=`betiq_kupon_${today.replace(/\./g,'-')}.png`;
    link.href=couponCanvas.toDataURL('image/png'); link.click();
    document.getElementById('couponModal')?.remove();
}

function getBadgeColor(type) {
    const map={
        '1X2':{bg:'rgba(124,58,237,0.15)',border:'rgba(124,58,237,0.6)',text:'#a78bfa'},
        '2.5 Üst':{bg:'rgba(34,197,94,0.12)',border:'rgba(34,197,94,0.5)',text:'#4ade80'},
        '2.5 Alt':{bg:'rgba(59,130,246,0.12)',border:'rgba(59,130,246,0.5)',text:'#60a5fa'},
        'KG Var':{bg:'rgba(245,158,11,0.12)',border:'rgba(245,158,11,0.5)',text:'#fbbf24'},
        'KG Yok':{bg:'rgba(239,68,68,0.12)',border:'rgba(239,68,68,0.5)',text:'#f87171'},
        'İY 0.5 Üst':{bg:'rgba(168,85,247,0.12)',border:'rgba(168,85,247,0.5)',text:'#c084fc'},
    };
    return map[type]||map['1X2'];
}

function roundRect(ctx,x,y,w,h,r){
    ctx.beginPath(); ctx.moveTo(x+r,y); ctx.lineTo(x+w-r,y); ctx.quadraticCurveTo(x+w,y,x+w,y+r);
    ctx.lineTo(x+w,y+h-r); ctx.quadraticCurveTo(x+w,y+h,x+w-r,y+h);
    ctx.lineTo(x+r,y+h); ctx.quadraticCurveTo(x,y+h,x,y+h-r);
    ctx.lineTo(x,y+r); ctx.quadraticCurveTo(x,y,x+r,y); ctx.closePath();
}

// ===== FIXTURES =====
async function loadFixtures() {
    const container = document.getElementById('fixturesList');
    container.innerHTML = `<div class="loading-fixtures"><div class="spinner"></div><span>Maçlar yükleniyor...</span></div>`;
    try {
        const resp = await fetch('/api/fixtures/today');
        const fixtures = await resp.json();
        if (!fixtures || fixtures.length === 0) {
            container.innerHTML = `<div class="no-matches"><p>📭 API kotası doldu.<br>📸 Görsel yükle veya CSV ekle.</p></div>`; return;
        }
        const grouped = {};
        fixtures.forEach(f => { const l=f.league||'Diğer'; if(!grouped[l])grouped[l]=[]; grouped[l].push(f); });
        let html = '';
        for (const [league, matches] of Object.entries(grouped)) {
            html += `<div class="league-group"><div class="league-title">🏆 ${league}</div>`;
            matches.forEach(f => {
                const time = formatTime(f.date);
                html += `<div class="fixture-item" data-id="${f.id}" onclick="toggleFixture(${f.id},'${f.home_team}','${f.away_team}','${f.league}','${f.date}')">
                    <div class="fixture-check" id="check-${f.id}">☐</div>
                    <div class="fixture-info">
                        <span class="fixture-teams">${f.home_team} vs ${f.away_team}</span>
                        ${time?`<span class="fixture-time">${time}</span>`:''}
                    </div>
                </div>`;
            });
            html += `</div>`;
        }
        container.innerHTML = html;
    } catch(e) {
        container.innerHTML = `<div class="no-matches"><p>📭 API kotası doldu.<br>📸 Görsel yükle veya CSV ekle.</p></div>`;
    }
}

function toggleFixture(id,home,away,league,date) {
    if(selectedFixtures[id]){delete selectedFixtures[id];document.getElementById(`check-${id}`).textContent='☐';document.querySelector(`[data-id="${id}"]`).classList.remove('selected');}
    else{selectedFixtures[id]={id,home_team:home,away_team:away,league,date};document.getElementById(`check-${id}`).textContent='✅';document.querySelector(`[data-id="${id}"]`).classList.add('selected');}
    updateSelectedCount();
}

function selectAll() {
    const items=document.querySelectorAll('.fixture-item');
    const allSelected=items.length===Object.keys(selectedFixtures).length;
    items.forEach(item=>{
        const id=parseInt(item.dataset.id);
        if(allSelected){delete selectedFixtures[id];document.getElementById(`check-${id}`).textContent='☐';item.classList.remove('selected');}
        else{selectedFixtures[id]={id};document.getElementById(`check-${id}`).textContent='✅';item.classList.add('selected');}
    });
    updateSelectedCount();
}

function updateSelectedCount() {
    const total=Object.keys(selectedFixtures).length+manualMatches.length;
    document.getElementById('selectedCount').textContent=`${total} maç seçildi`;
    document.getElementById('analyzeBtn').disabled=total===0;
}

// ===== IMAGE UPLOAD =====
function initImageUpload() {
    const btn=document.getElementById('imageUploadBtn');
    const input=document.getElementById('imageUpload');
    btn.addEventListener('click',()=>input.click());
    input.addEventListener('change',async(e)=>{
        const file=e.target.files[0]; if(!file) return;
        const reader=new FileReader();
        reader.onload=(ev)=>{document.getElementById('previewImg').src=ev.target.result;document.getElementById('imagePreview').style.display='block';};
        reader.readAsDataURL(file);
        const status=document.getElementById('imageStatus');
        status.textContent='🔍 Görsel analiz ediliyor...'; status.style.color='#888'; btn.disabled=true;
        try {
            const base64=await fileToBase64(file);
            const resp=await fetch('/api/parse/image',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({image:base64,media_type:file.type})});
            const data=await resp.json();
            if(data.status==='success'&&data.matches.length>0){
                data.matches.forEach(m=>{if(!manualMatches.some(x=>x.home_team===m.home_team&&x.away_team===m.away_team))manualMatches.push(m);});
                renderManualList(); updateSelectedCount();
                status.textContent=`✅ ${data.matches.length} maç eklendi!`; status.style.color='#22c55e';
            } else {status.textContent='❌ Maç bulunamadı.'; status.style.color='#ef4444';}
        } catch(err){status.textContent='❌ Hata: '+err.message; status.style.color='#ef4444';}
        btn.disabled=false; input.value='';
    });
}

function fileToBase64(file){
    return new Promise((resolve,reject)=>{
        const reader=new FileReader();
        reader.onload=()=>resolve(reader.result.split(',')[1]);
        reader.onerror=reject; reader.readAsDataURL(file);
    });
}

// ===== MANUAL MATCHES =====
function addManualMatch() {
    const home=document.getElementById('homeTeam').value.trim();
    const away=document.getElementById('awayTeam').value.trim();
    const league=document.getElementById('leagueName').value.trim()||'Manuel Maç';
    const time=document.getElementById('matchTime').value;
    if(!home||!away){alert('Ev sahibi ve deplasman takımı gerekli!');return;}
    let matchDate=null;
    if(time){const t=new Date();const[h,m]=time.split(':');t.setHours(parseInt(h),parseInt(m),0,0);matchDate=t.toISOString();}
    manualMatches.push({home_team:home,away_team:away,league,date:matchDate});
    document.getElementById('homeTeam').value=''; document.getElementById('awayTeam').value='';
    document.getElementById('leagueName').value=''; document.getElementById('matchTime').value='';
    renderManualList(); updateSelectedCount();
}

function removeManual(index){manualMatches.splice(index,1);renderManualList();updateSelectedCount();}

function renderManualList() {
    const container=document.getElementById('manualList');
    if(manualMatches.length===0){container.innerHTML='';return;}
    container.innerHTML=manualMatches.map((m,i)=>{
        const timeStr=formatTime(m.date);
        return `<div class="manual-item">
            <span>⚽ ${m.home_team} vs ${m.away_team} <small>(${m.league})</small>${timeStr?' 🕐 '+timeStr:''}</span>
            <button onclick="removeManual(${i})" class="btn-remove">✕</button>
        </div>`;
    }).join('');
}

// ===== ANALYSIS =====
async function runAnalysis() {
    const btn=document.getElementById('analyzeBtn');
    const statusDiv=document.getElementById('analysisStatus');
    const total=Object.keys(selectedFixtures).length+manualMatches.length;
    btn.disabled=true; btn.innerHTML='⏳ Analiz başlatılıyor...';
    statusDiv.style.display='block';
    statusDiv.innerHTML=`<div class="status-box"><div class="status-spinner"></div><div class="status-text">
        <strong>🔍 ${total} maç analiz ediliyor...</strong>
        <span>Claude AI çalışıyor, yaklaşık ${total*10} saniye sürer.</span>
        <div class="progress-bar-wrap"><div class="progress-bar-fill" id="progressBar"></div></div>
        <small id="progressText">Başlatılıyor...</small>
    </div></div>`;
    const duration=total*10000;
    [10,25,40,55,70,85,95].forEach((pct,i)=>{
        setTimeout(()=>{
            const bar=document.getElementById('progressBar'); const txt=document.getElementById('progressText');
            if(bar)bar.style.width=pct+'%';
            if(txt)txt.textContent=`🤖 Analiz yapılıyor... (${Math.ceil(i*total/7)}/${total})`;
        },(duration/7)*i);
    });
    try {
        const resp=await fetch('/api/analyze/selected',{method:'POST',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({fixture_ids:Object.keys(selectedFixtures).map(Number),manual_matches:manualMatches})});
        const data=await resp.json();
        if(data.status==='success') setTimeout(async()=>await checkAndReload(statusDiv,btn,total),duration+5000);
        else showError(statusDiv,btn,data.message);
    } catch(e){showError(statusDiv,btn,e.message);}
}

async function checkAndReload(statusDiv,btn,total) {
    try {
        const res=await fetch('/api/matches/today'); const matches=await res.json();
        if(matches&&matches.length>0){
            const bar=document.getElementById('progressBar'); const txt=document.getElementById('progressText');
            if(bar)bar.style.width='100%'; if(txt)txt.textContent='✅ Analiz tamamlandı!';
            statusDiv.innerHTML=`<div class="status-box success"><span>✅ ${matches.length} maç analiz edildi!</span></div>`;
            renderMatches(matches); btn.disabled=false; btn.innerHTML='🔍 Seçilenleri Analiz Et'; statusDiv.style.display='none';
        } else setTimeout(()=>checkAndReload(statusDiv,btn,total),15000);
    } catch(e){setTimeout(()=>checkAndReload(statusDiv,btn,total),15000);}
}

function showError(statusDiv,btn,message){
    statusDiv.innerHTML=`<div class="status-box error"><span>❌ Hata: ${message}</span></div>`;
    btn.disabled=false; btn.innerHTML='🔍 Seçilenleri Analiz Et';
}

async function sendToTelegram() {
    const btn=document.getElementById('telegramBtn'); btn.disabled=true; btn.innerHTML='⏳ Gönderiliyor...';
    try {
        const resp=await fetch('/api/telegram/send',{method:'POST'}); const data=await resp.json();
        if(data.status==='success'){btn.innerHTML='✅ Gönderildi!';btn.style.background='#22c55e';setTimeout(()=>{btn.innerHTML="📨 Telegram'a Gönder";btn.style.background='';btn.disabled=false;},3000);}
        else{btn.innerHTML='❌ Hata!';btn.style.background='#ef4444';alert('Hata: '+data.message);setTimeout(()=>{btn.innerHTML="📨 Telegram'a Gönder";btn.style.background='';btn.disabled=false;},3000);}
    } catch(e){btn.innerHTML='❌ Hata!';alert('Hata: '+e.message);btn.disabled=false;}
}

async function loadMatches() {
    const container=document.getElementById('matchesContainer');
    try {
        const resp=await fetch('/api/matches/today'); const matches=await resp.json();
        if(!matches||matches.length===0){container.innerHTML=`<div class="no-matches"><p>📭 Henüz analiz yapılmadı.</p><p>Sol taraftan maç seçip analiz et.</p></div>`;return;}
        renderMatches(matches);
    } catch(e){container.innerHTML=`<div class="no-matches"><p>📭 Henüz analiz yapılmadı.</p></div>`;}
}

function renderMatches(matches) {
    const container=document.getElementById('matchesContainer');
    if(!matches||matches.length===0){container.innerHTML=`<div class="no-matches"><p>📭 Henüz analiz yapılmadı.</p></div>`;return;}
    container.innerHTML=`
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding:0 4px;">
            <div style="display:flex;gap:8px;">
                <button id="telegramBtn" onclick="sendToTelegram()" style="padding:8px 18px;border-radius:8px;border:none;background:#2563eb;color:#fff;font-size:13px;cursor:pointer;font-family:inherit;font-weight:600;">📨 Telegram'a Gönder</button>
                <button id="couponBtn" onclick="generateCoupon()" style="padding:8px 18px;border-radius:8px;border:none;background:#7c3aed;color:#fff;font-size:13px;cursor:pointer;font-family:inherit;font-weight:600;">🎫 Kupon Oluştur</button>
            </div>
            <button onclick="clearAllMatches()" style="padding:6px 14px;border-radius:8px;border:1px solid #ef4444;background:transparent;color:#ef4444;font-size:12px;cursor:pointer;font-family:inherit;">🗑️ Tümünü Sil</button>
        </div>
        <div id="matchCardsList">${matches.map(m=>createMatchCard(m)).join('')}</div>`;
}

function createMatchCard(match) {
    const prediction=match.prediction_1x2||'?';
    const confidence=match.confidence||'Orta';
    const confidenceClass={'Çok Yüksek':'confidence-very-high','Yüksek':'confidence-high','Orta':'confidence-medium','Düşük':'confidence-low'}[confidence]||'confidence-medium';
    const cardClass=cardConfidenceClass(confidence);
    const timeStr=formatTime(match.match_time);
    const homeLogo=teamLogoHtml(match.home_team);
    const awayLogo=teamLogoHtml(match.away_team);
    const winner=getWinnerLabel(prediction,match.home_team,match.away_team);
    const over25=match.over25_pct||0, ht2g=match.ht2g_pct||0, btts=match.btts_pct||0;
    const trendHtml=buildTrendHtml(match);
    return `<div class="match-card ${cardClass}" id="matchcard-${match.id}">
        <div style="display:flex;justify-content:flex-end;gap:6px;margin-bottom:4px;">
            <button id="dlbtn-${match.id}" onclick="downloadCard(${match.id},'${match.home_team.replace(/'/g,"\\'")}','${match.away_team.replace(/'/g,"\\'")}' )"
                style="background:transparent;border:none;color:#555;font-size:15px;cursor:pointer;padding:0;line-height:1;"
                onmouseover="this.style.color='#7c3aed'" onmouseout="this.style.color='#555'" title="Kartı İndir">📸</button>
            <button onclick="deleteMatch(${match.id})"
                style="background:transparent;border:none;color:#444;font-size:15px;cursor:pointer;padding:0;line-height:1;"
                onmouseover="this.style.color='#ef4444'" onmouseout="this.style.color='#444'" title="Sil">🗑️</button>
        </div>
        <div class="match-header">
            <span class="league-badge">⚽ ${match.league||'Bilinmeyen Lig'}</span>
            ${timeStr?`<span class="match-time">${timeStr}`:''}${timeStr?'</span>':''}
        </div>
        <div class="teams">
            <div class="team home-team">${homeLogo}<span class="team-name">${match.home_team}</span><span class="team-form">${match.home_form||'N/A'}</span></div>
            <div class="vs-badge prediction-${prediction.toLowerCase()}">
                <img src="/static/img/logo.png" alt="GL" onerror="this.parentElement.innerHTML='${prediction}'">
            </div>
            <div class="team away-team">${awayLogo}<span class="team-name">${match.away_team}</span><span class="team-form">${match.away_form||'N/A'}</span></div>
        </div>
        <div class="stats-grid">
            <div class="stat-box"><span class="stat-label">🎯 2.5 GOL ÜSTÜ</span><span class="stat-value ${pctClass(over25)}">${over25}%</span><div class="stat-bar"><div class="stat-fill ${barClass(over25)}" style="width:${over25}%"></div></div></div>
            <div class="stat-box"><span class="stat-label">⚽ İY 0.5 ÜST</span><span class="stat-value ${pctClass(ht2g)}">${ht2g}%</span><div class="stat-bar"><div class="stat-fill ${barClass(ht2g)}" style="width:${ht2g}%"></div></div></div>
            <div class="stat-box"><span class="stat-label">🔁 KG VAR (BTTS)</span><span class="stat-value ${pctClass(btts)}">${btts}%</span><div class="stat-bar"><div class="stat-fill ${barClass(btts)}" style="width:${btts}%"></div></div></div>
            <div class="stat-box"><span class="stat-label">📊 GOL ORT.</span><span class="stat-value">${match.home_goals_avg||0} / ${match.away_goals_avg||0}</span></div>
        </div>
        <div class="prediction-row">
            <div class="predicted-score"><span class="score-label">${winner.icon} KAZANAN TAHMİNİ</span><span class="score-value">${winner.label}</span></div>
            <span class="confidence-badge ${confidenceClass}">Analiz Güveni: ${confidence}</span>
        </div>
        ${trendHtml}
    </div>`;
}

async function deleteMatch(id) {
    if(!confirm('Bu analizi silmek istediğine emin misin?')) return;
    try {
        await fetch(`/api/matches/delete/${id}`,{method:'DELETE'});
        document.getElementById(`matchcard-${id}`)?.remove();
        if(document.querySelectorAll('.match-card').length===0)
            document.getElementById('matchesContainer').innerHTML=`<div class="no-matches"><p>📭 Henüz analiz yapılmadı.</p></div>`;
    } catch(e){alert('Silme hatası: '+e.message);}
}

async function clearAllMatches() {
    if(!confirm('Bugünün tüm analizleri silinecek. Emin misin?')) return;
    try {
        await fetch('/api/matches/clear',{method:'DELETE'});
        document.getElementById('matchesContainer').innerHTML=`<div class="no-matches"><p>📭 Henüz analiz yapılmadı.</p></div>`;
    } catch(e){alert('Silme hatası: '+e.message);}
}

function formatTime(dateStr) {
    if(!dateStr) return '';
    try {
        const d=new Date(dateStr); if(isNaN(d.getTime())) return '';
        const t=d.toLocaleTimeString('tr-TR',{hour:'2-digit',minute:'2-digit',timeZone:'Europe/Istanbul'});
        if(t==='00:00'||t==='03:00') return '';
        return t;
    } catch{return '';}
}

// ===== INIT =====
document.addEventListener('DOMContentLoaded',()=>{
    loadFixtures(); loadMatches();
    document.getElementById('analyzeBtn').addEventListener('click',runAnalysis);
    document.getElementById('refreshFixtures').addEventListener('click',loadFixtures);
    document.getElementById('selectAll').addEventListener('click',selectAll);
    document.getElementById('addManual').addEventListener('click',addManualMatch);
    initImageUpload(); initCsvUpload();
});
