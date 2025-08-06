"""
Gunicorn configuration for Telegram Claim Bot
Optimized for Render deployment with proper worker management
"""

import os
import multiprocessing

# Server socket
bind = f"0.0.0.0:{os.environ.get('PORT', 8000)}"
backlog = 2048

# Worker processes
# Set workers to 1 to prevent ConversationHandler state loss across multiple workers
# When using multiple workers, each worker has its own memory space and ConversationHandler state,
# which can cause the bot to lose track of conversation state when requests are load-balanced
# across different workers
workers = 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2

# Restart workers after this many requests, to prevent memory leaks
max_requests = 1000
max_requests_jitter = 50

# Logging
accesslog = "-"
errorlog = "-"
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = "telegram-claim-bot"

# Server mechanics
daemon = False
pidfile = None
user = None
group = None
tmp_upload_dir = None

# SSL (not needed for Render)
keyfile = None
certfile = None

# Application
wsgi_app = "app:app"

# Preload application for better performance
preload_app = True

# Worker timeout for long-running requests (like photo uploads)
graceful_timeout = 30

# Enable worker recycling to prevent memory leaks
max_worker_memory = 200  # MB

def when_ready(server):
    """Called just after the server is started."""
    server.log.info("Telegram Claim Bot server is ready. Listening on %s", bind)

def worker_int(worker):
    """Called just after a worker exited on SIGINT or SIGQUIT."""
    worker.log.info("Worker received INT or QUIT signal")

def pre_fork(server, worker):
    """Called just before a worker is forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_fork(server, worker):
    """Called just after a worker has been forked."""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def worker_abort(worker):
    """Called when a worker received the SIGABRT signal."""
    worker.log.info("Worker received SIGABRT signal")
