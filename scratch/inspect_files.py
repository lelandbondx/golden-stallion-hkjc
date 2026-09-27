import os

def inspect_file(filepath):
    print(f"--- Inspecting {filepath} ---")
    if not os.path.exists(filepath):
        print("File does not exist.")
        return
    
    # Try different encodings
    for encoding in ['utf-8', 'utf-16', 'utf-16le', 'utf-16be', 'latin-1']:
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                content = f.read(500)
                print(f"Success with {encoding}:")
                print(content[:300])
                print("...\n")
                return
        except Exception as e:
            pass
    print("Could not decode file with standard encodings.")

inspect_file('data/overnight_predictions_snapshot.txt')
inspect_file('picks_output.txt')
inspect_file('tmp_predictions_report.txt')
inspect_file('tmp_preds.txt')
inspect_file('tmp_preds_output.txt')
