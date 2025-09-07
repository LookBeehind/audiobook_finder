import os
from enum import StrEnum

import requests
from bs4 import BeautifulSoup
import urllib3
import threading
import re
from concurrent.futures import ThreadPoolExecutor
import warnings
from urllib.parse import urlparse

from tokybook_downloader import tokyscrapper

warnings.filterwarnings("ignore", category=SyntaxWarning)

def custom_title_filter(title: str) -> bool:
    return True if not title else title not in [
        'Home',
        'Next',
        'Terms and Conditions',
        'Privacy Policy',
        'Contact',
        'Member',
        'Uncategorized',
        'Continue Reading',
        '[email protected]',
        'Go back to home'
    ]

def clean_title(title: str) -> str:
    title = re.sub(r'\[Liste]|\[Listen]|\[Download]|By.*', '', title)
    title = re.sub(r'\s*[–.]*\s*$', '', title)
    title = title.replace(" – Audiobook Online", "").replace("Audiobook", "")
    title = title.replace("audiobook", "").replace("Audiobook Online – ", "").replace(" – Online Free ", "")
    return title.strip()

class WebsitesEnum(StrEnum):
    TOKYBOOK = 'https://tokybook.com'
    GALAXYAUDIOBOOK = 'https://galaxyaudiobook.com'
    FREEAUDIOBOOKS = 'https://freeaudiobooks.top'
    ZAUDIOBOOKS = 'https://zaudiobooks.com'

    @classmethod
    def list(cls) -> list[str]:
        return [member.value for member in cls] # noqa

REPLACEMENTS = {
    ' ': '_',
    '\\': '-',
    '/': '-',
    ':': '-',
    '*': '(star)',
    '?': '(question)',
    '(quote)': '_',
    '<': '(lt)',
    '>': '(gt)',
    r'|': '(pipeline)'
}
FILTERS = {
    'https://tokybook.com': {'tag': 'a', 'href': re.compile(r'/post/')},
    'https://galaxyaudiobook.com': {'rel': 'bookmark', 'href': True},
    'https://freeaudiobooks.top': {'href': True, 'string': custom_title_filter},
    'https://zaudiobooks.com': {'rel': 'bookmark', 'href': True},
}
FIRST_PART_LINKS = {
    WebsitesEnum.GALAXYAUDIOBOOK: 'https://files01.freeaudiobooks.top/audio/',
    WebsitesEnum.FREEAUDIOBOOKS: 'https://files01.freeaudiobooks.top/audio/',
    WebsitesEnum.ZAUDIOBOOKS: 'https://files01.freeaudiobooks.top/audio/',
}


