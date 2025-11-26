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

# --- [반응 옵션 정의] ---
REACTION_OPTIONS = ["선택 안 함", "😄 재미있어요", "😓 어려워요", "🎨 그림이 좋았어요", "🐣 스스로 읽었어요", "💤 관심 없어요"]

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

# --- [함수 2] 데이터 로드 ---
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
            'ID', '제목', 'ISBN', '레벨', '읽은횟수', '상태', 
            '반응_첫째', '반응_둘째', '반응_메모', '표지URL', '음원URL'
        ]
        
        if books_df.empty:
            books_df = pd.DataFrame(columns=required_cols)
        else:
            for col in required_cols:
                if col not in books_df.columns:
                    books_df[col] = ""
            for col in ['반응_첫째', '반응_둘째']:
                books_df[col] = books_df[col].replace("", "선택 안 함").fillna("선택 안 함")
            for col in ['ISBN', '표지URL', '음원URL', '반응_메모']:
                books_df[col] = books_df[col].astype(str)
            
    except gspread.exceptions.WorksheetNotFound:
        wks_books = sh.add_worksheet(title="books", rows=100, cols=15)
        wks_books.append_row([
            'ID', '제목', 'ISBN', '레벨', '읽은횟수', '상태', 
            '반응_첫째', '반응_둘째', '반응_메모', '표지URL', '음원URL'
        ])
        books_df = pd.DataFrame(columns=[
            'ID', '제목', 'ISBN', '레벨', '읽은횟수', '상태', 
            '반응_첫째', '반응_둘째', '반응_메모', '표지URL', '음원URL'
        ])

    # 2. Logs 데이터 로드
    try:
        wks_logs = sh.worksheet("logs")
        data_logs = wks_logs.get_all_records()
        logs_df = pd.DataFrame(data_logs)
        
        if logs_df.empty:
            logs_df = pd.DataFrame(columns=['날짜', '책ID', '제목', '레벨'])
        else:
            logs_df['날짜'] = pd.to_datetime(logs_df['날짜'])
            
    except gspread.exceptions.WorksheetNotFound:
        wks_logs = sh.add_worksheet(title="logs", rows=100, cols=5)
        wks_logs.append_row(['날짜', '책ID', '제목', '레벨'])
        logs_df = pd.DataFrame(columns=['날짜', '책ID', '제목', '레벨'])

    return books_df, logs_df

# --- [함수 3] 데이터 저장 ---
def save_books(df):
    client = get_google_sheet_client()
    sh = client.open_by_url(SHEET_URL)
    wks = sh.worksheet("books")
    
    save_cols = [
        'ID', '제목', 'ISBN', '레벨', '읽은횟수', '상태', 
        '반응_첫째', '반응_둘째', '반응_메모', '표지URL', '음원URL'
    ]
    for col in save_cols:
        if col not in df.columns: df[col] = ""
            
    df_tosave = df[save_cols].copy()
    header = df_tosave.columns.values.tolist()
    data = df_tosave.fillna("").values.tolist()
    
    wks.clear()
    wks.update(range_name='A1', values=[header] + data)

# --- [함수 4] 로그 추가 ---
def add_log(book_id, title, level):
    client = get_google_sheet_client()
    sh = client.open_by_url(SHEET_URL)
    wks = sh.worksheet("logs")
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    wks.append_row([today_str, str(book_id), str(title), int(level)])

# --- [함수 5] 통합 스캔 (바코드 & QR) ---
def scan_code(image_file):
    try:
        image = Image.open(image_file)
        attempts = [
            image,
            image.convert('L'), 
            ImageEnhance.Contrast(image.convert('L')).enhance(2.0)
        ]
        for img in attempts:
            decoded = decode(img)
            for obj in decoded:
                return obj.data.decode("utf-8")
    except Exception: pass
    return None

# --- [함수 6] 도서 정보 검색 ---
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

st.set_page_config(page_title="아이 영어 독서 매니저 (Pro)", layout="wide", page_icon="☁️")

# 데이터 로드
with st.spinner("구글 시트와 연결 중..."):
    books_df, logs_df = load_data()

st.title("📚 Smart English Library v4.3")
st.caption("음원 듣기 복구 | 갤러리 업로드 지원 (인식률 향상)")

tab1, tab2, tab3 = st.tabs(["📊 대시보드", "📖 서재 관리", "➕ 새 책 등록"])

