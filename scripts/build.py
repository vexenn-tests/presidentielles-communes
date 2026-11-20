"""
Construit les données locales du moteur à partir des fichiers bruts de data.gouv.fr.

Entrées (data/raw/, voir scripts/telecharger.ps1) :
  - general_results.parquet    : Données des élections agrégées (Ministère de l'Intérieur), résultats généraux
  - candidats_results.parquet  : idem, résultats par candidat
  - codes_postaux.csv          : Base officielle des codes postaux (La Poste)
  - v_commune_2026.csv         : COG Insee, communes au 01/01/2026
  - v_mvt_commune_2026.csv     : COG Insee, événements sur les communes (fusions...)
  - v_departement_2026.csv     : COG Insee, départements

Sorties :
  - data/index.js              : liste des communes + métadonnées des scrutins (chargé au démarrage)
  - data/dep/<dep>.js          : résultats par commune, un fichier par département (chargé à la demande)
  - data/csv/*.csv             : les mêmes données en tableaux (Excel, séparateur ;)

Usage (depuis la racine du projet) :  py scripts/build.py
"""
import csv, json, os, re, sys, unicodedata
from collections import defaultdict
import duckdb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data")

ELECTIONS = [f"{y}_pres_t{t}" for y in (2002, 2007, 2012, 2017, 2022) for t in (1, 2)]

# Couleurs par famille politique, prises dans la palette 20 Minutes (variables CSS de 20minutes.fr)
COL = {
    "xg": "#dc0e19",   # extrême gauche          -> secondary-red
    "g": "#ff3f3f",    # gauche radicale / PCF   -> secondary-scarlet
    "ps": "#ef2a82",   # socialiste / gauche     -> secondary-pink
    "eco": "#00b482",  # écologiste              -> theme-planet
    "c": "#fa9917",    # centre                  -> secondary-orange
    "d": "#4742ff",    # droite                  -> primary-ultramarine
    "sv": "#ae6ba2",   # souverainiste           -> secondary-purple
    "xd": "#253548",   # extrême droite          -> secondary-blue-grey
    "xd2": "#b49b56",  # extrême droite (2e)     -> theme-vie-pro
    "div": "#898a8c",  # divers                  -> greyscale-grey-300
}
CANDIDATS = {
    "CHIRAC": ("Jacques Chirac", "d"), "LE PEN|JEAN-MARIE": ("Jean-Marie Le Pen", "xd"),
    "LE PEN|MARINE": ("Marine Le Pen", "xd"), "JOSPIN": ("Lionel Jospin", "ps"),
    "BAYROU": ("François Bayrou", "c"), "LAGUILLER": ("Arlette Laguiller", "xg"),
    "CHEVENEMENT": ("Jean-Pierre Chevènement", "sv"), "MAMERE": ("Noël Mamère", "eco"),
    "BESANCENOT": ("Olivier Besancenot", "xg"), "SAINT-JOSSE": ("Jean Saint-Josse", "div"),
    "MADELIN": ("Alain Madelin", "d"), "HUE": ("Robert Hue", "g"),
    "MEGRET": ("Bruno Mégret", "xd2"), "TAUBIRA": ("Christiane Taubira", "ps"),
    "LEPAGE": ("Corinne Lepage", "eco"), "BOUTIN": ("Christine Boutin", "d"),
    "GLUCKSTEIN": ("Daniel Gluckstein", "xg"), "SARKOZY": ("Nicolas Sarkozy", "d"),
    "ROYAL": ("Ségolène Royal", "ps"), "DE VILLIERS": ("Philippe de Villiers", "sv"),
    "BUFFET": ("Marie-George Buffet", "g"), "VOYNET": ("Dominique Voynet", "eco"),
    "BOVE": ("José Bové", "eco"), "NIHOUS": ("Frédéric Nihous", "div"),
    "SCHIVARDI": ("Gérard Schivardi", "xg"), "HOLLANDE": ("François Hollande", "ps"),
    "MELENCHON": ("Jean-Luc Mélenchon", "g"), "JOLY": ("Eva Joly", "eco"),
    "DUPONT-AIGNAN": ("Nicolas Dupont-Aignan", "sv"), "POUTOU": ("Philippe Poutou", "xg"),
    "ARTHAUD": ("Nathalie Arthaud", "xg"), "CHEMINADE": ("Jacques Cheminade", "div"),
    "MACRON": ("Emmanuel Macron", "c"), "FILLON": ("François Fillon", "d"),
    "HAMON": ("Benoît Hamon", "ps"), "LASSALLE": ("Jean Lassalle", "div"),
    "ASSELINEAU": ("François Asselineau", "sv"), "ZEMMOUR": ("Éric Zemmour", "xd2"),
    "PECRESSE": ("Valérie Pécresse", "d"), "JADOT": ("Yannick Jadot", "eco"),
    "ROUSSEL": ("Fabien Roussel", "g"), "HIDALGO": ("Anne Hidalgo", "ps"),
}
DEP_EXTRA = {
    "975": "Saint-Pierre-et-Miquelon", "977": "Saint-Barthélemy", "978": "Saint-Martin",
    "986": "Wallis-et-Futuna", "987": "Polynésie française", "988": "Nouvelle-Calédonie",
    "ZZ": "Français établis hors de France",
}


