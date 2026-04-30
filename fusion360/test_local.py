#!/usr/bin/env python3
"""
Test script to verify that all Kumiki dependencies work locally.
This simulates what Fusion 360 will do when importing our modules.
"""

import sys
import os

# Add the local libs directory, current script directory, and parent directory to sys.path (same as in giraffetest.py)
script_dir = os.path.dirname(os.path.realpath(__file__))
libs_dir = os.path.join(script_dir, 'libs')
parent_dir = os.path.dirname(script_dir)

if libs_dir not in sys.path:
    sys.path.insert(0, libs_dir)
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

def test_dependencies():
    """Test that all dependencies can be imported."""
    print("Testing dependency imports...")
    
    try:
        import sympy
        print(f"✓ sympy {sympy.__version__} imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import sympy: {e}")
        return False
    
    try:
        import mpmath
        print(f"✓ mpmath {mpmath.__version__} imported successfully")
    except ImportError as e:
        print(f"✗ Failed to import mpmath: {e}")
        return False
    
    print("✓ numpy not required (removed from dependencies)")
    
    return True

def test_kumiki_modules():
    """Test that Kumiki modules can be imported from parent directory."""
    print("\nTesting Kumiki module imports from parent directory...")
    
    try:
        from kumiki.rule import Orientation
        print("✓ rule.Orientation imported successfully from parent dir")
    except ImportError as e:
        print(f"✗ Failed to import rule from parent dir: {e}")
        return False
    
    try:
        from kumiki import CutTimber, Timber, create_v3
        print("✓ giraffe core classes imported successfully from parent dir")
    except ImportError as e:
        print(f"✗ Failed to import kumiki from parent dir: {e}")
        return False
    
    try:
        from patterns.structures.kumiki_example import create_sawhorse
        print("✓ sawhorse_example imported successfully from parent dir")
    except ImportError as e:
        print(f"✗ Failed to import sawhorse_example from parent dir: {e}")
        return False
    
    # Note: We can't test giraffe_render_fusion360 outside of Fusion 360
    # because it depends on adsk modules, but we can test that the file exists
    try:
        import kumiki_render_fusion360
        print("✓ giraffe_render_fusion360 found in current dir (requires Fusion 360 to run)")
    except ImportError as e:
        if "adsk" in str(e):
            print("✓ giraffe_render_fusion360 found in current dir (adsk modules missing - normal outside Fusion 360)")
        else:
            print(f"✗ Failed to find giraffe_render_fusion360 in current dir: {e}")
            return False
    
    return True

def test_sawhorse_creation():
    """Test that we can create a sawhorse using path imports."""
    print("\nTesting sawhorse creation with path imports...")
    
    try:
        from patterns.structures.kumiki_example import create_sawhorse
        sawhorse = create_sawhorse()
        cut_timbers = sawhorse.cut_timbers if hasattr(sawhorse, 'cut_timbers') else sawhorse
        
        print(f"✓ Created sawhorse with {len(cut_timbers)} timbers:")
        for i, cut_timber in enumerate(cut_timbers):
            timber = cut_timber.timber
            print(f"    {i+1}. Length={timber.length:.3f}m, "
                  f"Size=({float(timber.size[0]):.3f}m x {float(timber.size[1]):.3f}m), "
                  f"Joints={len(cut_timber.joints)}")
        
        return True
        
    except Exception as e:
        print(f"✗ Failed to create sawhorse: {e}")
        import traceback
        print(traceback.format_exc())
        return False

def test_path_structure():
    """Test that the expected file structure exists."""
    print("\nTesting file structure...")
    
    script_dir = os.path.dirname(os.path.realpath(__file__))
    parent_dir = os.path.dirname(script_dir)
    
    # Files that should be in parent directory
    parent_required_files = [
        'giraffe.py',
        'kumiki/rule.py', 
        'patterns/structures/kumiki_example.py',
    ]
    
    # Files that should be in current (fusion360) directory
    local_required_files = [
        'giraffe_render_fusion360.py'
    ]
    
    missing_files = []
    for filename in parent_required_files:
        filepath = os.path.join(parent_dir, filename)
        if os.path.exists(filepath):
            print(f"✓ Found {filename} in parent directory")
        else:
            print(f"✗ Missing {filename} in parent directory")
            missing_files.append(filename)
    
    for filename in local_required_files:
        filepath = os.path.join(script_dir, filename)
        if os.path.exists(filepath):
            print(f"✓ Found {filename} in current directory")
        else:
            print(f"✗ Missing {filename} in current directory")
            missing_files.append(filename)
    
    libs_dir = os.path.join(script_dir, 'libs')
    if os.path.exists(libs_dir):
        print(f"✓ Found libs directory: {libs_dir}")
    else:
        print(f"✗ Missing libs directory: {libs_dir}")
        missing_files.append('libs/')
    
    return len(missing_files) == 0

def main():
    """Run all tests."""
    print("Kumiki Local Dependency Test (Path Import Version)")
    print("=" * 50)
    
    all_passed = True
    
    if not test_path_structure():
        all_passed = False
        print("⚠️  File structure issues found. Some tests may fail.")
    
    if not test_dependencies():
        all_passed = False
    
    if not test_giraffe_modules():
        all_passed = False
    
    if not test_sawhorse_creation():
        all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 All tests passed! Ready for Fusion 360.")
        print("📁 Using path imports - no file duplication!")
    else:
        print("❌ Some tests failed. Check the errors above.")
    
    return all_passed

if __name__ == "__main__":
    main() 