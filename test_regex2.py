import re

# 测试文本（从数据库中提取的实际文本）
test_texts = [
    'George likes to jumping muddy puddles too.',
    'will you and Mummy come and play, too?',
    'George wants to play, too.',
]

print("测试不同的正则表达式模式:\n")
print("=" * 80)

patterns = [
    ('too$', '以 too 结尾（不匹配标点）'),
    (r'too\.$', '以 too. 结尾'),
    (r'too[.?!]$', '以 too 加标点结尾'),
    (r'too[.?!]?$', '以 too 结尾（标点可选）'),
    (r'\btoo\b', '单词边界匹配 too'),
    (r'too\W*$', '以 too 结尾（后面可有非单词字符）'),
]

for text in test_texts:
    print(f"\n文本: {repr(text)}")
    print("-" * 80)
    for pattern, description in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        result = "[YES]" if match else "[NO] "
        print(f"  {result}  {pattern:20s} - {description}")

print("\n" + "=" * 80)
print("\n结论:")
print("  - 'too$' 不匹配是因为句子以标点符号结尾，不是单词 'too'")
print("  - 建议使用 'too\\W*$' 或 'too[.?!]?$' 来匹配以 too 结尾的句子")
print("  - 或使用 '\\btoo\\b' 来匹配单词 too（不限位置）")
