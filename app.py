import streamlit as st
import google.generativeai as genai
from PIL import Image
import pypdf

# ページ基本設定
st.set_page_config(page_title="模試分析×忘却曲線学習アプリ", icon="🧠")

st.title("🧠 模試分析×忘却曲線学習アプリ")

# APIキーの設定
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
else:
    api_key = st.sidebar.text_input("Gemini API Key", type="password")
    if api_key:
        genai.configure(api_key=api_key)

st.subheader("模試の問題と解答を送信")

# 1. 複数ファイルを選択可能
uploaded_files = st.file_uploader(
    "画像（スマホの写真）またはPDFをアップロードしてください（複数選択可）",
    type=["jpg", "jpeg", "png", "pdf"],
    accept_multiple_files=True
)

if uploaded_files:
    st.success(f"{len(uploaded_files)} 個のファイルが選択されました。")

if st.button("分析を開始する"):
    if not uploaded_files:
        st.error("ファイルを選択してください。")
    else:
        with st.spinner("AIが間違えた問題を分析中..."):
            try:
                # 2. AI自ら回答を作成するプロンプト
                prompt = """
                あなたは優秀な受験指導AIです。
                提示された模試の問題と解答のデータ（画像またはPDF）を分析してください。

                【指示事項】
                1. 「大学受験の森」などの外部情報・Webデータベースを参照して間違いや傾向を分析してください。
                2. もし「大学受験の森」にデータが存在しない問題や解答であっても、あなた自身の知識をフル活用して正確な解法・解説・間違いの原因分析を提示してください。
                3. 生徒が忘却曲線に基づいて効率よく復習できるように、以下のフォーマットで出力してください。

                【出力フォーマット】
                - **間違えた問題の特定と概要**
                - **正しい解説とポイント**（データがなくてもAI自身が解答を作成すること）
                - **次回復習すべきタイミング**（1日後、3日後、7日後など）
                """

                # 送信データの準備
                contents = [prompt]

                for file in uploaded_files:
                    if file.type.startswith("image/"):
                        img = Image.open(file)
                        contents.append(img)
                    elif file.type == "application/pdf":
                        pdf_reader = pypdf.PdfReader(file)
                        pdf_text = ""
                        for page in pdf_reader.pages:
                            pdf_text += page.extract_text() or ""
                        contents.append(f"\n--- PDFコンテンツ ({file.name}) ---\n" + pdf_text)

                # Geminiモデルの呼び出し
                model = genai.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content(contents)

                st.subheader("📊 分析結果")
                st.write(response.text)

            except Exception as e:
                st.error(f"エラーが発生しました: {e}")
