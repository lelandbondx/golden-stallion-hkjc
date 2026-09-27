import json
import os

transcript_path = r"C:\Users\lelan\.gemini\antigravity\brain\77f0d995-376f-4490-8e9b-029ba8705a29\.system_generated\logs\transcript.jsonl"

with open(transcript_path, 'r', encoding='utf-8') as f:
    for line in f:
        try:
            data = json.loads(line.strip())
            created_at = data.get('created_at', '')
            if '2026-06-29' in created_at:
                source = data.get('source')
                step_type = data.get('type')
                
                # Check for USER inputs or MODEL responses (PLANNER_RESPONSE)
                if step_type == 'USER_INPUT':
                    content = data.get('content', '')
                    print(f"[{created_at}] USER:")
                    print(content)
                    print("-" * 50)
                elif step_type == 'PLANNER_RESPONSE':
                    content = data.get('content', '')
                    print(f"[{created_at}] AGENT:")
                    print(content[:600] + ("..." if len(content) > 600 else ""))
                    print("-" * 50)
        except Exception as e:
            print("Error parsing line:", e)
