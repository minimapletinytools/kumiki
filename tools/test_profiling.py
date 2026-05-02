#!/usr/bin/env python3
"""
Profiling script for all Kumiki patterns.

Imports every pattern module, builds each pattern, profiles execution time
and call counts, then writes results to a text file.

Usage:
    python test_profiling.py                      # profile all patterns
    python test_profiling.py oscarshed kumiki      # profile specific patterns

Output goes to step_test_output/profiling_results.txt
"""

import sys
import time
import cProfile
import pstats
import io
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "patterns" / "structures"))

# Registry of all known patterns: (name, import_func)
# import_func is a callable that returns (module_func, args) to defer imports
PATTERN_REGISTRY = {
    # Structures (return Frame)
    "kumiki": lambda: (__import__("kumiki_example", fromlist=["create_sawhorse"]).create_sawhorse, []),
    "oscarshed": lambda: (__import__("oscarshed", fromlist=["create_oscarshed"]).create_oscarshed, []),
    "gateway": lambda: (__import__("gateway_example", fromlist=["create_gateway"]).create_gateway, []),
    "ladder": lambda: (__import__("ladder_example", fromlist=["create_ladder_frame"]).create_ladder_frame, []),
    "honeycomb_shed": lambda: (__import__("new_shed", fromlist=["create_honeycomb_shed"]).create_honeycomb_shed, []),
    "sillyshed": lambda: (__import__("sillyshed_example", fromlist=["create_sillyshed_frame"]).create_sillyshed_frame, []),
    "tinyhouse120": lambda: (__import__("tinyhouse120", fromlist=["create_tinyhouse120"]).create_tinyhouse120, []),
    # Joint examples (return PatternBook)
    "basic_joints": lambda: (__import__("patterns.basic_joints_examples", fromlist=["create_basic_joints_patternbook"]).create_basic_joints_patternbook, []),
    "mortise_and_tenon": lambda: (__import__("patterns.mortise_and_tenon_joint_examples", fromlist=["create_mortise_and_tenon_patternbook"]).create_mortise_and_tenon_patternbook, []),
    "plain_joints": lambda: (__import__("patterns.plain_joints_example", fromlist=["create_plain_joints_patternbook"]).create_plain_joints_patternbook, []),
    "irrational_angles": lambda: (__import__("patterns.irrational_angles_example", fromlist=["create_irrational_angles_patternbook"]).create_irrational_angles_patternbook, []),
    "construction": lambda: (__import__("patterns.construction_examples", fromlist=["create_construction_patternbook"]).create_construction_patternbook, []),
    "double_butt_joints": lambda: (__import__("patterns.double_butt_joints_example", fromlist=["create_double_butt_joints_patternbook"]).create_double_butt_joints_patternbook, []),
    "japanese_joints": lambda: (__import__("patterns.japanese_joints_example", fromlist=["create_japanese_joints_patternbook"]).create_japanese_joints_patternbook, []),
    "csg_debug": lambda: (__import__("patterns.CSG_debug_examples", fromlist=["create_csg_examples_patternbook"]).create_csg_examples_patternbook, []),
    "patternbook_example": lambda: (__import__("patterns.patternbook_example", fromlist=["create_patternbook_example_patternbook"]).create_patternbook_example_patternbook, []),
}


def profile_pattern(name, func, args):
    """Profile a single pattern build. Returns (result, wall_time, pstats_text)."""
    profiler = cProfile.Profile()

    t0 = time.perf_counter()
    profiler.enable()
    try:
        result = func(*args)
    finally:
        profiler.disable()
    wall_time = time.perf_counter() - t0

    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats("cumulative")
    stats.print_stats(30)
    pstats_text = stream.getvalue()

    return result, wall_time, pstats_text


