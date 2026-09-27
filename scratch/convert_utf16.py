import os

files = ['picks_output.txt', 'tmp_predictions_report.txt', 'tmp_preds.txt', 'tmp_preds_output.txt']
for filename in files:
    if os.path.exists(filename):
        try:
            with open(filename, 'r', encoding='utf-16') as f:
                content = f.read()
            utf8_name = filename.replace('.txt', '_utf8.txt')
            with open(utf8_name, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Converted {filename} to {utf8_name}")
        except Exception as e:
            print(f"Error converting {filename}: {e}")
