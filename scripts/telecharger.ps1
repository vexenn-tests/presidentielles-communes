# Télécharge les fichiers sources (data.gouv.fr / La Poste / Insee) dans data\raw
# puis reconstruit les données locales du moteur.
# Usage, depuis la racine du projet :  powershell -File scripts\telecharger.ps1
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$raw = Join-Path $PSScriptRoot '..\data\raw'
New-Item -ItemType Directory -Force $raw | Out-Null

$files = @{
  'general_results.parquet'   = 'https://data-pipeline-open.s3.sbg.io.cloud.ovh.net/elections/general_results.parquet'
  'candidats_results.parquet' = 'https://data-pipeline-open.s3.sbg.io.cloud.ovh.net/elections/candidats_results.parquet'
  'codes_postaux.csv'         = 'https://data.laposte.fr/data-fair/api/v1/datasets/laposte-hexasmal/raw'
  'v_commune_2026.csv'        = 'https://www.insee.fr/fr/statistiques/fichier/8740222/v_commune_2026.csv'
  'v_mvt_commune_2026.csv'    = 'https://www.insee.fr/fr/statistiques/fichier/8740222/v_mvt_commune_2026.csv'
  'v_departement_2026.csv'    = 'https://www.insee.fr/fr/statistiques/fichier/8740222/v_departement_2026.csv'
}
foreach ($name in $files.Keys) {
  Write-Host "Téléchargement $name..."
  Invoke-WebRequest $files[$name] -OutFile (Join-Path $raw $name)
}

$env:PYTHONIOENCODING = 'utf-8'
py -m pip install --user -q duckdb
py -P (Join-Path $PSScriptRoot 'build.py')
