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

2. Set GitHub token (recommended to avoid rate limits and required for private repositories):
```bash
export GITHUB_TOKEN=your_github_token_here
```

To create a token:
- Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
- Generate new token with appropriate scope:
  - `public_repo` - for public repositories only (higher rate limits)
  - `repo` - for both public and private repositories
- Copy the token and set it in your environment

**Note:** Without a token, the script can only access public repositories and is limited to 60 API requests per hour. With a token, you get 5,000 requests per hour and can access private repositories (if you have the `repo` scope).

## Usage

### Check all repositories (default: openedx organization):
```bash
python check_packages.py
```

### Check a specific organization or user:
```bash
# Check an organization
python check_packages.py --org my-organization

# Check a user's repositories (e.g., for checking forks)
python check_packages.py --org github-username
```

**Note:** The `--org` flag works for both GitHub organizations and individual user accounts. The script automatically detects the account type and uses the appropriate API endpoint.

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

# Check different organization with custom packages
python check_packages.py --org my-org --packages-file custom_packages.txt
```

### Recursively search for nested package files:
```bash
# Search all subdirectories for package files (increases API usage)
python check_packages.py --recursive

# Combine with other options
python check_packages.py --org my-org --recursive --packages-file custom.txt
```

**Note:** By default, the script only checks package files in the repository root (`/package.json`, `/package-lock.json`, `/yarn.lock`). Use `--recursive` to search for package files in all subdirectories (e.g., `/frontend/package.json`, `/backend/package.json`). This will increase API usage significantly for large repositories.

The script will:
1. Fetch repositories from the specified GitHub organization (all or specific repo)
2. Check `package.json`, `package-lock.json`, and `yarn.lock` for the target packages
   - By default: checks only the repository root
   - With `--recursive`: searches all subdirectories (e.g., `/frontend/`, `/packages/`, etc.)
3. Display results showing which repositories contain the packages, their versions, and file paths
4. Generate two report files (exact matches and partial matches)

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
- Package name and source file path (e.g., `package.json`, `frontend/package-lock.json`, `packages/common/yarn.lock`)
- Target version
- Installed version

## Examples

### Example: Check specific repo with recursive search
```bash
python check_packages.py --repo frontend-base --recursive
```

Output shows nested files:
```
Packages found:
  ✗ @babel/core (package.json)
    Target: 7.26.0
    Installed: ^7.24.9
  ✗ @babel/core (test-site/package-lock.json)
    Target: 7.26.0
    Installed: 7.27.4
```

### Example: Check all repos in custom organization
```bash
python check_packages.py --org my-company --packages-file vulnerable-packages.txt
```

### Example: Check your fork repositories
```bash
python check_packages.py --org your-github-username
```

## Features

- ✅ Supports public and private repositories (with appropriate GitHub token)
- ✅ Works with both GitHub organizations and user accounts
- ✅ Automatically detects account type (user vs organization)
- ✅ Checks multiple file types: `package.json`, `package-lock.json`, and `yarn.lock`
- ✅ Recursive search for nested package files in subdirectories (optional)
- ✅ Handles scoped packages (e.g., `@scope/package@version`)
- ✅ Configurable organization/user, packages, and branches
- ✅ Generates detailed reports with exact and partial matches
- ✅ Reports show file paths for easy location of matches
