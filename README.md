# SCP 中文维基抓取器（SCP Wiki Scraper）

一个用于抓取 SCP 中文分部（Wikidot）页面内容的爬虫，支持单条与批量抓取，并将结果以 JSON 结构化输出。项目以 Jupyter Notebook 形式组织，便于阅读、调试与扩展。

- 目标站点：`http://scp-wiki-cn.wikidot.com/`
- 主要入口：SCP 项目页面，例如 `scp-001`、`scp-049` 等

## 功能特性
- 稳定抓取
  - 复用 `requests.Session`，配置重试与指数退避，连接池优化；自定义 User-Agent。
  - 解析器优先使用 `lxml`，不可用时自动回退到 `html.parser`。
  - 可通过 `VERBOSE` 变量开启/关闭调试日志。
- 信息提取
  - 标准字段解析：项目编号、项目等级（class）、特殊收容措施（containment）、描述（description）等，以及常见记录（附录、实验记录、访谈记录、事件记录、更新记录、历史、发现等）。
  - 系列号与项目名称：根据编号自动计算系列页，并从系列目录中提取项目名称。
  - 图片抓取：仅在主体内容区域提取图片，支持 `src`、`data-src`、`data-image`、`srcset` 等懒加载与多分辨率来源，并按 URL/alt/title 与 `SCP-xxx` 的相关性过滤。
  - 标签抓取：从页面标签中提取项目标签，并过滤掉通用等级类标签（如 safe、euclid、keter 等）。
  - 额外信息归档：对未归入标准字段的内容统一收纳到 `more_info` 字段中，避免丢失信息。
- 批量抓取与持久化
  - 通过设置 `start` 与 `end` 进行区间批量抓取，提供成功/失败统计与失败 ID 列表。
  - 将结果写入 `scp_database_cn.json`，UTF-8 编码、`ensure_ascii=False` 并缩进格式化，便于阅读与二次处理。

## 环境与依赖
- Python 3（推荐 3.8+）
- Jupyter Notebook
- 依赖库：
  - `requests`
  - `beautifulsoup4`
  - `lxml`（可选，但推荐用于更快的 HTML 解析）

安装示例（可选）：
```bash
pip install jupyter requests beautifulsoup4 lxml
```

## 快速开始
1. 打开并依次运行 Notebook：`SCP Wiki Scraper.ipynb` 中的各个代码单元。
   - 首个单元完成全局设置（Session、重试、解析器、日志、正则等）。
   - 随后为工具与解析函数（名称解析、系列页缓存、图片/标签提取、字段清洗等）。
2. 在“批量抓取”单元中设置抓取区间：
   - 修改 `start` 与 `end` 变量，例如：`start = 1`, `end = 50`。
   - 运行该单元后，会输出成功/失败统计与失败的 ID 列表（如有）。
3. 在“保存为 JSON”单元中运行写文件逻辑：
   - 默认输出到同目录下的 `scp_database_cn.json`。
4. 可选：使用辅助函数仅分析某条目的相关图片：
   - 例如运行 `analyze_images(49)` 将打印与 SCP-049 相关的图片 URL 列表。

## 输出数据结构（示例）
单条记录的典型结构如下（字段可能因页面结构差异而变化）：
```json
{
  "series": 1,
  "name": "瘟疫医生",
  "class": "Euclid",
  "containment": "……",
  "description": "……",
  "images": [
    "https://example.com/local--files/scp-049/xxx.jpg"
  ],
  "tags": ["医学", "人形", "异常"],
  "more_info": {
    "实验记录：": "……",
    "访谈记录：": "……"
  }
}
```
说明：
- `series`：根据编号自动计算得到的系列号（1-9）。
- `name`：从对应系列页的目录中解析到的项目中文名称（尽力匹配）。
- `images`：与条目强相关的图片 URL 列表，仅限常见图片扩展名。
- `tags`：过滤掉通用等级标签后的项目标签集合。
- `more_info`：其余无法归入标准字段的信息，按原区块名聚合，便于后续处理。
- 当未能解析出标准字段时，会附带 `warning` 字段提示。

## 注意与建议
- 尊重目标站点的使用条款与 robots 协议，合理控制抓取频率。
- 已内置对 429/5xx 的重试与退避，但若频繁失败，请适当减少抓取量或延长间隔。
- 站点页面结构可能随时间变化，如遇大面积字段缺失，请检查并调整解析逻辑。

## 许可证
请参考仓库内的 `LICENSE` 文件。原仓库版权与条款请遵循其要求。
