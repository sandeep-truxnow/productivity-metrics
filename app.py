import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from collections import OrderedDict
import statistics as stats

# --- Import from local utility files ---
from utils.jira_parser import fetch_jira_metrics_via_api, connect_to_jira_streamlit, get_all_jira_users_streamlit, fetch_jira_metrics_for_team # NEW: Import for team JIRA metrics
from utils.git_parser import fetch_git_metrics_via_api
from utils.sonar_parser import fetch_all_sonar_projects, fetch_single_project_metrics, RATING_MAP

# Set Streamlit page configuration
st.set_page_config(
    page_title="Productivity Metrics Dashboard",
    layout="wide",
    initial_sidebar_state="auto",
    page_icon=":bar_chart:",
)

st.title("📊 Productivity Dashboard")


# --- Configuration Constants ---
TEAMS_DATA = OrderedDict([
    ("A Team", "34e068f6-978d-4ad9-4aef-3bf5eec72f65"),
    ("Avengers", "8d39d512-0220-4711-9ad0-f14fbf74a50e"),
    ("Jarvis", "1ec8443e-a42c-4613-bc88-513ee29203d0"),
    ("Mavrix", "1d8f251a-8fd9-4385-8f5f-6541c28bda19"),
    ("Phoenix", "ac9cc58b-b860-4c4d-8a4e-5a64f50c5122"),
    ("Quantum", "99b45e3f-49de-446c-b28d-25ef8e915ad6")
])


