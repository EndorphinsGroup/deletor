import vk_api
import requests
import time
import os
from datetime import datetime
from dateutil.relativedelta import relativedelta

# --- НАСТРОЙКИ ---
# Токен берем из секретов GitHub
TOKEN = os.getenv('VK_TOKEN')
# Список групп
GROUP_NAMES = ['givepromo', 'anton_kupon'] 
# На сколько месяцев назад откатываемся для проверки
MONTHS_OFFSET = 2 

def expand_url(url):
    """Разворачивает сокращенную ссылку и проверяет на erid"""
    try:
        if 'erid' in url.lower():
            return True
        # Проверяем редирект (timeout 5 сек чтобы не зависнуть)
        response = requests.head(url, allow_redirects=True, timeout=5)
        return 'erid' in response.url.lower()
    except Exception:
        return False

def get_group_id(vk, screen_name):
    """Преобразует короткое имя в числовой ID"""
    try:
        res = vk.utils.resolveScreenName(screen_name=screen_name)
        if res and res['type'] == 'group':
            return -res['object_id']
    except Exception as e:
        print(f"Ошибка при поиске ID группы {screen_name}: {e}")
    return None

def process_wall():
    if not TOKEN:
        print("Ошибка: VK_TOKEN не найден!")
        return

    vk_session = vk_api.VkApi(token=TOKEN)
    vk = vk_session.get_api()

    # Считаем порог даты ОТ СЕГОДНЯШНЕГО ДНЯ
    now = datetime.now()
    threshold_date = now - relativedelta(months=MONTHS_OFFSET)

    print(f"Сегодняшняя дата: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Будем удалять посты с erid старше: {threshold_date.strftime('%Y-%m-%d %H:%M:%S')}")

    for name in GROUP_NAMES:
        group_id = get_group_id(vk, name)
        if not group_id:
            print(f"\n[!] Не удалось найти группу: {name}")
            continue
        
        print(f"\n>>> Обработка группы: {name} ({group_id})")
        
        offset = 0
        deleted_count = 0
        stop_scanning = False

        while not stop_scanning:
            try:
                # Получаем посты порциями по 100
                response = vk.wall.get(owner_id=group_id, offset=offset, count=100)
                posts = response.get('items', [])
                
                if not posts:
                    break
                
                for post in posts:
                    post_date = datetime.fromtimestamp(post['date'])
                    
                    # Если дошли до постов старше порога — начинаем проверку
                    if post_date <= threshold_date:
                        post_id = post['id']
                        text = post.get('text', '')
                        found_erid = False

                        # 1. Проверка текста
                        if 'erid' in text.lower():
                            found_erid = True
                        
                        # 2. Проверка ссылок в тексте
                        if not found_erid:
                            words = text.split()
                            for word in words:
                                if word.startswith('http'):
                                    if expand_url(word):
                                        found_erid = True
                                        break
                        
                        # 3. Проверка вложений (кнопок)
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
                                print(f"[УДАЛЕНО] Пост {post_id} от {post_date}")
                                deleted_count += 1
                                time.sleep(0.4) # Пауза для лимитов ВК
                            except Exception as e:
                                print(f"Ошибка удаления {post_id}: {e}")
                    
                    # Если в текущей пачке мы дошли до ОЧЕНЬ старых постов (например, на год назад)
                    # тут можно добавить логику остановки, но для надежности пройдем до конца
                
                offset += 100
                if len(posts) < 100: # Если постов меньше 100, значит это была последняя страница
                    break
                    
            except Exception as e:
                print(f"Ошибка при получении стены: {e}")
                break

        print(f"Итог по группе {name}: удалено {deleted_count} постов.")

if __name__ == "__main__":
    process_wall()
