import os
import re
import tempfile
import streamlit as st
import fitz  # PyMuPDF
import gdown

st.set_page_config(page_title="PDF結合＆A4サイズ統一ツール", page_icon="📄")
st.title("📄 Googleドライブ PDF結合ツール")
st.write("Googleドライブの共有フォルダ内にあるPDFを名前順に結合し、すべてA4サイズに統一します。")

# --- UI: 入力フォーム ---
folder_url = st.text_input(
    "1. Googleドライブの共有フォルダURL",
    placeholder="https://drive.google.com/drive/folders/XXXXXXXXXXXXXXXXXXXX?usp=sharing"
)

output_filename = st.text_input(
    "2. 出力ファイル名",
    placeholder="pena"
)

# 元のコードにあった画像圧縮オプションをUIで切り替え可能に
use_image_compression = st.checkbox(
    "埋め込み画像を圧縮してファイルサイズを小さくする（文字やベクター図形の画質は落ちません）",
    value=False
)

if use_image_compression:
    col1, col2, col3 = st.columns(3)
    with col1:
        dpi_threshold = st.number_input("圧縮対象の閾値 (DPI)", value=200, step=10)
    with col2:
        dpi_target = st.number_input("目標解像度 (DPI)", value=150, step=10)
    with col3:
        quality = st.slider("JPEG画質 (Quality)", min_value=10, max_value=100, value=75)

# --- 実行ボタン ---
if st.button("PDFを結合する", type="primary"):
    if not folder_url:
        st.error("GoogleドライブのフォルダURLを入力してください。")
        st.stop()

    # ファイル名の末尾に .pdf がなければ補完
    if not output_filename.lower().endswith(".pdf"):
        output_filename += ".pdf"

    with st.spinner("GoogleドライブからPDFを取得して結合しています..."):
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # 1. Googleドライブの共有フォルダからファイルを一括ダウンロード
                # 一部のファイル（Googleドキュメント等）で失敗しても処理を止めないよう try-except で囲む
                try:
                    gdown.download_folder(
                        url=folder_url,
                        output=temp_dir,
                        quiet=True,
                        use_cookies=False,
                        remaining_ok=True
                    )
                except Exception as dl_err:
                    st.warning(
                        f"⚠️ 一部のファイルがダウンロードできませんでした（Googleドキュメント形式やショートカット、権限設定の可能性があります）。"
                        f"取得できたPDFのみで結合を続行します。\n\n詳細: {dl_err}"
                    )

                # 2. フォルダ内のPDFファイルを収集（「.pdf のコピー」なども含めて判定）
                pdf_paths = []
                for root, _, files in os.walk(temp_dir):
                    for f in files:
                        # 拡張子が .pdf またはファイル名に .pdf を含む（例: 〇〇.pdf のコピー）場合を対象にする
                        if ".pdf" in f.lower():
                            full_path = os.path.join(root, f)
                            # 実際にPDFとして開けるかチェック
                            try:
                                test_doc = fitz.open(full_path)
                                if test_doc.is_pdf:
                                    pdf_paths.append(full_path)
                                test_doc.close()
                            except Exception:
                                pass

                # ファイル名（大文字・小文字区別なし）でソート
                pdf_paths.sort(key=lambda p: os.path.basename(p).lower())

                if not pdf_paths:
                    st.error("結合可能なPDFファイルが見つかりませんでした。フォルダの共有設定（「リンクを知っている全員」）や中身を確認してください。")
                    st.stop()

                # 3. 統一したいサイズ（A4）の寸法を取得し、空PDFを作成
                a4_rect = fitz.paper_rect("a4")
                doc_out = fitz.open()

                progress_bar = st.progress(0, text="PDFを結合中...")

                for idx, pdf_path in enumerate(pdf_paths):
                    pdf_name = os.path.basename(pdf_path)
                    progress_bar.progress(
                        (idx + 1) / len(pdf_paths),
                        text=f"処理中 ({idx + 1}/{len(pdf_paths)}): {pdf_name}"
                    )

                    doc_in = fitz.open(pdf_path)
                    for page in doc_in:
                        new_page = doc_out.new_page(width=a4_rect.width, height=a4_rect.height)
                        new_page.show_pdf_page(new_page.rect, doc_in, page.number)
                    doc_in.close()

                # 4. オプションONの場合、埋め込み画像を最適化
                if use_image_compression:
                    progress_bar.progress(1.0, text="埋め込み画像を最適化中...")
                    doc_out.rewrite_images(
                        dpi_threshold=int(dpi_threshold),
                        dpi_target=int(dpi_target),
                        quality=int(quality)
                    )

                # 5. メモリ上のバイト列として出力
                pdf_bytes = doc_out.tobytes(
                    garbage=4,
                    deflate=True,
                    clean=True
                )
                total_pages = len(doc_out)
                doc_out.close()

            # --- 完了表示とダウンロードボタン ---
            st.success(f"🎉 {len(pdf_paths)}個のPDFファイル（計 {total_pages} ページ）を結合し、A4サイズに統一しました！")

            with st.expander("結合されたファイル一覧（順番確認）", expanded=True):
                for i, p in enumerate(pdf_paths, 1):
                    st.write(f"{i}. `{os.path.basename(p)}`")

            st.download_button(
                label="📥 結合したPDFをダウンロード",
                data=pdf_bytes,
                file_name=output_filename,
                mime="application/pdf"
            )

        except Exception as e:
            st.error(f"処理中にエラーが発生しました: {e}")
