WITH geolocation AS (
    SELECT
        zip_code,
        AVG(latitude) AS latitude,  -- avg the lat and lng because 1 zip code has many diff coords
        AVG(longitude) AS longitude -- so avg them consolidate all orders in the same zip code
    FROM {{ ref('stg_geolocation') }}
    GROUP BY zip_code
),

sellers AS (
    SELECT
        s.seller_id,
        s.zip_code,
        s.city,
        s.state,
        g.latitude,
        g.longitude
    FROM {{ ref('snap_dim_sellers') }} AS s
    LEFT JOIN geolocation AS g ON s.zip_code = g.zip_code
    WHERE s.dbt_valid_to IS NULL  -- active record only
)

SELECT * FROM sellers