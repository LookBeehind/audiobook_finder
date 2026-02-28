import os
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import requests

from parsers.interface import IParser
from bs4 import BeautifulSoup

from utils.strutils import clean_title, REPLACEMENTS

MAX_WORKERS = 333

class NAudios(IParser):
    def __init__(self):
        self.base_url = "https://naudios.com"
        self.ch_flag = {}

    def download_chapter(self, url: str, file_path: str, file_name: str) -> None:
        try:
            response = requests.get(url, verify=False)
            with open(file_path, 'wb') as file:
                file.write(response.content)
            print(f"Downloaded {file_path}")
        except Exception as e:
            print(f"Error downloading {file_path}: {str(e)}")
        finally:
            self.ch_flag[file_name] = True

    def download_all_chapters(self, title: str, chapters: list[str]):
        replaced_chars = [REPLACEMENTS.get(char, char) for char in title]
        book_title = ''.join(replaced_chars)
        os.makedirs(book_title, exist_ok=True)

        with ThreadPoolExecutor(MAX_WORKERS) as executor:
            for index, link in enumerate(chapters):
                file_name = f'{book_title} - chapter {index + 1}.mp3'
                file_path = os.path.join(book_title, file_name)

                if self.ch_flag.get(file_name):
                    print(f"File already downloaded for {file_name}")
                    continue

                executor.submit(self.download_chapter, link, file_path, file_name)

    # def get_chapters(self, book_url: str) -> list[str]:
    #     response = requests.get(book_url, verify=False)
    #     html = response.text
    #     soup = BeautifulSoup(html, 'html.parser')
    #
    #     for script in soup.find_all("script"):
    #         if 'jQuery(function' in script.text:
    #             input_string = script.text
    #
    #             match = re.search(r"tracks = \[([^]]+)]", input_string)
    #             if not match:
    #                 print("Could not extract tracks from the jQuery, the website structure may have changed.")
    #                 exit()
    #
    #             extracted_text = match.group(1)
    #             extracted_text = extracted_text.strip(', ')
    #             extracted_text = f"[{extracted_text}]"
    #             extracted_data = eval(extracted_text)
    #
    #             tracks = [track for track in extracted_data]
    #             break
    #     else:
    #         print("Could not find the jQuery script containing track information.")
    #         exit()
    #
    #     chapter_links = [
    #         item["chapter_link_dropbox"]
    #         for item in tracks
    #         if "chapter_link_dropbox" in item
    #     ]
    #
    #     second_part_links = [
    #         link.replace('\\', '')
    #         for link in chapter_links
    #         if 'https://' not in link
    #     ]
    #
    #     return [
    #         f'https://files01.freeaudiobooks.top/audio/{second_part_link}'
    #         for second_part_link in second_part_links
    #     ]

    def get_chapters(self, book_url: str) -> list[str]:
        response = requests.get(book_url, verify=False)
        html = response.text
        soup = BeautifulSoup(html, 'html.parser')

        return [
            item.get("data-src")
            for item in soup.find_all("div", class_="track-item")
        ]

    def get_search_page(self, query: str) -> str | None:
        response = None

        search_url = f"{self.base_url}/?s={quote(query)}"
        try:
            response = requests.get(search_url, verify=False, timeout=10)
        except (requests.exceptions.TooManyRedirects, requests.exceptions.RequestException) as e:
            print(f"Error fetching {search_url}: {e}, skipping.")

        return response.text

    def list_books(self, search_page: str) -> list[dict[str, str]]:
        soup = BeautifulSoup(search_page, 'html.parser')
        books = []
        for book in soup.find_all('a', class_="post-item"):
            book_dict = {
                "title": clean_title(book.find('div', class_="post-title").text.strip()),
                "href": f"{self.base_url.rstrip('/')}/{book.get('href')}" if book.get('href') else ''
            }
            if book_dict['title']:
                books.append(book_dict)

        return books


naudios = NAudios()