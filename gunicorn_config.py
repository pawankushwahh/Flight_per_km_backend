# Gunicorn configuration file for Render
workers = 4
bind = "0.0.0.0:10000"
worker_class = "gevent"
