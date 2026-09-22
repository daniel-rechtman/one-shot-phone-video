#!/usr/bin/env python3
"""
seedance — כלי CLI מקומי לניסויים עם Seedance (ByteDance) דרך fal.ai.

stdlib בלבד. אין pip install. אין תלויות.

    ./seedance.py t2v "חתול רוקד על גג בתל אביב" --dur 5 --ar 9:16
    ./seedance.py i2v product.png "המצלמה מקיפה את המוצר" --dur 6
    ./seedance.py ref "@Image1 מדבר עם @Image2" -i a.png -i b.png
    ./seedance.py cost --res 1080p --dur 10        # כמה זה יעלה, בלי לשלם
    ./seedance.py spend                            # כמה הוצאתי עד עכשיו
    ./seedance.py get <request_id>                 # לשחזר job שנתקע
"""

import argparse
import base64
import json
import mimetypes
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"
LEDGER = RUNS / "ledger.jsonl"

QUEUE = "https://queue.fal.run"
UPLOAD_INITIATE = "https://rest.alpha.fal.ai/storage/upload/initiate?storage_type=fal-cdn-v3"

# ---------------------------------------------------------------- תמחור
# fal מתמחר את Seedance לפי טוקנים:  tokens = (h * w * seconds * 24) / 1024
# standard = $0.014 / 1k tokens   |   fast = $0.0112 / 1k tokens (0.8x)
# אימות: 1280x720 standard -> 21,600 tok/s -> $0.3024/s, בדיוק המחיר המפורסם.
TOK_PER_1K = {"standard": 0.014, "fast": 0.0112}
SHORT_EDGE = {"480p": 480, "720p": 720, "1080p": 1080, "4k": 2160}
ASPECTS = {
    "21:9": 21 / 9, "16:9": 16 / 9, "4:3": 4 / 3,
    "1:1": 1.0, "3:4": 3 / 4, "9:16": 9 / 16,
}
# --- MiniMax H3 (Hailuo-03) — תמחור שטוח לשנייה לפי רזולוציה, לא לפי טוקנים.
# 5 תמונות רפרנס ראשונות חינם, כל נוספת $0.08.
H3_PER_SEC = {"480P": 0.05, "768P": 0.06, "2K": 0.13, "4K": 0.16}
H3_EXTRA_REF = 0.08
H3_FREE_REFS = 5
H3_RES_ALIAS = {"480p": "480P", "768p": "768P", "720p": "768P",
                "1080p": "2K", "2k": "2K", "4k": "4K"}
MINIMAX_IMAGE = "fal-ai/minimax/image-01"
IMAGE_USD = 0.01

# מעל זה הכלי עוצר ושואל לפני שהוא שורף כסף
CONFIRM_ABOVE_USD = float(os.environ.get("SEEDANCE_CONFIRM_ABOVE", "2.50"))


def h3_res(res):
    """ממפה --res לאנום של H3, שהוא באותיות גדולות ושונה מ-Seedance."""
    r = H3_RES_ALIAS.get(str(res).lower())
    if r is None:
        die(f"H3 תומך ב-480P/768P/2K/4K בלבד. קיבלתי {res!r}.")
    if str(res).lower() in ("720p", "1080p"):
        print(f"  ℹ️  {res} → {r} (H3 לא מכיר {res})")
    return r


def h3_estimate(res, seconds, n_refs=0):
    usd = H3_PER_SEC[res] * seconds
    extra = max(0, n_refs - H3_FREE_REFS)
    return usd + extra * H3_EXTRA_REF, extra


# fal לא מחזיר בדיוק את הממדים הנומינליים. נמדד בפועל: ביקשנו 480p 9:16,
# קיבלנו 496x864 במקום 480x853 — כ-4.7% יותר פיקסלים, כלומר 4.7% יותר כסף.
# כלל העיגול שלהם לא ידוע מדגימה אחת, אז במקום לנחש אותו — מרווח ביטחון.
# ההערכה היא חסם עליון. העלות האמיתית נמדדת מה-MP4 אחרי ההורדה.
SAFETY = 1.10


def dims(resolution, aspect):
    """(w, h) נומינליים. הצלע הקצרה היא מחלקת הרזולוציה."""
    short = SHORT_EDGE[resolution]
    ratio = ASPECTS.get(aspect)
    if ratio is None:  # auto -> מניחים 16:9
        ratio = 16 / 9
    if ratio >= 1:
        return int(round(short * ratio)), short
    return short, int(round(short / ratio))


