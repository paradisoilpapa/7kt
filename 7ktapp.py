# ヴェロビ集計：2車複→2車単、◎・α・ε軸。3連複集計なし。
# -*- coding: utf-8 -*-
"""ヴェロビ集計｜通常◎・妙味α 集計版。

元の618行版を基準とした仕様:
- 通常 ◎○▲△× / 妙味 αβγεΩ の印着内率
- 2車単は各軸の1着固定4通りだけ（通常◎、妙味α）
- 通常◎→○▲△ / 妙味α→γβε の3点セット集計
- 旧通常評価の入力キー・引継ぎキーを維持
- 日次100レース、除外、集計CSV、日次・累積レース別確認
"""
from typing import Dict, List, Tuple
from itertools import combinations
import re
import pandas as pd
import streamlit as st

st.set_page_config(page_title="ヴェロビ集計｜◎・α比較", layout="wide")
st.title("ヴェロビ集計｜通常◎・妙味α 比較")
st.caption("通常評価と妙味軸評価を独立集計。◎→×・無印2車も比較。各買い目100円平買い換算。")

GROUP_MARKS = {
    "通常": ("◎", "○", "▲", "△", "×"),
    "妙味": ("α", "β", "γ", "ε", "Ω"),
}
SET_TARGETS = {"通常": ("○", "▲", "△"), "妙味": ("γ", "β", "ε")}
GROUP_AXES = {g: marks[0] for g, marks in GROUP_MARKS.items()}


def all_axis_pairs(marks: Tuple[str, ...]) -> List[Tuple[str, str]]:
    axis = marks[0]
    return [(axis, other) for other in marks[1:]]


BET_PAIRS = {g: all_axis_pairs(marks) for g, marks in GROUP_MARKS.items()}


def blank_bet():
    return {"N": 0, "H": 0, "SUM": 0, "KSUM": 0}


def blank_unmarked():
    return {"N": 0, "H": 0, "SUM": 0, "KSUM": 0}


def blank_mark():
    return {"N": 0, "C1": 0, "C2": 0, "C3": 0}


def blank_group_bets(g):
    return {pair: blank_bet() for pair in BET_PAIRS[g]}


def blank_group_marks(g):
    return {mark: blank_mark() for mark in GROUP_MARKS[g]}


def add_records(left, right, fields):
    return {f: int(left.get(f, 0)) + int(right.get(f, 0)) for f in fields}


def pct(num, den):
    return round(100 * num / den, 1) if den else None


def clean_digits(value: str) -> str:
    """元コードと同じく区切りを無視して車番数字を取得する。"""
    return "".join(c for c in str(value or "") if c.isdigit())


def parse_markline(value: str, group: str) -> Dict[str, str]:
    """4車または5車。通常は◎○▲△×、妙味はαβγεΩ。"""
    s = clean_digits(value)
    if len(s) not in (4, 5) or len(set(s)) != len(s) or "0" in s:
        return {}
    return dict(zip(GROUP_MARKS[group][:len(s)], list(s)))


def parse_finish(value: str) -> List[str]:
    """上位3着を取得。旧版同様、後続の余分な数字は無視する。"""
    s = clean_digits(value)
    result = []
    for c in s:
        if c == "0":
            continue
        if c not in result:
            result.append(c)
        if len(result) == 3:
            break
    return result


def mark_row(mark: str, rec: Dict[str, int]) -> Dict:
    n = int(rec["N"])
    c1, c2, c3 = (int(rec[f"C{i}"]) for i in (1, 2, 3))
    return {
        "印": mark,
        "対象N": n,
        "1着回数": c1,
        "2着回数": c2,
        "3着回数": c3,
        "1着率%": pct(c1, n),
        "連対率%": pct(c1 + c2, n),
        "印着内率%": pct(c1 + c2 + c3, n),
    }


def bet_row(name: str, rec: Dict[str, int]) -> Dict:
    n, h, summ = int(rec["N"]), int(rec["H"]), int(rec["SUM"])
    ksum = int(rec.get("KSUM", n))
    invest = ksum * 100
    return {
        "買い目": name,
        "対象R": n,
        "購入点数": ksum,
        "投資額": invest,
        "的中数": h,
        "的中率%": pct(h, n),
        "払戻合計": summ,
        "平均的中配当": round(summ / h, 1) if h else None,
        "回収率%": pct(summ, invest),
    }


def style_roi(df):
    def color_roi(value):
        try:
            v = float(value)
        except (TypeError, ValueError):
            return ""
        if v >= 100:
            return "background-color: #d9ead3; font-weight: 700;"
        if v >= 90:
            return "background-color: #fff2cc; font-weight: 600;"
        return ""
    if "回収率%" not in df.columns:
        return df
    formats = {col: "{:.1f}" for col in df.columns if "率%" in str(col) or col == "平均的中配当"}
    return df.style.format(formats, na_rep="—").map(color_roi, subset=["回収率%"])


def show_full_table(data, *, hide_index=True):
    rows = len(data.data) if isinstance(data, pd.io.formats.style.Styler) else len(data)
    st.dataframe(data, use_container_width=True, hide_index=hide_index,
                 height=max(110, 39 + rows * 36))


def pair_label(a, b):
    return f"2車単 {a}-{b}"


def carry_keys(group, a, b):
    """旧版の入力キーを可能な限り維持する。

    旧 CURRENT_2T_BETS に存在したものは carry_*、
    旧追加全20通りは pair_carry_* に保存されていた。
    """
    label = pair_label(a, b)
    legacy_direct = {
        "2車単 ◎-○", "2車単 ◎-▲", "2車単 ◎-△", "2車単 ◎-×",
        "2車単 ○-◎", "2車単 ○-▲", "2車単 △-◎", "2車単 △-○",
        "2車単 △-▲", "2車単 ▲-◎",
    }
    if group == "通常":
        prefix = "carry" if label in legacy_direct else "pair_carry"
        return tuple(f"{prefix}_{f}_{label}" for f in ("n", "h", "sum"))
    return tuple(f"alpha_carry_{f}_{a}_{b}" for f in ("n", "h", "sum"))


# ============================================================
# A. 日次入力（旧版と同じ100R、旧通常入力キーを保持）
# ============================================================
tab_daily, tab_carry, tab_result = st.tabs(
    ["日次入力", "前日までの集計（引継ぎ）", "集計結果"]
)

# 100Rの入力欄を50Rずつ描画する。ページ間の値はウィジェットとは別に保持。
import json

def _empty_race(i):
    return {"race": str(i), "normal": "", "alpha": "", "epsilon_final": "", "finish": "",
            "pay": 0, "quinella_pay": 0,
            "wide_entries": [["", 0] for _ in range(3)],
            "field_size": 7, "exclude": False, "girls": False, "session": "デイ"}

