"""
验证数据库中的法规数据
检查最近保存的法规是否包含有效内容
"""
from scraper.supabase_client import SupabaseClient
from utils.logger import logger

def verify_data():
    client = SupabaseClient()
    
    print("\n--- 正在查询最近的法规数据 ---")
    
    # 获取最近的 5 条记录
    try:
        response = client.client.table('ab_statutes').select('*').order('last_updated', desc=True).limit(5).execute()
        rows = response.data
        
        print(f"找到 {len(rows)} 条记录:\n")
        
        for row in rows:
            title = row.get('title', 'Unknown')
            citation = row.get('citation', 'Unknown')
            html_len = len(row.get('content_html', '') or '')
            text_len = len(row.get('content_text', '') or '')
            url = row.get('source_url', '')
            
            print(f"标题: {title}")
            print(f"引文: {citation}")
            print(f"HTML 长度: {html_len} 字符")
            print(f"文本长度: {text_len} 字符")
            print(f"URL: {url}")
            
            if html_len < 100 or text_len < 100:
                print("⚠️ 警告: 内容似乎为空或过短！")
            else:
                print("✅ 内容看起来有效")
            print("-" * 50)
            
    except Exception as e:
        print(f"查询失败: {e}")

if __name__ == "__main__":
    verify_data()
