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
    <title>SILKS.AI | Institutional HKJC Terminal</title>
    <meta name="description" content="AI-Powered Real-Time Hong Kong Jockey Club Quantitative Terminal & Win Predictor" />
    <meta property="og:title" content="SILKS.AI | Institutional HKJC Terminal" />
    <meta property="og:description" content="AI-Powered Real-Time Hong Kong Jockey Club Quantitative Terminal & Win Predictor" />
    <meta property="og:site_name" content="SILKS.AI" />
    <meta property="og:type" content="website" />
    <meta property="og:url" content="https://silks-ai.onrender.com/" />
    <meta name="twitter:card" content="summary" />
    <meta name="twitter:title" content="SILKS.AI | Institutional HKJC Terminal" />
    <meta name="twitter:description" content="AI-Powered Real-Time Hong Kong Jockey Club Quantitative Terminal & Win Predictor" />
        """.strip()

        if "<title>Streamlit</title>" in html:
            html = html.replace("<title>Streamlit</title>", new_metadata)
            with open(index_path, "w", encoding="utf-8") as f:
                f.write(html)
            print("Successfully patched index.html with SILKS.AI metadata.")
            return True
        elif "SILKS.AI" in html:
            print("index.html is already patched with SILKS.AI metadata.")
            return True
        return False
    except Exception as e:
        print(f"Notice: Failed to patch index.html: {e}")
        return False

if __name__ == "__main__":
    patch_index()
