#!/usr/bin/env python3
"""
Olist E-Commerce Intelligence Dashboard v3
Redesigned visuals and interactivity — data layer unchanged.
Fetches from BigQuery mart tables → self-contained HTML → docs/index.html

Run:    python report/generate_dashboard_v2.py
Deploy: git add docs/index.html && git commit -m "..." && git push
Live:   https://Maycoooz.github.io/olist-sandbox/
"""
import json, pathlib, decimal, datetime
import pandas as pd
from google.cloud import bigquery

# ── Config ─────────────────────────────────────────────────────────────────────
KEY_FILE = '/Users/mudkip/Desktop/olist-498903-e7f8763e517a.json'
PROJECT  = 'olist-498903'
DATASET  = 'olist_transformed_sandbox'
MARTS    = f'{PROJECT}.{DATASET}_marts'
EXCL     = "'bfbd0f9bdef84302105ad712db648a6c'"
OUT      = pathlib.Path(__file__).parent.parent / 'docs' / 'index.html'

client = bigquery.Client.from_service_account_json(KEY_FILE)
q = lambda sql: client.query(sql).to_dataframe()

# ── Brazil state metadata ───────────────────────────────────────────────────────
STATE_COORDS = {
    'AC':[-9.02,-70.81],'AL':[-9.57,-36.78],'AM':[-4.00,-61.99],
    'AP':[0.90,-52.00], 'BA':[-12.57,-41.70],'CE':[-5.50,-39.32],
    'DF':[-15.78,-47.93],'ES':[-19.19,-40.34],'GO':[-15.83,-49.98],
    'MA':[-4.96,-45.27],'MG':[-18.10,-44.38],'MS':[-20.51,-54.54],
    'MT':[-12.64,-55.42],'PA':[-3.79,-52.48],'PB':[-7.06,-36.55],
    'PE':[-8.81,-36.95],'PI':[-7.72,-42.73],'PR':[-24.89,-51.55],
    'RJ':[-22.25,-42.66],'RN':[-5.84,-36.53],'RO':[-10.83,-63.34],
    'RR':[2.07,-61.40], 'RS':[-30.03,-53.23],'SC':[-27.45,-50.95],
    'SE':[-10.57,-37.45],'SP':[-22.19,-48.79],'TO':[-10.18,-48.33],
}
STATE_NAMES = {
    'AC':'Acre','AL':'Alagoas','AM':'Amazonas','AP':'Amapá','BA':'Bahia',
    'CE':'Ceará','DF':'Distrito Federal','ES':'Espírito Santo','GO':'Goiás',
    'MA':'Maranhão','MG':'Minas Gerais','MS':'Mato Grosso do Sul',
    'MT':'Mato Grosso','PA':'Pará','PB':'Paraíba','PE':'Pernambuco',
    'PI':'Piauí','PR':'Paraná','RJ':'Rio de Janeiro','RN':'Rio Grande do Norte',
    'RO':'Rondônia','RR':'Roraima','RS':'Rio Grande do Sul',
    'SC':'Santa Catarina','SE':'Sergipe','SP':'São Paulo','TO':'Tocantins',
}


class BQEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, decimal.Decimal): return float(obj)
        if isinstance(obj, (datetime.date, datetime.datetime)): return str(obj)
        if hasattr(obj, 'item'): return obj.item()
        return super().default(obj)


