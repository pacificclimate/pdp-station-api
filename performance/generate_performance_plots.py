"""Generate dependency-free SVG plots for the deployed API benchmarks."""

from __future__ import annotations

import csv
import math
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT / "END_TO_END_PERFORMANCE_THROUGHPUT.csv"
BY_OBSERVATION_COUNT_PATH = ROOT / "end_to_end_throughput_by_observation_count.svg"
EC_BCH_PATH = ROOT / "ecraw_bch_endpoint_throughput.svg"
RUSTPY_XLSX_PATH = ROOT / "rustpy_xlsx_throughput_by_observation_count.svg"

COLORS = {"prime": "#1769aa", "legacy": "#d1495b"}
FORMATS = ("ascii", "csv", "xlsx", "nc")


def escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def load_rows() -> list[dict[str, str | float]]:
    with DATA_PATH.open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    for row in rows:
        row["total_seconds"] = float(row["total_seconds"])
        row["bytes"] = float(row["bytes"])
        row["station_count"] = float(row["station_count"])
        row["observation_count"] = float(row["observation_count"])
        row["bytes_per_second"] = row["bytes"] / row["total_seconds"]
    return rows


def text(x: float, y: float, value: str, **attrs: str) -> str:
    attributes = " ".join(
        f'{key.replace("_", "-")}="{escape(val)}"' for key, val in attrs.items()
    )
    return f'<text x="{x:.1f}" y="{y:.1f}" {attributes}>{escape(value)}</text>'


def point(x: float, y: float, row: dict[str, str | float]) -> str:
    endpoint = str(row["endpoint"])
    rate = float(row["bytes_per_second"])
    title = (
        f"{row['measurement_date']}; {row['case']}; "
        f"{endpoint.title()} {row['format']}: {rate:,.0f} B/s; "
        f"{float(row['bytes']):,.0f} bytes in {float(row['total_seconds']):.2f}s"
        f"; {float(row['station_count']):,.0f} stations; "
        f"{float(row['observation_count']):,.0f} observations"
    )
    return (
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{COLORS[endpoint]}" '
        f'stroke="white" stroke-width="1.2"><title>{escape(title)}</title></circle>'
    )


