const API_BASE = '';
let selectedFixtures = {};
let manualMatches = [];

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
    'Nottingham Forest': 351, 'Nott\'m Forest': 351,
    'Southampton': 340, 'Tottenham': 73, 'Spurs': 73,
    'West Ham': 563, 'Wolverhampton': 76, 'Wolves': 76,
    'Burnley': 328, 'Leeds': 341, 'Sunderland': 71,
    'Coventry': 1076, 'Middlesbrough': 343,
    'Barcelona': 81, 'Real Madrid': 86, 'Atlético Madrid': 78, 'Atletico': 78,
    'Athletic Club': 77, 'Athletic Bilbao': 77,
    'Real Sociedad': 92, 'Villarreal': 95,
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

function pctClass(pct) {
    const v = parseFloat(pct) || 0;
    if (v >= 70) return 'pct-high';
    if (v >= 40) return 'pct-medium';
    return 'pct-low';
}

function barClass(pct) {
    const v = parseFloat(pct) || 0;
    if (v >= 70) return 'bar-high';
    if (v >= 40) return 'bar-medium';
    return 'bar-low';
}

function cardConfidenceClass(confidence) {
    const map = {
        'Çok Yüksek': 'card-confidence-very-high',
        'Yüksek':     'card-confidence-high',
        'Orta':       'card-confidence-medium',
        'Düşük':      'card-confidence-low',
    };
    return map[confidence] || 'card-confidence-medium';
}

// ─── Gol Trendi HTML ─────────────────────────────────────────────────────────
function buildTrendHtml(match) {
    let homeTrend = null, awayTrend = null;
    try { homeTrend = match.home_goals_trend ? JSON.parse(match.home_goals_trend) : null; } catch(e) {}
    try { awayTrend = match.away_goals_trend ? JSON.parse(match.away_goals_trend) : null; } catch(e) {}
    if (!homeTrend && !awayTrend) return '';

    function goalDot(goals, type) {
        return goals.map(g => {
            let color;
            if (type === 'scored') color = g === 0 ? '#ef4444' : g >= 3 ? '#22c55e' : '#f59e0b';
            else color = g === 0 ? '#22c55e' : g >= 3 ? '#ef4444' : '#f59e0b';
            return `<span style="display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:50%;background:${color}22;border:1px solid ${color};color:${color};font-size:11px;font-weight:700;">${g === 0 ? '○' : g}</span>`;
        }).join('');
    }

    function trendRow(label, goals, type) {
        const avg = goals.length ? (goals.reduce((a,b) => a+b, 0) / goals.length).toFixed(1) : '0';
        return `<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
            <span style="font-size:11px;color:#666;width:90px;flex-shrink:0;">${label}</span>
            <div style="display:flex;gap:4px;">${goalDot(goals, type)}</div>
            <span style="font-size:11px;color:#555;margin-left:4px;">ort. ${avg}</span>
        </div>`;
    }

    let html = `<div style="margin-top:14px;padding:12px 14px;background:#0d0d1a;border-radius:10px;border:1px solid #1e1e3a;">
        <div style="font-size:11px;color:#7c3aed;font-weight:700;letter-spacing:0.5px;margin-bottom:10px;">📈 GOL TRENDİ (Son 5 Maç)</div>`;
    if (homeTrend) {
        html += `<div style="margin-bottom:8px;">
            <div style="font-size:11px;color:#aaa;font-weight:600;margin-bottom:4px;">${match.home_team}</div>
            ${trendRow('⚽ Attığı', homeTrend.scored, 'scored')}
            ${trendRow('🥅 Yediği', homeTrend.conceded, 'conceded')}
        </div>`;
    }
    if (awayTrend) {
        html += `<div style="margin-top:${homeTrend ? '8px' : '0'};padding-top:${homeTrend ? '8px' : '0'};${homeTrend ? 'border-top:1px solid #1e1e3a;' : ''}">
            <div style="font-size:11px;color:#aaa;font-weight:600;margin-bottom:4px;">${match.away_team}</div>
            ${trendRow('⚽ Attığı', awayTrend.scored, 'scored')}
            ${trendRow('🥅 Yediği', awayTrend.conceded, 'conceded')}
        </div>`;
    }
    html += `<div style="font-size:10px;color:#333;margin-top:6px;">← Eski &nbsp;&nbsp;&nbsp; Yeni →</div></div>`;
    return html;
}