if "velovi_saved_daily_50" not in st.session_state:
    _prior = [_empty_race(i) for i in range(1, 101)]
    # 旧100R画面から同じStreamlitセッションで切替えた場合、旧キーを引き継ぐ。
    for _i in range(1, 101):
        _r = _prior[_i - 1]
        for _field, _prefix in (("race", "rid"), ("normal", "mark"), ("alpha", "alpha_mark"), ("finish", "fin"), ("pay", "pay2t"), ("quinella_pay", "pay2f"), ("field_size", "field_size"), ("exclude", "exclude")):
            _r[_field] = st.session_state.get(f"{_prefix}_{_i}", _r[_field])
        for _j in range(1, 4):
            _r["wide_entries"][_j-1] = [st.session_state.get(f"wide_pair{_j}_{_i}", ""), st.session_state.get(f"wide_pay{_j}_{_i}", 0)]
    st.session_state["velovi_saved_daily_50"] = _prior

with tab_daily:
    st.caption("100Rの枠はそのまま、50Rずつ表示します。切り替える前に『この50Rを反映』を押してください。")
    page = st.radio("入力範囲", [0, 1], format_func=lambda p: "1～50R" if p == 0 else "51～100R", horizontal=True, key="velovi_50_page")
    start, end = page * 50, (page + 1) * 50
    page_rows = []
    with st.form(f"daily_input_form_50_{page}"):
        for i in range(start + 1, end + 1):
            old = st.session_state["velovi_saved_daily_50"][i-1]
            st.markdown(f"**{i}R**")
            c1, c2, c3 = st.columns([1.0, 2.0, 2.0])
            rid = c1.text_input("R番号", value=str(old["race"]), key=f"p{page}_rid_{i}")
            normal = c2.text_input("通常印順 ◎○▲△×", value=str(old["normal"]), key=f"p{page}_mark_{i}")
            alpha = c3.text_input("妙味印順 αβγεΩ", value=str(old["alpha"]), key=f"p{page}_alpha_{i}")
            epsilon_final = st.text_input("最終総合評価 εABCD（任意・5車番）", value=str(old.get("epsilon_final", "")), key=f"p{page}_epsilon_final_{i}")
            c4, c5, c6, c7 = st.columns([1.6, 1.5, 1.0, 0.9])
            finish = c4.text_input("着順（3着まで）", value=str(old["finish"]), key=f"p{page}_fin_{i}")
            quinella_pay = c5.number_input("2車複払戻（100円）", min_value=0, value=int(old["quinella_pay"]), step=10, key=f"p{page}_pay2f_{i}")
            pay = c5.number_input("2車単払戻", min_value=0, value=int(old["pay"]), step=10, key=f"p{page}_pay2t_{i}")
            field_size = c6.selectbox("車数", [7, 6], index=0 if int(old["field_size"]) == 7 else 1, key=f"p{page}_field_size_{i}")
            # ミッドナイトだけチェック式にする。旧JSONの開催時間帯も読み取る。
            session_value = old.get("session", "デイ")
            midnight = c7.checkbox("ミッドナイト", value=(session_value == "ミッドナイト"), key=f"p{page}_midnight_{i}")
            session = "ミッドナイト" if midnight else (session_value if session_value in ("モーニング", "デイ", "ナイター") else "デイ")
            girls = c7.checkbox("ガールズ", value=bool(old.get("girls", False)), key=f"p{page}_girls_{i}")
            exclude = c7.checkbox("集計除外", value=bool(old["exclude"]), key=f"p{page}_exclude_{i}")
            page_rows.append({"race": rid, "normal": normal, "alpha": alpha, "epsilon_final": epsilon_final,
                "finish": finish, "pay": int(pay),
                "quinella_pay": int(quinella_pay), "wide_entries": old.get("wide_entries", [["", 0] for _ in range(3)]),
                "field_size": int(field_size), "exclude": bool(exclude), "girls": bool(girls), "session": session})
            st.divider()
        submitted_50 = st.form_submit_button("この50Rを反映")
    if submitted_50:
        st.session_state["velovi_saved_daily_50"][start:end] = page_rows
        st.success(f"{start+1}～{end}Rを反映しました。")
    daily_rows = st.session_state["velovi_saved_daily_50"]
    st.download_button("入力内容をバックアップ（JSON）", data=json.dumps({"daily_rows": daily_rows}, ensure_ascii=False).encode("utf-8"), file_name="velovi_input_backup.json", mime="application/json")
    upload = st.file_uploader("入力バックアップを復元（JSON）", type=["json"], key="velovi_restore_50")
    if st.button("バックアップを復元", disabled=upload is None):
        try:
            payload = json.loads(upload.getvalue().decode("utf-8"))
            rows = payload["daily_rows"]
            if not isinstance(rows, list) or len(rows) != 100:
                raise ValueError("100R分のデータではありません")
            st.session_state["velovi_saved_daily_50"] = [{**_empty_race(i), **r} for i, r in enumerate(rows, 1)]
            # 既存ウィジェットキーを破棄し、復元データから入力欄を再生成する。
            for key in list(st.session_state.keys()):
                if key.startswith(("p0_", "p1_")):
                    del st.session_state[key]
            st.rerun()
        except (ValueError, KeyError, TypeError, UnicodeError) as exc:
            st.error(f"復元できません: {exc}")


# ============================================================
# B. 引継ぎ（旧通常評価の入力キーを維持）
# ============================================================
carry_mark_records = {g: blank_group_marks(g) for g in GROUP_MARKS}
carry_bet_records = {g: blank_group_bets(g) for g in GROUP_MARKS}
carry_unmarked = {name: blank_unmarked() for name in ("◎→×", "◎→無印")}

daily_quinella_labels = ('◎－○', '◎－▲', '◎－△', '◎－×', '◎－無印合計', '◎－β', '◎－ε')
carry_quinella_all = {g:{} for g in GROUP_MARKS}
carry_quinella_named = {}
carry_epsilon_exacta = {m: blank_bet() for m in ("α", "β", "γ", "Ω")}
carry_epsilon_quinella = {m: blank_bet() for m in ("β", "γ", "Ω")}

# 保存・復元はセッション外でも使える明示的なJSONバックアップで行う。
# Streamlit Cloudではローカルファイルの永続性を保証できないため、
# サーバー内ファイルへの自動保存だけに依存しない。
CARRY_KEY_PREFIXES = (
    "carry_mark_", "alpha_carry_mark_", "carry_", "pair_carry_",
    "alpha_carry_", "unmarked_", "wide_carry_", "carry_qall_",
    "carry_qnamed_", "carry_wextra_", "unified_", "trio2_carry_", "epsilon_carry_", "scopedcarry_",
)


def export_complete_backup():
    carry = {}
    for key, value in st.session_state.items():
        if isinstance(key, str) and key.startswith(CARRY_KEY_PREFIXES) and isinstance(value, (int, float, str, bool)):
            carry[key] = int(value) if isinstance(value, (int, float)) else value
    return {
        "format": "velovi_complete_backup_v1",
        "daily_rows": st.session_state["velovi_saved_daily_50"],
        "carry_values": carry,
    }


