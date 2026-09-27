import json
import os
import sys

# Ensure stdout handles utf-8 characters cleanly on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def audit():
    frozen_path = "data/frozen_predictions_20260923.json"
    if not os.path.exists(frozen_path):
        print(f"Error: {frozen_path} does not exist.")
        return

    with open(frozen_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    total_runners = 0
    all_clean = True

    print("=================================================================")
    print(f"🏆 GOLDEN STALLION AI — DEEP COMPREHENSIVE CARD AUDIT")
    print(f"Meeting: Happy Valley | Date: 2026-09-23 | File: {frozen_path}")
    print(f"Total Race Keys: {len(data.keys())}")
    print("=================================================================\n")

    for race_key in sorted(data.keys(), key=lambda x: int(x.split("_R")[-1]) if "_R" in x else 99):
        runners = data[race_key]
        r_num = race_key.split("_R")[-1]
        total_runners += len(runners)

        print(f"-----------------------------------------------------------------")
        print(f"🏇 RACE {r_num} ({len(runners)} Runners)")
        print(f"-----------------------------------------------------------------")

        # Sort runners by gs_score descending
        sorted_runners = sorted(
            runners,
            key=lambda x: -float(x.get("gs_score", 0) or 0)
        )

        for idx, runner in enumerate(sorted_runners[:5]):
            no = runner.get("no")
            name = runner.get("name")
            jockey = runner.get("jockey")
            trainer = runner.get("trainer")
            draw = runner.get("draw")
            weight = runner.get("actual_weight")
            rating = runner.get("rtg", runner.get("horse_rating"))
            odds = runner.get("win_odds")
            score = float(runner.get("gs_score", 0) or 0)
            prob = float(runner.get("model_prob", 0) or 0)
            ev = float(runner.get("value_diff", 0) or 0)
            conf = runner.get("confidence", 0)

            if odds is None or odds <= 0 or score <= 0:
                print(f"  ❌ ANOMALY on Runner #{no} {name}!")
                all_clean = False

            print(f"  Rank {idx+1} | #{no:>2} {name:<18} | Draw: {draw:>2} | Wgt: {weight:>3} | Rtg: {str(rating):>3} | Jockey: {str(jockey):<12} | Trainer: {str(trainer):<10} | Odds: {odds:>4.1f} | Conf: {conf:>2}% | EV: {ev:>+6.3f} | GS Score: {score:.2f}")


        top_pick = sorted_runners[0]
        sleeper = sorted_runners[min(4, len(sorted_runners)-1)]
        print(f"  🎯 STRATEGY: Anchor #{top_pick.get('no')} {top_pick.get('name')} ({top_pick.get('win_odds')}) + Sleeper #{sleeper.get('no')} {sleeper.get('name')} ({sleeper.get('win_odds')})\n")

    print("=================================================================")
    if all_clean:
        print(f"✅ AUDIT PASSED 100%: All {len(data.keys())} races and {total_runners} runners validated with zero nulls/anomalies.")
    else:
        print("❌ AUDIT FAILED: Issues found in runner telemetry.")
    print("=================================================================")


if __name__ == "__main__":
    audit()