def generate_by_observation_count(rows: list[dict[str, str | float]]) -> None:
    width, height = 1400, 920
    left, right, top, bottom = 95, 30, 105, 75
    panel_gap = 55
    panel_height = (height - top - bottom - panel_gap) / 2
    panel_width = (width - left - right - panel_gap) / 2
    x_min, x_max = 1_000_000.0, 60_000_000.0
    y_min, y_max = 10_000.0, 2_000_000.0

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        text(
            width / 2,
            34,
            "Completed response throughput by observation count",
            text_anchor="middle",
            font_family="sans-serif",
            font_size="22",
            font_weight="bold",
        ),
        text(
            width / 2,
            58,
            "Logarithmic axes; points are runs and lines connect medians at each workload",
            text_anchor="middle",
            font_family="sans-serif",
            font_size="13",
            fill="#555",
        ),
    ]

    for panel_index, format_name in enumerate(FORMATS):
        column = panel_index % 2
        row_index = panel_index // 2
        x0 = left + column * (panel_width + panel_gap)
        y0 = top + row_index * (panel_height + panel_gap)
        plot_bottom = y0 + panel_height

        def x_position(observation_count: float) -> float:
            fraction = (math.log10(observation_count) - math.log10(x_min)) / (
                math.log10(x_max) - math.log10(x_min)
            )
            return x0 + fraction * panel_width

        def y_position(rate: float) -> float:
            fraction = (math.log10(rate) - math.log10(y_min)) / (
                math.log10(y_max) - math.log10(y_min)
            )
            return plot_bottom - fraction * panel_height

        svg.append(
            text(
                x0,
                y0 - 13,
                format_name.upper(),
                font_family="sans-serif",
                font_size="17",
                font_weight="bold",
            )
        )
        for tick in (10_000, 30_000, 100_000, 300_000, 1_000_000):
            y = y_position(tick)
            svg.append(
                f'<line x1="{x0:.1f}" y1="{y:.1f}" x2="{x0 + panel_width:.1f}" y2="{y:.1f}" stroke="#e2e2e2"/>'
            )
            svg.append(
                text(
                    x0 - 8,
                    y + 4,
                    f"{tick:,.0f}",
                    text_anchor="end",
                    font_family="sans-serif",
                    font_size="10",
                    fill="#555",
                )
            )
        svg.append(
            f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x0:.1f}" y2="{plot_bottom:.1f}" stroke="#777"/>'
        )
        svg.append(
            f'<line x1="{x0:.1f}" y1="{plot_bottom:.1f}" x2="{x0 + panel_width:.1f}" y2="{plot_bottom:.1f}" stroke="#777"/>'
        )

        for tick in (1_000_000, 3_000_000, 10_000_000, 30_000_000):
            x = x_position(tick)
            svg.append(
                f'<line x1="{x:.1f}" y1="{y0:.1f}" x2="{x:.1f}" y2="{plot_bottom:.1f}" stroke="#eeeeee"/>'
            )
            if row_index == 1:
                svg.append(
                    text(
                        x,
                        plot_bottom + 18,
                        f"{tick / 1_000_000:g}M",
                        text_anchor="middle",
                        font_family="sans-serif",
                        font_size="10",
                        fill="#555",
                    )
                )

        for endpoint in ("prime", "legacy"):
            endpoint_rows = [
                result
                for result in rows
                if result["format"] == format_name and result["endpoint"] == endpoint
            ]
            rates_by_count: dict[float, list[float]] = {}
            for result in endpoint_rows:
                count = float(result["observation_count"])
                rates_by_count.setdefault(count, []).append(
                    float(result["bytes_per_second"])
                )
            median_points = [
                (x_position(count), y_position(median(rates)))
                for count, rates in sorted(rates_by_count.items())
            ]
            if len(median_points) > 1:
                points = " ".join(f"{x:.1f},{y:.1f}" for x, y in median_points)
                svg.append(
                    f'<polyline points="{points}" fill="none" stroke="{COLORS[endpoint]}" stroke-width="2.5"/>'
                )
            svg.extend(
                point(
                    x_position(float(result["observation_count"])),
                    y_position(float(result["bytes_per_second"])),
                    result,
                )
                for result in endpoint_rows
            )

    svg.append(
        text(
            24,
            height / 2,
            "Bytes / second",
            transform=f"rotate(-90 24 {height / 2:.1f})",
            text_anchor="middle",
            font_family="sans-serif",
            font_size="13",
        )
    )
    svg.append(
        text(
            width / 2,
            height - 12,
            "Frontend approximate observation count",
            text_anchor="middle",
            font_family="sans-serif",
            font_size="13",
        )
    )
    legend_x = width - 245
    for offset, endpoint in enumerate(("prime", "legacy")):
        x = legend_x + offset * 105
        svg.append(
            f'<line x1="{x}" y1="31" x2="{x + 25}" y2="31" stroke="{COLORS[endpoint]}" stroke-width="3"/>'
        )
        svg.append(
            text(x + 31, 35, endpoint.title(), font_family="sans-serif", font_size="12")
        )
    svg.append("</svg>")
    BY_OBSERVATION_COUNT_PATH.write_text("\n".join(svg) + "\n", encoding="utf-8")


