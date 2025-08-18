import pandas as pd
import requests
from datetime import datetime
import statistics
import base64
from dateutil import parser
from jira import JIRA
from jira.exceptions import JIRAError

JIRA_URL = "https://truxinc.atlassian.net"

# --- JIRA Connection Function ---
def connect_to_jira_streamlit(url, username, api_token, log_list):
    log_list.append(f"[INFO] JIRA Connect: Attempting connection to {url} for user {username}...")
    try:
        jira_options = {'server': url}
        jira = JIRA(options=jira_options, basic_auth=(username, api_token))
        jira.myself() # Test connection
        log_list.append(f"[INFO] JIRA Connect: Successfully connected to Jira as {username}.")
        return jira
    except JIRAError as e:
        log_list.append(f"[ERROR] JIRA Connect: Error connecting to Jira: Status {e.status_code} - {e.text}")
        return None
    except Exception as e:
        log_list.append(f"[ERROR] JIRA Connect: An unexpected error occurred during Jira connection: {e}")
        return None

# --- Get All JIRA Users Function ---
def get_all_jira_users_streamlit(jira_url, jira_username, jira_api_token, log_list, filter_domain=None):
    log_list.append(f"[INFO] JIRA Users: Fetching all active Jira users from {jira_url}...")
    jira_instance = connect_to_jira_streamlit(jira_url, jira_username, jira_api_token, log_list)
    if not jira_instance: 
        log_list.append("[ERROR] JIRA Users: Jira instance not available to fetch users.")
        return {}
    
    all_users = {}
    start_at = 0
    max_results = 50 

    while True:
        users_page = fetch_users_page(jira_instance, start_at, max_results, log_list)
        if not users_page:
            break
        process_users_page(users_page, all_users, filter_domain, log_list)
        start_at += max_results
        if len(users_page) < max_results:
            break

    log_list.append(f"[INFO] JIRA Users: Fetched {len(all_users)} active human Jira users{get_filter_status_message(filter_domain)}.")
    return all_users


def fetch_users_page(jira_instance, start_at, max_results, log_list):
    try:
        return jira_instance.search_users(query='*', startAt=start_at, maxResults=max_results)
    except JIRAError as e:
        log_list.append(f"[ERROR] JIRA Users: Error fetching users: Status {e.status_code} - {e.text}")
    except Exception as e:
        log_list.append("[ERROR] JIRA Users: An unexpected error occurred while fetching users.")
    return None


def process_users_page(users_page, all_users, filter_domain, log_list):
    for user in users_page:
        if is_human_user(user) and is_matching_domain(user, filter_domain):
            all_users[user.accountId] = {
                'displayName': user.displayName if hasattr(user, 'displayName') else user.accountId,
                'emailAddress': user.emailAddress if hasattr(user, 'emailAddress') else 'N/A'
            }


def is_human_user(user):
    if hasattr(user, 'accountType') and user.accountType.lower() != 'atlassian':
        return False
    display_name_lower = user.displayName.lower() if hasattr(user, 'displayName') else ''
    email_lower = user.emailAddress.lower() if hasattr(user, 'emailAddress') else ''
    NON_HUMAN_KEYWORDS = ['[app]', 'automation', 'bot', 'service', 'plugin', 'jira-system', 'addon', 'connect', 'integration', 'github', 'slack', 'webhook', 'migrator', 'system', 'importer', 'syncer']
    return not any(keyword in display_name_lower or keyword in email_lower for keyword in NON_HUMAN_KEYWORDS)


def is_matching_domain(user, filter_domain):
    if not filter_domain:
        return True
    email_lower = user.emailAddress.lower() if hasattr(user, 'emailAddress') else ''
    return email_lower.endswith(f"@{filter_domain.lower()}")


def get_filter_status_message(filter_domain):
    return f" (filtered by domain '{filter_domain}')" if filter_domain else ""

