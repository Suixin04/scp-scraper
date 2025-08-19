"""
SCP 解析器模块 - 提供统一的字段提取、映射、去重和标准化功能
"""
import re
from typing import Dict, Any, List, Set


class SCPParser:
    """SCP 页面内容解析器"""
    
    # 标准字段映射 - 包含简体、繁体和常见同义写法
    FIELD_MAPPING = {
        # 项目编号
        '项目编号': 'id',
        '項目編號': 'id',
        '编号': 'id',
        '編號': 'id',
        'scp编号': 'id',
        'scp編號': 'id',
        'item #': 'id',
        'item number': 'id',
        
        # 项目等级
        '项目等级': 'class',
        '項目等級': 'class',
        '等级': 'class',
        '等級': 'class',
        '对象等级': 'class',
        '對象等級': 'class',
        'object class': 'class',
        'classification': 'class',
        
        # 特殊收容措施
        '特殊收容措施': 'containment',
        '特殊收容程序': 'containment',
        '收容措施': 'containment',
        '收容程序': 'containment',
        '收容': 'containment',
        'special containment procedures': 'containment',
        'containment': 'containment',
        'containment procedures': 'containment',
        
        # 描述
        '描述': 'description',
        '項目描述': 'description',
        '项目描述': 'description',
        '说明': 'description',
        '詳述': 'description',
        'description': 'description',
        
        # 附录和记录类
        '附录': 'addendum',
        '附錄': 'addendum',
        '实验记录': 'experiment_log',
        '實驗記錄': 'experiment_log',
        '访谈记录': 'interview_log',
        '訪談記錄': 'interview_log',
        '事件记录': 'incident_log',
        '事件記錄': 'incident_log',
        '更新记录': 'update_log',
        '更新記錄': 'update_log',
        '历史': 'history',
        '歷史': 'history',
        '发现': 'discovery',
        '發現': 'discovery',
        '註': 'notes',
        '注': 'notes',
        '备注': 'notes',
        '記錄開始': 'record_start',
        '记录开始': 'record_start',
        '記錄結束': 'record_end',
        '记录结束': 'record_end',
    }
    
    # 标准字段列表
    STANDARD_FIELDS = [
        'id', 'class', 'description', 'containment', 'addendum',
        'experiment_log', 'interview_log', 'incident_log', 
        'update_log', 'history', 'discovery', 'notes',
        'error', 'warning', 'series', 'name', 'images', 'tags'
    ]
    
    # 正则表达式
    RE_REDACT = re.compile(r'\[数据删除\]|\[资料删除\]|\[已编辑\]|\[删除\]|\[REDACTED\]|\[DATA EXPUNGED\]', re.IGNORECASE)
    RE_WS = re.compile(r'\s+')
    RE_COLON_PREFIX = re.compile(r'^[：:]\s*')
    
    def __init__(self):
        self.stop_indicators = ['«', '‹', '附录', '实验记录', '访谈记录', '事件记录']
    
    def normalize_key(self, key: str) -> str:
        """标准化字段键名"""
        if not key:
            return ''
        
        # 移除前后空白和标点
        key = key.strip().rstrip('：:')
        
        # 转换为小写进行匹配
        key_lower = key.lower()
        
        # 查找映射
        for pattern, standard_key in self.FIELD_MAPPING.items():
            if pattern.lower() == key_lower:
                return standard_key
        
        # 如果没有找到映射，返回清理后的原键名
        return re.sub(r'[^\w\u4e00-\u9fff]', '_', key).lower()
    
    def clean_value(self, value: str) -> str:
        """清理字段值"""
        if not value:
            return ''
        
        # 替换敏感信息标记
        value = self.RE_REDACT.sub('[REDACTED]', value)
        # 规范化空白字符
        value = self.RE_WS.sub(' ', value)
        # 移除前导冒号
        value = self.RE_COLON_PREFIX.sub('', value)
        
        return value.strip()
    
    def deduplicate_content(self, content: str) -> str:
        """去除内容中的重复段落"""
        if not content:
            return content
        
        # 按句号分割段落
        sentences = [s.strip() for s in content.split('。') if s.strip()]
        
        # 去重（保持顺序）
        seen = set()
        unique_sentences = []
        for sentence in sentences:
            if sentence not in seen and len(sentence) > 5:  # 忽略过短的片段
                seen.add(sentence)
                unique_sentences.append(sentence)
        
        return '。'.join(unique_sentences) + ('。' if unique_sentences else '')
    
    def extract_id_from_url(self, url: str) -> str:
        """从 URL 中提取 SCP 编号"""
        match = re.search(r'scp-(\d+)', url, re.IGNORECASE)
        if match:
            return f"SCP-{match.group(1).zfill(3)}"
        return ''
    
    def ensure_required_fields(self, data: Dict[str, Any], scp_id: int, url: str = '') -> Dict[str, Any]:
        """确保必要字段存在"""
        result = data.copy()
        
        # 确保有 id 字段
        if 'id' not in result or not result['id']:
            if url:
                extracted_id = self.extract_id_from_url(url)
                if extracted_id:
                    result['id'] = extracted_id
                else:
                    result['id'] = f"SCP-{scp_id:03d}"
            else:
                result['id'] = f"SCP-{scp_id:03d}"
        
        # 去重主要字段内容
        for field in ['description', 'containment']:
            if field in result and isinstance(result[field], str):
                result[field] = self.deduplicate_content(result[field])
        
        return result
    
    def categorize_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """将所有字段扁平化到顶级，不再使用 more_info 嵌套结构"""
        result = {}
        
        # 如果已经存在 more_info，先提取其内容并扁平化
        existing_more_info = data.get('more_info', {})
        if isinstance(existing_more_info, dict):
            for key, value in existing_more_info.items():
                normalized_key = self.normalize_key(key)
                result[normalized_key] = value
        
        # 处理所有其他字段
        for key, value in data.items():
            if key != 'more_info':  # 跳过 more_info 字段，因为已经处理过了
                # 标准化键名
                normalized_key = self.normalize_key(key)
                result[normalized_key] = value
        
        return result
    
    def parse_page_content(self, elements: List, scp_id: int, url: str = '') -> Dict[str, Any]:
        """解析页面内容元素，提取字段信息"""
        result = {}
        current_key = None
        current_value = ''
        
        for element in elements:
            element_text = element.get_text().strip()
            
            # 跳过空元素
            if not element_text:
                continue
            
            # 检查是否应该停止解析主要内容
            if any(indicator in element_text for indicator in self.stop_indicators[:2]):
                if element_text.startswith(('«', '‹')):
                    break
            
            # 查找强调标签（字段名）
            strong_tag = element.find('strong')
            
            if strong_tag:
                # 保存上一个字段
                if current_key:
                    normalized_key = self.normalize_key(current_key)
                    cleaned_value = self.clean_value(current_value)
                    if normalized_key and cleaned_value:
                        result[normalized_key] = cleaned_value
                
                # 开始新字段
                current_key = strong_tag.get_text().strip()
                # 获取字段值（去掉字段名部分）
                current_value = element_text[len(current_key):].strip()
            else:
                # 如果当前有字段在处理，添加到其值中
                if current_key:
                    if current_value and not current_value.endswith(' '):
                        current_value += ' '
                    current_value += element_text
        
        # 处理最后一个字段
        if current_key:
            normalized_key = self.normalize_key(current_key)
            cleaned_value = self.clean_value(current_value)
            if normalized_key and cleaned_value:
                result[normalized_key] = cleaned_value
        
        # 确保必要字段存在
        result = self.ensure_required_fields(result, scp_id, url)
        
        # 字段分类
        result = self.categorize_fields(result)
        
        return result


class SCPValidator:
    """SCP 数据验证器"""
    
    REQUIRED_FIELDS = ['id']
    RECOMMENDED_FIELDS = ['class', 'containment', 'description']
    
    @staticmethod
    def validate(data: Dict[str, Any]) -> Dict[str, Any]:
        """验证 SCP 数据完整性"""
        issues = []
        
        # 检查必需字段
        for field in SCPValidator.REQUIRED_FIELDS:
            if field not in data or not data[field]:
                issues.append(f"缺少必需字段: {field}")
        
        # 检查推荐字段
        missing_recommended = []
        for field in SCPValidator.RECOMMENDED_FIELDS:
            if field not in data or not data[field]:
                missing_recommended.append(field)
        
        if missing_recommended:
            issues.append(f"缺少推荐字段: {', '.join(missing_recommended)}")
        
        # 添加验证结果
        if issues:
            data['validation_issues'] = issues
        
        return data