# ── BigQuery fetches (unchanged) ────────────────────────────────────────────────
def fetch():
    print('Fetching from BigQuery…')

    kpi = q(f"""
        SELECT
            COUNT(DISTINCT fo.order_id)                              AS total_orders,
            COUNT(DISTINCT dc.customer_unique_id)                    AS unique_customers,
            ROUND(SUM(fo.price), 0)                                  AS total_revenue,
            ROUND(AVG(fo.price), 2)                                  AS avg_order_value,
            ROUND(COUNTIF(fo.is_late) / COUNT(*) * 100, 1)           AS late_pct,
            ROUND(AVG(fr.review_score), 2)                           AS avg_review_score
        FROM `{MARTS}.fact_orders` fo
        JOIN `{MARTS}.dim_customers` dc ON fo.customer_id = dc.customer_id
        LEFT JOIN `{MARTS}.fact_reviews` fr ON fo.order_id = fr.order_id
            AND DATE(fr.review_creation_date) >= DATE(fo.order_purchase_timestamp)
        WHERE fo.order_status = 'delivered'
          AND fo.order_id NOT IN ({EXCL})
    """).iloc[0]

    repeat_pct = q(f"""
        SELECT ROUND(COUNTIF(total_orders > 1) / COUNT(*) * 100, 1) AS v
        FROM `{MARTS}.mart_customer_summary`
    """).iloc[0]['v']

    geo = q(f"""
        WITH cc AS (
            SELECT state, COUNT(DISTINCT customer_unique_id) AS customers
            FROM `{MARTS}.dim_customers` GROUP BY state
        ),
        sc AS (
            SELECT state, COUNT(DISTINCT seller_id) AS sellers
            FROM `{MARTS}.dim_sellers` GROUP BY state
        ),
        ds AS (
            SELECT dc.state,
                ROUND(AVG(fo.delivery_days), 1)             AS avg_delivery_days,
                ROUND(AVG(fo.freight_value), 2)             AS avg_freight,
                ROUND(COUNTIF(fo.is_late)/COUNT(*)*100, 1)  AS late_pct
            FROM `{MARTS}.fact_orders` fo
            JOIN `{MARTS}.dim_customers` dc ON fo.customer_id = dc.customer_id
            WHERE fo.order_status = 'delivered'
              AND fo.delivery_days IS NOT NULL
              AND fo.order_id NOT IN ({EXCL})
            GROUP BY dc.state
        ),
        hs AS (
            SELECT d.state, ROUND(AVG(h.health_score), 1) AS avg_health_score
            FROM `{MARTS}.mart_seller_health` h
            JOIN `{MARTS}.dim_sellers` d ON h.seller_id = d.seller_id
            GROUP BY d.state
        ),
        ch AS (
            SELECT state,
                ROUND(COUNTIF(total_orders = 1)/COUNT(*)*100, 1) AS churn_rate_pct
            FROM `{MARTS}.mart_customer_summary`
            GROUP BY state
        )
        SELECT cc.state, cc.customers,
            COALESCE(sc.sellers, 0) AS sellers,
            ROUND(cc.customers / NULLIF(COALESCE(sc.sellers,0), 0), 0) AS customer_per_seller,
            ds.avg_delivery_days, ds.avg_freight, ds.late_pct,
            hs.avg_health_score, ch.churn_rate_pct
        FROM cc
        LEFT JOIN sc USING (state)
        LEFT JOIN ds USING (state)
        LEFT JOIN hs USING (state)
        LEFT JOIN ch USING (state)
        WHERE cc.customers >= 100
        ORDER BY cc.customers DESC
    """)
    geo['lat'] = geo['state'].map(lambda s: STATE_COORDS.get(s, [0, 0])[0])
    geo['lng'] = geo['state'].map(lambda s: STATE_COORDS.get(s, [0, 0])[1])
    geo['name'] = geo['state'].map(STATE_NAMES).fillna(geo['state'])

    monthly = q(f"""
        SELECT
            FORMAT_DATE('%Y-%m', DATE(fo.order_purchase_timestamp)) AS month,
            COUNT(DISTINCT fo.order_id)                              AS orders,
            ROUND(SUM(fo.price), 0)                                  AS revenue,
            ROUND(AVG(fr.review_score), 2)                           AS avg_review
        FROM `{MARTS}.fact_orders` fo
        LEFT JOIN `{MARTS}.fact_reviews` fr ON fo.order_id = fr.order_id
            AND DATE(fr.review_creation_date) >= DATE(fo.order_purchase_timestamp)
        WHERE fo.order_status = 'delivered'
          AND fo.order_id NOT IN ({EXCL})
        GROUP BY month ORDER BY month
    """)

    rfm = q(f"""
        SELECT rfm_segment,
            COUNT(*) AS customers,
            ROUND(AVG(monetary), 2) AS avg_spend,
            ROUND(AVG(recency_days), 0) AS avg_recency_days,
            COUNTIF(campaign_type IS NOT NULL) AS actionable
        FROM `{MARTS}.mart_rfm_scores`
        GROUP BY rfm_segment
        ORDER BY AVG(rfm_score) DESC
    """)

    campaigns = q(f"""
        SELECT campaign_type, COUNT(*) AS customers,
               ROUND(AVG(monetary), 2) AS avg_spend
        FROM `{MARTS}.mart_rfm_scores`
        WHERE campaign_type IS NOT NULL
        GROUP BY campaign_type ORDER BY customers DESC
    """)

    cohort_raw = q(f"""
        SELECT FORMAT_DATE('%Y-%m', cohort_month) AS cohort_month,
               months_since_first, retention_rate_pct
        FROM `{MARTS}.mart_cohort_retention`
        ORDER BY cohort_month, months_since_first
    """)
    pivot = cohort_raw.pivot(
        index='cohort_month', columns='months_since_first', values='retention_rate_pct'
    )
    cohort = {
        'z': [[None if pd.isna(v) else round(float(v), 1) for v in row]
              for row in pivot.values.tolist()],
        'x': [int(c) for c in pivot.columns.tolist()],
        'y': list(pivot.index),
    }

    cats = q(f"""
        WITH first_cat AS (
            SELECT dc.customer_unique_id,
                   dp.product_category_name_english AS category
            FROM `{MARTS}.fact_orders` fo
            JOIN `{MARTS}.dim_customers` dc ON fo.customer_id = dc.customer_id
            JOIN `{MARTS}.dim_products`  dp ON fo.product_id  = dp.product_id
            WHERE fo.order_status = 'delivered'
              AND fo.order_id NOT IN ({EXCL})
              AND dp.product_category_name_english IS NOT NULL
            QUALIFY ROW_NUMBER() OVER (
                PARTITION BY dc.customer_unique_id
                ORDER BY fo.order_purchase_timestamp
            ) = 1
        )
        SELECT fc.category,
               COUNT(*) AS cohort_size,
               ROUND(COUNTIF(mcs.total_orders > 1)/COUNT(*)*100, 1) AS return_rate_pct
        FROM first_cat fc
        JOIN `{MARTS}.mart_customer_summary` mcs USING (customer_unique_id)
        GROUP BY fc.category
        HAVING COUNT(*) >= 50
        ORDER BY return_rate_pct DESC
        LIMIT 20
    """)

    health_scores = q(f"SELECT health_score FROM `{MARTS}.mart_seller_health`")

    health_summary = q(f"""
        SELECT health_tier, trend_status, COUNT(*) AS sellers
        FROM `{MARTS}.mart_seller_health`
        GROUP BY health_tier, trend_status
    """)

    intervention = q(f"""
        SELECT seller_id, state, city, health_score, health_tier,
               recent_health_score, score_delta, trend_status, intervention_reason
        FROM `{MARTS}.mart_seller_health`
        WHERE intervention_reason IS NOT NULL
        ORDER BY
            CASE trend_status WHEN 'declining' THEN 1 WHEN 'inactive' THEN 2 ELSE 3 END,
            health_score ASC
        LIMIT 100
    """)

    print('  Done.')

    def _f(v):
        return None if pd.isna(v) else float(v)

    return {
        'generated': datetime.datetime.now().strftime('%Y-%m-%d %H:%M'),
        'kpi': {
            'total_orders':     int(kpi.total_orders),
            'unique_customers': int(kpi.unique_customers),
            'total_revenue':    float(kpi.total_revenue),
            'avg_order_value':  float(kpi.avg_order_value),
            'late_pct':         float(kpi.late_pct),
            'avg_review_score': float(kpi.avg_review_score),
            'repeat_pct':       float(repeat_pct),
        },
        'geo': [
            {
                'state': r.state, 'name': r.name,
                'lat': float(r.lat), 'lng': float(r.lng),
                'customers': int(r.customers), 'sellers': int(r.sellers),
                'customer_per_seller': _f(r.customer_per_seller),
                'avg_delivery_days':   _f(r.avg_delivery_days),
                'avg_freight':         _f(r.avg_freight),
                'late_pct':            _f(r.late_pct),
                'avg_health_score':    _f(r.avg_health_score),
                'churn_rate_pct':      _f(r.churn_rate_pct),
            }
            for _, r in geo.iterrows()
        ],
        'monthly': [
            {'month': r.month, 'orders': int(r.orders),
             'revenue': float(r.revenue),
             'avg_review': _f(r.avg_review)}
            for _, r in monthly.iterrows()
        ],
        'rfm': [
            {'segment': r.rfm_segment, 'customers': int(r.customers),
             'avg_spend': float(r.avg_spend), 'avg_recency': float(r.avg_recency_days),
             'actionable': int(r.actionable)}
            for _, r in rfm.iterrows()
        ],
        'campaigns': [
            {'type': r.campaign_type, 'customers': int(r.customers),
             'avg_spend': float(r.avg_spend)}
            for _, r in campaigns.iterrows()
        ],
        'cohort': cohort,
        'cats': [
            {'category': r.category.replace('_', ' ').title(),
             'cohort_size': int(r.cohort_size),
             'return_rate_pct': float(r.return_rate_pct)}
            for _, r in cats.iterrows()
        ],
        'health_scores': [float(v) for v in health_scores['health_score'].dropna().tolist()],
        'health_summary': [
            {'tier': r.health_tier, 'trend': r.trend_status, 'sellers': int(r.sellers)}
            for _, r in health_summary.iterrows()
        ],
        'intervention': [
            {
                'seller_id':      r.seller_id[:12] + '…',
                'state':          r.state,
                'city':           r.city.title(),
                'health_score':   float(r.health_score),
                'health_tier':    r.health_tier,
                'recent_score':   _f(r.recent_health_score),
                'score_delta':    float(r.score_delta),
                'trend_status':   r.trend_status,
                'reason':         r.intervention_reason,
            }
            for _, r in intervention.iterrows()
        ],
    }


