{% snapshot snap_dim_sellers %}

{{
    config(
        target_schema='snapshots',
        unique_key='seller_id',
        strategy='check',
        check_cols=['zip_code', 'city', 'state'],
        invalidate_hard_deletes=True,
    )
}}

SELECT * FROM {{ ref('stg_sellers') }}

{% endsnapshot %}
