import vk_api
import requests
import time
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- НАСТРОЙКИ ---
# Токен берем из переменных окружения GitHub (для безопасности)
TOKEN = os.getenv('VK_TOKEN')
# Короткие имена ваших групп
GROUP_NAMES = ['givepromo', 'anton_kupon'] 
MONTHS_OFFSET = 2 

def expand_url(url):
    """Разворачивает сокращенную ссылку и проверяет на erid"""
    try:
        # Проверяем, не является ли ссылка сразу рекламой
        if 'erid' in url.lower():
            return True
        
        # Если ссылка сокращенная, идем по редиректу
        # Используем head, чтобы не скачивать всю страницу
        response = requests.head(url, allow_redirects=True, timeout=5)
        full_url = response.url.lower()
        return 'erid' in full_url
    except Exception:
        return False

def get_group_id(vk, screen_name):
    """Преобразует короткое имя в числовой ID с минусом"""
    res = vk.utils.resolveScreenName(screen_name=screen_name)
    if res and res['type'] == 'group':
        return -res['object_id']
    return None

def process_wall():
    if not TOKEN:
        print("Ошибка: VK_TOKEN не найден в секретах GitHub!")
        return

    vk_session = vk_api.VkApi(token=TOKEN)
    vk = vk_session.get_api()

    for name in GROUP_NAMES:
        group_id = get_group_id(vk, name)
        if not group_id:
            print(f"Не удалось найти группу: {name}")
            continue
        
        print(f"\n>>> Обработка группы: {name} ({group_id})")

        # 1. Получаем дату последнего поста
        wall = vk.wall.get(owner_id=group_id, count=1)
        if not wall['items']:
            continue
        
        latest_date = datetime.fromtimestamp(wall['items'][0]['date'])
        # Вычисляем порог (например, от 7 мая до 7 марта)
        threshold_date = latest_date - relativedelta(months=MONTHS_OFFSET)
        
        print(f"Последний пост от: {latest_date}")
        print(f"Будем проверять посты старше: {threshold_date}")

        offset = 0
        deleted_count = 0

        while True:
            # Получаем посты порциями по 100
            posts = vk.wall.get(owner_id=group_id, offset=offset, count=100)['items']
            if not posts:
                break
            
            for post in posts:
                post_date = datetime.fromtimestamp(post['date'])
                
                # Если пост старше (меньше) нашей даты
                if post_date <= threshold_date:
                    post_id = post['id']
                    text = post.get('text', '')
                    found_erid = False

                    # Ищем erid в тексте
                    if 'erid' in text.lower():
                        found_erid = True
                    
                    # Если в тексте нет, проверяем все ссылки внутри текста
                    if not found_erid:
                        words = text.split()
                        for word in words:
                            if word.startswith('http'):
                                if expand_url(word):
                                    found_erid = True
                                    break
                    
                    # Если всё еще нет, проверяем вложения (кнопки-ссылки)
                    if not found_erid and 'attachments' in post:
                        for attach in post['attachments']:
                            if attach['type'] == 'link':
                                if expand_url(attach['link']['url']):
                                    found_erid = True
                                    break

                    # Если нашли erid — удаляем
                    if found_erid:
                        try:
                            vk.wall.delete(owner_id=group_id, post_id=post_id)
                            print(f"[УДАЛЕНО] Пост ID {post_id} от {post_date} (найден erid)")
                            deleted_count += 1
                            time.sleep(0.4) # Защита от лимитов ВК
                        except Exception as e:
                            print(f"Ошибка удаления {post_id}: {e}")
                
            offset += 100
            # Если дата текущего поста в цикле уже сильно свежее порога, и мы в начале
            # Но так как wall.get выдает от новых к старым, нам нужно пролистать до старых.
            if post_date > threshold_date and len(posts) < 100:
                break

        print(f"Итог по группе {name}: удалено {deleted_count} постов.")

if __name__ == "__main__":
    process_wall()
