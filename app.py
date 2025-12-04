from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
from models import db, User, ChatMessage, UserActivity
import json
import re
import random
import urllib.parse
import requests
import time
import os
from werkzeug.utils import secure_filename
from datetime import datetime

# 设置文件上传目录
UPLOAD_FOLDER = 'static/uploads/avatars'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# 确保上传目录存在
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 和风天气API配置
WEATHER_API_KEY = '922f00828e4241f3b02bf4efe5e9c9d9'  
WEATHER_API_URL = 'https://nj4jaay6vr.re.qweatherapi.com/v7/weather/now'
WEATHER_CITY_LOOKUP_URL = 'https://nj4jaay6vr.re.qweatherapi.com/v7/city/lookup'  # 修正城市查询接口URL

# 常用城市ID映射表（作为备选方案）
COMMON_CITY_IDS = {
    '北京': '101010100',
    '上海': '101020100',
    '广州': '101280101',
    '深圳': '101280601',
    '成都': '101270101',
    '杭州': '101210101',
    '武汉': '101200101',
    '西安': '101110101',
    '重庆': '101040100',
    '南京': '101190101',
    '雅安': '101271701',
    '遂宁': '101270701'
}

# 新闻API配置（使用GNews API）
NEWS_API_KEY = 'dc6ebae407736824409fc7ba82af28b2'  
NEWS_API_URL = 'https://gnews.io/api/v4/search'

# 音乐API配置（网易云音乐）
MUSIC_API_BASE_URL = 'https://netease-cloud-music-api-alpha.vercel.app'
MUSIC_SEARCH_ENDPOINT = '/search'
MUSIC_DETAIL_ENDPOINT = '/song/url'
MUSIC_LYRICS_ENDPOINT = '/lyric'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'  # SQLite数据库
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

CORS(app)  # 添加CORS支持

# 初始化数据库
db.init_app(app)

# 创建数据库表
with app.app_context():
    db.create_all()

socketio = SocketIO(app, cors_allowed_origins="*")

# 存储在线用户信息 (sid -> user_id)
users = {}
# 存储服务器配置
servers_config = {
    "servers": [
        {"name": "默认服务器", "url": "http://localhost:9000"}
    ]
}

# 保存配置到文件
def save_config():
    with open('config.json', 'w', encoding='utf-8') as f:
        json.dump(servers_config, f, ensure_ascii=False, indent=2)

# 加载配置文件
try:
    with open('config.json', 'r', encoding='utf-8') as f:
        servers_config = json.load(f)
except FileNotFoundError:
    # 如果配置文件不存在，创建默认配置
    save_config()

# 记录用户活动
def log_user_activity(user_id, activity_type, activity_data=None):
    """记录用户活动"""
    try:
        activity = UserActivity(
            user_id=user_id,
            activity_type=activity_type,
            activity_data=json.dumps(activity_data) if activity_data else None
        )
        db.session.add(activity)
        db.session.commit()
    except Exception as e:
        print(f"记录用户活动失败: {e}")
        db.session.rollback()

def generate_ai_response(question):
    """调用WebAI接口生成AI对话响应"""
    if not question:
        return "您好！我是AI助手川小农，请问有什么可以帮助您的吗？"
    
    # 尝试调用WebAI接口（免费的AI对话接口）
    try:
        # WebAI接口调用
        url = "https://api.webai.ai/v1/chat/completions"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "model": "gpt-3.5-turbo",  # 使用兼容的模型名称
            "messages": [
                {"role": "system", "content": "你是AI助手川小农，一个友好、专业的中文助手。请用简洁、清晰的语言回答用户问题。"},
                {"role": "user", "content": question}
            ],
            "max_tokens": 500,
            "temperature": 0.7
        }
        
        # 添加超时处理
        response = requests.post(url, headers=headers, json=data, timeout=10)
        
        # 检查响应状态
        if response.status_code == 200:
            result = response.json()
            if 'choices' in result and result['choices']:
                return result['choices'][0]['message']['content']
            else:
                # 如果接口返回格式不正确，返回友好提示
                return "抱歉，我暂时无法获取准确的回复。请稍后再试。"
        elif response.status_code == 429:
            # 处理请求过多的情况
            return "服务器繁忙，请稍后再试。"
        else:
            # 其他错误情况
            return "抱歉，AI服务暂时不可用。请稍后再试。"
    
    except requests.RequestException as e:
        # 处理网络错误、超时等异常
        print(f"AI接口调用失败: {e}")
        
        # 备用：使用本地模拟回复作为fallback
        return generate_fallback_response(question)

