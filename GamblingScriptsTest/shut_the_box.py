import random

def roll_dice(num_dice=2):
    """Roll dice and return the total."""
    rolls = [random.randint(1, 6) for _ in range(num_dice)]
    return sum(rolls), rolls

def get_valid_combinations(tiles, target):
    """Find all valid combinations of tiles that sum to target."""
    valid = []
    # Check single tiles
    for tile in tiles:
        if tile == target:
            valid.append([tile])
    # Check pairs
    for i, t1 in enumerate(tiles):
        for t2 in tiles[i+1:]:
            if t1 + t2 == target:
                valid.append([t1, t2])
    # Check triples
    for i, t1 in enumerate(tiles):
        for j, t2 in enumerate(tiles[i+1:], i+1):
            for t3 in tiles[j+1:]:
                if t1 + t2 + t3 == target:
                    valid.append([t1, t2, t3])
    # Check quadruples (for larger sums)
    for i, t1 in enumerate(tiles):
        for j, t2 in enumerate(tiles[i+1:], i+1):
            for k, t3 in enumerate(tiles[j+1:], j+1):
                for t4 in tiles[k+1:]:
                    if t1 + t2 + t3 + t4 == target:
                        valid.append([t1, t2, t3, t4])
    return valid

def display_tiles(tiles):
    """Display the current state of tiles."""
    print("\n+---" * 9 + "+")
    print("|", end="")
    for i in range(1, 10):
        if i in tiles:
            print(f" {i} |", end="")
        else:
            print(" X |", end="")
    print("\n+---" * 9 + "+")

def play_round():
    """Play a single round of Shut the Box. Returns True if player wins."""
    tiles = list(range(1, 10))  # Tiles 1-9
    
    print("\n" + "="*50)
    print("       SHUT THE BOX - NEW GAME")
    print("="*50)
    print("Goal: Shut all tiles by matching dice rolls!")
    
    while tiles:
        display_tiles(tiles)
        
        # Roll one die if remaining tiles sum to 6 or less
        remaining_sum = sum(tiles)
        if remaining_sum <= 6:
            num_dice = 1
            total, rolls = roll_dice(1)
            print(f"\nRolling 1 die (remaining sum <= 6): [{rolls[0]}] = {total}")
        else:
            num_dice = 2
            total, rolls = roll_dice(2)
            print(f"\nRolling 2 dice: [{rolls[0]}] [{rolls[1]}] = {total}")
        
        # Find valid combinations
        combinations = get_valid_combinations(tiles, total)
        
        if not combinations:
            print(f"\nNo valid moves! You can't make {total} with remaining tiles.")
            print("GAME OVER - You lose!")
            return False
        
        # Show choices
        print(f"\nYou need to shut tiles that add up to {total}")
        print("\nYour choices:")
        for i, combo in enumerate(combinations, 1):
            print(f"  {i}. Shut tile(s): {combo}")
        
        # Get player choice
        while True:
            try:
                choice = input(f"\nSelect your choice (1-{len(combinations)}): ").strip()
                choice_idx = int(choice) - 1
                if 0 <= choice_idx < len(combinations):
                    break
                print(f"Please enter a number between 1 and {len(combinations)}")
            except ValueError:
                print("Please enter a valid number")
        
        # Shut the selected tiles
        selected = combinations[choice_idx]
        for tile in selected:
            tiles.remove(tile)
        print(f"\nShut tile(s): {selected}")
    
    # All tiles shut!
    display_tiles(tiles)
    print("\n*** CONGRATULATIONS! YOU SHUT THE BOX! ***")
    return True

def main():
    """Main game loop."""
    money = 1000
    cost_to_play = 100
    win_prize = 200
    
    print("\n" + "#"*50)
    print("#" + " "*48 + "#")
    print("#        WELCOME TO SHUT THE BOX!            #")
    print("#" + " "*48 + "#")
    print("#"*50)
    print(f"\nRules:")
    print(f"  - Cost to play: ${cost_to_play}")
    print(f"  - Win prize: +${win_prize}")
    print(f"  - Starting money: ${money}")
    print(f"\nHow to play:")
    print("  - Roll dice and shut tiles that sum to the roll")
    print("  - Shut all tiles (1-9) to win!")
    print("  - If you can't make a move, you lose")
    
    while True:
        print(f"\n{'='*50}")
        print(f"Your money: ${money}")
        print(f"{'='*50}")
        
        if money < cost_to_play:
            print("\nYou don't have enough money to play!")
            print("GAME OVER - Thanks for playing!")
            break
        
        print(f"\n[P] Play (costs ${cost_to_play})")
        print("[Q] Quit")
        
        choice = input("\nWhat would you like to do? ").strip().upper()
        
        if choice == 'Q':
            print(f"\nYou leave with ${money}. Thanks for playing!")
            break
        elif choice == 'P':
            money -= cost_to_play
            print(f"\nPaid ${cost_to_play} to play. Remaining: ${money}")
            
            if play_round():
                money += win_prize + cost_to_play  # Return bet + prize
                print(f"\nYou won +${win_prize}! New balance: ${money}")
            else:
                print(f"\nYou lost ${cost_to_play}. Remaining: ${money}")
        else:
            print("Invalid choice. Please enter P or Q.")

if __name__ == "__main__":
    main()
