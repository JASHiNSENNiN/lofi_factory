"""
webui.py — launcher for the Lo-fi Factory web control panel.

    python webui.py

Reads .env for WEBUI_PASSWORD, PUBLIC_BASE_URL, WEBUI_SECRET, WEBUI_HOST/PORT.
Expose it through your Cloudflare Tunnel pointing at WEBUI_HOST:WEBUI_PORT.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env):
    try:
        from dotenv import load_dotenv
        load_dotenv(_env, override=False)
    except ImportError:
        pass

# NiceGUI requires the launch guard (covers reload/multiprocessing entrypoints).
if __name__ in {"__main__", "__mp_main__"}:
    from webui.app import run
    run()
