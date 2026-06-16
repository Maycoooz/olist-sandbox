WITH reviews AS ( -- grain: one row per review
    SELECT
        review_id,
        order_id,
        review_score,
        review_comment_title,
        review_comment_message,
        review_creation_date,
        review_answer_timestamp
    FROM {{ ref('stg_order_reviews') }}
),

orders AS (
    SELECT 
        order_id,
        customer_id
    FROM {{ ref('stg_orders' )}}
),

final AS (
    SELECT
        r.review_id,
        r.order_id,
        o.customer_id,
        r.review_score,
        CASE 
            WHEN r.review_score >= 4 THEN 'positive'
            WHEN r.review_score = 3 THEN 'neutral'
            ELSE 'negative'
        END AS sentiment,
        r.review_comment_title,
        r.review_comment_message,
        r.review_creation_date,
        r.review_answer_timestamp
    FROM reviews AS r 
    LEFT JOIN orders AS o ON r.order_id = o.order_id 
)

SELECT * FROM final

-- Questions fact_reviews can answer:
-- Average review score by product/seller/category/state
-- Sentiment distribution across the platform
-- Correlation between delivery time and review score (join with fact_orders)
-- Review response time (review_answer_timestamp - review_creation_date)