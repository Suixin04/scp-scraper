# imports 和全局设置 cell
import requests
from bs4 import BeautifulSoup
import json
import re
from functools import lru_cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import urljoin
import concurrent.futures
import time

# 导入新的解析器模块
from scp_parser import SCPParser, SCPValidator

# 优先使用 lxml，加速解析；不可用则回退
try:
    import lxml  # 仅用于检查是否可用
    BS_PARSER = 'lxml'
except Exception:
    BS_PARSER = 'html.parser'

# 复用 Session + 重试策略 + 连接池
session = requests.Session()
retry_strategy = Retry(
    total=3,
    connect=3,
    read=3,
    backoff_factor=0.5,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
    raise_on_status=False,
)
adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=20, pool_maxsize=20)
session.mount("http://", adapter)
session.mount("https://", adapter)
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})

# 可控日志
VERBOSE = False
def vprint(*args, **kwargs):
    if VERBOSE:
        print(*args, **kwargs)

# 在第一个cell中添加预编译正则
# 预编译正则
RE_REDACT = re.compile('\u2588+')
RE_WS = re.compile(r'\s+')
RE_CLEAN_NAME = re.compile(r'[·•].*$')  # 新增：清理名称的正则

IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg')

base_url = "http://scp-wiki-cn.wikidot.com/scp-"

def analyze_images(scp_id: int):
    """分析页面中的图片并打印与项目相关的图片URL"""
    urls = get_scp_images(scp_id)
    print(f"SCP-{scp_id:03d} 相关图片共 {len(urls)} 张：")
    for i, u in enumerate(urls, 1):
        print(f"{i}. {u}")
def _extract_urls_from_img(img_tag):
    """从单个 <img> 标签收集所有可能的图片URL"""
    urls = set()
    # 直接 src
    src = (img_tag.get('src') or '').strip()
    if src:
        urls.add(src)
    # 懒加载常见属性
    for attr in ('data-src', 'data-image'):
        val = (img_tag.get(attr) or '').strip()
        if val:
            urls.add(val)
    # srcset: 可能包含多条，以逗号分隔，形如 "url w, url2 w"
    srcset = (img_tag.get('srcset') or '').strip()
    if srcset:
        for part in srcset.split(','):
            p = part.strip().split(' ')[0].strip()
            if p:
                urls.add(p)
    return list(urls)

def _normalize_and_filter_urls(urls, page_url):
    """标准化为绝对URL并过滤非图片/无效链接"""
    abs_urls = []
    for u in urls:
        full = urljoin(page_url, u)
        # 只接受 http/https
        if not (full.startswith('http://') or full.startswith('https://')):
            continue
        # 过滤常见静态文件外的资源，限制为图片扩展名
        lower = full.lower()
        if any(lower.endswith(ext) for ext in IMAGE_EXTS):
            abs_urls.append(full)
    return abs_urls

def _is_relevant_image(url, alt, title, scp_id_formatted):
    """根据URL/alt/title 判断是否与SCP项目相关（优化版）"""
    # 使用更高效的字符串操作
    url_lower = url.lower() if url else ''
    
    # 优先检查最可能的匹配
    if f"scp-{scp_id_formatted}" in url_lower:
        return True
    if 'scp' in url_lower:
        return True
    
    # 检查alt和title（通常较短，检查成本低）
    if alt or title:
        alt_lower = alt.lower() if alt else ''
        title_lower = title.lower() if title else ''
        if 'scp' in alt_lower or 'scp' in title_lower:
            return True
    
    return False

def analyze_images(scp_id: int):
    """分析页面中的图片并打印与项目相关的图片URL"""
    _id = harmonize_id(scp_id)
    page_url = base_url + _id
    try:
        resp = session.get(page_url, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.content, BS_PARSER)
        page_content = soup.find('div', id='page-content')
        urls = extract_images_from_soup(soup, page_content, scp_id, resp.url)
    except Exception as e:
        vprint(f"获取页面失败 {page_url}: {e}")
        urls = []
    
    print(f"SCP-{scp_id:03d} 相关图片共 {len(urls)} 张：")
    for i, u in enumerate(urls, 1):
        print(f"{i}. {u}")
def harmonize_id(_id: int) -> str:
    # 使用zfill()方法将数字填充为3位字符串
    # zfill性能优于字符串拼接,因为它是C实现的内置方法
    return str(_id).zfill(3)

