# OpenEdx Repository Package Checker

This script checks OpenEdx organization repositories for specific npm packages and generates detailed reports.

## Configuration

### Target Packages (`target_packages.txt`)

List packages to search for in the format `package@version`:
- @hestjs/eslint-config@0.1.2
- @hestjs/logger@0.1.6
- @hestjs/scalar@0.1.7
- @hestjs/validation@0.1.6
- @nativescript-community/arraybuffers@1.1.6

### Target Branches (`target_branches.txt`)

Optionally specify branches to check. If not provided, only the default branch is checked.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Set GitHub token (recommended to avoid rate limits):
```bash
export GITHUB_TOKEN=your_github_token_here
```

To create a token:
- Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
- Generate new token with `public_repo` scope
- Copy the token and set it in your environment

## Usage

### Check all repositories:
```bash
python check_packages.py
```

### Check a specific repository:
```bash
python check_packages.py --repo edx-platform
```

### Use custom configuration files:
```bash
# Custom packages file
python check_packages.py --packages-file custom_packages.txt

# Custom branches file
python check_packages.py --branches-file custom_branches.txt
```

### Run Oct 2025 supply-chain-attacks-NPM-packages Check
```bash
python check_packages.py --packages-file supply-chain-attacks-NPM-packages.txt
```

The script will:
1. Fetch repositories from the OpenEdx organization (all or specific repo)
2. Check `package.json`, `package-lock.json`, and `yarn.lock` for the target packages
3. Display results showing which repositories contain the packages and their versions
4. Generate two report files

## Output

### Console Output
- Progress as it checks each repository
- Final results listing repositories that contain any of the target packages
- Version comparisons (target vs installed)
- Match indicators (✓ for exact match, ✗ for mismatch)

### Report Files

Reports are saved in the `results/` directory:

**`results/exact_matches.txt`** - Repositories with exact package and version matches
- Lists repos where both the package name and version match exactly
- These are the primary findings matching your search criteria

**`results/partial_matches.txt`** - Repositories with same package but different version
- Lists repos where the package name matches but the version differs
- These may be of interest depending on your use case

Each report includes:
- Repository name and URL
- Branch name
- Package name and source file (package.json, package-lock.json, or yarn.lock)
- Target version
- Installed version

## Note

The script uses the GitHub API without authentication, which has rate limits (60 requests/hour). For better rate limits, you can add GitHub token authentication to the script.
