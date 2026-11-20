"""Réglages globaux de la chaîne. Modifie ici plutôt que dans le code."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLIPS_DIR = ROOT / "clips"
WORK_DIR = ROOT / "work"
SOURCES_DIR = WORK_DIR / "sources"
REPORTS_DIR = ROOT / "reports"
MUSIC_DIR = ROOT / "music"  # mets ici des sons libres (YouTube Audio Library)
FONTS_DIR = ROOT / "assets" / "fonts"
PLANNING_CSV = ROOT / "planning.csv"

CHANNEL_NAME = "@MaChaineGTA6"  # remplacé par --channel ou par la variable GTA6_CHANNEL
TIMEZONE = "Africa/Casablanca"

# Créneaux (heure de Casablanca) : 13:00 Europe/Maghreb, 19:30 pic du soir, 00:30 pic US
SLOTS = ["13:00", "19:30", "00:30"]
CLIPS_PER_DAY = 3
PLATFORMS = ["youtube", "instagram"]

# Format
W, H = 1080, 1920
FPS = 30
FG_W, FG_H, FG_Y = 1080, 1200, 360  # zone vidéo principale (le reste = fond flouté)
MIN_LEN, MAX_LEN, TARGET_LEN = 15.0, 45.0, 26.0
MAX_CLIPS_PER_SOURCE = 10
MIN_CLIPS_PER_SOURCE = 5
WHISPER_MODEL = "small"

HASHTAGS_CORE = ["#gta6", "#gtavi", "#grandtheftauto", "#grandtheftauto6", "#gta", "#rockstargames"]
HASHTAGS_GAMING = ["#gaming", "#gamer", "#gameplay", "#gamingclips", "#gamingreels",
                   "#gamingnews", "#gamingcommunity", "#ps5", "#xbox"]
HASHTAGS_REACH = ["#shorts", "#reels", "#viral", "#fyp", "#foryou"]
HASHTAGS_BY_TYPE = {
    "crash": ["#gta6physics", "#gta6clips", "#gta6moments"],
    "poursuite": ["#gta6clips", "#gta6moments", "#vicecity"],
    "reaction": ["#gta6funny", "#gta6clips", "#gta6moments"],
    "physique": ["#gta6physics", "#gta6leonida", "#gta6gameplay"],
    "moment": ["#gta6gameplay", "#gta6clips", "#gta6eastereggs"],
}

# Mots qui signalent une réaction forte dans la transcription (FR + EN)
EXCLAIM_WORDS = {
    "oh", "wow", "quoi", "non", "regarde", "incroyable", "dingue", "fou", "folle", "mdr",
    "jamais", "attends", "sérieux", "putain", "wesh", "hein", "ouf", "abusé", "what",
    "no", "bro", "omg", "insane", "crazy", "look", "dude", "yo", "holy", "damn", "wtf",
}
# Mots colorés en vert dans les sous-titres (en plus des exclamations en jaune)
KEYWORDS = {
    "gta", "gta6", "police", "voiture", "crash", "explosion", "argent", "jason", "lucia",
    "vice", "city", "leonida", "secret", "easter", "egg", "bug", "hélico", "étoiles",
    "car", "cops", "money", "rockstar",
}