def estimate(resolution, aspect, seconds, tier):
    w, h = dims(resolution, aspect)
    tokens = (w * h * seconds * 24) / 1024
    return tokens / 1000 * TOK_PER_1K[tier] * SAFETY, (w, h), tokens


# ---------------------------------------------------------------- auth
def fal_key():
    k = os.environ.get("FAL_KEY") or os.environ.get("FAL_API_KEY")
    if k:
        return k.strip()
    secret = Path.home() / ".claude" / "secrets" / "fal.json"
    if secret.exists():
        try:
            d = json.loads(secret.read_text())
            for field in ("FAL_KEY", "api_key", "key", "fal_key"):
                if d.get(field):
                    return str(d[field]).strip()
        except json.JSONDecodeError:
            die(f"{secret} אינו JSON תקין.")
    die(
        "לא נמצא FAL_KEY.\n"
        "  קח מפתח מ- https://fal.ai/dashboard/keys ואז:\n"
        '    echo \'{"FAL_KEY":"<המפתח>"}\' > ~/.claude/secrets/fal.json\n'
        "  או:  export FAL_KEY=...",
    )


def die(msg, code=1):
    print(f"\n✗ {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------- HTTP
def req(url, method="GET", body=None, headers=None, raw=None, timeout=180):
    h = {"Authorization": f"Key {fal_key()}"}
    h.update(headers or {})
    data = raw
    if body is not None:
        data = json.dumps(body).encode()
        h.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            payload = resp.read()
            ctype = resp.headers.get("Content-Type", "")
            if "json" in ctype:
                return json.loads(payload)
            return payload
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:1200]
        low = detail.lower()
        if e.code == 403 and ("exhausted balance" in low or "top_up" in low or "user is locked" in low):
            die("נגמרו הקרדיטים ב-fal. החשבון נעול עד טעינה:\n"
                "  https://fal.ai/dashboard/billing\n"
                "  (לא חויבת על הניסיון הזה — שום דבר לא נוצר.)")
        if e.code == 401:
            die("המפתח נדחה (401). בדוק את ~/.claude/secrets/fal.json מול fal.ai/dashboard/keys.")
        if e.code == 422:
            die(f"הסכמה נדחתה (422) — פרמטר לא תקין:\n{detail}")
        die(f"HTTP {e.code} מ-{url}\n{detail}")
    except urllib.error.URLError as e:
        die(f"שגיאת רשת מול {url}: {e.reason}")


# ---------------------------------------------------------------- העלאת קבצים
def to_url(path_or_url):
    """קובץ מקומי -> URL של fal. URL נשאר כמו שהוא."""
    s = str(path_or_url)
    if s.startswith(("http://", "https://", "data:")):
        return s
    p = Path(s).expanduser().resolve()
    if not p.exists():
        die(f"הקובץ לא קיים: {p}")
    ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    blob = p.read_bytes()
    mb = len(blob) / 1e6
    print(f"  ↑ מעלה {p.name} ({mb:.1f}MB)…", flush=True)

    # מסלול א' — אחסון fal הרשמי
    try:
        init = req(UPLOAD_INITIATE, "POST",
                   {"content_type": ctype, "file_name": p.name}, timeout=60)
        if isinstance(init, dict) and init.get("upload_url") and init.get("file_url"):
            urllib.request.urlopen(
                urllib.request.Request(init["upload_url"], data=blob,
                                       headers={"Content-Type": ctype}, method="PUT"),
                timeout=300,
            ).read()
            return init["file_url"]
    except SystemExit:
        pass  # die() נקרא בפנים — נופלים למסלול ב'
    except Exception:
        pass

    # מסלול ב' — data URI (מוגבל בגודל, מספיק לתמונות)
    if mb > 9:
        die(f"העלאה ל-fal נכשלה ו-{p.name} גדול מדי ל-data URI ({mb:.1f}MB). "
            "העלה ידנית ותן URL.")
    print("  ↳ אחסון fal לא זמין, עובר ל-data URI", flush=True)
    return f"data:{ctype};base64," + base64.b64encode(blob).decode()


