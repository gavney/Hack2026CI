import re

with open('frontend/index.html', 'r', encoding='utf-8') as f:
    html = f.read()

with open('frontend/js/app.js', 'r', encoding='utf-8') as f:
    js = f.read()

handlers = set(re.findall(r'on[a-z]+="([a-zA-Z0-9_]+)\(', html))

print(f"Total event handlers found across all on* attributes: {len(handlers)}")
missing = []
for fn in sorted(handlers):
    if fn in js:
        print(f"  [OK] {fn}")
    else:
        print(f"  [MISSING!] {fn}")
        missing.append(fn)

if missing:
    print(f"\nMISSING HANDLERS: {missing}")
else:
    print("\nALL HANDLERS ARE PRESENT AND ACCOUNTED FOR!")
