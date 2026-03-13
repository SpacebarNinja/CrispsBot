import random

# Card setup
SUITS = ['♥', '♦', '♣', '♠']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
RANK_VALUES = {r: i for i, r in enumerate(RANKS)}

def create_deck():
    """Create a shuffled 52-card deck."""
    deck = [(rank, suit) for suit in SUITS for rank in RANKS]
    random.shuffle(deck)
    return deck

def display_card(card, hidden=False):
    """Return ASCII art for a card."""
    if hidden:
        return [
            "┌─────────┐",
            "│░░░░░░░░░│",
            "│░░░░░░░░░│",
            "│░░░ ? ░░░│",
            "│░░░░░░░░░│",
            "│░░░░░░░░░│",
            "└─────────┘"
        ]
    rank, suit = card
    r = rank if len(rank) == 2 else rank + " "
    r2 = rank if len(rank) == 2 else " " + rank
    return [
        "┌─────────┐",
        f"│ {r}      │",
        "│         │",
        f"│    {suit}    │",
        "│         │",
        f"│      {r2} │",
        "└─────────┘"
    ]

def show_cards(current, next_card=None, reveal=False):
    """Display cards side by side."""
    card1 = display_card(current)
    if next_card:
        card2 = display_card(next_card, hidden=not reveal)
    else:
        card2 = display_card(('?', '?'), hidden=True)
    
    print()
    for i in range(7):
        print(f"  {card1[i]}    {card2[i]}")
    print("     CURRENT         NEXT")

def compare_cards(current, next_card):
    """Compare two cards. Returns 'higher', 'lower', or 'tie'."""
    curr_val = RANK_VALUES[current[0]]
    next_val = RANK_VALUES[next_card[0]]
    
    if next_val > curr_val:
        return 'higher'
    elif next_val < curr_val:
        return 'lower'
    else:
        return 'tie'

def calculate_multiplier(streak):
    """Calculate payout multiplier based on streak."""
    if streak <= 0:
        return 1.0
    # Each correct guess increases multiplier
    return 1.0 + (streak * 0.5)

def play_round(bet):
    """Play a round. Returns winnings."""
    deck = create_deck()
    current = deck.pop()
    streak = 0
    winnings = bet
    
    print("\n" + "=" * 50)
    print("       HIGHER OR LOWER")
    print("=" * 50)
    
    while True:
        multiplier = calculate_multiplier(streak)
        potential = int(bet * multiplier)
        
        print(f"\nStreak: {streak}  |  Multiplier: {multiplier:.1f}x  |  Value: ${potential}")
        show_cards(current)
        
        print(f"\nCurrent card: {current[0]}{current[1]}")
        print(f"\n[H] Higher  [L] Lower  [C] Cash out (${potential})")
        
        choice = input("> ").strip().upper()
        
        if choice == 'C':
            print(f"\nYou cash out with ${potential}!")
            return potential
        elif choice not in ['H', 'L']:
            print("Please enter H, L, or C")
            continue
        
        # Draw next card
        next_card = deck.pop()
        result = compare_cards(current, next_card)
        
        show_cards(current, next_card, reveal=True)
        print(f"\nNext card: {next_card[0]}{next_card[1]}")
        
        # Check result
        if result == 'tie':
            print("\n*** TIE! You keep your streak. ***")
        elif (choice == 'H' and result == 'higher') or (choice == 'L' and result == 'lower'):
            streak += 1
            new_mult = calculate_multiplier(streak)
            print(f"\n*** CORRECT! Streak: {streak}  Multiplier: {new_mult:.1f}x ***")
        else:
            print(f"\n*** WRONG! The card was {result}. ***")
            print("You lose everything!")
            return 0
        
        # Check if deck is running low
        if len(deck) < 5:
            print("\nDeck running low - shuffling new deck...")
            deck = create_deck()
        
        # Next card becomes current
        current = next_card

def main():
    """Main game loop."""
    money = 1000
    cost_to_play = 100
    win_bonus = 200
    
    print("\n" + "#" * 50)
    print("#" + " " * 48 + "#")
    print("#         HIGHER OR LOWER                    #")
    print("#" + " " * 48 + "#")
    print("#" * 50)
    
    print(f"\nRules:")
    print(f"  - Bet: ${cost_to_play}")
    print(f"  - Win bonus: +${win_bonus}")
    print(f"  - Starting money: ${money}")
    print(f"\nHow to play:")
    print("  - Guess if the next card is Higher or Lower")
    print("  - Each correct guess increases your multiplier")
    print("  - Cash out anytime to keep your winnings")
    print("  - Wrong guess = lose everything!")
    print(f"\nMultipliers: 1x -> 1.5x -> 2x -> 2.5x -> 3x ...")
    
    while True:
        print(f"\n{'=' * 50}")
        print(f"Your money: ${money}")
        print(f"{'=' * 50}")
        
        if money < cost_to_play:
            print("\nNot enough money to play!")
            print("GAME OVER - Thanks for playing!")
            break
        
        print(f"\n[P] Play (bet ${cost_to_play})")
        print("[Q] Quit")
        
        choice = input("\n> ").strip().upper()
        
        if choice == 'Q':
            print(f"\nYou leave with ${money}. Thanks for playing!")
            break
        elif choice == 'P':
            money -= cost_to_play
            print(f"\nBet ${cost_to_play}. Remaining: ${money}")
            
            winnings = play_round(cost_to_play)
            
            if winnings > cost_to_play:
                total = winnings + win_bonus
                money += total
                print(f"\nPayout: ${winnings} + ${win_bonus} bonus = ${total}")
                print(f"New balance: ${money}")
            elif winnings == cost_to_play:
                # Cashed out at 1x
                money += winnings
                print(f"\nBalance: ${money}")
            else:
                print(f"\nYou lost. Balance: ${money}")
        else:
            print("Enter P or Q.")

if __name__ == "__main__":
    main()