# ── HTML template (dark theme) ─────────────────────────────────────────────────
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Olist Intelligence Dashboard</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
:root {
  --bg:#080D1A; --surface:#0F172A; --surface2:#1E293B;
  --border:#1E293B; --border2:#334155;
  --cyan:#06B6D4; --cyan-d:#0891B2; --cyan-glow:rgba(6,182,212,.18);
  --purple:#8B5CF6;
  --text:#F1F5F9; --muted:#64748B;
  --shadow-sm:0 2px 12px rgba(0,0,0,.5);
  --shadow-md:0 8px 32px rgba(0,0,0,.6);
  --radius:10px; --transition:all .18s ease;
  --excellent:#10B981; --good:#F59E0B; --at-risk:#F97316; --critical:#EF4444;
  --stable:#3B82F6; --declining:#EF4444; --inactive:#64748B;
}
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
html,body{
  height:100%;overflow:hidden;
  font-family:'Inter','Segoe UI',system-ui,sans-serif;
  color:var(--text);background:var(--bg);
  -webkit-font-smoothing:antialiased;
}

/* ── HEADER ── */
header{
  height:64px;
  background:linear-gradient(90deg,#080D1A 0%,#0F172A 60%,#080D1A 100%);
  border-bottom:1px solid var(--border2);
  display:flex;align-items:center;justify-content:space-between;
  padding:0 24px;flex-shrink:0;z-index:1000;position:relative;
}
header::before{
  content:'';position:absolute;left:0;top:0;bottom:0;width:4px;
  background:linear-gradient(180deg,var(--cyan) 0%,var(--purple) 100%);
}
header h1{color:#fff;font-size:16px;font-weight:700;letter-spacing:-.2px;padding-left:8px}
header .sub{color:var(--muted);font-size:11px;margin-top:3px;padding-left:8px}
.meta{color:var(--muted);font-size:11px;text-align:right;line-height:1.6}
.meta span{color:var(--cyan);font-weight:600}

/* ── LAYOUT ── */
#layout{display:flex;height:calc(100vh - 64px)}

/* ── MAP PANEL ── */
#map-panel{width:38%;display:flex;flex-direction:column;border-right:1px solid var(--border)}
#map{flex:1}
#map-footer{background:var(--surface);padding:14px 16px;flex-shrink:0;border-top:1px solid var(--border)}
.mode-label{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.1em;margin-bottom:8px;font-weight:600}
.mode-btns{
  display:flex;flex-wrap:wrap;gap:0;margin-bottom:8px;
  border:1px solid var(--border2);border-radius:8px;overflow:hidden;
}
.mode-btn{
  flex:1;padding:7px 6px;
  border:none;border-right:1px solid var(--border2);
  background:transparent;color:var(--muted);font-size:11px;font-weight:500;
  cursor:pointer;transition:var(--transition);white-space:nowrap;
  font-family:'Inter',system-ui,sans-serif;
}
.mode-btn:last-child{border-right:none}
.mode-btn:hover{background:var(--surface2);color:var(--text)}
.mode-btn.active{background:var(--cyan);color:#fff;font-weight:700}
#mode-desc{color:#475569;font-size:10px;margin-bottom:10px;min-height:14px;font-style:italic;line-height:1.5}
#legend-title{color:var(--text);font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px}
#map-legend{display:flex;align-items:center;gap:8px}
.legend-bar{flex:1;height:6px;border-radius:4px}
.legend-labels{display:flex;justify-content:space-between;color:var(--muted);font-size:10px;margin-top:4px;font-weight:600}

/* ── DASHBOARD PANEL ── */
#dashboard{width:62%;display:flex;flex-direction:column;overflow:hidden;background:var(--bg)}
#tabs{
  display:flex;background:var(--surface);
  border-bottom:1px solid var(--border2);padding:0 20px;flex-shrink:0;
}
.tab{
  padding:16px 22px;border:none;background:none;
  font-size:11px;font-weight:600;color:var(--muted);cursor:pointer;
  border-bottom:2px solid transparent;margin-bottom:-1px;
  transition:color .15s,border-color .15s;
  text-transform:uppercase;letter-spacing:.09em;
  font-family:'Inter',system-ui,sans-serif;
}
.tab:hover{color:var(--text)}
.tab.active{color:var(--cyan);border-bottom-color:var(--cyan)}
#panes{flex:1;overflow-y:auto;padding:16px 20px;background:var(--bg)}
#panes::-webkit-scrollbar{width:4px}
#panes::-webkit-scrollbar-track{background:transparent}
#panes::-webkit-scrollbar-thumb{background:var(--border2);border-radius:4px}
.pane{display:none}
.pane.active{display:block;animation:fadeIn .2s ease}
@keyframes fadeIn{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}

/* ── CARDS ── */
.card{
  background:var(--surface);border:1px solid var(--border);
  border-radius:var(--radius);padding:18px 20px;margin-bottom:14px;
  transition:border-color .18s,box-shadow .18s;
}
.card:hover{border-color:var(--border2);box-shadow:var(--shadow-sm)}
.card-title{
  font-size:10px;font-weight:700;text-transform:uppercase;
  letter-spacing:.1em;color:var(--cyan);margin-bottom:14px;
}
.two-col{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px}

/* ── KPI CARDS ── */
.kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px}
.kpi-card{
  background:var(--surface);border:1px solid var(--border);
  border-left:3px solid var(--cyan);
  border-radius:var(--radius);padding:18px 20px;
  transition:transform .18s ease,box-shadow .18s ease,border-color .18s;
  cursor:default;
}
.kpi-card:hover{transform:translateY(-2px);box-shadow:0 0 24px var(--cyan-glow);border-color:var(--cyan)}
.kpi-v{font-size:30px;font-weight:800;color:#fff;line-height:1;letter-spacing:-.5px}
.kpi-l{font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:var(--cyan);margin-top:8px;font-weight:600}
.kpi-card.warn{border-left-color:var(--good)}
.kpi-card.warn:hover{box-shadow:0 0 24px rgba(245,158,11,.18);border-color:var(--good)}
.kpi-card.warn .kpi-l{color:var(--good)}
.kpi-card.good{border-left-color:var(--excellent)}
.kpi-card.good:hover{box-shadow:0 0 24px rgba(16,185,129,.18);border-color:var(--excellent)}
.kpi-card.good .kpi-l{color:var(--excellent)}
.kpi-card.danger{border-left-color:var(--critical)}
.kpi-card.danger .kpi-l{color:var(--critical)}

/* ── SELLER KPIs ── */
.seller-kpi-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px}

/* ── TABLE ── */
.tbl-controls{display:flex;gap:8px;margin-bottom:10px;align-items:center;flex-wrap:wrap}
.tbl-filter{
  padding:5px 14px;border-radius:20px;
  border:1px solid var(--border2);background:transparent;
  font-size:11px;color:var(--muted);cursor:pointer;
  transition:var(--transition);font-weight:500;
  font-family:'Inter',system-ui,sans-serif;
}
.tbl-filter:hover,.tbl-filter.active{background:var(--cyan);color:#fff;border-color:var(--cyan)}
.tbl-search{
  flex:1;padding:6px 12px;border-radius:8px;
  border:1px solid var(--border2);font-size:12px;outline:none;
  background:var(--surface2);color:var(--text);
  font-family:'Inter',system-ui,sans-serif;transition:border-color .15s;
}
.tbl-search::placeholder{color:var(--muted)}
.tbl-search:focus{border-color:var(--cyan);box-shadow:0 0 0 3px rgba(6,182,212,.15)}
.tbl-count{font-size:11px;color:var(--muted);white-space:nowrap}
#clear-state-filter{
  padding:5px 12px;border-radius:20px;
  border:1px solid var(--cyan);background:rgba(6,182,212,.1);
  color:var(--cyan);font-size:11px;cursor:pointer;font-weight:600;
  display:none;transition:var(--transition);
  font-family:'Inter',system-ui,sans-serif;
}
#clear-state-filter:hover{background:var(--cyan);color:#fff}
.tbl-scroll{overflow-x:auto;max-height:380px;overflow-y:auto}
table{width:100%;border-collapse:collapse;font-size:12px}
thead{position:sticky;top:0;z-index:2}
th{
  text-align:left;padding:9px 10px;
  background:var(--surface2);font-size:10px;
  text-transform:uppercase;letter-spacing:.07em;color:var(--muted);
  border-bottom:1px solid var(--border2);font-weight:700;
}
th.sortable{cursor:pointer;user-select:none}
th.sortable:hover{color:var(--cyan)}
.sort-icon{margin-left:4px;opacity:.4;font-size:9px}
th.sort-asc .sort-icon::after{content:'↑';opacity:1;color:var(--cyan)}
th.sort-desc .sort-icon::after{content:'↓';opacity:1;color:var(--cyan)}
th:not(.sort-asc):not(.sort-desc) .sort-icon::after{content:'↕'}
td{padding:8px 10px;border-bottom:1px solid var(--border);vertical-align:middle;color:var(--text)}
tr:nth-child(even) td{background:rgba(255,255,255,.02)}
tr:hover td{background:rgba(6,182,212,.05) !important}
.tr-declining td:first-child{border-left:3px solid var(--critical)}
.tr-inactive td:first-child{border-left:3px solid var(--inactive)}
.tr-stable td:first-child{border-left:3px solid var(--stable)}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600}
.badge-excellent{background:rgba(16,185,129,.15);color:#34D399}
.badge-good{background:rgba(245,158,11,.15);color:#FCD34D}
.badge-at_risk{background:rgba(249,115,22,.15);color:#FB923C}
.badge-critical{background:rgba(239,68,68,.15);color:#F87171}
.badge-declining{background:rgba(239,68,68,.15);color:#F87171}
.badge-inactive{background:rgba(100,116,139,.15);color:#94A3B8}
.badge-stable{background:rgba(59,130,246,.15);color:#93C5FD}
.delta-neg{color:var(--critical);font-weight:700}
.delta-pos{color:var(--excellent);font-weight:700}
.reason-text{color:var(--muted);font-size:11px;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

/* ── MAP ── */
.leaflet-tile-pane{filter:brightness(0.9)}
.leaflet-popup-content-wrapper{
  padding:0 !important;border-radius:10px !important;overflow:hidden;
  box-shadow:var(--shadow-md) !important;
  background:var(--surface2) !important;border:1px solid var(--border2) !important;
}
.leaflet-popup-tip{background:var(--surface2) !important}
.leaflet-popup-content{font-size:12px;line-height:1.6;margin:0 !important}
.popup-header{padding:10px 14px;color:#fff;font-weight:700;font-size:13px;line-height:1.3}
.popup-body{padding:10px 14px;background:var(--surface2)}
.popup-row{
  display:flex;justify-content:space-between;gap:16px;
  padding:3px 0;border-bottom:1px solid var(--border);
}
.popup-row:last-child{border-bottom:none}
.popup-label{color:var(--muted);font-size:11px}
.popup-val{font-weight:600;color:var(--text);font-size:11px}
</style>
</head>
<body>
<header>
  <div>
    <h1>Olist E-Commerce Intelligence</h1>
    <div class="sub">Seller Health &middot; Customer Retention &middot; Regional Analysis</div>
  </div>
  <div class="meta">
    <div>Olist Brazilian Dataset</div>
    <div id="gen-ts"><span></span></div>
  </div>
</header>

<div id="layout">

  <!-- LEFT: MAP -->
  <div id="map-panel">
    <div id="map"></div>
    <div id="map-footer">
      <div class="mode-label">Map View</div>
      <div class="mode-btns">
        <button class="mode-btn active" data-mode="customer_per_seller">Seller Gap</button>
        <button class="mode-btn" data-mode="avg_freight">Freight</button>
        <button class="mode-btn" data-mode="avg_delivery_days">Delivery</button>
        <button class="mode-btn" data-mode="avg_health_score">Health</button>
        <button class="mode-btn" data-mode="churn_rate_pct">Churn</button>
      </div>
      <div id="mode-desc"></div>
      <div id="legend-title"></div>
      <div id="map-legend">
        <div style="flex:1">
          <div class="legend-bar" id="legend-bar"></div>
          <div class="legend-labels"><span id="leg-min"></span><span id="leg-max"></span></div>
        </div>
      </div>
    </div>
  </div>

  <!-- RIGHT: DASHBOARD -->
  <div id="dashboard">
    <div id="tabs">
      <button class="tab active" data-tab="overview">Overview</button>
      <button class="tab" data-tab="customers">Customers</button>
      <button class="tab" data-tab="sellers">Seller Health</button>
    </div>

    <div id="panes">

      <!-- OVERVIEW -->
      <div class="pane active" id="pane-overview">
        <div class="kpi-grid" id="overview-kpis"></div>
        <div class="card">
          <div class="card-title">Monthly Revenue &amp; Review Score Trend</div>
          <div id="chart-monthly" style="height:290px"></div>
        </div>
      </div>

      <!-- CUSTOMERS -->
      <div class="pane" id="pane-customers">
        <div class="card">
          <div class="card-title">RFM Segmentation — Customer Base</div>
          <div id="chart-rfm" style="height:260px"></div>
        </div>
        <div class="card">
          <div class="card-title">Campaign Targets by Action Type</div>
          <div id="chart-campaign" style="height:200px"></div>
        </div>
        <div class="card">
          <div class="card-title">Cohort Retention Heatmap — % still active at month N</div>
          <div id="chart-cohort" style="height:380px"></div>
        </div>
        <div class="card">
          <div class="card-title">Repeat Purchase Rate by First-Order Category</div>
          <div id="chart-cats" style="height:380px"></div>
        </div>
      </div>

      <!-- SELLERS -->
      <div class="pane" id="pane-sellers">
        <div class="seller-kpi-grid" id="seller-kpis"></div>
        <div class="card">
          <div class="card-title">Health Score Distribution</div>
          <div id="chart-health-dist" style="height:240px"></div>
        </div>
        <div class="two-col">
          <div class="card">
            <div class="card-title">Sellers by Health Tier</div>
            <div id="chart-tier" style="height:220px"></div>
          </div>
          <div class="card">
            <div class="card-title">Seller Trend Status</div>
            <div id="chart-trend" style="height:220px"></div>
          </div>
        </div>
        <div class="card">
          <div class="card-title">Intervention List</div>
          <div class="tbl-controls">
            <button class="tbl-filter active" data-tf="all">All</button>
            <button class="tbl-filter" data-tf="declining">Declining</button>
            <button class="tbl-filter" data-tf="inactive">Inactive</button>
            <button id="clear-state-filter">&#x2715; Clear state</button>
            <input class="tbl-search" id="tbl-search" type="text" placeholder="Filter by state or city…">
            <span class="tbl-count" id="row-count"></span>
          </div>
          <div class="tbl-scroll">
            <table>
              <thead><tr>
                <th>Seller</th>
                <th>Location</th>
                <th class="sortable" data-sort="health_score">Health <span class="sort-icon"></span></th>
                <th class="sortable" data-sort="recent_score">Recent <span class="sort-icon"></span></th>
                <th class="sortable" data-sort="score_delta">Delta <span class="sort-icon"></span></th>
                <th>Trend</th>
                <th>Reason</th>
              </tr></thead>
              <tbody id="intervention-tbody"></tbody>
            </table>
          </div>
        </div>
      </div>

    </div>
  </div>

</div>

<script>
/*INLINE_DATA*/

// ── Plotly layout factory (dark theme) ───────────────────────────────────────
const PL = (extra={}) => Object.assign({
  margin:{l:56,r:16,t:28,b:48},
  paper_bgcolor:'#0F172A', plot_bgcolor:'#0F172A',
  font:{family:"'Inter',system-ui,sans-serif",color:'#F1F5F9',size:12},
  hoverlabel:{bgcolor:'#1E293B',font:{color:'#F1F5F9',family:"'Inter',system-ui,sans-serif",size:12},bordercolor:'#334155'},
  showlegend:true,
  legend:{font:{size:11},bgcolor:'transparent',bordercolor:'transparent'},
}, extra);
const PC = {displayModeBar:false, responsive:true};
const DARK_GRID = '#1E293B';
const DARK_LINE = '#334155';

// ── Color constants ──────────────────────────────────────────────────────────
const SEG_COLORS = {
  champions:'#10B981', loyal_customers:'#06B6D4', promising:'#8B5CF6',
  potential_loyalists:'#F59E0B', at_risk:'#F97316', lost:'#EF4444',
};
const CAMP_COLORS = {
  loyalty_reward:'#10B981', nurture:'#06B6D4',
  second_purchase:'#8B5CF6', winback:'#F97316', reactivation:'#EF4444',
};
const TIER_COLORS = {excellent:'#10B981', good:'#F59E0B', at_risk:'#F97316', critical:'#EF4444'};
const TREND_COLORS = {stable:'#3B82F6', declining:'#EF4444', inactive:'#64748B'};

// ── Map mode config ──────────────────────────────────────────────────────────
const MODES = {
  customer_per_seller:{label:'Seller Gap',     unit:'×',    dir:'bad',  grad:['#FEF9C3','#DC2626']},
  avg_freight:        {label:'Avg Freight',    unit:'R$',   dir:'bad',  grad:['#FEF9C3','#DC2626']},
  avg_delivery_days:  {label:'Avg Delivery',   unit:'d',    dir:'bad',  grad:['#FEF9C3','#DC2626']},
  avg_health_score:   {label:'Seller Health',  unit:'/100', dir:'good', grad:['#FEE2E2','#16A34A']},
  churn_rate_pct:     {label:'Churn Rate',     unit:'%',    dir:'bad',  grad:['#FEF9C3','#DC2626']},
};
const MODE_DESCS = {
  customer_per_seller:'Ratio of customers to sellers — higher means sellers are underserved.',
  avg_freight:        'Average freight cost per delivered order — higher flags costly regions.',
  avg_delivery_days:  'Average delivery time in days — higher values flag logistics gaps.',
  avg_health_score:   'Average seller health score (0–100) — lower scores identify at-risk regions.',
  churn_rate_pct:     'Customers with only one order (%) — higher means worse retention.',
};

// ── Utilities ────────────────────────────────────────────────────────────────
function lerpColor(c1, c2, t) {
  const h = c => [parseInt(c.slice(1,3),16), parseInt(c.slice(3,5),16), parseInt(c.slice(5,7),16)];
  const a = h(c1), b = h(c2);
  return `rgb(${Math.round(a[0]+(b[0]-a[0])*t)},${Math.round(a[1]+(b[1]-a[1])*t)},${Math.round(a[2]+(b[2]-a[2])*t)})`;
}

function countUp(el, endVal, formatter) {
  if (endVal == null || isNaN(+endVal)) return;
  const startTime = performance.now();
  const dur = 850;
  function step(now) {
    const t = Math.min((now - startTime) / dur, 1);
    const ease = 1 - Math.pow(1 - t, 3);
    el.textContent = formatter(endVal * ease);
    if (t < 1) requestAnimationFrame(step);
    else el.textContent = formatter(endVal);
  }
  requestAnimationFrame(step);
}

function fmt(n, prefix='', suffix='') {
  if (n >= 1e6) return prefix + (n/1e6).toFixed(1) + 'M' + suffix;
  if (n >= 1e3) return prefix + (n/1e3).toFixed(1) + 'K' + suffix;
  return prefix + n.toLocaleString() + suffix;
}

// ── Timestamp ────────────────────────────────────────────────────────────────
document.querySelector('#gen-ts span').textContent = 'Updated ' + D.generated;

// ── Map setup ────────────────────────────────────────────────────────────────
const map = L.map('map', {zoomControl:true, attributionControl:false}).setView([-15,-52],4);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  maxZoom:18, subdomains:'abcd'
}).addTo(map);

fetch('https://raw.githubusercontent.com/codeforgermany/click_that_hood/master/public/data/brazil-states.geojson')
  .then(r => r.json())
  .then(gj => {
    L.geoJSON(gj, {
      style:{color:'#475569', weight:0.8, fillOpacity:0, opacity:0.6},
      interactive:false
    }).addTo(map);
  }).catch(()=>{});

// ── Global state ─────────────────────────────────────────────────────────────
let currentMode = 'customer_per_seller';
let markers = [];
let stateFilter = null;
let sortState = {field:null, asc:false};
let tableFilter = 'all';
let tableSearch = '';

// ── Draw map markers ─────────────────────────────────────────────────────────
function drawMarkers(mode) {
  markers.forEach(m => map.removeLayer(m));
  markers = [];
  const cfg = MODES[mode];
  const vals = D.geo.map(s => s[mode]).filter(v => v !== null);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  const maxC = Math.max(...D.geo.map(s => s.customers));

  document.getElementById('legend-title').textContent = cfg.label;
  document.getElementById('leg-min').textContent = lo.toFixed(1) + cfg.unit;
  document.getElementById('leg-max').textContent = hi.toFixed(1) + cfg.unit;
  document.getElementById('legend-bar').style.background =
    `linear-gradient(to right,${cfg.grad[0]},${cfg.grad[1]})`;
  document.getElementById('mode-desc').textContent = MODE_DESCS[mode];

  // Find extreme state for highlight
  const extremeVal = cfg.dir === 'bad' ? hi : lo;

  D.geo.forEach(s => {
    const raw = s[mode];
    if (raw === null || s.lat === 0) return;
    const t = hi === lo ? 0.5 : (raw - lo) / (hi - lo);
    const col = lerpColor(cfg.grad[0], cfg.grad[1], t);
    const r = 8 + (s.customers / maxC) * 20;
    const isExtreme = raw === extremeVal;

    const pop = `
      <div class="popup-header" style="background:${col}">
        ${s.name} <span style="opacity:.75;font-size:11px;font-weight:500">(${s.state})</span>
      </div>
      <div class="popup-body">
        <div class="popup-row"><span class="popup-label">Customers</span><span class="popup-val">${s.customers.toLocaleString()}</span></div>
        <div class="popup-row"><span class="popup-label">Sellers</span><span class="popup-val">${s.sellers.toLocaleString()}</span></div>
        <div class="popup-row"><span class="popup-label">Customer / Seller</span><span class="popup-val">${s.customer_per_seller !== null ? s.customer_per_seller+'×' : '—'}</span></div>
        <div class="popup-row"><span class="popup-label">Avg Delivery</span><span class="popup-val">${s.avg_delivery_days !== null ? s.avg_delivery_days+'d' : '—'}</span></div>
        <div class="popup-row"><span class="popup-label">Avg Freight</span><span class="popup-val">${s.avg_freight !== null ? 'R$'+s.avg_freight : '—'}</span></div>
        <div class="popup-row"><span class="popup-label">Late Orders</span><span class="popup-val">${s.late_pct !== null ? s.late_pct+'%' : '—'}</span></div>
        <div class="popup-row"><span class="popup-label">Seller Health</span><span class="popup-val">${s.avg_health_score !== null ? s.avg_health_score+'/100' : '—'}</span></div>
        <div class="popup-row"><span class="popup-label">Churn Rate</span><span class="popup-val">${s.churn_rate_pct !== null ? s.churn_rate_pct+'%' : '—'}</span></div>
      </div>`;

    const m = L.circleMarker([s.lat, s.lng], {
      radius: r,
      color: isExtreme ? '#fff' : 'white',
      weight: isExtreme ? 2.5 : 1.5,
      fillColor: col,
      fillOpacity: 0.9,
    }).bindPopup(pop, {maxWidth:260});

    // Highlight on hover
    m.on('mouseover', function() { this.setStyle({weight:3, color:'#fff'}); });
    m.on('mouseout',  function() { this.setStyle({weight: isExtreme ? 2.5 : 1.5, color:'white'}); });

    // Click: filter intervention table by state
    m.on('click', function() {
      stateFilter = s.state;
      if (rendered['pane-sellers']) renderTable();
    });

    m.addTo(map);
    markers.push(m);

    // State label
    L.marker([s.lat, s.lng], {
      icon: L.divIcon({
        className:'', iconSize:[0,0],
        html:`<span style="font-size:9px;font-weight:700;color:#1E293B;text-shadow:0 0 3px #fff,0 0 3px #fff,0 0 3px #fff">${s.state}</span>`
      })
    }).addTo(map);
  });
}

document.querySelectorAll('.mode-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.mode-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentMode = btn.dataset.mode;
    drawMarkers(currentMode);
  });
});

drawMarkers(currentMode);

// ── Tab switching ─────────────────────────────────────────────────────────────
const rendered = {};
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.pane').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    const id = 'pane-' + tab.dataset.tab;
    document.getElementById(id).classList.add('active');
    if (!rendered[id]) { renderTab(tab.dataset.tab); rendered[id] = true; }
    map.invalidateSize();
  });
});

