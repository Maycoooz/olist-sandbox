WITH products AS (
    SELECT DISTINCT
        p.product_id,
        COALESCE(t.product_category_name_english, p.product_category_name) AS product_category_name_english,
        SAFE_CAST(p.product_name_lenght AS INT64 ) AS product_name_length,
        SAFE_CAST(p.product_description_lenght AS INT64 ) AS product_description_length,
        SAFE_CAST(p.product_photos_qty AS INT64 ) AS product_photos_qty,
        SAFE_CAST(p.product_weight_g AS INT64 ) AS product_weight_g,
        SAFE_CAST(p.product_length_cm AS INT64 ) AS product_length_cm,
        SAFE_CAST(p.product_height_cm AS INT64 ) AS product_height_cm,
        SAFE_CAST(p.product_width_cm AS INT64 ) AS product_width_cm
    FROM
        {{ source('olist_raw', 'public_products') }} AS p 
    LEFT JOIN
        {{ source('olist_raw', 'public_product_category_name_translation') }} AS t 
    ON 
        p.product_category_name = t.product_category_name
)

SELECT * FROM products