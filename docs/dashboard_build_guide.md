# Dashboard Build Guide (Power BI Desktop)

`scripts/build_pbip.py` generates a Power BI Project with the full semantic model
(tables, Power Query, relationships, 25 DAX measures) and four report pages with
starter visuals. The generated files are text, so they diff cleanly on GitHub.
This guide covers the steps that need Power BI Desktop (Windows).

> The semantic model was checked with Microsoft's TMDL parser
> (`Microsoft.AnalysisServices` `TmdlSerializer`). The report layout was written
> by the generator and has not been opened in Desktop yet. If a starter visual
> fails to render, delete it and rebuild it from the table below: the model
> and measures are unaffected.

## 1. Open the project

1. Run the pipeline (see README → *How to run*) so `data/processed/*.csv` exist.
2. Open `powerbi/AirlineAnalytics.pbip` in Power BI Desktop (enable *File → Options →
   Preview features → Power BI Project (.pbip) save option* on older versions).
3. **Transform data → Edit parameters → `DataFolder`**: set it to the full path of your
   `data/processed/` folder **with a trailing backslash**, e.g.
   `C:\Users\you\ACSLA\data\processed\`.
4. **Refresh**. The model loads ~130k passengers and ~1.8M rating rows.

## 2. Apply the theme

**View → Themes → Browse for themes →** `powerbi/theme/AirlineTheme.json`.
Blue = satisfied / primary, orange = dissatisfied / contrast. The rest of the palette is
colour-blind-checked for adjacent series.

## 3. Pages

Every page has the same slicer row at the top right: **Class**, **Travel type**, **Customer type**.
Use *View → Sync slicers* to sync them across pages.

| Page | Starter visuals (generated) | Add in Desktop |
|---|---|---|
| **1. Executive Overview** | Cards: Total Passengers, Satisfaction %, Delayed %, Avg Dep Delay · Bar: Satisfaction % by class · Column: Satisfaction % by travel type × class | Data labels on both charts, and a 43.4% constant line on the bar chart (*Analytics pane*). |
| **2. Customer Segments** | Matrix: age band × customer type (Satisfaction %) · Donut: passengers by gender · Bar: Satisfaction % by distance band · Bar: Dissatisfied passengers by trip segment | Matrix → *Cell elements → Background color* → gradient (orange = low, blue = high). |
| **3. Service Drivers** | Bar: Service Gap ranking · Matrix: service × class (Avg Service Rating) · Bar: rating gap satisfied vs dissatisfied | A **Key Influencers** visual (*Analyze* = `Fact_Flights[satisfaction]`, *Explain by* = `Dim_Travel[class]`, `Dim_Travel[travel_type]`, `Dim_Customer[customer_type]`, `Fact_Flights[delay_bucket]`, `Dim_Customer[age_band]`). Heat-map colours on the matrix. |
| **4. Delay Impact** | Cards: Delayed %, Delay Penalty >15 pts, Projected Satisfaction %, Projected Gain pts · What-if slicer on `Delay Reduction %` · Column: Satisfaction % by delay bucket · Scatter: avg delay vs satisfaction by trip segment (size = passengers) | Switch the what-if slicer to *Single value* (slider) style. |

Keep it to six analytical visuals per page, not counting the title and slicers.

## 4. Tooltip page and navigation

1. **Tooltip page:** add a page, set *Page information → Allow use as tooltip*, size *Tooltip*.
   Add cards for Total Passengers, Satisfaction %, Avg Service Rating and Delayed %.
   On the page 1 and 2 charts, set *Tooltips → Type: Report page → Page:* your tooltip page.
2. **Navigation:** *Insert → Buttons → Navigator → Page navigator*, placed in the left margin
   of every page. Or add one bookmark per page with buttons linked to them.

## 5. Validate against Python

Page 3's Key Influencers ranking should agree with `screenshots/driver_importance.png`:
travel type, customer type, online boarding and inflight Wi-Fi should come out on top.
Record the comparison in the README's *Validation* section.

## 6. Screenshots and publish

1. Export each page (*File → Export → PDF*, or use a screen capture) into `screenshots/`
   as `page1_overview.png` … `page4_delay.png`, and record a short GIF for the README.
2. *Home → Publish* to Power BI Service. For a public portfolio link, use *File → Embed report →
   Publish to web (public)*. Only do this because the data is public. Paste the link into the README.
3. Save (Ctrl+S). The `.pbip` text files update, so commit them.
