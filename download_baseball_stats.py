import pybaseball
import sys
import pandas as pd

def download_stats(team, year):
    """
    Downloads batting and pitching stats for a specific team and year
    using pybaseball and saves them as CSV files.
    """
    print(f"Downloading stats for Team: {team}, Year: {year}")

    # --- Batting Stats ---
    print("Downloading batting stats...")
    try:
        # Fetch batting stats for the given year. qual=None ensures we get all players, not just qualified ones.
        # Actually in pybaseball documentation qual should be a number (minimum PA) or None.
        # However, checking the library source or behavior, 0 is often used.
        # Let's verify if qual=0 works or qual=None.
        # According to docstring, qual: minimum number of plate appearances to be included. If None is specified, all players are included.
        # But wait, looking at pybaseball source code (if I could), usually it is `qual=None` for all.
        # However, the reviewer suggested `qual=0`.
        # I will use qual=0 as it is standard for "minimum 0 PA".
        batting = pybaseball.batting_stats(year, qual=0)

        # Filter by team
        if 'Team' in batting.columns:
            team_batting = batting[batting['Team'] == team]

            if team_batting.empty:
                print(f"Warning: No batting data found for team '{team}'. Check if the abbreviation is correct (e.g., 'NYY', 'LAD').")
            else:
                filename = f"{team}_{year}_batting.csv"
                team_batting.to_csv(filename, index=False)
                print(f"Batting stats saved to {filename}")
                print(f"Number of players found: {len(team_batting)}")
        else:
             print("Error: 'Team' column not found in batting data.")

    except Exception as e:
        print(f"Error downloading batting stats: {e}")

    # --- Pitching Stats ---
    print("Downloading pitching stats...")
    try:
        # Fetch pitching stats for the given year. qual=0 for all pitchers.
        pitching = pybaseball.pitching_stats(year, qual=0)

        if 'Team' in pitching.columns:
            team_pitching = pitching[pitching['Team'] == team]

            if team_pitching.empty:
                print(f"Warning: No pitching data found for team '{team}'.")
            else:
                filename = f"{team}_{year}_pitching.csv"
                team_pitching.to_csv(filename, index=False)
                print(f"Pitching stats saved to {filename}")
                print(f"Number of pitchers found: {len(team_pitching)}")
        else:
            print("Error: 'Team' column not found in pitching data.")

    except Exception as e:
        print(f"Error downloading pitching stats: {e}")

if __name__ == "__main__":
    # Check if arguments are provided via command line
    if len(sys.argv) == 3:
        team_arg = sys.argv[1].upper()
        year_arg = sys.argv[2]
        try:
            year_int = int(year_arg)
            download_stats(team_arg, year_int)
        except ValueError:
            print("Error: Year must be an integer.")
            sys.exit(1)
    else:
        # Interactive mode
        print("Enter team and year to download stats.")
        team_input = input("Enter Team Abbreviation (e.g., NYY): ").strip().upper()
        year_input = input("Enter Year (e.g., 2023): ").strip()

        try:
            year_int = int(year_input)
            download_stats(team_input, year_int)
        except ValueError:
            print("Error: Year must be an integer.")
            sys.exit(1)
