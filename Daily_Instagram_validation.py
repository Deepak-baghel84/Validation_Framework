import requests
from datetime import datetime, timedelta, timezone
import pandas as pd

ACCESS_TOKEN = "EAAD70HM0dlEBSAGngbr7fIVLX9OMGqw2ldT46V0ohMuZAZAroAZANBQ38hNxtwSW2plctlscJSSSCfik4QgPsAFQ4zRVhZCAu0lYsa4CoPymGPu7bXJXcpfCmfGUXt1c8eAZCId6owZCDtbGlPPG4iwEhwrIRnaZC95hdJX5D4RI4c8x7a55GLqlsdelxeemJwXhAIS"





def unix_conversion(current_date):

    next_date = current_date + timedelta(days=1)

    since = int(current_date.timestamp())
    until = int(next_date.timestamp())

    return since, until

    # print("\nPostman values:")
    # print("since =", since)
    # print("until =", until)
    #
    # print("\nIST:")
    # print("Start:", date_ist)
    # print("End:  ", date_ist + timedelta(days=1))
def extract_insight_values(api_response, instagram_id, date):
    rows = []

    for item in api_response.get("data", []):

        metric = item.get("name")

        total_value = item.get("total_value", {})
        value = total_value.get("value")

        rows.append({
            "Instagram_ID": instagram_id,
            "Date": date.strftime("%Y-%m-%d"),
            "Metric": metric,
            "API_Value": value
        })

    return rows

def get_instagram_insights(
    instagram_id,
    access_token,
    since,
    until,
    metrics
):
    """
    Fetch Instagram daily insights from Meta Graph API.

    Parameters
    ----------
    instagram_id : str
        Instagram Business/Creator account ID.

    access_token : str
        Meta API access token.

    since : int
        Unix timestamp for the start of the period.

    until : int
        Unix timestamp for the end of the period.

    metrics : list[str]
        List of Instagram insight metrics.

    Returns
    -------
    dict
        Raw JSON response from Meta API.
    """

    url = f"https://graph.facebook.com/v26.0/{instagram_id}/insights"

    params = {
        "access_token": access_token,
        "since": since,
        "until": until,
        "metric": ",".join(metrics),
        "metric_type": "total_value",
        "period": "day"
    }

    response = requests.get(
        url,
        params=params,
        timeout=30
    )

    # Raise an exception if Meta returns 4xx/5xx
    response.raise_for_status()

    return response.json()



start_date = datetime.strptime("01-07-2026", "%d-%m-%Y")
end_date = datetime.strptime("31-07-2026", "%d-%m-%Y")


instagram_id = "17841408107333098"

metrics = [
    "reach",
    "views",
    "accounts_engaged",
    "total_interactions",
    "likes",
    "comments",
    "saves",
    "shares",
    "profile_links_taps",
    "replies",
    "reposts"
]

results = []

current_date = start_date

while current_date <= end_date:

    # Convert current date into Unix timestamps
    since, until = unix_conversion(current_date)

    print(
        f"Fetching data for "
        f"{current_date.strftime('%d-%m-%Y')}"
    )

    # Call Meta API
    data = get_instagram_insights(
        instagram_id=instagram_id,
        access_token=ACCESS_TOKEN,
        since=since,
        until=until,
        metrics=metrics
    )

    # Extract metric values
    values = extract_insight_values(data,instagram_id,current_date)


    # Add date and IG ID
    results.extend(values)



    # Move to next day
    current_date += timedelta(days=1)




api_df = pd.DataFrame(results)

# ============================================================
# BIGQUERY DATA
# ============================================================

bq_file = "BQ_Data/sqllab_untitled_query_1_20260827T105714.csv"

bq_df = pd.read_csv(bq_file)


# BQ column name -> API metric name
bq_metric_mapping = {
    "Reach_Day": "reach",
    "Views_Day": "views",
    "Accounts_Engaged_Day": "accounts_engaged",
    "Total_Interactions_Day": "total_interactions",
    "Likes_Day": "likes",
    "Comments_Day": "comments",
    "Saves_Day": "saves",
    "Shares_Day": "shares",
    "Profile_Links_Taps_Day": "profile_links_taps",
    "Replies_Day": "replies",
    "Reposts_Day": "reposts"
}


# Convert BQ wide format -> long format
bq_long = bq_df.melt(
    id_vars=["Activity_Date"],
    value_vars=list(bq_metric_mapping.keys()),
    var_name="BQ_Metric",
    value_name="BQ_Value"
)


# Convert BQ metric names to API metric names
bq_long["Metric"] = bq_long["BQ_Metric"].map(
    bq_metric_mapping
)


# Convert date
bq_long["Date"] = pd.to_datetime(
    bq_long["Activity_Date"]
).dt.strftime("%Y-%m-%d")


# Add Instagram ID
bq_long["Instagram_ID"] = instagram_id


# ============================================================
# FILTER BQ DATA TO SAME DATE RANGE AS API
# ============================================================

start_date_str = start_date.strftime("%Y-%m-%d")
end_date_str = end_date.strftime("%Y-%m-%d")

bq_long = bq_long[
    (bq_long["Date"] >= start_date_str) &
    (bq_long["Date"] <= end_date_str)
]


# ============================================================
# MERGE API + BQ
# ============================================================

validation_df = pd.merge(
    api_df,
    bq_long[
        ["Instagram_ID", "Date", "Metric", "BQ_Value"]
    ],
    on=["Instagram_ID", "Date", "Metric"],
    how="outer"
)


# ============================================================
# DIFFERENCE
# ============================================================

validation_df["Difference"] = (
    validation_df["API_Value"]
    - validation_df["BQ_Value"]
)


# ============================================================
# DIFFERENCE %
# ============================================================

validation_df["Difference_%"] = validation_df.apply(
    lambda row:
        0
        if row["API_Value"] == row["BQ_Value"]
        else (
            abs(row["Difference"])
            / abs(row["BQ_Value"])
            * 100
            if row["BQ_Value"] != 0
            else None
        ),
    axis=1
)


# ============================================================
# STATUS
# ============================================================

validation_df["Status"] = validation_df.apply(
    lambda row:
        "VALIDATED"
        if row["API_Value"] == row["BQ_Value"]
        else "ISSUE",
    axis=1
)


# ============================================================
# FINAL COLUMN ORDER
# ============================================================

validation_df = validation_df[
    [
        "Instagram_ID",
        "Date",
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
    ["Date", "Metric"]
)


# ============================================================
# SAVE EXCEL
# ============================================================

validation_df.to_excel(
    "instagram_validation_july_report.xlsx",
    index=False
)

print("Validation report created successfully.")





