"""Montage vertical 9:16 : accroche, coupes, zooms, sous-titres mot par mot, boucle, watermark."""
import random
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import config as C
from .detect import Analysis, Moment, STEP, _norm_word
from .fetch import has_audio


@dataclass
class Plan:
    intervals: list  # [(a, b)] en secondes source, dans l'ordre de sortie
    zooms: list      # [(t0, t1, z_start, z_end)] en temps de sortie

    @property
    def duration(self):
        return sum(b - a for a, b in self.intervals)

    def to_out(self, t: float):
        off = 0.0
        for a, b in self.intervals:
            if a <= t < b:
                return off + t - a
            off += b - a
        return None


# ---------------------------------------------------------------- plan de montage

def plan_edit(m: Moment, a: Analysis) -> Plan:
    s, e, p = m.start, m.end, m.peak
    # 1) Supprimer les temps morts : calme + peu de mouvement + personne ne parle, >= 1 s
    q_loud = np.percentile(a.loud_db, 30)
    q_mot = np.percentile(a.motion, 40)
    spoken = np.zeros(len(a.loud_db), bool)
    for w in a.words:
        i0, i1 = int(w.start / STEP), int(w.end / STEP) + 1
        spoken[i0:i1] = True
    dead = (a.loud_db <= q_loud) & (a.motion <= q_mot) & ~spoken
    keep, cur = [], s
    i, i_end = int(s / STEP), int(e / STEP)
    while i < i_end:
        if dead[i]:
            j = i
            while j < i_end and dead[j]:
                j += 1
            if (j - i) * STEP >= 1.0:
                cut_a, cut_b = i * STEP + 0.15, j * STEP - 0.15
                if cut_a > cur and not (cut_a <= p <= cut_b):
                    keep.append((cur, cut_a))
                    cur = cut_b
            i = j
        else:
            i += 1
    keep.append((cur, e))
    keep = [(x, y) for x, y in keep if y - x > 0.2]

    # 2) Accroche + boucle : on commence juste avant le pic, on joue jusqu'à la fin,
    #    puis la montée en tension, qui se termine pile où la vidéo commence -> boucle parfaite.
    h = max(s, p - 0.4)
    part_a = [(max(x, h), y) for x, y in keep if y > h]
    part_b = [(x, min(y, h)) for x, y in keep if x < h]
    if sum(y - x for x, y in part_b) < 1.5:
        part_b = []
        part_a = keep if h - s < 1.5 else part_a
    order = part_a + part_b
    # 3) Durée max : on raccourcit la montée (début de part_b) puis la fin de part_a
    total = sum(y - x for x, y in order)
    while total > C.MAX_LEN and part_b:
        x, y = part_b[0]
        cut = min(total - C.MAX_LEN, y - x - 0.5)
        if cut <= 0:
            part_b.pop(0)
        else:
            part_b[0] = (x + cut, y)
        order = part_a + part_b
        total = sum(y - x for x, y in order)
    if total > C.MAX_LEN:
        x, y = order[len(part_a) - 1]
        order[len(part_a) - 1] = (x, y - (total - C.MAX_LEN))

    # 4) Zooms : coup de zoom à l'ouverture, puis alternance tous les ~2,5 s
    levels = [1.10, 1.0, 1.16, 1.04, 1.2, 1.0]
    zooms, t, k = [], 0.0, 0
    for x, y in order:
        seg_t = t
        while seg_t < t + (y - x) - 1e-3:
            ln = min(2.5, t + (y - x) - seg_t)
            z = levels[k % len(levels)]
            if k == 0:
                zooms.append((seg_t, seg_t + 0.45, 1.38, z))
                zooms.append((seg_t + 0.45, seg_t + ln, z, z + 0.03))
            else:
                zooms.append((seg_t, seg_t + ln, z, z + 0.03))
            seg_t += ln
            k += 1
        t += y - x
    return Plan([(round(x, 3), round(y, 3)) for x, y in order], zooms)


# ---------------------------------------------------------------- sous-titres ASS

def _ass_color(word: str, is_current: bool) -> str:
    n = _norm_word(word)
    if n in C.EXCLAIM_WORDS:
        return "&H00E5FF&"  # jaune
    if n in C.KEYWORDS or n.isdigit():
        return "&H4CFF4C&"  # vert
    return "&H00E5FF&" if is_current else "&HFFFFFF&"


def _esc(t: str) -> str:
    return t.replace("{", "(").replace("}", ")").replace("\\", "")


def _ts(t: float) -> str:
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    mnt, sec = divmod(rem, 60)
    return f"{int(h)}:{int(mnt):02d}:{sec:05.2f}"


