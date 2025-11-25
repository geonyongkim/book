import streamlit as st
import pandas as pd
import os
import uuid
import requests
from PIL import Image, ImageEnhance
from pyzbar.pyzbar import decode
from datetime import datetime, timedelta
import plotly.express as px

# --- 파일 설정 ---
BOOK_FILE = 'books_data.csv'
LOG_FILE = 'reading_log.csv'

# --- [반응 옵션 정의] ---
REACTION_OPTIONS = ["선택 안 함", "😄 재미있어요", "😓 어려워요", "🎨 그림이 마음에 들어요", "🐣 스스로 읽을 수 있어요"]

# --- [함수 1] 데이터 로드 및 초기화 ---
def load_data():
    if not os.path.exists(BOOK_FILE):
        books_df = pd.DataFrame(columns=['ID', '제목', 'ISBN', '레벨', '읽은횟수', '상태', '반응', '표지URL'])
        books_df.to_csv(BOOK_FILE, index=False)
    else:
        books_df = pd.read_csv(BOOK_FILE)
        # 컬럼 누락 방지 및 초기화 (기존 데이터 호환성)
        if 'ID' not in books_df.columns:
            books_df['ID'] = [str(uuid.uuid4()) for _ in range(len(books_df))]
        if 'ISBN' not in books_df.columns:
            books_df['ISBN'] = ""
        # [추가] 반응 컬럼이 없으면 기본값으로 생성
        if '반응' not in books_df.columns:
            books_df['반응'] = "선택 안 함"
        # NaN 값 처리
        books_df['반응'] = books_df['반응'].fillna("선택 안 함")

    if not os.path.exists(LOG_FILE):
        logs_df = pd.DataFrame(columns=['날짜', '책ID', '제목', '레벨'])
        logs_df.to_csv(LOG_FILE, index=False)
    else:
        logs_df = pd.read_csv(LOG_FILE)
        logs_df['날짜'] = pd.to_datetime(logs_df['날짜'])

    return books_df, logs_df

# --- [함수 2] 데이터 저장 ---
def save_books(df):
    df.to_csv(BOOK_FILE, index=False)

# --- [함수 3] 로그 기록 추가 ---
def add_log(book_id, title, level):
    new_log = pd.DataFrame([{
        '날짜': datetime.now().date(),
        '책ID': book_id,
        '제목': title,
        '레벨': level
    }])
    if os.path.exists(LOG_FILE):
        new_log.to_csv(LOG_FILE, mode='a', header=False, index=False)
    else:
        new_log.to_csv(LOG_FILE, index=False)

# --- [함수 4] 바코드 스캔 (줌 & 보정 기능 탑재) ---
def scan_barcode(image_file):
    try:
        image = Image.open(image_file)
        attempts = []
        
        # 1. 기본 흑백
        gray = image.convert('L')
        attempts.append(gray)
        
        # 2. 중앙 크롭 (줌 효과)
        w, h = gray.size
        cropped = gray.crop((w * 0.2, h * 0.2, w * 0.8, h * 0.8)) 
        attempts.append(cropped)
        
        # 3. 더 좁은 크롭
        cropped_zoom = gray.crop((w * 0.35, h * 0.35, w * 0.65, h * 0.65))
        attempts.append(cropped_zoom)
        
        # 4. 선명도 보정
        enhancer = ImageEnhance.Sharpness(cropped)
        sharpened = enhancer.enhance(2.0)
        attempts.append(sharpened)

        for img in attempts:
            decoded_objects = decode(img)
            for obj in decoded_objects:
                return obj.data.decode("utf-8")
                
    except Exception as e:
        st.error(f"이미지 처리 오류: {e}")
    return None

# --- [함수 5] 도서 정보 검색 ---
def search_book_info(isbn):
    if not isbn: return None, None
    clean_isbn = str(isbn).strip().replace("-", "").replace(" ", "")
    
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{clean_isbn}"
        response = requests.get(url)
        data = response.json()
        if "items" in data:
            book = data["items"][0]["volumeInfo"]
            return book.get("title", ""), book.get("imageLinks", {}).get("thumbnail", "")
    except: pass

    try:
        url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{clean_isbn}&jscmd=data&format=json"
        response = requests.get(url)
        data = response.json()
        key = f"ISBN:{clean_isbn}"
        if key in data:
            book = data[key]
            cover = book.get("cover", {})
            return book.get("title", ""), (cover.get("medium") or cover.get("large") or cover.get("small", ""))
    except: pass
    return None, None

# =========================================================
# 메인 UI
# =========================================================

