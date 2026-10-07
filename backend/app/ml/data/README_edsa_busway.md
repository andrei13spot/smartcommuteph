# edsa busway hourly ridership (digitized tally sheets)

`edsa_busway_hourly.csv` is the hourly passenger count at an EDSA Busway
(EDSA Bus Carousel) station, typed in from the DOTr station security
detachment tally sheets that the group obtained through a formal data request.
The sheets are scanned, handwritten PDFs: one table per station-day with 24
hourly cells (0600H-0700H to 0500H-0600H) and a handwritten total.

## columns

| column | meaning |
|---|---|
| station | busway station the sheet is for (today: Kamuning) |
| service_date | the date written on the sheet, or worked out from the weekday and the period in the sheet header |
| hour | start hour of the cell, 0 to 23 (the sheet runs 06:00 to 05:59 the next morning) |
| timestamp | calendar date and hour; hours 0 to 5 are placed on the day after the service date |
| boardings | the number written in that cell; empty when the cell was blank or unreadable |
| day_status | `verified` when the 24 cells add up to the handwritten total; `mismatch`, `incomplete` or `no_total` otherwise |
| source_pdf, page, image | which pdf and page the value came from |

## how it was checked

1. every page was read and transcribed as written; no value was changed to
   make a total match
2. the 24 cells must add up to the handwritten total on the same sheet
3. the day total is compared with the Kamuning column of DOTr's own
   `Daily_Boarding` sheet when that day is present
4. May 2025 was compared cell by cell with DOTr's hourly sheet for Kamuning
5. days that failed check 2 were read a second time before being marked

`train_busway.py` trains only on `verified` days. the presentable workbook
with colour-coded checks (for the data return to DOTr) is
`EDSA_Busway_Kamuning_Hourly_Ridership.xlsx` in the group drive, built by the
same pipeline.

## what uses it

- `python -m app.ml.train_busway` trains `models/busway_lstm.keras` and
  writes `models/busway_metrics.json` and `models/busway_hourly_curve.json`
- `ml/ridership.py` uses the busway lstm for EDSA-Bus edges when the model
  file exists, else the hourly curve