def restore_complete_backup(payload):
    if not isinstance(payload, dict):
        raise ValueError("バックアップ形式が不正です")
    rows = payload.get("daily_rows")
    carry = payload.get("carry_values")
    if not isinstance(rows, list) or len(rows) != 100:
        raise ValueError("日次データが100R分ありません")
    if not isinstance(carry, dict):
        raise ValueError("引継ぎ値が含まれていません。日次のみの旧バックアップです")
    clean_carry = {}
    for key, value in carry.items():
        if not isinstance(key, str) or not key.startswith(CARRY_KEY_PREFIXES):
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0 or int(value) != value:
            raise ValueError(f"引継ぎ値が不正です: {key}")
        clean_carry[key] = int(value)
    new_rows = []
    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"日次{i}Rの形式が不正です")
        new_rows.append({**_empty_race(i), **row})
    st.session_state["velovi_saved_daily_50"] = new_rows
    # 復元ファイルにない過去値が混ざらないように初期化する。
    for key in list(st.session_state):
        if isinstance(key, str) and (key.startswith(CARRY_KEY_PREFIXES) or key.startswith(("p0_", "p1_"))):
            del st.session_state[key]
    st.session_state.update(clean_carry)


with tab_carry:
    st.subheader("前日までの集計（累積・引継ぎ）")
    st.warning("引継ぎ値はセッション内だけでは永続保存されません。入力後に下部の『日次＋引継ぎをまとめてバックアップ』を保存し、次回はここから復元してください。")
    restored_file = st.file_uploader("日次＋前日までの集計を復元（完全バックアップJSON）", type=["json"], key="velovi_complete_restore_file")
    if st.button("完全バックアップを復元", disabled=restored_file is None, key="velovi_complete_restore_button"):
        try:
            restore_complete_backup(json.loads(restored_file.getvalue().decode("utf-8")))
            st.rerun()
        except (ValueError, KeyError, TypeError, UnicodeError) as exc:
            st.error(f"完全バックアップを復元できません: {exc}")
    st.markdown("### 区分別の前日引継ぎ（新方式）")
    st.caption("男子通常・男子ミッドナイト・ガールズ通常・ガールズミッドナイトを別保存。日次入力と同じく2車複→2車単の順です。旧引継ぎとは重複入力しないでください。")
    scope_options = {"男子・通常開催":"boy_day", "男子・ミッドナイト":"boy_mid", "ガールズ・通常開催":"girl_day", "ガールズ・ミッドナイト":"girl_mid"}
    _scope_tabs = st.tabs(list(scope_options))
    for _scope_tab, (scope_name, scope_id) in zip(_scope_tabs, scope_options.items()):
        with _scope_tab:
            with st.form("scoped_carry_form_" + scope_id):
                for group, marks in GROUP_MARKS.items():
                    st.markdown(f"**{group}評価・印着内率**")
                    cols = st.columns([1.1, 1, 1, 1, 1])
                    for col, name in zip(cols, ("印", "対象R", "1着", "2着", "3着")):
                        col.markdown(f"**{name}**")
                    for mark in marks:
                        cols = st.columns([1.1, 1, 1, 1, 1])
                        cols[0].write(mark)
                        for col, field in zip(cols[1:], ("n", "c1", "c2", "c3")):
                            col.number_input(field, min_value=0, step=1, label_visibility="collapsed", key=f"scopedcarry_{scope_id}_mark_{group}_{mark}_{field}")
                for ticket_type in ("2車複", "2車単"):
                    for axis, targets in (("◎", ("○", "▲", "△", "×", "無印", "β", "ε")),
                                          ("α", ("β", "γ", "ε", "Ω")),
                                          ("ε", ("β", "γ", "Ω")) if ticket_type == "2車複" else ("ε", ("α", "β", "γ", "Ω"))):
                        st.markdown(f"**{ticket_type}｜{axis}軸**")
                        c = st.columns([2, 1, 1, 1, 1])
                        for col, title in zip(c, ("買い目", "対象R", "購入点数", "的中数", "払戻合計")):
                            col.markdown(f"**{title}**")
                        for target in targets:
                            label = f"{axis}{'－' if ticket_type == '2車複' else '→'}{target}"
                            code = f"{ticket_type}_{axis}_{target}"
                            c = st.columns([2, 1, 1, 1, 1])
                            c[0].write(label)
                            c[1].number_input("対象R", min_value=0, step=1, label_visibility="collapsed", key=f"scopedcarry_{scope_id}_{code}_n")
                            if target == "無印":
                                c[2].number_input("購入点数", min_value=0, step=1, label_visibility="collapsed", key=f"scopedcarry_{scope_id}_{code}_points")
                            else:
                                c[2].caption("対象Rと同数")
                            c[3].number_input("的中数", min_value=0, step=1, label_visibility="collapsed", key=f"scopedcarry_{scope_id}_{code}_h")
                            c[4].number_input("払戻合計", min_value=0, step=10, label_visibility="collapsed", key=f"scopedcarry_{scope_id}_{code}_sum")
                st.form_submit_button("この区分の引継ぎを反映")
    st.divider()
    with st.expander("従来の区分なし引継ぎ（既存データ互換）"):
        st.caption(
            "通常評価は印別1～3着回数と、◎1着固定の2車単4通りを転記。"
            "妙味評価はα軸の成績を新規入力。旧版の他の2車単は転記不要です。"
            "引継ぎ対象Nは各印・買い目ごとに入力できます。"
        )
        st.caption("前日までの対象R・的中数・払戻合計を入力します。1R1点の買い目は購入点数を自動計算します。")
        with st.form("carryover_form"):
            for group, marks in GROUP_MARKS.items():
                st.markdown(f"### {group}評価｜印別 入賞回数（引継ぎ）")
                h = st.columns([1.2, 1.0, 1.0, 1.0, 1.0])
                for col, title in zip(h, ["印", "対象N", "1着", "2着", "3着"]):
                    col.markdown(f"**{title}**")
                for mark in marks:
                    c0, c1, c2, c3, c4 = st.columns([1.2, 1.0, 1.0, 1.0, 1.0])
                    c0.markdown(f"**{mark}**")
                    prefix = "carry_mark" if group == "通常" else "alpha_carry_mark"
                    n = c1.number_input("対象N", min_value=0, value=0, step=1,
                                        key=f"{prefix}_n_{mark}", label_visibility="collapsed")
                    x1 = c2.number_input("1着", min_value=0, value=0, step=1,
                                         key=f"{prefix}_c1_{mark}", label_visibility="collapsed")
                    x2 = c3.number_input("2着", min_value=0, value=0, step=1,
                                         key=f"{prefix}_c2_{mark}", label_visibility="collapsed")
                    x3 = c4.number_input("3着", min_value=0, value=0, step=1,
                                         key=f"{prefix}_c3_{mark}", label_visibility="collapsed")
                    carry_mark_records[group][mark] = {"N": int(n), "C1": int(x1),
                                                        "C2": int(x2), "C3": int(x3)}
                    if x1 + x2 + x3 > n:
                        st.warning(f"{group}{mark}: 1～3着回数合計が対象Nを超えています。")

            # 旧入力キーからの復元は下の統一欄に一度だけ取り込む。
            def old_value(key):
                return int(st.session_state.get(key, 0) or 0)

            def old_record(prefix):
                return {"N": old_value(prefix + "_n"), "H": old_value(prefix + "_h"),
                        "SUM": old_value(prefix + "_sum"), "KSUM": old_value(prefix + "_points")}

            def merged_legacy_unmarked(prefixes):
                rows = [old_record(prefix) for prefix in prefixes]
                return {"N": max((r["N"] for r in rows), default=0),
                        "H": sum(r["H"] for r in rows), "SUM": sum(r["SUM"] for r in rows),
                        "KSUM": sum(r["KSUM"] or r["N"] for r in rows)}

            def carry_entry(label, key, legacy=None, points=None, multi=False):
                legacy = legacy or blank_bet()
                n_default = legacy["N"]
                k_default = legacy["KSUM"] or (n_default * points if points else n_default)
                if multi:
                    c = st.columns([2.3, 1, 1, 1, 1.3])
                    c[0].markdown(f"**{label}**")
                    n = c[1].number_input("対象R", min_value=0, value=n_default, key=key+"_n", label_visibility="collapsed")
                    k = c[2].number_input("購入点数", min_value=0, value=k_default, key=key+"_points", label_visibility="collapsed")
                    h = c[3].number_input("的中数", min_value=0, value=legacy["H"], key=key+"_h", label_visibility="collapsed")
                    v = c[4].number_input("払戻合計", min_value=0, value=legacy["SUM"], step=10, key=key+"_sum", label_visibility="collapsed")
                else:
                    c = st.columns([2.3, 1, 1, 1.3])
                    c[0].markdown(f"**{label}**")
                    n = c[1].number_input("対象R", min_value=0, value=n_default, key=key+"_n", label_visibility="collapsed")
                    k = int(n)
                    h = c[2].number_input("的中数", min_value=0, value=legacy["H"], key=key+"_h", label_visibility="collapsed")
                    v = c[3].number_input("払戻合計", min_value=0, value=legacy["SUM"], step=10, key=key+"_sum", label_visibility="collapsed")
                return {"N":int(n), "KSUM":int(k), "H":int(h), "SUM":int(v)}

            def header(multi=False):
                labels = ("買い目", "対象R", "購入点数", "的中数", "払戻合計") if multi else ("買い目", "対象R", "的中数", "払戻合計")
                c = st.columns([2.3, 1, 1, 1, 1.3] if multi else [2.3, 1, 1, 1.3])
                for col, name in zip(c, labels):
                    col.markdown(f"**{name}**")

            st.markdown("### 2車複｜通常評価（◎軸）")
            header()
            for other in ("○", "▲", "△", "×", "無印", "β", "ε"):
                label = "◎－" + other
                named = old_record("carry_qnamed_" + ("◎－無印合計" if other == "無印" else label))
                if not any(named.values()):
                    if other == "無印":
                        prefixes = [f"carry_qall_n_◎_無印{i}" for i in (1,2)]
                        named = merged_legacy_unmarked(prefixes)
                    elif other in ("○", "▲", "△", "×"):
                        named = old_record(f"carry_qall_n_◎_{other}")
                carry_quinella_named["◎－無印合計" if other == "無印" else label] = carry_entry(
                    label, "unified_2f_normal_"+other, named, multi=(other == "無印"))

            st.markdown("### 2車複｜妙味評価（α軸）")
            header()
            for other in ("β", "γ", "ε", "Ω", "無印"):
                if other == "無印":
                    legacy = merged_legacy_unmarked([f"carry_qall_v_α_無印{i}" for i in (1,2)])
                else:
                    legacy = old_record(f"carry_qall_v_α_{other}")
                carry_quinella_all["妙味"][("α",other)] = carry_entry(
                    f"α－{other}", "unified_2f_value_"+other, legacy, multi=(other == "無印"))
            st.markdown("### 2車複｜妙味評価（ε軸・過去分引継ぎ）")
            st.caption("ε－αは上のα－εと同一車券のため、そちらの引継ぎ値を共有します。")
            header()
            for other in ("β", "γ", "Ω"):
                carry_epsilon_quinella[other] = carry_entry(
                    f"ε－{other}", f"epsilon_carry_2f_{other}")

            for group, marks in GROUP_MARKS.items():
                axis = marks[0]
                st.markdown(f"### {group}評価｜2車単（{axis}1着固定）")
                header()
                for other in marks[1:]:
                    oldkeys = carry_keys(group, axis, other)
                    legacy = {"N":old_value(oldkeys[0]), "H":old_value(oldkeys[1]),
                              "SUM":old_value(oldkeys[2]), "KSUM":old_value(oldkeys[0])}
                    carry_bet_records[group][(axis, other)] = carry_entry(
                        f"{axis}→{other}", f"unified_2t_{group}_{other}", legacy)
                # 妙味α→無印も同じ表示形式で引継ぎ可能
                if group == "通常":
                    st.caption("◎→無印のみ複数点集計のため購入点数を入力します。")
                    legacy = merged_legacy_unmarked(["unmarked_"+field for field in ()]) if False else {
                        "N":max(old_value("unmarked_n_◎→無印1"), old_value("unmarked_n_◎→無印2")),
                        "H":old_value("unmarked_h_◎→無印1")+old_value("unmarked_h_◎→無印2"),
                        "SUM":old_value("unmarked_sum_◎→無印1")+old_value("unmarked_sum_◎→無印2"),
                        "KSUM":old_value("unmarked_n_◎→無印1")+old_value("unmarked_n_◎→無印2")}
                    carry_unmarked["◎→無印"] = carry_entry("◎→無印", "unified_2t_normal_unmarked", legacy, multi=True)

            st.markdown("### 2車単｜妙味評価（ε軸・過去分引継ぎ）")
            st.caption("ε軸の過去成績は、既存のα軸集計からは復元できません。確認できる過去データだけ入力してください。")
            header()
            for other in ("α", "β", "γ", "Ω"):
                carry_epsilon_exacta[other] = carry_entry(
                    f"ε→{other}", f"epsilon_carry_2t_{other}")
            st.form_submit_button("前日までの集計を反映")
    st.download_button(
        "日次＋引継ぎをまとめてバックアップ（JSON）",
        data=json.dumps(export_complete_backup(), ensure_ascii=False, indent=2).encode("utf-8"),
        file_name="velovi_complete_backup.json", mime="application/json",
        key="velovi_complete_backup_download",
    )
    st.caption("バックアップには日次100Rと印着内率、2車単、2車複の引継ぎ入力値を含みます。引継ぎ値の変更後は再度ダウンロードしてください。")


