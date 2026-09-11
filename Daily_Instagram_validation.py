import requests
from datetime import datetime, timedelta, timezone
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()


ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")

instagram_id = "17841408107333098"
facebook_id = "748841775232461"
dealer_id = "12162"
name = "KTM_Husqvarna_Andheri_East"


start_date = datetime.strptime("25-08-2026", "%d-%m-%Y")
end_date = datetime.strptime("31-08-2026", "%d-%m-%Y")


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


def unix_conversion(current_date):

    next_date = current_date + timedelta(days=1)

    since = int(current_date.timestamp())
    until = int(next_date.timestamp())

    return since, until

def extract_insight_values(api_response, instagram_id, date):
    rows = []

    for item in api_response.get("data", []):

        metric = item.get("name")

        total_value = item.get("total_value", {})
        value = total_value.get("value")

        rows.append({
            "Dealer_Code": dealer_id,
            "Facebook_ID": facebook_id,
            "Instagram_ID": instagram_id,
            "Outlet_Name":name,
            "Date": date.strftime("%Y-%m-%d"),
            "Metric": metric,
            "API_Value": value,

        })

    return rows


def generate_remark(row):

    api_value = row["API_Value"]
    bq_value = row["BQ_Value"]
    difference = row["Difference"]
    metric = row["Metric"]

    # --------------------------------------------------
    # BOTH VALUES MISSING
    # --------------------------------------------------

    if pd.isna(api_value) and pd.isna(bq_value):

        return (
            "No comparable value is available from either "
            "the API or BigQuery."
        )

    # --------------------------------------------------
    # API VALUE MISSING
    # --------------------------------------------------

    if pd.isna(api_value):

        return (
            "API value is unavailable for this metric, "
            "so validation cannot be completed."
        )

    # --------------------------------------------------
    # BQ VALUE MISSING
    # --------------------------------------------------

    if pd.isna(bq_value):

        return (
            "BigQuery value is unavailable for this metric, "
            "so validation cannot be completed."
        )

    # --------------------------------------------------
    # EXACT MATCH - BOTH ZERO
    # --------------------------------------------------

    if api_value == 0 and bq_value == 0:

        return (
            "Exact match. Both sides zero."
        )

    # --------------------------------------------------
    # EXACT MATCH
    # --------------------------------------------------

    if api_value == bq_value:

        return (
            "Exact match."
        )

    # --------------------------------------------------
    # API HIGHER THAN BQ
    # --------------------------------------------------

    if api_value > bq_value:

        return (
            f"API value is higher than BigQuery by "
            f"{difference}. The API returns the current "
            f"post insight value, while BigQuery contains "
            f"the value captured during the earlier data fetch. "
            f"The difference may represent activity accrued "
            f"after the BigQuery capture."
        )

    # --------------------------------------------------
    # BQ HIGHER THAN API
    # --------------------------------------------------

    if api_value < bq_value:

        return (
            f"BigQuery value is higher than the current API "
            f"value by {abs(difference)}. This may indicate "
            f"an insight restatement, content activity change, "
            f"or a difference between capture timings. "
            f"Further investigation may be required."
        )


def calculate_difference_percent(row):

    api_value = row["API_Value"]
    bq_value = row["BQ_Value"]

    # Cannot calculate if either value is missing
    if pd.isna(api_value) or pd.isna(bq_value):
        return None

    # Exact match when both are zero
    if api_value == 0 and bq_value == 0:
        return 0

    # Avoid division by zero
    if bq_value == 0:
        return None

    return (
        row["Difference"] /
        abs(bq_value)
    ) * 100


def generate_status(row):

    api_value = row["API_Value"]
    bq_value = row["BQ_Value"]

    # Missing values
    if pd.isna(api_value) or pd.isna(bq_value):
        return "Not validated"

    # Exact match
    if api_value == bq_value:
        return "Pass"

    # API higher
    if api_value > bq_value:
        return "Pass-accrual lag"

    # BQ higher
    if api_value < bq_value:
        return "Pass-within tolerance"


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


