import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import random

# Create a session with connection pooling and retries
def _get_optimized_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=20)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def _get_github_login_from_fullname(github_token, full_name_from_ui, github_org_key, log_list):
    """
    Fetches organization members and their full names to find a matching GitHub login.
    Returns the GitHub login (username) if found, otherwise None.
    Caches the mapping to avoid repeated API calls within the same session.
    """
    # Use a simple in-memory cache for this helper function to reduce redundant API calls
    # within the same application run.
    if not hasattr(_get_github_login_from_fullname, 'cache'):
        _get_github_login_from_fullname.cache = {}

    # Check for None values to prevent AttributeError
    if not github_token or not full_name_from_ui or not github_org_key:
        log_list.append("[ERROR] Git: Missing required parameters for resolving GitHub login.")
        return None

    cache_key = f"{full_name_from_ui.lower()}_{github_org_key.lower()}"

    if cache_key in _get_github_login_from_fullname.cache:
        log_list.append(f"[INFO] Git: Resolved '{full_name_from_ui}' from cache to login '{_get_github_login_from_fullname.cache[cache_key]}'.")
        return _get_github_login_from_fullname.cache[cache_key]

    log_list.append(f"[INFO] Git: Attempting to resolve developer '{full_name_from_ui}' to GitHub login in organization '{github_org_key}'. (API call)")
    
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    base_api_url = "https://api.github.com"

    members_url = f"{base_api_url}/orgs/{github_org_key}/members"
    members_params = {"per_page": 100} # Max per_page. Need pagination for very large orgs.

    try:
        members_resp = requests.get(members_url, headers=headers, params=members_params)
        members_resp.raise_for_status()
        members_list = members_resp.json()
        log_list.append(f"[INFO] Git API: Fetched {len(members_list)} members for '{github_org_key}'.")

        fullname_to_login_map = {}
        for member in members_list:
            login = member.get('login')
            if login:
                user_detail_url = f"{base_api_url}/users/{login}"
                user_detail_resp = requests.get(user_detail_url, headers=headers)
                user_detail_resp.raise_for_status()
                user_data = user_detail_resp.json()
                
                user_fullname = user_data.get('name') # 'name' field is the full name
                if user_fullname:
                    fullname_to_login_map[user_fullname.lower()] = login
                    # For cases where developer_name is actually the GitHub login
                    fullname_to_login_map[login.lower()] = login
                    # log_list.append(f"[DEBUG] Git: Mapped '{user_fullname.lower()}' to login '{login}'.")
                else:
                    # If full name is not set, map by login only
                    fullname_to_login_map[login.lower()] = login


        resolved_login = fullname_to_login_map.get(full_name_from_ui.lower())
        
        if resolved_login:
            log_list.append(f"[INFO] Git: Successfully resolved '{full_name_from_ui}' to GitHub login '{resolved_login}'.")
            _get_github_login_from_fullname.cache[cache_key] = resolved_login # Cache the result
            return resolved_login
        else:
            log_list.append(f"[WARNING] Git: Could not resolve '{full_name_from_ui}' to a GitHub login in organization '{github_org_key}'. Ensure name matches exactly or developer is a member.")
            _get_github_login_from_fullname.cache[cache_key] = None # Cache failure
            return None

    except requests.exceptions.RequestException as e:
        error_msg = f"Git API: Error fetching organization members or user details for '{github_org_key}': {e}"
        log_list.append(f"[ERROR] {error_msg}")
        _get_github_login_from_fullname.cache[cache_key] = None # Cache failure
        return None

from datetime import datetime, timedelta

def get_sprint_date_range(
    target_sprint: str,
    base_sprint: str = "2025.12",
    base_start_date_str: str = "2025-06-11",
    sprint_length_days: int = 14
):
    base_year, base_sprint_num = map(int, base_sprint.split("."))
    base_start_date = datetime.strptime(base_start_date_str, "%Y-%m-%d").date()

    target_year, target_sprint_num = map(int, target_sprint.split("."))

    # Calculate the number of sprints between base and target
    year_diff = target_year - base_year
    sprint_offset = (year_diff * 52) + (target_sprint_num - base_sprint_num)

    # Calculate start and end date
    target_start_date = base_start_date + timedelta(days=sprint_offset * sprint_length_days)
    target_end_date = target_start_date + timedelta(days=sprint_length_days - 1)

    return target_start_date, target_end_date

