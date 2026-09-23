"""Which factors drive passenger satisfaction?

Fits a logistic regression on the 14 service ratings, departure delay, class,
travel type and customer type, then ranks drivers with permutation importance
(drop in ROC AUC on a held-out set when a feature is shuffled).

Input : data/processed/flights_clean.csv  (run scripts/clean.py first)
Output: screenshots/driver_importance.png
        data/processed/driver_importance.csv
        data/processed/service_uplift.csv   (what-if: +1 rating point per service)

Usage:
    python scripts/driver_analysis.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parent))
from clean import SERVICE_COLUMNS, SERVICE_LABELS  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed" / "flights_clean.csv"
CHART = ROOT / "screenshots" / "driver_importance.png"
TABLE = ROOT / "data" / "processed" / "driver_importance.csv"
UPLIFT = ROOT / "data" / "processed" / "service_uplift.csv"

NUMERIC = [*SERVICE_COLUMNS, "dep_delay"]
CATEGORICAL = ["class", "travel_type", "customer_type"]
TARGET = "is_satisfied"
SEED = 42

FEATURE_LABELS = {
    **{k: v[0] for k, v in SERVICE_LABELS.items()},
    "dep_delay": "Departure Delay",
    "class": "Travel Class",
    "travel_type": "Travel Type",
    "customer_type": "Customer Type",
}

# Chart colors (validated reference palette, light mode).
INK = "#0b0b0b"
INK_MUTED = "#52514e"
SERVICE_COLOR = "#2a78d6"
CONTEXT_COLOR = "#eb6834"


def build_model() -> Pipeline:
    # Rating 0 = "not applicable": treat as missing, impute the median and let
    # the model see an indicator for it.
    numeric = make_pipeline(
        SimpleImputer(missing_values=0, strategy="median", add_indicator=True),
        StandardScaler(),
    )
    # dep_delay is legitimately 0 for on-time flights, so it bypasses the 0-imputer.
    preprocess = ColumnTransformer(
        [
            ("ratings", numeric, SERVICE_COLUMNS),
            ("delay", make_pipeline(StandardScaler()), ["dep_delay"]),
            ("cats", OneHotEncoder(drop="first", handle_unknown="ignore"), CATEGORICAL),
        ]
    )
    return Pipeline([("prep", preprocess), ("clf", LogisticRegression(max_iter=2000))])


def plot_importance(imp: pd.DataFrame, auc: float) -> None:
    imp = imp.sort_values("importance")
    colors = [SERVICE_COLOR if f in SERVICE_COLUMNS else CONTEXT_COLOR for f in imp["feature"]]

    fig, ax = plt.subplots(figsize=(9, 7), dpi=150)
    values = imp["importance"].clip(lower=0)
    ax.barh(imp["label"], values, color=colors, height=0.7)
    for y, v in enumerate(values):
        ax.text(v + values.max() * 0.012, y, f"{v:.3f}", va="center", fontsize=8, color=INK_MUTED)

    fig.suptitle("What drives passenger satisfaction?", x=0.02, ha="left", fontsize=14,
                 color=INK, fontweight="bold")
    fig.text(0.02, 0.935, "Permutation importance = drop in ROC AUC when the feature is shuffled "
             f"(logistic regression, hold-out AUC {auc:.3f})", fontsize=9, color=INK_MUTED)
    ax.set_xlabel("Drop in ROC AUC", color=INK_MUTED)
    ax.tick_params(colors=INK_MUTED, labelsize=9)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#d0cfca")
    ax.xaxis.grid(True, color="#e8e7e2", linewidth=0.8)
    ax.set_axisbelow(True)

    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=SERVICE_COLOR, label="Service rating"),
                       Patch(color=CONTEXT_COLOR, label="Trip / customer context")],
              loc="lower right", frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, 0, 1, 0.925))
    CHART.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(CHART, facecolor="white")
    plt.close(fig)


def simulate_uplift(model: Pipeline, X: pd.DataFrame) -> pd.DataFrame:
    """Predicted satisfaction if every applicable rating of one service rose by 1 point (max 5)."""
    baseline = model.predict_proba(X)[:, 1].mean()
    rows = []
    for col in SERVICE_COLUMNS:
        X_new = X.copy()
        applicable = X_new[col] > 0
        X_new.loc[applicable, col] = (X_new.loc[applicable, col] + 1).clip(upper=5)
        projected = model.predict_proba(X_new)[:, 1].mean()
        rows.append({"service": SERVICE_LABELS[col][0], "baseline": baseline,
                     "projected": projected, "uplift_pts": (projected - baseline) * 100})
    return pd.DataFrame(rows).sort_values("uplift_pts", ascending=False).reset_index(drop=True)


def main() -> None:
    if not DATA.exists():
        sys.exit(f"Missing {DATA}. Run `python scripts/clean.py` first.")
    df = pd.read_csv(DATA)
    X, y = df[NUMERIC + CATEGORICAL], df[TARGET]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, stratify=y, random_state=SEED
    )

    model = build_model().fit(X_train, y_train)
    proba = model.predict_proba(X_test)[:, 1]
    auc = roc_auc_score(y_test, proba)
    acc = accuracy_score(y_test, proba >= 0.5)
    print(f"Hold-out ROC AUC: {auc:.3f} | accuracy: {acc:.3f}")

    # Permutation importance on raw columns (each categorical permuted as a whole).
    sample = X_test.sample(n=min(10_000, len(X_test)), random_state=SEED)
    result = permutation_importance(
        model, sample, y_test.loc[sample.index], scoring="roc_auc",
        n_repeats=10, random_state=SEED, n_jobs=-1,
    )
    imp = pd.DataFrame(
        {
            "feature": X.columns,
            "label": [FEATURE_LABELS[c] for c in X.columns],
            "importance": result.importances_mean,
            "std": result.importances_std,
        }
    ).sort_values("importance", ascending=False).reset_index(drop=True)
    imp["rank"] = np.arange(1, len(imp) + 1)

    # Direction of effect for the service ratings (standardised coefficients).
    names = model.named_steps["prep"].get_feature_names_out()
    coefs = pd.Series(model.named_steps["clf"].coef_[0], index=names)
    imp["coefficient"] = imp["feature"].map(
        lambda f: coefs.get(f"ratings__{f}", coefs.get(f"delay__{f}", np.nan))
    ).round(3)

    TABLE.parent.mkdir(parents=True, exist_ok=True)
    imp.round(4).to_csv(TABLE, index=False)
    plot_importance(imp, auc)

    print("\nTop drivers (permutation importance, ROC AUC drop):")
    print(imp[["rank", "label", "importance", "std", "coefficient"]].to_string(index=False))
    uplift = simulate_uplift(model, X)
    uplift.round(4).to_csv(UPLIFT, index=False)
    print("\nWhat-if: +1 rating point on one service (predicted satisfaction, pct points):")
    print(uplift.round(3).to_string(index=False))

    print(f"\nSaved {CHART.relative_to(ROOT)}, {TABLE.relative_to(ROOT)}, {UPLIFT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
