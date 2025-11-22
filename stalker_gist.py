# stalker_gist.py
import requests, re, os, time
from urllib.parse import urljoin, urlparse   # ← THIS LINE WAS MISSING
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from tqdm import tqdm
except:
    def tqdm(x, **kw): return x

GIST_TOKEN = os.getenv("GIST_TOKEN")
PORTAL     = os.getenv("PORTAL").rstrip("/") + "/"   # ensure trailing slash
MAC        = os.getenv("MAC")

if not all([GIST_TOKEN, PORTAL, MAC]):
    raise SystemExit("Missing one of: GIST_TOKEN, PORTAL, MAC secrets")

headers = {"User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)"}
s = requests.Session()
s.headers.update(headers)

def handshake():
    url = urljoin(PORTAL, "portal.php")
    s.cookies.clear()
    s.cookies.set("mac", MAC, domain=urlparse(PORTAL).hostname)
    s.cookies.set("stb_lang", "en")
    r = s.get(url, params={"type":"stb","action":"handshake","JsHttpRequest":"1-xml"})
    r.raise_for_status()
    return r.json()["js"]["token"]

def api_call(action, **params):
    params["JsHttpRequest"] = "1-xml"
    r = s.get(urljoin(PORTAL, "portal.php"), params=params, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    return r.json()["js"]

def clean_url(cmd):
    return re.sub(r'^(ffmpeg|ffplay|vlc)\s+', '', cmd.strip())

def create_gist(files_dict, description="Stalker M3U - Auto Updated"):
    url = "https://api.github.com/gists"
    payload = {
        "description": description,
        "public": True,
        "files": files_dict
    }
    r = requests.post(url, headers={"Authorization": f"token {GIST_TOKEN}"}, json=payload)
    r.raise_for_status()
    return r.json()["html_url"]

# === MAIN ===
token = handshake()
genres = api_call("itv", action="get_genres")

targets = ["AU | Sports", "Sports | Astro", "4K/UHD"]
selected_genres = []

for g in genres:
    title = g["title"]
    if any(t in title for t in targets) or any(x in title.lower() for x in ["4k", "uhd"]):
        selected_genres.append(g)

print(f"Found {len(selected_genres)} target groups:")
for g in selected_genres: print("  •", g["title"])

gist_files = {}
total_channels = 0

for genre in selected_genres:
    gid = genre["id"]
    gtitle = genre["title"]
    print(f"\nFetching {gtitle} (ID: {gid})...")

    channels = []
    page = 1
    while True:
        data = api_call("itv", action="get_ordered_list", genre=gid, p=page)
        batch = data.get("data", [])
        if not batch: break
        channels.extend(batch)
        page += 1
        time.sleep(0.1)

    print(f"  → {len(channels)} channels, generating fresh tokens...")
    m3u_lines = ["#EXTM3U"]

    def get_stream(cmd):
        url = api_call("itv", action="create_link", cmd=cmd, forced_storage="undefined")["cmd"]
        return clean_url(url)

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(get_stream, ch["cmd"]): ch for ch in channels}
        for future in tqdm(as_completed(futures), total=len(futures), desc=gtitle[:30]):
            ch