def get_weather_by_city(city_name):
    """根据城市名获取天气信息"""
    try:
        location_id = None
        city_data = None
        
        # 1. 先尝试从常用城市ID映射表获取
        if city_name in COMMON_CITY_IDS:
            location_id = COMMON_CITY_IDS[city_name]
            # 构造city_data以便后续使用
            city_data = {
                'location': [{'name': city_name, 'id': location_id}]
            }
        else:
            # 2. 尝试调用城市查询API获取location ID
            city_params = {
                'key': WEATHER_API_KEY,
                'location': city_name
            }
            try:
                city_response = requests.get(WEATHER_CITY_LOOKUP_URL, params=city_params, timeout=5)
                
                # 检查响应是否为空
                if not city_response.text:
                    return None, "城市查询服务无响应"
                    
                try:
                    city_data = city_response.json()
                except json.JSONDecodeError:
                    return None, "城市查询服务异常"
                
                if city_data.get('code') != '200' or not city_data.get('location'):
                    return None, f"无法找到城市'{city_name}'的信息"
                
                location_id = city_data['location'][0]['id']
            except requests.exceptions.RequestException:
                return None, "城市查询服务不可用"
        
        if not location_id:
            return None, f"无法找到城市'{city_name}'的信息"
        
        # 2. 使用location ID查询天气
        weather_params = {
            'key': WEATHER_API_KEY,
            'location': location_id
        }
        weather_response = requests.get(WEATHER_API_URL, params=weather_params, timeout=5)
        
        # 检查响应是否为空
        if not weather_response.text:
            return None, "天气查询服务无响应"
            
        try:
            weather_data = weather_response.json()
        except json.JSONDecodeError:
            print(f"天气查询返回非JSON数据: {weather_response.text}")
            return None, "天气查询服务异常"
        
        if weather_data.get('code') != '200':
            return None, "获取天气信息失败"
        
        # 3. 解析天气数据
        weather_info = {
            'city': city_data['location'][0]['name'],
            'temp': weather_data['now']['temp'],
            'feels_like': weather_data['now']['feelsLike'],
            'weather': weather_data['now']['text'],
            'wind_dir': weather_data['now']['windDir'],
            'wind_scale': weather_data['now']['windScale'],
            'humidity': weather_data['now']['humidity'],
            'pressure': weather_data['now']['pressure'],
            'update_time': weather_data['updateTime']
        }
        
        return weather_info, None
    except requests.exceptions.Timeout:
        print("天气查询超时")
        return None, "天气查询超时，请稍后重试"
    except requests.exceptions.RequestException as e:
        print(f"天气查询网络错误: {e}")
        return None, "网络连接失败，请检查网络设置"
    except Exception as e:
        print(f"天气查询失败: {e}")
        return None, "天气服务暂时不可用"

def generate_weather_tips(weather_info):
    """根据天气信息生成提示"""
    temp = int(weather_info['temp'])
    weather = weather_info['weather']
    
    # 根据温度提供穿衣建议
    if temp >= 30:
        clothing = "天气炎热，建议穿着轻薄、透气的衣物，如棉麻面料的短袖短裤"
    elif temp >= 25:
        clothing = "天气温暖，建议穿着短袖、薄长裤等舒适的衣物"
    elif temp >= 20:
        clothing = "天气适中，建议穿着长袖衬衫、薄外套等"
    elif temp >= 15:
        clothing = "天气微凉，建议穿着毛衣、夹克等保暖衣物"
    elif temp >= 10:
        clothing = "天气较冷，建议穿着厚外套、保暖内衣等"
    else:
        clothing = "天气寒冷，建议穿着羽绒服、厚毛衣等厚实保暖的衣物"
    
    # 根据天气状况提供额外建议
    additional_tips = []
    if '雨' in weather:
        additional_tips.append("别忘了带伞，出行注意安全")
    elif '雪' in weather:
        additional_tips.append("路面可能湿滑，注意安全，建议穿防滑鞋")
    elif '晴' in weather:
        additional_tips.append("天气晴朗，适合外出活动，但注意防晒")
    elif '阴' in weather:
        additional_tips.append("天气阴沉，适合室内活动")
    elif '雾' in weather or '霾' in weather:
        additional_tips.append("空气质量不佳，建议减少户外活动，外出佩戴口罩")
    
    # 整合提示信息
    tips = f"穿衣建议：{clothing}"
    if additional_tips:
        tips += "\n" + "，".join(additional_tips)
    
    return tips

