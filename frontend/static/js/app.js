const API_BASE = '';

async function runAnalysis() {
    const btn = document.getElementById('analyzeBtn');
    const statusDiv = document.getElementById('analysisStatus');
    
    btn.disabled = true;
    btn.innerHTML = '⏳ Analiz başlatılıyor...';
    statusDiv.style.display = 'block';
    statusDiv.innerHTML = `
        <div class="status-box">
            <div class="status-spinner"></div>
            <div class="status-text">
                <strong>🔍 Analiz yapılıyor...</strong>
                <span>Groq AI maçları inceliyor, yaklaşık 2 dakika sürer.</span>
                <div class="progress-bar-wrap">
                    <div class="progress-bar-fill" id="progressBar"></div>
                </div>
                <small id="progressText">Maçlar hazırlanıyor...</small>
            </div>
        </div>
    `;

    // Progress animasyonu
    let progress = 0;
    const steps = [
        { pct: 10, text: '📡 Bugünkü maçlar çekiliyor...', time: 1000 },
        { pct: 25, text: '🔍 Maçlar puanlanıyor...', time: 3000 },
        { pct: 40, text: '🤖 Groq AI analiz yapıyor... (1/10)', time: 8000 },
        { pct: 55, text: '🤖 Groq AI analiz yapıyor... (3/10)', time: 16000 },
        { pct: 70, text: '🤖 Groq AI analiz yapıyor... (6/10)', time: 24000 },
        { pct: 85, text: '🤖 Groq AI analiz yapıyor... (9/10)', time: 32000 },
        { pct: 95, text: '📱 Telegram\'a gönderiliyor...', time: 40000 },
    ];

    steps.forEach(step => {
        setTimeout(() => {
            const bar = document.getElementById('progressBar');
            const txt = document.getElementById('progressText');
            if (bar) bar.style.width = step.pct + '%';
            if (txt) txt.textContent = step.text;
        }, step.time);
    });

    try {
        const response = await fetch(`${API_BASE}/api/analyze/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const data = await response.json();

        if (data.status === 'success') {
            // 90 saniye sonra kontrol et
            setTimeout(async () => {
                await checkAndReload(statusDiv, btn);
            }, 90000);
        } else {
            showError(statusDiv, btn, data.message);
        }
    } catch (error) {
        showError(statusDiv, btn, error.message);
    }
}

async function checkAndReload(statusDiv, btn) {
    try {
        const res = await fetch('/api/matches/today');
        const matches = await res.json();
        
        if (matches && matches.length > 0) {
            const bar = document.getElementById('progressBar');
            const txt = document.getElementById('progressText');
            if (bar) bar.style.width = '100%';
            if (txt) txt.textContent = '✅ Analiz tamamlandı!';
            
            statusDiv.innerHTML = `
                <div class="status-box success">
                    <span>✅ ${matches.length} maç analiz edildi! Sayfa yenileniyor...</span>
                </div>
            `;
            setTimeout(() => location.reload(), 2000);
        } else {
            // Henüz bitmemiş, 30 sn daha bekle
            setTimeout(async () => {
                await checkAndReload(statusDiv, btn);
            }, 30000);
        }
    } catch (e) {
        setTimeout(() => location.reload(), 3000);
    }
}

function showError(statusDiv, btn, message) {
    statusDiv.innerHTML = `
        <div class="status-box error">
            <span>❌ Hata: ${message}</span>
        </div>
    `;
    btn.disabled = false;
    btn.innerHTML = '🔍 Şimdi Analiz Yap';
}

async function loadMatches() {
    try {
        const response = await fetch(`${API_BASE}/api/matches/today`);
        const matches = await response.json();
        const container = document.getElementById('matchesContainer');
        
        if (!matches || matches.length === 0) {
            container.innerHTML = `
                <div class="no-matches">
                    <p>📭 Bugün henüz analiz yapılmadı.</p>
                    <p>Analiz yapmak için butona basın.</p>
                </div>
            `;
            return;
        }
        
        container.innerHTML = matches.map(match => createMatchCard(match)).join('');
    } catch (error) {
        console.error('Error loading matches:', error);
    }
}

function createMatchCard(match) {
    const prediction = match.prediction_1x2 || '?';
    const predictionText = {
        '1': `1 (${match.home_team})`,
        'X': 'X (Beraberlik)',
        '2': `2 (${match.away_team})`
    }[prediction] || prediction;

    const confidenceClass = {
        'Çok Yüksek': 'confidence-very-high',
        'Yüksek': 'confidence-high',
        'Orta': 'confidence-medium',
        'Düşük': 'confidence-low'
    }[match.confidence] || 'confidence-medium';

    let reasoning = [];
    try {
        reasoning = JSON.parse(match.reasoning || '[]');
    } catch (e) {
        reasoning = match.reasoning ? [match.reasoning] : [];
    }

    const matchTime = match.match_time ? formatTime(match.match_time) : '--:--';

    return `
        <div class="match-card">
            <div class="match-header">
                <span class="league-badge">⚽ ${match.league || 'Bilinmeyen Lig'}</span>
                <span class="match-time">${matchTime}</span>
            </div>
            <div class="teams">
                <div class="team home-team">
                    <span class="team-name">${match.home_team}</span>
                    <span class="team-form">${match.home_form || 'N/A'}</span>
                </div>
                <div class="vs-badge prediction-${prediction.toLowerCase()}">
                    ${prediction}
                </div>
                <div class="team away-team">
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
                    <span class="stat-label">⚽ İY 2 GOL</span>
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
        </div>
    `;
}

function formatTime(dateStr) {
    try {
        const d = new Date(dateStr);
        return d.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Istanbul' });
    } catch {
        return dateStr ? dateStr.substring(11, 16) : '--:--';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    loadMatches();
    const btn = document.getElementById('analyzeBtn');
    if (btn) btn.addEventListener('click', runAnalysis);
});
