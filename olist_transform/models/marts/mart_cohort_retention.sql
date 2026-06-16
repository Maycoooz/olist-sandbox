WITH orders_deduped AS (
    -- deduplicate to one row per order
    SELECT DISTINCT
        fo.order_id,
        fo.customer_id,
        fo.order_purchase_timestamp
    FROM {{ ref('fact_orders') }} fo
    WHERE fo.order_status = 'delivered'
),

customer_orders AS (
    SELECT
        dc.customer_unique_id,
        DATE_TRUNC(DATE(od.order_purchase_timestamp), MONTH) AS order_month
    FROM orders_deduped od
    JOIN {{ ref('dim_customers') }} dc ON od.customer_id = dc.customer_id
),

-- One row per customer: their cohort (month of first order)
customer_cohorts AS (
    SELECT
        customer_unique_id,
        MIN(order_month) AS cohort_month
    FROM customer_orders
    GROUP BY customer_unique_id
),

-- Cross join cohorts with all their subsequent order months
cohort_activity AS (
    SELECT
        cc.cohort_month,
        co.order_month,
        DATE_DIFF(co.order_month, cc.cohort_month, MONTH) AS months_since_first,
        COUNT(DISTINCT co.customer_unique_id)              AS customers_retained
    FROM customer_cohorts cc
    JOIN customer_orders co ON cc.customer_unique_id = co.customer_unique_id
    GROUP BY cc.cohort_month, co.order_month, months_since_first
),

cohort_sizes AS (
    SELECT
        cohort_month,
        COUNT(DISTINCT customer_unique_id) AS cohort_size
    FROM customer_cohorts
    GROUP BY cohort_month
)

SELECT
    ca.cohort_month,
    ca.months_since_first,
    ca.order_month,
    cs.cohort_size,
    ca.customers_retained,
    ROUND(ca.customers_retained / cs.cohort_size * 100, 2) AS retention_rate_pct

FROM cohort_activity ca
JOIN cohort_sizes cs ON ca.cohort_month = cs.cohort_month
ORDER BY ca.cohort_month, ca.months_since_first
