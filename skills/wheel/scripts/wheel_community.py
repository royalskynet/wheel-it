#!/usr/bin/env python3
"""wheel community -- the community axis of `skills/wheel/SKILL.md` §3, run as one command.

Why a script and not the bare `gh search` / `curl` lines the skill used to list.
Prose asked for "at least two community sources" and nothing checked it: a card
could say 社群共識 without one query having left the machine. So the fan-out runs
here, and every run appends a receipt to the ledger that `wheel_registry.py add`
reads. The card's community line is then backed by a record, not by recollection.

Each source reports an outcome, not only a count. `no-results` means the source
answered and had nothing; `rate-limited` / `blocked` / `unreachable` / `skipped` mean it never
answered. Only the first two say anything about the community, so they are kept
apart: "nothing on Reddit" is a claim this script will not make for a 403.

Sources: GitHub issues, PRs and Discussions (through `gh` when logged in, the
public search API otherwise), Hacker News (Algolia), Stack Overflow, Reddit.
Queries leave this machine, so home paths, the login name, e-mail addresses and
long hex strings are stripped from them first.

Standalone: standard library only. Storage is `$WHEEL_LEDGER`, else
`~/.wheel/ledger.jsonl`, one JSON object per line.
"""
import concurrent.futures
import datetime
import getpass
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_LEDGER = os.path.join(os.path.expanduser("~"), ".wheel", "ledger.jsonl")
# Per request. The slowest source sets the wall time of a run, so this is the
# speed budget of `/wheel fix`: a source that has not answered by now is reported
# as unreachable rather than waited for.
TIMEOUT = 8
UA = "wheel-community/1 (prior-art search)"
# Outcomes where the source really answered. Everything else is "did not answer".
ANSWERED = ("ok", "no-results")
MAX_QUERIES = 4

USAGE = """wheel_community -- 社群軸一次查完並留收據（skills/wheel/SKILL.md §3）
  wheel_community.py [--repo owner/name] [--limit N] "<錯誤原文或問題>" ["<通用說法>" "<英文說法>" ...]
    最多 %d 組說法；每組各查 GitHub issues／PRs／Discussions、Hacker News、Stack Overflow、Reddit
    --repo   只查這個 repo 的 issues／PRs（已確認元件歸屬的上游）
    --limit  每個來源最多列幾筆（預設 5）
  每個來源印結果與狀態：ok／no-results＝有回應；rate-limited／blocked／unreachable／skipped＝沒回應，不能當成「社群沒人提」
收據寫入: %s（環境變數 WHEEL_LEDGER 可改）
"""


def ledger_path():
    return os.environ.get("WHEEL_LEDGER") or DEFAULT_LEDGER


def scrub(text):
    """Remove what identifies this machine or its owner before a query leaves it."""
    home = os.path.expanduser("~")
    for needle in {home, home.replace("\\", "/"), home.replace("\\", "\\\\")}:
        if needle and len(needle) > 3:
            text = text.replace(needle, "~")
    try:
        user = getpass.getuser()
    except Exception:
        user = ""
    if len(user) > 3:
        text = re.sub(re.escape(user), "user", text, flags=re.I)
    text = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "<email>", text)
    text = re.sub(r"\b(?:0x)?[0-9a-fA-F]{32,}\b", "<hex>", text)
    return text.strip()


def http_json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json", "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip" or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8", "replace"))


def outcome_of(exc):
    """Name why a source did not answer. Never 'no-results': that is an answer."""
    if isinstance(exc, urllib.error.HTTPError):
        # 429 says so itself. 403 only says "refused": the cause is not ours to guess.
        return {429: "rate-limited", 403: "blocked"}.get(exc.code, "error-http-%d" % exc.code)
    if isinstance(exc, (urllib.error.URLError, TimeoutError, OSError)):
        return "unreachable"
    return "error"


def item(title, url, votes=None, comments=None, date="", state=""):
    return {"title": " ".join((title or "").split())[:110], "url": url or "",
            "votes": votes, "comments": comments, "date": (date or "")[:10], "state": state or ""}


_GH = None


def gh_ready():
    """`gh` installed and logged in. Checked once: a missing login makes every
    `gh search` fail the same way, and that is one fact, not twelve."""
    global _GH
    if _GH is None:
        _GH = False
        if shutil.which("gh"):
            try:
                _GH = subprocess.run(["gh", "auth", "status"], capture_output=True,
                                     timeout=TIMEOUT).returncode == 0
            except (OSError, subprocess.SubprocessError):
                _GH = False
    return _GH


