WITH order_payments AS (
    SELECT
        order_id,
        SAFE_CAST(payment_sequential AS INT64) AS payment_sequential,
        payment_type,
        SAFE_CAST(payment_installments AS INT64) AS payment_installments,
        SAFE_CAST(payment_value AS NUMERIC) AS payment_value
    FROM 
        {{ source('olist_raw', 'public_order_payments') }}
)

SELECT * FROM order_payments