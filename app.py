import os
import re
import copy
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client

st.set_page_config(page_title="키노사다리 3중 지울픽 분석기", page_icon="⚡", layout="centered")

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
    if not supabase: 
        return []
    try:
        res = supabase.table("ladder_records").select("date, round, result, id").order("id", desc=True).limit(MAX_DATA_SIZE).execute()
        if res and res.data:
            sorted_records = sorted(res.data, key=lambda x: int(x['id']))
            return [
                {
                    'date': str(r['date']).strip(),
                    'round': int(r['round']),
                    'result': str(r['result']).strip()
                }
                for r in sorted_records
            ]
        return []
    except Exception: 
        return []

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

def analyze_pure_rule_axis(stream, val1, val2, prev_failed=False):
    n = len(stream)
    if n < 3: return val1, 70

    last, prev, prev2 = stream[-1], stream[-2], stream[-3]

    if prev_failed:
        if prev2 == prev and last != prev: pick, weight = last, 90
        elif n >= 4 and stream[-4] == prev2 and prev2 == prev and last != prev: pick, weight = OPPOSITE_SINGLE_MAP[last], 88
        else: pick, weight = last, 75
    else:
        if prev2 != prev and prev != last: pick, weight = prev, 85
        elif prev == last: pick, weight = last, 82
        else: pick, weight = last, 78

    return pick, weight

def score_pure_rule_axis(stream, val1, val2, prev_failed=False):
    pick, weight = analyze_pure_rule_axis(stream, val1, val2, prev_failed)
    other_val = OPPOSITE_SINGLE_MAP[pick]
    return {pick: weight, other_val: 100 - weight}

# 🎯 [엔진 1] 3축 점수합산 최저 확률 (4순위 지울픽)
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
    avoid_combo = sorted_combos[-1][0]  # 최저 4순위

    avoid_s, avoid_l, avoid_o = ITEM_MAP[avoid_combo]
    element_scores = [
        (avoid_s, s_scores.get(avoid_s, 50)),
        (avoid_l, l_scores.get(avoid_l, 50)),
        (avoid_o, o_scores.get(avoid_o, 50))
    ]
    single_hole = sorted(element_scores, key=lambda x: x[1])[0][0]

    return rec_combo, avoid_combo, single_hole

# 🎯 [엔진 2] 엔진1과 동일한 분석법 기반 최고 확률 (1순위 추천픽)
def get_engine2_picks(records_tuple, prev_failures):
    valid = [r[2] for r in records_tuple if r[2] in ALL_COMBOS]
    if len(valid) < 3: return '우삼', '우'

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
    top_combo = sorted_combos[0][0] # 최고 확률 (1순위)

    top_s, top_l, top_o = ITEM_MAP[top_combo]
    element_scores = [
        (top_s, s_scores.get(top_s, 50)),
        (top_l, l_scores.get(top_l, 50)),
        (top_o, o_scores.get(top_o, 50))
    ]
    single_hole = sorted(element_scores, key=lambda x: x[1], reverse=True)[0][0]

    return top_combo, single_hole

# 🎯 [엔진 3] 최근 가장 오랫동안 나오지 않은(미출) 조합 지울픽
def get_engine3_avoid_pattern(records_tuple):
    valid = [r[2] for r in records_tuple if r[2] in ALL_COMBOS]
    if not valid: return '좌사', '좌'

    last_seen = {c: float('inf') for c in ALL_COMBOS}
    for i, c in enumerate(reversed(valid)):
        if last_seen[c] == float('inf'):
            last_seen[c] = i

    avoid_combo = max(last_seen.items(), key=lambda x: x[1])[0]
    single_hole = ITEM_MAP[avoid_combo][0]

    return avoid_combo, single_hole

# 🎯 [통합 분석]
def analyze_triple_avoid_system(records_tuple, prev_failures={'start': False, 'line': False, 'oe': False}, last_avoid_failed=False):
    valid = [r[2] for r in records_tuple if r[2] in ALL_COMBOS]
    if len(valid) < 3:
        return {
            'rec1': '우삼', 'avoid1': '좌사', 'hole1': '좌',
            'avoid2': '우삼', 'hole2': '우',
            'avoid3': '좌사', 'hole3': '좌',
            'pattern_str': '-', 'bet_guide': '⛔ 패스 추천 (데이터 부족)'
        }

    rec1, avoid1, hole1 = get_engine1_picks(records_tuple, prev_failures)
    avoid2, hole2 = get_engine2_picks(records_tuple, prev_failures)
    avoid3, hole3 = get_engine3_avoid_pattern(records_tuple)

    pattern_display = " ➔ ".join(valid[-4:]) if valid else "-"

    if last_avoid_failed:
        bet_guide = "⛔ 패스 권장 (직전 지울픽 실패 - 변칙 구간 방어)"
    elif avoid1 == avoid3:
        bet_guide = f"🔥 [지울픽 일치] 엔진1/3: `{avoid1}` ({ITEM_FULL_MAP[avoid1]}) ➔ 3마킹 배팅 (GO)"
    else:
        bet_guide = f"📊 [분석 대기] 엔진1:`{avoid1}` vs 엔진2(1순위):`{avoid2}` vs 엔진3:`{avoid3}`"

    return {
        'rec1': rec1,
        'avoid1': avoid1, 'hole1': hole1,
        'avoid2': avoid2, 'hole2': hole2,
        'avoid3': avoid3, 'hole3': hole3,
        'pattern_str': pattern_display,
        'bet_guide': bet_guide
    }

