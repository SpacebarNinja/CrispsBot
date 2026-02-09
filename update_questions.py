"""Script to update config.py with new question banks"""

# Read the new questions from questions_v163.py
exec(open('questions_v163.py', 'r', encoding='utf-8').read())

# Read current config
with open('config.py', 'r', encoding='utf-8') as f:
    config = f.read()

# Replace FRIEND_GROUP_QUESTIONS with STRUCTURAL_QUESTIONS
friend_start = config.find('FRIEND_GROUP_QUESTIONS = [')
friend_end = config.find(']', config.find('# ==================== SPARK — WOULD YOU RATHER ====================') - 10) + 1

wyr_start = config.find('SPARK_WYR = [')
wyr_end = config.find(']', config.find('# ==================== SPARK — DEBATES ====================') - 10) + 1

debates_start = config.find('SPARK_DEBATES = [')
debates_end = config.find(']', config.find('# ==================== BUTTON QUESTIONS ====================') - 10) + 1

buttons_start = config.find('BUTTON_QUESTIONS = [')
buttons_end = config.find(']', config.find('# ==================== SPARK — CHILL ====================') - 10) + 1

# Build new config
new_config = config[:friend_start]
new_config += 'FRIEND_GROUP_QUESTIONS = [\n    # REPLACED WITH STRUCTURAL SYSTEM-THINKING QUESTIONS\n'
for q in STRUCTURAL_QUESTIONS_NEW:
    new_config += f'    "{q}",\n'
new_config += config[friend_end:]

# Update WYR
config = new_config
wyr_start = config.find('SPARK_WYR = [')
wyr_end = config.find(']', config.find('# ==================== SPARK — DEBATES ====================') - 10) + 1
new_config = config[:wyr_start]
new_config += 'SPARK_WYR = [\n'
for q in SPARK_WYR_NEW:
    new_config += f'    "{q}",\n'
new_config += config[wyr_end:]

# Update DEBATES
config = new_config
debates_start = config.find('SPARK_DEBATES = [')
debates_end = config.find(']', config.find('# ==================== BUTTON QUESTIONS ====================') - 10) + 1
new_config = config[:debates_start]
new_config += 'SPARK_DEBATES = [\n'
for q in SPARK_DEBATES_NEW:
    new_config += f'    "{q}",\n'
new_config += config[debates_end:]

# Update BUTTONS  
config = new_config
buttons_start = config.find('BUTTON_QUESTIONS = [')
buttons_end = config.find(']', config.find('# ==================== SPARK — CHILL ====================') - 10) + 1
new_config = config[:buttons_start]
new_config += 'BUTTON_QUESTIONS = [\n'
for q in BUTTON_QUESTIONS_NEW:
    new_config += f'    "{q}",\n'
new_config += config[buttons_end:]

# Write updated config
with open('config.py', 'w', encoding='utf-8') as f:
    f.write(new_config)

# Count questions
print(f"✓ FRIEND_GROUP_QUESTIONS → STRUCTURAL: {len(STRUCTURAL_QUESTIONS_NEW)} questions")
print(f"✓ SPARK_WYR: {len(SPARK_WYR_NEW)} questions")
print(f"✓ SPARK_DEBATES: {len(SPARK_DEBATES_NEW)} questions")
print(f"✓ BUTTON_QUESTIONS: {len(BUTTON_QUESTIONS_NEW)} questions")
print(f"✓ Total: {len(STRUCTURAL_QUESTIONS_NEW) + len(SPARK_WYR_NEW) + len(SPARK_DEBATES_NEW) + len(BUTTON_QUESTIONS_NEW)} questions")
print("\n✓ config.py updated successfully!")
