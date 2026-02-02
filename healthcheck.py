from http.server import HTTPServer, BaseHTTPRequestHandler
import logging

logger = logging.getLogger(__name__)


class HealthCheckHandler(BaseHTTPRequestHandler):
    """Health check endpoint"""

    def do_GET(self):
        """Health check response"""
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK - Bot is running')

    def log_message(self, format, *args):
        """Loglarni o'chirish"""
        pass


def start_health_server(port=8080):
    """Health check server'ni ishga tushirish"""
    try:
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        logger.info(f"✅ Health check server started on port {port}")
        server.serve_forever()
    except Exception as e:
        logger.error(f"Health check server error: {e}")