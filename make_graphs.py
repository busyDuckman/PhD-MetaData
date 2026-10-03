#!/usr/bin/env python3
"""Render the thesis meta-data graphs from analysis_of_backups.csv.

Usage:
    python make_graphs.py      (or ./make_graphs.py)

On first run it creates ./.venv and installs requirements.txt into it, then
re-runs itself inside that venv. Writes each graph to ./graphs/ as PNG.
"""

import os
import subprocess
import sys
import venv
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV = HERE / ".venv"


def ensure_venv() -> None:
    """Re-run this script with the project venv's Python, creating it if needed."""
    if Path(sys.prefix).resolve() == VENV:
        return
    python = VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        print("Creating .venv and installing requirements...")
        venv.create(VENV, with_pip=True)
        subprocess.check_call([str(python), "-m", "pip", "install", "-q",
                               "-r", str(HERE / "requirements.txt")])
    sys.exit(subprocess.call([str(python), str(Path(__file__).resolve()), *sys.argv[1:]]))


if __name__ == "__main__":
    ensure_venv()

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle
from matplotlib.ticker import FuncFormatter
from matplotlib.transforms import blended_transform_factory, offset_copy


CSV = HERE / "analysis_of_backups.csv"
OUT = HERE / "graphs"

# Soft pastel palette,
PASTELS = ["#8db9e3", "#9ad3a5", "#c3a6dd", "#f4a7b9", "#6fb0b8", "#c2d86a", "#f2c14e"]
THEME = dict(
    surface="#fcfcfb", text="#0b0b0b", text2="#52514e", muted="#8a8984",
    grid="#e6e5e1", neutral="#c4c0b8", recovery="#ca6060", line="#5b9bd5",
    series=PASTELS,
)

# Stages in order of first appearance; each takes the next palette slot.
STAGES = [
    "LIT-REVIEW", "METHOD", "DATA_ANALYSIS", "DATA_VISUALISATION",
    "RESTRUCTURE", "RESULTS", "PROOF_READING",
]
NEUTRAL_STAGE = "EXAMINERS_COMMENTS"
RECOVERY_STAGE = "DOCUMENT_RECOVERY"  # clear, with red diagonal hatching

# In the CSV, SUPERVISOR_REVIEW marks work addressing supervisor comments, not a
# section of the thesis. Those rows carry on the subject before them, and after
# the first completed version (v9) the work was proof reading.
SUPERVISOR_STAGE = "SUPERVISOR_REVIEW"
PROOF_STAGE = "PROOF_READING"
FIRST_COMPLETE = 9

FONTS = ["Inter", "Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans"]


def load() -> pd.DataFrame:
    """Rows in CSV order, keeping only the last backup of each day."""
    df = pd.read_csv(CSV, header=1)
    df["date"] = pd.to_datetime(df["Date last modified"], format="%d-%b-%y")
    df["supervisor"] = df["Stage (Major Focus)"] == SUPERVISOR_STAGE

    stage = df["Stage (Major Focus)"].mask(df["supervisor"])
    after = df["Version (in file name)"] > FIRST_COMPLETE
    stage[after & ~stage.isin([RECOVERY_STAGE, NEUTRAL_STAGE])] = PROOF_STAGE
    subject = stage.where(stage != RECOVERY_STAGE).ffill()
    df["stage"] = stage.fillna(subject)
    df["recovery"] = df["stage"] == RECOVERY_STAGE
    df["subject"] = df["stage"].where(~df["recovery"], subject)  # the stage a recovery interrupted
    return df.drop_duplicates("date", keep="last").reset_index(drop=True)