# --- Helper for capturing Streamlit messages (remains in app.py as UI-level helper) ---
def add_log_message(log_list, level, message):
    """Appends a timestamped log message to the log list and optionally displays immediate feedback."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_list.append(f"[{timestamp}] [{level.upper()}] {message}")
    if level == "error" or level == "critical":
        st.error(f"[{timestamp}] {message}")
    elif level == "warning":
        st.warning(f"[{timestamp}] {message}")


# --- Initialize Session State Variables ---
if 'data_fetched' not in st.session_state: st.session_state.data_fetched = False
if 'log_messages' not in st.session_state: st.session_state.log_messages = []
if 'jira_result_individual' not in st.session_state: st.session_state.jira_result_individual = {} # Individual metrics
if 'git_metrics_individual' not in st.session_state: st.session_state.git_metrics_individual = {} # Individual metrics
if 'sonar_all_projects_data_individual' not in st.session_state: st.session_state.sonar_all_projects_data_individual = [] # Individual metrics
if 'sonar_errors_individual' not in st.session_state: st.session_state.sonar_errors_individual = [] # Individual metrics
if 'sonar_key_map_global' not in st.session_state: st.session_state.sonar_key_map_global = {}

# NEW: Team-level metrics storage
if 'jira_result_team' not in st.session_state: st.session_state.jira_result_team = {}
if 'git_metrics_team' not in st.session_state: st.session_state.git_metrics_team = {}
if 'sonar_metrics_team' not in st.session_state: st.session_state.sonar_metrics_team = []
if 'team_sonar_errors' not in st.session_state: st.session_state.team_sonar_errors = []


# Input widget values (to persist across reruns)
if 'jira_email_input' not in st.session_state: st.session_state.jira_email_input = ""
if 'jira_token_input' not in st.session_state: st.session_state.jira_token_input = ""
if 'github_token_input' not in st.session_state: st.session_state.github_token_input = ""
if 'sonar_token_input' not in st.session_state: st.session_state.sonar_token_input = ""
if 'sonar_org_input' not in st.session_state: st.session_state.sonar_org_input = "truxinc"

# Jira connection and developer list specific session states
if 'jira_conn_details' not in st.session_state: st.session_state.jira_conn_details = None
if 'available_developers' not in st.session_state: st.session_state.available_developers = []
if 'jira_users_loaded' not in st.session_state: st.session_state.jira_users_loaded = False 

# Selection states for dropdowns
if 'selected_developer_name' not in st.session_state: st.session_state.selected_developer_name = "--- Select a Developer ---"
if 'selected_team_name' not in st.session_state: st.session_state.selected_team_name = list(TEAMS_DATA.keys())[0]
if 'selected_team_id' not in st.session_state: st.session_state.selected_team_id = TEAMS_DATA[list(TEAMS_DATA.keys())[0]]
if 'sprint_id_input' not in st.session_state: st.session_state.sprint_id_input = ""


# --- Sidebar Inputs ---
with st.sidebar:
    st.header("🔐 API Tokens")
    jira_email = st.text_input("JIRA Email (used for token)", value=st.session_state.jira_email_input, type="default", key="jira_email_widget")
    st.session_state.jira_email_input = jira_email

    jira_token = st.text_input("JIRA API Token", value=st.session_state.jira_token_input, type="password", key="jira_token_widget")
    st.session_state.jira_token_input = jira_token

    github_token = st.text_input("GitHub Token", value=st.session_state.github_token_input, type="password", key="github_token_widget")
    st.session_state.github_token_input = github_token

    sonar_token = st.text_input("SonarQube Token", value=st.session_state.sonar_token_input, type="password", help="Your SonarCloud Personal Access Token.", key="sonar_token_widget")
    st.session_state.sonar_token_input = sonar_token

    sonar_org = st.text_input("SonarQube Organization Key", value=st.session_state.sonar_org_input, help="Your SonarCloud organization key (e.g., 'truxinc').", key="sonar_org_widget")
    st.session_state.sonar_org_input = sonar_org

    st.markdown("---")
    st.subheader("🧑‍💻 Report Filters")

    # --- JIRA Connection & Load Developers Button ---
    if st.button("Connect to JIRA & Load Developers"):
        st.session_state.log_messages = [] # Clear logs for connection attempt
        st.session_state.jira_users_loaded = False # Reset flag
        st.session_state.available_developers = [] # Clear previous list

        if not jira_email or not jira_token:
            add_log_message(st.session_state.log_messages, "error", "JIRA email and API token are required to connect.")
            st.rerun() 
        
        with st.spinner("Connecting to JIRA and fetching user list..."):
            # jira_username_for_conn = jira_email.split('@')[0]
            jira_instance_conn = connect_to_jira_streamlit("https://truxinc.atlassian.net", jira_email, jira_token, log_list=st.session_state.log_messages)
            
            if jira_instance_conn:
                st.session_state.jira_conn_details = ("https://truxinc.atlassian.net", jira_email, jira_token)
                add_log_message(st.session_state.log_messages, "success", "JIRA connection established for user lookup.")
                
                all_jira_users_map = get_all_jira_users_streamlit(st.session_state.jira_conn_details[0], st.session_state.jira_conn_details[1], st.session_state.jira_conn_details[2], log_list=st.session_state.log_messages)
                
                if all_jira_users_map:
                    sorted_developers = sorted([user_data['displayName'] for user_data in all_jira_users_map.values()])
                    st.session_state.available_developers = sorted_developers
                    st.session_state.jira_users_loaded = True 
                    add_log_message(st.session_state.log_messages, "success", f"Loaded {len(st.session_state.available_developers)} active developers from Jira.")
                else:
                    st.session_state.available_developers = []
                    st.session_state.jira_users_loaded = False
                    add_log_message(st.session_state.log_messages, "warning", "No active developers found or failed to fetch developers from Jira.")
            else:
                st.session_state.jira_conn_details = None
                st.session_state.jira_users_loaded = False
                add_log_message(st.session_state.log_messages, "error", "Failed to connect to JIRA for user lookup. Check credentials and URL.")
        st.rerun() 

    # --- Team Selection ---
    team_names_display = list(TEAMS_DATA.keys())
    current_team_idx = team_names_display.index(st.session_state.selected_team_name) if st.session_state.selected_team_name in team_names_display else 0

    selected_team_name_widget = st.selectbox(
        "Select Team",
        options=team_names_display,
        index=current_team_idx,
        key="team_selector_widget_key",
        help="Select the team to filter issues."
    )
    st.session_state.selected_team_name = selected_team_name_widget
    st.session_state.selected_team_id = TEAMS_DATA.get(st.session_state.selected_team_name)

    # --- Developer Selection (Dropdown) - Now conditional on Jira users being loaded ---
    if st.session_state.jira_users_loaded:
        current_dev_idx = 0
        if st.session_state.selected_developer_name in st.session_state.available_developers:
            current_dev_idx = st.session_state.available_developers.index(st.session_state.selected_developer_name) + 1 
        
        selected_developer_name_widget = st.selectbox(
            "Select Developer",
            options=["--- Select a Developer ---"] + st.session_state.available_developers,
            index=current_dev_idx,
            key="developer_selector_widget",
            help="Choose the developer whose metrics you want to analyze."
        )
        st.session_state.selected_developer_name = selected_developer_name_widget if selected_developer_name_widget != "--- Select a Developer ---" else None
    else:
        st.info("Please connect to JIRA first to load available developers.")
        st.session_state.selected_developer_name = None 

    # --- Sprint ID Input ---
    sprint_id = st.text_input("Sprint ID (e.g., 2025.12)", value=st.session_state.sprint_id_input, help="Sprint IDs in the format of YYYY.<sprint_number>.", key="sprint_id_widget")
    st.session_state.sprint_id_input = sprint_id

    st.markdown("---")
    generate_metrics_button = st.button("Generate Metrics")


# --- Function to fetch all metrics (orchestrates calls to utility modules) ---
def _fetch_all_metrics(jira_email, jira_token, github_token, sonar_token, sonar_org, developer_name_ui, sprint_id_ui, team_name_ui, team_id_ui, log_list):
    """Orchestrates fetching metrics for both individual and team."""
    
    # Individual metrics
    jira_result_individual = {"error": "Not fetched"}
    git_metrics_individual = {"error": "Not fetched"}
    sonar_all_projects_data_individual = []
    sonar_errors_individual = []
    team_sonar_errors = []

    # Team metrics
    jira_result_team = {"error": "Not fetched"}
    git_metrics_team = {"error": "Not fetched"}
    sonar_metrics_team = []

    dev_repos_from_jira_individual = [] 

    try:
        # --- Fetch INDIVIDUAL JIRA Metrics ---
        if developer_name_ui and developer_name_ui != "--- Select a Developer ---":
            add_log_message(log_list, "info", f"Initiating INDIVIDUAL JIRA metrics fetch for developer '{developer_name_ui}' in sprint '{sprint_id_ui}'...")
            jira_result_individual = fetch_jira_metrics_via_api(
                jira_email, jira_token, developer_name_ui, 
                sprint_id=sprint_id_ui, 
                team_name=team_name_ui, 
                log_list=log_list
            )
            if "error" in jira_result_individual:
                add_log_message(log_list, "error", f"INDIVIDUAL JIRA Error: {jira_result_individual['error']}")
                dev_repos_from_jira_individual = [] 
            else:
                dev_repos_from_jira_individual = jira_result_individual.get("dev_branches", [])
        else:
            add_log_message(log_list, "warning", "No individual developer selected. Skipping individual JIRA metrics fetch.")
            jira_result_individual = {"error": "No developer selected."}


        # --- Fetch TEAM JIRA Metrics ---
        if team_id_ui:
            add_log_message(log_list, "info", f"Initiating TEAM JIRA metrics fetch for team '{team_name_ui}' in sprint '{sprint_id_ui}'...")
            jira_result_team = fetch_jira_metrics_for_team(
                jira_email, jira_token, team_id_ui, team_name_ui,
                sprint_id=sprint_id_ui,
                log_list=log_list
            )
            if "error" in jira_result_team:
                add_log_message(log_list, "error", f"TEAM JIRA Error: {jira_result_team['error']}")
                dev_repos_from_jira_team = [] 
            else:
                dev_repos_from_jira_team = jira_result_team.get("dev_branches", [])
            
        else:
            add_log_message(log_list, "warning", "No team selected. Skipping team JIRA metrics fetch.")
            jira_result_team = {"error": "No team selected."}


        # --- Fetch INDIVIDUAL Git Metrics ---
        if developer_name_ui and developer_name_ui != "--- Select a Developer ---":
            add_log_message(log_list, "info", "Initiating INDIVIDUAL Git metrics fetch...")
            git_metrics_individual = fetch_git_metrics_via_api(
                github_token, developer_name_ui, dev_repos_from_jira_individual, 
                log_list=log_list,
                github_org_key=sonar_org,
                sprint_id=sprint_id_ui
            )
            if "error" in git_metrics_individual:
                add_log_message(log_list, "error", f"INDIVIDUAL Git Error: {git_metrics_individual['error']}")
        else:
            add_log_message(log_list, "warning", "No individual developer selected. Skipping individual Git metrics fetch.")
            git_metrics_individual = {"error": "No developer selected."}

        # --- Fetch TEAM Git Metrics (Placeholder) ---
        # add_log_message(log_list, "warning", "TEAM Git metrics aggregation is not fully implemented. This is a placeholder.")
        # git_metrics_team = {"error": "Team Git aggregation not implemented."}
        if team_id_ui:
            add_log_message(log_list, "info", f"Initiating TEAM Git metrics fetch for team '{team_name_ui}' in sprint '{sprint_id_ui}'...")
            git_metrics_team = fetch_git_metrics_via_api(
                github_token, developer_name_ui, dev_repos_from_jira_team, 
                log_list=log_list,
                github_org_key=sonar_org,
                sprint_id=sprint_id_ui
            )
            if "error" in jira_result_team:
                add_log_message(log_list, "error", f"TEAM JIRA Error: {jira_result_team['error']}")
        else:
            add_log_message(log_list, "warning", "No team selected. Skipping team JIRA metrics fetch.")
            jira_result_team = {"error": "No team selected."}


        # --- Fetch INDIVIDUAL Sonar Metrics ---
        if dev_repos_from_jira_individual: 
            add_log_message(log_list, "info", f"Sonar: Attempting to fetch INDIVIDUAL SonarCloud metrics for {len(dev_repos_from_jira_individual)} linked repositories.")
            
            add_log_message(log_list, "info", "Sonar: Discovering all projects in organization...")
            all_sonar_org_projects = fetch_all_sonar_projects(sonar_token, sonar_org, log_list=log_list)
            
            if "error" in all_sonar_org_projects:
                sonar_errors_individual.append(f"SonarCloud Project List Error: {all_sonar_org_projects['error']}")
                add_log_message(log_list, "error", f"Sonar: Project List Error: {all_sonar_org_projects['error']}")
            else:
                sonar_key_map = {} 
                for project in all_sonar_org_projects:
                    sonar_key_map[project['key'].lower()] = project['key']
                    sonar_key_map[project['name'].lower()] = project['key']
                    
                    if project['key'].startswith(sonar_org + '_') and '_' in project['key']:
                        derived_jira_format = project['key'].replace('_', '/', 1)
                        sonar_key_map[derived_jira_format.lower()] = project['key']
                    elif '/' in project['key'] and project['key'].startswith(sonar_org + '/'):
                        sonar_key_map[project['key'].lower()] = project['key']

                st.session_state.sonar_key_map_global = sonar_key_map

                sonar_projects_to_fetch = []
                for jira_repo_path in dev_repos_from_jira_individual:
                    actual_sonar_project_key = _get_sonar_key_from_jira_repo_in_fetcher(jira_repo_path, sonar_org, sonar_key_map)
                    
                    if actual_sonar_project_key:
                        sonar_projects_to_fetch.append(actual_sonar_project_key)
                        # add_log_message(log_list, "info", f"Sonar: Mapped JIRA repo '{jira_repo_path}' to SonarCloud key '{actual_sonar_project_key}'.")
                    # else:
                        # sonar_errors_individual.append(f"Could not find SonarCloud project key for JIRA repo: '{jira_repo_path}'. It might not exist or its key/name differs.")
                        # add_log_message(log_list, "warning", f"Sonar: Could not find SonarCloud project key for JIRA repo: '{jira_repo_path}'.")

                if sonar_projects_to_fetch:
                    add_log_message(log_list, "info", f"Sonar: Fetching INDIVIDUAL metrics for {len(sonar_projects_to_fetch)} matched SonarCloud projects concurrently...")
                    
                    temp_sonar_data = [] 
                    with ThreadPoolExecutor(max_workers=5) as executor:
                        future_to_project_key = {executor.submit(fetch_single_project_metrics, sonar_token, pk, log_list=log_list): pk for pk in sonar_projects_to_fetch}
                        for future in as_completed(future_to_project_key):
                            project_key = future_to_project_key[future]
                            try:
                                metrics_result = future.result()
                                if "error" in metrics_result:
                                    sonar_errors_individual.append(f"Error fetching metrics for {project_key}: {metrics_result['error']}")
                                    add_log_message(log_list, "error", f"Sonar: Failed to fetch metrics for {project_key}: {metrics_result['error']}")
                                else:
                                    temp_sonar_data.append(metrics_result)
                            except Exception as e:
                                sonar_errors_individual.append(f"Exception processing SonarCloud project {project_key}: {e}")
                                add_log_message(log_list, "error", f"Sonar: Exception processing SonarCloud project {project_key}: {e}")
                    sonar_all_projects_data_individual = temp_sonar_data 
                    add_log_message(log_list, "info", "Sonar: INDIVIDUAL SonarCloud metrics fetching complete.")
                else: 
                    sonar_errors_individual.append("No matching SonarCloud projects found for JIRA-linked repositories for individual developer.")
                    add_log_message(log_list, "warning", "Sonar: No matching SonarCloud projects found for JIRA-linked repositories for individual developer.")
        else: 
            sonar_errors_individual.append("No repositories linked from JIRA for individual SonarQube metrics.")
            add_log_message(log_list, "warning", "Sonar: No repositories linked from JIRA for individual SonarQube metrics.")

        # --- Fetch TEAM Sonar Metrics ---
        if dev_repos_from_jira_team: 
            add_log_message(log_list, "info", f"Sonar: Attempting to fetch TEAM SonarCloud metrics for {len(dev_repos_from_jira_team)} linked repositories.")
            
            add_log_message(log_list, "info", "Sonar: Discovering all projects in organization...")
            all_sonar_org_projects_team = fetch_all_sonar_projects(sonar_token, sonar_org, log_list=log_list)
            
            if "error" in all_sonar_org_projects_team:
                team_sonar_errors.append(f"SonarCloud Project List Error: {all_sonar_org_projects_team['error']}")
                add_log_message(log_list, "error", f"Sonar: Project List Error: {all_sonar_org_projects_team['error']}")
            else:
                sonar_key_map = {} 
                for project in all_sonar_org_projects_team:
                    sonar_key_map[project['key'].lower()] = project['key']
                    sonar_key_map[project['name'].lower()] = project['key']
                    
                    if project['key'].startswith(sonar_org + '_') and '_' in project['key']:
                        derived_jira_format = project['key'].replace('_', '/', 1)
                        sonar_key_map[derived_jira_format.lower()] = project['key']
                    elif '/' in project['key'] and project['key'].startswith(sonar_org + '/'):
                        sonar_key_map[project['key'].lower()] = project['key']

                st.session_state.sonar_key_map_global = sonar_key_map

                sonar_projects_to_fetch = []
                for jira_repo_path in dev_repos_from_jira_team:
                    actual_sonar_project_key_team = _get_sonar_key_from_jira_repo_in_fetcher(jira_repo_path, sonar_org, sonar_key_map)
                    
                    if actual_sonar_project_key_team:
                        sonar_projects_to_fetch.append(actual_sonar_project_key_team)
                        # add_log_message(log_list, "info", f"Sonar: Mapped JIRA repo '{jira_repo_path}' to SonarCloud key '{actual_sonar_project_key}'.")
                    # else:
                        # sonar_errors_individual.append(f"Could not find SonarCloud project key for JIRA repo: '{jira_repo_path}'. It might not exist or its key/name differs.")
                        # add_log_message(log_list, "warning", f"Sonar: Could not find SonarCloud project key for JIRA repo: '{jira_repo_path}'.")

                if sonar_projects_to_fetch:
                    add_log_message(log_list, "info", f"Sonar: Fetching TEAM metrics for {len(sonar_projects_to_fetch)} matched SonarCloud projects concurrently...")
                    
                    temp_sonar_data = [] 
                    with ThreadPoolExecutor(max_workers=5) as executor:
                        future_to_project_key = {executor.submit(fetch_single_project_metrics, sonar_token, pk, log_list=log_list): pk for pk in sonar_projects_to_fetch}
                        for future in as_completed(future_to_project_key):
                            project_key = future_to_project_key[future]
                            try:
                                metrics_result = future.result()
                                if "error" in metrics_result:
                                    team_sonar_errors.append(f"Error fetching metrics for {project_key}: {metrics_result['error']}")
                                    add_log_message(log_list, "error", f"Sonar: Failed to fetch metrics for {project_key}: {metrics_result['error']}")
                                else:
                                    temp_sonar_data.append(metrics_result)
                            except Exception as e:
                                team_sonar_errors.append(f"Exception processing SonarCloud project {project_key}: {e}")
                                add_log_message(log_list, "error", f"Sonar: Exception processing SonarCloud project {project_key}: {e}")
                    sonar_metrics_team = temp_sonar_data 
                    add_log_message(log_list, "info", "Sonar: TEAM SonarCloud metrics fetching complete.")
                else: 
                    team_sonar_errors.append("No matching SonarCloud projects found for JIRA-linked repositories for TEAM developer.")
                    add_log_message(log_list, "warning", "Sonar: No matching SonarCloud projects found for JIRA-linked repositories for TEAM developer.")
        else: 
            team_sonar_errors.append("No repositories linked from JIRA for TEAM SonarQube metrics.")
            add_log_message(log_list, "warning", "Sonar: No repositories linked from JIRA for TEAM SonarQube metrics.")



    except Exception as e:
        add_log_message(log_list, "critical", f"An unexpected error occurred during metric generation: {e}")
    
    return (jira_result_individual, git_metrics_individual, sonar_all_projects_data_individual, sonar_errors_individual,
            jira_result_team, git_metrics_team, sonar_metrics_team, team_sonar_errors) # Return all results


# --- Helper to get the potential Sonar Key from JIRA repo path (uses global session state map) ---
def _get_sonar_key_from_jira_repo(jira_repo_path, sonar_org):
    """
    Attempts to find the SonarCloud project key from a JIRA repo path using the global map.
    This helper is used for UI rendering, after the map has been populated.
    """
    sonar_key_map = st.session_state.get('sonar_key_map_global', {})
    
    if not sonar_key_map:
        return None 

    cleaned_jira_path_for_match = jira_repo_path.lower()
    
    if cleaned_jira_path_for_match in sonar_key_map:
         return sonar_key_map[cleaned_jira_path_for_match]

    transformed_jira_path_for_match = jira_repo_path.replace('/', '_', 1).lower()
    if transformed_jira_path_for_match in sonar_key_map:
        return sonar_key_map[transformed_jira_path_for_match]
    
    repo_name_part = jira_repo_path.split('/')[-1].lower()
    if repo_name_part in sonar_key_map:
        return sonar_key_map[repo_name_part]

    return None 


# --- Team Aggregation Functions ---
# def _aggregate_git_sonar_for_team(all_members_individual_metrics, team_dev_branches_from_jira_team_issues, team_members_from_jira_issues, github_token, sonar_token, sonar_org, log_list):
#     """
#     Aggregates Git and Sonar metrics for the team based on individual data and team-linked repos.
#     """
#     log_list.append("[INFO] Aggregating Git and Sonar metrics for the team dashboard...")

