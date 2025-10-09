#!/usr/bin/env python3
"""
Script to check OpenEdx repositories for specific packages.
"""

import requests
import json
import sys
import os
import argparse
from typing import List, Dict, Set

# Read packages from target_packages.txt
def load_target_packages() -> List[str]:
    """Load target packages from target_packages.txt."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "target_packages.txt")

    packages = []
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    packages.append(line)
    return packages

def load_target_branches() -> List[str]:
    """Load target branches from target_branches.txt."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(script_dir, "target_branches.txt")

    branches = []
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    branches.append(line)
    return branches

TARGET_PACKAGES = load_target_packages()
TARGET_BRANCHES = load_target_branches()

# GitHub API base URL
GITHUB_API_BASE = "https://api.github.com"
ORG_NAME = "openedx"

# GitHub token (optional, for higher rate limits)
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")

# Setup headers for API requests
HEADERS = {}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"token {GITHUB_TOKEN}"


def get_all_repos(org: str) -> List[Dict]:
    """Fetch all repositories for the organization."""
    repos = []
    page = 1
    per_page = 100

    print(f"Fetching repositories from {org}...")

    while True:
        url = f"{GITHUB_API_BASE}/orgs/{org}/repos"
        params = {"page": page, "per_page": per_page, "type": "all"}

        response = requests.get(url, params=params, headers=HEADERS)

        if response.status_code != 200:
            print(f"Error fetching repos: {response.status_code}")
            print(response.text)
            break

        page_repos = response.json()

        if not page_repos:
            break

        repos.extend(page_repos)
        page += 1

        print(f"Fetched {len(repos)} repositories so far...")

    print(f"Total repositories found: {len(repos)}\n")
    return repos


def get_repo_branches(repo_name: str) -> List[str]:
    """Fetch all branches for a repository."""
    branches = []
    page = 1
    per_page = 100

    while True:
        url = f"{GITHUB_API_BASE}/repos/{ORG_NAME}/{repo_name}/branches"
        params = {"page": page, "per_page": per_page}

        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=10)

            if response.status_code != 200:
                break

            page_branches = response.json()

            if not page_branches:
                break

            branches.extend([b["name"] for b in page_branches])
            page += 1

        except (requests.exceptions.Timeout, requests.exceptions.RequestException):
            break

    return branches


def check_package_json(repo_name: str, branch: str) -> Dict[str, List[str]]:
    """Check package.json for target packages."""
    found_packages = {}

    # Try to fetch package.json from root
    url = f"https://raw.githubusercontent.com/{ORG_NAME}/{repo_name}/{branch}/package.json"

    try:
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            try:
                package_data = response.json()

                # Check dependencies
                all_deps = {}
                all_deps.update(package_data.get("dependencies", {}))
                all_deps.update(package_data.get("devDependencies", {}))
                all_deps.update(package_data.get("peerDependencies", {}))

                for target_pkg in TARGET_PACKAGES:
                    # Handle both formats: color@5.0.1 and @scope/package@5.0.1
                    if target_pkg.startswith("@"):
                        # Scoped package: @scope/package@version
                        parts = target_pkg.rsplit("@", 1)
                        pkg_name = parts[0]
                        pkg_version = parts[1]
                    else:
                        # Regular package: package@version
                        pkg_name, pkg_version = target_pkg.rsplit("@", 1)

                    if pkg_name in all_deps:
                        installed_version = all_deps[pkg_name]
                        exact_match = installed_version == pkg_version or installed_version == f"^{pkg_version}" or installed_version == f"~{pkg_version}"

                        # Check if any version is installed (for warnings)
                        # Strip version ranges like ^, ~, >=, etc.
                        installed_clean = installed_version.lstrip("^~>=<")
                        any_version_match = pkg_name in all_deps

                        if pkg_name not in found_packages:
                            found_packages[pkg_name] = []
                        found_packages[pkg_name].append({
                            "target_version": pkg_version,
                            "installed_version": installed_version,
                            "exact_match": exact_match,
                            "any_version_match": any_version_match,
                            "source": "package.json"
                        })

            except json.JSONDecodeError:
                pass

    except requests.exceptions.Timeout:
        pass
    except requests.exceptions.RequestException:
        pass

    return found_packages