def gh_json(args):
    p = subprocess.run(["gh"] + args, capture_output=True, timeout=TIMEOUT * 2)
    if p.returncode != 0:
        err = p.stderr.decode("utf-8", "replace").lower()
        raise RuntimeError("rate-limited" if "rate limit" in err else "error-gh")
    return json.loads(p.stdout.decode("utf-8", "replace") or "null")


def parse_gh_search(rows):
    return [item(r.get("title"), r.get("url"), comments=r.get("commentsCount"),
                 date=r.get("updatedAt"), state=r.get("state")) for r in rows or []]


def parse_gh_api(data):
    return [item(r.get("title"), r.get("html_url"), comments=r.get("comments"),
                 date=r.get("updated_at"), state=r.get("state")) for r in data.get("items", [])]


def parse_gh_discussions(data):
    nodes = (((data or {}).get("data") or {}).get("search") or {}).get("nodes") or []
    return [item(n.get("title"), n.get("url"), votes=n.get("upvoteCount"),
                 comments=(n.get("comments") or {}).get("totalCount"),
                 date=n.get("updatedAt"), state="answered" if n.get("isAnswered") else "")
            for n in nodes if n]


def parse_hn(data):
    out = []
    for h in data.get("hits", []):
        url = "https://news.ycombinator.com/item?id=%s" % h.get("objectID")
        out.append(item(h.get("title") or h.get("story_title"), url, votes=h.get("points"),
                        comments=h.get("num_comments"), date=h.get("created_at")))
    return out


def parse_so(data):
    out = []
    for q in data.get("items", []):
        date = ""
        if q.get("creation_date"):
            date = datetime.datetime.fromtimestamp(
                q["creation_date"], datetime.timezone.utc).date().isoformat()
        out.append(item(q.get("title"), q.get("link"), votes=q.get("score"),
                        comments=q.get("answer_count"), date=date,
                        state="answered" if q.get("is_answered") else ""))
    return out


def parse_reddit(data):
    out = []
    for c in ((data or {}).get("data") or {}).get("children", []):
        d = c.get("data") or {}
        date = ""
        if d.get("created_utc"):
            date = datetime.datetime.fromtimestamp(
                d["created_utc"], datetime.timezone.utc).date().isoformat()
        out.append(item(d.get("title"), "https://www.reddit.com%s" % d.get("permalink", ""),
                        votes=d.get("score"), comments=d.get("num_comments"), date=date,
                        state="r/%s" % d.get("subreddit", "")))
    return out


def src_gh(kind, query, limit, repo):
    """kind: issues | prs."""
    if gh_ready():
        args = ["search", kind, query, "--limit", str(limit),
                "--json", "title,url,state,commentsCount,updatedAt"]
        if repo:
            args += ["--repo", repo]
        return parse_gh_search(gh_json(args))
    q = query + (" repo:%s" % repo if repo else "") + (" is:pr" if kind == "prs" else " is:issue")
    return parse_gh_api(http_json("https://api.github.com/search/issues?per_page=%d&q=%s"
                                  % (limit, urllib.parse.quote(q))))


def src_discussions(query, limit, repo):
    if not gh_ready():
        raise RuntimeError("skipped")  # GraphQL search needs a token
    gql = ("query($q:String!,$n:Int!){search(query:$q,type:DISCUSSION,first:$n){nodes{"
           "... on Discussion{title url upvoteCount isAnswered updatedAt comments{totalCount}}}}}")
    q = query + (" repo:%s" % repo if repo else "")
    return parse_gh_discussions(gh_json(
        ["api", "graphql", "-f", "query=" + gql, "-f", "q=" + q, "-F", "n=%d" % limit]))


def src_hn(query, limit, repo):
    return parse_hn(http_json("https://hn.algolia.com/api/v1/search?tags=story&hitsPerPage=%d&query=%s"
                              % (limit, urllib.parse.quote(query))))


def src_so(query, limit, repo):
    return parse_so(http_json(
        "https://api.stackexchange.com/2.3/search/advanced?site=stackoverflow&sort=votes"
        "&order=desc&pagesize=%d&q=%s" % (limit, urllib.parse.quote(query))))