def fetch_git_metrics_via_api(github_token, developer_name, repos, log_list, github_org_key, sprint_id=None):
    log_list.append(f"[INFO] Git: Starting fetch for developer '{developer_name}' across {len(repos)} repositories in org '{github_org_key}'...")
    log_list.append(f"[DEBUG] Git: Input repos: {repos}")
    log_list.append(f"[DEBUG] Git: Sprint ID: {sprint_id}")

    # Check if GitHub token is valid by testing a simple API call
    headers = _build_headers(github_token)
    try:
        test_response = requests.get("https://api.github.com/user", headers=headers, timeout=5)
        if test_response.status_code != 200:
            log_list.append(f"[ERROR] Git: Invalid GitHub token - using mock data for testing")
            return _get_mock_git_metrics(developer_name, log_list)
    except Exception as e:
        log_list.append(f"[ERROR] Git: GitHub API unavailable - using mock data: {e}")
        return _get_mock_git_metrics(developer_name, log_list)

    # Limit repos for performance (max 3 for individual metrics)
    repos = repos[:3] if len(repos) > 3 else repos
    log_list.append(f"[DEBUG] Git: Processing {len(repos)} repos after limit")
    
    github_login = _get_github_login_from_fullname(github_token, developer_name, github_org_key, log_list)
    
    if not github_login:
        log_list.append(f"[WARNING] Git: Failed to resolve GitHub login for '{developer_name}' - trying fallback methods")
        # Fallback: try using developer name as-is (common for GitHub usernames)
        potential_logins = [
            developer_name.lower().replace(' ', ''),  # Remove spaces
            developer_name.lower().replace(' ', '-'), # Replace spaces with hyphens
            developer_name.lower().replace(' ', '_'), # Replace spaces with underscores
            developer_name.split()[0].lower() if ' ' in developer_name else developer_name.lower()  # First name only
        ]
        log_list.append(f"[INFO] Git: Trying fallback GitHub logins: {potential_logins}")
        github_login = potential_logins[0]  # Use first fallback
    else:
        log_list.append(f"[INFO] Git: Successfully resolved '{developer_name}' to GitHub login '{github_login}'")
    
    sprint_start_date, sprint_end_date = _calculate_sprint_dates(sprint_id, log_list)
    if sprint_start_date is None and sprint_end_date is None and sprint_id:
        return {"error": f"Failed to calculate sprint date range for '{sprint_id}'."}

    headers = _build_headers(github_token)
    metrics = _initialize_metrics()
    session = _get_optimized_session()

    for repo_full_name in repos:
        _process_repository(repo_full_name, github_login, headers, sprint_start_date, sprint_end_date, metrics, log_list, session)

    session.close()
    log_list.append(f"[INFO] Git: Finished processing {len(repos)} repositories. Total commits: {metrics['commits']}")
    return metrics


def _calculate_sprint_dates(sprint_id, log_list):
    if not sprint_id:
        log_list.append(f"[DEBUG] Git: No sprint_id provided, using no date filtering")
        return None, None
    
    # Skip date calculation for JQL functions
    if sprint_id in ["openSprints()", "startOfYear()"]:
        log_list.append(f"[DEBUG] Git: Skipping date calculation for JQL function: {sprint_id}")
        return None, None
        
    try:
        dates = get_sprint_date_range(sprint_id)
        log_list.append(f"[DEBUG] Git: Calculated sprint dates for {sprint_id}: {dates}")
        return dates
    except Exception as e:
        log_list.append(f"[ERROR] Git: Failed to calculate sprint date range for '{sprint_id}': {e}")
        return None, None


def _build_headers(github_token):
    return {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }


def _initialize_metrics():
    return {
        "commits": 0,
        "lines_added": 0,
        "lines_deleted": 0,
        "files_changed": 0,
        "prs_created": 0,
        "prs_merged": 0,
        # "review_comments_given": 0
    }


