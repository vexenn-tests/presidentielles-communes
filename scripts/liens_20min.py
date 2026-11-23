"""Associe chaque commune du moteur à sa page résultats sur 20minutes.fr.

Source : le plan de site élections de 20 Minutes (sitemap-elections.xml), téléchargé
dans un fichier texte (une URL par ligne). Usage :
    py -P scripts/liens_20min.py <urls.txt>
Écrit data/liens20min.js : window.LIENS20 = {"<code INSEE>": "<departement>/<commune-cp>", ...}
"""
import json, os, re, sys, unicodedata
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREFIX = "https://www.20minutes.fr/elections/resultats/"


def slug(s):
    s = unicodedata.normalize("NFKD", s.replace("œ", "oe").replace("Œ", "oe").replace("æ", "ae"))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


urls = [u.strip().lstrip("﻿") for u in open(sys.argv[1], encoding="utf-8-sig") if u.strip()]
# pages commune : <dep>/<slug>-<cp 5 chiffres>
pages = {}            # suffixe -> (dep_slug, nom_slug, cp)
by_cp = defaultdict(list)
for u in urls:
    m = re.fullmatch(re.escape(PREFIX) + r"([a-z0-9-]+)/([a-z0-9-]+)-(\d{5}|2[ab]\d{3})", u)
    if m:
        pages[m.group(1) + "/" + m.group(2) + "-" + m.group(3)] = m.groups()
        by_cp[m.group(3)].append(m.groups())

txt = open(os.path.join(ROOT, "data", "index.js"), encoding="utf-8").read()
P = json.loads(txt[txt.index("{"):txt.rindex("}") + 1])
communes = P["communes"]

# Villes à arrondissements : la page "ville entière" est en 75000 / 69000 / 13000
SPECIAL = {"75056": "paris/paris-75000", "69123": "rhone/lyon-69000", "13055": "bouches-du-rhone/marseille-13000"}

liens, manquants = {}, []
for code, name, dep, cps, aliases in communes:
    if code in SPECIAL and SPECIAL[code] in pages:
        liens[code] = SPECIAL[code]; continue
    s = slug(name)
    cands = [c for c in re.split(r"[ ,;|]+", cps) if c]
    hit = None
    for cp in cands:
        for d, n, c in by_cp.get(cp, []):
            if n == s:
                hit = f"{d}/{n}-{c}"; break
        if hit: break
    if hit: liens[code] = hit
    else: manquants.append((code, name, dep, cps))

# 2e passe : 20 Minutes utilise parfois un autre code postal que La Poste.
# On cherche alors le même nom dans le même département, s'il y est unique.
dep_votes = defaultdict(lambda: defaultdict(int))
for code, name, dep, *_ in communes:
    if code in liens: dep_votes[dep][liens[code].split("/")[0]] += 1
dep_slug = {d: max(v, key=v.get) for d, v in dep_votes.items()}
by_dep_name = defaultdict(list)
for d, n, c in pages.values():
    by_dep_name[(d, n)].append(f"{d}/{n}-{c}")
used = set(liens.values())
reste = []
for code, name, dep, cps in manquants:
    hits = [h for h in by_dep_name.get((dep_slug.get(dep), slug(name)), []) if h not in used]
    if len(hits) == 1: liens[code] = hits[0]; used.add(hits[0])
    else: reste.append((code, name, dep, cps))
print(f"2e passe (même nom, même département) : {len(manquants) - len(reste)} communes en plus")
manquants = reste

# 3e passe : commune renommée récemment (ex. Cransac -> Cransac-les-Thermes) :
# même code postal, un nom est le début de l'autre, une seule page candidate.
reste = []
for code, name, dep, cps in manquants:
    s = slug(name)
    hits = {f"{d}/{n}-{c}" for cp in re.split(r"[ ,;|]+", cps) if cp for d, n, c in by_cp.get(cp, [])
            if (n.startswith(s + "-") or s.startswith(n + "-")) and f"{d}/{n}-{c}" not in used}
    if len(hits) == 1: h = hits.pop(); liens[code] = h; used.add(h)
    else: reste.append((code, name, dep, cps))
print(f"3e passe (commune renommée) : {len(manquants) - len(reste)} communes en plus")
manquants = reste

out = os.path.join(ROOT, "data", "liens20min.js")
with open(out, "w", encoding="utf-8") as f:
    f.write("window.LIENS20=" + json.dumps(liens, ensure_ascii=False, separators=(",", ":")) + ";\n")
print(f"{len(pages)} pages commune dans le plan de site")
print(f"{len(liens)}/{len(communes)} communes reliées, {len(manquants)} sans page")
with open(os.path.join(ROOT, "data", "liens20min_manquants.csv"), "w", encoding="utf-8-sig") as f:
    f.write("code_insee;commune;dep;codes_postaux\n")
    for r in manquants: f.write(";".join(r) + "\n")
for r in manquants[:25]: print("  ", r)
