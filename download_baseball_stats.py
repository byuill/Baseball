import pybaseball
import sys
import pandas as pd
import numpy as np

def download_stats(team, year):
    """
    Downloads batting and pitching stats for a specific team and year
    using pybaseball and saves them as CSV files.
    Also identifies the optimal batting order and best starting pitcher.
    """
    print(f"Downloading stats for Team: {team}, Year: {year}")

    # --- Batting Stats ---
    print("Downloading batting stats...")
    try:
        batting = pybaseball.batting_stats(year, qual=0)

        if 'Team' in batting.columns:
            team_batting = batting[batting['Team'] == team].copy()

            if team_batting.empty:
                print(f"Warning: No batting data found for team '{team}'. Check if the abbreviation is correct (e.g., 'NYY', 'LAD').")
            else:
                filename = f"{team}_{year}_batting.csv"
                team_batting.to_csv(filename, index=False)
                print(f"Batting stats saved to {filename}")
                print(f"Number of players found: {len(team_batting)}")
        else:
             print("Error: 'Team' column not found in batting data.")
             return

    except Exception as e:
        print(f"Error downloading batting stats: {e}")
        return

    # --- Pitching Stats ---
    print("Downloading pitching stats...")
    try:
        pitching = pybaseball.pitching_stats(year, qual=0)

        if 'Team' in pitching.columns:
            team_pitching = pitching[pitching['Team'] == team].copy()

            if team_pitching.empty:
                print(f"Warning: No pitching data found for team '{team}'.")
            else:
                filename = f"{team}_{year}_pitching.csv"
                team_pitching.to_csv(filename, index=False)
                print(f"Pitching stats saved to {filename}")
                print(f"Number of pitchers found: {len(team_pitching)}")
        else:
            print("Error: 'Team' column not found in pitching data.")
            return

    except Exception as e:
        print(f"Error downloading pitching stats: {e}")
        return

    # --- Optimal Lineup & Best Pitcher ---
    print("Calculating optimal lineup and best starting pitcher...")
    try:
        # 1. Get Fielding Stats to determine positions
        # qual=0 ensures we get all fielders
        fielding = pybaseball.fielding_stats(year, qual=0)

        # Filter fielding for the team
        if 'Team' in fielding.columns:
            team_fielding = fielding[fielding['Team'] == team].copy()
        else:
            print("Error: 'Team' column not found in fielding data.")
            return

        # Prepare to merge batting and fielding
        # A player might appear multiple times in fielding (different positions).
        # We want their primary position (most innings).
        # We sort by Innings descending and drop duplicates keeping the first (max innings).
        if 'Inn' in team_fielding.columns:
             team_fielding = team_fielding.sort_values('Inn', ascending=False)

        # Drop duplicates by IDfg to get primary position
        # Rename 'Pos' to 'FieldingPos' to avoid conflict with batting 'Pos' (Positional Adjustment)
        primary_positions = team_fielding.drop_duplicates(subset=['IDfg'])[['IDfg', 'Pos']].rename(columns={'Pos': 'FieldingPos'})

        # Merge Position into Batting Data
        # We use left join to keep all batters (including those who didn't field, likely DH)
        merged_batting = pd.merge(team_batting, primary_positions, on='IDfg', how='left')

        # Define positions we want to fill
        target_positions = ['C', '1B', '2B', '3B', 'SS', 'LF', 'CF', 'RF']

        optimal_lineup = []
        used_player_ids = set()

        # Find best player for each defensive position based on WAR
        metric = 'WAR'
        if metric not in merged_batting.columns:
             print(f"Warning: '{metric}' column not found. Using 'wRC+' instead.")
             metric = 'wRC+' # Fallback

        for pos in target_positions:
            # Filter for players at this position
            candidates = merged_batting[merged_batting['FieldingPos'] == pos]

            if not candidates.empty:
                # Find the one with max WAR
                best_player = candidates.loc[candidates[metric].idxmax()]
                optimal_lineup.append({
                    'Position': pos,
                    'Player': best_player['Name'],
                    'Stat_Name': metric,
                    'Stat_Value': best_player[metric]
                })
                used_player_ids.add(best_player['IDfg'])
            else:
                optimal_lineup.append({
                    'Position': pos,
                    'Player': 'N/A',
                    'Stat_Name': metric,
                    'Stat_Value': 'N/A'
                })

        # Identify DH (Best remaining batter)
        # Any batter not yet assigned to a position
        remaining_batters = merged_batting[~merged_batting['IDfg'].isin(used_player_ids)]

        # Filter out pitchers from remaining batters if possible (though they usually have low WAR anyway)
        # But wait, fielding stats include 'P'. If a player is strictly P, they might be in remaining_batters if they batted.
        # However, we only care about their batting stats.

        if not remaining_batters.empty:
            best_dh = remaining_batters.loc[remaining_batters[metric].idxmax()]
            optimal_lineup.append({
                'Position': 'DH',
                'Player': best_dh['Name'],
                'Stat_Name': metric,
                'Stat_Value': best_dh[metric]
            })
        else:
             optimal_lineup.append({
                'Position': 'DH',
                'Player': 'N/A',
                'Stat_Name': metric,
                'Stat_Value': 'N/A'
            })

        # --- Best Starting Pitcher ---
        # Criteria: Best winning percentage, ERA, and innings pitched.
        # Filter for Starters: GS >= 1
        starters = team_pitching[team_pitching['GS'] > 0].copy()

        if not starters.empty:
            # Calculate Win Percentage
            starters['Win_Pct'] = starters.apply(lambda row: row['W'] / (row['W'] + row['L']) if (row['W'] + row['L']) > 0 else 0, axis=1)

            # Normalize metrics
            def normalize(series, maximize=True):
                min_val = series.min()
                max_val = series.max()
                if max_val == min_val:
                    return pd.Series([1.0] * len(series), index=series.index)
                if maximize:
                    return (series - min_val) / (max_val - min_val)
                else:
                    return 1 - (series - min_val) / (max_val - min_val)

            starters['Norm_Win_Pct'] = normalize(starters['Win_Pct'], maximize=True)
            starters['Norm_ERA'] = normalize(starters['ERA'], maximize=False)
            starters['Norm_IP'] = normalize(starters['IP'], maximize=True)

            # Composite Score
            starters['Score'] = starters['Norm_Win_Pct'] + starters['Norm_ERA'] + starters['Norm_IP']

            best_sp = starters.loc[starters['Score'].idxmax()]

            optimal_lineup.append({
                'Position': 'SP',
                'Player': best_sp['Name'],
                'Stat_Name': 'Composite Score (Win%, ERA, IP)',
                'Stat_Value': f"{best_sp['Score']:.2f} (W:{best_sp['W']}, L:{best_sp['L']}, ERA:{best_sp['ERA']}, IP:{best_sp['IP']})"
            })
        else:
             optimal_lineup.append({
                'Position': 'SP',
                'Player': 'N/A',
                'Stat_Name': 'Composite Score',
                'Stat_Value': 'N/A'
            })

        # Create DataFrame and Save
        optimal_df = pd.DataFrame(optimal_lineup)
        optimal_filename = f"{team}_{year}_optimal_lineup.csv"
        optimal_df.to_csv(optimal_filename, index=False)
        print(f"Optimal lineup and best pitcher saved to {optimal_filename}")
        print(optimal_df)

    except Exception as e:
        print(f"Error calculating optimal lineup: {e}")
        import traceback
        traceback.print_exc()

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
