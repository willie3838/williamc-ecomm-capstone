#!/usr/bin/env python3
"""Span Analysis and Distributed Trace Inspection Tool.

Provides CLI diagnostics for:
1. Local execution profiling via InMemorySpanExporter:
   Measures latency across pipeline nodes (Intent -> Retrieval -> Relevance -> Synthesis),
   fine-grained Gemini LLM spans, and outputs an ASCII waterfall diagram and timing table.
2. Remote Google Cloud Trace inspection:
   Fetches and visualizes production distributed trace spans given a Trace ID.

Usage:
    # Analyze a local query run hermetically or live
    python scripts/analyze_spans.py --query "MacBook Air vs Dell XPS 13"

    # Analyze with specific model routing
    python scripts/analyze_spans.py --query "Sony WH-1000XM5 vs Bose QC Ultra" --model tiered-hybrid

    # Inspect a production Cloud Trace by Trace ID
    python scripts/analyze_spans.py --trace-id 4bf92f3577b34da6a3ce929d0e0e4736

    # Output machine-readable JSON
    python scripts/analyze_spans.py --query "iPad Pro vs Galaxy Tab" --format json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any

# Ensure backend/src is on sys.path
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from opentelemetry.sdk.trace import ReadableSpan

from app.config import settings
from app.observability.tracing import get_in_memory_exporter, setup_tracing


@dataclass
class SpanReportItem:
    name: str
    trace_id: str
    span_id: str
    parent_span_id: str | None
    start_time_ns: int
    end_time_ns: int
    duration_ms: float
    offset_ms: float
    attributes: dict[str, Any]
    status: str


def _format_ascii_waterfall(items: list[SpanReportItem], total_duration_ms: float) -> str:
    """Render a text-based ASCII Gantt/waterfall chart of span execution."""
    if not items:
        return "No spans recorded."

    chart_width = 40
    lines = []
    lines.append("\n" + "=" * 80)
    lines.append(f"{'SPAN NAME':<34} | {'DURATION':<10} | {'WATERFALL TIMELINE':<32}")
    lines.append("-" * 80)

    for item in items:
        start_ratio = (item.offset_ms / total_duration_ms) if total_duration_ms > 0 else 0
        dur_ratio = (item.duration_ms / total_duration_ms) if total_duration_ms > 0 else 0

        start_col = int(start_ratio * chart_width)
        bar_len = max(1, int(dur_ratio * chart_width))
        bar_str = " " * start_col + "█" * bar_len

        truncated_name = (item.name[:31] + "...") if len(item.name) > 34 else item.name
        dur_str = f"{item.duration_ms:8.2f} ms"
        lines.append(f"{truncated_name:<34} | {dur_str} | {bar_str}")

    lines.append("=" * 80)
    return "\n".join(lines)


def analyze_local_query(
    query: str,
    category: str | None = None,
    model: str | None = None,
    offline: bool = False,
    output_format: str = "text",
) -> int:
    """Execute query locally and inspect recorded spans."""
    # Ensure tracing is initialized with in-memory exporter
    setup_tracing()
    exporter = get_in_memory_exporter()
    exporter.clear()

    print(f"[*] Executing pipeline for query: '{query}' (model: {model or 'default'})...")

    from app.agent.multi_agent import MultiAgentCoordinator

    bq_client = None
    if offline:
        from app.agent.hermetic_adapter import create_hermetic_bq_client

        bq_client = create_hermetic_bq_client()

    try:
        coordinator = MultiAgentCoordinator(bq_client=bq_client, model=model)
        t_start = time.perf_counter()
        response = coordinator.execute(
            raw_query=query,
            category=category,
            model=model,
        )
        t_end = time.perf_counter()
    except Exception as exc:
        err_str = str(exc).lower()
        if "reauth" in err_str or "credentials" in err_str or "401" in err_str:
            print(
                f"[*] Live GCP credentials unavailable ({exc}). Profiling using hermetic grounded adapter..."
            )
            from app.agent.hermetic_adapter import create_hermetic_bq_client

            exporter.clear()
            coordinator = MultiAgentCoordinator(bq_client=create_hermetic_bq_client(), model=model)
            t_start = time.perf_counter()
            response = coordinator.execute(
                raw_query=query,
                category=category,
                model=model,
            )
            t_end = time.perf_counter()
        else:
            raise

    wall_clock_ms = round((t_end - t_start) * 1000.0, 2)

    finished_spans: list[ReadableSpan] = exporter.get_finished_spans()
    if not finished_spans:
        print("[!] No spans were captured by the InMemorySpanExporter.")
        return 1

    # Sort spans by start_time
    sorted_spans = sorted(finished_spans, key=lambda s: s.start_time)
    min_start_ns = sorted_spans[0].start_time
    max_end_ns = max(s.end_time for s in sorted_spans)
    total_span_duration_ms = round((max_end_ns - min_start_ns) / 1_000_000.0, 2)

    report_items: list[SpanReportItem] = []
    for s in sorted_spans:
        offset_ms = round((s.start_time - min_start_ns) / 1_000_000.0, 2)
        dur_ms = round((s.end_time - s.start_time) / 1_000_000.0, 2)
        parent_id = f"{s.parent.span_id:016x}" if s.parent else None
        attrs = dict(s.attributes or {})
        report_items.append(
            SpanReportItem(
                name=s.name,
                trace_id=f"{s.context.trace_id:032x}",
                span_id=f"{s.context.span_id:016x}",
                parent_span_id=parent_id,
                start_time_ns=s.start_time,
                end_time_ns=s.end_time,
                duration_ms=dur_ms,
                offset_ms=offset_ms,
                attributes=attrs,
                status=s.status.status_code.name,
            )
        )

    if output_format == "json":
        output_data = {
            "query": query,
            "wall_clock_ms": wall_clock_ms,
            "total_span_duration_ms": total_span_duration_ms,
            "timing_breakdown_ms": response.timing_breakdown_ms,
            "spans": [asdict(item) for item in report_items],
        }
        print(json.dumps(output_data, indent=2))
        return 0

    # Text report
    print("\n" + "=" * 80)
    print(" PIPELINE EXECUTION & SPAN LATENCY ANALYSIS")
    print("=" * 80)
    print(f" Query:                  {query}")
    print(f" Active Model:           {response.model_version or model}")
    print(f" Synthesis Model:        {response.synthesis_model}")
    print(f" Wall-clock Latency:     {wall_clock_ms:.2f} ms")
    print(f" Total Span Duration:    {total_span_duration_ms:.2f} ms")
    print(f" Products Compared:      {len(response.products)}")
    print(f" Matrix Rows Built:      {len(response.comparison_matrix)}")

    if response.timing_breakdown_ms:
        print("\n--- Pipeline Stage Breakdown (X-Pipeline-Timing) ---")
        for stage, duration in response.timing_breakdown_ms.items():
            pct = (duration / wall_clock_ms * 100) if wall_clock_ms > 0 else 0
            print(f"  • {stage:<22}: {duration:8.2f} ms ({pct:5.1f}%)")

    print(_format_ascii_waterfall(report_items, total_span_duration_ms))

    print("\n--- Key Span Attributes & Model Metrics ---")
    for item in report_items:
        key_attrs = {
            k: v
            for k, v in item.attributes.items()
            if any(
                prefix in k for prefix in ("gen_ai.", "ai.", "pipeline.", "candidates.", "agent.")
            )
        }
        if key_attrs:
            print(f"  [{item.name}] ({item.duration_ms:.2f} ms)")
            for k, v in key_attrs.items():
                print(f"    - {k}: {v}")

    return 0


def analyze_remote_trace(trace_id: str, output_format: str = "text") -> int:
    """Fetch and inspect spans for a given Cloud Trace ID from Google Cloud Trace."""
    print(
        f"[*] Fetching trace spans for Trace ID: {trace_id} from GCP project: {settings.gcp_project}..."
    )
    try:
        from google.cloud import trace_v2

        client = trace_v2.TraceServiceClient()
        project_name = f"projects/{settings.gcp_project}"
        # Cloud Trace trace_id is formatted as 32 hex chars
        trace_name = f"{project_name}/traces/{trace_id}"

        # List spans for trace
        spans_pager = client.list_spans(parent=trace_name)
        remote_spans = list(spans_pager)

        if not remote_spans:
            print(
                f"[!] No spans found in Cloud Trace for {trace_name}. (Spans may take 10-30s to ingest)."
            )
            return 1

        print(f"[+] Successfully retrieved {len(remote_spans)} spans from Google Cloud Trace.")

        if output_format == "json":
            json_spans = [
                {
                    "name": s.display_name.value if s.display_name else s.name,
                    "span_id": s.span_id,
                    "parent_span_id": s.parent_span_id,
                    "start_time": s.start_time.isoformat() if s.start_time else None,
                    "end_time": s.end_time.isoformat() if s.end_time else None,
                    "attributes": {k: str(v) for k, v in s.attributes.attribute_map.items()}
                    if s.attributes
                    else {},
                }
                for s in remote_spans
            ]
            print(json.dumps(json_spans, indent=2))
            return 0

        for s in remote_spans:
            name = s.display_name.value if s.display_name else s.name
            print(f"  • Span: {name} (ID: {s.span_id}, Parent: {s.parent_span_id})")
            if s.attributes and s.attributes.attribute_map:
                for k, v in s.attributes.attribute_map.items():
                    print(f"      - {k}: {v.string_value.value if v.string_value else v}")
        return 0

    except Exception as err:
        print(f"[!] Error fetching Cloud Trace: {err}")
        print(
            "    Note: Ensure Application Default Credentials (ADC) or GOOGLE_APPLICATION_CREDENTIALS are configured."
        )
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Span Analysis and Distributed Trace Inspection Tool for Catalog Comparison Service.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--query", "-q", type=str, help="Natural language query to execute locally and profile."
    )
    group.add_argument(
        "--trace-id",
        "-t",
        type=str,
        help="Google Cloud Trace ID (32 hex characters) to fetch and inspect.",
    )

    parser.add_argument(
        "--category", "-c", type=str, default=None, help="Optional category filter."
    )
    parser.add_argument(
        "--model",
        "-m",
        type=str,
        default=None,
        help="LLM model to use (e.g. tiered-hybrid, gemini-2.5-flash).",
    )
    parser.add_argument(
        "--offline", action="store_true", help="Run with hermetic catalog and offline model."
    )
    parser.add_argument(
        "--format", "-f", choices=["text", "json"], default="text", help="Output format."
    )

    args = parser.parse_args()

    if args.query:
        sys.exit(
            analyze_local_query(
                args.query,
                category=args.category,
                model=args.model,
                offline=args.offline,
                output_format=args.format,
            )
        )
    elif args.trace_id:
        sys.exit(analyze_remote_trace(args.trace_id, output_format=args.format))


if __name__ == "__main__":
    main()
