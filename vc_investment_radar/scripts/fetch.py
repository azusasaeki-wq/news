import os, re, json, time, hashlib, datetime
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
import feedparser
import yaml

ROOT = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(ROOT, "data")
OUT_DIR = os.path.join(ROOT, "output")
CFG_PATH = os.path.join(ROOT, "config", "sources.yml")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(OUT_DIR, exist_ok=True)

def load_cfg():
    with open(CFG_PATH, "r") as f:
        return yaml.safe_load(f)

def load_db():
    p = os.path.join(DATA_DIR, "db.json")
    if os.path.exists(p):
        with open(p, "r") as f:
            return json.load(f)
    return {"seen": {}}

def save_db(db):
    p = os.path.join(DATA_DIR, "db.json")
    with open(p, "w") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

def norm_url(u):
    try:
        return requests.utils.requote_uri(u.strip())
    except Exception:
        return u.strip()

def make_id(url):
    return hashlib.sha1(url.encode("utf-8")).hexdigest()

def within_days(dt, days=180):
    try:
        if isinstance(dt, str):
            return True  # keep, later filtered by seen cache; RSS dates vary
        now = datetime.datetime.utcnow()
        return (now - dt).days <= days
    except Exception:
        return True

def fetch_rss(url):
    fp = feedparser.parse(url)
    items = []
    for e in fp.entries:
        link = norm_url(e.get("link") or e.get("id") or "")
        title = (e.get("title") or "").strip()
        if not link or not title:
            continue
        # Try to parse date
        dt = None
        for key in ("published_parsed","updated_parsed","created_parsed"):
            if e.get(key):
                dt = datetime.datetime.fromtimestamp(time.mktime(e.get(key)))
                break
        items.append({"title": title, "url": link, "source_url": url, "date": dt.isoformat() if dt else None})
    return items

def is_probably_nav(a_tag):
    txt = (a_tag.get_text() or "").strip().lower()
    nav_words = {"about","careers","jobs","contact","newsletter","subscribe","privacy","terms","press","team","portfolio","companies","submit","search"}
    if txt in nav_words:
        return True
    href = (a_tag.get("href") or "").lower()
    if any(x in href for x in ["#","/privacy","/terms","/careers","/jobs","/contact","/subscribe","/login","/signin","/search","mailto:","tel:"]):
        return True
    return False

def fetch_page_list(page_url, max_links=40):
    """Generic: get candidate article links from News/Press page"""
    resp = requests.get(page_url, timeout=20, headers={"User-Agent":"Mozilla/5.0 VC-Radar"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html5lib")
    base = "{uri.scheme}://{uri.netloc}".format(uri=urlparse(page_url))
    links = []
    # Prefer <article> then fall back to anchors in main
    articles = soup.find_all("article")
    if articles:
        for art in articles:
            a = art.find("a", href=True)
            if not a: 
                continue
            if is_probably_nav(a): 
                continue
            href = a["href"]
            url = href if href.startswith("http") else urljoin(base, href)
            title = (a.get_text() or "").strip()
            if title and url:
                links.append((title, url))
    else:
        main = soup.find("main") or soup.find("div", {"role":"main"}) or soup
        for a in main.find_all("a", href=True):
            if is_probably_nav(a): 
                continue
            title = (a.get_text() or "").strip()
            if len(title) < 6: 
                continue
            href = a["href"]
            if href.startswith("javascript:"): 
                continue
            url = href if href.startswith("http") else urljoin(base, href)
            # Heuristic: same host, and likely newsy path
            if urlparse(url).netloc != urlparse(base).netloc: 
                continue
            path = urlparse(url).path.lower()
            if any(seg in path for seg in ["/news","/press","/stories","/insights","/blog","/perspectives","/latest"]):
                links.append((title, url))
    # Dedupe by URL
    seen = set()
    out = []
    for title, url in links:
        if url in seen: 
            continue
        seen.add(url)
        out.append({"title": title, "url": url, "source_url": page_url, "date": None})
        if len(out) >= max_links:
            break
    return out

def keep_by_keywords(title, keywords):
    t = (title or "").lower()
    return any(k in t for k in keywords)

def post_to_slack(items):
    hook = os.getenv("SLACK_WEBHOOK_URL")
    if not hook or not items:
        return
    blocks = []
    blocks.append({"type":"section","text":{"type":"mrkdwn","text":f"*VC Investment Radar* found {len(items)} new items"}})
    for it in items[:15]:
        blocks.append({"type":"section","text":{"type":"mrkdwn","text":f"• <{it['url']}|{it['title']}> — _{it.get('firm','')}_"}})
        blocks.append({"type":"divider"})
    try:
        requests.post(hook, json={"blocks":blocks}, timeout=10)
    except Exception as e:
        print("Slack error:", e)

def main():
    cfg = load_cfg()
    db = load_db()
    include_kw = [k.lower() for k in cfg.get("filters",{}).get("include_title_any",[])]
    all_new = []
    for firm, spec in cfg.get("firms",{}).items():
        rss = spec.get("rss") or []
        pages = spec.get("pages") or []
        for r in rss:
            try:
                items = fetch_rss(r)
            except Exception as e:
                print(f"[RSS ERR] {firm} {r} {e}")
                items = []
            for it in items:
                it["firm"] = firm
                if include_kw and not keep_by_keywords(it["title"], include_kw):
                    continue
                uid = make_id(it["url"])
                if uid in db["seen"]:
                    continue
                db["seen"][uid] = {"title": it["title"], "first_seen": datetime.datetime.utcnow().isoformat()}
                all_new.append(it)
        for p in pages:
            try:
                items = fetch_page_list(p)
            except Exception as e:
                print(f"[PAGE ERR] {firm} {p} {e}")
                items = []
            for it in items:
                it["firm"] = firm
                if include_kw and not keep_by_keywords(it["title"], include_kw):
                    continue
                uid = make_id(it["url"])
                if uid in db["seen"]:
                    continue
                db["seen"][uid] = {"title": it["title"], "first_seen": datetime.datetime.utcnow().isoformat()}
                all_new.append(it)

    # Write outputs
    today = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    if all_new:
        # sort by firm then title
        all_new.sort(key=lambda x: (x.get("firm",""), x.get("title","").lower()))
        md_lines = [f"# VC Investment Radar — {today}\n"]
        cur = None
        for it in all_new:
            if it["firm"] != cur:
                md_lines.append(f"\n## {it['firm']}\n")
                cur = it["firm"]
            md_lines.append(f"- [{it['title']}]({it['url']})")
        with open(os.path.join(OUT_DIR, f"digest_{today}.md"), "w") as f:
            f.write("\n".join(md_lines))
    # latest.json (last 200 items)
    # Keep db small
    if len(db["seen"]) > 5000:
        # drop oldest half
        items_sorted = sorted(db["seen"].items(), key=lambda kv: kv[1].get("first_seen",""))
        db["seen"] = dict(items_sorted[len(items_sorted)//2:])

    latest = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "new_items": all_new[:200]
    }
    with open(os.path.join(OUT_DIR, "latest.json"), "w") as f:
        json.dump(latest, f, indent=2, ensure_ascii=False)

    save_db(db)
    post_to_slack(all_new)
    print(f"New items: {len(all_new)}")

if __name__ == "__main__":
    main()
