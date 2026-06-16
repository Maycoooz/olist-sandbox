{% macro current_analysis_date() %}
    {% if var('analysis_date', none) %}
        TIMESTAMP('{{ var("analysis_date") }}')
    {% else %}
        (
            SELECT TIMESTAMP_ADD(MAX(order_purchase_timestamp), INTERVAL 1 DAY)
            FROM {{ ref('fact_orders') }}
        )
    {% endif %}
{% endmacro %}
