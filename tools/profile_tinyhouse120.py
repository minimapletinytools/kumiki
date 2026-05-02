#!/usr/bin/env python3
"""
Dedicated profiling test for tinyhouse120 structure.

This test provides detailed timing breakdown and profiling of the tinyhouse120
frame construction and geometry generation to help identify performance bottlenecks.

Usage:
    python profile_tinyhouse120.py            # Run all profiling
    python profile_tinyhouse120.py --quick    # Quick profile (no detailed stats)
    python profile_tinyhouse120.py --hash     # Include timber hashing time
"""

import sys
import time
import cProfile
import pstats
import io
import importlib.util
from pathlib import Path
from datetime import datetime
import argparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from kumiki.rule import set_numeric_mode, get_numeric_mode


def _load_structure_factory(module_name: str, factory_name: str):
    module_path = PROJECT_ROOT / "patterns" / "structures" / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(f"patterns_structures_{module_name}", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    factory = getattr(module, factory_name, None)
    if not callable(factory):
        raise AttributeError(f"{factory_name} is missing or not callable in {module_path}")
    return factory


create_tinyhouse120 = _load_structure_factory("tinyhouse120", "create_tinyhouse120")


def profile_frame_construction(quick=False, hash_timbers=False):
    """
    Profile frame construction with detailed timing breakdown.
    
    Returns dict with timing data:
        {
            'wall_time': float,          # Total wall time in seconds
            'profile_output': str,       # Detailed pstats output
            'timber_count': int,         # Number of timbers in frame
            'hash_time': float or None,  # Time to hash all timbers (if enabled)
        }
    """
    print("=" * 70)
    print("PROFILING: tinyhouse120 Frame Construction")
    print("=" * 70)
    
    # Start profiling construction
    profiler = cProfile.Profile()
    
    print("\n[1/3] Constructing frame...")
    t0 = time.perf_counter()
    profiler.enable()
    
    try:
        frame = create_tinyhouse120()
    finally:
        profiler.disable()
    
    construction_time = time.perf_counter() - t0
    print(f"      ✓ Frame constructed in {construction_time:.3f}s")
    print(f"      ✓ Frame contains {len(frame.cut_timbers)} timbers")
    
    # Generate pstats output
    if not quick:
        print("\n[2/3] Generating detailed statistics...")
        stream = io.StringIO()
        stats = pstats.Stats(profiler, stream=stream)
        stats.sort_stats("cumulative")
        stats.print_stats(50)  # Top 50 functions
        profile_output = stream.getvalue()
        print("      ✓ Statistics generated")
    else:
        profile_output = None
        print("\n[2/3] Skipping detailed statistics (--quick mode)")
    
    # Hash timbers if requested
    hash_time = None
    if hash_timbers:
        print("\n[3/3] Hashing all timbers...")
        t0 = time.perf_counter()
        for timber in frame.cut_timbers:
            timber.deep_hash()
        hash_time = time.perf_counter() - t0
        print(f"      ✓ Hashed {len(frame.cut_timbers)} timbers in {hash_time:.3f}s")
    else:
        print("\n[3/3] Skipping timber hashing (use --hash to enable)")
    
    return {
        'wall_time': construction_time,
        'profile_output': profile_output,
        'timber_count': len(frame.cut_timbers),
        'hash_time': hash_time,
        'frame': frame,
    }


def profile_geometry_generation(frame, num_runs=1):
    """
    Profile geometry generation for the frame using CSG operations.
    Simulates what happens in the viewer when rendering.
    
    Returns dict with timing data:
        {
            'csg_build_times': list[float],  # Time for each CSG build
            'avg_csg_time': float,
            'total_time': float,
        }
    """
    print("\n" + "=" * 70)
    print(f"PROFILING: Geometry Generation (CSG) - {num_runs} run(s)")
    print("=" * 70)
    
    csg_times = []
    
    for i in range(num_runs):
        if num_runs > 1:
            print(f"\nRun {i+1}/{num_runs}:")
        
        t0 = time.perf_counter()
        try:
            # Get the CSG for each timber and combine
            timber_csgs = []
            for timber in frame.cut_timbers:
                if hasattr(timber, 'get_actual_csg_global'):
                    csg = timber.get_actual_csg_global()
                    timber_csgs.append(csg)
            csg_time = time.perf_counter() - t0
            csg_times.append(csg_time)
            print(f"  ✓ CSG generated for {len(timber_csgs)} timbers in {csg_time:.3f}s")
        except Exception as e:
            print(f"  ✗ CSG generation failed: {e}")
            # Don't raise, just skip geometry profiling
            return None
    
    avg_time = sum(csg_times) / len(csg_times) if csg_times else 0
    total_time = sum(csg_times)
    
    return {
        'csg_build_times': csg_times,
        'avg_csg_time': avg_time,
        'total_time': total_time,
    }


def estimate_bottlenecks():
    """
    Estimate where the time is being spent based on quick analysis of the frame.
    """
    print("\n" + "=" * 70)
    print("ANALYSIS: Estimating Performance Bottlenecks")
    print("=" * 70)
    
    frame = create_tinyhouse120()
    
    print(f"\nFrame Statistics:")
    print(f"  • Timbers:                {len(frame.cut_timbers)}")
    
    # Count operations by analyzing cuts
    total_cuts = 0
    for timber in frame.cut_timbers:
        if hasattr(timber, 'cuts') and timber.cuts:
            total_cuts += len(timber.cuts)
    
    print(f"  • Total cuts applied:     {total_cuts}")
    print(f"  • Average cuts per timber: {total_cuts / len(frame.cut_timbers):.1f}")
    
    # Estimate CSG complexity
    print(f"\nEstimated bottlenecks:")
    print(f"  1. Timber construction ({len(frame.cut_timbers)} timbers)")
    print(f"  2. Joint cut computation ({total_cuts} total cuts)")
    print(f"  3. CSG boolean operations (union of {len(frame.cut_timbers)} geometries)")
    
    # Check which timbers have the most cuts
    cuts_per_timber = [(i, len(t.cuts) if hasattr(t, 'cuts') and t.cuts else 0) 
                       for i, t in enumerate(frame.cut_timbers)]
    cuts_per_timber.sort(key=lambda x: x[1], reverse=True)
    
    if cuts_per_timber[:5]:
        print(f"\nTimbers with most cuts:")
        for idx, cut_count in cuts_per_timber[:5]:
            if cut_count > 0:
                print(f"  • Timber {idx}: {cut_count} cuts")


def write_report(filepath, results_construction, results_geometry):
    """Write a detailed profiling report to file."""
    with open(filepath, 'w') as f:
        f.write("=" * 70 + "\n")
        f.write(f"PROFILING REPORT: tinyhouse120\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"Numeric Mode: {get_numeric_mode()}\n")
        f.write("=" * 70 + "\n\n")
        
        # Frame Construction Timing
        f.write("FRAME CONSTRUCTION TIMING\n")
        f.write("-" * 70 + "\n")
        f.write(f"Wall Time:     {results_construction['wall_time']:.3f}s\n")
        f.write(f"Timber Count:  {results_construction['timber_count']}\n")
        if results_construction['hash_time']:
            f.write(f"Hash Time:     {results_construction['hash_time']:.3f}s\n")
        f.write("\n")
        
        # Geometry Generation Timing
        if results_geometry:
            f.write("GEOMETRY GENERATION TIMING\n")
            f.write("-" * 70 + "\n")
            f.write(f"Runs:          {len(results_geometry['csg_build_times'])}\n")
            for i, t in enumerate(results_geometry['csg_build_times']):
                f.write(f"  Run {i+1}:      {t:.3f}s\n")
            f.write(f"Average:       {results_geometry['avg_csg_time']:.3f}s\n")
            f.write(f"Total:         {results_geometry['total_time']:.3f}s\n")
            f.write("\n")
        
        # Detailed pstats
        if results_construction['profile_output']:
            f.write("DETAILED PROFILING STATISTICS\n")
            f.write("-" * 70 + "\n")
            f.write(results_construction['profile_output'])
            f.write("\n")


def main():
    parser = argparse.ArgumentParser(description="Profile tinyhouse120 construction")
    parser.add_argument("--quick", action="store_true", help="Skip detailed pstats output")
    parser.add_argument("--hash", action="store_true", help="Include timber hashing time")
    parser.add_argument("--geometry", type=int, default=1, 
                        help="Number of times to generate geometry (default: 1)")
    parser.add_argument("--numeric-mode", type=str, choices=["symbolic", "float"], default="symbolic",
                        help="Numeric mode for hot math paths (default: symbolic)")
    parser.add_argument("--output", type=str, default=None,
                        help="Write report to file (default: prints to stdout)")
    
    args = parser.parse_args()

    set_numeric_mode(args.numeric_mode)
    print(f"Numeric mode: {get_numeric_mode()}")
    
    # Run profiling
    results_construction = profile_frame_construction(quick=args.quick, hash_timbers=args.hash)
    
    results_geometry = None
    if args.geometry > 0:
        results_geometry = profile_geometry_generation(results_construction['frame'], 
                                                       num_runs=args.geometry)
    
    # Analyze bottlenecks
    estimate_bottlenecks()
    
    # Write report
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_report(output_path, results_construction, results_geometry)
        print(f"\n✓ Report written to {output_path}")
    
    # Print summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Numeric mode:        {get_numeric_mode()}")
    print(f"Frame construction:  {results_construction['wall_time']:.3f}s")
    if results_geometry:
        print(f"Geometry generation: {results_geometry['avg_csg_time']:.3f}s (avg)")
    if results_construction['hash_time']:
        print(f"Timber hashing:      {results_construction['hash_time']:.3f}s")
    print("=" * 70)


if __name__ == "__main__":
    main()