def by_date(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(["date", "Version (in file name)"], kind="stable").reset_index(drop=True)


def stage_colours(t: dict) -> dict:
    colours = dict(zip(STAGES, t["series"]))
    colours[NEUTRAL_STAGE] = t["neutral"]
    colours[RECOVERY_STAGE] = "none"
    return colours


def stage_label(stage: str) -> str:
    return stage.replace("_", " ").replace("-", " ").capitalize()


# shorter names for the narrow stage row segments
ROW_LABELS = {"DATA_VISUALISATION": "Vis", "EXAMINERS_COMMENTS": "Examiners"}


def style(t: dict) -> None:
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": FONTS,
        "font.size": 11,
        "figure.facecolor": t["surface"],
        "axes.facecolor": t["surface"],
        "savefig.facecolor": t["surface"],
        "axes.edgecolor": t["grid"],
        "axes.labelcolor": t["text2"],
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": t["grid"],
        "grid.linewidth": 0.8,
        "xtick.color": t["text2"],
        "ytick.color": t["text2"],
        "xtick.major.size": 0,
        "ytick.major.size": 0,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.spines.left": False,
        "legend.frameon": False,
        "text.color": t["text"],
    })


def frame(fig, t, title: str, top_in: float = 1.0, bottom_in: float = 0.5):
    """Title and margins, positioned in inches so tall figures match short ones."""
    h = fig.get_figheight()
    text = fig.text(0.04, 1 - 0.35 / h, title, fontsize=19, fontweight="bold", color=t["text"], va="top")
    fig.subplots_adjust(top=1 - top_in / h, bottom=bottom_in / h)
    return text


def year_axis(ax) -> None:
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.xaxis.set_minor_locator(mdates.MonthLocator(bymonth=[4, 7, 10]))
    ax.tick_params(axis="x", which="minor", length=0)


def kilo(v, _) -> str:
    return f"{v:.0f}k"


# Callouts shown on every graph: (backup date, text, cumulative offset, quality offset).
CALLOUTS = [
    ("2010-11-29", "Conference\nPublication", (-5, 130), (-30, 40)),
    ("2011-04-27", "First supervisor\nread through", (0, 60), (0, 80)),
    ("2011-10-10", "Moved to\nWord 10", (0, 60), (25, 40)),
    ("2012-07-31", "First completed\nversion", (0, 75), (-20, 45)),
    ("2013-02-13", "Submitted for\nexamination", (-62, 62), (25, 70)),
]
REVIEW_MARK = "v"  # drawn just above each supervisor review record
REVIEW_LABEL = "Addressing Supervisor Comments"


def callout(ax, t, x, y, text, dx, dy) -> None:
    ax.annotate(
        text, xy=(x, y), xytext=(dx, dy), textcoords="offset points",
        fontsize=10, color=t["text2"], ha="center",
        arrowprops=dict(arrowstyle="-", color=t["muted"], lw=0.8, shrinkA=2, shrinkB=14),
    )


def review_marks(ax, t, x, y, dy: float = 9, alpha: float = 1) -> None:
    above = offset_copy(ax.transData, fig=ax.figure, y=dy, units="points")
    ax.scatter(x, y, marker=REVIEW_MARK, s=30, color=t["text2"], linewidths=0, alpha=alpha,
               transform=above, zorder=4, clip_on=False)


def review_handle(t) -> Line2D:
    return Line2D([], [], marker=REVIEW_MARK, ls="", ms=7, color=t["text2"], mew=0)


def row_at(df, date):
    return df[df["date"] == pd.Timestamp(date)].iloc[-1]


def year_brackets(ax, t, years: pd.Series, top_in: float = 0.55) -> None:
    """Multi-level x-axis: a bracket under each run of bars from the same year."""
    tr = blended_transform_factory(ax.transData, ax.transAxes)
    ax_h = ax.get_position().height * ax.figure.get_figheight()
    y, tick, label = -top_in / ax_h, -(top_in - 0.08) / ax_h, -(top_in + 0.08) / ax_h
    for year, idx in years.groupby(years).groups.items():
        x0, x1 = min(idx) - 0.4, max(idx) + 0.4
        ax.plot([x0, x0, x1, x1], [tick, y, y, tick], transform=tr,
                color=t["muted"], lw=1, clip_on=False)
        ax.text((x0 + x1) / 2, label, str(year), transform=tr, ha="center", va="top",
                fontsize=10.5, color=t["text2"])


