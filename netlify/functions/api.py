import sys
import os

# Make web/ and tracebi/ importable — Netlify places included_files at /var/task/
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mangum import Mangum
from web.api.main import app

handler = Mangum(app, lifespan="off")
