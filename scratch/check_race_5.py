import pandas as pd
from scraper import get_live_meeting_data
from model import predict_probabilities, load_model

def check_race_5():
    data = get_live_meeting_data()
    meeting = data['meetings'][0]
    # Race 5 is index 4
    race = meeting['races'][4] 
    df_runners = pd.DataFrame(race['runners'])

    probs, df_feats = predict_probabilities(df_runners, venue=meeting.get('venue'), going=meeting.get('going'), race_date=meeting.get('date'), race_class_int=3)
    df_feats['model_prob'] = probs

    print("--- RACE 5 CONTENDERS DEEP-DIVE ---")
    cols = ['no', 'name', 'jockey', 'trainer', 'draw', 'actual_weight', 'horse_rating', 'recent_avg_pos', 'ST_vs_HV_pref', 'last_form_going', 'gear_changed', 'jockey_win_rate', 'trainer_win_rate', 'model_prob']
    df_print = df_feats.sort_values(by='model_prob', ascending=False)[cols].head(3)
    
    for _, r in df_print.iterrows():
        print(f"\nRunner #{r['no']} {r['name']}:")
        print(f"  Jockey: {r['jockey']} (Win Rate: {r['jockey_win_rate']:.3f})")
        print(f"  Trainer: {r['trainer']} (Win Rate: {r['trainer_win_rate']:.3f})")
        print(f"  Draw (Barrier): {r['draw']}")
        print(f"  Weight: {r['actual_weight']} lbs")
        print(f"  Rating: {r['horse_rating']}")
        print(f"  Recent Avg Finish Position (Form): {r['recent_avg_pos']:.2f}")
        print(f"  Track Preference: {r['ST_vs_HV_pref']}")
        print(f"  Last Preferred Going: {r['last_form_going']}")
        print(f"  Gear Changed: {r['gear_changed']}")
        print(f"  Raw Model Probability: {r['model_prob']:.4f}")

if __name__ == '__main__':
    check_race_5()
