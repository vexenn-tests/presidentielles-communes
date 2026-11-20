# Présidentielles par commune (2002 → 2022)

Ouvrir **`index.html`** dans un navigateur (double-clic, aucun serveur nécessaire).
Taper un nom de commune, un code postal ou un code INSEE : la page affiche, pour les
5 présidentielles (2002, 2007, 2012, 2017, 2022) et les deux tours, les scores de chaque
candidat dans la commune, la participation et l'écart avec le score national.

Toutes les données sont stockées localement : aucun appel à une API pendant l'utilisation.

## Contenu

| Chemin | Rôle |
|---|---|
| `index.html` | Le moteur de recherche |
| `data/index.js` | Liste des communes (noms, codes postaux, anciens noms) + candidats et résultats nationaux |
| `data/dep/*.js` | Résultats par commune, un fichier par département, chargé à la demande |
| `data/csv/presidentielle_<année>_tour<n>.csv` | Les mêmes résultats en tableau (une ligne par commune, voix et % par candidat) |
| `data/csv/synthese_en_tete_par_commune.csv` | Candidat arrivé en tête dans chaque commune à chaque scrutin |
| `data/raw/` | Fichiers sources bruts (~240 Mo), seulement utiles pour reconstruire les données |
| Google Sheet « Photos candidats – moteur présidentielles » | Lien photo de chaque candidat (colonne B), lu par la page à chaque ouverture. Ne pas renommer les candidats en colonne A. Sans lien : initiales. |
| `assets/photos/` | Anciennes photos Wikimedia, plus utilisées par la page (peut être supprimé) |
| `scripts/` | `telecharger.ps1` (re-télécharge les sources puis reconstruit), `build.py` (construction) |

Les CSV utilisent le séparateur `;` et l'encodage UTF-8 avec BOM : ils s'ouvrent directement dans Excel.

## Sources (data.gouv.fr)

- Données des élections agrégées — Ministère de l'Intérieur (résultats par bureau de vote)
- Base officielle des codes postaux — La Poste
- Code officiel géographique 2026 — Insee (communes, fusions de communes)

## Choix de traitement

- **Communes fusionnées** : les résultats sont rattachés au périmètre de la commune actuelle
  (ex. Annecy inclut Annecy-le-Vieux, Seynod… pour 2002–2012). On peut chercher par l'ancien nom.
- **Paris, Lyon, Marseille** : résultats à l'échelle de la ville ; les codes postaux d'arrondissement renvoient vers la ville.
- **Français de l'étranger** : présents à partir de 2012 (par circonscription consulaire).
- Pourcentages calculés sur les suffrages exprimés. Le « score national » est la somme de toutes
  les communes du fichier ; il peut différer de quelques dixièmes du résultat officiel (2002 et 2007 n'incluent pas les Français de l'étranger).

## Mettre à jour (ex. après la présidentielle 2027)

1. `powershell -File scripts\telecharger.ps1`
2. Si de nouveaux candidats apparaissent, ajouter leur nom et leur famille politique dans `CANDIDATS` (`scripts/build.py`)
   et l'année dans `ELECTIONS`, puis relancer `py scripts\build.py`. La page s'adapte toute seule au nombre de scrutins.