def calculate_stats(records_tuple, history_store, target_date=None):
    n = len(records_tuple)
    if n < 4: return None, {}

    tot = 0
    avoid1_win, avoid2_win, avoid3_win = 0, 0, 0
    e1_win_streak, max_e1_win_streak = 0, 0
    e1_lose_streak, max_e1_lose_streak = 0, 0
    e2_win_streak, max_e2_win_streak = 0, 0
    e2_lose_streak, max_e2_lose_streak = 0, 0
    e3_win_streak, max_e3_win_streak = 0, 0
    e3_lose_streak, max_e3_lose_streak = 0, 0

    prev_failures = {'start': False, 'line': False, 'oe': False}
    last_avoid_failed = False
    history_picks = {}

    for i in range(3, n):
        act = records_tuple[i][2]
        rd_key = f"{records_tuple[i][0]}_{records_tuple[i][1]}"
        past_sub = records_tuple[:i]

        if history_store and rd_key in history_store:
            res = history_store[rd_key]
        else:
            res = analyze_triple_avoid_system(past_sub, prev_failures, last_avoid_failed)

        history_picks[i] = res
        if act not in ALL_COMBOS: continue

        act_s, act_l, act_o = ITEM_MAP[act]

        if not target_date or records_tuple[i][0] == target_date:
            tot += 1
            
            # 엔진1: 지울픽이므로 나오지 않아야 승리
            if res['avoid1'] != act:
                avoid1_win += 1; e1_win_streak += 1; e1_lose_streak = 0
                if e1_win_streak > max_e1_win_streak: max_e1_win_streak = e1_win_streak
            else:
                e1_lose_streak += 1; e1_win_streak = 0
                if e1_lose_streak > max_e1_lose_streak: max_e1_lose_streak = e1_lose_streak

            # 엔진2: 1순위 추천픽이므로 실제로 나와야 적중(승리)
            if res['avoid2'] == act:
                avoid2_win += 1; e2_win_streak += 1; e2_lose_streak = 0
                if e2_win_streak > max_e2_win_streak: max_e2_win_streak = e2_win_streak
            else:
                e2_lose_streak += 1; e2_win_streak = 0
                if e2_lose_streak > max_e2_lose_streak: max_e2_lose_streak = e2_lose_streak

            # 엔진3: 지울픽이므로 나오지 않아야 승리
            if res['avoid3'] != act:
                avoid3_win += 1; e3_win_streak += 1; e3_lose_streak = 0
                if e3_win_streak > max_e3_win_streak: max_e3_win_streak = e3_win_streak
            else:
                e3_lose_streak += 1; e3_win_streak = 0
                if e3_lose_streak > max_e3_lose_streak: max_e3_lose_streak = e3_lose_streak

        rec_s, rec_l, rec_o = ITEM_MAP[res['rec1']]
        prev_failures['start'] = (rec_s != act_s)
        prev_failures['line'] = (rec_l != act_l)
        prev_failures['oe'] = (rec_o != act_o)
        last_avoid_failed = (res['avoid1'] == act)

    stats = {
        'tot': tot,
        'avoid1_win': avoid1_win, 'avoid1_lose': tot - avoid1_win, 'avoid1_rate': (avoid1_win/tot*100.0) if tot > 0 else 0.0,
        'avoid2_win': avoid2_win, 'avoid2_lose': tot - avoid2_win, 'avoid2_rate': (avoid2_win/tot*100.0) if tot > 0 else 0.0,
        'avoid3_win': avoid3_win, 'avoid3_lose': tot - avoid3_win, 'avoid3_rate': (avoid3_win/tot*100.0) if tot > 0 else 0.0,
        'max_e1_win_streak': max_e1_win_streak, 'max_e1_lose_streak': max_e1_lose_streak,
        'max_e2_win_
