import streamlit as st
import pandas as pd
import uuid
import requests
import urllib.parse
from PIL import Image, ImageEnhance
from pyzbar.pyzbar import decode
from datetime import datetime, timedelta
import plotly.express as px

# [Google Sheets 연동 라이브러리]
import gspread
from google.oauth2.service_account import Credentials

# =========================================================
# 🚨 [필수 설정] 사용자의 구글 시트 주소 (유지)
# =========================================================
SHEET_URL = "https://docs.google.com/spreadsheets/d/1WyA_dM3_cxqurORJ1wbYACBFBgDG9-4b_wPk8nWbwhA/edit?gid=1353177291#gid=1353177291"

# --- [별점 옵션 정의] ---
STAR_OPTIONS = ["선택 안 함", "⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]

# --- [함수 1] 구글 시트 연결 ---
@st.cache_resource
def get_google_sheet_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    credentials = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"],
        scopes=scopes
    )
    client = gspread.authorize(credentials)
    return client

# --- [함수 2] 데이터 로드 (게시판 ID 추가) ---
def load_data():
    client = get_google_sheet_client()
    try:
        sh = client.open_by_url(SHEET_URL)
    except Exception as e:
        st.error(f"구글 시트 연결 오류: {e}")
        st.stop()

    # 1. Books 데이터 로드
    try:
        wks_books = sh.worksheet("books")
        data_books = wks_books.get_all_records()
        books_df = pd.DataFrame(data_books)
        
        required_cols = [
            'ID', '제목', 'ISBN', '레벨', '상태', '표지URL', '음원URL',
            '횟수_첫째', '횟수_둘째', 
            '반응_첫째', '반응_둘째', 
            '메모_첫째', '메모_둘째'
        ]
        
        if books_df.empty:
            books_df = pd.DataFrame(columns=required_cols)
        else:
            for col in required_cols:
                if col not in books_df.columns:
                    books_df[col] = ""
            for col in ['반응_첫째', '반응_둘째']:
                books_df[col] = books_df[col].replace("", "선택 안 함").fillna("선택 안 함")
            for col in ['횟수_첫째', '횟수_둘째']:
                books_df[col] = pd.to_numeric(books_df[col], errors='coerce').fillna(0)
            for col in ['ISBN', '표지URL', '음원URL', '메모_첫째', '메모_둘째']:
                books_df[col] = books_df[col].astype(str)
            
    except gspread.exceptions.WorksheetNotFound:
        wks_books = sh.add_worksheet(title="books", rows=100, cols=20)
        wks_books.append_row([
            'ID', '제목', 'ISBN', '레벨', '상태', '표지URL', '음원URL',
            '횟수_첫째', '횟수_둘째', 
            '반응_첫째', '반응_둘째', 
            '메모_첫째', '메모_둘째'
        ])
        books_df = pd.DataFrame(columns=[
            'ID', '제목', 'ISBN', '레벨', '상태', '표지URL', '음원URL',
            '횟수_첫째', '횟수_둘째', 
            '반응_첫째', '반응_둘째', 
            '메모_첫째', '메모_둘째'
        ])

    # 2. Logs 데이터 로드
    try:
        wks_logs = sh.worksheet("logs")
        data_logs = wks_logs.get_all_records()
        logs_df = pd.DataFrame(data_logs)
        
        required_log_cols = ['날짜', '책ID', '제목', '레벨', '누가']
        for col in required_log_cols:
            if col not in logs_df.columns: logs_df[col] = ""

        if logs_df.empty:
            logs_df = pd.DataFrame(columns=required_log_cols)
        else:
            logs_df['날짜'] = pd.to_datetime(logs_df['날짜'], errors='coerce')
            
    except gspread.exceptions.WorksheetNotFound:
        wks_logs = sh.add_worksheet(title="logs", rows=100, cols=6)
        wks_logs.append_row(['날짜', '책ID', '제목', '레벨', '누가'])
        logs_df = pd.DataFrame(columns=['날짜', '책ID', '제목', '레벨', '누가'])

    # 3. 게시판(Board) 데이터 로드 (ID 컬럼 추가)
    try:
        wks_board = sh.worksheet("board")
        data_board = wks_board.get_all_records()
        board_df = pd.DataFrame(data_board)
        
        # ID 컬럼이 없으면 자동 생성 (기존 데이터 호환성)
        if 'ID' not in board_df.columns:
            board_df['ID'] = [str(uuid.uuid4()) for _ in range(len(board_df))]
        
        # 필수 컬럼 확인
        if '날짜' not in board_df.columns: board_df['날짜'] = ""
        if '내용' not in board_df.columns: board_df['내용'] = ""
            
        if board_df.empty:
             board_df = pd.DataFrame(columns=['ID', '날짜', '내용'])
             
    except gspread.exceptions.WorksheetNotFound:
        wks_board = sh.add_worksheet(title="board", rows=100, cols=3)
        wks_board.append_row(['ID', '날짜', '내용'])
        board_df = pd.DataFrame(columns=['ID', '날짜', '내용'])

    return books_df, logs_df, board_df