# ---------------------------------------------------------------- ledger
def log_run(entry):
    RUNS.mkdir(exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- הרצה
def endpoint(kind, model, fast, engine="seedance"):
    if engine == "h3":
        return f"minimax/h3/{kind}"
    tier = "fast/" if fast else ""
    return f"bytedance/seedance-{model}/{tier}{kind}"


def submit_and_wait(ep, payload, label, est_usd, args, ctx=None):
    RUNS.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    outdir = RUNS / f"{stamp}-{label}"

    if args.dry_run:
        print(f"\n--- DRY RUN ---\nendpoint: {ep}\n{json.dumps(payload, ensure_ascii=False, indent=2)[:2000]}")
        print(f"עלות משוערת: ${est_usd:.2f}  (לא נשלח כלום)")
        return

    if est_usd > CONFIRM_ABOVE_USD and not args.yes:
        if not sys.stdin.isatty():
            die(f"עלות משוערת ${est_usd:.2f} מעל הסף ${CONFIRM_ABOVE_USD:.2f}. הוסף --yes.")
        ans = input(f"\n⚠️  עלות משוערת ${est_usd:.2f}. להריץ? [y/N] ").strip().lower()
        if ans not in ("y", "yes", "כן"):
            print("בוטל.")
            return

    print(f"\n▶ {ep}")
    job = req(f"{QUEUE}/{ep}", "POST", payload)
    rid = job.get("request_id")
    status_url = job.get("status_url") or f"{QUEUE}/{ep}/requests/{rid}/status"
    result_url = job.get("response_url") or f"{QUEUE}/{ep}/requests/{rid}"
    print(f"  request_id: {rid}")

    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "request.json").write_text(
        json.dumps({"endpoint": ep, "request_id": rid, "payload": payload,
                    "status_url": status_url, "result_url": result_url,
                    "est_usd": round(est_usd, 4)}, ensure_ascii=False, indent=2))

    t0 = time.time()
    last = None
    while True:
        st = req(f"{status_url}?logs=1")
        state = st.get("status")
        if state != last:
            print(f"  [{time.time()-t0:5.0f}s] {state}"
                  + (f"  תור: {st['queue_position']}" if st.get("queue_position") is not None else ""))
            last = state
        if state == "COMPLETED":
            if time.time() - t0 < 2:
                print("  ⚠️  הסתיים מיידית — חשוד. בודק את התוצאה…")
            break
        if state in ("FAILED", "ERROR", "CANCELLED"):
            (outdir / "error.json").write_text(json.dumps(st, ensure_ascii=False, indent=2))
            die(f"ה-job נכשל ({state}). פרטים: {outdir/'error.json'}")
        if time.time() - t0 > 1800:
            die(f"timeout אחרי 30 דק'. שחזר עם:  ./seedance.py get {rid} --endpoint {ep}")
        time.sleep(3)

    res = req(result_url)
    return save_result(res, outdir, ep, rid, est_usd, time.time() - t0, args, ctx)