def _process_repository(repo_full_name, github_login, headers, sprint_start_date, sprint_end_date, metrics, log_list, session=None):
    if session is None:
        session = requests
    owner_repo = repo_full_name.strip()
    if "/" not in owner_repo or owner_repo.count('/') > 1:
        log_list.append(f"[WARNING] Git: Skipping invalid repo format: '{repo_full_name}'. Expected 'owner/repo-name'.")
        return

    log_list.append(f"[INFO] Git: Processing repo: '{owner_repo}' for user: {github_login or 'team-mode'}")
    _process_pull_requests(owner_repo, github_login, headers, sprint_start_date, sprint_end_date, metrics, log_list, session)
    _process_commits(owner_repo, github_login, headers, sprint_start_date, sprint_end_date, metrics, log_list, session)
    get_review_comments_given(owner_repo, github_login, headers, sprint_start_date, sprint_end_date, metrics, log_list, session)


def _process_pull_requests(owner_repo, github_login, headers, sprint_start_date, sprint_end_date, metrics, log_list, session=None):
    if session is None:
        session = requests
    pr_url = f"https://api.github.com/repos/{owner_repo}/pulls"
    # Optimize: Reduce per_page and add date filtering
    pr_params = {
        "state": "all",
        "per_page": 50,  # Reduced from 100
        "sort": "updated",
        "direction": "desc"
    }
    
    try:
        pr_resp = session.get(pr_url, headers=headers, params=pr_params, timeout=10)
        pr_resp.raise_for_status()

        login_to_match = github_login.lower() if github_login else None

        for pr in pr_resp.json():
            pr_login = pr.get("user", {}).get("login", "").lower()

            if login_to_match:
                # Developer-level: filter by login
                if pr_login == login_to_match:
                    metrics["prs_created"] += 1
                    if pr.get("merged_at"):
                        metrics["prs_merged"] += 1
            else:
                # Team-level: count all PRs
                metrics["prs_created"] += 1
                if pr.get("merged_at"):
                    metrics["prs_merged"] += 1

    except requests.exceptions.RequestException as e:
        if "404" in str(e):
            log_list.append(f"[WARNING] Git: Repository {owner_repo} not found or not accessible - skipping PRs")
        else:
            log_list.append(f"[ERROR] Git API PRs Error for {owner_repo}: {e}")


def _process_commits(owner_repo, github_login, headers, sprint_start_date, sprint_end_date, metrics, log_list, session=None):
    if session is None:
        session = requests
    commits_url = f"https://api.github.com/repos/{owner_repo}/commits"

    # Optimize: Add author filter and limit results
    commits_params = {
        "per_page": 50,  # Reduced from 100
        "since": sprint_start_date.isoformat() if sprint_start_date else "1970-01-01",
        "until": sprint_end_date.isoformat() if sprint_end_date else "9999-12-31"
    }
    
    # Debug logging for date filtering
    if sprint_start_date and sprint_end_date:
        log_list.append(f"[DEBUG] Git: Filtering commits from {sprint_start_date} to {sprint_end_date}")
    else:
        log_list.append(f"[WARNING] Git: No sprint date filtering applied - may return all commits")
    
    # Add author filter for individual metrics
    if github_login:
        commits_params["author"] = github_login

    try:
        commits_resp = session.get(commits_url, headers=headers, params=commits_params, timeout=10)
        commits_resp.raise_for_status()
        commits = commits_resp.json()
        
        log_list.append(f"[DEBUG] Git: Found {len(commits)} commits in {owner_repo} for processing")

        for commit in commits:
            # Skip merge commits (individual work only) - be more precise
            commit_message = commit.get("commit", {}).get("message", "")
            parents = commit.get("parents", [])
            
            # Skip if it's a merge commit (has multiple parents) or explicit merge message
            if (len(parents) > 1 or 
                commit_message.lower().startswith("merge pull request") or 
                commit_message.lower().startswith("merge branch")):
                log_list.append(f"[DEBUG] Git: Skipping merge commit: {commit_message[:50]}...")
                continue
                
            author_data = commit.get("author")
            author_login = author_data.get("login", "").lower() if author_data else ""
            login_to_match = github_login.lower() if github_login else None

            # Process commit details only for matching author
            if login_to_match and author_login == login_to_match:
                _process_commit_details(owner_repo, commit.get("sha"), headers, metrics, log_list, session)
                metrics["commits"] += 1
            elif not login_to_match:
                # Team mode: process all non-merge commits
                _process_commit_details(owner_repo, commit.get("sha"), headers, metrics, log_list, session)
                metrics["commits"] += 1

    except requests.exceptions.RequestException as e:
        if "404" in str(e):
            log_list.append(f"[WARNING] Git: Repository {owner_repo} not found or not accessible - skipping commits")
        else:
            log_list.append(f"[ERROR] Git API Commits Error for {owner_repo}: {e}")


