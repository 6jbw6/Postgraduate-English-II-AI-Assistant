import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
from main import app

print("Registered Routes:")
for route in app.routes:
    if hasattr(route, 'methods'):
        print(f"{route.path} - {route.methods}")
    else:
        print(f"{route.path} - No methods")
