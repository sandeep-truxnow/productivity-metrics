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
        try:
            users_page = jira_instance.search_users(query='*', startAt=start_at, maxResults=max_results)
            if not users_page: break
            
            for user in users_page:
                is_human = True
                if hasattr(user, 'accountType') and user.accountType.lower() != 'atlassian':
                    is_human = False 
                
                if is_human:
                    display_name_lower = user.displayName.lower() if hasattr(user, 'displayName') else ''
                    email_lower = user.emailAddress.lower() if hasattr(user, 'emailAddress') else ''
                    NON_HUMAN_KEYWORDS = ['[app]', 'automation', 'bot', 'service', 'plugin', 'jira-system', 'addon', 'connect', 'integration', 'github', 'slack', 'webhook', 'migrator', 'system', 'importer', 'syncer']
                    for keyword in NON_HUMAN_KEYWORDS:
                        if keyword in display_name_lower or keyword in email_lower:
                            is_human = False
                            break

                is_matching_domain = True
                if filter_domain:
                    if not email_lower or not email_lower.endswith(f"@{filter_domain.lower()}"): 
                        is_matching_domain = False

                if is_human and is_matching_domain:
                    all_users[user.accountId] = {
                        'displayName': user.displayName if hasattr(user, 'displayName') else user.accountId,
                        'emailAddress': user.emailAddress if hasattr(user, 'emailAddress') else 'N/A'
                    }
            start_at += max_results
            if len(users_page) < max_results: break 
        except JIRAError as e:
            log_list.append(f"[ERROR] JIRA Users: Error fetching users: Status {e.status_code} - {e.text}")
            break
        except Exception as e:
            log_list.append(f"[ERROR] JIRA Users: An unexpected error occurred while fetching users: {e}")
            break
    
    filter_status_message = ""
    if filter_domain:
        filter_status_message = f" (filtered by domain '{filter_domain}')"
    
    log_list.append(f"[INFO] JIRA Users: Fetched {len(all_users)} active human Jira users{filter_status_message}.")
    return all_users


