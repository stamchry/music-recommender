import os

import json
import socket
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from src.lambda_function import lambda_handler
from src.config import WEB_DIR

class RecommenderDevServer(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Serve static files directly from our vibrant web/ frontend folder
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)
        
    def do_GET(self):
        parsed = urlparse(self.path)
        
        # Intercept API calls to simulate real-time cloud Lambda executions locally!
        if parsed.path == "/api/recommend":
            query = parse_qs(parsed.query)
            username = query.get("username", [None])[0]
            
            mock_event = {"queryStringParameters": {"username": username}}
            print(f"\n[DEV SERVER] Intercepted /api/recommend -> Triggering lambda_handler for user: '{username}'")
            
            response = lambda_handler(mock_event)
            
            self.send_response(response.get("statusCode", 200))
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            self.wfile.write(response.get("body", "{}").encode("utf-8"))
            return
            
        # Fall back to serving standard frontend static files (index.html, style.css, app.js)
        super().do_GET()
        
    def log_message(self, format, *args):
        # Clean logging format
        print(f"[DEV WEB SERVER] {args[0]} | {self.headers.get('User-Agent', 'unknown client')[:40]}")

def run_dev_server(port=8000):
    server_address = ('', port)
    
    # Allow port reuse to avoid 'Address already in use' errors during rapid iteration
    HTTPServer.allow_reuse_address = True
    httpd = HTTPServer(server_address, RecommenderDevServer)
    
    print("=" * 70)
    print(f"🌟 Music Recommender Dev Server Running at: http://localhost:{port}/")
    print("   -> Frontend UI: Interactive dark-mode glassmorphism interface")
    print("   -> API Bridge:  http://localhost:8000/api/recommend?username=...")
    print("   -> Press Ctrl+C to shut down dev server")
    print("=" * 70)
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n shutting down web dev server.")
        httpd.server_close()

if __name__ == "__main__":
    run_dev_server()