# 集計区分は表示とCSVに共通。元の100Rデータには一切手を加えない。
with tab_result:
    category = st.radio("集計区分", ("男子（通常）", "ガールズ", "全レース"),
                        horizontal=True, key="velovi_result_category")
    st.caption("ガールズにチェックしたレースだけをガールズ集計へ。未チェックは男子として扱います。")
    session_category = st.radio("開催区分", ("通常開催", "ミッドナイト", "全開催"), horizontal=True, key="velovi_result_session")
    st.caption("入力時に『ミッドナイト』へチェックしたレースだけを分離します。未チェックは通常開催です。旧データの開催区分も引き継ぎます。")

# 引継ぎの過去数値には男女区分がないため、区分別集計には絶対に混ぜない。
# 全レースを選んだときのみ従来どおり引継ぎを合算する。
if category != "全レース" or session_category != "全開催":
    carry_mark_records = {g: blank_group_marks(g) for g in GROUP_MARKS}
    carry_bet_records = {g: blank_group_bets(g) for g in GROUP_MARKS}
    carry_unmarked = {name: blank_unmarked() for name in carry_unmarked}
    carry_quinella_all = {g: {} for g in GROUP_MARKS}
    carry_quinella_named = {}
    carry_epsilon_exacta = {m: blank_bet() for m in ("α", "β", "γ", "Ω")}
    carry_epsilon_quinella = {m: blank_bet() for m in ("β", "γ", "Ω")}

