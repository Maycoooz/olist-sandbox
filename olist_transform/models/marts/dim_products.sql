WITH products AS (
    SELECT
        product_id,
        product_category_name_english,
        product_photos_qty, -- more photoes = more sales? 
        product_weight_g,
        product_length_cm,
        product_height_cm,
        product_width_cm
    FROM {{ ref('stg_products') }}
)

SELECT * FROM products