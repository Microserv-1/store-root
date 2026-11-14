"""Exercise the real load client against failed writes without AWS or databases."""
import http.server
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest


class WriteAttemptLimit(unittest.TestCase):
    def test_failed_orders_do_not_trigger_unbounded_write_retries(self):
        writes=[]

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):
                pass

            def respond(self,status,payload):
                body=json.dumps(payload).encode()
                self.send_response(status)
                self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length',0)))
                if self.path=='/accounts':self.respond(201,{'id':'account'})
                elif self.path=='/auth/login':self.respond(200,{'access_token':'local-test-token'})
                elif self.path=='/products':self.respond(201,{'id':'fixture'})
                elif self.path=='/orders':
                    writes.append(self.path)
                    self.respond(503,{'error':'simulated unavailable response'})
                else:self.respond(404,{})

            def do_GET(self):
                self.respond(200,[] if self.path=='/products' else {'id':'fixture'})

            def do_DELETE(self):
                self.respond(204,{})

        server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True)
        worker.start()
        try:
            with tempfile.TemporaryDirectory() as directory:
                output=Path(directory)/'load.json'
                process=subprocess.run([sys.executable,'scripts/load-business.py',
                    '--base-url',f'http://127.0.0.1:{server.server_port}',
                    '--scenario','orders','--users','1','--duration','1',
                    '--pause-ms','20','--max-orders-per-user','2','--output',str(output)],
                    cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True,timeout=20)
                self.assertEqual(process.returncode,1,process.stderr)
                report=json.loads(output.read_text())
                self.assertEqual(len(writes),2)
                self.assertEqual(report['overall']['status_counts'],{'503':2})
                self.assertEqual(report['overall']['error_ratio'],1)
                self.assertEqual(report['max_order_post_attempts'],2)
        finally:
            server.shutdown()
            server.server_close()
            worker.join(timeout=2)


if __name__=='__main__':
    unittest.main()
