"""
Great Expectations — Olist RAW Layer Validation v2
Project: olist-498903
Dataset: olist_raw

Purpose: Detect anomalies in raw data BEFORE dbt transformation.
Results document what needs to be cleaned in dbt staging.

Run:
    conda activate m2
    cd ~/ELT_olist
    python ge_olist_raw_v2.py
"""

import great_expectations as gx
import pandas as pd
from sqlalchemy import create_engine
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT  = "olist-498903"
DATASET  = "olist_raw"
KEYFILE  = "/home/wanjz/ELT_olist/olist-498903-e7f8763e517a.json"
LOCATION = "US"

CONNECTION = (
    f"bigquery://{PROJECT}/{DATASET}"
    f"?credentials_path={KEYFILE}&location={LOCATION}"
)

BRAZIL_STATES = [
    "AC","AL","AM","AP","BA","CE","DF","ES","GO",
    "MA","MG","MS","MT","PA","PB","PE","PI","PR",
    "RJ","RN","RO","RR","RS","SC","SE","SP","TO"
]

def load_table(table_name: str) -> pd.DataFrame:
    engine = create_engine(CONNECTION)
    with engine.connect() as conn:
        df = pd.read_sql(
            f"SELECT * FROM `{PROJECT}.{DATASET}.{table_name}`", conn
        )
    print(f"  Loaded {table_name}: {len(df):,} rows")
    return df

context = gx.get_context(mode="ephemeral")
results_summary = []

def run_suite(suite_name: str, df: pd.DataFrame, expectation_fns: list):
    datasource = context.data_sources.add_pandas(name=f"ds_{suite_name}")
    data_asset = datasource.add_dataframe_asset(name=f"asset_{suite_name}")
    batch_def  = data_asset.add_batch_definition_whole_dataframe(
        name=f"batch_{suite_name}"
    )
    context.suites.add(gx.ExpectationSuite(name=suite_name))
    batch = batch_def.get_batch(batch_parameters={"dataframe": df})

    passed = failed = 0
    failures = []

    for fn in expectation_fns:
        expectation = fn()
        result = batch.validate(expectation)
        if result.success:
            passed += 1
        else:
            failed += 1
            failures.append({
                "expectation": type(expectation).__name__,
                "result": result.result,
            })

    summary = {
        "suite":    suite_name,
        "rows":     len(df),
        "passed":   passed,
        "failed":   failed,
        "failures": failures,
        "success":  failed == 0,
    }
    results_summary.append(summary)
    return summary

from great_expectations.expectations import (
    ExpectTableRowCountToBeBetween,
    ExpectColumnValuesToBeBetween,
    ExpectColumnValuesToBeInSet,
    ExpectColumnValuesToNotBeNull,
    ExpectColumnValuesToBeUnique,
    ExpectColumnUniqueValueCountToBeBetween,
    ExpectColumnValueLengthsToEqual,
    ExpectColumnMeanToBeBetween,
)

# ── Load all tables upfront ───────────────────────────────────────────────────
print("\n── Loading all raw tables ──")
raw_orders    = load_table("public_orders")
raw_payments  = load_table("public_order_payments")
raw_reviews   = load_table("public_order_reviews")
raw_items     = load_table("public_order_items")
raw_customers = load_table("public_customers")
raw_sellers   = load_table("public_sellers")
raw_products  = load_table("public_products")
raw_geo       = load_table("public_geolocation")

# ── Parse timestamps for time-based checks ───────────────────────────────────
raw_orders["order_purchase_timestamp"]      = pd.to_datetime(raw_orders["order_purchase_timestamp"], errors="coerce", utc=True)
raw_orders["order_delivered_customer_date"] = pd.to_datetime(raw_orders["order_delivered_customer_date"], errors="coerce", utc=True)
raw_orders["order_estimated_delivery_date"] = pd.to_datetime(raw_orders["order_estimated_delivery_date"], errors="coerce", utc=True)
raw_reviews["review_creation_date"]         = pd.to_datetime(raw_reviews["review_creation_date"], errors="coerce", utc=True)

# ══════════════════════════════════════════════════════════════════════════════
# GE SUITES
# ══════════════════════════════════════════════════════════════════════════════
print("\n── Running GE suites ──")

run_suite("public_orders", raw_orders, [
    lambda: ExpectTableRowCountToBeBetween(min_value=90_000, max_value=110_000),
    lambda: ExpectColumnValuesToNotBeNull(column="order_id"),
    lambda: ExpectColumnValuesToBeUnique(column="order_id"),
    lambda: ExpectColumnValuesToNotBeNull(column="customer_id"),
    lambda: ExpectColumnValuesToNotBeNull(column="order_status"),
    lambda: ExpectColumnValuesToBeInSet(
        column="order_status",
        value_set=["delivered","shipped","canceled","unavailable",
                   "invoiced","processing","approved","created"]
    ),
    lambda: ExpectColumnValuesToNotBeNull(column="order_purchase_timestamp"),
    lambda: ExpectColumnValuesToNotBeNull(column="order_estimated_delivery_date"),
])

