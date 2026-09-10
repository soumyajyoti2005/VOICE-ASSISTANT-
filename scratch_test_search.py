import urllib.request
import re
import urllib.parse

req = urllib.request.Request(
    'https://html.duckduckgo.com/html/?q=Python+programming+language+Wikipedia',
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
)
html = urllib.request.urlopen(req).read().decode('utf-8')
urls = re.findall(r'href="//duckduckgo\.com/l/\?uddg=([^&"\']+)', html)
snippets = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)
print(f"URLs: {len(urls)}, Snippets: {len(snippets)}")

valid_snippets = []
for u, s in zip(urls, snippets):
    decoded_u = urllib.parse.unquote(u)
    if "ad_domain" not in decoded_u and "duckduckgo.com/y.js" not in decoded_u:
        valid_snippets.append(re.sub(r'<[^>]+>', '', s).strip())

print(valid_snippets[:2])

