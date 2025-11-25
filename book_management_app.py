import streamlit as st
import pandas as pd
import os
import uuid
import requests
from PIL import Image, ImageEnhance
from pyzbar.pyzbar import decode
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go

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
        if 'ID' not in books_df.columns:
            books_df['ID'] = [str(uuid.uuid4()) for _ in range(len(books_df))]
        if 'ISBN' not in books_df.columns: books_df['ISBN'] = ""
        if '반응' not in books_df.columns: books_df['반응'] = "선택 안 함"
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

# --- [함수 4] 바코드 스캔 (줌 & 보정) ---
def scan_barcode(image_file):
    try:
        image = Image.open(image_file)
        attempts = [
            image.convert('L'), # 흑백
            image.convert('L').crop((image.size[0]*0.2, image.size[1]*0.2, image.size[0]*0.8, image.size[1]*0.8)), # 줌
            ImageEnhance.Sharpness(image.convert('L').crop((image.size[0]*0.35, image.size[1]*0.35, image.size[0]*0.65, image.size[1]*0.65))).enhance(2.0) # 슈퍼줌+선명
        ]
        for img in attempts:
            decoded = decode(img)
            for obj in decoded: return obj.data.decode("utf-8")
    except Exception: pass
    return None

# --- [함수 5] 도서 검색 ---
def search_book_info(isbn):
    if not isbn: return None, None
    clean_isbn = str(isbn).strip().replace("-", "").replace(" ", "")
    try:
        r = requests.get(f"https://www.googleapis.com/books/v1/volumes?q=isbn:{clean_isbn}").json()
        if "items" in r:
            return r["items"][0]["volumeInfo"].get("title", ""), r["items"][0]["volumeInfo"].get("imageLinks", {}).get("thumbnail", "")
    except: pass
    try:
        r = requests.get(f"https://openlibrary.org/api/books?bibkeys=ISBN:{clean_isbn}&jscmd=data&format=json").json()
        if f"ISBN:{clean_isbn}" in r:
            bk = r[f"ISBN:{clean_isbn}"]
            cv = bk.get("cover", {})
            return bk.get("title", ""), (cv.get("medium") or cv.get("large") or cv.get("small", ""))
    except: pass
    return None, None

# =========================================================
# 메인 UI
# =========================================================

st.set_page_config(page_title="아이 영어 독서 매니저", layout="wide", page_icon="📚")
books_df, logs_df = load_data()

st.title("📚 Smart English Library v2.5")

tab1, tab2, tab3 = st.tabs(["📊 상세 대시보드", "📖 서재 관리 (정렬/수정)", "➕ 새 책 등록"])

# --- [탭 1] 상세 대시보드 ---
with tab1:
    st.markdown("### 📈 독서 현황 브리핑")
    
    if logs_df.empty and books_df.empty:
        st.info("데이터가 없습니다. 책을 등록하고 독서 기록을 시작해보세요!")
    else:
        # 1. 핵심 지표 (KPI)
        today = pd.Timestamp.now().normalize()
        this_month_start = today.replace(day=1)
        
        daily_reads = logs_df[logs_df['날짜'] == today]
        month_reads = logs_df[logs_df['날짜'] >= this_month_start]
        
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("총 보유 도서", f"{len(books_df)}권")
        kpi2.metric("총 누적 읽기", f"{len(logs_df)}회")
        kpi3.metric("이번 달 독서", f"{len(month_reads)}회")
        kpi4.metric("오늘 읽은 책", f"{len(daily_reads)}권")
        
        st.divider()
        
        # 2. 차트 분석 영역
        c1, c2 = st.columns([1, 1])
        
        with c1:
            st.subheader("🗓️ 최근 30일 독서 추이")
            if not logs_df.empty:
                last_30 = logs_df[logs_df['날짜'] >= (today - timedelta(days=29))]
                daily_counts = last_30.groupby('날짜').size().reset_index(name='권수')
                fig = px.bar(daily_counts, x='날짜', y='권수', text_auto=True, color_discrete_sequence=['#4C78A8'])
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.write("데이터 부족")

        with c2:
            st.subheader("🧸 아이의 반응 분석")
            if not books_df.empty:
                # '선택 안 함' 제외하고 분석 (원하면 포함 가능)
                reaction_counts = books_df[books_df['반응'] != '선택 안 함']['반응'].value_counts().reset_index()
                reaction_counts.columns = ['반응', '권수']
                if not reaction_counts.empty:
                    fig2 = px.pie(reaction_counts, values='권수', names='반응', hole=0.4, title="등록된 책에 대한 아이 반응")
                    st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.info("아직 아이 반응이 기록된 책이 없습니다.")
            else:
                st.write("데이터 부족")

        st.divider()

        # 3. 상세 랭킹
        r1, r2 = st.columns(2)
        with r1:
            st.subheader("🏆 가장 많이 읽은 책 Best 5")
            if not books_df.empty:
                top_books = books_df.sort_values(by='읽은횟수', ascending=False).head(5)
                for idx, row in top_books.iterrows():
                    st.write(f"**{row['읽은횟수']}회** | {row['제목']} (Lv.{row['레벨']})")
        
        with r2:
            st.subheader("📚 레벨별 보유 현황")
            if not books_df.empty:
                lvl_counts = books_df['레벨'].value_counts().sort_index()
                st.bar_chart(lvl_counts)

