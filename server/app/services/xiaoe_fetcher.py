import shlex
import urllib.parse
import urllib.request
import json
import time
import random
import logging
from concurrent.futures import ThreadPoolExecutor

from app.config import get_settings
from app.models import db_mysql
from app.tools.joplinUtil import JoplinToolbox

logger = logging.getLogger(__name__)
settings = get_settings()

# 使用简单的线程池来执行后台任务
executor = ThreadPoolExecutor(max_workers=2)

def parse_curl(curl_string):
    """
    从 curl 文本中解析出 URL 和 Headers。
    兼容文件末尾可能附带 JSON 响应体的情况（浏览器 copy as curl 后手动粘贴的内容）。
    """
    # 只取 curl 命令部分：从 'curl ' 开始，到最后一个不以 \ 结尾的行为止
    lines = curl_string.splitlines()
    curl_lines = []
    started = False
    for line in lines:
        stripped = line.strip()
        if not started:
            if stripped.startswith('curl '):
                started = True
                curl_lines.append(line)
            continue
        else:
            # 如果上一行以 \ 结尾，继续拼接
            if curl_lines and curl_lines[-1].rstrip().endswith('\\'):
                curl_lines.append(line)
            else:
                break  # curl 命令已结束，后面的内容（如 JSON 响应）忽略

    curl_cmd = '\n'.join(curl_lines)
    tokens = shlex.split(curl_cmd)
    url = None
    headers = {}
    
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token == 'curl':
            i += 1
            continue
        elif token in ('-H', '--header'):
            header_val = tokens[i+1]
            if ':' in header_val:
                k, v = header_val.split(':', 1)
                headers[k.strip()] = v.strip()
            i += 2
        elif token in ('-b', '--cookie'):
            cookies = tokens[i+1]
            if 'Cookie' not in headers and 'cookie' not in headers:
                headers['Cookie'] = cookies
            else:
                if 'Cookie' in headers:
                    headers['Cookie'] += '; ' + cookies
                elif 'cookie' in headers:
                    headers['cookie'] += '; ' + cookies
            i += 2
        elif token.startswith('http://') or token.startswith('https://'):
            url = token
            i += 1
        elif token == '--compressed':
            i += 1
        else:
            i += 1
            
    # 移除 Accept-Encoding 防止返回 gzip 乱码
    if 'Accept-Encoding' in headers:
        del headers['Accept-Encoding']
    if 'accept-encoding' in headers:
        del headers['accept-encoding']
        
    return url, headers

