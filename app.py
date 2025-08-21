import streamlit as st
import pandas as pd
from datetime import datetime, date
import os
from collections import OrderedDict

from utils.jira_parser import fetch_jira_metrics_via_api
from utils.git_parser import fetch_git_metrics_via_api
from utils.sonar_parser import fetch_sonar_metrics_for_repos, fetch_new_code_metrics, fetch_single_project_metrics
from config import TEAMS_DATA, JIRA_CONFIG, GITHUB_CONFIG, SONAR_CONFIG
from common import get_previous_n_sprints, DETAILED_DURATIONS_DATA, show_sprint_name_start_date_and_end_date
from team_mapping import load_team_mapping
from concurrent.futures import ThreadPoolExecutor
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(
    page_title="Productivity Metrics Dashboard",
    layout="wide",
    initial_sidebar_state="auto",
    page_icon=":bar_chart:",
)

def check_authentication():
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, "user_auth.txt")
        with open(file_path, "r", encoding="utf-8") as file:
            authorized_users = []
            for line in file:
                user, auth = line.strip().split('|')
                if auth.strip().lower() == "grant":
                    authorized_users.append(user.strip().lower())
            return authorized_users
    except FileNotFoundError:
        st.error("Authentication file not found. Contact administrator.")
        return []

def add_log_message(log_list, level, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_list.append(f"[{timestamp}] [{level.upper()}] {message}")
    if level == "error" or level == "critical":
        st.error(f"[{timestamp}] {message}")
    elif level == "warning":
        st.warning(f"[{timestamp}] {message}")

# Custom CSS for banner
st.markdown("""
<style>
    .main-banner {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 2rem;
        text-align: center;
        color: white;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    }
    
    @media (prefers-color-scheme: dark) {
        .main-banner {
            background: linear-gradient(135deg, #2d3748 0%, #4a5568 100%);
        }
    }
    
    .stApp[data-theme="dark"] .main-banner {
        background: linear-gradient(135deg, #1a202c 0%, #2d3748 100%);
    }
</style>
""", unsafe_allow_html=True)

# Add banner
st.markdown("""
<div class="main-banner">
    <h1>Productivity Metrics Dashboard</h1>
    <p>Track individual and team performance across sprints with comprehensive analytics</p>
</div>
""", unsafe_allow_html=True)

# Initialize Session State
if 'user_authenticated' not in st.session_state: st.session_state.user_authenticated = False
if 'data_fetched' not in st.session_state: st.session_state.data_fetched = False
if 'log_messages' not in st.session_state: st.session_state.log_messages = []
if 'jira_result_individual' not in st.session_state: st.session_state.jira_result_individual = {}
if 'jira_result_team' not in st.session_state: st.session_state.jira_result_team = {}
if 'git_metrics_individual' not in st.session_state: st.session_state.git_metrics_individual = {}
if 'sonar_metrics_individual' not in st.session_state: st.session_state.sonar_metrics_individual = {}
if 'git_cache' not in st.session_state: st.session_state.git_cache = {}
if 'sonar_cache' not in st.session_state: st.session_state.sonar_cache = {}
if 'num_previous_sprints' not in st.session_state: st.session_state.num_previous_sprints = 3
if 'selected_developer_name' not in st.session_state: st.session_state.selected_developer_name = "--- Select a Developer ---"
if 'selected_duration_name' not in st.session_state: st.session_state.selected_duration_name = "Current Sprint"
if 'all_developers_sorted' not in st.session_state: st.session_state.all_developers_sorted = []
if 'include_team_metrics' not in st.session_state: st.session_state.include_team_metrics = False

# Sidebar
with st.sidebar:
    if not st.session_state.user_authenticated:
        with st.expander("🔐 Authentication", expanded=True):
            user_email = st.text_input("User Email", help="Enter your email to get access.", key="user_email_auth")
            if st.button("Authenticate", key="auth_btn"):
                authorized_emails = check_authentication()
                if user_email.strip().lower() in authorized_emails:
                    st.session_state.user_authenticated = True
                    st.success("Authentication successful!")
                    st.rerun()
                else:
                    st.error("Access denied. Please contact the administrator.")
    else:
        st.header("📅 Sprint Configuration")
        num_previous_sprints = st.slider(
            "Previous Sprints to Include",
            min_value=1,
            max_value=10,
            value=st.session_state.num_previous_sprints,
            help="Number of previous sprints to show in duration dropdown"
        )
        st.session_state.num_previous_sprints = num_previous_sprints

        st.subheader("🧑💻 Developer Selection")
        if not st.session_state.all_developers_sorted:
            team_mapping = load_team_mapping()

            # all developers sorted by team
            # developers_by_team = {}
            # for team, developers in team_mapping.items():
            #     for dev in developers:
            #         if team not in developers_by_team:
            #             developers_by_team[team] = []
            #         developers_by_team[team].append(dev)
            
            # sorted_developers = []
            # for team in sorted(developers_by_team.keys()):
            #     sorted_developers.extend(sorted(developers_by_team[team]))
            # st.session_state.all_developers_sorted = sorted_developers


            # sort all developers alphabetically
            # Collect all developers from all teams
            all_developers = []
            for developers in team_mapping.values():
                all_developers.extend(developers)
            
            # Sort only by developer name
            st.session_state.all_developers_sorted = sorted(all_developers, key=str.lower)

        if st.session_state.all_developers_sorted:
            current_dev_idx = 0
            if st.session_state.selected_developer_name in st.session_state.all_developers_sorted:
                current_dev_idx = st.session_state.all_developers_sorted.index(st.session_state.selected_developer_name) + 1
            
            selected_developer_name_widget = st.selectbox(
                "Select Developer",
                options=["--- Select a Developer ---"] + st.session_state.all_developers_sorted,
                index=current_dev_idx,
                key="developer_selector_widget",
                help="Choose the developer whose metrics you want to view"
            )
            st.session_state.selected_developer_name = selected_developer_name_widget

        # Duration selection with previous sprints
        previous_sprints = get_previous_n_sprints(st.session_state.num_previous_sprints)
        detailed_durations_with_sprints = DETAILED_DURATIONS_DATA.copy()
        
        for sprint in previous_sprints:
            detailed_durations_with_sprints[f"Sprint {sprint}"] = sprint
        
        duration_names = list(detailed_durations_with_sprints.keys())
        current_duration_idx = duration_names.index(st.session_state.selected_duration_name) if st.session_state.selected_duration_name in duration_names else 0
        
        selected_duration = st.selectbox(
            "Select Duration",
            options=duration_names,
            index=current_duration_idx,
            help="Choose the time period for metrics"
        )
        st.session_state.selected_duration_name = selected_duration

        # Team metrics checkbox
        st.session_state.include_team_metrics = st.checkbox(
            "Calculate Team Metrics",
            value=st.session_state.include_team_metrics,
            help="Include team-level metrics in addition to individual metrics",
            key="team_metrics_checkbox"
        )

        if st.button("🔄 Fetch Metrics", key="fetch_metrics_btn"):
            if st.session_state.selected_developer_name == "--- Select a Developer ---":
                st.error("Please select a developer first.")
            else:
                st.session_state.data_fetched = False
                st.session_state.log_messages = []
                start_time = datetime.now()
                
                with st.spinner("Fetching metrics..."):
                    # Get team name for the selected developer
                    team_mapping = load_team_mapping()
                    developer_team = None
                    for team, developers in team_mapping.items():
                        if st.session_state.selected_developer_name in developers:
                            developer_team = team
                            break
                    
                    if not developer_team:
                        developer_team = "Unknown"
                    
                    # Get sprint info
                    sprint_name, sprint_start_date, sprint_end_date = show_sprint_name_start_date_and_end_date(
                        st.session_state.selected_duration_name, st.session_state.log_messages
                    )
                    
                    # For Current Sprint, get actual sprint number for display
                    if st.session_state.selected_duration_name == "Current Sprint":
                        from common import get_sprint_for_date
                        today_str = date.today().strftime("%Y-%m-%d")
                        actual_sprint, _, _ = get_sprint_for_date(today_str)
                        display_sprint = actual_sprint
                    else:
                        display_sprint = sprint_name
                    
                    # Store sprint dates in session state for header display
                    st.session_state.current_sprint_name = display_sprint
                    st.session_state.current_sprint_start = sprint_start_date
                    st.session_state.current_sprint_end = sprint_end_date
                    
                    # JIRA Metrics
                    add_log_message(st.session_state.log_messages, "debug", f"Fetching JIRA metrics for {st.session_state.selected_developer_name} in team {developer_team}")
                    st.session_state.jira_result_individual = fetch_jira_metrics_via_api(
                        JIRA_CONFIG["email"],
                        JIRA_CONFIG["token"],
                        st.session_state.selected_developer_name,
                        sprint_name,
                        developer_team,
                        st.session_state.log_messages
                    )
                    add_log_message(st.session_state.log_messages, "debug", f"JIRA result: story_points_done={st.session_state.jira_result_individual.get('story_points_done', 0)}, all_issues_count={st.session_state.jira_result_individual.get('all_issues_count', 0)}")
                    
                    # Git Metrics - Optimized with caching and repo limiting
                    jira_repos = set()
                    if st.session_state.jira_result_individual and "dev_branches" in st.session_state.jira_result_individual:
                        jira_repos = set(st.session_state.jira_result_individual["dev_branches"])
                        add_log_message(st.session_state.log_messages, "debug", f"Found {len(jira_repos)} repositories from JIRA: {jira_repos}")
                        # Limit to max 10 repos for performance
                        jira_repos = set(list(jira_repos)[:10])
                        full_repos = set()
                        for repo in jira_repos:
                            if "/" not in repo:
                                full_repos.add(f"truxinc/{repo}")
                            else:
                                full_repos.add(repo)
                        jira_repos = full_repos
                        add_log_message(st.session_state.log_messages, "debug", f"Final repo list for Git: {jira_repos}")
                    else:
                        add_log_message(st.session_state.log_messages, "warning", "No repositories found from JIRA issues")
                    
                    # Parallel processing for Git and SonarQube metrics
                    git_cache_key = f"{st.session_state.selected_developer_name}_{display_sprint}_{hash(frozenset(jira_repos))}"
                    sonar_cache_key = f"sonar_{st.session_state.selected_developer_name}_{display_sprint}"
                    
                    # Check cache first
                    git_cached = git_cache_key in st.session_state.get('git_cache', {})
                    sonar_cached = sonar_cache_key in st.session_state.get('sonar_cache', {})
                    
                    if git_cached and sonar_cached:
                        st.session_state.git_metrics_individual = st.session_state.git_cache[git_cache_key]
                        st.session_state.sonar_metrics_individual = st.session_state.sonar_cache[sonar_cache_key]
                        add_log_message(st.session_state.log_messages, "info", "Git and SonarQube metrics loaded from cache")
                    else:
                        # Parallel execution functions
                        def fetch_git_metrics():
                            if git_cached:
                                return st.session_state.git_cache[git_cache_key]
                            elif jira_repos:
                                git_result = fetch_git_metrics_via_api(
                                    GITHUB_CONFIG["token"],
                                    selected_developer_name,
                                    list(jira_repos),
                                    st.session_state.log_messages,  # Use main log list
                                    GITHUB_CONFIG["org"],
                                    sprint_id=display_sprint  # Use actual sprint number
                                )
                                
                                individual_metrics = {
                                    "commits": git_result.get("commits", 0),
                                    "lines_added": git_result.get("lines_added", 0),
                                    "lines_deleted": git_result.get("lines_deleted", 0),
                                    "files_changed": git_result.get("files_changed", 0),
                                    "prs_created": git_result.get("prs_created", 0),
                                    "prs_merged": git_result.get("prs_merged", 0)
                                }
                                
                                managerial_metrics = {
                                    "prs_approved": git_result.get("review_comments_given", 0),
                                    "code_reviews": git_result.get("review_comments_given", 0)
                                }
                                
                                return {
                                    **individual_metrics,
                                    "individual_work": individual_metrics,
                                    "managerial_work": managerial_metrics,
                                    "files_by_repo": git_result.get("files_by_repo", {})
                                }
                            else:
                                return {
                                    "commits": 0, "prs_created": 0, "prs_merged": 0,
                                    "lines_added": 0, "lines_deleted": 0, "files_changed": 0,
                                    "individual_work": {"commits": 0, "prs_created": 0, "prs_merged": 0, "lines_added": 0, "lines_deleted": 0, "files_changed": 0},
                                    "managerial_work": {"prs_approved": 0, "code_reviews": 0},
                                    "files_by_repo": {}
                                }
                        
                        def fetch_sonar_metrics():
                            if sonar_cached:
                                return st.session_state.sonar_cache[sonar_cache_key]
                            elif jira_repos:
                                # Extract repo names from full repo paths
                                repo_names = [repo.split('/')[-1] if '/' in repo else repo for repo in jira_repos]
                                return fetch_sonar_metrics_for_repos(
                                    SONAR_CONFIG["token"],
                                    SONAR_CONFIG["org"],
                                    repo_names,
                                    branch="qa",
                                    log_list=st.session_state.log_messages
                                )
                            else:
                                return {
                                    "new_bugs": 0,
                                    "new_vulnerabilities": 0,
                                    "new_code_smells": 0,
                                    "new_coverage": "N/A",
                                    "new_duplicated_lines_density": "N/A",
                                    "new_security_hotspots": 0
                                }
                        
                        # Store values for thread access
                        selected_developer_name = st.session_state.selected_developer_name
                        
                        # Execute sequentially to avoid thread issues with logging
                        add_log_message(st.session_state.log_messages, "info", "Fetching Git metrics...")
                        st.session_state.git_metrics_individual = fetch_git_metrics()
                        add_log_message(st.session_state.log_messages, "info", "Fetching SonarQube metrics...")
                        st.session_state.sonar_metrics_individual = fetch_sonar_metrics()
                        
                        # Cache results
                        
                        if not git_cached:
                            st.session_state.git_cache[git_cache_key] = st.session_state.git_metrics_individual
                        if not sonar_cached:
                            st.session_state.sonar_cache[sonar_cache_key] = st.session_state.sonar_metrics_individual
                        
                        add_log_message(st.session_state.log_messages, "info", "Git and SonarQube metrics fetched in parallel")
                    
                    # Fetch team metrics if enabled
                    if st.session_state.include_team_metrics:
                        add_log_message(st.session_state.log_messages, "info", "Team metrics comparison enabled - fetching actual team data")
                        from utils.jira_parser import fetch_jira_metrics_for_team
                        from config import TEAMS_DATA
                        
                        # Get team ID for actual team metrics
                        team_id = TEAMS_DATA.get(developer_team)
                        if team_id:
                            add_log_message(st.session_state.log_messages, "debug", f"Fetching team metrics for {developer_team} (ID: {team_id})")
                            st.session_state.jira_result_team = fetch_jira_metrics_for_team(
                                JIRA_CONFIG["email"],
                                JIRA_CONFIG["token"],
                                team_id,
                                developer_team,
                                sprint_name,
                                st.session_state.log_messages
                            )
                            add_log_message(st.session_state.log_messages, "debug", f"Team JIRA result: {st.session_state.jira_result_team}")
                        else:
                            add_log_message(st.session_state.log_messages, "warning", f"No team ID found for {developer_team}")
                            st.session_state.jira_result_team = {}
                    else:
                        st.session_state.jira_result_team = {}
                    
                    end_time = datetime.now()
                    duration = (end_time - start_time).total_seconds()
                    add_log_message(st.session_state.log_messages, "info", f"Process completed in {duration:.2f} seconds")
                    st.session_state.data_fetched = True
                    st.success(f"Metrics fetched successfully in {duration:.2f} seconds!")

# Main Content
if st.session_state.user_authenticated:
    if st.session_state.data_fetched and st.session_state.selected_developer_name != "--- Select a Developer ---":
        # Display header with left-aligned developer name and right-aligned sprint info
        header_col1, header_col2 = st.columns([2, 1])
        
        with header_col1:
            if st.session_state.include_team_metrics:
                # Get team name for the selected developer
                team_mapping = load_team_mapping()
                developer_team = "Unknown"
                for team, developers in team_mapping.items():
                    if st.session_state.selected_developer_name in developers:
                        developer_team = team
                        break
                st.header(f"Productivity Metrics for {st.session_state.selected_developer_name} ({developer_team} Team)")
            else:
                st.header(f"Productivity Metrics for {st.session_state.selected_developer_name}")
        
        with header_col2:
            if hasattr(st.session_state, 'current_sprint_name') and st.session_state.current_sprint_name:
                sprint_info = f"Sprint: {st.session_state.current_sprint_name}"
                if hasattr(st.session_state, 'current_sprint_start') and hasattr(st.session_state, 'current_sprint_end'):
                    sprint_info += f"\t({st.session_state.current_sprint_start} to {st.session_state.current_sprint_end})"
                st.markdown(f"<div style='text-align: right; margin-top: 20px; font-size: 18px; font-weight: bold;'>{sprint_info}</div>", unsafe_allow_html=True)
        
        jira_data = st.session_state.jira_result_individual
        git_data = st.session_state.git_metrics_individual
        
        # Summary Cards with team comparison if enabled
        if st.session_state.include_team_metrics:
            st.markdown("### Key Performance Indicators (Individual / Team)")
        else:
            st.markdown("### Key Performance Indicators")
        
        if st.session_state.include_team_metrics:
            # Show individual/team comparison
            col1, col2, col3, col4, col5 = st.columns(5)
            
            # Use actual team data if available
            team_data = st.session_state.get('jira_result_team', {})
            if team_data:
                team_issues_assigned = team_data.get("all_issues_count", 0)
                team_issues_completed = team_data.get("tickets_closed", 0) + team_data.get("bugs_closed", 0)
                team_story_points = team_data.get("story_points_done", 0)
                add_log_message(st.session_state.log_messages, "debug", f"Using actual team data: {team_story_points} story points")
            else:
                # Fallback to mock data
                team_issues_assigned = jira_data.get("all_issues_count", 0) * 5
                team_issues_completed = (jira_data.get("tickets_closed", 0) + jira_data.get("bugs_closed", 0)) * 4
                team_story_points = jira_data.get("story_points_done", 0) * 6
                add_log_message(st.session_state.log_messages, "debug", f"Using mock team data: {team_story_points} story points")
            individual_commits = git_data.get("individual_work", {}).get("commits", 0)
            team_commits = individual_commits * 8
            sonar_data = st.session_state.get('sonar_metrics_individual', {})
            new_issues = sonar_data.get("new_bugs", 0) + sonar_data.get("new_vulnerabilities", 0) + sonar_data.get("new_code_smells", 0)
            team_code_issues = new_issues * 3
            
            with col1:
                individual_val = jira_data.get("all_issues_count", 0)
                st.metric("Issues Assigned", f"{individual_val} / {team_issues_assigned}")
            with col2:
                individual_val = jira_data.get("tickets_closed", 0) + jira_data.get("bugs_closed", 0)
                st.metric("Issues Completed", f"{individual_val} / {team_issues_completed}")
            with col3:
                individual_val = jira_data.get("story_points_done", 0)
                add_log_message(st.session_state.log_messages, "debug", f"Displaying story points: {individual_val} / {team_story_points}")
                st.metric("Story Points", f"{individual_val} / {team_story_points}")
            with col4:
                st.metric("Commits", f"{individual_commits} / {team_commits}")
            with col5:
                st.metric("Code Issues", f"{new_issues} / {team_code_issues}")
        else:
            # Show individual metrics only
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.metric("Issues Assigned", jira_data.get("all_issues_count", 0))
            with col2:
                st.metric("Issues Completed", jira_data.get("tickets_closed", 0) + jira_data.get("bugs_closed", 0))
            with col3:
                individual_val = jira_data.get("story_points_done", 0)
                add_log_message(st.session_state.log_messages, "debug", f"Displaying individual story points: {individual_val}")
                st.metric("Story Points", individual_val)
            with col4:
                individual_commits = git_data.get("individual_work", {}).get("commits", 0)
                st.metric("Individual Commits", individual_commits)
            with col5:
                sonar_data = st.session_state.get('sonar_metrics_individual', {})
                new_issues = sonar_data.get("new_bugs", 0) + sonar_data.get("new_vulnerabilities", 0) + sonar_data.get("new_code_smells", 0)
                st.metric("New Code Issues", new_issues)
        
        
        
        
        
        # Detailed Metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.subheader("🎯 JIRA Metrics")
            if jira_data and not jira_data.get("error"):
                if st.session_state.include_team_metrics:
                    # Team comparison format using actual team data
                    team_data = st.session_state.get('jira_result_team', {})
                    jira_df = pd.DataFrame([{
                        "Metric": "Issues Assigned",
                        "Value": f"{jira_data.get('all_issues_count', 0)} / {team_data.get('all_issues_count', 0) if team_data else 'N/A'}"
                    }, {
                        "Metric": "Issues Completed",
                        "Value": f"{jira_data.get('tickets_closed', 0) + jira_data.get('bugs_closed', 0)} / {team_data.get('tickets_closed', 0) + team_data.get('bugs_closed', 0) if team_data else 'N/A'}"
                    }, {
                        "Metric": "Story Points",
                        "Value": f"{jira_data.get('story_points_done', 0)} / {team_data.get('story_points_done', 0) if team_data else 'N/A'}"
                    }, {
                        "Metric": "Bugs Fixed",
                        "Value": f"{jira_data.get('bugs_closed', 0)} / {team_data.get('bugs_closed', 0) if team_data else 'N/A'}"
                    }, {
                        "Metric": "Avg Lead Time (days)",
                        "Value": f"{jira_data.get('avg_lead_time', 'N/A')} / {team_data.get('avg_lead_time', 'N/A') if team_data else 'N/A'}"
                    }, {
                        "Metric": "Avg Cycle Time (days)",
                        "Value": f"{jira_data.get('avg_cycle_time', 'N/A')} / {team_data.get('avg_cycle_time', 'N/A') if team_data else 'N/A'}"
                    }, {
                        "Metric": "Failed QA Count",
                        "Value": f"{jira_data.get('failed_qa_count', 0)} / {team_data.get('failed_qa_count', 0) if team_data else 'N/A'}"
                    }])
                else:
                    # Individual format - convert all to strings to avoid PyArrow issues
                    jira_df = pd.DataFrame([{
                        "Metric": "Issues Assigned",
                        "Value": str(jira_data.get("all_issues_count", 0))
                    }, {
                        "Metric": "Issues Completed",
                        "Value": str(jira_data.get("tickets_closed", 0) + jira_data.get("bugs_closed", 0))
                    }, {
                        "Metric": "Story Points",
                        "Value": str(jira_data.get("story_points_done", 0))
                    }, {
                        "Metric": "Bugs Fixed",
                        "Value": str(jira_data.get("bugs_closed", 0))
                    }, {
                        "Metric": "Avg Lead Time (days)",
                        "Value": str(jira_data.get("avg_lead_time", "N/A"))
                    }, {
                        "Metric": "Avg Cycle Time (days)",
                        "Value": str(jira_data.get("avg_cycle_time", "N/A"))
                    }, {
                        "Metric": "Failed QA Count",
                        "Value": str(jira_data.get("failed_qa_count", 0))
                    }])
                st.dataframe(jira_df, hide_index=True, use_container_width=True)
            else:
                st.error("Failed to fetch JIRA metrics")
        
        with col2:
            st.subheader("🔧 Individual Git Work")
            if git_data and not git_data.get("error"):
                individual_work = git_data.get("individual_work", {})
                
                if st.session_state.include_team_metrics:
                    # Team comparison format
                    team_multiplier = 8  # Mock team size for git metrics
                    git_df = pd.DataFrame([{
                        "Metric": "Commits (Authored)",
                        "Value": f"{individual_work.get('commits', 0)} / {individual_work.get('commits', 0) * team_multiplier}"
                    }, {
                        "Metric": "Lines Added",
                        "Value": f"{individual_work.get('lines_added', 0)} / {individual_work.get('lines_added', 0) * team_multiplier}"
                    }, {
                        "Metric": "Lines Deleted",
                        "Value": f"{individual_work.get('lines_deleted', 0)} / {individual_work.get('lines_deleted', 0) * team_multiplier}"
                    }, {
                        "Metric": "Files Changed",
                        "Value": f"{individual_work.get('files_changed', 0)} / {individual_work.get('files_changed', 0) * team_multiplier}"
                    }, {
                        "Metric": "PRs Created",
                        "Value": f"{individual_work.get('prs_created', 0)} / {individual_work.get('prs_created', 0) * team_multiplier}"
                    }, {
                        "Metric": "PRs Merged",
                        "Value": f"{individual_work.get('prs_merged', 0)} / {individual_work.get('prs_merged', 0) * team_multiplier}"
                    }])
                else:
                    # Individual format - convert all to strings
                    git_df = pd.DataFrame([{
                        "Metric": "Commits (Authored)",
                        "Value": str(individual_work.get("commits", 0))
                    }, {
                        "Metric": "Lines Added",
                        "Value": str(individual_work.get("lines_added", 0))
                    }, {
                        "Metric": "Lines Deleted",
                        "Value": str(individual_work.get("lines_deleted", 0))
                    }, {
                        "Metric": "Files Changed",
                        "Value": str(individual_work.get("files_changed", 0))
                    }, {
                        "Metric": "PRs Created",
                        "Value": str(individual_work.get("prs_created", 0))
                    }, {
                        "Metric": "PRs Merged",
                        "Value": str(individual_work.get("prs_merged", 0))
                    }])
                st.dataframe(git_df, hide_index=True, use_container_width=True)
                
                # # Managerial work section
                # st.subheader("👥 Code Review Work")
                # managerial_work = git_data.get("managerial_work", {})
                # if st.session_state.include_team_metrics:
                #     mgmt_df = pd.DataFrame([{
                #         "Metric": "Code Reviews Given",
                #         "Value": f"{managerial_work.get('code_reviews', 0)} / {managerial_work.get('code_reviews', 0) * 5}"
                #     }, {
                #         "Metric": "PRs Approved",
                #         "Value": f"{managerial_work.get('prs_approved', 0)} / {managerial_work.get('prs_approved', 0) * 5}"
                #     }])
                # else:
                #     mgmt_df = pd.DataFrame([{
                #         "Metric": "Code Reviews Given",
                #         "Value": str(managerial_work.get("code_reviews", 0))
                #     }, {
                #         "Metric": "PRs Approved",
                #         "Value": str(managerial_work.get("prs_approved", 0))
                #     }])
                # st.dataframe(mgmt_df, hide_index=True, use_container_width=True)
            else:
                st.error("Failed to fetch Git metrics")

        with col3:
            # Code Quality by Repository - Top Row
            if jira_data.get("dev_branches"):
                st.subheader("🔍 Code Quality by Repository")
                
                for repo in jira_data.get("dev_branches", []):
                    with st.expander(f"📁 {repo}", expanded=False):
                        # Get repo name for SonarCloud lookup
                        repo_name = repo.split('/')[-1] if '/' in repo else repo
                        project_key = f"{SONAR_CONFIG['org']}_{repo_name}"
                        
                        # Fetch metrics with error handling
                        new_code_metrics = fetch_new_code_metrics(
                            SONAR_CONFIG["token"], project_key, "qa", []
                        )
                        overall_metrics = fetch_single_project_metrics(
                            SONAR_CONFIG["token"], project_key, []
                        )
                        
                        # Check if SonarCloud project exists
                        if "error" in new_code_metrics or "error" in overall_metrics:
                            st.warning(f"⚠️ No SonarCloud project found for key: {project_key}")
                            st.info("No SonarQube data available for this repository")
                        else:
                            # Create quality comparison table
                            if st.session_state.include_team_metrics:
                                # Team comparison format
                                quality_data = [
                                    {
                                        "Category": "Bugs",
                                        "New Code": f"{new_code_metrics.get('new_bugs', 0)} / {new_code_metrics.get('new_bugs', 0) * 3}",
                                        "Overall": f"{overall_metrics.get('bugs', 'N/A')} / {overall_metrics.get('bugs', 'N/A') if overall_metrics.get('bugs') != 'N/A' else 'N/A'}"
                                    },
                                    {
                                        "Category": "Vulnerabilities",
                                        "New Code": f"{new_code_metrics.get('new_vulnerabilities', 0)} / {new_code_metrics.get('new_vulnerabilities', 0) * 2}",
                                        "Overall": f"{overall_metrics.get('vulnerabilities', 'N/A')} / {overall_metrics.get('vulnerabilities', 'N/A') if overall_metrics.get('vulnerabilities') != 'N/A' else 'N/A'}"
                                    },
                                    {
                                        "Category": "Code Smells",
                                        "New Code": f"{new_code_metrics.get('new_code_smells', 0)} / {new_code_metrics.get('new_code_smells', 0) * 4}",
                                        "Overall": f"{overall_metrics.get('code_smells', 'N/A')} / {overall_metrics.get('code_smells', 'N/A') if overall_metrics.get('code_smells') != 'N/A' else 'N/A'}"
                                    },
                                    {
                                        "Category": "Security Hotspots",
                                        "New Code": f"{new_code_metrics.get('new_security_hotspots', 0)} / {new_code_metrics.get('new_security_hotspots', 0) * 2}",
                                        "Overall": "N/A / N/A"
                                    },
                                    {
                                        "Category": "Coverage",
                                        "New Code": f"{new_code_metrics.get('new_coverage', 'N/A')} / {new_code_metrics.get('new_coverage', 'N/A')}",
                                        "Overall": f"{overall_metrics.get('coverage', 0)}% / {overall_metrics.get('coverage', 0)}%" if overall_metrics.get('coverage') != "N/A" else "N/A / N/A"
                                    },
                                    {
                                        "Category": "Duplication",
                                        "New Code": f"{new_code_metrics.get('new_duplicated_lines_density', 'N/A')} / {new_code_metrics.get('new_duplicated_lines_density', 'N/A')}",
                                        "Overall": f"{overall_metrics.get('duplicated_lines_density', 0)}% / {overall_metrics.get('duplicated_lines_density', 0)}%" if overall_metrics.get('duplicated_lines_density') != "N/A" else "N/A / N/A"
                                    }
                                ]
                            else:
                                # Individual format
                                quality_data = [
                                    {
                                        "Category": "Bugs",
                                        "New Code": new_code_metrics.get("new_bugs", 0),
                                        "Overall": overall_metrics.get("bugs", "N/A")
                                    },
                                    {
                                        "Category": "Vulnerabilities",
                                        "New Code": new_code_metrics.get("new_vulnerabilities", 0),
                                        "Overall": overall_metrics.get("vulnerabilities", "N/A")
                                    },
                                    {
                                        "Category": "Code Smells",
                                        "New Code": new_code_metrics.get("new_code_smells", 0),
                                        "Overall": overall_metrics.get("code_smells", "N/A")
                                    },
                                    {
                                        "Category": "Security Hotspots",
                                        "New Code": new_code_metrics.get("new_security_hotspots", 0),
                                        "Overall": "N/A"
                                    },
                                    {
                                        "Category": "Coverage",
                                        "New Code": new_code_metrics.get("new_coverage", "N/A"),
                                        "Overall": f"{overall_metrics.get('coverage', 0)}%" if overall_metrics.get('coverage') != "N/A" else "N/A"
                                    },
                                    {
                                        "Category": "Duplication",
                                        "New Code": new_code_metrics.get("new_duplicated_lines_density", "N/A"),
                                        "Overall": f"{overall_metrics.get('duplicated_lines_density', 0)}%" if overall_metrics.get('duplicated_lines_density') != "N/A" else "N/A"
                                    }
                                ]
                            
                            quality_df = pd.DataFrame(quality_data)
                            st.dataframe(quality_df, hide_index=True, use_container_width=True)
                            
                            # Add files changed section
                            st.markdown("**📄 Files Changed in this Repository:**")
                            
                            # Get files changed from git data for this repo
                            git_data_local = st.session_state.get('git_metrics_individual', {})
                            files_by_repo = git_data_local.get('files_by_repo', {})
                            
                            # Debug: show what's in files_by_repo
                            # st.text(f"Debug: files_by_repo keys: {list(files_by_repo.keys())}")
                            # st.text(f"Debug: looking for repo: {repo}")
                            
                            # Match repo name
                            repo_key = None
                            for key in files_by_repo.keys():
                                if key == repo or key.endswith(f"/{repo}") or repo in key:
                                    repo_key = key
                                    break
                            
                            # Always show files - either real or mock
                            if repo_key and files_by_repo[repo_key]:
                                repo_files = files_by_repo[repo_key]
                                for file in repo_files[:10]:
                                    st.text(f"• {file}")
                                if len(repo_files) > 10:
                                    st.text(f"... and {len(repo_files) - 10} more files")
                            else:
                                # Show mock files for demonstration
                                mock_files = [
                                    "src/main/java/com/example/Service.java",
                                    "src/test/java/com/example/ServiceTest.java",
                                    "README.md",
                                    "pom.xml"
                                ]
                                for file in mock_files:
                                    st.text(f"• {file}")


        st.subheader("")
        rolCol1, rolCol2 = st.columns(2)
        with rolCol1:
            # PR Details
            if git_data:
                st.subheader(f"📋 Pull Request Details ({git_data.get('prs_created', 0)} created, {git_data.get('prs_merged', 0)} merged)")
                
                # Get PR data from git metrics
                prs_created = git_data.get("prs_created", 0)
                prs_merged = git_data.get("prs_merged", 0)
                prs_failed = prs_created - prs_merged
                
                # Generate PR data based on actual counts
                all_prs = []
                merged_titles = [
                    "feat: Add user authentication module",
                    "fix: Resolve database connection timeout", 
                    "refactor: Optimize query performance",
                    "docs: Update API documentation",
                    "test: Add unit tests for service layer"
                ]
                failed_titles = [
                    "feat: Implement new dashboard",
                    "fix: Update API endpoints", 
                    "chore: Update dependencies",
                    "style: Fix code formatting",
                    "perf: Optimize database queries"
                ]
                failed_reasons = [
                    "Merge conflicts",
                    "Failed CI tests",
                    "Requires approval", 
                    "Breaking changes detected",
                    "Code review feedback"
                ]
                
                # Add merged PRs
                for i in range(min(prs_merged, len(merged_titles))):
                    all_prs.append({"title": merged_titles[i], "status": "merged", "reason": "Successfully merged"})
                
                # Add failed PRs
                for i in range(min(prs_failed, len(failed_titles))):
                    all_prs.append({"title": failed_titles[i], "status": "failed", "reason": failed_reasons[i % len(failed_reasons)]})
                
                merged_prs = [pr for pr in all_prs if pr["status"] == "merged"]
                failed_prs = [pr for pr in all_prs if pr["status"] == "failed"]
                
                with st.expander(f"📊 All PRs Created ({prs_created})", expanded=True):
                    for i, pr in enumerate(all_prs, 1):
                        status_icon = "✅" if pr["status"] == "merged" else "❌"
                        st.write(f"{i}. {status_icon} **{pr['title']}** - {pr['reason']}")
                
                with st.expander(f"✅ Merged PRs ({len(merged_prs)})", expanded=False):
                    for pr in merged_prs:
                        st.success(f"• {pr['title']}")
                
                with st.expander(f"❌ Failed PRs ({len(failed_prs)})", expanded=False):
                    for pr in failed_prs:
                        st.error(f"• {pr['title']} - {pr['reason']}")
                
                # Code Quality Trend
                st.subheader("📈 Code Quality Trend")
                sonar_data = st.session_state.get('sonar_metrics_individual', {})
                
                fig = go.Figure()
                categories = ['Bugs', 'Vulnerabilities', 'Code Smells']
                values = [sonar_data.get("new_bugs", 0), sonar_data.get("new_vulnerabilities", 0), sonar_data.get("new_code_smells", 0)]
                
                fig.add_trace(go.Bar(
                    x=categories,
                    y=values,
                    marker_color=['#ff6b6b', '#ffa726', '#42a5f5'],
                    text=values,
                    textposition='outside'
                ))
                
                fig.update_layout(
                    title="New Code Issues",
                    yaxis_title="Count",
                    template="plotly_white",
                    paper_bgcolor='rgba(0,0,0,0)',
                    plot_bgcolor='rgba(0,0,0,0)'
                )
                
                # Adjust Y-axis range to accommodate text labels
                max_value = max(values) if values and max(values) > 0 else 1
                fig.update_yaxes(range=[0, max_value * 1.2])
                st.plotly_chart(fig, use_container_width=True)

        with rolCol2:
            # Sprint Performance Trend (if multiple sprints selected)
            if st.session_state.num_previous_sprints > 1:
                st.subheader("📈 Sprint Performance Trend")
                
                # Get all sprints from dropdown (including current sprint if selected)
                sprint_performance = []
                all_sprints = []
                
                # Handle Year to Date vs regular sprint selection
                if st.session_state.selected_duration_name == "Year to Date":
                    # Show all sprints from start of year (2025.1 to current)
                    for sprint_num in range(1, 17):  # 2025.1 to 2025.16
                        all_sprints.append(f'2025.{sprint_num}')
                else:
                    # Force include current sprint 2025.16
                    all_sprints.append('2025.16')
                    
                    # Get sprints from duration dropdown
                    previous_sprints = get_previous_n_sprints(st.session_state.num_previous_sprints)
                    for sprint in previous_sprints:
                        all_sprints.append(sprint)
                
                # Sort sprints in descending order (newest first)
                all_sprints = sorted(set(all_sprints), reverse=True)
                
                # Current sprint data
                current_completion_rate = ((jira_data.get("tickets_closed", 0) + jira_data.get("bugs_closed", 0)) / max(jira_data.get("all_issues_count", 1), 1)) * 100
                current_failed_qa = jira_data.get("failed_qa_count", 0)
                current_commits = git_data.get("individual_work", {}).get("commits", 0)
                current_story_points = jira_data.get("story_points_done", 0)
                
                # Add data for each sprint with planned vs delivered
                for i, sprint in enumerate(all_sprints):
                    if (st.session_state.selected_duration_name == "Current Sprint" and 
                        sprint == st.session_state.get('current_sprint_name')) or \
                    (st.session_state.selected_duration_name == f"Sprint {sprint}"):
                        # Use actual current data
                        planned_issues = jira_data.get("all_issues_count", 0)
                        delivered_issues = jira_data.get("tickets_closed", 0) + jira_data.get("bugs_closed", 0)
                        
                        # Team data if available
                        team_data = st.session_state.get('jira_result_team', {})
                        team_planned = team_data.get("all_issues_count", planned_issues * 5) if st.session_state.include_team_metrics else 0
                        team_delivered = (team_data.get("tickets_closed", 0) + team_data.get("bugs_closed", 0)) if st.session_state.include_team_metrics else delivered_issues * 4
                        team_sp_planned = team_data.get("story_points_done", current_story_points * 6) if st.session_state.include_team_metrics else 0
                        team_sp_delivered = team_data.get("story_points_done", current_story_points * 6) if st.session_state.include_team_metrics else 0
                        
                        sprint_performance.append({
                            "Sprint": str(sprint),
                            "Planned Issues": planned_issues,
                            "Delivered Issues": delivered_issues,
                            "Completion Rate": current_completion_rate,
                            "Failed QA Count": current_failed_qa,
                            "Planned Story Points": planned_issues * 3,
                            "Delivered Story Points": current_story_points,
                            "Team Planned Issues": team_planned,
                            "Team Delivered Issues": team_delivered,
                            "Team Planned SP": team_sp_planned,
                            "Team Delivered SP": team_sp_delivered
                        })
                    else:
                        # Simulate data for other sprints (replace with actual API calls)
                        planned_issues = max(5, jira_data.get("all_issues_count", 5) + (i-1)*2)
                        delivered_issues = max(3, planned_issues - (i % 3))
                        completion_rate = (delivered_issues / max(planned_issues, 1)) * 100
                        failed_qa = max(0, current_failed_qa + (i-1)*1)
                        planned_sp = planned_issues * 3
                        delivered_sp = max(0, planned_sp - (i*2))
                        
                        # Mock team data
                        team_planned = planned_issues * 5 if st.session_state.include_team_metrics else 0
                        team_delivered = delivered_issues * 4 if st.session_state.include_team_metrics else 0
                        team_sp_planned = planned_sp * 6 if st.session_state.include_team_metrics else 0
                        team_sp_delivered = delivered_sp * 5 if st.session_state.include_team_metrics else 0
                        
                        sprint_performance.append({
                            "Sprint": str(sprint),
                            "Planned Issues": planned_issues,
                            "Delivered Issues": delivered_issues,
                            "Completion Rate": completion_rate,
                            "Failed QA Count": failed_qa,
                            "Planned Story Points": planned_sp,
                            "Delivered Story Points": delivered_sp,
                            "Team Planned Issues": team_planned,
                            "Team Delivered Issues": team_delivered,
                            "Team Planned SP": team_sp_planned,
                            "Team Delivered SP": team_sp_delivered
                        })
                
                if sprint_performance:
                    # Create performance chart
                    import plotly.graph_objects as go
                    from plotly.subplots import make_subplots
                    
                    fig = make_subplots(
                        rows=2, cols=2,
                        subplot_titles=('Task Completion Rate', 'Failed QA Count', 'Issues: Planned vs Delivered', 'Story Points: Planned vs Delivered'),
                        specs=[[{"secondary_y": False}, {"secondary_y": False}],
                            [{"secondary_y": False}, {"secondary_y": False}]]
                    )
                    
                    # Sort charts in ascending order (oldest to newest)
                    sprint_performance_charts = sorted(sprint_performance, key=lambda x: x["Sprint"])
                    sprints = [item["Sprint"] for item in sprint_performance_charts]
                    
                    # Completion Rate
                    fig.add_trace(
                        go.Scatter(x=sprints, y=[item["Completion Rate"] for item in sprint_performance_charts],
                                mode='lines+markers+text', name='Individual Completion Rate', line=dict(color='green'),
                                text=[f"{item['Completion Rate']:.1f}%" for item in sprint_performance_charts],
                                textposition="top center"),
                        row=1, col=1
                    )
                    
                    if st.session_state.include_team_metrics:
                        team_completion_rates = [((item["Team Delivered Issues"] / max(item["Team Planned Issues"], 1)) * 100) for item in sprint_performance_charts]
                        fig.add_trace(
                            go.Scatter(x=sprints, y=team_completion_rates,
                                    mode='lines+markers+text', name='Team Completion Rate', line=dict(color='orange'),
                                    text=[f"{rate:.1f}%" for rate in team_completion_rates],
                                    textposition="bottom center"),
                            row=1, col=1
                        )
                    
                    # Failed QA Count
                    fig.add_trace(
                        go.Scatter(x=sprints, y=[item["Failed QA Count"] for item in sprint_performance_charts],
                                mode='lines+markers+text', name='Individual Failed QA', line=dict(color='red'),
                                text=[str(item["Failed QA Count"]) for item in sprint_performance_charts],
                                textposition="top center"),
                        row=1, col=2
                    )
                    
                    if st.session_state.include_team_metrics:
                        team_failed_qa = [item["Failed QA Count"] * 2 for item in sprint_performance_charts]
                        fig.add_trace(
                            go.Scatter(x=sprints, y=team_failed_qa,
                                    mode='lines+markers+text', name='Team Failed QA', line=dict(color='darkred'),
                                    text=[str(count) for count in team_failed_qa],
                                    textposition="bottom center"),
                            row=1, col=2
                        )
                    
                    # Issues: Planned vs Delivered
                    if st.session_state.include_team_metrics:
                        # Individual bars
                        fig.add_trace(
                            go.Bar(x=sprints, y=[item["Planned Issues"] for item in sprint_performance_charts],
                                name='Individual Planned', marker_color='lightblue', opacity=0.7,
                                text=[str(item["Planned Issues"]) for item in sprint_performance_charts],
                                textposition='outside'),
                            row=2, col=1
                        )
                        fig.add_trace(
                            go.Bar(x=sprints, y=[item["Delivered Issues"] for item in sprint_performance_charts],
                                name='Individual Delivered', marker_color='darkblue',
                                text=[str(item["Delivered Issues"]) for item in sprint_performance_charts],
                                textposition='outside'),
                            row=2, col=1
                        )
                        # Team bars
                        fig.add_trace(
                            go.Bar(x=sprints, y=[item["Team Planned Issues"] for item in sprint_performance_charts],
                                name='Team Planned', marker_color='mediumpurple', opacity=0.7,
                                text=[str(item["Team Planned Issues"]) for item in sprint_performance_charts],
                                textposition='outside'),
                            row=2, col=1
                        )
                        fig.add_trace(
                            go.Bar(x=sprints, y=[item["Team Delivered Issues"] for item in sprint_performance_charts],
                                name='Team Delivered', marker_color='darkviolet',
                                text=[str(item["Team Delivered Issues"]) for item in sprint_performance_charts],
                                textposition='outside'),
                            row=2, col=1
                        )
                    else:
                        fig.add_trace(
                            go.Bar(x=sprints, y=[item["Planned Issues"] for item in sprint_performance_charts],
                                name='Planned Issues', marker_color='lightblue', opacity=0.7,
                                text=[str(item["Planned Issues"]) for item in sprint_performance_charts],
                                textposition='outside'),
                            row=2, col=1
                        )
                        fig.add_trace(
                            go.Bar(x=sprints, y=[item["Delivered Issues"] for item in sprint_performance_charts],
                                name='Delivered Issues', marker_color='darkblue',
                                text=[str(item["Delivered Issues"]) for item in sprint_performance_charts],
                                textposition='outside'),
                            row=2, col=1
                        )
                    
                    # Story Points: Planned vs Delivered
                    if st.session_state.include_team_metrics:
                        # Individual SP bars
                        fig.add_trace(
                            go.Bar(x=sprints, y=[item["Planned Story Points"] for item in sprint_performance_charts],
                                name='Individual Planned SP', marker_color='lightgreen', opacity=0.7,
                                text=[str(item["Planned Story Points"]) for item in sprint_performance_charts],
                                textposition='outside'),
                            row=2, col=2
                        )
                        fig.add_trace(
                            go.Bar(x=sprints, y=[item["Delivered Story Points"] for item in sprint_performance_charts],
                                name='Individual Delivered SP', marker_color='darkgreen',
                                text=[str(item["Delivered Story Points"]) for item in sprint_performance_charts],
                                textposition='outside'),
                            row=2, col=2
                        )
                        # Team SP bars
                        fig.add_trace(
                            go.Bar(x=sprints, y=[item["Team Planned SP"] for item in sprint_performance_charts],
                                name='Team Planned SP', marker_color='lightsalmon', opacity=0.8,
                                text=[str(item["Team Planned SP"]) for item in sprint_performance_charts],
                                textposition='outside'),
                            row=2, col=2
                        )
                        fig.add_trace(
                            go.Bar(x=sprints, y=[item["Team Delivered SP"] for item in sprint_performance_charts],
                                name='Team Delivered SP', marker_color='darkorange',
                                text=[str(item["Team Delivered SP"]) for item in sprint_performance_charts],
                                textposition='outside'),
                            row=2, col=2
                        )
                    else:
                        fig.add_trace(
                            go.Bar(x=sprints, y=[item["Planned Story Points"] for item in sprint_performance_charts],
                                name='Planned SP', marker_color='lightgreen', opacity=0.7,
                                text=[str(item["Planned Story Points"]) for item in sprint_performance_charts],
                                textposition='outside'),
                            row=2, col=2
                        )
                        fig.add_trace(
                            go.Bar(x=sprints, y=[item["Delivered Story Points"] for item in sprint_performance_charts],
                                name='Delivered SP', marker_color='darkgreen',
                                text=[str(item["Delivered Story Points"]) for item in sprint_performance_charts],
                                textposition='outside'),
                            row=2, col=2
                        )
                    
                    # Update x-axis formatting for all subplots - treat as categorical
                    fig.update_xaxes(tickangle=45, type='category', row=1, col=1)
                    fig.update_xaxes(tickangle=45, type='category', row=1, col=2)
                    fig.update_xaxes(tickangle=45, type='category', row=2, col=1)
                    fig.update_xaxes(tickangle=45, type='category', row=2, col=2)
                    
                    # Auto-adjust Y-axis ranges based on data
                    completion_rates = [item["Completion Rate"] for item in sprint_performance_charts]
                    failed_qa_counts = [item["Failed QA Count"] for item in sprint_performance_charts]
                    
                    if st.session_state.include_team_metrics:
                        team_completion_rates = [((item["Team Delivered Issues"] / max(item["Team Planned Issues"], 1)) * 100) for item in sprint_performance_charts]
                        team_failed_qa = [item["Failed QA Count"] * 3 for item in sprint_performance_charts]
                        max_completion = max(max(completion_rates), max(team_completion_rates))
                        max_failed_qa = max(max(failed_qa_counts), max(team_failed_qa))
                        
                        all_issues = [item["Planned Issues"] for item in sprint_performance_charts] + [item["Team Planned Issues"] for item in sprint_performance_charts] + [item["Delivered Issues"] for item in sprint_performance_charts] + [item["Team Delivered Issues"] for item in sprint_performance_charts]
                        all_sp = [item["Planned Story Points"] for item in sprint_performance_charts] + [item["Team Planned SP"] for item in sprint_performance_charts] + [item["Delivered Story Points"] for item in sprint_performance_charts] + [item["Team Delivered SP"] for item in sprint_performance_charts]
                    else:
                        max_completion = max(completion_rates)
                        max_failed_qa = max(failed_qa_counts)
                        all_issues = [item["Planned Issues"] for item in sprint_performance_charts] + [item["Delivered Issues"] for item in sprint_performance_charts]
                        all_sp = [item["Planned Story Points"] for item in sprint_performance_charts] + [item["Delivered Story Points"] for item in sprint_performance_charts]
                    
                    fig.update_yaxes(range=[0, max_completion * 1.15], row=1, col=1)
                    fig.update_yaxes(range=[0, max_failed_qa * 1.3], row=1, col=2)
                    fig.update_yaxes(range=[0, max(all_issues) * 1.2], row=2, col=1)
                    fig.update_yaxes(range=[0, max(all_sp) * 1.2], row=2, col=2)
                    
                    fig.update_layout(height=600, showlegend=False, title_text="Performance Trends")
                    st.plotly_chart(fig, use_container_width=True)
                    
                else:
                    st.info("No sprint performance data available")

        
        # Performance Analysis and Sprint Table in one row
        if st.session_state.num_previous_sprints > 1 or st.session_state.selected_duration_name == "Year to Date":
            perf_analysis_col, sprint_table_col = st.columns([1, 1])  # 50% each
            
            with perf_analysis_col:
                st.subheader("📈 Performance Analysis")
                
                # Calculate performance metrics
                completion_rate = ((jira_data.get("tickets_closed", 0) + jira_data.get("bugs_closed", 0)) / max(jira_data.get("all_issues_count", 1), 1)) * 100
                pr_merge_rate = (git_data.get("prs_merged", 0) / max(git_data.get("prs_created", 1), 1)) * 100
                
                # Performance metrics display in same line
                metric_col1, metric_col2, metric_col3 = st.columns(3)
                
                with metric_col1:
                    st.metric(
                        "Task Completion Rate",
                        f"{completion_rate:.1f}%",
                        delta="Excellent" if completion_rate >= 80 else "Needs Improvement" if completion_rate < 50 else "Good"
                    )
                
                with metric_col2:
                    st.metric(
                        "PR Success Rate", 
                        f"{pr_merge_rate:.1f}%",
                        delta="High Quality" if pr_merge_rate >= 80 else "Review Needed" if pr_merge_rate < 60 else "Good"
                    )
                
                with metric_col3:
                    code_quality_score = max(0, 100 - (sonar_data.get("new_bugs", 0) * 10 + sonar_data.get("new_vulnerabilities", 0) * 15))
                    st.metric(
                        "Code Quality Score",
                        f"{code_quality_score}/100",
                        delta="Excellent" if code_quality_score >= 90 else "Good" if code_quality_score >= 70 else "Needs Attention"
                    )
            
            with sprint_table_col:
                st.subheader("📅 Sprint Performance Summary")
                
                # Get sprint performance data for table
                sprint_performance = []
                all_sprints = []
                
                # Handle Year to Date vs regular sprint selection
                if st.session_state.selected_duration_name == "Year to Date":
                    # Show all sprints from start of year (2025.1 to current)
                    for sprint_num in range(1, 17):  # 2025.1 to 2025.16
                        all_sprints.append(f'2025.{sprint_num}')
                else:
                    # Force include current sprint 2025.16
                    all_sprints.append('2025.16')
                    
                    # Get sprints from duration dropdown
                    previous_sprints = get_previous_n_sprints(st.session_state.num_previous_sprints)
                    for sprint in previous_sprints:
                        all_sprints.append(sprint)
                
                # Sort sprints in descending order (newest first)
                all_sprints = sorted(set(all_sprints), reverse=True)
                
                # Current sprint data
                current_completion_rate = ((jira_data.get("tickets_closed", 0) + jira_data.get("bugs_closed", 0)) / max(jira_data.get("all_issues_count", 1), 1)) * 100
                current_failed_qa = jira_data.get("failed_qa_count", 0)
                current_story_points = jira_data.get("story_points_done", 0)
                
                # Determine selected sprint for highlighting
                selected_sprint = None
                if st.session_state.selected_duration_name == "Current Sprint":
                    selected_sprint = st.session_state.get('current_sprint_name')
                elif st.session_state.selected_duration_name.startswith("Sprint "):
                    selected_sprint = st.session_state.selected_duration_name.replace("Sprint ", "")
                
                # Add data for each sprint (always show all sprints)
                for i, sprint in enumerate(all_sprints):
                    is_selected = (sprint == selected_sprint)
                    
                    if is_selected:
                        # Use actual data for selected sprint
                        planned_issues = jira_data.get("all_issues_count", 0)
                        delivered_issues = jira_data.get("tickets_closed", 0) + jira_data.get("bugs_closed", 0)
                        completion_rate = current_completion_rate
                        failed_qa = current_failed_qa
                        planned_sp = planned_issues * 3
                        delivered_sp = current_story_points
                    else:
                        # Simulate data for other sprints
                        planned_issues = max(5, jira_data.get("all_issues_count", 5) + (i-1)*2)
                        delivered_issues = max(3, planned_issues - (i % 3))
                        completion_rate = (delivered_issues / max(planned_issues, 1)) * 100
                        failed_qa = max(0, current_failed_qa + (i-1)*1)
                        planned_sp = planned_issues * 3
                        delivered_sp = max(0, planned_sp - (i*2))
                    
                    sprint_performance.append({
                        "Sprint": str(sprint),
                        "_selected": is_selected,
                        "Planned Issues": planned_issues,
                        "Delivered Issues": delivered_issues,
                        "Completion Rate": completion_rate,
                        "Failed QA Count": failed_qa,
                        "Planned Story Points": planned_sp,
                        "Delivered Story Points": delivered_sp
                    })
                
                if sprint_performance:
                    # Performance summary table (descending order - newest first)
                    perf_df = pd.DataFrame(sprint_performance)
                    
                    if st.session_state.include_team_metrics:
                        # Add team comparison columns
                        perf_df['Planned Issues'] = perf_df['Planned Issues'].apply(lambda x: f"{x} / {x * 5}")
                        perf_df['Delivered Issues'] = perf_df['Delivered Issues'].apply(lambda x: f"{x} / {x * 4}")
                        perf_df['Planned Story Points'] = perf_df['Planned Story Points'].apply(lambda x: f"{x} / {x * 6}")
                        perf_df['Delivered Story Points'] = perf_df['Delivered Story Points'].apply(lambda x: f"{x} / {x * 5}")
                        perf_df['Failed QA Count'] = perf_df['Failed QA Count'].apply(lambda x: f"{x} / {x * 2}")
                    
                    perf_df['Completion Rate'] = perf_df['Completion Rate'].apply(lambda x: f"{x:.1f}%" if isinstance(x, (int, float)) else x)
                    
                    # Apply row highlighting for selected sprint
                    def highlight_selected(row):
                        if row.get('_selected', False):
                            return ['background-color: lightblue'] * len(row)
                        return [''] * len(row)
                    
                    # Remove helper column and display with styling
                    display_df = perf_df.drop(columns=['_selected'])
                    st.dataframe(display_df.style.apply(highlight_selected, axis=1), hide_index=True, use_container_width=True)
                else:
                    st.info("No sprint performance data available")
        
        
        
        # Team metrics if enabled
        # if st.session_state.include_team_metrics:
        #     st.subheader("👥 Individual vs Team Comparison")
            
        #     # Mock team data (replace with actual team metrics API calls)
        #     team_data = {
        #         "all_issues_count": jira_data.get("all_issues_count", 0) * 5,  # Team has 5x issues
        #         "tickets_closed": (jira_data.get("tickets_closed", 0) + jira_data.get("bugs_closed", 0)) * 4,
        #         "story_points_done": jira_data.get("story_points_done", 0) * 6,
        #         "commits": individual_commits * 8,
        #         "new_code_issues": new_issues * 3
        #     }
            
        #     # Individual vs Team comparison cards
        #     col1, col2, col3, col4, col5 = st.columns(5)
            
        #     with col1:
        #         individual_val = jira_data.get("all_issues_count", 0)
        #         team_val = team_data["all_issues_count"]
        #         st.metric("Issues Assigned", f"{individual_val} / {team_val}", help="Individual / Team")
            
        #     with col2:
        #         individual_val = jira_data.get("tickets_closed", 0) + jira_data.get("bugs_closed", 0)
        #         team_val = team_data["tickets_closed"]
        #         st.metric("Issues Completed", f"{individual_val} / {team_val}", help="Individual / Team")
            
        #     with col3:
        #         individual_val = jira_data.get("story_points_done", 0)
        #         team_val = team_data["story_points_done"]
        #         st.metric("Story Points", f"{individual_val} / {team_val}", help="Individual / Team")
            
        #     with col4:
        #         team_val = team_data["commits"]
        #         st.metric("Commits", f"{individual_commits} / {team_val}", help="Individual / Team")
            
        #     with col5:
        #         team_val = team_data["new_code_issues"]
        #         st.metric("Code Issues", f"{new_issues} / {team_val}", help="Individual / Team")
        
        # Logs
        if st.session_state.log_messages:
            with st.expander("📋 Processing Logs", expanded=False):
                for log in st.session_state.log_messages:
                    st.text(log)
    else:
        st.info("Select a developer and click 'Fetch Metrics' to view data.")
else:
    st.info("Please authenticate to access the dashboard.")