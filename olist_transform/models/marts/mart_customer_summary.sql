WITH orders_deduped AS (
    -- fact_orders grain is per order_item; deduplicate to one row per order
    SELECT DISTINCT
        fo.order_id,
        fo.customer_id,
        fo.order_purchase_timestamp,
        fo.order_status,
        fo.total_payment_value,
        fo.is_late
    FROM {{ ref('fact_orders') }} fo
    WHERE fo.order_status = 'delivered'
),

customer_orders AS (
    SELECT
        dc.customer_unique_id,
        od.order_id,
        od.order_purchase_timestamp,
        od.total_payment_value,
        od.is_late
    FROM orders_deduped od
    JOIN {{ ref('dim_customers') }} dc ON od.customer_id = dc.customer_id
),

customer_reviews AS (
    SELECT
        dc.customer_unique_id,
        AVG(fr.review_score) AS avg_review_score
    FROM {{ ref('fact_reviews') }} fr
    JOIN {{ ref('dim_customers') }} dc ON fr.customer_id = dc.customer_id
    GROUP BY dc.customer_unique_id
),

-- Most recent location per customer (a customer may have different addresses across orders)
latest_location AS (
    SELECT
        dc.customer_unique_id,
        dc.state,
        dc.city,
        dc.latitude,
        dc.longitude
    FROM {{ ref('dim_customers') }} dc
    JOIN orders_deduped od ON dc.customer_id = od.customer_id
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY dc.customer_unique_id
        ORDER BY od.order_purchase_timestamp DESC
    ) = 1
),

order_agg AS (
    SELECT
        customer_unique_id,
        COUNT(DISTINCT order_id)                                          AS total_orders,
        MIN(order_purchase_timestamp)                                     AS first_order_date,
        MAX(order_purchase_timestamp)                                     AS last_order_date,
        SUM(COALESCE(total_payment_value, 0))                             AS total_spend,
        SUM(COALESCE(total_payment_value, 0)) / COUNT(DISTINCT order_id) AS avg_order_value,
        COUNTIF(is_late)                                                  AS late_orders
    FROM customer_orders
    GROUP BY customer_unique_id
)

SELECT
    oa.customer_unique_id,
    ll.state,
    ll.city,
    ll.latitude,
    ll.longitude,

    -- Order history
    oa.total_orders,
    oa.first_order_date,
    oa.last_order_date,
    DATE_DIFF({{ current_analysis_date() }}, oa.last_order_date, DAY)              AS days_since_last_order,

    -- Spend
    ROUND(oa.total_spend, 2)                                             AS total_spend,
    ROUND(oa.avg_order_value, 2)                                         AS avg_order_value,

    -- Satisfaction
    ROUND(cr.avg_review_score, 2)                                        AS avg_review_score,

    -- Delivery
    oa.late_orders,
    ROUND(oa.late_orders / oa.total_orders * 100, 1)                    AS pct_late_orders,

    -- Segment based on recency
    CASE
        WHEN DATE_DIFF({{ current_analysis_date() }}, oa.last_order_date, DAY) <= 90
            AND oa.total_orders = 1                                       THEN 'new'
        WHEN DATE_DIFF({{ current_analysis_date() }}, oa.last_order_date, DAY) <= 180 THEN 'active'
        WHEN DATE_DIFF({{ current_analysis_date() }}, oa.last_order_date, DAY) <= 365 THEN 'at_risk'
        ELSE 'churned'
    END                                                                   AS customer_segment

FROM order_agg oa
LEFT JOIN latest_location ll  ON oa.customer_unique_id = ll.customer_unique_id
LEFT JOIN customer_reviews cr ON oa.customer_unique_id = cr.customer_unique_id
