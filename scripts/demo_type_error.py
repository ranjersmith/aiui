#!/usr/bin/env python3
"""
Demonstration of the TypeError that was fixed.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the module to test
import app

def demo_problem():
    print("Demonstrating the TypeError fix:")
    
    # This would cause TypeError in the old implementation:
    # 5 + "3" # Would cause: TypeError: unsupported operand type(s) for +: 'int' and 'str'
    
    # But our fixed implementation handles it properly:
    print("Testing safe_add_ints(5, '3'):")
    result = app.safe_add_ints(5, "3")
    print(f"Result: {result}")
    
    # This would also have caused a similar error:
    print("Testing safe_add_ints('5', '3'):")
    result = app.safe_add_ints("5", "3")
    print(f"Result: {result}")
    
    # This demonstrates error handling:
    print("Testing safe_add_ints('hello', 3):")
    result = app.safe_add_ints("hello", 3)
    print(f"Result (should be 0): {result}")
    
    print("All examples handled safely without TypeError!")

if __name__ == "__main__":
    demo_problem()