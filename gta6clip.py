#!/usr/bin/env python3
"""Une commande = tout le processus.

  python gta6clip.py <source> [--channel @MaChaine] [--max 8] [--music none|fichier]

<source> : fichier/dossier local, lien Google Drive partagé, ou URL Creative Commons.
Résultat : clips/*.mp4 (+ .jpg miniature, .json métadonnées), planning.csv, reports/*.md
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

from gta6 import config as C
from gta6.detect import analyze, find_moments, fmt_t
from gta6.fetch import fetch, RightsError
from gta6.meta import build_meta, hook_for, schedule
from gta6.render import plan_edit, render


def slug(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-")[:40] or "source"


def process(src: Path, args) -> list[dict]:
    name = slug(src.stem)
    work = C.WORK_DIR / name
    print(f"\n=== {src.name} ===\n[1/3] Analyse")
    a = analyze(src, work, use_whisper=not args.no_whisper)
    moments = find_moments(a, args.max)
    if args.min_score:
        moments = [m for m in moments if m.score >= args.min_score] or moments[:C.MIN_CLIPS_PER_SOURCE]
    print(f"  -> {len(moments)} moments retenus")

    report = [f"# Moments détectés – {src.name}\n", f"Durée : {fmt_t(a.duration)} · langue : {a.language}\n"]
    C.CLIPS_DIR.mkdir(exist_ok=True)
    made = []
    print("[2/3] Montage")
    for i, m in enumerate(moments, 1):
        clip_name = f"{name}_{i:02d}"
        out = C.CLIPS_DIR / f"{clip_name}.mp4"
        hook = args.hook or hook_for(m.kind, i - 1)
        plan = plan_edit(m, a)
        render(src, plan, a, hook, args.channel, out, work, args.music)
        meta = build_meta(m.kind, m.quote)
        meta.update({"hook": hook, "moment": m.to_dict(), "source": str(src),
                     "duration": round(plan.duration, 2), "thumbnail": out.with_suffix(".jpg").name,
                     "intervals_source": plan.intervals})
        out.with_suffix(".json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ✓ {out.name}  score {m.score}  {m.kind}  {plan.duration:.1f}s")
        report.append(f"\n## {i}. {clip_name} — score viral {m.score}/100 ({m.kind})\n"
                      f"- Extrait source : {fmt_t(m.start)} → {fmt_t(m.end)}, pic à {fmt_t(m.peak)}\n"
                      f"- Durée finale : {plan.duration:.1f} s · accroche : « {hook} »\n"
                      + "".join(f"- {r}\n" for r in m.reasons))
        made.append({"clip": out.name, "meta": meta, "score": m.score, "kind": m.kind})
    C.REPORTS_DIR.mkdir(exist_ok=True)
    (C.REPORTS_DIR / f"{name}.md").write_text("".join(report), encoding="utf-8")
    return made


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--channel", default=os.environ.get("GTA6_CHANNEL", C.CHANNEL_NAME))
    ap.add_argument("--max", type=int, default=C.MAX_CLIPS_PER_SOURCE)
    ap.add_argument("--min-score", type=int, default=0)
    ap.add_argument("--hook", help="forcer le texte d'accroche")
    ap.add_argument("--music", help="'none' ou chemin d'un son libre (sinon un son au hasard de music/)")
    ap.add_argument("--authorized", action="store_true", help="l'auteur de la vidéo t'a donné son accord")
    ap.add_argument("--no-whisper", action="store_true")
    ap.add_argument("--no-schedule", action="store_true")
    args = ap.parse_args()

    try:
        sources = fetch(args.source, args.authorized)
    except RightsError as e:
        sys.exit(f"⛔ {e}")
    made = []
    for src in sources:
        made += process(src, args)
    made.sort(key=lambda c: -c["score"])
    if made and not args.no_schedule:
        print("[3/3] Planning")
        schedule(made)
        print(f"  -> {C.PLANNING_CSV}")
    print(f"\nTerminé : {len(made)} clips dans {C.CLIPS_DIR}")


if __name__ == "__main__":
    main()
