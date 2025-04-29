from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
import time
import requests
from dotenv import load_dotenv
import os
import re
import pymysql
import boto3

KAKAO_API_KEY=None
CHROMEDRIVER_PATH = "../chromedriver-win64/chromedriver.exe"
driver = None
DATABASE_NAME = None
DATABASE_HOST = None
DATABASE_USER = None
DATABASE_PASSWORD = None
AWS_ACCESS_KEY_ID = None
AWS_SECRET_ACCESS_KEY = None
REGION_NAME = None
BUCKET_NAME = None
ADMIN_ID = None

def init():
    global KAKAO_API_KEY
    global driver
    global DATABASE_NAME
    global DATABASE_HOST
    global DATABASE_USER
    global DATABASE_PASSWORD
    global AWS_ACCESS_KEY_ID
    global AWS_SECRET_ACCESS_KEY
    global REGION_NAME
    global BUCKET_NAME
    global ADMIN_ID

     # 이미지 저장을 위한 디렉토리 생성
    if not os.path.exists('./images'):
        os.makedirs('./images')

    load_dotenv(override=True)
    
    KAKAO_API_KEY = os.getenv("KAKAO_API_KEY")
    DATABASE_NAME = os.getenv("DATABASE_NAME")
    DATABASE_HOST = os.getenv("DATABASE_HOST")
    DATABASE_USER = os.getenv("DATABASE_USER")
    DATABASE_PASSWORD = os.getenv("DATABASE_PASSWORD")
    AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
    REGION_NAME = os.getenv("REGION_NAME")
    BUCKET_NAME = os.getenv("BUCKET_NAME")
    ADMIN_ID = os.getenv("ADMIN_ID")

    # 옵션 설정
    options = Options()
    # options.add_argument("--headless")             # 브라우저 창 없이 실행
    options.add_argument("--no-sandbox")            # 보안 옵션 끔 (리눅스 환경 대비용)
    options.add_argument("--disable-dev-shm-usage") # 메모리 부족 방지
    # options.binary_location = "C:/경로/chrome.exe"  # Chromium 쓸 경우 경로 지정
    # 드라이버 경로 설정 (chromedriver.exe 위치에 맞게 수정) 
    service = Service(executable_path=CHROMEDRIVER_PATH)
    driver = webdriver.Chrome(options = options, service=service)

def convert_to_road_address(addr):
    url = f"https://dapi.kakao.com/v2/local/search/address.json?query={addr}"
    headers = {
        "Authorization": f"KakaoAK {KAKAO_API_KEY}" 
    }

    try:
        res = requests.get(url, headers=headers)
        data = res.json()
        
        # API 응답 상태 확인
        if res.status_code != 200:
            print(f"API 호출 실패: {res.status_code} - {data.get('message', '알 수 없는 오류')}")
            return None, None, None
            
        # documents 리스트에서 첫 번째 결과 추출
        documents = data.get("documents", [])
        if not documents:
            print(f"검색 결과 없음: {addr}")
            return None, None, None

        first = documents[0]

        # 도로명 주소 우선, 없으면 지번 주소
        if first.get("road_address"):
            return first["road_address"].get("address_name"), first["x"], first["y"]
        elif first.get("address"):
            return first["address"].get("address_name"), first["x"], first["y"]
        else:
            print(f"주소 정보 없음: {addr}")
            return None, None, None
    except Exception as e:
        print(f"주소 변환 중 오류 발생: {e}")
        return None, None, None


def strip_detail_address(addr):
    match = re.search(r'^([\w\s가-힣·\-]+?\s\d+(-\d+)?)(?=\s|$)', addr)
    return match.group(1) if match else addr

def extract_detail_address(addr):
    # 도로명 + 건물번호까지만 매칭
    match = re.search(r'^([\w\s가-힣·\-]+?\s\d+(-\d+)?)(?=\s|$)', addr)
    if match:
        base_addr = match.group(1)
        detail = addr.replace(base_addr, '', 1).strip()
        return detail
    return ""  # 못 찾으면 상세주소도 없다고 판단


def extract_gu_address(addr):
    # 시/도 + 구/군 까지만 추출 구가 없으면 시나 군까지가 구
    rslt = None
    match = re.search(r'^(([가-힣]+\s)?([가-힣]+[시]\s[가-힣]+[구군]\s))', addr)
    if match:
        rslt = match.group(1).strip()
    else:
        match = re.search(r'^(([가-힣]+\s)?([\w가-힣]+[시군]\s))', addr)
        if match:
            rslt = match.group(1).strip()
    return rslt


def insert_place_to_database(title, category, gu_address, after_gu_address, detail_address, x, y, user_id):
    # DB 연결
    connection = pymysql.connect(
        host=DATABASE_HOST,         # 또는 RDS 주소
        user=DATABASE_USER,     # DB 사용자 이름
        password=DATABASE_PASSWORD, # DB 비밀번호
        database=DATABASE_NAME, # DB 이름
        charset='utf8mb4',         # 한글 인코딩 문제 방지
        cursorclass=pymysql.cursors.DictCursor
    )
    place_no = None
    try:
        with connection.cursor() as cursor:
            # 삽입할 SQL
            sql = """
            INSERT INTO place
            (title, category, gu_address, after_gu_address, detail_address, x, y, user_id) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """

            # 삽입할 값
            values = (
                title,
                category, 
                gu_address, 
                after_gu_address, 
                detail_address, 
                x, 
                y, 
                user_id
            )

            # 쿼리 실행
            cursor.execute(sql, values)
            # 저장한 장소의 번호 가져오기
            place_no = cursor.lastrowid
            
        # 변경사항 커밋
        connection.commit()
        return place_no

    except Exception as e:
        print("DB 삽입 중 오류 발생:", e)
        connection.rollback()  # 오류 발생 시 롤백
        return None

    finally:
        connection.close()

        
