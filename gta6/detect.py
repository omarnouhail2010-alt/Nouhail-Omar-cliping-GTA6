"""Détection automatique des meilleurs moments d'une vidéo.

Signaux combinés (grille de 0,5 s) :
  - volume (pics = explosions, cris, tirs)          -> ffmpeg + numpy
  - intensité visuelle (score de scène par image)   -> ffmpeg select/scene
  - coupes / changements de plan                    -> PySceneDetect
  - réactions parlées (mots d'exclamation)           -> faster-whisper (horodatage par mot)
"""
import math
import re
import subprocess
import wave
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np

from . import config as C
from .fetch import ffprobe_duration, has_audio

STEP = 0.5


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Moment:
    start: float
    end: float
    peak: float
    score: int
    kind: str
    reasons: list = field(default_factory=list)
    quote: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class Analysis:
    duration: float
    loud_db: np.ndarray
    motion: np.ndarray
    cuts: list
    words: list
    language: str = "fr"


# ---------------------------------------------------------------- signaux

def _extract_wav(src: Path, wav: Path):
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn", "-ac", "1",
                    "-ar", "16000", "-c:a", "pcm_s16le", str(wav)], check=True)


def loudness_curve(wav: Path, n_bins: int) -> np.ndarray:
    with wave.open(str(wav)) as w:
        sr = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32)
    data /= 32768.0
    hop = int(sr * STEP)
    out = np.full(n_bins, -80.0)
    for i in range(n_bins):
        seg = data[i * hop:(i + 1) * hop]
        if len(seg):
            # RMS en dB + petit bonus pour les crêtes (impacts courts)
            rms = math.sqrt(float(np.mean(seg ** 2)) + 1e-12)
            peak = float(np.max(np.abs(seg))) + 1e-9
            out[i] = 0.7 * 20 * math.log10(rms + 1e-9) + 0.3 * 20 * math.log10(peak)
    return out


def motion_curve(src: Path, n_bins: int) -> np.ndarray:
    """Score de différence entre images (0..1), moyenné par case de 0,5 s."""
    cmd = ["ffmpeg", "-v", "error", "-i", str(src), "-an", "-vf",
           "fps=6,scale=320:-2,select='gte(scene,0)',metadata=print:file=-", "-f", "null", "-"]
    txt = subprocess.run(cmd, capture_output=True, text=True).stdout
    times = [float(x) for x in re.findall(r"pts_time:([\d.]+)", txt)]
    scores = [float(x) for x in re.findall(r"lavfi\.scene_score=([\d.]+)", txt)]
    out = np.zeros(n_bins)
    cnt = np.zeros(n_bins)
    for t, s in zip(times, scores):
        i = min(int(t / STEP), n_bins - 1)
        out[i] += s
        cnt[i] += 1
    return out / np.maximum(cnt, 1)


def scene_cuts(src: Path) -> list[float]:
    from scenedetect import detect, ContentDetector
    try:
        scenes = detect(str(src), ContentDetector(threshold=27.0, min_scene_len=8),
                        show_progress=False)
    except Exception as e:  # vidéo illisible par OpenCV : on continue sans
        print(f"  ! PySceneDetect : {e}")
        return []
    return [s[0].get_seconds() for s in scenes[1:]]


def transcribe(wav: Path) -> tuple[list[Word], str]:
    from faster_whisper import WhisperModel
    model = WhisperModel(C.WHISPER_MODEL, device="cpu", compute_type="int8")
    with wave.open(str(wav)) as w:  # wav 16 kHz mono (évite la dépendance à PyAV)
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    segments, info = model.transcribe(audio, word_timestamps=True, vad_filter=True,
                                      beam_size=1, condition_on_previous_text=False)
    words = []
    for seg in segments:
        for w in seg.words or []:
            t = w.word.strip()
            if not t:
                continue
            # « c » + « 'est » -> « c'est » (Whisper colle les morceaux sans espace)
            if words and not w.word.startswith(" ") and w.start - words[-1].end < 0.3:
                words[-1] = Word(words[-1].start, float(w.end), words[-1].text + t)
            else:
                words.append(Word(float(w.start), float(w.end), t))
    return words, info.language


def analyze(src: Path, work: Path, use_whisper: bool = True) -> Analysis:
    work.mkdir(parents=True, exist_ok=True)
    dur = ffprobe_duration(src)
    n = max(1, int(math.ceil(dur / STEP)))
    print("  - volume…")
    if has_audio(src):
        wav = work / "audio.wav"
        _extract_wav(src, wav)
        loud = loudness_curve(wav, n)
    else:
        wav, loud = None, np.full(n, -80.0)
    print("  - mouvement…")
    motion = motion_curve(src, n)
    print("  - changements de scène (PySceneDetect)…")
    cuts = scene_cuts(src)
    words, lang = [], "fr"
    if use_whisper and wav is not None:
        print("  - transcription (faster-whisper)…")
        words, lang = transcribe(wav)
    return Analysis(dur, loud, motion, cuts, words, lang)


# ---------------------------------------------------------------- scoring

def _rz(x: np.ndarray) -> np.ndarray:
    """z-score robuste (médiane / MAD)."""
    med = np.median(x)
    mad = np.median(np.abs(x - med)) * 1.4826 + 1e-6
    return np.clip((x - med) / mad, -3, 6)


def _norm_word(t: str) -> str:
    return re.sub(r"[^\wàâçéèêëîïôûùüÿœ']", "", t.lower())