def stage_row(ax, t, subjects: pd.Series, colours: dict, top_in: float, height_in: float) -> None:
    """A second row of bars under the axis: one segment per run of the same stage."""
    tr = blended_transform_factory(ax.transData, ax.transAxes)
    fig = ax.figure
    ax_h = ax.get_position().height * fig.get_figheight()
    bar_pt = ax.get_position().width * fig.get_figwidth() * 72 / len(subjects)
    y0, h = -(top_in + height_in) / ax_h, height_in / ax_h
    runs = (subjects != subjects.shift()).cumsum()
    for _, run in subjects.groupby(runs):
        i0, i1, stage = run.index[0], run.index[-1], run.iloc[0]
        ax.add_patch(Rectangle((i0 - 0.46, y0), i1 - i0 + 0.92, h, transform=tr,
                               facecolor=colours[stage], lw=0, clip_on=False))
        label = ROW_LABELS.get(stage, stage_label(stage))
        if len(label) * 4.8 < (i1 - i0 + 1) * bar_pt - 6:
            ax.text((i0 + i1) / 2, y0 + h / 2, label, transform=tr, ha="center", va="center",
                    fontsize=8, color=t["text"])


def cumulative(df, t) -> plt.Figure:
    colours = stage_colours(t)
    n = len(df)
    fig, ax = plt.subplots(figsize=(14, 8.4))
    fig.subplots_adjust(left=0.06, right=0.94)
    frame(fig, t, "Cumulative Word Count and File Size", top_in=1.6, bottom_in=2.05)

    rows = range(n)
    # word count bars
    bars = ax.bar(rows, df["Words (x1k)"], width=0.72,
                  color=[colours[s] for s in df["subject"]], zorder=2)
    # recovery hatching
    for bar, recovery in zip(bars, df["recovery"]):
        if recovery:
            bar.set_hatch("///")
            bar.set_edgecolor(t["recovery"])
            bar.set_linewidth(1.2)
    # date labels
    ax.set_xticks(list(rows))
    ax.set_xticklabels([f"{d:%d %b}" for d in df["date"]], fontsize=8, rotation=90)
    ax.tick_params(axis="x", pad=0.36 * 72)
    ax.set_xlim(-0.6, n - 0.4)
    # stage row under bars
    stage_row(ax, t, df["subject"], colours, top_in=0.06, height_in=0.24)
    # year brackets
    year_brackets(ax, t, df["date"].dt.year, top_in=0.95)

    # file size line (right axis)
    size = ax.twinx()
    size.plot(rows, df["Size (Mb)"], color=t["recovery"], lw=1, ls="--", zorder=3, solid_joinstyle="round")
    size.set_ylim(0, 100)
    size.set_ylabel("File size (MB)")
    size.grid(False)
    size.spines["right"].set_visible(False)
    size.spines["bottom"].set_visible(False)

    # words axis (left)
    ax.yaxis.set_major_formatter(FuncFormatter(kilo))
    ax.set_ylabel("Words")

    # final word count label
    last = df["Words (x1k)"].iloc[-1]
    ax.annotate(f"{last * 1000:,.0f}", (n - 1, last), xytext=(0, 4),
                textcoords="offset points", ha="right", va="bottom",
                fontsize=9.5, color=t["text"])

    # supervisor review marks
    reviews = df.index[df["supervisor"]]
    review_marks(ax, t, reviews, df.loc[reviews, "Words (x1k)"], dy=7)

    # callouts
    for date, text, offset, _ in CALLOUTS:
        i = row_at(df, date).name
        callout(ax, t, i, df.loc[i, "Words (x1k)"], text, *offset)

    # legend
    order =[s for s in STAGES + [NEUTRAL_STAGE, RECOVERY_STAGE] if s in set(df["stage"])]
    handles = [Patch(facecolor=colours[s], edgecolor=t["recovery"], linewidth=1.2 if s == RECOVERY_STAGE else 0,
                     hatch="///" if s == RECOVERY_STAGE else None) for s in order]
    handles += [review_handle(t), Line2D([], [], color=t["recovery"], lw=1, ls="--")]
    fig.legend(handles, [stage_label(s) for s in order] + [REVIEW_LABEL, "File size"], ncol=6, fontsize=10,
               labelcolor=t["text2"], loc="upper left",
               bbox_to_anchor=(0.035, 1 - 0.75 / fig.get_figheight()),
               handlelength=1.1, handleheight=1.1, columnspacing=1.6)
    return fig


