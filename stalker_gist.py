# stalker_gist.py
import requests, re, os, json, time
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from tqdm import tqdm
    tqdm = tqdm
except:
    tqdm = lambda x, **kw: x

GIST_TOKEN = os.getenv("GIST_TOKEN")
PORTAL = os.getenv("PORTAL")
MAC = os.getenv("MAC")

headers = {"User-Agent": "Mozilla/5.0 (QtEmbedded; U; Linux; C)"}
s = requests.Session()
s.headers.update(headers)

def handshake():
    url = urljoin(PORTAL, "portal.php")
    s.cookies.clear()
    s.cookies.set("mac", MAC, domain=urlparse(PORTAL).hostname)
    r = s.get(url, params={"type":"stb","action":"handshake","JsHttpRequest":"1-xml"})
    return r.json()["js"]["token"]

def api_call(action, **params):
    params["JsHttpRequest"] = "1-xml"
    r = s.get(urljoin(PORTAL, "portal.php"), params=params, headers={"Authorization": f"Bearer {token}"})
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

# Target groups (exact or partial match)
targets = [
    "AU | Sports",
    "Sports | Astro",
    "4K/UHD"          # will also catch "UK | 4K/UHD", "Sports 4K", etc.
]

selected_genres = []
for g in genres:
    title = g["title"]
    if any(t in title for t in targets) or any(x in title.lower() for x in ["4k", "uhd"]):
        selected_genres.append(g)

print(f"Found {len(selected_genres)} target groups: {[g['title'] for g in selected_genres]}")

gist_files = {}
all_channels = 0

for genre in selected_genres:
    gid = genre["id"]
    gtitle = genre["title"]
    print(f"Fetching {gtitle}...")
    channels = []
    page = 1
    while True:
        data = api_call("itv", action="get_ordered_list", genre=gid, p=page)
        chans = data.get("data", [])
        if not chans: break
        channels.extend(chans)
        page += 1

    print(f"  → {len(channels)} channels, generating fresh tokens...")
    m3u_lines = ["#EXTM3U"]

    def get_stream(cmd):
        url = api_call("itv", action="create_link", cmd=cmd, forced_storage="undefined")["cmd"]
        return clean_url(url)

    with ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(get_stream, ch["cmd"]): ch for ch in channels}
        for future in tqdm(as_completed(futures), total=len(futures)):
            ch = futures[future]
            url = future.result()
            m3u_lines.append(f'#EXTINF:-1 tvg-name="{ch["name"]}" group-title="{gtitle}",{ch["name"]}')
            m3u_lines.append(url)

    filename = re.sub(r'[^\w\- ]', '', gtitle.strip())[:50] + ".m3u"
    gist_files[filename] = {"content": "\n".join(m3u_lines)}
    all_channels += len(channels) // 2

gist_url = create_gist(gist_files, f"Stalker Groups - {time.strftime('%Y-%m-%d %H:%M')} UTC")
print(f"\nAll done! {all_channels} channels uploaded")
print(f"Gist URL → {gist_url}")