def generate_ec_bch(rows: list[dict[str, str | float]]) -> None:
    width, height = 900, 560
    left, right, top, bottom = 95, 40, 105, 95
    plot_width = width - left - right
    plot_height = height - top - bottom
    latest: dict[tuple[str, str], dict[str, str | float]] = {}
    for row in rows:
        if row["run"] == "ecraw_bch":
            latest[(str(row["format"]), str(row["endpoint"]))] = row
        elif row["run"] == "rustpy_xlsx":
            latest[("xlsx", str(row["endpoint"]))] = row
    max_rate = 1_000_000.0

    def x_position(index: int) -> float:
        return left + index * plot_width / (len(FORMATS) - 1)

    def y_position(rate: float) -> float:
        return top + plot_height - rate / max_rate * plot_height

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        text(
            width / 2,
            34,
            "EC_raw/BCH throughput: Prime vs Legacy",
            text_anchor="middle",
            font_family="sans-serif",
            font_size="22",
            font_weight="bold",
        ),
        text(
            width / 2,
            58,
            "RustPy rerun used for XLSX; missing Legacy CSV did not complete",
            text_anchor="middle",
            font_family="sans-serif",
            font_size="13",
            fill="#555",
        ),
    ]
    for tick in range(0, 1_000_001, 200_000):
        y = y_position(float(tick))
        svg.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_width}" y2="{y:.1f}" stroke="#e2e2e2"/>'
        )
        svg.append(
            text(
                left - 9,
                y + 4,
                f"{tick:,.0f}",
                text_anchor="end",
                font_family="sans-serif",
                font_size="11",
                fill="#555",
            )
        )
    svg.append(
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#777"/>'
    )
    svg.append(
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}" stroke="#777"/>'
    )

    for endpoint in ("prime", "legacy"):
        segment: list[tuple[float, float, dict[str, str | float]]] = []
        for index, format_name in enumerate(FORMATS):
            result = latest.get((format_name, endpoint))
            if result is None:
                if len(segment) > 1:
                    points = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in segment)
                    svg.append(
                        f'<polyline points="{points}" fill="none" stroke="{COLORS[endpoint]}" stroke-width="3"/>'
                    )
                svg.extend(point(x, y, item) for x, y, item in segment)
                segment = []
                continue
            segment.append(
                (
                    x_position(index),
                    y_position(float(result["bytes_per_second"])),
                    result,
                )
            )
        if len(segment) > 1:
            points = " ".join(f"{x:.1f},{y:.1f}" for x, y, _ in segment)
            svg.append(
                f'<polyline points="{points}" fill="none" stroke="{COLORS[endpoint]}" stroke-width="3"/>'
            )
        svg.extend(point(x, y, item) for x, y, item in segment)

    for index, format_name in enumerate(FORMATS):
        svg.append(
            text(
                x_position(index),
                top + plot_height + 28,
                format_name.upper(),
                text_anchor="middle",
                font_family="sans-serif",
                font_size="13",
            )
        )
    svg.append(
        text(
            25,
            top + plot_height / 2,
            "Bytes / second",
            transform=f"rotate(-90 25 {top + plot_height / 2:.1f})",
            text_anchor="middle",
            font_family="sans-serif",
            font_size="13",
        )
    )
    for offset, endpoint in enumerate(("prime", "legacy")):
        x = width - 230 + offset * 105
        svg.append(
            f'<line x1="{x}" y1="82" x2="{x + 25}" y2="82" stroke="{COLORS[endpoint]}" stroke-width="3"/>'
        )
        svg.append(
            text(x + 31, 86, endpoint.title(), font_family="sans-serif", font_size="12")
        )
    svg.append("</svg>")
    EC_BCH_PATH.write_text("\n".join(svg) + "\n", encoding="utf-8")


