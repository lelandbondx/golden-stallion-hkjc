import pandas as pd
import numpy as np

# 1. Process Standard Times
df_std = pd.read_csv('data/scraped_table_0.csv')
# Rename columns
df_std.columns = ['Venue', 'Distance', 'Group', '1', '2', '3', '4', '5', 'Griffin']

# Forward fill venue
venues = df_std['Venue'].replace(r'^\s*$', np.nan, regex=True).ffill()
df_std['Venue'] = venues

# Clean venue names
df_std['Venue'] = df_std['Venue'].str.replace('', '', regex=False).str.strip()
df_std['Venue'] = df_std['Venue'].str.replace(r'\s+', ' ', regex=True).str.strip()

# Melt the dataframe
df_std_melted = pd.melt(df_std, id_vars=['Venue', 'Distance'], 
                        value_vars=['Group', '1', '2', '3', '4', '5', 'Griffin'],
                        var_name='Class', value_name='Standard_Time')

# Filter out empty or '-'
df_std_melted = df_std_melted[df_std_melted['Standard_Time'].notna()]
df_std_melted = df_std_melted[df_std_melted['Standard_Time'] != '-']

# 2. Process Course Records
st_turf = pd.concat([pd.read_csv('data/scraped_table_4.csv'), pd.read_csv('data/scraped_table_5.csv')])
st_turf['Venue'] = 'Sha Tin Turf Track'

hv_turf = pd.concat([pd.read_csv('data/scraped_table_6.csv'), pd.read_csv('data/scraped_table_7.csv')])
hv_turf['Venue'] = 'Happy Valley Turf Track'

st_awt = pd.concat([pd.read_csv('data/scraped_table_8.csv'), pd.read_csv('data/scraped_table_9.csv'), pd.read_csv('data/scraped_table_10.csv'), pd.read_csv('data/scraped_table_11.csv')])
st_awt['Venue'] = 'Sha Tin All Weather Track'

df_records = pd.concat([st_turf, hv_turf, st_awt])
df_records.rename(columns={'Time': 'Record_Time', 'Horse Name': 'Record_Horse'}, inplace=True)
df_records['Distance'] = pd.to_numeric(df_records['Distance'], errors='coerce')
df_std_melted['Distance'] = pd.to_numeric(df_std_melted['Distance'], errors='coerce')

# Standardize class formatting
def standardize_class(c):
    c = str(c)
    if '1' in c: return '1'
    if '2' in c: return '2'
    if '3' in c: return '3'
    if '4' in c: return '4'
    if '5' in c: return '5'
    if 'Group' in c or 'G1' in c or 'G2' in c or 'G3' in c or 'Listed' in c: return 'Group'
    if 'Griffin' in c: return 'Griffin'
    return c

df_records['Class'] = df_records['Class'].apply(standardize_class)
df_std_melted['Class'] = df_std_melted['Class'].apply(standardize_class)

# Deduplicate records by keeping the fastest (min) time per Venue/Distance/Class.
# Or just keeping the first one.
df_records = df_records.drop_duplicates(subset=['Venue', 'Distance', 'Class'], keep='first')

df_merged = pd.merge(df_std_melted, df_records[['Venue', 'Distance', 'Class', 'Record_Time', 'Record_Horse']], 
                     on=['Venue', 'Distance', 'Class'], how='left')

df_merged.to_csv('data/course_standard_times.csv', index=False)
print("Saved data/course_standard_times.csv")