selected_daily_rows = [r for r in daily_rows
                       if category == "全レース" or
                       bool(r.get("girls", False)) == (category == "ガールズ")]
selected_daily_rows = [r for r in selected_daily_rows
                       if session_category == "全開催" or
                       (r.get("session", "デイ") == "ミッドナイト") == (session_category == "ミッドナイト")]

# 区分別引継ぎは集計区分に一致するものだけを合算する。
def _scoped_values(scope_id):
    prefix = f"scopedcarry_{scope_id}_"
    def value(key):
        return int(st.session_state.get(prefix + key, 0) or 0)
    marks = {g: {m: {"N":value(f"mark_{g}_{m}_n"), "C1":value(f"mark_{g}_{m}_c1"),
                       "C2":value(f"mark_{g}_{m}_c2"), "C3":value(f"mark_{g}_{m}_c3")}
                 for m in GROUP_MARKS[g]} for g in GROUP_MARKS}
    def bet(kind, axis, target):
        code=f"{kind}_{axis}_{target}"
        n=value(code+"_n")
        return {"N":n, "KSUM":value(code+"_points") if target == "無印" else n,
                "H":value(code+"_h"), "SUM":value(code+"_sum")}
    return marks, bet

_scope_ids = []
for _g, _sid in ((False,"boy_day"),(False,"boy_mid"),(True,"girl_day"),(True,"girl_mid")):
    if category != "全レース" and (category == "ガールズ") != _g:
        continue
    if session_category != "全開催" and (session_category == "ミッドナイト") != _sid.endswith("mid"):
        continue
    _scope_ids.append(_sid)

# 区分別引継ぎを既存の累積レコードに反映。
for _sid in _scope_ids:
    _marks, _bet = _scoped_values(_sid)
    for _g in GROUP_MARKS:
        for _m in GROUP_MARKS[_g]:
            carry_mark_records[_g][_m] = add_records(carry_mark_records[_g][_m], _marks[_g][_m], ("N","C1","C2","C3"))
    for _m in ("○","▲","△","×"):
        _key=("◎",_m)
        carry_bet_records["通常"][_key] = add_records(carry_bet_records["通常"][_key], _bet("2車単","◎",_m), ("N","H","SUM","KSUM"))
    for _m in ("β","γ","ε","Ω"):
        _key=("α",_m)
        carry_bet_records["妙味"][_key] = add_records(carry_bet_records["妙味"][_key], _bet("2車単","α",_m), ("N","H","SUM","KSUM"))
    for _m in ("α","β","γ","Ω"):
        carry_epsilon_exacta[_m] = add_records(carry_epsilon_exacta[_m], _bet("2車単","ε",_m), ("N","H","SUM","KSUM"))
    for _m in ("○","▲","△","×","無印","β","ε"):
        _label="◎－無印合計" if _m == "無印" else "◎－"+_m
        carry_quinella_named[_label] = add_records(carry_quinella_named.get(_label,blank_bet()), _bet("2車複","◎",_m), ("N","H","SUM","KSUM"))
    for _m in ("β","γ","ε","Ω"):
        _pair=("α",_m)
        carry_quinella_all["妙味"][_pair] = add_records(carry_quinella_all["妙味"].get(_pair,blank_bet()), _bet("2車複","α",_m), ("N","H","SUM","KSUM"))
    for _m in ("β","γ","Ω"):
        carry_epsilon_quinella[_m] = add_records(carry_epsilon_quinella[_m], _bet("2車複","ε",_m), ("N","H","SUM","KSUM"))

# ============================================================
# C. 日次集計（除外・部分入力・払い戻しチェック）
# ============================================================
daily_mark_records = {g: blank_group_marks(g) for g in GROUP_MARKS}
daily_bet_records = {g: blank_group_bets(g) for g in GROUP_MARKS}
daily_epsilon_exacta = {m: blank_bet() for m in ("α", "β", "γ", "Ω")}
daily_final_2f = {m: blank_bet() for m in "ABCD"}
daily_final_2t = {m: blank_bet() for m in "ABCD"}
daily_final_marks = {m: blank_mark() for m in ("ε", "A", "B", "C", "D")}
daily_unmarked = {name: blank_unmarked() for name in ("◎→×", "◎→無印1", "◎→無印2")}
daily_quinella = {name: blank_bet() for name in ('◎－○', '◎－▲', '◎－△', '◎－×', '◎－無印合計', '◎－β', '◎－ε')}
quinella_missing_payouts = 0
# 全2車複：通常／妙味それぞれの5印＋残り無印を全組み合わせで検証。
# 集計は日次入力のみ。引継ぎの集計値から未記録の組み合わせは復元できない。
quinella_all_records = {g: {} for g in GROUP_MARKS}
quinella_all_races = {g: 0 for g in GROUP_MARKS}
quinella_all_missing = {g: 0 for g in GROUP_MARKS}
quinella_all_order = {g: list(GROUP_MARKS[g]) + ["無印1", "無印2"] for g in GROUP_MARKS}
valid_races = {g: 0 for g in GROUP_MARKS}
excluded_races = 0
warnings: List[str] = []
race_details: List[Dict] = []

