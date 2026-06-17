import pymysql
import logging
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

def get_connection():
    return pymysql.connect(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        database=settings.MYSQL_DATABASE,
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True
    )

def init_db():
    try:
        # 先不指定 database 连接，如果库不存在则创建
        conn = pymysql.connect(
            host=settings.MYSQL_HOST,
            port=settings.MYSQL_PORT,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            charset='utf8mb4',
            autocommit=True
        )
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{settings.MYSQL_DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        conn.close()

        # 连接指定的 database 创建表
        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS posts (
                    id VARCHAR(255) PRIMARY KEY,
                    content LONGTEXT,
                    created_at DATETIME,
                    user_id VARCHAR(255),
                    nick_name VARCHAR(255),
                    zan_num INT DEFAULT 0,
                    comment_count INT DEFAULT 0,
                    raw_json LONGTEXT
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            ''')
            
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS comments (
                    id BIGINT PRIMARY KEY,
                    post_id VARCHAR(255),
                    comment LONGTEXT,
                    created_at DATETIME,
                    user_id VARCHAR(255),
                    nick_name VARCHAR(255),
                    zan_num INT DEFAULT 0,
                    raw_json LONGTEXT,
                    INDEX idx_post_id (post_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            ''')
        conn.close()
        logger.info("✅ MySQL 数据库表初始化完成")
    except Exception as e:
        logger.error(f"❌ MySQL 初始化失败: {e}")