// ─── KUPON ───────────────────────────────────────────────────────────────────
async function generateCoupon() {
    const btn = document.getElementById('couponBtn');
    btn.disabled = true;
    btn.textContent = '⏳ Oluşturuluyor...';
    try {
        const resp = await fetch('/api/coupon/today');
        const data = await resp.json();
        if (data.status !== 'success') {
            alert(data.message || 'Kupon oluşturulamadı. Önce analiz yaptır.');
            btn.disabled = false;
            btn.textContent = '🎫 Kupon Oluştur';
            return;
        }
        drawCouponCanvas(data.coupon);
    } catch(e) {
        alert('Hata: ' + e.message);
        btn.disabled = false;
        btn.textContent = '🎫 Kupon Oluştur';
    }
}

function drawCouponCanvas(coupon) {
    const today = new Date().toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric' });

    // 4:5 format
    const width = 480;
    const headerH = 110;
    const rowH = 72;
    const footerH = 70;
    const minHeight = width * 1.25; // 4:5 oranı
    const contentH = headerH + coupon.length * rowH + footerH;
    const height = Math.max(minHeight, contentH);

    // Boş alan: maçlar az ise alt padding ekle
    const extraPad = Math.max(0, height - contentH);

    const canvas = document.createElement('canvas');
    canvas.width = width * 2;
    canvas.height = height * 2;
    const ctx = canvas.getContext('2d');
    ctx.scale(2, 2);

    // Arka plan
    const bg = ctx.createLinearGradient(0, 0, 0, height);
    bg.addColorStop(0, '#0d0d1a');
    bg.addColorStop(1, '#160a28');
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, width, height);

    // Mor glow sağ üst
    const glow = ctx.createRadialGradient(width, 0, 0, width, 0, 220);
    glow.addColorStop(0, 'rgba(124,58,237,0.3)');
    glow.addColorStop(1, 'transparent');
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, width, height);

    // Alt glow sol
    const glow2 = ctx.createRadialGradient(0, height, 0, 0, height, 180);
    glow2.addColorStop(0, 'rgba(124,58,237,0.15)');
    glow2.addColorStop(1, 'transparent');
    ctx.fillStyle = glow2;
    ctx.fillRect(0, 0, width, height);

    // Border
    ctx.strokeStyle = '#2a1a4e';
    ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, width - 1, height - 1);

    const logo = new Image();
    logo.crossOrigin = 'anonymous';
    logo.src = '/static/img/logo.png';

    const drawContent = () => {
        // Logo
        logo.width && ctx.drawImage(logo, 20, 20, 56, 56);

        // Tarih sağ üst
        ctx.fillStyle = '#555';
        ctx.font = '500 11px Syne, sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText(today, width - 20, 32);

        // GÜNÜN KUPONU
        ctx.fillStyle = '#7c3aed';
        ctx.font = '800 16px Syne, sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText('GÜNÜN KUPONU', width - 20, 54);

        // Güven badge
        ctx.fillStyle = 'rgba(124,58,237,0.15)';
        roundRect(ctx, width - 158, 62, 138, 24, 12);
        ctx.fill();
        ctx.strokeStyle = 'rgba(124,58,237,0.4)';
        ctx.lineWidth = 1;
        roundRect(ctx, width - 158, 62, 138, 24, 12);
        ctx.stroke();
        ctx.fillStyle = '#a78bfa';
        ctx.font = '600 10px Syne, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('✦ Yüksek Güven Analizi', width - 89, 78);

        // Ayırıcı
        ctx.strokeStyle = '#1e1e3a';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(20, headerH - 6);
        ctx.lineTo(width - 20, headerH - 6);
        ctx.stroke();

        // Maçlar
        coupon.forEach((item, i) => {
            const y = headerH + i * rowH;

            if (i % 2 === 0) {
                ctx.fillStyle = 'rgba(124,58,237,0.04)';
                ctx.fillRect(0, y, width, rowH);
            }

            // Maç bilgisi sol
            ctx.fillStyle = '#ffffff';
            ctx.font = '700 13px Syne, sans-serif';
            ctx.textAlign = 'left';

            // Uzun isim kısalt
            const maxW = 240;
            let matchText = `${item.home_team} vs ${item.away_team}`;
            ctx.font = '700 12px Syne, sans-serif';
            while (ctx.measureText(matchText).width > maxW && matchText.length > 10) {
                matchText = matchText.slice(0, -4) + '...';
            }
            ctx.fillText(matchText, 20, y + 26);

            ctx.fillStyle = '#444';
            ctx.font = '500 10px Syne, sans-serif';
            ctx.fillText(item.league, 20, y + 42);

            // Yüzde
            ctx.fillStyle = '#7c3aed';
            ctx.font = '800 14px Syne, sans-serif';
            ctx.textAlign = 'left';
            ctx.fillText(`%${item.pct}`, 20, y + 60);

            // Tahmin badge sağda
            const badgeColor = getBadgeColor(item.prediction_type);
            const badgeW = 120;
            const badgeH = 48;
            const badgeX = width - badgeW - 20;
            const badgeY = y + (rowH - badgeH) / 2;

            ctx.fillStyle = badgeColor.bg;
            roundRect(ctx, badgeX, badgeY, badgeW, badgeH, 10);
            ctx.fill();
            ctx.strokeStyle = badgeColor.border;
            ctx.lineWidth = 1.5;
            roundRect(ctx, badgeX, badgeY, badgeW, badgeH, 10);
            ctx.stroke();

            // Badge içinde sadece TAHMİN TÜRÜ (tek satır, ortalı)
            ctx.fillStyle = badgeColor.text;
            ctx.font = '700 13px Syne, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(item.prediction_label, badgeX + badgeW / 2, badgeY + badgeH / 2 + 5);

            // Alt çizgi
            if (i < coupon.length - 1) {
                ctx.strokeStyle = '#1a1a2e';
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(20, y + rowH);
                ctx.lineTo(width - 20, y + rowH);
                ctx.stroke();
            }
        });

        // Footer
        const fy = headerH + coupon.length * rowH + extraPad / 2;

        ctx.strokeStyle = '#1e1e3a';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(20, fy + 12);
        ctx.lineTo(width - 20, fy + 12);
        ctx.stroke();

        ctx.fillStyle = '#2a2a3a';
        ctx.font = '400 9px Syne, sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('Bu tahminler yapay zeka analizi ile oluşturulmuştur. Sorumluluk kabul edilmez.', width / 2, fy + 32);

        ctx.fillStyle = '#7c3aed';
        ctx.font = '700 11px Syne, sans-serif';
        ctx.fillText('⚡ BetIQ ANALYZER', width / 2, fy + 52);

        // İndir
        const link = document.createElement('a');
        link.download = `betiq_kupon_${today.replace(/\./g, '-')}.png`;
        link.href = canvas.toDataURL('image/png');
        link.click();

        const btn = document.getElementById('couponBtn');
        if (btn) { btn.disabled = false; btn.textContent = '🎫 Kupon Oluştur'; }
    };

    logo.onload = drawContent;
    logo.onerror = drawContent;
}

