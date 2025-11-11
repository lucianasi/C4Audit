#!/usr/bin/env python3
"""
Parser de relatórios Code4rena (versão final)
- Lê URLs de um arquivo .txt
- Extrai escopo (repo, contratos, LOC)
- Extrai issues (High, Medium, Low, etc.)
- Só ignora relatórios sem tag <h1 id="scope"> ou sem menção a Solidity
"""

import requests
from bs4 import BeautifulSoup
import re
import json
import os
import sys


# =====================================================
# 1. UTILITÁRIOS
# =====================================================

def normalize_number(num_str: str) -> int:
    """Limpa vírgulas, til e converte para int seguro."""
    if not num_str:
        return 0
    num_str = re.sub(r"[^\d]", "", num_str)
    try:
        return int(num_str)
    except ValueError:
        return 0


def get_section_html(soup: BeautifulSoup, section_id: str) -> str | None:
    """Extrai o HTML de uma seção (<h1 id=...>) até o próximo <h1>."""
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


# =====================================================
# 2. PARSER DE ESCOPO
# =====================================================

def parse_repository_link(scope_soup: BeautifulSoup) -> str | None:
    """Extrai o link do repositório do escopo."""
    for a in scope_soup.find_all("a", href=True):
        href = a["href"]
        if "github.com" in href and "code-423n4" in href:
            return href
    return None


def parse_scope_section(soup: BeautifulSoup) -> dict | None:
    """
    Lê o conteúdo entre <h1 id="scope"> e o próximo <h1>.
    Se existir e mencionar Solidity, retorna sempre:
      - repository (ou None)
      - contracts (int, default 0)
      - lines_solidity (int, default 0)
    Caso a tag <h1 id="scope"> não exista, retorna None.
    """
    section_html = get_section_html(soup, "scope")
    if not section_html:
        return None  # tag não existe → ignorar relatório

    scope_soup = BeautifulSoup(section_html, "html.parser")
    scope_text = scope_soup.get_text(" ", strip=True)

    # Detecta se é Solidity (caso contrário, ignorar)
    if not re.search(r"\bSolidity\b", scope_text, re.IGNORECASE):
        return None

    scope = {
        "repository": parse_repository_link(scope_soup),
        "contracts": 0,
        "lines_solidity": 0,
    }

    # Contratos
    m_contracts = re.search(r"([\d,~]+)\s+(?:smart\s+)?contracts?", scope_text, re.IGNORECASE)
    if m_contracts:
        scope["contracts"] = normalize_number(m_contracts.group(1))

    # Linhas de código
    m_lines = re.search(
        r"([\d,~]+)\s+(?:source\s+lines|lines\s+of\s+Solidity|lines\s+of\s+Solidity\s+code|lines\s+of\s+code\s+written\s+in\s+Solidity)",
        scope_text,
        re.IGNORECASE,
    )
    if m_lines:
        scope["lines_solidity"] = normalize_number(m_lines.group(1))

    return scope


# =====================================================
# 3. PARSER DE ISSUES
# =====================================================

SEVERITY_MAP = {
    "H": "High",
    "M": "Medium",
    "L": "Low",
    "N": "Non-Critical",
    "G": "Gas"
}

def parse_issue_from_h2(tag) -> dict | None:
    """Extrai uma issue de um cabeçalho <h2>."""
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
        for a in sib.find_all("a", href=True):
            if "github.com" in a["href"]:
                code_links.append(a["href"])
        sib = sib.find_next_sibling()

    return {
        "issue_id": issue_id,
        "title": title,
        "severity": severity,
        "description": " ".join(desc_parts).strip(),
        "vulnerable_code_links": list(set(code_links))
    }

def parse_issues_from_tables(table, severity="Low") -> list:
    """Extrai issues de tabelas HTML."""
    issues = []
    rows = table.find_all("tr")
    for row in rows[1:]:
        cols = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
        if len(cols) >= 2:
            issue_id = f"{severity[0]}-{len(issues) + 1}"
            issues.append({
                "issue_id": issue_id,
                "title": cols[0],
                "severity": severity,
                "description": " ".join(cols[1:]),
                "vulnerable_code_links": []
            })
    return issues

