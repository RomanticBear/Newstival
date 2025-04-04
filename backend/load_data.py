import os
import django
import html
from bs4 import BeautifulSoup
import json
import urllib.request
from datetime import datetime, timedelta
from django.utils.timezone import make_aware
from dotenv import load_dotenv
import time  # 추가

# DJANGO_SETTINGS_MODULE 설정 (프로젝트 이름에 맞게 변경)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

# Django 설정 초기화
django.setup()

# 필요한 모델들 import
from festivals_news.models import FestivalNews
from festivals_details.models import Festival_Details  # FestivalDetails 모델 추가

# .env 파일에서 API 키 로드
load_dotenv()
client_id = os.getenv("CLIENT_ID")
client_secret = os.getenv("CLIENT_SECRET")


# 네이버 뉴스 API 요청
def search_news(query):
    encText = urllib.parse.quote(query)
    url = f"https://openapi.naver.com/v1/search/news.json?query={encText}&display=100"
    request = urllib.request.Request(url)
    request.add_header("X-Naver-Client-Id", client_id)
    request.add_header("X-Naver-Client-Secret", client_secret)

    try:
        response = urllib.request.urlopen(request)
        if response.getcode() == 200:
            return json.loads(response.read().decode('utf-8'))
        else:
            print(f"Error Code: {response.getcode()}")
            return None
    except Exception as e:
        print(f"Error while requesting news: {e}")
        return None


# 최근 12개월 이내 기사 필터링
def filter_recent_articles(articles, months=12):
    cutoff_date = make_aware(datetime.now() - timedelta(days=30 * months))
    recent_articles = []

    for article in articles:
        try:
            pub_date = datetime.strptime(article['pubDate'], "%a, %d %b %Y %H:%M:%S %z")
            if pub_date > cutoff_date:
                article['pubDate'] = pub_date
                recent_articles.append(article)
        except (ValueError, KeyError) as e:
            print(f"Skipping invalid article: {e}")
    return recent_articles


# 뉴스 데이터를 DB에 저장
def save_articles_to_db(festival_name, main_region, articles):
    for article in articles:
        try:
            # 제목과 설명을 가져옵니다
            title = article['title']
            description = article.get('description', '')

            # HTML 태그 제거
            title_soup = BeautifulSoup(title, features='html.parser')
            title_text = title_soup.get_text()
            description_soup = BeautifulSoup(description, features='html.parser')
            description_text = description_soup.get_text()

            # HTML 엔티티 디코딩
            clean_title = html.unescape(title_text)
            clean_description = html.unescape(description_text)

            # 데이터베이스에 저장
            FestivalNews.objects.update_or_create(
                link=article['link'],
                defaults={
                    'festival_name': festival_name,
                    'title': clean_title,
                    'originallink': article.get('originallink', article['link']),
                    'description': clean_description,
                    'pub_date': article['pubDate'],
                    'main_region': main_region,
                }
            )
        except Exception as e:
            print(f"Error saving article: {e}")


# 축제 상세 정보를 DB에 저장
def save_festival_details_to_db(directory):
    """
    JSON 파일에서 FestivalDetails 데이터를 읽어와 PostgreSQL에 저장합니다.
    """
    for file_name in os.listdir(directory):
        if file_name.endswith('.json'):  # JSON 파일만 처리
            file_path = os.path.join(directory, file_name)
            with open(file_path, 'r', encoding='utf-8') as file:
                try:
                    data = json.load(file)  # JSON 데이터를 파싱
                    for item in data:
                        try:
                            # 데이터베이스에 저장
                            Festival_Details.objects.update_or_create(
                                title=item.get('Title'),
                                defaults={
                                    'region': item.get('Region'),
                                    'Main_Region': item.get('Main Region'),
                                    'period': item.get('Period'),
                                    'nature': item.get('Nature'),
                                    'fee': item.get('Fee'),
                                    'info': item.get('Info'),
                                    'url': item.get('URL'),
                                    'created_at': make_aware(datetime.now()),
                                    'updated_at': make_aware(datetime.now()),
                                }
                                #print(defaults)
                            )
                        except Exception as e:
                            print(f"Error saving festival details: {e}")
                except Exception as e:
                    print(f"파일 {file_name} 처리 중 오류 발생: {e}")


# 메인 함수
def main():
    # JSON 파일들이 저장된 디렉토리 경로
    directory = r"data/festival_info"

    # 축제 정보를 DB에 저장
    print("Saving festival details to database...")
    save_festival_details_to_db(directory)

    # 축제 이름과 지역 로드
    festival = []
    for file_name in os.listdir(directory):
        if file_name.endswith('.json'):
            with open(os.path.join(directory, file_name), 'r', encoding='utf-8') as f:
                data = json.load(f)
                festival.extend([[festival['Title'], festival['Main Region']] for festival in data])

    # 뉴스 검색 및 저장을 30초마다 반복
    while True:
        print("Saving news articles to database...")
        for name, main_region in festival:
            print(f"Searching news for: {name}")
            response = search_news(name)

            if response and 'items' in response:
                recent_articles = filter_recent_articles(response['items'])
                save_articles_to_db(name, main_region, recent_articles)
            else:
                print(f"No articles found for {name}")

        print("Waiting for 30 seconds...")
        time.sleep(30)  # 30초 대기


if __name__ == "__main__":
    main()
