# stalker_gist.py
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
    raise SystemExit("Missing secrets: GIST_TOKEN, PORTAL or MAC")

# THIS IS THE KEY FIX — real MAG box headers (ptv.lol allows only these)
headers = {
    "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
    "Accept": "*/*",
    "Connection": "Keep-Alive",
    "X-User-Agent": "Model: MAG254; Link: Ethernet",
    "Cookie": f"mac={MAC}; stb_lang=en; timezone=Europe/London"
}

s = requests.Session()
s.headers.update(headers)

def handshake():
    url = urljoin(PORTAL, "portal.php")
    params = {"type": "stb", "action": "handshake", "JsHttpRequest": "1-xml"}
    r = s.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()["js"]["token"]

def api_call(action, **params):
    params["JsHttpRequest"] = "1-xml"
    r = s.get(urljoin(PORTAL, "portal.php"), params=params,
              headers={"Authorization": f"Bearer {token}"}, timeout=30)
    r.raise_for_status()
    return r.json()["js"]

def clean_url(cmd):
    return re.sub(r'^(ffmpeg|ffplay|vlc)\s+', '', cmd.strip(), flags=re.I)

def create_gist(files_dict, description="Stalker M3U - Auto Updated"):
    url = "https://api.github.com/gists"
    payload = {
        "description": description,
        "public": False,           # ← PRIVATE GIST
        "files": files_dict
    }
    r = requests.post(url, headers={"Authorization": f"token {GIST_TOKEN}"}, json=payload)
    r.raise_for_status()
    return r.json()["html_url"]

# === MAIN ===
print("Handshake...")
token = handshake()
print("Token received")

print("Fetching genres...")
genres = api_call("itv", action="get_genres")

targets = ["AU | Sports", "Sports | Astro", "4K/UHD"]
selected_genres = []

for g in genres:
    t = g["title"]
    if any(x in t for x in targets) or any(x in t.lower() for x in ["4k", "uhd"]):
        selected_genres.append(g)

print(f"Found {len(selected_genres)} groups: {[g['title'] for g in selected_genres]}")

gist_files = {}
total = 0

for genre in selected_genres:
    gid = genre["id"]
    gtitle = genre["title"]
    print(f"\n→ {gtitle}")

    channels = []
    p = 1
    while True:
        data = api_call("itv", action="get_ordered_list", genre=gid, p=p)
        batch = data.get("data", [])
        if not batch: break
        channels.extend(batch)
        p += 1
        time.sleep(0.1)

    print(f"  {len(channels)} channels → generating tokens...")

    m3u = ["#EXTM3U"]

    def get_stream(cmd):
        url = api_call("itv", action="create_link", cmd=cmd, forced_storage="undefined")["cmd"]
        return clean_url(url)

    with ThreadPoolExecutor(max_workers=12) as ex:
        futures = {ex.submit(get_stream, ch["cmd"]): ch for ch in channels}
        for f in tqdm(as_completed(futures), total=len(futures)):
            ch = futures[f]
            url = f.result()
            m3u.append(f'#EXTINF:-1 tvg-name="{ch["name"]}" group-title="{gtitle}",{ch["name"]}')
            m3u.append(url)

    safe_name = re.sub(r'[^\w\-]+', '_', gtitle.strip())[:60] + ".m3u"
    gist_files[safe_name] = {"content": "\n".join(m3u)}
    total += len(channels)

gist_url = create_gist(gist_files, f"Stalker • {time.strftime('%Y-%m-%d %H:%M')} UTC")
print(f"\nSUCCESS! {total} channels → PRIVATE Gist created")
print(gist_url)
