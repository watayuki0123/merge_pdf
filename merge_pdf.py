import io
import os
import re
import time
import zipfile
import tempfile
import streamlit as st
import fitz  # PyMuPDF
import gdown

st.set_page_config(page_title="PDF結合＆A4サイズ統一ツール", page_icon="📄")
st.title("📄 PDF結合＆A4サイズ統一ツール")


def natural_sort_key(name):
    """
    ファイル名に含まれる数字（0, 0.9, 1, 1.9, 1.92, 2...）を数値として扱い、
    自然な順番でソートするためのキー関数
    """
    basename = os.path.basename(name).lower()
    parts = re.split(r'(\d+(?:\.\d+)?)', basename)
    return [float(part) if i % 2 == 1 else part for i, part in enumerate(parts)]


def merge_and_optimize_pdfs(pdf_items, use_compression, dpi_thresh, dpi_targ, qual):
    """
    (ファイル名, PDFバイト列) のリストを受け取り、A4統一＆結合してバイト列を返す
    """
    a4_rect = fitz.paper_rect("a4")
    doc_out = fitz.open()
    progress_bar = st.progress(0, text="PDFを結合中...")

    valid_files = []
    for idx, (fname, pdf_bytes) in enumerate(pdf_items):
        progress_bar.progress(
            (idx + 1) / len(pdf_items),
            text=f"処理中 ({idx + 1}/{len(pdf_items)}): {fname}"
        )
        try:
            doc_in = fitz.open(stream=pdf_bytes, filetype="pdf")
            if len(doc_in) > 0:
                for page in doc_in:
                    new_page = doc_out.new_page(width=a4_rect.width, height=a4_rect.height)
                    new_page.show_pdf_page(new_page.rect, doc_in, page.number)
                valid_files.append(fname)
            doc_in.close()
        except Exception as e:
            st.warning(f"⚠️ `{fname}` はPDFとして開けなかったためスキップしました ({e})")

    if len(doc_out) == 0:
        doc_out.close()
        return None, 0, []

    if use_compression:
        progress_bar.progress(1.0, text="埋め込み画像を最適化中...")
        doc_out.rewrite_images(
            dpi_threshold=int(dpi_thresh),
            dpi_target=int(dpi_targ),
            quality=int(qual)
        )

    out_bytes = doc_out.tobytes(
        garbage=4,
        deflate=True,
        clean=True
    )
    total_pages = len(doc_out)
    doc_out.close()
    return out_bytes, total_pages, valid_files


# --- 共通設定（出力ファイル名・画像圧縮オプション） ---
output_filename = st.text_input("出力ファイル名", placeholder="PENA.pdf")

use_image_compression = st.checkbox(
    "埋め込み画像を圧縮してファイルサイズを小さくする（文字やベクター図形の画質は落ちません）",
    value=False
)

dpi_threshold, dpi_target, quality = 200, 150, 75
if use_image_compression:
    col1, col2, col3 = st.columns(3)
    with col1:
        dpi_threshold = st.number_input("圧縮対象の閾値 (DPI)", value=200, step=10)
    with col2:
        dpi_target = st.number_input("目標解像度 (DPI)", value=150, step=10)
    with col3:
        quality = st.slider("JPEG画質 (Quality)", min_value=10, max_value=100, value=75)

st.divider()

# --- 取得方法の選択タブ ---
tab1, tab2 = st.tabs([
    "🔴方法A: ZIPまたはPDFを直接アップロード",
    "🔵方法B: GoogleドライブフォルダURLから取得"
])

# =====================================================================
# タブ1: GoogleドライブからダウンロードしたZIPや複数PDFを直接入れる方法
# =====================================================================
with tab1:
    st.markdown(
        "1. Googleドライブでpenaを集めたフォルダを右クリック ＞ 「ダウンロード」 をクリック（1つの `.zip` ファイルになります）\n"
        "2. ダウンロードされた **ZIPファイルそのまま**（または中のPDFファイル全部）を下の枠にドラッグ＆ドロップしてアップロードしてください。\n"
        "※もちろんGoogle関係なくZIPファイル、複数のpdfを入れて結合することもできます。"
    )

    uploaded_files = st.file_uploader(
        "ZIPファイル または PDFファイル（複数選択可）をここにドロップ",
        accept_multiple_files=True
    )

    if st.button("アップロードしたファイルを結合する", type="primary", key="btn_upload"):
        if not uploaded_files:
            st.error("ファイルをアップロードしてください。")
            st.stop()

        if not output_filename.lower().endswith(".pdf"):
            output_filename += ".pdf"

        pdf_items = []
        for uf in uploaded_files:
            raw_data = uf.read()
            # ZIPファイルがアップロードされた場合は自動解凍して中のPDFを探す
            if uf.name.lower().endswith(".zip") or zipfile.is_zipfile(io.BytesIO(raw_data)):
                with zipfile.ZipFile(io.BytesIO(raw_data)) as z:
                    for zinfo in z.infolist():
                        if not zinfo.is_dir() and ".pdf" in zinfo.filename.lower():
                            # macOS等の隠しファイルを除外
                            if "__MACOSX" not in zinfo.filename:
                                fname = os.path.basename(zinfo.filename)
                                pdf_items.append((fname, z.read(zinfo.filename)))
            elif ".pdf" in uf.name.lower():
                pdf_items.append((uf.name, raw_data))

        # 自然順ソート（0 -> 0.9 -> 1 -> 1.9 -> 1.92 -> 2...）
        pdf_items.sort(key=lambda x: natural_sort_key(x[0]))

        if not pdf_items:
            st.error("PDFファイルが見つかりませんでした。")
            st.stop()

        with st.spinner("PDFを結合・最適化しています..."):
            out_bytes, total_pages, valid_files = merge_and_optimize_pdfs(
                pdf_items, use_image_compression, dpi_threshold, dpi_target, quality
            )

        if out_bytes:
            st.success(f"🎉 {len(valid_files)}個のPDFファイル（計 {total_pages} ページ）を結合し、A4サイズに統一しました！")
            with st.expander("結合されたファイル一覧（順番確認）", expanded=True):
                for i, name in enumerate(valid_files, 1):
                    st.write(f"{i}. `{name}`")

            st.download_button(
                label="📥 結合したPDFをダウンロード",
                data=out_bytes,
                file_name=output_filename,
                mime="application/pdf",
                key="dl_upload"
            )

