import pytest
from wiki_engine import MarkdownParser

def test_heading_parsing():
    parser = MarkdownParser()
    assert parser.to_html("# H1") == "<h1>H1</h1>"
    assert parser.to_html("## H2") == "<h2>H2</h2>"
    assert parser.to_html("### H3") == "<h3>H3</h3>"

def test_bold_parsing():
    parser = MarkdownParser()
    assert "<b>bold</b>" in parser.to_html("This is **bold** text")

def test_link_parsing():
    parser = MarkdownParser()
    html = parser.to_html("[Google](https://google.com)")
    assert '<a href="https://google.com">Google</a>' in html

def test_list_parsing():
    parser = MarkdownParser()
    md = "- Item 1\n- Item 2"
    html = parser.to_html(md)
    assert "<ul>" in html
    assert "<li>Item 1</li>" in html
    assert "<li>Item 2</li>" in html
    assert "</ul>" in html

def test_mixed_content():
    parser = MarkdownParser()
    md = "# Title\n\n- [Link](url)\n- **Bold**"
    html = parser.to_html(md)
    assert "<h1>Title</h1>" in html
    assert '<a href="url">Link</a>' in html
    assert "<b>Bold</b>" in html
