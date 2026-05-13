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
MONTHS_OFFSET = 2 

# Сессия для ускорения запросов и кэш ссылок
session = requests.Session()
session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'})
URL_CACHE = {}

def expand_url(url):
    """Проверка сокращенной ссылки на erid"""
    url = url.strip('.,()[]"\'')
    if 'erid' in url.lower(): return True
    if url in URL_CACHE: return URL_CACHE[url]
    
    try:
        # Пытаемся быстро получить финальный URL
        resp = session.get(url, allow_redirects=True, timeout=5, stream=True)
        final_url = resp.url.lower()
        resp.close()
        found = any(x in final_url for x in ['erid', '%26erid', 'erid%3d'])
        URL_CACHE[url] = found
        return found
    except:
        URL_CACHE[url] = False
        return False

def process_wall():
    if not TOKEN:
        print("Ошибка: VK_TOKEN не найден!")
        return

    vk = vk_api.VkApi(token=TOKEN).get_api()
    now = datetime.now()
    threshold_date = now - relativedelta(months=MONTHS_OFFSET)

    print(f"=== ЗАПУСК БОТА ===")
    print(f"Сегодня: {now.strftime('%d.%m.%Y %H:%M')}")
    print(f"Порог (не трогаем новее): {threshold_date.strftime('%d.%m.%Y %H:%M')}")

    for name in GROUP_NAMES:
        print(f"\n>>> НАЧИНАЕМ ОБРАБОТКУ ГРУППЫ: {name}")
        
        # Получаем ID группы
        try:
            res = vk.utils.resolveScreenName(screen_name=name)
            group_id = -res['object_id']
        except:
            print(f"!!! Не удалось найти группу {name}")
            continue

        offset = 0
        total_deleted = 0
        total_checked = 0

        while True:
            try:
                response = vk.wall.get(owner_id=group_id, offset=offset, count=100)
                posts = response.get('items', [])
                if not posts: break
                
                for post in posts:
                    total_checked += 1
                    post_date = datetime.fromtimestamp(post['date'])
                    post_id = post['id']
                    
                    # 1. Проверка даты
                    if post_date > threshold_date:
                        # Пост слишком свежий
                        status = "СВЕЖИЙ (пропуск)"
                    else:
                        # Пост старый, ищем рекламу
                        text = post.get('text', '')
                        found_erid = False
                        reason = ""

                        # Поиск в тексте
                        if 'erid' in text.lower() or 'ерид' in text.lower():
                            found_erid = True
                            reason = "erid в тексте"
                        
                        # Поиск в ссылках
                        if not found_erid:
                            urls = re.findall(r'(https?://[^\s<>"]+)', text)
                            for u in urls:
                                if expand_url(u):
                                    found_erid = True
                                    reason = f"erid в ссылке {u[:30]}..."
                                    break
                        
                        # Поиск во вложениях
                        if not found_erid and 'attachments' in post:
                            for attach in post['attachments']:
                                if attach['type'] == 'link':
                                    if expand_url(attach['link']['url']):
                                        found_erid = True
                                        reason = "erid в кнопке/ссылке"
                                        break

                        if found_erid:
                            try:
                                vk.wall.delete(owner_id=group_id, post_id=post_id)
                                status = f"УДАЛЕН ({reason})"
                                total_deleted += 1
                                time.sleep(0.3)
                            except:
                                status = "ОШИБКА УДАЛЕНИЯ"
                        else:
                            status = "ОК (нет рекламы)"

                    # Выводим лог каждые 10 постов
                    if total_checked % 10 == 0:
                        print(f"   [{total_checked}] Пост {post_id} от {post_date.strftime('%d.%m')}: {status}")

                offset += 100
                # Ограничение, чтобы не сканировать вечность (последние 1500 постов)
                if total_checked >= 1500 or len(posts) < 100:
                    break
            except Exception as e:
                print(f"Ошибка при чтении стены: {e}")
                break

        print(f"--- Итог по {name}: Проверено {total_checked}, Удалено {total_deleted}")

if __name__ == "__main__":
    process_wall()