#     aggregated_git = {
#         "commits": 0, "lines_added": 0, "lines_deleted": 0, "files_changed": 0,
#         "prs_created": 0, "prs_merged": 0, "review_comments_given": 0
#     }
    
#     aggregated_sonar = {
#         "total_bugs_overall": 0, "total_vulnerabilities_overall": 0, "total_code_smells_overall": 0, "total_ncloc_overall": 0,
#         "total_bugs_new_code": 0, "total_vulnerabilities_new_code": 0, "total_code_smells_new_code": 0, "total_new_technical_debt": 0,
#         "avg_coverage_overall_sum": 0, "avg_coverage_overall_count": 0,
#         "avg_duplicated_lines_density_overall_sum": 0, "avg_duplicated_lines_density_overall_count": 0,
#         "avg_coverage_new_code_sum": 0, "avg_coverage_new_code_count": 0,
#         "avg_duplicated_lines_density_new_code_sum": 0, "avg_duplicated_lines_density_new_code_count": 0,
#         "unique_sonar_projects_count": 0
#     }
    
#     unique_sonar_projects_processed = set() # To prevent double counting sonar projects


#     # --- Git Aggregation for Team ---
#     if team_members_from_jira_issues and github_token:
#         log_list.append(f"[INFO] Git Team Aggregation: Fetching Git metrics for {len(team_members_from_jira_issues)} team members and {len(team_dev_branches_from_jira_team_issues)} unique repos.")
        
