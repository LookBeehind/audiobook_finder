import urllib3
import threading
import warnings
from urllib.parse import urlparse

from parsers.tokybook import tokybook
from parsers.naudios import naudios

warnings.filterwarnings("ignore", category=SyntaxWarning)
urllib3.disable_warnings()

WEBSITES = [
    {
        'name': 'tokybook',
        'url': 'https://tokybook.com',
    },
    {
        'name': 'naudios',
        'url': 'https://naudios.com',
    },
]

class BookScraper:
    def __init__(self):
        self.selected_book = None
        self.printed_books = set()
        self.print_lock = threading.Lock()
        self.thread_pool = []
        self.book_count = 0  # Initialize book_count
        self.book_urls = {}  # Initialize a dictionary to store book URLs

    def list_detected_books(self, books: list[dict[str, str]]):
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

    def get_desired_book_number(self) -> int:
        while True:
            requested_book = input(f"Select a book by entering its number (1 - {self.book_count}): ")

            if requested_book.isdigit():
                requested_book = int(requested_book)
                if 1 <= requested_book <= self.book_count:
                    return requested_book

            print(f"Invalid input. Please enter a valid number between 1 and {self.book_count}.")

    def search(self, request_input: str) -> None:
        books = []  # Initialize books list
        for website in WEBSITES:
            # Print the website name before listing the books
            print(f"Website: {website.get("url")}")

            class_inst = globals().get(website.get('name'))
            html = class_inst.get_search_page(request_input)
            books.extend(class_inst.list_books(html))
            self.list_detected_books(books)

        if self.book_count == 0:
            print("No matching books :<")
            exit()

        requested_book = self.get_desired_book_number()
        self.selected_book = books[requested_book - 1]

        if self.selected_book:
            print(f"Selected Book : {self.selected_book["title"]} ({self.selected_book.get('href')})")
        else:
            print("Invalid book selection.")

    def scrape_books(self, request_input: str) -> None:
        thread = threading.Thread(target=self.search, args=(request_input,))
        thread.start()
        self.thread_pool.append(thread)

        # Wait for all threads to finish
        for thread in self.thread_pool:
            thread.join()

    def download_chapters(self) -> None:
        if not hasattr(self, "selected_book") or not (url := self.selected_book.get('href')):
            print("No valid book selected")
            return

        if self.book_count == 0:
            exit()

        # Extract the website name from the title
        book_parts = urlparse(url)
        website = book_parts.netloc.split('.')[0]
        class_inst = globals().get(website)
        chapters = class_inst.get_chapters(url)
        if not chapters:
            print("No chapters found for the selected book.")
            return

        class_inst.download_all_chapters(title=self.selected_book.get('title'), chapters=chapters)

    def main(self) -> None:
        # request = input(f"Enter desired book: ")
        request = "dragon"
        self.scrape_books(request)
        self.download_chapters()


if __name__ == '__main__':
    BookScraper().main()
