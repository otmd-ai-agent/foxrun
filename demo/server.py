"""Single-visitor Codespaces demo UI. Keep the forwarded port private."""
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
from settings import *
import agent

LOCK=threading.Lock()
HISTORY=[]
EVENTS=[]

def status():
    try:return json.loads((ROOT/'status.json').read_text())
    except (OSError,ValueError):return {'stage':'Starting','detail':'Preparing the disposable demo.','ready':False,'model':MODEL}

class Handler(BaseHTTPRequestHandler):
    def reply(self,data,code=200):
        body=json.dumps(data).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)
    def do_GET(self):
        # Simple Browser adds a cache-busting query parameter to the page URL.
        path = urlsplit(self.path).path
        if path=='/api/health':return self.reply({'application':'foxrun-demo'})
        if path=='/api/state':return self.reply({'setup':status(),'tasks':agent.tasks() if status().get('ready') else [],'events':EVENTS[-12:]})
        if path!='/':return self.reply({'error':'Not found'},404)
        body=(SOURCE/'demo/index.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'self' https://*.github.dev https://github.dev https://*.vscode-cdn.net https://*.vscode-webview.net; base-uri 'none'");self.end_headers();self.wfile.write(body)
    def do_POST(self):
        # Cross-origin forms cannot supply this header; we grant no CORS preflight.
        if self.headers.get('X-Foxrun-Demo')!='1' or self.headers.get('Content-Type')!='application/json':return self.reply({'error':'Expected a same-site JSON request'},403)
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=12000:raise ValueError('Request too large or empty')
            body=json.loads(self.rfile.read(size))
            if not isinstance(body,dict):raise ValueError('Expected JSON object')
        except (ValueError,json.JSONDecodeError) as e:return self.reply({'error':str(e)},400)
        if not status().get('ready'):return self.reply({'error':'Setup is not ready yet.'},503)
        if not LOCK.acquire(blocking=False):return self.reply({'error':'A request is already running. Wait for it to finish.'},409)
        try:
            if self.path=='/api/chat':result=agent.chat(body.get('message'),HISTORY,EVENTS.append)
            elif self.path=='/api/new-chat':HISTORY.clear();result={'ok':True}
            elif self.path=='/api/accept':
                ident=agent.task_id(body.get('task_id'))
                if body.get('reviewed') is not True:raise ValueError('Read the proof before accepting.')
                result=agent.work('accept',ident,'--by','visitor')
                EVENTS.append({'tool':'human_accept','result':result})
            else:return self.reply({'error':'Not found'},404)
            self.reply(result)
        except Exception as e:self.reply({'error':str(e)},400)
        finally:LOCK.release()

def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    with (ROOT/'prepare.log').open('a') as log:
        subprocess.Popen([sys.executable,str(SOURCE/'demo/prepare.py')],stdout=log,stderr=log)
    ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()

if __name__=='__main__':main()
