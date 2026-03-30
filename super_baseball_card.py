import pybaseball
import pandas as pd
import sys
import warnings

# Suppress warnings
warnings.filterwarnings("ignore")

# Setup pandas display options
pd.set_option('display.max_columns', None)
pd.set_option('display.width', 1000)
pd.set_option('display.colheader_justify', 'center')
pd.set_option('display.precision', 3)

def lookup_player(name_input):
    """
    Look up a player by name.
    Returns the player info row from playerid_lookup.
    """
    print(f"Looking up '{name_input}'...")

    parts = name_input.split()
    if len(parts) == 1:
        # Try as last name, then first name?
        # playerid_lookup requires last, first usually.
        # If one name provided, pybaseball might assume it's last name.
        # Let's try last name first.
        try:
            data = pybaseball.playerid_lookup(parts[0])
        except:
             # If it fails, maybe try assuming it's a known single name (unlikely in MLB)
             return None
    else:
        first = parts[0]
        last = " ".join(parts[1:])
        data = pybaseball.playerid_lookup(last, first)

    if data.empty:
        # Try swapping?
        if len(parts) > 1:
             data = pybaseball.playerid_lookup(parts[0], parts[1])
        if data.empty:
            return None

    # Filter for valid Fangraphs ID (since we use Fangraphs stats)
    data = data[data['key_fangraphs'] != -1]

    if data.empty:
        return None

    if len(data) > 1:
        print(f"Found {len(data)} players matching '{name_input}':")
        # Display options
        for i, row in data.iterrows():
            print(f"{i}: {row['name_first']} {row['name_last']} (MLB: {row['mlb_played_first']}-{row['mlb_played_last']}) - ID: {row['key_fangraphs']}")

        # In a real interactive script, we'd ask. For now, pick the most recent one or exact match.
        # Let's sort by recent year.
        data = data.sort_values('mlb_played_last', ascending=False)
        print(f"Selecting most recent: {data.iloc[0]['name_first']} {data.iloc[0]['name_last']}")
        return data.iloc[0]

    return data.iloc[0]

def fetch_stats(player_info):
    """
    Fetch batting and pitching stats for the player.
    Fetching large ranges at once can fail (FanGraphs 500 error).
    We fetch in chunks or year-by-year to be safe.
    """
    start_year = int(player_info['mlb_played_first'])
    end_year = int(player_info['mlb_played_last'])
    fg_id = player_info['key_fangraphs']

    print(f"Fetching stats for {player_info['name_first']} {player_info['name_last']} ({start_year}-{end_year})...")
    print("This may take a moment as we download data from FanGraphs...")

    batting_data = pd.DataFrame()
    pitching_data = pd.DataFrame()

    # Define a helper to fetch in chunks
    def fetch_in_chunks(func, start, end, chunk_size=3):
        all_stats = pd.DataFrame()
        for year in range(start, end + 1, chunk_size):
            chunk_end = min(year + chunk_size - 1, end)
            # print(f"  Downloading {year}-{chunk_end}...")
            try:
                # qual=0 is needed to ensure we get the player even if not qualified
                chunk = func(year, chunk_end, qual=0)
                if not chunk.empty:
                    all_stats = pd.concat([all_stats, chunk], ignore_index=True)
            except Exception as e:
                # If chunk fails, try year by year for this chunk?
                # Or just print error and continue
                print(f"  Warning: Failed to fetch {year}-{chunk_end}: {e}")
                # Fallback to year-by-year for this chunk
                for y in range(year, chunk_end + 1):
                    try:
                        y_stats = func(y, qual=0)
                        if not y_stats.empty:
                            all_stats = pd.concat([all_stats, y_stats], ignore_index=True)
                    except Exception as inner_e:
                        print(f"  Warning: Failed to fetch {y}: {inner_e}")

        return all_stats

    # Fetch Batting
    try:
        batting = fetch_in_chunks(pybaseball.batting_stats, start_year, end_year)
        if not batting.empty and 'IDfg' in batting.columns:
            batting_data = batting[batting['IDfg'] == fg_id].copy()
            # Remove duplicates if any (though range/year fetch shouldn't overlap)
            batting_data = batting_data.drop_duplicates(subset=['Season', 'Team'])
    except Exception as e:
        print(f"Error fetching batting stats: {e}")

    # Fetch Pitching
    try:
        pitching = fetch_in_chunks(pybaseball.pitching_stats, start_year, end_year)
        if not pitching.empty and 'IDfg' in pitching.columns:
            pitching_data = pitching[pitching['IDfg'] == fg_id].copy()
            pitching_data = pitching_data.drop_duplicates(subset=['Season', 'Team'])
    except Exception as e:
        print(f"Error fetching pitching stats: {e}")

    return batting_data, pitching_data

def calculate_batting_career(df):
    """Calculate career totals for batting."""
    if df.empty:
        return None

    totals = {}
    sum_cols = ['G', 'AB', 'PA', 'H', '1B', '2B', '3B', 'HR', 'R', 'RBI', 'BB', 'SO', 'SB', 'CS']

    for col in sum_cols:
        if col in df.columns:
            totals[col] = df[col].sum()
        else:
            totals[col] = 0

    # Averages
    if totals['AB'] > 0:
        totals['AVG'] = totals['H'] / totals['AB']
        totals['SLG'] = (totals['1B'] + 2*totals['2B'] + 3*totals['3B'] + 4*totals['HR']) / totals['AB']
    else:
        totals['AVG'] = 0.0
        totals['SLG'] = 0.0

    if totals['PA'] > 0:
        # Approximate OBP: (H + BB + HBP) / (AB + BB + HBP + SF)
        # We need HBP and SF from df
        hbp = df['HBP'].sum() if 'HBP' in df.columns else 0
        sf = df['SF'].sum() if 'SF' in df.columns else 0
        totals['OBP'] = (totals['H'] + totals['BB'] + hbp) / (totals['AB'] + totals['BB'] + hbp + sf)
    else:
        totals['OBP'] = 0.0

    totals['OPS'] = totals['OBP'] + totals['SLG']

    # WAR is sum
    if 'WAR' in df.columns:
        totals['WAR'] = df['WAR'].sum()
    else:
        totals['WAR'] = 0.0

    return totals

