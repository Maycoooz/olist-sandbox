WITH order_items AS (
    SELECT
        order_id,
        order_item_id,
        product_id,
        seller_id,
        SAFE_CAST(shipping_limit_date AS TIMESTAMP) AS shipping_limit_date,
        SAFE_CAST(price AS NUMERIC) AS price,
        SAFE_CAST(freight_value AS NUMERIC) AS freight_value
    FROM
        {{ source('olist_raw', 'public_order_items') }}
)

SELECT * FROM order_items