# --- [함수 3] 데이터 저장 (책) ---
def save_books(df):
    client = get_google_sheet_client()
    sh = client.open_by_url(SHEET_URL)
    wks = sh.worksheet("books")
    
    save_cols = [
        'ID', '제목', 'ISBN', '레벨', '상태', '표지URL', '음원URL',
        '횟수_첫째', '횟수_둘째', 
        '반응_첫째', '반응_둘째', 
        '메모_첫째', '메모_둘째'
    ]
    for col in save_cols:
        if col not in df.columns: df[col] = ""
            
    df_tosave = df[save_cols].copy()
    header = df_tosave.columns.values.tolist()
    data = df_tosave.fillna("").values.tolist()
    
    wks.clear()
    wks.update(range_name='A1', values=[header] + data)

# --- [함수 4] 데이터 저장 (게시판) ---
def save_board(df):
    client = get_google_sheet_client()
    sh = client.open_by_url(SHEET_URL)
    wks = sh.worksheet("board")
    
    save_cols = ['ID', '날짜', '내용']
    for col in save_cols:
        if col not in df.columns: df[col] = ""
            
    df_tosave = df[save_cols].copy()
    header = df_tosave.columns.values.tolist()
    data = df_tosave.fillna("").values.tolist()
    
    wks.clear()
    wks.update(range_name='A1', values=[header] + data)

# --- [함수 5] 로그 추가 ---
def add_log(book_id, title, level, who):
    client = get_google_sheet_client()
    sh = client.open_by_url(SHEET_URL)
    wks = sh.worksheet("logs")
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    wks.append_row([today_str, str(book_id), str(title), int(level), str(who)])

# --- [함수 6] 통합 스캔 ---
def scan_code(image_file):
    try:
        image = Image.open(image_file)
        attempts = [image, image.convert('L'), ImageEnhance.Contrast(image.convert('L')).enhance(2.0)]
        for img in attempts:
            decoded = decode(img)
            for obj in decoded: return obj.data.decode("utf-8")
    except Exception: pass
    return None

# --- [함수 7] 도서 검색 ---
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

st.set_page_config(page_title="아이 영어 독서 매니저 (Final)", layout="wide", page_icon="🧸")

with st.spinner("데이터 로딩 중..."):
    books_df, logs_df, board_df = load_data()

st.title("📚 Smart English Library v5.1")
st.caption("아이별 기록 | 게시판 수정/삭제 지원")

tab1, tab2, tab3, tab4 = st.tabs(["📊 대시보드", "📖 서재 관리", "➕ 새 책 등록", "📌 교육 정보 게시판"])