def src_reddit(query, limit, repo):
    return parse_reddit(http_json("https://www.reddit.com/search.json?sort=relevance&limit=%d&q=%s"
                                  % (limit, urllib.parse.quote(query))))


SOURCES = (
    ("gh_issues", lambda q, n, r: src_gh("issues", q, n, r)),
    ("gh_prs", lambda q, n, r: src_gh("prs", q, n, r)),
    ("gh_discussions", src_discussions),
    ("hn", src_hn),
    ("stackoverflow", src_so),
    ("reddit", src_reddit),
)


def one(fn, query, limit, repo):
    try:
        return "ok", fn(query, limit, repo)
    except RuntimeError as e:  # outcomes raised by name
        return str(e), []
    except Exception as e:  # network, JSON, subprocess
        return outcome_of(e), []


def merge(results):
    """results: [(outcome, items)] for one source across queries -> (outcome, items).

    The source answered if any query got through. Items are de-duplicated by URL
    in query order, so the verbatim-error hits (first query) stay on top.
    """
    seen, items = set(), []
    for _, got in results:
        for it in got:
            if it["url"] and it["url"] not in seen:
                seen.add(it["url"])
                items.append(it)
    outcomes = [o for o, _ in results]
    if "ok" in outcomes:
        return ("ok" if items else "no-results"), items
    return outcomes[0] if outcomes else "error", items


def search(queries, limit=5, repo=None, sources=SOURCES):
    gh_ready()  # settle the login check once, before the threads race to ask
    jobs = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for name, fn in sources:
            jobs[name] = [pool.submit(one, fn, q, limit, repo) for q in queries]
        report = {}
        for name, _ in sources:
            outcome, items = merge([f.result() for f in jobs[name]])
            report[name] = {"outcome": outcome, "items": items[:limit]}
    return report


def write_receipt(queries, report, repo=None):
    path = ledger_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    entry = {
        "kind": "search",
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "queries": queries,
        "repo": repo,
        "sources": {n: {"outcome": r["outcome"], "n": len(r["items"])} for n, r in report.items()},
        "urls": [it["url"] for r in report.values() for it in r["items"][:2]],
    }
    with open(path, "a", encoding="utf-8", newline="") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def receipt_line(sources):
    return "｜".join("%s %s%s" % (n, s["outcome"], (" %d" % s["n"]) if s["n"] else "")
                    for n, s in sources.items())


def render(queries, report):
    out = ["查詢：" + " ｜ ".join(queries)]
    for name, r in report.items():
        out.append("## %s — %s%s" % (name, r["outcome"],
                                     " %d" % len(r["items"]) if r["items"] else ""))
        for it in r["items"]:
            meta = [m for m in (it["state"],
                                "▲%s" % it["votes"] if it["votes"] is not None else "",
                                "💬%s" % it["comments"] if it["comments"] is not None else "",
                                it["date"]) if m]
            out.append("- %s（%s）%s" % (it["title"], " ".join(meta), it["url"]))
    return "\n".join(out)


def main(argv):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args, repo, limit, queries = list(argv[1:]), None, 5, []
    while args:
        a = args.pop(0)
        if a in ("-h", "--help"):
            sys.stdout.write(USAGE % (MAX_QUERIES, ledger_path()))
            return 0
        if a == "--repo" and args:
            repo = args.pop(0)
        elif a == "--limit" and args and args[0].isdigit():
            limit = max(1, min(20, int(args.pop(0))))
        elif a.startswith("--"):
            sys.stderr.write("wheel_community: 不認得的選項 %s\n" % a)
            return 2
        else:
            queries.append(a)
    queries = [q for q in (scrub(q) for q in queries) if q][:MAX_QUERIES]
    if not queries:
        sys.stderr.write(USAGE % (MAX_QUERIES, ledger_path()))
        return 2
    report = search(queries, limit, repo)
    print(render(queries, report))
    entry = write_receipt(queries, report, repo)
    answered = [n for n, s in entry["sources"].items() if s["outcome"] in ANSWERED]
    print("\n收據：%s" % receipt_line(entry["sources"]))
    print("有回應的來源 %d 個（%s）。沒回應的來源不算「社群沒人提」，卡片「降級：」照寫。"
          % (len(answered), "、".join(answered) or "無"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
