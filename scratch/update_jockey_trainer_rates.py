import pandas as pd
import os

# Define the modern 2025/2026 win rates
modern_jockeys = {
    'Z PURTON': 0.207,
    'H BOWMAN': 0.109,
    'A ATZENI': 0.105,
    'K TEETAN': 0.080,
    'C L CHAU': 0.093,
    'C Y HO': 0.087,
    'A BADEL': 0.075,
    'H BENTLEY': 0.077,
    'L FERRARIS': 0.079,
    'K C LEUNG': 0.074,
    'J ORMAN': 0.068,
    'Y L CHUNG': 0.060,
    'E C W WONG': 0.070,
    'M F POON': 0.060,
    'M CHADWICK': 0.070,
    'H T MO': 0.040,
    'A HAMELIN': 0.060,
    'P N WONG': 0.050,
    'J MOREIRA': 0.170,
    'R KINGSCOTE': 0.030
}

modern_trainers = {
    'C FOWNES': 0.1228,
    'C S SHUM': 0.1214,
    'M NEWNHAM': 0.1085,
    'K W LUI': 0.1051,
    'D A HAYES': 0.0819,
    'J SIZE': 0.0897,
    'W K MO': 0.0895,
    'A S CRUZ': 0.0754,
    'P F YIU': 0.0952,
    'K L MAN': 0.0877,
    'F C LOR': 0.0900,
    'P C NG': 0.0800,
    'J RICHARDS': 0.0700,
    'W Y SO': 0.0600,
    'Y S TSUI': 0.0600,
    'C W CHANG': 0.0400,
    'K H TING': 0.0600,
    'C H YIP': 0.0600,
    'B CRAWFORD': 0.0800,
    'D EUSTACE': 0.0700
}

def update_csv(filepath, column_name, rates_dict):
    if not os.path.exists(filepath):
        print(f"File {filepath} not found. Creating new.")
        df = pd.DataFrame(columns=[column_name, f"{column_name}_win_rate"])
    else:
        df = pd.read_csv(filepath)
    
    # Ensure uppercase and stripped key
    df[column_name] = df[column_name].astype(str).str.strip().str.upper()
    
    # Create dict from df
    current_rates = dict(zip(df[column_name], df[f"{column_name}_win_rate"]))
    
    updated_count = 0
    added_count = 0
    
    for name, rate in rates_dict.items():
        name_upper = name.strip().upper()
        if name_upper in current_rates:
            if current_rates[name_upper] != rate:
                print(f"Updating {name_upper}: {current_rates[name_upper]} -> {rate}")
                current_rates[name_upper] = rate
                updated_count += 1
        else:
            print(f"Adding new {name_upper}: {rate}")
            current_rates[name_upper] = rate
            added_count += 1
            
    # Save back
    new_df = pd.DataFrame({
        column_name: list(current_rates.keys()),
        f"{column_name}_win_rate": list(current_rates.values())
    })
    new_df.to_csv(filepath, index=False)
    print(f"Finished {filepath}: updated {updated_count}, added {added_count} entries.")

if __name__ == '__main__':
    update_csv('data/jockey_win_rates.csv', 'jockey', modern_jockeys)
    update_csv('data/trainer_win_rates.csv', 'trainer', modern_trainers)