def excel_validation():
    # for excel file validation
    from openpyxl import load_workbook
    from openpyxl.styles import Alignment, PatternFill

    wb = load_workbook(output_file)
    ws = wb["Page Report"]

    # ============================================================
    # MERGE SAME DATE GROUP ROWS      , when instagram id have same dealer_id else use Group by technique
    # ============================================================

    merge_columns = ["A", "B", "C", "D", "E"]  # Columns on which grouping will be apply

    max_row = ws.max_row
    current_start = 2

    for row in range(3, max_row + 2):

        current_date = (
            ws[f"E{row}"].value
            if row <= max_row
            else None
        )

        previous_date = ws[f"E{row - 1}"].value

        # End of a date group
        if row > max_row or current_date != previous_date:

            end_row = row - 1

            # Merge only when there is more than one row
            if end_row > current_start:

                for column in merge_columns:
                    ws.merge_cells(
                        f"{column}{current_start}:{column}{end_row}"
                    )

                    cell = ws[f"{column}{current_start}"]

                    cell.alignment = Alignment(
                        horizontal="center",
                        vertical="center"
                    )

            current_start = row

    # ============================================================
    # STATUS COLORS
    # ============================================================

    pass_fill = PatternFill(
        fill_type="solid",
        fgColor="C6E0B4"
    )

    tolerance_fill = PatternFill(
        fill_type="solid",
        fgColor="FFF2CC"
    )

    issue_fill = PatternFill(
        fill_type="solid",
        fgColor="F4CCCC"
    )

    not_validated_fill = PatternFill(
        fill_type="solid",
        fgColor="D9D9D9"
    )

    # Get header -> column mapping
    headers = {
        cell.value: cell.column_letter
        for cell in ws[1]
    }

    status_column = headers["Status"]

    for row in range(2, ws.max_row + 1):

        status_cell = ws[f"{status_column}{row}"]
        status = status_cell.value

        if status == "Pass":
            status_cell.fill = pass_fill

        elif status == "Pass-within tolerance":
            status_cell.fill = tolerance_fill

        elif status == "Pass-accrual lag":
            status_cell.fill = issue_fill

        elif status == "Not validated":
            status_cell.fill = not_validated_fill

    # ============================================================
    # IMPORTANT: SAVE AFTER ALL MODIFICATIONS
    # ============================================================

    wb.save(output_file)

    print("Excel formatting, merging and colors applied successfully.")







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
# NORMALIZE API DATA
# ============================================================

api_df["Instagram_ID"] = (
    api_df["Instagram_ID"]
    .astype(str)
    .str.strip()
)

api_df["Date"] = pd.to_datetime(
    api_df["Date"],
    errors="coerce"
).dt.strftime("%Y-%m-%d")

api_df["Metric"] = (
    api_df["Metric"]
    .astype(str)
    .str.strip()
    .str.lower()
)
# ============================================================
# BIGQUERY DATA
# ============================================================

bq_file = "BQ_Data/sqllab_untitled_query_4_20260907T074016.csv"

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


# ============================================================
# NORMALIZE BQ DATA
# ============================================================

# Convert Activity_Date to datetime
bq_df["Activity_Date"] = pd.to_datetime(
    bq_df["Activity_Date"],
    errors="coerce"
)

# Filter BQ data using actual datetime objects
bq_df = bq_df[
    (bq_df["Activity_Date"] >= start_date) &
    (bq_df["Activity_Date"] <= end_date)
].copy()


# ============================================================
# CONVERT BQ WIDE FORMAT -> LONG FORMAT
# ============================================================

bq_long = bq_df.melt(
    id_vars=["Activity_Date"],
    value_vars=list(bq_metric_mapping.keys()),
    var_name="BQ_Metric",
    value_name="BQ_Value"
)

# Map BQ metric names to API metric names
bq_long["Metric"] = bq_long["BQ_Metric"].map(
    bq_metric_mapping
)


# Normalize Date
bq_long["Date"] = pd.to_datetime(
    bq_long["Activity_Date"],
    errors="coerce"
).dt.strftime("%Y-%m-%d")


# Normalize Metric
bq_long["Metric"] = (
    bq_long["Metric"]
    .astype(str)
    .str.strip()
    .str.lower()
)

# Add identifying columns
bq_long["Dealer_Code"] = str(dealer_id).strip()
bq_long["Facebook_ID"] = str(facebook_id).strip()
bq_long["Instagram_ID"] = str(instagram_id).strip()
bq_long["Outlet_Name"] = str(name).strip()

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
    calculate_difference_percent,
    axis=1
)

    #  Adding Remark Column
validation_df["Remark"] = validation_df.apply(
    generate_remark,
    axis=1
)
# ============================================================
# STATUS
# ============================================================

validation_df["Status"] = validation_df.apply(
    generate_status,
    axis=1
)
# ============================================================
# FINAL COLUMN ORDER
# ============================================================

validation_df = validation_df[
    [
        "Dealer_Code",
        "Facebook_ID",
        "Instagram_ID",
        "Outlet_Name",
        "Date",
        "Metric",
        "API_Value",
        "BQ_Value",
        "Difference",
        "Difference_%",
        "Status",
        "Remark"
    ]
]

# Sort by date and metric
validation_df = validation_df.sort_values(
    ["Date", "Metric"]
)

# ============================================================
# SAVE EXCEL
# ============================================================

output_file = "Results/Socionix_instagram_report_validation_6.xlsx"

validation_df.to_excel(
    output_file,
    index=False,
    sheet_name="Page Report"
)
print("Validation report created successfully.")


  #  validate excel file

excel_validation()



