WITH sellers AS (
    SELECT DISTINCT
        seller_id,
        LPAD(SAFE_CAST(seller_zip_code_prefix AS STRING), 5, '0') AS zip_code,
        seller_city AS city,
        seller_state AS state
    FROM 
        {{ source('olist_raw', 'public_sellers') }}
)

SELECT * FROM sellers