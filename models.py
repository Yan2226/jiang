from flask_sqlalchemy import SQLAlchemy
import bcrypt
from datetime import datetime

# 初始化数据库
db = SQLAlchemy()

class User(db.Model):
    """用户模型"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(128), nullable=False)
    is_online = db.Column(db.Boolean, default=False)
    avatar = db.Column(db.String(255), default='')  # 存储头像路径或标识符
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联聊天记录
    messages = db.relationship('ChatMessage', backref='user', lazy='dynamic')
    
    def set_password(self, password):
        """设置密码（加密存储）"""
        # 生成盐值并哈希密码
        salt = bcrypt.gensalt()
        self.password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    
    def check_password(self, password):
        """验证密码"""
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))
    
    def to_dict(self):
        """转换为字典格式"""
        return {
            'id': self.id,
            'username': self.username,
            'is_online': self.is_online,
            'avatar': self.avatar,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'created_at': self.created_at.isoformat()
        }

class ChatMessage(db.Model):
    """聊天消息模型"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    message_type = db.Column(db.String(20), default='text')
    command_data = db.Column(db.Text)  # JSON格式存储指令数据
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        """转换为字典格式"""
        import json
        command_data = json.loads(self.command_data) if self.command_data else None
        return {
            'id': self.id,
            'username': self.user.username,
            'message': self.message,
            'type': self.message_type,
            'command_data': command_data,
            'timestamp': self.created_at.timestamp()
        }

class UserActivity(db.Model):
    """用户活动记录模型"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    activity_type = db.Column(db.String(50), nullable=False)  # login, logout, create_account, weather_search, news_search, music_play
    activity_data = db.Column(db.Text)  # JSON格式存储活动数据
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        """转换为字典格式"""
        import json
        activity_data = json.loads(self.activity_data) if self.activity_data else None
        return {
            'id': self.id,
            'username': self.user.username,
            'activity_type': self.activity_type,
            'activity_data': activity_data,
            'created_at': self.created_at.isoformat()
        }