def get_news_by_keyword(keyword, language='zh', max_results=10):
    """根据关键词获取新闻信息"""
    try:
        # 构建请求参数
        params = {
                'q': keyword,
                'lang': language,
                'max': max_results,
                'apikey': NEWS_API_KEY
            }
        
        # 发送请求
        response = requests.get(NEWS_API_URL, params=params, timeout=5)
        
        # 检查响应是否为空
        if not response.text:
            return None, "新闻查询服务无响应"
            
        # 尝试解析JSON数据
        try:
            response_data = response.json()
        except json.JSONDecodeError:
            print(f"新闻查询返回非JSON数据: {response.text}")
            return None, "新闻查询服务异常"
        
        # 检查是否成功获取数据
        if response.status_code != 200 or 'articles' not in response_data:
            return None, f"获取新闻失败: {response_data.get('error', '未知错误')}"
        
        # 解析新闻数据
        news_list = []
        for article in response_data['articles']:
            news_item = {
                'title': article.get('title', ''),
                'description': article.get('description', ''),
                'url': article.get('url', ''),
                'publishedAt': article.get('publishedAt', ''),
                'source': article.get('source', {}).get('name', '')
            }
            news_list.append(news_item)
        
        return news_list, None
    except requests.exceptions.Timeout:
        print("新闻查询超时")
        return None, "新闻查询超时，请稍后重试"
    except requests.exceptions.RequestException as e:
        print(f"新闻查询网络错误: {e}")
        return None, "网络连接失败，请检查网络设置"
    except Exception as e:
        print(f"新闻查询失败: {e}")
        return None, "新闻服务暂时不可用"

def search_music(keyword):
    """根据关键词搜索音乐"""
    try:
        # 构建请求URL
        search_url = f"{MUSIC_API_BASE_URL}{MUSIC_SEARCH_ENDPOINT}"
        params = {
            'keywords': keyword,
            'limit': 10  # 最多返回10首歌曲
        }
        
        # 发送API请求
        response = requests.get(search_url, params=params, timeout=10)
        
        # 检查响应状态
        if response.status_code != 200:
            print(f"音乐搜索API返回错误状态码: {response.status_code}")
            # 尝试返回模拟数据
            return generate_mock_music_list(keyword), f"当前音乐API不可用，显示模拟数据"
        
        # 检查响应是否为空
        if not response.text:
            print("音乐搜索服务无响应")
            # 尝试返回模拟数据
            return generate_mock_music_list(keyword), "当前音乐API无响应，显示模拟数据"
            
        # 解析响应数据
        try:
            data = response.json()
        except json.JSONDecodeError:
            print(f"音乐搜索返回非JSON数据: {response.text}")
            # 尝试返回模拟数据
            return generate_mock_music_list(keyword), "当前音乐API返回无效数据，显示模拟数据"
        
        # 提取音乐列表
        songs = data.get('result', {}).get('songs', [])
        
        # 处理音乐数据
        music_list = []
        for song in songs:
            # 获取歌手信息
            artists = []
            for artist in song.get('artists', []):
                artists.append(artist.get('name', '未知歌手'))
            
            music = {
                'id': song.get('id', ''),
                'name': song.get('name', '未命名歌曲'),
                'artists': artists,
                'artist_names': '、'.join(artists),
                'album': song.get('album', {}).get('name', '未知专辑'),
                'duration': song.get('duration', 0) // 1000  # 转换为秒
            }
            music_list.append(music)
        
        return music_list, None
    
    except requests.exceptions.RequestException as e:
        print(f"请求音乐搜索API时出错: {e}")
        # 尝试返回模拟数据
        return generate_mock_music_list(keyword), "当前音乐搜索服务暂时不可用，显示模拟数据"
    except ValueError as e:
        print(f"解析音乐数据时出错: {e}")
        # 尝试返回模拟数据
        return generate_mock_music_list(keyword), "当前音乐数据解析失败，显示模拟数据"
    except Exception as e:
        print(f"搜索音乐时发生未知错误: {e}")
        # 尝试返回模拟数据
        return generate_mock_music_list(keyword), "当前音乐搜索失败，显示模拟数据"

def generate_mock_music_list(keyword):
    """生成模拟音乐数据"""
    mock_music = [
        {
            'id': '1',
            'name': f'{keyword} - 热门歌曲1',
            'artists': ['模拟歌手1'],
            'artist_names': '模拟歌手1',
            'album': '模拟专辑1',
            'duration': 240,
            'url': ''  # 模拟数据没有播放URL
        },
        {
            'id': '2',
            'name': f'{keyword} - 热门歌曲2',
            'artists': ['模拟歌手2'],
            'artist_names': '模拟歌手2',
            'album': '模拟专辑2',
            'duration': 210,
            'url': ''  # 模拟数据没有播放URL
        },
        {
            'id': '3',
            'name': f'{keyword} - 热门歌曲3',
            'artists': ['模拟歌手3'],
            'artist_names': '模拟歌手3',
            'album': '模拟专辑3',
            'duration': 270,
            'url': ''  # 模拟数据没有播放URL
        }
    ]
    return mock_music

