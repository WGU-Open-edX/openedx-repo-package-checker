#!/usr/bin/env python3
"""
Script to check OpenEdx repositories for specific packages.
"""

import requests
import json
import sys
import os
import argparse
from typing import List, Dict, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod


@dataclass
class PackageMatch:
    """Data class representing a package match."""
    target_version: str
    installed_version: str
    exact_match: bool
    any_version_match: bool
    source: str


@dataclass
class RepositoryResult:
    """Data class representing repository check results."""
    repo: str
    url: str
    branches: Dict[str, Dict[str, List[PackageMatch]]]


class ConfigLoader:
    """Responsible for loading configuration files."""
    
    @staticmethod
    def load_packages(config_path: Optional[str] = None) -> List[str]:
        """Load target packages from configuration file."""
        if config_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, "target_packages.txt")
        
        return ConfigLoader._load_lines_from_file(config_path)
    
    @staticmethod
    def load_branches(config_path: Optional[str] = None) -> List[str]:
        """Load target branches from configuration file."""
        if config_path is None:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, "target_branches.txt")
        
        return ConfigLoader._load_lines_from_file(config_path)
    
    @staticmethod
    def _load_lines_from_file(file_path: str) -> List[str]:
        """Load non-empty, non-comment lines from a file."""
        lines = []
        if os.path.exists(file_path):
            with open(file_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        lines.append(line)
        return lines


class GitHubClient:
    """Handles all GitHub API interactions."""
    
    def __init__(self, token: Optional[str] = None):
        self.base_url = "https://api.github.com"
        self.headers = {}
        if token:
            self.headers["Authorization"] = f"token {token}"
    
    def get_all_repos(self, org: str) -> List[Dict]:
        """Fetch all repositories for an organization."""
        repos = []
        page = 1
        per_page = 100
        
        print(f"Fetching repositories from {org}...")
        
        while True:
            url = f"{self.base_url}/orgs/{org}/repos"
            params = {"page": page, "per_page": per_page, "type": "all"}
            
            response = requests.get(url, params=params, headers=self.headers)
            
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
    
    def get_repo(self, org: str, repo_name: str) -> Optional[Dict]:
        """Fetch a single repository."""
        url = f"{self.base_url}/repos/{org}/{repo_name}"
        response = requests.get(url, headers=self.headers)
        
        if response.status_code != 200:
            print(f"Error fetching repository '{repo_name}': {response.status_code}")
            print(response.text)
            return None
        
        return response.json()
    
    def get_repo_branches(self, org: str, repo_name: str) -> List[str]:
        """Fetch all branches for a repository."""
        branches = []
        page = 1
        per_page = 100
        
        while True:
            url = f"{self.base_url}/repos/{org}/{repo_name}/branches"
            params = {"page": page, "per_page": per_page}
            
            try:
                response = requests.get(url, params=params, headers=self.headers, timeout=10)
                
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
    
    def get_file_content(self, org: str, repo_name: str, branch: str, file_path: str) -> Optional[str]:
        """Fetch raw file content from GitHub."""
        url = f"https://raw.githubusercontent.com/{org}/{repo_name}/{branch}/{file_path}"
        
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.text
        except (requests.exceptions.Timeout, requests.exceptions.RequestException):
            pass
        
        return None
    
    def get_tree_recursive(self, org: str, repo_name: str, branch: str) -> Optional[Dict]:
        """Get repository tree recursively."""
        url = f"{self.base_url}/repos/{org}/{repo_name}/git/trees/{branch}"
        params = {"recursive": "1"}
        
        try:
            response = requests.get(url, params=params, headers=self.headers, timeout=30)
            if response.status_code == 200:
                return response.json()
        except (requests.exceptions.Timeout, requests.exceptions.RequestException):
            pass
        
        return None


class PackageParser:
    """Base class for package file parsers."""
    
    @staticmethod
    def parse_package_identifier(package_identifier: str) -> tuple[str, str]:
        """Parse package identifier into name and version.
        
        Handles both formats: color@5.0.1 and @scope/package@5.0.1
        """
        if package_identifier.startswith("@"):
            parts = package_identifier.rsplit("@", 1)
            return parts[0], parts[1]
        else:
            name, version = package_identifier.rsplit("@", 1)
            return name, version


class PackageJsonParser(PackageParser):
    """Parser for package.json files."""
    
    @staticmethod
    def parse(content: str, target_packages: List[str], source_path: str) -> Dict[str, List[PackageMatch]]:
        """Parse package.json content and find target packages."""
        found_packages = {}
        
        try:
            package_data = json.loads(content)
            
            all_deps = {}
            all_deps.update(package_data.get("dependencies", {}))
            all_deps.update(package_data.get("devDependencies", {}))
            all_deps.update(package_data.get("peerDependencies", {}))
            
            for target_pkg in target_packages:
                pkg_name, pkg_version = PackageParser.parse_package_identifier(target_pkg)
                
                if pkg_name in all_deps:
                    installed_version = all_deps[pkg_name]
                    exact_match = PackageJsonParser._is_exact_match(installed_version, pkg_version)
                    
                    if pkg_name not in found_packages:
                        found_packages[pkg_name] = []
                    
                    found_packages[pkg_name].append(PackageMatch(
                        target_version=pkg_version,
                        installed_version=installed_version,
                        exact_match=exact_match,
                        any_version_match=True,
                        source=source_path
                    ))
        
        except json.JSONDecodeError:
            pass
        
        return found_packages
    
    @staticmethod
    def _is_exact_match(installed: str, target: str) -> bool:
        """Check if installed version is an exact match to target."""
        return installed in [target, f"^{target}", f"~{target}"]


class PackageLockParser(PackageParser):
    """Parser for package-lock.json files."""
    
    @staticmethod
    def parse(content: str, target_packages: List[str], source_path: str) -> Dict[str, List[PackageMatch]]:
        """Parse package-lock.json content and find target packages."""
        found_packages = {}
        
        try:
            lock_data = json.loads(content)
            packages = lock_data.get("packages", {})
            dependencies = lock_data.get("dependencies", {})
            
            for target_pkg in target_packages:
                pkg_name, pkg_version = PackageParser.parse_package_identifier(target_pkg)
                
                # Check lockfileVersion 2+ format
                for pkg_path, pkg_info in packages.items():
                    if pkg_path in [f"node_modules/{pkg_name}", pkg_name]:
                        installed_version = pkg_info.get("version", "")
                        if installed_version:
                            PackageLockParser._add_match(
                                found_packages, pkg_name, pkg_version, 
                                installed_version, source_path
                            )
                            break
                
                # Check lockfileVersion 1 format
                if pkg_name not in found_packages and pkg_name in dependencies:
                    installed_version = dependencies[pkg_name].get("version", "")
                    if installed_version:
                        PackageLockParser._add_match(
                            found_packages, pkg_name, pkg_version, 
                            installed_version, source_path
                        )
        
        except json.JSONDecodeError:
            pass
        
        return found_packages
    
    @staticmethod
    def _add_match(found_packages: Dict, pkg_name: str, pkg_version: str, 
                   installed_version: str, source_path: str):
        """Add a package match to the results."""
        if pkg_name not in found_packages:
            found_packages[pkg_name] = []
        
        found_packages[pkg_name].append(PackageMatch(
            target_version=pkg_version,
            installed_version=installed_version,
            exact_match=(installed_version == pkg_version),
            any_version_match=True,
            source=source_path
        ))


class YarnLockParser(PackageParser):
    """Parser for yarn.lock files."""
    
    @staticmethod
    def parse(content: str, target_packages: List[str], source_path: str) -> Dict[str, List[PackageMatch]]:
        """Parse yarn.lock content and find target packages."""
        found_packages = {}
        lines = content.split("\n")
        
        for target_pkg in target_packages:
            pkg_name, pkg_version = PackageParser.parse_package_identifier(target_pkg)
            
            i = 0
            while i < len(lines):
                line = lines[i].strip()
                
                if line.startswith(f'"{pkg_name}@') or line.startswith(f"{pkg_name}@"):
                    for j in range(i + 1, min(i + 10, len(lines))):
                        version_line = lines[j].strip()
                        if version_line.startswith("version "):
                            installed_version = version_line.split("version ")[1].strip('"')
                            
                            if pkg_name not in found_packages:
                                found_packages[pkg_name] = []
                            
                            found_packages[pkg_name].append(PackageMatch(
                                target_version=pkg_version,
                                installed_version=installed_version,
                                exact_match=(installed_version == pkg_version),
                                any_version_match=True,
                                source=source_path
                            ))
                            break
                    break
                i += 1
        
        return found_packages


class PackageFileFinder:
    """Finds package-related files in repositories."""
    
    def __init__(self, github_client: GitHubClient):
        self.github_client = github_client
    
    def find_package_files(self, org: str, repo_name: str, branch: str, 
                          recursive: bool = False) -> Dict[str, List[str]]:
        """Find all package files in a repository."""
        if recursive:
            return self._find_recursive(org, repo_name, branch)
        else:
            return self._find_root_only()
    
    def _find_root_only(self) -> Dict[str, List[str]]:
        """Return root-level package files only."""
        return {
            "package.json": ["package.json"],
            "package-lock.json": ["package-lock.json"],
            "yarn.lock": ["yarn.lock"]
        }
    
    def _find_recursive(self, org: str, repo_name: str, branch: str) -> Dict[str, List[str]]:
        """Find all package files recursively."""
        package_files = {
            "package.json": [],
            "package-lock.json": [],
            "yarn.lock": []
        }
        
        tree_data = self.github_client.get_tree_recursive(org, repo_name, branch)
        if not tree_data or "tree" not in tree_data:
            return package_files
        
        for item in tree_data["tree"]:
            path = item.get("path", "")
            if path.endswith("/package.json") or path == "package.json":
                package_files["package.json"].append(path)
            elif path.endswith("/package-lock.json") or path == "package-lock.json":
                package_files["package-lock.json"].append(path)
            elif path.endswith("/yarn.lock") or path == "yarn.lock":
                package_files["yarn.lock"].append(path)
        
        return package_files


class PackageChecker:
    """Checks repositories for target packages."""
    
    def __init__(self, github_client: GitHubClient, file_finder: PackageFileFinder):
        self.github_client = github_client
        self.file_finder = file_finder
        self.parsers = {
            "package.json": PackageJsonParser,
            "package-lock.json": PackageLockParser,
            "yarn.lock": YarnLockParser
        }
    
    def check_repository(self, org: str, repo: Dict, target_packages: List[str],
                        target_branches: List[str], recursive: bool) -> Optional[RepositoryResult]:
        """Check a repository for target packages."""
        repo_name = repo["name"]
        default_branch = repo.get("default_branch", "master")
        
        branches_to_check = self._determine_branches(
            org, repo_name, default_branch, target_branches
        )
        
        repo_found_packages = {}
        
        for branch in branches_to_check:
            found = self._check_branch(
                org, repo_name, branch, target_packages, recursive
            )
            if found:
                repo_found_packages[branch] = found
        
        if repo_found_packages:
            return RepositoryResult(
                repo=repo_name,
                url=repo["html_url"],
                branches=repo_found_packages
            )
        
        return None
    
    def _determine_branches(self, org: str, repo_name: str, default_branch: str,
                           target_branches: List[str]) -> List[str]:
        """Determine which branches to check."""
        if not target_branches:
            return [default_branch]
        
        all_branches = self.github_client.get_repo_branches(org, repo_name)
        branches_to_check = [b for b in target_branches if b in all_branches]
        
        if default_branch not in branches_to_check:
            branches_to_check.insert(0, default_branch)
        
        return branches_to_check
    
    def _check_branch(self, org: str, repo_name: str, branch: str,
                     target_packages: List[str], recursive: bool) -> Dict[str, List[PackageMatch]]:
        """Check a specific branch for target packages."""
        package_files = self.file_finder.find_package_files(
            org, repo_name, branch, recursive
        )
        
        if recursive:
            total_files = sum(len(files) for files in package_files.values())
            if total_files > 0:
                print(f"  Found {total_files} package file(s) in repository:")
                for file_type, paths in package_files.items():
                    for path in paths:
                        print(f"    - {path}")
        
        found = {}
        
        for file_type, paths in package_files.items():
            parser = self.parsers.get(file_type)
            if not parser:
                continue
            
            for file_path in paths:
                content = self.github_client.get_file_content(
                    org, repo_name, branch, file_path
                )
                
                if content:
                    file_found = parser.parse(content, target_packages, file_path)
                    for pkg_name, matches in file_found.items():
                        if pkg_name not in found:
                            found[pkg_name] = []
                        found[pkg_name].extend(matches)
        
        return found


class ResultsReporter:
    """Handles result output and report generation."""
    
    @staticmethod
    def print_results(results: List[RepositoryResult]):
        """Print results to console."""
        print("\n" + "=" * 80)
        print("RESULTS")
        print("=" * 80 + "\n")
        
        if results:
            for result in results:
                print(f"\n📦 Repository: {result.repo}")
                print(f"   URL: {result.url}")
                
                for branch, packages in result.branches.items():
                    print(f"\n   Branch: {branch}")
                    print("   Packages found:")
                    
                    for pkg_name, matches in packages.items():
                        for match in matches:
                            match_indicator = "✓" if match.exact_match else "✗"
                            print(f"     {match_indicator} {pkg_name} ({match.source})")
                            print(f"       Target: {match.target_version}")
                            print(f"       Installed: {match.installed_version}")
            
            print(f"\n\nTotal repositories with target packages: {len(results)}")
        else:
            print("No repositories found with the target packages.")
        
        print("\n" + "=" * 80)
    
    @staticmethod
    def generate_reports(results: List[RepositoryResult]):
        """Generate text report files."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        results_dir = os.path.join(script_dir, "results")
        os.makedirs(results_dir, exist_ok=True)
        
        exact_matches = []
        partial_matches = []
        
        for result in results:
            for branch, packages in result.branches.items():
                for pkg_name, matches in packages.items():
                    for match in matches:
                        match_data = {
                            "repo": result.repo,
                            "url": result.url,
                            "branch": branch,
                            "package": pkg_name,
                            "target_version": match.target_version,
                            "installed_version": match.installed_version,
                            "source": match.source
                        }
                        
                        if match.exact_match:
                            exact_matches.append(match_data)
                        else:
                            partial_matches.append(match_data)
        
        ResultsReporter._write_report(
            os.path.join(results_dir, "exact_matches.txt"),
            "EXACT MATCHES: Repositories with exact package and version matches",
            exact_matches
        )
        
        ResultsReporter._write_report(
            os.path.join(results_dir, "partial_matches.txt"),
            "PARTIAL MATCHES: Repositories with same package but different version",
            partial_matches
        )
        
        print(f"\n📄 Reports generated:")
        print(f"   Exact matches: {os.path.join(results_dir, 'exact_matches.txt')}")
        print(f"   Partial matches: {os.path.join(results_dir, 'partial_matches.txt')}")
    
    @staticmethod
    def _write_report(file_path: str, title: str, matches: List[Dict]):
        """Write a report file."""
        with open(file_path, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write(f"{title}\n")
            f.write("=" * 80 + "\n\n")
            
            if matches:
                for match in matches:
                    f.write(f"Repository: {match['repo']}\n")
                    f.write(f"URL: {match['url']}\n")
                    f.write(f"Branch: {match['branch']}\n")
                    f.write(f"Package: {match['package']} ({match['source']})\n")
                    f.write(f"Target Version: {match['target_version']}\n")
                    f.write(f"Installed Version: {match['installed_version']}\n")
                    f.write("-" * 80 + "\n\n")
                
                f.write(f"Total matches: {len(matches)}\n")
            else:
                f.write("No matches found.\n")


class Application:
    """Main application orchestrator."""
    
    def __init__(self):
        self.args = self._parse_arguments()
        self.github_client = GitHubClient(os.environ.get("GITHUB_TOKEN"))
        self.file_finder = PackageFileFinder(self.github_client)
        self.package_checker = PackageChecker(self.github_client, self.file_finder)
        self.reporter = ResultsReporter()
    
    def _parse_arguments(self) -> argparse.Namespace:
        """Parse command line arguments."""
        parser = argparse.ArgumentParser(
            description="Check GitHub repositories for specific packages"
        )
        parser.add_argument(
            '--org', type=str, default='openedx',
            help='GitHub organization name (default: openedx)'
        )
        parser.add_argument(
            '--repo', type=str,
            help='Specific repository name to check. If not provided, checks all repositories.'
        )
        parser.add_argument(
            '--packages-file', type=str,
            help='Path to custom target packages file (default: target_packages.txt)'
        )
        parser.add_argument(
            '--branches-file', type=str,
            help='Path to custom target branches file (default: target_branches.txt)'
        )
        parser.add_argument(
            '--recursive', action='store_true',
            help='Recursively search for package files in subdirectories'
        )
        return parser.parse_args()
    
    def run(self):
        """Run the application."""
        target_packages = ConfigLoader.load_packages(self.args.packages_file)
        target_branches = ConfigLoader.load_branches(self.args.branches_file)
        
        self._print_header(target_packages, target_branches)
        
        repos = self._get_repositories()
        if not repos:
            print("No repositories found or error occurred.")
            sys.exit(1)
        
        results = self._check_repositories(repos, target_packages, target_branches)
        
        self.reporter.print_results(results)
        self.reporter.generate_reports(results)
    
    def _print_header(self, target_packages: List[str], target_branches: List[str]):
        """Print application header."""
        print("=" * 80)
        print("GitHub Repository Package Checker")
        print("=" * 80)
        print(f"\nOrganization: {self.args.org}")
        print("\nTarget packages:")
        for pkg in target_packages:
            print(f"  - {pkg}")
        
        if target_branches:
            print("\nTarget branches:")
            for branch in target_branches:
                print(f"  - {branch}")
        else:
            print("\nChecking default branch only (no target_branches.txt found)")
        
        if self.args.repo:
            print(f"\nChecking specific repository: {self.args.repo}")
        else:
            print(f"\nChecking all repositories in {self.args.org} organization")
        
        print("\n" + "=" * 80 + "\n")
    
    def _get_repositories(self) -> List[Dict]:
        """Get repositories to check."""
        if self.args.repo:
            repo = self.github_client.get_repo(self.args.org, self.args.repo)
            if not repo:
                sys.exit(1)
            print(f"Found repository: {self.args.repo}\n")
            return [repo]
        else:
            return self.github_client.get_all_repos(self.args.org)
    
    def _check_repositories(self, repos: List[Dict], target_packages: List[str],
                           target_branches: List[str]) -> List[RepositoryResult]:
        """Check all repositories for target packages."""
        results = []
        
        for idx, repo in enumerate(repos, 1):
            print(f"[{idx}/{len(repos)}] Checking {repo['name']}...")
            
            result = self.package_checker.check_repository(
                self.args.org, repo, target_packages,
                target_branches, self.args.recursive
            )
            
            if result:
                print(f"  ✓ Found packages in {len(result.branches)} branch(es)")
                results.append(result)
            else:
                print("  ✗")
        
        return results


def main():
    """Main entry point."""
    app = Application()
    app.run()


if __name__ == "__main__":
    main()