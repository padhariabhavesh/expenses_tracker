import os
import site

paths = site.getsitepackages()
print(f"Searching in: {paths}")

for p in paths:
    if os.path.exists(p):
        print(f"Listing {p}:")
        try:
            items = os.listdir(p)
            for i in items:
                if 'PyQt5' in i or 'Qt' in i:
                    print(f"  {i}")
                    # Explore inside
                    sub = os.path.join(p, i)
                    if os.path.isdir(sub):
                        for r, d, f in os.walk(sub):
                            for file in f:
                                if file.endswith('.dll'):
                                    print(f"    DLL: {os.path.join(r, file)}")
        except Exception as e:
            print(f"Error accessing {p}: {e}")
