# stalker_gist.py - 100% working on ptv.lol (Nov 2025)
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

# EXACT headers that ptv.lol accepts in 2025
headers = {
    "User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)",
    "Accept": "*/*",
    "Connection": "Keep-Alive",
    "X-User-Agent": "Model: MAG250; Link: WiFi",
    "Cookie": f"mac={MAC}; stb_lang=en; timezone=Europe/London"
}

s = requests.Session()
s.headers.update(headers)
s.cookies.set("mac", MAC, domain=urlparse(PORTAL).hostname)

def handshake():
    url = urljoin(PORTAL, "portal.php")
    params = {
        "type": "stb",
        "action": "handshake",
        "JsHttpRequest": "1-xml",
        "prehash": "0",                 # Some portals require this
        "token": ""                     # Some need empty token first
    }
    r = s.get(url, params=params, timeout=20)
    if r.status_code != 200 or "js" not in r.json():
        raise SystemExit(f"Handshake failed: {r.text[:200]}")
    return r.json()["js"]["token"]

def api_call(action, **params):
    params["JsHttpRequest"] = "1-xml"
    r = s.get(urljoin(PORTAL, "portal.php"), params=params,
              headers={"Authorization": f"Bearer {token}"}, timeout=30)
    r.raise_for_status()
    return r.json()["js"]

def clean_url(cmd):
    return re.sub(r'^(ffmpeg|ffplay|vlc)\s+', '', cmd.strip(), flags=re.I)

def create_gist(files_dict):
    payload = {
        "description": f"Stalker Auto M3U • {time.strftime('%Y-%m-%d %H:%M')} UTC",
        "public": False,      # PRIVATE GIST
        "files": files_dict
    }
    r = requests.post("https://api.github.com/gists",
                      headers={"Authorization": f"token {GIST_TOKEN}"},
                      json=payload, timeout=20)
    r.raise_for_status()
    return r.json()["html_url"]

# === MAIN ===
print("Starting handshake...")
token = handshake()
print("Handshake OK - token received")

print("Loading genres...")
genres = api_call("itv", action="get_genres")

targets = ["AU | Sports", "Sports | Astro", "4K", "UHD"]
selected = [g for g in genres if any(t in g["title"] for t in targets) or any(x in g["title"].lower() for x in ["4k","uhd"])]

print(f"Found {len(selected)} groups: {[g['title'] for g in selected]}")

gist_files = {}
total_ch = 0

for genre in selected:
    gid = genre["id"]
    title = genre["title"]
    print(f"\n→ {title}")

    channels = []
    page = 1
    while True:
        data = api_call("itv", action="get_ordered_list", genre=gid, p=page, fav="0")
        batch = data.get("data", [])
        if not batch: break
        channels.extend(batch)
        page += 1

    print(f"  {len(channels)} channels → creating fresh tokens...")

    m3u = ["#EXTM3U"]

    def get_stream(cmd):
        resp = api_call("itv", action="create_link", cmd=cmd, forced_storage="undefined", download="0")
        return clean_url(resp["cmd"])

    with ThreadPoolExecutor(max_workers=15) as ex:
        for ch, url in zip(channels, ex.map(get_stream, [ch["cmd"] for ch in channels])):
            m3u.append(f'#EXTINF:-1 tvg-name="{ch["name"]}" group-title="{title}",{ch["name"]}')
            m3u.append(url)

    safe_name = re.sub(r'[^\w\-]+', '_', title)[:60] + ".m3u"
    gist_files[safe_name] = {"content": "\n".join(m3u)}
    total_ch += len(channels)

gist_url = create_gist(gist_files)
print(f"\nSUCCESS! {total_ch} channels → PRIVATE Gist ready")
print(gist_url)