#         with ThreadPoolExecutor(max_workers=3) as executor: # Limit concurrency for API calls
#             future_to_member = {
#                 executor.submit(fetch_git_metrics_via_api, github_token, member_name, team_dev_branches_from_jira_team_issues, log_list, sonar_org): member_name
#                 for member_name in team_members_from_jira_issues
#             }
#             for future in as_completed(future_to_member):
#                 member_name = future_to_member[future]
#                 try:
#                     member_git_metrics = future.result()
#                     if "error" not in member_git_metrics:
#                         for key in aggregated_git:
#                             aggregated_git[key] += member_git_metrics.get(key, 0)
#                     else:
#                         log_list.append(f"[WARNING] Git Team: Skipping '{member_name}' due to error: {member_git_metrics['error']}")
#                 except Exception as e:
#                     add_log_message(log_list, "error", f"Git Team: Exception fetching Git for '{member_name}': {e}")
        
#         if not any(aggregated_git.values()): 
#             git_metrics_team = {"error": "No aggregated Git data for team or an error occurred."}
#             log_list.append("[WARNING] Git Team: No aggregated Git data found for team.")
#         else:
#             git_metrics_team = aggregated_git
#             log_list.append("[INFO] Git Team: Aggregation complete.")
#     else:
#         git_metrics_team = {"error": "Git aggregation skipped (no GitHub token, no team members, or no linked repos)."}
#         log_list.append("[WARNING] Git Team: Aggregation skipped.")


    # --- Sonar Aggregation for Team ---
    # sonar_metrics_team_final = {}
    # team_sonar_errors_local = []

    # if team_dev_branches_from_jira_team_issues and sonar_token:
    #     log_list.append(f"[INFO] Sonar Team Aggregation: Discovering Sonar projects for {len(team_dev_branches_from_jira_team_issues)} unique team repos.")
        
    #     all_sonar_org_projects_for_team_map = fetch_all_sonar_projects(sonar_token, sonar_org, log_list=log_list)
    #     if "error" in all_sonar_org_projects_for_team_map:
    #         sonar_metrics_team_final = {"error": f"Failed to get Sonar project list for team aggregation: {all_sonar_org_projects_for_team_map['error']}"}
    #         team_sonar_errors_local.append(sonar_metrics_team_final["error"])
    #     else:
    #         team_sonar_key_map_local = {}
    #         for project in all_sonar_org_projects_for_team_map:
    #             team_sonar_key_map_local[project['key'].lower()] = project['key']
    #             team_sonar_key_map_local[project['name'].lower()] = project['key']
    #             if project['key'].startswith(sonar_org + '_') and '_' in project['key']:
    #                 derived_jira_format = project['key'].replace('_', '/', 1)
    #                 team_sonar_key_map_local[derived_jira_format.lower()] = project['key']
    #             elif '/' in project['key'] and project['key'].startswith(sonar_org + '/'):
    #                 team_sonar_key_map_local[project['key'].lower()] = project['key']

    #         sonar_projects_to_fetch_for_team = []
    #         for jira_repo_path in team_dev_branches_from_jira_team_issues:
    #             actual_sonar_project_key = _get_sonar_key_from_jira_repo_in_fetcher(jira_repo_path, sonar_org, team_sonar_key_map_local)
    #             if actual_sonar_project_key:
    #                 sonar_projects_to_fetch_for_team.append(actual_sonar_project_key)
    #             else:
    #                 log_list.append(f"[WARNING] Sonar Team: Could not map repo '{jira_repo_path}' for aggregation.")
            
    #         if sonar_projects_to_fetch_for_team:
    #             log_list.append(f"[INFO] Sonar Team Aggregation: Fetching metrics for {len(sonar_projects_to_fetch_for_team)} unique Sonar projects concurrently.")
    #             raw_team_sonar_metrics = []
    #             with ThreadPoolExecutor(max_workers=3) as executor:
    #                 future_to_team_proj = {
    #                     executor.submit(fetch_single_project_metrics, sonar_token, pk, log_list=log_list): pk
    #                     for pk in sonar_projects_to_fetch_for_team
    #                 }
    #                 for future in as_completed(future_to_team_proj):
    #                     proj_key = future_to_team_proj[future]
    #                     try:
    #                         proj_metrics = future.result()
    #                         if "error" not in proj_metrics:
    #                             raw_team_sonar_metrics.append(proj_metrics)
    #                         else:
    #                             team_sonar_errors_local.append(f"Error fetching Sonar for team project '{proj_key}': {proj_metrics['error']}")
    #                             add_log_message(log_list, "warning", f"Sonar: Error fetching for '{proj_key}': {proj_metrics['error']}")
    #                     except Exception as e:
    #                         team_sonar_errors_local.append(f"Exception fetching Sonar for team project '{proj_key}': {e}")
    #                         add_log_message(log_list, "error", f"Sonar Team: Exception for '{proj_key}': {e}")
                
    #             if raw_team_sonar_metrics:
    #                 aggregated_sonar_results = {"Total Projects Processed": len(raw_team_sonar_metrics)}

    #                 for key in ['coverage_overall', 'duplicated_lines_density_overall', 'coverage_new_code', 'duplicated_lines_density_new_code']:
    #                     values = [float(p.get(key, 0)) for p in raw_team_sonar_metrics if p.get(key) not in ["N/A", None]]
    #                     aggregated_sonar_results[f"Avg {key}"] = round(stats.mean(values), 1) if values else "N/A"
                    
    #                 for key in ['bugs_overall', 'code_smells_overall', 'vulnerabilities_overall', 'ncloc_overall',
    #                             'bugs_new_code', 'code_smells_new_code', 'vulnerabilities_new_code', 'new_technical_debt']:
    #                     values = [int(float(p.get(key, 0))) for p in raw_team_sonar_metrics if p.get(key) not in ["N/A", None]]
    #                     aggregated_sonar_results[f"Total {key}"] = sum(values) if values else 0

    #                 aggregated_sonar_results["Ratings Aggregation Note"] = "Detailed rating averages (A-E) are complex and not aggregated in this version."
                    
    #                 sonar_metrics_team_final = aggregated_sonar_results
    #                 log_list.append("[INFO] Sonar Team: Aggregation complete.")
    #             else:
    #                 sonar_metrics_team_final = {"error": "No Sonar data available for team projects or an error occurred during fetch for aggregation."}
    #                 log_list.append("[WARNING] Sonar Team: No Sonar data for aggregation.")
    #         else:
    #             sonar_metrics_team_final = {"error": "Failed to discover Sonar projects for team aggregation."}
    #             log_list.append("[WARNING] Sonar Team: No projects identified for aggregation.")
    # else:
    #     sonar_metrics_team_final = {"error": "Sonar aggregation skipped (no Sonar token or no team repos from Jira)."}
    #     log_list.append("[WARNING] Sonar Team: Aggregation skipped.")

    # return git_metrics_team, sonar_metrics_team_final, team_sonar_errors_local # Return these three specific results for team