run_suite("public_order_payments", raw_payments, [
    lambda: ExpectTableRowCountToBeBetween(min_value=100_000, max_value=120_000),
    lambda: ExpectColumnValuesToNotBeNull(column="order_id"),
    lambda: ExpectColumnValuesToNotBeNull(column="payment_type"),
    lambda: ExpectColumnValuesToBeInSet(
        column="payment_type",
        value_set=["credit_card","boleto","voucher","debit_card","not_defined"]
    ),
    lambda: ExpectColumnValuesToNotBeNull(column="payment_value"),
    lambda: ExpectColumnValuesToBeBetween(
        column="payment_value", min_value=0, max_value=15_000, mostly=0.99
    ),
    lambda: ExpectColumnValuesToBeBetween(
        column="payment_installments", min_value=0, max_value=24, mostly=0.99
    ),
])

run_suite("public_order_reviews", raw_reviews, [
    lambda: ExpectTableRowCountToBeBetween(min_value=90_000, max_value=110_000),
    lambda: ExpectColumnValuesToNotBeNull(column="review_id"),
    lambda: ExpectColumnValuesToNotBeNull(column="order_id"),
    lambda: ExpectColumnValuesToNotBeNull(column="review_score"),
    lambda: ExpectColumnValuesToBeInSet(
        column="review_score", value_set=[1, 2, 3, 4, 5]
    ),
    lambda: ExpectColumnMeanToBeBetween(
        column="review_score", min_value=3.5, max_value=5.0
    ),
])

run_suite("public_order_items", raw_items, [
    lambda: ExpectTableRowCountToBeBetween(min_value=100_000, max_value=130_000),
    lambda: ExpectColumnValuesToNotBeNull(column="order_id"),
    lambda: ExpectColumnValuesToNotBeNull(column="product_id"),
    lambda: ExpectColumnValuesToNotBeNull(column="seller_id"),
    lambda: ExpectColumnValuesToNotBeNull(column="price"),
    lambda: ExpectColumnValuesToBeBetween(
        column="price", min_value=0.01, max_value=7_000, mostly=0.99
    ),
    lambda: ExpectColumnValuesToNotBeNull(column="freight_value"),
    lambda: ExpectColumnValuesToBeBetween(
        column="freight_value", min_value=0, max_value=500, mostly=0.99
    ),
])

run_suite("public_customers", raw_customers, [
    lambda: ExpectTableRowCountToBeBetween(min_value=90_000, max_value=110_000),
    lambda: ExpectColumnValuesToNotBeNull(column="customer_id"),
    lambda: ExpectColumnValuesToBeUnique(column="customer_id"),
    lambda: ExpectColumnValuesToNotBeNull(column="customer_zip_code_prefix"),
    lambda: ExpectColumnValuesToNotBeNull(column="customer_state"),
    lambda: ExpectColumnValuesToBeInSet(
        column="customer_state", value_set=BRAZIL_STATES
    ),
])

run_suite("public_sellers", raw_sellers, [
    lambda: ExpectTableRowCountToBeBetween(min_value=2_000, max_value=5_000),
    lambda: ExpectColumnValuesToNotBeNull(column="seller_id"),
    lambda: ExpectColumnValuesToBeUnique(column="seller_id"),
    lambda: ExpectColumnValuesToNotBeNull(column="seller_state"),
    lambda: ExpectColumnValuesToBeInSet(
        column="seller_state", value_set=BRAZIL_STATES
    ),
])

run_suite("public_products", raw_products, [
    lambda: ExpectTableRowCountToBeBetween(min_value=30_000, max_value=40_000),
    lambda: ExpectColumnValuesToNotBeNull(column="product_id"),
    lambda: ExpectColumnValuesToBeUnique(column="product_id"),
    lambda: ExpectColumnValuesToBeBetween(
        column="product_weight_g", min_value=1, max_value=40_000, mostly=0.95
    ),
])

# ══════════════════════════════════════════════════════════════════════════════
# CUSTOM ANOMALY CHECKS
# ══════════════════════════════════════════════════════════════════════════════
print("\n── Running custom anomaly checks ──")
anomalies = []

def add(check, count, action, severity=None):
    if severity is None:
        severity = "High" if count > 1000 else "Medium" if count > 50 else "Low"
    anomalies.append({
        "check": check, "count": count,
        "action": action, "severity": severity
    })
    icon = "✗" if count > 0 else "✓"
    print(f"  {icon}  {check}: {count}")

