"""Local control center (stdlib only): switch models, see sessions/usage, deploy new models."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import foundry, state, usage
from .config import load_profiles

PORT = 4001
_cache: dict[str, tuple[float, object]] = {}
_deploying: dict[str, str] = {}  # deployment name -> "running" | error text


def _cached(key: str, ttl: int, fn):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    value = fn()
    _cache[key] = (time.time(), value)
    return value


def _deployments() -> list[dict]:
    rows = []
    for name, p in load_profiles().items():
        for d in foundry.list_deployments(p):
            m = d.properties.model
            rows.append(
                {
                    "profile": name,
                    "alias": f"{p.label}-{d.name}",
                    "deployment": d.name,
                    "model": f"{m.name} {m.version or ''}".strip(),
                    "format": m.format,
                    "sku": d.sku.name if d.sku else None,
                    "status": str(d.properties.provisioning_state),
                }
            )
    return rows


def _catalog(profile: str) -> list[dict]:
    return foundry.list_catalog(load_profiles()[profile])


def _deploy(profile: str, name: str, item: dict) -> None:
    from .cli import sync  # rebuild the gateway config after the deployment exists

    try:
        skus = item.get("skus") or []
        sku = "GlobalStandard" if "GlobalStandard" in skus or not skus else skus[0]
        foundry.deploy(
            load_profiles()[profile], name, item["name"], item["version"], item["format"], sku, 10
        )
        sync()
        _deploying[name] = "done"
    except Exception as e:  # surfaced in the UI
        _deploying[name] = f"error: {e}"
    _cache.clear()


PAGE = """<!doctype html><meta charset=utf-8><title>BYOM control center</title>
<style>
:root{--bg:#f6f7f9;--card:#fff;--ink:#1c2430;--mut:#6b7686;--acc:#0a7;--bd:#dde2e8}
@media(prefers-color-scheme:dark){:root{--bg:#14181d;--card:#1d232b;--ink:#e8edf2;--mut:#93a0b0;--bd:#2c3540}}
body{font:15px system-ui;background:var(--bg);color:var(--ink);margin:0;padding:1.5rem}
h1{margin:0 0 1rem}h2{font-size:1rem;margin:0 0 .6rem;color:var(--mut);text-transform:uppercase;
letter-spacing:.05em}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:1rem}
.card{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:1rem}
.kpis{display:flex;gap:1rem;flex-wrap:wrap;margin-bottom:1rem}.kpi{flex:1;min-width:130px}
.kpi b{display:block;font-size:1.6rem}.kpi span{color:var(--mut);font-size:.85rem}
table{width:100%;border-collapse:collapse}td,th{padding:.3rem .4rem;text-align:left;font-size:.9rem;
border-bottom:1px solid var(--bd)}th{color:var(--mut);font-weight:500}td.n{text-align:right}
button{font:inherit;cursor:pointer;border:1px solid var(--bd);border-radius:7px;padding:.25rem .6rem;
background:var(--card);color:var(--ink)}button.on{background:var(--acc);color:#fff;border-color:var(--acc)}
.dot{display:inline-block;width:.6rem;height:.6rem;border-radius:50%;background:#bbb;margin-right:.4rem}
.dot.live{background:var(--acc)}.mut{color:var(--mut)}select{font:inherit;padding:.3rem .5rem;border:1px solid var(--bd);border-radius:7px;background:var(--card);
color:var(--ink);max-width:100%}.id{font-family:ui-monospace,Consolas,monospace;font-size:.85rem}
td.nw{white-space:nowrap}tr.closed td{opacity:.55}.card{overflow-x:auto}
input[type=text],input:not([type]){font:inherit;padding:.3rem .5rem;border:1px solid var(--bd);border-radius:7px;
background:var(--card);color:var(--ink)}button:hover{border-color:var(--acc)}
</style>
<h1>Copilot BYOM</h1><div class=kpis id=kpis></div>
<div class=grid>
<div class=card><h2>Active model</h2><div id=models></div></div>
<div class=card><h2>Sessions</h2><div id=sessions></div></div>
<div class=card><h2>Usage per model</h2><div id=usage></div></div>
<div class=card><h2>Profiles (tenant prefix)</h2><div id=profiles></div></div>
<div class=card><h2>Deployed</h2><div id=deployed></div></div>
<div class=card style="grid-column:1/-1"><h2>Available to deploy</h2>
<div id=catalog class=mut>Loading catalog...</div></div>
<div class=card id=cli style="grid-column:1/-1;display:none"><h2>Deploy with the CLI</h2>
<pre id=clitext style="white-space:pre-wrap;margin:0 0 .6rem"></pre>
<button onclick="copyCli()">Copy</button> <span id=clinote class=mut></span></div></div>
<p class=mut>Costs are estimates from a local price table, not your Azure invoice.</p>
<script>
const $=id=>document.getElementById(id), fmt=n=>(n||0).toLocaleString();
const usd=n=>'$'+(n||0).toFixed(3);
let showClosed=false,profile=null,catalogLoaded=false;
async function j(u,o){return (await fetch(u,o)).json()}
async function useFor(sid,a){await fetch('/api/use',{method:'POST',body:sid+'|'+a});load()}
async function use(a){await fetch('/api/use',{method:'POST',body:a});load()}
async function deploy(p,item){
 const name=prompt('Deployment name',item.name.replace(/[^a-z0-9-]/gi,'-'));if(!name)return;
 if(!confirm('Deploy '+item.name+' ('+item.version+')?\\nThis can incur Azure costs per use.'))return;
 await fetch('/api/deploy',{method:'POST',body:JSON.stringify({profile:p,name,item})});load()}
async function savePrefix(name){
 const prefix=$('pf-'+name).value.trim();
 const r=await fetch('/api/profile',{method:'POST',body:JSON.stringify({name,prefix})});
 if(!r.ok)alert(await r.text());else{profilesLoaded=false;load()}}
async function loadProfiles(){
 const ps=await j('/api/profiles');
 $('profiles').innerHTML=ps.map(p=>'<div style="margin:.4rem 0"><b>'+p.name+'</b> <span class=mut>'+p.account+' / '+p.tenant.slice(0,8)+'</span><br>'+
  'Prefix <input id="pf-'+p.name+'" value="'+p.prefix+'" size=14> <button onclick="savePrefix(\\''+p.name+'\\')">Save</button></div>').join('')+
  '<div class=mut>Models appear as <i>prefix-model</i>. Saving rewrites the aliases.</div>'}
let profilesLoaded=false;
async function load(){
 if(document.activeElement&&document.activeElement.tagName=='SELECT')return;
 if(!profilesLoaded){profilesLoaded=true;loadProfiles()}
 const [o,u,d]=await Promise.all([j('/api'),j('/api/overview'),j('/api/deployments')]);
 $('kpis').innerHTML=[['Open sessions',u.sessions.filter(s=>s.open).length],
  ['Requests (24h)',fmt(u.requests_24h)],['Est. cost (24h)',usd(u.cost_24h)],
  ['Est. cost (total)',usd(u.cost_total)]].map(([k,v])=>'<div class="card kpi"><b>'+v+'</b><span>'+k+'</span></div>').join('');
 $('models').innerHTML=o.models.map(a=>'<div><button style="width:100%;text-align:left;margin:.2rem 0" class="'+(a==o.active?'on':'')+'" onclick="use(\\''+a+'\\')">'+(a==o.active?'\\u25cf ':'\\u25cb ')+a+'</button></div>').join('');
 const ss=u.sessions.filter(s=>showClosed||s.open),nc=u.sessions.length-u.sessions.filter(s=>s.open).length;
 $('sessions').innerHTML=(ss.length?'<table><tr><th></th><th>Id</th><th>Folder</th><th>Model</th><th>Req</th><th>Cost</th></tr>'+
  ss.map(s=>'<tr class="'+(s.open?'':'closed')+'"><td><span class="dot '+(s.open?'live':'')+'"></span></td><td class="id nw">'+s.id+'</td><td class="mut nw" title="'+s.cwd+'">'+(s.cwd||'').split(/[\\\\/]/).pop()+'</td><td>'+(s.open?'<select onchange="useFor(\\''+s.id+'\\',this.value)"><option value="">Global ('+o.active+')</option>'+o.models.map(m=>'<option'+(m==s.model?' selected':'')+'>'+m+'</option>').join('')+'</select>':'<span class=mut>'+(s.model||'')+'</span>')+'</td><td class=n>'+s.requests+'</td><td class=n>'+usd(s.cost)+'</td></tr>').join('')+'</table>':'<div class=mut>No open sessions. Start one with <code>byom copilot</code>.</div>')+
  (nc?'<div class=mut style="margin-top:.5rem"><label><input type=checkbox '+(showClosed?'checked ':'')+'onchange="showClosed=this.checked;load()"> show '+nc+' closed sessions</label></div>':'');
 $('usage').innerHTML='<table><tr><th>Model</th><th>Req</th><th>In</th><th>Out</th><th>Cost</th></tr>'+
  u.models.map(m=>'<tr><td>'+m.alias+'</td><td class=n>'+m.requests+'</td><td class=n>'+fmt(m.prompt_tokens)+'</td><td class=n>'+fmt(m.completion_tokens)+'</td><td class=n>'+usd(m.cost)+'</td></tr>').join('')+'</table>';
 $('deployed').innerHTML='<table><tr><th>Alias</th><th>Model</th><th>SKU</th><th>Status</th></tr>'+
  (d.deployments||[]).map(x=>'<tr><td>'+x.alias+'</td><td>'+x.model+'</td><td>'+(x.sku||'')+'</td><td>'+x.status+'</td></tr>').join('')+'</table>'+
  Object.entries(d.deploying||{}).map(([k,v])=>'<div class=mut>'+k+': '+v+'</div>').join('');
 const nowDeployed=new Set((d.deployments||[]).map(x=>x.model.split(' ')[0]));
 const changed=[...nowDeployed].join()!=[...catalogDeployed].join();
 catalogDeployed=nowDeployed;
 if(changed&&catalogLoaded)renderCatalog();
 if(!catalogLoaded&&d.deployments&&d.deployments.length){profile=d.deployments[0].profile;loadCatalog()}
 else if(d.error)$('deployed').innerHTML+='<div class=mut>Error: '+d.error+'</div>';
}
let CAT_ALL=[],catalogDeployed=new Set(),showAll=false;
async function loadCatalog(){
 try{const c=await j('/api/catalog?profile='+profile);
  if(c.error)throw new Error(c.error);
  CAT_ALL=c;catalogLoaded=true;renderCatalog()}
 catch(e){$('catalog').innerHTML='Catalog failed to load: '+e.message+' <button onclick="loadCatalog()">Retry</button>'}}
function renderCatalog(){
 CAT=CAT_ALL.filter(i=>!catalogDeployed.has(i.name)&&(showAll||i.compatible));
 const hidden=CAT_ALL.filter(i=>!catalogDeployed.has(i.name)&&!i.compatible).length;
 $('catalog').innerHTML='<div style="margin-bottom:.5rem">Showing models verified to work through the gateway (OpenAI chat models and Anthropic). '+
  '<label><input type=checkbox '+(showAll?'checked':'')+' onchange="showAll=this.checked;renderCatalog()"> also show '+hidden+' other-provider models (untested)</label></div>'+
  '<table><tr><th>Model</th><th>Provider</th><th>Version</th><th>SKUs</th><th></th></tr>'+
  CAT.map((i,n)=>'<tr><td>'+i.name+'</td><td>'+i.format+(i.compatible?'':' <span class=mut>(untested)</span>')+'</td><td>'+i.version+'</td><td class=mut>'+i.skus.join(', ')+'</td><td>'+
  (i.format=='OpenAI'&&i.compatible?'<button onclick="deploy(profile,CAT['+n+'])">Deploy</button> ':'')+
  '<button onclick="showCli('+n+')">CLI command</button></td></tr>').join('')+'</table>'}
function cliCmd(i){
 const slug=i.name.toLowerCase().replace(/[^a-z0-9-]/g,'-');
 let c='byom deploy '+profile+' '+slug+' --model '+i.name+' --version '+i.version+' --format '+i.format;
 if(i.skus.length&&!i.skus.includes('GlobalStandard'))c+=' --sku '+i.skus[0];
 if(i.format=='Anthropic')c+=' --org-name "<your org>" --industry <industry> --country <ISO code, e.g. BE>';
 return c+'\\nbyom sync   # then restart byom copilot so the gateway picks up the new model'}
function showCli(n){
 const i=CAT[n],c=cliCmd(i);
 $('cli').style.display='block';
 $('clitext').textContent=c;
 $('clinote').textContent=i.format=='Anthropic'?'Anthropic models need organization details and an Azure Marketplace-enabled subscription (a payment method on the subscription).':
  i.format=='OpenAI'?'You can also use the Deploy button.':'Non-OpenAI, non-Anthropic models are deployed here but are not verified to work through the gateway yet.';
 $('cli').scrollIntoView({behavior:'smooth'})}
function copyCli(){navigator.clipboard.writeText($('clitext').textContent)}
let CAT=[];
load();setInterval(load,4000);
</script>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: str, ctype: str = "application/json", code: int = 200):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        url = urlparse(self.path)
        try:
            if url.path == "/api":
                body = {"active": state.get_active(), "models": state.list_aliases()}
            elif url.path == "/api/overview":
                body = usage.overview()
                for s in body["sessions"]:
                    s["model"] = state.get_session_model(s["id"])
            elif url.path == "/api/deployments":
                body = {
                    "deployments": _cached("dep", 15, _deployments),
                    "deploying": _deploying,
                }
            elif url.path == "/api/profiles":
                body = [
                    {"name": n, "prefix": p.label, "tenant": p.tenant_id, "account": p.account}
                    for n, p in load_profiles().items()
                ]
            elif url.path == "/api/catalog":
                profile = parse_qs(url.query).get("profile", [""])[0]
                body = _cached("cat:" + profile, 600, lambda: _catalog(profile))
            else:
                return self._send(PAGE, "text/html")
            self._send(json.dumps(body))
        except Exception as e:
            self._send(json.dumps({"error": str(e)}), code=500)

    def do_POST(self):  # noqa: N802
        # Reject cross-site requests: only the page served from this origin may change anything.
        origin = self.headers.get("Origin")
        if origin and origin != f"http://127.0.0.1:{PORT}":
            return self._send("forbidden", "text/plain", 403)
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode()
        if self.path == "/api/use":
            try:
                state.set_active(raw)
            except ValueError as e:
                return self._send(str(e), "text/plain", 400)
            return self._send(json.dumps({"active": raw}))
        if self.path == "/api/profile":
            from .cli import profile_set

            req = json.loads(raw)
            try:
                profile_set(req["name"], req["prefix"], None)
            except (SystemExit, Exception) as e:
                return self._send(f"invalid prefix or profile ({e})", "text/plain", 400)
            _cache.clear()
            return self._send(json.dumps({"ok": True}))
        if self.path == "/api/deploy":
            req = json.loads(raw)
            profile, item = req["profile"], req["item"]
            profiles = load_profiles()
            if profile not in profiles or item.get("format") != "OpenAI":
                return self._send("unsupported", "text/plain", 400)
            # Alias = <prefix>-<deployment>; the user only names the deployment itself.
            name = req["name"].removeprefix(profiles[profile].label + "-")
            _deploying[name] = "running"
            threading.Thread(target=_deploy, args=(profile, name, item), daemon=True).start()
            return self._send(json.dumps({"started": name}), code=202)
        self._send("not found", "text/plain", 404)

    def log_message(self, *args):
        pass


def serve() -> None:
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
