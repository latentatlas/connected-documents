"""Start the recorded judge build, evidence walkthrough, or configured live workspace."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlsplit
import zipfile

ROOT=Path(__file__).resolve().parent


def source_archive():
    # Only the verified distribution is exportable, never runtime or auth files.
    from verify_release import verify
    verify(ROOT)
    manifest=json.loads((ROOT/'RELEASE_MANIFEST.json').read_text())
    buffer=io.BytesIO()
    with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for name in sorted([*manifest['files'],'RELEASE_MANIFEST.json']):
            archive.writestr(name,(ROOT/name).read_bytes())
    return buffer.getvalue()


def walkthrough(port,judge=False):
    site=ROOT/('judge-build' if judge else 'walkthrough')
    assets={('/'+str(p.relative_to(site))):p for p in site.rglob('*') if p.is_file()}
    assets['/']=site/'index.html';assets['/examples']=site/'index.html'
    hosts={f'127.0.0.1:{port}',f'localhost:{port}'}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):
            pass
        def do_GET(self):
            if self.headers.get('Host') not in hosts:
                self.send_error(403);return
            route=urlsplit(self.path).path
            path=assets.get(route)
            if judge and route=='/downloads/connected-documents-source.zip':
                try:
                    data=source_archive()
                except (ValueError,OSError,KeyError):
                    self.send_error(409,'Source integrity check failed');return
                content_type='application/zip'
            elif path is not None:
                data=path.read_bytes()
                content_type=mimetypes.guess_type(path.name)[0] or 'application/octet-stream'
            else:
                self.send_error(404);return
            self.send_response(200)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers();self.wfile.write(data)
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    label='Recorded judge build' if judge else 'Recorded walkthrough'
    print(f'{label}: http://127.0.0.1:{port}/?lang=en — no model calls',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    modes=parser.add_mutually_exclusive_group()
    modes.add_argument('--workspace',action='store_true',help='Start live app; requires separate account/credit configuration for generation')
    modes.add_argument('--judge',action='store_true',help='Try the recorded review, editing, acceptance, export and undo workflow without credentials')
    parser.add_argument('--port',type=int,default=8981)
    args=parser.parse_args()
    if args.workspace:
        from connected_work.server import serve
        serve(ROOT/'work/runtime',args.port,provider='nebius',control=ROOT/'work/control',trial_data=ROOT/'work/private-study')
    else:
        walkthrough(args.port,judge=args.judge)
