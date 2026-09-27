import json
import re

transcript_path = r"C:\Users\lelan\.gemini\antigravity\brain\77f0d995-376f-4490-8e9b-029ba8705a29\.system_generated\logs\transcript.jsonl"

print("Scanning transcript for links and past instructions...")
with open(transcript_path, 'r', encoding='utf-8') as f:
    for line_idx, line in enumerate(f):
        try:
            step = json.loads(line)
            # Check for user input steps
            if step.get('type') == 'USER_INPUT':
                content = step.get('content', '')
                print(f"\n[Step {step.get('step_index')}] USER_INPUT:")
                print(content)
            elif step.get('source') == 'USER_EXPLICIT':
                content = step.get('content', '')
                print(f"\n[Step {step.get('step_index')}] USER_EXPLICIT:")
                print(content)
        except Exception as e:
            print(f"Error parsing line {line_idx}: {e}")