def check_lock_files(repo_name: str, branch: str) -> Dict[str, List[str]]:
    """Check package-lock.json and yarn.lock for target packages."""
    found_packages = {}

    # Check package-lock.json
    package_lock_url = f"https://raw.githubusercontent.com/{ORG_NAME}/{repo_name}/{branch}/package-lock.json"
    try:
        response = requests.get(package_lock_url, timeout=10)
        if response.status_code == 200:
            try:
                lock_data = response.json()

                # Check both lockfileVersion 1 and 2+ formats
                packages = lock_data.get("packages", {})
                dependencies = lock_data.get("dependencies", {})

                for target_pkg in TARGET_PACKAGES:
                    # Handle both formats: color@5.0.1 and @scope/package@5.0.1
                    if target_pkg.startswith("@"):
                        # Scoped package: @scope/package@version
                        parts = target_pkg.rsplit("@", 1)
                        pkg_name = parts[0]
                        pkg_version = parts[1]
                    else:
                        # Regular package: package@version
                        pkg_name, pkg_version = target_pkg.rsplit("@", 1)

                    # Check lockfileVersion 2+ format (packages)
                    for pkg_path, pkg_info in packages.items():
                        if pkg_path == f"node_modules/{pkg_name}" or pkg_path == pkg_name:
                            installed_version = pkg_info.get("version", "")
                            if installed_version:
                                exact_match = installed_version == pkg_version
                                any_version_match = True
                                if pkg_name not in found_packages:
                                    found_packages[pkg_name] = []
                                found_packages[pkg_name].append({
                                    "target_version": pkg_version,
                                    "installed_version": installed_version,
                                    "exact_match": exact_match,
                                    "any_version_match": any_version_match,
                                    "source": "package-lock.json"
                                })
                                break

                    # Check lockfileVersion 1 format (dependencies)
                    if pkg_name not in found_packages and pkg_name in dependencies:
                        installed_version = dependencies[pkg_name].get("version", "")
                        if installed_version:
                            exact_match = installed_version == pkg_version
                            any_version_match = True
                            if pkg_name not in found_packages:
                                found_packages[pkg_name] = []
                            found_packages[pkg_name].append({
                                "target_version": pkg_version,
                                "installed_version": installed_version,
                                "exact_match": exact_match,
                                "any_version_match": any_version_match,
                                "source": "package-lock.json"
                            })
            except json.JSONDecodeError:
                pass
    except (requests.exceptions.Timeout, requests.exceptions.RequestException):
        pass

    # Check yarn.lock
    yarn_lock_url = f"https://raw.githubusercontent.com/{ORG_NAME}/{repo_name}/{branch}/yarn.lock"
    try:
        response = requests.get(yarn_lock_url, timeout=10)
        if response.status_code == 200:
            yarn_content = response.text

            for target_pkg in TARGET_PACKAGES:
                # Handle both formats: color@5.0.1 and @scope/package@5.0.1
                if target_pkg.startswith("@"):
                    # Scoped package: @scope/package@version
                    parts = target_pkg.rsplit("@", 1)
                    pkg_name = parts[0]
                    pkg_version = parts[1]
                else:
                    # Regular package: package@version
                    pkg_name, pkg_version = target_pkg.rsplit("@", 1)

                # Parse yarn.lock format (simplified parsing)
                lines = yarn_content.split("\n")
                i = 0
                while i < len(lines):
                    line = lines[i].strip()
                    # Look for package declaration (e.g., "package-name@version:")
                    if line.startswith(f'"{pkg_name}@') or line.startswith(f"{pkg_name}@"):
                        # Next lines contain version info
                        for j in range(i + 1, min(i + 10, len(lines))):
                            version_line = lines[j].strip()
                            if version_line.startswith("version "):
                                installed_version = version_line.split("version ")[1].strip('"')
                                exact_match = installed_version == pkg_version
                                any_version_match = True
                                if pkg_name not in found_packages:
                                    found_packages[pkg_name] = []
                                found_packages[pkg_name].append({
                                    "target_version": pkg_version,
                                    "installed_version": installed_version,
                                    "exact_match": exact_match,
                                    "any_version_match": any_version_match,
                                    "source": "yarn.lock"
                                })
                                break
                        break
                    i += 1
    except (requests.exceptions.Timeout, requests.exceptions.RequestException):
        pass

    return found_packages


