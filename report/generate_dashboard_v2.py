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
                'state': r.state, 'name': r['name'],
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


# ── HTML template (light theme, ECharts + AG Grid) ─────────────────────────────
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
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/ag-grid-community@31.3.4/styles/ag-grid.css"/>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/ag-grid-community@31.3.4/styles/ag-theme-alpine.css"/>
<style>
:root {
  --bg:#F4F6F9;
  --card:#FFFFFF;
  --border:#E4E7EC;
  --border2:#C8CDD6;
  --primary:#1D4ED8;
  --primary-l:rgba(29,78,216,.07);
  --primary-m:rgba(29,78,216,.14);
  --secondary:#059669;
  --amber:#D97706;
  --danger:#DC2626;
  --orange:#EA580C;
  --text:#101828;
  --text2:#344054;
  --muted:#667085;
  --radius:10px;
  --shadow-xs:0 1px 2px rgba(16,24,40,.05);
  --shadow-sm:0 1px 3px rgba(16,24,40,.08),0 1px 2px rgba(16,24,40,.04);
  --shadow-md:0 4px 8px rgba(16,24,40,.06),0 2px 4px rgba(16,24,40,.04);
  --nav-w:196px;
  --hdr-h:64px;
}
*,*::before,*::after{margin:0;padding:0;box-sizing:border-box}
html{font-size:14px}
body{font-family:'Inter',system-ui,sans-serif;background:var(--bg);color:var(--text);overflow:hidden;height:100vh;-webkit-font-smoothing:antialiased}

/* ── HEADER ─────────────────────────────────────────────────── */
#top-header{
  position:fixed;top:0;left:0;right:0;height:var(--hdr-h);z-index:200;
  background:#fff;border-bottom:1px solid var(--border);
  box-shadow:var(--shadow-xs);display:flex;align-items:stretch;
}
.hdr-brand{
  width:var(--nav-w);flex-shrink:0;
  display:flex;align-items:center;gap:12px;padding:0 20px;
  border-right:1px solid var(--border);
}
.hdr-mark{
  width:34px;height:34px;border-radius:8px;flex-shrink:0;
  background:linear-gradient(135deg,#1D4ED8 0%,#3B82F6 100%);
  display:flex;align-items:center;justify-content:center;
  font-weight:800;font-size:15px;color:#fff;letter-spacing:-1px;
}
.hdr-wordmark{display:flex;flex-direction:column}
.hdr-title{font-size:13px;font-weight:700;color:var(--text);letter-spacing:-.2px;line-height:1.2}
.hdr-sub{font-size:10px;color:var(--muted);font-weight:400;margin-top:1px}
#hdr-pills{display:flex;flex:1;align-items:stretch}
.hdr-kpi{
  display:flex;flex-direction:column;justify-content:center;
  padding:0 22px;border-right:1px solid var(--border);
  min-width:130px;
}
.hdr-kpi-val{font-size:16px;font-weight:700;color:var(--text);letter-spacing:-.3px;line-height:1.2}
.hdr-kpi-lbl{font-size:9px;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;margin-top:2px}
.hdr-meta{
  display:flex;flex-direction:column;justify-content:center;
  padding:0 24px;font-size:11px;color:var(--muted);text-align:right;
  border-left:1px solid var(--border);margin-left:auto;line-height:1.7;
}
.hdr-meta strong{color:var(--text2);font-weight:600}

/* ── LAYOUT ─────────────────────────────────────────────────── */
#app{position:relative}

/* ── SIDE NAV ───────────────────────────────────────────────── */
#side-nav{
  position:fixed;top:var(--hdr-h);left:0;bottom:0;width:var(--nav-w);z-index:100;
  background:#fff;border-right:1px solid var(--border);
  padding:20px 12px 16px;display:flex;flex-direction:column;gap:2px;overflow-y:auto;
}
.nav-group-lbl{
  font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.14em;
  color:var(--muted);padding:2px 12px 8px;margin-top:4px;
}
.nav-link{
  display:flex;align-items:center;gap:11px;
  padding:10px 12px;border-radius:8px;
  color:var(--muted);font-size:13px;font-weight:500;
  transition:all .12s;cursor:pointer;border:none;background:none;
  width:100%;text-align:left;font-family:'Inter',system-ui,sans-serif;
  position:relative;
}
.nav-link:hover{background:var(--bg);color:var(--text2)}
.nav-link.active{background:var(--primary-l);color:var(--primary);font-weight:600}
.nav-link.active::before{
  content:'';position:absolute;left:0;top:6px;bottom:6px;
  width:3px;border-radius:0 3px 3px 0;background:var(--primary);
}
.nav-icon{font-size:16px;flex-shrink:0;line-height:1}
#filter-panel{margin-top:auto;padding:16px 4px 0;border-top:1px solid var(--border)}
.filter-panel-lbl{font-size:9px;font-weight:700;text-transform:uppercase;letter-spacing:.12em;color:var(--muted);margin-bottom:8px}
#filter-list-text{font-size:11px;color:var(--muted);line-height:1.6}
#btn-clear-all{
  width:100%;margin-top:10px;padding:7px;border-radius:8px;
  border:1px solid var(--border2);background:#fff;color:var(--muted);
  font-size:11px;cursor:pointer;font-family:'Inter',system-ui,sans-serif;
  font-weight:500;transition:all .12s;display:none;
}
#btn-clear-all:hover{border-color:var(--danger);color:var(--danger);background:#FEF2F2}
#btn-clear-all.show{display:block}

/* ── SCROLL MAIN ────────────────────────────────────────────── */
#scroll-main{
  position:fixed;top:var(--hdr-h);left:var(--nav-w);right:0;bottom:0;
  overflow-y:auto;padding:32px 36px 72px;scroll-behavior:smooth;
}
#scroll-main::-webkit-scrollbar{width:4px}
#scroll-main::-webkit-scrollbar-track{background:transparent}
#scroll-main::-webkit-scrollbar-thumb{background:var(--border2);border-radius:4px}

/* ── SECTIONS ───────────────────────────────────────────────── */
section{margin-bottom:52px;scroll-margin-top:16px}
.sec-hdr{margin-bottom:22px;padding-bottom:16px;border-bottom:1px solid var(--border)}
.sec-title{font-size:19px;font-weight:700;color:var(--text);letter-spacing:-.4px}
.sec-sub{font-size:12px;color:var(--muted);margin-top:4px}