# --- [탭 1] 대시보드 ---
with tab1:
    st.markdown("### 📈 독서 통계")
    if books_df.empty:
        st.info("데이터가 없습니다.")
    else:
        # 1. 핵심 지표
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("총 보유 도서", f"{len(books_df)}권")
        c2.metric("누적 읽은 횟수 (전체)", f"{len(logs_df)}회")
        
        count_1 = int(books_df['횟수_첫째'].sum())
        count_2 = int(books_df['횟수_둘째'].sum())
        c3.metric("👦 첫째 누적 독서", f"{count_1}회")
        c4.metric("👧 둘째 누적 독서", f"{count_2}회")

        st.divider()
        
        # 2. 차트 영역
        col_chart1, col_chart2 = st.columns([2, 1])
        with col_chart1:
            st.subheader("🗓️ 월간 독서 추이")
            if not logs_df.empty:
                logs_df['Count'] = 1
                daily_counts = logs_df.groupby(['날짜', '누가']).size().reset_index(name='권수')
                fig = px.bar(daily_counts, x='날짜', y='권수', color='누가', barmode='group', title="일별 독서량 비교")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("기록이 없습니다.")

        with col_chart2:
            st.subheader("⭐ 반응(별점) 분포")
            target_child = st.radio("누구의 반응을 볼까요?", ["첫째", "둘째"], horizontal=True)
            col_name = '반응_첫째' if target_child == "첫째" else '반응_둘째'
            
            if not books_df.empty:
                r_data = books_df[books_df[col_name] != '선택 안 함'][col_name].value_counts().reset_index()
                r_data.columns = ['별점', '권수']
                if not r_data.empty:
                    fig_pie = px.pie(r_data, values='권수', names='별점', hole=0.4)
                    st.plotly_chart(fig_pie, use_container_width=True)
                else:
                    st.caption("별점 기록이 없습니다.")

