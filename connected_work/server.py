"""Local-only demo server. Start with python3 -B -m connected_work.server."""
import argparse
import fcntl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import secrets
import threading
from urllib.parse import urlsplit, parse_qs

from .core import Store, decode, require
from .export import package
from .provider import Provider
from .showcase import PACKETS
from .review_context import context_for
from .review_trial import TrialStore

SITE=Path(__file__).parent/"site"


def serve(folder, port, reviewer="operator_ui", provider="nebius", control=None, trial_data="work/connected-review-v2-2026-10-30/participant-sessions"):
    backend=Provider(provider,control)
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    lease=(folder/"server.lock").open("a")
    fcntl.flock(lease,fcntl.LOCK_EX|fcntl.LOCK_NB)
    store=Store(folder);token=secrets.token_urlsafe(32)
    trial=TrialStore(trial_data)
    hosts={f"127.0.0.1:{port}",f"localhost:{port}"}
    origins={"http://"+host for host in hosts}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass

        def send(self,status,data,kind="application/json; charset=utf-8",extra=None):
            if not isinstance(data,bytes): data=json.dumps(data,ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type",kind)
            self.send_header("Content-Length",str(len(data)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Referrer-Policy","no-referrer")
            self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            for key,value in (extra or {}).items(): self.send_header(key,value)
            self.end_headers();self.wfile.write(data)

        def boundary(self):
            require(self.headers.get("Host") in hosts,"LOCAL_HOST_REQUIRED")
            require(self.headers.get("Origin") in (None,*origins),"CROSS_ORIGIN_BLOCKED")
            require(self.headers.get("Sec-Fetch-Site") not in ("cross-site",),"CROSS_ORIGIN_BLOCKED")

        def fail(self,exc):
            value=str(exc)
            code=value if re.fullmatch(r"[A-Z_]+",value) else "INVALID_REQUEST"
            self.send(409,{"error":code})

        def do_GET(self):
            try:
                self.boundary();parsed=urlsplit(self.path)
                if parsed.path=="/api/trial/bootstrap":
                    self.send(200,{"csrf":token,"study":"review_comparison_v2_2026_10_30","provider_calls":0});return
                if parsed.path in ("/api/trial/session","/api/trial/export"):
                    query=parse_qs(parsed.query,strict_parsing=True)
                    require(set(query)=={"session"} and len(query["session"])==1,"TRIAL_QUERY")
                    ident=query["session"][0]
                    if parsed.path.endswith("export"):
                        self.send(200,trial.export(ident),"application/zip",{"Content-Disposition":'attachment; filename="my-review-study.zip"'})
                    else:self.send(200,trial.get(ident))
                    return
                if parsed.path=="/api/state":
                    view=store.view()
                    for work in view["works"].values():
                        work["review_context"]=context_for(work)
                    self.send(200,view|backend.status()|{"csrf":token,"review_actor":reviewer});return
                if parsed.path=="/api/export":
                    query=parse_qs(parsed.query,strict_parsing=True)
                    require(set(query)=={"work","revision"} and all(len(v)==1 for v in query.values()),"EXPORT_QUERY")
                    ident=query["work"][0];revision=int(query["revision"][0])
                    data,_=package(store,ident,revision)
                    self.send(200,data,"application/zip",{"Content-Disposition":f'attachment; filename="connected-work-{ident}-r{revision}.zip"'});return
                mapping={"/":"index.html","/index.html":"index.html","/app.js":"app.js","/style.css":"style.css",
                         "/examples":"examples.html","/examples.html":"examples.html","/examples.js":"examples.js",
                         "/examples.css":"examples.css","/examples.json":"examples.json",
                         "/review.js":"review.js","/review.css":"review.css",
                         "/trial":"trial.html","/trial.html":"trial.html","/trial.js":"trial.js","/trial.css":"trial.css"}
                mapping.update({"/example-packets/"+name:"example-packets/"+name for name in PACKETS})
                require(parsed.path in mapping,"NOT_FOUND")
                path=SITE/mapping[parsed.path]
                self.send(200,path.read_bytes(),(mimetypes.guess_type(path.name)[0] or "text/plain")+"; charset=utf-8")
            except (ValueError,TypeError,KeyError,OSError) as exc: self.fail(exc)

        def do_POST(self):
            try:
                self.boundary()
                require(self.headers.get("Origin") in origins,"ORIGIN_REQUIRED")
                require(secrets.compare_digest(self.headers.get("X-Workspace-Token",""),token),"SESSION_TOKEN_REQUIRED")
                require(self.headers.get("Content-Type")=="application/json","JSON_REQUIRED")
                length=int(self.headers.get("Content-Length","0"))
                require(0<length<=50000,"REQUEST_SIZE")
                data=decode(self.rfile.read(length).decode("utf8"))
                require(isinstance(data,dict),"REQUEST_SHAPE")
                action=urlsplit(self.path).path
                if action=="/api/trial/create":
                    require(set(data)=={"actor","consent","exposure"},"REQUEST_SHAPE")
                    self.send(200,trial.create(data["actor"],data["consent"],data["exposure"]));return
                if action=="/api/trial/action":
                    require(set(data)=={"session","revision","action","payload"},"REQUEST_SHAPE")
                    self.send(200,trial.command(data["session"],data["revision"],data["action"],data["payload"]));return
                if action=="/api/preview":
                    require(set(data)=={"work","revision","facts"},"REQUEST_SHAPE")
                    with store.lock:
                        store.verify()
                        self.send(200,context_for(store.current(data["work"],data["revision"]),data["facts"]))
                    return
                shapes={"/api/generate":{"work","revision","facts","language"},"/api/edit":{"work","revision","job","bodies"},
                        "/api/accept":{"work","revision","job","reviewed"},"/api/discard":{"work","revision","job"},
                        "/api/undo":{"work","revision"}}
                require(action in shapes and set(data)==shapes[action],"REQUEST_SHAPE")
                args=(data["work"],data["revision"])
                if action=="/api/generate":
                    backend.preflight(store.folder)
                    job=store.begin(*args,data["facts"],data["language"],backend.name,backend.contract)
                    thread=threading.Thread(target=backend.run_job,args=(store,data["work"],job),daemon=True)
                    try: thread.start()
                    except Exception:
                        store.finish(data["work"],job["id"],error="WORKER_START_FAILED");raise
                elif action=="/api/edit": store.edit(*args,data["job"],data["bodies"])
                elif action=="/api/accept": store.accept(*args,data["job"],data["reviewed"],reviewer)
                elif action=="/api/discard": store.discard(*args,data["job"])
                else: store.undo(*args)
                self.send(200,{"ok":True})
            except (ValueError,TypeError,KeyError,OSError) as exc: self.fail(exc)

    server=ThreadingHTTPServer(("127.0.0.1",port),Handler)
    print(f"Connected work ready: http://127.0.0.1:{port}/ — {backend.name}; fictional workspaces only",flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close();lease.close()


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--port",type=int,default=8977)
    parser.add_argument("--data",default="work/connected-work-nebius-v1-2026-10-30/workspace")
    parser.add_argument("--provider",choices=("nebius","local"),default="nebius")
    parser.add_argument("--control",default="work/connected-work-nebius-v1-2026-10-30/control")
    parser.add_argument("--reviewer",choices=("operator_ui","assistant_qa"),default="operator_ui")
    parser.add_argument("--trial-data",default="work/connected-review-v2-2026-10-30/participant-sessions")
    args=parser.parse_args();serve(args.data,args.port,args.reviewer,args.provider,args.control,args.trial_data)
