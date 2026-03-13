import random

# Card suits and ranks
SUITS = ['♥', '♦', '♣', '♠']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
RANK_VALUES = {r: i for i, r in enumerate(RANKS)}

# Payouts (multiplier of bet)
PAYOUTS = {
    'Royal Flush': 250,
    'Straight Flush': 50,
    'Four of a Kind': 25,
    'Full House': 9,
    'Flush': 6,
    'Straight': 4,
    'Three of a Kind': 3,
    'Two Pair': 2,
    'Jacks or Better': 1,
}

def create_deck():
    """Create a standard 52-card deck."""
    return [(rank, suit) for suit in SUITS for rank in RANKS]

def display_hand(hand, held=None):
    """Display the hand with card numbers."""
    print("\n" + "+-------" * 5 + "+")
    
    # Top of cards
    line = "|"
    for i, (rank, suit) in enumerate(hand):
        r = rank if len(rank) == 2 else rank + " "
        line += f" {r}    |"
    print(line)
    
    # Middle of cards (suit)
    line = "|"
    for rank, suit in hand:
        line += f"   {suit}   |"
    print(line)
    
    # Bottom of cards
    line = "|"
    for rank, suit in hand:
        r = rank if len(rank) == 2 else " " + rank
        line += f"    {r} |"
    print(line)
    
    print("+-------" * 5 + "+")
    
    # Card numbers
    print("    1       2       3       4       5")
    
    # Hold indicators
    if held:
        holds = "   "
        for i in range(5):
            if i in held:
                holds += " HOLD   "
            else:
                holds += "        "
        print(holds)

def get_hand_rank(hand):
    """Evaluate the poker hand and return its rank name."""
    ranks = [card[0] for card in hand]
    suits = [card[1] for card in hand]
    
    # Get rank counts
    rank_counts = {}
    for r in ranks:
        rank_counts[r] = rank_counts.get(r, 0) + 1
    
    counts = sorted(rank_counts.values(), reverse=True)
    
    # Check for flush
    is_flush = len(set(suits)) == 1
    
    # Check for straight
    rank_indices = sorted([RANK_VALUES[r] for r in ranks])
    is_straight = False
    if rank_indices == list(range(rank_indices[0], rank_indices[0] + 5)):
        is_straight = True
    # Special case: A-2-3-4-5 (wheel)
    if rank_indices == [0, 1, 2, 3, 12]:  # 2,3,4,5,A
        is_straight = True
    
    # Check for royal flush
    if is_flush and is_straight and set(ranks) == {'10', 'J', 'Q', 'K', 'A'}:
        return 'Royal Flush'
    
    # Straight flush
    if is_flush and is_straight:
        return 'Straight Flush'
    
    # Four of a kind
    if counts == [4, 1]:
        return 'Four of a Kind'
    
    # Full house
    if counts == [3, 2]:
        return 'Full House'
    
    # Flush
    if is_flush:
        return 'Flush'
    
    # Straight
    if is_straight:
        return 'Straight'
    
    # Three of a kind
    if counts == [3, 1, 1]:
        return 'Three of a Kind'
    
    # Two pair
    if counts == [2, 2, 1]:
        return 'Two Pair'
    
    # Jacks or better (pair of J, Q, K, or A)
    if counts == [2, 1, 1, 1]:
        for rank, count in rank_counts.items():
            if count == 2 and rank in ['J', 'Q', 'K', 'A']:
                return 'Jacks or Better'
    
    return None

def display_paytable():
    """Display the payout table."""
    print("\n┌─────────────────────────────┐")
    print("│       PAYOUT TABLE          │")
    print("├─────────────────────────────┤")
    for hand, payout in PAYOUTS.items():
        print(f"│ {hand:<18} {payout:>5}x   │")
    print("└─────────────────────────────┘")

def play_round(bet):
    """Play a single round of video poker. Returns winnings."""
    deck = create_deck()
    random.shuffle(deck)
    
    # Deal 5 cards
    hand = [deck.pop() for _ in range(5)]
    
    print("\n" + "=" * 50)
    print("       VIDEO POKER - DEAL")
    print("=" * 50)
    
    display_hand(hand)
    
    # Get cards to hold
    print("\nEnter card numbers to HOLD (e.g., '1 3 5' or '135')")
    print("Press ENTER to hold none, or 'all' to hold all:")
    
    while True:
        choice = input("> ").strip().lower()
        
        if choice == '':
            held = set()
            break
        elif choice == 'all':
            held = {0, 1, 2, 3, 4}
            break
        else:
            # Parse numbers
            try:
                # Handle both "1 3 5" and "135" formats
                if ' ' in choice:
                    nums = [int(x) for x in choice.split()]
                else:
                    nums = [int(x) for x in choice]
                
                held = set()
                valid = True
                for n in nums:
                    if 1 <= n <= 5:
                        held.add(n - 1)  # Convert to 0-indexed
                    else:
                        print("Please enter numbers 1-5 only")
                        valid = False
                        break
                
                if valid:
                    break
            except ValueError:
                print("Please enter valid card numbers (1-5)")
    
    # Draw new cards
    print("\n" + "=" * 50)
    print("       VIDEO POKER - DRAW")
    print("=" * 50)
    
    for i in range(5):
        if i not in held:
            hand[i] = deck.pop()
    
    display_hand(hand, held)
    
    # Evaluate hand
    result = get_hand_rank(hand)
    
    if result:
        payout = PAYOUTS[result]
        winnings = bet * payout
        print(f"\n*** {result.upper()}! ***")
        print(f"You win ${winnings}!")
        return winnings
    else:
        print("\nNo winning hand. Better luck next time!")
        return 0

def main():
    """Main game loop."""
    money = 1000
    cost_to_play = 100
    win_bonus = 200  # Extra bonus on top of payout
    
    print("\n" + "#" * 50)
    print("#" + " " * 48 + "#")
    print("#          WELCOME TO VIDEO POKER!           #")
    print("#" + " " * 48 + "#")
    print("#" * 50)
    
    display_paytable()
    
    print(f"\nRules:")
    print(f"  - Bet per hand: ${cost_to_play}")
    print(f"  - Win bonus: +${win_bonus} on any winning hand")
    print(f"  - Starting money: ${money}")
    
    while True:
        print(f"\n{'=' * 50}")
        print(f"Your money: ${money}")
        print(f"{'=' * 50}")
        
        if money < cost_to_play:
            print("\nYou don't have enough money to play!")
            print("GAME OVER - Thanks for playing!")
            break
        
        print(f"\n[P] Play (bet ${cost_to_play})")
        print("[T] View payout table")
        print("[Q] Quit")
        
        choice = input("\nWhat would you like to do? ").strip().upper()
        
        if choice == 'Q':
            print(f"\nYou leave with ${money}. Thanks for playing!")
            break
        elif choice == 'T':
            display_paytable()
        elif choice == 'P':
            money -= cost_to_play
            print(f"\nBet ${cost_to_play}. Remaining: ${money}")
            
            winnings = play_round(cost_to_play)
            
            if winnings > 0:
                total_win = winnings + win_bonus
                money += total_win
                print(f"Payout: ${winnings} + ${win_bonus} bonus = ${total_win}")
                print(f"New balance: ${money}")
        else:
            print("Invalid choice. Please enter P, T, or Q.")

if __name__ == "__main__":
    main()
