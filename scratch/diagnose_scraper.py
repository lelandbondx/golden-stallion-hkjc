import os
import sys

# Ensure current directory is in path
sys.path.append(os.getcwd())

import scraper

def run_diagnostics():
    print("=================== SCRAPER DIAGNOSTIC ===================")
    
    # 1. Test live meeting scraping
    print("\n[1] Testing get_live_meeting_data()...")
    data = scraper.get_live_meeting_data()
    status = data.get("status")
    print(f"Scraper Status: {status}")
    
    meetings = data.get("meetings", [])
    print(f"Number of meetings found: {len(meetings)}")
    
    for idx, m in enumerate(meetings):
        print(f"\n--- Meeting {idx + 1} ---")
        print(f"Venue: {m.get('venue')}")
        print(f"Date: {m.get('date')}")
        print(f"Status: {m.get('status')}")
        print(f"Going: {m.get('going')}")
        print(f"Weather Info: {m.get('weather')}")
        
        races = m.get("races", [])
        print(f"Number of Races: {len(races)}")
        
        for r in races[:3]: # print first 3 races
            print(f"  Race {r.get('race_no')}: {r.get('class_dist')} at {r.get('time')} - {len(r.get('runners'))} runners")
            if r.get('runners'):
                # print top 3 runners
                print("    Sample runners:")
                for runner in r.get('runners')[:3]:
                    print(f"      #{runner.get('no')} {runner.get('name')} (J: {runner.get('jockey')}, T: {runner.get('trainer')}, Odds: {runner.get('win_odds')})")
        if len(races) > 3:
            print(f"  ... and {len(races) - 3} more races")

    # 2. Test tips index scraping
    print("\n[2] Testing get_live_tips_index()...")
    tips = scraper.get_live_tips_index()
    print(f"Scraped tips keys (races): {list(tips.keys())}")
    for race_no, horse_tips in list(tips.items())[:2]:
        print(f"  Race {race_no} tips: {horse_tips}")

    # 3. Test news scraping
    print("\n[3] Testing get_hkjc_news()...")
    news = scraper.get_hkjc_news()
    print(f"Number of news items: {len(news)}")
    for item in news[:3]:
        print(f"  - {item.get('title')} ({item.get('link')})")
        
    print("\n==========================================================")

if __name__ == "__main__":
    run_diagnostics()
