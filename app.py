from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS
import json
import re
import random
import urllib.parse
import requests
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
CORS(app)  # 添加CORS支持
socketio = SocketIO(app, cors_allowed_origins="*")

# 存储在线用户信息
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
        return "您可以使用以下指令：\n1. @电影 URL - 播放电影\n2. @川小农 问题 - 与我对话"
    elif any(keyword in question for keyword in ['天气', '气温']):
        return "我暂时无法查询天气信息，但我会努力学习这个功能！"
    elif any(keyword in question for keyword in ['谢谢', '感谢']):
        return "不客气！能够帮助您是我的荣幸！"
    
    # 随机选择一个默认回复
    return random.choice(default_responses)

@app.route('/')
def index():
    return render_template('login.html')

@app.route('/chat')
def chat():
    nickname = request.args.get('nickname')
    if not nickname:
        return render_template('login.html')
    return render_template('chat.html', nickname=nickname)

@app.route('/api/servers')
def get_servers():
    """获取服务器列表"""
    return jsonify(servers_config)

@app.route('/api/check_nickname', methods=['POST'])
def check_nickname():
    """检查昵称是否可用"""
    try:
        print("收到昵称检查请求")
        data = request.get_json()
        if not data:
            return jsonify({"error": "无效的请求数据"}), 400
        
        nickname = data.get('nickname')
        if not nickname:
            return jsonify({"error": "昵称不能为空"}), 400
            
        print(f"检查昵称: {nickname}")
        is_available = nickname not in users.values()  # 修正：检查的是values而不是keys
        print(f"昵称是否可用: {is_available}")
        return jsonify({"available": is_available})
    except Exception as e:
        print(f"昵称检查出错: {str(e)}")
        return jsonify({"error": f"服务器错误: {str(e)}"}), 500

@socketio.on('connect')
def handle_connect():
    print('客户端已连接')

@socketio.on('disconnect')
def handle_disconnect():
    """处理用户断开连接"""
    for sid, nickname in list(users.items()):
        if sid == request.sid:
            del users[sid]
            # 广播用户离开消息
            emit('user_left', {'nickname': nickname}, broadcast=True)
            # 更新在线用户列表
            emit('user_list_update', {'users': list(users.values())}, broadcast=True)
            print(f'用户 {nickname} 已离开')
            break

@socketio.on('join')
def handle_join(data):
    """处理用户加入聊天室"""
    nickname = data.get('nickname')
    if not nickname or nickname in users.values():
        emit('join_error', {'message': '昵称已被使用，请更换昵称'})
        return
    
    # 存储用户信息
    users[request.sid] = nickname
    
    # 加入默认房间
    join_room('default_room')
    
    # 通知用户加入成功
    emit('join_success', {'message': f'欢迎 {nickname}！'})
    
    # 广播新用户加入消息
    emit('user_joined', {'nickname': nickname, 'message': f'{nickname} 加入了聊天室'}, broadcast=True, include_self=False)
    
    # 发送在线用户列表给所有用户
    emit('user_list_update', {'users': list(users.values())}, broadcast=True)
    
    print(f'用户 {nickname} 已加入，当前在线: {list(users.values())}')

@socketio.on('send_message')
def handle_message(data):
    """处理发送消息"""
    nickname = users.get(request.sid)
    if not nickname:
        return
    
    message = data.get('message', '')
    timestamp = data.get('timestamp')
    
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
    
    # 构建消息数据
    message_data = {
        'nickname': nickname,
        'message': message,
        'timestamp': timestamp,
        'type': message_type
    }
    
    # 如果是指令消息，添加指令数据
    if command_data:
        message_data['command_data'] = command_data
    
    # 广播消息给所有用户
    emit('new_message', message_data, broadcast=True)
    print(f'消息: {nickname}: {message}')

@socketio.on('leave')
def handle_leave():
    """处理用户主动离开"""
    handle_disconnect()

# 启动服务器
if __name__ == '__main__':
    port = 8888  # 使用端口8888
    print('服务器启动中...')
    print(f'访问地址: http://localhost:{port}')
    socketio.run(app, host='0.0.0.0', port=port, debug=True)
