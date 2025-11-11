#!/usr/bin/env python3
import os
import pandas as pd
from pathlib import Path

# ===============================
# CONFIGURATION
# ===============================
INPUT_DIR = "lizard_metrics_output"
OUTPUT_DIR = "C4Audit_metrics"
os.makedirs(OUTPUT_DIR, exist_ok=True)

MERGED_FILE = Path(OUTPUT_DIR) / "merged_lizard_classified.csv"
MISSING_FILE = Path(OUTPUT_DIR) / "missing_repositories.txt"
NO_CODE_FILE = Path(OUTPUT_DIR) / "repositories_without_code.txt"

EXTERNAL_DEP_PATHS = [
    "node_modules", "out", "artifacts", "build", "cache",
    ".openzeppelin", "venv", "__pycache__", "dependencies",
    "@openzeppelin", "gitmodules"
]

TEST_PATHS = [
    "test", "tests", "testing", "integration-tests", "spec",
    "mock", "mocks", "harness", "certora", "helper", "helpers"
]

DEPLOY_PATHS = ["deploy", "deployment", "deployments", "script", "scripts", "tasks", "migrations"]

CODE_FOLDERS = ["src", "contracts"]
CODE_EXTS = [".sol"]
SCRIPT_EXTS = [".js", ".ts", ".py", ".mjs", ".cjs"]


# ===============================
# CLASSIFICATION HELPERS
# ===============================
def is_external_dependency(rel_path, relevant_parts):
    if any(p in rel_path for p in EXTERNAL_DEP_PATHS):
        return True
    if "lib" in relevant_parts:
        lib_index = relevant_parts.index("lib")
        if not any(x in relevant_parts[:lib_index] for x in CODE_FOLDERS):
            return True
    return False


def is_test_file(rel_path):
    if any(f"{folder}/" in rel_path for folder in ["src/tests", "src/test", "contracts/tests", "contracts/test"]):
        return True
    if any(term in rel_path for term in TEST_PATHS):
        return True
    if rel_path.endswith(".t.sol"):
        return True
    return False


def is_deploy_or_script(rel_path):
    return any(term in rel_path for term in DEPLOY_PATHS) or rel_path.endswith(tuple(SCRIPT_EXTS))


def classify_source(filepath: str, repo_has_code_folder: bool) -> str:
    """
    Classify file according to its path and extension.
    """
    path = str(filepath).lower().replace("\\", "/")
    parts = [p for p in path.split("/") if p not in ("", ".", "..")]
    relevant_parts = parts[4:] if len(parts) > 4 else parts
    rel_path = "/".join(relevant_parts)

    if is_external_dependency(rel_path, relevant_parts):
        return "ExternalDependency"
    if is_test_file(rel_path):
        return "Test"
    if is_deploy_or_script(rel_path):
        return "DeployScript"

    if any(folder + "/" in rel_path for folder in CODE_FOLDERS):
        if any(term in rel_path for term in TEST_PATHS):
            return "Test"
        if "lib" in relevant_parts:
            lib_index = relevant_parts.index("lib")
            if any(x in relevant_parts[:lib_index] for x in CODE_FOLDERS):
                return "Code"
        return "Code" if rel_path.endswith(tuple(CODE_EXTS)) else "Other"

    if rel_path.endswith(tuple(CODE_EXTS)):
        return "Code" if not repo_has_code_folder else "Other"
    return "Other"


# ===============================
# DATA PROCESSING HELPERS
# ===============================
def load_and_prepare_csv(csv_file):
    try:
        df = pd.read_csv(csv_file)
        if "File" not in df.columns or "NLOC" not in df.columns or df.empty:
            return None, "invalid"
        df["NLOC"] = pd.to_numeric(df["NLOC"], errors="coerce").fillna(0)
        df_grouped = df.groupby("File", as_index=False).agg({"NLOC": "sum"})
        return df_grouped, None
    except Exception as e:
        return None, str(e)


def detect_code_folder(all_paths):
    return any(f in p for f in ["src/", "contracts/"] for p in all_paths)


