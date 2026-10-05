import os
import re
import copy
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client

st.set_page_config(page_title="키노사다리 2중 지울픽 분석기", page_icon="⚡", layout="centered")

@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    key = st.secrets.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY")
    if not url or not key:
        return None
    try:
        return create_client(url, key)
    except Exception:
        return None

supabase = init_supabase()

st.markdown("""
<style>
    html, body { overscroll-behavior-y: contain !important; }
    .stApp { overscroll-behavior-y: none !important; }
    .block-container { padding: 0.8rem 0.3rem 80px 0.3rem !important; }
    h1, h2, h3 { display: none !important; }
    p, div, span { font-size: 0.8rem !important; line-height: 1.3 !important; }

    div[data-testid="stHorizontalBlock"] {
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        width: 100% !important;
        gap: 2px !important;
    }
    div[data-testid="stHorizontalBlock"] > div {
        flex: 1 1 25% !important;
        width: 25% !important;
        min-width: 0px !important;
    }
    div[data-testid="stHorizontalBlock"] button {
        width: 100% !important;
        padding: 0.4rem 0rem !important;
        font-size: 0.85rem !important;
        font-weight: bold !important;
    }

    .ctrl-container .stButton { width: 100% !important; margin-bottom: 0.2rem !important; }
    .ctrl-container .stButton>button {
        padding: 0.5rem 0.1rem !important; font-size: 0.88rem !important;
        font-weight: bold !important; width: 100% !important;
    }

    .ctrl-container div[data-testid="stDownloadButton"] { width: 100% !important; margin-bottom: 0.2rem !important; }
    .ctrl-container div[data-testid="stDownloadButton"]>button {
        padding: 0.5rem 0.1rem !important; font-size: 0.88rem !important;
        font-weight: bold !important; width: 100% !important;
        background-color: #28a745 !important; color: white !important; border: none !important;
    }

    hr { margin: 0.3rem 0 !important; border-color: #ddd !important; }
</style>
""", unsafe_allow_html=True)

MAX_DATA_SIZE = 500
ALL_COMBOS = ['우삼', '우사', '좌삼', '좌사']

ITEM_FULL_MAP = {
    '우사': '우사짝',
    '우삼': '우삼홀',
    '좌사': '좌사홀',
    '좌삼': '좌삼짝'
}

ITEM_MAP = {
    '우사': ('우', '사', '짝'),
    '우삼': ('우', '삼', '홀'),
    '좌사': ('좌', '사', '홀'),
    '좌삼': ('좌', '삼', '짝')
}

OPPOSITE_SINGLE_MAP = {
    '우': '좌', '좌': '우',
    '삼': '사', '사': '삼',
    '홀': '짝', '짝': '홀'
}

WEEKDAYS = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']