def count_comments(changelog_histories):
    if not isinstance(changelog_histories, list):
        return 0

    count = 0
    for history in changelog_histories:
        if not isinstance(history, dict):
            continue

        items = history.get('items', [])
        if not isinstance(items, list):
            # Skip if 'items' is not iterable (e.g., int, None, etc.)
            continue

        for item in items:
            if isinstance(item, dict) and str(item.get('field', '')).lower() == 'comment':
                count += 1

    return count

def count_comments_from_fields(issue, log_list=None):
    try:
        # Ensure issue is a dictionary
        if not isinstance(issue, dict):
            if log_list:
                log_list.append(f"[WARN] Invalid issue type: {type(issue)}")
            return 0

        fields = issue.get("fields", {})
        if not isinstance(fields, dict):
            if log_list:
                log_list.append(f"[WARN] Invalid fields type: {type(fields)}")
            return 0

        comment_obj = fields.get("comment", {})
        if not isinstance(comment_obj, dict):
            if log_list:
                log_list.append(f"[WARN] Invalid comment type: {type(comment_obj)}")
            return 0

        comments = comment_obj.get("comments", [])
        if not isinstance(comments, list):
            if log_list:
                log_list.append(f"[WARN] Invalid comments type: {type(comments)}")
            return 0

        return len(comments)

    except Exception as e:
        if log_list:
            log_list.append(f"[ERROR] Failed to count comments: {e}")
        return 0

def count_transitions(changelog_histories, from_status, to_status, log_list):
    count = 0
    try:
        for history in changelog_histories:
            for item in history.get('items', []):
                if item.get('field') == 'status':
                    from_str = item.get('fromString', '')
                    to_str = item.get('toString', '')
                    if from_str.lower() == from_status.lower() and to_str.lower() == to_status.lower():
                        count += 1
    except Exception as e:
        log_list.append(f"[ERROR] Exception while counting transitions from '{from_status}' to '{to_status}': {e}")
    return count


def seconds_to_dhm(seconds):
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    return f"{days} days {hours} hrs {minutes} mins"

def seconds_to_hm(seconds_str):
    try:
        seconds = int(seconds_str)
    except (ValueError, TypeError):
        return "Invalid input"

    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours} hrs {minutes} mins"

def get_logged_time(histories, log_list, developer_account_id=None):
    total_logged_time = 0
    # print(f"developer_account_id = {developer_account_id}")
    for history in histories:
        author = history.get("author", {})
        account_id = author.get("accountId")

        for item in history.get("items", []):
            if item.get("field") == "timespent":
                try:
                    to_seconds = int(item.get("to", 0))

                    if developer_account_id:
                        # Only accumulate time if author matches the developer
                        if account_id == developer_account_id:
                            total_logged_time = to_seconds
                    else:
                        # Return first available timespent regardless of author
                        return to_seconds

                except (TypeError, ValueError):
                    continue  # skip invalid values

    return total_logged_time if developer_account_id else 0

# def get_logged_time(histories, developer_account_id=None):
#     logged_time = 0

#     if developer_account_id:
#         for history in histories:
#             # print(f"history = {history}")

#             # below is the history data, retrieve the 'To' value for the author.
#             # history = {'id': '597620', 'author': {'self': 'https://truxinc.atlassian.net/rest/api/3/user?accountId=712020%3Ac274c6c5-5313-42db-952f-8b4181f0dbbd', 'accountId': '712020:c274c6c5-5313-42db-952f-8b4181f0dbbd', 'avatarUrls': {'48x48': 'https://secure.gravatar.com/avatar/910bf6c3e5809ce405991f2d17ec7aa5?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FSB-0.png', '24x24': 'https://secure.gravatar.com/avatar/910bf6c3e5809ce405991f2d17ec7aa5?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FSB-0.png', '16x16': 'https://secure.gravatar.com/avatar/910bf6c3e5809ce405991f2d17ec7aa5?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FSB-0.png', '32x32': 'https://secure.gravatar.com/avatar/910bf6c3e5809ce405991f2d17ec7aa5?d=https%3A%2F%2Favatar-management--avatars.us-west-2.prod.public.atl-paas.net%2Finitials%2FSB-0.png'}, 'displayName': 'Suraj Bandgar', 'active': True, 'timeZone': 'America/New_York', 'accountType': 'atlassian'}, 'created': '2025-07-24T01:57:01.438-0400', 'items': [{'field': 'description', 'fieldtype': 'jira', 'fieldId': 'description', 'from': None, 'fromString': 'Change name of Estimate Start time --> Estimate Origin Arrival time ', 'to': None, 'toString': "*Issue :* \n\nThe wording used for drivers estimated time of arrival at a load’s origin location was used as _Estimate Start Time._  We have another event of similar wording “Start Time” of load which defines when a load was started by the driver. Even though these two parameter's names are similar to each other but their is a difference in the occurrence of these events when it comes to subsequent loads. .\n\nFor example, for the 1st load of the day or similar, the Punch in event i.e. Start load event = Estimated start time would be occurring at the same time. However when it comes to start load event of subsequent load, the load would be started at previous loads destinations while the Estimated start time would show time of estimated arrival of the driver at that load’s origin location. \n\n*Expected behavior :*  \n\nThe nomenclature used for arrival time should be changed from Estimated Start time to Estimated Origin Arrival time"}]}
            