# ── PAYMENT ANOMALIES ─────────────────────────────────────────────────────────
add("Zero or negative payment_value",
    int((raw_payments["payment_value"] <= 0).sum()),
    "Flag in dbt staging, exclude from payment analysis")

add("Payment > R$5,000 (potential fraud)",
    int((raw_payments["payment_value"] > 5_000).sum()),
    "Flag for fraud review, retain in data")

add("Installments > 12 (Brazil norm exceeded)",
    int((raw_payments["payment_installments"] > 12).sum()),
    "Flag in dbt staging, investigate")

add("Orders with no payment record",
    int(len(set(raw_orders["order_id"]) - set(raw_payments["order_id"]))),
    "Exclude from payment analysis")

add("Orders with > 5 payment methods",
    int((raw_payments.groupby("order_id")["payment_sequential"].max() > 5).sum()),
    "Flag as unusual payment behaviour")

# Payment vs item price mismatch
# total payment per order vs sum of (price + freight) per order
order_payment_total = raw_payments.groupby("order_id")["payment_value"].sum()
order_item_total = raw_items.groupby("order_id").apply(
    lambda x: (x["price"] + x["freight_value"]).sum()
)
merged = pd.DataFrame({
    "payment_total": order_payment_total,
    "item_total": order_item_total
}).dropna()
mismatch = (abs(merged["payment_total"] - merged["item_total"]) > 1.0).sum()
add("Payment vs item price mismatch (diff > R$1)",
    int(mismatch),
    "Expected — installment interest and vouchers cause legitimate differences")

# ── ORDER / DELIVERY ANOMALIES ────────────────────────────────────────────────
delivered = raw_orders[raw_orders["order_status"] == "delivered"]

add("Delivered orders with missing delivery timestamp",
    int(delivered["order_delivered_customer_date"].isna().sum()),
    "Exclude from delivery time calculations, flag is_missing_delivery_ts")

# Delivery before purchase (time inversion)
time_inversion = (
    raw_orders["order_delivered_customer_date"] <
    raw_orders["order_purchase_timestamp"]
).sum()
add("Delivery timestamp before purchase timestamp",
    int(time_inversion),
    "Data error — exclude from delivery analysis")

# Estimated delivery before purchase
bad_estimate = (
    raw_orders["order_estimated_delivery_date"] <
    raw_orders["order_purchase_timestamp"]
).sum()
add("Estimated delivery date before purchase date",
    int(bad_estimate),
    "Data error — exclude from delivery analysis")

# Duplicate order_ids
add("Duplicate order_id in orders",
    int(raw_orders["order_id"].duplicated().sum()),
    "Deduplicate in dbt staging")

# ── REVIEW ANOMALIES ──────────────────────────────────────────────────────────
add("Null review scores",
    int(raw_reviews["review_score"].isna().sum()),
    "Retain, exclude from satisfaction metrics only")

# Review before order purchase
reviews_merged = raw_reviews.merge(
    raw_orders[["order_id","order_purchase_timestamp"]],
    on="order_id", how="left"
)
review_before_order = (
    reviews_merged["review_creation_date"] <
    reviews_merged["order_purchase_timestamp"]
).sum()
add("Review creation date before order purchase date",
    int(review_before_order),
    "Data error — flag and exclude from time-based analysis")

# Same order reviewed multiple times by same customer
dup_reviews = raw_reviews.groupby("order_id")["review_id"].nunique()
multi_reviews = (dup_reviews > 1).sum()
add("Orders with multiple distinct reviews",
    int(multi_reviews),
    "Known Olist data issue — use composite key (review_id, order_id)")

# ── PRODUCT ANOMALIES ─────────────────────────────────────────────────────────
add("Products with weight = 0 or null",
    int((raw_products["product_weight_g"].isna() |
         (raw_products["product_weight_g"] == 0)).sum()),
    "Flag — weight used in freight calculations")

add("Products with zero dimensions (length/height/width)",
    int(((raw_products["product_length_cm"] == 0) |
         (raw_products["product_height_cm"] == 0) |
         (raw_products["product_width_cm"] == 0)).sum()),
    "Flag — dimensions used in freight calculations")

# ── SELLER ANOMALIES (critical for our analysis) ──────────────────────────────
# Orphan sellers in order_items not in sellers table
seller_ids_items   = set(raw_items["seller_id"].unique())
seller_ids_sellers = set(raw_sellers["seller_id"].unique())
orphan_sellers = len(seller_ids_items - seller_ids_sellers)
add("Sellers in order_items not in sellers table (orphan sellers)",
    orphan_sellers,
    "Will be lost on JOIN — document count for analysis coverage")

