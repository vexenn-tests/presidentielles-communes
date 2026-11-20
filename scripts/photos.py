"""
Télécharge un portrait de chaque candidat depuis Wikipédia (images Wikimedia Commons, licences libres)
dans assets/photos/, et écrit assets/photos/credits.json (auteur + licence de chaque image).

Usage (depuis la racine du projet) :  py scripts/photos.py   puis   py scripts/build.py
"""
import json, os, re, sys, time, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build import CANDIDATS, slug  # noqa: E402

ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "assets", "photos")
UA = {"User-Agent": "moteur-presidentielles/1.0 (script local)"}
API = "https://fr.wikipedia.org/w/api.php"


def get(url, tries=6):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code != 429 or i == tries - 1:
                raise
            wait = int(e.headers.get("Retry-After") or 0) or 5 * (i + 1)
            time.sleep(wait)


def strip_html(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()


def main():
    os.makedirs(OUT, exist_ok=True)
    cpath = os.path.join(OUT, "credits.json")
    credits = {}
    if os.path.exists(cpath):
        with open(cpath, encoding="utf-8") as f:
            credits = json.load(f)
    names = sorted({v[0] for v in CANDIDATS.values()})
    for name in names:
        if name in credits and os.path.exists(os.path.join(OUT, slug(name) + ".jpg")):
            continue
        q = urllib.parse.urlencode({"action": "query", "format": "json", "redirects": 1, "titles": name,
                                    "prop": "pageimages", "piprop": "thumbnail|name", "pithumbsize": 240})
        pages = json.loads(get(f"{API}?{q}"))["query"]["pages"]
        page = next(iter(pages.values()))
        thumb = page.get("thumbnail", {}).get("source")
        fname = page.get("pageimage")
        if not thumb:
            print("PAS DE PHOTO :", name)
            continue
        dest = os.path.join(OUT, slug(name) + ".jpg")
        with open(dest, "wb") as f:
            f.write(get(thumb))
        q = urllib.parse.urlencode({"action": "query", "format": "json", "titles": "File:" + fname,
                                    "prop": "imageinfo", "iiprop": "extmetadata|url"})
        info = next(iter(json.loads(get(f"https://commons.wikimedia.org/w/api.php?{q}"))["query"]["pages"].values()))
        meta = (info.get("imageinfo") or [{}])[0]
        em = meta.get("extmetadata", {})
        credits[name] = {"auteur": strip_html(em.get("Artist", {}).get("value")),
                         "licence": strip_html(em.get("LicenseShortName", {}).get("value")),
                         "source": meta.get("descriptionurl", "")}
        print("ok", name, "|", credits[name]["licence"])
        with open(cpath, "w", encoding="utf-8") as f:
            json.dump(credits, f, ensure_ascii=False, indent=1)
        time.sleep(1.5)


if __name__ == "__main__":
    main()
