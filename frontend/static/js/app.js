const CONF_LABELS = {
  'Çok Yüksek': 'conf-very-high',
  'Yüksek': 'conf-high',
  'Orta': 'conf-medium',
  'Düşük': 'conf-low'
};

function formatDate(str) {
  if (!str) return '';
  const d = new Date(str);
  return d.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' });
}

function formatTodayDate() {
  return new Date().toLocaleDateString('tr-TR', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
}

function colorForm(form) {
  if (!form) return '<span class="text-muted">-</span>';
  return form.split('').map(c => `<span class="form-${c}">${c}</span>`).join('');
}

function getPredClass(pred) {
  if (pred === '1') return 'pred-1';
  if (pred === 'X') return 'pred-x';
  if (pred === '2') return 'pred-2';
  return '';
}

function getBarColor(pct) {
  if (pct >= 70) return '#00ff80';
  if (pct >= 50) return '#00c4ff';
  if (pct >= 35) return '#ffd166';
  return '#5a6878';
}

function parseReasoning(raw) {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [raw];
  } catch {
    return [raw];
  }
}

function buildCard(m, index) {
  const confClass = CONF_LABELS[m.confidence] || 'conf-medium';
  const over25 = Math.round(m.over25_pct || 0);
  const ht2g = Math.round(m.ht2g_pct || 0);
  const btts = Math.round(m.btts_pct || 0);
  const reasoning = parseReasoning(m.reasoning);
  const matchTime = formatDate(m.match_time);
  const delay = index * 0.06;

  return `
    <div class="match-card ${confClass}" style="animation-delay:${delay}s">
      <div class="card-header">
        <div class="league-row">
          <span class="league-name">⚽ ${m.league || 'Bilinmeyen Lig'}</span>
          <span class="match-time mono">${matchTime || '--:--'}</span>
        </div>
        <div class="teams-row">
          <div class="team-info">
            <div class="team-name">${m.home_team}</div>
            <div class="team-form">${colorForm(m.home_form)}</div>
          </div>
          <div class="vs-block">
            <div class="vs-text">VS</div>
            <div class="prediction-badge ${getPredClass(m.prediction_1x2)}">${m.prediction_1x2 || '?'}</div>
          </div>
          <div class="team-info away">
            <div class="team-name">${m.away_team}</div>
            <div class="team-form">${colorForm(m.away_form)}</div>
          </div>
        </div>
      </div>

      <div class="stats-grid">
        <div class="stat-item">
          <div class="stat-label">📈 2.5 Gol Üstü</div>
          <div class="stat-value" style="color:${getBarColor(over25)}">${over25}%</div>
          <div class="stat-bar"><div class="stat-bar-fill" style="width:${over25}%;background:${getBarColor(over25)}"></div></div>
        </div>
        <div class="stat-item">
          <div class="stat-label">⚽ İY 2 Gol</div>
          <div class="stat-value" style="color:${getBarColor(ht2g)}">${ht2g}%</div>
          <div class="stat-bar"><div class="stat-bar-fill" style="width:${ht2g}%;background:${getBarColor(ht2g)}"></div></div>
        </div>
        <div class="stat-item">
          <div class="stat-label">🔁 KG Var (BTTS)</div>
          <div class="stat-value" style="color:${getBarColor(btts)}">${btts}%</div>
          <div class="stat-bar"><div class="stat-bar-fill" style="width:${btts}%;background:${getBarColor(btts)}"></div></div>
        </div>
        <div class="stat-item">
          <div class="stat-label">📊 Gol Ort.</div>
          <div class="stat-value">${Number(m.home_goals_avg||0).toFixed(1)} / ${Number(m.away_goals_avg||0).toFixed(1)}</div>
          <div class="stat-bar"><div class="stat-bar-fill" style="width:${Math.min(100,(m.home_goals_avg+m.away_goals_avg)/4*100)}%;background:#c084fc"></div></div>
        </div>
      </div>

      <div class="score-row">
        <div>
          <div class="score-label">🎯 Tahmini Skor</div>
          <div class="score-tag">${m.predicted_score || '?-?'}</div>
        </div>
        <div class="confidence-tag">${m.confidence || 'Orta'}</div>
      </div>

      ${reasoning.length > 0 ? `
      <div class="reasoning-section">
        <div class="reasoning-title">🧠 Analiz Gerekçesi</div>
        <ul class="reasoning-list">
          ${reasoning.map(r => `<li>${r}</li>`).join('')}
        </ul>
      </div>` : ''}
    </div>
  `;
}

function updateHeroStats(matches) {
  document.getElementById('total-matches').textContent = matches.length;
  const highConf = matches.filter(m => m.confidence === 'Yüksek' || m.confidence === 'Çok Yüksek').length;
  document.getElementById('high-conf').textContent = highConf;
  const avgO25 = matches.length
    ? Math.round(matches.reduce((s, m) => s + (m.over25_pct || 0), 0) / matches.length)
    : 0;
  document.getElementById('avg-over25').textContent = avgO25 + '%';
}

async function loadMatches() {
  try {
    const res = await fetch('/api/matches/today');
    const matches = await res.json();
    document.getElementById('loading').style.display = 'none';
    const container = document.getElementById('matches-container');
    if (!matches || matches.length === 0) {
      document.getElementById('empty-state').style.display = 'block';
      return;
    }
    document.getElementById('empty-state').style.display = 'none';
    container.innerHTML = matches.map((m, i) => buildCard(m, i)).join('');
    updateHeroStats(matches);
  } catch (e) {
    document.getElementById('loading').innerHTML = '<p style="color:var(--text-muted)">Veriler yüklenirken hata oluştu.</p>';
  }
}

async function refreshAnalysis() {
  const icon = document.getElementById('refresh-icon');
  icon.style.animation = 'spin .5s linear infinite';
  await loadMatches();
  icon.style.animation = '';
  showToast('Analizler güncellendi ✓');
}

async function triggerAnalysis() {
  showToast('Analiz başlatılıyor...');
  try {
    const res = await fetch('/api/analyze/run', { method: 'POST' });
    const data = await res.json();
    showToast(data.message);
    setTimeout(loadMatches, 2000);
  } catch {
    showToast('Hata oluştu');
  }
}

function showToast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3000);
}

document.getElementById('current-date').textContent = formatTodayDate();
loadMatches();
setInterval(loadMatches, 5 * 60 * 1000);
