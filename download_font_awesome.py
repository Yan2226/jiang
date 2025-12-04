import requests
import os

# 创建必要的目录
css_dir = 'static/css'
fonts_dir = 'static/fonts'
os.makedirs(css_dir, exist_ok=True)
os.makedirs(fonts_dir, exist_ok=True)

# 下载CSS文件
css_url = 'https://cdn.jsdelivr.net/npm/font-awesome@4.7.0/css/font-awesome.min.css'
response = requests.get(css_url)
if response.status_code == 200:
    with open(os.path.join(css_dir, 'font-awesome.min.css'), 'wb') as f:
        f.write(response.content)
    print('CSS file downloaded successfully.')
else:
    print(f'Failed to download CSS file. Status code: {response.status_code}')

# 下载字体文件
font_files = [
    'fontawesome-webfont.eot',
    'fontawesome-webfont.woff2',
    'fontawesome-webfont.woff',
    'fontawesome-webfont.ttf',
    'fontawesome-webfont.svg'
]

for font_file in font_files:
    font_url = f'https://cdn.jsdelivr.net/npm/font-awesome@4.7.0/fonts/{font_file}'
    response = requests.get(font_url)
    if response.status_code == 200:
        with open(os.path.join(fonts_dir, font_file), 'wb') as f:
            f.write(response.content)
        print(f'Font file {font_file} downloaded successfully.')
    else:
        print(f'Failed to download font file {font_file}. Status code: {response.status_code}')

print('All files downloaded.')
