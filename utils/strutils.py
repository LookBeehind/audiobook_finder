import re


def clean_title(title: str) -> str:
    title = re.sub(r'\[Liste]|\[Listen]|\[Download]|By.*', '', title)
    title = re.sub(r'\s*[–.]*\s*$', '', title)
    return (
        title
        .replace(" – Audiobook Online", "")
        .replace("Audiobook", "")
        .replace("audiobook", "")
        .replace("Audiobook Online – ", "")
        .replace(" – Online Free ", "")
    ).strip()


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
