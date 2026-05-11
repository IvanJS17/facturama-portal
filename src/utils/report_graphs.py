from __future__ import annotations

import base64
from io import BytesIO

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def _to_data_uri(buffer: BytesIO) -> str:
    encoded = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{encoded}"


def generate_product_pie(labels: list[str], values: list[float]) -> str:
    """Build a pie chart PNG as a base64 data URI."""
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(8, 5), dpi=150)

    if not labels or not values or sum(values) <= 0:
        ax.text(0.5, 0.5, "Sin datos", ha="center", va="center", fontsize=12)
        ax.axis("off")
    else:
        wedges, _, _ = ax.pie(
            values,
            autopct="%1.1f%%",
            startangle=90,
            wedgeprops={"linewidth": 1, "edgecolor": "white"},
        )
        ax.axis("equal")
        ax.legend(
            wedges,
            labels,
            title="Productos",
            loc="center left",
            bbox_to_anchor=(1, 0.5),
            frameon=False,
        )

    ax.set_title("Distribución por producto", fontsize=12)
    fig.tight_layout()

    buffer = BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    return _to_data_uri(buffer)


def generate_trend_bar(labels: list[str], values: list[float]) -> str:
    """Build a bar chart PNG as a base64 data URI."""
    plt.style.use("seaborn-v0_8-whitegrid")
    fig, ax = plt.subplots(figsize=(9, 5), dpi=150)

    if not labels or not values:
        ax.text(0.5, 0.5, "Sin datos", ha="center", va="center", fontsize=12)
        ax.axis("off")
    else:
        ax.bar(labels, values, color="#1a1a2e")
        if len(labels) > 8:
            ax.tick_params(axis="x", rotation=45)
        ax.set_ylabel("Total")
        ax.set_title("Tendencia")

    fig.tight_layout()

    buffer = BytesIO()
    fig.savefig(buffer, format="png", bbox_inches="tight")
    plt.close(fig)
    buffer.seek(0)
    return _to_data_uri(buffer)
