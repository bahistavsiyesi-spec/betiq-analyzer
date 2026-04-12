import psycopg2, psycopg2.extras, os, sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

db_url = os.environ.get('DATABASE_URL', '')
if not db_url:
    print("HATA: DATABASE_URL tanimli degil.")
    print("Kullanim: DATABASE_URL='postgresql://...' python3 query_calibration.py")
    sys.exit(1)

conn = psycopg2.connect(db_url, connect_timeout=5)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

print("\n=== 2.5 UST - Kumülatif (esik ve uzeri) ===")
print(f"{'Esik':<12} | {'Mac Sayisi':>10} | {'Dogru':>7} | {'Basari':>9}")
print("-" * 48)

for t in [65, 70, 75, 80]:
    cur.execute('''
        SELECT COUNT(*) as total, SUM(r.over25_correct) as correct
        FROM analyses a
        JOIN match_results r ON a.id = r.analysis_id
        WHERE a.over25_pct >= %s
    ''', (t,))
    row = cur.fetchone()
    total = row['total'] or 0
    correct = int(row['correct'] or 0)
    pct = round(correct / total * 100, 1) if total > 0 else 0
    print(f">= {t}%       | {total:>10} | {correct:>7} | {pct:>8}%")

print("\n=== 2.5 UST - Aralik Bazli Segmentler ===")
print(f"{'Aralik':<12} | {'Mac':>6} | {'Dogru':>7} | {'Basari':>9}")
print("-" * 44)

for low, high, label in [(65,70,'65-69%'), (70,75,'70-74%'), (75,80,'75-79%'), (80,101,'80%+')]:
    cur.execute('''
        SELECT COUNT(*) as total, SUM(r.over25_correct) as correct
        FROM analyses a
        JOIN match_results r ON a.id = r.analysis_id
        WHERE a.over25_pct >= %s AND a.over25_pct < %s
    ''', (low, high))
    row = cur.fetchone()
    total = row['total'] or 0
    correct = int(row['correct'] or 0)
    pct = round(correct / total * 100, 1) if total > 0 else 0
    print(f"{label:<12} | {total:>6} | {correct:>7} | {pct:>8}%")

cur.close()
conn.close()