def run_xiaoe_fetch_task(curl_string: str, joplin_path: str, start_page: int = 1, limit: int = 0):
    logger.info("🚀 开始执行小鹅通后台抓取任务...")
    try:
        # 1. 解析 MySQL 和 CURL
        db_mysql.init_db()  # 确保表已创建
        
        url, headers = parse_curl(curl_string)
        if not url:
            logger.error("❌ 无法从 curl 中解析出 URL")
            return
            
        parsed_url = urllib.parse.urlparse(url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        # 移除原 curl 中可能自带的 cursor 参数，强制依赖 page 翻页，确保总是从最新数据开始抓取
        if 'cursor' in query_params:
            del query_params['cursor']
        
        page = start_page
        fetched_count = 0
        consecutive_unchanged = 0
        updated_months = set()
        
        # 如果请求没有传 limit (传了0)，则降级使用环境变量的配置
        if limit == 0:
            limit = settings.XIAOE_FETCH_LIMIT
        
        conn = db_mysql.get_connection()
        cursor = conn.cursor()
        
        while True:
            if limit > 0 and fetched_count >= limit:
                logger.info(f"⚠️ 达到测试限制: 本次已拉取 {limit} 页，停止拉取。")
                break
                
            query_params['page'] = [str(page)]
            new_query = urllib.parse.urlencode(query_params, doseq=True)
            current_url = urllib.parse.urlunparse(parsed_url._replace(query=new_query))
            
            logger.info(f"正在拉取第 {page} 页...")
            
            req = urllib.request.Request(current_url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=15) as response:
                    response_data = response.read().decode('utf-8')
                    data = json.loads(response_data)
            except Exception as e:
                logger.error(f"❌ 拉取第 {page} 页时出错: {e}")
                break
                
            if data.get('code') != 0:
                logger.error(f"❌ API 返回错误: {data.get('msg')}")
                break
                
            posts = data.get('data', {}).get('list', [])
            if not posts:
                logger.info(f"✅ 第 {page} 页没有找到任何帖子，所有数据拉取结束。")
                break
                
            for post in posts:
                post_id = post.get('id')
                content_obj = post.get('content')
                if isinstance(content_obj, dict):
                    q_title = content_obj.get('question_title', '')
                    q_text = content_obj.get('question_text', '')
                    ans_text = content_obj.get('text', '')
                    
                    parts = []
                    if q_title or q_text:
                        questioner = content_obj.get('questioner_info', {}).get('nick_name', '匿名用户')
                        parts.append(f"❓ **【{questioner} 提问】**")
                        if q_title:
                            parts.append(f"**{q_title}**")
                        if q_text:
                            parts.append(q_text)
                        parts.append("\n💡 **【回答】**")
                        
                    if ans_text:
                        parts.append(ans_text)
                    content_text = '\n\n'.join(parts)
                elif isinstance(content_obj, str):
                    content_text = content_obj
                elif isinstance(content_obj, list):
                    content_text = '\n'.join([c.get('text', '') if isinstance(c, dict) else str(c) for c in content_obj])
                else:
                    content_text = str(content_obj) if content_obj else ''
                created_at = post.get('created_at', '')
                if created_at:
                    updated_months.add(created_at[:7])
                user_id = post.get('user_id', '')
                nick_name = post.get('nick_name', '')
                zan_num = post.get('zan_num', 0)
                comment_count = post.get('comment_count', 0)
                raw_json = json.dumps(post, ensure_ascii=False)
                
                # INSERT OR UPDATE
                sql = '''
                    INSERT INTO posts (id, content, created_at, user_id, nick_name, zan_num, comment_count, raw_json)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        content = VALUES(content),
                        nick_name = VALUES(nick_name),
                        zan_num = VALUES(zan_num),
                        comment_count = VALUES(comment_count),
                        raw_json = VALUES(raw_json)
                '''
                cursor.execute(sql, (post_id, content_text, created_at, user_id, nick_name, zan_num, comment_count, raw_json))
                affected = cursor.rowcount
                
                if affected == 0:
                    # 没有任何字段更新（原样存在）
                    consecutive_unchanged += 1
                else:
                    # 新增(1) 或有更新(2)
                    consecutive_unchanged = 0
                
                # 评论处理
                comments = post.get('commentList', {}).get('list', [])
                for c in comments:
                    c_id = c.get('id')
                    c_text = c.get('comment', '')
                    c_created_at = c.get('created_at', '')
                    c_user_id = c.get('user_id', '')
                    c_nick_name = c.get('nick_name', '')
                    c_zan_num = c.get('zan_num', 0)
                    c_raw_json = json.dumps(c, ensure_ascii=False)
                    
                    c_sql = '''
                        INSERT INTO comments (id, post_id, comment, created_at, user_id, nick_name, zan_num, raw_json)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            comment = VALUES(comment),
                            nick_name = VALUES(nick_name),
                            zan_num = VALUES(zan_num),
                            raw_json = VALUES(raw_json)
                    '''
                    cursor.execute(c_sql, (c_id, post_id, c_text, c_created_at, c_user_id, c_nick_name, c_zan_num, c_raw_json))
                    
                if consecutive_unchanged >= 10:
                    logger.info("🎯 连续 10 个帖子数据完全没有更新，判定历史数据已全部衔接完毕，提前停止抓取。")
                    break

            if consecutive_unchanged >= 10:
                break
                
            sleep_time = random.uniform(0, 10)
            logger.info(f"休眠 {sleep_time:.2f} 秒以防止限流...")
            time.sleep(sleep_time)
            page += 1
            fetched_count += 1
            
        conn.close()
        logger.info(f"✅ 抓取任务完成，本次更新影响了以下月份: {updated_months}")
        logger.info("开始将受影响的月份数据同步到 Joplin...")
        
        # 同步 Joplin
        sync_to_joplin(joplin_path, updated_months)
        logger.info("🎉 整个任务闭环完成！")
        
    except Exception as e:
        logger.exception(f"❌ 抓取任务异常退出: {e}")

def sync_to_joplin(joplin_path: str, target_months: set = None):
    """
    按年月分组，查询出所有的帖子和对应评论，
    并选择性地同步受影响的月份到 Joplin，避免全量覆盖的性能浪费。
    """
    try:
        conn = db_mysql.get_connection()
        cursor = conn.cursor()
        
        # 取出所有评论并按 post_id 归类
        cursor.execute("SELECT * FROM comments ORDER BY created_at ASC")
        all_comments = cursor.fetchall()
        comments_by_post = {}
        for c in all_comments:
            pid = c['post_id']
            if pid not in comments_by_post:
                comments_by_post[pid] = []
            comments_by_post[pid].append(c)
            
        # 取出所有帖子，要求按时间倒序排列 (最新的在最上面)
        cursor.execute("SELECT * FROM posts ORDER BY created_at DESC")
        posts = cursor.fetchall()
        
        groups = {}
        for p in posts:
            dt = p['created_at']
            if not dt:
                continue
            month = dt.strftime('%Y-%m') if hasattr(dt, 'strftime') else str(dt)[:7]
            if month not in groups:
                groups[month] = []
            groups[month].append(p)
            
        conn.close()
        
        joplin_tool = JoplinToolbox(settings.JOPLIN_TOKEN, url=settings.JOPLIN_HOST)
        
        for month, m_posts in groups.items():
            if target_months is not None and month not in target_months:
                continue
                
            title = f"{month} 帖子汇总"
            md_lines = [f"# {title}", ""]
            
            for p in m_posts:
                md_lines.append(f"## {p['nick_name']} · {p['created_at']}")
                md_lines.append(f"{p['content']}")
                md_lines.append("")
                md_lines.append(f"> ❤️ 点赞: {p['zan_num']} | 💬 评论: {p['comment_count']}")
                
                # 附加评论
                p_comments = comments_by_post.get(p['id'], [])
                if p_comments:
                    md_lines.append("")
                    md_lines.append("**评论区:**")
                    for c in p_comments:
                        # 替换换行符为 <br> 以防止破坏 Markdown 列表结构
                        safe_comment = c['comment'].replace('\n', '<br>') if c['comment'] else ''
                        md_lines.append(f"- **{c['nick_name']}**: {safe_comment} *(赞: {c['zan_num']})*")
                        
                md_lines.append("")
                md_lines.append("---")
                md_lines.append("")
                
            body = "\n".join(md_lines)
            note_id = joplin_tool.get_or_create_note_by_title(title, joplin_path)
            joplin_tool.update_note(note_id, body=body)
            logger.info(f"✅ Joplin 笔记更新成功: {title} (包含 {len(m_posts)} 篇帖子)")
            
    except Exception as e:
        logger.exception(f"❌ 同步 Joplin 异常: {e}")

def submit_fetch_task(curl_string: str, joplin_path: str, start_page: int = 1, limit: int = 0) -> str:
    """
    提交后台任务
    """
    task_id = f"task_{int(time.time())}"
    executor.submit(run_xiaoe_fetch_task, curl_string, joplin_path, start_page, limit)
    return task_id