#             for item in history.get('items', []):
                
#                 if item.get('author', {}).get('accountId') == developer_account_id:
#                     # try:
#                     #     print(f"item = {item}")
#                     #     logged_time = int(item.get('author', {}).get('to'))
#                     #     break
#                     # except (ValueError, TypeError):
#                     #     return 0  # fallback if conversion fails
#                     print(f"item = \n{item}")
#                     if item.get('field') == 'timespent':
#                         try:
#                             logged_time = int(item['to'])
#                             break
#                         except (ValueError, TypeError):
#                             return 0
#     else:
#         latest_history = histories[0] if histories else None

#         if not latest_history:
#             return 0  # safe fallback

#         for item in latest_history.get('items', []):
#             if item.get('field') == 'timespent':
#                 try:
#                     logged_time = int(item['to'])
#                 except (ValueError, TypeError):
#                     return 0

#     return logged_time

# def get_logged_time(histories, developer_account_id=None):
#     logged_time = 0
#     latest_history = histories[0] if histories else None

#     if not latest_history:
#         return 0  # safe fallback

#     for item in latest_history.get('items', []):
#         # print(f"developer_account_id = {developer_account_id}...")  # Debugging line
#         if developer_account_id:
#             print(f"item = {item}...")  # Debugging line")
#             if item.get('field') == 'timespent' and item.get('author', {}).get('accountId') == developer_account_id:
#                 try:
                    
#                     logged_time = int(item.get('author', {}).get('to'))
#                 except (ValueError, TypeError):
#                     return 0 # fallback if conversion fails
#         else:
#             if item.get('field') == 'timespent':
#                 try:
#                     logged_time = int(item['to'])
#                 except (ValueError, TypeError):
#                     return 0
#         # if item.get('field') == 'timespent':
#         #     try:
#         #         logged_time = int(item['to'])
#         #     except (ValueError, TypeError):
#         #         return 0  # fallback if conversion fails
#             # break

#     return logged_time


# --- Helper function to process a list of issues and extract metrics ---
# MODIFIED: Added 'headers' parameter
def _process_jira_issues(issues, sprint_id, log_list, headers, developer_account_id=None):
    metrics = initialize_metrics()
    log_list.append(f"[DEBUG] Processing {len(issues)} issues with sprint_id: {sprint_id}")
    
    filtered_count = 0
    for issue in issues:
        if sprint_id and not _filter_issues_by_sprint(issue, sprint_id):
            log_list.append(f"[DEBUG] Issue {issue.get('key')} filtered out (not in sprint {sprint_id})")
            continue
        filtered_count += 1
        _update_metrics(issue, metrics, headers, log_list, developer_account_id)
    
    log_list.append(f"[DEBUG] {filtered_count} issues passed sprint filter")
    return summarize_metrics(metrics, issues)