# --- [탭 2] 서재 관리 ---
with tab2:
    c_head, c_sort = st.columns([3, 2])
    with c_head: st.subheader("보유 도서 목록")
    with c_sort:
        sort_option = st.selectbox("정렬 기준", ["최신 등록순", "첫째 많이 읽은 책", "둘째 많이 읽은 책", "레벨 높은 순"])

    if not books_df.empty:
        # 정렬 로직
        display_df = books_df.copy()
        display_df['횟수_첫째'] = pd.to_numeric(display_df['횟수_첫째'], errors='coerce').fillna(0)
        display_df['횟수_둘째'] = pd.to_numeric(display_df['횟수_둘째'], errors='coerce').fillna(0)
        
        if sort_option == "최신 등록순": display_df = display_df.iloc[::-1]
        elif sort_option == "첫째 많이 읽은 책": display_df = display_df.sort_values(by='횟수_첫째', ascending=False)
        elif sort_option == "둘째 많이 읽은 책": display_df = display_df.sort_values(by='횟수_둘째', ascending=False)
        elif sort_option == "레벨 높은 순": display_df = display_df.sort_values(by='레벨', ascending=False)

        st.caption(f"총 {len(display_df)}권의 책이 있습니다.")

        for i, row in display_df.iterrows():
            with st.container():
                c1, c2 = st.columns([1, 4])
                
                # [좌측] 이미지 & 미디어
                with c1:
                    img_url = row['표지URL'] if pd.notna(row['표지URL']) and str(row['표지URL']).startswith("http") else "https://via.placeholder.com/150?text=No+Image"
                    st.image(img_url, width=90)
                    
                    audio_url = str(row.get('음원URL', '')).strip()
                    if audio_url.startswith("http"):
                        st.link_button("🎧 음원 듣기", audio_url)
                    
                    search_query = f"{row['제목']} read a loud"
                    yt_url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(search_query)}"
                    st.link_button("▶️ Read Aloud", yt_url)

                # [우측] 정보 & 조작
                with c2:
                    new_title = st.text_input("제목", value=row['제목'], key=f"tt_{row['ID']}", label_visibility="collapsed")
                    
                    st.markdown(f"**읽은 횟수:** 👦 첫째 `{int(row['횟수_첫째'])}회` | 👧 둘째 `{int(row['횟수_둘째'])}회`")
                    
                    b_read1, b_read2, b_empty = st.columns([1, 1, 3])
                    if b_read1.button("👦 첫째 (+1)", key=f"r1_btn_{row['ID']}"):
                        idx = books_df[books_df['ID'] == row['ID']].index[0]
                        books_df.at[idx, '횟수_첫째'] += 1
                        save_books(books_df)
                        add_log(row['ID'], row['제목'], row['레벨'], "첫째")
                        st.toast(f"👦 첫째가 '{row['제목']}'을 읽었습니다!")
                        st.rerun()
                        
                    if b_read2.button("👧 둘째 (+1)", key=f"r2_btn_{row['ID']}"):
                        idx = books_df[books_df['ID'] == row['ID']].index[0]
                        books_df.at[idx, '횟수_둘째'] += 1
                        save_books(books_df)
                        add_log(row['ID'], row['제목'], row['레벨'], "둘째")
                        st.toast(f"👧 둘째가 '{row['제목']}'을 읽었습니다!")
                        st.rerun()

                    with st.expander("📝 상세 기록 수정 (별점/메모/URL)"):
                        # 기본 정보
                        c_edit1, c_edit2 = st.columns(2)
                        with c_edit1:
                            new_lvl = st.selectbox("레벨", [1,2,3,4,5], index=int(row['레벨'])-1, key=f"lv_{row['ID']}")
                            new_sts = st.selectbox("상태", ["읽지 않음", "읽는 중", "완독"], index=["읽지 않음", "읽는 중", "완독"].index(row['상태']) if row['상태'] in ["읽지 않음", "읽는 중", "완독"] else 0, key=f"st_{row['ID']}")
                        with c_edit2:
                            new_img = st.text_input("표지 URL", value=row['표지URL'], key=f"url_{row['ID']}")
                            new_aud = st.text_input("음원 URL", value=row.get('음원URL', ''), key=f"aud_{row['ID']}")
                            qr_scan_method = st.radio("QR 입력", ["직접 촬영", "갤러리"], horizontal=True, key=f"qm_{row['ID']}")
                            qr_file = None
                            if qr_scan_method == "직접 촬영": qr_file = st.camera_input("QR 촬영", key=f"qc_{row['ID']}")
                            else: qr_file = st.file_uploader("QR 사진", type=['jpg','png'], key=f"qu_{row['ID']}")
                            if qr_file:
                                code = scan_code(qr_file)
                                if code: 
                                    st.success("인식 성공")
                                    new_aud = code

                        st.markdown("---")
                        col_k1, col_k2 = st.columns(2)
                        with col_k1:
                            st.markdown("##### 👦 첫째 기록")
                            cur_r1 = row.get('반응_첫째', '선택 안 함')
                            idx_r1 = STAR_OPTIONS.index(cur_r1) if cur_r1 in STAR_OPTIONS else 0
                            new_r1 = st.selectbox("별점 (첫째)", STAR_OPTIONS, index=idx_r1, key=f"str1_{row['ID']}")
                            new_m1 = st.text_area("메모 (첫째)", value=row.get('메모_첫째', ''), key=f"mem1_{row['ID']}", height=80)
                            
                        with col_k2:
                            st.markdown("##### 👧 둘째 기록")
                            cur_r2 = row.get('반응_둘째', '선택 안 함')
                            idx_r2 = STAR_OPTIONS.index(cur_r2) if cur_r2 in STAR_OPTIONS else 0
                            new_r2 = st.selectbox("별점 (둘째)", STAR_OPTIONS, index=idx_r2, key=f"str2_{row['ID']}")
                            new_m2 = st.text_area("메모 (둘째)", value=row.get('메모_둘째', ''), key=f"mem2_{row['ID']}", height=80)

                        btn_col1, btn_col2 = st.columns([1, 4])
                        if btn_col1.button("💾 저장", key=f"sv_{row['ID']}"):
                            idx = books_df[books_df['ID'] == row['ID']].index[0]
                            books_df.at[idx, '제목'] = new_title
                            books_df.at[idx, '레벨'] = new_lvl
                            books_df.at[idx, '상태'] = new_sts
                            books_df.at[idx, '표지URL'] = new_img
                            books_df.at[idx, '음원URL'] = new_aud
                            books_df.at[idx, '반응_첫째'] = new_r1
                            books_df.at[idx, '반응_둘째'] = new_r2
                            books_df.at[idx, '메모_첫째'] = new_m1
                            books_df.at[idx, '메모_둘째'] = new_m2
                            save_books(books_df)
                            st.toast("저장되었습니다.")
                            st.rerun()

                        if btn_col2.button("🗑 삭제", key=f"del_{row['ID']}"):
                            if st.session_state.get(f"chk_{row['ID']}"):
                                idx = books_df[books_df['ID'] == row['ID']].index[0]
                                books_df = books_df.drop(idx)
                                save_books(books_df)
                                st.rerun()
                            else:
                                st.session_state[f"chk_{row['ID']}"] = True
                                st.warning("삭제하려면 한 번 더 누르세요.")
                st.divider()

