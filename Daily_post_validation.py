import requests
from datetime import datetime, timedelta, timezone
import pandas as pd

ACCESS_TOKEN = "EAAD70HM0dlEBSAGngbr7fIVLX9OMGqw2ldT46V0ohMuZAZAroAZANBQ38hNxtwSW2plctlscJSSSCfik4QgPsAFQ4zRVhZCAu0lYsa4CoPymGPu7bXJXcpfCmfGUXt1c8eAZCId6owZCDtbGlPPG4iwEhwrIRnaZC95hdJX5D4RI4c8x7a55GLqlsdelxeemJwXhAIS"






def extract_post_insight_values(data):

    result = {}

    for metric in data.get("data", []):

        metric_name = metric["name"]

        values = metric.get("values", [])

        if values:
            result[metric_name] = values[0]["value"]
        else:
            result[metric_name] = 0

    return result




def get_instagram_post_insights(
        media_id,
        access_token,
        metrics
):
    url = f"https://graph.facebook.com/v26.0/{media_id}/insights"

    params = {
        "access_token": access_token,
        "metric": ",".join(metrics)
    }

    response = requests.get(
        url,
        params=params,
        timeout=30
    )

    response.raise_for_status()

    return response.json()





instagram_id = "17841408107333098"

metrics = [
    "views",
    "reach",
    "likes",
    "comments",
    "saved",
    "shares",
    "total_interactions",
    "reposts"
]


      # Load big query99 data
bq_file = "BQ_Data/sqllab_untitled_query_1_20260831T080253.csv"

bq_df = pd.read_csv(bq_file)


  # filter data for specific date range
bq_df["Post_Date"] = pd.to_datetime(
    bq_df["Post_Date"]
)

start_date = pd.Timestamp("2026-07-01")
end_date = pd.Timestamp("2026-08-10")

bq_df = bq_df[
    (bq_df["Post_Date"] >= start_date) &
    (bq_df["Post_Date"] <= end_date)
].copy()

# Remove timestamp AFTER filtering
bq_df["Post_Date"] = bq_df["Post_Date"].dt.date

# BQ column name -> API metric name
metric_mapping = {
    "Reach": "reach",
    "Views": "views",
    "Total_Interactions": "total_interactions",
    "Likes": "likes",
    "Comments": "comments",
    "Saves": "saved",
    "Shares": "shares",
    "Reel_Reposts": "reposts"
}



all_records = []

for _, row in bq_df.iterrows():

    media_id = str(row["Media_ID"])

    print(f"Fetching insights for Media_ID: {media_id}")

    media_data = get_instagram_post_insights(
        media_id=media_id,
        access_token=ACCESS_TOKEN,
        metrics=metrics
    )

    api_values = extract_post_insight_values(media_data)

    for bq_column, api_metric in metric_mapping.items():

        record = {
            "Instagram_ID": instagram_id,
            "Media_ID": media_id,
            "Post_Date": row["Post_Date"],
            "Metric": api_metric,

            "API_Value": api_values.get(
                api_metric,
                None
            ),

            "BQ_Value": row[bq_column]
        }

        all_records.append(record)

post_api_df = pd.DataFrame(all_records)


# Replace null-like values in BQ_Value with 0
post_api_df["BQ_Value"] = (
    post_api_df["BQ_Value"]
    .replace(["null", "NULL", "Null", "", "None"], 0)
    .fillna(0)
)

# Convert BQ_Value to numeric
post_api_df["BQ_Value"] = pd.to_numeric(
    post_api_df["BQ_Value"],
    errors="coerce"
).fillna(0)





# ============================================================
# DIFFERENCE
# ============================================================

post_api_df["Difference"] = (
    post_api_df["API_Value"] -
    post_api_df["BQ_Value"]
)


# ============================================================
# DIFFERENCE %
# ============================================================

post_api_df["Difference_%"] = (
    post_api_df["Difference"].abs()
    .div(post_api_df["BQ_Value"].abs())
    .mul(100)
)

# BQ value is 0 → blank
post_api_df.loc[
    post_api_df["BQ_Value"].eq(0),
    "Difference_%"
] = None

# Both BQ and API are null → 0%
# post_api_df.loc[
#     post_api_df["BQ_Value"].isna() & post_api_df["API_Value"].isna(),
#     "Difference_%"
# ] = 0

# API and BQ values are equal → 0%
post_api_df.loc[
    post_api_df["API_Value"].eq(post_api_df["BQ_Value"]),
    "Difference_%"
] = 0

# Round percentage to 2 decimal places
post_api_df["Difference_%"] = post_api_df["Difference_%"].round(2)

# ============================================================
# STATUS
# ============================================================

post_api_df["Status"] = post_api_df.apply(
    lambda row:
        "VALIDATED"
        if row["API_Value"] == row["BQ_Value"]
        else "ISSUE",
    axis=1
)

# ============================================================
# FINAL COLUMN ORDER
# ============================================================

validation_df = post_api_df[
    [
        "Instagram_ID",
        "Media_ID",
        "Post_Date",
        "Metric",
        "API_Value",
        "BQ_Value",
        "Difference",
        "Difference_%",
        "Status"
    ]
]


# Sort by date and metric
validation_df = validation_df.sort_values(
    ["Post_Date", "Media_ID", "Metric"]
)


# ============================================================
# SAVE EXCEL
# ============================================================

validation_df.to_excel(
    "instagram_post_validation_report_17841408107333098.xlsx",
    index=False
)

print("Validation report created successfully.")





