# keep the suite fully offline: no live weather fetches during tests
import os

os.environ.setdefault("SCPH_RAINFALL_PROVIDER", "off")
