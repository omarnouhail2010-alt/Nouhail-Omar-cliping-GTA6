"""Titres, descriptions, hashtags, accroches et planning de publication."""
import csv
import random
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

from . import config as C

HOOKS = {
    "crash": ["Personne n'a vu ça dans GTA 6", "La physique de GTA 6 est irréelle",
              "Ce crash dans GTA 6…"],
    "poursuite": ["La police de GTA 6 ne lâche rien", "Cette poursuite dans GTA 6",
                  "GTA 6 : impossible de s'échapper ?"],
    "reaction": ["GTA 6 m'a fait ça…", "J'ai pas compris ce qui s'est passé",
                 "Personne n'a vu ça dans GTA 6"],
    "physique": ["Le réalisme de GTA 6 est abusé", "Rockstar a pensé à tout dans GTA 6",
                 "Regarde bien ce détail dans GTA 6"],
    "moment": ["Personne n'a vu ça dans GTA 6", "GTA 6 a vraiment fait ça ?",
               "Ce moment dans GTA 6"],
}

TITLES = {
    "crash": ["GTA 6 : ce crash est complètement fou 💥", "La physique de GTA 6 est irréelle 😳",
              "GTA 6 vs réalité : ce crash 🤯"],
    "poursuite": ["GTA 6 : la police la plus intense de la série 🚨", "Poursuite folle dans GTA 6 😱",
                  "GTA 6 : 5 étoiles, impossible de fuir ? 🚔"],
    "reaction": ["GTA 6 m'a fait ça… 💀", "Je ne m'attendais pas à ça dans GTA 6 😭",
                 "GTA 6 : personne n'a vu ça venir 😳"],
    "physique": ["GTA 6 : Rockstar a pensé à TOUT 🤯", "Ce détail de GTA 6 est abusé 😳",
                 "Le réalisme de GTA 6 est irréel 🔥"],
    "moment": ["Personne n'a vu ça dans GTA 6 😳", "GTA 6 a vraiment fait ça ?! 🤯",
               "Ce moment GTA 6 est incroyable 🔥"],
}

EN_LINE = {
    "crash": "GTA 6 physics are insane 💥", "poursuite": "GTA 6 police chase is crazy 🚨",
    "reaction": "GTA 6 did this to me 💀", "physique": "Rockstar thought of everything 🤯",
    "moment": "Nobody saw this in GTA 6 😳",
}


def hook_for(kind: str, i: int) -> str:
    opts = HOOKS.get(kind, HOOKS["moment"])
    return opts[i % len(opts)]


def build_meta(kind: str, quote: str = "") -> dict:
    titles = list(TITLES.get(kind, TITLES["moment"]))
    tags_type = C.HASHTAGS_BY_TYPE.get(kind, C.HASHTAGS_BY_TYPE["moment"])
    yt_tags = ["#gta6", "#shorts", tags_type[0], "#gtavi", "#gaming"]
    ig_tags = C.HASHTAGS_CORE[:4] + tags_type + random.sample(C.HASHTAGS_GAMING, 3) + ["#reels", "#viral"]
    desc = (f"{titles[0]}\n"
            f"{('« ' + quote + ' »' + chr(10)) if quote else ''}"
            "👉 Abonne-toi pour un clip GTA 6 chaque jour !\n"
            "💬 Dis-moi en commentaire si tu l'avais remarqué.\n\n"
            f"{EN_LINE.get(kind, EN_LINE['moment'])} – follow for daily GTA 6 clips.\n\n"
            "Gameplay capturé par moi-même. GTA VI © Rockstar Games.\n")
    return {
        "titles": titles,
        "description": desc,
        "hashtags_youtube": yt_tags,
        "hashtags_instagram": list(dict.fromkeys(ig_tags)),
    }


# ---------------------------------------------------------------- planning

FIELDS = ["clip", "plateforme", "date", "heure", "datetime_iso", "titre", "titre_option_2",
          "titre_option_3", "description", "hashtags", "score", "type", "statut", "post_id"]


def load_planning():
    if not C.PLANNING_CSV.exists():
        return []
    with open(C.PLANNING_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def save_planning(rows):
    rows.sort(key=lambda r: (r["datetime_iso"], r["plateforme"]))
    with open(C.PLANNING_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def next_slots(rows, platform: str, count: int, start: datetime | None = None):
    """Prochains créneaux libres pour une plateforme (heure de Casablanca)."""
    tz = ZoneInfo(C.TIMEZONE)
    now = start or datetime.now(tz) + timedelta(minutes=30)
    taken = {r["datetime_iso"] for r in rows if r["plateforme"] == platform}
    out, day = [], now.date()
    while len(out) < count:
        for hhmm in C.SLOTS:
            hh, mm = map(int, hhmm.split(":"))
            d = day + timedelta(days=1) if hh < 6 else day  # 00:30 = nuit suivante
            dt = datetime.combine(d, time(hh, mm), tz)
            if dt > now and dt.isoformat() not in taken:
                out.append(dt)
                taken.add(dt.isoformat())
                if len(out) == count:
                    break
        day += timedelta(days=1)
    return out


def schedule(clips: list[dict]):
    """clips : [{'clip': nom, 'meta': {...}, 'score': int, 'kind': str}] triés par score.
    Les meilleurs clips vont sur le créneau de 19:30."""
    rows = load_planning()
    for platform in C.PLATFORMS:
        slots = next_slots(rows, platform, len(clips))
        # le meilleur clip disponible pour chaque créneau du soir
        prime = [s for s in slots if s.strftime("%H:%M") == "19:30"]
        other = [s for s in slots if s not in prime]
        ordered_slots = prime + other
        for c, dt in zip(clips, ordered_slots):
            m = c["meta"]
            tags = m["hashtags_youtube"] if platform == "youtube" else m["hashtags_instagram"]
            rows.append({
                "clip": c["clip"], "plateforme": platform,
                "date": dt.strftime("%Y-%m-%d"), "heure": dt.strftime("%H:%M"),
                "datetime_iso": dt.isoformat(), "titre": m["titles"][0],
                "titre_option_2": m["titles"][1], "titre_option_3": m["titles"][2],
                "description": m["description"], "hashtags": " ".join(tags),
                "score": c["score"], "type": c["kind"], "statut": "prêt", "post_id": "",
            })
    save_planning(rows)
    return rows
