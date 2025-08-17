from collections import OrderedDict
from datetime import datetime, date, timedelta
from typing import Dict, Any

# Duration options similar to trux-jira-metrics
DETAILED_DURATIONS_DATA: Dict[str, Any] = OrderedDict([
    ("Current Sprint", "openSprints()"),
    ("Year to Date", "startOfYear()"),
])

def get_sprint_dates_from_name(sprint_name, base_sprint="2025.12", base_start_date_str="2025-06-11", sprint_length_days=14):
    """Get sprint start and end dates from sprint name"""
    base_year, base_sprint_num = map(int, base_sprint.split("."))
    target_year, target_sprint_num = map(int, sprint_name.split("."))
    base_start_date = datetime.strptime(base_start_date_str, "%Y-%m-%d").date()

    # Calculate total number of sprints between base and target
    year_diff = target_year - base_year
    sprint_diff = (year_diff * 52) + (target_sprint_num - base_sprint_num)

    # Get sprint start and end dates
    sprint_start_date = base_start_date + timedelta(days=sprint_diff * sprint_length_days)
    sprint_end_date = sprint_start_date + timedelta(days=sprint_length_days - 1)

    return sprint_start_date, sprint_end_date

def get_previous_n_sprints(count, base_sprint="2025.12", base_start_date_str="2025-06-11", sprint_length_days=14):
    base_year, base_sprint_num = map(int, base_sprint.split("."))
    base_start_date = datetime.strptime(base_start_date_str, "%Y-%m-%d").date()
    today = datetime.today().date()

    # Calculate how many sprints have passed
    days_elapsed = (today - base_start_date).days
    sprint_offset = days_elapsed // sprint_length_days
    current_sprint_num = base_sprint_num + sprint_offset
    current_year = base_year

    # Adjust year if needed
    while current_sprint_num > 52:
        current_sprint_num -= 52
        current_year += 1

    # Get previous 'count' sprints
    result = []
    for i in range(count):
        sprint_num = current_sprint_num - i - 1
        year = current_year
        while sprint_num <= 0:
            sprint_num += 52
            year -= 1
        result.append(f"{year}.{sprint_num:02d}")
    return list(result)

def get_previous_sprints(count=5):
    """Generate previous sprint names based on current date"""
    current_year = datetime.now().year
    current_week = datetime.now().isocalendar()[1]
    
    # Estimate current sprint (assuming 2-week sprints, 26 per year)
    current_sprint = min(26, max(1, (current_week // 2) + 1))
    
    sprints = []
    for i in range(count):
        sprint_num = current_sprint - i - 1
        year = current_year
        
        if sprint_num <= 0:
            year -= 1
            sprint_num = 26 + sprint_num
            
        sprints.append(f"{year}.{sprint_num:02d}")
    
    return sprints

def get_sprint_for_date(target_date, base_sprint="2025.12", base_start_date_str="2025-06-11", sprint_length_days=14):
    """Get sprint info for a given date using the same logic as trux-jira-metrics"""
    try:
        base_year, base_sprint_num = map(int, base_sprint.split("."))
        base_start_date = datetime.strptime(base_start_date_str, "%Y-%m-%d").date()
        target_date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()

        # Calculate days between target and base
        days_elapsed = (target_date_obj - base_start_date).days
        sprint_offset = days_elapsed // sprint_length_days

        sprint_num = base_sprint_num + sprint_offset
        sprint_start_date = base_start_date + timedelta(days=sprint_offset * sprint_length_days)
        sprint_year = base_year

        # Adjust for year overflow
        while sprint_num > 52:
            sprint_num -= 52
            sprint_year += 1

        sprint_end_date = sprint_start_date + timedelta(days=sprint_length_days - 1)
        sprint_name = f"{sprint_year}.{sprint_num:02d}"

        return sprint_name, sprint_start_date, sprint_end_date
    except Exception as e:
        return "2025.01", date.today(), date.today()

def show_sprint_name_start_date_and_end_date(duration_name, log_list):
    """Get sprint details based on duration selection"""
    if duration_name == "Current Sprint":
        today_str = date.today().strftime("%Y-%m-%d")
        return get_sprint_for_date(today_str)
    elif duration_name.startswith("Sprint "):
        sprint_name = duration_name.replace("Sprint ", "")
        sprint_start_date, sprint_end_date = get_sprint_dates_from_name(sprint_name)
        return sprint_name, sprint_start_date, sprint_end_date
    else:
        today_str = date.today().strftime("%Y-%m-%d")
        return get_sprint_for_date(today_str)
