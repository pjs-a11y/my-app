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

    div[data-testid="stSegmentedControl"] { width: 100% !important; }
    div[data-testid="stSegmentedControl"] > div {
        display: flex !important; flex-direction: row !important;
        width: 100% !important; gap: 2px !important;
    }
    div[data-testid="stSegmentedControl"] button {
        flex: 1 1 25% !important; width: 25% !important;
        max-width: 25% !important; min-width: 0px !important;
        padding: 0.3rem 0rem !important; font-size: 0.85rem !important;
        font-weight: bold !important; height: 38px !important;
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

# 🛠️ 세션 안전 최우선 초기화
if "records" not in st.session_state:
    st.session_state.records = []
if "history_store" not in st.session_state:
    st.session_state.history_store = {}
if "history_stack" not in st.session_state:
    st.session_state.history_stack = []
if "show_bulk" not in st.session_state:
    st.session_state.show_bulk = False
if "manual_target_round" not in st.session_state:
    st.session_state.manual_target_round = None

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

def push_backup():
    st.session_state.history_stack.append(copy.deepcopy(st.session_state.records))
    if len(st.session_state.history_stack) > 10: st.session_state.history_stack.pop(0)

# 🎯 축별 점수 산출
def score_pure_rule_axis(stream, val1, val2, prev_failed=False):
    n = len(stream)
    if n < 3: return {val1: 50, val2: 50}

    last, prev, prev2 = stream[-1], stream[-2], stream[-3]

    if prev_failed:
        if prev2 == prev and last != prev: pick, weight = last, 90
        elif n >= 4 and stream[-4] == prev2 and prev2 == prev and last != prev: pick, weight = OPPOSITE_SINGLE_MAP[last], 88
        else: pick, weight = last, 75
    else:
        if prev2 != prev and prev != last: pick, weight = prev, 85
        elif prev == last: pick, weight = last, 82
        else: pick, weight = last, 78

    other_val = OPPOSITE_SINGLE_MAP[pick]
    return {pick: weight, other_val: 100 - weight}

# 🎯 [엔진 1] 점수합산 4순위 선별
def get_engine1_picks(records_tuple, prev_failures):
    valid = [r[2] for r in records_tuple if r[2] in ALL_COMBOS]
    if len(valid) < 3: return '우삼', '좌사', '좌'

    s_scores = score_pure_rule_axis([ITEM_MAP[r][0] for r in valid], '우', '좌', prev_failures['start'])
    l_scores = score_pure_rule_axis([ITEM_MAP[r][1] for r in valid], '삼', '사', prev_failures['line'])
    o_scores = score_pure_rule_axis([ITEM_MAP[r][2] for r in valid], '홀', '짝', prev_failures['oe'])

    combo_scores = {
        '우삼': s_scores.get('우', 50) + l_scores.get('삼', 50) + o_scores.get('홀', 50),
        '우사': s_scores.get('우', 50) + l_scores.get('사', 50) + o_scores.get('짝', 50),
        '좌삼': s_scores.get('좌', 50) + l_scores.get('삼', 50) + o_scores.get('짝', 50),
        '좌사': s_scores.get('좌', 50) + l_scores.get('사', 50) + o_scores.get('홀', 50)
    }

    sorted_combos = sorted(combo_scores.items(), key=lambda x: x[1], reverse=True)
    rec_combo = sorted_combos[0][0]
    avoid_combo = sorted_combos[-1][0]

    avoid_s, avoid_l, avoid_o = ITEM_MAP[avoid_combo]
    element_scores = [
        (avoid_s, s_scores.get(avoid_s, 50)),
        (avoid_l, l_scores.get(avoid_l, 50)),
        (avoid_o, o_scores.get(avoid_o, 50))
    ]
    single_hole = sorted(element_scores, key=lambda x: x[1])[0][0]

    return rec_combo, avoid_combo, single_hole

# 🎯 [엔진 2] 패턴 점수합산 4순위 지울픽 선별
def get_engine2_avoid_pattern(records_tuple, last_e2_failed=False):
    valid = [r[2] for r in records_tuple if r[2] in ALL_COMBOS]
    n = len(valid)
    if n < 4: return '좌사', '기본', '좌'

    # 특수 대칭 검출
    for span in [3, 2, 1]:
        if n >= (span * 2 + 1):
            center_idx = n - 1 - span
            is_decal = True
            for offset in range(1, span + 1):
                if valid[center_idx - offset] != valid[center_idx + offset]:
                    is_decal = False
                    break
            
            if is_decal:
                decal_target = valid[center_idx - span]
                avoid_decal = f"{OPPOSITE_SINGLE_MAP[decal_target[0]]}{OPPOSITE_SINGLE_MAP[decal_target[1]]}"
                return avoid_decal, f'특수({span*2+1}회차데칼)', OPPOSITE_SINGLE_MAP[decal_target[0]]

    s_stream = [ITEM_MAP[r][0] for r in valid]
    l_stream = [ITEM_MAP[r][1] for r in valid]
    o_stream = [ITEM_MAP[r][2] for r in valid]

    s_scores = {s_stream[-1]: 70, OPPOSITE_SINGLE_MAP[s_stream[-1]]: 30} if s_stream[-1] == s_stream[-2] else {OPPOSITE_SINGLE_MAP[s_stream[-1]]: 70, s_stream[-1]: 30}
    l_scores = {OPPOSITE_SINGLE_MAP[l_stream[-1]]: 70, l_stream[-1]: 30} if l_stream[-1] == l_stream[-2] else {l_stream[-1]: 70, OPPOSITE_SINGLE_MAP[l_stream[-1]]: 30}
    o_scores = {o_stream[-1]: 60, OPPOSITE_SINGLE_MAP[o_stream[-1]]: 40}

    combo_scores = {
        '우삼': s_scores.get('우', 50) + l_scores.get('삼', 50) + o_scores.get('홀', 50),
        '우사': s_scores.get('우', 50) + l_scores.get('사', 50) + o_scores.get('짝', 50),
        '좌삼': s_scores.get('좌', 50) + l_scores.get('삼', 50) + o_scores.get('짝', 50),
        '좌사': s_scores.get('좌', 50) + l_scores.get('사', 50) + o_scores.get('홀', 50)
    }

    sorted_combos = sorted(combo_scores.items(), key=lambda x: x[1], reverse=True)
    avoid_combo = sorted_combos[-1][0]

    avoid_s, avoid_l, avoid_o = ITEM_MAP[avoid_combo]
    element_scores = [
        (avoid_s, s_scores.get(avoid_s, 50)),
        (avoid_l, l_scores.get(avoid_l, 50)),
        (avoid_o, o_scores.get(avoid_o, 50))
    ]
    single_hole = sorted(element_scores, key=lambda x: x[1])[0][0]

    return avoid_combo, '4순위패턴', single_hole

# 🎯 [통합 분석]
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

    pattern_display = " ➔ ".join(valid[-4:]) if valid else "-"

    if last_avoid_failed:
        bet_guide = "⛔ 패스 권장 (직전 지울픽 실패 - 변칙 구간 방어)"
    elif avoid1 == avoid2:
        bet_guide = f"🔥 [더블 지울픽 일치] 지울픽: `{avoid1}` ({ITEM_FULL_MAP[avoid1]}) ➔ 3마킹 강한 배팅 (GO)"
    else:
        bet_guide = f"⛔ [지울픽 불일치] 엔진1:`{avoid1}` vs 엔진2:`{avoid2
