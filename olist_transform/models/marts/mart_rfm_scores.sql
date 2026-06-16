WITH orders_deduped AS (
    -- deduplicate to one row per order to avoid summing total_payment_value multiple times
    SELECT DISTINCT
        fo.order_id,
        fo.customer_id,
        fo.order_purchase_timestamp,
        fo.total_payment_value
    FROM {{ ref('fact_orders') }} fo
    WHERE fo.order_status = 'delivered'
),

customer_metrics AS (
    SELECT
        dc.customer_unique_id,
        MIN(od.order_purchase_timestamp)              AS first_order_date,
        MAX(od.order_purchase_timestamp)              AS last_order_date,
        COUNT(DISTINCT od.order_id)                   AS frequency,
        SUM(COALESCE(od.total_payment_value, 0))      AS monetary
    FROM orders_deduped od
    JOIN {{ ref('dim_customers') }} dc ON od.customer_id = dc.customer_id
    GROUP BY dc.customer_unique_id
),

rfm_raw AS (
    SELECT
        customer_unique_id,
        DATE_TRUNC(DATE(first_order_date), MONTH)                    AS cohort_month,
        DATE_DIFF({{ current_analysis_date() }}, last_order_date, DAY) AS recency_days,
        frequency,
        ROUND(monetary, 2)                                           AS monetary
    FROM customer_metrics
),

rfm_scored AS (
    SELECT
        customer_unique_id,
        cohort_month,
        recency_days,
        frequency,
        monetary,

        -- Recency: fewer days since last order = higher score
        NTILE(5) OVER (ORDER BY recency_days DESC) AS recency_score,

        -- Frequency: more orders = higher score
        NTILE(5) OVER (ORDER BY frequency ASC)     AS frequency_score,

        -- Monetary: higher spend = higher score
        NTILE(5) OVER (ORDER BY monetary ASC)      AS monetary_score
    FROM rfm_raw
),

rfm_segmented AS (
    SELECT
        customer_unique_id,
        cohort_month,
        recency_days,
        frequency,
        monetary,
        recency_score,
        frequency_score,
        monetary_score,
        ROUND((recency_score + frequency_score + monetary_score) / 3.0, 2) AS rfm_score,

        CASE
            WHEN recency_score >= 4 AND frequency_score >= 4 AND monetary_score >= 4
                THEN 'champions'           -- bought recently, buy often, spend the most
            WHEN recency_score >= 3 AND frequency_score >= 3
                THEN 'loyal_customers'     -- buy regularly, responsive to promotions
            WHEN recency_score >= 4 AND frequency_score <= 2
                THEN 'promising'           -- recent but infrequent — nurture them
            WHEN recency_score <= 2 AND frequency_score >= 3
                THEN 'at_risk'             -- used to buy often but haven't recently
            WHEN recency_score <= 2 AND frequency_score <= 2
                THEN 'lost'                -- haven't bought in a long time, low frequency
            ELSE
                'potential_loyalists'      -- above average recency but not yet frequent
        END AS rfm_segment
    FROM rfm_scored
)

SELECT
    customer_unique_id,
    cohort_month,
    DATE_DIFF(DATE({{ current_analysis_date() }}), cohort_month, MONTH) AS months_since_first_order,
    recency_days,
    frequency,
    monetary,
    recency_score,
    frequency_score,
    monetary_score,
    rfm_score,
    rfm_segment,

    -- Campaign assignment: drives the dashboard customer list and CRM export
    CASE
        WHEN frequency = 1
             AND recency_days BETWEEN 30 AND 60   THEN 'second_purchase'
        WHEN rfm_segment = 'at_risk'              THEN 'winback'
        WHEN rfm_segment = 'lost'                 THEN 'reactivation'
        WHEN rfm_segment IN (
             'promising', 'potential_loyalists')   THEN 'nurture'
        WHEN rfm_segment IN (
             'champions', 'loyal_customers')       THEN 'loyalty_reward'
        ELSE                                            NULL
    END AS campaign_type

FROM rfm_segmented