def profile_timber_hashing(result):
    """Hash all timbers in a Frame result. Returns (hash_time, timber_count) or (None, 0)."""
    from kumiki.timber import Frame

    if not isinstance(result, Frame):
        return None, 0

    timbers = result.cut_timbers
    t0 = time.perf_counter()
    for timber in timbers:
        timber.deep_hash()
    hash_time = time.perf_counter() - t0
    return hash_time, len(timbers)


def describe_result(result):
    """Return a short description of the build result."""
    from kumiki.timber import Frame
    from kumiki.patternbook import PatternBook

    if isinstance(result, Frame):
        return f"Frame with {len(result.cut_timbers)} timbers"
    elif isinstance(result, PatternBook):
        patterns = result.list_patterns()
        return f"PatternBook with {len(patterns)} patterns"
    else:
        return f"{type(result).__name__}"


def main():
    requested = sys.argv[1:] if len(sys.argv) > 1 else sorted(PATTERN_REGISTRY.keys())

    unknown = [p for p in requested if p not in PATTERN_REGISTRY]
    if unknown:
        print(f"Unknown patterns: {', '.join(unknown)}")
        print(f"Available: {', '.join(sorted(PATTERN_REGISTRY.keys()))}")
        sys.exit(1)

    output_dir = PROJECT_ROOT / "step_test_output"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "profiling_results.txt"

    lines = []
    lines.append(f"Kumiki Pattern Profiling Results")
    lines.append(f"Date: {datetime.now().isoformat()}")
    lines.append(f"Python: {sys.version}")
    lines.append(f"Patterns: {len(requested)}")
    lines.append("=" * 80)

    summary_rows = []

    for name in requested:
        print(f"Profiling: {name} ... ", end="", flush=True)
        try:
            func, args = PATTERN_REGISTRY[name]()
            result, wall_time, pstats_text = profile_pattern(name, func, args)
            description = describe_result(result)
            hash_time, timber_count = profile_timber_hashing(result)
            hash_info = f", hash {timber_count} timbers: {hash_time:.3f}s" if hash_time is not None else ""
            print(f"{wall_time:.2f}s ({description}{hash_info})")

            summary_rows.append((name, wall_time, hash_time, timber_count, description, None))

            lines.append("")
            lines.append(f"Pattern: {name}")
            lines.append(f"  Wall time: {wall_time:.3f}s")
            if hash_time is not None:
                lines.append(f"  Timber hash time: {hash_time:.3f}s ({timber_count} timbers)")
            lines.append(f"  Result: {description}")
            lines.append(f"  Top 30 calls by cumulative time:")
            lines.append(pstats_text)
            lines.append("-" * 80)

        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            print(f"FAILED: {e}")
            summary_rows.append((name, None, None, 0, None, str(e)))
            lines.append("")
            lines.append(f"Pattern: {name}")
            lines.append(f"  FAILED: {e}")
            lines.append(f"  {tb}")
            lines.append("-" * 80)

    # Summary table
    lines.append("")
    lines.append("=" * 80)
    lines.append("SUMMARY")
    lines.append("=" * 80)
    lines.append(f"{'Pattern':<25} {'Build (s)':>10} {'Hash (s)':>10}  {'Result'}")
    lines.append("-" * 80)
    total_time = 0.0
    total_hash_time = 0.0
    for name, wall_time, hash_time, timber_count, description, error in summary_rows:
        if error:
            lines.append(f"{name:<25} {'FAILED':>10} {'':>10}  {error}")
        else:
            hash_col = f"{hash_time:.3f}" if hash_time is not None else "n/a"
            lines.append(f"{name:<25} {wall_time:>10.3f} {hash_col:>10}  {description}")
            total_time += wall_time
            if hash_time is not None:
                total_hash_time += hash_time
    lines.append("-" * 80)
    lines.append(f"{'TOTAL':<25} {total_time:>10.3f} {total_hash_time:>10.3f}")

    report = "\n".join(lines) + "\n"
    output_file.write_text(report)
    print(f"\nResults written to {output_file}")
    print(f"Total time: {total_time:.2f}s")


if __name__ == "__main__":
    main()