def save_grouped_metrics(grouped_df):
    for source in grouped_df["Source"].unique():
        df_source = grouped_df[grouped_df["Source"] == source][["Repo", "LOC", "Contracts"]]
        output_path = Path(OUTPUT_DIR) / f"{source}_metrics.csv"
        df_source.to_csv(output_path, index=False)
        print(f"{source}: {len(df_source)} rows saved at {output_path}")


def check_consistency(merged_df):
    print("\nChecking classification consistency...")

    invalid_code = merged_df[
        (merged_df["Source"] == "Code") & (~merged_df["File"].str.lower().str.endswith(".sol"))
    ]
    if not invalid_code.empty:
        invalid_code.to_csv(Path(OUTPUT_DIR) / "invalid_code_classifications.csv", index=False)
        print(f"{len(invalid_code)} file(s) classified as Code are not .sol (saved).")
    else:
        print("All files classified as Code have .sol extension.")

    misplaced_tests = merged_df[
        (merged_df["Source"].isin(["Test", "DeployScript"]))
        & (merged_df["File"].str.lower().str.endswith(".sol"))
    ]
    if not misplaced_tests.empty:
        misplaced_tests.to_csv(Path(OUTPUT_DIR) / "misplaced_sol_files.csv", index=False)
        print(f"{len(misplaced_tests)} .sol file(s) incorrectly classified (saved).")
    else:
        print("No .sol files incorrectly classified as Test/DeployScript.")


# ===============================
# MAIN
# ===============================
def main():
    csv_files = list(Path(INPUT_DIR).glob("*.csv"))
    if not csv_files:
        print(f"No CSV files found in {INPUT_DIR}")
        return

    all_rows, processed_repos, skipped_repos = [], [], []

    for csv_file in csv_files:
        repo_name = csv_file.stem
        print(f"Processing {repo_name}...")

        df_grouped, error = load_and_prepare_csv(csv_file)
        if error:
            print(f"Skipping {repo_name}: {error}")
            skipped_repos.append(repo_name)
            continue

        all_paths = df_grouped["File"].astype(str).str.lower().tolist()
        repo_has_code_folder = detect_code_folder(all_paths)
        if not repo_has_code_folder:
            print(f"{repo_name}: no src/contracts found, enabling .sol → Code exception")

        df_grouped["Repo"] = repo_name
        df_grouped["Source"] = df_grouped["File"].apply(lambda f: classify_source(f, repo_has_code_folder))

        all_rows.append(df_grouped[["Repo", "NLOC", "File", "Source"]])
        processed_repos.append(repo_name)

    if not all_rows:
        print("No valid data found.")
        return

    merged_df = pd.concat(all_rows, ignore_index=True).sort_values(by=["Repo", "File"])
    merged_df.to_csv(MERGED_FILE, index=False)
    print(f"\nMerged file saved at: {MERGED_FILE}")
    print(f"Total rows: {len(merged_df)}")

    grouped = merged_df.groupby(["Repo", "Source"], as_index=False).agg(
        LOC=("NLOC", "sum"), Contracts=("File", "count")
    )
    save_grouped_metrics(grouped)
    check_consistency(merged_df)

    summarize_repositories(csv_files, processed_repos, grouped, merged_df)


# ===============================
# SUMMARY AND REPORTING
# ===============================
def summarize_repositories(csv_files, processed_repos, grouped, merged_df):
    all_repo_names = sorted([csv.stem for csv in csv_files])
    found_repos = set(processed_repos)
    missing_repos = [r for r in all_repo_names if r not in found_repos]

    if missing_repos:
        with open(MISSING_FILE, "w", encoding="utf-8") as f:
            for repo in missing_repos:
                f.write(repo + "\n")
        print(f"\nRepositories without metrics saved in {MISSING_FILE}")
        print(f"Total missing: {len(missing_repos)}")
    else:
        print("\nAll repositories processed successfully.")

    repos_with_code = set(grouped[grouped["Source"] == "Code"]["Repo"].unique())
    all_repos = set(grouped["Repo"].unique())
    repos_without_code = sorted(list(all_repos - repos_with_code))

    if repos_without_code:
        with open(NO_CODE_FILE, "w", encoding="utf-8") as f:
            for repo in repos_without_code:
                f.write(repo + "\n")
        print(f"\nRepositories without any file classified as 'Code': {len(repos_without_code)}")
    else:
        print("\nAll repositories have files classified as 'Code'.")

    summary = merged_df.groupby("Source", as_index=False)["NLOC"].sum().sort_values(by="NLOC", ascending=False)
    print("\nTotal LOC summary by category:")
    print(summary.to_string(index=False))
    print(f"\nTotal processed: {len(processed_repos)} / {len(csv_files)}")


