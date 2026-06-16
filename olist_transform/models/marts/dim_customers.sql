WITH geolocation AS (
    SELECT
        zip_code,
        AVG(latitude) AS latitude,  -- avg the lat and lng because 1 zip code has many diff coords
        AVG(longitude) AS longitude -- so avg them consolidate all orders in the same zip code
    FROM {{ ref('stg_geolocation') }}
    GROUP BY zip_code
),

customers AS (
    SELECT
        c.customer_id,        -- PK (connects customer to their order)
        c.customer_unique_id, -- A specific customer, might have duplicates (a customer who ordered more than once)
        c.zip_code,
        c.city,
        c.state,
        g.latitude,
        g.longitude
    FROM {{ ref('stg_customers') }} AS c 
    LEFT JOIN geolocation AS g
    ON c.zip_code = g.zip_code
)

SELECT * FROM customers
