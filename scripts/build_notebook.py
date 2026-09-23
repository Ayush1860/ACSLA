"""Generate notebooks/01_eda.ipynb (run with --execute to embed outputs).

Keeping the notebook source in a script makes it easy to review in git and to
regenerate after changing the analysis.

Usage:
    python scripts/build_notebook.py --execute
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = ROOT / "notebooks" / "01_eda.ipynb"

md = nbf.v4.new_markdown_cell
code = nbf.v4.new_code_cell

CELLS = [
    md(
        "# 01 - Exploratory Data Analysis\n"
        "**Airline Customer Satisfaction & Loyalty Analytics**\n\n"
        "Explores the cleaned Kaggle *Airline Passenger Satisfaction* data (129,880 passengers) "
        "before modelling it in Power BI.\n\n"
        "Prerequisite: `python scripts/download_data.py && python scripts/clean.py`"
    ),
    code(
        "import sys\n"
        "from pathlib import Path\n\n"
        "import matplotlib.pyplot as plt\n"
        "import numpy as np\n"
        "import pandas as pd\n"
        "import seaborn as sns\n\n"
        "ROOT = Path.cwd().parent if Path.cwd().name == 'notebooks' else Path.cwd()\n"
        "sys.path.insert(0, str(ROOT / 'scripts'))\n"
        "from clean import SERVICE_COLUMNS, SERVICE_LABELS, AGE_BANDS, DELAY_BUCKETS, DISTANCE_BANDS\n\n"
        "SAT, DIS = '#2a78d6', '#eb6834'   # satisfied / dissatisfied\n"
        "INK, MUTED, GRID = '#0b0b0b', '#52514e', '#e8e7e2'\n"
        "plt.rcParams.update({\n"
        "    'figure.dpi': 110, 'axes.spines.top': False, 'axes.spines.right': False,\n"
        "    'axes.edgecolor': '#d0cfca', 'axes.labelcolor': MUTED, 'xtick.color': MUTED,\n"
        "    'ytick.color': MUTED, 'axes.titlecolor': INK, 'axes.titleweight': 'bold',\n"
        "    'axes.titlelocation': 'left', 'axes.grid': True, 'grid.color': GRID, 'axes.axisbelow': True,\n"
        "})\n"
        "SHOTS = ROOT / 'screenshots'\n\n"
        "df = pd.read_csv(ROOT / 'data' / 'processed' / 'flights_clean.csv')\n"
        "print(df.shape)\n"
        "df.head()"
    ),
    md("## 1. Data quality"),
    code(
        "raw = pd.concat([pd.read_csv(ROOT / 'data' / 'raw' / f) for f in ('train.csv', 'test.csv')])\n"
        "print('Raw rows:', len(raw))\n"
        "print('Missing values in raw data:')\n"
        "print(raw.isna().sum()[lambda s: s > 0])\n"
        "print('\\nDuplicate passenger ids:', raw['id'].duplicated().sum())\n"
        "print('Missing after cleaning:', df.isna().sum().sum())"
    ),
    code(
        "# Rating 0 = 'not applicable' (e.g. no Wi-Fi on board) - share per service\n"
        "na_share = (df[SERVICE_COLUMNS] == 0).mean().rename(lambda c: SERVICE_LABELS[c][0])\n"
        "na_share.sort_values(ascending=False).map('{:.1%}'.format).to_frame('rated 0 (N/A)')"
    ),
    md("## 2. Target: how many passengers are satisfied?"),
    code(
        "rate = df['is_satisfied'].mean()\n"
        "print(f'Satisfied: {rate:.1%}  |  Neutral or dissatisfied: {1 - rate:.1%}')\n"
        "df['satisfaction'].value_counts()"
    ),
    md("## 3. Satisfaction by segment"),
    code(
        "def sat_by(col, order=None, ax=None):\n"
        "    s = df.groupby(col)['is_satisfied'].mean()\n"
        "    s = s.reindex(order) if order else s.sort_values()\n"
        "    ax.barh(s.index.astype(str), s.values, color=SAT, height=0.6)\n"
        "    ax.axvline(rate, color=MUTED, lw=1, ls='--')\n"
        "    for y, v in enumerate(s.values):\n"
        "        ax.text(v + 0.01, y, f'{v:.0%}', va='center', fontsize=9, color=MUTED)\n"
        "    ax.set_xlim(0, 1); ax.xaxis.set_major_formatter('{x:.0%}'); ax.grid(axis='y', visible=False)\n"
        "    ax.set_title(col.replace('_', ' ').title())\n\n"
        "fig, axes = plt.subplots(3, 2, figsize=(12, 10))\n"
        "sat_by('class', ['Economy', 'Eco Plus', 'Business'], axes[0, 0])\n"
        "sat_by('travel_type', ax=axes[0, 1])\n"
        "sat_by('customer_type', ax=axes[1, 0])\n"
        "sat_by('gender', ax=axes[1, 1])\n"
        "sat_by('age_band', AGE_BANDS, axes[2, 0])\n"
        "sat_by('distance_band', DISTANCE_BANDS, axes[2, 1])\n"
        "fig.suptitle(f'Satisfaction % by segment (dashed line = overall {rate:.1%})', x=0.01, ha='left',\n"
        "             fontweight='bold', color=INK)\n"
        "fig.tight_layout()\n"
        "fig.savefig(SHOTS / 'eda_segments.png', facecolor='white')\n"
        "plt.show()"
    ),
    code(
        "# Where are the at-risk passengers? Satisfaction % by customer type x travel type x class\n"
        "seg = (df.groupby(['customer_type', 'travel_type', 'class'])['is_satisfied']\n"
        "         .agg(passengers='size', satisfaction='mean').reset_index())\n"
        "seg['dissatisfied_passengers'] = (seg['passengers'] * (1 - seg['satisfaction'])).round().astype(int)\n"
        "seg.sort_values('dissatisfied_passengers', ascending=False).style.format(\n"
        "    {'satisfaction': '{:.1%}', 'passengers': '{:,}', 'dissatisfied_passengers': '{:,}'})"
    ),
    code(
        "pivot = df.pivot_table(index='age_band', columns='customer_type', values='is_satisfied').reindex(AGE_BANDS)\n"
        "fig, ax = plt.subplots(figsize=(6, 4))\n"
        "sns.heatmap(pivot, annot=True, fmt='.0%', cmap='Blues', vmin=0, vmax=1, cbar=False, ax=ax,\n"
        "            linewidths=2, linecolor='white')\n"
        "ax.set_title('Satisfaction % - age band x customer type'); ax.set_xlabel(''); ax.set_ylabel('')\n"
        "plt.show()"
    ),
    md("## 4. Distributions"),
    code(
        "fig, axes = plt.subplots(1, 2, figsize=(12, 4))\n"
        "for label, color, flag in (('Neutral/dissatisfied', DIS, 0), ('Satisfied', SAT, 1)):\n"
        "    sub = df[df['is_satisfied'] == flag]\n"
        "    axes[0].hist(sub['age'], bins=40, alpha=0.6, color=color, label=label)\n"
        "    axes[1].hist(sub['flight_distance'], bins=50, alpha=0.6, color=color, label=label)\n"
        "axes[0].set_title('Age'); axes[1].set_title('Flight distance')\n"
        "axes[0].legend(frameon=False)\n"
        "fig.tight_layout(); plt.show()"
    ),
    md("## 5. Delays"),
    code(
        "print(f\"Delayed > 15 min: {(df['dep_delay'] > 15).mean():.1%}\")\n"
        "print(f\"Delayed > 60 min: {(df['dep_delay'] > 60).mean():.1%}\")\n"
        "print(f\"Mean departure delay: {df['dep_delay'].mean():.1f} min (median {df['dep_delay'].median():.0f})\")\n"
        "print('Correlation departure vs arrival delay:', round(df['dep_delay'].corr(df['arr_delay']), 3))\n\n"
        "by_bucket = df.groupby('delay_bucket')['is_satisfied'].agg(['mean', 'size']).reindex(DELAY_BUCKETS)\n"
        "fig, ax = plt.subplots(figsize=(8, 4))\n"
        "ax.bar(by_bucket.index, by_bucket['mean'], color=SAT, width=0.6)\n"
        "for x, (v, n) in enumerate(zip(by_bucket['mean'], by_bucket['size'])):\n"
        "    ax.text(x, v + 0.01, f'{v:.1%}\\n(n={n:,})', ha='center', fontsize=9, color=MUTED)\n"
        "ax.set_ylim(0, 0.6); ax.yaxis.set_major_formatter('{x:.0%}'); ax.grid(axis='x', visible=False)\n"
        "ax.set_title('Satisfaction % by departure delay')\n"
        "fig.tight_layout(); fig.savefig(SHOTS / 'eda_delay_impact.png', facecolor='white'); plt.show()"
    ),
    md("## 6. Service ratings"),
    code(
        "ratings = df[SERVICE_COLUMNS].replace(0, np.nan)  # 0 = N/A, not a score\n"
        "svc = pd.DataFrame({\n"
        "    'avg_rating': ratings.mean(),\n"
        "    'satisfied': ratings[df['is_satisfied'] == 1].mean(),\n"
        "    'dissatisfied': ratings[df['is_satisfied'] == 0].mean(),\n"
        "}).rename(index=lambda c: SERVICE_LABELS[c][0])\n"
        "svc['gap'] = svc['satisfied'] - svc['dissatisfied']\n"
        "svc['service_gap_vs_5'] = 5 - svc['avg_rating']\n"
        "svc = svc.sort_values('gap')\n\n"
        "fig, ax = plt.subplots(figsize=(9, 6))\n"
        "y = np.arange(len(svc))\n"
        "ax.hlines(y, svc['dissatisfied'], svc['satisfied'], color='#c3c2b7', lw=2)\n"
        "ax.scatter(svc['dissatisfied'], y, color=DIS, s=60, label='Neutral/dissatisfied', zorder=3)\n"
        "ax.scatter(svc['satisfied'], y, color=SAT, s=60, label='Satisfied', zorder=3)\n"
        "ax.set_yticks(y, svc.index); ax.set_xlim(1, 5); ax.grid(axis='y', visible=False)\n"
        "ax.set_title('Average rating: satisfied vs dissatisfied passengers')\n"
        "ax.legend(frameon=False, loc='lower right')\n"
        "fig.tight_layout(); fig.savefig(SHOTS / 'eda_service_gap.png', facecolor='white'); plt.show()\n"
        "svc.sort_values('gap', ascending=False).round(2)"
    ),
    code(
        "# Satisfaction jumps sharply once Wi-Fi / online boarding are rated 4+\n"
        "pd.DataFrame({\n"
        "    'Inflight Wi-Fi': df.groupby('inflight_wifi_service')['is_satisfied'].mean(),\n"
        "    'Online Boarding': df.groupby('online_boarding')['is_satisfied'].mean(),\n"
        "}).rename_axis('rating (0 = N/A)').style.format('{:.1%}')"
    ),
    md("## 7. Correlations"),
    code(
        "cols = SERVICE_COLUMNS + ['age', 'flight_distance', 'dep_delay', 'arr_delay', 'is_satisfied']\n"
        "corr = df[cols].replace({c: {0: np.nan} for c in SERVICE_COLUMNS}).corr()\n"
        "labels = [SERVICE_LABELS.get(c, (c.replace('_', ' ').title(),))[0] for c in cols]\n"
        "fig, ax = plt.subplots(figsize=(12, 10))\n"
        "sns.heatmap(corr, cmap='vlag', center=0, vmin=-1, vmax=1, annot=True, fmt='.2f',\n"
        "            annot_kws={'size': 7}, xticklabels=labels, yticklabels=labels, ax=ax,\n"
        "            cbar_kws={'shrink': 0.6})\n"
        "ax.set_title('Correlation matrix (service ratings with 0 = N/A excluded)')\n"
        "fig.tight_layout(); fig.savefig(SHOTS / 'eda_correlation.png', facecolor='white'); plt.show()"
    ),
    code(
        "corr['is_satisfied'].drop('is_satisfied').rename(lambda c: SERVICE_LABELS.get(c, (c,))[0])\\\n"
        "    .sort_values(ascending=False).round(3).to_frame('corr with satisfaction')"
    ),
    md(
        "## 8. Takeaways\n"
        "- **Class and purpose dominate**: Business class passengers are far more satisfied than Economy, "
        "and personal-travel passengers are the least satisfied group overall.\n"
        "- **Loyalty matters**: disloyal customers are roughly half as likely to be satisfied as loyal ones.\n"
        "- **Digital touchpoints separate the two groups**: online boarding and inflight Wi-Fi show the "
        "largest rating gaps and satisfaction jumps once they reach 4+.\n"
        "- **Delays hurt, but less than service**: satisfaction falls ~9 points for departures >15 min late; "
        "departure and arrival delay are almost perfectly correlated, so only one is needed in the model.\n"
        "- Several in-flight ratings (seat comfort, entertainment, cleanliness, food) are strongly correlated "
        "with each other - the driver model has to share credit between them.\n\n"
        "Next: `python scripts/driver_analysis.py` quantifies these drivers."
    ),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="execute and embed outputs")
    args = parser.parse_args()

    nb = nbf.v4.new_notebook()
    nb["cells"] = CELLS
    nb["metadata"] = {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    }
    NOTEBOOK.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(nb, NOTEBOOK)
    print(f"Wrote {NOTEBOOK.relative_to(ROOT)}")

    if args.execute:
        subprocess.run(
            ["jupyter", "nbconvert", "--to", "notebook", "--execute", "--inplace",
             str(NOTEBOOK)],
            check=True,
            cwd=NOTEBOOK.parent,
        )
        print("Executed notebook in place")


if __name__ == "__main__":
    main()