# ===============================
# OUTLIER FIX
# ===============================
def fix_outlier_repository(repo_name: str):
    print(f"\nFixing outlier repository: {repo_name}")

    if not MERGED_FILE.exists():
        print(f"File {MERGED_FILE} not found — run main() first.")
        return

    df = pd.read_csv(MERGED_FILE)
    if not {"Repo", "File", "Source"}.issubset(df.columns):
        print("Unexpected CSV structure.")
        return

    mask_repo = df["Repo"].astype(str) == repo_name
    if not mask_repo.any():
        print(f"No records found for {repo_name}.")
        return

    df_repo = df[mask_repo].copy()

    def fix_class(path: str) -> str:
        p = str(path).lower()
        if "contracts-full/test" in p:
            return "Test"
        if "contracts-full" in p:
            return "Code"
        if any(x in p for x in ["contracts-hardhat", "test-forge", "test-hardhat"]):
            return "Test"
        return "Other"

    df.loc[mask_repo, "Source"] = df_repo["File"].apply(fix_class)
    df.to_csv(MERGED_FILE, index=False)
    print("Correction saved. Rebuilding metrics...")

    grouped = df.groupby(["Repo", "Source"], as_index=False).agg(LOC=("NLOC", "sum"), Contracts=("File", "count"))
    save_grouped_metrics(grouped)
    print("Metrics updated after outlier correction.")


# ===============================
# MULTISYSTEM FIX
# ===============================
def fix_multisystem_repository(repo_name: str):
    print(f"\nFixing multisystem repository: {repo_name}")

    if not MERGED_FILE.exists():
        print(f"File {MERGED_FILE} not found — run main() first.")
        return

    df = pd.read_csv(MERGED_FILE)
    if not {"Repo", "File", "Source", "NLOC"}.issubset(df.columns):
        print("Unexpected CSV structure.")
        return

    mask_repo = df["Repo"].astype(str) == repo_name.split("/")[1]
    if not mask_repo.any():
        print(f"No records found for {repo_name}.")
        return

    df_repo = df[mask_repo].copy()
    subsystems = ["proposals", "silo-core", "silo-oracles", "silo-vaults", "ve-silo"]

    def classify_multisystem(path: str) -> str:
        p = str(path).lower()
        if not any(f"/{s}/" in p for s in subsystems):
            return "Other"
        if any(x in p for x in ["node_modules", "artifacts", "build", "lib", "dependencies", "__pycache__"]):
            return "ExternalDependency"
        if any(x in p for x in ["test/", "tests/", "testing/", ".t.sol", "test_", "mock", "harness", "certora"]):
            return "Test"
        if any(x in p for x in ["deploy/", "scripts/", "tasks/", "migrations/"]):
            return "DeployScript"
        if any(x in p for x in ["src/", "contracts/"]):
            return "Code"
        if p.endswith(".sol"):
            return "Code"
        return "Other"

    df_repo["NewSource"] = df_repo["File"].apply(classify_multisystem)
    df.loc[mask_repo, "Source"] = df_repo["NewSource"]
    df.to_csv(MERGED_FILE, index=False)
    print("Classification updated for multisystem repository.")

    grouped = df.groupby(["Repo", "Source"], as_index=False).agg(LOC=("NLOC", "sum"), Contracts=("File", "count"))
    save_grouped_metrics(grouped)
    print("Metrics regenerated after multisystem correction.")


if __name__ == "__main__":
    main()
    # these were two outliers that lizard could not compute the metrics
    fix_outlier_repository(INPUT_DIR + "/2022-05-alchemix")
    fix_multisystem_repository(INPUT_DIR + "/2025-03-silo-finance")