def actual_cost(mp4, tier, ctx=None):
    """מודד עלות אמיתית מה-MP4. ctx נושא את מודל התמחור — H3 שטוח לשנייה,
    Seedance לפי טוקנים. בלי זה היינו מחשבים ל-H3 מחיר של Seedance (באג שנתפס
    בהרצה הראשונה: דיווח $27.85 על קליפ שעלה $1.62)."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(mp4)],
            capture_output=True, text=True, timeout=30)
        vals = [v for v in out.stdout.split() if v]
        if len(vals) < 3:
            return None
        w, h, dur = int(vals[0]), int(vals[1]), float(vals[2])
        if ctx and ctx.get("engine") == "h3":
            extra = max(0, ctx.get("n_refs", 0) - H3_FREE_REFS)
            usd = H3_PER_SEC[ctx["res"]] * dur + extra * H3_EXTRA_REF
            return usd, w, h, dur
        tokens = (w * h * dur * 24) / 1024
        return tokens / 1000 * TOK_PER_1K[tier], w, h, dur
    except Exception:
        return None


def save_result(res, outdir, ep, rid, est_usd, secs, args, ctx=None):
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "result.json").write_text(json.dumps(res, ensure_ascii=False, indent=2))
    video = (res.get("video") or {}) if isinstance(res, dict) else {}
    url = video.get("url")
    if not url:
        print(f"⚠️  אין וידאו בתשובה. ראה {outdir/'result.json'}")
        return
    mp4 = outdir / (video.get("file_name") or "out.mp4")
    print("  ↓ מוריד…", flush=True)
    with urllib.request.urlopen(url, timeout=600) as r, mp4.open("wb") as f:
        f.write(r.read())
    size = mp4.stat().st_size / 1e6

    tier = "fast" if "/fast/" in ep else "standard"
    act = actual_cost(mp4, tier, ctx)
    entry = {"ts": datetime.now(timezone.utc).isoformat(), "endpoint": ep,
             "request_id": rid, "est_usd": round(est_usd, 4),
             "wall_s": round(secs), "file": str(mp4), "seed": res.get("seed")}
    if act:
        usd, w, h, dur = act
        entry.update({"actual_usd": round(usd, 4), "dims": f"{w}x{h}", "secs": round(dur, 2)})
    log_run(entry)

    if act:
        usd, w, h, dur = act
        drift = (usd - est_usd) / est_usd * 100 if est_usd else 0
        flag = f"  ⚠️ מעל החסם העליון ב-{drift:.0f}%" if drift > 3 else ""
        print(f"\n✓ {mp4}  ({size:.1f}MB, {secs:.0f}s wall)")
        print(f"  בפועל: {w}x{h} · {dur:.1f}s · ${usd:.2f}   (הוערך ${est_usd:.2f}){flag}")
    else:
        print(f"\n✓ {mp4}  ({size:.1f}MB, {secs:.0f}s, ~${est_usd:.2f})")
    if getattr(args, "open", False):
        subprocess.run(["open", str(mp4)], check=False)
    return mp4


# ---------------------------------------------------------------- פקודות
def common_video_args(p, with_audio=True):
    p.add_argument("--dur", default="auto", help="שניות 4-15, או auto (ברירת מחדל)")
    p.add_argument("--res", default="720p",
                   choices=["480p", "720p", "768p", "1080p", "2k", "4k"],
                   help="Seedance: 480p/720p/1080p/4k · H3: 480p/768p/2k/4k")
    p.add_argument("--ar", default="auto", choices=["auto", *ASPECTS], help="יחס תצוגה")
    p.add_argument("--fast", action="store_true", help="tier מהיר — 20%% זול יותר, מקס 720p (Seedance)")
    p.add_argument("--model", default="2.0", choices=["2.0", "2.5"])
    p.add_argument("--engine", default="seedance", choices=["seedance", "h3"],
                   help="h3 = MiniMax Hailuo-03 — זול משמעותית, 2K/4K")
    p.add_argument("--seed", type=int)
    if with_audio:
        p.add_argument("--no-audio", action="store_true", help="בלי סאונד (המחיר לא משתנה)")
    p.add_argument("--dry-run", action="store_true", help="להראות payload ועלות בלי לשלם")
    p.add_argument("-y", "--yes", action="store_true", help="לדלג על אישור העלות")
    p.add_argument("--open", action="store_true", help="לפתוח את ה-MP4 בסוף")


def check_res(args):
    """לכל מנוע סולם רזולוציות משלו. עדיף ליפול כאן מאשר לקבל 422 מ-fal."""
    if getattr(args, "engine", "seedance") == "seedance" and args.res in ("768p", "2k"):
        die(f"{args.res} הוא סולם של H3. ל-Seedance: 480p/720p/1080p/4k, "
            f"או הוסף --engine h3.")


def base_payload(args):
    check_res(args)
    if getattr(args, "engine", "seedance") == "h3":
        secs, _ = billable_seconds(args.dur)
        d = {"resolution": h3_res(args.res), "duration": int(secs),
             "aspect_ratio": "adaptive" if args.ar == "auto" else args.ar}
        if args.seed is not None:
            d["seed"] = args.seed
        if getattr(args, "no_audio", False):
            print("  ℹ️  ל-H3 אין כיבוי אודיו — הוא תמיד מפיק סטריאו נייטיב.")
        return d
    d = {"resolution": args.res, "duration": str(args.dur), "aspect_ratio": args.ar}
    if getattr(args, "no_audio", False):
        d["generate_audio"] = False
    if args.seed is not None:
        d["seed"] = args.seed
    return d


def billable_seconds(dur):
    """'auto' לא ידוע מראש — מעריכים 5ש' ואומרים את זה."""
    try:
        return float(dur), False
    except (TypeError, ValueError):
        return 5.0, True


