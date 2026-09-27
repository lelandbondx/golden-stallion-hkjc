with open('data/overnight_predictions_snapshot.txt', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

print("=== OVERNIGHT PREDICTIONS SNAPSHOT FOR 2026-06-21 ===")
print(content[:2500])