st.set_page_config(page_title="아이 영어 독서 매니저", layout="wide", page_icon="📚")
books_df, logs_df = load_data()

st.title("📚 Smart English Library v2.4")

tab1, tab2, tab3 = st.tabs(["📊 대시보드", "📖 서재 관리 (반응 체크)", "➕ 새 책 등록"])

# --- [탭 1] 대시보드 ---
with tab1:
    st.header("독서 현황 브리핑")
    if logs_df.empty:
        st.info("아직 데이터가 없습니다.")
    else:
        today = pd.Timestamp.now().normalize()
        daily_reads = logs_df[logs_df['날짜'] == today]
        
        c1, c2 = st.columns(2)
        c1.metric("오늘 읽은 책", f"{len(daily_reads)}권")
        c2.metric("총 누적 독서", f"{len(logs_df)}권")
        
        st.divider()
        
        col_chart1, col_chart2 = st.columns([2, 1])
        with col_chart1:
            st.subheader("최근 30일 독서 추이")
            last_30 = logs_df[logs_df['날짜'] >= (today - timedelta(days=29))]
            daily_counts = last_30.groupby('날짜').size().reset_index(name='권수')
            if not daily_counts.empty:
                fig = px.bar(daily_counts, x='날짜', y='권수', text_auto=True)
                st.plotly_chart(fig, use_container_width=True)
        with col_chart2:
            st.subheader("레벨별 비중")
            level_counts = logs_df.groupby('레벨').size().reset_index(name='권수')
            if not level_counts.empty:
                fig2 = px.pie(level_counts, values='권수', names='레벨', hole=0.4)
                st.plotly_chart(fig2, use_container_width=True)

# --- [탭 2] 서재 관리 (반응 기능 추가됨) ---
with tab2:
    st.subheader("보유 도서 관리")
    st.caption("레벨, 상태, 그리고 **아이의 반응**을 체크해주세요. 변경 즉시 저장됩니다.")
    
    if not books_df.empty:
        # 최신 등록순
        for i, row in books_df.iloc[::-1].iterrows():
            with st.container():
                c1, c2 = st.columns([1, 5])
                
                # 왼쪽: 이미지
                with c1:
                    st.image(row['표지URL'] if pd.notna(row['표지URL']) and str(row['표지URL']).startswith("http") else "https://via.placeholder.com/150", width=80)
                
                # 오른쪽: 정보 및 수정
                with c2:
                    st.markdown(f"#### **{row['제목']}**")
                    st.text(f"ISBN: {row['ISBN'] if pd.notna(row['ISBN']) else '-'}")

                    # [수정 영역: 레벨 | 상태 | 반응]
                    ec1, ec2, ec3 = st.columns([1, 1.2, 2])
                    
                    # 1. 레벨
                    current_lvl_idx = row['레벨'] - 1 if 1 <= row['레벨'] <= 5 else 0
                    with ec1:
                        new_level = st.selectbox("레벨", [1, 2, 3, 4, 5], index=int(current_lvl_idx), key=f"lvl_{row['ID']}", label_visibility="collapsed")
                    
                    # 2. 상태
                    status_options = ["읽지 않음", "읽는 중", "완독"]
                    try: sts_idx = status_options.index(row['상태'])
                    except: sts_idx = 0
                    with ec2:
                        new_status = st.selectbox("상태", status_options, index=sts_idx, key=f"sts_{row['ID']}", label_visibility="collapsed")
                    
                    # 3. [추가] 아이 반응
                    try: reaction_idx = REACTION_OPTIONS.index(row['반응'])
                    except: reaction_idx = 0
                    with ec3:
                        new_reaction = st.selectbox("아이 반응", REACTION_OPTIONS, index=reaction_idx, key=f"react_{row['ID']}", help="아이의 반응을 기록해주세요")

                    # 변경 감지 및 저장
                    if new_level != row['레벨'] or new_status != row['상태'] or new_reaction != row['반응']:
                        idx = books_df[books_df['ID'] == row['ID']].index[0]
                        books_df.at[idx, '레벨'] = new_level
                        books_df.at[idx, '상태'] = new_status
                        books_df.at[idx, '반응'] = new_reaction # 반응 저장
                        save_books(books_df)
                        st.toast(f"✅ '{row['제목']}' 정보 업데이트 완료!")
                        st.rerun()

                    # 버튼 영역
                    b1, b2 = st.columns([1, 1])
                    if b1.button(f"➕ 읽기 추가 ({row['읽은횟수']}회)", key=f"read_{row['ID']}"):
                        idx = books_df[books_df['ID'] == row['ID']].index[0]
                        books_df.at[idx, '읽은횟수'] += 1
                        if books_df.at[idx, '상태'] == '읽지 않음': books_df.at[idx, '상태'] = '읽는 중'
                        save_books(books_df)
                        add_log(row['ID'], row['제목'], new_level)
                        st.toast(f"📖 기록 추가 완료!")
                        st.rerun()

                    if b2.button("🗑 삭제", key=f"del_{row['ID']}"):
                        books_df = books_df[books_df['ID'] != row['ID']]
                        save_books(books_df)
                        st.rerun()
                st.divider()
    else:
        st.info("등록된 책이 없습니다.")

