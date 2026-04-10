# Analiz Sistemi — Kod Bazlı Detaylı Rapor

---

## 1. TARAF ANALİZİ (`prediction_1x2` + `confidence`)

### Kullanılan Veriler

| Veri | Kaynak | Değişken |
|---|---|---|
| Bahisçi oranları | CSV | `odds_home`, `odds_away` |
| Güncel puan/maç ortalaması | CSV | `current_home_ppg`, `current_away_ppg` |
| Ev/deplasman ligdeki sırası | standing API | `home_position` (evdeki), `away_position` (deplasmandaki) |
| H2H galibiyet dağılımı | football-data.org | `h2h_fd.home_wins`, `.away_wins` |

**xG (`home_xg`, `away_xg`) taraf kararını ETKİLEMEZ.** Prompt'ta açıkça yazılı: *"xG verisi SADECE over/under ve BTTS tahmininde kullanılır."*

### Karar Zinciri (Prompt İçinde)

```
1. Bahisçi oranı → implied probability
   home_implied = 1/odds_home * 100
   away_implied = 1/odds_away * 100
   fark > 15% → "net favori"
   fark 5-15% → "hafif favori"
   fark < 5%  → "dengeli"

2. Güncel PPG
   ppg_diff = current_home_ppg - current_away_ppg
   > +0.5  → ev sahibi üstün
   < -0.5  → deplasman üstün
   ara     → dengeli

3. Ev/Deplasman Sırası
   fark = away_dep_sirasi - home_ev_sirasi
   ≥ +4 → ev sahibi bu sahada üstün
   ≤ -4 → deplasman bu sahada üstün

4. H2H
   home_wins > away_wins + 1 → ev üstünlüğü (teyit sinyali)
```

Kombinasyon kuralları prompta yazılı: bahisçi + PPG aynı yöndeyse o tarafı seç; çelişiyorsa bahisçiye ağırlık ver; tümü çelişkili → "X" ver.

### Güven — AI Yanıtı DEĞİL, Kod Override Eder

AI bir güven seviyesi döndürse de **`analyze_with_claude` bunu hesapladıktan sonra üzerine yazar** (satır 1508-1543):

```python
three_aligned = odds_side == ppg_favors == venue_rank_favors  (ve hepsi 'X' değil)
two_aligned   = odds_side == ppg_favors                       (venue_rank eksik olsa bile)

if three_aligned or two_aligned → confidence = 'Yüksek'
elif odds_ppg_conflict           → confidence = 'Düşük'
else                             → confidence = 'Orta'
```

Ek kısıtlar:
- `Çok Yüksek` → her zaman `Yüksek`'e indirilir (kod seviyesinde yasaklı)
- Kupa/hazırlık maçı → maksimum `Orta`

**Özet:** Güven seviyesi yalnızca `(bahisçi oranı) × (güncel PPG) × (ev/dep sırası)` üçlüsünün hizalamasına göre belirlenir. Form, H2H, xG güveni değiştirmez.

---

## 2. 2.5 ÜST (`over25_pct`)

### Nasıl Hesaplanıyor?

**Adım 1 — Prompt kısıtları (AI çağrısından önce belirlenir)**

CSV `over25_avg` varsa:
```
Baz değer: over25_avg
İzin verilen aralık: [over25_avg - 10, over25_avg + 10]
Her iki takım 3+ gol avg → +10'a kadar artır
Her iki takım 1'den az gol avg → -10'a kadar düşür
```

Şut istatistikleri varsa ek kural:
```
toplam_isabetli_şut ≥ 10 → over25 minimum %55 olmalı
toplam_isabetli_şut ≤ 5  → over25 maksimum %50 olmalı
```

H2H varsa ek ipucu:
```
h2h_avg_goals ≥ 3.0 → over25/btts +5'e kadar artır
h2h_avg_goals < 1.8 → over25/btts -5'e kadar düşür
```

CSV yoksa AI serbest hesaplar.

**Adım 2 — AI yanıtı**

Claude/Grok/Gemini prompt kurallarına göre bir değer üretir.