def extract_all_issues(soup: BeautifulSoup) -> list:
    """Varre todas as seções de risco e extrai issues (High, Medium, Low, Non-Critical)."""
    all_issues = []

    # -------------------------
    # High e Medium
    # -------------------------
    for prefix in ["high-risk-findings", "medium-risk-findings"]:
        for block in soup.find_all("h1", id=True):
            if block["id"].startswith(prefix):
                sib = block.find_next_sibling()
                while sib and sib.name != "h1":
                    if sib.name == "h2":
                        issue = parse_issue_from_h2(sib)
                        if issue:
                            all_issues.append(issue)
                    sib = sib.find_next_sibling()

    # -------------------------
    # Low Risk e Non-Critical
    # -------------------------
    for block in soup.find_all("h1", id=True):
        h1_id = block["id"].lower()
        if "low-risk" in h1_id or "non-critical" in h1_id:
            sib = block.find_next_sibling()
            issue_counter = 1

            while sib and sib.name != "h1":
                # Caso 1: padrão normal [L-xx]
                if sib.name == "h2":
                    issue = parse_issue_from_h2(sib)
                    if issue:
                        issue["severity"] = "Low"
                        all_issues.append(issue)
                        issue_counter += 1
                    else:
                        # Caso 2: <h2> sem [L-xx], apenas [01], [02]
                        txt = sib.get_text(" ", strip=True)
                        if re.match(r"\[\d+\]", txt):
                            title = txt.split("]", 1)[1].strip()
                            code_links = [a["href"] for a in sib.find_all("a", href=True)]
                            desc_parts = []

                            next_tag = sib.find_next_sibling()
                            while next_tag and next_tag.name not in ["h2", "h1"]:
                                if next_tag.get_text(strip=True):
                                    desc_parts.append(next_tag.get_text(" ", strip=True))
                                for a in next_tag.find_all("a", href=True):
                                    if "github.com" in a["href"]:
                                        code_links.append(a["href"])
                                next_tag = next_tag.find_next_sibling()

                            all_issues.append({
                                "issue_id": f"L-{issue_counter:02d}",
                                "title": title,
                                "severity": "Low",
                                "description": " ".join(desc_parts).strip(),
                                "vulnerable_code_links": list(set(code_links))
                            })
                            issue_counter += 1

                # Caso 3: listas <ul><li> (antigos)
                elif sib.name == "ul":
                    for li in sib.find_all("li", recursive=False):
                        a_tag = li.find("a")
                        if not a_tag:
                            continue
                        text = a_tag.get_text(" ", strip=True)
                        m = re.match(r"\[(L-\d+)\]", text)
                        if m:
                            issue_id = m.group(1)
                            title = text.split("]", 1)[1].strip()
                        else:
                            issue_id = f"L-{issue_counter:02d}"
                            title = text
                            issue_counter += 1

                        code_links = [a_tag["href"]]
                        author_tag = li.find("em")
                        author = author_tag.get_text(" ", strip=True) if author_tag else ""
                        desc = f"{title}. {author}".strip()

                        all_issues.append({
                            "issue_id": issue_id,
                            "title": title,
                            "severity": "Low",
                            "description": desc,
                            "vulnerable_code_links": code_links
                        })

                sib = sib.find_next_sibling()

    return all_issues




# =====================================================
# 4. RUNNER PRINCIPAL
# =====================================================

def parse_code4rena_report(url: str) -> dict | None:
    print(f"\n📥 Fetching {url} ...")
    resp = requests.get(url)
    if resp.status_code != 200:
        print(f"❌ HTTP {resp.status_code} — skipping {url}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    scope = parse_scope_section(soup)
    if not scope:
        print(f"⚠️ Skipping {url.split('/')[-1]} — no valid <h1 id='scope'> or Solidity mention.")
        return None

    title_tag = soup.find("h1")
    title = title_tag.get_text(" ", strip=True) if title_tag else None
    issues = extract_all_issues(soup)

    return {"report_title": title, "scope": scope, "issues": issues}


def process_reports_from_file(input_file, out_dir="reports_parser"):
    if not os.path.exists(input_file):
        print(f"❌ Input file not found: {input_file}")
        sys.exit(1)

    with open(input_file, "r", encoding="utf-8") as f:
        urls = [u.strip() for u in f if u.strip() and not u.startswith("#")]

    os.makedirs(out_dir, exist_ok=True)

    for url in urls:
        try:
            data = parse_code4rena_report(url)
            if not data:
                continue  # pular relatórios sem escopo

            slug = url.rstrip("/").split("/")[-1]
            out_file = os.path.join(out_dir, f"{slug}.json")

            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            sc = data["scope"]
            print(f"✅ {slug}: repo={sc['repository']}, contracts={sc['contracts']}, LOC={sc['lines_solidity']}, issues={len(data['issues'])}")
        except Exception as e:
            print(f"❌ Error parsing {url}: {e}")


# =====================================================
# MAIN
# =====================================================
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python parser_reports.py <arquivo_de_urls.txt>")
        sys.exit(1)
    process_reports_from_file(sys.argv[1])