# --- [탭 3] 새 책 등록 ---
with tab3:
    st.subheader("새로운 책 입고")
    
    if 'auto_title' not in st.session_state: st.session_state['auto_title'] = ""
    if 'auto_isbn' not in st.session_state: st.session_state['auto_isbn'] = ""
    if 'auto_img' not in st.session_state: st.session_state['auto_img'] = ""
    if 'search_done' not in st.session_state: st.session_state['search_done'] = False

    input_method = st.radio("입력 방식", ["📸 바코드 스캔 (실시간)", "📂 앨범 사진 업로드 (추천)", "✍️ 수동 입력"], horizontal=True)
    
    img_file = None 
    if input_method == "📸 바코드 스캔 (실시간)":
        st.info("💡 팁: 초점이 안 맞으면 30cm 이상 떼고 촬영하세요.")
        img_file = st.camera_input("바코드 촬영")
    elif input_method == "📂 앨범 사진 업로드 (추천)":
        st.info("💡 폰 기본 카메라로 찍은 선명한 사진을 올려주세요.")
        img_file = st.file_uploader("바코드 사진 선택", type=['png', 'jpg', 'jpeg'])

    if img_file and not st.session_state.get('search_done'):
        isbn_val = scan_barcode(img_file)
        if isbn_val:
            st.toast(f"🎉 인식 성공: {isbn_val}")
            if st.session_state['auto_isbn'] != isbn_val:
                with st.spinner("정보 검색 중..."):
                    t, i = search_book_info(isbn_val)
                    st.session_state['auto_isbn'] = isbn_val
                    st.session_state['auto_title'] = t if t else ""
                    st.session_state['auto_img'] = i if i else ""
                    st.session_state['search_done'] = True
                    if t: st.success(f"발견: {t}")
                    else: st.warning("책 정보를 찾지 못했습니다. 직접 입력해주세요.")
                    st.rerun()
        else:
            st.error("바코드 인식 실패. 다시 시도해주세요.")

    if input_method == "✍️ 수동 입력":
        manual_isbn = st.text_input("ISBN 직접 입력", value=st.session_state['auto_isbn'])
        if manual_isbn and manual_isbn != st.session_state.get('last_manual', ''):
             with st.spinner("검색 중..."):
                t, i = search_book_info(manual_isbn)
                st.session_state['auto_isbn'] = manual_isbn
                st.session_state['auto_title'] = t if t else ""
                st.session_state['auto_img'] = i if i else ""
                st.session_state['last_manual'] = manual_isbn
                st.rerun()

    st.divider()

    with st.form("reg_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            title = st.text_input("책 제목", value=st.session_state['auto_title'])
            isbn = st.text_input("ISBN", value=st.session_state['auto_isbn'])
            level = st.selectbox("레벨", [1,2,3,4,5])
        with c2:
            img_url = st.text_input("표지 URL", value=st.session_state['auto_img'])
            if img_url: st.image(img_url, width=80)
            status = st.selectbox("상태", ["읽지 않음", "읽는 중", "완독"])
            # [추가] 등록 시 반응 선택
            reaction = st.selectbox("아이 반응 (선택)", REACTION_OPTIONS)
            
        if st.form_submit_button("등록하기"):
            if not title:
                st.error("제목은 필수입니다.")
            else:
                new_data = {
                    'ID': str(uuid.uuid4()),
                    '제목': title, 'ISBN': isbn, '레벨': level, 
                    '읽은횟수': 0, '상태': status, 
                    '반응': reaction, # 반응 저장
                    '표지URL': img_url
                }
                books_df = pd.concat([books_df, pd.DataFrame([new_data])], ignore_index=True)
                save_books(books_df)
                
                for key in ['auto_title', 'auto_isbn', 'auto_img', 'search_done', 'last_manual']:
                    if key in st.session_state: del st.session_state[key]
                st.success("등록 완료")
                st.rerun()
