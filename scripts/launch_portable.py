"""No credentials required. LAN access must be explicitly enabled."""
import argparse, os, socket, threading, webbrowser
from pathlib import Path
def main():
    p=argparse.ArgumentParser();p.add_argument('--lan',action='store_true');p.add_argument('--port',type=int,default=8000);args=p.parse_args()
    os.chdir(Path(__file__).resolve().parent)
    probe=socket.socket()
    try: probe.bind(('127.0.0.1',args.port))
    except OSError: raise SystemExit(f'Port {args.port} is in use. Close the old instance or run launch.py --port 8001.')
    finally: probe.close()
    url=f'http://127.0.0.1:{args.port}'
    def browser():
        import time, urllib.request
        for _ in range(40):
            try: urllib.request.urlopen(url+'/api/status',timeout=1).close();webbrowser.open(url);return
            except OSError: time.sleep(.5)
    threading.Thread(target=browser,daemon=True).start()
    print('Travel Planner 1.0.0:',url,'| Ctrl+C to stop')
    import uvicorn
    uvicorn.run('backend.app.main:app',host='0.0.0.0' if args.lan else '127.0.0.1',port=args.port)
if __name__=='__main__': main()