def main():
    """Main function to orchestrate the package checking."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Check OpenEdx repositories for specific packages")
    parser.add_argument('--repo', type=str, help='Specific repository name to check (e.g., "edx-platform"). If not provided, checks all repositories.')
    args = parser.parse_args()

    print("=" * 80)
    print("OpenEdx Repository Package Checker")
    print("=" * 80)
    print("\nTarget packages:")
    for pkg in TARGET_PACKAGES:
        print(f"  - {pkg}")

    if TARGET_BRANCHES:
        print("\nTarget branches:")
        for branch in TARGET_BRANCHES:
            print(f"  - {branch}")
    else:
        print("\nChecking default branch only (no target_branches.txt found)")

    if args.repo:
        print(f"\nChecking specific repository: {args.repo}")
    else:
        print(f"\nChecking all repositories in {ORG_NAME} organization")

    print("\n" + "=" * 80 + "\n")

    # Get repositories
    if args.repo:
        # Check single repository
        url = f"{GITHUB_API_BASE}/repos/{ORG_NAME}/{args.repo}"
        response = requests.get(url, headers=HEADERS)

        if response.status_code != 200:
            print(f"Error fetching repository '{args.repo}': {response.status_code}")
            print(response.text)
            sys.exit(1)

        repos = [response.json()]
        print(f"Found repository: {args.repo}\n")
    else:
        # Get all repositories
        repos = get_all_repos(ORG_NAME)

    if not repos:
        print("No repositories found or error occurred.")
        sys.exit(1)

    # Check each repository for target packages
    results = []

    for idx, repo in enumerate(repos, 1):
        repo_name = repo["name"]
        default_branch = repo.get("default_branch", "master")

        print(f"[{idx}/{len(repos)}] Checking {repo_name}...")

        # Determine which branches to check
        branches_to_check = []

        if TARGET_BRANCHES:
            # Get all branches for the repo
            all_branches = get_repo_branches(repo_name)

            # Check which target branches exist in this repo
            for target_branch in TARGET_BRANCHES:
                if target_branch in all_branches:
                    branches_to_check.append(target_branch)

            # Always include default branch if not already in list
            if default_branch not in branches_to_check:
                branches_to_check.insert(0, default_branch)
        else:
            # Only check default branch
            branches_to_check = [default_branch]

        # Check each branch
        repo_found_packages = {}
        for branch in branches_to_check:
            # Merge results from package.json and lock files
            found_json = check_package_json(repo_name, branch)
            found_lock = check_lock_files(repo_name, branch)

            # Combine results
            found = {}
            for pkg_name, versions in found_json.items():
                if pkg_name not in found:
                    found[pkg_name] = []
                found[pkg_name].extend(versions)

            for pkg_name, versions in found_lock.items():
                if pkg_name not in found:
                    found[pkg_name] = []
                found[pkg_name].extend(versions)

            if found:
                repo_found_packages[branch] = found

        if repo_found_packages:
            print(f"  ✓ Found packages in {len(repo_found_packages)} branch(es)")
            results.append({
                "repo": repo_name,
                "url": repo["html_url"],
                "branches": repo_found_packages
            })
        else:
            print("  ✗")

    # Display results
    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80 + "\n")

    if results:
        for result in results:
            print(f"\n📦 Repository: {result['repo']}")
            print(f"   URL: {result['url']}")

            for branch, packages in result['branches'].items():
                print(f"\n   Branch: {branch}")
                print("   Packages found:")

                for pkg_name, versions in packages.items():
                    for version_info in versions:
                        match_indicator = "✓" if version_info['exact_match'] else "✗"
                        print(f"     {match_indicator} {pkg_name} ({version_info['source']})")
                        print(f"       Target: {version_info['target_version']}")
                        print(f"       Installed: {version_info['installed_version']}")

        print(f"\n\nTotal repositories with target packages: {len(results)}")
    else:
        print("No repositories found with the target packages.")

    print("\n" + "=" * 80)

    # Generate report files
    script_dir = os.path.dirname(os.path.abspath(__file__))
    results_dir = os.path.join(script_dir, "results")

    # Create results directory if it doesn't exist
    os.makedirs(results_dir, exist_ok=True)

    errors_file = os.path.join(results_dir, "errors.txt")
    warnings_file = os.path.join(results_dir, "warnings.txt")

    # Collect errors (exact version matches - vulnerable) and warnings (same package, different version)
    errors = []
    warnings = []

    for result in results:
        repo_name = result['repo']
        repo_url = result['url']

        for branch, packages in result['branches'].items():
            for pkg_name, versions in packages.items():
                for version_info in versions:
                    if version_info['exact_match']:
                        # Error: exact version match found (vulnerable package)
                        errors.append({
                            "repo": repo_name,
                            "url": repo_url,
                            "branch": branch,
                            "package": pkg_name,
                            "target_version": version_info['target_version'],
                            "installed_version": version_info['installed_version'],
                            "source": version_info['source']
                        })
                    else:
                        # Warning: same package name but different version
                        warnings.append({
                            "repo": repo_name,
                            "url": repo_url,
                            "branch": branch,
                            "package": pkg_name,
                            "target_version": version_info['target_version'],
                            "installed_version": version_info['installed_version'],
                            "source": version_info['source']
                        })

    # Write errors file
    with open(errors_file, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("ERRORS: Repositories with exact vulnerable package matches\n")
        f.write("=" * 80 + "\n\n")

        if errors:
            for error in errors:
                f.write(f"Repository: {error['repo']}\n")
                f.write(f"URL: {error['url']}\n")
                f.write(f"Branch: {error['branch']}\n")
                f.write(f"Package: {error['package']} ({error['source']})\n")
                f.write(f"Target Version: {error['target_version']}\n")
                f.write(f"Installed Version: {error['installed_version']}\n")
                f.write("-" * 80 + "\n\n")

            f.write(f"Total exact vulnerable package matches: {len(errors)}\n")
        else:
            f.write("No exact vulnerable package matches found.\n")

    # Write warnings file
    with open(warnings_file, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("WARNINGS: Repositories with same package but different version\n")
        f.write("=" * 80 + "\n\n")

        if warnings:
            for warning in warnings:
                f.write(f"Repository: {warning['repo']}\n")
                f.write(f"URL: {warning['url']}\n")
                f.write(f"Branch: {warning['branch']}\n")
                f.write(f"Package: {warning['package']} ({warning['source']})\n")
                f.write(f"Target Version: {warning['target_version']}\n")
                f.write(f"Installed Version: {warning['installed_version']}\n")
                f.write("-" * 80 + "\n\n")

            f.write(f"Total packages with different versions: {len(warnings)}\n")
        else:
            f.write("No packages with different versions found.\n")

    print(f"\n📄 Reports generated:")
    print(f"   Errors: {errors_file}")
    print(f"   Warnings: {warnings_file}")


if __name__ == "__main__":
    main()