def generate_rustpy_xlsx(rows: list[dict[str, str | float]]) -> None:
    width, height = 900, 560
    left, right, top, bottom = 100, 45, 105, 85
    plot_width = width - left - right
    plot_height = height - top - bottom
    x_min, x_max = 1_000_000.0, 60_000_000.0
    y_min, y_max = 100_000.0, 1_500_000.0
    series = {
        "Prime pre-RustPy": {
            "color": "#1769aa",
            "rows": [
                row
                for row in rows
                if row["format"] == "xlsx"
                and row["endpoint"] == "prime"
                and row["xlsx_engine"] == "pre_rustpy"
            ],
        },
        "Prime RustPy": {
            "color": "#e07a1f",
            "rows": [
                row
                for row in rows
                if row["format"] == "xlsx"
                and row["endpoint"] == "prime"
                and row["xlsx_engine"] == "rustpy"
            ],
        },
        "Legacy": {
            "color": "#d1495b",
            "rows": [
                row
                for row in rows
                if row["format"] == "xlsx" and row["endpoint"] == "legacy"
            ],
        },
    }

    def x_position(observation_count: float) -> float:
        fraction = (math.log10(observation_count) - math.log10(x_min)) / (
            math.log10(x_max) - math.log10(x_min)
        )
        return left + fraction * plot_width

    def y_position(rate: float) -> float:
        fraction = (math.log10(rate) - math.log10(y_min)) / (
            math.log10(y_max) - math.log10(y_min)
        )
        return top + plot_height - fraction * plot_height

    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        text(
            width / 2,
            34,
            "XLSX throughput by observation count",
            text_anchor="middle",
            font_family="sans-serif",
            font_size="22",
            font_weight="bold",
        ),
        text(
            width / 2,
            58,
            "August 20 pre-RustPy runs separated from RustPy runs; logarithmic axes",
            text_anchor="middle",
            font_family="sans-serif",
            font_size="13",
            fill="#555",
        ),
    ]

    for tick in (100_000, 300_000, 1_000_000):
        y = y_position(tick)
        svg.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_width}" y2="{y:.1f}" stroke="#e2e2e2"/>'
        )
        svg.append(
            text(
                left - 9,
                y + 4,
                f"{tick:,.0f}",
                text_anchor="end",
                font_family="sans-serif",
                font_size="11",
                fill="#555",
            )
        )
    for tick in (1_000_000, 3_000_000, 10_000_000, 30_000_000):
        x = x_position(tick)
        svg.append(
            f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_height}" stroke="#eeeeee"/>'
        )
        svg.append(
            text(
                x,
                top + plot_height + 22,
                f"{tick / 1_000_000:g}M",
                text_anchor="middle",
                font_family="sans-serif",
                font_size="11",
                fill="#555",
            )
        )
    svg.append(
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#777"/>'
    )
    svg.append(
        f'<line x1="{left}" y1="{top + plot_height}" x2="{left + plot_width}" y2="{top + plot_height}" stroke="#777"/>'
    )

    for label, details in series.items():
        color = str(details["color"])
        series_rows = list(details["rows"])
        rates_by_count: dict[float, list[float]] = {}
        for result in series_rows:
            count = float(result["observation_count"])
            rates_by_count.setdefault(count, []).append(
                float(result["bytes_per_second"])
            )
        median_points = [
            (x_position(count), y_position(median(rates)))
            for count, rates in sorted(rates_by_count.items())
        ]
        if len(median_points) > 1:
            points = " ".join(f"{x:.1f},{y:.1f}" for x, y in median_points)
            svg.append(
                f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="3"/>'
            )
        for result in series_rows:
            x = x_position(float(result["observation_count"]))
            y = y_position(float(result["bytes_per_second"]))
            rate = float(result["bytes_per_second"])
            title = (
                f"{result['measurement_date']}; {label}; {result['case']}: "
                f"{rate:,.0f} B/s; "
                f"{float(result['observation_count']):,.0f} observations"
            )
            shape = (
                f'<rect x="{x - 5:.1f}" y="{y - 5:.1f}" width="10" height="10" '
                if label == "Prime RustPy"
                else f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4.5" '
            )
            svg.append(
                f'{shape}fill="{color}" stroke="white" stroke-width="1.2"><title>{escape(title)}</title>'
                + ("</rect>" if label == "Prime RustPy" else "</circle>")
            )

    svg.append(
        text(
            25,
            top + plot_height / 2,
            "Bytes / second",
            transform=f"rotate(-90 25 {top + plot_height / 2:.1f})",
            text_anchor="middle",
            font_family="sans-serif",
            font_size="13",
        )
    )
    svg.append(
        text(
            left + plot_width / 2,
            height - 14,
            "Frontend approximate observation count",
            text_anchor="middle",
            font_family="sans-serif",
            font_size="13",
        )
    )
    legend_x = width - 390
    for offset, (label, details) in enumerate(series.items()):
        x = legend_x + offset * 125
        color = str(details["color"])
        svg.append(
            f'<line x1="{x}" y1="82" x2="{x + 22}" y2="82" stroke="{color}" stroke-width="3"/>'
        )
        svg.append(text(x + 27, 86, label, font_family="sans-serif", font_size="11"))
    svg.append("</svg>")
    RUSTPY_XLSX_PATH.write_text("\n".join(svg) + "\n", encoding="utf-8")


def main() -> None:
    rows = load_rows()
    generate_by_observation_count(rows)
    generate_ec_bch(rows)
    generate_rustpy_xlsx(rows)


if __name__ == "__main__":
    main()