**Adım 3 — Clamp (AI yanıtından sonra, kod zorlar)**

```python
over25_pct = clamp(ai_over25, base=over25_avg, margin=10)
# AI ±10 dışına çıktıysa sınıra çeker
```

**Adım 4 — Şut bazlı düzeltme (clamp'ten sonra)**

```python
if pressure == 0 and over25 > 58:  # düşük şut baskısı
    over25 -= min(6, over25 - 52)
if pressure == 3 and over25 < 52:  # yüksek şut baskısı
    over25 += min(6, 58 - over25)
```

**Baskı skoru:**
```
total_on ≥ 10 ve avg_acc ≥ 38% → pressure = 3 (yüksek)
total_on ≥ 8  veya avg_acc ≥ 35% → pressure = 2
total_on ≥ 5  veya avg_acc ≥ 28% → pressure = 1
altı → pressure = 0 (düşük)
```

**Tutarlılık kontrolü:** `btts > 60` ise `over25` minimum `45`'e zorunlu çekilir (btts yüksekse toplam gol düşük olamaz).

**Veri önceliği:** `over25_avg` (CSV) > form trendi > H2H avg_goals > serbest AI tahmini

---

## 3. KG VAR (`btts_pct`)

### Kullanılan Veriler ve Sıra

**Prompt baz değer:** CSV `btts_avg` ±8 aralık

**Clamp:** `btts_pct = clamp(ai_btts, base=btts_avg, margin=8)`

**Şut bazlı düzeltme:**
```python
if her_iki_takım_isabetli ≥ 4.5 and btts < 60:
    btts += min(5, 65 - btts)   # yüksek şut → karşılıklı gol olası

if her_iki_takım_isabetli ≤ 2.5 and btts > 45:
    btts -= min(5, btts - 40)   # düşük şut → btts indir
```

**xG-BTTS tutarlılık kontrolü:**
```python
if home_xg ≥ 1.0 AND away_xg ≥ 1.0 AND btts < 50:
    btts = max(btts, 50)   # her iki takım tehlikeli → min %50
```

**Tutarlılık kuralları (prompt — AI zorlanıyor):**
```
btts > 60  → over25 min 45    (her iki takım gol atıyorsa toplam gol az olamaz)
btts < 35  → over25 max 55    (kimse atmıyorsa toplam da yüksek olamaz)
```

**Veri önceliği:** `btts_avg` (CSV) > şut istatistikleri > xG tutarlılık > AI tahmini

---

## 4. İY 0.5 ÜST (`ht2g_pct`)

### Nasıl Hesaplanıyor?

CSV `ht_over05_avg` varsa en sıkı clamp uygulanır:

**Prompt:**
```
Baz değer: ht_over05_avg
İzin verilen aralık: [ht_over05_avg - 5, ht_over05_avg + 5]
"İlk yarı istatistiği en sabit veridir — bu aralığın dışına çıkma"
```

**Clamp (±5, en dar marj):**
```python
ht2g_pct = clamp(ai_ht2g, base=ht_over05_avg, margin=5)
```

**Tutarlılık (prompt):**
```
over25 > 70 → ht2g_pct minimum 60
  (Golcü maçta ilk yarı da golsüz olmaz)
```

**Şut bazlı override yok** — ht2g için şut düzeltmesi uygulanmaz, yalnızca CSV clamp geçerlidir.

**Veri önceliği:** `ht_over05_avg` (CSV) ±5 içinde AI'ın tahmini → en az dış girdi alan metriktir.

---

## 5. SKOR TAHMİNİ

### Genel Akış

```
[AI skoru] → _is_score_valid? → Geçerliyse kullan
                              → Geçersizse:
                                [Poisson skoru] → _is_score_valid? → Geçerliyse kullan
                                                                    → Geçersizse:
                                                                      [CSV kural tabanlı skor]
```

### Poisson Nasıl Çalışıyor?

**Adım 1-2 — Ev/deplasman venue istatistikleri (son 5 maç)**
```
h_attack  = ev sahibinin evdeki gol ortalaması (yoksa genel, yoksa 1.55)
h_defense = ev sahibine evde yenilen gol ortalaması
a_attack  = deplasman takımının deplasmandaki gol ortalaması
a_defense = deplasmanın deplasmanda yendiği gol ortalaması
```

**Adım 3 — Beklenen gol (xG)**
```
home_xg = (h_attack + a_defense) / 2
away_xg = (a_attack + h_defense) / 2
```

**Adım 4 — H2H karıştırma (%20 ağırlık)**
```
Raw liste varsa:
  home_xg = home_xg * 0.8 + h2h_home_avg * 0.2

Raw liste yoksa ama h2h_fd varsa (≥3 maç):
  blended_total = mevcut_toplam * 0.8 + h2h_fd.avg_goals * 0.2
  home_xg *= scale, away_xg *= scale  (oran korunur)
```

**Adım 5 — CSV blend (%45 ağırlık)**
```
Hedef = avg_goals (CSV)  veya  over25_avg / 24.5 + 0.5  (türetilmiş)

blended_total = mevcut_toplam * 0.55 + hedef * 0.45
home_xg *= scale, away_xg *= scale
```

**Adım 6 — Poisson modu**
```python
for h in range(6):
    for a in range(6):
        prob = P(home_xg, h) * P(away_xg, a)   # e^(-λ) * λ^k / k!
        if prob > best: best_score = (h, a)
```

**Matematiksel sınır:** `home_xg ≈ away_xg < 2.0` iken **her zaman 1-1 modu** çıkar. Bu yüzden Poisson skoru `_is_score_valid` ile doğrulanır.

### `_is_score_valid` Eşik Değerleri

```
over25 > 70  →  toplam gol < 3 ise GEÇERSIZ  (1-1 reddedilir)
over25 < 40  →  toplam gol > 2 ise GEÇERSIZ
btts  < 40   →  her iki takım gol attıysa GEÇERSIZ
btts  > 65   →  bir takım 0 attıysa GEÇERSIZ
over35 ≥ 55  →  toplam gol < 4 ise GEÇERSIZ
over45 ≥ 35  →  toplam gol < 5 ise GEÇERSIZ
prediction=1 →  ev_gol ≤ dep_gol ise GEÇERSIZ
prediction=X →  skorlar eşit değilse GEÇERSIZ
toplam > 5   →  her zaman GEÇERSIZ
```

### CSV Kural Tabanlı Fallback (`_pick_score_by_csv_rules`)

Poisson geçersiz kalırsa öncelik sırası:

```
1. over45_avg ≥ 35%     → 5+ gollü skor (3-2, 4-1 vb.)
2. over35_avg ≥ 55%     → 4+ gollü skor (3-1, 2-2 vb.)
3. Şut baskısı (pressure ≥ 2)  → yukarı çek
4. over25 ≥ 70%         → 3+ gollü skor (2-1, 3-0, 2-2)
   [X + over25≥70%]    → her zaman 2-2 (3 gollü eşitlik imkânsız)
5. over35 45-54%         → 3 gol bandı
6. over35 < 45%          → 2 gol bandı (2-1, 2-0, 1-2)
7. over25 ≤ 35%          → düşük gol (1-0, 0-1, 0-0)
8. Varsayılan            → pred=1: 2-0/2-1 | pred=2: 0-2/1-2 | X: 1-1
```

---

## Veri Yoksa Ne Olur?

| Durum | Etki |
|---|---|
| CSV yok | AI serbest hesaplar; clamp yok; fallback skor kurallar daha geniş aralıkta çalışır |
| Maç verisi yok (yeni takım) | Poisson lig ortalamasına (ev:1.55, dep:1.15) düşer → genellikle 1-1 → `_is_score_valid`'e bırakır |
| H2H yok | Poisson %20 H2H ağırlığını atlar, CSV blend devreye girer |
| Standing yok | `venue_rank_favors=None` → güven hesabı iki etkenle çalışır (odds + PPG) |
| Şut istatistiği yok | Pressure=None → şut düzeltmeleri atlanır |
