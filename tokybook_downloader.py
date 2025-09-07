import random
import subprocess
import atexit
import os
import threading
import time
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


class TokyBookScraper:
    def __init__(self):
        self.base_url = "https://tokybook.com"
        self.token = None
        self.referer = None
        self.book_id = None
        self.driver = None
        self.chapters = []

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
        options.add_argument("--headless")
        options.add_argument(f'--user-data-dir={USER_DATA_DIR}')
        options.add_argument('--profile-directory=Default')
        options.add_argument('--mute-audio')
        options.headless = True
        self.driver = webdriver.Chrome(options=options)

    def page_source(self, url: str) -> str:
        if not self.driver:
            self.init_driver()
        self.referer = url
        self.driver.get(url)
        play_button = self.driver.find_element(By.XPATH, '//button[@data-action="play-now"]')
        self.token = play_button.get_attribute('data-token')
        self.book_id = play_button.get_attribute('data-book-id')
        play_button.click()
        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.XPATH, '//li[contains(@class, "playlist-item-hls")]'))
        )
        page_src = self.driver.page_source
        self.driver.close()
        return page_src

    def get_chapters(self, book_url: str) -> list[str]:
        page_src = self.page_source(book_url)
        soup = BeautifulSoup(page_src, 'html.parser')

        chapters = soup.find_all('li', class_='playlist-item-hls')

        if not chapters:
            print("No chapters found on the page. The structure may have changed.")
            exit()

        for chapter in chapters:
            chapter_endpoint = chapter.get('data-track-src')
            self.chapters.append(f"{self.base_url}{chapter_endpoint}")

        return self.chapters

    @property
    def get_headers(self):
        if not all([self.token, self.referer, self.book_id]):
            raise ValueError("Token, referer, and book_id must be set before getting headers.")

        return {
            "accept": "*/*",
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en-US,en;q=0.9,ru;q=0.8,ro;q=0.7,fr;q=0.6",
            "cookie": "_ga=GA1.1.1451830200.1757179762; _ga_NK83792VER=GS2.1.s1757179761$o1$g1$t1757182427$j38$l0$h0",
            'referer': self.referer,
            "sec-ch-ua": "\"Opera GX\";v=\"120\", \"Not-A.Brand\";v=\"8\", \"Chromium\";v=\"135\"",
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": "\"Windows\"",
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": random.choice(USER_AGENTS),
            "x-audiobook-id": self.book_id,
            'authority': 'tokybook.com',
            'origin': self.base_url,
            "x-playback-token": self.token
        }

    def download_chapter(self, chapter_url: str):
        headers = self.get_headers
        response = requests.get(chapter_url, headers=headers)
        chapter_name = chapter_url.split("/")[-1].replace('.m3u8', '')
        base_url = chapter_url.replace(f"{chapter_name}.m3u8", "")

        chapter_name = chapter_name.replace(' -', '').replace(' ', '_').lower()
        if response.status_code == 200:
            playlist = response.text
        else:
            print(f"Request failed: {response.status_code}")
            exit()

        # Extract .ts files from playlist
        ts_files = [line.strip() for line in playlist.splitlines() if line.endswith(".ts")]

        # Create a local folder
        Path(f"chunks_{chapter_name}").mkdir(exist_ok=True)

        # Download each .ts file
        for i, ts in enumerate(ts_files, start=1):
            url = base_url + ts
            r = requests.get(url, headers=headers, stream=True, timeout=10)
            if r.status_code == 200:
                with open(f"chunks_{chapter_name}/{ts}", "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
                # Check if file is empty
                if Path(f"chunks_{chapter_name}/{ts}").stat().st_size == 0:
                    print(f"Warning: {ts} downloaded but is empty!")
            else:
                print(f"Failed to download {url}: {r.status_code}")
            time.sleep(4)  # Be polite to the server

        # Merge into a single .ts file
        merged_ts_path = Path(f"all_{chapter_name}.ts")
        chunks_dir = Path(f"chunks_{chapter_name}")
        with open(merged_ts_path, "wb") as outfile:
            for ts in ts_files:
                with open(chunks_dir / ts, "rb") as f:
                    outfile.write(f.read())

        # Convert to mp3 using ffmpeg
        subprocess.run(
            [
                str(FFMPEG_PATH),
                "-i", str(merged_ts_path),
                "-c:a", "libmp3lame", "-q:a", "2",
                str(DOWNLOAD_DIR / f"{chapter_name}.mp3")
            ],
            stdout=subprocess.DEVNULL,
        )

        def cleanup():
            try:
                os.remove(merged_ts_path)
                for ts in ts_files:
                    os.remove(chunks_dir / ts)
                os.rmdir(chunks_dir)
            except Exception as e:
                print(f"Cleanup failed: {e}")

        atexit.register(cleanup)

        time.sleep(10)
        return str(DOWNLOAD_DIR / chapter_name)

    def download_all_chapters(self, chapters: list[str]):
        with ThreadPoolExecutor(max_workers=10) as executor:
            tasks = [
                executor.submit(self.download_chapter, chapter_url)
                for chapter_url in chapters
            ]
            for task in tasks:
                name = task.result()
                print(f"Downloaded chapter: {name}")


tokyscrapper = TokyBookScraper()