QUALITY = [
    ("Flesch Index", "Flesch reading ease", "higher = easier to read", "{:.1f}"),
    ("Fog Index", "Gunning fog index", "years of schooling needed", "{:.1f}"),
    ("% passive sentences", "Passive sentences", "share of all sentences", "{:.0f}%"),
    ("Ave Word Len", "Average word length", "letters per word", "{:.2f}"),
]


def stage_brackets(ax, t, dates: pd.Series, subjects: pd.Series, top_in: float) -> None:
    """Second level of the date axis: a bracket under each run of the same stage.
    Labels that would collide with their neighbour drop to a second row."""
    fig = ax.figure
    tr = blended_transform_factory(ax.transData, ax.transAxes)
    ax_h = ax.get_position().height * fig.get_figheight()
    y, tick = -top_in / ax_h, -(top_in - 0.06) / ax_h
    rows = [-(top_in + 0.06) / ax_h, -(top_in + 0.26) / ax_h]

    def pt(d):  # date -> x position in points
        return ax.transData.transform((mdates.date2num(d), 0))[0] * 72 / fig.dpi

    runs = (subjects != subjects.shift()).cumsum()
    spans = [[dates[r.index[0]], None, r.iloc[0]] for _, r in subjects.groupby(runs)]
    for a, b in zip(spans, spans[1:]):
        a[1] = b[0]
    spans[-1][1] = dates.iloc[-1]

    renderer = fig.canvas.get_renderer()
    row1_end, row2 = -1e9, []  # row2: [mid date, width, label, left offset from mid in points]
    for x0, x1, stage in spans:
        gap = pd.Timedelta(days=min(4, (x1 - x0).days * 0.2))
        x0, x1 = x0 + gap, x1 - gap
        ax.plot([x0, x0, x1, x1], [tick, y, y, tick], transform=tr,
                color=t["muted"], lw=1, clip_on=False)
        label = ROW_LABELS.get(stage, stage_label(stage))
        mid = x0 + (x1 - x0) / 2
        text = ax.text(mid, rows[0], label, transform=tr, ha="center", va="top",
                       fontsize=9.5, color=t["text2"])
        width = text.get_window_extent(renderer).width * 72 / fig.dpi
        if pt(mid) - width / 2 > row1_end + 10:
            row1_end = pt(mid) + width / 2
        else:
            text.remove()
            row2.append([mid, width, label, -width / 2])

    # second row: neighbours that would overlap split at the point between them
    for a, b in zip(row2, row2[1:]):
        a_right = pt(a[0]) + a[3] + a[1]
        if a_right + 10 > pt(b[0]) + b[3]:
            split = (pt(a[0]) + pt(b[0])) / 2
            a[3] = split - 5 - a[1] - pt(a[0])
            b[3] = split + 5 - pt(b[0])
    for mid, width, label, offset in row2:
        ax.annotate(label, (mdates.date2num(mid), rows[1]), xycoords=tr, xytext=(offset, 0),
                    textcoords="offset points", ha="left", va="top",
                    fontsize=9.5, color=t["text2"], annotation_clip=False)