# --- Helper function to process a list of issues and extract metrics ---
# MODIFIED: Added 'headers' parameter
def _process_jira_issues(issues, sprint_id, log_list, headers):
    story_points = 0
    tickets_closed = 0
    bugs_closed = 0
    comments_count_per_ticket = []
    lead_times = []
    cycle_times = []
    dev_branches = set() # Use a set to store unique branch names

    for issue in issues:
        fields = issue["fields"]
        changelog = issue.get("changelog", {}).get("histories", [])
        issue_key = issue.get("key", "N/A") 
        issue_type = fields.get("issuetype", {}).get("name", "").lower()
        status = fields.get("status", {}).get("name", "").lower()
        created = fields.get("created")
        comments_count_per_ticket.append(len(fields.get("comment", {}).get("comments", [])))

        # Filter by sprint_id if provided and not empty
        is_in_sprint = False
        if sprint_id: 
            issue_sprints = fields.get("customfield_10010", []) 
            if isinstance(issue_sprints, list):
                for s in issue_sprints:
                    if isinstance(s, dict):
                        if sprint_id.lower() in str(s.get('name', '')).lower() or \
                           sprint_id == str(s.get('id', '')): 
                            is_in_sprint = True
                            break
                    elif isinstance(s, str): 
                        if sprint_id.lower() in s.lower():
                            is_in_sprint = True
                            break
            elif isinstance(issue_sprints, str): 
                if sprint_id.lower() in issue_sprints.lower():
                    is_in_sprint = True
            
            if not is_in_sprint: 
                # log_list.append(f"[DEBUG] JIRA: Skipping issue {issue_key} (not in sprint '{sprint_id}').")
                continue 
        else: 
            is_in_sprint = True

        log_list.append(f"[INFO] JIRA: Processing issue {issue_key} (status: {status}, in_sprint: {is_in_sprint})")

        # Development panel (linked repos/branches)
        dev_panel_url = f"{JIRA_URL}/rest/dev-status/1.0/issue/detail"
        dev_panel_params = {"issueId": issue["id"], "applicationType": "GitHub", "dataType": "repository"}
        try:
            # MODIFIED: Pass 'headers' to requests.get
            dev_resp = requests.get(dev_panel_url, headers=headers, params=dev_panel_params)
            dev_resp.raise_for_status()
            dev_data = dev_resp.json()
            
            detail = dev_data.get("detail", [])
            if detail:
                repos_in_dev_panel = detail[0].get("repositories", [])
                if repos_in_dev_panel:
                    log_list.append(f"[DEBUG] JIRA Dev Panel for {issue_key}: Found {len(repos_in_dev_panel)} repositories.")
                    for repo_entry in repos_in_dev_panel:
                        repo_name_from_jira = repo_entry.get("name")
                        if repo_name_from_jira:
                            dev_branches.add(repo_name_from_jira)
                            log_list.append(f"[DEBUG] JIRA Dev Panel: Added repo '{repo_name_from_jira}' from name for {issue_key}.")
                        elif repo_entry.get("url"): 
                            try:
                                url_path = repo_entry['url'].replace('https://github.com/', '').strip('/')
                                if '/' in url_path:
                                    dev_branches.add(url_path)
                                    log_list.append(f"[DEBUG] JIRA Dev Panel: Added repo '{url_path}' from URL for {issue_key}.")
                            except Exception as parse_e:
                                log_list.append(f"[WARNING] JIRA Dev Panel: Could not parse repo name from URL '{repo_entry.get('url')}' for {issue_key}: {parse_e}")
                else:
                    log_list.append(f"[DEBUG] JIRA Dev Panel for {issue_key}: 'repositories' list is empty or not found in detail.")
            else:
                log_list.append(f"[DEBUG] JIRA Dev Panel for {issue_key}: 'detail' is empty or not found.")

        except requests.exceptions.RequestException as e:
            log_list.append(f"[WARNING] JIRA Dev Panel API Error for issue {issue_key}: {e}")
        
        story_points += fields.get("customfield_10014") or 0

        if status in ["done", "released", "closed"]:
            tickets_closed += 1
            if issue_type == "bug":
                bugs_closed += 1

        in_progress_date = None
        done_date = None

        for entry in changelog:
            for item in entry["items"]:
                if item["field"] == "status":
                    to_status = item["toString"].lower()
                    if to_status == "in progress" and not in_progress_date:
                        in_progress_date = entry["created"]
                    elif to_status in ["done", "released", "closed"] and not done_date:
                        done_date = entry["created"]
            
        if in_progress_date and done_date:
            try:
                delta = (parser.isoparse(done_date) - parser.isoparse(in_progress_date)).days
                if delta >= 0: cycle_times.append(delta)
            except ValueError as ve:
                log_list.append(f"[WARNING] JIRA: Could not parse cycle time dates for {issue_key}: {ve}")
        if created and done_date:
            try:
                delta = (parser.isoparse(done_date) - parser.isoparse(created)).days
                if delta >= 0: lead_times.append(delta)
            except ValueError as ve:
                log_list.append(f"[WARNING] JIRA: Could not parse lead time dates for {issue_key}: {ve}")

    return {
        "all_issues_count": len(issues),
        "story_points_done": story_points, 
        "tickets_closed": tickets_closed,
        "bugs_closed": bugs_closed,
        "avg_comments": round(statistics.mean(comments_count_per_ticket), 2) if comments_count_per_ticket else 0,
        "avg_lead_time": round(statistics.mean(lead_times), 2) if lead_times else "N/A",
        "avg_cycle_time": round(statistics.mean(cycle_times), 2) if cycle_times else "N/A",
        "dev_branches": list(dev_branches),
    }


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
        jql_parts.append(f'sprint = "{team_name} {sprint_id}"') # Adjust JQL for sprint if needed (e.g., openSprints())

    
    jql = " AND ".join(jql_parts)
    url = f"{JIRA_URL}/rest/api/3/search"

    params = {
        "jql": jql,
        "maxResults": 100, 
        "fields": "summary,issuetype,assignee,created,comment,customfield_10014,status,customfield_10000,customfield_10001,customfield_10010", 
        "expand": "changelog" 
    }

    try:
        # log_list.append(f"[INFO] JIRA individual API: GET {url} \n Headers: {headers} \n Params: {params}")
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status() 
        log_list.append(f"[INFO] JIRA API: GET {url} - Status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        log_list.append(f"[ERROR] JIRA API Request Error: {e}")
        return {"error": f"JIRA API failed: {e}"}

    issues = response.json().get("issues", [])
    log_list.append(f"[INFO] Fetched {len(issues)} issues for individual developer '{developer_name}' in sprint '{sprint_id}'.")
    if not issues:
        log_list.append("[WARNING] JIRA: No issues found for the specified individual developer/team/sprint combination.")
        return {"error": "No issues found for individual developer/team/sprint.", "dev_branches": []}

    # MODIFIED: Pass 'headers' to _process_jira_issues
    return _process_jira_issues(issues, sprint_id, log_list, headers)


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
        jql_parts.append(f'sprint = "{team_name} {sprint_id}"') # Adjust JQL for sprint if needed (e.g., openSprints())

    jql = " AND ".join(jql_parts)
    url = f"{JIRA_URL}/rest/api/3/search"

    params = {
        "jql": jql,
        "maxResults": 100, 
        "fields": "summary,issuetype,assignee,created,comment,customfield_10014,status,customfield_10000,customfield_10001,customfield_10010", 
        "expand": "changelog" 
    }

    try:
        # log_list.append(f"[INFO] JIRA Team API: GET {url} \n Headers: {headers} \n Params: {params}")
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status() 
        log_list.append(f"[INFO] JIRA API: GET {url} - Status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        log_list.append(f"[ERROR] JIRA Team API Request Error: {e}")
        return {"error": f"JIRA Team API failed: {e}"}

    issues = response.json().get("issues", [])
    log_list.append(f"[INFO] Fetched {len(issues)} issues for team '{team_name}' in sprint '{sprint_id}'.")
    if not issues:
        log_list.append("[WARNING] JIRA Team: No issues found for the specified team/sprint combination.")
        return {"error": "No issues found for team/sprint.", "dev_branches": []}

    # MODIFIED: Pass 'headers' to _process_jira_issues
    return _process_jira_issues(issues, sprint_id, log_list, headers)