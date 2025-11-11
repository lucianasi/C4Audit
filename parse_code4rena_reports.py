#!/usr/bin/env python3
"""
Code4rena Report Parser (refactored)
- Reads URLs from a .txt file
- Extracts scope (repository, contracts, LOC)
- Extracts issues (High, Medium, Low, etc.)
- Ignores reports without <h1 id="scope"> or without Solidity mention
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import os
import sys


# =====================================================
# 1. UTILITIES
# =====================================================

def normalize_number(num_str: str) -> int:
    """Removes commas, tildes, and safely converts to int."""
    if not num_str:
        return 0
    num_str = re.sub(r"[^\d]", "", num_str)
    try:
        return int(num_str)
    except ValueError:
        return 0


def get_section_html(soup: BeautifulSoup, section_id: str) -> str | None:
    """Extracts the HTML of a section (<h1 id=...>) until the next <h1>."""
    header = soup.find("h1", id=section_id)
    if not header:
        return None
    section_html = ""
    sib = header.find_next_sibling()
    while sib and sib.name != "h1":
        if hasattr(sib, "get_text"):
            section_html += str(sib)
        sib = sib.find_next_sibling()
    return section_html


def extract_github_links(tag):
    """Returns all GitHub links found in a tag."""
    return [a["href"] for a in tag.find_all("a", href=True) if "github.com" in a["href"]]


# =====================================================
# 2. SCOPE PARSER
# =====================================================

def parse_repository_link(scope_soup: BeautifulSoup) -> str | None:
    """Extracts the repository link from the scope section."""
    for a in scope_soup.find_all("a", href=True):
        href = a["href"]
        if "github.com" in href and "code-423n4" in href:
            return href
    return None


def extract_scope_numbers(scope_text: str) -> tuple[int, int]:
    """Extracts number of contracts and lines of Solidity code."""
    contracts, lines = 0, 0

    m_contracts = re.search(r"([\d,~]+)\s+(?:smart\s+)?contracts?", scope_text, re.IGNORECASE)
    if m_contracts:
        contracts = normalize_number(m_contracts.group(1))

    m_lines = re.search(
        r"([\d,~]+)\s+(?:source\s+lines|lines\s+of\s+Solidity|lines\s+of\s+Solidity\s+code|lines\s+of\s+code\s+written\s+in\s+Solidity)",
        scope_text,
        re.IGNORECASE,
    )
    if m_lines:
        lines = normalize_number(m_lines.group(1))

    return contracts, lines


def parse_scope_section(soup: BeautifulSoup) -> dict | None:
    """Parses the <h1 id='scope'> section, extracting repo, contracts, and lines."""
    section_html = get_section_html(soup, "scope")
    if not section_html:
        return None  # tag does not exist → skip report

    scope_soup = BeautifulSoup(section_html, "html.parser")
    scope_text = scope_soup.get_text(" ", strip=True)

    # Must contain Solidity
    if not re.search(r"\bSolidity\b", scope_text, re.IGNORECASE):
        return None

    contracts, lines = extract_scope_numbers(scope_text)
    return {
        "repository": parse_repository_link(scope_soup),
        "contracts": contracts,
        "lines_solidity": lines,
    }


# =====================================================
# 3. ISSUE PARSER
# =====================================================

SEVERITY_MAP = {
    "H": "High",
    "M": "Medium",
    "L": "Low",
    "N": "Non-Critical",
    "G": "Gas"
}


def parse_issue_from_h2(tag) -> dict | None:
    """Extracts an issue from an <h2> tag."""
    text = tag.get_text(" ", strip=True)
    m = re.match(r"\[(H|M|L|N|G)-\d+\]", text)
    if not m:
        return None

    issue_id = m.group(0).strip("[]")
    title = text.split("]", 1)[1].strip()
    severity = SEVERITY_MAP.get(issue_id.split("-")[0], "Info")

    desc_parts, code_links = [], []
    sib = tag.find_next_sibling()
    while sib and not (sib.name == "h2" and re.match(r"\[(H|M|L|N|G)-\d+\]", sib.get_text(" ", strip=True))):
        txt = sib.get_text(" ", strip=True)
        if txt:
            desc_parts.append(txt)
        code_links += extract_github_links(sib)
        sib = sib.find_next_sibling()

    return {
        "issue_id": issue_id,
        "title": title,
        "severity": severity,
        "description": " ".join(desc_parts).strip(),
        "vulnerable_code_links": list(set(code_links))
    }


def parse_simple_issue_block(sib, issue_counter: int) -> dict:
    """Handles [01], [02] issue blocks without severity prefix."""
    txt = sib.get_text(" ", strip=True)
    title = txt.split("]", 1)[1].strip() if "]" in txt else txt
    code_links = extract_github_links(sib)
    desc_parts = []

    next_tag = sib.find_next_sibling()
    while next_tag and next_tag.name not in ["h2", "h1"]:
        if next_tag.get_text(strip=True):
            desc_parts.append(next_tag.get_text(" ", strip=True))
        code_links += extract_github_links(next_tag)
        next_tag = next_tag.find_next_sibling()

    return {
        "issue_id": f"L-{issue_counter:02d}",
        "title": title,
        "severity": "Low",
        "description": " ".join(desc_parts).strip(),
        "vulnerable_code_links": list(set(code_links))
    }


def parse_issue_list_items(sib, issue_counter: int) -> list:
    """Handles <ul><li> lists (older reports)."""
    issues = []
    for li in sib.find_all("li", recursive=False):
        a_tag = li.find("a")
        if not a_tag:
            continue
        text = a_tag.get_text(" ", strip=True)
        m = re.match(r"\[(L-\d+)\]", text)
        issue_id = m.group(1) if m else f"L-{issue_counter:02d}"
        title = text.split("]", 1)[1].strip() if "]" in text else text

        code_links = [a_tag["href"]]
        author_tag = li.find("em")
        author = author_tag.get_text(" ", strip=True) if author_tag else ""
        desc = f"{title}. {author}".strip()

        issues.append({
            "issue_id": issue_id,
            "title": title,
            "severity": "Low",
            "description": desc,
            "vulnerable_code_links": code_links
        })
        issue_counter += 1
    return issues


def extract_all_issues(soup: BeautifulSoup) -> list:
    """Scans all sections and extracts issues of all severities."""
    all_issues = []
    all_issues += extract_high_medium_issues(soup)
    all_issues += extract_low_non_critical_issues(soup)
    return all_issues


def extract_high_medium_issues(soup: BeautifulSoup) -> list:
    """Extracts High and Medium risk issues."""
    issues = []
    for prefix in ["high-risk-findings", "medium-risk-findings"]:
        for block in soup.find_all("h1", id=True):
            if block["id"].startswith(prefix):
                sib = block.find_next_sibling()
                while sib and sib.name != "h1":
                    if sib.name == "h2":
                        issue = parse_issue_from_h2(sib)
                        if issue:
                            issues.append(issue)
                    sib = sib.find_next_sibling()
    return issues


def extract_low_non_critical_issues(soup: BeautifulSoup) -> list:
    """Extracts Low Risk and Non-Critical issues."""
    issues = []
    for block in soup.find_all("h1", id=True):
        h1_id = block["id"].lower()
        if "low-risk" in h1_id or "non-critical" in h1_id:
            sib = block.find_next_sibling()
            issue_counter = 1

            while sib and sib.name != "h1":
                if sib.name == "h2":
                    issue = parse_issue_from_h2(sib)
                    if issue:
                        issue["severity"] = "Low"
                        issues.append(issue)
                        issue_counter += 1
                    elif re.match(r"\[\d+\]", sib.get_text(" ", strip=True)):
                        issues.append(parse_simple_issue_block(sib, issue_counter))
                        issue_counter += 1

                elif sib.name == "ul":
                    issues += parse_issue_list_items(sib, issue_counter)
                    issue_counter += len(issues)

                sib = sib.find_next_sibling()
    return issues


# =====================================================
# 4. MAIN PARSING LOGIC
# =====================================================

def parse_code4rena_report(url: str) -> dict | None:
    """Downloads and parses a single Code4rena report page."""
    print(f"\nFetching {url} ...")
    resp = requests.get(url)
    if resp.status_code != 200:
        print(f"HTTP {resp.status_code} — skipping {url}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    scope = parse_scope_section(soup)
    if not scope:
        print(f"Skipping {url.split('/')[-1]} — no valid <h1 id='scope'> or Solidity mention.")
        return None

    title_tag = soup.find("h1")
    title = title_tag.get_text(" ", strip=True) if title_tag else None
    issues = extract_all_issues(soup)

    return {"report_title": title, "scope": scope, "issues": issues}


# =====================================================
# 5. FILE HANDLING AND EXECUTION
# =====================================================

def load_urls_from_file(input_file: str) -> list[str]:
    """Reads URLs from a text file, ignoring empty lines and comments."""
    with open(input_file, "r", encoding="utf-8") as f:
        return [u.strip() for u in f if u.strip() and not u.startswith("#")]


def save_json(data: dict, out_file: str):
    """Writes parsed data to a JSON file."""
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def process_reports_from_file(input_file, out_dir="reports_parser"):
    """Reads a list of report URLs and parses each into JSON files."""
    if not os.path.exists(input_file):
        print(f"Input file not found: {input_file}")
        sys.exit(1)

    urls = load_urls_from_file(input_file)
    os.makedirs(out_dir, exist_ok=True)

    for url in urls:
        try:
            data = parse_code4rena_report(url)
            if not data:
                continue

            slug = url.rstrip("/").split("/")[-1]
            out_file = os.path.join(out_dir, f"{slug}.json")
            save_json(data, out_file)

            sc = data["scope"]
            print(f"{slug}: repo={sc['repository']}, contracts={sc['contracts']}, LOC={sc['lines_solidity']}, issues={len(data['issues'])}")
        except Exception as e:
            print(f"Error parsing {url}: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python parser_reports.py <urls_file.txt>")
        sys.exit(1)
    process_reports_from_file(sys.argv[1])