def _filter_issues_by_sprint(issue, sprint_id):
    # Skip filtering for openSprints() and startOfYear() - they're handled by JQL
    if sprint_id in ["openSprints()", "startOfYear()"]:
        return True
        
    issue_sprints = issue.get("fields", {}).get("customfield_10010", [])
    return any(
        sprint_id.lower() in str(s.get("name", "")).lower() or sprint_id == str(s.get("id", ""))
        for s in issue_sprints if isinstance(s, dict)
    ) if isinstance(issue_sprints, list) else sprint_id.lower() in issue_sprints.lower()


def _update_metrics(issue, metrics, headers, log_list, developer_account_id=None):
    changelog = issue.get("changelog", {}).get("histories", [])

    # print("[DEBUG] issue type:", type(issue))
    # print("[DEBUG] issue content:", issue)
    # metrics["comments_count"] += count_comments_from_fields(issue, log_list)
    metrics["failed_qa_count"] += count_transitions(changelog, "In Testing", "Rejected", log_list)
    metrics["logged_time"] += get_logged_time(changelog, log_list, developer_account_id)
    _process_dev_panel(issue, headers, log_list, metrics["dev_branches"])

    value = issue.get("fields", {}).get("customfield_10014")
    issue_key = issue.get("key", "Unknown")
    try:
        points = float(value) if value is not None else 0.0
        metrics["story_points"] += points
        if points > 0:
            log_list.append(f"[DEBUG] JIRA: Added {points} story points from issue {issue_key}")
    except (TypeError, ValueError):
        metrics["story_points"] += 0.0
        log_list.append(f"[DEBUG] JIRA: No story points for issue {issue_key} (value: {value})")

    _update_closure_metrics(issue, metrics)
    in_progress_date, done_date = _calculate_times(changelog)
    _update_time_metrics(issue, metrics, in_progress_date, done_date)


def _process_dev_panel(issue, headers, log_list, dev_branches):
    dev_panel_url = f"{JIRA_URL}/rest/dev-status/1.0/issue/detail"
    dev_panel_params = {"issueId": issue["id"], "applicationType": "GitHub", "dataType": "repository"}
    try:
        dev_resp = requests.get(dev_panel_url, headers=headers, params=dev_panel_params)
        dev_resp.raise_for_status()
        dev_data = dev_resp.json()
        _extract_repositories(dev_data, dev_branches)
    except requests.exceptions.RequestException as e:
        log_list.append(f"[WARNING] JIRA Dev Panel API Error: {e}")


def _extract_repositories(dev_data, dev_branches):
    details = dev_data.get("detail", [])
    
    if not details or not isinstance(details, list):
        return  # or log a warning if needed

    first_detail = details[0]
    if not isinstance(first_detail, dict):
        return  # defensive check

    for repo_entry in first_detail.get("repositories", []):
        repo_name = repo_entry.get("name") or repo_entry.get("url", "").replace("https://github.com/", "").strip("/")
        if repo_name:
            dev_branches.add(repo_name)


def _calculate_times(changelog):
    in_progress_date, done_date = None, None
    for entry in changelog:
        for item in entry["items"]:
            if item["field"] == "status":
                in_progress_date, done_date = _update_status_dates(item, entry, in_progress_date, done_date)
    return in_progress_date, done_date


def _update_status_dates(item, entry, in_progress_date, done_date):
    to_status = item["toString"].lower()
    if to_status == "in progress" and not in_progress_date:
        in_progress_date = entry["created"]
    elif to_status in ["qa complete", "done", "released", "closed"] and not done_date:
        done_date = entry["created"]
    return in_progress_date, done_date

def _update_closure_metrics(issue, metrics):
    fields = issue.get("fields", {})
    status = fields.get("status", {}).get("name", "").lower()
    issue_type = fields.get("issuetype", {}).get("name", "").lower()

    if status in ["qa complete", "done", "released", "closed"]:
        if issue_type == "bug":
            metrics["bugs_closed"] += 1
        else:
            metrics["tickets_closed"] += 1


def _update_time_metrics(issue, metrics, in_progress_date, done_date):
    if in_progress_date and done_date:
        metrics["cycle_times"].append((parser.isoparse(done_date) - parser.isoparse(in_progress_date)).days)
    if issue.get("fields", {}).get("created") and done_date:
        metrics["lead_times"].append((parser.isoparse(done_date) - parser.isoparse(issue["fields"]["created"])).days)