def get_music_url(song_id):
    """获取音乐的播放URL"""
    try:
        # 构建请求URL
        url = f"{MUSIC_API_BASE_URL}{MUSIC_DETAIL_ENDPOINT}"
        params = {
            'id': song_id
        }
        
        # 发送API请求
        response = requests.get(url, params=params, timeout=10)
        
        # 检查响应状态
        if response.status_code != 200:
            return None, f"音乐URL API返回错误状态码: {response.status_code}"
        
        # 解析响应数据
        data = response.json()
        
        # 提取音乐URL
        music_url = data.get('data', [{}])[0].get('url', '')
        
        if not music_url:
            return None, "无法获取音乐播放链接"
        
        return music_url, None
    
    except Exception as e:
        print(f"获取音乐URL时出错: {e}")
        return None, "获取音乐播放链接失败"

def generate_fallback_response(question):
    """本地模拟的AI回复（作为API调用失败的备用）"""
    # 预定义的回复模板
    default_responses = [
        "您好！很高兴为您提供帮助。",
        "这个问题很有趣，让我思考一下...",
        "我理解您的意思，您可以尝试一下...",
        "谢谢您的提问，我会尽力解答。",
        "这个问题我还需要学习，不过我可以试着回答..."
    ]
    
    question = question.lower()
    
    if any(keyword in question for keyword in ['你好', 'hi', 'hello', '嗨']):
        return random.choice([
            "你好！很高兴见到你！",
            "嗨！有什么可以帮你的吗？",
            "Hello！How can I help you today?"
        ])
    elif any(keyword in question for keyword in ['再见', '拜拜', 'bye']):
        return random.choice([
            "再见！祝您有愉快的一天！",
            "Bye！期待下次与您交流！",
            "回头见！"
        ])
    elif any(keyword in question for keyword in ['名字', '谁', '你是']):
        return "我是川小农，一个AI助手，很高兴为您服务！"
    elif any(keyword in question for keyword in ['帮助', '怎么用', '使用']):
        return "您可以使用以下指令：\n1. @电影 URL - 播放电影\n2. @川小农 问题 - 与我对话\n3. @天气 城市名 - 查询指定城市的天气信息\n4. @新闻 关键词 - 查询指定关键词的新闻\n5. @音乐 关键词 - 查询指定关键词的音乐"
    elif any(keyword in question for keyword in ['天气', '气温']):
        return "您可以使用@天气 城市名的格式来查询天气信息，例如：@天气 北京"
    elif any(keyword in question for keyword in ['谢谢', '感谢']):
        return "不客气！能够帮助您是我的荣幸！"
    
    # 随机选择一个默认回复
    return random.choice(default_responses)

@app.route('/')
def index():
    # 如果已登录，直接跳转到聊天页面
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            return redirect(url_for('chat'))
    return render_template('login.html')

@app.route('/chat')
def chat():
    # 检查是否已登录
    if 'user_id' not in session:
        return redirect(url_for('index'))
    user = User.query.get(session['user_id'])
    if not user:
        return redirect(url_for('index'))
    return render_template('chat.html', username=user.username)

