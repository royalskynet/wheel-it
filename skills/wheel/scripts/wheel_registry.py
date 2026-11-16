#!/usr/bin/env python3
"""wheel registry — the store behind step 0 and the sign-off row of `skills/wheel/SKILL.md`.

Why a CLI and not the skill's bare `printf`. Step 0 is "look at what you already
decided before deciding again", and a hand-rolled writer is where a registry rots:

  * A verdict typed as `借鏡+自造` or `借鏡|自造` is not a verdict the skill can
    act on. SKILL.md says "不發明組合字串" and nothing enforces it.
  * One missing TAB shifts every later column, so `review_by` silently holds the
    wrong value and a live decision reads as expired — the failure mode this file
    exists to prevent is a stale card *looking* fresh, not a missing card.

So the grammar is enforced at the only moment it can be: the write. One verdict
word, or several joined by the full-width `｜` — `|` and `+` are exactly the
typos that need rejecting, so they are not accepted as separators. `check` covers
the rows that did not come through this CLI (hand-edited, pasted from a chat,
written by an older skill version): it names each broken line by number and never
rewrites it, because a card someone typed by hand is still their decision.

Storage is `$WHEEL_REGISTRY`, else `~/.wheel/registry.tsv`. Five TAB-separated
columns: date, verdict, problem, choice, review_by. `review_by` is why the file
carries an expiry at all — a card about model routing or a free quota is stale in
a month, and the three windows (30 / 90 / 180) are the skill's, not a guess.

Standalone: standard library only, no network, no import from the host harness.
`SKILL.md` calls it by absolute path when the folder is present and falls back to
`grep` / bare `printf` when it is not, so the two paths must agree on the format.

Cost: the contract is argv → exit code → stdout, so `test_wheel_registry.py`
drives this as a subprocess and never touches a real `~/.wheel/registry.tsv`.
"""
import datetime
import json
import os
import re
import sys

# skills/wheel/SKILL.md §5, lowest cost to highest. Kept in this order so the
# usage text reads as the ladder, not as an alphabet.
VERDICTS = ("不做", "換題", "設定", "採用", "改用", "借鏡", "自造")
# Full-width on purpose. Half-width `|` reads as a shell pipe and `+` as
# arithmetic, which is why both are common in hand-typed verdicts and neither is
# a verdict the skill can act on.
VERDICT_SEP = "｜"
COLUMNS = 5
# SKILL.md's review windows: fast-moving (AI/LLM/agent, model routing, free
# quotas) 30, ordinary packages and CLIs 90, OS mechanisms and mature frameworks
# 180. Three values, not a range: a card re-reviewed on a whim is a card nobody
# trusts.
DAY_CHOICES = ("30", "90", "180")
DATE_RE = re.compile(r"\A\d{4}-\d{2}-\d{2}\Z")
DEFAULT_PATH = os.path.expanduser("~/.wheel/registry.tsv")
DEFAULT_FORCE_PATH = os.path.expanduser("~/.wheel/force.json")
DEFAULT_LEDGER_PATH = os.path.expanduser("~/.wheel/ledger.jsonl")
# SKILL.md §3 社群軸. The registry's five columns record what was decided, not
# whether anyone looked: a card could claim 社群共識 with no query sent. So `add`
# asks the ledger that `wheel_community.py` writes. A receipt is good for this
# long -- one wheel run, not a standing licence -- and backs one card: the `add`
# that uses it records its timestamp, and a used receipt opens nothing further.
RECEIPT_MAX_AGE_MIN = 120
# A source that answered, with or without hits. `rate-limited` and the like are
# not answers and do not count toward "two sources".
ANSWERED = ("ok", "no-results")
MIN_ANSWERED = 2
# Verdicts reachable at SKILL.md §1, before any search: nothing to prove.
NO_SEARCH_VERDICTS = ("不做", "換題")
QUICK_FLAG = "--quick"
# SKILL.md §6.5: 自造的實作連續失敗兩次（Genie fail_streak 的既有計數器已經在
# context 跳出警告）才會走到這裡 -- force mode 不重算失敗次數，只記「要不要收窄
# 裁決」這一個新狀態，計數本身永遠留在 fail_streak.py，這裡不重造。
FORCE_SOURCES = ("manual", "auto")
# What a trip does: force = narrow verdicts for one decision; pause = stop and
# offer 收尾／換路／force. First entry is the default.
ON_FAIL2 = ("force", "pause")
# Force is one-shot: the next accepted `add` uses it up. A flag nobody used up
# (session ended first) stops counting after this many days, so it cannot stay
# on for good.
FORCE_TTL_DAYS = 1
FORCE_BANNED = "自造"
PAUSE_TEXT = (
    "wheel pause：{fp} 在 wheel 發動後連續失敗兩次，先停手，三選一：\n"
    "  1. 收尾：保留已成功的部分，未完成項寫成待辦回報\n"
    "  2. 換路：重跑 /wheel，換一個裁決（不重試同一修法）\n"
    "  3. 強制：/wheel f，之後只准用現成輪子膠水收尾，禁止自造"
)
FORCE_TEXT = (
    "wheel force mode ON（{source}：{reason}）：裁決只能是 不做／換題／設定／採用／改用／借鏡，"
    "禁止自造；只用社群現成輪子或做法膠水收尾。只管下一筆裁決，登記後自動解除；提早解除：/wheel off"
)