for entry in selected_daily_rows:
    rid = str(entry["race"]).strip()
    raw_normal = str(entry["normal"]).strip()
    raw_alpha = str(entry["alpha"]).strip()
    raw_finish = str(entry["finish"]).strip()
    payout = int(entry["pay"])
    quinella_pay = int(entry.get("quinella_pay", 0))
    field_size = int(entry["field_size"])
    exclude = bool(entry["exclude"])

    if not any([raw_normal, raw_alpha, raw_finish, payout > 0, quinella_pay > 0, exclude]):
        continue

    if exclude:
        excluded_races += 1
        race_details.append({
            "R": rid, "通常印順": raw_normal, "妙味印順": raw_alpha,
            "着順": raw_finish, "2車単払戻": payout,
            "集計除外": "除外", "通常的中": "集計除外", "妙味的中": "集計除外"
        })
        continue

    finish = parse_finish(raw_finish)
    if len(finish) < 3:
        warnings.append(f"R{rid}: 着順は3着まで入力してください。例 463 / 4-6-3")
        continue

    detail = {
        "R": rid, "通常印順": raw_normal, "妙味印順": raw_alpha,
        "着順": "-".join(finish[:3]), "2車単払戻": payout,
        "集計除外": "", "◎→×無無": "未集計"
    }
    for group, raw in (("通常", raw_normal), ("妙味", raw_alpha)):
        if not raw:
            detail[f"{group}的中"] = "未入力"
            continue
        marks = parse_markline(raw, group)
        if not marks:
            warnings.append(f"R{rid}: {group}印順は4車または5車、重複なしで入力してください。")
            detail[f"{group}的中"] = "入力不正"
            continue
        valid_races[group] += 1

        # 印別の1着、2着、3着回数。
        # 5番目の印が省略された場合、その印だけ対象Nから除外する。
        car_to_mark = {car: mark for mark, car in marks.items()}
        for mark in marks:
            daily_mark_records[group][mark]["N"] += 1
        for pos, car in enumerate(finish[:3], 1):
            mark = car_to_mark.get(car)
            if mark:
                daily_mark_records[group][mark][f"C{pos}"] += 1

        # 2車単は軸1着固定のみ。
        hits = []
        for a, b in BET_PAIRS[group]:
            if a not in marks or b not in marks:
                continue
            rec = daily_bet_records[group][(a, b)]
            rec["N"] += 1
            rec["KSUM"] += 1
            if finish[0] == marks[a] and finish[1] == marks[b]:
                rec["H"] += 1
                rec["SUM"] += payout
                hits.append(f"{a}→{b}")
                if payout <= 0:
                    warnings.append(f"R{rid}: {group} {a}→{b} 的中ですが払戻が0です。")
        if group == "妙味" and "ε" in marks:
            for other, rec in daily_epsilon_exacta.items():
                if other not in marks or marks[other] == marks["ε"]:
                    continue
                rec["N"] += 1
                rec["KSUM"] += 1
                if finish[0] == marks["ε"] and finish[1] == marks[other]:
                    rec["H"] += 1
                    rec["SUM"] += payout
                    if payout <= 0:
                        warnings.append(f"R{rid}: ε→{other} 的中ですが2車単払戻が未入力です。")
        detail[f"{group}的中"] = " / ".join(hits) if hits else "なし"
        if group == "通常":
            # 5印のあるレースだけ、残る車番を無印として確定する。
            # 6車なら無印1車、7車なら無印2車。4印では判定しない。
            if len(marks) == 5 and all(1 <= int(v) <= field_size for v in marks.values()) and all(1 <= int(v) <= field_size for v in finish):
                unknown = sorted(set(str(v) for v in range(1, field_size + 1)) - set(marks.values()), key=int)
                targets = [("◎→×", marks["×"])] + [(f"◎→無印{i}", car) for i, car in enumerate(unknown, 1)]
                if len(unknown) == field_size - 5:
                    hit_names = []
                    for name, second_car in targets:
                        if name not in daily_unmarked:
                            continue
                        rec_u = daily_unmarked[name]
                        rec_u["N"] += 1
                        rec_u["KSUM"] += 1
                        if finish[0] == marks["◎"] and finish[1] == second_car:
                            rec_u["H"] += 1
                            rec_u["SUM"] += payout
                            hit_names.append(name)
                            if payout <= 0:
                                warnings.append(f"R{rid}: {name}的中ですが払戻が0です。")
                    detail["◎→×無無"] = " / ".join(hit_names) if hit_names else "なし"
            elif len(marks) == 4:
                detail["◎→×無無"] = "×未入力・対象外"
            else:
                warnings.append(f"R{rid}: 車数と車番が一致しないため◎→×無無を集計しません。")
                detail["◎→×無無"] = "車数不一致・対象外"
    # 2車複・全通り：各評価の5印＋無印1・2で全21通り（6車なら15通り）。
    # 無印1・2は、その評価で印のない車番を小さい順に割り当てる。
    # 同一レースで各評価は別集計。的中は1組のみで、払戻は2車複入力を使う。
    for q_group, q_raw in (("通常", raw_normal), ("妙味", raw_alpha)):
        q_all_marks = parse_markline(q_raw, q_group) if q_raw else {}
        if len(q_all_marks) != 5 or not all(1 <= int(v) <= field_size for v in q_all_marks.values()):
            continue
        if not all(1 <= int(v) <= field_size for v in finish[:2]):
            continue
        q_remaining = sorted(set(str(v) for v in range(1, field_size + 1)) - set(q_all_marks.values()), key=int)
        if len(q_remaining) != field_size - 5:
            continue
        q_labeled = dict(q_all_marks)
        q_labeled.update({f"無印{i}": car for i, car in enumerate(q_remaining, 1)})
        q_order = [label for label in quinella_all_order[q_group] if label in q_labeled]
        quinella_all_races[q_group] += 1
        for left, right in combinations(q_order, 2):
            key = (left, right)
            rec = quinella_all_records[q_group].setdefault(key, blank_bet())
            rec["N"] += 1
            rec["KSUM"] += 1
            if {q_labeled[left], q_labeled[right]} == set(finish[:2]):
                rec["H"] += 1
                if quinella_pay > 0:
                    rec["SUM"] += quinella_pay
                else:
                    quinella_all_missing[q_group] += 1
                    warnings.append(f"R{rid}: {q_group}2車複 {left}－{right} 的中ですが払戻未入力です。")

    # 2車複：通常印4～5車、妙味印4～5車。車番が重なる買い目も分類ごとに独立検証。
    q_marks = parse_markline(raw_normal, "通常") if raw_normal else {}
    q_value_marks = parse_markline(raw_alpha, "妙味") if raw_alpha else {}
    q_valid = (len(q_marks) in (4, 5) and "◎" in q_marks
               and all(1 <= int(v) <= field_size for v in q_marks.values()))
    if q_valid:
        q_axis = q_marks["◎"]
        q_unmarked = sorted(set(str(v) for v in range(1, field_size + 1)) - set(q_marks.values()), key=int)
        q_pairs = [(f"◎－{mark}", q_marks[mark]) for mark in ("○", "▲", "△", "×") if mark in q_marks]
        q_pairs += [("◎－無印合計", car) for car in q_unmarked]
        if len(q_value_marks) in (4, 5):
            q_pairs += [(f"◎－{mark}", q_value_marks[mark]) for mark in ("β", "ε") if mark in q_value_marks]
        q_results = {name: False for name in daily_quinella}
        for q_label, q_other in q_pairs:
            if q_axis == q_other or not 1 <= int(q_other) <= field_size:
                continue
            q_rec = daily_quinella[q_label]
            q_rec["N"] += 1
            q_rec["KSUM"] += 1
            if {q_axis, q_other} == set(finish[:2]):
                q_rec["H"] += 1
                q_results[q_label] = True
                if quinella_pay > 0:
                    q_rec["SUM"] += quinella_pay
                else:
                    quinella_missing_payouts += 1
                    warnings.append(f"R{rid}: 2車複{q_label}が的中していますが、2車複払戻が未入力です。")
        for q_label in daily_quinella:
            detail[f"2車複 {q_label}"] = "的中" if q_results[q_label] else "外れ・対象外"
    else:
        for q_label in daily_quinella:
            detail[f"2車複 {q_label}"] = "印不足・対象外"
    # 最終総合評価 εABCD：妙味評価とは独立した任意入力。
    final_raw = clean_digits(entry.get("epsilon_final", ""))
    if final_raw:
        if len(final_raw) != 5 or len(set(final_raw)) != 5 or "0" in final_raw or any(int(x)>field_size for x in final_raw):
            warnings.append(f"R{rid}: 最終総合評価εABCDは異なる5車番で入力してください。")
        else:
            final_map=dict(zip(("ε","A","B","C","D"),final_raw))
            for m,car in final_map.items():
                daily_final_marks[m]["N"]+=1
                if car in finish[:3]:
                    daily_final_marks[m][f"C{finish.index(car)+1}"]+=1
            for m in "ABCD":
                if {final_map["ε"],final_map[m]} == set(finish[:2]):
                    daily_final_2f[m]["H"]+=1
                    daily_final_2f[m]["SUM"]+=quinella_pay
                daily_final_2f[m]["N"]+=1
                daily_final_2f[m]["KSUM"]+=1
                if finish[0]==final_map["ε"] and finish[1]==final_map[m]:
                    daily_final_2t[m]["H"]+=1
                    daily_final_2t[m]["SUM"]+=payout
                daily_final_2t[m]["N"]+=1
                daily_final_2t[m]["KSUM"]+=1
    race_details.append(detail)