def _smooth(x, k=3):
    return np.convolve(x, np.ones(k) / k, mode="same")


def fmt_t(t: float) -> str:
    return f"{int(t // 60):02d}:{int(t % 60):02d}"


def find_moments(a: Analysis, max_n: int = C.MAX_CLIPS_PER_SOURCE) -> list[Moment]:
    n = len(a.loud_db)
    zl, zm = _rz(a.loud_db), _rz(a.motion)
    cut_density = np.zeros(n)
    for c in a.cuts:
        i = min(int(c / STEP), n - 1)
        cut_density[max(0, i - 4):i + 5] += 1
    exclaim = np.zeros(n)
    speech = np.zeros(n)
    for w in a.words:
        i = min(int(w.start / STEP), n - 1)
        speech[i] += 1
        if _norm_word(w.text) in C.EXCLAIM_WORDS:
            exclaim[i] += 1
    excite = 0.45 * zl + 0.30 * zm + 0.15 * _rz(cut_density) + 0.10 * np.minimum(speech, 3) \
        + 1.2 * np.minimum(exclaim, 2)
    sm = _smooth(excite, 3)

    dur = a.duration
    if dur <= C.MIN_LEN + 1:
        peaks = [int(np.argmax(sm))]
    else:
        order = np.argsort(-sm)
        peaks = [int(i) for i in order
                 if sm[i] >= sm[max(0, i - 3):i + 4].max() - 1e-9]
    chosen: list[Moment] = []
    for pi in peaks:
        if len(chosen) >= max_n:
            break
        p = pi * STEP + STEP / 2
        s, e = _window(p, dur, a.cuts, sm)
        if any(_overlap((s, e), (m.start, m.end)) > 0.3 for m in chosen):
            continue
        chosen.append(_score(a, s, e, p, zl, zm, exclaim))
    chosen.sort(key=lambda m: -m.score)
    return chosen


def _overlap(x, y):
    inter = max(0.0, min(x[1], y[1]) - max(x[0], y[0]))
    return inter / max(1e-6, min(x[1] - x[0], y[1] - y[0]))


def _window(p, dur, cuts, sm):
    if dur <= C.MAX_LEN:
        return 0.0, dur
    pre, post = C.TARGET_LEN * 0.62, C.TARGET_LEN * 0.38
    s, e = p - pre, p + post
    # Aligner le début sur un changement de plan proche (démarrage propre)
    near = [c for c in cuts if abs(c - s) <= 3 and c < p - 4]
    if near:
        s = min(near, key=lambda c: abs(c - s))
    # Prolonger si l'action continue juste après la fin
    i_end = int(e / STEP)
    while e - s < C.MAX_LEN - 1 and i_end < len(sm) and sm[i_end] > 1.0:
        e += STEP
        i_end += 1
    if s < 0:
        e, s = e - s, 0.0
    if e > dur:
        s, e = max(0.0, s - (e - dur)), dur
    return round(s, 2), round(e, 2)


def _score(a, s, e, p, zl, zm, exclaim) -> Moment:
    i0, i1 = int(s / STEP), max(int(s / STEP) + 1, int(e / STEP))
    ip = min(int(p / STEP), len(zl) - 1)
    seg_l, seg_m = zl[i0:i1], zm[i0:i1]
    n_cuts = sum(1 for c in a.cuts if s <= c <= e)
    n_excl = int(exclaim[i0:i1].sum())
    top = np.sort(0.6 * seg_l + 0.4 * seg_m)[-max(1, len(seg_l) // 4):].mean()
    raw = 0.35 * zl[ip] + 0.15 * zm[ip] + 0.30 * top + 0.12 * (n_cuts / max(1, (e - s) / 10)) \
        + 0.35 * min(n_excl, 4)
    score = int(round(100 / (1 + math.exp(-(raw - 1.2) / 0.9))))

    reasons = []
    db_above = a.loud_db[ip] - np.median(a.loud_db)
    if zl[ip] > 2:
        reasons.append(f"Pic de volume +{db_above:.0f} dB à {fmt_t(p)} (explosion, impact ou cri probable)")
    if zm[ip] > 1.5 or seg_m.mean() > 1:
        reasons.append("Beaucoup de mouvement à l'écran (action rapide)")
    if n_cuts >= 3:
        reasons.append(f"{n_cuts} changements de plan en {e - s:.0f} s (rythme nerveux)")
    words_in = [w for w in a.words if s <= w.start <= e]
    quote = ""
    if n_excl:
        near = [w for w in words_in if abs(w.start - p) < 6]
        quote = " ".join(w.text for w in near[:12])
        reasons.append(f"Réaction forte captée ({n_excl} exclamation(s)) : « {quote} »")
    elif words_in:
        reasons.append(f"{len(words_in)} mots de commentaire (sous-titres possibles)")
    if not reasons:
        reasons.append("Moment le plus intense de cette partie de la vidéo")

    if n_excl >= 2:
        kind = "reaction"
    elif zl[ip] > 3 and zm[ip] > 1:
        kind = "crash"
    elif n_cuts >= 4 or seg_m.mean() > 1.2:
        kind = "poursuite"
    elif zm[ip] > 1.5 and zl[ip] < 1.5:
        kind = "physique"
    else:
        kind = "moment"
    return Moment(s, e, round(p, 2), score, kind, reasons, quote)
