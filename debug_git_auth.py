#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from utils.git_parser import _get_github_login_from_fullname
from config import GITHUB_CONFIG

def test_github_auth():
    """Test GitHub authentication and name resolution"""
    
    github_token = GITHUB_CONFIG["token"]
    github_org = GITHUB_CONFIG["org"]
    test_names = ["Pratik Dandavate", "Amsal Karic"]
    
    print(f"Testing GitHub authentication...")
    print(f"Organization: {github_org}")
    print(f"Token present: {bool(github_token)}")
    print(f"Token length: {len(github_token) if github_token else 0}")
    print()
    
    for developer_name in test_names:
        print(f"Testing name resolution for: {developer_name}")
        log_list = []
        
        github_login = _get_github_login_from_fullname(
            github_token, 
            developer_name, 
            github_org, 
            log_list
        )
        
        print(f"Resolved login: {github_login}")
        print("Logs:")
        for log in log_list:
            print(f"  {log}")
        print("-" * 50)

if __name__ == "__main__":
    test_github_auth()
