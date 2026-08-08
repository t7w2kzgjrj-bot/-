import sqlite3
import re
from datetime import datetime, timedelta
import streamlit as st
import pandas as pd
import plotly.express as px
from google import genai
from google.genai import types

# 1. データベース設定 (SQLite)
CONN = sqlite3.connect("forgetting_curve.db", check_same_thread=False)
CURSOR = CONN.cursor()
CURSOR.execute(
    """
CREATE TABLE IF NOT EXISTS weaknesses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    interval_stage INTEGER DEFAULT 0,
    next_review_date TEXT NOT NULL,
    status TEXT DEFAULT 'learning'
)
"""
)
CONN.commit()

# 2. Gemini APIの設定
API_KEY = st.secrets.get("GEMINI_API_KEY") if "GEMINI_API_KEY" in st.secrets else None
if API_KEY:
    client = genai.Client(api_key=API_KEY)

# 復習間隔（日数）
INTERVALS = [1, 3, 7, 14]

def analyze_mistake_with_search(file_bytes: bytes, mime_type: str) -> str:
    """GeminiにファイルとGoogle検索を使わせて分析させる"""
    prompt = """
    あなたは優秀な予備校講師です。添付されたファイルは、私が解いた模試の問題と自分の解答です。
    
    以下の手順で分析を行ってください：
    1. 添付ファイルの内容から問題文のキーワードを読み取り、Google検索で「大学受験の森」の中にある該当問題の解答解説を調べてください。
    2. 検索して得た正しい解答解説と、私の解答を比較し、「どこで、なぜ間違えたのか（計算ミスか、公式の勘違いか、方針の誤りか）」を優しく詳細に分析してください。
    3. この間違いを克服するために復習すべき「単元名」を一つ特定してください。
    
    必ず以下のフォーマットで出力してください。
    
    【間違いの分析】
    （ここに詳細な分析結果と正しい考え方を書く）
    
    【苦手単元】
    （単元名のみを短く書く。例：三角関数の合成、2次方程式の解の配置 など）
    """
    
    document_part = types.Part.from_bytes(data=file_bytes, mime_type=mime_type)
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[document_part, prompt],
        config=types.GenerateContentConfig(
            tools=[{"google_search": {}}],
            temperature=0.2,
        )
    )
    return response.text

def generate_question_with_gemini(topic: str) -> str:
    """類似問題生成"""
    prompt = f"単元「{topic}」に関する理解度確認テストを作成してください。\n1. 類似問題（1問）\n2. ヒント・使うべき公式\n3. 詳細な解説と解答"
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    return response.text

# 3. Streamlit UI構築
st.set_page_config(page_title="模試分析×忘却曲線", layout="wide")
st.title("🧠 模試分析 × 忘却曲線 学習アプリ")

# サイドバー設定（日本語化）
st.sidebar.header("⚙️ 設定")
if not API_KEY:
    user_api_key = st.sidebar.text_input("Gemini APIキーを入力してください", type="password")
    if user_api_key:
        client = genai.Client(api_key=user_api_key)
        API_KEY = user_api_key
else:
    st.sidebar.success("APIキー設定済み")

# タブ名（日本語化）
tab1, tab2, tab3 = st.tabs(["📸 模試を分析・登録", "⏰ 本日の復習問題", "📊 学習ダッシュボード"])

# 【タブ1】画像・PDFからの分析と登録
with tab1:
    st.subheader("模試の問題と解答を送信")
    st.write("画像（スマホの写真）またはPDFをアップロードすると、AIが「大学受験の森」を検索して間違いを分析します。")
    
    uploaded_file = st.file_uploader("ファイルを選択（画像: JPG, PNG / 文書: PDF）", type=["jpg", "jpeg", "png", "pdf"])
    
    if uploaded_file is not None:
        if "image" in uploaded_file.type:
            st.image(uploaded_file, caption="アップロードされた画像", use_container_width=True)
            
        if st.button("AIで間違いを分析する"):
            if not API_KEY:
                st.error("サイドバーにAPIキーが入力されていません。")
            else:
                with st.spinner("🔍 「大学受験の森」を検索し、あなたの解答を分析中...（しばらくお待ちください）"):
                    file_bytes = uploaded_file.getvalue()
                    mime_type = uploaded_file.type
                    
                    try:
                        analysis_result = analyze_mistake_with_search(file_bytes, mime_type)
                        
                        st.markdown("### 💡 AIによる分析結果")
                        st.write(analysis_result)
                        
                        match = re.search(r"【苦手単元】\n(.*)", analysis_result)
                        if match:
                            topic = match.group(1).strip()
                            tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                            CURSOR.execute(
                                "INSERT INTO weaknesses (topic, interval_stage, next_review_date) VALUES (?, 0, ?)",
                                (topic, tomorrow),
                            )
                            CONN.commit()
                            st.success(f"✅ 苦手単元「**{topic}**」を復習スケジュール（初回: {tomorrow}）に自動登録しました！")
                        else:
                            st.warning("単元名の自動抽出に失敗しました。")
                            
                    except Exception as e:
                        st.error(f"エラーが発生しました: {e}")

