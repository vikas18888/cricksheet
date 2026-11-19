-- Rules used:
--   Balls FACED by batter = all balls except wides
--   LEGAL balls           = all balls except wides and no-balls
--   Runs CONCEDED         = bat runs + wides + no-balls (not byes/leg-byes)
--   Super overs excluded from normal stats

-- Q1. Matches per season
SELECT season, COUNT(*) AS matches
FROM matches
GROUP BY season
ORDER BY MIN(match_date);

-- Q2. Top 10 run scorers with strike rate
SELECT batter,
       SUM(batter_runs) AS runs,
       SUM(CASE WHEN wides = 0 THEN 1 ELSE 0 END) AS balls_faced,
       ROUND(100.0 * SUM(batter_runs)
             / SUM(CASE WHEN wides = 0 THEN 1 ELSE 0 END), 2) AS strike_rate
FROM deliveries
WHERE is_super_over = 0
GROUP BY batter
ORDER BY runs DESC
LIMIT 10;

-- Q3. Best death-over hitters (min 300 balls). HAVING filters AFTER grouping.
SELECT batter,
       SUM(batter_runs) AS runs,
       SUM(CASE WHEN wides = 0 THEN 1 ELSE 0 END) AS balls_faced,
       ROUND(100.0 * SUM(batter_runs)
             / SUM(CASE WHEN wides = 0 THEN 1 ELSE 0 END), 2) AS strike_rate
FROM deliveries
WHERE phase = 'death'
GROUP BY batter
HAVING balls_faced >= 300
ORDER BY strike_rate DESC
LIMIT 10;

-- Q4. Best powerplay bowlers by economy (min 300 legal balls)
SELECT bowler,
       SUM(is_legal_ball) AS legal_balls,
       SUM(batter_runs + wides + noballs) AS runs_conceded,
       ROUND(6.0 * SUM(batter_runs + wides + noballs) / SUM(is_legal_ball), 2) AS economy
FROM deliveries
WHERE phase = 'powerplay'
GROUP BY bowler
HAVING legal_balls >= 300
ORDER BY economy ASC
LIMIT 10;

-- Q5. Top 10 wicket takers
SELECT bowler,
       SUM(is_bowler_wicket) AS wickets,
       ROUND(1.0 * SUM(is_legal_ball) / SUM(is_bowler_wicket), 1) AS balls_per_wicket
FROM deliveries
WHERE is_super_over = 0
GROUP BY bowler
ORDER BY wickets DESC
LIMIT 10;

-- Q6. Does winning the toss help?
SELECT toss_decision,
       COUNT(*) AS matches,
       SUM(CASE WHEN toss_winner = winner THEN 1 ELSE 0 END) AS toss_winner_won,
       ROUND(100.0 * SUM(CASE WHEN toss_winner = winner THEN 1 ELSE 0 END)
             / COUNT(*), 1) AS win_pct
FROM matches
WHERE winner IS NOT NULL
GROUP BY toss_decision;

-- Q7. Team win % (CTE + UNION ALL stacks team1 and team2 into one column)
WITH team_matches AS (
    SELECT match_id, team1 AS team, winner FROM matches WHERE winner IS NOT NULL
    UNION ALL
    SELECT match_id, team2 AS team, winner FROM matches WHERE winner IS NOT NULL
)
SELECT team,
       COUNT(*) AS played,
       SUM(CASE WHEN team = winner THEN 1 ELSE 0 END) AS won,
       ROUND(100.0 * SUM(CASE WHEN team = winner THEN 1 ELSE 0 END) / COUNT(*), 1) AS win_pct
FROM team_matches
GROUP BY team
HAVING played >= 20
ORDER BY win_pct DESC;

-- Q8. Top 3 run scorers in EACH season (window function)
WITH season_runs AS (
    SELECT m.season, d.batter, SUM(d.batter_runs) AS runs
    FROM deliveries d
    JOIN matches m ON m.match_id = d.match_id
    WHERE d.is_super_over = 0
    GROUP BY m.season, d.batter
),
ranked AS (
    SELECT season, batter, runs,
           RANK() OVER (PARTITION BY season ORDER BY runs DESC) AS rnk
    FROM season_runs
)
SELECT season, rnk, batter, runs
FROM ranked
WHERE rnk <= 3
ORDER BY season, rnk;

-- Q9. Scoring rate and wickets by phase
SELECT phase,
       ROUND(6.0 * SUM(total_runs) / SUM(is_legal_ball), 2) AS runs_per_over,
       ROUND(6.0 * SUM(is_wicket)  / SUM(is_legal_ball), 3) AS wickets_per_over
FROM deliveries
WHERE is_super_over = 0
GROUP BY phase
ORDER BY CASE phase WHEN 'powerplay' THEN 1 WHEN 'middle' THEN 2 ELSE 3 END;

-- Q10. Over-by-over score progression of one match (running total)
WITH per_over AS (
    SELECT innings_no, batting_team, over_no,
           SUM(total_runs) AS runs,
           SUM(is_wicket)  AS wkts
    FROM deliveries
    WHERE match_id = (SELECT MIN(match_id) FROM matches)
      AND is_super_over = 0
    GROUP BY innings_no, batting_team, over_no
)
SELECT innings_no, batting_team, over_no, runs,
       SUM(runs) OVER (PARTITION BY innings_no ORDER BY over_no) AS score_after_over,
       SUM(wkts) OVER (PARTITION BY innings_no ORDER BY over_no) AS wickets_after_over
FROM per_over
ORDER BY innings_no, over_no;

-- Q11. Batter vs bowler head-to-head
-- Find exact names first:  SELECT DISTINCT batter FROM deliveries WHERE batter LIKE '%Kohli%';
SELECT batter, bowler,
       SUM(batter_runs) AS runs,
       SUM(CASE WHEN wides = 0 THEN 1 ELSE 0 END) AS balls,
       SUM(CASE WHEN is_bowler_wicket = 1 AND player_out = batter THEN 1 ELSE 0 END) AS dismissals
FROM deliveries
WHERE batter = 'V Kohli' AND bowler = 'JJ Bumrah'
GROUP BY batter, bowler;

-- Q12. Ten highest team totals
SELECT d.match_id, m.match_date, d.batting_team,
       SUM(d.total_runs) AS total, SUM(d.is_wicket) AS wickets_lost
FROM deliveries d
JOIN matches m ON m.match_id = d.match_id
WHERE d.is_super_over = 0
GROUP BY d.match_id, d.innings_no, d.batting_team
ORDER BY total DESC
LIMIT 10;

-- Q13. See what an index does (SEARCH = fast, SCAN = slow)
EXPLAIN QUERY PLAN
SELECT SUM(batter_runs) FROM deliveries WHERE batter = 'V Kohli';
-- DROP INDEX idx_deliveries_batter;   -- then run the EXPLAIN again
-- CREATE INDEX idx_deliveries_batter ON deliveries(batter);