# ============================================================
# D. 累積 = 引継ぎ + 日次
# ============================================================
total_mark_records = {}
total_bet_records = {}
for group, marks in GROUP_MARKS.items():
    total_mark_records[group] = {
        m: add_records(carry_mark_records[group][m], daily_mark_records[group][m],
                       ("N", "C1", "C2", "C3")) for m in marks
    }
    total_bet_records[group] = {
        pair: add_records(carry_bet_records[group][pair], daily_bet_records[group][pair],
                          ("N", "H", "SUM", "KSUM")) for pair in BET_PAIRS[group]
    }



total_unmarked = {"◎→×": add_records(carry_unmarked["◎→×"], daily_unmarked["◎→×"], ("N","H","SUM","KSUM"))}
_daily_um = sum_bets([daily_unmarked["◎→無印1"], daily_unmarked["◎→無印2"]]) if "sum_bets" in globals() else {
    "N": max(daily_unmarked["◎→無印1"]["N"],daily_unmarked["◎→無印2"]["N"]),
    "H": sum(daily_unmarked[k]["H"] for k in ("◎→無印1","◎→無印2")),
    "SUM": sum(daily_unmarked[k]["SUM"] for k in ("◎→無印1","◎→無印2")),
    "KSUM": sum(daily_unmarked[k]["KSUM"] for k in ("◎→無印1","◎→無印2"))}
total_unmarked["◎→無印"] = add_records(carry_unmarked["◎→無印"], _daily_um, ("N","H","SUM","KSUM"))


def unmarked_summary(records):
    """◎→×と無印を合計。実際に対象となった点数を分母にする。"""
    keys = ("◎→×", "◎→無印1", "◎→無印2")
    n = max(int(records[k]["N"]) for k in keys)
    ksum = sum(int(records[k]["KSUM"]) for k in keys)
    h = sum(int(records[k]["H"]) for k in keys)
    summ = sum(int(records[k]["SUM"]) for k in keys)
    return {"評価": "通常・穴相手", "3点セット": "◎→×・無印・無印", "対象R": int(n),
            "購入点数": ksum, "投資額": ksum * 100, "的中数": h,
            "平均的中配当": round(summ / h, 1) if h else None,
            "払戻合計": summ, "回収率%": pct(summ, ksum * 100)}


def unmarked_frame(records):
    return pd.DataFrame([bet_row(k, records[k]) for k in ("◎→×", "◎→無印1", "◎→無印2")])


def mark_frame(group, records):
    return pd.DataFrame([mark_row(m, records[group][m]) for m in GROUP_MARKS[group]])


def bet_frame(group, records):
    return pd.DataFrame([
        bet_row(f"{a}→{b}", records[group][(a, b)]) for a, b in BET_PAIRS[group]
    ])


def set_summary(group, records):
    """指定3点の実購入点数合計から回収率を算出。欠損印は対象外。"""
    axis = GROUP_AXES[group]
    selected = [records[group][(axis, m)] for m in SET_TARGETS[group]]
    n = min(int(r["N"]) for r in selected) if selected else 0
    ksum = sum(int(r["KSUM"]) for r in selected)
    h = sum(int(r["H"]) for r in selected)
    summ = sum(int(r["SUM"]) for r in selected)
    return {
        "評価": group,
        "3点セット": f"{axis}→{'・'.join(SET_TARGETS[group])}",
        "対象R": int(n),
        "購入点数": ksum,
        "投資額": ksum * 100,
        "的中数": h,
        "払戻合計": summ,
        "平均的中配当": round(summ / h, 1) if h else None,
        "回収率%": pct(summ, ksum * 100),
    }


# ============================================================
# E. 結果・CSV・本日分・レース別判定
# ============================================================
# 累積：既存の日次集計に過去引継ぎを加算（入力済みの過去分を二重に入れないこと）。
quinella_all_total = {g:{} for g in GROUP_MARKS}
for g in GROUP_MARKS:
    for pair in set(quinella_all_records[g]) | set(carry_quinella_all[g]):
        quinella_all_total[g][pair] = add_records(quinella_all_records[g].get(pair, blank_bet()), carry_quinella_all[g].get(pair, blank_bet()), ("N","H","SUM","KSUM"))
# ε軸2車複の引継ぎを累積に反映。α－εは既存のα軸入力を共用。
# 組み合わせキーは全組み合わせ集計と同じ並び順に揃える。
for other, pair in (("β", ("β", "ε")), ("γ", ("γ", "ε")), ("Ω", ("ε", "Ω"))):
    quinella_all_total["妙味"][pair] = add_records(
        quinella_all_total["妙味"].get(pair, blank_bet()),
        carry_epsilon_quinella[other], ("N", "H", "SUM", "KSUM"))

