#!/usr/bin/env python3
"""Builds data.json from free public sources. No API keys. Logs to usage/usage.jsonl."""
import json, re, html, time, csv, io, datetime as dt, urllib.request, xml.etree.ElementTree as ET, os
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG=json.load(open(f"{ROOT}/config.json"))
LOG=[]
import subprocess
def get(url):
    t=time.time(); ok=False; n=0
    try:
        b=subprocess.run(["curl","--http1.1","-sSfL","-m","20","-A","Mozilla/5.0 (mf-dashboard; public RSS/CSV reader)",url],capture_output=True,timeout=60,check=True).stdout
        n=len(b); ok=True; return b.decode("utf-8","replace")
    except Exception:
        return None
    finally:
        LOG.append({"url":url[:200],"ok":ok,"bytes":n,"ms":int((time.time()-t)*1000)})
def clean(s): return html.unescape(re.sub(r"<[^>]+>","",s or "")).strip()
def rss(url,src):
    x=get(url); out=[]
    if not x: return out
    try: root=ET.fromstring(x.encode())
    except Exception: return out
    for it in root.iter("item"):
        t=clean(it.findtext("title")); l=(it.findtext("link") or "").strip(); d=it.findtext("pubDate") or ""
        s=it.find("source"); pub=s.text if s is not None and s.text else src
        try: iso=dt.datetime.strptime(d.strip()[:25],"%a, %d %b %Y %H:%M:%S").isoformat()
        except Exception: iso=""
        out.append({"title":t,"link":l,"date":iso,"source":pub,"desc":clean(it.findtext("description"))[:300]})
    return out
def dedupe(items):
    seen=set(); r=[]
    for i in sorted(items,key=lambda i:i["date"],reverse=True):
        k=i["title"].lower()[:70]
        if k not in seen: seen.add(k); r.append(i)
    return r
D={"generated":dt.datetime.now(dt.timezone.utc).isoformat()}
nat=[i for f in CFG["national_feeds"] for i in rss(f["url"],f["name"])]
D["news_national"]=dedupe(nat)[:40]
kw=[k.lower() for k in CFG["local_keywords"]]
loc=[i for i in nat if any(k in (i["title"]+" "+i["desc"]).lower() for k in kw)]
loc+=[i for f in CFG["local_feeds"] for i in rss(f["url"],f["name"]) if any(k in i["title"].lower() for k in kw) and re.search(r"apartment|multifamily|multi-family|rent|housing|landlord|tenant|lease|residential|development",i["title"],re.I)]
D["news_local"]=dedupe(loc)[:40]
D["competitors"]={c["name"]:dedupe([dict(i,source=i["source"]) for u in c["feeds"] for i in rss(u,c["name"])])[:20] for c in CFG["competitors"]}
# market numbers
M=[]
try: PREV=json.load(open(f"{ROOT}/data.json"))
except Exception: PREV={}
def fred(sid,label,area,unit):
    x=get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}")
    if not x or "html" in x[:100].lower():
        old=[m for m in PREV.get("market",[]) if m.get("source")==f"FRED {sid}"]
        if old: M.append(dict(old[0],cached=True))
        return
    rows=[r for r in csv.reader(io.StringIO(x))][1:]; rows=[r for r in rows if r[1] not in ("",".")]
    if rows: M.append({"area":area,"metric":label,"value":round(float(rows[-1][1]),1),"unit":unit,"period":rows[-1][0],"source":f"FRED {sid}","url":f"https://fred.stlouisfed.org/series/{sid}"})
for st,nm in [("MD","Maryland"),("DC","Washington DC"),("NY","New York State")]:
    fred(f"{st}RVAC","Rental vacancy rate",nm,"%")
    fred(f"{st}BPPRIVSA","New private housing units permitted (monthly, SA)",nm,"units")
z=get("https://files.zillowstatic.com/research/public_csvs/zori/Metro_zori_uc_sfrcondomfr_sm_month.csv")
if z:
    rd=list(csv.reader(io.StringIO(z))); h=rd[0]
    for r in rd[1:]:
        if r[2] in ("Baltimore, MD","Washington, DC","Rochester, NY","Buffalo, NY"):
            v=[(h[j],r[j]) for j in range(5,len(h)) if r[j]]
            p,val=v[-1]; yo=v[-13][1] if len(v)>13 else None
            M.append({"area":r[2]+" metro","metric":"Zillow Observed Rent Index (typical rent)","value":round(float(val)),"unit":"$/mo","yoy":round((float(val)/float(yo)-1)*100,1) if yo else None,"period":p,"source":"Zillow Research ZORI","url":"https://www.zillow.com/research/data/"})
D["market"]=M
# events
E=[]; today=dt.date.today()
for ev in CFG["events"]:
    x=get(ev["url"]); base=re.match(r"https://[^/]+",ev["url"]).group(0)
    if not x: continue
    if ev["parser"]=="date-stub":
        for m in re.finditer(r'title="Starts (\w+ \d+, \d{4})[^"]*".*?href="([^"]+)"[^>]*data-aria-label="Event Details for ([^"]+)"',x,re.S):
            d=dt.datetime.strptime(m.group(1),"%B %d, %Y").date()
            if d>=today: E.append({"org":ev["org"],"date":d.isoformat(),"title":html.unescape(m.group(3)),"link":base+m.group(2) if m.group(2).startswith("/") else m.group(2)})
    else:
        t=re.sub(r"<script.*?</script>|<style.*?</style>","",x,flags=re.S); L=[l.strip() for l in html.unescape(re.sub(r"<[^>]+>","\n",t)).split("\n") if l.strip()]
        for i,l in enumerate(L):
            m=re.fullmatch(r"(January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}",l)
            if m and i+1<len(L):
                d=dt.datetime.strptime(l,"%B %d, %Y").date()
                if d>=today: E.append({"org":ev["org"],"date":d.isoformat(),"title":L[i+1],"link":ev["url"]})
seen=set(); D["events"]=[e for e in sorted(E,key=lambda e:e["date"]) if not ((e["org"],e["title"],e["date"]) in seen or seen.add((e["org"],e["title"],e["date"])))][:40]
D["events_unparsed"]=CFG["event_links_unparsed"]; D["social"]=CFG["social"]
json.dump(D,open(f"{ROOT}/data.json","w"),indent=1)
os.makedirs(f"{ROOT}/usage",exist_ok=True)
with open(f"{ROOT}/usage/usage.jsonl","a") as f:
    f.write(json.dumps({"run":D["generated"],"runner":os.environ.get("GITHUB_ACTIONS") and "github-actions" or "local","fetches":len(LOG),"failed":sum(not l["ok"] for l in LOG),"bytes":sum(l["bytes"] for l in LOG),"paid_api_calls":0,"tokens_used":0,"cost_usd":0,"counts":{"national":len(D["news_national"]),"local":len(D["news_local"]),"market":len(M),"events":len(D["events"])},"detail":LOG})+"\n")
print(json.dumps({k:(len(v) if isinstance(v,list) else "") for k,v in D.items()}))