# --- [탭 3] 새 책 등록 ---
with tab3:
    st.subheader("새 책 등록")
    if 'reg_title' not in st.session_state: 
        st.session_state.update({'reg_title':"", 'reg_isbn':"", 'reg_img':"", 'reg_audio':"", 'search_done':False})

    method = st.radio("입력 방식", ["📸 바코드 촬영", "🖼️ 갤러리 업로드", "✍️ 수동 입력"], horizontal=True, label_visibility="collapsed")
    img_file = None
    if method == "📸 바코드 촬영": img_file = st.camera_input("바코드", key="cam_reg")
    elif method == "🖼️ 갤러리 업로드": img_file = st.file_uploader("바코드 사진", type=['jpg','png'])

    if img_file and not st.session_state['search_done']:
        code = scan_code(img_file)
        if code:
            st.toast("인식 성공!")
            if st.session_state['reg_isbn'] != code:
                with st.spinner("책 찾는 중..."):
                    t, i = search_book_info(code)
                    st.session_state.update({'reg_isbn': code, 'reg_title': t or "", 'reg_img': i or "", 'search_done': True})
                    st.rerun()
    
    if method == "✍️ 수동 입력":
        manual = st.text_input("ISBN 입력", value=st.session_state['reg_isbn'])
        if manual and manual != st.session_state.get('last_m', ''):
             with st.spinner("검색 중..."):
                t, i = search_book_info(manual)
                st.session_state.update({'reg_isbn': manual, 'reg_title': t or "", 'reg_img': i or "", 'last_m': manual})
                st.rerun()

    st.divider()
    
    with st.form("new_book"):
        c1, c2 = st.columns(2)
        with c1:
            title = st.text_input("제목 *", value=st.session_state['reg_title'])
            isbn = st.text_input("ISBN", value=st.session_state['reg_isbn'])
            level = st.selectbox("레벨", [1,2,3,4,5])
        with c2:
            img_url = st.text_input("표지 URL", value=st.session_state['reg_img'])
            aud_url = st.text_input("음원 URL (직접 입력)", value=st.session_state['reg_audio'])

        st.markdown("##### 초기 반응 기록 (선택)")
        rc1, rc2 = st.columns(2)
        r1 = rc1.selectbox("첫째 별점", STAR_OPTIONS)
        r2 = rc2.selectbox("둘째 별점", STAR_OPTIONS)
        
        submitted = st.form_submit_button("등록하기")
        if submitted:
            if not title: st.error("제목을 입력해주세요.")
            else:
                new_data = {
                    'ID': str(uuid.uuid4()), '제목': title, 'ISBN': isbn, '레벨': level, '상태': '읽지 않음',
                    '표지URL': img_url, '음원URL': aud_url,
                    '횟수_첫째': 0, '횟수_둘째': 0,
                    '반응_첫째': r1, '반응_둘째': r2,
                    '메모_첫째': "", '메모_둘째': ""
                }
                books_df = pd.concat([books_df, pd.DataFrame([new_data])], ignore_index=True)
                save_books(books_df)
                
                for k in ['reg_title', 'reg_isbn', 'reg_img', 'reg_audio', 'search_done', 'last_m']:
                    if k in st.session_state: del st.session_state[k]
                st.success("등록 완료!")
                st.rerun()
                
    st.markdown("###### 🎵 음원 QR 등록 (선택)")
    q_method = st.radio("QR 스캔", ["촬영", "갤러리"], horizontal=True, key="qr_m_reg")
    q_file = None
    if q_method == "촬영": q_file = st.camera_input("QR 촬영", key="qc_reg")
    else: q_file = st.file_uploader("QR 사진", key="qu_reg")
    
    if q_file:
        c = scan_code(q_file)
        if c: 
            st.success("QR 인식됨")
            if st.session_state['reg_audio'] != c:
                st.session_state['reg_audio'] = c
                st.rerun()

