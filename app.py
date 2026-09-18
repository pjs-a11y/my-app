import os
import re
import copy
import numpy as np
import pandas as pd
import streamlit as st
from datetime import datetime, timedelta
from supabase import create_client, Client

st.set_page_config(page_title="키노사다리 A/B 미출현 스와프 분석기", page_icon="⚡", layout="centered")

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
    .block-container { padding: 0.3rem 0.3rem 80px 0.3rem !important; }
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

MAX_DATA_SIZE = 2000
ALL_COMBOS = ['우삼', '우사', '좌삼', '좌사']

ITEM_FULL_MAP = {
    '우사': '우사짝',
    '우삼': '우삼홀',
    '좌사': '좌사홀',
    '좌삼': '좌삼짝'
}

OPPOSITE_MAP = {
    '우사': '좌삼',
    '우삼': '좌사',
    '좌사': '우삼',
    '좌삼': '우사'
}

WEEKDAYS = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']

def get_current_realtime_round():
    now = datetime.now()
    total_minutes = now.hour * 60 + now.minute
    current_round = (total_minutes // 5) + 1
    if current_round > 288:
        current_round = 288
    return now.strftime("%Y-%m-%d"), current_round

def load_data():
    if not supabase: return []
    try:
        all_records = []
        start = 0
        step = 1000
        while start < MAX_DATA_SIZE:
            res = supabase.table("ladder_records").select("date, round, result, id").order("id", desc=True).range(start, start + step - 1).execute()
            if res and res.data:
                all_records.extend(res.data)
                if len(res.data) < step: break
                start += step
            else: break
        if all_records:
            sorted_records = sorted(all_records, key=lambda x: int(x['id']))
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

# 🎯 가장 오래 미출현한 조합 탐색
def get_longest_unreleased_combo(valid_list):
    if not valid_list:
        return '좌사', 0
    
    last_indices = {}
    total_len = len(valid_list)
    
    for combo in ALL_COMBOS:
        if combo in valid_list:
            rev_idx = valid_list[::-1].index(combo)
            last_indices[combo] = rev_idx
        else:
            last_indices[combo] = total_len

    sorted_unreleased = sorted(last_indices.items(), key=lambda x: x[1], reverse=True)
    return sorted_unreleased[0][0], sorted_unreleased[0][1]

# 🎯 A/B 스와프 분석
def analyze_ab_cold_swap_pattern(records_tuple, current_mode='A'):
    valid = [r[2] for r in records_tuple if r[2] in ALL_COMBOS]
    if len(valid) < 3:
        return {
            'rec': '우삼', 'avoid': '좌사', 
            'mode': 'A', 'cold_combo': '좌사', 'gap': 0,
            'pattern_str': '-'
        }

    cold_combo, gap = get_longest_unreleased_combo(valid)
    last_item = valid[-1]

    if current_mode == 'A':
        # [A 모드]: 오래 안 나온 조합을 지움 (안나옴 전제)
        avoid_pick = cold_combo
        rec_pick = OPPOSITE_MAP.get(avoid_pick, '우삼')
        mode_info = f"상태 A (미출현 {cold_combo} 지움 유지)"
    else:
        # [B 모드]: 오래 안 나온 조합이 터졌다고 보고 추천 (나옴 전제)
        rec_pick = cold_combo
        avoid_pick = last_item if last_item != rec_pick else OPPOSITE_MAP.get(rec_pick, '좌사')
        mode_info = f"⚡ 상태 B (미출현 {cold_combo} 추천 전환)"

    pattern_display = " ➔ ".join(valid[-4:])

    return {
        'rec': rec_pick,
        'avoid': avoid_pick,
        'mode': current_mode,
        'cold_combo': cold_combo,
        'gap': gap,
        'info': mode_info,
        'pattern_str': pattern_display
    }

def calculate_stats_with_ab_swap(records_tuple, history_store, target_date=None):
    n = len(records_tuple)
    if n < 4: return None, {}

    tot = 0
    rec_win, avoid_win = 0, 0
    avoid_win_streak, max_avoid_win_streak = 0, 0
    avoid_lose_streak, max_avoid_lose_streak = 0, 0

    mode = 'A'
    history_picks = {}

    for i in range(3, n):
        act = records_tuple[i][2]
        rd_key = f"{records_tuple[i][0]}_{records_tuple[i][1]}"
        past_sub = records_tuple[:i]

        if rd_key in history_store:
            res = history_store[rd_key]
        else:
            res = analyze_ab_cold_swap_pattern(past_sub, current_mode=mode)

        history_picks[i] = res
        if act not in ALL_COMBOS: continue

        if not target_date or records_tuple[i][0] == target_date:
            tot += 1
            if res['rec'] == act: rec_win += 1
            if res['avoid'] != act:
                avoid_win += 1
                avoid_win_streak += 1
                avoid_lose_streak = 0
                if avoid_win_streak > max_avoid_win_streak: max_avoid_win_streak = avoid_win_streak
            else:
                avoid_lose_streak += 1
                avoid_win_streak = 0
                if avoid_lose_streak > max_avoid_lose_streak: max_avoid_lose_streak = avoid_lose_streak

        # 📌 지울픽 실패 시 상태 스와프 (A -> B -> A)
        avoid_success = (res['avoid'] != act)
        if not avoid_success:
            mode = 'B' if mode == 'A' else 'A'

    stats = {
        'tot': tot,
        'rec_win': rec_win, 'rec_lose': tot - rec_win, 'rec_rate': (rec_win/tot*100.0) if tot > 0 else 0.0,
        'avoid_win': avoid_win, 'avoid_lose': tot - avoid_win, 'avoid_rate': (avoid_win/tot*100.0) if tot > 0 else 0.0,
        'max_avoid_win_streak': max_avoid_win_streak,
        'max_avoid_lose_streak': max_avoid_lose_streak,
        'next_mode': mode
    }
    return stats, history_picks

if "records" not in st.session_state:
    st.session_state.records = load_data()

if "history_store" not in st.session_state:
    st.session_state.history_store = {}

if "history_stack" not in st.session_state: st.session_state.history_stack = []
if "show_bulk" not in st.session_state: st.session_state.show_bulk = False

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
            st.cache_data.clear()
            st.toast(f"총 {len(found_items)}개 일괄 등록 완료!")
            st.session_state.show_bulk = False
            st.rerun()
    if col_b2.button("❌ 취소", use_container_width=True):
        st.session_state.show_bulk = False
        st.rerun()

elif not records:
    st.markdown("**⚙️ 최초 환경 설정**")
    init_date = st.date_input("날짜 선택", datetime.now())
    init_round = st.number_input("시작 회차 번호", min_value=1, max_value=288, value=1)
    sel = st.segmented_control(label="첫 결과 선택", options=ALL_COMBOS, selection_mode="single", label_visibility="collapsed", key="init_seg_ctrl")
    if sel:
        push_backup()
        dt_s, rd_n = init_date.strftime("%Y-%m-%d"), int(init_round)
        st.session_state.records.append({'date': dt_s, 'round': rd_n, 'result': sel})
        add_single_record_db(dt_s, rd_n, sel)
        st.cache_data.clear()
        st.rerun()

else:
    real_date_str, real_round_num = get_current_realtime_round()
    last_rec = records[-1]
    
    col_info, col_sync = st.columns([2, 1])
    with col_info:
        st.markdown(f"**현재 실제 시각: {real_date_str} / {real_round_num}회차 진행 중**")
        st.markdown(f"**DB 마지막 입력: {last_rec['date']} / {last_rec['round']}회차**")
    
    with col_sync:
        if st.button("⏰ 현재 회차로 점프", use_container_width=True):
            push_backup()
            st.session_state.records.append({'date': real_date_str, 'round': real_round_num - 1, 'result': "PASS"})
            st.session_state.records = st.session_state.records[-MAX_DATA_SIZE:]
            sync_all_records_db(st.session_state.records)
            st.cache_data.clear()
            st.rerun()

    if last_rec['round'] >= 288:
        next_round = 1
        curr_date = (datetime.strptime(last_rec['date'], "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        next_round = last_rec['round'] + 1
        curr_date = last_rec['date']

    if st.button("📋 텍스트 대량 추가", use_container_width=True):
        st.session_state.show_bulk = True
        st.rerun()

    st.markdown("---")

    recent_stat, history_picks = calculate_stats_with_ab_swap(records_tuple, st.session_state.history_store)
    recent_cnt = len(records)
    st.markdown(f"**누적 A/B 스와프 통계 (최근 {recent_cnt}개 기준)**")
    if recent_stat:
        st.markdown(f"🔥 **추천픽 적중률 : {recent_stat['rec_win']}승 {recent_stat['rec_lose']}패 (승률 {recent_stat['rec_rate']:.1f}%)**")
        st.markdown(f"⛔ **지울픽 성공률 : {recent_stat['avoid_win']}승 {recent_stat['avoid_lose']}패 (성공률 {recent_stat['avoid_rate']:.1f}%)**")

    st.markdown("---")

    try: dt_obj = datetime.strptime(curr_date, "%Y-%m-%d"); w_str = WEEKDAYS[dt_obj.weekday()]
    except Exception: w_str = ""
    today_stat, _ = calculate_stats_with_ab_swap(records_tuple, st.session_state.history_store, target_date=curr_date)
    st.markdown(f"**오늘 누적 A/B 스와프 통계 ({curr_date} {w_str})**")
    if today_stat:
        st.markdown(f"🔥 **추천픽 적중률 : {today_stat['rec_win']}승 {today_stat['rec_lose']}패 (승률 {today_stat['rec_rate']:.1f}%)**")
        st.markdown(f"⛔ **지울픽 성공률 : {today_stat['avoid_win']}승 {today_stat['avoid_lose']}패 (성공률 {today_stat['avoid_rate']:.1f}%)**")
        st.markdown(f"   🛡️ **지울픽 성적 : 최다 {today_stat['max_avoid_win_streak']}연속 성공 / 최다 {today_stat['max_avoid_lose_streak']}연속 나와버림**")

    st.markdown("---")

    if len(records_tuple) >= 4 and history_picks:
        last_idx = len(records_tuple) - 1
        prev_res = history_picks.get(last_idx)
        prev_actual = last_rec['result']
        st.markdown(f"**직전회차 결과 ( {last_rec['round']}회차 )**")
        if prev_actual == "PASS":
            st.markdown("결과 : **패스(PASS)**")
        else:
            act_full = ITEM_FULL_MAP.get(prev_actual, prev_actual)
            rec_ok = "추천적중 🎯" if prev_res and prev_res['rec'] == prev_actual else "추천미적중 ❌"
            avoid_ok = "안나옴 성공 🎯" if prev_res and prev_res['avoid'] != prev_actual else "나와버림 ❌"
            st.markdown(f"실제 결과 : **{prev_actual} ({act_full})**")
            if prev_res:
                st.markdown(f"🔥 **추천픽 ({prev_res['rec']}) ➔ {rec_ok}** / ⛔ **지울픽 ({prev_res['avoid']}) ➔ {avoid_ok}**")

    st.markdown("---")

    curr_mode = recent_stat['next_mode'] if recent_stat else 'A'
    curr_res = analyze_ab_cold_swap_pattern(records_tuple, current_mode=curr_mode)

    if curr_res:
        next_rd_key = f"{curr_date}_{next_round}"
        st.session_state.history_store[next_rd_key] = curr_res

    st.markdown(f"**이번회차 A/B 스와프 분석 ( {next_round}회차 )**")
    st.markdown(f"📊 **최근 진행 흐름**: `{curr_res['pattern_str']}`")
    st.markdown(f"❄️ **가장 오래 안 나온 조합**: `{curr_res['cold_combo']}` ({curr_res['gap']}회차 미출현)")
    st.markdown(f"🏷️ **현재 분석 상태**: `{curr_res['info']}`")
    st.markdown(f"🔥 **[추천픽] 추천: `{curr_res['rec']}` ({ITEM_FULL_MAP[curr_res['rec']]})**")
    st.markdown(f"⛔ **[지울픽] 제외: `{curr_res['avoid']}` ({ITEM_FULL_MAP[curr_res['avoid']]})**")

    st.markdown("---")
    st.markdown("**결과 입력**")

    input_val = st.segmented_control(
        label="결과 선택",
        options=ALL_COMBOS,
        selection_mode="single",
        label_visibility="collapsed",
        key=f"seg_ctrl_{len(records)}_{records[-1]['round'] if records else 0}"
    )

    if input_val:
        push_backup()
        st.session_state.records.append({'date': curr_date, 'round': next_round, 'result': input_val})
        if len(st.session_state.records) > MAX_DATA_SIZE:
            st.session_state.records = st.session_state.records[-MAX_DATA_SIZE:]
            sync_all_records_db(st.session_state.records)
        else: add_single_record_db(curr_date, next_round, input_val)
        st.cache_data.clear()
        st.rerun()

    st.markdown("---")

    st.markdown('<div class="ctrl-container">', unsafe_allow_html=True)
    if st.button("패스", use_container_width=True, key="btn_pass"):
        push_backup()
        st.session_state.records.append({'date': curr_date, 'round': next_round, 'result': "PASS"})
        if len(st.session_state.records) > MAX_DATA_SIZE:
            st.session_state.records = st.session_state.records[-MAX_DATA_SIZE:]
            sync_all_records_db(st.session_state.records)
        else: add_single_record_db(curr_date, next_round, "PASS")
        st.toast(f"{next_round}회차 패스")
        st.cache_data.clear()
        st.rerun()

    if st.button("직전취소", use_container_width=True, key="btn_cancel"):
        if st.session_state.records:
            push_backup()
            st.session_state.records.pop()
            delete_last_record_db()
            st.cache_data.clear()
            st.rerun()

    if st.button("초기화", use_container_width=True, key="btn_reset"):
        push_backup()
        st.session_state.records = []
        st.session_state.history_stack = []
        st.session_state.history_store = {}
        sync_all_records_db([])
        st.cache_data.clear()
        st.rerun()

    if st.button("되돌리기", use_container_width=True, key="btn_undo"):
        if st.session_state.history_stack:
            st.session_state.records = st.session_state.history_stack.pop()
            sync_all_records_db(st.session_state.records)
            st.cache_data.clear()
            st.rerun()

    export_lines = [f"{r['date']}|{r['round']}|{r['result']}" for r in records]
    export_bytes = "\n".join(export_lines).encode("utf-8-sig")
    st.download_button(label="📥 현재 누적 데이터 TXT 다운로드 (백업)", data=export_bytes, file_name=f"ladder_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt", mime="text/plain", use_container_width=True, key="btn_download")
    st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("---")

    st.markdown("**오늘 세부 결과 (A/B 스와프 리스트)**")
    if len(records_tuple) >= 4 and history_picks:
        rows = []
        today_indices = [idx for idx, r in enumerate(records_tuple) if r[0] == curr_date]
        for i in reversed(today_indices):
            if i < 3: continue
            res_prev = history_picks.get(i)
            act_item, rd_num = records_tuple[i][2], records_tuple[i][1]
            if act_item == "PASS": continue
            act_full = ITEM_FULL_MAP.get(act_item, act_item)

            rec_match = "적중 🎯" if res_prev and res_prev['rec'] == act_item else "미적중 ❌"
            avoid_match = "성공 🎯" if res_prev and res_prev['avoid'] != act_item else "나와버림 ❌"

            rows.append({
                "회차": f"{rd_num}회", "실제 결과": f"{act_item} ({act_full})",
                "적용 모드": f"모드 {res_prev['mode']}" if res_prev else "-",
                "추천픽 / 결과": f"{res_prev['rec'] if res_prev else '-'} / {rec_match}",
                "지울픽 / 결과": f"{res_prev['avoid'] if res_prev else '-'} / {avoid_match}"
            })
        if rows: st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        else: st.markdown("오늘 유효한 회차가 없습니다.")
