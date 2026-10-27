"""WSGI entry point for production servers (gunicorn, uWSGI, mod_wsgi).

app.py's own `if __name__ == "__main__"` block (the Flask dev server) is for
local development only -- in production, point the WSGI server at this
module instead, e.g.:

    gunicorn wsgi:app
"""
from app import app

# PEP 3333 / mod_wsgi convention -- some WSGI servers look for this name
# specifically rather than accepting any callable you point them at.
application = app
