import os
from pathlib import Path

USER = "exedis"
FFMPEG_PATH = "C:/ffmpeg/bin/ffmpeg.exe"

DEFAULT_CHROME_LOCATION = f'C:\\Users\\{USER}\\AppData\\Local\\Google\\Chrome\\User Data'

USER_DATA_DIR = Path(os.path.join(os.getcwd(), 'usr_data'))
DOWNLOAD_DIR = Path(os.path.join(os.getcwd(), 'downloads'))
DOWNLOAD_DIR.mkdir(exist_ok=True)

USER_AGENTS = [
    # Chrome (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",

    # Chrome (Linux)
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/118.0.5993.70 Safari/537.36",

    # Chrome (MacOS)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_2_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",

    # Firefox (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) "
    "Gecko/20100101 Firefox/122.0",

    # Firefox (Linux)
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) "
    "Gecko/20100101 Firefox/121.0",

    # Firefox (MacOS)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.0; rv:120.0) "
    "Gecko/20100101 Firefox/120.0",

    # Edge (Windows)
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",

    # Safari (MacOS)
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1_0) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.1 Safari/605.1.15",
]