# --- Added helper for use ONLY within _fetch_all_metrics function for mapping ---
def _get_sonar_key_from_jira_repo_in_fetcher(jira_repo_path, sonar_org, sonar_key_map_local):
    """Helper for mapping within the _fetch_all_metrics function's context."""
    if not sonar_key_map_local:
        return None

    cleaned_jira_path_for_match = jira_repo_path.lower()
    if cleaned_jira_path_for_match in sonar_key_map_local:
         return sonar_key_map_local[cleaned_jira_path_for_match]

    transformed_jira_path_for_match = jira_repo_path.replace('/', '_', 1).lower()
    if transformed_jira_path_for_match in sonar_key_map_local:
        return sonar_key_map_local[transformed_jira_path_for_match]
    
    repo_name_part = jira_repo_path.split('/')[-1].lower()
    if repo_name_part in sonar_key_map_local:
        return sonar_key_map_local[repo_name_part]

    return None


# --- Main App Execution Flow ---
if generate_metrics_button:
    # Clear previous logs and data
    st.session_state.log_messages = []
    st.session_state.jira_result_individual = {}
    st.session_state.git_metrics_individual = {}
    st.session_state.sonar_all_projects_data_individual = []
    st.session_state.sonar_errors_individual = []
    st.session_state.jira_result_team = {}
    st.session_state.git_metrics_team = {}
    st.session_state.sonar_metrics_team = []
    st.session_state.team_sonar_errors = []
    st.session_state.sonar_key_map_global = {} 
    st.session_state.data_fetched = False 

    current_jira_email = st.session_state.jira_email_input 
    current_jira_token = st.session_state.jira_token_input
    current_github_token = st.session_state.github_token_input
    current_sonar_token = st.session_state.sonar_token_input
    current_sonar_org = st.session_state.sonar_org_input
    current_developer_name = st.session_state.selected_developer_name 
    current_sprint_id = st.session_state.sprint_id_input
    current_team_name = st.session_state.selected_team_name
    current_team_id = st.session_state.selected_team_id


    # Input validation and trigger metric fetching
    # Validate that either a developer OR a team is selected
    is_individual_selected = (current_developer_name and current_developer_name != "--- Select a Developer ---")
    is_team_selected = (current_team_name and current_team_id)

    if not all([current_jira_email, current_jira_token, current_github_token, current_sonar_token, current_sonar_org, current_sprint_id]) or \
       (not is_individual_selected and not is_team_selected): # Must have credentials AND (individual OR team selected)
        add_log_message(st.session_state.log_messages, "error", "Please fill in all API tokens, and select either a developer or a team, and enter sprint info.")
        st.warning("⚠️ Please fill in all required inputs, select a developer or a team, and click 'Generate Metrics'.")
    else:
        status_message_placeholder = st.empty() 
        status_message_placeholder.info("✅ Fetching metrics... Please wait, this may take a moment.")
        
        # Call the orchestrator function
        (jira_res_ind, git_met_ind, sonar_data_ind, sonar_errs_ind,
         jira_res_team, git_met_team, sonar_met_team, sonar_errs_team) = _fetch_all_metrics(
            current_jira_email, current_jira_token, current_github_token,
            current_sonar_token, current_sonar_org, current_developer_name, 
            current_sprint_id, current_team_name, current_team_id, 
            st.session_state.log_messages
        )
        
        # Store results in session state
        st.session_state.jira_result_individual = jira_res_ind
        st.session_state.git_metrics_individual = git_met_ind
        st.session_state.sonar_all_projects_data_individual = sonar_data_ind
        st.session_state.sonar_errors_individual = sonar_errs_ind

        st.session_state.jira_result_team = jira_res_team
        st.session_state.git_metrics_team = git_met_team
        st.session_state.sonar_metrics_team = sonar_met_team
        st.session_state.team_sonar_errors = sonar_errs_team

        st.session_state.data_fetched = True 

        # Provide final status update
        # Check for errors in both individual and team fetches
        has_individual_error = (st.session_state.jira_result_individual.get("error") or 
                                st.session_state.git_metrics_individual.get("error") or 
                                st.session_state.sonar_errors_individual)
        has_team_error = (st.session_state.jira_result_team.get("error") or 
                          st.session_state.git_metrics_team.get("error") or 
                          st.session_state.team_sonar_errors)

        if not has_individual_error and not has_team_error:
            status_message_placeholder.success("✅ Metrics generation complete!")
        else:
            status_message_placeholder.error("❌ Metrics generation finished with errors. Check logs for details.")
        add_log_message(st.session_state.log_messages, "info", "Metrics generation process finished.")


