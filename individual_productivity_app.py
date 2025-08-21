import streamlit as st
import pandas as pd
from datetime import datetime, date
import os
from collections import OrderedDict

from utils.jira_parser import fetch_jira_metrics_via_api
from utils.git_parser import fetch_git_metrics_via_api
from config import TEAMS_DATA, JIRA_CONFIG, GITHUB_CONFIG
from common import get_previous_sprints, DETAILED_DURATIONS_DATA, show_sprint_name_start_date_and_end_date
from team_mapping import load_team_mapping

st.set_page_config(
    page_title="Individual Productivity Metrics",
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

def generate_performance_insights(jira_data, git_data):
    """Generate performance insights and suggestions"""
    insights = {
        "what_went_well": [],
        "areas_for_improvement": [],
        "performance_score": 0
    }
    
    # Analyze JIRA metrics
    total_issues = jira_data.get("all_issues_count", 0)
    completed_issues = jira_data.get("tickets_closed", 0) + jira_data.get("bugs_closed", 0)
    story_points = jira_data.get("story_points_done", 0)
    
    completion_rate = (completed_issues / total_issues * 100) if total_issues > 0 else 0
    
    # Analyze Git metrics
    commits = git_data.get("commits", 0)
    prs_created = git_data.get("prs_created", 0)
    prs_merged = git_data.get("prs_merged", 0)
    lines_added = git_data.get("lines_added", 0)
    
    pr_merge_rate = (prs_merged / prs_created * 100) if prs_created > 0 else 0
    
    # Performance scoring
    score = 0
    if completion_rate >= 80: score += 25
    elif completion_rate >= 60: score += 15
    elif completion_rate >= 40: score += 10
    
    if pr_merge_rate >= 80: score += 25
    elif pr_merge_rate >= 60: score += 15
    
    if commits >= 10: score += 20
    elif commits >= 5: score += 10
    
    if story_points >= 8: score += 20
    elif story_points >= 5: score += 10
    
    if lines_added >= 500: score += 10
    
    insights["performance_score"] = min(score, 100)
    
    # What went well
    if completion_rate >= 80:
        insights["what_went_well"].append(f"Excellent task completion rate ({completion_rate:.0f}%)")
    if pr_merge_rate >= 80:
        insights["what_went_well"].append(f"High PR merge rate ({pr_merge_rate:.0f}%)")
    if commits >= 10:
        insights["what_went_well"].append(f"Consistent development activity ({commits} commits)")
    if story_points >= 8:
        insights["what_went_well"].append(f"Good story point delivery ({story_points} points)")
    
    # Areas for improvement
    if completion_rate < 60:
        insights["areas_for_improvement"].append("Focus on completing assigned tasks")
    if pr_merge_rate < 60 and prs_created > 0:
        insights["areas_for_improvement"].append("Improve code quality to increase PR merge rate")
    if commits < 5:
        insights["areas_for_improvement"].append("Increase development activity and commit frequency")
    if story_points < 5:
        insights["areas_for_improvement"].append("Take on more challenging tasks with higher story points")
    
    return insights

st.title("👤 Individual Productivity Dashboard")

# Initialize Session State
if 'user_authenticated' not in st.session_state: st.session_state.user_authenticated = False
if 'data_fetched' not in st.session_state: st.session_state.data_fetched = False
if 'log_messages' not in st.session_state: st.session_state.log_messages = []
if 'jira_result_individual' not in st.session_state: st.session_state.jira_result_individual = {}
if 'git_metrics_individual' not in st.session_state: st.session_state.git_metrics_individual = {}
if 'num_previous_sprints' not in st.session_state: st.session_state.num_previous_sprints = 3
if 'selected_developer_name' not in st.session_state: st.session_state.selected_developer_name = "--- Select a Developer ---"
if 'selected_duration_name' not in st.session_state: st.session_state.selected_duration_name = "Current Sprint"
if 'all_developers_sorted' not in st.session_state: st.session_state.all_developers_sorted = []

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

    if st.session_state.user_authenticated:
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
            developers_by_team = {}
            for team, developers in team_mapping.items():
                for dev in developers:
                    if team not in developers_by_team:
                        developers_by_team[team] = []
                    developers_by_team[team].append(dev)
            
            sorted_developers = []
            for team in sorted(developers_by_team.keys()):
                sorted_developers.extend(sorted(developers_by_team[team]))
            st.session_state.all_developers_sorted = sorted_developers

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

        # Duration selection similar to trux-jira-metrics
        from common import get_previous_n_sprints, get_current_sprint
        previous_sprints = get_previous_n_sprints(st.session_state.num_previous_sprints)
        detailed_durations_with_sprints = DETAILED_DURATIONS_DATA.copy()
        
        # Add current sprint dynamically
        current_sprint = get_current_sprint()
        detailed_durations_with_sprints[f"Sprint {current_sprint}"] = current_sprint
        
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

        if st.button("🔄 Fetch Individual Metrics", key="fetch_individual_btn"):
            if st.session_state.selected_developer_name == "--- Select a Developer ---":
                st.error("Please select a developer first.")
            else:
                st.session_state.data_fetched = False
                st.session_state.log_messages = []
                
                with st.spinner("Fetching individual metrics..."):
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
                    
                    # JIRA Metrics
                    st.session_state.jira_result_individual = fetch_jira_metrics_via_api(
                        JIRA_CONFIG["email"],
                        JIRA_CONFIG["token"],
                        st.session_state.selected_developer_name,
                        sprint_name,
                        developer_team,
                        st.session_state.log_messages
                    )
                    
                    # Git Metrics - Use dev_branches from JIRA result
                    jira_repos = set()
                    if st.session_state.jira_result_individual and "dev_branches" in st.session_state.jira_result_individual:
                        jira_repos = set(st.session_state.jira_result_individual["dev_branches"])
                        full_repos = set()
                        for repo in jira_repos:
                            if "/" not in repo:
                                full_repos.add(f"truxinc/{repo}")
                            else:
                                full_repos.add(repo)
                        jira_repos = full_repos
                    
                    if jira_repos:
                        st.session_state.git_metrics_individual = fetch_git_metrics_via_api(
                            GITHUB_CONFIG["token"],
                            st.session_state.selected_developer_name,
                            list(jira_repos),
                            st.session_state.log_messages,
                            GITHUB_CONFIG["org"],
                            sprint_id=sprint_name
                        )
                    else:
                        st.session_state.git_metrics_individual = {"commits": 0, "prs_created": 0, "prs_merged": 0, "lines_added": 0, "lines_deleted": 0}
                    
                    st.session_state.data_fetched = True
                    st.success("Individual metrics fetched successfully!")

# Main Content
if st.session_state.user_authenticated:
    if st.session_state.data_fetched and st.session_state.selected_developer_name != "--- Select a Developer ---":
        st.header(f"📊 Individual Productivity for {st.session_state.selected_developer_name}")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🎯 JIRA Metrics")
            jira_data = st.session_state.jira_result_individual
            if jira_data and not jira_data.get("error"):
                jira_df = pd.DataFrame([{
                    "Metric": "Total Issues",
                    "Value": jira_data.get("all_issues_count", 0)
                }, {
                    "Metric": "Issues Completed",
                    "Value": jira_data.get("tickets_closed", 0) + jira_data.get("bugs_closed", 0)
                }, {
                    "Metric": "Story Points",
                    "Value": jira_data.get("story_points_done", 0)
                }, {
                    "Metric": "Bugs Fixed",
                    "Value": jira_data.get("bugs_closed", 0)
                }])
                st.dataframe(jira_df, hide_index=True, use_container_width=True)
            else:
                st.error("Failed to fetch JIRA metrics")
        
        with col2:
            st.subheader("🔧 Git Metrics")
            git_data = st.session_state.git_metrics_individual
            if git_data and not git_data.get("error"):
                git_df = pd.DataFrame([{
                    "Metric": "Commits",
                    "Value": git_data.get("commits", 0)
                }, {
                    "Metric": "PRs Created",
                    "Value": git_data.get("prs_created", 0)
                }, {
                    "Metric": "PRs Merged",
                    "Value": git_data.get("prs_merged", 0)
                }, {
                    "Metric": "Lines Added",
                    "Value": git_data.get("lines_added", 0)
                }])
                st.dataframe(git_df, hide_index=True, use_container_width=True)
            else:
                st.error("Failed to fetch Git metrics")
        
        # Performance Insights
        if jira_data and git_data:
            st.subheader("📈 Performance Insights")
            insights = generate_performance_insights(jira_data, git_data)
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("Performance Score", f"{insights['performance_score']}/100")
            
            with col2:
                st.markdown("**What Went Well:**")
                for item in insights["what_went_well"]:
                    st.success(f"✅ {item}")
            
            with col3:
                st.markdown("**Areas for Improvement:**")
                for item in insights["areas_for_improvement"]:
                    st.warning(f"⚠️ {item}")
        
        # Logs
        if st.session_state.log_messages:
            with st.expander("📋 Processing Logs", expanded=False):
                for log in st.session_state.log_messages:
                    st.text(log)
    else:
        st.info("Select a developer and click 'Fetch Individual Metrics' to view data.")
else:
    st.info("Please authenticate to access the dashboard.")