import random

# Card suits and ranks
SUITS = ['♥', '♦', '♣', '♠']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']

def create_deck(num_decks=1):
    """Create a shuffled deck."""
    deck = [(rank, suit) for suit in SUITS for rank in RANKS] * num_decks
    random.shuffle(deck)
    return deck

def card_value(card):
    """Get the value of a card (Ace returns 11, handled separately)."""
    rank = card[0]
    if rank in ['J', 'Q', 'K']:
        return 10
    elif rank == 'A':
        return 11
    else:
        return int(rank)

def hand_value(hand):
    """Calculate the best value of a hand (adjusting for Aces)."""
    total = sum(card_value(card) for card in hand)
    aces = sum(1 for card in hand if card[0] == 'A')
    
    # Reduce Aces from 11 to 1 if needed
    while total > 21 and aces > 0:
        total -= 10
        aces -= 1
    
    return total

def display_card(card):
    """Return a string representation of a card."""
    rank, suit = card
    return f"[{rank}{suit}]"

def display_hand(hand, name, hide_first=False):
    """Display a hand of cards."""
    if hide_first:
        cards = "[??] " + " ".join(display_card(c) for c in hand[1:])
        print(f"{name}: {cards}")
    else:
        cards = " ".join(display_card(c) for c in hand)
        value = hand_value(hand)
        print(f"{name}: {cards} = {value}")

def display_table(player_hand, dealer_hand, hide_dealer=True):
    """Display the game table."""
    print("\n" + "-" * 40)
    display_hand(dealer_hand, "Dealer", hide_first=hide_dealer)
    print("-" * 40)
    display_hand(player_hand, "You   ")
    print("-" * 40)

def play_round(bet):
    """Play a single round of blackjack. Returns winnings."""
    deck = create_deck(2)  # Use 2 decks
    
    # Deal initial cards
    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]
    
    print("\n" + "=" * 50)
    print("       BLACKJACK - DEAL")
    print("=" * 50)
    
    # Check for blackjack
    player_bj = hand_value(player_hand) == 21
    dealer_bj = hand_value(dealer_hand) == 21
    
    if player_bj or dealer_bj:
        display_table(player_hand, dealer_hand, hide_dealer=False)
        
        if player_bj and dealer_bj:
            print("\nBoth have Blackjack! Push.")
            return bet  # Return the bet
        elif player_bj:
            print("\n*** BLACKJACK! ***")
            return int(bet * 2.5)  # 3:2 payout
        else:
            print("\nDealer has Blackjack. You lose.")
            return 0
    
    # Player's turn
    while True:
        display_table(player_hand, dealer_hand, hide_dealer=True)
        
        player_value = hand_value(player_hand)
        
        if player_value > 21:
            print("\nBUST! You went over 21.")
            return 0
        
        if player_value == 21:
            print("\n21! Standing automatically.")
            break
        
        # Show options
        options = "[H] Hit  [S] Stand"
        if len(player_hand) == 2:
            options += "  [D] Double Down"
        
        print(f"\n{options}")
        choice = input("Your choice: ").strip().upper()
        
        if choice == 'H':
            player_hand.append(deck.pop())
            print(f"\nYou draw: {display_card(player_hand[-1])}")
        elif choice == 'S':
            break
        elif choice == 'D' and len(player_hand) == 2:
            player_hand.append(deck.pop())
            print(f"\nDouble Down! You draw: {display_card(player_hand[-1])}")
            bet *= 2
            
            if hand_value(player_hand) > 21:
                display_table(player_hand, dealer_hand, hide_dealer=False)
                print("\nBUST! You went over 21.")
                return 0
            break
        else:
            print("Invalid choice.")
    
    # Dealer's turn
    print("\n" + "=" * 50)
    print("       DEALER'S TURN")
    print("=" * 50)
    
    display_table(player_hand, dealer_hand, hide_dealer=False)
    
    while hand_value(dealer_hand) < 17:
        dealer_hand.append(deck.pop())
        print(f"\nDealer draws: {display_card(dealer_hand[-1])}")
        display_table(player_hand, dealer_hand, hide_dealer=False)
    
    player_value = hand_value(player_hand)
    dealer_value = hand_value(dealer_hand)
    
    # Determine winner
    print("\n" + "=" * 50)
    
    if dealer_value > 21:
        print("Dealer BUSTS! You win!")
        return bet * 2
    elif player_value > dealer_value:
        print(f"You win! {player_value} beats {dealer_value}")
        return bet * 2
    elif dealer_value > player_value:
        print(f"Dealer wins. {dealer_value} beats {player_value}")
        return 0
    else:
        print(f"Push! Both have {player_value}")
        return bet  # Return the bet

def main():
    """Main game loop."""
    money = 1000
    cost_to_play = 100
    win_bonus = 200
    
    print("\n" + "#" * 50)
    print("#" + " " * 48 + "#")
    print("#            WELCOME TO BLACKJACK!            #")
    print("#" + " " * 48 + "#")
    print("#" * 50)
    
    print(f"\nRules:")
    print(f"  - Bet per hand: ${cost_to_play}")
    print(f"  - Win bonus: +${win_bonus} on any win")
    print(f"  - Starting money: ${money}")
    print(f"  - Blackjack pays 3:2")
    print(f"  - Dealer stands on 17")
    print(f"  - Double down available on first two cards")
    
    while True:
        print(f"\n{'=' * 50}")
        print(f"Your money: ${money}")
        print(f"{'=' * 50}")
        
        if money < cost_to_play:
            print("\nYou don't have enough money to play!")
            print("GAME OVER - Thanks for playing!")
            break
        
        print(f"\n[P] Play (bet ${cost_to_play})")
        print("[Q] Quit")
        
        choice = input("\nWhat would you like to do? ").strip().upper()
        
        if choice == 'Q':
            print(f"\nYou leave with ${money}. Thanks for playing!")
            break
        elif choice == 'P':
            money -= cost_to_play
            print(f"\nBet ${cost_to_play}. Remaining: ${money}")
            
            winnings = play_round(cost_to_play)
            
            if winnings > cost_to_play:
                # Won the hand
                total_win = winnings + win_bonus
                money += total_win
                print(f"\nPayout: ${winnings} + ${win_bonus} bonus = ${total_win}")
                print(f"New balance: ${money}")
            elif winnings == cost_to_play:
                # Push - return bet only
                money += winnings
                print(f"\nBet returned. Balance: ${money}")
            else:
                # Lost
                print(f"\nYou lost. Balance: ${money}")
        else:
            print("Invalid choice. Please enter P or Q.")

if __name__ == "__main__":
    main()
