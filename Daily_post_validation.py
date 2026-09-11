import requests
from datetime import datetime, timedelta, timezone
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv()

ACCESS_TOKEN= os.getenv("ACCESS_TOKEN")

instagram_id = "17841408107333098"
facebook_id = "748841775232461"
dealer_id = "12162"
name = "KTM_Husqvarna_Andheri_East"



metrics = [
    "reach",
    "views",
    "total_interactions",
    "likes",
    "comments",
    "saved",
    "shares",
    "reposts"
]






def extract_post_insight_values(data):

    result = {}

    for metric in data.get("data", []):

        metric_name = metric["name"]

        values = metric.get("values", [])

        if values:
            result[metric_name] = values[0]["value"]
        else:
            result[metric_name] = 0
    print("extracted post insight values completed")
    return result




def get_instagram_post_insights(media_id,access_token,metrics):
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






"""
It does not take daily date but work based on the day of post(that will taken from b_q data).
But suppose big_query missed any post that cause error
Each post have unique media id and a post date and data(metrics) till today 

"""

      # Load big query99 data
bq_file = "BQ_Data/sqllab_untitled_query_1_20260831T080253.csv"   # from vw_dealer_ig_post_report

bq_df = pd.read_csv(bq_file)



bq_df["Post_Date"] = pd.to_datetime(
    bq_df["Post_Date"]
)

# filter data for specific date range

start_date = pd.Timestamp("2026-08-01")
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



print("got the big_query data")

all_records = []

for _, row in bq_df.iterrows():

    media_id = str(row["Media_ID"])

    print(f"Fetching insights for Media_ID: {media_id}")

    media_data = get_instagram_post_insights(
        media_id=media_id,
        access_token=ACCESS_TOKEN,
        metrics=metrics
    )
    print("extracting post insights")
    api_values = extract_post_insight_values(media_data)

    for bq_column, api_metric in metric_mapping.items():

        record = {
            "Dealer_Code": dealer_id,
            "Facebook_ID": facebook_id,
            "Instagram_ID": instagram_id,
            "Outlet_Name":name,
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
    generate_status,
    axis=1
)

    #  Adding Remark Column
post_api_df["Remark"] = post_api_df.apply(
    generate_remark,
    axis=1
)
# ============================================================
# FINAL COLUMN ORDER
# ============================================================

validation_df = post_api_df[
    [
        "Dealer_Code",
        "Facebook_ID",
        "Instagram_ID",
        "Outlet_Name",
        "Media_ID",
        "Post_Date",
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
    ["Post_Date", "Media_ID", "Metric"]
)


# ============================================================
# SAVE EXCEL
# ============================================================

output_file = "Socionix_instagram_report_post_validation.xlsx"

validation_df.to_excel(
    output_file,
    index=False,
    sheet_name="Page Report"
)
print("Validation report created successfully.")


# for excel file validation
from openpyxl import load_workbook
from openpyxl.styles import Alignment, PatternFill

wb = load_workbook(output_file)
ws = wb["Page Report"]


# ============================================================
# MERGE SAME DATE GROUP ROWS      , when instagram id have same dealer_id else use Group by technique
# ============================================================

merge_columns = ["A", "B", "C", "D", "E","F"]    #Columns on which grouping will be apply

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






