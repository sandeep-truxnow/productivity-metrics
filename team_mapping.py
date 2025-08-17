import os

def load_team_mapping():
    """Load team-developer mapping from teams.txt file."""
    team_map = {}
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, "teams.txt")
        
        with open(file_path, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if line and '|' in line:
                    team, developer = line.split('|', 1)
                    team = team.strip()
                    developer = developer.strip()
                    
                    if team not in team_map:
                        team_map[team] = []
                    team_map[team].append(developer)
        
        return team_map
    except FileNotFoundError:
        return {}

def get_developers_for_team(team_name):
    """Get list of developers for a specific team."""
    team_map = load_team_mapping()
    return team_map.get(team_name, [])

def get_all_teams():
    """Get list of all teams."""
    team_map = load_team_mapping()
    return list(team_map.keys())