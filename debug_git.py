#!/usr/bin/env python3
"""
Debug script to test git commit fetching functionality
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.git_parser import fetch_git_metrics_via_api, _get_github_login_from_fullname
from config import GITHUB_CONFIG
from team_mapping import load_team_mapping

def debug_git_commits():
    """Debug git commit fetching"""
    print("🔍 Debugging Git Commit Details...")
    print("=" * 50)
    
    # Test configuration
    print("1. Testing Configuration:")
    print(f"   GitHub Org: {GITHUB_CONFIG['org']}")
    print(f"   GitHub Token: {'*' * 20}{GITHUB_CONFIG['token'][-10:] if len(GITHUB_CONFIG['token']) > 10 else 'INVALID'}")
    
    # Test team mapping
    print("\n2. Testing Team Mapping:")
    team_mapping = load_team_mapping()
    if team_mapping:
        print(f"   Found {len(team_mapping)} teams:")
        for team, developers in team_mapping.items():
            print(f"   - {team}: {len(developers)} developers")
            if developers:
                print(f"     First developer: {developers[0]}")
    else:
        print("   ❌ No team mapping found!")
    
    # Test GitHub login resolution
    print("\n3. Testing GitHub Login Resolution:")
    if team_mapping:
        # Get first developer from first team
        first_team = list(team_mapping.keys())[0]
        first_developer = team_mapping[first_team][0]
        
        print(f"   Testing developer: {first_developer}")
        log_list = []
        
        github_login = _get_github_login_from_fullname(
            GITHUB_CONFIG["token"],
            first_developer,
            GITHUB_CONFIG["org"],
            log_list
        )
        
        print(f"   Resolved GitHub login: {github_login}")
        
        if log_list:
            print("   Logs:")
            for log in log_list:
                print(f"     {log}")
    
    # Test git metrics fetching
    print("\n4. Testing Git Metrics Fetching:")
    if team_mapping:
        first_team = list(team_mapping.keys())[0]
        first_developer = team_mapping[first_team][0]
        
        # Test with a common repository
        test_repos = ["truxinc/beacon-service", "truxinc/core-service"]
        
        print(f"   Testing with developer: {first_developer}")
        print(f"   Testing with repos: {test_repos}")
        
        log_list = []
        
        try:
            git_metrics = fetch_git_metrics_via_api(
                GITHUB_CONFIG["token"],
                first_developer,
                test_repos,
                log_list,
                GITHUB_CONFIG["org"],
                sprint_id="2025.13"  # Current sprint
            )
            
            print(f"   Git Metrics Result:")
            print(f"     Commits: {git_metrics.get('commits', 0)}")
            print(f"     Lines Added: {git_metrics.get('lines_added', 0)}")
            print(f"     Lines Deleted: {git_metrics.get('lines_deleted', 0)}")
            print(f"     Files Changed: {git_metrics.get('files_changed', 0)}")
            print(f"     PRs Created: {git_metrics.get('prs_created', 0)}")
            print(f"     PRs Merged: {git_metrics.get('prs_merged', 0)}")
            
            if git_metrics.get('error'):
                print(f"   ❌ Error: {git_metrics['error']}")
            
        except Exception as e:
            print(f"   ❌ Exception: {e}")
        
        if log_list:
            print("\n   Detailed Logs:")
            for log in log_list:
                print(f"     {log}")
    
    print("\n" + "=" * 50)
    print("Debug completed!")

if __name__ == "__main__":
    debug_git_commits()