// ── Render dispatch ───────────────────────────────────────────────────────────
function renderTab(tab) {
  if (tab === 'overview')   renderOverview();
  if (tab === 'customers')  renderCustomers();
  if (tab === 'sellers')    renderSellers();
}

// ── Global renderTable (accessed by map click + seller renders) ───────────────
function renderTable() {
  let rows = [...D.intervention];

  if (sortState.field) {
    rows.sort((a, b) => {
      const va = a[sortState.field] ?? (sortState.asc ? Infinity : -Infinity);
      const vb = b[sortState.field] ?? (sortState.asc ? Infinity : -Infinity);
      return sortState.asc ? va - vb : vb - va;
    });
  }

  rows = rows
    .filter(r => tableFilter === 'all' || r.trend_status === tableFilter)
    .filter(r => !tableSearch
      || r.state.includes(tableSearch.toUpperCase())
      || r.city.toLowerCase().includes(tableSearch.toLowerCase()))
    .filter(r => !stateFilter || r.state === stateFilter);

  document.getElementById('row-count').textContent = rows.length + ' sellers';
  const clrBtn = document.getElementById('clear-state-filter');
  clrBtn.style.display = stateFilter ? 'inline-block' : 'none';
  if (stateFilter) clrBtn.textContent = '✕ ' + stateFilter;

  document.getElementById('intervention-tbody').innerHTML = rows.map(r => {
    const delta = r.score_delta !== null
      ? (r.score_delta > 0 ? '+' + r.score_delta.toFixed(1) : r.score_delta.toFixed(1))
      : '—';
    const dCls = r.score_delta < 0 ? 'delta-neg' : 'delta-pos';
    return `<tr class="tr-${r.trend_status}">
      <td style="font-size:10px;font-family:monospace;color:#64748B">${r.seller_id}</td>
      <td><strong>${r.state}</strong> · ${r.city}</td>
      <td>
        <span style="font-weight:700">${r.health_score}</span>
        <span class="badge badge-${r.health_tier}" style="margin-left:4px">${r.health_tier.replace(/_/g,' ')}</span>
      </td>
      <td>${r.recent_score !== null ? r.recent_score : '—'}</td>
      <td class="${dCls}">${delta}</td>
      <td><span class="badge badge-${r.trend_status}">${r.trend_status}</span></td>
      <td class="reason-text" title="${r.reason}">${r.reason}</td>
    </tr>`;
  }).join('');
}