# Sellers with only 1 order — health score unreliable
seller_order_count = raw_items.groupby("seller_id")["order_id"].nunique()
single_order_sellers = (seller_order_count == 1).sum()
add("Sellers with only 1 order (health score unreliable)",
    int(single_order_sellers),
    "Exclude from seller health score calculation — insufficient sample size")

# ── CUSTOMER ANOMALIES (critical for our analysis) ────────────────────────────
# Orphan customers in orders not in customers table
customer_ids_orders    = set(raw_orders["customer_id"].unique())
customer_ids_customers = set(raw_customers["customer_id"].unique())
orphan_customers = len(customer_ids_orders - customer_ids_customers)
add("Customers in orders not in customers table (orphan customers)",
    orphan_customers,
    "Will be lost on JOIN — document count for analysis coverage")

# customer_unique_id to customer_id ratio (Olist known design)
unique_id_count = raw_customers["customer_unique_id"].nunique()
customer_id_count = raw_customers["customer_id"].nunique()
multi_id_customers = customer_id_count - unique_id_count
add("customer_unique_id with multiple customer_ids (repeat buyers)",
    int(multi_id_customers),
    "Expected Olist design — use customer_unique_id for repeat purchase analysis")

# ── GEOLOCATION COVERAGE ──────────────────────────────────────────────────────
geo_zips      = set(raw_geo["geolocation_zip_code_prefix"].astype(str).str.zfill(5).unique())
customer_zips = set(raw_customers["customer_zip_code_prefix"].astype(str).str.zfill(5).unique())
seller_zips   = set(raw_sellers["seller_zip_code_prefix"].astype(str).str.zfill(5).unique())

missing_customer_geo = len(customer_zips - geo_zips)
missing_seller_geo   = len(seller_zips - geo_zips)

add("Customer zip codes missing from geolocation table",
    missing_customer_geo,
    "These customers will have NULL lat/lng — cannot appear on map")

add("Seller zip codes missing from geolocation table",
    missing_seller_geo,
    "These sellers will have NULL lat/lng — cannot appear on map")

# ══════════════════════════════════════════════════════════════════════════════
# FINAL REPORT
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "═" * 70)
print("  GREAT EXPECTATIONS — OLIST RAW LAYER VALIDATION REPORT v2")
print(f"  Run at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("═" * 70)

total_passed = total_failed = 0
for r in results_summary:
    status = "✓ PASS" if r["success"] else "✗ FAIL"
    print(f"\n  {status}  {r['suite']}")
    print(f"         Rows: {r['rows']:,}  |  {r['passed']} passed, {r['failed']} failed")
    if r["failures"]:
        for f in r["failures"]:
            print(f"         ✗ {f['expectation']}")
    total_passed += r["passed"]
    total_failed += r["failed"]

print(f"\n  GE Expectations: {total_passed} passed, {total_failed} failed")

# Group anomalies by category
categories = [
    ("Payment Anomalies",     lambda a: "payment" in a["check"].lower() or "installment" in a["check"].lower()),
    ("Order / Delivery",      lambda a: "deliver" in a["check"].lower() or "order" in a["check"].lower() or "timestamp" in a["check"].lower() or "duplicate" in a["check"].lower()),
    ("Review Anomalies",      lambda a: "review" in a["check"].lower()),
    ("Product Anomalies",     lambda a: "product" in a["check"].lower() or "weight" in a["check"].lower() or "dimension" in a["check"].lower()),
    ("Seller Anomalies",      lambda a: "seller" in a["check"].lower()),
    ("Customer Anomalies",    lambda a: "customer" in a["check"].lower()),
    ("Geolocation Coverage",  lambda a: "zip" in a["check"].lower() or "geo" in a["check"].lower()),
]

printed = set()
for cat_name, cat_fn in categories:
    cat_items = [a for a in anomalies if cat_fn(a) and a["check"] not in printed]
    if cat_items:
        print(f"\n  ── {cat_name} ──")
        for a in cat_items:
            icon = "✗" if a["count"] > 0 else "✓"
            sev  = f"[{a['severity']}]" if a["count"] > 0 else ""
            print(f"  {icon}  {a['check']}: {a['count']} {sev}")
            print(f"       → {a['action']}")
            printed.add(a["check"])

print("\n  Note: Anomalies in raw data are EXPECTED.")
print("  Each is documented here and handled in dbt staging.")
print("  See schema.yml for cleaning rules and flags.")

print("\n" + "═" * 70)
print(f"  GE SUITE RESULT: {'ALL PASSED ✓' if total_failed == 0 else 'SOME FAILED ✗'}")
print("═" * 70 + "\n")
