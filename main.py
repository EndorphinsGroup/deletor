import vk_api
import requests
import time
import os
import re
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- НАСТРОЙКИ ---
TOKEN = os.getenv('VK_TOKEN')
GROUP_NAMES = ['givepromo', 'anton_kupon'] 

# СТРОГО 2 МЕСЯЦА: 
# Если сегодня 13 мая, то посты от 14 марта и свежее НЕ удалятся.
MONTHS_OFFSET = 2 

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
}

def expand_url(url):
    """Глубокая проверка сокращенной ссылки на erid"""
    url = url.strip('.,()[]"\'')
    if 'erid' in url.lower():
        return True
    
    try:
        # Используем GET для прохода через все рекламные редиректы
        response = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=10)
        final_url = response.url.lower()
        
        if 'erid' in final_url or '%26erid' in final_url or 'erid%3d' in final_url:
            return True
    except:
        pass
    return False

def get_group_id(vk, screen_name):
    try:
        res = vk.utils.resolveScreenName(screen_name=screen_name)
        if res and res['type'] == 'group':
            return -res['object_id']
    except: pass
    return None

def process_wall():
    if not TOKEN:
        print("Ошибка: VK_TOKEN не найден в Secrets!")
        return

    vk_session = vk_api.VkApi(token=TOKEN)
    vk = vk_session.get_api()

    # Вычисляем дату-отсечку
    now = datetime.now()
    threshold_date = now - relativedelta(months=MONTHS_OFFSET)

    print(f"--- ЗАПУСК ОЧИСТКИ ---")
    print(f"Сегодня: {now.strftime('%Y-%m-%d %H:%M')}")
    print(f"Удаляем рекламу ТОЛЬКО СТАРШЕ, ЧЕМ: {threshold_date.strftime('%Y-%m-%d %H:%M')}")
    print(f"(Все посты новее этой даты останутся нетронутыми)")

    for name in GROUP_NAMES:
        group_id = get_group_id(vk, name)
        if not group_id: continue
        
        print(f"\n>>> Проверка группы: {name}")
        offset = 0
        deleted_count = 0

        while True:
            try:
                response = vk.wall.get(owner_id=group_id, offset=offset, count=100)
                posts = response.get('items', [])
                if not posts: break
                
                for post in posts:
                    post_date = datetime.fromtimestamp(post['date'])
                    
                    # ПРОВЕРКА ДАТЫ: если пост старый (меньше или равен дате-отсечке)
                    if post_date <= threshold_date:
                        post_id = post['id']
                        text = post.get('text', '')
                        found_erid = False

                        # 1. Текст
                        if 'erid' in text.lower() or 'ерид' in text.lower():
                            found_erid = True
                        
                        # 2. Ссылки в тексте (даже сокращенные)
                        if not found_erid:
                            urls = re.findall(r'(https?://[^\s<>"]+)', text)
                            for u in urls:
                                if expand_url(u):
                                    found_erid = True
                                    break
                        
                        # 3. Кнопки и карточки
                        if not found_erid and 'attachments' in post:
                            for attach in post['attachments']:
                                if attach['type'] == 'link':
                                    if expand_url(attach['link']['url']):
                                        found_erid = True
                                        break

                        if found_erid:
                            try:
                                vk.wall.delete(owner_id=group_id, post_id=post_id)
                                print(f"   [УДАЛЕНО] Пост {post_id} от {post_date.strftime('%Y-%m-%d')}")
                                deleted_count += 1
                                time.sleep(0.5)
                            except Exception as e:
                                print(f"   Ошибка удаления {post_id}: {e}")
                    
                offset += 100
                # Если текущая пачка постов уже свежее порога, и мы не в начале, 
                # можно было бы прерваться, но в ВК посты могут идти не по порядку (закрепы),
                # поэтому надежнее просмотреть все.
                if len(posts) < 100: break
            except Exception as e:
                print(f"Ошибка API: {e}")
                break

        print(f"Итог по {name}: удалено {deleted_count} рекламных постов.")

if __name__ == "__main__":
    process_wall()
