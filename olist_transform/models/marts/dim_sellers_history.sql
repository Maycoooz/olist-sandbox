WITH geolocation AS (
    SELECT
        zip_code,
        AVG(latitude)  AS latitude,
        AVG(longitude) AS longitude
    FROM {{ ref('stg_geolocation') }}
    GROUP BY zip_code
)

SELECT
    s.dbt_scd_id,
    s.seller_id,
    s.zip_code,
    s.city,
    s.state,
    g.latitude,
    g.longitude,
    s.dbt_valid_from,
    s.dbt_valid_to,
    s.dbt_valid_to IS NULL AS is_active

FROM {{ ref('snap_dim_sellers') }} AS s
LEFT JOIN geolocation AS g ON s.zip_code = g.zip_code