# =====================================================================
# タブ2: Googleドライブの共有URLから取得する方法（1ファイルずつ個別取得に改善）
# =====================================================================
with tab2:
    st.caption(
        "※Googleドライブの仕様上、短時間に連続実行するとGoogle側から一時的なアクセス制限（Failed to download）がかかることがあります。"
        "その場合は上の「方法A（ZIPアップロード）」を使うと制限なしで結合できます。"
    )
    folder_url = st.text_input(
        "Googleドライブの共有フォルダURL",
        placeholder="https://drive.google.com/drive/folders/XXXXXXXXXXXXXXXXXXXX?usp=sharing"
    )

    if st.button("URLからPDFを結合する", type="primary", key="btn_url"):
        if not folder_url:
            st.error("GoogleドライブのフォルダURLを入力してください。")
            st.stop()

        if not output_filename.lower().endswith(".pdf"):
            output_filename += ".pdf"

        with st.spinner("Googleドライブからファイル一覧を取得しています..."):
            try:
                # skip_download=True でファイル一覧（IDと名前）だけを先に取得する
                file_list = gdown.download_folder(
                    url=folder_url,
                    skip_download=True,
                    quiet=True,
                    use_cookies=False
                )
            except Exception as e:
                st.error(f"フォルダ情報の取得に失敗しました。しばらく時間を置くか、🔴方法A（ZIPアップロード）をお試しください。\n詳細: {e}")
                st.stop()

            if not file_list:
                st.error("フォルダ内のファイル一覧を取得できませんでした。")
                st.stop()

            # PDFファイルのみを抽出し、先にファイル名順でソート
            target_files = [f for f in file_list if ".pdf" in os.path.basename(f.path).lower()]
            target_files.sort(key=lambda f: natural_sort_key(f.path))

            pdf_items = []
            failed_files = []
            dl_progress = st.progress(0, text="ファイルを1つずつ安全にダウンロード中...")

            with tempfile.TemporaryDirectory() as temp_dir:
                for idx, f_obj in enumerate(target_files):
                    fname = os.path.basename(f_obj.path)
                    dl_progress.progress(
                        (idx + 1) / len(target_files),
                        text=f"ダウンロード中 ({idx + 1}/{len(target_files)}): {fname}"
                    )
                    out_path = os.path.join(temp_dir, f"{idx}.pdf")
                    try:
                        # 1ファイルずつ個別にダウンロード（レート制限回避のため少し間隔を空ける）
                        res = gdown.download(id=f_obj.id, output=out_path, quiet=True, fuzzy=True)
                        if res and os.path.exists(out_path):
                            with open(out_path, "rb") as fp:
                                pdf_items.append((fname, fp.read()))
                        else:
                            failed_files.append(fname)
                    except Exception:
                        failed_files.append(fname)
                    time.sleep(0.5)  # 連続アクセスによるブロックを緩和

            if failed_files:
                st.warning(
                    f"⚠️ 以下の {len(failed_files)} 個のファイルはGoogleドライブのアクセス制限により取得できませんでした:\n"
                    + "\n".join([f"- `{name}`" for name in failed_files])
                )

            if not pdf_items:
                st.error(
                    "現在Googleドライブ側から一時的なダウンロード制限がかかっています。"
                    "上の **「🔴方法A: ZIPまたはPDFを直接アップロード」** タブを使い結合をお試しください！"
                )
                st.stop()

            out_bytes, total_pages, valid_files = merge_and_optimize_pdfs(
                pdf_items, use_image_compression, dpi_threshold, dpi_target, quality
            )

            if out_bytes:
                st.success(f"🎉 {len(valid_files)}個のPDFファイル（計 {total_pages} ページ）を結合し、A4サイズに統一しました！")
                with st.expander("結合されたファイル一覧（順番確認）", expanded=True):
                    for i, name in enumerate(valid_files, 1):
                        st.write(f"{i}. `{name}`")

                st.download_button(
                    label="📥 結合したPDFをダウンロード",
                    data=out_bytes,
                    file_name=output_filename,
                    mime="application/pdf",
                    key="dl_url"
                )