def get_series_number(_id: int) -> int:
    """根据项目编号计算所属系列
    
    Args:
        _id: SCP项目编号
        
    Returns:
        系列编号 (1-9)
    """
    # 系列计算公式：项目编号除以1000取整+1
    series = (_id // 1000) + 1
    return max(1, min(series, 9))  # 限制在1-9范围内

def get_series_url(series_number: int) -> str:
    """根据系列编号获取系列页面URL
    
    Args:
        series_number: 系列编号 (1-9)
        
    Returns:
        系列页面的URL
    """
    base_series_url = "http://scp-wiki-cn.wikidot.com/scp-series"
    if series_number == 1:
        return base_series_url
    else:
        return f"{base_series_url}-{series_number}"

@lru_cache(maxsize=16)
def fetch_series_page(series_number: int) -> bytes:
    """缓存系列页 HTML，减少重复请求"""
    url = get_series_url(series_number)
    try:
        resp = session.get(url, timeout=10)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        vprint(f"获取系列页失败 {url}: {e}")
        return b""

def extract_images_from_soup(soup, page_content, scp_id, page_url):
    """从已解析的soup中提取图片，避免重复请求和解析"""
    if not page_content:
        return []

    scp_id_formatted = harmonize_id(scp_id)
    ordered, seen = [], set()

    # 只在主体内容区域中找图片
    imgs = page_content.find_all('img')
    for img in imgs:
        candidates = _extract_urls_from_img(img)
        normalized = _normalize_and_filter_urls(candidates, page_url)
        alt = img.get('alt') or ''
        title = img.get('title') or ''
        for u in normalized:
            if _is_relevant_image(u, alt, title, scp_id_formatted):
                if u not in seen:
                    seen.add(u)
                    ordered.append(u)

    return ordered

# 在extract_images_from_soup函数之后添加新的代码单元格
def extract_tags_from_soup(soup, page_content):
    """从已解析的soup中提取SCP项目的标签信息，并过滤掉不需要的标签"""
    if not soup:
        return []
    
    tags = []
    
    # 定义需要过滤的标签（不区分大小写）
    filtered_tags = {
        'scp', 'safe', 'euclid', 'keter', 'thaumiel', 'apollyon', 
        'archon', 'neutralized', 'explained', 'decommissioned'
    }
    
    # 查找页面标签容器
    page_tags_div = soup.find('div', class_='page-tags')
    if page_tags_div:
        # 在标签容器中查找所有链接
        tag_links = page_tags_div.find_all('a')
        for link in tag_links:
            tag_text = link.get_text().strip()
            if tag_text and tag_text.lower() not in filtered_tags and tag_text not in tags:
                tags.append(tag_text)
    
    # 如果没有找到标签容器，尝试在页面内容中查找标签链接
    if not tags and page_content:
        # 查找可能的标签链接（通常以/tag/开头）
        tag_links = page_content.find_all('a', href=True)
        for link in tag_links:
            href = link.get('href', '')
            if '/tag/' in href:
                tag_text = link.get_text().strip()
                if tag_text and tag_text.lower() not in filtered_tags and tag_text not in tags:
                    tags.append(tag_text)
    
    return tags
def get_scp_name_from_series(_id: int) -> str:
    """从系列页面获取SCP项目名称（优化版）"""
    try:
        series_number = get_series_number(_id)
        content = fetch_series_page(series_number)
        if not content:
            return ""

        soup = BeautifulSoup(content, BS_PARSER)

        # 查找包含SCP编号的链接
        scp_id_formatted = harmonize_id(_id)
        scp_link_pattern = f"scp-{scp_id_formatted}"

        # 在页面中查找匹配的SCP链接
        links = soup.find_all('a', href=True)
        for link in links:
            if scp_link_pattern in link.get('href', ''):
                # 获取链接文本，通常格式为 "SCP-XXX - 名称"
                link_text = link.get_text().strip()
                if ' - ' in link_text:
                    # 提取名称部分（去掉SCP-XXX部分）
                    name_part = link_text.split(' - ', 1)[1].strip()
                    return name_part

        # 如果没有找到，尝试在文本中直接搜索
        page_text = soup.get_text()
        lines = page_text.split('\n')
        for line in lines:
            if f"SCP-{scp_id_formatted}" in line and ' - ' in line:
                parts = line.split(' - ', 1)
                if len(parts) > 1:
                    name_part = parts[1].strip()
                    # 使用预编译正则清理可能的额外字符
                    name_part = RE_CLEAN_NAME.sub('', name_part).strip()
                    if name_part:
                        return name_part

        return ""  # 未找到名称

    except Exception as e:
        vprint(f"获取SCP-{_id}名称时出错: {str(e)}")
        return ""
def affix_additional(results):
    """扁平化所有字段，将 more_info 内容提取到顶级"""
    _results = results.copy()
    
    # 如果已经存在 more_info，将其内容扁平化到顶级
    if 'more_info' in _results:
        existing_more_info = _results['more_info']
        if isinstance(existing_more_info, dict):
            # 将 more_info 中的内容合并到顶级
            for key, value in existing_more_info.items():
                if key not in _results:  # 避免覆盖已有的顶级字段
                    _results[key] = value
            # 删除 more_info 字段
            del _results['more_info']
    
    return _results
# 函数：scrape_scp（优化连接、解析与日志）
def scrape_scp(id):
    """改进的SCP爬取函数，增强错误处理和解析逻辑，包含系列、名称与图片信息"""
    result_dict = {}
    _id = harmonize_id(id)
    url = base_url + _id

    # 获取项目系列和名称
    series_number = get_series_number(id)
    scp_name = get_scp_name_from_series(id)

    # 添加系列和名称到结果中
    result_dict['series'] = series_number
    if scp_name:
        result_dict['name'] = scp_name

    # 先放入兜底的 id（标准格式），解析器会根据页面解析再覆盖或保持
    result_dict['id'] = f"SCP-{id:03d}"

    try:
        # 复用全局 session（含UA与重试）
        response = session.get(url, timeout=10)
        response.raise_for_status()  # 检查HTTP状态码
        vprint(f"成功访问: {url}")

    except requests.RequestException as e:
        vprint(f"请求失败 {url}: {str(e)}")
        return {'error': f'请求失败: {str(e)}'}

    soup = BeautifulSoup(response.content, BS_PARSER)
    page_content = soup.find('div', id='page-content')

    if not page_content:
        vprint(f"未找到页面内容: {url}")
        return {'error': '未找到页面内容'}

    # 获取所有可能包含信息的元素，不仅仅是p标签
    elements = page_content.find_all(['p', 'div', 'blockquote'])

    # 使用通用解析器解析字段
    parser = SCPParser()
    parsed = parser.parse_page_content(elements, id, response.url)

    # 合并解析结果
    result_dict.update(parsed)

    # 优化：复用已获取的soup和page_content来提取图片，避免重复请求
    images = extract_images_from_soup(soup, page_content, id, response.url)
    if images:
        result_dict['images'] = images

    # 提取标签信息
    tags = extract_tags_from_soup(soup, page_content)
    if tags:
        result_dict['tags'] = tags

    # 如果没有提取到任何有效字段
    if not result_dict or all(key == 'error' for key in result_dict.keys()):
        vprint(f"警告: 未能提取到有效字段 {url}")
        result_dict['warning'] = '未能提取到标准SCP字段'

    result_dict = affix_additional(result_dict)

    # 使用验证器检查并标注问题
    result_dict = SCPValidator.validate(result_dict)

    return result_dict

# --- Main Execution ---
if __name__ == "__main__":
    db = {}
    
    # --- 多线程爬取 ---
    start_id = 1
    end_id = 9999
    max_workers = 8  # 可以根据网络和CPU调整

    failed_ids = []
    
    start_time = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 创建future到id的映射
        future_to_id = {executor.submit(scrape_scp, i): i for i in range(start_id, end_id + 1)}
        
        for i, future in enumerate(concurrent.futures.as_completed(future_to_id), 1):
            scp_id = future_to_id[future]
            try:
                data = future.result()
                if data and 'error' not in data:
                    db[str(scp_id)] = data
                    print(f"({i}/{end_id-start_id+1}) 成功: SCP-{scp_id:03d}")
                else:
                    failed_ids.append(scp_id)
                    print(f"({i}/{end_id-start_id+1}) 失败: SCP-{scp_id:03d} - {data.get('error', '未知错误')}")
            except Exception as exc:
                failed_ids.append(scp_id)
                print(f"({i}/{end_id-start_id+1}) 异常: SCP-{scp_id:03d} - {exc}")

    end_time = time.time()
    
    # --- 结果处理 ---
    # 写入数据库文件
    try:
        with open('scp_database_cn.json', 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=4)
    except IOError as e:
        print(f"写入文件失败: {e}")

    print("\n=== 爬取完成 ===")
    print(f"耗时: {end_time - start_time:.2f} 秒")
    print(f"成功: {len(db)} 个")
    print(f"失败: {len(failed_ids)} 个")
    if failed_ids:
        print(f"失败的ID: {sorted(failed_ids)}")