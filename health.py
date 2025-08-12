"""
Health Check Module
Provides health endpoint for monitoring and keep-alive functionality for Render platform
"""
import logging
import threading
import time
from datetime import datetime
from flask import Flask, jsonify

logger = logging.getLogger(__name__)

class HealthServer:
    """Health check server for monitoring and keep-alive functionality"""
    
    def __init__(self):
        """Initialize health server"""
        self.app = Flask(__name__)
        self.start_time = time.time()
        self.health_thread = None
        self.keep_alive_thread = None
        self.last_health_check = time.time()
        self.health_check_count = 0
        self._setup_routes()
        
        # Disable Flask logging in production
        logging.getLogger('werkzeug').setLevel(logging.WARNING)
    
    def _setup_routes(self):
        """Setup health check routes"""
        
        @self.app.route('/health')
        def health_check():
            """Main health check endpoint for Render platform monitoring - optimized for 10-minute intervals"""
            try:
                # Update health check tracking
                self.last_health_check = time.time()
                self.health_check_count += 1
                
                uptime_seconds = time.time() - self.start_time
                uptime_hours = uptime_seconds / 3600
                
                return jsonify({
                    'status': 'healthy',
                    'service': 'telegram-claim-bot',
                    'timestamp': time.time(),
                    'uptime_seconds': uptime_seconds,
                    'uptime_hours': round(uptime_hours, 2),
                    'uptime_human': self._format_uptime(uptime_seconds),
                    'health_checks_total': self.health_check_count,
                    'last_check': self.last_health_check,
                    'monitoring_interval': '10_minutes',
                    'version': '1.0.0',
                    'deployment': 'development'
                }), 200
                
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                return jsonify({
                    'status': 'unhealthy',
                    'service': 'telegram-claim-bot',
                    'timestamp': time.time(),
                    'error': 'Health check failed'
                }), 500
        
        @self.app.route('/status')
        def status_check():
            """Detailed status endpoint"""
            try:
                uptime_seconds = time.time() - self.start_time
                
                return jsonify({
                    'service': 'telegram-claim-bot',
                    'status': 'running',
                    'timestamp': time.time(),
                    'start_time': self.start_time,
                    'uptime_seconds': uptime_seconds,
                    'uptime_human': self._format_uptime(uptime_seconds),
                    'health_endpoint': '/health',
                    'health_checks_total': self.health_check_count,
                    'last_health_check': self.last_health_check,
                    'keep_alive_active': self.is_keep_alive_running(),
                    'version': '1.0.0'
                }), 200
                
            except Exception as e:
                logger.error(f"Status check failed: {e}")
                return jsonify({
                    'service': 'telegram-claim-bot',
                    'status': 'error',
                    'timestamp': time.time(),
                    'error': str(e)
                }), 500
        
        @self.app.route('/')
        def root():
            """Root endpoint"""
            return jsonify({
                'service': 'telegram-claim-bot',
                'message': 'Telegram Claim Bot is running',
                'health_endpoint': '/health',
                'status_endpoint': '/status'
            })
    
    def _format_uptime(self, uptime_seconds: float) -> str:
        """Format uptime in human readable format"""
        try:
            hours, remainder = divmod(int(uptime_seconds), 3600)
            minutes, seconds = divmod(remainder, 60)
            
            if hours > 0:
                return f"{hours}h {minutes}m {seconds}s"
            elif minutes > 0:
                return f"{minutes}m {seconds}s"
            else:
                return f"{seconds}s"
                
        except Exception:
            return "unknown"
    
    def _start_keep_alive(self):
        """Start keep-alive mechanism for continuous operation"""
        def keep_alive_worker():
            """Keep-alive worker that runs periodic health checks"""
            while True:
                try:
                    # Sleep for 5 minutes between keep-alive checks
                    time.sleep(300)
                    
                    # Log keep-alive status
                    uptime = time.time() - self.start_time
                    logger.info(f"Keep-alive check: Service running for {self._format_uptime(uptime)}")
                    
                    # Check if health server is still responsive
                    if not self.is_running():
                        logger.warning("Health server thread appears to be dead")
                        break
                        
                except Exception as e:
                    logger.error(f"Keep-alive worker error: {e}")
                    time.sleep(60)  # Wait 1 minute before retrying
        
        self.keep_alive_thread = threading.Thread(
            target=keep_alive_worker,
            daemon=True,
            name="KeepAlive"
        )
        self.keep_alive_thread.start()
        logger.info("Keep-alive mechanism started")
    
    def start(self, port: int):
        """
        Start health check server in separate thread
        
        Args:
            port: Port to run health server on
        """
        try:
            logger.info(f"Starting health check server on port {port}")
            
            def run_server():
                try:
                    self.app.run(
                        host='0.0.0.0',
                        port=port,
                        debug=False,
                        use_reloader=False,
                        threaded=True
                    )
                except Exception as e:
                    logger.error(f"Health server error: {e}")
            
            self.health_thread = threading.Thread(
                target=run_server,
                daemon=True,
                name="HealthServer"
            )
            self.health_thread.start()
            
            # Start keep-alive mechanism
            self._start_keep_alive()
            
            logger.info(f"Health check server started successfully on port {port}")
            return self.health_thread
            
        except Exception as e:
            logger.error(f"Failed to start health server: {e}")
            raise
    
    def is_running(self) -> bool:
        """Check if health server is running"""
        return self.health_thread is not None and self.health_thread.is_alive()
    
    def is_keep_alive_running(self) -> bool:
        """Check if keep-alive mechanism is running"""
        return self.keep_alive_thread is not None and self.keep_alive_thread.is_alive()
    
    def get_health_stats(self) -> dict:
        """Get health statistics"""
        uptime_seconds = time.time() - self.start_time
        return {
            'uptime_seconds': uptime_seconds,
            'uptime_human': self._format_uptime(uptime_seconds),
            'health_checks_total': self.health_check_count,
            'last_health_check': self.last_health_check,
            'server_running': self.is_running(),
            'keep_alive_running': self.is_keep_alive_running(),
            'start_time': self.start_time
        }

# Legacy function for backward compatibility
def start_health_server(port: int):
    """
    Legacy function to start health server
    
    Args:
        port: Port to run health server on
        
    Returns:
        Thread object
    """
    health_server = HealthServer()
    return health_server.start(port)
