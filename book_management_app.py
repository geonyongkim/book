import streamlit as st
import pandas as pd
import os
import uuid
import requests
from PIL import Image
from pyzbar.pyzbar import decode
from datetime import datetime, timedelta
import plotly.express as px

# --- 파일 설정 ---
BOOK_FILE = 'books_data.csv'
LOG_FILE = 'reading_log.csv'

# --- [함수 1] 데이터 로드 및 초기화 ---
def load_data():
    if not os.path.exists(BOOK_FILE):
        books_df = pd.DataFrame(columns=['ID', '제목', 'ISBN', '레벨', '읽은횟수', '상태', '표지URL'])
        books_df.to_csv(BOOK_FILE, index=False)
    else:
        books_df = pd.read_csv(BOOK_FILE)
        if 'ID' not in books_df.columns:
            books_df['ID'] = [str(uuid.uuid4()) for _ in range(len(books_df))]
        if 'ISBN' not in books_df.columns:
            books_df['ISBN'] = ""

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

# --- [함수 4] 바코드 스캔 ---
def scan_barcode(image_file):
    try:
        image = Image.open(image_file)
        decoded_objects = decode(image)
        for obj in decoded_objects:
            return obj.data.decode("utf-8")
    except Exception as e:
        st.error(f"바코드 인식 오류: {e}")
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
            title = book.get("title", "")
            image_links = book.get("imageLinks", {})
            thumbnail = image_links.get("thumbnail", "")
            return title, thumbnail
    except Exception:
        pass

    try:
        url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{clean_isbn}&jscmd=data&format=json"
        response = requests.get(url)
        data = response.json()
        key = f"ISBN:{clean_isbn}"
        if key in data:
            book = data[key]
            title = book.get("title", "")
            cover = book.get("cover", {})
            thumbnail = cover.get("medium", "") or cover.get("large", "") or cover.get("small", "")
            return title, thumbnail
    except Exception:
        pass
    return None, None

# =========================================================
# 메인 UI
# =========================================================

st.set_page_config(page_title="아이 영어 독서 매니저", layout="wide", page_icon="📚")
books_df, logs_df = load_data()

st.title("📚 Smart English Library v2.2")

tab1, tab2, tab3 = st.tabs(["📊 대시보드", "📖 서재 관리 (수정/읽기)", "➕ 새 책 등록"])

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

# --- [탭 2] 서재 관리 (수정 기능 강화) ---
with tab2:
    st.subheader("보유 도서 관리")
    st.caption("레벨이나 상태를 변경하면 즉시 저장됩니다.")
    
    if not books_df.empty:
        # 최신 등록순
        for i, row in books_df.iloc[::-1].iterrows():
            with st.container():
                c1, c2 = st.columns([1, 5])
                
                # 왼쪽: 이미지
                with c1:
                    st.image(row['표지URL'] if pd.notna(row['표지URL']) and str(row['표지URL']).startswith("http") else "https://via.placeholder.com/150", width=80)
                
                # 오른쪽: 정보 및 수정 컨트롤
                with c2:
                    # 1. 제목 및 기본정보
                    st.markdown(f"#### **{row['제목']}**")
                    st.text(f"ISBN: {row['ISBN'] if pd.notna(row['ISBN']) else '-'}")

                    # 2. 수정 가능한 컨트롤 영역 (레벨, 상태)
                    ec1, ec2, ec3 = st.columns([1.5, 1.5, 2])
                    
                    # 현재 값 가져오기 (인덱싱 오류 방지)
                    current_lvl_idx = row['레벨'] - 1 if 1 <= row['레벨'] <= 5 else 0
                    status_options = ["읽지 않음", "읽는 중", "완독"]
                    try:
                        current_status_idx = status_options.index(row['상태'])
                    except:
                        current_status_idx = 0
                    
                    # [수정 1] 레벨 변경
                    with ec1:
                        new_level = st.selectbox(
                            "레벨", 
                            [1, 2, 3, 4, 5], 
                            index=int(current_lvl_idx), 
                            key=f"lvl_{row['ID']}",
                            label_visibility="collapsed" # 라벨 숨김
                        )
                    
                    # [수정 2] 상태 변경
                    with ec2:
                        new_status = st.selectbox(
                            "상태", 
                            status_options, 
                            index=current_status_idx, 
                            key=f"sts_{row['ID']}",
                            label_visibility="collapsed"
                        )
                    
                    # 변경 감지 및 저장 로직
                    if new_level != row['레벨'] or new_status != row['상태']:
                        idx = books_df[books_df['ID'] == row['ID']].index[0]
                        books_df.at[idx, '레벨'] = new_level
                        books_df.at[idx, '상태'] = new_status
                        save_books(books_df)
                        st.toast(f"✅ '{row['제목']}' 정보 수정 완료!")
                        st.rerun()

                    # 3. 조작 버튼 (읽기 추가 / 삭제)
                    b1, b2 = st.columns([1, 1])
                    if b1.button(f"➕ 읽기 추가 (현재 {row['읽은횟수']}회)", key=f"read_{row['ID']}"):
                        idx = books_df[books_df['ID'] == row['ID']].index[0]
                        books_df.at[idx, '읽은횟수'] += 1
                        # 읽으면 자동으로 상태를 '읽는 중'으로 변경 (완독이 아닐 때만)
                        if books_df.at[idx, '상태'] == '읽지 않음':
                            books_df.at[idx, '상태'] = '읽는 중'
                        
                        save_books(books_df)
                        add_log(row['ID'], row['제목'], new_level)
                        st.toast(f"📖 독서 기록 추가 완료!")
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

    input_method = st.radio("입력 방식", ["📸 바코드 스캔", "✍️ 수동 검색"], horizontal=True)
    
    if input_method == "📸 바코드 스캔":
        img_file = st.camera_input("바코드 촬영")
        if img_file:
            isbn_val = scan_barcode(img_file)
            if isbn_val and st.session_state['auto_isbn'] != isbn_val:
                with st.spinner("정보 찾는 중..."):
                    t, i = search_book_info(isbn_val)
                    st.session_state['auto_isbn'] = isbn_val
                    st.session_state['auto_title'] = t if t else ""
                    st.session_state['auto_img'] = i if i else ""
                    st.rerun()
    else:
        manual_isbn = st.text_input("ISBN 입력 (엔터)", value=st.session_state['auto_isbn'])
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
            
        if st.form_submit_button("등록하기"):
            if not title:
                st.error("제목 필수")
            else:
                new_data = {
                    'ID': str(uuid.uuid4()),
                    '제목': title, 'ISBN': isbn, '레벨': level, 
                    '읽은횟수': 0, '상태': status, '표지URL': img_url
                }
                books_df = pd.concat([books_df, pd.DataFrame([new_data])], ignore_index=True)
                save_books(books_df)
                
                st.session_state['auto_title'] = ""
                st.session_state['auto_isbn'] = ""
                st.session_state['auto_img'] = ""
                st.success("등록 완료")
                st.rerun()