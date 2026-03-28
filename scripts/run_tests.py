#!/usr/bin/env python3
"""
Script to run tests for the aiui project.
"""
import subprocess
import sys

def run_tests():
    print("Setting up test environment...")
    
    # Install dependencies
    print("Installing dependencies...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "-r", "requirements-dev.txt"], check=True)
        print("Dependencies installed successfully")
    except subprocess.CalledProcessError as e:
        print(f"Error installing dependencies: {e}")
        return False
    
    # Run pytest
    print("Running pytest...")
    try:
        result = subprocess.run([
            sys.executable, "-m", "pytest", 
            "-v", 
            "--tb=short",
            "tests/"
        ], check=True, capture_output=True, text=True)
        
        print("Test output:")
        print(result.stdout)
        if result.stderr:
            print("Test errors:")
            print(result.stderr)
            
        print("Tests completed successfully!")
        return True
        
    except subprocess.CalledProcessError as e:
        print("Tests failed with exit code:", e.returncode)
        print("STDOUT:", e.stdout)
        print("STDERR:", e.stderr)
        return False
    except FileNotFoundError:
        print("pytest not found. Please ensure it's installed.")
        return False

if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
