import os
import streamlit

def patch_index():
    try:
        index_path = os.path.join(os.path.dirname(streamlit.__file__), "static", "index.html")
        if not os.path.exists(index_path):
            return False
            
        with open(index_path, "r", encoding="utf-8") as f:
            html = f.read()

        new_metadata = """
    <title>SILKS.AI | Quantitative HKJC Intelligence</title>
    <meta name="description" content="AI-Powered Real-Time Hong Kong Jockey Club Quantitative Intelligence & Win Predictor" />
    <meta property="og:title" content="SILKS.AI | Quantitative HKJC Intelligence" />
    <meta property="og:description" content="AI-Powered Real-Time Hong Kong Jockey Club Quantitative Intelligence & Win Predictor" />
    <meta property="og:site_name" content="SILKS.AI" />
    <meta property="og:type" content="website" />
    <meta property="og:url" content="https://silks-ai.onrender.com/" />
    <meta name="twitter:card" content="summary" />
    <meta name="twitter:title" content="SILKS.AI | Quantitative HKJC Intelligence" />
    <meta name="twitter:description" content="AI-Powered Real-Time Hong Kong Jockey Club Quantitative Intelligence & Win Predictor" />
        """.strip()

        if "<title>Streamlit</title>" in html:
            html = html.replace("<title>Streamlit</title>", new_metadata)
            with open(index_path, "w", encoding="utf-8") as f:
                f.write(html)
            print("Successfully patched index.html with SILKS.AI metadata.")
            return True
        elif "SILKS.AI" in html:
            import re
            html = re.sub(r'<title>SILKS\.AI.*?</title>', '<title>SILKS.AI | Quantitative HKJC Intelligence</title>', html)
            html = re.sub(r'<meta property="og:title" content=".*?" />', '<meta property="og:title" content="SILKS.AI | Quantitative HKJC Intelligence" />', html)
            html = re.sub(r'<meta name="twitter:title" content=".*?" />', '<meta name="twitter:title" content="SILKS.AI | Quantitative HKJC Intelligence" />', html)
            html = re.sub(r'<meta property="og:description" content=".*?" />', '<meta property="og:description" content="AI-Powered Real-Time Hong Kong Jockey Club Quantitative Intelligence & Win Predictor" />', html)
            html = re.sub(r'<meta name="twitter:description" content=".*?" />', '<meta name="twitter:description" content="AI-Powered Real-Time Hong Kong Jockey Club Quantitative Intelligence & Win Predictor" />', html)
            html = re.sub(r'<meta name="description" content=".*?" />', '<meta name="description" content="AI-Powered Real-Time Hong Kong Jockey Club Quantitative Intelligence & Win Predictor" />', html)
            with open(index_path, "w", encoding="utf-8") as f:
                f.write(html)
            print("Successfully updated index.html with SILKS.AI | Quantitative HKJC Intelligence.")
            return True
        return False
    except Exception as e:
        print(f"Notice: Failed to patch index.html: {e}")
        return False

if __name__ == "__main__":
    patch_index()