function getBadgeColor(type) {
    const map = {
        '1X2':        { bg: 'rgba(124,58,237,0.15)', border: 'rgba(124,58,237,0.6)', text: '#a78bfa' },
        '2.5 Üst':    { bg: 'rgba(34,197,94,0.12)',  border: 'rgba(34,197,94,0.5)',  text: '#4ade80' },
        '2.5 Alt':    { bg: 'rgba(59,130,246,0.12)', border: 'rgba(59,130,246,0.5)', text: '#60a5fa' },
        'KG Var':     { bg: 'rgba(245,158,11,0.12)', border: 'rgba(245,158,11,0.5)', text: '#fbbf24' },
        'KG Yok':     { bg: 'rgba(239,68,68,0.12)',  border: 'rgba(239,68,68,0.5)',  text: '#f87171' },
        'İY 0.5 Üst': { bg: 'rgba(168,85,247,0.12)', border: 'rgba(168,85,247,0.5)', text: '#c084fc' },
    };
    return map[type] || map['1X2'];
}

function roundRect(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.lineTo(x + w - r, y);
    ctx.quadraticCurveTo(x + w, y, x + w, y + r);
    ctx.lineTo(x + w, y + h - r);
    ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
    ctx.lineTo(x + r, y + h);
    ctx.quadraticCurveTo(x, y + h, x, y + h - r);
    ctx.lineTo(x, y + r);
    ctx.quadraticCurveTo(x, y, x + r, y);
    ctx.closePath();
}

