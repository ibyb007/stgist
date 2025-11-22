# stalker_gist.py — FINAL VERSION (works on lol Nov 2025)
import requests, re, os, time
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from tqdm import tqdm
except:
    def tqdm(x, **kw): return x

GIST_TOKEN = os.getenv("GIST_TOKEN")
PORTAL     = os.getenv("PORTAL").rstrip("/") + "/"
MAC        = os.getenv("MAC")

if not all([GIST_TOKEN, PORTAL, MAC]):
    raise SystemExit("Missing secrets!")

# Try both common paths — ptv.lol uses the second one
BASE_PATHS = ["", "stalker_portal/"]
base_url = None

headers = {
    "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
    "X-User-Agent": "Model: MAG250; Link: WiFi",
    "Connection": "Keep-Alive"
}

s = requests.Session()
s.headers.update(headers)

def try_handshake(path):
    test_url = urljoin(PORTAL, path)
    url = urljoin(test_url, "portal.php")
    cookies = {"mac": MAC, "stb_lang": "en", "timezone": "Europe/London"}
    params = {"type": "stb", "action": "handshake", "JsHttpRequest": "1-xml"}
    r = s.get(url, params=params, cookies=cookies, timeout=20)
    if r.status_code == 200 and "js" in r.json():
        return test_url, r.json()["js"]["token"]
    return None, None

print("Finding correct portal path...")
token = None
for path in BASE_PATHS:
    print(f"  Trying {PORTAL}{path}portal.php ...")
    base_url, token = try_handshake(path)
    if token:
        print(f"  SUCCESS → using {path or '/'}portal.php")
        break

if not token:
    raise SystemExit("All paths failed — portal may be down or MAC blocked")

def api_call(action, **params):
    params["JsHttpRequest"] = "1-xml"
    r = s.get(urljoin(base_url, "portal.php"), params=params,
              headers={"Authorization": f"Bearer {token}"}, timeout=30)
    r.raise_for_status()
    return r.json()["js"]

def clean_url(cmd):
    return re.sub(r'^(ffmpeg|ffplay|vlc)\s+', '', cmd.strip(), flags=re.I)

# === REST OF THE SCRIPT (unchanged) ===
genres = api_call("itv", action="get_genres")
targets = ["AU | Sports", "Sports | Astro", "4K", "UHD"]
selected = [g for g in genres if any(t in g["title"] for t in targets) or "4k" in g["title"].lower() or "uhd" in g["title"].lower()]

print(f"Found {len(selected)} groups: {[g['title'] for g in selected]}")

gist_files = {}
total = 0

for genre in selected:
    gid, title = genre["id"], genre["title"]
    print(f"\n→ {title}")
    channels = []
    p = 1
    while True:
        data = api_call("itv", action="get_ordered_list", genre=gid, p=p)
        batch = data.get("data", [])
        if not batch: break
        channels.extend(batch)
        p += 1

    print(f"  {len(channels)} channels → generating tokens...")

    m3u = ["#EXTM3U"]
    def get_stream(cmd):
        return clean_url(api_call("itv", action="create_link", cmd=cmd, forced_storage="undefined")["cmd"])

    with ThreadPoolExecutor(max_workers=15) as ex:
        for ch, url in zip(channels, ex.map(get_stream, [ch["cmd"] for ch in channels])):
            m3u.append(f'#EXTINF:-1 tvg-name="{ch["name"]}" group-title="{title}",{ch["name"]}')
            m3u.append(url)

    safe = re.sub(r'[^\w\-]+', '_', title.strip())[:60] + ".m3u"
    gist_files[safe] = {"content": "\n".join(m3u)}
    total += len(channels)

# Private Gist
r = requests.post("https://api.github.com/gists",
                  headers={"Authorization": f"token {GIST_TOKEN}"},
                  json={"description": f"Stalker • {time.strftime('%Y-%m-%d %H:%M')} UTC", "public": False, "files": gist_files})
r.raise_for_status()
print(f"\nPRIVATE Gist ready → {r.json()['html_url']}")