class BookScraper:
    def __init__(self):
        self.selected_book_url = None
        self.selected_book_title = ''
        self.printed_books = set()
        self.print_lock = threading.Lock()
        self.max_threads = 10
        self.thread_pool = []
        self.book_count = 0  # Initialize book_count
        self.book_urls = {}  # Initialize a dictionary to store book URLs
        self.chapters = []
        self.ch_flag = {}

    def search(self, request_input: str) -> None:
        urllib3.disable_warnings()

        books = []  # Initialize books list
        for website in WebsitesEnum.list():
            if website == WebsitesEnum.TOKYBOOK:
                url = f"{website}/search?q={request_input}"
            else:
                url = f"{website}/?s={request_input}"

            try:
                response = requests.get(url, verify=False, timeout=10)
            except (requests.exceptions.TooManyRedirects, requests.exceptions.RequestException) as e:
                print(f"Error fetching {website}: {e}, skipping.")
                continue

            html = response.text
            soup = BeautifulSoup(html, 'html.parser')

            # Print the website name before listing the books
            print(f"Website: {website}")

            filter_dict = FILTERS.get(website, {})
            tag = filter_dict.pop('tag', 'a')
            for book in soup.find_all(tag, **filter_dict):
                book_dict = {"title": "", "href": book.get('href', '')}

                if website == WebsitesEnum.TOKYBOOK:
                    book_dict["title"] = book.find("img").get('alt') if book.find("img") else book.get_text(strip=True)
                    book_dict["href"] = f"{website}{book.get('href', '')}"
                else:
                    # For other tags, get 'string' as title and 'href' attribute
                    if book.string is not None:
                        book_dict["title"] = clean_title(book.string)

                if book_dict['title']:
                    books.append(book_dict)

            for index, book in enumerate(books):
                book_title = book['title']
                book_url = book['href']
                with self.print_lock:
                    if book_url and book_url not in self.printed_books:
                        self.book_count += 1  # Increment the book count
                        print(f"{self.book_count}: {book_title} ({book_url})")
                        # Add the book to the set of printed books
                        self.printed_books.add(book_url)

                        # Store the book URL in the dictionary with its index as the key
                        self.book_urls[self.book_count] = book_url

        if self.book_count == 0:
            print("No matching books :<")
            exit()

        while True:
            requested_book = input("Select a book by entering its number (1 - {}): ".format(self.book_count))

            if requested_book.isdigit():
                requested_book = int(requested_book)
                if 1 <= requested_book <= self.book_count:
                    break

            print("Invalid input. Please enter a valid number between 1 and {}.".format(self.book_count))

        self.selected_book_url = self.book_urls.get(requested_book)
        self.selected_book_title = [book['title'] for book in books if book['href'] == self.selected_book_url][0]

        if self.selected_book_url:
            print(f"Selected Book : {self.selected_book_title} ({self.selected_book_url})")
        else:
            print("Invalid book selection.")

    def scrape_books(self, request_input: str) -> None:
        thread = threading.Thread(target=self.search, args=(request_input,))
        thread.start()
        self.thread_pool.append(thread)

        # Wait for all threads to finish
        for thread in self.thread_pool:
            thread.join()

    def get_download_links(self) -> None:
        if not hasattr(self, "selected_book_url") or not self.selected_book_url:
            print("No valid book selected")
            return

        if self.book_count == 0:
            exit()

        url = self.selected_book_url

        if WebsitesEnum.TOKYBOOK in url:
            self.chapters = tokyscrapper.get_chapters(url)
            return

        response = requests.get(url, verify=False)
        html = response.text
        soup = BeautifulSoup(html, 'html.parser')

        book_parts = urlparse(self.selected_book_url)
        selected_website = f"{book_parts.scheme}://{book_parts.netloc}"
        first_part_link = FIRST_PART_LINKS.get(selected_website, False) # noqa
        if not first_part_link:
            print("Please specify first part link for this website in FIRST_PART_LINKS dictionary."
                  " Inspect the download link of a chapter and CTRL+F <mp3>.")
            exit()

        scripts = soup.find_all("script")
        for script in scripts:
            if 'jQuery(function' in script.text:
                input_string = script.text

                match = re.search(r"tracks = \[([^]]+)]", input_string)
                if not match:
                    print("Could not extract tracks from the jQuery, the website structure may have changed.")
                    exit()

                extracted_text = match.group(1)
                extracted_text = extracted_text.strip(', ')
                extracted_text = f"[{extracted_text}]"
                extracted_data = eval(extracted_text)

                tracks = [track for track in extracted_data]
                break
        else:
            print("Could not find the jQuery script containing track information.")
            exit()

        chapter_links = [
            item["chapter_link_dropbox"]
            for item in tracks
            if "chapter_link_dropbox" in item
        ]

        second_part_links = [
            link.replace('\\', '')
            for link in chapter_links
            if 'https://' not in link
        ]

        self.chapters = [
            f'{first_part_link}{second_part_link}'
            for second_part_link in second_part_links
        ]

    def download_file(self, url: str, file_path: str, file_name: str) -> None:
        try:
            response = requests.get(url, verify=False)
            with open(file_path, 'wb') as file:
                file.write(response.content)
            print(f"Downloaded {file_path}")
        except Exception as e:
            print(f"Error downloading {file_path}: {str(e)}")
        finally:
            self.ch_flag[file_name] = True

    def download_chapters(self) -> None:
        if not hasattr(self, "selected_book_title") or not self.selected_book_title:
            print("No valid book selected, skipping downloads.")
            return

        if WebsitesEnum.TOKYBOOK in self.selected_book_url:
            tokyscrapper.download_all_chapters(self.chapters)
            return

        replaced_chars = [
            REPLACEMENTS.get(char, char)
            for char in self.selected_book_title
        ]
        folder_name = ''.join(replaced_chars)
        download_folder = folder_name

        if not os.path.exists(download_folder):
            os.makedirs(download_folder)

        max_threads = 333

        with ThreadPoolExecutor(max_threads) as executor:
            for index, link in enumerate(self.chapters):
                replaced_chars = [REPLACEMENTS.get(char, char) for char in self.selected_book_title]
                res = ''.join(replaced_chars)
                file_name = f'{res} - chapter {index + 1}.mp3'
                file_path = os.path.join(download_folder, file_name)

                if self.ch_flag.get(file_name):
                    print(f"File already downloaded for {file_name}")
                    continue

                executor.submit(self.download_file, link, file_path, file_name)


if __name__ == '__main__':
    request = input(f"Enter desired book: ")

    book_scraper = BookScraper()
    book_scraper.scrape_books(request)
    book_scraper.get_download_links()
    book_scraper.download_chapters()