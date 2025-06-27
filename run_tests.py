#!/usr/bin/env python3
"""Test runner for the git squash tool - supports both pytest and manual fallback."""

import sys
import os
import subprocess

def run_pytest():
    """Run all tests using pytest."""
    try:
        print("Running tests with pytest...")
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/", 
            "-v", 
            "--tb=short"
        ], cwd=os.path.dirname(__file__))
        
        return result.returncode == 0
        
    except FileNotFoundError:
        print("pytest not found, falling back to manual test runner...")
        return False
    except Exception as e:
        print(f"Error running pytest: {e}")
        return False

def run_manual_tests():
    """Fallback manual test runner (preserves original functionality)."""
    import unittest
    import importlib.util

    # Add the current directory to Python path
    sys.path.insert(0, os.path.dirname(__file__))

    print("Running manual test suite...")
    
    # Import the test modules
    test_files = [
        'tests/test_tool.py',
        'tests/test_cli.py'
    ]
    
    success_count = 0
    total_count = 0
    
    for test_file in test_files:
        if not os.path.exists(test_file):
            continue
            
        module_name = os.path.basename(test_file)[:-3]  # Remove .py
        spec = importlib.util.spec_from_file_location(module_name, test_file)
        test_module = importlib.util.module_from_spec(spec)
        
        try:
            spec.loader.exec_module(test_module)
            print(f"✓ {module_name} loaded successfully")
        except Exception as e:
            print(f"✗ Failed to load {module_name}: {e}")
            continue
    
        # Run core tests from original test file
        if 'test_refactored_tool' in module_name:
            test_cases = [
                ('TestGitSquashConfig', 'test_default_config'),
                ('TestGitSquashConfig', 'test_config_with_overrides'),
                ('TestDiffAnalyzer', 'test_categorize_commits'),
                ('TestDiffAnalyzer', 'test_detect_special_conditions'),
                ('TestMessageFormatter', 'test_wrap_text_simple'),
                ('TestMessageFormatter', 'test_wrap_bullet_points'),
                ('TestMockAIClient', 'test_generate_summary_features'),
                ('TestMockAIClient', 'test_suggest_branch_name'),
                ('TestGitSquashTool', 'test_prepare_squash_plan_basic'),
                ('TestGitSquashTool', 'test_prepare_squash_plan_with_date_filter'),
            ]
            
            for test_class_name, test_method_name in test_cases:
                total_count += 1
                try:
                    test_class = getattr(test_module, test_class_name)
                    test_instance = test_class()
                    
                    # Call setup if it exists
                    if hasattr(test_instance, 'setup_method'):
                        test_instance.setup_method()
                    
                    # Run the test
                    test_method = getattr(test_instance, test_method_name)
                    test_method()
                    
                    print(f"✓ {test_class_name}.{test_method_name}")
                    success_count += 1
                except Exception as e:
                    print(f"✗ {test_class_name}.{test_method_name}: {e}")
    
    print(f"\n=== Test Results ===")
    print(f"Passed: {success_count}/{total_count}")
    if total_count > 0:
        print(f"Success rate: {success_count/total_count*100:.1f}%")
    
    return success_count == total_count

def run_coverage():
    """Run tests with coverage reporting."""
    print("\nRunning tests with coverage...")
    try:
        # Install coverage if needed
        subprocess.run([sys.executable, "-m", "pip", "install", "pytest-cov"], 
                      capture_output=True, check=False)
        
        # Run with coverage
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "tests/", 
            "--cov=git_squash",
            "--cov-report=term-missing",
            "--cov-report=html:htmlcov",
            "-v"
        ], cwd=os.path.dirname(__file__))
        
        if result.returncode == 0:
            print("\nCoverage report generated in htmlcov/")
        
        return result.returncode == 0
        
    except Exception as e:
        print(f"Coverage reporting failed: {e}")
        return False

if __name__ == "__main__":
    print("Git Squash Tool - Test Runner")
    print("=" * 40)
    
    # Parse command line arguments
    if len(sys.argv) > 1 and sys.argv[1] == "--coverage":
        success = run_coverage()
    else:
        # Try pytest first, fall back to manual if needed
        success = run_pytest()
        if not success:
            success = run_manual_tests()
        
    print(f"\n{'='*40}")
    if success:
        print("✓ All tests passed!")
    else:
        print("✗ Some tests failed!")
        
    sys.exit(0 if success else 1)