// ── OVERVIEW ──────────────────────────────────────────────────────────────────
function renderOverview() {
  const K = D.kpi;
  const cards = [
    {raw:K.total_orders,     fmt:v=>fmt(v),           label:'Total Orders',         cls:''},
    {raw:K.unique_customers, fmt:v=>fmt(v),           label:'Unique Customers',     cls:''},
    {raw:K.total_revenue,    fmt:v=>fmt(v,'R$'),      label:'Total Revenue',        cls:''},
    {raw:K.avg_order_value,  fmt:v=>'R$'+v.toFixed(2),label:'Avg Order Value',     cls:''},
    {raw:K.repeat_pct,       fmt:v=>v.toFixed(1)+'%', label:'Repeat Purchase Rate', cls:'good'},
    {raw:K.late_pct,         fmt:v=>v.toFixed(1)+'%', label:'Late Delivery Rate',   cls:'warn'},
    {raw:K.avg_review_score, fmt:v=>v.toFixed(2)+' ★',label:'Avg Review Score',    cls:'good'},
  ];

  const grid = document.getElementById('overview-kpis');
  const row1 = cards.slice(0,4).map(c =>
    `<div class="kpi-card ${c.cls}"><div class="kpi-v">${c.fmt(c.raw)}</div><div class="kpi-l">${c.label}</div></div>`
  ).join('');
  const row2el = document.createElement('div');
  row2el.style.cssText = 'grid-column:1/-1;display:grid;grid-template-columns:repeat(3,1fr);gap:10px';
  row2el.innerHTML = cards.slice(4).map(c =>
    `<div class="kpi-card ${c.cls}"><div class="kpi-v">${c.fmt(c.raw)}</div><div class="kpi-l">${c.label}</div></div>`
  ).join('');
  grid.innerHTML = row1;
  grid.appendChild(row2el);

  // Count-up all .kpi-v elements
  grid.querySelectorAll('.kpi-v').forEach((el, i) => {
    const c = cards[i];
    if (c) countUp(el, c.raw, c.fmt);
  });

  // Monthly chart — area + line on dark background
  const months = D.monthly.map(m => m.month);
  const revs   = D.monthly.map(m => m.revenue);
  Plotly.newPlot('chart-monthly', [
    {
      type:'scatter', fill:'tozeroy',
      fillcolor:'rgba(6,182,212,0.12)',
      line:{color:'#06B6D4', width:2.5, shape:'spline'},
      x:months, y:revs, name:'Revenue (R$)', mode:'lines',
      yaxis:'y',
      hovertemplate:'%{x}<br><b>R$%{y:,.0f}</b><extra></extra>'
    },
    {
      type:'scatter', mode:'lines+markers',
      x:months, y:D.monthly.map(m => m.avg_review), name:'Avg Review ★',
      line:{color:'#10B981', width:2, shape:'spline'},
      marker:{size:4, color:'#10B981'},
      yaxis:'y2',
      hovertemplate:'%{x}<br><b>★ %{y:.2f}</b><extra></extra>'
    }
  ], PL({
    xaxis:{tickangle:-45, tickfont:{size:10}, color:DARK_LINE, gridcolor:DARK_GRID, linecolor:DARK_LINE},
    yaxis:{title:'Revenue (R$)', tickformat:',.0f', titlefont:{size:11}, gridcolor:DARK_GRID, color:DARK_LINE, linecolor:DARK_LINE, zerolinecolor:DARK_GRID},
    yaxis2:{title:'Review ★', overlaying:'y', side:'right', range:[1,5], tickfont:{size:10}, titlefont:{size:11}, showgrid:false, color:DARK_LINE},
    legend:{orientation:'h', y:1.1, font:{color:'#F1F5F9'}},
    margin:{l:64,r:56,t:28,b:72},
  }), PC);
}