# 【タブ2】本日の復習問題
with tab2:
    st.subheader("今日復習すべき単元")
    today = datetime.now().strftime("%Y-%m-%d")

    CURSOR.execute(
        "SELECT id, topic, interval_stage FROM weaknesses WHERE next_review_date <= ? AND status = 'learning'",
        (today,),
    )
    due_items = CURSOR.fetchall()

    if not due_items:
        st.info("🎉 本日復習する問題はありません！素晴らしい進捗です。")
    else:
        for item_id, topic, stage in due_items:
            with st.expander(f"📌 単元: {topic} (現在の復習ステップ: {stage + 1}/4)"):
                st.write(f"復習ステップ: {stage + 1} 回目 / 次の間隔: {INTERVALS[stage]}日")

                if st.button(f"「{topic}」のAI類似問題を生成", key=f"btn_{item_id}"):
                    with st.spinner("AIが類似問題を生成中..."):
                        q_text = generate_question_with_gemini(topic)
                        st.markdown(q_text)

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("正解した ⭕️", key=f"ok_{item_id}"):
                        next_stage = stage + 1
                        if next_stage >= len(INTERVALS):
                            CURSOR.execute("UPDATE weaknesses SET status = 'mastered' WHERE id = ?", (item_id,))
                            st.balloons()
                            st.success(f"「{topic}」を完全克服しました！")
                        else:
                            next_date = (datetime.now() + timedelta(days=INTERVALS[next_stage])).strftime("%Y-%m-%d")
                            CURSOR.execute("UPDATE weaknesses SET interval_stage = ?, next_review_date = ? WHERE id = ?", (next_stage, next_date, item_id))
                            st.success(f"お見事！次回の復習は {next_date} です。")
                        CONN.commit()
                        st.rerun()
                with col2:
                    if st.button("間違えた ❌", key=f"ng_{item_id}"):
                        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
                        CURSOR.execute("UPDATE weaknesses SET interval_stage = 0, next_review_date = ? WHERE id = ?", (tomorrow, item_id))
                        CONN.commit()
                        st.error(f"次回は明日（{tomorrow}）再度チャレンジしましょう！")
                        st.rerun()

# 【タブ3】学習ダッシュボード
with tab3:
    st.subheader("📈 学習進捗状況と実績")

    df = pd.read_sql_query("SELECT * FROM weaknesses", CONN)

    if df.empty:
        st.info("まだ登録されている単元がありません。模試の画像をアップロードして分析を始めてみましょう！")
    else:
        total_count = len(df)
        mastered_count = len(df[df["status"] == "mastered"])
        learning_count = total_count - mastered_count
        mastery_rate = round((mastered_count / total_count) * 100, 1) if total_count > 0 else 0

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("総登録単元数", f"{total_count} 件")
        col2.metric("学習中の単元", f"{learning_count} 件")
        col3.metric("🎉 克服済みの単元", f"{mastered_count} 件")
        col4.metric("克服率", f"{mastery_rate} %")

        st.divider()

        col_left, col_right = st.columns(2)

        # 1. 円グラフ（日本語化）
        with col_left:
            st.write("#### 📊 学習ステータスの割合")
            status_df = df.copy()
            status_df["ステータス"] = status_df["status"].map({"learning": "復習中", "mastered": "克服済み"})
            
            fig_pie = px.pie(
                status_df, 
                names="ステータス", 
                color="ステータス",
                color_discrete_map={"復習中": "#FFA726", "克服済み": "#66BB6A"},
                hole=0.4
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        # 2. 棒グラフ（日本語化）
        with col_right:
            st.write("#### 🔁 復習進行度（ステップ分布）")
            learning_df = df[df["status"] == "learning"].copy()
            if not learning_df.empty:
                learning_df["ステップ"] = learning_df["interval_stage"] + 1
                stage_counts = learning_df["ステップ"].value_counts().sort_index().reset_index()
                stage_counts.columns = ["復習ステップ", "件数"]
                stage_counts["復習ステップ"] = stage_counts["復習ステップ"].astype(str) + " 回目"

                fig_bar = px.bar(
                    stage_counts, 
                    x="復習ステップ", 
                    y="件数",
                    color="件数",
                    color_continuous_scale="Blues"
                )
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.success("現在、復習中の単元はありません！すべて克服済みです！")

        st.divider()

        # 3. 克服済み単元の一覧リスト（日本語化）
        st.write("#### 🏆 完全克服した単元一覧")
        mastered_df = df[df["status"] == "mastered"][["id", "topic"]].reset_index(drop=True)
        mastered_df.columns = ["ID", "単元名"]

        if not mastered_df.empty:
            st.dataframe(mastered_df, use_container_width=True)
        else:
            st.write("まだ克服済みの単元はありません。毎日コツコツ復習を続けましょう！")

        # 4. 全データ管理テーブル（日本語化）
        with st.expander("⚙️ 登録データの一覧・手動管理"):
            # テーブルの列名を日本語に変換して表示
            display_df = df.copy()
            display_df.columns = ["ID", "単元名", "現在の復習段階", "次回予定日", "ステータス"]
            display_df["ステータス"] = display_df["ステータス"].map({"learning": "復習中", "mastered": "克服済み"})
            st.dataframe(display_df, use_container_width=True)
            
            delete_id = st.number_input("削除したいデータのIDを入力してください", min_value=1, step=1)
            if st.button("指定したIDのデータを削除"):
                CURSOR.execute("DELETE FROM weaknesses WHERE id = ?", (delete_id,))
                CONN.commit()
                st.success(f"ID {delete_id} のデータを削除しました。")
                st.rerun()