def get_current_realtime_round():
    kst = timezone(timedelta(hours=9))
    now = datetime.now(kst)
    total_minutes = now.hour * 60 + now.minute
    current_round = (total_minutes // 5) + 1
    if current_round > 288:
        current_round = 288
    return now.strftime("%Y-%m-%d"), current_round

def load_data():
    if not supabase: return []
    try:
        res = supabase.table("ladder_records").select("date, round, result, id").order("id", desc=True).limit(MAX_DATA_SIZE).execute()
        if res and res.data:
            sorted_records = sorted(res.data, key=lambda x: int(x['id']))
            return [{'date': str(r['date']).strip(), 'round': int(r['round']), 'result': str(r['result']).strip()} for r in sorted_records]
        return []
    except Exception: return []

def sync_all_records_db(records):
    if not supabase: return
    try:
        trimmed_records = records[-MAX_DATA_SIZE:] if records else []
        fetch_ids = supabase.table("ladder_records").select("id").execute()
        if fetch_ids and fetch_ids.data:
            id_list = [r['id'] for r in fetch_ids.data]
            for i in range(0, len(id_list), 200):
                supabase.table("ladder_records").delete().in_("id", id_list[i:i + 200]).execute()

        if trimmed_records:
            bulk_list = [{"date": str(r['date']).strip(), "round": int(r['round']), "result": str(r['result']).strip()} for r in trimmed_records]
            for i in range(0, len(bulk_list), 100):
                supabase.table("ladder_records").insert(bulk_list[i:i + 100]).execute()
    except Exception: pass

def add_single_record_db(date_str, round_num, result_str):
    if supabase:
        try:
            supabase.table("ladder_records").insert({"date": str(date_str), "round": int(round_num), "result": str(result_str)}).execute()
        except Exception: pass

def delete_last_record_db():
    if supabase:
        try:
            res = supabase.table("ladder_records").select("id").order("id", desc=True).limit(1).execute()
            if res and res.data:
                supabase.table("ladder_records").delete().eq("id", res.data[0]['id']).execute()
        except Exception: pass

# 🎯 축별 점수 산출 함수 (투박스/꺾임 규칙)
def score_engine1_axis(stream, val1, val2):
    n = len(stream)
    if n < 2: return {val1: 50, val2: 50}

    last, prev = stream[-1], stream[-2]

    if prev == last:
        # 전전 == 전 ➔ 다른 값 예측
        return {OPPOSITE_SINGLE_MAP[last]: 80, last: 20}
    else:
        # 전전 != 전 ➔ 같은 값 예측
        return {last: 80, OPPOSITE_SINGLE_MAP[last]: 20}

# 🎯 축별 점수 산출 함수 (연속성/유지 규칙)
def score_engine2_axis(stream, val1, val2):
    n = len(stream)
    if n < 2: return {val1: 50, val2: 50}

    last, prev = stream[-1], stream[-2]

    if prev == last:
        # 전전 == 전 ➔ 같은 값 예측
        return {last: 80, OPPOSITE_SINGLE_MAP[last]: 20}
    else:
        # 전전 != 전 ➔ 다른 값 예측
        return {OPPOSITE_SINGLE_MAP[last]: 80, last: 20}

# 🎯 [엔진 1: 4순위(최저 확률) 조합 선별]
def get_engine1_picks(records_tuple, prev_failures):
    valid = [r[2] for r in records_tuple if r[2] in ALL_COMBOS]
    if len(valid) < 3: return '우삼', '좌사', '좌'

    s_scores = score_engine1_axis([ITEM_MAP[r][0] for r in valid], '우', '좌')
    l_scores = score_engine1_axis([ITEM_MAP[r][1] for r in valid], '삼', '사')
    o_scores = score_engine1_axis([ITEM_MAP[r][2] for r in valid], '홀', '짝')

    combo_scores = {
        '우삼': s_scores.get('우',0) + l_scores.get('삼',0) + o_scores.get('홀',0),
        '우사': s_scores.get('우',0) + l_scores.get('사',0) + o_scores.get('짝',0),
        '좌삼': s_scores.get('좌',0) + l_scores.get('삼',0) + o_scores.get('짝',0),
        '좌사': s_scores.get('좌',0) + l_scores.get('사',0) + o_scores.get('홀',0)
    }

    sorted_combos = sorted(combo_scores.items(), key=lambda x: x[1], reverse=True)
    rec_combo = sorted_combos[0][0]   # 1순위
    avoid_combo = sorted_combos[-1][0] # 4순위 (지울픽)

    avoid_s, avoid_l, avoid_o = ITEM_MAP[avoid_combo]
    element_scores = [
        (avoid_s, s_scores.get(avoid_s, 0)),
        (avoid_l, l_scores.get(avoid_l, 0)),
        (avoid_o, o_scores.get(avoid_o, 0))
    ]
    single_hole = sorted(element_scores, key=lambda x: x[1])[0][0]

    return rec_combo, avoid_combo, single_hole

# 🎯 [엔진 2: 4순위(최저 확률) 조합 선별]
def get_engine2_avoid_pattern(records_tuple, last_e2_failed=False):
    valid = [r[2] for r in records_tuple if r[2] in ALL_COMBOS]
    if len(valid) < 3: return '우삼', '기본', '우'

    s_scores = score_engine2_axis([ITEM_MAP[r][0] for r in valid], '우', '좌')
    l_scores = score_engine2_axis([ITEM_MAP[r][1] for r in valid], '삼', '사')
    o_scores = score_engine2_axis([ITEM_MAP[r][2] for r in valid], '홀', '짝')

    combo_scores = {
        '우삼': s_scores.get('우',0) + l_scores.get('삼',0) + o_scores.get('홀',0),
        '우사': s_scores.get('우',0) + l_scores.get('사',0) + o_scores.get('짝',0),
        '좌삼': s_scores.get('좌',0) + l_scores.get('삼',0) + o_scores.get('짝',0),
        '좌사': s_scores.get('좌',0) + l_scores.get('사',0) + o_scores.get('홀',0)
    }

    sorted_combos = sorted(combo_scores.items(), key=lambda x: x[1], reverse=True)
    avoid_combo = sorted_combos[-1][0] # 4순위 (지울픽)

    avoid_s, avoid_l, avoid_o = ITEM_MAP[avoid_combo]
    element_scores = [
        (avoid_s, s_scores.get(avoid_s, 0)),
        (avoid_l, l_scores.get(avoid_l, 0)),
        (avoid_o, o_scores.get(avoid_o, 0))
    ]
    single_hole = sorted(element_scores, key=lambda x: x[1])[0][0]

    return avoid_combo, '4순위선별', single_hole

# 🎯 [통합 메인 연산]
def analyze_double_avoid_system(records_tuple, prev_failures={'start': False, 'line': False, 'oe': False}, last_avoid_failed=False, last_e2_failed=False):
    valid = [r[2] for r in records_tuple if r[2] in ALL_COMBOS]
    if len(valid) < 3:
        return {
            'rec1': '우삼', 'avoid1': '좌사', 'hole1': '좌',
            'avoid2': '우삼', 'hole2': '삼', 'e2_mode': '기본',
            'pattern_str': '-', 'bet_guide': '⛔ 패스 추천 (데이터 부족)'
        }

    rec1, avoid1, hole1 = get_engine1_picks(records_tuple, prev_failures)
    avoid2, e2_mode, hole2 = get_engine2_avoid_pattern(records_tuple, last_e2_failed)

    pattern_display = " ➔ ".join(valid[-4:])

    if last_avoid_failed:
        bet_guide = "⛔ 패스 권장 (직전 지울픽 실패 - 변칙 구간 방어)"
    elif avoid1 == avoid2:
        bet_guide = f"🔥 [더블 지울픽 일치] 지울픽: `{avoid1}` ({ITEM_FULL_MAP[avoid1]}) ➔ 3마킹 강한 배팅 (GO)"
    else:
        bet_guide = f"⛔ [지울픽 불일치] 엔진1:`{avoid1}` vs 엔진2:`{avoid2}` ➔ 패스 권장 (PASS)"

    return {
        'rec1': rec1,
        'avoid1': avoid1,
        'hole1': hole1,
        'avoid2': avoid2,
        'hole2': hole2,
        'e2_mode': e2_mode,
        'pattern_str': pattern_display,
        'bet_guide': bet_guide
    }

def calculate_stats(records_tuple, history_store, target_date=None):
    n = len(records_tuple)
    if n < 4: return None, {}

    tot = 0
    avoid1_win, avoid2_win = 0, 0
    double_match_tot, double_match_win = 0, 0
    
    e1_win_streak, max_e1_win_streak = 0, 0
    e1_lose_streak, max_e1_lose_streak = 0, 0
    e2_win_streak, max_e2_win_streak = 0, 0
    e2_lose_streak, max_e2_lose_streak = 0, 0

    prev_failures = {'start': False, 'line': False, 'oe': False}
    last_avoid_failed = False
    last_e2_failed = False
    history_picks = {}

    for i in range(3, n):
        act = records_tuple[i][2]
        rd_key = f"{records_tuple[i][0]}_{records_tuple[i][1]}"
        past_sub = records_tuple[:i]

        if rd_key in history_store:
            res = history_store[rd_key]
        else:
            res = analyze_double_avoid_system(past_sub, prev_failures, last_avoid_failed, last_e2_failed)

        history_picks[i] = res
        if act not in ALL_COMBOS: continue

        act_s, act_l, act_o = ITEM_MAP[act]

        if not target_date or records_tuple[i][0] == target_date:
            tot += 1
            
            if res['avoid1'] != act:
                avoid1_win += 1
                e1_win_streak += 1
                e1_lose_streak = 0
                if e1_win_streak > max_e1_win_streak: max_e1_win_streak = e1_win_streak
            else:
                e1_lose_streak += 1
                e1_win_streak = 0
                if e1_lose_streak > max_e1_lose_streak: max_e1_lose_streak = e1_lose_streak

            if res['avoid2'] != act:
                avoid2_win += 1
                e2_win_streak += 1
                e2_lose_streak = 0
                if e2_win_streak > max_e2_win_streak: max_e2_win_streak = e2_win_streak
            else:
                e2_lose_streak += 1
                e2_win_streak = 0
                if e2_lose_streak > max_e2_lose_streak: max_e2_lose_streak = e2_lose_streak

            if res['avoid1'] == res['avoid2']:
                double_match_tot += 1
                if res['avoid1'] != act: double_match_win += 1

        rec_s, rec_l, rec_o = ITEM_MAP[res['rec1']]
        prev_failures['start'] = (rec_s != act_s)
        prev_failures['line'] = (rec_l != act_l)
        prev_failures['oe'] = (rec_o != act_o)
        
        last_avoid_failed = (res['avoid1'] == act)
        last_e2_failed = (res['avoid2'] == act)

    stats = {
        'tot': tot,
        'avoid1_win': avoid1_win, 'avoid1_lose': tot - avoid1_win, 'avoid1_rate': (avoid1_win/tot*100.0) if tot > 0 else 0.0,
        'avoid2_win': avoid2_win, 'avoid2_lose': tot - avoid2_win, 'avoid2_rate': (avoid2_win/tot*100.0) if tot > 0 else 0.0,
        'double_tot': double_match_tot, 'double_win': double_match_win, 'double_lose': double_match_tot - double_match_win,
        'double_rate': (double_match_win/double_match_tot*100.0) if double_match_tot > 0 else 0.0,
        'max_e1_win_streak': max_e1_win_streak, 'max_e1_lose_streak': max_e1_lose_streak,
        'max_e2_win_streak': max_e2_win_streak, 'max_e2_lose_streak': max_e2_lose_streak,
        'prev_failures': prev_failures,
        'last_avoid_failed': last_avoid_failed,
        'last_e2_failed': last_e2_failed
    }
    return stats, history_picks

if "records" not in st.session_state:
    st.session_state.records = load_data()

if "history_store" not in st.session_state:
    st.session_state.history_store = {}

if "history_stack" not in st.session_state: st.session_state.history_stack = []
if "show_bulk" not in st.session_state: st.session_state.show_bulk = False

if "manual_target_round" not in st.session_state:
    st.session_state.manual_target_round = None

def push_backup():
    st.session_state.history_stack.append(copy.deepcopy(st.session_state.records))
    if len(st.session_state.history_stack) > 10: st.session_state.history_stack.pop(0)

records = st.session_state.records
records_tuple = tuple((r['date'], r['round'], r['result']) for r in records)

if st.session_state.show_bulk:
    st.markdown("**📋 과거 데이터 한 번에 복사/붙여넣기**")
    b_date = st.date_input("입력할 날짜 선택", datetime.now())
    b_start_rd = st.number_input("시작 회차 번호", min_value=1, max_value=288, value=1)
    raw_text = st.text_area("텍스트 붙여넣기", height=180, placeholder="예시:\n우사 우삼 좌사 좌삼 우사")
    col_b1, col_b2 = st.columns(2)
    if col_b1.button("📥 데이터 일괄 추가", use_container_width=True):
        found_items = re.findall(r'우사|우삼|좌사|좌삼', raw_text)
        if found_items:
            push_backup()
            curr_rd, curr_dt = int(b_start_rd), b_date
            for item in found_items:
                st.session_state.records.append({'date': curr_dt.strftime("%Y-%m-%d"), 'round': curr_rd, 'result': item})
                curr_rd += 1
                if curr_rd > 288:
                    curr_rd = 1
                    curr_dt = curr_dt + timedelta(days=1)
            st.session_state.records = st.session_state.records[-MAX_DATA_SIZE:]
            sync_all_records_db(st.session_state.records)
            st.toast(f"총 {len(found_items)}개 일괄 등록 완료!")
            st.session_state.show_bulk = False
            st.session_state.manual_target_round = None
            st.rerun()
