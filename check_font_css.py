with open('static/css/font-awesome.min.css', 'r', encoding='utf-8') as f:
    content = f.read()
    
# 搜索字体相关的内容
font_related = []
lines = content.split('\n')
for i, line in enumerate(lines):
    if 'font' in line.lower() or 'src' in line.lower():
        font_related.append(f"Line {i+1}: {line[:100]}...")

print(f"Found {len(font_related)} font-related lines:")
for line in font_related[:20]:  # 只显示前20行
    print(line)