// ── CUSTOMERS ────────────────────────────────────────────────────────────────
function renderCustomers() {
  // RFM → Treemap
  Plotly.newPlot('chart-rfm', [{
    type:'treemap',
    labels: D.rfm.map(r => r.segment.replace(/_/g,' ')),
    parents: D.rfm.map(() => ''),
    values: D.rfm.map(r => r.customers),
    marker:{
      colors: D.rfm.map(r => SEG_COLORS[r.segment]||'#64748B'),
      line:{color:'#080D1A', width:2},
      pad:{t:8,b:8,l:8,r:8},
    },
    texttemplate:'<b>%{label}</b><br>%{value:,}',
    textfont:{size:13, color:'#fff'},
    hovertemplate:'<b>%{label}</b><br>Customers: %{value:,}<br>Avg spend: R$%{customdata[0]:,.0f}<br>Avg recency: %{customdata[1]:.0f} days<extra></extra>',
    customdata: D.rfm.map(r => [r.avg_spend, r.avg_recency]),
    tiling:{packing:'squarify'},
  }], PL({
    margin:{l:0,r:0,t:0,b:0},
    showlegend:false,
    paper_bgcolor:'#0F172A',
    plot_bgcolor:'#0F172A',
  }), PC);

  // Campaign
  const camps = D.campaigns.map(c => c.type.replace(/_/g,' '));
  Plotly.newPlot('chart-campaign', [{
    type:'bar', orientation:'h',
    y:camps, x:D.campaigns.map(c => c.customers),
    marker:{color:D.campaigns.map(c => CAMP_COLORS[c.type]||'#64748B'), opacity:0.9},
    text:D.campaigns.map(c => c.customers.toLocaleString()),
    textposition:'outside', textfont:{size:10, color:'#F1F5F9'},
    hovertemplate:'<b>%{y}</b><br>%{x:,} customers<br>Avg spend: R$%{customdata:,.0f}<extra></extra>',
    customdata:D.campaigns.map(c => c.avg_spend)
  }], PL({
    xaxis:{title:'Customers Assigned', gridcolor:DARK_GRID, color:DARK_LINE, linecolor:DARK_LINE, zerolinecolor:DARK_GRID},
    yaxis:{autorange:'reversed', color:'#F1F5F9'},
    showlegend:false,
    margin:{l:120,r:70,t:16,b:48}
  }), PC);

  // Cohort heatmap — dark-adapted blue-cyan scale
  Plotly.newPlot('chart-cohort', [{
    type:'heatmap',
    z:D.cohort.z, x:D.cohort.x, y:D.cohort.y,
    colorscale:[[0,'#0F172A'],[0.2,'#134E4A'],[0.5,'#0891B2'],[1,'#06B6D4']],
    zmin:0, zmax:100,
    colorbar:{title:'%', len:0.8, thickness:12, tickfont:{size:10, color:'#F1F5F9'}, titlefont:{color:'#F1F5F9'}},
    hovertemplate:'Cohort: %{y}<br>Month +%{x}: <b>%{z:.1f}%</b><extra></extra>',
    xgap:1, ygap:1
  }], PL({
    xaxis:{title:'Months Since First Order', tickmode:'linear', color:DARK_LINE, gridcolor:DARK_GRID},
    yaxis:{title:'Acquisition Cohort', autorange:'reversed', tickfont:{size:10}, color:'#F1F5F9'},
    showlegend:false,
    margin:{l:72,r:60,t:16,b:52}
  }), PC);

  // Category repeat rate — dark cyan gradient
  const rates = D.cats.map(c => c.return_rate_pct);
  const rMin = Math.min(...rates), rMax = Math.max(...rates);
  const catColors = rates.map(r => lerpColor('#0C4A6E','#06B6D4', (r-rMin)/(rMax-rMin||1)));
  const catAvg = rates.reduce((a,b)=>a+b,0)/rates.length;

  Plotly.newPlot('chart-cats', [
    {
      type:'bar', orientation:'h',
      y:D.cats.map(c => c.category), x:rates,
      marker:{color:catColors, opacity:0.9},
      text:rates.map(r => r.toFixed(1)+'%'),
      textposition:'outside', textfont:{size:10, color:'#F1F5F9'},
      hovertemplate:'<b>%{y}</b><br>Repeat rate: %{x:.1f}%<br>Cohort: %{customdata:,}<extra></extra>',
      customdata:D.cats.map(c => c.cohort_size)
    },
    {
      type:'scatter', mode:'lines',
      x:[catAvg, catAvg],
      y:[D.cats[D.cats.length-1].category, D.cats[0].category],
      name:'Platform avg',
      line:{color:'#EF4444', dash:'dot', width:2},
      hovertemplate:`Platform avg: ${catAvg.toFixed(1)}%<extra></extra>`
    }
  ], PL({
    xaxis:{title:'Repeat Purchase Rate (%)', gridcolor:DARK_GRID, color:DARK_LINE, zerolinecolor:DARK_GRID},
    yaxis:{autorange:'reversed', tickfont:{size:10}, color:'#F1F5F9'},
    annotations:[{
      x:catAvg, xref:'x', y:D.cats[0].category, yref:'y',
      text:`avg ${catAvg.toFixed(1)}%`, showarrow:true,
      arrowhead:2, ax:30, ay:0,
      font:{color:'#EF4444', size:10}, arrowcolor:'#EF4444'
    }],
    showlegend:false,
    margin:{l:170,r:70,t:16,b:48}
  }), PC);
}