/* ── CARDS ──────────────────────────────────────────────────── */
.card{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--radius);padding:22px 24px;box-shadow:var(--shadow-sm);
}
.card-title{
  font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.08em;
  color:var(--muted);margin-bottom:18px;
  display:flex;align-items:center;gap:10px;
}
.card-title::after{content:'';flex:1;height:1px;background:var(--border)}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.g2-wide{display:grid;grid-template-columns:2fr 1fr;gap:16px}

/* ── KPI CARDS ──────────────────────────────────────────────── */
.kpi4{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:14px}
.kpi3{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:14px}
.kpi-card{
  background:var(--card);border:1px solid var(--border);border-radius:var(--radius);
  padding:20px 22px 18px;box-shadow:var(--shadow-sm);
  position:relative;overflow:hidden;transition:box-shadow .15s,transform .15s;
}
.kpi-card::after{
  content:'';position:absolute;bottom:0;left:0;right:0;height:3px;
  background:var(--primary);
}
.kpi-card.green::after{background:var(--secondary)}
.kpi-card.amber::after{background:var(--amber)}
.kpi-card.danger::after{background:var(--danger)}
.kpi-card:hover{transform:translateY(-1px);box-shadow:var(--shadow-md)}
.kpi-l{
  font-size:11px;font-weight:600;color:var(--muted);
  text-transform:uppercase;letter-spacing:.07em;margin-bottom:10px;
}
.kpi-v{
  font-size:32px;font-weight:800;color:var(--text);
  letter-spacing:-.8px;line-height:1;
}

/* ── MAP ────────────────────────────────────────────────────── */
#map{height:480px;border-radius:8px;overflow:hidden;border:1px solid var(--border)}
.map-btns{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px}
.map-btn{
  padding:6px 15px;border-radius:6px;
  border:1px solid var(--border);background:var(--bg);
  font-size:12px;font-weight:500;color:var(--muted);cursor:pointer;
  transition:all .12s;font-family:'Inter',system-ui,sans-serif;
}
.map-btn:hover{border-color:var(--primary);color:var(--primary);background:#fff}
.map-btn.active{
  background:var(--primary);color:#fff;border-color:var(--primary);
  font-weight:600;box-shadow:0 1px 4px rgba(29,78,216,.3);
}
.map-desc{font-size:11px;color:var(--muted);margin-bottom:14px;padding:8px 12px;background:var(--bg);border-radius:6px}
.geo-grid{display:grid;grid-template-columns:1fr 280px;gap:16px;align-items:start}
#state-detail{
  background:var(--card);border:1px solid var(--border);
  border-radius:var(--radius);padding:20px;box-shadow:var(--shadow-sm);min-height:180px;
}
.sd-name{font-size:15px;font-weight:700;color:var(--text);margin-bottom:2px}
.sd-sub{font-size:11px;color:var(--muted);margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid var(--border)}
.sd-row{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--border);font-size:12px}
.sd-row:last-child{border-bottom:none}
.sd-lbl{color:var(--muted)}
.sd-val{font-weight:600;color:var(--text);font-size:13px}
.sd-empty{color:var(--muted);font-size:12px;text-align:center;padding:36px 12px;line-height:1.9}
.leg-row{display:flex;align-items:center;gap:10px;margin-top:10px}
.leg-bar{flex:1;height:6px;border-radius:4px}
.leg-labels{display:flex;justify-content:space-between;font-size:10px;color:var(--muted);margin-top:4px;font-weight:600}

