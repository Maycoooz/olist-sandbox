WITH customers AS (
    SELECT DISTINCT
        customer_id,
        customer_unique_id,
        LPAD(SAFE_CAST(customer_zip_code_prefix AS STRING), 5, '0') AS zip_code,
        customer_city AS city,
        customer_state AS state
    FROM
        {{ source('olist_raw', 'public_customers') }}
)

SELECT * FROM customers