// ===== FIXTURES =====
async function loadFixtures() {
    const container = document.getElementById('fixturesList');
    container.innerHTML = `<div class="loading-fixtures"><div class="spinner"></div><span>Maçlar yükleniyor...</span></div>`;
    try {
        const resp = await fetch('/api/fixtures/today');
        const fixtures = await resp.json();
        if (!fixtures || fixtures.length === 0) {
            container.innerHTML = `<div class="no-matches"><p>📭 API kotası doldu.<br>📸 Görsel yükle veya manuel ekle.</p></div>`;
            return;
        }
        const grouped = {};
        fixtures.forEach(f => {
            const league = f.league || 'Diğer';
            if (!grouped[league]) grouped[league] = [];
            grouped[league].push(f);
        });
        let html = '';
        for (const [league, matches] of Object.entries(grouped)) {
            html += `<div class="league-group"><div class="league-title">🏆 ${league}</div>`;
            matches.forEach(f => {
                const time = formatTime(f.date);
                html += `
                <div class="fixture-item" data-id="${f.id}" onclick="toggleFixture(${f.id}, '${f.home_team}', '${f.away_team}', '${f.league}', '${f.date}')">
                    <div class="fixture-check" id="check-${f.id}">☐</div>
                    <div class="fixture-info">
                        <span class="fixture-teams">${f.home_team} vs ${f.away_team}</span>
                        ${time ? `<span class="fixture-time">${time}</span>` : ''}
                    </div>
                </div>`;
            });
            html += `</div>`;
        }
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<div class="no-matches"><p>📭 API kotası doldu.<br>📸 Görsel yükle veya manuel ekle.</p></div>`;
    }
}

function toggleFixture(id, home, away, league, date) {
    if (selectedFixtures[id]) {
        delete selectedFixtures[id];
        document.getElementById(`check-${id}`).textContent = '☐';
        document.querySelector(`[data-id="${id}"]`).classList.remove('selected');
    } else {
        selectedFixtures[id] = { id, home_team: home, away_team: away, league, date };
        document.getElementById(`check-${id}`).textContent = '✅';
        document.querySelector(`[data-id="${id}"]`).classList.add('selected');
    }
    updateSelectedCount();
}

function selectAll() {
    const items = document.querySelectorAll('.fixture-item');
    const allSelected = items.length === Object.keys(selectedFixtures).length;
    items.forEach(item => {
        const id = parseInt(item.dataset.id);
        if (allSelected) {
            delete selectedFixtures[id];
            document.getElementById(`check-${id}`).textContent = '☐';
            item.classList.remove('selected');
        } else {
            selectedFixtures[id] = { id };
            document.getElementById(`check-${id}`).textContent = '✅';
            item.classList.add('selected');
        }
    });
    updateSelectedCount();
}

function updateSelectedCount() {
    const total = Object.keys(selectedFixtures).length + manualMatches.length;
    document.getElementById('selectedCount').textContent = `${total} maç seçildi`;
    document.getElementById('analyzeBtn').disabled = total === 0;
}

// ===== IMAGE UPLOAD =====
function initImageUpload() {
    const btn = document.getElementById('imageUploadBtn');
    const input = document.getElementById('imageUpload');
    btn.addEventListener('click', () => input.click());
    input.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (ev) => {
            document.getElementById('previewImg').src = ev.target.result;
            document.getElementById('imagePreview').style.display = 'block';
        };
        reader.readAsDataURL(file);
        const status = document.getElementById('imageStatus');
        status.textContent = '🔍 Görsel analiz ediliyor...';
        status.style.color = '#888';
        btn.disabled = true;
        try {
            const base64 = await fileToBase64(file);
            const resp = await fetch('/api/parse/image', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ image: base64, media_type: file.type })
            });
            const data = await resp.json();
            if (data.status === 'success' && data.matches.length > 0) {
                data.matches.forEach(m => {
                    const exists = manualMatches.some(x => x.home_team === m.home_team && x.away_team === m.away_team);
                    if (!exists) manualMatches.push(m);
                });
                renderManualList();
                updateSelectedCount();
                status.textContent = `✅ ${data.matches.length} maç eklendi!`;
                status.style.color = '#22c55e';
            } else {
                status.textContent = '❌ Maç bulunamadı, tekrar dene.';
                status.style.color = '#ef4444';
            }
        } catch (err) {
            status.textContent = '❌ Hata: ' + err.message;
            status.style.color = '#ef4444';
        }
        btn.disabled = false;
        input.value = '';
    });
}

function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result.split(',')[1]);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

// ===== MANUAL MATCHES =====
function addManualMatch() {
    const home = document.getElementById('homeTeam').value.trim();
    const away = document.getElementById('awayTeam').value.trim();
    const league = document.getElementById('leagueName').value.trim() || 'Manuel Maç';
    const time = document.getElementById('matchTime').value;
    if (!home || !away) { alert('Ev sahibi ve deplasman takımı gerekli!'); return; }
    let matchDate;
    if (time) {
        const today = new Date();
        const [hours, minutes] = time.split(':');
        today.setHours(parseInt(hours), parseInt(minutes), 0, 0);
        matchDate = today.toISOString();
    } else { matchDate = null; }
    manualMatches.push({ home_team: home, away_team: away, league, date: matchDate });
    document.getElementById('homeTeam').value = '';
    document.getElementById('awayTeam').value = '';
    document.getElementById('leagueName').value = '';
    document.getElementById('matchTime').value = '';
    renderManualList();
    updateSelectedCount();
}

function removeManual(index) {
    manualMatches.splice(index, 1);
    renderManualList();
    updateSelectedCount();
}

function renderManualList() {
    const container = document.getElementById('manualList');
    if (manualMatches.length === 0) { container.innerHTML = ''; return; }
    container.innerHTML = manualMatches.map((m, i) => {
        const timeStr = formatTime(m.date);
        return `<div class="manual-item">
            <span>⚽ ${m.home_team} vs ${m.away_team} <small>(${m.league})</small>${timeStr ? ' 🕐 ' + timeStr : ''}</span>
            <button onclick="removeManual(${i})" class="btn-remove">✕</button>
        </div>`;
    }).join('');
}

// ===== ANALYSIS =====
async function runAnalysis() {
    const btn = document.getElementById('analyzeBtn');
    const statusDiv = document.getElementById('analysisStatus');
    const total = Object.keys(selectedFixtures).length + manualMatches.length;
    btn.disabled = true;
    btn.innerHTML = '⏳ Analiz başlatılıyor...';
    statusDiv.style.display = 'block';
    statusDiv.innerHTML = `
        <div class="status-box">
            <div class="status-spinner"></div>
            <div class="status-text">
                <strong>🔍 ${total} maç analiz ediliyor...</strong>
                <span>Claude AI çalışıyor, yaklaşık ${total * 10} saniye sürer.</span>
                <div class="progress-bar-wrap">
                    <div class="progress-bar-fill" id="progressBar"></div>
                </div>
                <small id="progressText">Başlatılıyor...</small>
            </div>
        </div>`;
    const duration = total * 10000;
    const steps = [10, 25, 40, 55, 70, 85, 95];
    steps.forEach((pct, i) => {
        setTimeout(() => {
            const bar = document.getElementById('progressBar');
            const txt = document.getElementById('progressText');
            if (bar) bar.style.width = pct + '%';
            if (txt) txt.textContent = `🤖 Analiz yapılıyor... (${Math.ceil(i * total / steps.length)}/${total})`;
        }, (duration / steps.length) * i);
    });
    try {
        const resp = await fetch('/api/analyze/selected', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                fixture_ids: Object.keys(selectedFixtures).map(Number),
                manual_matches: manualMatches
            })
        });
        const data = await resp.json();
        if (data.status === 'success') {
            setTimeout(async () => await checkAndReload(statusDiv, btn, total), duration + 5000);
        } else {
            showError(statusDiv, btn, data.message);
        }
    } catch (e) {
        showError(statusDiv, btn, e.message);
    }
}

async function checkAndReload(statusDiv, btn, total) {
    try {
        const res = await fetch('/api/matches/today');
        const matches = await res.json();
        if (matches && matches.length > 0) {
            const bar = document.getElementById('progressBar');
            const txt = document.getElementById('progressText');
            if (bar) bar.style.width = '100%';
            if (txt) txt.textContent = '✅ Analiz tamamlandı!';
            statusDiv.innerHTML = `<div class="status-box success"><span>✅ ${matches.length} maç analiz edildi! Yükleniyor...</span></div>`;
            renderMatches(matches);
            btn.disabled = false;
            btn.innerHTML = '🔍 Seçilenleri Analiz Et';
            statusDiv.style.display = 'none';
        } else {
            setTimeout(() => checkAndReload(statusDiv, btn, total), 15000);
        }
    } catch (e) {
        setTimeout(() => checkAndReload(statusDiv, btn, total), 15000);
    }
}

function showError(statusDiv, btn, message) {
    statusDiv.innerHTML = `<div class="status-box error"><span>❌ Hata: ${message}</span></div>`;
    btn.disabled = false;
    btn.innerHTML = '🔍 Seçilenleri Analiz Et';
}

// ===== TELEGRAM =====
async function sendToTelegram() {
    const btn = document.getElementById('telegramBtn');
    btn.disabled = true;
    btn.innerHTML = '⏳ Gönderiliyor...';
    try {
        const resp = await fetch('/api/telegram/send', { method: 'POST' });
        const data = await resp.json();
        if (data.status === 'success') {
            btn.innerHTML = '✅ Gönderildi!';
            btn.style.background = '#22c55e';
            setTimeout(() => { btn.innerHTML = '📨 Telegram\'a Gönder'; btn.style.background = ''; btn.disabled = false; }, 3000);
        } else {
            btn.innerHTML = '❌ Hata!';
            btn.style.background = '#ef4444';
            alert('Hata: ' + data.message);
            setTimeout(() => { btn.innerHTML = '📨 Telegram\'a Gönder'; btn.style.background = ''; btn.disabled = false; }, 3000);
        }
    } catch (e) {
        btn.innerHTML = '❌ Hata!';
        alert('Hata: ' + e.message);
        btn.disabled = false;
    }
}

// ===== MATCHES =====
async function loadMatches() {
    const container = document.getElementById('matchesContainer');
    try {
        const resp = await fetch('/api/matches/today');
        const matches = await resp.json();
        if (!matches || matches.length === 0) {
            container.innerHTML = `<div class="no-matches"><p>📭 Henüz analiz yapılmadı.</p><p>Sol taraftan maç seçip analiz et.</p></div>`;
            return;
        }
        renderMatches(matches);
    } catch (e) {
        container.innerHTML = `<div class="no-matches"><p>📭 Henüz analiz yapılmadı.</p></div>`;
    }
}

function renderMatches(matches) {
    const container = document.getElementById('matchesContainer');
    if (!matches || matches.length === 0) {
        container.innerHTML = `<div class="no-matches"><p>📭 Henüz analiz yapılmadı.</p></div>`;
        return;
    }
    container.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding:0 4px;">
            <div style="display:flex;gap:8px;">
                <button id="telegramBtn" onclick="sendToTelegram()" style="padding:8px 18px;border-radius:8px;border:none;background:#2563eb;color:#fff;font-size:13px;cursor:pointer;font-family:inherit;font-weight:600;">
                    📨 Telegram'a Gönder
                </button>
                <button id="couponBtn" onclick="generateCoupon()" style="padding:8px 18px;border-radius:8px;border:none;background:#7c3aed;color:#fff;font-size:13px;cursor:pointer;font-family:inherit;font-weight:600;">
                    🎫 Kupon Oluştur
                </button>
            </div>
            <button onclick="clearAllMatches()" style="padding:6px 14px;border-radius:8px;border:1px solid #ef4444;background:transparent;color:#ef4444;font-size:12px;cursor:pointer;font-family:inherit;">
                🗑️ Tümünü Sil
            </button>
        </div>
        <div id="matchCardsList">
            ${matches.map(m => createMatchCard(m)).join('')}
        </div>`;
}

function createMatchCard(match) {
    const prediction = match.prediction_1x2 || '?';
    const confidence = match.confidence || 'Orta';
    const confidenceClass = {
        'Çok Yüksek': 'confidence-very-high',
        'Yüksek':     'confidence-high',
        'Orta':       'confidence-medium',
        'Düşük':      'confidence-low',
    }[confidence] || 'confidence-medium';
    const cardClass = cardConfidenceClass(confidence);
    let reasoning = [];
    try { reasoning = JSON.parse(match.reasoning || '[]'); } catch (e) {}
    const timeStr = formatTime(match.match_time);
    const homeLogo = teamLogoHtml(match.home_team);
    const awayLogo = teamLogoHtml(match.away_team);
    const winner = getWinnerLabel(prediction, match.home_team, match.away_team);
    const over25 = match.over25_pct || 0;
    const ht2g   = match.ht2g_pct   || 0;
    const btts   = match.btts_pct   || 0;
    const trendHtml = buildTrendHtml(match);

    return `
        <div class="match-card ${cardClass}" id="matchcard-${match.id}">
            <div style="display:flex;justify-content:flex-end;margin-bottom:4px;">
                <button onclick="deleteMatch(${match.id})" style="background:transparent;border:none;color:#444;font-size:15px;cursor:pointer;padding:0;line-height:1;" title="Sil">🗑️</button>
            </div>
            <div class="match-header">
                <span class="league-badge">⚽ ${match.league || 'Bilinmeyen Lig'}</span>
                ${timeStr ? `<span class="match-time">${timeStr}</span>` : ''}
            </div>
            <div class="teams">
                <div class="team home-team">
                    ${homeLogo}
                    <span class="team-name">${match.home_team}</span>
                    <span class="team-form">${match.home_form || 'N/A'}</span>
                </div>
                <div class="vs-badge prediction-${prediction.toLowerCase()}">
                    <img src="/static/img/logo.png" alt="GL" onerror="this.parentElement.innerHTML='${prediction}'">
                </div>
                <div class="team away-team">
                    ${awayLogo}
                    <span class="team-name">${match.away_team}</span>
                    <span class="team-form">${match.away_form || 'N/A'}</span>
                </div>
            </div>
            <div class="stats-grid">
                <div class="stat-box">
                    <span class="stat-label">🎯 2.5 GOL ÜSTÜ</span>
                    <span class="stat-value ${pctClass(over25)}">${over25}%</span>
                    <div class="stat-bar"><div class="stat-fill ${barClass(over25)}" style="width:${over25}%"></div></div>
                </div>
                <div class="stat-box">
                    <span class="stat-label">⚽ İY 0.5 ÜST</span>
                    <span class="stat-value ${pctClass(ht2g)}">${ht2g}%</span>
                    <div class="stat-bar"><div class="stat-fill ${barClass(ht2g)}" style="width:${ht2g}%"></div></div>
                </div>
                <div class="stat-box">
                    <span class="stat-label">🔁 KG VAR (BTTS)</span>
                    <span class="stat-value ${pctClass(btts)}">${btts}%</span>
                    <div class="stat-bar"><div class="stat-fill ${barClass(btts)}" style="width:${btts}%"></div></div>
                </div>
                <div class="stat-box">
                    <span class="stat-label">📊 GOL ORT.</span>
                    <span class="stat-value">${match.home_goals_avg || 0} / ${match.away_goals_avg || 0}</span>
                </div>
            </div>
            <div class="prediction-row">
                <div class="predicted-score">
                    <span class="score-label">${winner.icon} KAZANAN TAHMİNİ</span>
                    <span class="score-value">${winner.label}</span>
                </div>
                <span class="confidence-badge ${confidenceClass}">Analiz Güveni: ${confidence}</span>
            </div>
            ${trendHtml}
            ${reasoning.length > 0 ? `
            <div class="reasoning">
                <span class="reasoning-label">🧠 ANALİZ GEREKÇESİ</span>
                ${reasoning.map(r => `<p class="reasoning-item">→ ${r}</p>`).join('')}
            </div>` : ''}
        </div>`;
}

async function deleteMatch(id) {
    if (!confirm('Bu analizi silmek istediğine emin misin?')) return;
    try {
        await fetch(`/api/matches/delete/${id}`, { method: 'DELETE' });
        document.getElementById(`matchcard-${id}`)?.remove();
        const remaining = document.querySelectorAll('.match-card');
        if (remaining.length === 0) {
            document.getElementById('matchesContainer').innerHTML = `<div class="no-matches"><p>📭 Henüz analiz yapılmadı.</p></div>`;
        }
    } catch (e) { alert('Silme hatası: ' + e.message); }
}

async function clearAllMatches() {
    if (!confirm('Bugünün tüm analizleri silinecek. Emin misin?')) return;
    try {
        await fetch('/api/matches/clear', { method: 'DELETE' });
        document.getElementById('matchesContainer').innerHTML = `<div class="no-matches"><p>📭 Henüz analiz yapılmadı.</p></div>`;
    } catch (e) { alert('Silme hatası: ' + e.message); }
}

function formatTime(dateStr) {
    if (!dateStr) return '';
    try {
        const d = new Date(dateStr);
        if (isNaN(d.getTime())) return '';
        const timeStr = d.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Istanbul' });
        if (timeStr === '00:00' || timeStr === '03:00') return '';
        return timeStr;
    } catch { return ''; }
}

// ===== INIT =====
document.addEventListener('DOMContentLoaded', () => {
    loadFixtures();
    loadMatches();
    document.getElementById('analyzeBtn').addEventListener('click', runAnalysis);
    document.getElementById('refreshFixtures').addEventListener('click', loadFixtures);
    document.getElementById('selectAll').addEventListener('click', selectAll);
    document.getElementById('addManual').addEventListener('click', addManualMatch);
    initImageUpload();
});
