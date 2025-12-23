"""
HTML 解析模块
解析 CanLII 网页内容
"""
from bs4 import BeautifulSoup
from typing import List, Dict, Optional
from utils.logger import logger
import re


class HTMLParser:
    """HTML 解析器"""
    
    @staticmethod
    def parse_statute_list_json(json_data: List[Dict]) -> List[Dict[str, str]]:
        """
        解析 JSON 格式的法规列表
        
        Args:
            json_data: JSON 数据列表
            
        Returns:
            List[Dict]: 法规列表
        """
        statutes = []
        try:
            logger.info(f"解析 JSON 数据，共 {len(json_data)} 条记录")
            
            for item in json_data:
                title = item.get('title', '')
                citation = item.get('citation', '')
                path = item.get('path', '')
                
                if path and not path.startswith('http'):
                    url = f"https://www.canlii.org{path}"
                else:
                    url = path
                
                # JSON return doesn't explicitly state 'is_active', but usually lists current ones.
                # 'status' field might be empty or 'repealed'.
                status = item.get('status', '').lower()
                is_active = 'repealed' not in status
                
                statutes.append({
                    'title': title,
                    'citation': citation,
                    'url': url,
                    'is_active': is_active
                })
                
            logger.info(f"成功解析 {len(statutes)} 个法规 (JSON)")
            
        except Exception as e:
            logger.error(f"解析 JSON 列表失败: {e}")
            
        return statutes

    @staticmethod
    def parse_statute_list(html_content: str) -> List[Dict[str, str]]:
        """
        从索引页解析所有法规链接 (HTML 模式 - 备用)
        
        Args:
            html_content: HTML 内容
            
        Returns:
            List[Dict]: 法规列表，每个字典包含:
                - title: 标题
                - citation: 引文
                - url: URL
        """
        statutes = []
        

        try:
            soup = BeautifulSoup(html_content, 'lxml')
            
            # 查找法规表格
            tbody = soup.find('tbody', id='legislationsContainer')
            if not tbody:
                logger.error("未找到法规列表容器")
                return statutes
            
            # 遍历所有行
            rows = tbody.find_all('tr')
            logger.info(f"找到 {len(rows)} 个法规行")
            
            for row in rows:
                try:
                    # 提取引文（始终是第一列）
                    tds = row.find_all('td')
                    citation = tds[0].get_text(strip=True) if tds else ''
                    
                    # 更加鲁棒的链接匹配：匹配 /ca/laws/stat/, /en/ab/laws/regu/, /fr/ca/laws/const/ 等
                    # 不再强制要求 class='canlii'，因为部分页面结构可能不同
                    link = row.find('a', href=re.compile(r'(/[a-z]{2})?/[a-z]{2}/laws/(stat|regu|const)/'))
                    
                    if link:
                        title = link.get_text(strip=True)
                        url = link.get('href', '')
                        
                        # 确保URL是完整的
                        if url and not url.startswith('http'):
                            url = f"https://www.canlii.org{url}"
                        
                        # 检查是否标记为"已废除/未生效" (Improved regex for status detection)
                        # Handles optional brackets and case-insensitivity
                        status_span = row.find('span', string=re.compile(r'\[?(Repealed|spent|not in force)\]?', re.IGNORECASE))
                        is_active = status_span is None
                        
                        statute = {
                            'title': title,
                            'citation': citation,
                            'url': url,
                            'is_active': is_active
                        }
                        statutes.append(statute)
                    elif len(rows) > 0 and len(statutes) == 0 and rows.index(row) < 5:
                        # 只在开始几行且没解析到东西时打印调试信息，避免日志爆炸
                        logger.debug(f"行匹配失败调试 [Row {rows.index(row)}]: {str(row)[:200]}...")
                        
                except Exception as e:
                    logger.warning(f"解析法规行失败: {e}")
                    continue
            
            logger.info(f"成功解析 {len(statutes)} 个法规")
            
        except Exception as e:
            logger.error(f"解析法规列表失败: {e}")
        
        return statutes
    
    @staticmethod
    def parse_statute_detail(html_content: str, source_url: str) -> Optional[Dict]:
        """
        从详情页解析法规内容
        
        Args:
            html_content: HTML 内容
            source_url: 来源URL
            
        Returns:
            Optional[Dict]: 法规数据，包含:
                - title: 标题
                - citation: 引文
                - content_html: HTML内容
                - content_text: 纯文本内容
                - source_url: 来源URL
        """
        try:
            soup = BeautifulSoup(html_content, 'lxml')
            
            # 提取标题
            title_tag = soup.find('h1', class_='canlii')
            if not title_tag:
                title_tag = soup.find('title')
            
            title = title_tag.get_text(strip=True) if title_tag else ''
            
            # 从标题中移除 "| CanLII" 后缀
            title = re.sub(r'\s*\|\s*CanLII\s*$', '', title)
            
            # 提取引文（从URL或页面内容）
            citation = HTMLParser._extract_citation(source_url, soup)
            
            # 提取主要内容
            main_content = soup.find('div', id='originalDocument')
            if not main_content:
                main_content = soup.find('div', class_='canliidocumentcontent')
            if not main_content:
                main_content = soup.find('div', id='mainContent')
            if not main_content:
                main_content = soup.find('div', class_='canliiContent')
            
            if not main_content:
                logger.error(f"未找到主要内容: {source_url}")
                return None
            
            # 清理内容
            cleaned_content = HTMLParser._clean_html_content(main_content)
            
            # 提取纯文本
            content_text = cleaned_content.get_text(separator='\n', strip=True)
            
            # 获取HTML字符串
            content_html = str(cleaned_content)
            
            statute_data = {
                'title': title,
                'citation': citation,
                'content_html': content_html,
                'content_text': content_text,
                'source_url': source_url
            }
            
            logger.debug(f"成功解析法规: {title}")
            return statute_data
            
        except Exception as e:
            logger.error(f"解析法规详情失败: {e}")
            logger.error(f"URL: {source_url}")
            return None
    
    @staticmethod
    def _extract_citation(url: str, soup: BeautifulSoup) -> str:
        """
        从URL或页面提取引文
        
        Args:
            url: 页面URL
            soup: BeautifulSoup对象
            
        Returns:
            str: 引文
        """
        # 尝试从URL提取
        # URL格式: .../stat/rsa-2000-c-a-1/latest/... 或 .../const/30---31-vict-c-3/...
        match = re.search(r'/(stat|regu|const)/([^/]+)/', url)
        if match:
            statute_id = match.group(2)
            # 转换为标准引文格式
            # rsa-2000-c-a-1 -> RSA 2000, c A-1
            citation = statute_id.upper().replace('-', ' ')
            # 在 'C' 前添加逗号
            citation = re.sub(r'\s+C\s+', ', c ', citation)
            return citation
        
        # 如果URL提取失败，尝试从页面内容提取
        # 这里可以添加更多提取逻辑
        
        return ''
    
    @staticmethod
    def _clean_html_content(content_tag) -> BeautifulSoup:
        """
        清理HTML内容，删除导航、脚本等无关元素
        
        Args:
            content_tag: BeautifulSoup标签对象
            
        Returns:
            BeautifulSoup: 清理后的内容
        """
        # 创建副本以避免修改原始对象
        cleaned = BeautifulSoup(str(content_tag), 'lxml')
        
        # 删除不需要的元素
        unwanted_selectors = [
            'header',
            'footer',
            'nav',
            'script',
            'style',
            '.d-print-none',  # 不打印的元素
            '#canlii-header',
            '#canlii-breadcrumbs',
            '#canlii-login',
            '#canlii-lang-toggler',
            '.collectionScopeLink',  # 信息图标链接
        ]
        
        for selector in unwanted_selectors:
            for element in cleaned.select(selector):
                element.decompose()
        
        return cleaned