USAGE = """wheel_registry -- 輪子卡登記簿（skills/wheel/SKILL.md 第 0 步與收尾登記）
  find <kw> [kw...]                    找舊卡（不分大小寫、字面比對），最多印最後 5 筆
                                      每筆前綴 [有效] 或 [過期]；沒有命中印「無舊卡」
  add [--quick] <verdict> <problem> <choice> <30|90|180>
                                      登記一筆，review_by = 今天 + 天數
                                      要有 120 分鐘內的社群收據（先跑 wheel_community.py），一張收據只放行一張卡；
                                      Quick 深度加 --quick 豁免；裁決只有 不做／換題 也豁免
  audit                               統計登記時的查證狀況（searched／degraded／quick／no-search）
  check                               逐列檢查欄數／日期／verdict；全對印 ok <列數> rows
  force on <manual|auto> <reason>      開 force mode（§6.5）：下一筆裁決收窄為 不做／換題／設定／採用／改用／借鏡
                                      登記那一筆後自動解除；沒用掉的隔 1 天失效
  force off                            解除 force mode
  force status                         印 on/off 與失敗兩次時的行為（force 或 pause）
  force mode <force|pause>             設定失敗兩次時：直接強制，或暫停給三個選項
  force trip <fingerprint>             失敗兩次時呼叫（Genie fail_streak）；依 mode 開 force 或印 pause 選項
verdict: %s
        多個用全形 ｜ 串接，例如 設定｜不做
檔案: %s（環境變數 WHEEL_REGISTRY 可改）
force 檔: %s（環境變數 WHEEL_FORCE 可改）
收據檔: %s（環境變數 WHEEL_LEDGER 可改）
"""


def registry_path():
    """`$WHEEL_REGISTRY`, else `~/.wheel/registry.tsv`.

    An empty env var counts as unset: `WHEEL_REGISTRY=` must not silently write a
    row to a file named "".
    """
    return os.environ.get("WHEEL_REGISTRY") or DEFAULT_PATH


def force_path():
    """`$WHEEL_FORCE`, else `~/.wheel/force.json`. Same empty-means-unset rule as registry_path."""
    return os.environ.get("WHEEL_FORCE") or DEFAULT_FORCE_PATH


def ledger_path():
    """`$WHEEL_LEDGER`, else `~/.wheel/ledger.jsonl`. Same empty-means-unset rule."""
    return os.environ.get("WHEEL_LEDGER") or DEFAULT_LEDGER_PATH


def today():
    return datetime.date.today()


def read_ledger():
    """-> [dict], file order. A missing file or an unreadable line is skipped: the
    ledger is evidence, and a torn line is absent evidence, not a crash."""
    out = []
    try:
        with open(ledger_path(), encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    entry = json.loads(line)
                except ValueError:
                    continue
                if isinstance(entry, dict):
                    out.append(entry)
    except OSError:
        pass
    return out


def fresh_receipt():
    """The newest community-search receipt, if it is recent enough to belong to
    this run and no earlier card has used it. -> dict or None."""
    now = datetime.datetime.now(datetime.timezone.utc)
    ledger = read_ledger()
    used = {e.get("receipt") for e in ledger if e.get("kind") == "add"}
    for entry in reversed(ledger):
        if entry.get("kind") != "search":
            continue
        if entry.get("ts") in used:
            return None
        try:
            ts = datetime.datetime.fromisoformat(str(entry.get("ts")))
        except ValueError:
            return None
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=datetime.timezone.utc)
        age = (now - ts).total_seconds() / 60
        return entry if 0 <= age <= RECEIPT_MAX_AGE_MIN else None
    return None


