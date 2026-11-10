import sys
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import config  # noqa: E402


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture
def open_form(browser):
    pages = []

    def _open(version):
        page = browser.new_page()
        page.goto(config.FORMS[version].as_uri())
        pages.append(page)
        return page

    yield _open
    for p in pages:
        p.close()