/* ── AG GRID ────────────────────────────────────────────────── */
.ag-theme-alpine{
  --ag-font-family:'Inter',system-ui,sans-serif;
  --ag-font-size:12px;
  --ag-header-background-color:#F9FAFB;
  --ag-odd-row-background-color:#FDFDFD;
  --ag-row-hover-color:rgba(29,78,216,.03);
  --ag-border-color:var(--border);
  --ag-header-foreground-color:var(--muted);
  --ag-cell-horizontal-padding:14px;
}
.ag-theme-alpine .ag-header-cell-label{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em}
#grid-bar{display:flex;gap:8px;margin-bottom:12px;align-items:center;flex-wrap:wrap}
.g-btn{
  padding:6px 16px;border-radius:6px;
  border:1px solid var(--border);background:var(--bg);
  font-size:11px;color:var(--muted);cursor:pointer;
  font-family:'Inter',system-ui,sans-serif;font-weight:500;transition:all .12s;
}
.g-btn:hover{background:#fff;color:var(--text2);border-color:var(--border2)}
.g-btn.active{background:var(--primary);color:#fff;border-color:var(--primary);box-shadow:0 1px 4px rgba(29,78,216,.3)}
#grid-count{font-size:11px;color:var(--muted);margin-left:auto;font-weight:500}
#active-chips{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:10px;min-height:4px}
.chip{
  display:flex;align-items:center;gap:5px;
  background:var(--primary-l);border:1px solid var(--primary-m);
  color:var(--primary);border-radius:6px;
  padding:4px 10px;font-size:11px;font-weight:600;cursor:pointer;
}
.chip:hover{background:#FEF2F2;border-color:rgba(220,38,38,.2);color:var(--danger)}

/* ── MAP POPUP ──────────────────────────────────────────────── */
.leaflet-popup-content-wrapper{border-radius:10px!important;box-shadow:var(--shadow-md)!important}
.leaflet-popup-content{font-family:'Inter',system-ui,sans-serif;font-size:12px;margin:0!important}
.pu-hdr{padding:12px 16px;font-weight:700;font-size:13px;border-radius:10px 10px 0 0;color:#fff}
.pu-body{padding:10px 16px}
.pu-row{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #F2F4F7;font-size:12px}
.pu-row:last-child{border-bottom:none}
.pu-lbl{color:#667085}
.pu-val{font-weight:600;color:#101828}
</style>
</head>
<body>

<header id="top-header">
  <div class="hdr-brand">
    <div class="hdr-mark">O</div>
    <div class="hdr-wordmark">
      <div class="hdr-title">Olist Intelligence</div>
      <div class="hdr-sub">E-Commerce Analytics</div>
    </div>
  </div>
  <div id="hdr-pills"></div>
  <div class="hdr-meta" id="hdr-meta"></div>
</header>

<div id="app">
  <nav id="side-nav">
    <div class="nav-group-lbl">Analytics</div>
    <button class="nav-link active" data-target="s-overview"><span class="nav-icon">&#128202;</span>Overview</button>
    <button class="nav-link" data-target="s-geo"><span class="nav-icon">&#127758;</span>Geographic</button>
    <button class="nav-link" data-target="s-customers"><span class="nav-icon">&#128100;</span>Customers</button>
    <button class="nav-link" data-target="s-sellers"><span class="nav-icon">&#128200;</span>Seller Health</button>
    <div id="filter-panel">
      <div class="filter-panel-lbl">Active Filters</div>
      <div id="filter-list-text">None</div>
      <button id="btn-clear-all" onclick="clearAllFilters()">Clear all filters</button>
    </div>
  </nav>

  <main id="scroll-main">

    <section id="s-overview">
      <div class="sec-hdr">
        <div class="sec-title">Business Overview</div>
        <div class="sec-sub">Platform-wide performance at a glance</div>
      </div>
      <div class="kpi4" id="kpi-top"></div>
      <div class="kpi3" id="kpi-bot"></div>
      <div class="card">
        <div class="card-title">Monthly Revenue &amp; Avg Review Score — drag the slider to zoom a time range</div>
        <div id="chart-monthly" style="height:340px"></div>
      </div>
    </section>

    <section id="s-geo">
      <div class="sec-hdr">
        <div class="sec-title">Geographic Intelligence</div>
        <div class="sec-sub">Click a state to filter the intervention table &amp; see regional detail</div>
      </div>
      <div class="card">
        <div class="map-btns">
          <button class="map-btn active" data-mode="customer_per_seller">Seller Gap</button>
          <button class="map-btn" data-mode="avg_freight">Freight Cost</button>
          <button class="map-btn" data-mode="avg_delivery_days">Delivery Days</button>
          <button class="map-btn" data-mode="avg_health_score">Seller Health</button>
          <button class="map-btn" data-mode="churn_rate_pct">Churn Rate</button>
        </div>
        <div class="map-desc" id="map-desc"></div>
        <div class="geo-grid">
          <div>
            <div id="map"></div>
            <div class="leg-row">
              <span style="font-size:10px;font-weight:600;color:var(--muted)" id="leg-min"></span>
              <div class="leg-bar" id="leg-bar"></div>
              <span style="font-size:10px;font-weight:600;color:var(--muted)" id="leg-max"></span>
            </div>
          </div>
          <div id="state-detail"><div class="sd-empty">&#128205; Click a state marker<br>on the map to see<br>regional details here</div></div>
        </div>
      </div>
    </section>

    <section id="s-customers">
      <div class="sec-hdr">
        <div class="sec-title">Customer Intelligence</div>
        <div class="sec-sub">RFM segments, cohort retention, campaign targeting, and acquisition quality</div>
      </div>
      <div class="g2">
        <div class="card">
          <div class="card-title">RFM Segments — Customer Count by Segment</div>
          <div id="chart-rfm" style="height:420px"></div>
        </div>
        <div class="card">
          <div class="card-title">Cohort Retention — % of customers still active at month N</div>
          <div id="chart-cohort" style="height:420px"></div>
        </div>
      </div>
      <div class="g2" style="margin-top:14px">
        <div class="card">
          <div class="card-title">Campaign Targets by Action Type</div>
          <div id="chart-campaign" style="height:340px"></div>
        </div>
        <div class="card">
          <div class="card-title">Repeat Purchase Rate by First-Order Category</div>
          <div id="chart-cats" style="height:340px"></div>
        </div>
      </div>
    </section>

    <section id="s-sellers">
      <div class="sec-hdr">
        <div class="sec-title">Seller Health</div>
        <div class="sec-sub">Health distribution, trend status, and intervention priority list</div>
      </div>
      <div class="kpi3" id="seller-kpis"></div>
      <div class="g2-wide" style="margin-bottom:14px">
        <div class="card">
          <div class="card-title">Health Score Distribution — drag to select a score range and filter the table below</div>
          <div id="chart-hist" style="height:280px"></div>
        </div>
        <div>
          <div class="card" style="margin-bottom:14px">
            <div class="card-title">By Health Tier</div>
            <div id="chart-tier" style="height:160px"></div>
          </div>
          <div class="card">
            <div class="card-title">By Trend Status</div>
            <div id="chart-trend" style="height:160px"></div>
          </div>
        </div>
      </div>
      <div class="card">
        <div class="card-title">Seller Intervention List</div>
        <div id="grid-bar">
          <button class="g-btn active" data-tf="all">All</button>
          <button class="g-btn" data-tf="declining">Declining</button>
          <button class="g-btn" data-tf="inactive">Inactive</button>
          <span id="grid-count"></span>
        </div>
        <div id="active-chips"></div>
        <div id="intervention-grid" class="ag-theme-alpine" style="height:420px"></div>
      </div>
    </section>

  </main>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/ag-grid-community@31.3.4/dist/ag-grid-community.min.noStyle.js"></script>
<script>
/*INLINE_DATA*/

// ── Colour constants ──────────────────────────────────────────────────────────
const SEG_CLR = {
  champions:'#1D4ED8', loyal_customers:'#10B981', promising:'#8B5CF6',
  potential_loyalists:'#F59E0B', at_risk:'#F97316', lost:'#EF4444'
};
const CAMP_CLR = {
  loyalty_reward:'#10B981', nurture:'#1D4ED8',
  second_purchase:'#8B5CF6', winback:'#F97316', reactivation:'#EF4444'
};
const TIER_CLR  = {excellent:'#10B981',good:'#F59E0B',at_risk:'#F97316',critical:'#EF4444'};
const TREND_CLR = {stable:'#1D4ED8',declining:'#EF4444',inactive:'#94A3B8'};
const MODES = {
  customer_per_seller:{ label:'Seller Gap',    unit:'x',    grad:['#EFF6FF','#1D4ED8'], desc:'Customer-to-seller ratio — higher means sellers are underserved in that region.' },
  avg_freight:        { label:'Avg Freight',   unit:'R$',   grad:['#FFF7ED','#C2410C'], desc:'Average freight cost per delivered order — higher values flag costly shipping regions.' },
  avg_delivery_days:  { label:'Avg Delivery',  unit:'d',    grad:['#FFF7ED','#C2410C'], desc:'Average days to deliver — higher values indicate logistics challenges.' },
  avg_health_score:   { label:'Seller Health', unit:'/100', grad:['#FEF2F2','#15803D'], desc:'Average seller health score — lower scores identify regions with at-risk sellers.' },
  churn_rate_pct:     { label:'Churn Rate',    unit:'%',    grad:['#FFF7ED','#C2410C'], desc:'Percentage of one-time customers — higher means worse retention in that region.' }
};

// ── Cross-filter state ────────────────────────────────────────────────────────
const F = { state:null, tier:null, trend:null, scoreMin:null, scoreMax:null, trendBtn:'all' };
let gridApi = null;
let mapMarkers = [];
let _chips = [];

// ── Utils ─────────────────────────────────────────────────────────────────────
function lerp(c1, c2, t) {
  const h = c => [parseInt(c.slice(1,3),16),parseInt(c.slice(3,5),16),parseInt(c.slice(5,7),16)];
  const a=h(c1),b=h(c2);
  return 'rgb('+[0,1,2].map(i=>Math.round(a[i]+(b[i]-a[i])*t)).join(',')+')';
}
function countUp(el, end, fmt) {
  if (end==null||isNaN(+end)){el.textContent=fmt(end);return}
  const dur=900,s=performance.now();
  const step=n=>{
    const t=Math.min((n-s)/dur,1),e=1-Math.pow(1-t,3);
    el.textContent=fmt(end*e);
    t<1?requestAnimationFrame(step):el.textContent=fmt(end);
  };
  requestAnimationFrame(step);
}
function fmt(n,pre='',suf=''){
  if(n>=1e6) return pre+(n/1e6).toFixed(1)+'M'+suf;
  if(n>=1e3) return pre+(n/1e3).toFixed(1)+'K'+suf;
  return pre+n.toLocaleString(undefined,{maximumFractionDigits:0})+suf;
}
function ec(id){return echarts.init(document.getElementById(id),null,{renderer:'canvas'})}

// ── Header ────────────────────────────────────────────────────────────────────
function initHeader(){
  const K=D.kpi;
  document.getElementById('hdr-meta').innerHTML='<strong>'+D.generated+'</strong><br>Olist Brazilian Dataset';
  const kpis=[
    {v:fmt(K.total_orders),l:'Total Orders'},
    {v:fmt(K.total_revenue,'R$'),l:'Total Revenue'},
    {v:'R$'+K.avg_order_value.toFixed(2),l:'Avg Order Value'},
    {v:K.avg_review_score.toFixed(2)+' ★',l:'Avg Review Score'}
  ];
  document.getElementById('hdr-pills').innerHTML=kpis.map(p=>
    '<div class="hdr-kpi"><div class="hdr-kpi-lbl">'+p.l+'</div><div class="hdr-kpi-val">'+p.v+'</div></div>'
  ).join('');
}

// ── Overview ──────────────────────────────────────────────────────────────────
function initOverview(){
  const K=D.kpi;
  function mkCards(id,cards){
    const el=document.getElementById(id);
    el.innerHTML=cards.map(c=>'<div class="kpi-card '+c.cls+'"><div class="kpi-l">'+c.lbl+'</div><div class="kpi-v">'+c.f(c.raw)+'</div></div>').join('');
    el.querySelectorAll('.kpi-v').forEach((v,i)=>countUp(v,cards[i].raw,cards[i].f));
  }
  mkCards('kpi-top',[
    {raw:K.total_orders,    f:v=>fmt(v),              lbl:'Total Orders',        cls:''},
    {raw:K.unique_customers,f:v=>fmt(v),              lbl:'Unique Customers',    cls:''},
    {raw:K.total_revenue,   f:v=>fmt(v,'R$'),         lbl:'Total Revenue',       cls:''},
    {raw:K.avg_order_value, f:v=>'R$'+v.toFixed(2),  lbl:'Avg Order Value',     cls:''},
  ]);
  mkCards('kpi-bot',[
    {raw:K.repeat_pct,      f:v=>v.toFixed(1)+'%',   lbl:'Repeat Purchase Rate',cls:'green'},
    {raw:K.late_pct,        f:v=>v.toFixed(1)+'%',   lbl:'Late Delivery Rate',  cls:'amber'},
    {raw:K.avg_review_score,f:v=>v.toFixed(2)+' ★',lbl:'Avg Review Score', cls:'green'},
  ]);

  const ch=ec('chart-monthly');
  ch.setOption({
    tooltip:{trigger:'axis',axisPointer:{type:'cross',crossStyle:{color:'#CBD5E1'}},
      formatter:ps=>{
        const r=ps.find(p=>p.seriesName==='Revenue'),s=ps.find(p=>p.seriesName==='Review Score');
        return '<b>'+ps[0].axisValue+'</b><br>'+(r?'Revenue: <b>R$'+Math.round(r.value).toLocaleString()+'</b><br>':'')+(s&&s.value?'Review: <b>★'+s.value.toFixed(2)+'</b>':'');
      }},
    legend:{data:['Revenue','Review Score'],top:4,right:16,textStyle:{fontSize:12,color:'#334155'}},
    grid:{left:64,right:64,top:44,bottom:60},
    xAxis:{type:'category',data:D.monthly.map(m=>m.month),
      axisLabel:{rotate:35,fontSize:10,color:'#94A3B8'},
      axisLine:{lineStyle:{color:'#E2E8F0'}},splitLine:{show:false}},
    yAxis:[
      {type:'value',name:'Revenue (R$)',nameTextStyle:{color:'#94A3B8',fontSize:10},
        axisLabel:{formatter:v=>v>=1e6?(v/1e6).toFixed(1)+'M':v>=1e3?(v/1e3).toFixed(0)+'K':v,fontSize:10,color:'#94A3B8'},
        splitLine:{lineStyle:{color:'#F1F5F9',type:'dashed'}}},
      {type:'value',name:'Review ★',min:1,max:5,nameTextStyle:{color:'#94A3B8',fontSize:10},
        axisLabel:{fontSize:10,color:'#94A3B8'},splitLine:{show:false}}
    ],
    dataZoom:[{type:'slider',height:20,bottom:8,
      fillerColor:'rgba(29,78,216,.08)',borderColor:'#E2E8F0',
      handleStyle:{color:'#1D4ED8'},textStyle:{color:'#94A3B8',fontSize:10}}],
    series:[
      {name:'Revenue',type:'line',smooth:true,yAxisIndex:0,
        data:D.monthly.map(m=>m.revenue),symbol:'none',
        lineStyle:{color:'#1D4ED8',width:2.5},itemStyle:{color:'#1D4ED8'},
        areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,
          colorStops:[{offset:0,color:'rgba(29,78,216,.18)'},{offset:1,color:'rgba(29,78,216,.01)'}]}}},
      {name:'Review Score',type:'line',smooth:true,yAxisIndex:1,
        data:D.monthly.map(m=>m.avg_review),
        lineStyle:{color:'#10B981',width:2},itemStyle:{color:'#10B981'},
        symbol:'circle',symbolSize:4}
    ]
  });
  window.addEventListener('resize',()=>ch.resize());
}

// ── Geographic ────────────────────────────────────────────────────────────────
function initGeo(){
  const map=L.map('map',{zoomControl:true,attributionControl:false}).setView([-15,-52],4);
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',{maxZoom:18,subdomains:'abcd'}).addTo(map);
  fetch('https://raw.githubusercontent.com/codeforgermany/click_that_hood/master/public/data/brazil-states.geojson')
    .then(r=>r.json()).then(gj=>{
      L.geoJSON(gj,{style:{color:'#CBD5E1',weight:1,fillOpacity:0.04,fillColor:'#1D4ED8',opacity:0.7},interactive:false}).addTo(map);
    }).catch(()=>{});

  function drawMarkers(mode){
    mapMarkers.forEach(m=>map.removeLayer(m));
    mapMarkers=[];
    const cfg=MODES[mode];
    const vals=D.geo.map(s=>s[mode]).filter(v=>v!=null);
    const lo=Math.min(...vals),hi=Math.max(...vals);
    const maxC=Math.max(...D.geo.map(s=>s.customers));
    document.getElementById('map-desc').textContent=cfg.desc;
    document.getElementById('leg-min').textContent=lo.toFixed(1)+cfg.unit;
    document.getElementById('leg-max').textContent=hi.toFixed(1)+cfg.unit;
    document.getElementById('leg-bar').style.background='linear-gradient(to right,'+cfg.grad[0]+','+cfg.grad[1]+')';
    D.geo.forEach(s=>{
      const raw=s[mode];
      if(raw==null||s.lat===0) return;
      const t=hi===lo?.5:(raw-lo)/(hi-lo);
      const col=lerp(cfg.grad[0],cfg.grad[1],t);
      const r=9+(s.customers/maxC)*22;
      const pop='<div class="pu-hdr" style="background:'+col+'">'+s.name+' <span style="opacity:.8;font-size:11px">('+s.state+')</span></div>'+
        '<div class="pu-body">'+
        '<div class="pu-row"><span class="pu-lbl">Customers</span><span class="pu-val">'+s.customers.toLocaleString()+'</span></div>'+
        '<div class="pu-row"><span class="pu-lbl">Sellers</span><span class="pu-val">'+s.sellers.toLocaleString()+'</span></div>'+
        '<div class="pu-row"><span class="pu-lbl">Cust / Seller</span><span class="pu-val">'+(s.customer_per_seller!=null?s.customer_per_seller+'x':'—')+'</span></div>'+
        '<div class="pu-row"><span class="pu-lbl">Avg Delivery</span><span class="pu-val">'+(s.avg_delivery_days!=null?s.avg_delivery_days+'d':'—')+'</span></div>'+
        '<div class="pu-row"><span class="pu-lbl">Avg Freight</span><span class="pu-val">'+(s.avg_freight!=null?'R$'+s.avg_freight:'—')+'</span></div>'+
        '<div class="pu-row"><span class="pu-lbl">Seller Health</span><span class="pu-val">'+(s.avg_health_score!=null?s.avg_health_score+'/100':'—')+'</span></div>'+
        '<div class="pu-row"><span class="pu-lbl">Churn Rate</span><span class="pu-val">'+(s.churn_rate_pct!=null?s.churn_rate_pct+'%':'—')+'</span></div>'+
        '</div>';
      const m=L.circleMarker([s.lat,s.lng],{radius:r,fillColor:col,color:'#fff',weight:1.5,fillOpacity:.88})
        .bindPopup(pop,{maxWidth:260});
      m.on('mouseover',function(){this.setStyle({weight:2.5,color:'#1D4ED8'})});
      m.on('mouseout', function(){this.setStyle({weight:1.5,color:'#fff'})});
      m.on('click',()=>{
        F.state=(F.state===s.state)?null:s.state;
        applyFilters();
        document.getElementById('state-detail').innerHTML=F.state?
          '<div class="sd-name">'+s.name+'</div><div class="sd-sub">'+s.state+' &middot; '+s.customers.toLocaleString()+' customers</div>'+
          ['Sellers|'+s.sellers.toLocaleString(),'Cust/Seller|'+(s.customer_per_seller!=null?s.customer_per_seller+'x':'—'),
           'Avg Delivery|'+(s.avg_delivery_days!=null?s.avg_delivery_days+'d':'—'),
           'Avg Freight|'+(s.avg_freight!=null?'R$'+s.avg_freight:'—'),
           'Seller Health|'+(s.avg_health_score!=null?s.avg_health_score+'/100':'—'),
           'Churn Rate|'+(s.churn_rate_pct!=null?s.churn_rate_pct+'%':'—')
          ].map(r=>{const[l,v]=r.split('|');return'<div class="sd-row"><span class="sd-lbl">'+l+'</span><span class="sd-val">'+v+'</span></div>'}).join(''):
          '<div class="sd-empty">&#128205; Click a state marker<br>on the map to see<br>regional details here</div>';
      });
      m.addTo(map);
      mapMarkers.push(m);
    });
  }

  document.querySelectorAll('.map-btn').forEach(btn=>{
    btn.addEventListener('click',()=>{
      document.querySelectorAll('.map-btn').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      drawMarkers(btn.dataset.mode);
    });
  });
  drawMarkers('customer_per_seller');
}

// ── Customers ─────────────────────────────────────────────────────────────────
function initCustomers(){
  // RFM bubble
  const rfmCh=ec('chart-rfm');
  const rfmData=[...D.rfm].sort((a,b)=>a.customers-b.customers);
  rfmCh.setOption({
    tooltip:{trigger:'axis',axisPointer:{type:'none'},
      formatter:ps=>{
        const r=D.rfm.find(r=>r.segment.replace(/_/g,' ')===ps[0].name);
        return '<b>'+ps[0].name+'</b><br>Customers: <b>'+ps[0].value.toLocaleString()+'</b>'+(r?'<br>Avg Spend: R$'+r.avg_spend.toFixed(2)+'<br>Avg Recency: '+r.avg_recency+' days':'');
      }},
    grid:{left:160,right:70,top:12,bottom:48},
    xAxis:{type:'value',
      name:'Customers',nameLocation:'middle',nameGap:28,
      nameTextStyle:{fontSize:11,color:'#94A3B8'},
      axisLabel:{fontSize:10,color:'#94A3B8',formatter:v=>v>=1000?(v/1000).toFixed(0)+'K':v},
      splitLine:{lineStyle:{color:'#F1F5F9'}}},
    yAxis:{type:'category',data:rfmData.map(r=>r.segment.replace(/_/g,' ')),
      axisLabel:{fontSize:11,color:'#334155',fontWeight:500}},
    series:[{type:'bar',barMaxWidth:32,
      data:rfmData.map(r=>({value:r.customers,itemStyle:{color:SEG_CLR[r.segment]||'#94A3B8',borderRadius:[0,4,4,0]}})),
      label:{show:true,position:'right',formatter:p=>p.value.toLocaleString(),fontSize:10,color:'#64748B'}}]
  });
  window.addEventListener('resize',()=>rfmCh.resize());

  // Cohort heatmap
  const cohCh=ec('chart-cohort');
  const flat=[];
  D.cohort.y.forEach((y,yi)=>D.cohort.x.forEach((x,xi)=>{const v=D.cohort.z[yi]?.[xi];if(v!=null)flat.push([xi,yi,v])}));
  cohCh.setOption({
    tooltip:{position:'top',formatter:p=>'<b>'+D.cohort.y[p.data[1]]+'</b><br>Month +'+D.cohort.x[p.data[0]]+': '+p.data[2].toFixed(1)+'%'},
    grid:{left:72,right:80,top:12,bottom:28},
    xAxis:{type:'category',data:D.cohort.x.map(x=>'+'+x+'mo'),axisLabel:{fontSize:9,color:'#94A3B8'},splitLine:{show:false}},
    yAxis:{type:'category',data:D.cohort.y,axisLabel:{fontSize:9,color:'#94A3B8'}},
    visualMap:{min:0,max:100,calculable:true,orient:'vertical',right:4,top:'center',
      inRange:{color:['#F8FAFC','#BFDBFE','#1D4ED8']},
      textStyle:{fontSize:9,color:'#94A3B8'},itemWidth:10,itemHeight:80,text:['100%','0%']},
    series:[{type:'heatmap',data:flat,emphasis:{itemStyle:{borderColor:'#1D4ED8',borderWidth:1}}}]
  });
  window.addEventListener('resize',()=>cohCh.resize());

  // Campaign bar
  const campCh=ec('chart-campaign');
  const campData=[...D.campaigns].reverse();
  campCh.setOption({
    tooltip:{trigger:'axis',axisPointer:{type:'none'},
      formatter:ps=>'<b>'+ps[0].name+'</b><br>'+ps[0].value.toLocaleString()+' customers<br>Avg spend: R$'+(campData.find(c=>c.type.replace(/_/g,' ')===ps[0].name)?.avg_spend.toFixed(2)||'—')},
    grid:{left:130,right:60,top:12,bottom:48},
    xAxis:{type:'value',
      name:'Customers Assigned',nameLocation:'middle',nameGap:28,
      nameTextStyle:{fontSize:11,color:'#94A3B8'},
      axisLabel:{fontSize:10,color:'#94A3B8',formatter:v=>v>=1000?(v/1000).toFixed(0)+'K':v},
      splitLine:{lineStyle:{color:'#F1F5F9'}}},
    yAxis:{type:'category',data:campData.map(c=>c.type.replace(/_/g,' ')),axisLabel:{fontSize:11,color:'#334155',fontWeight:500}},
    series:[{type:'bar',barMaxWidth:28,
      data:campData.map(c=>({value:c.customers,itemStyle:{color:CAMP_CLR[c.type]||'#94A3B8',borderRadius:[0,4,4,0]}})),
      label:{show:true,position:'right',formatter:p=>p.value.toLocaleString(),fontSize:10,color:'#64748B'}}]
  });
  window.addEventListener('resize',()=>campCh.resize());

  // Category repeat rate
  const catCh=ec('chart-cats');
  const rates=D.cats.map(c=>c.return_rate_pct);
  const catAvg=rates.reduce((a,b)=>a+b,0)/rates.length;
  const catRev=[...D.cats].reverse();
  catCh.setOption({
    tooltip:{trigger:'axis',axisPointer:{type:'none'},
      formatter:ps=>'<b>'+ps[0].name+'</b><br>Repeat rate: '+ps[0].value.toFixed(1)+'%<br>Cohort: '+(D.cats.find(c=>c.category===ps[0].name)?.cohort_size.toLocaleString()||'—')},
    grid:{left:170,right:60,top:12,bottom:30},
    xAxis:{type:'value',axisLabel:{formatter:v=>v+'%',fontSize:10,color:'#94A3B8'},splitLine:{lineStyle:{color:'#F1F5F9'}}},
    yAxis:{type:'category',data:catRev.map(c=>c.category),axisLabel:{fontSize:10,color:'#334155'}},
    series:[
      {type:'bar',barMaxWidth:20,
        data:catRev.map(c=>({value:c.return_rate_pct,itemStyle:{color:'#1D4ED8',opacity:.75,borderRadius:[0,4,4,0]}})),
        label:{show:true,position:'right',formatter:p=>p.value.toFixed(1)+'%',fontSize:9,color:'#64748B'}},
      {type:'line',markLine:{silent:true,symbol:'none',
        data:[{xAxis:catAvg,lineStyle:{color:'#EF4444',type:'dashed',width:1.5},
          label:{formatter:'avg '+catAvg.toFixed(1)+'%',position:'end',fontSize:10,color:'#EF4444'}}]}}
    ]
  });
  window.addEventListener('resize',()=>catCh.resize());
}

// ── Sellers ───────────────────────────────────────────────────────────────────
function initSellers(){
  const scores=D.health_scores;
  const total=scores.length;
  const avgScore=scores.reduce((a,b)=>a+b,0)/total;
  const skCards=[
    {raw:total,            f:v=>Math.round(v).toLocaleString(), lbl:'Total Sellers',       cls:''},
    {raw:D.intervention.length,f:v=>Math.round(v).toLocaleString(),lbl:'Need Intervention',cls:'amber'},
    {raw:avgScore,         f:v=>v.toFixed(1)+' / 100',          lbl:'Avg Health Score',    cls:'green'},
  ];
  const sg=document.getElementById('seller-kpis');
  sg.innerHTML=skCards.map(c=>'<div class="kpi-card '+c.cls+'"><div class="kpi-v">'+c.f(c.raw)+'</div><div class="kpi-l">'+c.lbl+'</div></div>').join('');
  sg.querySelectorAll('.kpi-v').forEach((el,i)=>countUp(el,skCards[i].raw,skCards[i].f));

  // Health histogram
  const BW=5,NB=20;
  const bins=new Array(NB).fill(0);
  scores.forEach(s=>{bins[Math.min(Math.floor(s/BW),NB-1)]++});
  const binLbls=Array.from({length:NB},(_,i)=>i*BW+'-'+(i+1)*BW);
  const binClrs=Array.from({length:NB},(_,i)=>{const c=i*BW+BW/2;return c<40?'#EF4444':c<60?'#F97316':c<80?'#F59E0B':'#10B981'});

  const histCh=ec('chart-hist');
  histCh.setOption({
    tooltip:{trigger:'axis',formatter:ps=>'Score '+ps[0].name+'<br><b>'+ps[0].value+' sellers</b>'},
    brush:{toolbox:['rect','clear'],xAxisIndex:0,brushStyle:{borderWidth:1,color:'rgba(29,78,216,.08)',borderColor:'#1D4ED8'}},
    toolbox:{feature:{brush:{type:['rect','clear']}},itemSize:14,right:8,top:4},
    grid:{left:52,right:24,top:36,bottom:44},
    xAxis:{type:'category',data:binLbls,axisLabel:{rotate:40,fontSize:9,color:'#94A3B8',interval:1},splitLine:{show:false}},
    yAxis:{type:'value',name:'Sellers',nameTextStyle:{fontSize:10,color:'#94A3B8'},axisLabel:{fontSize:10,color:'#94A3B8'},splitLine:{lineStyle:{color:'#F1F5F9'}}},
    series:[{
      type:'bar',barMaxWidth:32,
      data:bins.map((v,i)=>({value:v,itemStyle:{color:binClrs[i],borderRadius:[3,3,0,0]}})),
      markLine:{symbol:'none',silent:true,data:[40,60,80].map((t,i)=>({
        xAxis:binLbls.findIndex(l=>parseInt(l)===t),
        label:{formatter:['Critical','At-Risk','Good'][i],fontSize:9,color:['#EF4444','#F97316','#10B981'][i]},
        lineStyle:{color:['#EF4444','#F97316','#10B981'][i],type:'dashed',width:1.5}
      }))}
    }]
  });
  histCh.on('brushSelected',params=>{
    const sel=params.batch?.[0]?.selected?.[0];
    if(!sel||!sel.dataIndex.length){F.scoreMin=null;F.scoreMax=null;}
    else{F.scoreMin=sel.dataIndex[0]*BW;F.scoreMax=(sel.dataIndex[sel.dataIndex.length-1]+1)*BW;}
    applyFilters();
  });
  window.addEventListener('resize',()=>histCh.resize());

  // Tier donut
  const tierOrder=['excellent','good','at_risk','critical'];
  const tierC={};
  D.health_summary.forEach(r=>{tierC[r.tier]=(tierC[r.tier]||0)+r.sellers});
  const tierCh=ec('chart-tier');
  tierCh.setOption({
    tooltip:{trigger:'item',formatter:p=>'<b>'+p.name+'</b><br>'+p.value.toLocaleString()+' sellers ('+p.percent+'%)'},
    legend:{orient:'vertical',right:4,top:'middle',textStyle:{fontSize:10,color:'#64748B'},itemWidth:10,itemHeight:10},
    series:[{type:'pie',radius:['38%','70%'],center:['38%','50%'],
      data:tierOrder.map(t=>({name:t.replace('_',' '),value:tierC[t]||0,itemStyle:{color:TIER_CLR[t]}})),
      label:{formatter:'{b}\n{d}%',fontSize:10,color:'#334155'},labelLine:{length:6,length2:5}}]
  });
  tierCh.on('click','series',p=>{
    const t=p.name.replace(' ','_');
    F.tier=(F.tier===t)?null:t;
    applyFilters();
  });
  window.addEventListener('resize',()=>tierCh.resize());

  // Trend donut
  const trendOrder=['stable','declining','inactive'];
  const trendC={};
  D.health_summary.forEach(r=>{trendC[r.trend]=(trendC[r.trend]||0)+r.sellers});
  const trendCh=ec('chart-trend');
  trendCh.setOption({
    tooltip:{trigger:'item',formatter:p=>'<b>'+p.name+'</b><br>'+p.value.toLocaleString()+' sellers ('+p.percent+'%)'},
    legend:{orient:'vertical',right:4,top:'middle',textStyle:{fontSize:10,color:'#64748B'},itemWidth:10,itemHeight:10},
    series:[{type:'pie',radius:['38%','70%'],center:['38%','50%'],
      data:trendOrder.map(t=>({name:t,value:trendC[t]||0,itemStyle:{color:TREND_CLR[t]}})),
      label:{formatter:'{b}\n{d}%',fontSize:10,color:'#334155'},labelLine:{length:6,length2:5}}]
  });
  trendCh.on('click','series',p=>{
    F.trend=(F.trend===p.name)?null:p.name;
    applyFilters();
  });
  window.addEventListener('resize',()=>trendCh.resize());

  // AG Grid
  const TC={excellent:'#10B981',good:'#F59E0B',at_risk:'#F97316',critical:'#EF4444'};
  const TRC={stable:'#1D4ED8',declining:'#EF4444',inactive:'#94A3B8'};
  gridApi=agGrid.createGrid(document.getElementById('intervention-grid'),{
    columnDefs:[
      {field:'seller_id',headerName:'Seller ID',width:130,cellStyle:{fontFamily:'monospace',color:'#94A3B8',fontSize:'11px'}},
      {field:'state',headerName:'State',width:70},
      {field:'city',headerName:'City',width:130},
      {field:'health_score',headerName:'Health',width:120,sort:'asc',
        cellRenderer:p=>{
          const c=p.value<40?'#EF4444':p.value<60?'#F97316':p.value<80?'#F59E0B':'#10B981';
          const tc=TC[p.data.health_tier]||'#94A3B8';
          return '<span style="font-weight:700;color:'+c+'">'+p.value+'</span> <span style="background:'+tc+'18;color:'+tc+';padding:1px 7px;border-radius:10px;font-size:10px;font-weight:600">'+( p.data.health_tier||'').replace('_',' ')+'</span>';
        }},
      {field:'recent_score',headerName:'Recent',width:80,valueFormatter:p=>p.value??'—'},
      {field:'score_delta',headerName:'Delta',width:72,
        cellRenderer:p=>{
          if(p.value==null) return '—';
          const c=p.value<0?'#EF4444':'#10B981';
          return '<span style="color:'+c+';font-weight:700">'+(p.value>0?'+':'')+p.value.toFixed(1)+'</span>';
        }},
      {field:'trend_status',headerName:'Trend',width:95,
        cellRenderer:p=>{
          const c=TRC[p.value]||'#94A3B8';
          return '<span style="background:'+c+'18;color:'+c+';padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600">'+p.value+'</span>';
        }},
      {field:'reason',headerName:'Reason',flex:1,minWidth:160,cellStyle:{color:'#64748B',fontSize:'11px'}},
    ],
    rowData:D.intervention,
    defaultColDef:{resizable:true,sortable:true,filter:true},
    getRowStyle:p=>{const c={declining:'#EF4444',inactive:'#94A3B8',stable:'#1D4ED8'};return{borderLeft:'3px solid '+(c[p.data?.trend_status]||'#E2E8F0')}},
    rowHeight:44,headerHeight:40,animateRows:true,
  });

  document.querySelectorAll('.g-btn').forEach(btn=>{
    btn.addEventListener('click',()=>{
      document.querySelectorAll('.g-btn').forEach(b=>b.classList.remove('active'));
      btn.classList.add('active');
      F.trendBtn=btn.dataset.tf;
      applyFilters();
    });
  });
}

// ── Filter logic ──────────────────────────────────────────────────────────────
function applyFilters(){
  if(!gridApi) return;
  let rows=D.intervention;
  if(F.state) rows=rows.filter(r=>r.state===F.state);
  if(F.tier)  rows=rows.filter(r=>r.health_tier===F.tier);
  if(F.trend) rows=rows.filter(r=>r.trend_status===F.trend);
  if(F.trendBtn&&F.trendBtn!=='all') rows=rows.filter(r=>r.trend_status===F.trendBtn);
  if(F.scoreMin!=null) rows=rows.filter(r=>r.health_score>=F.scoreMin);
  if(F.scoreMax!=null) rows=rows.filter(r=>r.health_score<=F.scoreMax);
  gridApi.setGridOption('rowData',rows);
  document.getElementById('grid-count').textContent=rows.length+' sellers';
  _chips=[];
  if(F.state)  _chips.push({l:'State: '+F.state,       clr:()=>{F.state=null}});
  if(F.tier)   _chips.push({l:'Tier: '+F.tier.replace('_',' '),clr:()=>{F.tier=null}});
  if(F.trend)  _chips.push({l:'Trend: '+F.trend,       clr:()=>{F.trend=null}});
  if(F.scoreMin!=null) _chips.push({l:'Score: '+F.scoreMin+'-'+F.scoreMax,clr:()=>{F.scoreMin=null;F.scoreMax=null}});
  document.getElementById('active-chips').innerHTML=_chips.map((c,i)=>'<div class="chip" onclick="_chips['+i+'].clr();applyFilters()">x '+c.l+'</div>').join('');
  const hasF=_chips.length>0;
  document.getElementById('btn-clear-all').classList.toggle('show',hasF);
  document.getElementById('filter-list-text').textContent=hasF?_chips.map(c=>c.l).join(', '):'None';
}

function clearAllFilters(){
  F.state=null;F.tier=null;F.trend=null;F.scoreMin=null;F.scoreMax=null;F.trendBtn='all';
  document.querySelectorAll('.g-btn').forEach((b,i)=>b.classList.toggle('active',i===0));
  applyFilters();
}

// ── Scroll spy ────────────────────────────────────────────────────────────────
function initScrollSpy(){
  const links=document.querySelectorAll('.nav-link');
  const obs=new IntersectionObserver(entries=>{
    entries.forEach(e=>{
      if(e.isIntersecting)
        links.forEach(l=>l.classList.toggle('active',l.dataset.target===e.target.id));
    });
  },{root:document.getElementById('scroll-main'),threshold:.25});
  ['s-overview','s-geo','s-customers','s-sellers'].forEach(id=>{
    const el=document.getElementById(id);
    if(el) obs.observe(el);
  });
  links.forEach(l=>l.addEventListener('click',()=>{
    const t=document.getElementById(l.dataset.target);
    if(t) t.scrollIntoView({behavior:'smooth'});
  }));
}

// ── Init ──────────────────────────────────────────────────────────────────────
initHeader();
initOverview();
initGeo();
initCustomers();
initSellers();
initScrollSpy();
document.getElementById('grid-count').textContent=D.intervention.length+' sellers';
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
    print('  git commit -m "dashboard: v3 redesign — light theme, ECharts, AG Grid"')
    print('  git push')
    print('  Live at: https://Maycoooz.github.io/olist-sandbox/')


if __name__ == '__main__':
    main()
