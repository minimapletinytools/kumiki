#!/usr/bin/env python3
"""
Benchmark script for new_shed.py to measure performance improvements.

This script runs new_shed.py multiple times and reports timing statistics.
"""

import subprocess
import sys
import time
from pathlib import Path


def run_benchmark(num_runs: int = 3):
    """
    Run the benchmark multiple times and report statistics.
    
    Args:
        num_runs: Number of times to run the creation (default 3)
    """
    print("=" * 60)
    print(f"NEW SHED BENCHMARK - {num_runs} runs")
    print("=" * 60)
    print()
    
    times = []
    script_path = Path(__file__).parent / "new_shed.py"
    
    if not script_path.exists():
        print(f"Error: {script_path} not found!")
        return
    
    for run in range(num_runs):
        print(f"\n{'='*60}")
        print(f"RUN {run + 1}/{num_runs}")
        print('='*60)
        
        start_time = time.perf_counter()
        
        try:
            # Run new_shed.py as a subprocess
            result = subprocess.run(
                [sys.executable, "-u", str(script_path)],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
            
            end_time = time.perf_counter()
            elapsed = end_time - start_time
            
            if result.returncode == 0:
                times.append(elapsed)
                print(f"\n✓ Run {run + 1} completed successfully!")
                print(f"  Time: {elapsed:.2f} seconds")
                
                # Show last few lines of output
                output_lines = result.stdout.strip().split('\n')
                if len(output_lines) > 3:
                    print("  Last output lines:")
                    for line in output_lines[-3:]:
                        print(f"    {line}")
            else:
                print(f"\n✗ Run {run + 1} failed with exit code {result.returncode}")
                print(f"  stderr: {result.stderr[:500]}")
                return
                
        except subprocess.TimeoutExpired:
            end_time = time.perf_counter()
            elapsed = end_time - start_time
            print(f"\n✗ Run {run + 1} timed out after {elapsed:.2f} seconds")
            return
        except Exception as e:
            print(f"\n✗ Run {run + 1} failed with error:")
            print(f"  {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return
    
    # Calculate statistics
    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)
    
    if times:
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
        
        print(f"\nRuns completed: {len(times)}/{num_runs}")
        print(f"Average time:   {avg_time:.2f} seconds")
        print(f"Min time:       {min_time:.2f} seconds")
        print(f"Max time:       {max_time:.2f} seconds")
        
        if len(times) > 1:
            # Calculate standard deviation
            variance = sum((t - avg_time) ** 2 for t in times) / len(times)
            std_dev = variance ** 0.5
            print(f"Std deviation:  {std_dev:.2f} seconds")
        
        print("\nIndividual run times:")
        for i, t in enumerate(times, 1):
            print(f"  Run {i}: {t:.2f}s")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    # Allow command-line argument for number of runs
    num_runs = 3
    if len(sys.argv) > 1:
        try:
            num_runs = int(sys.argv[1])
        except ValueError:
            print(f"Invalid number of runs: {sys.argv[1]}")
            print("Usage: python new_shed_benchmark.py [num_runs]")
            sys.exit(1)
    
    run_benchmark(num_runs)
