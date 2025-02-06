import sys

def print_method_name():
    current_frame = sys._getframe(1)  # Get the caller's frame
    method_name = current_frame.f_code.co_name
    print(f"Hello from {method_name}")

def example_function():
    print_method_name()

def another_function():
    print_method_name()

example_function()
another_function()

