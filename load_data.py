"""
load_data.py
Reads every Cricsheet IPL match file (JSON) and loads it into a SQLite database.
Run it once:   python load_data.py
It creates:    ipl.db
"""

import json
import sqlite3
from pathlib import Path

DATA_DIR = Path("data/ipl_json")
DB_PATH = "ipl.db"

# Two tables: matches (one row per match) and deliveries (one row per ball),
# linked by match_id (one-to-many).
SCHEMA = """
DROP TABLE IF EXISTS deliveries;
DROP TABLE IF EXISTS matches;

CREATE TABLE matches (
    match_id        INTEGER PRIMARY KEY,
    season          TEXT,
    match_date      TEXT,
    venue           TEXT,
    city            TEXT,
    team1           TEXT,
    team2           TEXT,
    toss_winner     TEXT,
    toss_decision   TEXT,
    winner          TEXT,
    win_by_runs     INTEGER,
    win_by_wickets  INTEGER,
    result          TEXT,
    player_of_match TEXT
);

CREATE TABLE deliveries (
    delivery_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id         INTEGER NOT NULL REFERENCES matches(match_id),
    innings_no       INTEGER,
    is_super_over    INTEGER,
    over_no          INTEGER,   -- 1 to 20
    ball_in_over     INTEGER,
    phase            TEXT,      -- powerplay / middle / death / super_over
    batting_team     TEXT,
    bowling_team     TEXT,
    batter           TEXT,
    bowler           TEXT,
    non_striker      TEXT,
    batter_runs      INTEGER,
    wides            INTEGER,
    noballs          INTEGER,
    byes             INTEGER,
    legbyes          INTEGER,
    total_runs       INTEGER,
    is_legal_ball    INTEGER,   -- 0 for wides and no-balls
    is_wicket        INTEGER,
    player_out       TEXT,
    wicket_kind      TEXT,
    is_bowler_wicket INTEGER    -- run outs etc. are not credited to the bowler
);
"""

NOT_BOWLER_WICKETS = {"run out", "retired hurt", "retired out", "obstructing the field"}


def get_phase(over_no, is_super_over):
    if is_super_over:
        return "super_over"
    if over_no <= 6:
        return "powerplay"
    if over_no <= 15:
        return "middle"
    return "death"


def parse_match(path):
    """Turn ONE match JSON file into (match_row, list_of_delivery_rows)."""
    match_id = int(path.stem)               # '335982.json' -> 335982
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    info = data["info"]
    team1, team2 = info["teams"]
    outcome = info.get("outcome", {})
    by = outcome.get("by", {})
    toss = info.get("toss", {})

    winner = outcome.get("winner") or outcome.get("eliminator")
    result = outcome.get("result", "normal")

    match_row = (
        match_id,
        str(info.get("season")),
        info["dates"][0],
        info.get("venue"),
        info.get("city"),
        team1,
        team2,
        toss.get("winner"),
        toss.get("decision"),
        winner,
        by.get("runs"),
        by.get("wickets"),
        result,
        ", ".join(info.get("player_of_match", [])),
    )

    delivery_rows = []
    # JSON is nested: innings -> overs -> deliveries. We flatten it to one row per ball.
    for innings_no, innings in enumerate(data.get("innings", []), start=1):
        batting_team = innings["team"]
        bowling_team = team2 if batting_team == team1 else team1
        is_super_over = 1 if innings.get("super_over") else 0

        for over in innings.get("overs", []):
            over_no = over["over"] + 1       # Cricsheet counts from 0
            phase = get_phase(over_no, is_super_over)

            for ball_in_over, ball in enumerate(over["deliveries"], start=1):
                runs = ball["runs"]
                extras = ball.get("extras", {})
                wides = extras.get("wides", 0)
                noballs = extras.get("noballs", 0)
                is_legal = 1 if (wides == 0 and noballs == 0) else 0

                wickets = ball.get("wickets", [])
                if wickets:
                    w = wickets[0]           # keep only the first wicket on a ball
                    is_wicket = 1
                    player_out = w.get("player_out")
                    kind = w.get("kind")
                    is_bowler_wicket = 0 if kind in NOT_BOWLER_WICKETS else 1
                else:
                    is_wicket, player_out, kind, is_bowler_wicket = 0, None, None, 0

                delivery_rows.append((
                    match_id, innings_no, is_super_over, over_no, ball_in_over, phase,
                    batting_team, bowling_team,
                    ball["batter"], ball["bowler"], ball["non_striker"],
                    runs["batter"], wides, noballs,
                    extras.get("byes", 0), extras.get("legbyes", 0),
                    runs["total"], is_legal,
                    is_wicket, player_out, kind, is_bowler_wicket,
                ))

    return match_row, delivery_rows


def main():
    files = sorted(DATA_DIR.glob("*.json"))
    if not files:
        raise SystemExit(
            f"No .json files found in {DATA_DIR}/ \n"
            "Download ipl_json.zip from https://cricsheet.org/downloads/ and unzip it there."
        )

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    match_sql = "INSERT INTO matches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    delivery_sql = """
        INSERT INTO deliveries (
            match_id, innings_no, is_super_over, over_no, ball_in_over, phase,
            batting_team, bowling_team, batter, bowler, non_striker,
            batter_runs, wides, noballs, byes, legbyes, total_runs, is_legal_ball,
            is_wicket, player_out, wicket_kind, is_bowler_wicket
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """

    loaded = 0
    for i, path in enumerate(files, start=1):
        try:
            match_row, delivery_rows = parse_match(path)
        except (KeyError, ValueError) as err:
            print(f"Skipping {path.name}: {err!r}")
            continue
        conn.execute(match_sql, match_row)
        conn.executemany(delivery_sql, delivery_rows)
        loaded += 1
        if i % 100 == 0:
            print(f"  ...{i}/{len(files)} files")

    # Indexes are created AFTER inserting (faster than updating them per row).
    conn.executescript("""
        CREATE INDEX idx_deliveries_match  ON deliveries(match_id);
        CREATE INDEX idx_deliveries_batter ON deliveries(batter);
        CREATE INDEX idx_deliveries_bowler ON deliveries(bowler);
        CREATE INDEX idx_matches_season    ON matches(season);
    """)

    conn.commit()
    n_balls = conn.execute("SELECT COUNT(*) FROM deliveries").fetchone()[0]
    conn.close()
    print(f"Done. Loaded {loaded} matches and {n_balls:,} deliveries into {DB_PATH}")


if __name__ == "__main__":
    main()