def receipt_summary(entry):
    sources = entry.get("sources") if isinstance(entry.get("sources"), dict) else {}
    parts, answered = [], 0
    for name, info in sources.items():
        outcome = info.get("outcome") if isinstance(info, dict) else "?"
        answered += outcome in ANSWERED
        parts.append("%s %s" % (name, outcome))
    return answered, "｜".join(parts)


def log_add(mode, verdict, problem, detail="", receipt=None):
    """Record how this card was backed. Best effort: a ledger that cannot be
    written must not undo a card that was."""
    try:
        path = ledger_path()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8", newline="") as fh:
            fh.write(json.dumps({
                "kind": "add", "mode": mode, "verdict": verdict, "problem": problem,
                "detail": detail,
                "receipt": (receipt or {}).get("ts"),
                "queries": (receipt or {}).get("queries"),
                "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            }, ensure_ascii=False) + "\n")
    except OSError:
        pass


def parse_date(text):
    """`YYYY-MM-DD`, and a day that exists -- `2026-02-31` is a typo, not a date.

    Regex first so a 19-digit field cannot reach strptime's error text, which
    quotes the whole string and would put a stranger's bytes in our message.
    """
    if not DATE_RE.match(text or ""):
        return None
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def verdict_ok(verdict):
    """One verdict word, or several joined by `｜`. Nothing else.

    Splitting and comparing to the whole vocabulary is what rejects the near
    misses: `借鏡+自造` and `借鏡|自造` arrive as a single unrecognised token, and
    `設定｜` / `｜不做` leave an empty part that matches no word.
    """
    return bool(verdict) and all(part in VERDICTS for part in verdict.split(VERDICT_SEP))


def read_rows(path):
    """-> [(1-based line number, text without its newline)], in file order.

    A missing file is zero rows rather than an error: step 0 runs before the
    first `add`, and "you have no cards yet" is the normal first answer. Anything
    else (unreadable, is a directory) raises, so a broken path is reported as a
    failure rather than as an empty registry.
    """
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", errors="replace") as fh:
        return [(n, line.rstrip("\r\n")) for n, line in enumerate(fh, 1)]


def row_problems(text):
    """Every reason this row is unusable, in check order: columns, dates, verdict.

    A row with the wrong column count returns that alone -- the remaining fields
    are not the ones they look like, so reporting them would point at the wrong
    word.
    """
    fields = text.split("\t")
    if len(fields) != COLUMNS:
        return ["欄數 %d，應為 %d（date/verdict/problem/choice/review_by）"
                % (len(fields), COLUMNS)]
    out = []
    for label, value in (("date", fields[0]), ("review_by", fields[4])):
        if parse_date(value.strip()) is None:
            out.append("%s 不是 YYYY-MM-DD 的日期：%r" % (label, value))
    if not verdict_ok(fields[1]):
        out.append("verdict 不合法：%r（只能是 %s，或用全形 ｜ 串接數個）"
                   % (fields[1], " / ".join(VERDICTS)))
    return out


def _expired(text):
    """review_by < today. A row we cannot read a review_by out of counts as expired.

    `[有效]` promises "still live, cite this card and stop researching". A row with
    the wrong column count or an unparseable date cannot back that promise, so it
    is marked stale and re-checked here -- dropping it would let a whole broken
    registry answer "無舊卡", which is the one answer that is always safe to be
    wrong about. `check` is where such a row gets reported.
    """
    fields = text.split("\t")
    if len(fields) != COLUMNS:
        return True
    due = parse_date(fields[4].strip())
    return due is None or due < today()


def cmd_find(keywords):
    if not keywords:
        return usage("find 需要至少一個關鍵字")
    needles = [k.lower() for k in keywords]
    rows = read_rows(registry_path())
    hits = [text for _, text in rows if any(k in text.lower() for k in needles)]
    if not hits:
        print("無舊卡")
        return 0
    # Whole-line, case-insensitive, literal -- the same match as the `grep -iF`
    # the skill falls back to, so a card found by either command is the same card.
    # Last 5 only: step 0 answers "what did we already decide", and the newest row
    # is the one that supersedes the rest.
    for text in hits[-5:]:
        print(("[過期] " if _expired(text) else "[有效] ") + text)
    return 0


def cmd_add(args):
    quick = bool(args) and args[0] == QUICK_FLAG
    if quick:
        args = args[1:]
    if len(args) != 4:
        return usage("add 需要 4 個引數：[--quick] <verdict> <problem> <choice> <30|90|180>")
    verdict, problem, choice, days = args
    bad = []
    if not verdict_ok(verdict):
        bad.append("verdict 不合法：%r（只能是 %s，或用全形 ｜ 串接數個）"
                   % (verdict, " / ".join(VERDICTS)))
    if FORCE_BANNED in verdict.split(VERDICT_SEP) and force_on():
        bad.append("force mode 開著，裁決不得含「自造」；改選 採用／改用／借鏡，或 /wheel off 解除")
    if days not in DAY_CHOICES:
        bad.append("天數只能是 %s（依領域變化速度：快 30／中 90／慢 180），收到 %r"
                   % ("/".join(DAY_CHOICES), days))
    # A TAB or newline inside a field shifts every column after it, so the row
    # would still parse and still be wrong. Not something a caller can notice
    # afterwards, so it is refused here.
    for name, value in (("verdict", verdict), ("problem", problem), ("choice", choice)):
        if "\t" in value or "\n" in value or "\r" in value:
            bad.append("%s 欄位含 TAB 或換行，會把後面的欄位推歪" % name)
    # Community gate, last so a malformed card is reported for what is wrong with
    # it rather than for a missing receipt.
    mode, detail, receipt = "searched", "", None
    if not bad:
        if all(part in NO_SEARCH_VERDICTS for part in verdict.split(VERDICT_SEP)):
            mode = "no-search"
        elif quick:
            mode = "quick"
        else:
            receipt = fresh_receipt()
            if receipt is None:
                bad.append("沒有 %d 分鐘內、還沒被別張卡用掉的社群收據。先跑 wheel_community.py \"<錯誤原文或問題>\" "
                           "\"<通用說法>\" \"<英文說法>\" 再登記；Quick 深度（易回退小腳本、"
                           "版本號，且不是除錯題）改用 add %s" % (RECEIPT_MAX_AGE_MIN, QUICK_FLAG))
            else:
                answered, detail = receipt_summary(receipt)
                if answered < MIN_ANSWERED:
                    mode = "degraded"
    if bad:
        for line in bad:
            sys.stderr.write("wheel_registry: %s\n" % line)
        return 2
    path = registry_path()
    row = [today().isoformat(), verdict, problem, choice,
           (today() + datetime.timedelta(days=int(days))).isoformat()]
    try:
        append_row(path, row)
    except OSError as e:
        sys.stderr.write("wheel_registry: 寫不進 %s：%s\n" % (path, e))
        return 1
    log_add(mode, verdict, problem, detail, receipt)
    if mode == "searched":
        print("社群收據：%s" % detail)
    elif mode == "degraded":
        print("社群軸降級（有回應的來源不到 %d 個）：%s -- 卡片「降級：」照這行寫，"
              "不寫成社群共識" % (MIN_ANSWERED, detail or "無來源"))
    if force_on():
        data = load_force()
        data["on"] = False
        save_force(data)
        print("wheel force mode 已用掉這一次，自動解除")
    return 0


def cmd_audit(args):
    """How past cards were backed, so "did the community axis run" is a count
    and not a transcript dig."""
    if args:
        return usage("audit 不接受引數")
    adds = [e for e in read_ledger() if e.get("kind") == "add"]
    tally = {}
    for e in adds:
        tally[e.get("mode")] = tally.get(e.get("mode"), 0) + 1
    print("登記 %d 筆：%s" % (len(adds), "｜".join(
        "%s %d" % (m, tally.get(m, 0)) for m in ("searched", "degraded", "quick", "no-search"))))
    for e in adds[-5:]:
        print("%s\t%s\t%s\t%s" % (str(e.get("ts"))[:10], e.get("mode"), e.get("verdict"),
                                  e.get("problem")))
    return 0


def append_row(path, fields):
    """Append one row, creating the directory (step 0 runs before the first add)."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    row = "\t".join(fields)
    # A file whose last line lacks its newline (interrupted write, hand edit)
    # would swallow this row into the previous one. Close the line instead: a
    # half-written row then shows up in `check` instead of two decisions quietly
    # merging into one.
    if os.path.exists(path) and os.path.getsize(path) > 0:
        with open(path, "rb") as fh:
            fh.seek(-1, os.SEEK_END)
            if fh.read(1) != b"\n":
                row = "\n" + row
    with open(path, "a", encoding="utf-8", newline="") as fh:
        fh.write(row + "\n")


def cmd_check(args):
    if args:
        return usage("check 不接受引數")
    rows = read_rows(registry_path())
    # Violations go to stdout, not stderr: the caller asked for a report and
    # pipes it (`check > out`), so this is data. Exit 1 is the only thing telling
    # it apart from the ok line.
    reported, count = [], 0
    for lineno, text in rows:
        if not text.strip():
            continue  # a blank line is formatting, not a broken row
        count += 1
        reported += ["line %d: %s" % (lineno, why) for why in row_problems(text)]
    if reported:
        for line in reported:
            print(line)
        return 1
    print("ok %d rows" % count)
    return 0


def load_force():
    """-> dict. Missing or unreadable file is off with the default mode: a
    broken flag must not lock anyone out of 自造 forever."""
    try:
        with open(force_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def save_force(data):
    path = force_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.replace(tmp, path)


def force_on(data=None):
    """On, and switched on recently enough. A `since` we cannot read is off, for
    the same reason a broken file is."""
    data = load_force() if data is None else data
    since = parse_date(data.get("since") if isinstance(data.get("since"), str) else "")
    return (data.get("on") is True and since is not None
            and (today() - since).days <= FORCE_TTL_DAYS)


def mode_of(data):
    return data.get("on_fail2") if data.get("on_fail2") in ON_FAIL2 else ON_FAIL2[0]


def cmd_force(args):
    if not args:
        return usage("force 需要子指令：on / off / status / mode / trip")
    sub, rest = args[0], args[1:]
    data = load_force()
    if sub == "on":
        if len(rest) < 2 or rest[0] not in FORCE_SOURCES:
            return usage("force on <manual|auto> <reason>")
        data.update(on=True, source=rest[0], reason=" ".join(rest[1:]),
                    since=today().isoformat())
        save_force(data)
        print(FORCE_TEXT.format(source=data["source"], reason=data["reason"]))
        return 0
    if sub == "off" and not rest:
        data["on"] = False
        save_force(data)
        print("wheel force mode OFF")
        return 0
    if sub == "status" and not rest:
        if force_on(data):
            print("on（%s：%s，since %s）on_fail2=%s" % (
                data.get("source"), data.get("reason"), data.get("since"), mode_of(data)))
        else:
            print("off on_fail2=%s" % mode_of(data))
        return 0
    if sub == "mode" and len(rest) == 1 and rest[0] in ON_FAIL2:
        data["on_fail2"] = rest[0]
        save_force(data)
        print("on_fail2=%s" % rest[0])
        return 0
    if sub == "trip" and rest:
        fp = " ".join(rest)
        if force_on(data):
            print(FORCE_TEXT.format(source=data.get("source"), reason=data.get("reason")))
            return 0
        if mode_of(data) == "pause":
            print(PAUSE_TEXT.format(fp=fp))
            return 0
        return cmd_force(["on", "auto", "%s 在 wheel 發動後連續失敗兩次" % fp])
    return usage("force 子指令或引數不對：%s" % " ".join(args))


def usage(message=None):
    if message:
        sys.stderr.write("wheel_registry: %s\n" % message)
    sys.stderr.write(USAGE % (" / ".join(VERDICTS), registry_path(), force_path(), ledger_path()))
    return 2


def main(argv):
    # Cards are Chinese; a console code page (cp950 on Windows) turns `[有效]`
    # into bytes the reader cannot use.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = list(argv[1:])
    if not args:
        return usage()
    if args[0] in ("-h", "--help", "help"):
        sys.stdout.write(USAGE % (" / ".join(VERDICTS), registry_path(), force_path(), ledger_path()))
        return 0
    cmd, rest = args[0], args[1:]
    try:
        if cmd == "find":
            return cmd_find(rest)
        if cmd == "add":
            return cmd_add(rest)
        if cmd == "check":
            return cmd_check(rest)
        if cmd == "audit":
            return cmd_audit(rest)
        if cmd == "force":
            return cmd_force(rest)
    except OSError as e:
        sys.stderr.write("wheel_registry: %s：%s\n" % (registry_path(), e))
        return 1
    return usage("未知子指令：%s" % cmd)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
