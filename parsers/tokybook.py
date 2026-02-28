import random
import re
import subprocess
import atexit
import os
import time
from urllib.parse import urlparse, quote, unquote
from concurrent.futures import ThreadPoolExecutor

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pathlib import Path

from config import USER_DATA_DIR, DOWNLOAD_DIR, FFMPEG_PATH, DEFAULT_CHROME_LOCATION, USER_AGENTS
from parsers.interface import IParser

HEALDESS = False

MAX_WORKERS = 10

class TokyBook(IParser):
    def __init__(self):
        self.base_url = "https://tokybook.com"
        self.token = None
        self.referer = None
        self.book_id = None
        self.driver = None

    @staticmethod
    def copy_user_data():
        try:
            src = Path(DEFAULT_CHROME_LOCATION)
            dst = USER_DATA_DIR

            if dst.exists():
                return

            if not src.exists():
                print(f"Source user data directory does not exist: {src}")
                return

            import shutil
            shutil.copytree(src, dst)
            print(f"Copied user data from {src} to {dst}")
        except Exception as e:
            print(f"Failed to copy user data: {e}")

    def init_driver(self):
        options = Options()
        self.copy_user_data()
        if HEALDESS:
            options.add_argument("--headless")
            options.headless = True

        options.add_argument(f'--user-data-dir={USER_DATA_DIR}')
        options.add_argument('--profile-directory=Default')
        options.add_argument('--mute-audio')
        options.add_argument("--autoplay-policy=no-user-gesture-required")
        self.driver = webdriver.Chrome(options=options)

    def get_playlist_api_data(self, url: str) -> dict:
        if not self.driver:
            self.init_driver()
        self.referer = url
        self.driver.get(url)

        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, 'cms-post-details'))
        )

        # Wait specifically for the play button to render inside the Shadow DOM
        # We use a lambda function to continuously run a tiny JS check until it returns True
        WebDriverWait(self.driver, 10).until(
            lambda d: d.execute_script(
                "return !!(document.querySelector('cms-post-details')?.shadowRoot?.querySelector('.play-button'));"
            )
        )

        # Inject a JavaScript interceptor BEFORE clicking the button
        # This wraps the browser's fetch API and saves the JSON when it sees the playlist URL
        intercept_js = """
            window.interceptedPlaylistData = null;
            const originalFetch = window.fetch;

            window.fetch = async function(...args) {
                const response = await originalFetch.apply(this, args);

                // Check if the URL string exists and matches our target API
                const url = args[0] instanceof Request ? args[0].url : args[0];
                if (url && url.includes('/api/v1/playlist')) {
                    const clone = response.clone();
                    clone.json().then(data => { 
                        window.interceptedPlaylistData = data; 
                    });
                }
                return response;
            };
        """
        self.driver.execute_script(intercept_js)

        # Click the Play Button inside the shadow root to trigger the API call
        click_js = """
            const host = document.querySelector('cms-post-details');
            const playBtn = host.shadowRoot.querySelector('.play-button');
            console.log('Clicking play button:', playBtn);
            if (playBtn) playBtn.click();
        """
        self.driver.execute_script(click_js)

        # Wait for the intercepted data to populate and return it to Python
        # This lambda function checks the JS variable every 500ms until it isn't null
        playlist_data = WebDriverWait(self.driver, 15).until(
            lambda d: d.execute_script("return window.interceptedPlaylistData;")
        )

        self.driver.close()
        return playlist_data

    def search_page_source(self, url: str) -> str | None:
        if not self.driver:
            self.init_driver()
        self.referer = url
        self.driver.get(url)

        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, 'search-page'))
        )

        js_script = """
            const cards = document.querySelector('search-page').shadowRoot.querySelectorAll('audiobook-card');
            let combinedHtml = '<div class="grid-container">';

            cards.forEach(card => {
                // Grab the HTML natively hidden inside the inner shadow root
                if (card.shadowRoot) {
                    combinedHtml += '<audiobook-card>' + card.shadowRoot.innerHTML + '</audiobook-card>';
                }
            });

            combinedHtml += '</div>';
            return combinedHtml;
        """

        flat_html = self.driver.execute_script(js_script)
        return flat_html

    @property
    def get_headers(self):
        if not all([self.token, self.referer, self.book_id]):
            raise ValueError("Token, referer, and book_id must be set before getting headers.")

        return {
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en-GB,en-US;q=0.9,en;q=0.8",  # Matched to your curl
            'referer': self.referer,
            "sec-ch-ua": "\"Opera GX\";v=\"120\", \"Not-A.Brand\";v=\"8\", \"Chromium\";v=\"135\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": random.choice(USER_AGENTS),
            "x-audiobook-id": self.book_id,
            'origin': self.base_url,
            "x-stream-token": self.token,
        }

    def download_chapter(self, chapter_url: str):
        headers = self.get_headers

        # Generate the exact x-track-src the server expects
        # It needs to be the absolute path of the URL (e.g., /api/v1/public/audio/...)
        parsed_url = urlparse(chapter_url)
        headers["x-track-src"] = parsed_url.path

        response = requests.get(chapter_url, headers=headers)

        chapter_name = unquote(chapter_url.split("/")[-1].replace('.m3u8', ''))
        base_url = chapter_url.replace(f"{chapter_url.split('/')[-1]}", "")
        chapter_name_clean = chapter_name.replace(' -', '').replace(' ', '_').lower()

        if response.status_code == 200:
            playlist = response.text
        else:
            print(f"Request failed for {chapter_name}: {response.status_code}")
            print(f"Response body: {response.text}")
            return

        # Extract .ts files from playlist
        ts_files = [line.strip() for line in playlist.splitlines() if line.endswith(".ts") and not line.startswith("#")]

        if not ts_files:
            print(f"No TS files found in playlist for {chapter_name}")
            return

        chunk_dir = Path(f"chunks_{chapter_name_clean}")
        chunk_dir.mkdir(exist_ok=True)

        for i, ts in enumerate(ts_files, start=1):
            url = base_url + ts

            # VERY IMPORTANT: Update x-track-src to point to the TS file, not the m3u8 file
            parsed_ts_url = urlparse(url)
            headers["x-track-src"] = parsed_ts_url.path

            r = requests.get(url, headers=headers, stream=True, timeout=10)
            if r.status_code == 200:
                with open(chunk_dir / ts, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)

                # Check if file is empty
                if (chunk_dir / ts).stat().st_size == 0:
                    print(f"Warning: {ts} downloaded but is empty!")
            else:
                print(f"Failed to download {url}: {r.status_code}")

            time.sleep(1)

        # Merge into a single .ts file
        merged_ts_path = Path(f"all_{chapter_name_clean}.ts")
        with open(merged_ts_path, "wb") as outfile:
            for ts in ts_files:
                ts_path = chunk_dir / ts
                if ts_path.exists():
                    with open(ts_path, "rb") as f:
                        outfile.write(f.read())

        # Convert to mp3 using ffmpeg
        final_mp3_path = DOWNLOAD_DIR / f"{chapter_name_clean}.mp3"
        subprocess.run(
            [
                str(FFMPEG_PATH),
                "-i", str(merged_ts_path),
                "-c:a", "libmp3lame", "-q:a", "2",
                str(final_mp3_path)
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL  # Suppress stderr too for cleaner console
        )

        def cleanup():
            try:
                if merged_ts_path.exists():
                    os.remove(merged_ts_path)
                for ts in ts_files:
                    ts_file_path = chunk_dir / ts
                    if ts_file_path.exists():
                        os.remove(ts_file_path)
                if chunk_dir.exists():
                    os.rmdir(chunk_dir)
            except Exception as e:
                pass  # Silent cleanup

        atexit.register(cleanup)
        cleanup()

        return str(final_mp3_path)

    def download_all_chapters(self, title: str, chapters: list[str]):
        with ThreadPoolExecutor(max_workers=10) as executor:
            tasks = [
                executor.submit(self.download_chapter, chapter_url)
                for chapter_url in chapters
            ]
            for task in tasks:
                name = task.result()
                print(f"Downloaded chapter: {name}")

    def get_chapters(self, book_url: str) -> list[str]:
        playlist_data = self.get_playlist_api_data(book_url)
        tracks = playlist_data.get('tracks', [])
        chapters = []

        if not tracks:
            print("No chapters found in the API response. The structure may have changed.")
            exit()

        self.token = playlist_data.get('streamToken')
        self.book_id = playlist_data.get('audioBookId')

        for track in tracks:
            chapter_endpoint = track.get('src')

            if chapter_endpoint:
                # We must URL-encode the endpoint (handling spaces and special characters),
                # but preserve the forward slashes.
                encoded_endpoint = quote(chapter_endpoint.lstrip('/'), safe='/')
                chapters.append(f"{self.base_url.rstrip('/')}/api/v1/public/audio/{encoded_endpoint}")

        return chapters

    def get_search_page(self, query: str) -> str | None:
        search_url = f"{self.base_url}/search?q={quote(query)}"
        return self.search_page_source(search_url)

    def list_books(self, search_page: str) -> list[dict[str, str]]:
        soup = BeautifulSoup(search_page, 'html.parser')
        books = []
        for book in soup.find_all('a', href=re.compile(r'/post/')):
            book_dict = {
                "title": book.find("img").get('alt') if book.find("img") else book.get_text(strip=True),
                "href": f"{self.base_url}{book.get('href', '')}"
            }
            if book_dict['title']:
                books.append(book_dict)

        return books


tokybook = TokyBook()