# --- [탭 2] 서재 관리 (정렬 기능 강화) ---
with tab2:
    c_head, c_sort = st.columns([3, 2])
    with c_head:
        st.subheader("보유 도서 관리")
    with c_sort:
        # [기능 추가] 정렬 옵션
        sort_option = st.selectbox(
            "📚 정렬 기준", 
            ["최신 등록순", "자주 읽은 책 (Best)", "안 읽은 책 (0회)", "아이 반응별 모아보기", "레벨 높은 순"]
        )

    # 데이터 정렬 로직
    if not books_df.empty:
        display_df = books_df.copy()
        
        if sort_option == "최신 등록순":
            display_df = display_df.iloc[::-1]
        elif sort_option == "자주 읽은 책 (Best)":
            display_df = display_df.sort_values(by='읽은횟수', ascending=False)
        elif sort_option == "안 읽은 책 (0회)":
            display_df = display_df.sort_values(by='읽은횟수', ascending=True)
        elif sort_option == "아이 반응별 모아보기":
            display_df = display_df.sort_values(by='반응', ascending=False) # 가나다 역순(재미있어요가 위로 오게)
        elif sort_option == "레벨 높은 순":
            display_df = display_df.sort_values(by='레벨', ascending=False)

        st.caption(f"총 {len(display_df)}권의 책이 표시됩니다.")

        # 리스트 출력
        for i, row in display_df.iterrows():
            with st.container():
                c1, c2 = st.columns([1, 5])
                
                # 표지
                with c1:
                    st.image(row['표지URL'] if pd.notna(row['표지URL']) and str(row['표지URL']).startswith("http") else "https://via.placeholder.com/150", width=80)
                
                # 정보 및 컨트롤
                with c2:
                    st.markdown(f"#### **{row['제목']}**")
                    st.text(f"ISBN: {row['ISBN'] if pd.notna(row['ISBN']) else '-'}")

                    ec1, ec2, ec3 = st.columns([1, 1.2, 2.5])
                    
                    # 원래 데이터프레임의 실제 인덱스 찾기 (수정 저장을 위해 필수)
                    real_idx = books_df[books_df['ID'] == row['ID']].index[0]

                    # 1. 레벨
                    cur_lvl = int(row['레벨'] - 1) if 1 <= row['레벨'] <= 5 else 0
                    with ec1:
                        new_lvl = st.selectbox("레벨", [1,2,3,4,5], index=cur_lvl, key=f"l_{row['ID']}", label_visibility="collapsed")

                    # 2. 상태
                    sts_opts = ["읽지 않음", "읽는 중", "완독"]
                    try: s_idx = sts_opts.index(row['상태'])
                    except: s_idx = 0
                    with ec2:
                        new_sts = st.selectbox("상태", sts_opts, index=s_idx, key=f"s_{row['ID']}", label_visibility="collapsed")
                    
                    # 3. 반응
                    try: r_idx = REACTION_OPTIONS.index(row['반응'])
                    except: r_idx = 0
                    with ec3:
                        new_react = st.selectbox("반응", REACTION_OPTIONS, index=r_idx, key=f"r_{row['ID']}", label_visibility="collapsed")

                    # 변경 감지 및 즉시 저장
                    if new_lvl != row['레벨'] or new_sts != row['상태'] or new_react != row['반응']:
                        books_df.at[real_idx, '레벨'] = new_lvl
                        books_df.at[real_idx, '상태'] = new_sts
                        books_df.at[real_idx, '반응'] = new_react
                        save_books(books_df)
                        st.toast(f"✅ 수정 완료! 대시보드에 반영되었습니다.")
                        st.rerun()

                    # 버튼
                    b1, b2 = st.columns([1, 1])
                    if b1.button(f"➕ 읽기 추가 ({row['읽은횟수']}회)", key=f"btn_r_{row['ID']}"):
                        books_df.at[real_idx, '읽은횟수'] += 1
                        if books_df.at[real_idx, '상태'] == '읽지 않음': books_df.at[real_idx, '상태'] = '읽는 중'
                        save_books(books_df)
                        add_log(row['ID'], row['제목'], new_lvl)
                        st.toast("📖 독서 기록 추가 완료!")
                        st.rerun()

                    if b2.button("🗑 삭제", key=f"btn_d_{row['ID']}"):
                        books_df = books_df.drop(real_idx)
                        save_books(books_df)
                        st.rerun()
                st.divider()
    else:
        st.info("등록된 책이 없습니다.")