@app.route('/register', methods=['POST'])
@app.route('/api/register', methods=['POST'])
def register():
    """用户注册接口"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        # 验证参数
        if not username or not password:
            return jsonify({"success": False, "message": "用户名和密码不能为空"}), 400
        
        if len(username) < 2 or len(username) > 20:
            return jsonify({"success": False, "message": "用户名长度应在2-20个字符之间"}), 400
        
        if len(password) < 6:
            return jsonify({"success": False, "message": "密码长度至少为6个字符"}), 400
        
        # 检查用户名是否已存在
        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return jsonify({"success": False, "message": "用户名已被使用"}), 400
        
        # 创建新用户
        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        # 记录注册活动
        log_user_activity(user.id, 'create_account', {'username': username})
        
        return jsonify({"success": True, "message": "注册成功"})
    except Exception as e:
        print(f"注册失败: {e}")
        db.session.rollback()
        return jsonify({"success": False, "message": "注册失败，请稍后重试"}), 500

@app.route('/login', methods=['POST'])
@app.route('/api/login', methods=['POST'])
def login():
    """用户登录接口"""
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        # 验证参数
        if not username or not password:
            return jsonify({"success": False, "message": "用户名和密码不能为空"}), 400
        
        # 查找用户
        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            return jsonify({"success": False, "message": "用户名或密码错误"}), 401
        
        # 更新登录状态
        user.is_online = True
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        # 设置session
        session['user_id'] = user.id
        
        # 记录登录活动
        log_user_activity(user.id, 'login')
        
        return jsonify({"success": True, "message": "登录成功", "user": user.to_dict()})
    except Exception as e:
        print(f"登录失败: {e}")
        return jsonify({"success": False, "message": "登录失败，请稍后重试"}), 500

@app.route('/logout')
def logout():
    """用户登出接口"""
    try:
        if 'user_id' in session:
            user_id = session['user_id']
            # 更新用户状态为离线
            user = User.query.get(user_id)
            if user:
                user.is_online = False
                db.session.commit()
                # 记录登出活动
                log_user_activity(user_id, 'logout')
        # 清除session
        session.pop('user_id', None)
        return redirect(url_for('index'))
    except Exception as e:
        print(f"登出失败: {e}")
        return redirect(url_for('index'))

@app.route('/api/servers')
def get_servers():
    """获取服务器列表"""
    try:
        print("收到服务器列表请求")
        response = jsonify(servers_config)
        print(f"返回服务器列表: {servers_config}")
        return response
    except Exception as e:
        print(f"服务器列表API出错: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/update_avatar', methods=['POST'])
def update_avatar():
    """更新用户头像"""
    try:
        # 检查用户是否已登录
        if 'user_id' not in session:
            return jsonify({"success": False, "message": "用户未登录"}), 401
        
        user_id = session['user_id']
        user = User.query.get(user_id)
        if not user:
            return jsonify({"success": False, "message": "用户不存在"}), 404
        
        # 检查是否有文件上传
        if 'avatar' not in request.files:
            return jsonify({"success": False, "message": "未选择文件"}), 400
        
        file = request.files['avatar']
        if file.filename == '':
            return jsonify({"success": False, "message": "未选择文件"}), 400
        
        # 检查文件类型
        if not allowed_file(file.filename):
            return jsonify({"success": False, "message": "不支持的文件类型，仅支持png、jpg、jpeg、gif"}), 400
        
        # 生成安全的文件名
        filename = secure_filename(f"{user.username}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.{file.filename.rsplit('.', 1)[1].lower()}")
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        
        # 保存文件
        file.save(filepath)
        
        # 删除旧头像文件（如果存在）
        if user.avatar and os.path.exists(os.path.join(UPLOAD_FOLDER, user.avatar)):
            try:
                os.remove(os.path.join(UPLOAD_FOLDER, user.avatar))
            except:
                pass
        
        # 更新用户头像路径
        user.avatar = filename
        db.session.commit()
        
        # 返回头像URL
        avatar_url = f"/static/uploads/avatars/{filename}"
        
        return jsonify({"success": True, "message": "头像更新成功", "avatar_url": avatar_url})
    except Exception as e:
        print(f"更新头像失败: {e}")
        db.session.rollback()
        return jsonify({"success": False, "message": "头像更新失败，请稍后重试"}), 500

def allowed_file(filename):
    """检查文件类型是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/check_username', methods=['POST'])
