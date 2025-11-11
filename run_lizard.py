#!/usr/bin/env python3
import os
import subprocess
import csv
import io
from pathlib import Path
import math

REPOS_DIR = "../C4Audit/repositories"
OUTPUT_DIR = "lizard_metrics_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

CSV_HEADER = [
    "NLOC", "CCN", "token", "Param", "Length",
    "location", "File", "function_name", "signature_func",
    "line_start", "line_end"
]

MISSING_FILE = Path(OUTPUT_DIR) / "missing_projects.txt"

# ============================================================
# Helper functions
# ============================================================

def get_source_files(repo_path):
    """
    Returns a list with absolute paths of all files
    with relevant extensions (.sol, .ts, .js, .py, .rs) inside repo_path.
    """
    valid_exts = (".sol", ".ts", ".js", ".py", ".rs")
    source_files = []

    for root, _, files in os.walk(repo_path):
        for f in files:
            if f.endswith(valid_exts):
                source_files.append(os.path.join(root, f))
    return source_files


def run_lizard_csv(file_list, chunk_size=3000):
    """
    Runs Lizard in CSV mode in parts if the number of files is too large.
    Splits the list into blocks of up to 'chunk_size' files.
    """
    if not file_list:
        return []

    all_rows = []

    def _run_chunk(chunk):
        cmd = ["lizard", "--csv"] + chunk
        try:
            result = subprocess.run(
                cmd,
                capture_output=True, text=True, encoding="utf-8", check=False
            )
            if result.returncode != 0:
                print(f"Error running Lizard (return={result.returncode})")
                print("STDERR:", result.stderr.strip()[:500])
                return []

            if not result.stdout.strip():
                print("Empty output from Lizard for this chunk.")
                return []

            output = result.stdout.strip().splitlines()
            sep = "\t" if "\t" in output[0] else ","
            reader = csv.reader(io.StringIO(result.stdout), delimiter=sep)
            rows = [r for r in reader if len(r) >= 10]
            return rows

        except OSError as e:
            # Captures "Argument list too long" error
            if "Argument list too long" in str(e):
                print("Argument list too long — splitting into smaller chunks...")
                return []
            else:
                print(f"Unexpected error: {e}")
                return []
        except Exception as e:
            print(f"Exception while running Lizard: {e}")
            return []

    try:
        # If too large, split into chunks
        if len(file_list) > chunk_size:
            total_chunks = math.ceil(len(file_list) / chunk_size)
            print(f"File list too large ({len(file_list)}). "
                  f"Splitting into {total_chunks} parts of up to {chunk_size} files each.")
            for i in range(total_chunks):
                part = file_list[i * chunk_size:(i + 1) * chunk_size]
                print(f"   Running chunk {i+1}/{total_chunks} with {len(part)} files...")
                chunk_rows = _run_chunk(part)
                all_rows.extend(chunk_rows)
        else:
            all_rows.extend(_run_chunk(file_list))

    except Exception as e:
        print(f"General failure in run_lizard_csv: {e}")

    return all_rows


def parse_lizard_row(raw_row):
    """
    Converts a raw Lizard CSV row (list) into a standardized dictionary.
    """
    try:
        if len(raw_row) < 10:
            return None
        return {
            "NLOC": raw_row[0],
            "CCN": raw_row[1],
            "token": raw_row[2],
            "Param": raw_row[3],
            "Length": raw_row[4],
            "location": raw_row[5],
            "File": raw_row[6] if len(raw_row) > 6 else "",
            "function_name": raw_row[7] if len(raw_row) > 7 else "",
            "signature_func": raw_row[8] if len(raw_row) > 8 else "",
            "line_start": raw_row[-2] if len(raw_row) >= 2 else "",
            "line_end": raw_row[-1] if len(raw_row) >= 1 else ""
        }
    except Exception:
        return None


def get_project_paths(base_dir):
    """
    Returns a dictionary {project_name: [subpaths]}.
    """
    projects = {}
    for entry in os.listdir(base_dir):
        project_root = os.path.join(base_dir, entry)
        if not os.path.isdir(project_root):
            continue

        subdirs = []
        for sub in os.listdir(project_root):
            subdir = os.path.join(project_root, sub)
            if os.path.isdir(subdir):
                subdirs.append(subdir)

        if not subdirs:
            subdirs = [project_root]

        projects[entry] = subdirs
    return projects


# ============================================================
# Main execution
# ============================================================

def main():
    projects = get_project_paths(REPOS_DIR)
    if not projects:
        print("No projects found.")
        return

    processed = []
    failed = []
    empty = []

    for project_name, subdirs in projects.items():
        print(f"\nAnalyzing project: {project_name}")
        all_rows = []

        for repo in subdirs:
            print(f"   Searching for source files in {repo}")
            files = get_source_files(repo)

            if not files:
                print(f"   No source files found in {repo}")
                continue

            print(f"   {len(files)} files found. Running Lizard...")
            raw_rows = run_lizard_csv(files)

            if not raw_rows:
                print(f"   No output for {repo}")
                continue

            parsed = [parse_lizard_row(r) for r in raw_rows if parse_lizard_row(r)]
            all_rows.extend(parsed)

        if not all_rows:
            print(f"No valid data found for {project_name}")
            empty.append(project_name)
            continue

        try:
            csv_path = Path(OUTPUT_DIR) / f"{project_name}.csv"
            with open(csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
                writer.writeheader()
                writer.writerows(all_rows)
            print(f"CSV generated: {csv_path} ({len(all_rows)} functions)")
            processed.append(project_name)
        except Exception as e:
            print(f"Failed to save {project_name}: {e}")
            failed.append(project_name)

    # ============================================================
    # Final report
    # ============================================================

    total = len(projects)
    ok = len(processed)
    fail = len(failed)
    empty_count = len(empty)

    print("\nFINAL SUMMARY")
    print(f"  Total projects found: {total}")
    print(f"  Successful: {ok}")
    print(f"  Empty (no functions): {empty_count}")
    print(f"  Failed: {fail}")
    print(f"  Output saved in: {OUTPUT_DIR}")

    missing = set(projects.keys()) - set(processed)
    if missing:
        with open(MISSING_FILE, "w", encoding="utf-8") as f:
            for name in sorted(missing):
                f.write(name + "\n")

        print(f"\n{len(missing)} projects did not generate a CSV file.")
        print(f"List saved in: {MISSING_FILE}")
        print("Examples:", list(missing)[:10])
    else:
        print("\nAll projects successfully generated CSV files.")


if __name__ == "__main__":
    main()
