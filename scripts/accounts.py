"""Account Watch: polite public monitoring of account websites + Google News RSS.
Fetch rules: small thread pool, per-request timeout, identifying User-Agent, Google News requests serialized with a delay."""
import re, html, time, hashlib, threading, subprocess, urllib.parse, datetime as dt, xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
CATS=[("Merger",r"\bmerg(e|er|es|ed|ing)\b|\bcombin(e|es|ed) with\b|\bjoins forces\b|\bacquired by\b|\bpartnership with\b"),
 ("Acquisition",r"\bacquir|\bacquisition|\bpurchas|\bbuys?\b|\bbought\b|\bsells?\b|\bsold\b|\bsale of\b|\bdisposition|\bdivest|\bclos(es|ed) on\b|\brecapitaliz"),
 ("Hire/Leadership",r"\bhires?\b|\bhired\b|\bappoint|\bnames?\b.*\b(ceo|president|director|vp|vice president|chief|principal|partner|officer)|\bpromot|\bjoins\b|\bnew (ceo|president|cfo|coo)\b|\bsteps down\b|\bretire|\bsuccessor|\bexecutive\b|\bleadership\b"),
 ("Development",r"\bdevelop|\bgroundbreaking|\bbreaks? ground|\bconstruction|\bproposed|\bplans? for\b|\bapprov|\brezon|\bunits?\b|\bopens?\b|\bgrand opening|\bredevelop|\bproject\b|\bmixed-use|\bphase\b|\bzoning")]
def classify(t):
    for c,r in CATS:
        if re.search(r,t,re.I): return c
    return "Other"
def clean(s): return re.sub(r"\s+"," ",html.unescape(re.sub(r"<[^>]+>"," ",s or ""))).strip()
NEWSWORD=re.compile(r"news|press|blog|media|announcement|insights|updates|stories",re.I)
GENERIC={"companies","company","management","properties","property","group","realty","inc","llc","corp","corporation","development","developers","co","associates","partners","real","estate","enterprises","holdings","&","and","the","of","organization","services","mgmt","inc.","llc,"}
def match_term(a):
    """Distinctive phrase a Google News headline must contain (override with "match" in config)."""
    if a.get("match"): return a["match"]
    import re as _r
    n=_r.sub(r"\s*\(.*?\)","",a["name"]); n=_r.sub(r",?\s+(LLC|Llc|Inc\.?|Corp\.?)$","",n).strip()
    w=n.split(); core=list(w)
    while len(core)>1 and core[-1].lower().strip(",.") in GENERIC: core.pop()
    c=" ".join(core)
    return n if (len(c)<6 or c.lower() in ("empire","tower","pine","metro","summit","genesis","prospect","sentinel","midland","dominion","frontier","epoch","bayview","eastwood","neighborhood","triumph","whitmore","carlyle","symphony","capital investment advisors","first priority","first equity","university apartments","real ny")) else c
SPAM=re.compile(r"casino|gambling|no deposit|free spins|bingo|hacked by|viagra|payday loan",re.I)
def title_ok(a,t): return match_term(a).lower().replace("’","'") in t.lower().replace("’","'")
def cfg_hash(cfg):
    import json as _j
    return hashlib.sha1(_j.dumps([cfg["accounts"],cfg["account_watch"]],sort_keys=True).encode()).hexdigest()[:12]
def summarize(companies):
    return {"companies":len(companies),"with_items":sum(bool(c["items"]) for c in companies),"items":sum(len(c["items"]) for c in companies),"reachable":sum(c["status"]=="reachable" for c in companies),"no_news_page":sum(c["status"]=="no news page" for c in companies),"unreachable":sum(c["status"]=="unreachable" for c in companies),"no_url":sum(c["status"]=="no url" for c in companies)}
