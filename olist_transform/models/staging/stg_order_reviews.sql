WITH order_reviews AS (
    SELECT DISTINCT
        review_id,
        order_id,
        SAFE_CAST(review_score AS INT64) AS review_score,
        review_comment_title,
        review_comment_message,
        SAFE_CAST(review_creation_date AS TIMESTAMP) AS review_creation_date,
        SAFE_CAST(review_answer_timestamp AS TIMESTAMP) AS review_answer_timestamp
    FROM
        {{ source('olist_raw', 'public_order_reviews') }}
)

SELECT * FROM order_reviews