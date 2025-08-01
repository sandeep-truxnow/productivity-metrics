import requests

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

    # Resolve developer_name (full name from UI) to GitHub login
    github_login = _get_github_login_from_fullname(github_token, developer_name, github_org_key, log_list)

    sprint_start_date, sprint_end_date = None, None
    if sprint_id:
        # If sprint_id is provided, calculate the date range for the sprint
        try:
            sprint_start_date, sprint_end_date = get_sprint_date_range(sprint_id)
            log_list.append(f"[INFO] Git: Calculated sprint date range for '{sprint_id}': {sprint_start_date} to {sprint_end_date}.")
        except Exception as e:
            log_list.append(f"[ERROR] Git: Failed to calculate sprint date range for '{sprint_id}': {e}")
            return {"error": f"Failed to calculate sprint date range: {e}"}

    if not github_login:
        log_list.append(f"[ERROR] Git: Cannot proceed with metrics fetch. Could not resolve developer name '{developer_name}' to a GitHub login.")
        return {"error": f"Cannot proceed. Could not resolve developer name '{developer_name}' to GitHub login."}

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    base_api_url = "https://api.github.com"
    metrics = {
        "commits": 0,
        "lines_added": 0,
        "lines_deleted": 0,
        "files_changed": 0,
        "prs_created": 0,
        "prs_merged": 0,
        "review_comments_given": 0 # This is still hard to get accurately across all PRs for a user
    }

    log_list.append("[WARNING] Git: GitHub API has strict rate limits. Fetching detailed commit info (for lines_added/deleted) and PR comments is API intensive. Data might be incomplete if limits are hit or you might face temporary blocks. Consider caching or webhooks for production.")

    for repo_full_name in repos:
        owner_repo = repo_full_name.strip()
        if "/" not in owner_repo or owner_repo.count('/') > 1:
            log_list.append(f"[WARNING] Git: Skipping invalid repo format: '{repo_full_name}'. Expected 'owner/repo-name'.")
            continue

        log_list.append(f"[INFO] Git: Processing repo: '{owner_repo}'")

        # 1. PRs created by developer & merged
        pr_url = f"{base_api_url}/repos/{owner_repo}/pulls"
        pr_params = {"state": "all", "per_page": 100}
        
        try:
            pr_resp = requests.get(pr_url, headers=headers, params=pr_params)
            pr_resp.raise_for_status()
            log_list.append(f"[INFO] Git API: Fetched PRs for {owner_repo} (Status: {pr_resp.status_code})")
            
            for pr in pr_resp.json():
                if pr.get("user", {}).get("login", "").lower() == github_login.lower(): # Use resolved login
                    metrics["prs_created"] += 1
                    if pr.get("merged_at"):
                        metrics["prs_merged"] += 1
        except requests.exceptions.RequestException as e:
            log_list.append(f"[ERROR] Git API PRs Error for {owner_repo}: {e}")

        # 2. Commits authored by developer (and their lines changed)
        commits_url = f"{base_api_url}/repos/{owner_repo}/commits?since={sprint_start_date.isoformat() if sprint_start_date else '1970-01-01'}&until={sprint_end_date.isoformat() if sprint_end_date else '9999-12-31'}"
        commits_params = {"author": github_login, "per_page": 100} # Use resolved login
        
        try:
            commits_resp = requests.get(commits_url, headers=headers, params=commits_params)
            commits_resp.raise_for_status()
            log_list.append(f"[INFO] Git API: Fetched commits for {owner_repo} by {github_login} (Status: {commits_resp.status_code})")
            
            commits_list = commits_resp.json()
            metrics["commits"] += len(commits_list)

            for commit in commits_list:
                commit_sha = commit.get("sha")
                if commit_sha:
                    detail_url = f"{base_api_url}/repos/{owner_repo}/commits/{commit_sha}"
                    try:
                        detail_resp = requests.get(detail_url, headers=headers)
                        detail_resp.raise_for_status()
                        detail_data = detail_resp.json()
                        
                        stats = detail_data.get("stats", {})
                        metrics["lines_added"] += stats.get("additions", 0)
                        metrics["lines_deleted"] += stats.get("deletions", 0)
                        metrics["files_changed"] += len(detail_data.get("files", []))
                    except requests.exceptions.RequestException as e:
                        log_list.append(f"[WARNING] Git API Commit Detail Error for {owner_repo}/{commit_sha[:7]}: {e}")
        except requests.exceptions.RequestException as e:
            log_list.append(f"[ERROR] Git API Commits Error for {owner_repo}: {e}")
        
    log_list.append(f"[INFO] Git: Finished processing {len(repos)} repositories. Total commits: {metrics['commits']}")
    return metrics