def run(cfg, prev, log):
    W=cfg["account_watch"]; UA=W["user_agent"]; TO=str(W["timeout_s"])
    gn_lock=threading.Lock(); host_lock={}
    def get(url, gn=False):
        t=time.time(); ok=False; n=0; final=url
        try:
            if gn:
                gn_lock.acquire(); time.sleep(1.2)
            r=subprocess.run(["curl","--http1.1","-sSL","-m",TO,"--max-filesize","3000000","-A",UA,"-w","\n%{http_code} %{url_effective}",url],capture_output=True,timeout=int(TO)+10)
            body,_,tail=r.stdout.rpartition(b"\n"); code,_,final=tail.decode().partition(" ")
            if r.returncode==0 and code.startswith("2"):
                n=len(body); ok=True; return body.decode("utf-8","replace"), final
            return None, final
        except Exception: return None, final
        finally:
            if gn: gn_lock.release()
            log.append({"url":url[:200],"ok":ok,"bytes":n,"ms":int((time.time()-t)*1000),"part":"accounts"})
    def parse_rss(x):
        out=[]
        try: root=ET.fromstring(x.encode())
        except Exception: return None
        its=list(root.iter("item")) or list(root.iter("{http://www.w3.org/2005/Atom}entry"))
        for it in its:
            t=clean(it.findtext("title") or it.findtext("{http://www.w3.org/2005/Atom}title"))
            l=(it.findtext("link") or "").strip()
            if not l:
                le=it.find("{http://www.w3.org/2005/Atom}link"); l=le.get("href","") if le is not None else ""
            d=(it.findtext("pubDate") or it.findtext("{http://www.w3.org/2005/Atom}updated") or "").strip()
            iso=""
            for f,s in (("%a, %d %b %Y %H:%M:%S",d[:25]),("%Y-%m-%dT%H:%M:%S",d[:19])):
                try: iso=dt.datetime.strptime(s,f).isoformat(); break
                except Exception: pass
            s=it.find("source"); src=s.text if s is not None and s.text else ""
            if t: out.append({"title":t,"link":l,"date":iso,"source":src})
        return out
    def site(a):
        st={"name":a["name"],"url":a["url"],"status":"no url","news_page":None,"feed":None,"home_hash":None,"error":None}
        items=[]
        if not a["url"]: return st,items
        x,final=get(a["url"])
        if x is None and a["url"].startswith("http://"):
            x,final=get("https://"+a["url"][7:])
        if x is None: st["status"]="unreachable"; return st,items
        st["final_url"]=final
        txt=clean(re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>"," ",x))
        st["home_hash"]=hashlib.sha1(txt.encode()).hexdigest()[:12]
        base=final
        feed=None
        m=re.search(r'<link[^>]+type=["\']application/(rss|atom)\+xml["\'][^>]*>',x,re.I)
        if m:
            h=re.search(r'href=["\']([^"\']+)',m.group(0))
            if h and not re.search(r"comments",h.group(1),re.I): feed=urllib.parse.urljoin(base,h.group(1))
        cand=[]
        host=urllib.parse.urlparse(base).netloc
        for hm in re.finditer(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>',x,re.I|re.S):
            u=urllib.parse.urljoin(base,hm.group(1)); lab=clean(hm.group(2))
            if urllib.parse.urlparse(u).netloc!=host: continue
            path=urllib.parse.urlparse(u).path
            if NEWSWORD.search(path.split("/")[1] if path.count("/")>=1 else "") or (len(lab)<25 and NEWSWORD.search(lab) and not re.search(r"newsletter",lab,re.I)):
                if u.rstrip("/")!=base.rstrip("/") and u not in cand and not re.search(r"\.(pdf|jpg|png)$",u,re.I): cand.append(u)
        if feed:
            fx,_=get(feed); its=parse_rss(fx) if fx else None
            if its is not None:
                st["feed"]=feed
                for i in its[:15]: items.append(dict(i,source=a["name"]+" (site feed)"))
        if cand:
            np=sorted(cand,key=lambda u:len(urllib.parse.urlparse(u).path))[0]
            st["news_page"]=np
            if not st["feed"]:
                nx,nfinal=get(np)
                if nx:
                    npath=urllib.parse.urlparse(nfinal).path.rstrip("/")
                    seen=set()
                    for hm in re.finditer(r'<a\b[^>]*href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>',nx,re.I|re.S):
                        u=urllib.parse.urljoin(nfinal,hm.group(1)); lab=clean(hm.group(2)); p=urllib.parse.urlparse(u)
                        if p.netloc!=urllib.parse.urlparse(nfinal).netloc or len(lab)<25 or len(lab)>200: continue
                        # article-like: deeper than the news page, under it, or under a news-ish path segment
                        if not ((npath and p.path.startswith(npath+"/") and len(p.path)>len(npath)+3) or re.search(r"/(news|press|blog|post|article)s?[-/][^/]{6,}",p.path,re.I)): continue
                        if re.search(r"read more|learn more|^page \d|older posts|next",lab,re.I) or u in seen: continue
                        seen.add(u); items.append({"title":lab,"link":u,"date":"","source":a["name"]+" (site news page)"})
                        if len(seen)>=15: break
                else: st["news_page_error"]=True
        st["status"]="reachable" if (st["feed"] or st["news_page"]) else "no news page"
        return st,items
    def gnews(a):
        q=a["news_query"]+" "+W["gn_window"]
        url="https://news.google.com/rss/search?"+urllib.parse.urlencode({"q":q,"hl":"en-US","gl":"US","ceid":"US:en"})
        x,_=get(url,gn=True); its=parse_rss(x) if x else None
        return url,[i for i in (its or []) if title_ok(a,i["title"])][:10],its is not None
    accs=cfg["accounts"]
    with ThreadPoolExecutor(W["max_concurrency"]) as ex:
        sres=list(ex.map(site,accs))
        gres=list(ex.map(gnews,accs))
    pv={c["name"]:c for c in (prev or {}).get("companies",[])}
    first=not pv
    cutoff=(dt.datetime.utcnow()-dt.timedelta(days=W["recent_days"])).isoformat()
    companies=[]; total=0
    for a,(st,sitems),(gurl,gitems,gok) in zip(accs,sres,gres):
        p=pv.get(a["name"],{}); seen=set(p.get("seen",[]))
        st["google_news"]={"url":gurl,"ok":gok}
        st["home_changed"]=bool(p.get("home_hash") and st["home_hash"] and p["home_hash"]!=st["home_hash"])
        items=[]; keys=set()
        spam=[i for i in sitems if SPAM.search(i["title"])]
        if spam: st["site_flag"]=f"{len(spam)} spam/defacement-looking entries on the site's own feed or news page were hidden (site may be compromised)"
        sitems=[i for i in sitems if not SPAM.search(i["title"])]
        for i in sitems+[dict(g,source=(g["source"] or "Google News")) for g in gitems]:
            if i["date"] and i["date"]<cutoff: continue
            k=hashlib.sha1((i["link"] or i["title"]).encode()).hexdigest()[:12]
            tk=i["title"].lower()[:60]
            if k in keys or any(tk==x["title"].lower()[:60] for x in items): continue
            keys.add(k)
            items.append(dict(i,category=classify(i["title"]),new=(not first and bool(p)) and k not in seen,key=k))
        items.sort(key=lambda i:i["date"],reverse=True)
        st["items"]=items; st["seen"]=sorted(seen|keys)[-300:]
        total+=len(items); companies.append(st)
    import json as _j
    return {"config_hash":cfg_hash(cfg),"generated":dt.datetime.now(dt.timezone.utc).isoformat(),"companies":companies,
            "summary":summarize(companies)}