def _process_commit_details(owner_repo, commit_sha, headers, metrics, log_list, session=None):
    if session is None:
        session = requests
    if not commit_sha:
        log_list.append("[WARNING] Skipping commit with empty SHA.")
        return

    detail_url = f"https://api.github.com/repos/{owner_repo}/commits/{commit_sha}"
    
    try:
        detail_resp = session.get(detail_url, headers=headers, timeout=5)
        detail_resp.raise_for_status()
        detail_data = detail_resp.json()

        stats = detail_data.get("stats", {})
        files = detail_data.get("files", [])

        # Defensive updates
        try:
            metrics["lines_added"] += int(stats.get("additions", 0))
            metrics["lines_deleted"] += int(stats.get("deletions", 0))
            metrics["files_changed"] += len(files)
        except Exception as e:
            log_list.append(f"[ERROR] Metric update error for commit {commit_sha[:7]}: {e}")

    except requests.exceptions.RequestException as e:
        log_list.append(f"[ERROR] Git API Commit Detail Error for {owner_repo}/{commit_sha[:7]}: {e}")
        # Don't fail silently - this helps debug why commit details aren't showing



def get_review_comments_given(owner_repo, github_login, headers, sprint_start_date, sprint_end_date, metrics, log_list, session=None):
    if session is None:
        session = requests
    review_comments_url = f"https://api.github.com/repos/{owner_repo}/pulls/comments"
    params = {
        "per_page": 100
    }

    review_comments_given = 0
    login_to_match = github_login.lower() if github_login else None

    try:
        resp = session.get(review_comments_url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()

        comments = resp.json()
        if not isinstance(comments, list):
            log_list.append(f"[ERROR] Unexpected response format for review comments in {owner_repo}")
            return 0

        for comment in comments:
            if not comment:
                continue  # skip None

            user_info = comment.get("user", {})
            created_at = comment.get("created_at")

            if not user_info or not created_at:
                continue  # skip malformed comment

            user_login = user_info.get("login", "").lower()
            try:
                comment_date = datetime.fromisoformat(created_at.replace("Z", "+00:00")).date()
            except Exception:
                continue  # skip invalid date

            if sprint_start_date and sprint_end_date:
                if not (sprint_start_date <= comment_date <= sprint_end_date):
                    continue

            if login_to_match:
                if user_login == login_to_match:
                    review_comments_given += 1
            else:
                review_comments_given += 1

    except requests.exceptions.RequestException as e:
        if "404" in str(e):
            log_list.append(f"[WARNING] Git: Repository {owner_repo} not found or not accessible - skipping review comments")
        else:
            log_list.append(f"[ERROR] GitHub API Review Comments Error for {owner_repo}: {e}")

    return review_comments_given

def _get_mock_git_metrics(developer_name, log_list):
    """Generate mock git metrics for testing when GitHub API is unavailable"""
    log_list.append(f"[INFO] Git: Generating mock data for '{developer_name}' (GitHub API unavailable)")
    
    # Generate realistic mock data
    commits = random.randint(5, 25)
    lines_added = random.randint(100, 1000)
    lines_deleted = random.randint(20, 200)
    files_changed = random.randint(10, 50)
    prs_created = random.randint(2, 8)
    prs_merged = random.randint(1, prs_created)
    review_comments = random.randint(5, 20)
    
    individual_metrics = {
        "commits": commits,
        "lines_added": lines_added,
        "lines_deleted": lines_deleted,
        "files_changed": files_changed,
        "prs_created": prs_created,
        "prs_merged": prs_merged
    }
    
    managerial_metrics = {
        "prs_approved": review_comments,
        "code_reviews": review_comments
    }
    
    log_list.append(f"[INFO] Git: Mock data generated - {commits} commits, {prs_created} PRs created")
    
    return {
        **individual_metrics,
        "individual_work": individual_metrics,
        "managerial_work": managerial_metrics,
        "mock_data": True
    }