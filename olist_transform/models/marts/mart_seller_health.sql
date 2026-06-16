WITH analysis_ts AS (
    SELECT {{ current_analysis_date() }} AS val
),

seller_orders AS (
    -- deduplicate to one row per seller per order (fact_orders grain is order-item)
    SELECT DISTINCT
        seller_id,
        order_id,
        order_status,
        is_late,
        order_purchase_timestamp
    FROM {{ ref('fact_orders') }}
),

seller_reviews_base AS (
    -- attribute reviews to sellers via order_id; review is order-level in Olist
    SELECT DISTINCT
        fo.seller_id,
        fo.order_id,
        fr.review_score,
        fo.order_purchase_timestamp
    FROM {{ ref('fact_reviews') }} fr
    JOIN (
        SELECT DISTINCT seller_id, order_id, order_purchase_timestamp
        FROM {{ ref('fact_orders') }}
    ) fo ON fr.order_id = fo.order_id
    WHERE DATE(fr.review_creation_date) >= DATE(fo.order_purchase_timestamp)
),

-- ── All-time metrics (baseline health score) ──────────────────────────────────

seller_metrics_all AS (
    SELECT
        seller_id,
        COUNT(*)                                                              AS total_orders,
        COUNTIF(order_status = 'delivered')                                   AS delivered_orders,
        COUNTIF(order_status IN ('cancelled', 'unavailable'))                 AS cancelled_orders,
        COUNTIF(order_status = 'delivered' AND is_late)                       AS late_orders,
        ROUND(SAFE_DIVIDE(
            COUNTIF(order_status = 'delivered'), COUNT(*)
        ) * 100, 1)                                                           AS delivery_rate_pct,
        ROUND(SAFE_DIVIDE(
            COUNTIF(order_status = 'delivered' AND NOT is_late),
            COUNTIF(order_status = 'delivered')
        ) * 100, 1)                                                           AS on_time_rate_pct
    FROM seller_orders
    GROUP BY seller_id
),

seller_reviews_all AS (
    SELECT seller_id, ROUND(AVG(review_score), 2) AS avg_review_score
    FROM seller_reviews_base
    GROUP BY seller_id
),

-- ── Recent window: last 90 days before analysis date (trend signal) ───────────
-- In a live pipeline this window slides forward every daily run,
-- surfacing sellers whose performance is quietly degrading.

seller_metrics_recent AS (
    SELECT
        seller_id,
        COUNT(*)                                                              AS recent_total_orders,
        ROUND(SAFE_DIVIDE(
            COUNTIF(order_status = 'delivered'), COUNT(*)
        ) * 100, 1)                                                           AS recent_delivery_rate_pct,
        ROUND(SAFE_DIVIDE(
            COUNTIF(order_status = 'delivered' AND NOT is_late),
            COUNTIF(order_status = 'delivered')
        ) * 100, 1)                                                           AS recent_on_time_rate_pct
    FROM seller_orders
    WHERE TIMESTAMP_DIFF((SELECT val FROM analysis_ts), order_purchase_timestamp, DAY) <= 90
    GROUP BY seller_id
),

seller_reviews_recent AS (
    SELECT srb.seller_id, ROUND(AVG(srb.review_score), 2) AS recent_avg_review_score
    FROM seller_reviews_base srb
    JOIN seller_orders so USING (seller_id, order_id)
    WHERE TIMESTAMP_DIFF((SELECT val FROM analysis_ts), so.order_purchase_timestamp, DAY) <= 90
    GROUP BY srb.seller_id
),

-- ── Score assembly ────────────────────────────────────────────────────────────
-- Formula: 40% customer review score + 35% on-time delivery + 25% delivery rate
-- Sellers with no reviews default to 3.0 (neutral) — flagged separately via avg_review_score IS NULL

scored AS (
    SELECT
        a.seller_id,
        a.total_orders,
        a.delivered_orders,
        a.cancelled_orders,
        a.late_orders,
        a.delivery_rate_pct,
        a.on_time_rate_pct,
        COALESCE(ra.avg_review_score, 3.0)                                    AS avg_review_score,
        ROUND((
            0.40 * COALESCE(ra.avg_review_score, 3.0) / 5.0
            + 0.35 * COALESCE(a.on_time_rate_pct, 0) / 100.0
            + 0.25 * COALESCE(a.delivery_rate_pct, 0) / 100.0
        ) * 100, 1)                                                           AS health_score,
        r.recent_total_orders,
        ROUND((
            0.40 * COALESCE(rr.recent_avg_review_score, 3.0) / 5.0
            + 0.35 * COALESCE(r.recent_on_time_rate_pct, 0) / 100.0
            + 0.25 * COALESCE(r.recent_delivery_rate_pct, 0) / 100.0
        ) * 100, 1)                                                           AS recent_health_score
    FROM seller_metrics_all     a
    LEFT JOIN seller_reviews_all    ra ON a.seller_id = ra.seller_id
    LEFT JOIN seller_metrics_recent r  ON a.seller_id = r.seller_id
    LEFT JOIN seller_reviews_recent rr ON a.seller_id = rr.seller_id
),

-- ── Tier + trend labels + location (needed before intervention_reason) ─────────

tiered AS (
    SELECT
        s.seller_id,
        ds.state,
        ds.city,
        s.total_orders,
        s.delivered_orders,
        s.cancelled_orders,
        s.late_orders,
        s.delivery_rate_pct,
        s.on_time_rate_pct,
        s.avg_review_score,
        s.health_score,
        CASE
            WHEN s.health_score >= 80 THEN 'excellent'
            WHEN s.health_score >= 60 THEN 'good'
            WHEN s.health_score >= 40 THEN 'at_risk'
            ELSE                           'critical'
        END                                                                   AS health_tier,
        s.recent_total_orders,
        s.recent_health_score,
        ROUND(COALESCE(s.recent_health_score, 0) - s.health_score, 1)        AS score_delta,
        CASE
            WHEN s.recent_total_orders IS NULL             THEN 'inactive'
            WHEN COALESCE(s.recent_health_score, 0)
                 < s.health_score - 10                     THEN 'declining'
            ELSE                                                'stable'
        END                                                                   AS trend_status
    FROM scored s
    LEFT JOIN {{ ref('dim_sellers') }} ds ON s.seller_id = ds.seller_id
)

SELECT
    seller_id,
    state,
    city,
    total_orders,
    delivered_orders,
    cancelled_orders,
    late_orders,
    delivery_rate_pct,
    on_time_rate_pct,
    avg_review_score,
    health_score,
    health_tier,
    recent_total_orders,
    recent_health_score,
    score_delta,
    trend_status,

    -- Human-readable reason for intervention — drives dashboard filter and report download
    CASE
        WHEN trend_status = 'inactive'
             THEN 'No orders in past 90 days — possible churn'
        WHEN trend_status = 'declining' AND health_tier = 'critical'
             THEN 'Critical score and dropping — immediate outreach required'
        WHEN trend_status = 'declining' AND health_tier = 'at_risk'
             THEN 'At-risk score and worsening — schedule check-in'
        WHEN health_tier = 'critical'
             THEN 'Critical score — performance review needed'
        WHEN health_tier = 'at_risk'
             THEN 'At-risk score — monitor closely'
        ELSE NULL
    END                                                                       AS intervention_reason

FROM tiered
