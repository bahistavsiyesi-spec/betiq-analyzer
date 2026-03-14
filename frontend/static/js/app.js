const API_BASE = '';
let selectedFixtures = {};
let manualMatches = [];

// ─── Takım ID tablosu (football-data.org crest URL'leri için) ────────────────
const TEAM_IDS = {
    // Almanya
    'Bayern': 5, 'Dortmund': 4, 'Leverkusen': 3, 'Leipzig': 721,
    'Frankfurt': 19, 'Stuttgart': 10, 'Freiburg': 17, 'Hoffenheim': 2,
    'Bremen': 12, 'Wolfsburg': 11, 'Gladbach': 18, 'Augsburg': 16,
    'Union Berlin': 28, 'Bochum': 20, 'Mainz': 15, 'St. Pauli': 20,
    'Kiel': 44, 'Heidenheim': 44, 'Hamburg': 7, 'Hannover': 30,
    'Karlsruhe': 24, 'Schalke': 6, 'Darmstadt': 36, 'Köln': 1,
    'Hertha': 27, 'Düsseldorf': 45, 'Nürnberg': 7,
    // İngiltere
    'Arsenal': 57, 'Aston Villa': 58, 'Bournemouth': 1044,
    'Brentford': 402, 'Brighton': 397, 'Chelsea': 61,
    'Crystal Palace': 354, 'Everton': 62, 'Fulham': 63,
    'Ipswich': 349, 'Leicester': 338, 'Liverpool': 64,
    'Manchester City': 65, 'Manchester United': 66,
    'Newcastle': 67, 'Nottingham Forest': 351,
    'Southampton': 340, 'Tottenham': 73,
    'West Ham': 563, 'Wolverhampton': 76,
    'Burnley': 328, 'Leeds': 341, 'Sunderland': 71,
    'Coventry': 1076, 'Middlesbrough': 343,
    // İspanya
    'Barcelona': 81, 'Real Madrid': 86, 'Atlético Madrid': 78,
    'Athletic Club': 77, 'Real Sociedad': 92, 'Villarreal': 95,
    'Real Betis': 90, 'Valencia': 94, 'Girona': 298,
    'Celta Vigo': 558, 'Sevilla': 559, 'Osasuna': 79,
    'Getafe': 82, 'Rayo Vallecano': 88, 'Mallorca': 89,
    'Alavés': 263, 'Espanyol': 80, 'Las Palmas': 275,
    'Leganés': 745, 'Valladolid': 250,
    // İtalya
    'AC Milan': 98, 'Inter': 108, 'Juventus': 109,
    'Napoli': 113, 'Atalanta': 102, 'Roma': 100,
    'Lazio': 110, 'Fiorentina': 99, 'Bologna': 103,
    'Torino': 586, 'Udinese': 115, 'Genoa': 107,
    'Cagliari': 104, 'Lecce': 5890, 'Verona': 450,
    'Parma': 112, 'Como': 7397, 'Monza': 5911,
};

function getTeamLogoUrl(teamName) {
    // Direkt eşleşme
    if (TEAM_IDS[teamName]) {
        return `https://crests.football-data.org/${TEAM_IDS[teamName]}.png`;
    }
    // Kısmi eşleşme
    const lower = teamName.toLowerCase();
    for (const [key, id] of Object.entries(TEAM_IDS)) {
        if (key.toLowerCase().includes(lower) || lower.includes(key.toLowerCase())) {
            return `https://crests.football-data.org/${id}.png`;
        }
    }
    return null;
}

function teamLogoHtml(teamName) {
    const url = getTeamLogoUrl(teamName);
    if (!url) return '';
    return `<img src="${url}" alt="${teamName}" 
        style="width:24px; height:24px; object-fit:contain; border-radius:4px; margin-bottom:4px;"
        onerror="this.style.display='none'">`;
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
        return `
        <div class="manual-item">
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
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; padding:0 4px;">
            <button id="telegramBtn" onclick="sendToTelegram()" style="padding:8px 18px; border-radius:8px; border:none; background:#2563eb; color:#fff; font-size:13px; cursor:pointer; font-family:inherit; font-weight:600;">
                📨 Telegram'a Gönder
            </button>
            <button onclick="clearAllMatches()" style="padding:6px 14px; border-radius:8px; border:1px solid #ef4444; background:transparent; color:#ef4444; font-size:12px; cursor:pointer; font-family:inherit;">
                🗑️ Tümünü Sil
            </button>
        </div>
        <div id="matchCardsList">
            ${matches.map(m => createMatchCard(m)).join('')}
        </div>`;
}

function createMatchCard(match) {
    const prediction = match.prediction_1x2 || '?';
    const confidenceClass = {
        'Çok Yüksek': 'confidence-very-high',
        'Yüksek': 'confidence-high',
        'Orta': 'confidence-medium',
        'Düşük': 'confidence-low'
    }[match.confidence] || 'confidence-medium';

    let reasoning = [];
    try { reasoning = JSON.parse(match.reasoning || '[]'); } catch (e) {}

    const timeStr = formatTime(match.match_time);
    const homeLogo = teamLogoHtml(match.home_team);
    const awayLogo = teamLogoHtml(match.away_team);

    return `
        <div class="match-card" id="matchcard-${match.id}">
            <div style="display:flex; justify-content:flex-end; margin-bottom:4px;">
                <button onclick="deleteMatch(${match.id})" style="background:transparent; border:none; color:#444; font-size:15px; cursor:pointer; padding:0; line-height:1;" title="Sil">🗑️</button>
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
                    <span class="stat-value highlight-blue">${match.over25_pct}%</span>
                    <div class="stat-bar"><div class="stat-fill blue" style="width:${match.over25_pct}%"></div></div>
                </div>
                <div class="stat-box">
                    <span class="stat-label">⚽ İY 0.5 ÜST</span>
                    <span class="stat-value">${match.ht2g_pct}%</span>
                    <div class="stat-bar"><div class="stat-fill" style="width:${match.ht2g_pct}%"></div></div>
                </div>
                <div class="stat-box">
                    <span class="stat-label">🔁 KG VAR (BTTS)</span>
                    <span class="stat-value highlight-yellow">${match.btts_pct}%</span>
                    <div class="stat-bar"><div class="stat-fill yellow" style="width:${match.btts_pct}%"></div></div>
                </div>
                <div class="stat-box">
                    <span class="stat-label">📊 GOL ORT.</span>
                    <span class="stat-value">${match.home_goals_avg || 0} / ${match.away_goals_avg || 0}</span>
                </div>
            </div>
            <div class="prediction-row">
                <div class="predicted-score">
                    <span class="score-label">🎯 TAHMİNİ SKOR</span>
                    <span class="score-value">${match.predicted_score || '?-?'}</span>
                </div>
                <span class="confidence-badge ${confidenceClass}">${match.confidence || 'Orta'}</span>
            </div>
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
