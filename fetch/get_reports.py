import os
import re
import requests
import pandas as pd
from bs4 import BeautifulSoup
from git import Repo
from playwright.sync_api import sync_playwright
from urllib.parse import urlparse
from dotenv import load_dotenv
import time
import json

load_dotenv()

BASE_URL = "https://code4rena.com/reports"


def get_audit_report_links():
    """
    Uses Playwright to extract all valid audit report links from the Code4rena reports page.
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(BASE_URL, timeout=60000)
        
        # Wait for report links to load
        page.wait_for_selector("a[href^='/reports/']")
        anchors = page.query_selector_all("a[href^='/reports/']")
        
        links = []
        for a in anchors:
            href = a.get_attribute("href")
            # Match links of the form /reports/YYYY-MM-project-name
            if re.match(r"^/reports/\d{4}-\d{2}-", href):
                links.append("https://code4rena.com" + href)
        
        browser.close()
        return sorted(set(links))


if __name__ == "__main__":
    reports = get_audit_report_links()
    for url in reports:
        print(url)
    print("Reading URLs to send report to Gemini")
