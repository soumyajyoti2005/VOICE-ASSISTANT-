import re

with open('frontend/src/App.jsx', 'r', encoding='utf-8') as f:
    c = f.read()

c = c.replace("'Listening.'", "'Listening…'")
c = c.replace("'Speaking.'", "'Speaking…'")
c = c.replace("'Thinking.'", "'Thinking…'")
c = c.replace("'Searching.'", "'Searching…'")

with open('frontend/src/App.jsx', 'w', encoding='utf-8') as f:
    f.write(c)