# 「全21組」と「記号別比較」のどちらに前日分を入力しても◎軸累積へ反映。
# 同一買い目の二重加算を防止するため、記号別比較が入力済みなら優先する。
def sum_bets(records):
    """同じ軸からの異なる買い目を各100円ずつ購入した合算。"""
    selected = list(records)
    if not selected:
        return blank_bet()
    return {"N": max(int(r["N"]) for r in selected),
            "KSUM": sum(int(r["KSUM"]) for r in selected),
            "H": sum(int(r["H"]) for r in selected),
            "SUM": sum(int(r["SUM"]) for r in selected)}


def past_named_quinella(label):
    return carry_quinella_named.get(label, blank_bet())

quinella_named_total = {
    name: add_records(daily_quinella[name], past_named_quinella(name), ("N", "H", "SUM", "KSUM"))
    for name in daily_quinella
}
def compact_result(name, rec):
    """結果一覧に必要な項目だけを表示。的中率は対象R基準。"""
    r = bet_row(name, rec)
    return {"買い方": name, "対象R": r["対象R"], "購入点数": r["購入点数"],
            "的中R": r["的中数"], "的中率%": r["的中率%"],
            "投資額": r["投資額"], "払戻合計": r["払戻合計"],
            "収支": r["払戻合計"] - r["投資額"], "回収率%": r["回収率%"]}





# ε軸2車単は独立集計。2車複はα軸全組み合わせから同一車券を再利用。
total_epsilon_exacta = {
    m: add_records(carry_epsilon_exacta[m], daily_epsilon_exacta[m],
                   ("N", "H", "SUM", "KSUM"))
    for m in ("α", "β", "γ", "Ω")
}

with tab_result:
    st.subheader(f"印着内率【{category}】")
    if category != "全レース" or session_category != "全開催":
        st.info("この区分の成績はレース別入力のみから集計しています。区分のない過去引継ぎ値は含めていません。")
    st.caption(f"選択区分の有効入力：通常{valid_races['通常']}R／妙味{valid_races['妙味']}R・除外{excluded_races}R。過去引継ぎは全レース・全開催表示時のみ加算。")
    for group in GROUP_MARKS:
        st.markdown(f"**{group}評価**")
        show_full_table(mark_frame(group, total_mark_records).style.format({
            "1着率%": "{:.1f}", "連対率%": "{:.1f}", "印着内率%": "{:.1f}"
        }, na_rep="—"))

    st.markdown("**最終総合評価 εABCD｜日次入力分**")
    st.caption("独立した最終評価の入力があるレースだけ集計。前日引継ぎの妙味ε軸とは混同しません。")
    show_full_table(pd.DataFrame([mark_row(m,daily_final_marks[m]) for m in ("ε","A","B","C","D")]))
    st.subheader("2車複｜◎軸・買い目別【累積】")
    show_full_table(style_roi(pd.DataFrame([
        compact_result(name, quinella_named_total[name]) for name in daily_quinella_labels
    ])))

    st.subheader("2車複｜妙味評価 α軸・買い目別【累積】")
    show_full_table(style_roi(pd.DataFrame([
        compact_result(f"α－{m}", quinella_all_total["妙味"].get(("α", m), blank_bet()))
        for m in ("β", "γ", "ε", "Ω")
    ])))

    st.subheader("2車複｜妙味評価 ε軸・買い目別【累積】")
    st.caption("ε－αはα－εと同一車券。既存の2車複全組み合わせから参照し、二重集計しません。過去分は既存引継ぎのある組み合わせのみ反映されます。")
    epsilon_quinella = []
    for m in ("α", "β", "γ", "Ω"):
        pair = ("α", "ε") if m == "α" else (m, "ε") if m in ("β", "γ") else ("ε", "Ω")
        epsilon_quinella.append(compact_result(
            f"ε－{m}", quinella_all_total["妙味"].get(pair, blank_bet())
        ))
    show_full_table(style_roi(pd.DataFrame(epsilon_quinella)))

    st.markdown("**2車複｜最終総合評価 ε軸**")
    show_full_table(style_roi(pd.DataFrame([compact_result(f"ε－{m}",daily_final_2f[m]) for m in "ABCD"])))

    st.subheader("2車単｜◎軸・買い目別【累積】")
    normal_exacta_rows = [compact_result(f"◎→{m}", total_bet_records["通常"][("◎", m)])
                         for m in ("○", "▲", "△", "×")]
    normal_exacta_rows.append(compact_result("◎→無印", total_unmarked["◎→無印"]))
    show_full_table(style_roi(pd.DataFrame(normal_exacta_rows)))

    st.subheader("2車単｜妙味評価 α軸・買い目別【累積】")
    show_full_table(style_roi(pd.DataFrame([
        compact_result(f"α→{m}", total_bet_records["妙味"][("α", m)])
        for m in ("β", "γ", "ε", "Ω")
    ])))

    st.subheader("2車単｜妙味評価 ε軸・買い目別【累積】")
    show_full_table(style_roi(pd.DataFrame([
        compact_result(f"ε→{m}", total_epsilon_exacta[m])
        for m in ("α", "β", "γ", "Ω")
    ])))

    st.markdown("**2車単｜最終総合評価 ε軸**")
    show_full_table(style_roi(pd.DataFrame([compact_result(f"ε→{m}",daily_final_2t[m]) for m in "ABCD"])))

    if warnings:
        st.warning("\n".join(warnings[:25]) + ("\n…" if len(warnings) > 25 else ""))
    if race_details:
        with st.expander("本日のレース別判定を確認"):
            show_full_table(pd.DataFrame(race_details).fillna(""))
    st.download_button("買い目別集計CSV", data=pd.concat([
        pd.DataFrame([compact_result(name, quinella_named_total[name]) for name in daily_quinella_labels]).assign(分類="2車複◎"),
        pd.DataFrame(normal_exacta_rows).assign(分類="2車単◎"),
        pd.DataFrame([compact_result(f"α－{m}", quinella_all_total["妙味"].get(("α", m), blank_bet())) for m in ("β", "γ", "ε", "Ω")]).assign(分類="2車複α"),
        pd.DataFrame([compact_result(f"α→{m}", total_bet_records["妙味"][("α", m)]) for m in ("β", "γ", "ε", "Ω")]).assign(分類="2車単α"),
        pd.DataFrame(epsilon_quinella).assign(分類="2車複ε"),
        pd.DataFrame([compact_result(f"ε→{m}", total_epsilon_exacta[m]) for m in ("α", "β", "γ", "Ω")]).assign(分類="2車単ε"),
    ], ignore_index=True).to_csv(index=False).encode("utf-8-sig"), file_name=f"velovi_{category}_{session_category}_results.csv", mime="text/csv")
