import re

# Read the new questions
with open('questions_v164.py', 'r', encoding='utf-8') as f:
    content = f.read()
    
    # Extract all four question lists
    friend_match = re.search(r'FRIEND_GROUP_QUESTIONS_V164 = \[(.*?)\]', content, re.DOTALL)
    debates_match = re.search(r'SPARK_DEBATES_V164 = \[(.*?)\]', content, re.DOTALL)
    wyr_match = re.search(r'SPARK_WYR_V164 = \[(.*?)\]', content, re.DOTALL)
    button_match = re.search(r'BUTTON_QUESTIONS_V164 = \[(.*?)\]', content, re.DOTALL)

# Read config.py
with open('config.py', 'r', encoding='utf-8') as f:
    config_content = f.read()

# Replace FRIEND_GROUP_QUESTIONS (fix to correct "Who is most likely..." format)
if friend_match:
    new_friend = 'FRIEND_GROUP_QUESTIONS = [' + friend_match.group(1) + ']'
    config_content = re.sub(
        r'FRIEND_GROUP_QUESTIONS = \[.*?\](?=\s*(?:SPARK_WYR|SPARK_DEBATES|BUTTON_QUESTIONS|\Z))',
        new_friend,
        config_content,
        flags=re.DOTALL
    )

# Replace SPARK_WYR (casual would-you-rather with real tradeoffs)
if wyr_match:
    new_wyr = 'SPARK_WYR = [' + wyr_match.group(1) + ']'
    config_content = re.sub(
        r'SPARK_WYR = \[.*?\](?=\s*(?:SPARK_DEBATES|BUTTON_QUESTIONS|FRIEND_GROUP_QUESTIONS|\Z))',
        new_wyr,
        config_content,
        flags=re.DOTALL
    )

# Replace SPARK_DEBATES (casual debate questions about life/relationships)
if debates_match:
    new_debates = 'SPARK_DEBATES = [' + debates_match.group(1) + ']'
    config_content = re.sub(
        r'SPARK_DEBATES = \[.*?\](?=\s*(?:BUTTON_QUESTIONS|FRIEND_GROUP_QUESTIONS|SPARK_WYR|\Z))',
        new_debates,
        config_content,
        flags=re.DOTALL
    )

# Replace BUTTON_QUESTIONS (high-stakes button dilemmas with clear costs)
if button_match:
    new_button = 'BUTTON_QUESTIONS = [' + button_match.group(1) + ']'
    config_content = re.sub(
        r'BUTTON_QUESTIONS = \[.*?\](?=\s*(?:FRIEND_GROUP_QUESTIONS|SPARK_WYR|SPARK_DEBATES|\Z))',
        new_button,
        config_content,
        flags=re.DOTALL
    )

# Write back to config.py
with open('config.py', 'w', encoding='utf-8') as f:
    f.write(config_content)

print("✅ v1.64 questions deployed!")
print("\nQuestion Statistics:")
quote = '"'
print(f"  FRIEND_GROUP: {len(friend_match.group(1).split(quote)) // 2} questions (Who is most likely... format)")
print(f"  SPARK_DEBATES: {len(debates_match.group(1).split(quote)) // 2} questions (casual social debates)")
print(f"  SPARK_WYR: {len(wyr_match.group(1).split(quote)) // 2} questions (accessible tradeoffs)")
print(f"  BUTTON_QUESTIONS: {len(button_match.group(1).split(quote)) // 2} questions (high-stakes costs)")
print("\n✨ All questions updated with casual, friend-group-appropriate tone!")
print("🔥 Sharp dilemmas that spark debate without technical jargon!")