def quality(df, t) -> plt.Figure:
    df = by_date(df)
    # four panels stacked, sharing the date axis; top one taller for callouts
    fig, axes = plt.subplots(4, 1, figsize=(12, 11), sharex=True,
                             gridspec_kw=dict(height_ratios=[1.5, 1, 1, 1]))
    fig.subplots_adjust(left=0.07, right=0.93, hspace=0.3)
    title = frame(fig, t, "Readability over time", top_in=1.2, bottom_in=1.15)
    # key on the title line, right-aligned to the plot edge
    renderer = fig.canvas.get_renderer()
    key_y = title.get_window_extent(renderer).y0 / fig.bbox.height
    label = fig.text(fig.subplotpars.right, key_y, REVIEW_LABEL, ha="right", va="bottom",
                     fontsize=10.5, color=t["text2"])
    fig.text(label.get_window_extent(renderer).x0 / fig.bbox.width - 0.004, key_y, "▼",
             ha="right", va="bottom", fontsize=10.5, color=t["text2"], alpha=0.5)
    reviews = df[df["supervisor"]]
    marks = [row_at(df, date) for date, *_ in CALLOUTS]

    for n, (ax, (col, name, hint, fmt)) in enumerate(zip(axes, QUALITY)):
        y = df[col]
        # metric line
        ax.plot(df["date"], y, color=t["line"], lw=2, solid_joinstyle="round")
        # supervisor review marks
        review_marks(ax, t, reviews["date"], reviews[col], dy=7, alpha=0.5)
        # start and end dots
        for i in (0, len(df) - 1):
            ax.scatter(df["date"].iloc[i], y.iloc[i], s=42, color=t["line"],
                       edgecolor=t["surface"], linewidth=1.6, zorder=3)
        # start and end values
        ax.annotate(fmt.format(y.iloc[0]), (df["date"].iloc[0], y.iloc[0]),
                    xytext=(0, 9), textcoords="offset points", ha="left",
                    fontsize=10, color=t["text2"])
        ax.annotate(fmt.format(y.iloc[-1]), (df["date"].iloc[-1], y.iloc[-1]),
                    xytext=(8, 0), textcoords="offset points", ha="left", va="center",
                    fontsize=10, fontweight="bold", color=t["text"])
        # axes, panel title and hint
        span = y.max() - y.min()
        ax.set_ylim(y.min() - span * 0.35, y.max() + span * (1.25 if n == 0 else 0.35))
        # panel title with its description beside it
        head = ax.annotate(name, (0, 1), xycoords="axes fraction", xytext=(0, 12),
                           textcoords="offset points", va="baseline",
                           fontsize=12.5, fontweight="bold", color=t["text"])
        head_w = head.get_window_extent(renderer).width * 72 / fig.dpi
        ax.annotate(hint, (0, 1), xycoords="axes fraction", xytext=(head_w + 10, 12),
                    textcoords="offset points", va="baseline", fontsize=10, color=t["text2"])
        ticks = plt.MaxNLocator(6, steps=[1, 2, 5, 10]).tick_values(y.min(), y.max())
        ax.set_yticks([v for v in ticks if y.min() - span * 0.35 <= v <= y.max() + span * 0.35])
        year_axis(ax)
        ax.set_xlim(df["date"].iloc[0] - pd.Timedelta(days=45),
                    df["date"].iloc[-1] + pd.Timedelta(days=150))
        # dashed year lines, from the axis up to the top tick
        years = pd.date_range(f"{df['date'].iloc[0].year + 1}-01-01",
                              df["date"].iloc[-1] + pd.Timedelta(days=150), freq="YS")
        ax.vlines(years, ax.get_ylim()[0], max(ax.get_yticks()), color=t["muted"], lw=1.0, alpha=0.6,
                  linestyles=[(0, (4, 3))], zorder=0)
        ax.tick_params(axis="x", pad=6)
        # dashed callout position marks, centred on the line
        lo, hi = ax.get_ylim()
        half = 12 / (ax.get_position().height * fig.get_figheight() * 72) * (hi - lo)
        for row in marks:
            ax.plot([row["date"]] * 2, [row[col] - half, row[col] + half], color=t["muted"],
                    lw=1, ls=(0, (2, 2)), zorder=1)

    # stage brackets under the years
    stage_brackets(axes[-1], t, df["date"], df["subject"], top_in=0.42)

    # callouts on the top panel
    top, col = axes[0], QUALITY[0][0]
    for date, text, _, offset in CALLOUTS:
        row = row_at(df, date)
        callout(top, t, row["date"], row[col], text, *offset)
    return fig


def main() -> None:
    df = load()
    OUT.mkdir(exist_ok=True)
    style(THEME)
    for name, make in (("cumulative", cumulative), ("quality", quality)):
        fig = make(df, THEME)
        path = OUT / f"{name}.png"
        fig.savefig(path, dpi=200)
        plt.close(fig)
        print(f"wrote {path.relative_to(HERE)}")


if __name__ == "__main__":
    main()