// ── SELLERS ──────────────────────────────────────────────────────────────────
function renderSellers() {
  const scores = D.health_scores;
  const total = scores.length;
  const needsAction = D.intervention.length;
  const avgScore = scores.reduce((a,b)=>a+b,0)/total;

  const sellerCards = [
    {raw:total,       fmt:v=>Math.round(v).toLocaleString(), label:'Total Sellers',          cls:''},
    {raw:needsAction, fmt:v=>Math.round(v).toLocaleString(), label:'Needing Intervention',   cls:'warn'},
    {raw:avgScore,    fmt:v=>v.toFixed(1)+' / 100',          label:'Avg Health Score',       cls:'good'},
  ];

  const skGrid = document.getElementById('seller-kpis');
  skGrid.innerHTML = sellerCards.map(c =>
    `<div class="kpi-card ${c.cls}"><div class="kpi-v">${c.fmt(c.raw)}</div><div class="kpi-l">${c.label}</div></div>`
  ).join('');
  skGrid.querySelectorAll('.kpi-v').forEach((el, i) => {
    const c = sellerCards[i];
    if (c) countUp(el, c.raw, c.fmt);
  });

  // Health score histogram — colored by tier on dark bg
  const binW = 5, numBins = 20;
  const binCounts = new Array(numBins).fill(0);
  scores.forEach(s => {
    const idx = Math.min(Math.floor(s / binW), numBins - 1);
    binCounts[idx]++;
  });
  const binCenters = Array.from({length:numBins}, (_,i) => i*binW + binW/2);
  const binColors  = binCenters.map(c => c < 40 ? '#EF4444' : c < 60 ? '#F97316' : c < 80 ? '#F59E0B' : '#10B981');
  const binLabels  = Array.from({length:numBins}, (_,i) => `${i*binW}–${i*binW+binW}`);

  Plotly.newPlot('chart-health-dist', [{
    type:'bar',
    x:binCenters, y:binCounts,
    width:binW * 0.88,
    marker:{color:binColors, opacity:0.9, line:{color:'#080D1A', width:0.5}},
    text:binLabels,
    hovertemplate:'Score %{text}<br><b>%{y} sellers</b><extra></extra>'
  }], PL({
    annotations:[
      {x:20,  y:1, yref:'paper', text:'critical',  showarrow:false, font:{size:10, color:'#EF4444'}},
      {x:50,  y:1, yref:'paper', text:'at-risk',   showarrow:false, font:{size:10, color:'#F97316'}},
      {x:70,  y:1, yref:'paper', text:'good',      showarrow:false, font:{size:10, color:'#F59E0B'}},
      {x:90,  y:1, yref:'paper', text:'excellent', showarrow:false, font:{size:10, color:'#10B981'}},
    ],
    shapes:[40,60,80].map((t,i) => ({
      type:'line', x0:t, x1:t, y0:0, y1:1, yref:'paper',
      line:{color:['#EF4444','#F97316','#10B981'][i], dash:'dash', width:1.5}
    })),
    xaxis:{title:'Health Score (0–100)', range:[0,100], gridcolor:DARK_GRID, color:DARK_LINE, linecolor:DARK_LINE, zerolinecolor:DARK_GRID},
    yaxis:{title:'Number of Sellers', gridcolor:DARK_GRID, color:DARK_LINE},
    showlegend:false, margin:{l:56,r:16,t:36,b:48}
  }), PC);

  // Tier donut
  const tierOrder = ['excellent','good','at_risk','critical'];
  const tierCounts = {};
  D.health_summary.forEach(r => { tierCounts[r.tier] = (tierCounts[r.tier]||0) + r.sellers; });
  const tierTotal = tierOrder.reduce((s,t) => s+(tierCounts[t]||0), 0);
  Plotly.newPlot('chart-tier', [{
    type:'pie', hole:0.65,
    labels: tierOrder.map(t => t.replace('_',' ')),
    values: tierOrder.map(t => tierCounts[t]||0),
    marker:{colors:tierOrder.map(t=>TIER_COLORS[t]), line:{color:'#080D1A', width:2}},
    textinfo:'percent',
    textfont:{size:11, color:'#fff'},
    hovertemplate:'<b>%{label}</b><br>%{value:,} sellers<br>%{percent}<extra></extra>',
    sort:false,
  }], PL({
    annotations:[{
      text:`<b>${tierTotal.toLocaleString()}</b><br><span style="font-size:9px">sellers</span>`,
      showarrow:false, font:{size:13, color:'#F1F5F9'}, x:0.5, y:0.5
    }],
    showlegend:true,
    legend:{orientation:'v', x:1.02, y:0.5, font:{size:11, color:'#F1F5F9'}},
    margin:{l:0,r:90,t:16,b:16},
  }), PC);

  // Trend donut
  const trendOrder = ['stable','declining','inactive'];
  const trendCounts = {};
  D.health_summary.forEach(r => { trendCounts[r.trend] = (trendCounts[r.trend]||0) + r.sellers; });
  Plotly.newPlot('chart-trend', [{
    type:'pie', hole:0.65,
    labels: trendOrder,
    values: trendOrder.map(t => trendCounts[t]||0),
    marker:{colors:trendOrder.map(t=>TREND_COLORS[t]), line:{color:'#080D1A', width:2}},
    textinfo:'percent',
    textfont:{size:11, color:'#fff'},
    hovertemplate:'<b>%{label}</b><br>%{value:,} sellers<br>%{percent}<extra></extra>',
    sort:false,
  }], PL({
    annotations:[{
      text:`<b>${total.toLocaleString()}</b><br><span style="font-size:9px">sellers</span>`,
      showarrow:false, font:{size:13, color:'#F1F5F9'}, x:0.5, y:0.5
    }],
    showlegend:true,
    legend:{orientation:'v', x:1.02, y:0.5, font:{size:11, color:'#F1F5F9'}},
    margin:{l:0,r:90,t:16,b:16},
  }), PC);

  // Table filter buttons
  document.querySelectorAll('.tbl-filter').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tbl-filter').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      tableFilter = btn.dataset.tf;
      renderTable();
    });
  });

  // Search
  document.getElementById('tbl-search').addEventListener('input', e => {
    tableSearch = e.target.value;
    renderTable();
  });

  // Clear state filter
  document.getElementById('clear-state-filter').addEventListener('click', () => {
    stateFilter = null;
    renderTable();
  });

  // Sortable column headers
  document.querySelectorAll('th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const field = th.dataset.sort;
      if (sortState.field === field) {
        sortState.asc = !sortState.asc;
      } else {
        sortState.field = field;
        sortState.asc = false;
      }
      document.querySelectorAll('th.sortable').forEach(t => {
        t.classList.remove('sort-asc','sort-desc');
      });
      th.classList.add(sortState.asc ? 'sort-asc' : 'sort-desc');
      renderTable();
    });
  });

  renderTable();
}

// ── Init ──────────────────────────────────────────────────────────────────────
renderTab('overview');
rendered['pane-overview'] = true;
</script>
</body>
</html>"""


def build_html(data: dict) -> str:
    data_json = json.dumps(data, cls=BQEncoder, ensure_ascii=False)
    return HTML_TEMPLATE.replace('/*INLINE_DATA*/', f'const D = {data_json};')


def main():
    data = fetch()
    html = build_html(data)
    OUT.write_text(html, encoding='utf-8')
    kb = OUT.stat().st_size // 1024
    print(f'Dashboard written → {OUT}  ({kb} KB)')
    print('Next steps:')
    print('  git add docs/index.html')
    print('  git commit -m "dashboard: v3 redesign"')
    print('  git push')
    print('  Live at: https://Maycoooz.github.io/olist-sandbox/')


if __name__ == '__main__':
    main()
