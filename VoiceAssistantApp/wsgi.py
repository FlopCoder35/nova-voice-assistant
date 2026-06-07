"""
WSGI config for VoiceAssistantApp project.
Used by Django's built-in development server (manage.py runserver).
For production, use the ASGI entrypoint (asgi.py) with Daphne.
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'VoiceAssistantApp.settings')

application = get_wsgi_application()