# --- [탭 1] 대시보드 ---
with tab1:
    st.markdown("### 📈 독서 현황")
    if logs_df.empty and books_df.empty:
        st.info("데이터가 없습니다.")
    else:
        today = pd.Timestamp.now().normalize()
        this_month_start = today.replace(day=1)
        
        daily_reads = logs_df[logs_df['날짜'] == today]
        month_reads = logs_df[logs_df['날짜'] >= this_month_start]
        
        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("보유 도서", f"{len(books_df)}권")
        kpi2.metric("총 읽은 횟수", f"{len(logs_df)}회")
        kpi3.metric("이번 달", f"{len(month_reads)}회")
        kpi4.metric("오늘", f"{len(daily_reads)}권")
        
        st.divider()
        c1, c2 = st.columns([1, 1])
        with c1:
            st.subheader("🗓️ 월간 추이")
            if not logs_df.empty:
                last_30 = logs_df[logs_df['날짜'] >= (today - timedelta(days=29))]
                daily_counts = last_30.groupby('날짜').size().reset_index(name='권수')
                fig = px.bar(daily_counts, x='날짜', y='권수', text_auto=True, color_discrete_sequence=['#4C78A8'])
                st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.subheader("🧸 아이들 반응")
            if not books_df.empty:
                t1, t2 = st.tabs(["첫째", "둘째"])
                with t1:
                    r1 = books_df[books_df['반응_첫째'] != '선택 안 함']['반응_첫째'].value_counts().reset_index()
                    r1.columns = ['반응', '권수']
                    if not r1.empty: st.plotly_chart(px.pie(r1, values='권수', names='반응', hole=0.4), use_container_width=True)
                with t2:
                    r2 = books_df[books_df['반응_둘째'] != '선택 안 함']['반응_둘째'].value_counts().reset_index()
                    r2.columns = ['반응', '권수']
                    if not r2.empty: st.plotly_chart(px.pie(r2, values='권수', names='반응', hole=0.4), use_container_width=True)