def calculate_pitching_career(df):
    """Calculate career totals for pitching."""
    if df.empty:
        return None

    totals = {}
    # Handle IP separately for correct baseball math (base-3 for partial innings)
    sum_cols = ['W', 'L', 'G', 'GS', 'SV', 'H', 'ER', 'HR', 'BB', 'SO']

    for col in sum_cols:
        if col in df.columns:
            totals[col] = df[col].sum()
        else:
            totals[col] = 0

    # Calculate IP Sum correctly
    if 'IP' in df.columns:
        total_outs = 0
        for ip in df['IP']:
            if pd.isna(ip): continue
            full_innings = int(ip)
            partial = round((ip - full_innings) * 10) # 0, 1, or 2
            total_outs += full_innings * 3 + partial

        totals['IP'] = (total_outs // 3) + (total_outs % 3) / 10.0
    else:
        totals['IP'] = 0.0

    # ERA: 9 * ER / IP (using total innings in decimal form for ERA calc? No, usually pure innings)
    # ERA is typically 9 * ER / (Outs/3)
    # pybaseball IP column: 10.1 is 10 + 1/3.
    # But for ERA calculation, we should use the actual innings value (10.3333).
    # Wait, if we use the summed IP in X.Y format, the ERA calc might be slightly off if we don't convert .1 to .333.
    # Let's convert IP to true decimal for ERA calculation.

    true_ip = 0
    if 'IP' in df.columns:
        # Re-calculate true IP (e.g. 10.1 -> 10.333)
        ip_sum_outs = 0
        for ip in df['IP']:
            if pd.isna(ip): continue
            full = int(ip)
            part = round((ip - full) * 10)
            ip_sum_outs += full * 3 + part
        true_ip = ip_sum_outs / 3.0

    if true_ip > 0:
        totals['ERA'] = (9 * totals['ER']) / true_ip
        totals['WHIP'] = (totals['BB'] + totals['H']) / true_ip
        totals['K/9'] = (9 * totals['SO']) / true_ip
    else:
        totals['ERA'] = 0.0
        totals['WHIP'] = 0.0
        totals['K/9'] = 0.0

    if 'WAR' in df.columns:
        totals['WAR'] = df['WAR'].sum()
    else:
        totals['WAR'] = 0.0

    return totals

def display_card(player_info, batting, pitching):
    print("\n" + "="*80)
    print(f"  SUPER BASEBALL CARD: {player_info['name_first']} {player_info['name_last'].upper()}")
    print("="*80)

    # --- BATTING SECTION ---
    if not batting.empty:
        print("\n--- BATTING STATISTICS ---")
        cols = ['Season', 'Team', 'G', 'AB', 'R', 'H', 'HR', 'RBI', 'SB', 'BB', 'SO', 'AVG', 'OBP', 'SLG', 'OPS', 'wRC+', 'WAR']
        # Filter cols that exist
        cols = [c for c in cols if c in batting.columns]

        # Sort by season
        batting_sorted = batting.sort_values('Season')

        # Print Table
        print(batting_sorted[cols].to_string(index=False))

        # Career Line
        career = calculate_batting_career(batting)
        print("-" * 120)
        c_line = f"CAREER  Total {career['G']:>4} {career['AB']:>4} {career['R']:>4} {career['H']:>4} {career['HR']:>3} {career['RBI']:>4} {career['SB']:>3} {career['BB']:>4} {career['SO']:>4} "
        c_line += f"{career['AVG']:.3f} {career['OBP']:.3f} {career['SLG']:.3f} {career['OPS']:.3f}      {career['WAR']:.1f}"
        print(c_line)
        print("-" * 120)

    # --- PITCHING SECTION ---
    if not pitching.empty:
        print("\n--- PITCHING STATISTICS ---")
        cols = ['Season', 'Team', 'W', 'L', 'ERA', 'G', 'GS', 'SV', 'IP', 'H', 'ER', 'BB', 'SO', 'WHIP', 'WAR']
        cols = [c for c in cols if c in pitching.columns]

        pitching_sorted = pitching.sort_values('Season')
        print(pitching_sorted[cols].to_string(index=False))

        career = calculate_pitching_career(pitching)
        print("-" * 120)
        c_line = f"CAREER  Total {career['W']:>3} {career['L']:>3} {career['ERA']:.2f} {career['G']:>4} {career['GS']:>3} {career['SV']:>3} {career['IP']:>5.1f} {career['H']:>4} {career['ER']:>4} {career['BB']:>4} {career['SO']:>4} {career['WHIP']:.2f} {career['WAR']:.1f}"
        print(c_line)
        print("-" * 120)

    if batting.empty and pitching.empty:
        print("No stats found for this player.")

def main():
    if len(sys.argv) > 1:
        name_input = " ".join(sys.argv[1:])
    else:
        name_input = input("Enter player name: ").strip()

    if not name_input:
        print("No name entered.")
        return

    player_info = lookup_player(name_input)
    if player_info is None:
        print(f"Player '{name_input}' not found.")
        return

    batting, pitching = fetch_stats(player_info)
    display_card(player_info, batting, pitching)

if __name__ == "__main__":
    main()
