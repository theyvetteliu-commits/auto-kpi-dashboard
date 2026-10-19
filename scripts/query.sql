-- Daily metrics per market and plan.
-- In a real setup, refresh.py runs this on the data warehouse for the
-- refresh window. In this demo, demo_source.py makes the same columns.
-- :since and :until are filled in by refresh.py.

WITH daily_accounts AS (
    SELECT
        DATE(a.snapshot_at)            AS date,
        m.market_name                  AS market,
        m.stage                        AS stage,
        a.plan                         AS plan,
        COUNT(*)                       AS active_users,
        SUM(a.monthly_price_usd)       AS mrr_usd
    FROM account_snapshots a
    JOIN markets m ON m.market_id = a.market_id
    WHERE DATE(a.snapshot_at) BETWEEN :since AND :until
      AND a.status = 'active'
    GROUP BY 1, 2, 3, 4
),
daily_flows AS (
    SELECT
        DATE(e.event_at)                                      AS date,
        m.market_name                                         AS market,
        e.plan                                                AS plan,
        COUNT_IF(e.event_type = 'signup')                     AS signups,
        COUNT_IF(e.event_type = 'cancel')                     AS churned_users
    FROM account_events e
    JOIN markets m ON m.market_id = e.market_id
    WHERE DATE(e.event_at) BETWEEN :since AND :until
    GROUP BY 1, 2, 3
)
SELECT
    a.date, a.market, a.stage, a.plan,
    COALESCE(f.signups, 0)        AS signups,
    a.active_users,
    COALESCE(f.churned_users, 0)  AS churned_users,
    ROUND(a.mrr_usd)              AS mrr_usd
FROM daily_accounts a
LEFT JOIN daily_flows f USING (date, market, plan)
ORDER BY a.date, a.market, a.plan;