def strip_accents(s):
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn")


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", strip_accents(s).lower()).strip("-")


def cand_info(nom, prenom):
    n = strip_accents(nom).upper().strip()
    p = strip_accents(prenom).upper().strip()
    if n == "LE PEN":
        key = f"LE PEN|{p}"
    else:
        key = n
    if key not in CANDIDATS:
        sys.exit(f"Candidat inconnu : {nom} {prenom}")
    disp, fam = CANDIDATS[key]
    return disp, COL[fam]


def dep_of(code):
    if code.startswith("ZZ"):
        return "ZZ"
    if code[:2] in ("97", "98"):
        return code[:3]
    return code[:2]


def read_csv(path, delim=","):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f, delimiter=delim))


def main():
    # ---------- COG : communes actuelles, rattachements et fusions ----------
    cog = read_csv(os.path.join(RAW, "v_commune_2026.csv"))
    current = {r["COM"]: r for r in cog if r["TYPECOM"] == "COM"}
    parent = {}
    sub_names = defaultdict(set)  # communes déléguées / associées (anciens noms)
    for r in cog:
        if r["TYPECOM"] in ("COMD", "COMA", "ARM") and r["COMPARENT"]:
            if r["COM"] not in current:
                parent[r["COM"]] = r["COMPARENT"]
            if r["TYPECOM"] != "ARM" and r["LIBELLE"] != current.get(r["COMPARENT"], {}).get("LIBELLE"):
                sub_names[r["COMPARENT"]].add(r["LIBELLE"])

    nxt = {}
    for r in sorted(read_csv(os.path.join(RAW, "v_mvt_commune_2026.csv")), key=lambda r: r["DATE_EFF"]):
        if (r["DATE_EFF"] >= "2002-01-01" and r["MOD"] in ("31", "32", "33", "34", "41", "50")
                and r["TYPECOM_AV"] == "COM" and r["TYPECOM_AP"] == "COM" and r["COM_AV"] != r["COM_AP"]):
            nxt[r["COM_AV"]] = r["COM_AP"]

    def resolve(code, depth=0):
        if code in current or depth > 20:
            return code if code in current else None
        if code in parent:
            return resolve(parent[code], depth + 1)
        if code in nxt:
            return resolve(nxt[code], depth + 1)
        return None

    deps = {r["DEP"]: r["LIBELLE"] for r in read_csv(os.path.join(RAW, "v_departement_2026.csv"))}
    deps.update(DEP_EXTRA)

    # ---------- Résultats ----------
    db = duckdb.connect()
    gpath = os.path.join(RAW, "general_results.parquet").replace("\\", "/")
    kpath = os.path.join(RAW, "candidats_results.parquet").replace("\\", "/")
    elist = ",".join(f"'{e}'" for e in ELECTIONS)

    gen = db.sql(f"""
        select id_election, code_commune, libelle_commune,
               sum(inscrits)::bigint, sum(votants)::bigint, sum(exprimes)::bigint
        from '{gpath}' where id_election in ({elist})
        group by all""").fetchall()
    cand = db.sql(f"""
        select id_election, code_commune, no_panneau, sum(voix)::bigint
        from '{kpath}' where id_election in ({elist})
        group by all""").fetchall()
    cands_meta = db.sql(f"""
        select id_election, no_panneau, any_value(nom), any_value(prenom), sum(voix)::bigint v
        from '{kpath}' where id_election in ({elist})
        group by all order by id_election, v desc""").fetchall()

    # Ordre des candidats par élection : score national décroissant
    order = defaultdict(list)
    meta = defaultdict(list)
    for e, pan, nom, prenom, v in cands_meta:
        order[e].append(pan)
        disp, color = cand_info(nom, prenom)
        m = {"n": disp, "c": color}
        photo = f"assets/photos/{slug(disp)}.jpg"
        if os.path.exists(os.path.join(ROOT, photo)):
            m["p"] = photo
        meta[e].append(m)
    pos = {e: {p: i for i, p in enumerate(order[e])} for e in ELECTIONS}

    # Nom et code "actuel" de chaque code présent dans les résultats
    names_by_code = defaultdict(dict)  # code -> {election: libelle}
    for e, code, lib, *_ in gen:
        names_by_code[code][e] = lib

    def best_name(code):
        ns = names_by_code[code]
        for e in reversed(ELECTIONS):
            if e in ns and ns[e] and "?" not in ns[e]:
                return ns[e]
        return next(iter(ns.values()))

    target = {}
    for code in names_by_code:
        if code.startswith("ZZ"):
            # Français de l'étranger : codes réattribués entre 2012 et 2017 -> clé par code + nom
            target[code] = None
            continue
        target[code] = resolve(code) or code

    def key_for(e, code):
        if code.startswith("ZZ"):
            nm = names_by_code[code].get(e, "")
            return code + ("" if e >= "2017" else "-2012")
        return target[code]

    # Agrégation au périmètre communal actuel
    NE = len(ELECTIONS)
    eidx = {e: i for i, e in enumerate(ELECTIONS)}
    data = {}   # key -> list[NE] of [ins, vot, exp, v...]
    info = {}   # key -> {"name", "dep", "aliases"}
    for e, code, lib, ins, vot, exp in gen:
        k = key_for(e, code)
        rec = data.setdefault(k, [None] * NE)
        i = eidx[e]
        if rec[i] is None:
            rec[i] = [0, 0, 0] + [0] * len(order[e])
        rec[i][0] += ins or 0
        rec[i][1] += vot or 0
        rec[i][2] += exp or 0
        if k not in info:
            info[k] = {"aliases": set(), "libs": {}}
        if k.split("-")[0] == code:
            info[k]["libs"][e] = lib
        if k != code and not code.startswith("ZZ"):
            info[k]["aliases"].add(best_name(code))
    for e, code, pan, v in cand:
        k = key_for(e, code)
        data[k][eidx[e]][3 + pos[e][pan]] += v or 0

    for k in data:
        if k in current:
            name = current[k]["LIBELLE"]
            dep = current[k]["DEP"]
        else:
            src = k.split("-")[0]
            libs = info[k]["libs"]
            good = [libs[e] for e in ELECTIONS if libs.get(e) and "?" not in libs[e]]
            name = good[-1] if good else next(iter(libs.values()))
            if "?" in name:
                name = name.replace("?", "é")
            dep = dep_of(src)
        info[k]["name"] = name
        info[k]["dep"] = dep
        seen = {strip_accents(name).lower()}
        aliases = []
        for a in sorted(sub_names.get(k, set())) + sorted(info[k]["aliases"]):
            na = strip_accents(a).lower()
            if na not in seen:
                seen.add(na)
                aliases.append(a)
        info[k]["aliases"] = aliases

    # ---------- Codes postaux ----------
    cps = defaultdict(set)
    with open(os.path.join(RAW, "codes_postaux.csv"), encoding="latin-1", newline="") as f:
        rd = csv.reader(f, delimiter=";")
        next(rd)
        for row in rd:
            insee, cp = row[0].strip(), row[2].strip()
            k = insee if insee in data else resolve(insee)
            if k and k in data:
                cps[k].add(cp)

    # ---------- National ----------
    nat = []
    for i, e in enumerate(ELECTIONS):
        tot = [0] * (3 + len(order[e]))
        for rec in data.values():
            if rec[i]:
                for j, x in enumerate(rec[i]):
                    tot[j] += x
        nat.append(tot)

    # ---------- Écriture ----------
    os.makedirs(os.path.join(OUT, "dep"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "csv"), exist_ok=True)

    def sort_key(k):
        return (info[k]["dep"], strip_accents(info[k]["name"]).lower())

    keys = sorted(data, key=sort_key)
    communes = [[k, info[k]["name"], info[k]["dep"], " ".join(sorted(cps.get(k, ()))),
                 "|".join(info[k]["aliases"])] for k in keys]
    elections_meta = [{"id": e, "annee": int(e[:4]), "tour": int(e[-1]), "cands": meta[e], "nat": nat[i]}
                      for i, e in enumerate(ELECTIONS)]
    credits = {}
    cpath = os.path.join(ROOT, "assets", "photos", "credits.json")
    if os.path.exists(cpath):
        with open(cpath, encoding="utf-8") as f:
            credits = json.load(f)
    index = {"elections": elections_meta, "deps": deps, "communes": communes, "credits": credits,
             "source": "data.gouv.fr — Données des élections agrégées (Ministère de l'Intérieur), "
                       "Base officielle des codes postaux (La Poste), Code officiel géographique 2026 (Insee)"}
    with open(os.path.join(OUT, "index.js"), "w", encoding="utf-8") as f:
        f.write("window.PRESID=" + json.dumps(index, ensure_ascii=False, separators=(",", ":")) + ";\n")

    by_dep = defaultdict(dict)
    for k in keys:
        by_dep[info[k]["dep"]][k] = data[k]
    for d, rows in by_dep.items():
        with open(os.path.join(OUT, "dep", f"{d}.js"), "w", encoding="utf-8") as f:
            f.write(f"window.PRESID_DEP({json.dumps(d)},"
                    + json.dumps(rows, separators=(",", ":")) + ");\n")

    # CSV : un tableau par scrutin + une synthèse
    for i, e in enumerate(ELECTIONS):
        names = [c["n"] for c in meta[e]]
        with open(os.path.join(OUT, "csv", f"presidentielle_{e[:4]}_tour{e[-1]}.csv"), "w",
                  encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["code_insee", "commune", "departement", "codes_postaux", "inscrits", "votants",
                        "exprimes", "participation_pct", "en_tete", "en_tete_pct"]
                       + [f"{n} (voix)" for n in names] + [f"{n} (%)" for n in names])
            for k in keys:
                r = data[k][i]
                if not r:
                    continue
                ins, vot, exp, votes = r[0], r[1], r[2], r[3:]
                top = max(range(len(votes)), key=lambda j: votes[j])
                pct = [round(100 * v / exp, 2) if exp else "" for v in votes]
                w.writerow([k, info[k]["name"], info[k]["dep"], " ".join(sorted(cps.get(k, ()))), ins, vot, exp,
                            round(100 * vot / ins, 2) if ins else "", names[top], pct[top]]
                           + votes + pct)
    with open(os.path.join(OUT, "csv", "synthese_en_tete_par_commune.csv"), "w",
              encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["code_insee", "commune", "departement", "codes_postaux"]
                   + [f"{e[:4]} T{e[-1]}" for e in ELECTIONS])
        for k in keys:
            row = [k, info[k]["name"], info[k]["dep"], " ".join(sorted(cps.get(k, ())))]
            for i, e in enumerate(ELECTIONS):
                r = data[k][i]
                if not r or not r[2]:
                    row.append("")
                    continue
                votes = r[3:]
                top = max(range(len(votes)), key=lambda j: votes[j])
                row.append(f"{meta[e][top]['n']} ({100 * votes[top] / r[2]:.1f}%)")
            w.writerow(row)

    print(f"{len(keys)} communes, {len(by_dep)} départements, "
          f"{sum(1 for k in keys if cps.get(k))} avec code postal, "
          f"{sum(1 for k in keys if all(data[k][i] for i in range(NE)))} avec les 10 scrutins")
    for i, e in enumerate(ELECTIONS):
        t = nat[i]
        print(e, "inscrits", t[0], "exprimés", t[2], "|",
              ", ".join(f"{meta[e][j]['n']} {100 * t[3 + j] / t[2]:.2f}%" for j in range(min(3, len(meta[e])))))


if __name__ == "__main__":
    main()