def initialize_metrics():
    return {
        "story_points": 0, "tickets_closed": 0, "bugs_closed": 0, 
        # "comments_count": [],
        "lead_times": [], "cycle_times": [], "dev_branches": set(), "failed_qa_count": 0, "logged_time": 0
    }


def summarize_metrics(metrics, issues):
    result = {
        "all_issues_count": len(issues),
        "story_points_done": metrics["story_points"],
        "tickets_closed": metrics["tickets_closed"],
        "bugs_closed": metrics["bugs_closed"],
        # "avg_comments": round(statistics.mean(metrics["comments_count"]), 2) if metrics["comments_count"] else 0,
        "avg_lead_time": round(statistics.mean(metrics["lead_times"]), 2) if metrics["lead_times"] else "N/A",
        "avg_cycle_time": round(statistics.mean(metrics["cycle_times"]), 2) if metrics["cycle_times"] else "N/A",
        "dev_branches": list(metrics["dev_branches"]),
        "failed_qa_count": metrics["failed_qa_count"],
        "logged_time": metrics["logged_time"],
    }
    # Debug final story points
    print(f"[DEBUG] Final story points calculation: {metrics['story_points']} from {len(issues)} issues")
    return result


# --- Function to fetch JIRA metrics for an Individual Developer ---
# MODIFIED: Added 'headers' variable creation and passing to _process_jira_issues
def fetch_jira_metrics_via_api(jira_email, jira_token, developer_name, sprint_id, team_name, log_list):
    log_list.append(f"[INFO] JIRA: Starting fetch for individual developer '{developer_name}' in sprint '{sprint_id}' for team name '{team_name}'...")
    
    if not jira_email or not jira_token:
        log_list.append("[ERROR] JIRA: Credentials (email/token) not provided.")
        return {"error": "JIRA credentials not provided."}
    
    auth_string = f"{jira_email}:{jira_token}".encode("utf-8")
    encoded_auth = base64.b64encode(auth_string).decode("utf-8")
    headers = { # Headers are defined here
        "Authorization": f"Basic {encoded_auth}",
        "Accept": "application/json"
    }

    # Construct JQL query for individual developer
    jql_parts = [f'assignee="{developer_name}"']
    if sprint_id:
        if sprint_id == "openSprints()":
            jql_parts.append("sprint in openSprints()")
        elif sprint_id == "startOfYear()":
            jql_parts.append("created >= startOfYear()")
        else:
            jql_parts.append(f'sprint = "{team_name} {sprint_id}"')

    
    jql = " AND ".join(jql_parts)
    url = f"{JIRA_URL}/rest/api/3/search"

    params = {
        "jql": jql,
        "maxResults": 100, 
        "fields": "summary,issuetype,assignee,created,comment,customfield_10014,status,customfield_10000,customfield_10001,customfield_10010", 
        "expand": "changelog" 
    }

    try:
        log_list.append(f"[INFO] JIRA individual API: GET {url}")
        log_list.append(f"[DEBUG] JIRA Individual JQL: {jql}")
        log_list.append(f"[DEBUG] JIRA Individual Params: {params}")
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status() 
        log_list.append(f"[INFO] JIRA API: GET {url} - Status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        log_list.append(f"[ERROR] JIRA API Request Error: {e}")
        return {"error": f"JIRA API failed: {e}"}

    issues = response.json().get("issues", [])
    log_list.append(f"[INFO] Fetched {len(issues)} issues for individual developer '{developer_name}' in sprint '{sprint_id}'.")
    log_list.append(f"[DEBUG] Individual Issues: {[issue.get('key') for issue in issues[:5]]}...")  # Show first 5 issue keys
    if not issues:
        log_list.append("[WARNING] JIRA: No issues found for the specified individual developer/team/sprint combination.")
        return {"error": "No issues found for individual developer/team/sprint.", "dev_branches": []}

    # get developer account ID
    url = f"{JIRA_URL}/rest/api/3/user/search?query={developer_name.lower()}"
    developer_account_id = None
    try:
        account_response = requests.get(url, headers=headers)
        account_response.raise_for_status() 
        users = account_response.json()
        for user in users:
            developer_account_id = user.get("accountId")
            if developer_account_id:
                break

        if not developer_account_id:
            log_list.append(f"[WARNING] JIRA: Developer '{developer_name}' not found in JIRA.")
            return {"error": f"Developer '{developer_name}' not found in JIRA.", "dev_branches": []}
    
        # log_list.append(f"[INFO] JIRA API: GET {url} - Status: {response.status_code} - Account Id: {developer_account_id}")
    except requests.exceptions.RequestException as e:
        log_list.append(f"[ERROR] JIRA API Request Error: {e}")
        return {"error": f"JIRA API failed: {e}"}

    # print(f"developer_account_id 222 = {developer_account_id}...")  # Debugging line

    # MODIFIED: Pass 'headers' to _process_jira_issues
    return _process_jira_issues(issues, sprint_id, log_list, headers, developer_account_id)


# --- New: Function to fetch JIRA metrics for a Team ---
# MODIFIED: Added 'headers' variable creation and passing to _process_jira_issues
def fetch_jira_metrics_for_team(jira_email, jira_token, team_id, team_name, sprint_id, log_list):
    log_list.append(f"[INFO] JIRA: Starting fetch for TEAM '{team_name}' (ID: {team_id}) in sprint '{sprint_id}'...")
    
    if not jira_email or not jira_token:
        log_list.append("[ERROR] JIRA: Credentials (email/token) not provided for team fetch.")
        return {"error": "JIRA credentials not provided."}
    
    auth_string = f"{jira_email}:{jira_token}".encode("utf-8")
    encoded_auth = base64.b64encode(auth_string).decode("utf-8")
    headers = { # Headers are defined here
        "Authorization": f"Basic {encoded_auth}",
        "Accept": "application/json"
    }

    # Construct JQL query for the team
    jql_parts = []
    if team_id:
        jql_parts.append(f"'Team[Team]' = \"{team_id}\"") # Filter by team ID
    else:
        log_list.append("[ERROR] JIRA Team Fetch: Team ID is required for team metrics.")
        return {"error": "Team ID not provided."}

    jql_parts.append("issuetype NOT IN (Sub-task, Epic)")

    if sprint_id:
        if sprint_id == "openSprints()":
            jql_parts.append("sprint in openSprints()")
        elif sprint_id == "startOfYear()":
            jql_parts.append("created >= startOfYear()")
        else:
            jql_parts.append(f'sprint = "{team_name} {sprint_id}"')

    jql = " AND ".join(jql_parts)
    url = f"{JIRA_URL}/rest/api/3/search"

    params = {
        "jql": jql,
        "maxResults": 100, 
        "fields": "summary,issuetype,assignee,created,comment,customfield_10014,status,customfield_10000,customfield_10001,customfield_10010", 
        "expand": "changelog" 
    }

    try:
        log_list.append(f"[INFO] JIRA Team API: GET {url}")
        log_list.append(f"[DEBUG] JIRA Team JQL: {jql}")
        log_list.append(f"[DEBUG] JIRA Team Params: {params}")
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status() 
        log_list.append(f"[INFO] JIRA Team API: Status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        log_list.append(f"[ERROR] JIRA Team API Request Error: {e}")
        return {"error": f"JIRA Team API failed: {e}"}

    issues = response.json().get("issues", [])
    log_list.append(f"[INFO] Fetched {len(issues)} issues for team '{team_name}' in sprint '{sprint_id}'.")
    log_list.append(f"[DEBUG] Team Issues: {[issue.get('key') for issue in issues[:5]]}...")  # Show first 5 issue keys
    if not issues:
        log_list.append("[WARNING] JIRA Team: No issues found for the specified team/sprint combination.")
        return {"error": "No issues found for team/sprint.", "dev_branches": []}

    # MODIFIED: Pass 'headers' to _process_jira_issues
    return _process_jira_issues(issues, sprint_id, log_list, headers)