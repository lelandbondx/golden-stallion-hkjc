const { HorseRacingAPI, HKJCClient } = require('@gikndue/hkjc-api');

async function scrape() {
    try {
        const client = new HKJCClient();
        const hr = new HorseRacingAPI(client);
        const data = await hr.getRaceMeetings();
        
        if (!data || !data.raceMeetings || data.raceMeetings.length === 0) {
            console.log(JSON.stringify({ error: "No active meetings found" }));
            return;
        }

        const out = {
            status: "success",
            meetings: []
        };

        for (const meeting of data.raceMeetings) {
            const m = {
                venue: meeting.venueCode === "ST" ? "Sha Tin" : (meeting.venueCode === "HV" ? "Happy Valley" : meeting.venueCode),
                date: meeting.date,
                status: meeting.status || "UNKNOWN",
                going: meeting.races && meeting.races.length > 0 ? (meeting.races[0].go_en || "UNKNOWN") : "UNKNOWN",
                weather: "Live Feed Connected",
                races: []
            };

            for (const r of meeting.races || []) {
                const raceObj = {
                    race_no: parseInt(r.no),
                    time: r.postTime,
                    class_dist: `${r.raceClass_en || "Class ?"} - ${r.distance}m`,
                    runners: []
                };

                if (r.runners) {
                    for (const runner of r.runners) {
                        if (runner.status === 'Standby') continue;
                        
                        raceObj.runners.push({
                            no: parseInt(runner.no) || 0,
                            name: runner.name_en || runner.horse?.name_en || "Unknown",
                            jockey: runner.jockey ? runner.jockey.name_en : "Unknown",
                            trainer: runner.trainer ? runner.trainer.name_en : "Unknown",
                            draw: parseInt(runner.barrierDrawNumber) || 0,
                            actual_weight: parseInt(runner.handicapWeight) || 0,
                            declared_weight: parseInt(runner.currentWeight) || 0,
                            rtg: parseInt(runner.currentRating) || 0,
                            win_odds: parseFloat(runner.winOdds) || 0.0,
                            final_position: runner.finalPosition || null
                        });
                    }
                }
                raceObj.runners.sort((a,b) => a.no - b.no);
                m.races.push(raceObj);
            }
            m.races.sort((a,b) => a.race_no - b.race_no);
            out.meetings.push(m);
        }
        
        console.log(JSON.stringify(out));
    } catch (err) {
        console.log(JSON.stringify({ error: err.toString() }));
    }
}

scrape();
