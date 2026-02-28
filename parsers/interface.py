import abc


class IParser(abc.ABC):
    @abc.abstractmethod
    def get_chapters(self, book_url: str) -> list[str]:
        raise NotImplementedError()

    @abc.abstractmethod
    def download_all_chapters(self, title: str, chapters: list[str]) -> None:
        raise NotImplementedError()

    @abc.abstractmethod
    def get_search_page(self, query: str) -> str | None:
        raise NotImplementedError()

    @abc.abstractmethod
    def list_books(self, search_page: str) -> list[dict[str, str]]:
        raise NotImplementedError()