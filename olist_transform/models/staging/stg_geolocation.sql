WITH geolocation AS (
    SELECT DISTINCT
        LPAD(SAFE_CAST(geolocation_zip_code_prefix AS STRING), 5, '0') AS zip_code,
        SAFE_CAST(geolocation_lat AS FLOAT64 ) AS latitude,
        SAFE_CAST(geolocation_lng AS FLOAT64 ) AS longitude,
        geolocation_city AS city,
        geolocation_state AS state
    FROM 
        {{ source('olist_raw', 'public_geolocation') }}
)

SELECT * FROM geolocation