def insert_image_to_database(place_no, image_path):
    connection = pymysql.connect(
        host=DATABASE_HOST,         # 또는 RDS 주소
        user=DATABASE_USER,     # DB 사용자 이름
        password=DATABASE_PASSWORD, # DB 비밀번호
        database=DATABASE_NAME, # DB 이름
        charset='utf8mb4',         # 한글 인코딩 문제 방지
        cursorclass=pymysql.cursors.DictCursor
    )
    
    try:
        with connection.cursor() as cursor:
            sql = """
            INSERT INTO image
            (place_no, image_path) 
            VALUES (%s, %s)
            """
            values = (place_no, image_path)
            cursor.execute(sql, values)
        # 변경사항 커밋
        connection.commit()

    except Exception as e:
        print("이미지 정보 DB 저장 중 오류 발생:", e)
        connection.rollback()  # 오류 발생 시 롤백

    finally:
        connection.close()

def push_image_to_S3(img_data, image_path):
    # 세션 생성
    session = boto3.Session(
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=REGION_NAME
    )

    s3 = session.client('s3')

    # S3 업로드
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=image_path,
        Body=img_data,  # 여기에 파일 데이터 바로 넘김
        ContentType='image/jpeg'  # 필요하면 ContentType 지정
    )

    return 
    
                

def main():
    init()
    # 접속할 사이트 현재 좌표를 여기에 넣고 있음.
    url = "https://pcmap.place.naver.com/place/list?query=%EA%B0%95%EC%95%84%EC%A7%80&x=127.005941&y=37.268905&clientX=127.005941&clientY=37.268905&display=70&ts=1744774586148&additionalHeight=76&locale=ko&mapUrl=https%3A%2F%2Fmap.naver.com%2Fp%2Fsearch%2F%EA%B0%95%EC%95%84%EC%A7%80%2Fplace%2F12945929"  # 예: 해커뉴스
    driver.get(url)

    # 약간 대기 (동적 로딩 페이지 대비)
    time.sleep(3)

    # 원하는 요소 선택 (여기서는 뉴스 제목들)
    page_a_list = driver.find_elements(By.CSS_SELECTOR, '#app-root > div > div.XUrfU > div.zRM9F > a')
    for page_a in page_a_list:
        page_a.click()
        time.sleep(1)
        li_elements = driver.find_elements(By.CSS_SELECTOR, '#_pcmap_list_scroll_container > ul > li')
        print(len(li_elements))
        
        for li_element in li_elements:
            title = li_element.find_element(By.CSS_SELECTOR, 'div > div > a > div > span:nth-of-type(1)')
            if '입양' in title.text or '분양' in title.text:
                continue
            category = li_element.find_element(By.CSS_SELECTOR, 'div > div > a > div > span:nth-of-type(2)')
            address_a = li_element.find_element(By.CSS_SELECTOR, 'div > div > div:last-child > div > span:nth-child(2) > a > span:nth-of-type(1)')
            address_a.click()
            time.sleep(0.5)
            address = li_element.find_element(By.CSS_SELECTOR, 'div > div > div > div > div > div > div > span:nth-of-type(2)')
            detail_address = extract_detail_address(address.text)
            rest_address = strip_detail_address(address.text)
            #도로명 주소를 받아오면서, 좌표값도 받아옴.            
            road_address, x, y = convert_to_road_address(rest_address)

            if road_address is None:
                print(f"주소 변환 실패: {rest_address}")
                continue

            gu_address = extract_gu_address(road_address)
            if(gu_address is None):
                print("gu_address 추출 실패:", road_address)
                continue
            after_gu_address = road_address.replace(gu_address, "")

            print(title.text, category.text, gu_address, after_gu_address, detail_address, x, y)
            place_no = insert_place_to_database(title.text, category.text, gu_address, after_gu_address, detail_address, x, y, ADMIN_ID)
            does_image_exists = False  
            img_title=str(place_no)+"_1.jpg"
            image_path="image/"+img_title
            #이미지 다운로드
            try:
                img = li_element.find_element(By.CSS_SELECTOR, 'img')
                img_src = img.get_attribute("src").replace("type=f160_160", "type=w560_sharpen")
                if img_src:
                    try:
                        img_data = requests.get(img_src).content
                        push_image_to_S3(img_data, image_path)
                        does_image_exists = True
                    except Exception as e:
                        print(f"Error downloading {img_src}: {e}")
                    print(img_src)
            except Exception as e:
                print(f"{title.text}은(는) 이미지 없음.")
            #이미지 S3에 업로드 후 데이터 베이스 image 테이블에 추가해야함.

            #데이터베이스에 장소 및 이미지 인스턴스 추가
            
            if does_image_exists:
                print(place_no)
                insert_image_to_database(place_no, image_path)
                
    # 종료
    driver.quit()

main()


