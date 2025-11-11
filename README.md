
**Dataset**: C4Audit is publicly available at Zenodo: https://doi.org/10.5281/zenodo.17571170

# **C4Audit – Dataset Description**

**C4Audit** is a curated, structured dataset that bridges real-world smart contract audit reports with their corresponding source code and quantitative code metrics.

It was built from **Code4rena** audit contests (a large community-driven security auditing platform) and is organized in **three sub-datasets**, where:

---

**C4Audit-Reports**: Contains a folder named `reports_parser`. For each audit, there is a report (e.g., `reports_parser/2025-03-silo-finance/` contains the report for this audit). The names of the directories are based on the report identifier: [https://code4rena.com/reports/2025-03-silo-finance](https://code4rena.com/reports/2025-03-silo-finance)


**C4Audit-Repos**: Contains a folder named `repositories`. Similarly, we followed the same structure for the repositories to allow identifying the code for the respective report.

**C4Audit-Metrics**: Contains a folder named `C4Audit_metrics`. This folder consists of a subfolder with code metrics for each audit in CSV format and also additional CSV files with classifications for the type of code. The content of each sub-dataset is detailed in the next sections.


## **1. C4Audit-Reports — Parsed Audit Reports**

Structured JSON files derived from the original Code4rena audit reports.
Each parsed report includes:

### **Metadata**

* Audit name, date, protocol name
* Repository links
* Scope information (number of contracts, LOC)

### **Vulnerability Findings**

All issues identified by wardens, categorized by severity (High, Medium, Low).

### **Issue Attributes**

* `issue_id`: unique identifier
* `title`: short description of the finding
* `severity`: severity classification
* `description`: natural language explanation of the bug
* `vulnerable_code_links`: URLs pointing to affected files and line numbers in the audited repository

These structured fields enable linking each vulnerability directly to its corresponding source file and function in the associated GitHub repository.

**Example — audit `2024-02-wise-lending`:**

```json
{
  "report_title": "Wise Lending Findings & Analysis Report",
  "scope": {
    "contracts": 44,
    "lines_solidity": 6326,
    "repositories": [
      "https://github.com/code-423n4/2024-02-wise-lending"
    ]
  },
  "issues": [
    {
      "issue_id": "H-01",
      "title": "Exploitation of the receive Function to Steal Funds",
      "severity": "High",
      "description": "...The WiseLending contract incorporates a reentrancy guard through its syncPool modifier...",
      "vulnerable_code_links": [
        "https://github.com/code-423n4/2024-02-wise-lending/blob/.../contracts/WiseLending.sol#L49",
        "https://github.com/code-423n4/2024-02-wise-lending/blob/.../contracts/WiseLending.sol#L636",
        "https://github.com/code-423n4/2024-02-wise-lending/blob/.../contracts/TransferHub/SendValueHelper.sol#L12"
      ]
    },
    {
      "issue_id": "H-02",
      "title": "User can erase their position debt for free",
      "severity": "High",
      "description": "...In the function FeeManager.paybackBadDebtNoReward(), insufficient validation...",
      "vulnerable_code_links": [ ... ]
    }
  ]
}
```

> The issue `H-01` includes a title, detailed description, and several links pointing to the affected code paths, which span multiple functions in the execution flow.

---

## **2. C4Audit-Repos — Linked Repositories**

Each audit links to one or more GitHub repositories that were within scope during the audit.

For reproducibility, the dataset stores:

* Repository URLs (in the report),
* Commit hashes (if available, in the repo README file),
* A local copy of the source code.

All the reports point to: [https://github.com/code-423n4](https://github.com/code-423n4) + the audit name (e.g., `2022-11-debtdao`).

Sometimes, the actual code to be cloned was listed in the README file.

> The cloning process required **manual cloning for 34 repositories** because of structural differences that made automation difficult.

### **Examples**

* **Non-standard structure:**
  `2022-11-debtdao` — smart contracts hosted in an external repo referenced in its README.
* **Standard structure:**
  `2025-07-lido-finance` — follows the canonical Code4rena layout.

---

## **3. C4Audit-Metrics**

### **4.1 Code Metrics (Lizard Output)**

Quantitative metrics are extracted for every file and function using the **Lizard** static analysis tool.
Each audit directory contains CSV files with raw and aggregated metrics.

#### **Function-level metrics (`functions.csv`)**

* `function_name`
* `nloc` — lines of code (excluding comments)
* `ccn` — cyclomatic complexity
* `token_count` and `parameter_count`
* `start_line` and `end_line` of the function

---

### **4.2 Dataset Organization**

We also classified the code files for each repository (from Lizard CSV outputs) into categories:

| Type                    | Description                                                                 |
| ----------------------- | --------------------------------------------------------------------------- |
| **Code/**               | Business logic smart contracts (`.sol` files within `src/` or `contracts/`) |
| **Test/**               | Testing and validation files (`test/`, `.t.sol`, or mocks)                  |
| **DeployScript/**       | Deployment and automation scripts (`scripts/`, `deploy*/`, `tasks/`)        |
| **ExternalDependency/** | Imported libraries and third-party packages (`lib/`, `node_modules/`, etc.) |

This hierarchical classification enables fine-grained analyses of modularity, dependency usage, and testing practices in DeFi protocols.

---

#### **File structure**

```bash
C4Audit_metrics/
├── Lizard_metrics_csv/
│   ├── 2024-12-lido-oracle/
│   ├── 2025-03-silo-finance/
│   └── ...
├── Code_metrics.csv
├── Test_metrics.csv
├── DeployScript_metrics.csv
├── ExternalDependency_metrics.csv
└── merged_lizard_classified.csv
```

The file `merged_lizard_classified.csv` summarizes how many contracts per repository were found.
This information is aggregated into the final dataset-level statistics.

---

## **5. Dataset Features and Applications**

**Scale**

* 342 audits
* ≈10k smart contracts as code (including test contracts)
* 15k+ test files (`.sol`, `.py`, `.ts`, `.js`)
* ≈6k deployment scripts

**Linkage**: Ground-truth vulnerabilities mapped to actual source code and metrics.

**Use Cases**: 

* Empirical studies on code complexity, modularity, and testing practices
* Machine learning models for automated vulnerability detection
* Large-scale benchmarking of static analysis tools
* Mining studies on DeFi ecosystem architecture and security patterns