# --- [탭 3] 새 책 등록 ---
with tab3:
    st.subheader("새로운 책 입고")
    
    if 'auto_title' not in st.session_state: st.session_state.update({'auto_title':"", 'auto_isbn':"", 'auto_img':"", 'search_done':False})

    input_method = st.radio("입력 방식", ["📸 바코드 스캔 (실시간)", "📂 앨범 사진 업로드 (추천)", "✍️ 수동 입력"], horizontal=True)
    
    img_file = None 
    if input_method == "📸 바코드 스캔 (실시간)":
        st.info("💡 팁: 초점이 안 맞으면 30cm 이상 떼고 촬영하세요.")
        img_file = st.camera_input("바코드 촬영")
    elif input_method == "📂 앨범 사진 업로드 (추천)":
        st.info("💡 폰 카메라로 찍은 선명한 사진을 올려주세요.")
        img_file = st.file_uploader("바코드 사진 선택", type=['png', 'jpg', 'jpeg'])

    if img_file and not st.session_state.get('search_done'):
        isbn_val = scan_barcode(img_file)
        if isbn_val:
            st.toast(f"🎉 인식 성공: {isbn_val}")
            if st.session_state['auto_isbn'] != isbn_val:
                with st.spinner("정보 검색 중..."):
                    t, i = search_book_info(isbn_val)
                    st.session_state.update({'auto_isbn': isbn_val, 'auto_title': t or "", 'auto_img': i or "", 'search_done': True})
                    st.rerun()
        else:
            st.error("바코드 인식 실패. 다시 시도해주세요.")

    if input_method == "✍️ 수동 입력":
        manual_isbn = st.text_input("ISBN 직접 입력", value=st.session_state['auto_isbn'])
        if manual_isbn and manual_isbn != st.session_state.get('last_manual', ''):
             with st.spinner("검색 중..."):
                t, i = search_book_info(manual_isbn)
                st.session_state.update({'auto_isbn': manual_isbn, 'auto_title': t or "", 'auto_img': i or "", 'last_manual': manual_isbn})
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
            reaction = st.selectbox("아이 반응 (초기값)", REACTION_OPTIONS)
            
        if st.form_submit_button("등록하기"):
            if not title:
                st.error("제목은 필수입니다.")
            else:
                new_data = {
                    'ID': str(uuid.uuid4()), '제목': title, 'ISBN': isbn, '레벨': level, 
                    '읽은횟수': 0, '상태': status, '반응': reaction, '표지URL': img_url
                }
                books_df = pd.concat([books_df, pd.DataFrame([new_data])], ignore_index=True)
                save_books(books_df)
                
                for key in ['auto_title', 'auto_isbn', 'auto_img', 'search_done', 'last_manual']:
                    if key in st.session_state: del st.session_state[key]
                st.success("등록 완료! 대시보드에 즉시 반영됩니다.")
                st.rerun()