# --- [탭 2] 서재 관리 (음원 버튼 복구 및 갤러리 스캔 추가) ---
with tab2:
    c_head, c_sort = st.columns([3, 2])
    with c_head: st.subheader("보유 도서 목록")
    with c_sort:
        sort_option = st.selectbox("정렬", ["최신 등록순", "자주 읽은 책", "안 읽은 책", "레벨 높은 순"])

    if not books_df.empty:
        books_df['읽은횟수'] = pd.to_numeric(books_df['읽은횟수'], errors='coerce').fillna(0)
        books_df['레벨'] = pd.to_numeric(books_df['레벨'], errors='coerce').fillna(1)
        
        display_df = books_df.copy()
        if sort_option == "최신 등록순": display_df = display_df.iloc[::-1]
        elif sort_option == "자주 읽은 책": display_df = display_df.sort_values(by='읽은횟수', ascending=False)
        elif sort_option == "안 읽은 책": display_df = display_df.sort_values(by='읽은횟수', ascending=True)
        elif sort_option == "레벨 높은 순": display_df = display_df.sort_values(by='레벨', ascending=False)

        st.caption(f"총 {len(display_df)}권")

        for i, row in display_df.iterrows():
            with st.container():
                c1, c2 = st.columns([1, 5])
                
                # [좌측: 표지 및 음원 듣기 버튼]
                with c1: 
                    img_url = row['표지URL'] if pd.notna(row['표지URL']) and str(row['표지URL']).startswith("http") else "https://via.placeholder.com/150?text=No+Image"
                    st.image(img_url, width=80)
                    
                    # [수정됨] 음원 듣기 버튼 강제 표시 로직
                    audio_url = str(row.get('음원URL', '')).strip()
                    if audio_url.startswith("http"):
                        st.link_button("🎧 음원 듣기", audio_url, help="클릭하면 음원이 재생됩니다.")
                    else:
                        st.caption("음원 없음")

                # [우측: 정보 및 기능]
                with c2:
                    new_title = st.text_input("제목", value=row['제목'], key=f"t_{row['ID']}", label_visibility="collapsed")
                    
                    # [수정됨] 상세 수정 메뉴 (갤러리 스캔 지원)
                    with st.expander("📝 상세 정보 / 반응 기록 / QR 등록"):
                        st.caption(f"ISBN: {row['ISBN']}")
                        new_img = st.text_input("표지 URL", value=row['표지URL'], key=f"img_{row['ID']}")
                        
                        st.markdown("---")
                        st.markdown("**🎵 음원(QR) 관리**")
                        
                        # 1. 텍스트 입력
                        new_audio = st.text_input("음원 링크 (직접 입력)", value=audio_url, key=f"aud_{row['ID']}")
                        
                        # 2. 스캔 방식 선택 (카메라 vs 갤러리)
                        scan_type = st.radio("QR 스캔 방식", ["📸 직접 촬영", "🖼️ 갤러리 사진 업로드"], horizontal=True, key=f"stype_{row['ID']}")
                        
                        scan_img = None
                        if scan_type == "📸 직접 촬영":
                            scan_img = st.camera_input("QR 촬영", key=f"cam_{row['ID']}")
                        else:
                            scan_img = st.file_uploader("QR 사진 선택", type=['png', 'jpg', 'jpeg'], key=f"upl_{row['ID']}")
                        
                        # 스캔 처리
                        if scan_img:
                            scanned = scan_code(scan_img)
                            if scanned:
                                st.success(f"QR 인식됨: {scanned}")
                                new_audio = scanned
                        
                        st.markdown("---")
                        st.markdown("**🧸 아이 반응**")
                        rc1, rc2 = st.columns(2)
                        cur_r1 = row.get('반응_첫째', '선택 안 함')
                        cur_r2 = row.get('반응_둘째', '선택 안 함')
                        idx1 = REACTION_OPTIONS.index(cur_r1) if cur_r1 in REACTION_OPTIONS else 0
                        idx2 = REACTION_OPTIONS.index(cur_r2) if cur_r2 in REACTION_OPTIONS else 0
                        
                        new_r1 = rc1.selectbox("첫째", REACTION_OPTIONS, index=idx1, key=f"r1_{row['ID']}")
                        new_r2 = rc2.selectbox("둘째", REACTION_OPTIONS, index=idx2, key=f"r2_{row['ID']}")
                        new_memo = st.text_area("메모", value=row.get('반응_메모', ''), key=f"m_{row['ID']}", height=60)

                    # 레벨/상태
                    ec1, ec2 = st.columns([1, 1.2])
                    new_lvl = ec1.selectbox("레벨", [1,2,3,4,5], index=int(row['레벨'])-1, key=f"l_{row['ID']}", label_visibility="collapsed")
                    s_idx = ["읽지 않음", "읽는 중", "완독"].index(row['상태']) if row['상태'] in ["읽지 않음", "읽는 중", "완독"] else 0
                    new_sts = ec2.selectbox("상태", ["읽지 않음", "읽는 중", "완독"], index=s_idx, key=f"s_{row['ID']}", label_visibility="collapsed")

                    # 저장
                    if (new_title != row['제목'] or new_img != row['표지URL'] or new_audio != audio_url or
                        new_lvl != row['레벨'] or new_sts != row['상태'] or
                        new_r1 != cur_r1 or new_r2 != cur_r2 or new_memo != row.get('반응_메모', '')):
                        
                        with st.spinner("저장 중..."):
                            real_idx = books_df[books_df['ID'] == row['ID']].index[0]
                            books_df.at[real_idx, '제목'] = new_title
                            books_df.at[real_idx, '표지URL'] = new_img
                            books_df.at[real_idx, '음원URL'] = new_audio
                            books_df.at[real_idx, '레벨'] = new_lvl
                            books_df.at[real_idx, '상태'] = new_sts
                            books_df.at[real_idx, '반응_첫째'] = new_r1
                            books_df.at[real_idx, '반응_둘째'] = new_r2
                            books_df.at[real_idx, '반응_메모'] = new_memo
                            save_books(books_df)
                        st.toast("✅ 수정되었습니다!")
                        st.rerun()

                    # 읽기/삭제 버튼
                    b1, b3 = st.columns([2, 1])
                    if b1.button(f"➕ 읽기 ({int(row['읽은횟수'])})", key=f"read_{row['ID']}"):
                        real_idx = books_df[books_df['ID'] == row['ID']].index[0]
                        books_df.at[real_idx, '읽은횟수'] += 1
                        if books_df.at[real_idx, '상태'] == '읽지 않음': books_df.at[real_idx, '상태'] = '읽는 중'
                        save_books(books_df)
                        add_log(row['ID'], new_title, new_lvl)
                        st.toast("기록 완료!")
                        st.rerun()

                    if b3.button("🗑 삭제", key=f"del_{row['ID']}"):
                        if st.session_state.get(f"confirm_{row['ID']}"):
                             real_idx = books_df[books_df['ID'] == row['ID']].index[0]
                             books_df = books_df.drop(real_idx)
                             save_books(books_df)
                             st.rerun()
                        else:
                             st.session_state[f"confirm_{row['ID']}"] = True
                             st.warning("삭제 확인")
                st.divider()
    else: st.info("등록된 책이 없습니다.")

