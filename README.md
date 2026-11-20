# Clips GTA 6 – pipeline automatique (YouTube Shorts + Instagram Reels)

Une commande :

```bash
python gta6clip.py "<lien Drive | fichier | dossier | URL Creative Commons>" --channel "@MaChaine"
```

Étapes : récupération (contrôle des droits) → détection des moments (volume, mouvement,
PySceneDetect, faster-whisper) → score viral 0–100 + explication → montage 9:16 1080×1920
(accroche à t=0, zooms, coupes des temps morts, sous-titres mot par mot, boucle, watermark)
→ miniature + titres/description/hashtags → `planning.csv`.

Sorties : `clips/*.mp4|.jpg|.json`, `reports/<source>.md`, `planning.csv`.
Musique : dépose des sons libres (YouTube Audio Library) dans `music/` ; `--music none` pour désactiver.
Recherche phase 1 : `docs/phase1_recherche.md`.
