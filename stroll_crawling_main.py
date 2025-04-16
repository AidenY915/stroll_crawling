from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
import time
import requests
from dotenv import load_dotenv
import os
import re

KAKAO_API_KEY=None
CHROMEDRIVER_PATH = "../chromedriver-win64/chromedriver.exe"
driver = None

def init():
    global KAKAO_API_KEY
    global driver

     # 이미지 저장을 위한 디렉토리 생성
    if not os.path.exists('./images'):
        os.makedirs('./images')

    load_dotenv()
    KAKAO_API_KEY=os.getenv("KAKAO_API_KEY")

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
        "Authorization": f"KakaoAK {KAKAO_API_KEY}"  # 여기에 본인의 REST API 키 삽입
    }

    res = requests.get(url, headers=headers)
    data = res.json()
    
    # documents 리스트에서 첫 번째 결과 추출
    documents = data.get("documents", [])
    if not documents:
        return None  # 검색 결과 없음

    first = documents[0]

    # 도로명 주소 우선, 없으면 지번 주소
    if first.get("road_address"):
        return first["road_address"].get("address_name")
    elif first.get("address"):
        return first["address"].get("address_name")
    else:
        return None


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
    # 시/도 + 구/군 까지만 추출
    match = re.search(r'^([\w가-힣]+[시도]\s[\w가-힣]+[구군])', addr)
    return match.group(1) if match else addr

def main():
    init()
    # 접속할 사이트
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
            
            road_address = convert_to_road_address(rest_address)
            gu_address = extract_gu_address(road_address)
            after_gu_address = road_address.replace(gu_address, "")
            
            if(road_address is None):
                continue
            print(title.text, category.text, gu_address, after_gu_address, detail_address)

            #이미지 다운로드
            try:
                img = li_element.find_element(By.CSS_SELECTOR, 'img')
                img_src = img.get_attribute("src").replace("type=f160_160", "type=w560_sharpen")
                
                # 데이터 베이스 연결해서 no랑 연동해서 업로드 해야함.
                if img_src:
                    try:
                        img_data = requests.get(img_src).content
                        with open(f"./images/{title.text}.jpg", "wb") as f:
                            f.write(img_data)
                        print(f"{title.text}.jpg")
                    except Exception as e:
                        print(f"Error downloading {img_src}: {e}")
                    print(img_src)
            except Exception as e:
                print(f"{title.text}은(는) 이미지 없음.")
                
    # 종료
    driver.quit()

main()