def price_ctx(args, n_refs=0):
    """מה שצריך כדי לחשב עלות אמיתית אחרי ההרצה."""
    if getattr(args, "engine", "seedance") == "h3":
        return {"engine": "h3", "res": h3_res(args.res), "n_refs": n_refs}
    return {"engine": "seedance", "tier": "fast" if args.fast else "standard"}


def price_line(args, n_refs=0):
    secs, guessed = billable_seconds(args.dur)
    if getattr(args, "engine", "seedance") == "h3":
        res = h3_res(args.res)
        usd, extra = h3_estimate(res, secs, n_refs)
        note = " (auto — מוערך כ-5ש')" if guessed else ""
        xtra = f" + {extra} רפרנס מעבר ל-5 (${extra*H3_EXTRA_REF:.2f})" if extra else ""
        print(f"  H3 · {res} · {secs:g}s{note} → ${usd:.2f}{xtra}")
        return usd
    tier = "fast" if args.fast else "standard"
    usd, (w, h), tok = estimate(args.res, args.ar, secs, tier)
    note = " (auto — מוערך כ-5ש')" if guessed else ""
    ar = args.ar if args.ar != "auto" else "16:9?"
    print(f"  ~{w}x{h} · {ar} · {secs:g}s{note} · {tier} → עד ${usd:.2f}  ({tok/1000:.0f}k tokens)")
    if args.fast and args.res in ("1080p", "4k"):
        print("  ⚠️  tier מהיר מוגבל ל-720p. הסר --fast לרזולוציה הזו.")
    return usd


def cmd_t2v(args):
    p = base_payload(args)
    p["prompt"] = args.prompt
    if args.engine == "h3":
        die("ל-H3 לא אימתתי endpoint של text-to-video. השתמש ב-i2v/ref, או --engine seedance.")
    usd = price_line(args)
    return submit_and_wait(endpoint("text-to-video", args.model, args.fast, args.engine), p, "t2v", usd, args, price_ctx(args, 0))


def cmd_i2v(args):
    p = base_payload(args)
    p["prompt"] = args.prompt
    p["image_url"] = to_url(args.image)
    if args.end_image:
        p["end_image_url"] = to_url(args.end_image)
    usd = price_line(args, 1)
    return submit_and_wait(endpoint("image-to-video", args.model, args.fast, args.engine), p, "i2v", usd, args, price_ctx(args, 1))


def cmd_ref(args):
    total = len(args.image) + len(args.video) + len(args.audio)
    if total == 0:
        die("reference-to-video דורש לפחות רפרנס אחד (-i / -v / -a).")
    if total > 12:
        die(f"מקסימום 12 קבצים סה\"כ, נתת {total}.")
    if len(args.image) > 9 or len(args.video) > 3 or len(args.audio) > 3:
        die("מגבלות: עד 9 תמונות, 3 וידאו, 3 אודיו.")
    if args.audio and not (args.image or args.video):
        die("אודיו דורש לפחות תמונה או וידאו אחד.")
    p = base_payload(args)
    p["prompt"] = args.prompt
    pre = "reference_" if args.engine == "h3" else ""
    if args.image:
        p[f"{pre}image_urls"] = [to_url(x) for x in args.image]
    if args.video:
        p[f"{pre}video_urls"] = [to_url(x) for x in args.video]
    if args.audio:
        p[f"{pre}audio_urls"] = [to_url(x) for x in args.audio]
    print(f"  רפרנסים: {len(args.image)} תמונות, {len(args.video)} וידאו, {len(args.audio)} אודיו")
    if "@" not in args.prompt and args.engine == "seedance":
        print('  💡 הפרומפט לא מזכיר @Image1/@Video1/@Audio1 — המודל לא ידע למה להתייחס.')
    if args.engine == "h3" and "Image 1" not in args.prompt and "@" not in args.prompt:
        print('  💡 H3 מצטט רפרנסים כ-"Image 1" / "Video 1" — כדאי להזכיר אותם בפרומפט.')
    usd = price_line(args, total)
    return submit_and_wait(endpoint("reference-to-video", args.model, args.fast, args.engine), p, "ref", usd, args, price_ctx(args, total))