# --- [탭 4] 교육 정보 게시판 (수정/삭제 지원) ---
with tab4:
    st.header("📌 엄마표 영어 정보 게시판")
    st.caption("유용한 유튜브 채널, 교육 팁, 아이디어 등을 메모해두세요.")
    
    # 1. 새 글 작성 폼
    with st.form("board_form", clear_on_submit=True):
        content = st.text_area("내용 입력", height=100, placeholder="예: Super Simple Songs 채널이 흘려듣기에 좋음.")
        if st.form_submit_button("게시글 저장"):
            if content:
                # 새 글 저장 로직
                new_post = {
                    'ID': str(uuid.uuid4()),
                    '날짜': datetime.now().strftime("%Y-%m-%d %H:%M"),
                    '내용': content
                }
                board_df = pd.concat([board_df, pd.DataFrame([new_post])], ignore_index=True)
                save_board(board_df)
                st.success("저장되었습니다.")
                st.rerun()
            else:
                st.warning("내용을 입력해주세요.")

    st.divider()
    st.subheader("📋 저장된 메모")
    
    if not board_df.empty:
        # 최신순 정렬
        for i, row in board_df.iloc[::-1].iterrows():
            with st.container():
                st.markdown(f"**📅 {row['날짜']}**")
                st.write(row['내용'])
                
                # 수정/삭제 기능 (Expander)
                with st.expander("✏️ 수정 / 🗑 삭제"):
                    edit_content = st.text_area("내용 수정", value=row['내용'], key=f"bd_edit_{row['ID']}")
                    
                    c_btn1, c_btn2 = st.columns([1, 4])
                    if c_btn1.button("수정 저장", key=f"bd_sav_{row['ID']}"):
                        # 수정 로직
                        idx = board_df[board_df['ID'] == row['ID']].index[0]
                        board_df.at[idx, '내용'] = edit_content
                        save_board(board_df)
                        st.toast("수정되었습니다.")
                        st.rerun()
                        
                    if c_btn2.button("삭제", key=f"bd_del_{row['ID']}"):
                        # 삭제 로직 (확인 없이 즉시 삭제 or 세션 체크 가능)
                        if st.session_state.get(f"bd_chk_{row['ID']}"):
                            idx = board_df[board_df['ID'] == row['ID']].index[0]
                            board_df = board_df.drop(idx)
                            save_board(board_df)
                            st.rerun()
                        else:
                            st.session_state[f"bd_chk_{row['ID']}"] = True
                            st.warning("한 번 더 누르면 삭제됩니다.")
                st.divider()
    else:
        st.info("아직 등록된 글이 없습니다.")