# --- Display Metrics and Charts (conditionally based on data_fetched flag in session state) ---

st.markdown("---")
with st.expander("View Processing Logs"):
    if st.session_state.log_messages:
        for log_msg in st.session_state.log_messages:
            st.code(log_msg, language="text")
    else:
        st.info("No logs generated yet. Click 'Generate Metrics' to see activity.")

if st.session_state.data_fetched:
    # --- Tabs for Individual and Team ---
    tab_individual, tab_team = st.tabs(["Individual Metrics", "Team Metrics"])

    with tab_individual:
        col1, col2 = st.columns([2, 3])

        with col1:
            st.subheader(f"📋 Summary - {st.session_state.selected_developer_name} | Sprint {st.session_state.sprint_id_input}")

            st.markdown("**JIRA Metrics**")
            if st.session_state.jira_result_individual and "error" not in st.session_state.jira_result_individual:
                jira_display_data = {k: v for k, v in st.session_state.jira_result_individual.items() if k != 'dev_branches'}
                df_jira_metrics = pd.DataFrame(jira_display_data.items(), columns=["Metric", "Value"])
                # Start index from 1 for better readability
                df_jira_metrics.index = np.arange(1, len(df_jira_metrics) + 1)
                st.dataframe(df_jira_metrics, use_container_width=True)
                
            elif "error" in st.session_state.jira_result_individual: 
                st.error(st.session_state.jira_result_individual["error"])
            else:
                st.info("No JIRA metrics available for individual developer or an error occurred during fetch.")

            st.markdown("**Git Metrics**")
            if st.session_state.git_metrics_individual and "error" not in st.session_state.git_metrics_individual:
                git_display_data = {k: v for k, v in st.session_state.git_metrics_individual.items() if k not in ['dev_branches', 'repos']}
                df_git_metrics = pd.DataFrame(git_display_data.items(), columns=["Metric", "Value"])
                # Start index from 1 for better readability
                df_git_metrics.index = np.arange(1, len(df_git_metrics) + 1)
                st.dataframe(df_git_metrics, use_container_width=True)
                # st.dataframe(pd.DataFrame(st.session_state.git_metrics_individual.items(), columns=["Metric", "Value"]), use_container_width=True)
            elif "error" in st.session_state.git_metrics_individual:
                st.error(st.session_state.git_metrics_individual["error"])
            else:
                st.info("No Git metrics available for individual developer or an error occurred during fetch.")
            

        with col2:
            st.subheader("📈 Charts")
            
            st.markdown("##### Linked Repositories")
            linked_repos_for_display = st.session_state.jira_result_individual.get('dev_branches', [])
            
            selected_sonar_metrics = None 

            if linked_repos_for_display:
                repo_display_options = ["--- Select a Repository ---"]
                
                for jira_repo_path in linked_repos_for_display:
                    sonar_key = _get_sonar_key_from_jira_repo(jira_repo_path, st.session_state.sonar_org_input)
                    
                    if sonar_key:
                        has_sonar_data = any(proj['Project Key'] == sonar_key for proj in st.session_state.sonar_all_projects_data_individual)
                        if has_sonar_data:
                            display_name = f"{jira_repo_path} (Sonar: {sonar_key})"
                        else:
                            display_name = f"{jira_repo_path} (Sonar Data Not Fetched/Mapped)"
                    else:
                        display_name = f"{jira_repo_path} (No Sonar Map)"
                    
                    repo_display_options.append(display_name)
                
                selected_repo_display_name = st.selectbox(
                    "Select Repository for Radar Chart",
                    options=repo_display_options,
                    key="repo_select_box", 
                    help="Choose a repository to display its SonarQube metrics on the radar chart."
                )
                
                if selected_repo_display_name != "--- Select a Repository ---":
                    original_jira_repo_path_from_selection = selected_repo_display_name.split(' (')[0]
                    
                    actual_sonar_key_for_radar = _get_sonar_key_from_jira_repo(original_jira_repo_path_from_selection, st.session_state.sonar_org_input)
                    
                    if actual_sonar_key_for_radar:
                        selected_sonar_metrics = next(
                            (proj for proj in st.session_state.sonar_all_projects_data_individual if proj['Project Key'] == actual_sonar_key_for_radar),
                            None
                        )
                        if not selected_sonar_metrics:
                            st.warning(f"No SonarQube data found for selected project: {actual_sonar_key_for_radar}. It might have been skipped due to fetch errors.")
                    else:
                        st.warning("Selected repository does not have a valid SonarQube mapping.")
                
            else:
                st.info("No repositories linked from JIRA Dev Panel to display for radar chart selection.")
                selected_sonar_metrics = None 

            
            st.markdown("##### Productivity Profile (Radar Chart)")
            if selected_sonar_metrics: 
                st.info(f"Displaying Sonar metrics for: {selected_sonar_metrics['Project Key']}")

                jira_sp = st.session_state.jira_result_individual.get("story_points_done", 0) if st.session_state.jira_result_individual and "error" not in st.session_state.jira_result_individual else 0
                git_commits = st.session_state.git_metrics_individual.get("commits", 0) if st.session_state.git_metrics_individual and "error" not in st.session_state.git_metrics_individual else 0
                git_prs_merged = st.session_state.git_metrics_individual.get("prs_merged", 0) if st.session_state.git_metrics_individual and "error" not in st.session_state.git_metrics_individual else 0
                
                radar_coverage = float(selected_sonar_metrics.get("coverage", 0)) if selected_sonar_metrics.get("coverage") != "N/A" else 0 # Use coverage
                radar_bugs = float(selected_sonar_metrics.get("bugs", 0)) if selected_sonar_metrics.get("bugs") != "N/A" else 0 # Use bugs
                radar_vulnerabilities = float(selected_sonar_metrics.get("vulnerabilities", 0)) if selected_sonar_metrics.get("vulnerabilities") != "N/A" else 0 # Use vulnerabilities
                radar_code_smells = float(selected_sonar_metrics.get("code_smells", 0)) if selected_sonar_metrics.get("code_smells") != "N/A" else 0 # Use code smells

                radar_data = {
                    "Metric": ["Story Points", "Commits", "PRs Merged", "Coverage", "Vulnerabilities", "Code Smells"],
                    "Score": [
                        jira_sp,
                        git_commits,
                        git_prs_merged,
                        radar_coverage,
                        radar_bugs,
                        radar_vulnerabilities,
                        radar_code_smells
                    ]
                }

                fig = go.Figure()
                fig.add_trace(go.Scatterpolar(
                    r=radar_data["Score"],
                    theta=radar_data["Metric"],
                    fill='toself',
                    name='Productivity Profile'
                ))
                fig.update_layout(
                    polar=dict(
                        radialaxis=dict(
                            visible=True,
                            range=[min(0, min(radar_data["Score"]) * 1.1), max(radar_data["Score"]) * 1.1 + 1]
                        )
                    ),
                    showlegend=False
                )
                st.plotly_chart(fig, use_container_width=True)
            elif st.session_state.sonar_errors_individual:
                st.warning("Radar chart could not be generated due to SonarQube fetch errors for individual developer.")
            else: 
                st.info("Select a linked repository from the dropdown to display its SonarQube metrics on the radar chart.")

        col3 = st.columns(1)[0]
        with col3:
            # SonarQube Metrics (per project) for Individual
            st.markdown("**SonarQube Metrics (per project)**")
            if st.session_state.sonar_errors_individual: 
                for err in st.session_state.sonar_errors_individual:
                    st.error(err)
            if st.session_state.sonar_all_projects_data_individual:
                df_sonar = pd.DataFrame(st.session_state.sonar_all_projects_data_individual)
                
                # Define desired display column order and filter to actual existing columns
                sonar_display_cols = [
                    "Project Key", "alert_status", "coverage", "coverage_with_rating", "bugs",
                    "Reliability Rating (A-E)", "vulnerabilities", "Security Rating (A-E)",
                    "Security Hotspot Rating (A-E)", "code_smells", "Maintainability Rating (A-E)",
                    "duplicated_lines_density", "ncloc"
                ]
                df_sonar_display = df_sonar[[col for col in sonar_display_cols if col in df_sonar.columns]]
                
                # Apply formatting for duplicated_lines_density to 1 decimal place.
                if 'duplicated_lines_density' in df_sonar_display.columns:
                    df_sonar_display['duplicated_lines_density'] = df_sonar_display['duplicated_lines_density'].apply(
                        lambda x: f"{float(x):.1f}" if isinstance(x, (float, int)) and not pd.isna(x) else x
                    )

                # Start index from 1 for better readability
                df_sonar_display.index = np.arange(1, len(df_sonar_display) + 1)
                st.dataframe(df_sonar_display, use_container_width=True)
            else:
                st.info("No SonarQube metrics available for individual linked projects or an error occurred during fetch.")

    
    with tab_team:
        col1, col2 = st.columns([2, 3])

        with col1:
            st.subheader(f"👥 Team Metrics - {st.session_state.selected_team_name} | Sprint {st.session_state.sprint_id_input}")

            st.markdown("**JIRA Metrics (Team)**")
            if st.session_state.jira_result_team and "error" not in st.session_state.jira_result_team:
                jira_team_display_data = {k: v for k, v in st.session_state.jira_result_team.items() if k != 'dev_branches'} # Exclude raw issues data if present
                df_team_jira_metrics = pd.DataFrame(jira_team_display_data.items(), columns=["Metric", "Value"])
                # Start index from 1 for better readability
                df_team_jira_metrics.index = np.arange(1, len(df_team_jira_metrics) + 1)
                st.dataframe(df_team_jira_metrics, use_container_width=True)
                    
                # st.dataframe(pd.DataFrame(jira_team_display_data.items(), columns=["Metric", "Value"]), use_container_width=True)
            elif "error" in st.session_state.jira_result_team:
                st.error(st.session_state.jira_result_team["error"])
            else:
                st.info("No JIRA metrics available for the selected team or an error occurred during fetch.")


            st.markdown("**Git Metrics (Team)**")
            if st.session_state.git_metrics_team and "error" not in st.session_state.git_metrics_team:
                git_team_display_data = {k: v for k, v in st.session_state.git_metrics_team.items() if k not in ['dev_branches', 'repos']}
                df_team_git_metrics = pd.DataFrame(git_team_display_data.items(), columns=["Metric", "Value"])
                # Start index from 1 for better readability
                df_team_git_metrics.index = np.arange(1, len(df_team_git_metrics) + 1)
                st.dataframe(df_team_git_metrics, use_container_width=True)

                # st.dataframe(pd.DataFrame(st.session_state.git_metrics_team.items(), columns=["Metric", "Value"]), use_container_width=True)
            elif "error" in st.session_state.git_metrics_team:
                st.error(st.session_state.git_metrics_team["error"])
            else:
                st.info("Team Git metrics aggregation not fully implemented or an error occurred.")
        
        with col2:
            st.subheader("📈 Charts")
            
            st.markdown("##### Linked Repositories")
            team_linked_repos_for_display = st.session_state.jira_result_team.get('dev_branches', [])
            
            team_selected_sonar_metrics = None 

            if team_linked_repos_for_display:
                repo_display_options = ["--- Select a Repository ---"]
                
                for jira_repo_path in team_linked_repos_for_display:
                    sonar_key = _get_sonar_key_from_jira_repo(jira_repo_path, st.session_state.sonar_org_input)
                    
                    if sonar_key:
                        has_sonar_data = any(proj['Project Key'] == sonar_key for proj in st.session_state.sonar_metrics_team)
                        if has_sonar_data:
                            display_name = f"{jira_repo_path} (Sonar: {sonar_key})"
                        else:
                            display_name = f"{jira_repo_path} (Sonar Data Not Fetched/Mapped)"
                    else:
                        display_name = f"{jira_repo_path} (No Sonar Map)"
                    
                    repo_display_options.append(display_name)
                
                selected_repo_display_name = st.selectbox(
                    "Select Repository for Radar Chart",
                    options=repo_display_options,
                    key="repo_select_box_team", 
                    help="Choose a repository to display its SonarQube metrics on the radar chart."
                )
                
                if selected_repo_display_name != "--- Select a Repository ---":
                    original_jira_repo_path_from_selection = selected_repo_display_name.split(' (')[0]
                    
                    actual_sonar_key_for_radar = _get_sonar_key_from_jira_repo(original_jira_repo_path_from_selection, st.session_state.sonar_org_input)
                    
                    if actual_sonar_key_for_radar:
                        team_selected_sonar_metrics = next(
                            (proj for proj in st.session_state.sonar_metrics_team if proj['Project Key'] == actual_sonar_key_for_radar),
                            None
                        )
                        if not team_selected_sonar_metrics:
                            st.warning(f"No SonarQube data found for selected project: {actual_sonar_key_for_radar}. It might have been skipped due to fetch errors.")
                    else:
                        st.warning("Selected repository does not have a valid SonarQube mapping.")
                
            else:
                st.info("No repositories linked from JIRA Dev Panel to display for radar chart selection.")
                team_selected_sonar_metrics = None 

            
            st.markdown("##### Team Productivity Profile (Radar Chart)")
            if team_selected_sonar_metrics: 
                st.info(f"Displaying Sonar metrics for: {team_selected_sonar_metrics['Project Key']}")

                jira_sp = st.session_state.jira_result_team.get("story_points_done", 0) if st.session_state.jira_result_team and "error" not in st.session_state.jira_result_individual else 0
                git_commits = st.session_state.git_metrics_team.get("commits", 0) if st.session_state.git_metrics_team and "error" not in st.session_state.git_metrics_individual else 0
                git_prs_merged = st.session_state.git_metrics_team.get("prs_merged", 0) if st.session_state.git_metrics_team and "error" not in st.session_state.git_metrics_individual else 0
                
                radar_coverage = float(team_selected_sonar_metrics.get("coverage", 0)) if team_selected_sonar_metrics.get("coverage") != "N/A" else 0 # Use coverage
                radar_bugs = float(team_selected_sonar_metrics.get("bugs", 0)) if team_selected_sonar_metrics.get("bugs") != "N/A" else 0 # Use bugs
                radar_vulnerabilities = float(team_selected_sonar_metrics.get("vulnerabilities", 0)) if team_selected_sonar_metrics.get("vulnerabilities") != "N/A" else 0 # Use vulnerabilities
                radar_code_smells = float(team_selected_sonar_metrics.get("code_smells", 0)) if team_selected_sonar_metrics.get("code_smells") != "N/A" else 0 # Use code smells

                team_radar_data = {
                    "Metric": ["Story Points", "Commits", "PRs Merged", "Coverage", "Vulnerabilities", "Code Smells"],
                    "Score": [
                        jira_sp,
                        git_commits,
                        git_prs_merged,
                        radar_coverage,
                        radar_bugs,
                        radar_vulnerabilities,
                        radar_code_smells
                    ]
                }

                team_fig = go.Figure()
                team_fig.add_trace(go.Scatterpolar(
                    r=team_radar_data["Score"],
                    theta=team_radar_data["Metric"],
                    fill='toself',
                    name='Team Productivity Profile'
                ))
                team_fig.update_layout(
                    polar=dict(
                        radialaxis=dict(
                            visible=True,
                            range=[min(0, min(team_radar_data["Score"]) * 1.1), max(team_radar_data["Score"]) * 1.1 + 1]
                        )
                    ),
                    showlegend=False
                )
                st.plotly_chart(team_fig, use_container_width=True)
            elif st.session_state.team_sonar_errors:
                st.warning("Radar chart could not be generated due to SonarQube fetch errors for Team.")
            else: 
                st.info("Select a linked repository from the dropdown to display its SonarQube metrics on the radar chart.")

        col3 = st.columns(1)[0]
        with col3:
            st.markdown("**SonarQube Metrics (Team)**")
            if st.session_state.team_sonar_errors:
                if "error" in st.session_state.team_sonar_errors:
                    st.error(st.session_state.team_sonar_errors["error"]) 
            if st.session_state.sonar_metrics_team and isinstance(st.session_state.sonar_metrics_team, list) and st.session_state.sonar_metrics_team:
                # Display aggregated Sonar metrics for the team
                df_team_sonar_metrics = pd.DataFrame(st.session_state.sonar_metrics_team)
                # df_sonar = pd.DataFrame(st.session_state.sonar_all_projects_data_individual)
                
                # Define desired display column order and filter to actual existing columns
                sonar_display_cols = [
                    "Project Key", "alert_status", "coverage", "coverage_with_rating", "bugs",
                    "Reliability Rating (A-E)", "vulnerabilities", "Security Rating (A-E)",
                    "Security Hotspot Rating (A-E)", "code_smells", "Maintainability Rating (A-E)",
                    "duplicated_lines_density", "ncloc"
                ]
                df_sonar_display = df_team_sonar_metrics[[col for col in sonar_display_cols if col in df_team_sonar_metrics.columns]]
                
                # Apply formatting for duplicated_lines_density to 1 decimal place.
                if 'duplicated_lines_density' in df_sonar_display.columns:
                    df_sonar_display['duplicated_lines_density'] = df_sonar_display['duplicated_lines_density'].apply(
                        lambda x: f"{float(x):.1f}" if isinstance(x, (float, int)) and not pd.isna(x) else x
                    )
                # if 'duplicated_lines_density_new_code' in df_sonar_display.columns:
                #     df_sonar_display['duplicated_lines_density_new_code'] = df_sonar_display['duplicated_lines_density_new_code'].apply(
                #         lambda x: f"{float(x):.1f}" if isinstance(x, (float, int)) and not pd.isna(x) else x
                #     )

                # Start index from 1 for better readability
                df_sonar_display.index = np.arange(1, len(df_sonar_display) + 1)
                st.dataframe(df_sonar_display, use_container_width=True)
            else:
                st.info("No SonarQube metrics available for Team linked projects or an error occurred during fetch.")


else: # Initial load or after inputs are changed without button click
    st.warning("⚠️ Enter your credentials and click 'Generate Metrics' to begin.")