def check_username():
    """检查用户名是否可用"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "无效的请求数据"}), 400
        
        username = data.get('username')
        if not username:
            return jsonify({"error": "用户名不能为空"}), 400
            
        # 检查用户名是否已存在
        existing_user = User.query.filter_by(username=username).first()
        is_available = existing_user is None
        return jsonify({"available": is_available})
    except Exception as e:
        print(f"用户名检查出错: {str(e)}")
        return jsonify({"error": f"服务器错误: {str(e)}"}), 500

@app.route('/api/user_info')
def get_user_info():
    """获取当前用户信息"""
    if 'user_id' not in session:
        return jsonify({"error": "未登录"}), 401
    
    user = User.query.get(session['user_id'])
    if not user:
        return jsonify({"error": "用户不存在"}), 404
    
    return jsonify({"user": user.to_dict()})

@app.route('/api/check_login')
def check_login():
    """检查登录状态接口"""
    if 'user_id' in session:
        user = User.query.get(session['user_id'])
        if user:
            return jsonify({'logged_in': True, 'username': user.username})
    return jsonify({'logged_in': False})

@app.route('/api/users', methods=['GET'])
def get_users():
    """获取用户列表（简单的管理员功能）"""
    # 验证登录状态
    if 'user_id' not in session:
        return jsonify({'error': '未登录'}), 401
    
    # 简单实现：获取所有用户列表
    users = User.query.all()
    users_list = [{
        'id': user.id,
        'username': user.username,
        'is_online': user.is_online,
        'last_login': user.last_login.isoformat() if user.last_login else None,
        'created_at': user.created_at.isoformat()
    } for user in users]
    
    return jsonify({'users': users_list})

@app.route('/api/users/<int:user_id>', methods=['GET'])
def get_user(user_id):
    """获取指定用户信息"""
    # 验证登录状态
    if 'user_id' not in session:
        return jsonify({'error': '未登录'}), 401
    
    # 只能查看自己的信息（简单权限控制）
    current_user_id = session['user_id']
    if current_user_id != user_id:
        return jsonify({'error': '无权查看其他用户信息'}), 403
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': '用户不存在'}), 404
    
    return jsonify({'user': user.to_dict()})

@app.route('/api/users/<int:user_id>', methods=['PUT'])
def update_user(user_id):
    """更新用户信息"""
    # 验证登录状态
    if 'user_id' not in session:
        return jsonify({'error': '未登录'}), 401
    
    # 只能更新自己的信息
    current_user_id = session['user_id']
    if current_user_id != user_id:
        return jsonify({'error': '无权更新其他用户信息'}), 403
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': '用户不存在'}), 404
    
    try:
        data = request.get_json()
        
        # 检查是否更新密码
        if 'current_password' in data and 'new_password' in data:
            current_password = data['current_password']
            new_password = data['new_password']
            
            # 验证当前密码
            if not user.check_password(current_password):
                return jsonify({'error': '当前密码错误'}), 400
            
            # 验证新密码长度
            if len(new_password) < 6:
                return jsonify({'error': '新密码长度至少为6个字符'}), 400
            
            # 更新密码
            user.set_password(new_password)
            log_user_activity(user_id, 'update_password')
            
        # 提交更新
        db.session.commit()
        
        return jsonify({'success': True, 'message': '用户信息更新成功', 'user': user.to_dict()})
    except Exception as e:
        print(f"更新用户信息失败: {e}")
        db.session.rollback()
        return jsonify({'error': '更新失败，请稍后重试'}), 500

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """删除用户（简单实现，仅用于测试）"""
    # 验证登录状态
    if 'user_id' not in session:
        return jsonify({'error': '未登录'}), 401
    
    # 只能删除自己的账户
    current_user_id = session['user_id']
    if current_user_id != user_id:
        return jsonify({'error': '无权删除其他用户账户'}), 403
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': '用户不存在'}), 404
    
    try:
        # 记录删除活动
        log_user_activity(user_id, 'delete_account', {'username': user.username})
        
        # 删除用户（注意：这里可能需要先处理关联数据）
        db.session.delete(user)
        db.session.commit()
        
        # 清除session
        session.pop('user_id', None)
        
        return jsonify({'success': True, 'message': '账户已成功删除'})
    except Exception as e:
        print(f"删除用户失败: {e}")
        db.session.rollback()
        return jsonify({'error': '删除失败，请稍后重试'}), 500

def update_all_user_lists():
    """更新所有用户列表（包含在线状态和头像信息）"""
    # 获取所有用户
    all_users = User.query.all()
    
    # 构建用户列表，包含在线状态和头像
    user_list = []
    for user in all_users:
        user_list.append({
            'username': user.username,
            'nickname': user.username,  # 添加nickname字段，与前端保持一致
            'is_online': user.is_online,
            'avatar': user.avatar  # 添加头像信息
        })
    
    # 广播用户列表更新
    emit('user_list_update', {'users': user_list}, broadcast=True)
    
    # 打印当前在线用户数量
    online_count = sum(1 for u in all_users if u.is_online)
    print(f'当前在线用户数: {online_count}')

@socketio.on('connect')
def handle_connect():
    print('客户端已连接')

@socketio.on('disconnect')
def handle_disconnect():
    """处理用户断开连接"""
    if request.sid in users:
        user_id = users[request.sid]
        user = User.query.get(user_id)
        if user:
            # 更新用户状态为离线
            user.is_online = False
            db.session.commit()
            # 记录离线活动
            log_user_activity(user_id, 'logout')
            
            # 广播用户离开消息
            emit('user_left', {'username': user.username}, broadcast=True)
            
            # 更新用户列表（包含在线状态）
            update_all_user_lists()
            
            print(f'用户 {user.username} 已离开')
        
        # 移除在线用户映射
        del users[request.sid]

@socketio.on('join')
def handle_join(data):
    """处理用户加入聊天室"""
    # 兼容新的前端实现，获取username而不是user_id
    username = data.get('username')
    
    # 验证用户是否已登录
    if 'user_id' not in session:
        emit('join_error', {'message': '未登录'})
        return
    
    # 获取用户信息
    user = User.query.get(session['user_id'])
    if not user:
        emit('join_error', {'message': '用户不存在'})
        return
    
    # 验证用户名匹配
    if username and user.username != username:
        emit('join_error', {'message': '用户名不匹配'})
        return
    
    # 存储用户信息 (sid -> user_id)
    users[request.sid] = session['user_id']
    
    # 加入默认房间
    join_room('default_room')
    
    # 通知用户加入成功
    emit('join_success', {'message': f'欢迎 {user.username}！', 'user': user.to_dict()})
    
    # 更新用户状态为在线
    user.is_online = True
    db.session.commit()
    
    # 广播新用户加入消息
    emit('user_joined', {'username': user.username}, broadcast=True, include_self=False)
    
    # 发送用户列表给所有用户（包含在线状态）
    update_all_user_lists()
    
    # 加载历史聊天记录并发送给当前用户
    # 获取最近的50条消息
    recent_messages = ChatMessage.query.order_by(ChatMessage.created_at.desc()).limit(50).all()
    # 反转顺序，使最早的消息在前
    recent_messages.reverse()
    
    # 构建历史消息数据
    history_messages = []
    for msg in recent_messages:
        msg_dict = msg.to_dict()
        history_messages.append(msg_dict)
    
    # 发送历史消息给当前用户
    emit('load_history', {'messages': history_messages})
    
    print(f'用户 {user.username} 已加入，已加载历史聊天记录')

@socketio.on('send_message')
def handle_message(data):
    """处理发送消息"""
    user_id = users.get(request.sid)
    if not user_id:
        return
    
    # 获取用户信息
    user = User.query.get(user_id)
    if not user:
        return
    
    message = data.get('message', '')
    timestamp = data.get('timestamp') or datetime.utcnow().timestamp()
    
    # 消息类型
    message_type = 'text'
    # 检查是否包含指令
    command_data = None
    
    # 解析@指令
    if message.startswith('@'):
        command_match = re.match(r'^@(\S+)(?:\s+(.*))?$', message)
        if command_match:
            command = command_match.group(1).lower()
            command_content = command_match.group(2) or ''
            
            # 电影指令
            if command == '电影' and command_content:
                message_type = 'movie'
                # 提取URL
                url = command_content.strip()
                # 验证URL格式
                if not re.match(r'^https?://', url):
                    # 如果不是完整URL，添加http前缀
                    url = 'http://' + url
                # URL编码
                encoded_url = urllib.parse.quote(url)
                # 拼接至解析接口
                parsed_url = f"https://jx.m3u8.tv/jiexi/?url={encoded_url}"
                command_data = {'url': url, 'parsed_url': parsed_url}
            # 天气查询指令
            elif command == '天气' and command_content:
                message_type = 'weather'
                city_name = command_content.strip()
                command_data = {'city': city_name}
                
                try:
                    # 调用天气查询功能
                    print(f"处理天气查询: {city_name}")
                    weather_info, error = get_weather_by_city(city_name)
                    
                    if weather_info:
                        # 生成天气提示
                        weather_tips = generate_weather_tips(weather_info)
                        
                        # 确定天气类型用于前端背景切换
                        weather_desc = weather_info['weather'].lower()
                        weather_type = 'default'
                        if any(keyword in weather_desc for keyword in ['晴', 'sunny']):
                            weather_type = 'sunny'
                        elif any(keyword in weather_desc for keyword in ['雨', 'rain', '阵雨']):
                            weather_type = 'rainy'
                        elif any(keyword in weather_desc for keyword in ['阴', 'overcast']):
                            weather_type = 'cloudy'
                        elif any(keyword in weather_desc for keyword in ['雪', 'snow']):
                            weather_type = 'snowy'
                        elif any(keyword in weather_desc for keyword in ['多云', 'partly cloudy']):
                            weather_type = 'partly-cloudy'
                        elif any(keyword in weather_desc for keyword in ['雾', '霾', 'fog', 'haze']):
                            weather_type = 'foggy'
                        
                        # 构建天气回复
                        weather_response = f"🌤️ {weather_info['city']} 当前天气\n" \
                                          f"温度: {weather_info['temp']}°C (体感温度: {weather_info['feels_like']}°C)\n" \
                                          f"天气状况: {weather_info['weather']}\n" \
                                          f"风向风速: {weather_info['wind_dir']} {weather_info['wind_scale']}级\n" \
                                          f"湿度: {weather_info['humidity']}%  气压: {weather_info['pressure']}hPa\n\n" \
                                          f"{weather_tips}"
                        
                        command_data['response'] = weather_response
                        command_data['status'] = 'success'
                        command_data['weather_type'] = weather_type
                    else:
                        command_data['response'] = error
                        command_data['status'] = 'error'
                        command_data['weather_type'] = 'default'
                        
                except Exception as e:
                    # 捕获所有可能的异常
                    error_message = f"天气查询出错: {str(e)}"
                    print(error_message)
                    command_data['response'] = "抱歉，查询天气时遇到了困难。请稍后再试。"
                    command_data['status'] = 'error'
                    command_data['weather_type'] = 'default'
            
            # 新闻查询指令
            elif command == '新闻' and command_content:
                message_type = 'news'
                keyword = command_content.strip()
                command_data = {'keyword': keyword}
                
                try:
                    # 调用新闻查询功能
                    print(f"处理新闻查询: {keyword}")
                    news_list, error = get_news_by_keyword(keyword)
                    
                    if news_list:
                        # 构建新闻回复
                        command_data['news_list'] = news_list
                        command_data['response'] = f"已找到关于'{keyword}'的{len(news_list)}条新闻。"
                        command_data['status'] = 'success'
                    else:
                        command_data['response'] = error or f"未找到关于'{keyword}'的新闻。"
                        command_data['status'] = 'error'
                        
                except Exception as e:
                    # 捕获所有可能的异常
                    error_message = f"新闻查询出错: {str(e)}"
                    print(error_message)
                    command_data['response'] = "抱歉，查询新闻时遇到了困难。请稍后再试。"
                    command_data['status'] = 'error'
            
            # 音乐查询指令
            elif command == '音乐' and command_content:
                message_type = 'music'
                keyword = command_content.strip()
                command_data = {'keyword': keyword}
                
                try:
                    # 调用音乐搜索功能
                    print(f"处理音乐搜索: {keyword}")
                    music_list, error = search_music(keyword)
                    
                    if music_list:
                        # 为每首歌曲获取播放URL
                        for i, music in enumerate(music_list):
                            if i < 3:  # 只获取前3首歌曲的URL以提高性能
                                music_url, url_error = get_music_url(music['id'])
                                if music_url:
                                    music_list[i]['url'] = music_url
                        
                        # 构建音乐回复
                        command_data['music_list'] = music_list
                        command_data['response'] = f"已找到关于'{keyword}'的{len(music_list)}首歌曲。"
                        command_data['status'] = 'success'
                    else:
                        command_data['response'] = error or f"未找到关于'{keyword}'的歌曲。"
                        command_data['status'] = 'error'
                        
                except Exception as e:
                    # 捕获所有可能的异常
                    error_message = f"音乐搜索出错: {str(e)}"
                    print(error_message)
                    command_data['response'] = "抱歉，搜索音乐时遇到了困难。请稍后再试。"
                    command_data['status'] = 'error'
            
            # AI对话指令
            elif command == '川小农':
                message_type = 'ai'
                question = command_content.strip()
                command_data = {'question': question}
                
                try:
                    # 调用AI回复功能
                    print(f"处理AI请求: {question}")
                    start_time = time.time()
                    ai_response = generate_ai_response(question)
                    end_time = time.time()
                    print(f"AI回复生成完成，耗时: {end_time - start_time:.2f}秒")
                    
                    # 格式化回复，确保换行正常显示
                    formatted_response = ai_response.replace('\n', '\\n')
                    command_data['response'] = formatted_response
                    command_data['status'] = 'success'
                    
                except Exception as e:
                    # 捕获所有可能的异常
                    error_message = f"AI处理出错: {str(e)}"
                    print(error_message)
                    command_data['response'] = "抱歉，处理您的问题时遇到了困难。请稍后再试。"
                    command_data['status'] = 'error'
    
    # 保存消息到数据库
    chat_message = ChatMessage(
        user_id=user_id,
        message=message,
        message_type=message_type,
        command_data=json.dumps(command_data) if command_data else None
    )
    try:
        db.session.add(chat_message)
        db.session.commit()
    except Exception as e:
        print(f"保存消息失败: {e}")
        db.session.rollback()
    
    # 构建消息数据
    message_data = {
        'username': user.username,
        'nickname': user.username,  # 使用用户名作为昵称
        'avatar': user.avatar,  # 添加头像信息
        'message': message,
        'timestamp': timestamp,
        'type': message_type
    }
    
    # 如果是指令消息，添加指令数据
    if command_data:
        message_data['command_data'] = command_data
    
    # 为每个用户单独发送消息，添加is_self标识
    for client_sid, receiver_user_id in users.items():
        receiver_user = User.query.get(receiver_user_id)
        personalized_message = message_data.copy()
        personalized_message['is_self'] = (user_id == receiver_user_id)
        socketio.emit('new_message', personalized_message, room=client_sid)
    print(f'消息: {user.username}: {message}')

@socketio.on('leave')
def handle_leave():
    """处理用户主动离开"""
    handle_disconnect()
    # 清除session
    session.pop('user_id', None)

@socketio.on('refresh_user_list')
def handle_refresh_user_list():
    """处理用户列表刷新请求（用于头像更新后刷新显示）"""
    user_id = users.get(request.sid)
    if not user_id:
        return
    
    # 获取所有用户
    all_users = User.query.all()
    
    # 构建用户列表，包含在线状态和头像
    user_list = []
    for user in all_users:
        user_list.append({
            'username': user.username,
            'is_online': user.is_online,
            'avatar': user.avatar  # 添加头像信息
        })
    
    # 仅发送给请求刷新的用户
    emit('refresh_user_list_success', {'users': user_list})

# 启动服务器
if __name__ == '__main__':
    port = 8888  # 使用端口8888
    print('服务器启动中...')
    print(f'访问地址: http://localhost:{port}')
    socketio.run(app, host='0.0.0.0', port=port, debug=True)