# --- [탭 3] 새 책 등록 (갤러리 업로드 추가) ---
with tab3:
    st.subheader("새 책 등록")
    if 'reg_title' not in st.session_state: 
        st.session_state.update({'reg_title':"", 'reg_isbn':"", 'reg_img':"", 'reg_audio':"", 'search_done':False})

    st.markdown("##### 1. 책 찾기")
    # [수정됨] 입력 방식에 갤러리 업로드 명확히 구분
    input_method = st.radio("방식 선택", ["📸 바코드 촬영", "🖼️ 바코드 사진 업로드 (갤러리)", "✍️ 수동 입력"], horizontal=True, label_visibility="collapsed")
    
    img_file = None 
    if input_method == "📸 바코드 촬영": img_file = st.camera_input("바코드 촬영", key="cam_reg")
    elif input_method == "🖼️ 바코드 사진 업로드 (갤러리)": img_file = st.file_uploader("바코드 사진 선택", type=['png', 'jpg', 'jpeg'])

    if img_file and not st.session_state['search_done']:
        code = scan_code(img_file)
        if code:
            st.toast(f"인식됨: {code}")
            if st.session_state['reg_isbn'] != code:
                with st.spinner("검색 중..."):
                    t, i = search_book_info(code)
                    st.session_state.update({'reg_isbn': code, 'reg_title': t or "", 'reg_img': i or "", 'search_done': True})
                    st.rerun()
        else:
            st.warning("바코드를 인식하지 못했습니다. 사진을 더 선명하게 찍거나 수동 입력을 이용하세요.")

    if input_method == "✍️ 수동 입력":
        manual = st.text_input("ISBN 입력", value=st.session_state['reg_isbn'])
        if manual and manual != st.session_state.get('last_manual', ''):
             with st.spinner("검색 중..."):
                t, i = search_book_info(manual)
                st.session_state.update({'reg_isbn': manual, 'reg_title': t or "", 'reg_img': i or "", 'last_manual': manual})
                st.rerun()
    
    st.divider()

    with st.form("reg_form", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            title = st.text_input("제목 *", value=st.session_state['reg_title'])
            isbn = st.text_input("ISBN", value=st.session_state['reg_isbn'])
            level = st.selectbox("레벨", [1,2,3,4,5])
            status = st.selectbox("상태", ["읽지 않음", "읽는 중", "완독"])
        with c2:
            img_url = st.text_input("표지 URL", value=st.session_state['reg_img'])
            audio_url = st.text_input("음원 주소 (QR은 아래 이용)", value=st.session_state['reg_audio'])

        st.markdown("**🧸 아이 반응 & 메모**")
        rc1, rc2 = st.columns(2)
        r1 = rc1.selectbox("첫째", REACTION_OPTIONS)
        r2 = rc2.selectbox("둘째", REACTION_OPTIONS)
        note = st.text_area("메모", height=60, placeholder="내용 입력")

        if st.form_submit_button("등록하기"):
            if not title: st.error("제목은 필수입니다.")
            else:
                with st.spinner("저장 중..."):
                    new_data = {
                        'ID': str(uuid.uuid4()), 
                        '제목': title, 'ISBN': isbn, '레벨': level, 
                        '읽은횟수': 0, '상태': status, 
                        '반응_첫째': r1, '반응_둘째': r2, '반응_메모': note,
                        '표지URL': img_url, '음원URL': audio_url
                    }
                    books_df = pd.concat([books_df, pd.DataFrame([new_data])], ignore_index=True)
                    save_books(books_df)
                    
                    for k in ['reg_title', 'reg_isbn', 'reg_img', 'reg_audio', 'search_done', 'last_manual']:
                        if k in st.session_state: del st.session_state[k]
                st.success("등록 완료!")
                st.rerun()

    # (폼 밖) 음원 QR 스캔 (방식 선택 추가)
    st.markdown("##### 🎵 음원 QR 스캔 (선택)")
    audio_scan_method = st.radio("QR 스캔 방식", ["📸 직접 촬영", "🖼️ 갤러리 사진 업로드"], horizontal=True, key="aud_method")
    
    qr_img = None
    if audio_scan_method == "📸 직접 촬영":
        qr_img = st.camera_input("QR 촬영", key="cam_audio")
    else:
        qr_img = st.file_uploader("QR 사진 업로드", type=['png', 'jpg'], key="file_audio")
        
    if qr_img:
        code = scan_code(qr_img)
        if code:
            st.success("QR 인식 성공!")
            if st.session_state['reg_audio'] != code:
                st.session_state['reg_audio'] = code
                st.rerun()
