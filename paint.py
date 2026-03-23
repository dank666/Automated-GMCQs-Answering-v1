from pathlib import Path
from textwrap import fill

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D


domains = [
    "Topography and Geomorphology",
    "Climatology",
    "Hydrology",
    "Soil and Vegetation",
    "Human and Economic Geography",
    "Geographical Processes and Principles",
]

ours_sc = np.array([68, 82, 75, 58, 92, 57])
llm_sc = np.array([88, 84, 90, 96, 92, 93])

ours_mc = np.array([46, 83, 65, 50, 75, 47])
llm_mc = np.array([76, 80, 71, 71, 82, 74])


PALETTE = {
    "canvas": "#F4F1EA",
    "panel": "#FFFDF8",
    "stripe": "#F0EBE1",
    "connector": "#B7B2A7",
    "ours": "#2D6A6A",
    "llm": "#D66A4E",
    "text": "#24303A",
    "muted": "#667085",
    "delta_bg": "#FFF1E8",
    "highlight": "#D6C7A1",
}


def setup_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 11,
            "axes.titlesize": 15,
            "axes.labelsize": 11,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "axes.edgecolor": "#D7D2C8",
            "axes.linewidth": 0.8,
        }
    )


def wrap_labels(labels: list[str], width: int = 26) -> list[str]:
    return [fill(label, width=width) for label in labels]


def draw_panel(ax, title: str, ours: np.ndarray, llm: np.ndarray, y: np.ndarray) -> None:
    ax.set_facecolor(PALETTE["panel"])

    for yi in y[::2]:
        ax.axhspan(yi - 0.5, yi + 0.5, color=PALETTE["stripe"], zorder=0)

    ax.axvline(80, color=PALETTE["highlight"], linewidth=1.2, linestyle=(0, (4, 4)), zorder=1)

    for value_ours, value_llm, yi in zip(ours, llm, y):
        ax.plot(
            [value_ours, value_llm],
            [yi, yi],
            color=PALETTE["connector"],
            linewidth=3,
            solid_capstyle="round",
            zorder=2,
        )

        gap = int(value_llm - value_ours)
        mid_x = (value_ours + value_llm) / 2
        ax.text(
            mid_x,
            yi + 0.24,
            f"{gap:+d}",
            ha="center",
            va="bottom",
            fontsize=9,
            fontweight="bold",
            color=PALETTE["text"],
            bbox={
                "boxstyle": "round,pad=0.24",
                "facecolor": PALETTE["delta_bg"],
                "edgecolor": "none",
            },
            zorder=5,
        )

    ax.scatter(
        ours,
        y,
        s=180,
        color=PALETTE["ours"],
        edgecolors="white",
        linewidths=1.6,
        zorder=4,
    )
    ax.scatter(
        llm,
        y,
        s=190,
        marker="D",
        color=PALETTE["llm"],
        edgecolors="white",
        linewidths=1.6,
        zorder=4,
    )

    for value_ours, value_llm, yi in zip(ours, llm, y):
        ax.text(
            value_ours - 1.8,
            yi - 0.22,
            f"{value_ours}",
            ha="right",
            va="center",
            fontsize=9,
            color=PALETTE["ours"],
            fontweight="bold",
        )
        ax.text(
            value_llm + 1.8,
            yi - 0.22,
            f"{value_llm}",
            ha="left",
            va="center",
            fontsize=9,
            color=PALETTE["llm"],
            fontweight="bold",
        )

    avg_gap = np.mean(llm - ours)
    ax.set_title(title, loc="left", pad=14, fontweight="bold", color=PALETTE["text"])
    ax.text(
        0.0,
        1.02,
        f"Average gap: {avg_gap:+.1f} points",
        transform=ax.transAxes,
        fontsize=10,
        color=PALETTE["muted"],
    )

    ax.set_xlim(30, 100)
    ax.set_xticks(np.arange(30, 101, 10))
    ax.set_xlabel("Accuracy (%)", color=PALETTE["text"])
    ax.grid(axis="x", color="#D7D2C8", linestyle=(0, (2, 4)), linewidth=0.8)
    ax.tick_params(axis="x", colors=PALETTE["muted"])
    ax.tick_params(axis="y", length=0, colors=PALETTE["text"])

    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#D7D2C8")


def main() -> None:
    setup_style()

    wrapped_domains = wrap_labels(domains)
    y = np.arange(len(domains))[::-1]

    fig, axes = plt.subplots(1, 2, figsize=(16, 7.2), sharey=True)
    fig.patch.set_facecolor(PALETTE["canvas"])

    panels = [
        ("Single-choice Questions", ours_sc, llm_sc, axes[0]),
        ("Multiple-choice Questions", ours_mc, llm_mc, axes[1]),
    ]

    for title, ours, llm, ax in panels:
        draw_panel(ax, title, ours, llm, y)

    axes[0].set_yticks(y)
    axes[0].set_yticklabels(wrapped_domains, color=PALETTE["text"])

    legend_items = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="none",
            label="Our method",
            markerfacecolor=PALETTE["ours"],
            markeredgecolor="white",
            markeredgewidth=1.6,
            markersize=10,
        ),
        Line2D(
            [0],
            [0],
            marker="D",
            color="none",
            label="LLM baseline",
            markerfacecolor=PALETTE["llm"],
            markeredgecolor="white",
            markeredgewidth=1.6,
            markersize=9,
        ),
    ]
    fig.legend(
        handles=legend_items,
        loc="upper center",
        ncol=2,
        frameon=False,
        bbox_to_anchor=(0.5, 0.945),
        fontsize=10.5,
    )

    fig.suptitle(
        "Comparison of Domain Accuracy Between Our Method and the LLM",
        y=0.975,
        fontsize=17,
        fontweight="bold",
        color=PALETTE["text"],
    )
    fig.text(
        0.5,
        0.928,
        "Labels above the connectors show the point gap (LLM - Ours).",
        ha="center",
        fontsize=10,
        color=PALETTE["muted"],
    )

    fig.subplots_adjust(left=0.29, right=0.97, top=0.82, bottom=0.12, wspace=0.14)

    output_dir = Path(__file__).resolve().parent / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = output_dir / "method_vs_llm_dumbbell.pdf"
    png_path = output_dir / "method_vs_llm_dumbbell.png"

    plt.savefig(pdf_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.savefig(png_path, dpi=300, bbox_inches="tight", facecolor=fig.get_facecolor())

    if "agg" in plt.get_backend().lower():
        plt.close(fig)
    else:
        plt.show()

    print("Saved to:")
    print(pdf_path)
    print(png_path)


if __name__ == "__main__":
    main()
