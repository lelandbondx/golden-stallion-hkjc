import os

files = [f for f in os.listdir('data') if f.endswith('.json')]
print(f"Total JSON files: {len(files)}")
print("Files:")
for fn in sorted(files):
    print(f"  {fn}")