def cmd_cost(args):
    print("\nמחשבון עלות Seedance (fal.ai)\n")
    secs, guessed = billable_seconds(args.dur)
    print(f"{'רזולוציה':<10} {'ממדים':<12} {'standard':>10} {'fast':>10}   ל-{secs:g} שניות (חסם עליון)")
    print("-" * 52)
    for res in SHORT_EDGE:
        s, (w, h), _ = estimate(res, args.ar, secs, "standard")
        f, _, _ = estimate(res, args.ar, secs, "fast")
        flag = "" if res != "4k" else "  ← יקר"
        print(f"{res:<10} {f'{w}x{h}':<12} {'$'+format(s,'.2f'):>10} {'$'+format(f,'.2f'):>10}{flag}")
    print(f"\nכולל מרווח ביטחון של {(SAFETY-1)*100:.0f}% — fal מפיק ממדים קצת גדולים מהנומינליים.")
    print(f"יחס: {args.ar if args.ar != 'auto' else '16:9 (הנחה)'}"
          + ("   · duration=auto הוערך כ-5ש'" if guessed else ""))
    print("fast מוגבל ל-720p ומטה.")


def cmd_spend(args):
    if not LEDGER.exists():
        print("עוד לא הרצת כלום.")
        return
    rows = [json.loads(l) for l in LEDGER.read_text().splitlines() if l.strip()]
    total = sum(r.get("actual_usd", r.get("est_usd", 0)) for r in rows)
    print(f"\n{len(rows)} הרצות · סה\"כ משוער ${total:.2f}\n")
    for r in rows[-args.n:]:
        ts = r["ts"][:16].replace("T", " ")
        c = r.get("actual_usd", r.get("est_usd", 0))
        mark = " " if "actual_usd" in r else "~"
        print(f"  {ts} {mark}${c:>5.2f}  {r['endpoint'].split('/',1)[1]:<34} {r.get('dims','')}")
    print("\n(~ = הערכה מראש · בלי ~ = נמדד מה-MP4 · החיוב הרשמי: fal.ai/dashboard/usage)")


def cmd_get(args):
    ep = args.endpoint
    rid = args.request_id
    res = req(f"{QUEUE}/{ep}/requests/{rid}")
    outdir = RUNS / f"recovered-{rid[:8]}"
    save_result(res, outdir, ep, rid, 0.0, 0, args)


def main():
    ap = argparse.ArgumentParser(prog="seedance", description="Seedance דרך fal.ai — ניסויים מקומיים")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("t2v", help="טקסט → וידאו")
    p.add_argument("prompt")
    common_video_args(p)
    p.set_defaults(func=cmd_t2v)

    p = sub.add_parser("i2v", help="תמונה → וידאו")
    p.add_argument("image", help="נתיב מקומי או URL")
    p.add_argument("prompt")
    p.add_argument("--end-image", help="פריים סיום (למעברים)")
    common_video_args(p)
    p.set_defaults(func=cmd_i2v)

    p = sub.add_parser("ref", help="עד 12 רפרנסים → וידאו (הפיצ'ר של 2.0)")
    p.add_argument("prompt", help='השתמש ב-@Image1 / @Video1 / @Audio1 בתוך הפרומפט')
    p.add_argument("-i", "--image", action="append", default=[], help="עד 9")
    p.add_argument("-v", "--video", action="append", default=[], help="עד 3")
    p.add_argument("-a", "--audio", action="append", default=[], help="עד 3")
    common_video_args(p)
    p.set_defaults(func=cmd_ref)

    p = sub.add_parser("cost", help="כמה זה יעלה — בלי לשלם")
    p.add_argument("--dur", default="5")
    p.add_argument("--ar", default="auto", choices=["auto", *ASPECTS])
    p.set_defaults(func=cmd_cost)

    p = sub.add_parser("spend", help="כמה הוצאתי")
    p.add_argument("-n", type=int, default=15)
    p.set_defaults(func=cmd_spend)

    p = sub.add_parser("get", help="לשחזר job לפי request_id")
    p.add_argument("request_id")
    p.add_argument("--endpoint", default="bytedance/seedance-2.0/text-to-video")
    p.add_argument("--open", action="store_true")
    p.set_defaults(func=cmd_get)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nהופסק. אם ה-job כבר נשלח הוא ממשיך לרוץ — שחזר עם  ./seedance.py get <request_id>")
        sys.exit(130)
