#!/usr/bin/env python3
"""Vídeo bruto -> reel 9:16 com silêncios cortados e legenda palavra a palavra.

Etapas: corta silêncios (ffmpeg silencedetect), transcreve com faster-whisper,
gera legenda .ass com a palavra falada destacada e renderiza em 1080x1920.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

W, H = 1080, 1920


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"Erro rodando {cmd[0]}:\n{r.stderr[-2000:]}")
    return r


def duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", str(path)])
    return float(r.stdout.strip())


def has_audio(path):
    r = run(["ffprobe", "-v", "error", "-select_streams", "a",
             "-show_entries", "stream=index", "-of", "csv=p=0", str(path)])
    return bool(r.stdout.strip())


def keep_segments(path, noise_db, min_silence, pad):
    """Trechos com fala, a partir dos silêncios que o ffmpeg detecta."""
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-af",
         f"silencedetect=n={noise_db}dB:d={min_silence}", "-f", "null", "-"],
        capture_output=True, text=True)
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    total = duration(path)
    ends += [total] * (len(starts) - len(ends))

    keep, cursor = [], 0.0
    for s, e in zip(starts, ends):
        if s > cursor:
            keep.append((cursor, s))
        cursor = e
    if cursor < total:
        keep.append((cursor, total))

    padded = [(max(0.0, a - pad), min(total, b + pad)) for a, b in keep]
    merged = []
    for a, b in padded:
        if b - a < 0.05:
            continue
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged, total


def cut_silences(src, dst, segments):
    expr = "+".join(f"between(t,{a:.3f},{b:.3f})" for a, b in segments)
    vf = f"select='{expr}',setpts=N/FRAME_RATE/TB"
    af = f"aselect='{expr}',asetpts=N/SR/TB"
    run(["ffmpeg", "-y", "-hide_banner", "-i", str(src), "-vf", vf, "-af", af,
         "-c:v", "libx264", "-crf", "16", "-preset", "veryfast",
         "-c:a", "aac", "-b:a", "192k", str(dst)])


def transcribe(path, model_name, lang):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("Falta o faster-whisper. Instale com:  pip install faster-whisper")
    model = WhisperModel(model_name)
    segments, _ = model.transcribe(str(path), language=lang, word_timestamps=True)
    words = []
    for seg in segments:
        for w in seg.words or []:
            text = w.word.strip()
            if text:
                words.append({"word": text, "start": round(w.start, 3),
                              "end": round(w.end, 3)})
    return words


def ass_color(hex_color):
    h = hex_color.lstrip("#")
    if len(h) != 6:
        sys.exit(f"Cor inválida: {hex_color} (use #RRGGBB)")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}".upper()


def ass_time(t):
    t = max(0.0, t)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def ass_escape(text):
    return text.replace("\\", "").replace("{", "(").replace("}", ")")


def group_words(words, per_line, max_gap):
    groups, cur = [], []
    for w in words:
        if cur and (len(cur) >= per_line or w["start"] - cur[-1]["end"] > max_gap):
            groups.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.!?…]$", w["word"]):
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    return groups


def build_ass(words, args):
    base, hl = ass_color(args.color), ass_color(args.highlight)
    margin_v = int(H * (1 - args.position))
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}",
        "WrapStyle: 0", "ScaledBorderAndShadow: yes", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, "
        "MarginL, MarginR, MarginV, Encoding",
        f"Style: Reel,{args.font},{args.size},{base},{base},&H00000000,&H80000000,"
        f"-1,0,0,0,100,100,0,0,1,{args.outline},2,2,80,80,{margin_v},1",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    for group in group_words(words, args.words_per_line, args.max_gap):
        for i, w in enumerate(group):
            end = group[i + 1]["start"] if i + 1 < len(group) else w["end"]
            if end <= w["start"]:
                end = w["start"] + 0.05
            parts = []
            for j, other in enumerate(group):
                text = ass_escape(other["word"])
                if args.uppercase:
                    text = text.upper()
                if j == i:
                    text = (f"{{\\c{hl}\\fscx{args.pop}\\fscy{args.pop}}}{text}"
                            f"{{\\c{base}\\fscx100\\fscy100}}")
                parts.append(text)
            lines.append(f"Dialogue: 0,{ass_time(w['start'])},{ass_time(end)},Reel,,0,0,0,,"
                         + " ".join(parts))
    return "\n".join(lines) + "\n"


def render(src, ass_file, dst, workdir):
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"setsar=1,ass={ass_file.name}")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-i", str(src), "-vf", vf,
           "-c:v", "libx264", "-crf", "20", "-preset", "medium", "-pix_fmt", "yuv420p",
           "-r", "30", "-movflags", "+faststart"]
    cmd += ["-c:a", "aac", "-b:a", "160k"] if has_audio(src) else ["-an"]
    run(cmd + [str(dst)], cwd=workdir)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("input")
    p.add_argument("-o", "--output", help="padrão: <nome>_reel.mp4")
    p.add_argument("--no-cut", action="store_true", help="não cortar silêncios")
    p.add_argument("--silence-db", type=float, default=-35,
                   help="abaixo disso conta como silêncio (padrão -35)")
    p.add_argument("--min-silence", type=float, default=0.5,
                   help="pausa mínima em segundos para cortar (padrão 0.5)")
    p.add_argument("--pad", type=float, default=0.12,
                   help="respiro mantido antes/depois de cada fala (padrão 0.12)")
    p.add_argument("--words", help="usar este words.json em vez de transcrever")
    p.add_argument("--model", default="small", help="modelo do Whisper (padrão small)")
    p.add_argument("--lang", default="pt")
    p.add_argument("--no-captions", action="store_true")
    p.add_argument("--words-per-line", type=int, default=3)
    p.add_argument("--max-gap", type=float, default=0.6)
    p.add_argument("--font", default="Arial")
    p.add_argument("--size", type=int, default=84)
    p.add_argument("--outline", type=int, default=6)
    p.add_argument("--color", default="#FFFFFF")
    p.add_argument("--highlight", default="#FFD400")
    p.add_argument("--pop", type=int, default=112, help="zoom da palavra ativa em %%")
    p.add_argument("--position", type=float, default=0.72,
                   help="altura da legenda, 0 = topo, 1 = base (padrão 0.72)")
    p.add_argument("--no-uppercase", dest="uppercase", action="store_false")
    args = p.parse_args()

    for tool in ("ffmpeg", "ffprobe"):
        if not shutil.which(tool):
            sys.exit(f"Falta o {tool}. Instale o ffmpeg antes.")

    src = Path(args.input).resolve()
    if not src.exists():
        sys.exit(f"Arquivo não encontrado: {src}")
    dst = Path(args.output or src.with_name(src.stem + "_reel.mp4")).resolve()
    words_out = dst.with_suffix(".words.json")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        work = src
        if not args.no_cut and not args.words and has_audio(src):
            segments, total = keep_segments(src, args.silence_db, args.min_silence, args.pad)
            kept = sum(b - a for a, b in segments)
            if segments and kept < total - 0.2:
                work = tmp / "cut.mp4"
                cut_silences(src, work, segments)
                print(f"Silêncios cortados: {total:.1f}s -> {kept:.1f}s")
            else:
                print("Nenhum silêncio relevante para cortar.")
        elif args.words and not args.no_cut:
            print("Com --words, uso o vídeo como está (o words.json já é do vídeo cortado).")

        ass_file = tmp / "subs.ass"
        if args.no_captions:
            ass_file.write_text(build_ass([], args), encoding="utf-8")
        else:
            if args.words:
                words = json.loads(Path(args.words).read_text(encoding="utf-8"))
            else:
                if not has_audio(work):
                    sys.exit("O vídeo não tem áudio para transcrever. Use --no-captions.")
                print("Transcrevendo...")
                words = transcribe(work, args.model, args.lang)
                words_out.write_text(json.dumps(words, ensure_ascii=False, indent=1),
                                     encoding="utf-8")
                if work != src:
                    keep_cut = dst.with_name(dst.stem + "_cortado.mp4")
                    shutil.copy(work, keep_cut)
                print(f"Transcrição salva em {words_out}")
            ass_file.write_text(build_ass(words, args), encoding="utf-8")

        render(work, ass_file, dst, tmp)
    print(f"Pronto: {dst}")


if __name__ == "__main__":
    main()
