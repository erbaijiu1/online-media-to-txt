====================================================
小鹅通帖子抓取接口  /api/xiaoe/upload-curl
====================================================

一、功能说明
    上传一个包含 curl 请求的文本文件，服务端会：
    1. 解析 curl 中的 URL、Headers、Cookie
    2. 自动翻页抓取帖子和评论，写入 MySQL 数据库
    3. 按年月分组，将所有帖子全量渲染成 Markdown 同步到 Joplin

二、环境变量（.env 文件）
    # MySQL
    MYSQL_HOST=127.0.0.1
    MYSQL_PORT=3306
    MYSQL_USER=root
    MYSQL_PASSWORD=yourpassword
    MYSQL_DATABASE=xiaoe_db

    # Joplin
    JOPLIN_TOKEN=你的joplin_token
    JOPLIN_HOST=http://host.docker.internal:41184

    # 测试模式：仅拉取指定页数（0=不限制）
    XIAOE_FETCH_LIMIT=1

三、调用方式（curl 命令）

    curl -X POST "http://127.0.0.1:8000/api/xiaoe/upload-curl" \
         -F "file=@/path/to/your/curl_rec.txt" \
         -F "joplin_path=Project/stock/不惑少年/帖子"

    参数说明：
    - file:         必填，curl 请求文本文件（从浏览器 Copy as cURL 后保存的文件）
    - joplin_path:  必填，Joplin 笔记本路径，笔记会按 "YYYY-MM 帖子汇总" 命名

四、返回示例
    {
        "success": true,
        "task_id": "task_1750046123",
        "message": "抓取任务已提交到后台执行，帖子将写入 MySQL 并同步到 Joplin"
    }

五、测试流程
    1. 在 .env 中设置 XIAOE_FETCH_LIMIT=1 （只拉一页，快速验证）
    2. 调用上面的 curl 命令
    3. 检查 MySQL 中 posts / comments 表是否有数据
    4. 检查 Joplin 中是否生成了月度汇总笔记
    5. 验证无误后，将 XIAOE_FETCH_LIMIT 改为 0 放开全量抓取

六、停止策略
    - 连续 10 条帖子的点赞/评论/内容等完全没有变化 → 自动停止
    - 当前页无数据 → 自动停止
    - XIAOE_FETCH_LIMIT > 0 时超过指定页数 → 自动停止
    - 每页之间随机休眠 0~10 秒以防限流