def build_ass(plan: Plan, a: Analysis, hook: str, channel: str, out: Path):
    dur = plan.duration
    words = []
    for w in a.words:
        t0 = plan.to_out(w.start)
        if t0 is not None:
            t1 = plan.to_out(min(w.end, w.start + 1.2)) or t0 + 0.3
            words.append((t0, max(t1, t0 + 0.12), w.text.strip()))
    words.sort()
    # groupes de 1 à 3 mots
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) == 3 or w[0] - cur[-1][1] > 0.5 or cur[-1][2][-1:] in ".?!,"):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)

    hook_txt = _esc(hook.upper()).replace("GTA 6", r"{\c&H00E5FF&}GTA 6{\c&HFFFFFF&}")
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {C.W}", f"PlayResY: {C.H}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Hook,Montserrat Black,92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,8,4,8,60,60,90,1",
        "Style: Sub,Montserrat Black,96,&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,0,0,0,0,100,100,0,0,1,9,4,5,50,50,0,1",
        "Style: Mark,Montserrat ExtraBold,40,&H60FFFFFF,&H60FFFFFF,&H80000000,&H00000000,0,0,0,0,100,100,0,0,1,2,0,9,40,40,385,1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        f"Dialogue: 2,{_ts(0)},{_ts(dur)},Hook,,0,0,0,,{{\\fscx135\\fscy135\\t(0,260,\\fscx100\\fscy100)}}{hook_txt}",
        f"Dialogue: 1,{_ts(0)},{_ts(dur)},Mark,,0,0,0,,{_esc(channel)}",
    ]
    for ci, ch in enumerate(chunks):
        nxt = chunks[ci + 1][0][0] if ci + 1 < len(chunks) else dur
        for wi, (t0, t1, _) in enumerate(ch):
            end = ch[wi + 1][0] if wi + 1 < len(ch) else min(t1 + 0.35, nxt)
            parts = []
            for wj, (_, _, txt) in enumerate(ch):
                col = _ass_color(txt, wj == wi)
                tag = f"{{\\c{col}}}"
                if wj == wi:
                    tag = f"{{\\c{col}\\fscx118\\fscy118\\t(0,90,\\fscx100\\fscy100)}}"
                parts.append(tag + _esc(txt.upper()) + "{\\fscx100\\fscy100}")
            lines.append(f"Dialogue: 3,{_ts(t0)},{_ts(max(end, t0 + 0.1))},Sub,,0,0,0,,"
                         f"{{\\pos({C.W // 2},1420)}}" + " ".join(parts))
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- rendu ffmpeg

def _zoom_expr(zooms):
    expr = "1"
    for t0, t1, z0, z1 in reversed(zooms):
        d = max(t1 - t0, 1e-3)
        seg = f"({z0}+({z1}-{z0})*(it-{t0:.3f})/{d:.3f})"
        expr = f"if(between(it,{t0:.3f},{t1:.3f}),{seg},{expr})"
    return expr


def pick_music(music: str | None):
    if music == "none":
        return None
    if music:
        return Path(music)
    files = [p for p in C.MUSIC_DIR.glob("*") if p.suffix.lower() in {".mp3", ".wav", ".m4a", ".ogg"}]
    return random.choice(files) if files else None


def render(src: Path, plan: Plan, a: Analysis, hook: str, channel: str, out: Path,
           work: Path, music: str | None = None):
    work.mkdir(parents=True, exist_ok=True)
    ass = work / f"{out.stem}.ass"
    build_ass(plan, a, hook, channel, ass)
    s0 = max(0.0, min(x for x, _ in plan.intervals) - 0.5)
    span = max(y for _, y in plan.intervals) - s0 + 0.5
    audio = has_audio(src)
    mus = pick_music(music)

    cmd = ["ffmpeg", "-y", "-v", "error", "-ss", f"{s0:.3f}", "-t", f"{span:.3f}", "-i", str(src)]
    if mus:
        cmd += ["-stream_loop", "-1", "-i", str(mus)]
    fc = []
    n = len(plan.intervals)
    for k, (x, y) in enumerate(plan.intervals):
        x, y = x - s0, y - s0
        fc.append(f"[0:v]trim=start={x:.3f}:end={y:.3f},setpts=PTS-STARTPTS[v{k}]")
        if audio:
            fc.append(f"[0:a]atrim=start={x:.3f}:end={y:.3f},asetpts=PTS-STARTPTS,"
                      f"afade=t=in:d=0.02,afade=t=out:st={max(0, y - x - 0.03):.3f}:d=0.03[a{k}]")
    if audio:
        fc.append("".join(f"[v{k}][a{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac]")
    else:
        fc.append("".join(f"[v{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=0[vc]")
    fc.append(f"[vc]fps={C.FPS},setsar=1,split[b][f]")
    fc.append(f"[b]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,"
              f"boxblur=8:2,eq=brightness=-0.10:saturation=1.2,scale={C.W}:{C.H}[bg]")
    fc.append(f"[f]crop='min(iw,ih*{C.FG_W / C.FG_H:.4f})':ih,scale={C.FG_W}:{C.FG_H},"
              f"zoompan=z='{_zoom_expr(plan.zooms)}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
              f":d=1:s={C.FG_W}x{C.FG_H}:fps={C.FPS}[fg]")
    fc.append(f"[bg][fg]overlay=0:{C.FG_Y},ass=filename={ass.name}:fontsdir={C.FONTS_DIR}[vout]")
    dur = plan.duration
    game_a = "[ac]" if audio else None
    if mus:
        fc.append(f"[1:a]atrim=0:{dur:.3f},volume=0.12,afade=t=out:st={max(0, dur - 0.5):.3f}:d=0.5[mu]")
        if game_a:
            fc.append(f"{game_a}[mu]amix=inputs=2:duration=first:normalize=0[mx]")
            game_a = "[mx]"
        else:
            game_a = "[mu]"
    if game_a:
        fc.append(f"{game_a}loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")
    cmd += ["-filter_complex", ";".join(fc), "-map", "[vout]"]
    if game_a:
        cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out.resolve())]
    subprocess.run(cmd, check=True, cwd=work)

    thumb = out.with_suffix(".jpg")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", "0.6", "-i", str(out), "-frames:v", "1",
                    "-q:v", "2", str(thumb)], check=True)
    return out, thumb
