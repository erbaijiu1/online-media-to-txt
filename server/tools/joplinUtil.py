import os

from joppy.client_api import ClientApi


class JoplinToolbox:
    def __init__(self, token=None):
        self.token = token or os.getenv("JOPLIN_TOKEN", "")
        if not self.token:
            raise ValueError("❌ 未检测到 JOPLIN_TOKEN")
        self.api = ClientApi(token=self.token)
        self._path_map = {}  # 缓存 路径 -> ID 的映射

    def _refresh_path_map(self):
        """
        构建全量路径映射表。
        支持多级目录，例如 {"不惑少年/直播": "id_123", "文集/石油": "id_456"}
        """
        all_notebooks = self.api.get_all_notebooks()
        # 1. 建立 ID 到 对象的索引，方便向上回溯
        id_to_nb = {nb.id: nb for nb in all_notebooks}

        path_map = {}

        # 2. 对每个笔记本计算全路径
        for nb in all_notebooks:
            path_parts = [nb.title]
            curr = nb
            # 循环向上寻找父节点，直到根节点 (parent_id 为空字符串)
            while curr.parent_id:
                curr = id_to_nb.get(curr.parent_id)
                if not curr:
                    break
                path_parts.insert(0, curr.title)

            full_path = "/".join(path_parts)

            # 如果 Joplin 中存在完全重名的路径，后找到的会覆盖前面的（这种情况极少）
            path_map[full_path] = nb.id

        self._path_map = path_map
        print(f"📊 路径索引构建完成，共计 {len(path_map)} 个有效路径。")

    def get_notebook_id_by_strict_path(self, path_str):
        """
        根据完整路径获取 ID。
        path_str 例如: "不惑少年/直播"
        """
        # 实时刷新或按需刷新，确保数据准确
        self._refresh_path_map()

        # 规范化路径输入，去掉首尾斜杠
        target_path = path_str.strip("/")

        note_id = self._path_map.get(target_path)
        if not note_id:
            raise FileNotFoundError(f"🚨 严格路径匹配失败: '{target_path}'。请检查 Joplin 中目录是否存在，或层级是否正确。")

        return note_id

    def get_or_create_tag(self, title):
        tags = self.api.get_all_tags()
        for t in tags:
            if t.title == title:
                return t.id
        return self.api.add_tag(title=title)

    def create_note(self, title, body, notebook_path, tags=[]):
        """
        核心方法：只有路径完全正确，才会写入。
        """
        try:
            # 1. $O(1)$ 查找 ID
            notebook_id = self.get_notebook_id_by_strict_path(notebook_path)

            # 2. 创建笔记
            note_id = self.api.add_note(title=title, body=body, parent_id=notebook_id)

            # 3. 关联标签
            for tag_name in tags:
                tag_id = self.get_or_create_tag(tag_name)
                self.api.add_tag_to_note(tag_id=tag_id, note_id=note_id)

            print(f"✨ 同步成功: [{notebook_path}] -> {title}")
            return note_id

        except FileNotFoundError as e:
            print(f"❌ 路径错误: {e}")
            return None
        except Exception as e:
            print(f"❌ 系统错误: {str(e)}")
            return None


if __name__ == "__main__":
    TOKEN = os.getenv("JOPLIN_TOKEN", "你的TOKEN")
    tools = JoplinToolbox(TOKEN)

    # 现在的调用非常安全且直观
    # 只要你传入完整的路径，它就能精准定位到那个唯一的 ID
    tools.create_note(
        title="石油危机专题_测试",
        body="这是测试内容",
        notebook_path="Project/stock/不惑少年/直播",
        tags=["石油"]
    )